"""
APScheduler — Scheduled Data Ingestion Jobs
=============================================
Two jobs:
  1. nav_job   — daily: pull AMFI NAVAll.txt at ~9 PM IST (after AMFI publishes)
  2. news_job  — hourly: pull all configured RSS feeds

Run standalone:
    python -m backend.ingestion.scheduler

Or import `start_scheduler()` and call it from the FastAPI lifespan handler.
"""

from __future__ import annotations

import asyncio
import signal
import sys

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger

from backend.config import settings


# ── Job functions ─────────────────────────────────────────────────────────────

async def nav_job() -> None:
    """Pull daily NAV from AMFI and persist to DB."""
    from backend.ingestion.amfi_client import AMFIClient
    try:
        client = AMFIClient()
        count = await client.fetch_latest_nav()
        logger.info(f"[nav_job] {count} NAV rows upserted.")
    except Exception as exc:
        logger.error(f"[nav_job] Failed: {exc}", exc_info=True)


async def news_job() -> None:
    """Pull all RSS feeds and score new articles."""
    from backend.ingestion.news_scraper import NewsScraper
    from backend.nlp.sentiment import SentimentPipeline
    try:
        scraper = NewsScraper()
        summary = await scraper.run_all()
        total_new = sum(summary.values())
        logger.info(f"[news_job] Articles ingested: {summary}")

        if total_new > 0:
            # Score newly ingested articles immediately
            pipeline = SentimentPipeline()
            scored = await pipeline.score_pending_articles(limit=total_new + 50)
            logger.info(f"[news_job] {scored} articles scored for sentiment.")
    except Exception as exc:
        logger.error(f"[news_job] Failed: {exc}", exc_info=True)


async def score_job() -> None:
    """
    Re-compute features and scores for all active schemes.
    Runs daily after the NAV job completes.
    """
    from backend.features.feature_builder import FeatureBuilder
    from backend.scoring.rule_based import RuleBasedScorer
    from backend.scoring.risk_model import RiskModel
    try:
        builder = FeatureBuilder()
        await builder.build_all_features()
        logger.info("[score_job] Features rebuilt.")

        scorer = RuleBasedScorer()
        await scorer.score_all()
        logger.info("[score_job] Scores updated.")
        
        # Add risk scoring
        try:
            risk_model = RiskModel()
            await risk_model.score_all_risks()
            logger.info("[score_job] Risk scores updated.")
        except FileNotFoundError:
            logger.warning("[score_job] Risk model not trained yet, skipping risk scoring.")
        except Exception as exc:
            logger.error(f"[score_job] Risk scoring failed: {exc}")
    except Exception as exc:
        logger.error(f"[score_job] Failed: {exc}", exc_info=True)


# ── Scheduler setup ───────────────────────────────────────────────────────────

def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")

    # Daily NAV pull at 21:15 IST (AMFI typically publishes by ~9 PM)
    scheduler.add_job(
        nav_job,
        CronTrigger(hour=21, minute=15, timezone="Asia/Kolkata"),
        id="nav_daily",
        name="AMFI NAV daily pull",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # Daily score refresh at 22:00 IST (after NAV job)
    scheduler.add_job(
        score_job,
        CronTrigger(hour=22, minute=0, timezone="Asia/Kolkata"),
        id="score_daily",
        name="Feature + score refresh",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # News pull every hour
    scheduler.add_job(
        news_job,
        IntervalTrigger(seconds=settings.news_pull_interval_seconds),
        id="news_hourly",
        name="RSS news pull",
        replace_existing=True,
        misfire_grace_time=600,
    )

    return scheduler


_scheduler: AsyncIOScheduler | None = None


def start_scheduler() -> AsyncIOScheduler:
    """Start the global scheduler. Safe to call from FastAPI lifespan."""
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


# ── Standalone entry point ────────────────────────────────────────────────────

async def _run_forever() -> None:
    from backend.db.session import init_db

    logger.info("Initialising DB …")
    await init_db()

    scheduler = start_scheduler()
    logger.info("Scheduler running. Press Ctrl+C to stop.")

    # Kick off an immediate news pull on startup so we have data right away
    asyncio.create_task(news_job())

    loop = asyncio.get_running_loop()

    stop_event = asyncio.Event()

    def _handle_signal():
        logger.info("Shutdown signal received.")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle_signal)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler for all signals
            pass

    await stop_event.wait()
    stop_scheduler()


if __name__ == "__main__":
    asyncio.run(_run_forever())
