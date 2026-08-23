"""
Backfill NAV history for the investable universe.

AMFI's daily file carries one print per scheme.  Every return, volatility and
drawdown number in the product needs years of prints, which come from
api.mfapi.in.  This script pulls history for every open-ended Growth plan that
is still pricing, then repairs the derived columns.

    python -m scripts.backfill_history [--years 11] [--concurrency 12] [--limit N]
"""

from __future__ import annotations

import argparse
import asyncio
import time

from loguru import logger
from sqlalchemy import text

from backend.ingestion.amfi_client import AMFIClient
from backend.ingestion.universe import refresh_universe
from backend.db.session import engine

CANDIDATE_SQL = """
SELECT scheme_code
  FROM scheme
 WHERE is_active = 1
   AND option_type = 'Growth'
   AND category <> 'Fixed Maturity Plan'
 ORDER BY nav_count ASC, scheme_code
"""


async def main(years: int, concurrency: int, limit: int | None) -> None:
    async with engine.connect() as conn:
        rows = await conn.execute(text(CANDIDATE_SQL))
        codes = [row[0] for row in rows.all()]

    if limit:
        codes = codes[:limit]

    logger.info(f"Backfilling {len(codes)} schemes ({years}y of history, {concurrency} in flight) …")
    started = time.perf_counter()

    stats = await AMFIClient().backfill_history(codes, years=years, concurrency=concurrency)

    logger.info(f"Backfill took {time.perf_counter() - started:.0f}s: {stats}")
    await refresh_universe()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", type=int, default=11)
    parser.add_argument("--concurrency", type=int, default=12)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    asyncio.run(main(args.years, args.concurrency, args.limit))
