"""
Universe maintenance
====================
Decides *which* of the ~38,000 scheme rows AMFI publishes are things a person
could actually invest in today, and repairs the derived columns on
``scheme`` (AMC, category, asset class, plan, option, NAV summary).

Why this is a separate stage
----------------------------
Everything the product shows is a ranking, and a ranking is only as good as
its universe.  The raw AMFI master is dominated by dead weight:

* ~15,000 matured Fixed Maturity Plans, closed-ended by construction;
* thousands of IDCW plans, whose NAV drops on every payout and whose returns
  are therefore not comparable with a Growth plan of the same fund;
* ~7,700 schemes with fewer than 30 NAV prints in total;
* schemes whose last NAV print is years old.

Leaving those in does not just add noise — it distorts every percentile, and
percentiles are what the conviction label is built from.

The rules
---------
A scheme is **investable** when all of these hold:

1. Its category is not a closed-ended wrapper (FMP / interval / capital
   protection).
2. Its option is Growth — one comparable share class per fund.
3. It has a NAV print within :data:`STALE_AFTER_DAYS` of the newest NAV print
   in the database (so the cut-off follows the data, not the wall clock).
4. It has at least :data:`MIN_NAV_HISTORY` NAV prints.
"""

from __future__ import annotations

import asyncio
from datetime import date

from loguru import logger
from sqlalchemy import text

from backend.analytics.taxonomy import EXCLUDED_CATEGORIES, parse_scheme
from backend.db.session import engine

#: A scheme whose latest NAV is older than this (relative to the freshest NAV
#: in the database) is treated as dormant or wound up.
STALE_AFTER_DAYS = 21

#: Below this many prints nothing meaningful can be computed.
MIN_NAV_HISTORY = 60

#: Name fragments that mark a share class nobody can actually buy.  These plans
#: keep publishing a NAV for years after they stop accepting money, and because
#: they are usually tiny and low-volatility they rank suspiciously well.
DEAD_CLASS_PATTERNS = (
    "%discontinued%",
    "%defunct%",
    "%unclaimed%",
    "%institutional%",
    "%segregated portfolio%",
    "%investor education%",
)


async def reclassify_schemes(batch_size: int = 5000) -> int:
    """
    Re-derive AMC, category, asset class, plan and option from scheme names.

    Only touches schemes AMFI did not classify for us — wound-up funds that no
    longer appear in the daily file.  AMFI's own SEBI category is authoritative
    and must never be overwritten by a guess from the name.
    """
    logger.info("Reclassifying schemes absent from the AMFI file …")

    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT id, scheme_name FROM scheme "
                    "WHERE amfi_classified IS NULL OR amfi_classified = 0"
                )
            )
        ).all()

    updates = [
        {"id": scheme_id, **parse_scheme(scheme_name)} for scheme_id, scheme_name in rows
    ]

    if not updates:
        return 0

    sql = text(
        """
        UPDATE scheme
           SET amc_name = :amc_name,
               category = :category,
               asset_class = :asset_class,
               plan_type = :plan_type,
               option_type = :option_type
         WHERE id = :id
        """
    )
    async with engine.begin() as conn:
        for start in range(0, len(updates), batch_size):
            await conn.execute(sql, updates[start : start + batch_size])

    logger.info(f"Reclassified {len(updates)} name-only schemes.")
    return len(updates)


