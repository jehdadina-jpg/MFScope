"""
Risk model
==========
Assigns every scheme a 0–100 realised-risk score and a six-tier label, using
the same vocabulary as SEBI's riskometer ("Low" … "Very High").

This is deliberately **not a reproduction of the official SEBI riskometer**.
SEBI's methodology is structural — it scores a fund from its *holdings*
(market-cap mix, credit rating, duration, liquidity) per a prescribed formula,
independent of how the fund actually traded.  This model scores *realised
behaviour* — the volatility, drawdown and market sensitivity the fund's NAV
actually exhibited — which is a different, complementary question ("how did
this fund behave" vs. "what does it hold").  The two will disagree by
construction: SEBI puts almost every diversified equity fund, including large
cap, at "Very High" because it holds equity, while a large-cap fund's
*realised* volatility is genuinely calmer than a small-cap fund's.  Both
numbers are useful; this module only ever claims to compute the second one.
Label it "Realised risk" in the UI, not "Riskometer", so the two are never
mistaken for the same figure.

Why this is not machine learning
--------------------------------
The previous implementation trained an XGBoost regressor on labels it had
computed itself, from the same features it then fed back in as inputs.  A
model fitted to reproduce ``0.35·vol + 0.35·drawdown + 0.20·beta + 0.10·spread``
learns exactly that formula, plus approximation error — so the ML added a
model file, a SHAP dependency and a per-fund inference call, and subtracted
accuracy.  (It also called ``df.fillna(df.median())`` on a single-row frame,
where the median of a NaN is NaN, so missing inputs were never actually
filled.)  It never ran in production either: every ``risk_level`` in the
database was NULL.

Two further things were wrong in principle:

* **Risk was ranked within a category.**  That makes the riskiest liquid fund
  "High risk" and the safest small-cap fund "Low risk", which inverts what the
  words mean.  Risk is an absolute property of a return distribution.
* **Three tiers.**  Indian funds are labelled on SEBI's six-tier riskometer,
  and investors read those exact words on the factsheet.

So the model here is a transparent, absolute, monotone mapping from realised
volatility, drawdown and market sensitivity onto the riskometer, with the
anchor points calibrated to what each Indian fund category actually realises.
Every output can be traced to an input by hand — which for a risk label is a
feature, not a limitation.
"""

from __future__ import annotations

import asyncio
import json
from datetime import date
from typing import Literal

import numpy as np
import pandas as pd
from loguru import logger
from sqlalchemy import text

from backend.db.session import engine

MODEL_VERSION = "riskometer_v2"

RiskLevel = Literal[
    "Low", "Low to Moderate", "Moderate", "Moderately High", "High", "Very High"
]

#: SEBI's six-tier riskometer, in order.
RISK_LEVELS: tuple[str, ...] = (
    "Low", "Low to Moderate", "Moderate", "Moderately High", "High", "Very High",
)

_LEVEL_CUTOFFS: tuple[tuple[float, str], ...] = (
    (16.0, "Low"),
    (32.0, "Low to Moderate"),
    (48.0, "Moderate"),
    (64.0, "Moderately High"),
    (80.0, "High"),
)

RISK_FEATURES: tuple[str, ...] = (
    "volatility_1y",
    "volatility_3y",
    "max_drawdown_1y",
    "max_drawdown_3y",
    "downside_deviation_1y",
    "beta_1y",
    "var_95_1y",
    "rolling_1y_worst",
)

# ── Calibration anchors ───────────────────────────────────────────────────────
# (realised value, risk points).  Piecewise-linear between anchors, flat
# outside them.  The volatility anchors are the observed annualised σ of each
# Indian fund category, which is what makes the output map onto the tiers the
# way a factsheet does.

#: A verified pass with real category-average volatility showed large- and
#: mid-cap funds landing within a fraction of a point of the "High"/"Very
#: High" cutoffs — meaning next quarter's ordinary volatility wobble could
#: flip a whole category's label between refreshes. The knots through the
#: 11–24% range carry more headroom below their nearest cutoff than the
#: version this replaced, without changing where the calm (debt) and extreme
#: (thematic) ends of the table sit.
_VOLATILITY_ANCHORS = np.array(
    [
        [0.0, 0.0],
        [0.35, 8.0],     # overnight
        [1.0, 16.0],     # liquid / ultra short
        [2.5, 26.0],     # low duration, arbitrage
        [5.0, 34.0],     # corporate bond, dynamic bond
        [8.0, 42.0],     # gilt, conservative hybrid
        [11.0, 50.0],    # balanced advantage, multi-asset
        [14.0, 58.0],    # large cap, index
        [17.0, 68.0],    # flexi / multi cap
        [20.0, 78.0],    # mid cap
        [24.0, 88.0],    # small cap
        [32.0, 96.0],    # single-sector, thematic
        [50.0, 100.0],
    ]
)

