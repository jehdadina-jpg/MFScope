"""
Run the MFScope data pipeline end to end.

    python -m scripts.pipeline                 # everything, including the AMFI pull
    python -m scripts.pipeline --no-nav        # recompute from data already stored
    python -m scripts.pipeline --stage scores  # one stage only

Stages
------
nav       Download AMFI's daily file; sync scheme master and today's NAV.
universe  Re-derive classification, NAV summary and the investable universe.
features  Rebuild the point-in-time feature vector.
scores    Composite score + peer rank, then the riskometer.
"""

from __future__ import annotations

import argparse
import asyncio
import time
from datetime import date

from loguru import logger

STAGES = ("nav", "universe", "features", "scores")


async def run(stages: tuple[str, ...], as_of: date | None) -> None:
    from backend.db.migrate import reconcile_schema
    from backend.ingestion.scheduler import feature_job, nav_job, score_job, universe_job

    await reconcile_schema()

    runners = {
        "nav": nav_job,
        "universe": universe_job,
        "features": lambda: feature_job(as_of),
        "scores": lambda: score_job(as_of),
    }

    for stage in stages:
        started = time.perf_counter()
        logger.info(f"── {stage} ──")
        result = await runners[stage]()
        logger.info(f"── {stage} done in {time.perf_counter() - started:.1f}s → {result}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=STAGES, help="Run a single stage.")
    parser.add_argument("--no-nav", action="store_true", help="Skip the AMFI download.")
    parser.add_argument("--as-of", type=date.fromisoformat, default=None)
    args = parser.parse_args()

    if args.stage:
        selected: tuple[str, ...] = (args.stage,)
    elif args.no_nav:
        selected = tuple(s for s in STAGES if s != "nav")
    else:
        selected = STAGES

    asyncio.run(run(selected, args.as_of))
