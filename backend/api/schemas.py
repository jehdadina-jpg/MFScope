"""
Pydantic response schemas.

Kept separate from the ORM so the wire format can evolve independently, and so
every field the frontend relies on is declared in one readable place.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class OrmBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ── Data quality ──────────────────────────────────────────────────────────────

class DataQuality(BaseModel):
    """
    What the numbers on this fund are actually based on.

    Surfaced rather than hidden: a 1-year return computed from eight months of
    NAV is not a 1-year return, and the UI needs to be able to say so.
    """
    nav_days_available: int
    history_years: float | None = None
    first_nav_date: date | None = None
    latest_nav_date: date | None = None
    returns_valid: bool
    risk_metrics_valid: bool
    inception_date: date | None = None
    #: Corporate actions (payouts, splits, side-pocketing) neutralised in the
    #: NAV series before any metric was computed.
    nav_adjustments: int = 0


# ── Scheme ────────────────────────────────────────────────────────────────────

class SchemeOut(OrmBase):
    id: int
    scheme_code: str
    scheme_name: str
    amc_name: str
    category: str
    asset_class: str | None = None
    plan_type: str | None = None
    option_type: str | None = None
    inception_date: date | None = None
    is_active: bool
    is_investable: bool | None = None
    nav_latest: float | None = None
    nav_latest_date: date | None = None


# ── NAV ───────────────────────────────────────────────────────────────────────

class NAVPoint(OrmBase):
    nav_date: date
    nav: float


class SeriesPoint(BaseModel):
    """A point on a rebased comparison curve (start = 100)."""
    date: date
    value: float


# ── Scores ────────────────────────────────────────────────────────────────────

class ComponentBreakdown(BaseModel):
    """Parsed form of the scorer's explanation blob."""
    components: dict[str, float] = Field(default_factory=dict)
    weights: dict[str, float] = Field(default_factory=dict)
    nominal_weights: dict[str, float] = Field(default_factory=dict)
    missing: list[str] = Field(default_factory=list)
    #: The un-spread blend before the peer-group normal-scores transform —
    #: see backend/scoring/rule_based.py's module docstring. composite_score
    #: is what's shown everywhere; this is here for anyone who wants the raw
    #: number the spread was computed from.
    blended_score: float | None = None
    data_confidence: float | None = None
    peer_group: str | None = None
    peer_count: int | None = None
    model_version: str | None = None


class RiskBreakdown(BaseModel):
    model_version: str | None = None
    components: dict[str, float | None] = Field(default_factory=dict)
    weights: dict[str, float] = Field(default_factory=dict)
    inputs: dict[str, float | None] = Field(default_factory=dict)
    confidence: float | None = None


class FundScoreOut(OrmBase):
    score_date: date
    composite_score: float
    conviction: str
    model_version: str
    score_returns: float | None = None
    score_consistency: float | None = None
    score_momentum: float | None = None
    score_cost: float | None = None
    score_sentiment: float | None = None
    score_stability: float | None = None
    data_confidence: float | None = None
    peer_group: str | None = None
    peer_count: int | None = None
    peer_rank: int | None = None
    risk_score: float | None = None
    risk_level: str | None = None
    breakdown: ComponentBreakdown | None = None
    risk_breakdown: RiskBreakdown | None = None


# ── Fund card (list view) ─────────────────────────────────────────────────────

class FundCardOut(BaseModel):
    """Compact representation used in the fund grid and tables."""
    id: int
    scheme_code: str
    scheme_name: str
    amc_name: str
    category: str
    asset_class: str | None = None
    plan_type: str | None = None

    composite_score: float | None = None
    conviction: str | None = None
    data_confidence: float | None = None
    peer_rank: int | None = None
    peer_count: int | None = None

    risk_score: float | None = None
    risk_level: str | None = None

    return_1y: float | None = None
    return_3y: float | None = None
    return_5y: float | None = None
    volatility_1y: float | None = None
    sharpe_1y: float | None = None
    max_drawdown_1y: float | None = None
    expense_ratio: float | None = None
    aum_crore: float | None = None

    nav: float | None = None
    nav_date: date | None = None
    nav_sparkline: list[float] = Field(default_factory=list)
    data_quality: DataQuality | None = None


# ── Fund detail ───────────────────────────────────────────────────────────────

class FundMetaOut(OrmBase):
    as_of_date: date
    aum_crore: float | None = None
    expense_ratio: float | None = None
    fund_manager: str | None = None
    manager_tenure_years: float | None = None
    portfolio_turnover: float | None = None
    category_rank: int | None = None
    category_total: int | None = None
    benchmark_index: str | None = None


