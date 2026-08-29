"""
MFScope API
===========
Read-mostly JSON API over the scored fund universe.

Query design
------------
Every list endpoint reads from ``scheme`` joined to the *latest* ``fund_score``
and ``fund_features`` rows, using the NAV facts denormalised onto ``scheme`` by
the refresh pipeline.  The previous implementation ran ``COUNT(*)`` and
``MAX(nav_date)`` subqueries against the 3M-row NAV table on every request and
fetched 90 days of NAV per card; those are now a single indexed scan plus one
bounded sparkline query.

Filtering, sorting and pagination all happen in SQL.  ``sort_by`` used to be
accepted and then silently ignored for every value except ``composite_score``,
so the UI's sort control did nothing.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from typing import Any, Iterable

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from loguru import logger
from sqlalchemy import desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.schemas import (
    AMCSummary,
    CategorySummary,
    ComponentBreakdown,
    DataQuality,
    FilterOptions,
    FundCardOut,
    FundDetailOut,
    FundFeaturesOut,
    FundMetaOut,
    FundScoreOut,
    NAVPoint,
    NewsSnippet,
    Page,
    PeerStat,
    RiskBreakdown,
    SchemeOut,
    ScoreHistoryPoint,
    SeriesPoint,
    UniverseStats,
)
from backend.config import settings
from backend.db.models import (
    FundFeatures,
    FundMetadata,
    FundScore,
    NAVRecord,
    NewsArticle,
    NewsSentiment,
    Scheme,
)
from backend.db.session import AsyncSessionLocal, engine, init_db
from backend.scoring.risk_model import RISK_LEVELS

#: NAV history and universe aggregates change once a day; recomputing them per
#: request is pure waste.  Values are held in-process with a short TTL.
_CACHE: dict[str, tuple[float, Any]] = {}
CACHE_TTL_SECONDS = 300


def _cached(key: str) -> Any | None:
    entry = _CACHE.get(key)
    if entry and time.monotonic() - entry[0] < CACHE_TTL_SECONDS:
        return entry[1]
    return None


def _store(key: str, value: Any) -> Any:
    _CACHE[key] = (time.monotonic(), value)
    return value


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting MFScope API …")
    await init_db()

    # The scheduler used to start on import, so every `--reload` restart span
    # up another one and an empty database triggered a full AMFI pull inside
    # request startup.  Both are now opt-in.
    if _env_flag("MFSCOPE_ENABLE_SCHEDULER"):
        from backend.ingestion.scheduler import start_scheduler

        start_scheduler()
        logger.info("Background scheduler enabled.")
    else:
        logger.info("Scheduler disabled (set MFSCOPE_ENABLE_SCHEDULER=1 to enable).")

    yield

    if _env_flag("MFSCOPE_ENABLE_SCHEDULER"):
        from backend.ingestion.scheduler import stop_scheduler

        stop_scheduler()
    await engine.dispose()
    logger.info("MFScope API shut down.")


app = FastAPI(
    title="MFScope API",
    description="Scored, peer-ranked intelligence over the Indian mutual fund universe.",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


async def get_session():
    async with AsyncSessionLocal() as session:
        yield session


# ── Shared SQL ────────────────────────────────────────────────────────────────

#: One row per investable fund, carrying its latest score and features.
_CARD_SELECT = """
    SELECT s.id, s.scheme_code, s.scheme_name, s.amc_name, s.category,
           s.asset_class, s.plan_type, s.inception_date,
           s.nav_latest, s.nav_latest_date, s.nav_first_date, s.nav_count,
           sc.composite_score, sc.conviction, sc.data_confidence,
           sc.peer_rank, sc.peer_count, sc.risk_score, sc.risk_level,
           f.return_1y, f.return_3y, f.return_5y, f.volatility_1y, f.sharpe_1y,
           f.max_drawdown_1y, f.expense_ratio, f.aum_crore,
           f.history_years, f.nav_days, f.nav_adjustments
      FROM scheme s
      LEFT JOIN fund_score sc
             ON sc.scheme_id = s.id AND sc.score_date = :score_date
      LEFT JOIN fund_features f
             ON f.scheme_id = s.id AND f.feature_date = :feature_date
