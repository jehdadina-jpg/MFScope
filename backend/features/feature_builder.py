"""
Feature Builder
===============
Turns raw NAV history into the point-in-time feature vector that the scorer
consumes.  One row per ``(scheme, feature_date)`` in ``fund_features``.

Design notes
------------
* **All maths lives in** :mod:`backend.analytics`.  This module is only
  responsible for loading, orchestrating and persisting.
* **Bulk path.**  A full rebuild touches ~1.5M NAV rows.  Doing that with one
  round trip per scheme (the old design) meant tens of thousands of async
  queries.  :meth:`FeatureBuilder.build_all` instead streams the NAV table
  once, ordered by scheme, and computes as it goes.
* **Two passes.**  Category-relative context (peer average return) can only be
  computed once every scheme in the category has its own numbers, so it is
  filled in after the per-scheme pass.  The old single-pass version read the
  averages while it was still writing them, which made results depend on
  scheduling order.
* **No leakage.**  Every metric is derived only from NAV prints dated on or
  before ``as_of``.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, AsyncIterator, Iterable

import numpy as np
import pandas as pd
from loguru import logger
from sqlalchemy import func, select, text, update

from backend.analytics import metrics
from backend.analytics.nav import NavSeries, blend_benchmark, build_series
from backend.db.models import FundFeatures, FundMetadata, NAVRecord, NewsSentiment, Scheme
from backend.db.session import AsyncSessionLocal, engine

#: Columns owned by the metric layer, in the order they are written.
_METRIC_COLUMNS = tuple(
    c.name
    for c in FundFeatures.__table__.columns
    if c.name not in {"id", "scheme_id", "feature_date", "computed_at"}
)

#: Minimum NAV prints before any metric is attempted.
MIN_NAV_POINTS = 60

#: Categories used to synthesise the market proxy for alpha/beta.
BENCHMARK_CATEGORIES = ("Index - Nifty 50", "Index - Sensex")


# ── Benchmark ─────────────────────────────────────────────────────────────────

async def build_market_benchmark(as_of: date, lookback_days: int = 1400) -> pd.Series | None:
    """
    Synthesise a Nifty-50 total-return proxy from the NAV of index funds that
    track it.  We do not have an index feed, but we do have dozens of funds
    whose whole job is to replicate one — the cross-sectional median of their
    daily returns is a clean, survivorship-light stand-in.
    """
    since = as_of - timedelta(days=lookback_days)
    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            select(NAVRecord.scheme_id, NAVRecord.nav_date, NAVRecord.nav)
            .join(Scheme, Scheme.id == NAVRecord.scheme_id)
            .where(Scheme.category.in_(BENCHMARK_CATEGORIES))
            .where(Scheme.plan_type == "Direct")
            .where(Scheme.option_type == "Growth")
            .where(Scheme.is_investable.is_(True))
            .where(NAVRecord.nav_date >= since)
            .where(NAVRecord.nav_date <= as_of)
            .order_by(NAVRecord.scheme_id, NAVRecord.nav_date)
        )
        data = rows.all()

    if not data:
        logger.warning("No index-fund NAV available — alpha/beta will be unavailable.")
        return None

    grouped: dict[int, list[tuple[date, float]]] = defaultdict(list)
    for scheme_id, nav_date, nav in data:
        grouped[scheme_id].append((nav_date, float(nav)))

    series_list: list[pd.Series] = []
    for points in grouped.values():
        if len(points) < 200:
            continue
        dates, values = zip(*points)
        cleaned = NavSeries(build_series(dates, values)).adjusted
        series_list.append(cleaned)

    benchmark = blend_benchmark(series_list)
    if benchmark is None:
        logger.warning("Benchmark blend produced no series (too few members).")
        return None

    logger.info(
        f"Market proxy built from {len(series_list)} index funds "
        f"({benchmark.index[0].date()} → {benchmark.index[-1].date()}, {len(benchmark)} points)."
    )
    return benchmark


# ── Sentiment ─────────────────────────────────────────────────────────────────

async def load_sentiment_by_scheme(as_of: date) -> dict[int, dict[str, float | None]]:
    """
    Rolling sentiment per scheme, loaded in one query.

    Scheme-tagged articles and category-tagged articles are merged; when the
    news tables are empty (the common case for a fresh install) every scheme
    simply gets no sentiment and the scorer drops that component instead of
    imputing a neutral value.
    """
    from backend.db.models import NewsArticle

    since = as_of - timedelta(days=90)
    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            select(
                NewsSentiment.scheme_id,
                NewsSentiment.category,
                NewsSentiment.compound_score,
                NewsArticle.published_at,
            )
            .join(NewsArticle, NewsSentiment.article_id == NewsArticle.id)
            .where(NewsArticle.published_at >= since)
        )
        records = rows.all()

    if not records:
        return {}

    category_map: dict[str, list[int]] = defaultdict(list)
    async with AsyncSessionLocal() as session:
        scheme_rows = await session.execute(
            select(Scheme.id, Scheme.category).where(Scheme.is_investable.is_(True))
        )
        for scheme_id, category in scheme_rows.all():
            category_map[category].append(scheme_id)

    buckets: dict[int, list[tuple[pd.Timestamp, float]]] = defaultdict(list)
    for scheme_id, category, compound, published_at in records:
        if compound is None or published_at is None:
            continue
        stamp = pd.Timestamp(published_at)
        if scheme_id is not None:
            buckets[scheme_id].append((stamp, float(compound)))
        elif category:
            for sid in category_map.get(category, ()):
                buckets[sid].append((stamp, float(compound)))

    as_of_ts = pd.Timestamp(as_of)
    cutoff_7d = as_of_ts - pd.Timedelta(days=7)
    cutoff_30d = as_of_ts - pd.Timedelta(days=30)

    out: dict[int, dict[str, float | None]] = {}
    for scheme_id, points in buckets.items():
        stamps = np.array([p[0].value for p in points])
        scores = np.array([p[1] for p in points], dtype="float64")
        mask_7d = stamps >= cutoff_7d.value
        mask_30d = stamps >= cutoff_30d.value
        count_7d = int(mask_7d.sum())
        baseline = scores.size / 90.0 * 7.0
        out[scheme_id] = {
            "sentiment_7d": float(scores[mask_7d].mean()) if count_7d else None,
            "sentiment_30d": float(scores[mask_30d].mean()) if mask_30d.any() else None,
            "news_volume_7d": float(count_7d),
            "news_volume_spike": float(count_7d / baseline) if baseline > 0 else None,
        }
    return out


# ── Metadata ──────────────────────────────────────────────────────────────────

async def load_latest_metadata() -> dict[int, FundMetadata]:
    """Most recent fundamental snapshot per scheme, in one pass."""
    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            select(FundMetadata).order_by(FundMetadata.scheme_id, FundMetadata.as_of_date.desc())
        )
        latest: dict[int, FundMetadata] = {}
        for meta in rows.scalars().all():
            latest.setdefault(meta.scheme_id, meta)
    return latest


async def load_aum_growth() -> dict[int, float]:
    """Percent change between the two most recent AUM snapshots per scheme."""
    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            select(FundMetadata.scheme_id, FundMetadata.aum_crore, FundMetadata.as_of_date)
            .where(FundMetadata.aum_crore.is_not(None))
            .order_by(FundMetadata.scheme_id, FundMetadata.as_of_date.desc())
        )
        by_scheme: dict[int, list[float]] = defaultdict(list)
        for scheme_id, aum, _ in rows.all():
            if len(by_scheme[scheme_id]) < 2:
                by_scheme[scheme_id].append(float(aum))

    growth: dict[int, float] = {}
    for scheme_id, values in by_scheme.items():
        if len(values) == 2 and values[1] > 0:
            growth[scheme_id] = (values[0] - values[1]) / values[1] * 100.0
    return growth


# ── NAV streaming ─────────────────────────────────────────────────────────────

async def _stream_nav_by_scheme(
    scheme_ids: set[int],
    as_of: date,
    lookback_days: int,
    only_investable: bool = True,
) -> AsyncIterator[tuple[int, list[date], list[float]]]:
    """
    Yield ``(scheme_id, dates, navs)`` for each scheme, reading the NAV table
    in one ordered scan.

    SQLite streams this comfortably; the alternative — a query per scheme —
    costs ~7,000 round trips per rebuild.
    """
    since = as_of - timedelta(days=lookback_days)
    # Filtering in SQL rather than in Python keeps ~1.4M rows belonging to
    # matured FMPs and dormant plans out of the transfer entirely.
    universe_filter = (
        "JOIN scheme s ON s.id = n.scheme_id AND s.is_investable = 1"
        if only_investable
        else ""
    )
    sql = text(
        f"""
        SELECT n.scheme_id, n.nav_date, n.nav
        FROM nav_record n
        {universe_filter}
        WHERE n.nav_date >= :since AND n.nav_date <= :as_of
        ORDER BY n.scheme_id, n.nav_date
        """
    )

    current_id: int | None = None
    dates: list[date] = []
    navs: list[float] = []

    async with engine.connect() as conn:
        result = await conn.stream(sql, {"since": since.isoformat(), "as_of": as_of.isoformat()})
        async for scheme_id, nav_date, nav in result:
            if scheme_id != current_id:
                if current_id is not None and current_id in scheme_ids and dates:
                    yield current_id, dates, navs
                current_id, dates, navs = scheme_id, [], []
            if scheme_id in scheme_ids:
                dates.append(nav_date)
                navs.append(nav)

    if current_id is not None and current_id in scheme_ids and dates:
        yield current_id, dates, navs


# ── Builder ───────────────────────────────────────────────────────────────────

class FeatureBuilder:
    """Computes and persists the feature vector for the investable universe."""

    def __init__(self, lookback_days: int = 365 * 11) -> None:
        self.lookback_days = lookback_days

    # ── Single scheme (used by tests and ad-hoc inspection) ──────────────────

    async def build_features(
        self,
        scheme_id: int,
        as_of: date | None = None,
        benchmark_returns: pd.Series | None = None,
    ) -> dict[str, Any] | None:
        as_of = as_of or date.today()
        since = as_of - timedelta(days=self.lookback_days)

        async with AsyncSessionLocal() as session:
            scheme = await session.get(Scheme, scheme_id)
            if scheme is None:
                return None
            rows = await session.execute(
                select(NAVRecord.nav_date, NAVRecord.nav)
                .where(NAVRecord.scheme_id == scheme_id)
                .where(NAVRecord.nav_date >= since)
                .where(NAVRecord.nav_date <= as_of)
                .order_by(NAVRecord.nav_date)
            )
            data = rows.all()
            meta = await session.scalar(
                select(FundMetadata)
                .where(FundMetadata.scheme_id == scheme_id)
                .order_by(FundMetadata.as_of_date.desc())
                .limit(1)
            )

        if len(data) < MIN_NAV_POINTS:
            return None

        dates = [row[0] for row in data]
        values = [float(row[1]) for row in data]
        feature = self._compute(scheme_id, as_of, dates, values, benchmark_returns)
        if feature is None:
            return None

        if meta is not None:
            feature.update(
                expense_ratio=meta.expense_ratio,
                aum_crore=meta.aum_crore,
                manager_tenure_years=meta.manager_tenure_years,
                portfolio_turnover=meta.portfolio_turnover,
            )
        return feature

    # ── Core computation ─────────────────────────────────────────────────────

    def _compute(
        self,
        scheme_id: int,
        as_of: date,
        dates: Iterable[date],
        values: Iterable[float],
        benchmark_returns: pd.Series | None,
    ) -> dict[str, Any] | None:
        series = build_series(dates, values)
        if len(series) < MIN_NAV_POINTS:
            return None

        nav = NavSeries(series)
        computed = metrics.compute_all(nav, benchmark_returns=benchmark_returns, as_of=as_of)

        feature: dict[str, Any] = {"scheme_id": scheme_id, "feature_date": as_of}
        for column in _METRIC_COLUMNS:
            feature[column] = computed.get(column)
        return feature

    # ── Full rebuild ─────────────────────────────────────────────────────────

    async def build_all(
        self,
        as_of: date | None = None,
        only_investable: bool = True,
    ) -> int:
        as_of = as_of or date.today()

        async with AsyncSessionLocal() as session:
            stmt = select(Scheme.id, Scheme.category)
            if only_investable:
                stmt = stmt.where(Scheme.is_investable.is_(True))
            else:
                stmt = stmt.where(Scheme.is_active.is_(True))
            rows = (await session.execute(stmt)).all()

        universe = {scheme_id: category for scheme_id, category in rows}
        if not universe:
            logger.warning("Investable universe is empty — run the universe refresh first.")
            return 0

        logger.info(f"Building features for {len(universe)} schemes as of {as_of} …")

        benchmark = await build_market_benchmark(as_of)
        benchmark_returns = benchmark.pct_change().dropna() if benchmark is not None else None

        sentiment = await load_sentiment_by_scheme(as_of)
        metadata = await load_latest_metadata()
        aum_growth = await load_aum_growth()

        scheme_ids = set(universe)
        batch: list[dict[str, Any]] = []
        built = 0
        seen = 0

        async for scheme_id, dates, values in _stream_nav_by_scheme(
            scheme_ids, as_of, self.lookback_days, only_investable=only_investable
        ):
            seen += 1
            try:
                feature = self._compute(scheme_id, as_of, dates, values, benchmark_returns)
            except Exception as exc:  # a single bad series must not stop the rebuild
                logger.warning(f"Feature build failed for scheme {scheme_id}: {exc}")
                continue
            if feature is None:
                continue

            meta = metadata.get(scheme_id)
            if meta is not None:
                feature["expense_ratio"] = meta.expense_ratio
                feature["aum_crore"] = meta.aum_crore
                feature["manager_tenure_years"] = meta.manager_tenure_years
                feature["portfolio_turnover"] = meta.portfolio_turnover
                if meta.category_rank and meta.category_total:
                    feature["category_rank_pct"] = (meta.category_rank - 1) / meta.category_total
            feature["aum_growth_3m"] = aum_growth.get(scheme_id)
            feature.update(sentiment.get(scheme_id, {}))

            batch.append(feature)
            built += 1

            if len(batch) >= 1000:
                await self._flush(batch, as_of)
                batch.clear()
                logger.info(f"  … {built} schemes computed")

        if batch:
            await self._flush(batch, as_of)

        await self._fill_category_context(as_of)
        logger.info(f"Feature build complete: {built} feature rows from {seen} NAV series.")
        return built

    # ── Persistence ──────────────────────────────────────────────────────────

    async def _flush(self, batch: list[dict[str, Any]], as_of: date) -> None:
        """Upsert a batch in one statement using SQLite's ON CONFLICT clause."""
        if not batch:
            return

        columns = ["scheme_id", "feature_date", *_METRIC_COLUMNS]
        placeholders = ", ".join(f":{c}" for c in columns)
        updates = ", ".join(f"{c} = excluded.{c}" for c in _METRIC_COLUMNS)
        sql = text(
            f"INSERT INTO fund_features ({', '.join(columns)}) VALUES ({placeholders}) "
            f"ON CONFLICT(scheme_id, feature_date) DO UPDATE SET {updates}"
        )

        payload = []
        for row in batch:
            record = {c: row.get(c) for c in columns}
            record["feature_date"] = as_of.isoformat()
            payload.append(record)

        async with engine.begin() as conn:
            await conn.execute(sql, payload)

    async def _fill_category_context(self, as_of: date) -> None:
        """
        Second pass: peer-average 1Y return per category.

        Runs only after every scheme has been written, so the average is over
        the complete category rather than whatever happened to be persisted
        first.
        """
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    UPDATE fund_features
                       SET category_avg_return_1y = (
                            SELECT AVG(f2.return_1y)
                              FROM fund_features f2
                              JOIN scheme s2 ON s2.id = f2.scheme_id
                             WHERE f2.feature_date = :as_of
                               AND f2.return_1y IS NOT NULL
                               AND s2.category = (
                                    SELECT category FROM scheme WHERE id = fund_features.scheme_id
                               )
                       )
                     WHERE feature_date = :as_of
                    """
                ),
                {"as_of": as_of.isoformat()},
            )

    # ── Backwards-compatible aliases ─────────────────────────────────────────

    async def build_all_features(self, as_of: date | None = None, **_: Any) -> int:
        return await self.build_all(as_of=as_of)

    async def persist_features(self, features: dict[str, Any]) -> None:
        await self._flush([features], features["feature_date"])


# ── Module-level convenience ──────────────────────────────────────────────────

async def rebuild(as_of: date | None = None) -> int:
    return await FeatureBuilder().build_all(as_of=as_of)


if __name__ == "__main__":
    asyncio.run(rebuild())
