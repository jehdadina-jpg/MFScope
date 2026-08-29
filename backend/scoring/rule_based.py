"""
Composite scorer (v3)
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

**The published score is a normal-scores transform of that blend**, not the
blend itself and not a raw rank of it.  Averaging several roughly independent
percentiles pulls results toward the middle — the central limit theorem does
not care about our thresholds — so the raw blend clusters between 35 and 65
and almost nothing clears a "Strong Buy" cut-off.

An earlier version fixed that by publishing ``blend.rank(pct=True)`` directly,
which restores spread but goes too far the other way: a plain percentile rank
is uniform on (0, 100] *within every peer group by construction*, so the
leader of a 4-fund group and the leader of a 300-fund group both land on
exactly 100.0, and the thresholds below then carve an identical quota of
"Strong Buy" out of every group regardless of how good that group's funds are
relative to each other — a global leaderboard becomes a tie among category
leaders, ordered by nothing meaningful.

The fix is :func:`_spread_score`: convert each fund's rank to a plotting
position, pass it through the inverse-normal CDF, and rescale.  This still
de-clusters the blend, but a large, decisive peer group now produces a wider
spread of scores than a small one — the leader of 4 peers lands in the
high-60s, the leader of 300 can reach the high 90s — because that is a fair
reading of the evidence: "best of 4" and "best of 300" are not equally strong
claims.  :attr:`blended_score` keeps the raw, pre-transform blend for anyone
who wants the un-spread number.

v3: Empirical Bayes shrinkage of the noisy inputs
--------------------------------------------------
Percentile ranking treats every fund's Sharpe, Sortino, alpha and 1-year
return as equally trustworthy point estimates. They are not: a ratio
estimated from 90 days of history has a much wider sampling-error band than
one estimated from 3 years, and a fund can print a great Sharpe purely by
being lucky over a short window. Before those four signals are ranked, each
is passed through :func:`backend.analytics.shrinkage.shrink_to_group_mean` —
an Empirical Bayes / random-effects estimator (Efron & Morris 1975;
DerSimonian & Laird 1986) that pulls a fund's value toward its peer group's
consensus by an amount proportional to how uncertain that fund's own estimate
is, using the Lo (2002) asymptotic standard error of an estimated Sharpe
ratio (and matched formulas for the other three). A fund with a precise,
long-history estimate keeps almost all of its raw value; a fund with a wide
error band is pulled hard toward the group.

This is deliberately *not* a machine-learning model. There is no ground-truth
"true skill" label to fit a model against — see the identical argument in
``backend/scoring/risk_model.py``'s docstring for why that was removed from
the risk model, too. What actually reduces error here is classical inference
about how much of each raw number is signal versus estimation noise, which is
exactly what shrinkage estimates and corrects for. See
``backend/analytics/shrinkage.py`` for the full derivation and a synthetic
recovery test.
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
from scipy.stats import norm
from sqlalchemy import select, text

from backend.analytics import shrinkage
from backend.db.models import ConvictionLabel, FundFeatures, Scheme
from backend.db.session import AsyncSessionLocal, engine

MODEL_VERSION = "rule_based_v3"

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
    #: Apply Empirical Bayes shrinkage (see backend/analytics/shrinkage.py)
    #: before ranking. Reserved for estimated performance ratios that get
    #: noisier with less history — not for exactly-known inputs like expense
    #: ratio, or levels like AUM that shrinkage's iid-sampling-error model
    #: doesn't describe.
    shrink: bool = False


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
            # sharpe/sortino/alpha/return_1y are shrunk toward the peer-group
            # consensus by how uncertain each fund's own estimate is (short
            # history or high volatility → wider standard error → more
            # shrinkage) before being ranked — see shrinkage.py. return_3y and
            # return_5y are left unshrunk: at multi-year horizons the daily-
            # iid assumption behind the standard error formula is weaker, and
            # a fund with real 3-5y history has already earned a stable
            # estimate that doesn't need it.
            Signal("sharpe_1y", 0.26, shrink=True),
            Signal("sortino_1y", 0.20, shrink=True),
            Signal("alpha_1y", 0.16, shrink=True),
            Signal("return_1y", 0.14, shrink=True),
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

#: Every column the scorer reads as a ranked signal.
FEATURE_COLUMNS: tuple[str, ...] = tuple(
    dict.fromkeys(signal.column for component in COMPONENTS for signal in component.signals)
)

#: Extra columns needed only to compute standard errors for shrinkage
#: (nav_days / volatility_1y for sample size and dispersion, r_squared_1y for
#: alpha's residual variance) — not scoring signals themselves.
_SHRINKAGE_AUX_COLUMNS: tuple[str, ...] = ("nav_days", "volatility_1y", "r_squared_1y")

#: All columns the scorer's SQL needs to select.
QUERY_COLUMNS: tuple[str, ...] = tuple(
    dict.fromkeys((*FEATURE_COLUMNS, *_SHRINKAGE_AUX_COLUMNS))
)


# ── Label mapping ─────────────────────────────────────────────────────────────
# The published score is centred at 50 with an approximately-normal spread
# (see _spread_score), so these thresholds are inverse-normal-CDF points
# rather than literal percentiles — they hold exactly for a large, decisive
# peer group and compress automatically for a small one.

_THRESHOLDS: tuple[tuple[float, ConvictionLabel], ...] = (
    (70.0, ConvictionLabel.STRONG_BUY),   # z ≳ +1.28 → top ~10% of a large group
    (58.0, ConvictionLabel.BUY),          # z ≳ +0.55 → next ~19%
    (45.0, ConvictionLabel.HOLD),         # z ≳ −0.33 → middle ~32%
    (35.0, ConvictionLabel.SELL),         # z ≳ −1.00 → next ~23%
)                                          # bottom ~16% → Strong Sell

#: A conviction stronger than Hold requires this much of the model to have run.
#: Recommending a fund on a third of the evidence is not a recommendation.
MIN_CONFIDENCE_FOR_CONVICTION = 0.45

#: …and enough peers for the ranking to mean anything.  Being first of four is
#: not evidence, and without this floor the leader of every stray bucket lands
#: on an inflated score.
MIN_PEERS_FOR_CONVICTION = 8

_SOFT = {ConvictionLabel.STRONG_BUY, ConvictionLabel.BUY}
_HARSH = {ConvictionLabel.STRONG_SELL, ConvictionLabel.SELL}


def _label(
    score: float, confidence: float = 1.0, peer_count: int = 10**6
) -> ConvictionLabel:
    """
    Map a spread score to a conviction, then withhold *any* strong verdict —
    buy or sell — when the evidence behind it is thin.

    An earlier version only gated the buy side, on the theory that a false
    "sell" is safer than a false "buy". But a Strong Sell is still a
    recommendation someone will act on, and a fund ranked last of four peers
    on 20% data coverage has not earned that verdict any more than one ranked
    first has earned a Strong Buy.
    """
    supported = (
        confidence >= MIN_CONFIDENCE_FOR_CONVICTION
        and peer_count >= MIN_PEERS_FOR_CONVICTION
    )
    for threshold, label in _THRESHOLDS:
        if score >= threshold:
            is_strong = label in _SOFT or label in _HARSH
            return ConvictionLabel.HOLD if (is_strong and not supported) else label
    return ConvictionLabel.HOLD if not supported else ConvictionLabel.STRONG_SELL


# ── Percentile / spread helpers ────────────────────────────────────────────────

def percentile_rank(series: pd.Series, higher_is_better: bool = True) -> pd.Series:
    """
    Percentile in (0, 100] over the non-null values only.

    Nulls stay null: a missing input must not be imputed to a rank it did not
    earn.  The component aggregator renormalises around whatever is present.

    Uses pandas' own ``ascending`` flag for the inverted direction rather than
    ``100 - rank``: ``rank(pct=True)`` spans ``1/n`` to ``1`` (a "beaten-or-tied"
    fraction, not a symmetric percentile), so subtracting it from 100 does not
    mirror the scale — the best value of an ascending signal reaches 100.0 but
    the best value of a descending signal only reached ``100 - 100/n``, capping
    every "lower is better" input (expense ratio, drawdown, volatility) below
    its ascending counterparts by up to that amount.
    """
    return series.rank(pct=True, ascending=higher_is_better, na_option="keep") * 100.0


def _spread_score(blend: pd.Series) -> pd.Series:
    """
    Map a peer-relative blend onto a 0–100 scale centred at 50, using a
    rank-based normal-scores transform instead of a raw percentile rank.

    A raw ``rank(pct=True)`` is uniform on (0, 100] *within every peer group by
    construction*: the leader of a 4-fund group and the leader of a 300-fund
    group both land on exactly 100, and a fixed threshold then carves an
    identical quota out of every group no matter how strong or weak it is
    internally.  This transform keeps the same ordering but lets a large,
    decisive group spread out more than a small one — see the module
    docstring for the reasoning.

    Blom's plotting position (``(rank - 0.375) / (n + 0.25)``) is the standard
    unbiased choice for this transform and keeps every rank strictly inside
    (0, 1), so the inverse-normal CDF never returns ±inf even for the single
    best or worst fund in a group.
    """
    n = int(blend.notna().sum())
    if n == 0:
        return pd.Series(np.nan, index=blend.index, dtype="float64")
    plotting_position = (blend.rank(method="average", na_option="keep") - 0.375) / (n + 0.25)
    z = pd.Series(
        norm.ppf(plotting_position.to_numpy(dtype="float64")),
        index=blend.index,
        dtype="float64",
    )
    return (50.0 + z * 15.0).clip(0, 100).where(blend.notna())


#: How to compute each shrinkable signal's standard error, given the peer
#: group's frame. Keyed by column name so `_signal_series` can dispatch.
_STANDARD_ERROR_FNS: dict[str, "callable"] = {
    "sharpe_1y": lambda f: shrinkage.sharpe_like_standard_error(f["sharpe_1y"], f["nav_days"]),
    "sortino_1y": lambda f: shrinkage.sharpe_like_standard_error(f["sortino_1y"], f["nav_days"]),
    "return_1y": lambda f: shrinkage.mean_return_standard_error(f["volatility_1y"], f["nav_days"]),
    "alpha_1y": lambda f: shrinkage.alpha_standard_error(
        f["volatility_1y"], f["r_squared_1y"], f["nav_days"]
    ),
}


def _signal_series(frame: pd.DataFrame, signal: Signal) -> pd.Series:
    if signal.column not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    values = pd.to_numeric(frame[signal.column], errors="coerce")

    if signal.shrink and signal.column in _STANDARD_ERROR_FNS:
        try:
            se = _STANDARD_ERROR_FNS[signal.column](frame)
            values = shrinkage.shrink_to_group_mean(values, se)
        except KeyError:
            pass  # auxiliary column missing from this frame — rank raw values

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
        signal_weight_total = sum(s.weight for s in component.signals)

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
        # Row-level share of *this component's own* signal weight that had
        # real data — used below to scale data_confidence by how much of the
        # component actually ran, not just whether it produced a number at
        # all (a component with one of five signals present still produces a
        # number, and previously counted as 100% present).
        out[f"_coverage_{component.name}"] = (
            weight_present / signal_weight_total if signal_weight_total > 0 else weight_present
        ).where(score.notna(), 0.0)
        coverage[component.name] = float(score.notna().mean())

    # ── Composite: renormalise across components that actually ran ───────────
    numerator = pd.Series(0.0, index=frame.index, dtype="float64")
    denominator = pd.Series(0.0, index=frame.index, dtype="float64")
    confidence_weighted = pd.Series(0.0, index=frame.index, dtype="float64")
    for component in COMPONENTS:
        score = out[f"score_{component.name}"]
        present = score.notna()
        numerator = numerator.add(score.fillna(0.0) * component.weight * present, fill_value=0.0)
        denominator = denominator.add(component.weight * present, fill_value=0.0)
        confidence_weighted = confidence_weighted.add(
            component.weight * out[f"_coverage_{component.name}"], fill_value=0.0
        )

    total_weight = sum(c.weight for c in COMPONENTS)
    blend = numerator.divide(denominator.where(denominator > 0)).clip(0, 100)

    out["blended_score"] = blend
    out["composite_score"] = _spread_score(blend)
    out["data_confidence"] = (confidence_weighted / total_weight).clip(0, 1)
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
    blended = row.get("blended_score")
    confidence = row.get("data_confidence")
    peer_count = row.get("peer_count")
    return json.dumps(
        {
            "components": {name: round(value, 1) for name, value in present.items()},
            "weights": {
                name: round(COMPONENT_WEIGHTS[name] / live_weight, 4) for name in present
            },
            "nominal_weights": COMPONENT_WEIGHTS,
            "missing": [c.name for c in COMPONENTS if c.name not in present],
            # `x or default` is wrong here: NaN is truthy in Python, so
            # `nan or 0.0` evaluates to `nan`, not `0.0` — and json.dumps of a
            # bare NaN emits the literal token `NaN`, which is invalid JSON.
            "blended_score": round(float(blended), 1) if pd.notna(blended) else 0.0,
            "data_confidence": round(float(confidence), 3) if pd.notna(confidence) else 0.0,
            "peer_group": row.get("peer_group"),
            "peer_count": int(peer_count) if pd.notna(peer_count) else 0,
            "model_version": MODEL_VERSION,
        }
    )


# ── Scorer ────────────────────────────────────────────────────────────────────

class RuleBasedScorer:
    """Ranks the investable universe and writes ``fund_score`` rows."""

    async def load_frame(self, as_of: date) -> pd.DataFrame:
        columns = ", ".join(f"f.{c}" for c in QUERY_COLUMNS)
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
            return pd.DataFrame(columns=["scheme_id", "category", "asset_class", *QUERY_COLUMNS])
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
