"""
Shared pytest fixtures for the MFScope test suite.

Uses an in-memory SQLite database — no external services required.
All fixtures are async-compatible via pytest-asyncio.
"""
from __future__ import annotations

import asyncio
from datetime import date, timedelta
from decimal import Decimal
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.db.models import (
    Base,
    FundCategory,
    FundFeatures,
    FundMetadata,
    FundScore,
    NAVRecord,
    NewsArticle,
    NewsSentiment,
    Scheme,
    ConvictionLabel,
    SentimentLabel,
)

# ── In-memory SQLite engine for tests ────────────────────────────────────────

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

TestSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


@pytest_asyncio.fixture(scope="session")
def event_loop():
    """Single event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def create_tables():
    """Create all tables once per session."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    """Fresh transactional session per test — rolled back on teardown."""
    async with TestSessionLocal() as session:
        yield session
        await session.rollback()


# ── Domain fixtures ───────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def sample_scheme(db: AsyncSession) -> Scheme:
    scheme = Scheme(
        scheme_code="999999",
        scheme_name="Test Large Cap Fund - Direct Growth",
        amc_name="Test AMC",
        category=FundCategory.LARGE_CAP.value,
        plan_type="Direct",
        option_type="Growth",
        is_active=True,
    )
    db.add(scheme)
    await db.commit()
    await db.refresh(scheme)
    return scheme


@pytest_asyncio.fixture
async def sample_nav_series(db: AsyncSession, sample_scheme: Scheme) -> list[NAVRecord]:
    """365 days of synthetic NAV data (linear trend + noise)."""
    import random
    random.seed(42)
    base_nav = 100.0
    records: list[NAVRecord] = []
    today = date.today()
    for i in range(365):
        d = today - timedelta(days=365 - i)
        base_nav *= 1 + random.gauss(0.0004, 0.008)
        rec = NAVRecord(
            scheme_id=sample_scheme.id,
            nav_date=d,
            nav=Decimal(str(round(base_nav, 4))),
        )
        db.add(rec)
        records.append(rec)
    await db.commit()
    return records


@pytest_asyncio.fixture
async def sample_metadata(db: AsyncSession, sample_scheme: Scheme) -> FundMetadata:
    meta = FundMetadata(
        scheme_id=sample_scheme.id,
        as_of_date=date.today(),
        aum_crore=12345.67,
        expense_ratio=0.45,
        fund_manager="Jane Doe",
        manager_tenure_years=5.5,
        portfolio_turnover=28.0,
        category_rank=5,
        category_total=40,
        benchmark_index="Nifty 50 TRI",
        source="test",
    )
    db.add(meta)
    await db.commit()
    await db.refresh(meta)
    return meta


@pytest_asyncio.fixture
async def sample_features(db: AsyncSession) -> FundFeatures:
    """Create sample features without creating a new scheme (use existing scheme_id if present)."""
    # Create a scheme for this fixture if needed
    scheme = Scheme(
        scheme_code="999998",  # Different scheme code to avoid conflicts
        scheme_name="Test Features Fund",
        amc_name="Test AMC",
        category=FundCategory.LARGE_CAP.value,
        plan_type="Direct",
        option_type="Growth",
        is_active=True,
    )
    db.add(scheme)
    await db.flush()
    
    feat = FundFeatures(
        scheme_id=scheme.id,
        feature_date=date.today(),
        return_1m=2.1,
        return_3m=5.4,
        return_6m=9.8,
        return_1y=18.5,
        return_3y=14.2,
        return_5y=12.1,
        volatility_1y=14.3,
        sharpe_1y=1.12,
        sortino_1y=1.45,
        alpha_1y=2.3,
        beta_1y=0.95,
        max_drawdown_1y=-8.4,
        expense_ratio=0.45,
        aum_crore=12345.67,
        aum_growth_3m=3.2,
        manager_tenure_years=5.5,
        portfolio_turnover=28.0,
        category_rank_pct=0.25,
        sentiment_7d=0.12,
        sentiment_30d=0.08,
        news_volume_7d=3.0,
        news_volume_spike=0.5,
        category_avg_return_1y=15.2,
    )
    db.add(feat)
    await db.commit()
    await db.refresh(feat)
    return feat


@pytest_asyncio.fixture
async def sample_score(db: AsyncSession, sample_scheme: Scheme) -> FundScore:
    score = FundScore(
        scheme_id=sample_scheme.id,
        score_date=date.today(),
        composite_score=74.5,
        conviction=ConvictionLabel.BUY.value,
        model_version="rule_based_v1",
        score_returns=78.0,
        score_consistency=70.0,
        score_cost=80.0,
        score_sentiment=65.0,
        score_stability=72.0,
    )
    db.add(score)
    await db.commit()
    await db.refresh(score)
    return score


@pytest_asyncio.fixture
async def sample_news(db: AsyncSession) -> tuple[NewsArticle, NewsSentiment]:
    article = NewsArticle(
        guid="test-guid-001",
        source="et_markets",
        title="Test fund posts strong quarterly returns",
        summary="The test fund delivered above-benchmark returns this quarter.",
        url="https://example.com/article/1",
    )
    db.add(article)
    await db.flush()

    sentiment = NewsSentiment(
        article_id=article.id,
        scheme_id=None,
        category=FundCategory.LARGE_CAP.value,
        sentiment_label=SentimentLabel.POSITIVE.value,
        positive_score=0.82,
        negative_score=0.05,
        neutral_score=0.13,
        compound_score=0.77,
        model_used="finbert",
    )
    db.add(sentiment)
    await db.commit()
    return article, sentiment


# ── FastAPI test client fixture ───────────────────────────────────────────────

@pytest_asyncio.fixture
async def api_client() -> AsyncGenerator[AsyncClient, None]:
    """
    HTTPX AsyncClient wired to the FastAPI app.
    Overrides the DB session dependency to use the in-memory test DB.
    """
    from backend.api.main import app
    from backend.db.session import AsyncSessionLocal as ProdSession

    # Override the DB dependency
    async def override_get_session():
        async with TestSessionLocal() as session:
            yield session

    app.dependency_overrides[
        # import the exact dependency function used in main.py
        __import__("backend.api.main", fromlist=["get_session"]).get_session
    ] = override_get_session

    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
