"""
Pydantic response schemas for the FastAPI layer.
Kept separate from ORM models to allow independent evolution.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ── Shared ────────────────────────────────────────────────────────────────────

class OrmBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ── Data Quality ──────────────────────────────────────────────────────────────

class DataQuality(BaseModel):
    """Indicates which metrics are calculated from sufficient data."""
    nav_days_available: int
    returns_valid: bool
    risk_metrics_valid: bool
    inception_date: date | None


# ── Scheme ────────────────────────────────────────────────────────────────────

class SchemeBase(OrmBase):
    scheme_code: str
    scheme_name: str
    amc_name: str
    category: str
    plan_type: str | None
    option_type: str | None
    is_active: bool


class SchemeOut(SchemeBase):
    id: int


# ── NAV ───────────────────────────────────────────────────────────────────────

class NAVPoint(OrmBase):
    nav_date: date
    nav: float


# ── Score ─────────────────────────────────────────────────────────────────────

class ComponentScores(BaseModel):
    returns: float | None = None
    consistency: float | None = None
    cost: float | None = None
    sentiment: float | None = None
    stability: float | None = None
    weights: dict[str, float] | None = None


class FundScoreOut(OrmBase):
    composite_score: float
    conviction: str
    model_version: str
    score_date: date
    score_returns: float | None
    score_consistency: float | None
    score_cost: float | None
    score_sentiment: float | None
    score_stability: float | None
    shap_json: str | None
    risk_score: float | None = None
    risk_level: str | None = None
    risk_shap_json: str | None = None


# ── Fund card (list view) ─────────────────────────────────────────────────────

class FundCardOut(BaseModel):
    """Compact representation used in the fund grid."""
    id: int
    scheme_code: str
    scheme_name: str
    amc_name: str
    category: str
    composite_score: float | None = None
    conviction: str | None = None
    return_1y: float | None = None
    return_3y: float | None = None
    sharpe_ratio: float | None = None
    expense_ratio: float | None = None
    aum_crore: float | None = None
    risk_score: float | None = None
    risk_level: str | None = None
    # Sparkline: last 30 NAV points
    nav_sparkline: list[NAVPoint] = Field(default_factory=list)
    data_quality: DataQuality | None = None


# ── Fund detail ───────────────────────────────────────────────────────────────

class FundMetaOut(OrmBase):
    as_of_date: date
    aum_crore: float | None
    expense_ratio: float | None
    fund_manager: str | None
    manager_tenure_years: float | None
    portfolio_turnover: float | None
    category_rank: int | None
    category_total: int | None
    benchmark_index: str | None


class FundFeaturesOut(OrmBase):
    feature_date: date
    return_1m: float | None
    return_3m: float | None
    return_6m: float | None
    return_1y: float | None
    return_3y: float | None
    return_5y: float | None
    volatility_1y: float | None
    sharpe_1y: float | None
    sortino_1y: float | None
    alpha_1y: float | None
    beta_1y: float | None
    max_drawdown_1y: float | None
    sentiment_7d: float | None
    sentiment_30d: float | None
    news_volume_7d: float | None
    data_quality: DataQuality | None = None


class NewsSnippet(BaseModel):
    title: str
    url: str | None
    published_at: datetime | None
    sentiment_label: str | None
    compound_score: float | None
    source: str


class ScoreHistoryPoint(BaseModel):
    score_date: date
    composite_score: float
    conviction: str


class FundDetailOut(BaseModel):
    scheme: SchemeOut
    latest_score: FundScoreOut | None
    metadata: FundMetaOut | None
    features: FundFeaturesOut | None
    nav_history: list[NAVPoint]           # last 365 days for main chart
    score_history: list[ScoreHistoryPoint]
    recent_news: list[NewsSnippet]


# ── Category summary ──────────────────────────────────────────────────────────

class CategorySummary(BaseModel):
    category: str
    fund_count: int
    avg_score: float | None
    top_fund_name: str | None
    top_fund_score: float | None


# ── Pagination wrapper ────────────────────────────────────────────────────────

class Page(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[Any]
