"""
MFScope FastAPI Application
"""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from sqlalchemy import func, select, desc, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.schemas import (
    CategorySummary,
    DataQuality,
    FundCardOut,
    FundDetailOut,
    FundFeaturesOut,
    FundMetaOut,
    FundScoreOut,
    NAVPoint,
    NewsSnippet,
    Page,
    ScoreHistoryPoint,
    SchemeOut,
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
from backend.db.session import AsyncSessionLocal, init_db


# ── Seed helper ───────────────────────────────────────────────────────────────

async def _seed_if_empty() -> None:
    """Pull AMFI data if the DB has no schemes yet."""
    async with AsyncSessionLocal() as session:
        count = await session.scalar(text("SELECT COUNT(*) FROM scheme"))

    if count and count > 0:
        logger.info(f"DB already has {count} schemes — skipping seed.")
        return

    logger.info("DB is empty — seeding from AMFI now …")
    from backend.ingestion.amfi_client import AMFIClient
    client = AMFIClient()
    try:
        n = await client.fetch_scheme_master()
        logger.info(f"Seed: {n} schemes inserted.")
        n2 = await client.fetch_latest_nav()
        logger.info(f"Seed: {n2} NAV rows inserted.")
    except Exception as exc:
        logger.error(f"Seed failed: {exc}")


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting MFScope API …")
    await init_db()
    # Seed in background so startup is not blocked
    asyncio.create_task(_seed_if_empty())
    from backend.ingestion.scheduler import start_scheduler
    start_scheduler()
    yield
    from backend.ingestion.scheduler import stop_scheduler
    stop_scheduler()
    logger.info("MFScope API shut down.")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="MFScope API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── DB dependency ─────────────────────────────────────────────────────────────

async def get_session():
    async with AsyncSessionLocal() as session:
        yield session


# ── Data Quality Helper ───────────────────────────────────────────────────────

def _compute_data_quality(scheme_id: int, scheme: Scheme, nav_count: int) -> DataQuality:
    """
    Compute data quality indicators for a scheme.
    
    Args:
        scheme_id: Database ID of the scheme
        scheme: Scheme object containing inception_date
        nav_count: Number of NAV records available
    
    Returns:
        DataQuality object with validation flags
    """
    # Minimum 370 days required for 1-year returns and risk metrics
    MIN_DAYS_1Y = 370
    
    returns_valid = nav_count >= MIN_DAYS_1Y
    risk_metrics_valid = nav_count >= MIN_DAYS_1Y
    
    return DataQuality(
        nav_days_available=nav_count,
        returns_valid=returns_valid,
        risk_metrics_valid=risk_metrics_valid,
        inception_date=scheme.inception_date,
    )


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["meta"])
async def health():
    async with AsyncSessionLocal() as session:
        scheme_count = await session.scalar(text("SELECT COUNT(*) FROM scheme")) or 0
        nav_count    = await session.scalar(text("SELECT COUNT(*) FROM nav_record")) or 0
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "schemes": scheme_count,
        "nav_records": nav_count,
    }


# ── Categories ────────────────────────────────────────────────────────────────

@app.get("/api/v1/categories", response_model=list[CategorySummary], tags=["funds"])
async def list_categories(db: AsyncSession = Depends(get_session)):
    # Get latest score date
    latest_score_date = await db.scalar(
        select(func.max(FundScore.score_date))
    )
    
    # Count active schemes per category
    count_result = await db.execute(
        select(Scheme.category, func.count(Scheme.id).label("cnt"))
        .where(Scheme.is_active == True)
        .group_by(Scheme.category)
    )
    counts = {row.category: row.cnt for row in count_result.all()}

    # Get avg score per category using latest scores
    if latest_score_date:
        score_result = await db.execute(
            select(Scheme.category, func.avg(FundScore.composite_score).label("avg_score"))
            .join(FundScore, FundScore.scheme_id == Scheme.id)
            .where(FundScore.score_date == latest_score_date)
            .group_by(Scheme.category)
        )
        avg_scores = {row.category: row.avg_score for row in score_result.all()}
    else:
        avg_scores = {}

    summaries = []
    for cat, cnt in sorted(counts.items()):
        summaries.append(CategorySummary(
            category=cat,
            fund_count=cnt,
            avg_score=float(avg_scores[cat]) if cat in avg_scores else None,
            top_fund_name=None,
            top_fund_score=None,
        ))
    return summaries


# ── Fund list ─────────────────────────────────────────────────────────────────

