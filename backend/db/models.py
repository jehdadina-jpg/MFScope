"""
SQLAlchemy ORM models for MFScope.

Tables
------
Scheme          — AMFI scheme master (one row per fund / plan)
NAVRecord       — daily NAV history per scheme
FundMetadata    — AUM, expense ratio, fund manager, category rank (scraped)
NewsArticle     — ingested news headlines with raw text
NewsSentiment   — per-article FinBERT / VADER scores + entity links
FundFeatures    — engineered feature snapshot per scheme per date
FundScore       — final composite score + conviction label per scheme per date
"""

from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


# ── Base ──────────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


# ── Enums ─────────────────────────────────────────────────────────────────────

class ConvictionLabel(str, enum.Enum):
    STRONG_BUY = "Strong Buy"
    BUY = "Buy"
    HOLD = "Hold"
    SELL = "Sell"
    STRONG_SELL = "Strong Sell"


class SentimentLabel(str, enum.Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


class FundCategory(str, enum.Enum):
    # Equity
    LARGE_CAP = "Large Cap"
    MID_CAP = "Mid Cap"
    SMALL_CAP = "Small Cap"
    LARGE_MID_CAP = "Large & Mid Cap"
    FLEXI_CAP = "Flexi Cap"
    MULTI_CAP = "Multi Cap"
    ELSS = "ELSS"
    # Sectoral / Thematic
    DEFENSE = "Defense"
    PSU = "PSU"
    BANKING_FINANCIAL = "Banking & Financial Services"
    PHARMA_HEALTHCARE = "Pharma & Healthcare"
    IT_TECHNOLOGY = "IT/Technology"
    INFRASTRUCTURE = "Infrastructure"
    CONSUMPTION = "Consumption"
    ENERGY = "Energy"
    SECTORAL_OTHER = "Sectoral/Thematic Other"
    # Debt
    LIQUID = "Liquid"
    OVERNIGHT = "Overnight"
    SHORT_DURATION = "Short Duration"
    CORPORATE_BOND = "Corporate Bond"
    GILT = "Gilt"
    DEBT_OTHER = "Debt Other"
    # Hybrid
    AGGRESSIVE_HYBRID = "Aggressive Hybrid"
    BALANCED_ADVANTAGE = "Balanced Advantage"
    MULTI_ASSET = "Multi-Asset"
    # Index / Passive
    INDEX_NIFTY50 = "Index - Nifty 50"
    INDEX_SENSEX = "Index - Sensex"
    INDEX_NIFTY_NEXT50 = "Index - Nifty Next 50"
    INDEX_OTHER = "Index Other"
    # International
    INTERNATIONAL = "International/FoF"
    # Unknown
    OTHER = "Other"


# ── Models ────────────────────────────────────────────────────────────────────

class Scheme(Base):
    """
    AMFI scheme master — one row per fund / plan / option.
    
    Tracks fund inception date for data quality validation and display.
    """
    __tablename__ = "scheme"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scheme_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    isin_growth: Mapped[str | None] = mapped_column(String(20))
    isin_div_reinvest: Mapped[str | None] = mapped_column(String(20))
    scheme_name: Mapped[str] = mapped_column(String(512), nullable=False)
    amc_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    category: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="Other",
        index=True,
    )
    sub_category: Mapped[str | None] = mapped_column(String(128))
    plan_type: Mapped[str | None] = mapped_column(String(32))   # Direct / Regular
    option_type: Mapped[str | None] = mapped_column(String(32)) # Growth / Dividend
    inception_date: Mapped[date | None] = mapped_column(Date, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # relationships
    nav_records: Mapped[list[NAVRecord]] = relationship(back_populates="scheme", cascade="all, delete-orphan")
    metadata_: Mapped[list[FundMetadata]] = relationship(back_populates="scheme", cascade="all, delete-orphan")
    features: Mapped[list[FundFeatures]] = relationship(back_populates="scheme", cascade="all, delete-orphan")
    scores: Mapped[list[FundScore]] = relationship(back_populates="scheme", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Scheme {self.scheme_code} | {self.scheme_name[:40]}>"


class NAVRecord(Base):
    """Daily NAV snapshot per scheme."""
    __tablename__ = "nav_record"
    __table_args__ = (UniqueConstraint("scheme_id", "nav_date", name="uq_nav_scheme_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scheme_id: Mapped[int] = mapped_column(ForeignKey("scheme.id"), nullable=False, index=True)
    nav_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    nav: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    repurchase_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    sale_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    ingested_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    scheme: Mapped[Scheme] = relationship(back_populates="nav_records")


class FundMetadata(Base):
    """AUM, expense ratio, manager info — scraped periodically."""
    __tablename__ = "fund_metadata"
    __table_args__ = (UniqueConstraint("scheme_id", "as_of_date", name="uq_meta_scheme_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scheme_id: Mapped[int] = mapped_column(ForeignKey("scheme.id"), nullable=False, index=True)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)

    aum_crore: Mapped[float | None] = mapped_column(Float)           # AUM in crores INR
    expense_ratio: Mapped[float | None] = mapped_column(Float)       # percentage
    fund_manager: Mapped[str | None] = mapped_column(String(256))
    manager_tenure_years: Mapped[float | None] = mapped_column(Float)
    portfolio_turnover: Mapped[float | None] = mapped_column(Float)  # percentage
    category_rank: Mapped[int | None] = mapped_column(Integer)       # rank within category
    category_total: Mapped[int | None] = mapped_column(Integer)      # total funds in category
    benchmark_index: Mapped[str | None] = mapped_column(String(128))
    star_rating: Mapped[int | None] = mapped_column(Integer)         # 1-5 if available
    source: Mapped[str | None] = mapped_column(String(64))           # "moneycontrol" | "valueresearch"
    ingested_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    scheme: Mapped[Scheme] = relationship(back_populates="metadata_")


class NewsArticle(Base):
    """Raw news article ingested from RSS feeds."""
    __tablename__ = "news_article"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guid: Mapped[str] = mapped_column(String(512), unique=True, nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)   # "et_markets" etc.
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(String(2048))
    published_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    sentiments: Mapped[list[NewsSentiment]] = relationship(
        back_populates="article", cascade="all, delete-orphan"
    )


class NewsSentiment(Base):
    """
    Sentiment score for a news article, optionally linked to a scheme.
    An article may link to multiple schemes (e.g. sector news).
    """
    __tablename__ = "news_sentiment"
    __table_args__ = (
        UniqueConstraint("article_id", "scheme_id", name="uq_sentiment_article_scheme"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("news_article.id"), nullable=False, index=True)
    scheme_id: Mapped[int | None] = mapped_column(ForeignKey("scheme.id"), index=True)  # nullable = sector-level
    category: Mapped[str | None] = mapped_column(String(64), index=True)  # sector / category tag

    sentiment_label: Mapped[str] = mapped_column(String(16), nullable=False)
    positive_score: Mapped[float] = mapped_column(Float, default=0.0)
    negative_score: Mapped[float] = mapped_column(Float, default=0.0)
    neutral_score: Mapped[float] = mapped_column(Float, default=0.0)
    compound_score: Mapped[float] = mapped_column(Float, default=0.0)  # VADER compound or finbert max
    model_used: Mapped[str] = mapped_column(String(64), default="finbert")
    scored_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    article: Mapped[NewsArticle] = relationship(back_populates="sentiments")


class FundFeatures(Base):
    """
    Engineered feature snapshot — one row per (scheme, date).
    All numeric; NULLs allowed where data is unavailable.
    """
    __tablename__ = "fund_features"
    __table_args__ = (UniqueConstraint("scheme_id", "feature_date", name="uq_feat_scheme_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scheme_id: Mapped[int] = mapped_column(ForeignKey("scheme.id"), nullable=False, index=True)
    feature_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # ── Trailing returns (%) ──────────────────────────────────────────────────
    return_1m: Mapped[float | None] = mapped_column(Float)
    return_3m: Mapped[float | None] = mapped_column(Float)
    return_6m: Mapped[float | None] = mapped_column(Float)
    return_1y: Mapped[float | None] = mapped_column(Float)
    return_3y: Mapped[float | None] = mapped_column(Float)
    return_5y: Mapped[float | None] = mapped_column(Float)

    # ── Risk metrics ─────────────────────────────────────────────────────────
    volatility_1y: Mapped[float | None] = mapped_column(Float)     # annualised std dev
    sharpe_1y: Mapped[float | None] = mapped_column(Float)
    sortino_1y: Mapped[float | None] = mapped_column(Float)
    alpha_1y: Mapped[float | None] = mapped_column(Float)
    beta_1y: Mapped[float | None] = mapped_column(Float)
    max_drawdown_1y: Mapped[float | None] = mapped_column(Float)
    drawdown_recovery_days: Mapped[float | None] = mapped_column(Float)

    # ── Momentum ─────────────────────────────────────────────────────────────
    momentum_roc_1m: Mapped[float | None] = mapped_column(Float)   # rate of change
    momentum_roc_3m: Mapped[float | None] = mapped_column(Float)
    ma_50d: Mapped[float | None] = mapped_column(Float)
    ma_200d: Mapped[float | None] = mapped_column(Float)
    ma_crossover: Mapped[float | None] = mapped_column(Float)      # nav / ma200 ratio

    # ── Fundamental / fund-specific ───────────────────────────────────────────
    expense_ratio: Mapped[float | None] = mapped_column(Float)
    aum_crore: Mapped[float | None] = mapped_column(Float)
    aum_growth_3m: Mapped[float | None] = mapped_column(Float)     # % change in AUM
    manager_tenure_years: Mapped[float | None] = mapped_column(Float)
    portfolio_turnover: Mapped[float | None] = mapped_column(Float)
    category_rank_pct: Mapped[float | None] = mapped_column(Float) # 0–1 percentile (lower = better rank)

    # ── Sentiment ────────────────────────────────────────────────────────────
    sentiment_7d: Mapped[float | None] = mapped_column(Float)      # rolling avg compound score
    sentiment_30d: Mapped[float | None] = mapped_column(Float)
    news_volume_7d: Mapped[float | None] = mapped_column(Float)    # article count
    news_volume_spike: Mapped[float | None] = mapped_column(Float) # z-score vs 90-day avg

    # ── Category / sector context ─────────────────────────────────────────────
    category_avg_return_1y: Mapped[float | None] = mapped_column(Float)
    sector_index_return_1m: Mapped[float | None] = mapped_column(Float)

    computed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    scheme: Mapped[Scheme] = relationship(back_populates="features")


class FundScore(Base):
    """Final composite score and conviction label per scheme per date."""
    __tablename__ = "fund_score"
    __table_args__ = (UniqueConstraint("scheme_id", "score_date", name="uq_score_scheme_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scheme_id: Mapped[int] = mapped_column(ForeignKey("scheme.id"), nullable=False, index=True)
    score_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    composite_score: Mapped[float] = mapped_column(Float, nullable=False)   # 0–100
    conviction: Mapped[str] = mapped_column(String(32), nullable=False)
    model_version: Mapped[str] = mapped_column(String(32), default="rule_based_v1")

    # Component scores (0–100 each) for explainability breakdown in UI
    score_returns: Mapped[float | None] = mapped_column(Float)
    score_consistency: Mapped[float | None] = mapped_column(Float)
    score_cost: Mapped[float | None] = mapped_column(Float)
    score_sentiment: Mapped[float | None] = mapped_column(Float)
    score_stability: Mapped[float | None] = mapped_column(Float)

    # SHAP / feature importance JSON blob (populated by ML model)
    shap_json: Mapped[str | None] = mapped_column(Text)

    # Risk assessment (0-100 score and Low/Medium/High level)
    risk_score: Mapped[float | None] = mapped_column(Float)         # 0-100
    risk_level: Mapped[str | None] = mapped_column(String(16))      # Low / Medium / High
    risk_shap_json: Mapped[str | None] = mapped_column(Text)        # Risk SHAP values

    scored_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    scheme: Mapped[Scheme] = relationship(back_populates="scores")

    def __repr__(self) -> str:
        return f"<FundScore {self.scheme_id} | {self.score_date} | {self.composite_score:.1f} {self.conviction}>"