class FundFeaturesOut(OrmBase):
    feature_date: date

    return_1m: float | None = None
    return_3m: float | None = None
    return_6m: float | None = None
    return_ytd: float | None = None
    return_1y: float | None = None
    return_2y: float | None = None
    return_3y: float | None = None
    return_5y: float | None = None
    return_10y: float | None = None
    return_since_inception: float | None = None

    volatility_1y: float | None = None
    volatility_3y: float | None = None
    downside_deviation_1y: float | None = None
    sharpe_1y: float | None = None
    sortino_1y: float | None = None
    calmar_1y: float | None = None
    var_95_1y: float | None = None
    alpha_1y: float | None = None
    beta_1y: float | None = None
    r_squared_1y: float | None = None
    tracking_error_1y: float | None = None
    information_ratio_1y: float | None = None
    up_capture_1y: float | None = None
    down_capture_1y: float | None = None
    max_drawdown_1y: float | None = None
    max_drawdown_3y: float | None = None
    drawdown_recovery_days: float | None = None

    rolling_1y_mean: float | None = None
    rolling_1y_std: float | None = None
    rolling_1y_best: float | None = None
    rolling_1y_worst: float | None = None
    rolling_1y_positive_pct: float | None = None

    momentum_roc_1m: float | None = None
    momentum_roc_3m: float | None = None
    momentum_roc_6m: float | None = None
    ma_50d: float | None = None
    ma_200d: float | None = None
    ma_crossover: float | None = None

    expense_ratio: float | None = None
    aum_crore: float | None = None
    sentiment_7d: float | None = None
    sentiment_30d: float | None = None
    news_volume_7d: float | None = None

    history_years: float | None = None
    nav_days: float | None = None
    data_quality: DataQuality | None = None


class PeerStat(BaseModel):
    """Where this fund sits against its peer group on one metric."""
    metric: str
    value: float | None
    peer_median: float | None
    peer_best: float | None
    peer_worst: float | None
    percentile: float | None
    higher_is_better: bool


class NewsSnippet(BaseModel):
    title: str
    url: str | None = None
    published_at: datetime | None = None
    sentiment_label: str | None = None
    compound_score: float | None = None
    source: str


class ScoreHistoryPoint(BaseModel):
    score_date: date
    composite_score: float
    conviction: str


class FundDetailOut(BaseModel):
    scheme: SchemeOut
    latest_score: FundScoreOut | None = None
    fund_metadata: FundMetaOut | None = Field(default=None, alias="metadata")
    features: FundFeaturesOut | None = None
    nav_history: list[NAVPoint] = Field(default_factory=list)
    #: Fund vs. peer-group median, both rebased to 100 at the window start.
    benchmark_series: list[SeriesPoint] = Field(default_factory=list)
    fund_series: list[SeriesPoint] = Field(default_factory=list)
    score_history: list[ScoreHistoryPoint] = Field(default_factory=list)
    peer_stats: list[PeerStat] = Field(default_factory=list)
    recent_news: list[NewsSnippet] = Field(default_factory=list)
    similar_funds: list[FundCardOut] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)


# ── Aggregates ────────────────────────────────────────────────────────────────

class CategorySummary(BaseModel):
    category: str
    asset_class: str | None = None
    fund_count: int
    avg_score: float | None = None
    median_return_1y: float | None = None
    avg_risk_score: float | None = None
    top_fund_code: str | None = None
    top_fund_name: str | None = None
    top_fund_score: float | None = None


class AMCSummary(BaseModel):
    amc_name: str
    fund_count: int
    avg_score: float | None = None
    top_fund_name: str | None = None
    top_fund_score: float | None = None


class UniverseStats(BaseModel):
    """Headline numbers for the dashboard."""
    total_schemes: int
    investable_schemes: int
    scored_schemes: int
    nav_records: int
    amc_count: int
    category_count: int
    latest_nav_date: date | None = None
    latest_score_date: date | None = None
    median_return_1y: float | None = None
    conviction_breakdown: dict[str, int] = Field(default_factory=dict)
    risk_breakdown: dict[str, int] = Field(default_factory=dict)
    asset_class_breakdown: dict[str, int] = Field(default_factory=dict)
    mean_data_confidence: float | None = None


class FilterOptions(BaseModel):
    """Everything the filter UI needs, in one round trip."""
    categories: list[CategorySummary] = Field(default_factory=list)
    asset_classes: list[str] = Field(default_factory=list)
    amcs: list[str] = Field(default_factory=list)
    convictions: list[str] = Field(default_factory=list)
    risk_levels: list[str] = Field(default_factory=list)
    plan_types: list[str] = Field(default_factory=list)


# ── Pagination ────────────────────────────────────────────────────────────────

class Page(BaseModel, Generic[T]):
    total: int
    page: int
    page_size: int
    total_pages: int = 0
    items: list[T] = Field(default_factory=list)


SortField = Literal[
    "composite_score",
    "return_1y",
    "return_3y",
    "return_5y",
    "sharpe_1y",
    "volatility_1y",
    "max_drawdown_1y",
    "risk_score",
    "expense_ratio",
    "aum_crore",
    "scheme_name",
]
