"""
Empirical Bayes shrinkage for performance ratios
=================================================
A fund with 90 days of history and a lucky Sharpe of 3.0 is not a better fund
than one with 3 years of history and a steady Sharpe of 1.2 — it is a noisier
estimate that happened to land high.  Ranking raw point estimates treats both
numbers as equally trustworthy, which is exactly backwards: the shorter the
history (or the higher the fund's own volatility), the wider the sampling
error band around its Sharpe, Sortino, alpha or return, and the more of that
number is luck rather than skill.

Why this, and not a model
--------------------------
This is the answer to "use more advanced computation" that is actually
defensible for scoring, as opposed to the XGBoost regressor removed from the
risk model (see ``backend/scoring/risk_model.py``'s docstring) or a similar
model bolted onto this scorer: there is no ground-truth label for "true fund
skill" to fit against, so a learned model here would just be an expensive,
opaque way to approximate a formula — with the added risk of overfitting
noise in exactly the short-history funds this module exists to protect
against.  What genuinely improves the estimate is classical statistics:

1. **Lo (2002)** gives the asymptotic standard error of an estimated Sharpe
   ratio as a function of the point estimate and the sample size — a short
   history or an extreme ratio both widen it.  We use the same functional
   form (with the obvious substitution) for Sortino, and a matched OLS
   standard error for alpha's intercept.
2. **Empirical Bayes / random-effects shrinkage** (Efron & Morris 1975;
   DerSimonian & Laird 1986) treats each fund's estimate the way a
   meta-analysis treats one study's effect size: pull it toward the
   peer-group consensus by an amount proportional to how uncertain it is.
   A fund with a small standard error keeps almost all of its raw value; a
   fund with a large one is pulled hard toward the peer mean.  The amount of
   genuine skill-dispersion in the peer group (``tau²``) is estimated from
   the data itself via the standard DerSimonian-Laird method-of-moments
   estimator — nothing here is a free parameter tuned by hand.

The result: a fund's rank reflects how confident we can actually be that it
outperformed, not just how it happened to print over whatever window of
data exists for it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

#: Below this many peers with a usable standard error, "the peer-group
#: consensus" is itself too noisy to shrink toward — leave values unshrunk
#: rather than pull them toward a handful of other noisy estimates.
MIN_GROUP_FOR_SHRINKAGE = 6

#: Trading days per year, consistent with backend.analytics.metrics.
TRADING_DAYS_PER_YEAR = 252.0


def sharpe_like_standard_error(ratio: pd.Series, n_obs: pd.Series) -> pd.Series:
    """
    Asymptotic standard error of an annualised Sharpe-type ratio (Lo, 2002,
    "The Statistics of Sharpe Ratios", *Financial Analysts Journal*).

    For a daily Sharpe estimate over ``n`` iid daily observations,
    ``Var(SR_daily) ≈ (1 + SR_daily²/2) / n``. Annualising a ratio scales it
    by ``√252``, so the annualised variance scales by 252, giving

        SE(SR_annual) = √(252/n · (1 + SR_annual²/504))

    Applied unchanged to Sortino: both are mean-over-dispersion ratios of an
    approximately normal statistic, and absent a fund-specific derivation of
    the downside-deviation estimator's variance, the Sharpe result is the
    standard stand-in used in the empirical finance literature.
    """
    n = pd.to_numeric(n_obs, errors="coerce").clip(lower=20)
    r = pd.to_numeric(ratio, errors="coerce")
    variance = (TRADING_DAYS_PER_YEAR / n) * (1.0 + (r**2) / (2.0 * TRADING_DAYS_PER_YEAR))
    return np.sqrt(variance)


def mean_return_standard_error(annualised_volatility_pct: pd.Series, n_obs: pd.Series) -> pd.Series:
    """
    Standard error of an annualised return built from a sample mean of daily
    returns: ``SE(x̄) = σ/√n`` scaled to annual terms is just the annualised
    volatility divided by ``√n`` — the textbook CLT result for a sample mean,
    with ``σ`` already annualised so no further rescaling is needed.
    """
    n = pd.to_numeric(n_obs, errors="coerce").clip(lower=20)
    vol = pd.to_numeric(annualised_volatility_pct, errors="coerce")
    return vol / np.sqrt(n)


def alpha_standard_error(
    annualised_volatility_pct: pd.Series, r_squared: pd.Series, n_obs: pd.Series
) -> pd.Series:
    """
    Standard error of an OLS intercept (alpha), approximated from the
    regression's residual variance: ``Var(residual) = Var(fund) × (1 - R²)``.
    Drops the leverage term (``1/n + x̄²/Sxx``) down to its dominant ``1/n``
    part, which is accurate whenever the regressor's mean is small relative
    to its spread — true here since the regressor is a daily excess return
    centred near zero.
    """
    n = pd.to_numeric(n_obs, errors="coerce").clip(lower=20)
    vol = pd.to_numeric(annualised_volatility_pct, errors="coerce")
    r2 = pd.to_numeric(r_squared, errors="coerce").fillna(0.0).clip(lower=0.0, upper=0.999)
    residual_vol = vol * np.sqrt(1.0 - r2)
    return residual_vol / np.sqrt(n)


def shrink_to_group_mean(estimates: pd.Series, standard_errors: pd.Series) -> pd.Series:
    """
    Empirical Bayes (random-effects) shrinkage of ``estimates`` toward their
    precision-weighted group mean.

    Implements the DerSimonian-Laird estimator for the between-fund variance
    ``tau²`` — the genuine dispersion of skill in this peer group, net of
    estimation noise — then shrinks each fund toward the group mean by
    ``tau² / (tau² + se²)``: a precisely-estimated fund keeps its own value,
    an imprecisely-estimated one is pulled toward consensus.

    Funds with no usable standard error, or a group too small to trust a
    consensus at all, pass through unchanged — shrinkage should never be the
    reason a value goes missing.
    """
    values = pd.to_numeric(estimates, errors="coerce")
    se = pd.to_numeric(standard_errors, errors="coerce")
    valid = values.notna() & se.notna() & (se > 1e-9)

    if int(valid.sum()) < MIN_GROUP_FOR_SHRINKAGE:
        return values

    v = values[valid].to_numpy(dtype="float64")
    s = se[valid].to_numpy(dtype="float64")
    weights = 1.0 / (s**2)

    weighted_mean = float(np.sum(weights * v) / np.sum(weights))

    # DerSimonian-Laird method-of-moments estimator for the between-fund
    # (genuine skill) variance tau².
    q_statistic = float(np.sum(weights * (v - weighted_mean) ** 2))
    degrees_of_freedom = v.size - 1
    c_constant = float(np.sum(weights) - np.sum(weights**2) / np.sum(weights))
    tau_squared = max(0.0, (q_statistic - degrees_of_freedom) / c_constant) if c_constant > 0 else 0.0

    shrinkage_weight = tau_squared / (tau_squared + s**2)
    shrunk = weighted_mean + shrinkage_weight * (v - weighted_mean)

    result = values.copy()
    result[valid] = shrunk
    return result