@app.get("/api/v1/funds", response_model=Page, tags=["funds"])
async def list_funds(
    category:   str | None = Query(None),
    conviction: str | None = Query(None),
    search:     str | None = Query(None),
    sort_by:    str        = Query("composite_score"),
    sort_dir:   str        = Query("desc"),
    page:       int        = Query(1, ge=1),
    page_size:  int        = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_session),
):
    sparkline_since = date.today() - timedelta(days=90)

    # ── Get latest score date available ───────────────────────────────────────
    latest_score_date = await db.scalar(
        select(func.max(FundScore.score_date))
    )

    # ── Build base query ──────────────────────────────────────────────────────
    if not latest_score_date:
        # No scores yet - return schemes without scores
        stmt = select(Scheme).where(Scheme.is_active == True)
        
        if category:
            stmt = stmt.where(Scheme.category == category)
        if search:
            like = f"%{search}%"
            stmt = stmt.where(Scheme.scheme_name.ilike(like) | Scheme.amc_name.ilike(like))
        
        stmt = stmt.order_by(Scheme.scheme_name)
        
        # Get count
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = await db.scalar(count_stmt) or 0
        
        if total == 0:
            return Page(total=0, page=page, page_size=page_size, items=[])
        
        # Paginate
        offset = (page - 1) * page_size
        stmt = stmt.offset(offset).limit(page_size)
        result = await db.execute(stmt)
        schemes = result.scalars().all()
        
        # Get NAV counts for data quality
        scheme_ids = [s.id for s in schemes]
        nav_count_result = await db.execute(
            select(NAVRecord.scheme_id, func.count(NAVRecord.id).label("nav_count"))
            .where(NAVRecord.scheme_id.in_(scheme_ids))
            .group_by(NAVRecord.scheme_id)
        )
        nav_counts_by_id: dict[int, int] = {row.scheme_id: row.nav_count for row in nav_count_result.all()}
        
        # Build minimal cards with data quality
        cards = []
        for s in schemes:
            nav_count = nav_counts_by_id.get(s.id, 0)
            data_quality = _compute_data_quality(
                scheme_id=s.id,
                scheme=s,
                nav_count=nav_count
            )
            
            cards.append(FundCardOut(
                id=s.id,
                scheme_code=s.scheme_code,
                scheme_name=s.scheme_name,
                amc_name=s.amc_name,
                category=s.category,
                composite_score=None,
                conviction=None,
                risk_score=None,
                risk_level=None,
                return_1y=None,
                return_3y=None,
                expense_ratio=None,
                aum_crore=None,
                nav_sparkline=[],
                data_quality=data_quality,
            ))
        
        return Page(total=total, page=page, page_size=page_size, items=cards)
    
    # ── Query with scores ─────────────────────────────────────────────────────
    stmt = (
        select(Scheme, FundScore)
        .join(FundScore, FundScore.scheme_id == Scheme.id, isouter=True)
        .where(Scheme.is_active == True)
        .where((FundScore.score_date == latest_score_date) | (FundScore.score_date.is_(None)))
    )
    
    if category:
        stmt = stmt.where(Scheme.category == category)
    if conviction:
        stmt = stmt.where(FundScore.conviction == conviction)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(
            Scheme.scheme_name.ilike(like) | Scheme.amc_name.ilike(like)
        )
    
    # ── Apply sorting ─────────────────────────────────────────────────────────
    if sort_by == "composite_score":
        if sort_dir == "desc":
            stmt = stmt.order_by(desc(FundScore.composite_score).nulls_last())
        else:
            stmt = stmt.order_by(FundScore.composite_score.nulls_last())
    else:
        stmt = stmt.order_by(Scheme.scheme_name)
    
    # ── Get total count ───────────────────────────────────────────────────────
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = await db.scalar(count_stmt) or 0
    
    if total == 0:
        return Page(total=0, page=page, page_size=page_size, items=[])
    
    # ── Apply pagination ──────────────────────────────────────────────────────
    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size)
    result = await db.execute(stmt)
    rows = result.all()
    
    scheme_ids = [row.Scheme.id for row in rows]

    # ── Batch-load features ───────────────────────────────────────────────────
    latest_feat_date = await db.scalar(
        select(func.max(FundFeatures.feature_date))
        .where(FundFeatures.scheme_id.in_(scheme_ids))
    )
    
    if latest_feat_date:
        feat_rows = await db.execute(
            select(FundFeatures)
            .where(FundFeatures.scheme_id.in_(scheme_ids))
            .where(FundFeatures.feature_date == latest_feat_date)
        )
        feats_by_id: dict[int, FundFeatures] = {f.scheme_id: f for f in feat_rows.scalars().all()}
    else:
        feats_by_id = {}

    # ── Batch-load metadata ───────────────────────────────────────────────────
    meta_result = await db.execute(
        select(FundMetadata)
        .where(FundMetadata.scheme_id.in_(scheme_ids))
        .order_by(FundMetadata.as_of_date.desc())
    )
    metas_by_id: dict[int, FundMetadata] = {}
    for m in meta_result.scalars().all():
        if m.scheme_id not in metas_by_id:
            metas_by_id[m.scheme_id] = m

    # ── Batch-load sparklines ─────────────────────────────────────────────────
    nav_result = await db.execute(
        select(NAVRecord)
        .where(NAVRecord.scheme_id.in_(scheme_ids))
        .where(NAVRecord.nav_date >= sparkline_since)
        .order_by(NAVRecord.nav_date)
    )
    sparklines_by_id: dict[int, list[NAVPoint]] = {}
    for n in nav_result.scalars().all():
        sparklines_by_id.setdefault(n.scheme_id, []).append(
            NAVPoint(nav_date=n.nav_date, nav=float(n.nav))
        )

    # ── Batch-load NAV counts for data quality ────────────────────────────────
    nav_count_result = await db.execute(
        select(NAVRecord.scheme_id, func.count(NAVRecord.id).label("nav_count"))
        .where(NAVRecord.scheme_id.in_(scheme_ids))
        .group_by(NAVRecord.scheme_id)
    )
    nav_counts_by_id: dict[int, int] = {row.scheme_id: row.nav_count for row in nav_count_result.all()}

    # ── Build cards ───────────────────────────────────────────────────────────
    cards: list[FundCardOut] = []
    for row in rows:
        scheme = row.Scheme
        score = row.FundScore
        feat = feats_by_id.get(scheme.id)
        meta = metas_by_id.get(scheme.id)
        nav_count = nav_counts_by_id.get(scheme.id, 0)
        
        # Compute data quality
        data_quality = _compute_data_quality(
            scheme_id=scheme.id,
            scheme=scheme,
            nav_count=nav_count
        )

        cards.append(FundCardOut(
            id=scheme.id,
            scheme_code=scheme.scheme_code,
            scheme_name=scheme.scheme_name,
            amc_name=scheme.amc_name,
            category=scheme.category,
            composite_score=score.composite_score if score else None,
            conviction=score.conviction if score else None,
            risk_score=score.risk_score if score else None,
            risk_level=score.risk_level if score else None,
            return_1y=feat.return_1y if feat else None,
            return_3y=feat.return_3y if feat else None,
            expense_ratio=meta.expense_ratio if meta else None,
            aum_crore=meta.aum_crore if meta else None,
            nav_sparkline=sparklines_by_id.get(scheme.id, [])[-30:],
            data_quality=data_quality,
        ))

    return Page(total=total, page=page, page_size=page_size, items=cards)


