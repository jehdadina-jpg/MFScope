"""
Rule-Based Composite Scorer  (v1)
==================================
Converts a FundFeatures row into a 0–100 composite score and a 5-tier
conviction label.

Scoring method
--------------
Each feature group is normalised to a 0–100 percentile *within its category*
(small-cap funds are only ranked against other small-cap funds).  The five
component scores are then combined with fixed weights:

    Component             Weight   Key features
    ─────────────────── ─ ──────   ────────────────────────────────
    Risk-adjusted returns  45%    Sharpe, Sortino, alpha
    Consistency            25%    Return std dev (inverted), max drawdown (inv)
    Cost efficiency        10%    Expense ratio (inverted)
    News sentiment         10%    Compound sentiment 7d + 30d
    Stability              10%    AUM trend, manager tenure

Missing data is penalized: null values default to 25th percentile (below average),
and the final score is multiplied by a data completeness ratio.

Label mapping
─────────────
    75–100  →  Strong Buy
    60–74   →  Buy
    45–59   →  Hold
    25–44   →  Sell
     0–24   →  Strong Sell

Public interface
----------------
    scorer = RuleBasedScorer()
    await scorer.score_all(as_of=date.today())
    score, label = await scorer.score_scheme(scheme_id, as_of=date.today())
"""

from __future__ import annotations

import asyncio
import json
from datetime import date
from typing import Any

import numpy as np
import pandas as pd
from loguru import logger
from sqlalchemy import select

from backend.db.models import ConvictionLabel, FundFeatures, FundScore, Scheme
from backend.db.session import AsyncSessionLocal

# ── Weights ───────────────────────────────────────────────────────────────────

WEIGHTS = {
    "returns":     0.45,  # Increased from 0.40 to emphasize performance
    "consistency": 0.25,  # Increased from 0.20 to reward stability
    "cost":        0.10,  # Decreased from 0.15
    "sentiment":   0.10,  # Decreased from 0.15
    "stability":   0.10,  # Same
}

# ── Label mapping ─────────────────────────────────────────────────────────────

def _label(score: float) -> ConvictionLabel:
    if score >= 75:  # Changed from 80 for better distribution
        return ConvictionLabel.STRONG_BUY
    if score >= 60:  # Same
        return ConvictionLabel.BUY
    if score >= 45:  # Changed from 40 for more precision
        return ConvictionLabel.HOLD
    if score >= 25:  # Changed from 20 to avoid overly harsh labels
        return ConvictionLabel.SELL
    return ConvictionLabel.STRONG_SELL


# ── Percentile helpers ────────────────────────────────────────────────────────

def _pct_rank(series: pd.Series) -> pd.Series:
    """
    Rank each value as a percentile in [0, 100].
    Higher rank = higher value (better for positive metrics like returns).
    Missing values get 25 (below average) to penalize incomplete data.
    """
    ranked = series.rank(pct=True, na_option="keep") * 100
    return ranked.fillna(25.0)  # Changed from 50 to 25 to penalize missing data


def _pct_rank_inv(series: pd.Series) -> pd.Series:
    """
    Inverted percentile rank: lower value → higher score.
    Used for expense ratio, drawdown (negative), etc.
    """
    return 100 - _pct_rank(series)


# ── Score computation ─────────────────────────────────────────────────────────

def _compute_component_scores(df: pd.DataFrame) -> pd.DataFrame:
    """
    Given a DataFrame of FundFeatures rows for a single category,
    return a DataFrame with component score columns added.
    """

    # ── Calculate data completeness penalty ──────────────────────────────────
    # Penalize missing data: funds with incomplete data score lower
    data_completeness = df[[
        'sharpe_1y', 'sortino_1y', 'alpha_1y', 'return_1y',
        'volatility_1y', 'max_drawdown_1y', 'expense_ratio',
        'sentiment_7d', 'sentiment_30d', 'aum_growth_3m', 'manager_tenure_years'
    ]].notna().mean(axis=1) * 100

    # ── Returns score ────────────────────────────────────────────────────────
    # Primary: Sharpe + Sortino; supplement with alpha and 1Y return
    sharpe_pct  = _pct_rank(df["sharpe_1y"])
    sortino_pct = _pct_rank(df["sortino_1y"])
    alpha_pct   = _pct_rank(df["alpha_1y"])
    ret1y_pct   = _pct_rank(df["return_1y"])
    df["score_returns"] = (
        sharpe_pct  * 0.35
        + sortino_pct * 0.35
        + alpha_pct   * 0.15
        + ret1y_pct   * 0.15
    )

    # ── Consistency score ─────────────────────────────────────────────────────
    # Inverse volatility, inverse drawdown, stability across periods
    vol_pct    = _pct_rank_inv(df["volatility_1y"])
    mdd_pct    = _pct_rank_inv(df["max_drawdown_1y"])   # drawdown is negative → invert
    # Rolling return stability: lower std dev across 1M/3M/6M/1Y is better
    df["_ret_spread"] = (
        df[["return_1m", "return_3m", "return_6m", "return_1y"]]
        .apply(lambda row: row.std(), axis=1)
    )
    spread_pct = _pct_rank_inv(df["_ret_spread"])
    df["score_consistency"] = (
        vol_pct    * 0.40
        + mdd_pct  * 0.35
        + spread_pct * 0.25
    )

    # ── Cost score ───────────────────────────────────────────────────────────
    df["score_cost"] = _pct_rank_inv(df["expense_ratio"])

    # ── Sentiment score ──────────────────────────────────────────────────────
    sent7_pct  = _pct_rank(df["sentiment_7d"])
    sent30_pct = _pct_rank(df["sentiment_30d"])
    df["score_sentiment"] = sent7_pct * 0.55 + sent30_pct * 0.45

    # ── Stability score ──────────────────────────────────────────────────────
    aum_growth_pct = _pct_rank(df["aum_growth_3m"])
    tenure_pct     = _pct_rank(df["manager_tenure_years"])
    df["score_stability"] = aum_growth_pct * 0.50 + tenure_pct * 0.50

    # ── Composite with data completeness penalty ─────────────────────────────
    # Apply data completeness penalty to final score
    df["composite_score"] = (
        df["score_returns"]     * WEIGHTS["returns"]
        + df["score_consistency"] * WEIGHTS["consistency"]
        + df["score_cost"]        * WEIGHTS["cost"]
        + df["score_sentiment"]   * WEIGHTS["sentiment"]
        + df["score_stability"]   * WEIGHTS["stability"]
    ) * (data_completeness / 100)  # Multiply by completeness ratio
    df["composite_score"] = df["composite_score"].clip(0, 100)

    return df


