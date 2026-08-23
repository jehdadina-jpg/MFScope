"""
Composite scorer (v2)
=====================
Turns a feature row into a 0–100 conviction score, ranked **within a peer
group**, plus an explicit statement of how much of the model actually had data
to run on.

What changed from v1, and why
-----------------------------
v1 produced a distribution where 88% of 12,944 funds were "Hold" and no fund
scored above 69.  Three compounding defects caused that:

1. **Double-penalised missing data.**  Absent inputs were imputed at the 25th
   percentile *and* the finished score was multiplied by a data-completeness
   ratio.  With expense ratio, AUM, tenure and sentiment all unpopulated, the
   ceiling was ~45/100 for every fund in the database.  v2 instead **drops**
   components with no inputs and renormalises the surviving weights, then
   reports the surviving weight as :attr:`data_confidence`.  A fund is ranked
   on what is known about it, and the gap is disclosed rather than smeared
   into the number.

2. **Drawdown ranked backwards.**  ``_pct_rank_inv(max_drawdown_1y)`` gave the
   *deepest* drawdown the highest consistency score, because drawdown is
   already negative — less negative is better, so plain percentile rank is the
   correct direction and the inversion flipped it.  v2 ranks the magnitude.

3. **Peer groups of one.**  Percentile rank inside a category holding three
   funds is noise.  v2 falls back to the asset class when a category has fewer
   than :data:`MIN_PEER_GROUP` scored members.

Method
------
Every input is converted to a percentile inside the peer group, components are
weighted averages of those percentiles, and the blend is a weighted average of
the components.  Percentiles keep the model robust to the fat tails and unit
differences that raw ratios have.

**The published score is the peer-group percentile of that blend**, not the
blend itself.  Averaging several roughly independent percentiles pulls results
toward the middle — the central limit theorem does not care about our
thresholds — so the raw blend clusters between 35 and 65 and almost nothing
clears a "Strong Buy" cut-off.  Ranking the blend restores a controlled,
interpretable distribution and makes the number mean exactly one thing:

    composite_score = "this fund beats N% of its peer group"

which is also the only claim the inputs actually support, since every one of
them is already relative.  The UI can then always show the score next to
"rank 3 of 71 Large Cap funds" and the two agree by construction.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import date
from typing import Iterable, Sequence

import numpy as np
import pandas as pd
from loguru import logger
from sqlalchemy import select, text

from backend.db.models import ConvictionLabel, FundFeatures, Scheme
from backend.db.session import AsyncSessionLocal, engine

MODEL_VERSION = "rule_based_v2"

#: Below this many peers a within-category percentile is noise, so the fund is
#: ranked against its whole asset class instead.
MIN_PEER_GROUP = 12

#: A component contributes only if at least this share of the peer group has
#: the underlying data.  Otherwise ranking is between a handful of funds and
#: a wall of nulls.
MIN_COVERAGE = 0.30


# ── Component definitions ─────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class Signal:
    """One input to a component: which column, which direction, what weight."""
    column: str
    weight: float
    higher_is_better: bool = True
    use_magnitude: bool = False   # rank |x| — for drawdown, which is negative


@dataclass(frozen=True, slots=True)
class Component:
    name: str
    weight: float
    signals: tuple[Signal, ...]


COMPONENTS: tuple[Component, ...] = (
    Component(
        "returns", 0.34,
        (
            # Risk-adjusted first: a 30% return taken with 30% volatility is
            # not the same product as a 25% return taken with 14%.
            Signal("sharpe_1y", 0.26),
            Signal("sortino_1y", 0.20),
            Signal("alpha_1y", 0.16),
            Signal("return_1y", 0.14),
            Signal("return_3y", 0.14),
            Signal("return_5y", 0.10),
        ),
    ),
    Component(
        "consistency", 0.24,
        (
            # Drawdown is negative; rank its magnitude, smaller is better.
            Signal("max_drawdown_1y", 0.26, higher_is_better=False, use_magnitude=True),
            Signal("downside_deviation_1y", 0.20, higher_is_better=False),
            Signal("rolling_1y_std", 0.20, higher_is_better=False),
            Signal("rolling_1y_positive_pct", 0.18),
            Signal("rolling_1y_worst", 0.16),
        ),
    ),
    Component(
        "momentum", 0.12,
        (
            Signal("momentum_roc_3m", 0.40),
            Signal("momentum_roc_6m", 0.35),
            Signal("ma_crossover", 0.25),
        ),
    ),
    Component(
        "cost", 0.12,
        (Signal("expense_ratio", 1.0, higher_is_better=False),),
    ),
    Component(
        "sentiment", 0.08,
        (
            Signal("sentiment_7d", 0.55),
            Signal("sentiment_30d", 0.45),
        ),
    ),
    Component(
        "stability", 0.10,
        (
            Signal("aum_crore", 0.35),
            Signal("aum_growth_3m", 0.25),
            Signal("manager_tenure_years", 0.20),
            Signal("history_years", 0.20),
        ),
    ),
)

COMPONENT_WEIGHTS: dict[str, float] = {c.name: c.weight for c in COMPONENTS}

#: Every column the scorer reads.
FEATURE_COLUMNS: tuple[str, ...] = tuple(
    dict.fromkeys(signal.column for component in COMPONENTS for signal in component.signals)
)


# ── Label mapping ─────────────────────────────────────────────────────────────
# The published score is a peer percentile, so these thresholds map directly to
# shares of each peer group and the distribution is stable by construction.

_THRESHOLDS: tuple[tuple[float, ConvictionLabel], ...] = (
    (90.0, ConvictionLabel.STRONG_BUY),   # top 10% of the peer group
    (72.0, ConvictionLabel.BUY),          # next 18%
    (38.0, ConvictionLabel.HOLD),         # middle 34%
    (15.0, ConvictionLabel.SELL),         # next 23%
)                                          # bottom 15% → Strong Sell

#: A conviction stronger than Hold requires this much of the model to have run.
#: Recommending a fund on a third of the evidence is not a recommendation.
MIN_CONFIDENCE_FOR_CONVICTION = 0.45

#: …and enough peers for the ranking to mean anything.  Being first of four is
#: not evidence, and without this floor the leader of every stray bucket lands
#: on a perfect 100.
MIN_PEERS_FOR_CONVICTION = 8

_SOFT = {ConvictionLabel.STRONG_BUY, ConvictionLabel.BUY}
_HARSH = {ConvictionLabel.STRONG_SELL, ConvictionLabel.SELL}


def _label(
    score: float, confidence: float = 1.0, peer_count: int = 10**6
) -> ConvictionLabel:
    """
    Map a peer percentile to a conviction, then withhold the strong verdicts
    when the evidence behind them is thin.
    """
    supported = (
        confidence >= MIN_CONFIDENCE_FOR_CONVICTION
        and peer_count >= MIN_PEERS_FOR_CONVICTION
    )
    for threshold, label in _THRESHOLDS:
        if score >= threshold:
            return ConvictionLabel.HOLD if (label in _SOFT and not supported) else label
    return ConvictionLabel.HOLD if not supported else ConvictionLabel.STRONG_SELL


# ── Percentile helpers ────────────────────────────────────────────────────────

def percentile_rank(series: pd.Series, higher_is_better: bool = True) -> pd.Series:
    """
    Percentile in [0, 100] over the non-null values only.

    Nulls stay null: a missing input must not be imputed to a rank it did not
    earn.  The component aggregator renormalises around whatever is present.
    """
    ranked = series.rank(pct=True, na_option="keep") * 100.0
    return ranked if higher_is_better else 100.0 - ranked


def _signal_series(frame: pd.DataFrame, signal: Signal) -> pd.Series:
    if signal.column not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    values = pd.to_numeric(frame[signal.column], errors="coerce")
    if signal.use_magnitude:
        values = values.abs()
    return percentile_rank(values, signal.higher_is_better)


def compute_components(frame: pd.DataFrame) -> pd.DataFrame:
    """
    Score every component for one peer group.

    Within a component, signals with no data are dropped and the remaining
    signal weights renormalised.  A component with no data at all becomes NaN
    and is dropped at the composite step.
    """
    out = pd.DataFrame(index=frame.index)
    coverage: dict[str, float] = {}

    for component in COMPONENTS:
        weighted = pd.Series(0.0, index=frame.index, dtype="float64")
        weight_present = pd.Series(0.0, index=frame.index, dtype="float64")

        for signal in component.signals:
            ranks = _signal_series(frame, signal)
            available = ranks.notna()
            # A signal only counts if a real share of the peer group has it.
            if available.mean() < MIN_COVERAGE:
                continue
            weighted = weighted.add(ranks.fillna(0.0) * signal.weight * available, fill_value=0.0)
            weight_present = weight_present.add(signal.weight * available, fill_value=0.0)

        score = weighted.divide(weight_present.where(weight_present > 0))
        out[f"score_{component.name}"] = score
        coverage[component.name] = float(score.notna().mean())

    # ── Composite: renormalise across components that actually ran ───────────
    numerator = pd.Series(0.0, index=frame.index, dtype="float64")
    denominator = pd.Series(0.0, index=frame.index, dtype="float64")
    for component in COMPONENTS:
        score = out[f"score_{component.name}"]
        present = score.notna()
        numerator = numerator.add(score.fillna(0.0) * component.weight * present, fill_value=0.0)
        denominator = denominator.add(component.weight * present, fill_value=0.0)

    total_weight = sum(c.weight for c in COMPONENTS)
    blend = numerator.divide(denominator.where(denominator > 0)).clip(0, 100)

    out["blended_score"] = blend
    # Rank the blend inside the peer group: see the module docstring for why the
    # published score is the percentile and not the blend.
    out["composite_score"] = blend.rank(pct=True, na_option="keep") * 100.0
    out["data_confidence"] = (denominator / total_weight).clip(0, 1)
    out["_coverage"] = pd.Series([coverage] * len(frame), index=frame.index)
    return out


# ── Explainability ────────────────────────────────────────────────────────────

def breakdown_json(row: pd.Series) -> str:
    """
    Component breakdown for the UI, including the weight each component was
    actually given after renormalisation — so the explanation adds up to the
    score the user is looking at.
    """
    present = {
        component.name: float(row[f"score_{component.name}"])
        for component in COMPONENTS
        if pd.notna(row.get(f"score_{component.name}"))
    }
    live_weight = sum(COMPONENT_WEIGHTS[name] for name in present) or 1.0
    return json.dumps(
        {
            "components": {name: round(value, 1) for name, value in present.items()},
            "weights": {
                name: round(COMPONENT_WEIGHTS[name] / live_weight, 4) for name in present
            },
            "nominal_weights": COMPONENT_WEIGHTS,
            "missing": [c.name for c in COMPONENTS if c.name not in present],
            "blended_score": round(float(row.get("blended_score") or 0.0), 1),
            "data_confidence": round(float(row.get("data_confidence") or 0.0), 3),
            "peer_group": row.get("peer_group"),
            "peer_count": int(row.get("peer_count") or 0),
            "model_version": MODEL_VERSION,
        }
    )


# ── Scorer ────────────────────────────────────────────────────────────────────

class RuleBasedScorer:
    """Ranks the investable universe and writes ``fund_score`` rows."""

    async def load_frame(self, as_of: date) -> pd.DataFrame:
        columns = ", ".join(f"f.{c}" for c in FEATURE_COLUMNS)
        sql = text(
            f"""
            SELECT f.scheme_id, s.category, s.asset_class, {columns}
              FROM fund_features f
              JOIN scheme s ON s.id = f.scheme_id
             WHERE f.feature_date = :as_of
               AND s.is_investable = 1
            """
        )
        async with engine.connect() as conn:
            result = await conn.execute(sql, {"as_of": as_of.isoformat()})
            rows = result.all()
            names = list(result.keys())

        if not rows:
            return pd.DataFrame(columns=["scheme_id", "category", "asset_class", *FEATURE_COLUMNS])
        return pd.DataFrame(rows, columns=names)

    def assign_peer_groups(self, frame: pd.DataFrame) -> pd.DataFrame:
        """
        Category when it is populous enough to give a stable percentile,
        asset class otherwise.
        """
        sizes = frame["category"].value_counts()
        big_enough = set(sizes[sizes >= MIN_PEER_GROUP].index)
        frame = frame.copy()
        frame["peer_group"] = np.where(
            frame["category"].isin(big_enough),
            frame["category"],
            frame["asset_class"].fillna("Other"),
        )
        frame["peer_count"] = frame.groupby("peer_group")["scheme_id"].transform("size")
        return frame

    def score_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        groups: list[pd.DataFrame] = []
        for _, group in frame.groupby("peer_group", sort=False):
            scored = compute_components(group)
            merged = pd.concat([group.reset_index(drop=True), scored.reset_index(drop=True)], axis=1)
            merged["peer_rank"] = (
                merged["composite_score"].rank(ascending=False, method="min").astype("Int64")
            )
            groups.append(merged)

        if not groups:
            return pd.DataFrame()
        return pd.concat(groups, ignore_index=True)

    async def score_all(self, as_of: date | None = None) -> int:
        as_of = as_of or date.today()
        logger.info(f"Scoring universe for {as_of} …")

        frame = await self.load_frame(as_of)
        if frame.empty:
            logger.warning(f"No investable feature rows for {as_of} — run the feature build first.")
            return 0

        frame = self.assign_peer_groups(frame)
        scored = self.score_frame(frame)
        scored = scored[scored["composite_score"].notna()]
        if scored.empty:
            logger.warning("Scoring produced no usable rows.")
            return 0

        written = await self._persist(scored, as_of)
        self._log_distribution(scored)
        return written

    async def score_scheme(
        self, scheme_id: int, as_of: date | None = None
    ) -> tuple[float, ConvictionLabel] | None:
        """Score one scheme by ranking its whole peer group — the rank needs it."""
        as_of = as_of or date.today()
        frame = await self.load_frame(as_of)
        if frame.empty or scheme_id not in set(frame["scheme_id"]):
            return None

        frame = self.assign_peer_groups(frame)
        target_group = frame.loc[frame["scheme_id"] == scheme_id, "peer_group"].iloc[0]
        scored = self.score_frame(frame[frame["peer_group"] == target_group])
        row = scored[scored["scheme_id"] == scheme_id]
        if row.empty or pd.isna(row["composite_score"].iloc[0]):
            return None

        score = float(row["composite_score"].iloc[0])
        confidence = float(row["data_confidence"].iloc[0])
        return score, _label(score, confidence, int(row["peer_count"].iloc[0]))

    # ── Persistence ──────────────────────────────────────────────────────────

    async def _persist(self, scored: pd.DataFrame, as_of: date) -> int:
        payload: list[dict] = []
        for _, row in scored.iterrows():
            score = float(row["composite_score"])
            confidence = float(row["data_confidence"] or 0.0)
            payload.append(
                {
                    "scheme_id": int(row["scheme_id"]),
                    "score_date": as_of.isoformat(),
                    "composite_score": round(score, 2),
                    "conviction": _label(score, confidence, int(row["peer_count"])).value,
                    "model_version": MODEL_VERSION,
                    "score_returns": _opt(row.get("score_returns")),
                    "score_consistency": _opt(row.get("score_consistency")),
                    "score_momentum": _opt(row.get("score_momentum")),
                    "score_cost": _opt(row.get("score_cost")),
                    "score_sentiment": _opt(row.get("score_sentiment")),
                    "score_stability": _opt(row.get("score_stability")),
                    "data_confidence": round(confidence, 4),
                    "peer_group": str(row["peer_group"]),
                    "peer_count": int(row["peer_count"]),
                    "peer_rank": int(row["peer_rank"]) if pd.notna(row["peer_rank"]) else None,
                    "shap_json": breakdown_json(row),
                }
            )

        columns = list(payload[0])
        updatable = [c for c in columns if c not in ("scheme_id", "score_date")]
        sql = text(
            f"INSERT INTO fund_score ({', '.join(columns)}) "
            f"VALUES ({', '.join(f':{c}' for c in columns)}) "
            f"ON CONFLICT(scheme_id, score_date) DO UPDATE SET "
            f"{', '.join(f'{c} = excluded.{c}' for c in updatable)}"
        )
        async with engine.begin() as conn:
            for start in range(0, len(payload), 2000):
                await conn.execute(sql, payload[start : start + 2000])

        logger.info(f"Scoring complete: {len(payload)} scores written for {as_of}.")
        return len(payload)

    @staticmethod
    def _log_distribution(scored: pd.DataFrame) -> None:
        labels = scored.apply(
            lambda r: _label(
                float(r["composite_score"]),
                float(r["data_confidence"] or 0),
                int(r["peer_count"]),
            ).value,
            axis=1,
        )
        counts = labels.value_counts().to_dict()
        confidence = scored["data_confidence"].mean()
        logger.info(
            f"  distribution: {counts} · mean confidence {confidence:.2f} · "
            f"score range {scored['composite_score'].min():.1f}–"
            f"{scored['composite_score'].max():.1f}"
        )


def _opt(value) -> float | None:
    if value is None or pd.isna(value):
        return None
    return round(float(value), 2)


# ── Backwards-compatible aliases used by the existing test-suite ──────────────

def _pct_rank(series: pd.Series) -> pd.Series:
    return percentile_rank(series, higher_is_better=True)


def _pct_rank_inv(series: pd.Series) -> pd.Series:
    return percentile_rank(series, higher_is_better=False)


async def rescore(as_of: date | None = None) -> int:
    return await RuleBasedScorer().score_all(as_of=as_of)


if __name__ == "__main__":
    asyncio.run(rescore())