# ── Fund detail ───────────────────────────────────────────────────────────────

@app.get("/api/v1/funds/{scheme_code}", response_model=FundDetailOut, tags=["funds"])
async def get_fund_detail(scheme_code: str, db: AsyncSession = Depends(get_session)):
    scheme = await db.scalar(select(Scheme).where(Scheme.scheme_code == scheme_code))
    if not scheme:
        raise HTTPException(status_code=404, detail=f"Scheme '{scheme_code}' not found.")

    today       = date.today()
    one_year_ago = today - timedelta(days=365)

    latest_score = await db.scalar(
        select(FundScore).where(FundScore.scheme_id == scheme.id)
        .order_by(desc(FundScore.score_date)).limit(1)
    )
    meta = await db.scalar(
        select(FundMetadata).where(FundMetadata.scheme_id == scheme.id)
        .order_by(desc(FundMetadata.as_of_date)).limit(1)
    )
    features = await db.scalar(
        select(FundFeatures).where(FundFeatures.scheme_id == scheme.id)
        .order_by(desc(FundFeatures.feature_date)).limit(1)
    )

    # Query NAV count for data quality calculation
    nav_count = await db.scalar(
        select(func.count(NAVRecord.id))
        .where(NAVRecord.scheme_id == scheme.id)
    ) or 0

    # Compute data quality indicators
    data_quality = _compute_data_quality(scheme.id, scheme, nav_count)

    nav_result = await db.execute(
        select(NAVRecord)
        .where(NAVRecord.scheme_id == scheme.id)
        .where(NAVRecord.nav_date >= one_year_ago)
        .order_by(NAVRecord.nav_date)
    )
    nav_history = [NAVPoint(nav_date=n.nav_date, nav=float(n.nav)) for n in nav_result.scalars()]

    score_hist_result = await db.execute(
        select(FundScore)
        .where(FundScore.scheme_id == scheme.id)
        .where(FundScore.score_date >= one_year_ago)
        .order_by(FundScore.score_date)
    )
    score_history = [
        ScoreHistoryPoint(
            score_date=s.score_date,
            composite_score=s.composite_score,
            conviction=s.conviction,
        )
        for s in score_hist_result.scalars()
    ]

    news_result = await db.execute(
        select(NewsArticle, NewsSentiment.sentiment_label, NewsSentiment.compound_score)
        .join(NewsSentiment, NewsSentiment.article_id == NewsArticle.id, isouter=True)
        .where(
            (NewsSentiment.scheme_id == scheme.id) |
            (NewsSentiment.category == scheme.category)
        )
        .where(NewsArticle.published_at >= datetime.utcnow() - timedelta(days=14))
        .order_by(desc(NewsArticle.published_at))
        .limit(15)
        .distinct()
    )
    recent_news = [
        NewsSnippet(
            title=row.NewsArticle.title,
            url=row.NewsArticle.url,
            published_at=row.NewsArticle.published_at,
            sentiment_label=row.sentiment_label,
            compound_score=row.compound_score,
            source=row.NewsArticle.source,
        )
        for row in news_result.all()
    ]

    # Enrich features with data quality if features exist
    features_out = None
    if features:
        features_out = FundFeaturesOut.model_validate(features)
        features_out.data_quality = data_quality

    return FundDetailOut(
        scheme=SchemeOut.model_validate(scheme),
        latest_score=FundScoreOut.model_validate(latest_score) if latest_score else None,
        metadata=FundMetaOut.model_validate(meta) if meta else None,
        features=features_out,
        nav_history=nav_history,
        score_history=score_history,
        recent_news=recent_news,
    )