# ── Explainability breakdown ──────────────────────────────────────────────────

def _breakdown_json(row: pd.Series) -> str:
    """Human-readable component breakdown dict for UI display."""
    return json.dumps({
        "returns":     round(float(row.get("score_returns", 50)), 1),
        "consistency": round(float(row.get("score_consistency", 50)), 1),
        "cost":        round(float(row.get("score_cost", 50)), 1),
        "sentiment":   round(float(row.get("score_sentiment", 50)), 1),
        "stability":   round(float(row.get("score_stability", 50)), 1),
        "weights":     WEIGHTS,
    })


# ── Main scorer ───────────────────────────────────────────────────────────────

class RuleBasedScorer:

    async def score_all(self, as_of: date | None = None) -> int:
        """
        Score all schemes that have feature rows for `as_of`.
        Scoring is done per-category to ensure apples-to-apples percentile ranking.
        Returns the number of fund scores written.
        """
        if as_of is None:
            as_of = date.today()

        logger.info(f"Rule-based scoring for {as_of} …")

        # Load all FundFeatures for this date
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(FundFeatures, Scheme.category)
                .join(Scheme, FundFeatures.scheme_id == Scheme.id)
                .where(FundFeatures.feature_date == as_of)
            )
            rows = result.all()

        if not rows:
            logger.warning(f"No feature rows found for {as_of}. Run FeatureBuilder first.")
            return 0

        # Build a DataFrame
        records: list[dict] = []
        for feat, category in rows:
            d = {c.name: getattr(feat, c.name) for c in feat.__table__.columns}
            d["category"] = category
            records.append(d)

        df = pd.DataFrame(records)

        # Score per category group
        scored_dfs: list[pd.DataFrame] = []
        for cat, group in df.groupby("category"):
            scored_group = _compute_component_scores(group.copy())
            scored_dfs.append(scored_group)

        scored = pd.concat(scored_dfs, ignore_index=True)

        # Persist scores
        written = await self._persist_scores(scored, as_of)
        logger.info(f"Scoring complete: {written} fund scores written.")
        return written

    async def score_scheme(
        self,
        scheme_id: int,
        as_of: date | None = None,
    ) -> tuple[float, ConvictionLabel] | None:
        """
        Score a single scheme.  Falls back to scoring its entire category
        so the percentile rank is still meaningful.
        Returns (composite_score, label) or None if no features available.
        """
        if as_of is None:
            as_of = date.today()

        async with AsyncSessionLocal() as session:
            scheme = await session.get(Scheme, scheme_id)
            if not scheme:
                return None

            result = await session.execute(
                select(FundFeatures, Scheme.category)
                .join(Scheme, FundFeatures.scheme_id == Scheme.id)
                .where(FundFeatures.feature_date == as_of)
                .where(Scheme.category == scheme.category)
            )
            rows = result.all()

        if not rows:
            return None

        records = []
        for feat, cat in rows:
            d = {c.name: getattr(feat, c.name) for c in feat.__table__.columns}
            d["category"] = cat
            records.append(d)

        df = _compute_component_scores(pd.DataFrame(records))
        target = df[df["scheme_id"] == scheme_id]
        if target.empty:
            return None

        score = float(target["composite_score"].iloc[0])
        return score, _label(score)

    async def _persist_scores(self, df: pd.DataFrame, score_date: date) -> int:
        written = 0
        async with AsyncSessionLocal() as session:
            for _, row in df.iterrows():
                scheme_id = int(row["scheme_id"])
                score_val = float(row["composite_score"])
                label = _label(score_val)

                existing = await session.scalar(
                    select(FundScore)
                    .where(FundScore.scheme_id == scheme_id)
                    .where(FundScore.score_date == score_date)
                )
                if existing:
                    existing.composite_score = score_val
                    existing.conviction = label.value
                    existing.score_returns = float(row.get("score_returns", 50))
                    existing.score_consistency = float(row.get("score_consistency", 50))
                    existing.score_cost = float(row.get("score_cost", 50))
                    existing.score_sentiment = float(row.get("score_sentiment", 50))
                    existing.score_stability = float(row.get("score_stability", 50))
                    existing.shap_json = _breakdown_json(row)
                else:
                    obj = FundScore(
                        scheme_id=scheme_id,
                        score_date=score_date,
                        composite_score=score_val,
                        conviction=label.value,
                        model_version="rule_based_v1",
                        score_returns=float(row.get("score_returns", 50)),
                        score_consistency=float(row.get("score_consistency", 50)),
                        score_cost=float(row.get("score_cost", 50)),
                        score_sentiment=float(row.get("score_sentiment", 50)),
                        score_stability=float(row.get("score_stability", 50)),
                        shap_json=_breakdown_json(row),
                    )
                    session.add(obj)
                written += 1

            await session.commit()
        return written