_DRAWDOWN_ANCHORS = np.array(
    [
        [0.0, 0.0],
        [1.0, 10.0],
        [3.0, 22.0],
        [6.0, 34.0],
        [10.0, 46.0],
        [15.0, 58.0],
        [22.0, 70.0],
        [32.0, 84.0],
        [45.0, 95.0],
        [60.0, 100.0],
    ]
)

_BETA_ANCHORS = np.array(
    [
        [0.0, 0.0],
        [0.15, 15.0],
        [0.40, 32.0],
        [0.70, 48.0],
        [1.00, 60.0],
        [1.20, 72.0],
        [1.50, 86.0],
        [2.00, 100.0],
    ]
)

#: Component weights. Volatility dominates because it is the most reliably
#: measured; drawdown captures the tail that volatility understates.
_WEIGHTS = {"volatility": 0.50, "drawdown": 0.32, "beta": 0.18}


def _interpolate(values: pd.Series, anchors: np.ndarray) -> pd.Series:
    """Piecewise-linear map through the anchor table, clamped at both ends."""
    numeric = pd.to_numeric(values, errors="coerce")
    mapped = np.interp(numeric.to_numpy(dtype="float64"), anchors[:, 0], anchors[:, 1])
    result = pd.Series(mapped, index=values.index, dtype="float64")
    return result.where(numeric.notna())


def risk_level_for(score: float | None) -> str | None:
    if score is None or not np.isfinite(score):
        return None
    for cutoff, level in _LEVEL_CUTOFFS:
        if score < cutoff:
            return level
    return "Very High"


def compute_risk(frame: pd.DataFrame) -> pd.DataFrame:
    """
    Risk score and component contributions for a frame of feature rows.

    Prefers the 3-year window where available: a fund that has only seen a
    calm year looks safer than it is, and the longer window is the one that
    contains a real drawdown.
    """
    volatility = pd.to_numeric(frame.get("volatility_3y"), errors="coerce").fillna(
        pd.to_numeric(frame.get("volatility_1y"), errors="coerce")
    )
    drawdown = pd.to_numeric(frame.get("max_drawdown_3y"), errors="coerce").fillna(
        pd.to_numeric(frame.get("max_drawdown_1y"), errors="coerce")
    ).abs()

    # Beta is missing precisely for the funds whose beta is near zero — debt,
    # liquid and gold funds have no meaningful equity-benchmark relationship,
    # so alpha/beta regression is never attempted for them (see
    # metrics.compute_all). That absence is informative, unlike a genuinely
    # unknown input: dropping the beta component for these funds (the
    # previous behaviour) under-weights the two components that *are*
    # available and biases exactly the safest funds toward a higher score.
    # Impute beta ≈ 0 whenever the fund has real risk history to score at all.
    has_risk_history = volatility.notna() | drawdown.notna()
    beta_raw = pd.to_numeric(frame.get("beta_1y"), errors="coerce")
    beta = beta_raw.where(beta_raw.notna(), 0.0).where(has_risk_history).abs()

    parts = pd.DataFrame(index=frame.index)
    parts["risk_volatility"] = _interpolate(volatility, _VOLATILITY_ANCHORS)
    parts["risk_drawdown"] = _interpolate(drawdown, _DRAWDOWN_ANCHORS)
    parts["risk_beta"] = _interpolate(beta, _BETA_ANCHORS)

    numerator = pd.Series(0.0, index=frame.index, dtype="float64")
    denominator = pd.Series(0.0, index=frame.index, dtype="float64")
    for key, weight in _WEIGHTS.items():
        component = parts[f"risk_{key}"]
        present = component.notna()
        numerator = numerator.add(component.fillna(0.0) * weight * present, fill_value=0.0)
        denominator = denominator.add(weight * present, fill_value=0.0)

    parts["risk_score"] = numerator.divide(denominator.where(denominator > 0)).clip(0, 100)
    parts["risk_confidence"] = denominator / sum(_WEIGHTS.values())
    parts["risk_level"] = parts["risk_score"].map(risk_level_for)
    return parts