async def refresh_nav_summary() -> int:
    """
    Denormalise NAV coverage onto the scheme row.

    One aggregate scan replaces the per-request ``COUNT(*)`` and ``MAX(date)``
    subqueries the API used to run against a 3M-row table for every page of
    results.
    """
    logger.info("Refreshing NAV summary columns …")
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                UPDATE scheme
                   SET nav_count = COALESCE(agg.cnt, 0),
                       nav_latest = agg.last_nav,
                       nav_latest_date = agg.last_date,
                       nav_first_date = agg.first_date
                  FROM (
                        SELECT scheme_id,
                               COUNT(*) AS cnt,
                               MIN(nav_date) AS first_date,
                               MAX(nav_date) AS last_date,
                               (SELECT nav FROM nav_record x
                                 WHERE x.scheme_id = n.scheme_id
                              ORDER BY x.nav_date DESC LIMIT 1) AS last_nav
                          FROM nav_record n
                      GROUP BY scheme_id
                  ) AS agg
                 WHERE agg.scheme_id = scheme.id
                """
            )
        )
        # Schemes with no NAV at all still need consistent zeros.
        await conn.execute(
            text(
                "UPDATE scheme SET nav_count = 0 "
                "WHERE nav_count IS NULL OR nav_latest_date IS NULL"
            )
        )
        count = await conn.scalar(text("SELECT COUNT(*) FROM scheme WHERE nav_count > 0"))

    logger.info(f"NAV summary refreshed for {count} schemes.")
    return int(count or 0)


async def refresh_inception_dates() -> int:
    """Use the first NAV print as inception when AMFI gives us nothing better."""
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                "UPDATE scheme SET inception_date = nav_first_date "
                "WHERE inception_date IS NULL AND nav_first_date IS NOT NULL"
            )
        )
    return result.rowcount or 0


async def refresh_investable_flags() -> dict[str, int]:
    """Apply the investability rules and report how many schemes each one removes."""
    excluded = ", ".join(f"'{c}'" for c in sorted(EXCLUDED_CATEGORIES))
    dead_class = " AND ".join(
        f"LOWER(scheme_name) NOT LIKE '{pattern}'" for pattern in DEAD_CLASS_PATTERNS
    )

    async with engine.begin() as conn:
        newest = await conn.scalar(text("SELECT MAX(nav_date) FROM nav_record"))
        if newest is None:
            logger.warning("No NAV data — cannot determine the investable universe.")
            return {"investable": 0}

        await conn.execute(
            text(
                f"""
                UPDATE scheme
                   SET is_active = CASE
                            WHEN nav_latest_date >= date(:newest, '-' || :stale || ' days')
                            THEN 1 ELSE 0 END,
                       is_investable = CASE
                            WHEN nav_latest_date >= date(:newest, '-' || :stale || ' days')
                             AND nav_count >= :min_history
                             AND option_type = 'Growth'
                             AND category NOT IN ({excluded})
                             AND {dead_class}
                            THEN 1 ELSE 0 END
                """
            ),
            {"newest": str(newest), "stale": STALE_AFTER_DAYS, "min_history": MIN_NAV_HISTORY},
        )

        stats = {
            "total": await conn.scalar(text("SELECT COUNT(*) FROM scheme")),
            "active": await conn.scalar(text("SELECT COUNT(*) FROM scheme WHERE is_active = 1")),
            "investable": await conn.scalar(
                text("SELECT COUNT(*) FROM scheme WHERE is_investable = 1")
            ),
        }

    logger.info(
        f"Universe: {stats['investable']} investable / {stats['active']} active "
        f"/ {stats['total']} total (NAV as of {newest})."
    )
    return {k: int(v or 0) for k, v in stats.items()}


async def ensure_indexes() -> None:
    """
    Create the covering indexes the API's hot queries need.

    ``CREATE INDEX IF NOT EXISTS`` is idempotent, so this is safe to run on
    every refresh.
    """
    statements = [
        "CREATE INDEX IF NOT EXISTS ix_scheme_universe "
        "ON scheme (is_investable, category, asset_class)",
        "CREATE INDEX IF NOT EXISTS ix_scheme_amc ON scheme (amc_name)",
        "CREATE INDEX IF NOT EXISTS ix_nav_scheme_date ON nav_record (scheme_id, nav_date)",
        "CREATE INDEX IF NOT EXISTS ix_features_date_scheme "
        "ON fund_features (feature_date, scheme_id)",
        "CREATE INDEX IF NOT EXISTS ix_score_date_composite "
        "ON fund_score (score_date, composite_score DESC)",
        "CREATE INDEX IF NOT EXISTS ix_score_scheme_date ON fund_score (scheme_id, score_date)",
    ]
    async with engine.begin() as conn:
        for statement in statements:
            await conn.execute(text(statement))
    logger.info("Indexes ensured.")


async def refresh_universe() -> dict[str, int]:
    """Full universe maintenance pass — safe and idempotent."""
    await ensure_indexes()
    await reclassify_schemes()
    await refresh_nav_summary()
    await refresh_inception_dates()
    return await refresh_investable_flags()


if __name__ == "__main__":
    asyncio.run(refresh_universe())