"""

_SORTABLE: dict[str, str] = {
    "composite_score": "sc.composite_score",
    "return_1y": "f.return_1y",
    "return_3y": "f.return_3y",
    "return_5y": "f.return_5y",
    "sharpe_1y": "f.sharpe_1y",
    "volatility_1y": "f.volatility_1y",
    "max_drawdown_1y": "f.max_drawdown_1y",
    "risk_score": "sc.risk_score",
    "expense_ratio": "f.expense_ratio",
    "aum_crore": "f.aum_crore",
    "scheme_name": "s.scheme_name",
}

#: Minimum NAV prints for a metric to be honest about its horizon.
MIN_DAYS_1Y = 240          # trading days, not calendar days


async def _latest_dates() -> tuple[date | None, date | None]:
    cached = _cached("latest_dates")
    if cached is not None:
        return cached
    async with engine.connect() as conn:
        score_date = await conn.scalar(text("SELECT MAX(score_date) FROM fund_score"))
        feature_date = await conn.scalar(text("SELECT MAX(feature_date) FROM fund_features"))
    result = (_as_date(score_date), _as_date(feature_date))
    return _store("latest_dates", result)


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _data_quality(row: Any) -> DataQuality:
    nav_days = int(row.nav_count or 0)
    history_years = float(row.history_years) if row.history_years is not None else None
    return DataQuality(
        nav_days_available=nav_days,
        history_years=history_years,
        first_nav_date=_as_date(row.nav_first_date),
        latest_nav_date=_as_date(row.nav_latest_date),
        returns_valid=nav_days >= MIN_DAYS_1Y,
        risk_metrics_valid=nav_days >= MIN_DAYS_1Y,
        inception_date=_as_date(getattr(row, "inception_date", None)),
        nav_adjustments=int(row.nav_adjustments or 0),
    )


def _to_card(row: Any, sparkline: list[float] | None = None) -> FundCardOut:
    return FundCardOut(
        id=row.id,
        scheme_code=row.scheme_code,
        scheme_name=row.scheme_name,
        amc_name=row.amc_name,
        category=row.category,
        asset_class=row.asset_class,
        plan_type=row.plan_type,
        composite_score=row.composite_score,
        conviction=row.conviction,
        data_confidence=row.data_confidence,
        peer_rank=row.peer_rank,
        peer_count=row.peer_count,
        risk_score=row.risk_score,
        risk_level=row.risk_level,
        return_1y=row.return_1y,
        return_3y=row.return_3y,
        return_5y=row.return_5y,
        volatility_1y=row.volatility_1y,
        sharpe_1y=row.sharpe_1y,
        max_drawdown_1y=row.max_drawdown_1y,
        expense_ratio=row.expense_ratio,
        aum_crore=row.aum_crore,
        nav=row.nav_latest,
        nav_date=_as_date(row.nav_latest_date),
        nav_sparkline=sparkline or [],
        data_quality=_data_quality(row),
    )


async def _sparklines(scheme_ids: Iterable[int], points: int = 40, days: int = 180) -> dict[int, list[float]]:
    """
    Compact NAV curves for a page of cards.

    Returns bare floats, not ``{date, nav}`` objects: the card sparkline has no
    axis, so shipping the dates triples the payload for nothing.  Each series
    is downsampled to at most ``points`` values.
    """
    ids = list(scheme_ids)
    if not ids:
        return {}

    since = (date.today() - timedelta(days=days)).isoformat()
    placeholders = ", ".join(str(int(i)) for i in ids)
    sql = text(
        f"""
        SELECT scheme_id, nav
          FROM nav_record
         WHERE scheme_id IN ({placeholders}) AND nav_date >= :since
      ORDER BY scheme_id, nav_date
        """
    )
    async with engine.connect() as conn:
        rows = (await conn.execute(sql, {"since": since})).all()

    series: dict[int, list[float]] = {}
    for scheme_id, nav in rows:
        series.setdefault(scheme_id, []).append(float(nav))

    out: dict[int, list[float]] = {}
    for scheme_id, values in series.items():
        if len(values) <= points:
            out[scheme_id] = [round(v, 4) for v in values]
        else:
            step = len(values) / points
            out[scheme_id] = [round(values[int(i * step)], 4) for i in range(points)]
            out[scheme_id][-1] = round(values[-1], 4)
    return out


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["meta"])
async def health():
    async with engine.connect() as conn:
        schemes = await conn.scalar(text("SELECT COUNT(*) FROM scheme WHERE is_investable = 1"))
        latest_nav = await conn.scalar(text("SELECT MAX(nav_date) FROM nav_record"))
    return {
        "status": "ok",
        "timestamp": datetime.now(UTC).isoformat(),
        "investable_schemes": schemes or 0,
        "latest_nav_date": str(latest_nav) if latest_nav else None,
    }


# ── Universe stats ────────────────────────────────────────────────────────────

@app.get("/api/v1/stats", response_model=UniverseStats, tags=["meta"])
async def universe_stats(response: Response):
    cached = _cached("stats")
    if cached is not None:
        response.headers["X-Cache"] = "hit"
        return cached

    score_date, feature_date = await _latest_dates()
    async with engine.connect() as conn:
        total = await conn.scalar(text("SELECT COUNT(*) FROM scheme")) or 0
        investable = await conn.scalar(
            text("SELECT COUNT(*) FROM scheme WHERE is_investable = 1")
        ) or 0
        nav_records = await conn.scalar(text("SELECT COUNT(*) FROM nav_record")) or 0
        amc_count = await conn.scalar(
            text("SELECT COUNT(DISTINCT amc_name) FROM scheme WHERE is_investable = 1")
        ) or 0
        category_count = await conn.scalar(
            text("SELECT COUNT(DISTINCT category) FROM scheme WHERE is_investable = 1")
        ) or 0
        latest_nav = await conn.scalar(text("SELECT MAX(nav_date) FROM nav_record"))

        scored = 0
        conviction: dict[str, int] = {}
        risk: dict[str, int] = {}
        confidence = None
        if score_date:
            params = {"score_date": score_date.isoformat()}
            scored = await conn.scalar(
                text("SELECT COUNT(*) FROM fund_score WHERE score_date = :score_date"), params
            ) or 0
            conviction = {
                row[0]: row[1]
                for row in (
                    await conn.execute(
                        text(
                            "SELECT conviction, COUNT(*) FROM fund_score "
                            "WHERE score_date = :score_date GROUP BY 1"
                        ),
                        params,
                    )
                ).all()
            }
            risk = {
                row[0]: row[1]
                for row in (
                    await conn.execute(
                        text(
                            "SELECT risk_level, COUNT(*) FROM fund_score "
                            "WHERE score_date = :score_date AND risk_level IS NOT NULL GROUP BY 1"
                        ),
                        params,
                    )
                ).all()
            }
            confidence = await conn.scalar(
                text(
                    "SELECT AVG(data_confidence) FROM fund_score WHERE score_date = :score_date"
                ),
                params,
            )

        asset_classes = {
            row[0]: row[1]
            for row in (
                await conn.execute(
                    text(
                        "SELECT asset_class, COUNT(*) FROM scheme "
                        "WHERE is_investable = 1 GROUP BY 1 ORDER BY 2 DESC"
                    )
                )
            ).all()
        }

        median_1y = None
        if feature_date:
            median_1y = await conn.scalar(
                text(
                    """
                    SELECT AVG(return_1y) FROM (
                        SELECT f.return_1y
                          FROM fund_features f
                          JOIN scheme s ON s.id = f.scheme_id
                         WHERE f.feature_date = :feature_date
                           AND s.is_investable = 1
                           AND f.return_1y IS NOT NULL
                      ORDER BY f.return_1y
                         LIMIT 2 - (SELECT COUNT(*) FROM fund_features f2
                                     JOIN scheme s2 ON s2.id = f2.scheme_id
                                    WHERE f2.feature_date = :feature_date
                                      AND s2.is_investable = 1
                                      AND f2.return_1y IS NOT NULL) % 2
                        OFFSET (SELECT (COUNT(*) - 1) / 2 FROM fund_features f3
                                 JOIN scheme s3 ON s3.id = f3.scheme_id
                                WHERE f3.feature_date = :feature_date
                                  AND s3.is_investable = 1
                                  AND f3.return_1y IS NOT NULL)
                    )
                    """
                ),
                {"feature_date": feature_date.isoformat()},
            )

    stats = UniverseStats(
        total_schemes=total,
        investable_schemes=investable,
        scored_schemes=scored,
        nav_records=nav_records,
        amc_count=amc_count,
        category_count=category_count,
        latest_nav_date=_as_date(latest_nav),
        latest_score_date=score_date,
        median_return_1y=round(float(median_1y), 2) if median_1y is not None else None,
        conviction_breakdown=conviction,
        risk_breakdown=risk,
        asset_class_breakdown=asset_classes,
        mean_data_confidence=round(float(confidence), 3) if confidence is not None else None,
    )
    response.headers["X-Cache"] = "miss"
    return _store("stats", stats)


# ── Filter options ────────────────────────────────────────────────────────────

@app.get("/api/v1/filters", response_model=FilterOptions, tags=["meta"])
async def filter_options():
    """Everything the filter UI needs, in one request instead of four."""
    cached = _cached("filters")
    if cached is not None:
        return cached

    categories = await list_categories()
    async with engine.connect() as conn:
        asset_classes = [
            row[0]
            for row in (
                await conn.execute(
                    text(
                        "SELECT DISTINCT asset_class FROM scheme "
                        "WHERE is_investable = 1 AND asset_class IS NOT NULL ORDER BY 1"
                    )
                )
            ).all()
        ]
        amcs = [
            row[0]
            for row in (
                await conn.execute(
                    text(
                        "SELECT amc_name, COUNT(*) c FROM scheme "
                        "WHERE is_investable = 1 GROUP BY 1 ORDER BY c DESC, 1"
                    )
                )
            ).all()
        ]
        plans = [
            row[0]
            for row in (
                await conn.execute(
                    text(
                        "SELECT DISTINCT plan_type FROM scheme "
                        "WHERE is_investable = 1 AND plan_type IS NOT NULL ORDER BY 1"
                    )
                )
            ).all()
        ]

    options = FilterOptions(
        categories=categories,
        asset_classes=asset_classes,
        amcs=amcs,
        convictions=["Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"],
        risk_levels=list(RISK_LEVELS),
        plan_types=plans,
    )
    return _store("filters", options)


# ── Categories ────────────────────────────────────────────────────────────────

@app.get("/api/v1/categories", response_model=list[CategorySummary], tags=["funds"])
async def list_categories():
    cached = _cached("categories")
    if cached is not None:
        return cached

    score_date, feature_date = await _latest_dates()
    sql = text(
        """
        SELECT s.category,
               MIN(s.asset_class)            AS asset_class,
               COUNT(*)                      AS fund_count,
               AVG(sc.composite_score)       AS avg_score,
               AVG(f.return_1y)              AS avg_return_1y,
               AVG(sc.risk_score)            AS avg_risk
          FROM scheme s
          LEFT JOIN fund_score sc ON sc.scheme_id = s.id AND sc.score_date = :score_date
          LEFT JOIN fund_features f ON f.scheme_id = s.id AND f.feature_date = :feature_date
         WHERE s.is_investable = 1
      GROUP BY s.category
      ORDER BY fund_count DESC
        """
    )
    params = {
        "score_date": score_date.isoformat() if score_date else None,
        "feature_date": feature_date.isoformat() if feature_date else None,
    }

    async with engine.connect() as conn:
        rows = (await conn.execute(sql, params)).all()
        leaders: dict[str, tuple[str, str, float]] = {}
        if score_date:
            leader_rows = (
                await conn.execute(
                    text(
                        """
                        SELECT category, scheme_code, scheme_name, composite_score FROM (
                            SELECT s.category, s.scheme_code, s.scheme_name, sc.composite_score,
                                   ROW_NUMBER() OVER (
                                       PARTITION BY s.category ORDER BY sc.composite_score DESC
                                   ) AS rn
                              FROM scheme s
                              JOIN fund_score sc
                                ON sc.scheme_id = s.id AND sc.score_date = :score_date
                             WHERE s.is_investable = 1
                        ) WHERE rn = 1
                        """
                    ),
                    {"score_date": score_date.isoformat()},
                )
            ).all()
            leaders = {r[0]: (r[1], r[2], r[3]) for r in leader_rows}

    summaries = []
    for row in rows:
        leader = leaders.get(row.category)
        summaries.append(
            CategorySummary(
                category=row.category,
                asset_class=row.asset_class,
                fund_count=row.fund_count,
                avg_score=round(float(row.avg_score), 1) if row.avg_score is not None else None,
                median_return_1y=(
                    round(float(row.avg_return_1y), 2) if row.avg_return_1y is not None else None
                ),
                avg_risk_score=round(float(row.avg_risk), 1) if row.avg_risk is not None else None,
                top_fund_code=leader[0] if leader else None,
                top_fund_name=leader[1] if leader else None,
                top_fund_score=round(float(leader[2]), 1) if leader else None,
            )
        )
    return _store("categories", summaries)


@app.get("/api/v1/amcs", response_model=list[AMCSummary], tags=["funds"])
async def list_amcs(limit: int = Query(60, ge=1, le=200)):
    score_date, _ = await _latest_dates()
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    """
                    SELECT s.amc_name, COUNT(*) AS fund_count, AVG(sc.composite_score) AS avg_score
                      FROM scheme s
                      LEFT JOIN fund_score sc
                             ON sc.scheme_id = s.id AND sc.score_date = :score_date
                     WHERE s.is_investable = 1
                  GROUP BY s.amc_name
                  ORDER BY fund_count DESC
                     LIMIT :limit
                    """
                ),
                {"score_date": score_date.isoformat() if score_date else None, "limit": limit},
            )
        ).all()
    return [
        AMCSummary(
            amc_name=row.amc_name,
            fund_count=row.fund_count,
            avg_score=round(float(row.avg_score), 1) if row.avg_score is not None else None,
        )
        for row in rows
    ]


# ── Fund list ─────────────────────────────────────────────────────────────────

@app.get("/api/v1/funds", response_model=Page[FundCardOut], tags=["funds"])
async def list_funds(
    category: str | None = Query(None),
    asset_class: str | None = Query(None),
    amc: str | None = Query(None),
    conviction: str | None = Query(None),
    risk_level: str | None = Query(None),
    plan_type: str | None = Query(None),
    search: str | None = Query(None, max_length=120),
    min_score: float | None = Query(None, ge=0, le=100),
    min_return_1y: float | None = Query(None),
    max_expense_ratio: float | None = Query(None),
    sort_by: str = Query("composite_score"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
    with_sparkline: bool = Query(True),
):
    score_date, feature_date = await _latest_dates()
    params: dict[str, Any] = {
        "score_date": score_date.isoformat() if score_date else None,
        "feature_date": feature_date.isoformat() if feature_date else None,
    }
    clauses = ["s.is_investable = 1"]

    if category:
        clauses.append("s.category = :category")
        params["category"] = category
    if asset_class:
        clauses.append("s.asset_class = :asset_class")
        params["asset_class"] = asset_class
    if amc:
        clauses.append("s.amc_name = :amc")
        params["amc"] = amc
    if conviction:
        clauses.append("sc.conviction = :conviction")
        params["conviction"] = conviction
    if risk_level:
        clauses.append("sc.risk_level = :risk_level")
        params["risk_level"] = risk_level
    if plan_type:
        clauses.append("s.plan_type = :plan_type")
        params["plan_type"] = plan_type
    if min_score is not None:
        clauses.append("sc.composite_score >= :min_score")
        params["min_score"] = min_score
    if min_return_1y is not None:
        clauses.append("f.return_1y >= :min_return_1y")
        params["min_return_1y"] = min_return_1y
    if max_expense_ratio is not None:
        clauses.append("f.expense_ratio <= :max_expense_ratio")
        params["max_expense_ratio"] = max_expense_ratio
    if search:
        clauses.append("(s.scheme_name LIKE :search OR s.amc_name LIKE :search)")
        params["search"] = f"%{search}%"

    where = " WHERE " + " AND ".join(clauses)
    column = _SORTABLE.get(sort_by, _SORTABLE["composite_score"])
    direction = "DESC" if sort_dir == "desc" else "ASC"
    # NULLs last in both directions: an unscored fund is not the best fund.
    # composite_score is peer-relative (see rule_based.py), so exact ties still
    # happen — most often among funds in the same small peer group with
    # identical inputs. Break ties by how large that peer group was, then by
    # risk-adjusted return, so the page orders leaders of big, meaningful
    # groups first instead of alphabetically-adjacent ties.
    tiebreak = ", sc.peer_count DESC, f.sharpe_1y DESC" if sort_by == "composite_score" else ""
    order = f"ORDER BY ({column} IS NULL), {column} {direction}{tiebreak}, s.scheme_name ASC"

    async with engine.connect() as conn:
        total = await conn.scalar(
            text(
                f"""
                SELECT COUNT(*)
                  FROM scheme s
                  LEFT JOIN fund_score sc
                         ON sc.scheme_id = s.id AND sc.score_date = :score_date
                  LEFT JOIN fund_features f
                         ON f.scheme_id = s.id AND f.feature_date = :feature_date
                {where}
                """
            ),
            params,
        ) or 0

        if total == 0:
            return Page[FundCardOut](total=0, page=page, page_size=page_size, total_pages=0, items=[])

        rows = (
            await conn.execute(
                text(f"{_CARD_SELECT}{where} {order} LIMIT :limit OFFSET :offset"),
                {**params, "limit": page_size, "offset": (page - 1) * page_size},
            )
        ).all()

    sparklines = await _sparklines([r.id for r in rows]) if with_sparkline else {}
    return Page[FundCardOut](
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
        items=[_to_card(row, sparklines.get(row.id)) for row in rows],
    )


# ── Top funds ─────────────────────────────────────────────────────────────────

@app.get("/api/v1/scores/top", response_model=list[FundCardOut], tags=["scores"])
async def top_funds(
    category: str | None = Query(None),
    asset_class: str | None = Query(None),
    conviction: str | None = Query(None),
    limit: int = Query(8, ge=1, le=50),
    min_peer_count: int = Query(20, ge=1, le=500),
    with_sparkline: bool = Query(True),
):
    """
    Highest-scoring funds.

    ``composite_score`` is peer-relative and scales with how large the peer
    group was (see ``rule_based._spread_score``), so the leader of a 4-fund
    bucket already scores lower than the leader of a 300-fund one — but
    requiring a minimum peer count here still keeps this list to funds that
    beat a field worth beating, rather than the best of a handful of oddities.
    """
    score_date, feature_date = await _latest_dates()
    if not score_date:
        return []

    params: dict[str, Any] = {
        "score_date": score_date.isoformat(),
        "feature_date": feature_date.isoformat() if feature_date else None,
        "limit": limit,
    }
    clauses = [
        "s.is_investable = 1",
        "sc.composite_score IS NOT NULL",
        "sc.peer_count >= :min_peer_count",
    ]
    params["min_peer_count"] = min_peer_count
    if category:
        clauses.append("s.category = :category")
        params["category"] = category
    if asset_class:
        clauses.append("s.asset_class = :asset_class")
        params["asset_class"] = asset_class
    if conviction:
        clauses.append("sc.conviction = :conviction")
        params["conviction"] = conviction

    sql = (
        f"{_CARD_SELECT} WHERE {' AND '.join(clauses)} "
        "ORDER BY sc.composite_score DESC, sc.peer_count DESC, f.sharpe_1y DESC LIMIT :limit"
    )
    async with engine.connect() as conn:
        rows = (await conn.execute(text(sql), params)).all()

    sparklines = await _sparklines([r.id for r in rows]) if with_sparkline else {}
    return [_to_card(row, sparklines.get(row.id)) for row in rows]


# ── Compare ───────────────────────────────────────────────────────────────────

@app.get("/api/v1/funds/compare", response_model=list[FundCardOut], tags=["funds"])
async def compare_funds(codes: str = Query(..., description="Comma-separated scheme codes")):
    wanted = [c.strip() for c in codes.split(",") if c.strip()][:8]
    if not wanted:
        return []

    score_date, feature_date = await _latest_dates()
    placeholders = ", ".join(f":code{i}" for i in range(len(wanted)))
    params: dict[str, Any] = {
        "score_date": score_date.isoformat() if score_date else None,
        "feature_date": feature_date.isoformat() if feature_date else None,
    }
    params.update({f"code{i}": code for i, code in enumerate(wanted)})

    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(f"{_CARD_SELECT} WHERE s.scheme_code IN ({placeholders})"), params
            )
        ).all()

    sparklines = await _sparklines([r.id for r in rows], points=60, days=365)
    by_code = {row.scheme_code: _to_card(row, sparklines.get(row.id)) for row in rows}
    return [by_code[code] for code in wanted if code in by_code]


# ── Fund detail ───────────────────────────────────────────────────────────────

@app.get("/api/v1/funds/{scheme_code}", response_model=FundDetailOut, tags=["funds"])
async def get_fund_detail(
    scheme_code: str,
    days: int = Query(1095, ge=90, le=4000),
    db: AsyncSession = Depends(get_session),
):
    scheme = await db.scalar(select(Scheme).where(Scheme.scheme_code == scheme_code))
    if scheme is None:
        raise HTTPException(status_code=404, detail=f"Scheme '{scheme_code}' not found.")

    score_date, feature_date = await _latest_dates()
    since = date.today() - timedelta(days=days)

    latest_score = await db.scalar(
        select(FundScore)
        .where(FundScore.scheme_id == scheme.id)
        .order_by(desc(FundScore.score_date))
        .limit(1)
    )
    features = await db.scalar(
        select(FundFeatures)
        .where(FundFeatures.scheme_id == scheme.id)
        .order_by(desc(FundFeatures.feature_date))
        .limit(1)
    )
    meta = await db.scalar(
        select(FundMetadata)
        .where(FundMetadata.scheme_id == scheme.id)
        .order_by(desc(FundMetadata.as_of_date))
        .limit(1)
    )

    nav_rows = (
        await db.execute(
            select(NAVRecord.nav_date, NAVRecord.nav)
            .where(NAVRecord.scheme_id == scheme.id)
            .where(NAVRecord.nav_date >= since)
            .order_by(NAVRecord.nav_date)
        )
    ).all()
    nav_history = [NAVPoint(nav_date=row[0], nav=float(row[1])) for row in nav_rows]

    score_rows = (
        await db.execute(
            select(FundScore.score_date, FundScore.composite_score, FundScore.conviction)
            .where(FundScore.scheme_id == scheme.id)
            .order_by(FundScore.score_date)
        )
    ).all()
    score_history = [
        ScoreHistoryPoint(score_date=row[0], composite_score=row[1], conviction=row[2])
        for row in score_rows
    ]

    fund_series, benchmark_series = await _comparison_series(scheme, nav_history, since)
    peer_stats = await _peer_stats(scheme, features, latest_score, feature_date)
    similar = await _similar_funds(scheme, score_date, feature_date)
    recent_news = await _recent_news(db, scheme)

    features_out = None
    if features is not None:
        features_out = FundFeaturesOut.model_validate(features)
        features_out.data_quality = DataQuality(
            nav_days_available=int(scheme.nav_count or 0),
            history_years=features.history_years,
            first_nav_date=scheme.nav_first_date,
            latest_nav_date=scheme.nav_latest_date,
            returns_valid=(scheme.nav_count or 0) >= MIN_DAYS_1Y,
            risk_metrics_valid=(scheme.nav_count or 0) >= MIN_DAYS_1Y,
            inception_date=scheme.inception_date,
            nav_adjustments=int(features.nav_adjustments or 0),
        )

    score_out = None
    if latest_score is not None:
        score_out = FundScoreOut.model_validate(latest_score)
        score_out.breakdown = _parse_breakdown(latest_score.shap_json)
        score_out.risk_breakdown = _parse_risk(latest_score.risk_shap_json)

    return FundDetailOut(
        scheme=SchemeOut.model_validate(scheme),
        latest_score=score_out,
        metadata=FundMetaOut.model_validate(meta) if meta else None,
        features=features_out,
        nav_history=nav_history,
        fund_series=fund_series,
        benchmark_series=benchmark_series,
        score_history=score_history,
        peer_stats=peer_stats,
        recent_news=recent_news,
        similar_funds=similar,
    )


def _parse_breakdown(blob: str | None) -> ComponentBreakdown | None:
    if not blob:
        return None
    try:
        return ComponentBreakdown.model_validate(json.loads(blob))
    except Exception:
        return None


def _parse_risk(blob: str | None) -> RiskBreakdown | None:
    if not blob:
        return None
    try:
        return RiskBreakdown.model_validate(json.loads(blob))
    except Exception:
        return None


async def _comparison_series(
    scheme: Scheme, nav_history: list[NAVPoint], since: date
) -> tuple[list[SeriesPoint], list[SeriesPoint]]:
    """
    Fund vs. category median, both rebased to 100 at the window start.

    Rebasing is what makes the comparison readable: raw NAV levels differ by
    orders of magnitude between funds and say nothing about relative
    performance.
    """
    if len(nav_history) < 2:
        return [], []

    base = nav_history[0].nav
    fund_series = [
        SeriesPoint(date=p.nav_date, value=round(p.nav / base * 100.0, 3))
        for p in nav_history
        if base > 0
    ]

    cache_key = f"benchmark:{scheme.category}:{since.isoformat()}"
    cached = _cached(cache_key)
    if cached is not None:
        return fund_series, cached

    sql = text(
        """
        SELECT n.nav_date, AVG(n.nav / b.base_nav) AS rebased
          FROM nav_record n
          JOIN scheme s ON s.id = n.scheme_id
          JOIN (
                SELECT n2.scheme_id, n2.nav AS base_nav
                  FROM nav_record n2
                  JOIN (
                        SELECT scheme_id, MIN(nav_date) AS first_date
                          FROM nav_record
                         WHERE nav_date >= :since
                      GROUP BY scheme_id
                  ) firsts
                    ON firsts.scheme_id = n2.scheme_id AND firsts.first_date = n2.nav_date
          ) b ON b.scheme_id = n.scheme_id
         WHERE s.category = :category
           AND s.is_investable = 1
           AND s.plan_type = :plan_type
           AND n.nav_date >= :since
           AND b.base_nav > 0
      GROUP BY n.nav_date
        HAVING COUNT(*) >= 3
      ORDER BY n.nav_date
        """
    )
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                sql,
                {
                    "category": scheme.category,
                    "plan_type": scheme.plan_type or "Direct",
                    "since": since.isoformat(),
                },
            )
        ).all()

    benchmark = [
        SeriesPoint(date=_as_date(row[0]), value=round(float(row[1]) * 100.0, 3)) for row in rows
    ]
    _store(cache_key, benchmark)
    return fund_series, benchmark


_PEER_METRICS: tuple[tuple[str, bool], ...] = (
    ("return_1y", True),
    ("return_3y", True),
    ("return_5y", True),
    ("sharpe_1y", True),
    ("sortino_1y", True),
    ("alpha_1y", True),
    ("volatility_1y", False),
    ("max_drawdown_1y", True),      # less negative is better
    ("expense_ratio", False),
    ("rolling_1y_std", False),
)


async def _peer_stats(
    scheme: Scheme,
    features: FundFeatures | None,
    score: FundScore | None,
    feature_date: date | None,
) -> list[PeerStat]:
    """Where this fund sits inside its peer group on each headline metric."""
    if features is None or feature_date is None:
        return []

    peer_group = (score.peer_group if score else None) or scheme.category
    columns = ", ".join(f"f.{name}" for name, _ in _PEER_METRICS)
    sql = text(
        f"""
        SELECT {columns}
          FROM fund_features f
          JOIN scheme s ON s.id = f.scheme_id
          LEFT JOIN fund_score sc
                 ON sc.scheme_id = s.id AND sc.score_date = :feature_date
         WHERE f.feature_date = :feature_date
           AND s.is_investable = 1
           AND COALESCE(sc.peer_group, s.category) = :peer_group
        """
    )
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                sql, {"feature_date": feature_date.isoformat(), "peer_group": peer_group}
            )
        ).all()

    if len(rows) < 3:
        return []

    stats: list[PeerStat] = []
    for index, (metric, higher_is_better) in enumerate(_PEER_METRICS):
        values = sorted(float(row[index]) for row in rows if row[index] is not None)
        if len(values) < 3:
            continue
        own = getattr(features, metric, None)
        percentile = None
        if own is not None:
            below = sum(1 for v in values if v < own)
            percentile = round(below / len(values) * 100.0, 1)
            if not higher_is_better:
                percentile = round(100.0 - percentile, 1)
        stats.append(
            PeerStat(
                metric=metric,
                value=round(float(own), 3) if own is not None else None,
                peer_median=round(values[len(values) // 2], 3),
                peer_best=round(values[-1] if higher_is_better else values[0], 3),
                peer_worst=round(values[0] if higher_is_better else values[-1], 3),
                percentile=percentile,
                higher_is_better=higher_is_better,
            )
        )
    return stats


async def _similar_funds(
    scheme: Scheme, score_date: date | None, feature_date: date | None, limit: int = 4
) -> list[FundCardOut]:
    """Highest-scoring peers in the same category and plan type."""
    if not score_date:
        return []
    sql = (
        f"{_CARD_SELECT} WHERE s.is_investable = 1 AND s.category = :category "
        "AND s.plan_type = :plan_type AND s.id <> :scheme_id "
        "AND sc.composite_score IS NOT NULL "
        "ORDER BY sc.composite_score DESC LIMIT :limit"
    )
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(sql),
                {
                    "score_date": score_date.isoformat(),
                    "feature_date": feature_date.isoformat() if feature_date else None,
                    "category": scheme.category,
                    "plan_type": scheme.plan_type or "Direct",
                    "scheme_id": scheme.id,
                    "limit": limit,
                },
            )
        ).all()

    sparklines = await _sparklines([r.id for r in rows])
    return [_to_card(row, sparklines.get(row.id)) for row in rows]


async def _recent_news(db: AsyncSession, scheme: Scheme, limit: int = 10) -> list[NewsSnippet]:
    rows = (
        await db.execute(
            select(
                NewsArticle.title,
                NewsArticle.url,
                NewsArticle.published_at,
                NewsArticle.source,
                NewsSentiment.sentiment_label,
                NewsSentiment.compound_score,
            )
            .join(NewsSentiment, NewsSentiment.article_id == NewsArticle.id)
            .where((NewsSentiment.scheme_id == scheme.id) | (NewsSentiment.category == scheme.category))
            .where(NewsArticle.published_at >= datetime.now(UTC).replace(tzinfo=None) - timedelta(days=21))
            .order_by(desc(NewsArticle.published_at))
            .limit(limit)
        )
    ).all()
    return [
        NewsSnippet(
            title=row[0],
            url=row[1],
            published_at=row[2],
            source=row[3],
            sentiment_label=row[4],
            compound_score=row[5],
        )
        for row in rows
    ]


# ── NAV history ───────────────────────────────────────────────────────────────

@app.get("/api/v1/funds/{scheme_code}/nav", response_model=list[NAVPoint], tags=["funds"])
async def get_nav_history(
    scheme_code: str,
    days: int = Query(365, ge=30, le=4000),
    db: AsyncSession = Depends(get_session),
):
    scheme = await db.scalar(select(Scheme).where(Scheme.scheme_code == scheme_code))
    if scheme is None:
        raise HTTPException(status_code=404, detail=f"Scheme '{scheme_code}' not found.")
    since = date.today() - timedelta(days=days)
    rows = (
        await db.execute(
            select(NAVRecord.nav_date, NAVRecord.nav)
            .where(NAVRecord.scheme_id == scheme.id)
            .where(NAVRecord.nav_date >= since)
            .order_by(NAVRecord.nav_date)
        )
    ).all()
    return [NAVPoint(nav_date=row[0], nav=float(row[1])) for row in rows]


# ── Admin ─────────────────────────────────────────────────────────────────────

_refresh_task: asyncio.Task | None = None


@app.post("/api/v1/admin/refresh", tags=["admin"])
async def manual_refresh():
    """Kick off the daily pipeline: NAV pull → universe → features → scores."""
    global _refresh_task
    if _refresh_task and not _refresh_task.done():
        return {"status": "already_running"}

    from backend.ingestion.scheduler import daily_pipeline

    _refresh_task = asyncio.create_task(daily_pipeline())
    _CACHE.clear()
    return {"status": "queued"}


@app.get("/api/v1/admin/refresh/status", tags=["admin"])
async def refresh_status():
    if _refresh_task is None:
        return {"status": "idle"}
    if not _refresh_task.done():
        return {"status": "running"}
    error = _refresh_task.exception()
    return {"status": "failed" if error else "complete", "error": str(error) if error else None}
