"""
Scheduled jobs
==============
The daily pipeline, and the APScheduler wiring that runs it unattended.

Pipeline order matters
----------------------
Each stage depends on the previous one's output::

    NAV pull  →  universe refresh  →  features  →  scores  →  risk

The universe refresh has to run *after* the NAV pull, because investability is
defined relative to the freshest NAV print in the database.  Risk has to run
*after* scoring, because it updates the ``fund_score`` rows the scorer writes.
The previous version ran features and scoring concurrently with the NAV pull
via two independent ``create_task`` calls, so a refresh scored the previous
day's data.

Run standalone:

    python -m backend.ingestion.scheduler          # long-running scheduler
    python -m backend.ingestion.scheduler --once   # one pipeline pass, then exit
"""

from __future__ import annotations

import argparse
import asyncio
import signal
from datetime import date

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger

from backend.config import settings

#: One pipeline at a time.  A manual refresh landing on top of the nightly run
#: would have both stages writing the same feature rows.
_PIPELINE_LOCK = asyncio.Lock()


# ── Stages ────────────────────────────────────────────────────────────────────

async def nav_job() -> dict[str, int]:
    """Pull AMFI's daily NAV file and sync the scheme master."""
    from backend.ingestion.amfi_client import AMFIClient

    return await AMFIClient().fetch_latest_nav()


async def universe_job() -> dict[str, int]:
    from backend.ingestion.universe import refresh_universe

    return await refresh_universe()


async def feature_job(as_of: date | None = None) -> int:
    from backend.features.feature_builder import FeatureBuilder

    return await FeatureBuilder().build_all(as_of=as_of)


async def score_job(as_of: date | None = None) -> int:
    """Composite score, then risk — risk updates the rows scoring creates."""
    from backend.scoring.risk_model import RiskModel
    from backend.scoring.rule_based import RuleBasedScorer

    written = await RuleBasedScorer().score_all(as_of=as_of)
    if written:
        await RiskModel().score_all_risks(as_of=as_of)
    return written


async def news_job() -> int:
    """Pull RSS feeds and score anything new for sentiment."""
    from backend.ingestion.news_scraper import NewsScraper
    from backend.nlp.sentiment import SentimentPipeline

    try:
        summary = await NewsScraper().run_all()
    except Exception as exc:
        logger.error(f"[news] ingestion failed: {exc}")
        return 0

    total_new = sum(summary.values())
    logger.info(f"[news] articles ingested: {summary}")
    if total_new <= 0:
        return 0

    try:
        scored = await SentimentPipeline().score_pending_articles(limit=total_new + 50)
        logger.info(f"[news] {scored} articles scored.")
        return scored
    except Exception as exc:
        logger.error(f"[news] sentiment scoring failed: {exc}")
        return 0


# ── Full pipeline ─────────────────────────────────────────────────────────────

async def daily_pipeline(as_of: date | None = None, pull_nav: bool = True) -> dict[str, object]:
    """NAV → universe → features → scores → risk, in order, one at a time."""
    if _PIPELINE_LOCK.locked():
        logger.warning("Pipeline already running — skipping this trigger.")
        return {"status": "skipped"}

    async with _PIPELINE_LOCK:
        results: dict[str, object] = {"as_of": str(as_of or date.today())}
        try:
            if pull_nav:
                results["nav"] = await nav_job()
            results["universe"] = await universe_job()
            results["features"] = await feature_job(as_of)
            results["scores"] = await score_job(as_of)
            results["status"] = "complete"
            logger.info(f"Daily pipeline complete: {results}")
        except Exception as exc:
            results["status"] = "failed"
            results["error"] = str(exc)
            logger.exception(f"Daily pipeline failed: {exc}")
        return results


# ── Scheduler ─────────────────────────────────────────────────────────────────

def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")

    # AMFI publishes the day's NAV file by ~21:00 IST.
    scheduler.add_job(
        daily_pipeline,
        CronTrigger(hour=21, minute=30, timezone="Asia/Kolkata"),
        id="daily_pipeline",
        name="NAV → universe → features → scores",
        replace_existing=True,
        misfire_grace_time=7200,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        news_job,
        IntervalTrigger(seconds=settings.news_pull_interval_seconds),
        id="news_hourly",
        name="RSS news pull",
        replace_existing=True,
        misfire_grace_time=900,
        max_instances=1,
        coalesce=True,
    )
    return scheduler


_scheduler: AsyncIOScheduler | None = None


def start_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        return _scheduler
    _scheduler = build_scheduler()
    _scheduler.start()
    logger.info("Scheduler started.")
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped.")


# ── Entry point ───────────────────────────────────────────────────────────────

async def _run_forever() -> None:
    from backend.db.session import init_db

    await init_db()
    start_scheduler()
    logger.info("Scheduler running. Press Ctrl+C to stop.")

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass          # Windows does not support all signal handlers

    try:
        await stop_event.wait()
    except KeyboardInterrupt:
        pass
    finally:
        stop_scheduler()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Run one pipeline pass and exit.")
    parser.add_argument("--no-nav", action="store_true", help="Skip the AMFI download.")
    args = parser.parse_args()

    if args.once:
        asyncio.run(daily_pipeline(pull_nav=not args.no_nav))
    else:
        asyncio.run(_run_forever())
