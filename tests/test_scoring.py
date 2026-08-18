"""
Tests for backend/scoring/rule_based.py

Covers:
- Conviction label mapping
- Percentile rank helpers
- Component score computation (known inputs)
- score_all integration
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from backend.db.models import ConvictionLabel
from backend.scoring.rule_based import (
    RuleBasedScorer,
    _compute_component_scores,
    _label,
    _pct_rank,
    _pct_rank_inv,
)


# ── Unit: label mapping ───────────────────────────────────────────────────────

class TestLabel:
    @pytest.mark.parametrize("score,expected", [
        (95.0,  ConvictionLabel.STRONG_BUY),
        (80.0,  ConvictionLabel.STRONG_BUY),
        (79.9,  ConvictionLabel.BUY),
        (60.0,  ConvictionLabel.BUY),
        (59.9,  ConvictionLabel.HOLD),
        (40.0,  ConvictionLabel.HOLD),
        (39.9,  ConvictionLabel.SELL),
        (20.0,  ConvictionLabel.SELL),
        (19.9,  ConvictionLabel.STRONG_SELL),
        (0.0,   ConvictionLabel.STRONG_SELL),
    ])
    def test_boundary_labels(self, score, expected):
        assert _label(score) == expected


# ── Unit: percentile rank ─────────────────────────────────────────────────────

class TestPercentileRank:
    def test_monotone_series(self):
        s = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0])
        ranked = _pct_rank(s)
        # Values should be strictly increasing
        assert list(ranked) == sorted(ranked)

    def test_all_same_values_median_rank(self):
        s = pd.Series([5.0] * 5)
        ranked = _pct_rank(s)
        # All tied → all get same rank
        assert ranked.nunique() == 1

    def test_nan_filled_with_50(self):
        s = pd.Series([10.0, float("nan"), 30.0])
        ranked = _pct_rank(s)
        assert ranked.iloc[1] == pytest.approx(50.0)

    def test_inverted_rank_is_complement(self):
        s = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0])
        r  = _pct_rank(s)
        ri = _pct_rank_inv(s)
        # sum of rank and inv-rank should be ≈ 100 for each element
        for a, b in zip(r, ri):
            assert a + b == pytest.approx(100.0, abs=0.01)


# ── Unit: component score computation ────────────────────────────────────────

def _make_category_df(n: int = 20) -> pd.DataFrame:
    """Create a synthetic DataFrame of n funds with all required feature columns."""
    np.random.seed(42)
    return pd.DataFrame({
        "scheme_id":            list(range(1, n + 1)),
        "category":             ["Large Cap"] * n,
        "sharpe_1y":            np.random.normal(0.8, 0.3, n),
        "sortino_1y":           np.random.normal(1.0, 0.4, n),
        "alpha_1y":             np.random.normal(1.5, 1.0, n),
        "return_1y":            np.random.normal(15.0, 5.0, n),
        "return_1m":            np.random.normal(1.0, 1.5, n),
        "return_3m":            np.random.normal(3.0, 2.0, n),
        "return_6m":            np.random.normal(7.0, 3.0, n),
        "volatility_1y":        np.random.uniform(10.0, 20.0, n),
        "max_drawdown_1y":      np.random.uniform(-15.0, -3.0, n),
        "expense_ratio":        np.random.uniform(0.1, 1.5, n),
        "aum_growth_3m":        np.random.normal(5.0, 10.0, n),
        "manager_tenure_years": np.random.uniform(1.0, 15.0, n),
        "sentiment_7d":         np.random.uniform(-0.3, 0.5, n),
        "sentiment_30d":        np.random.uniform(-0.2, 0.4, n),
    })


class TestComputeComponentScores:
    def test_returns_expected_columns(self):
        df = _make_category_df()
        result = _compute_component_scores(df)
        for col in ["score_returns", "score_consistency", "score_cost",
                    "score_sentiment", "score_stability", "composite_score"]:
            assert col in result.columns

    def test_composite_score_in_range(self):
        df = _make_category_df()
        result = _compute_component_scores(df)
        assert (result["composite_score"] >= 0).all()
        assert (result["composite_score"] <= 100).all()

    def test_no_nan_composite(self):
        df = _make_category_df()
        result = _compute_component_scores(df)
        assert result["composite_score"].isna().sum() == 0

    def test_higher_sharpe_tends_to_higher_score(self):
        """Fund with highest Sharpe in its category should score above median."""
        df = _make_category_df(n=30)
        result = _compute_component_scores(df)
        best_idx  = df["sharpe_1y"].idxmax()
        worst_idx = df["sharpe_1y"].idxmin()
        assert (result.loc[best_idx, "score_returns"] >
                result.loc[worst_idx, "score_returns"])

    def test_lower_expense_ratio_higher_cost_score(self):
        df = _make_category_df(n=20)
        result = _compute_component_scores(df)
        cheapest = df["expense_ratio"].idxmin()
        priciest = df["expense_ratio"].idxmax()
        assert result.loc[cheapest, "score_cost"] > result.loc[priciest, "score_cost"]


# ── Integration: score_all ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_score_all_writes_fund_score(db, sample_features, sample_scheme):
    """score_all should create a FundScore row for today."""
    import backend.scoring.rule_based as mod
    from sqlalchemy import select
    from backend.db.models import FundScore
    from tests.conftest import TestSessionLocal

    original = mod.AsyncSessionLocal
    mod.AsyncSessionLocal = TestSessionLocal

    try:
        scorer = RuleBasedScorer()
        written = await scorer.score_all(as_of=sample_features.feature_date)
        assert written >= 1

        row = await db.scalar(
            select(FundScore)
            .where(FundScore.scheme_id == sample_scheme.id)
            .where(FundScore.score_date == sample_features.feature_date)
        )
        assert row is not None
        assert 0 <= row.composite_score <= 100
        assert row.conviction in [v.value for v in ConvictionLabel]
    finally:
        mod.AsyncSessionLocal = original


@pytest.mark.asyncio
async def test_score_all_no_features_returns_zero(db):
    """score_all on a date with no features should return 0."""
    import backend.scoring.rule_based as mod
    from tests.conftest import TestSessionLocal

    original = mod.AsyncSessionLocal
    mod.AsyncSessionLocal = TestSessionLocal

    try:
        scorer = RuleBasedScorer()
        from datetime import date
        far_future = date(2099, 1, 1)
        written = await scorer.score_all(as_of=far_future)
        assert written == 0
    finally:
        mod.AsyncSessionLocal = original