def _first_valid(*values):
    """
    NaN-safe coalesce.

    Plain ``a or b`` is wrong here: a pandas/numpy NaN is truthy in Python, so
    ``nan or b`` evaluates to ``nan`` and never falls through to ``b`` — the
    3-year figure silently "won" over a perfectly good 1-year fallback and the
    audit trail rendered blank for exactly the funds using that fallback.
    """
    for value in values:
        if value is not None and pd.notna(value):
            return value
    return None


def explain(row: pd.Series) -> str:
    """Per-component contribution, in the units a person can check."""
    return json.dumps(
        {
            "model_version": MODEL_VERSION,
            "components": {
                "volatility": _round(row.get("risk_volatility")),
                "drawdown": _round(row.get("risk_drawdown")),
                "beta": _round(row.get("risk_beta")),
            },
            "weights": _WEIGHTS,
            "inputs": {
                "volatility_pct": _round(_first_valid(row.get("volatility_3y"), row.get("volatility_1y"))),
                "max_drawdown_pct": _round(
                    _first_valid(row.get("max_drawdown_3y"), row.get("max_drawdown_1y"))
                ),
                "beta": _round(row.get("beta_1y")),
            },
            "confidence": _round(row.get("risk_confidence"), 3),
        }
    )


def _round(value, digits: int = 2):
    if value is None or (isinstance(value, float) and not np.isfinite(value)) or pd.isna(value):
        return None
    return round(float(value), digits)


class RiskModel:
    """Scores realised risk for the investable universe."""

    async def load_frame(self, as_of: date) -> pd.DataFrame:
        columns = ", ".join(f"f.{c}" for c in RISK_FEATURES)
        sql = text(
            f"""
            SELECT f.scheme_id, {columns}
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
            return pd.DataFrame(columns=["scheme_id", *RISK_FEATURES])
        return pd.DataFrame(rows, columns=names)

    def predict_single(self, features: dict) -> tuple[float, str, dict]:
        """Risk for one feature dict — used by tests and ad-hoc inspection."""
        frame = pd.DataFrame([{c: features.get(c) for c in RISK_FEATURES}])
        parts = compute_risk(frame)
        merged = pd.concat([frame, parts], axis=1).iloc[0]
        score = float(merged["risk_score"]) if pd.notna(merged["risk_score"]) else 50.0
        return score, risk_level_for(score) or "Moderate", json.loads(explain(merged))

    async def score_all_risks(self, as_of: date | None = None) -> int:
        as_of = as_of or date.today()
        frame = await self.load_frame(as_of)
        if frame.empty:
            logger.warning(f"No investable features for {as_of} — nothing to risk-score.")
            return 0

        parts = compute_risk(frame)
        merged = pd.concat([frame, parts], axis=1)
        merged = merged[merged["risk_score"].notna()]
        if merged.empty:
            logger.warning("Risk scoring produced no usable rows.")
            return 0

        payload = [
            {
                "scheme_id": int(row["scheme_id"]),
                "score_date": as_of.isoformat(),
                "risk_score": round(float(row["risk_score"]), 2),
                "risk_level": row["risk_level"],
                "risk_shap_json": explain(row),
            }
            for _, row in merged.iterrows()
        ]

        sql = text(
            """
            UPDATE fund_score
               SET risk_score = :risk_score,
                   risk_level = :risk_level,
                   risk_shap_json = :risk_shap_json
             WHERE scheme_id = :scheme_id AND score_date = :score_date
            """
        )
        async with engine.begin() as conn:
            for start in range(0, len(payload), 2000):
                await conn.execute(sql, payload[start : start + 2000])

        distribution = merged["risk_level"].value_counts().to_dict()
        logger.info(f"Risk scoring complete: {len(payload)} rows · {distribution}")
        return len(payload)

    # ── Compatibility shims ──────────────────────────────────────────────────

    def load(self) -> None:
        """No model artefact to load — the mapping is the model."""

    async def train(self, *_, **__) -> dict[str, float]:
        raise NotImplementedError(
            "riskometer_v2 is a calibrated deterministic mapping; there is nothing to fit. "
            "Adjust the anchor tables in this module to recalibrate."
        )


async def rescore_risk(as_of: date | None = None) -> int:
    return await RiskModel().score_all_risks(as_of=as_of)


if __name__ == "__main__":
    asyncio.run(rescore_risk())