# ── NAV history ───────────────────────────────────────────────────────────────

@app.get("/api/v1/funds/{scheme_code}/nav", response_model=list[NAVPoint], tags=["funds"])
async def get_nav_history(
    scheme_code: str,
    days: int = Query(365, ge=30, le=1825),
    db: AsyncSession = Depends(get_session),
):
    scheme = await db.scalar(select(Scheme).where(Scheme.scheme_code == scheme_code))
    if not scheme:
        raise HTTPException(status_code=404, detail=f"Scheme '{scheme_code}' not found.")
    since = date.today() - timedelta(days=days)
    result = await db.execute(
        select(NAVRecord)
        .where(NAVRecord.scheme_id == scheme.id)
        .where(NAVRecord.nav_date >= since)
        .order_by(NAVRecord.nav_date)
    )
    return [NAVPoint(nav_date=n.nav_date, nav=float(n.nav)) for n in result.scalars()]


# ── Top funds ─────────────────────────────────────────────────────────────────

@app.get("/api/v1/scores/top", response_model=list[FundCardOut], tags=["scores"])
async def top_funds(
    category:  str | None = Query(None),
    conviction: str | None = Query(None),
    limit:     int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_session),
):
    # Get latest score date
    latest_score_date = await db.scalar(
        select(func.max(FundScore.score_date))
    )
    
    if not latest_score_date:
        return []
    
    stmt = (
        select(Scheme, FundScore)
        .join(FundScore, FundScore.scheme_id == Scheme.id)
        .where(Scheme.is_active == True)
        .where(FundScore.score_date == latest_score_date)
        .order_by(desc(FundScore.composite_score))
    )
    if category:
        stmt = stmt.where(Scheme.category == category)
    if conviction:
        stmt = stmt.where(FundScore.conviction == conviction)
    stmt = stmt.limit(limit)

    rows = (await db.execute(stmt)).all()
    return [
        FundCardOut(
            id=s.id,
            scheme_code=s.scheme_code,
            scheme_name=s.scheme_name,
            amc_name=s.amc_name,
            category=s.category,
            composite_score=sc.composite_score,
            conviction=sc.conviction,
            risk_score=sc.risk_score,
            risk_level=sc.risk_level,
        )
        for s, sc in rows
    ]


# ── Admin refresh ─────────────────────────────────────────────────────────────

@app.post("/api/v1/admin/refresh", tags=["admin"])
async def manual_refresh():
    """Trigger immediate NAV pull + feature/score rebuild."""
    from backend.ingestion.scheduler import nav_job, score_job
    asyncio.create_task(nav_job())
    asyncio.create_task(score_job())
    return {"message": "Refresh jobs queued."}
