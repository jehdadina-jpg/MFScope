"""
Return and risk metrics
=======================
Pure functions over a :class:`~backend.analytics.nav.NavSeries`.  Every one of
them returns ``None`` rather than a plausible-looking wrong number when the
input does not support the calculation.

Conventions (these match AMFI / SEBI factsheet practice, and Value Research
and Morningstar India report the same way)
------------------------------------------------------------------------
* Horizons **shorter than one year** are reported as **absolute** point-to-point
  returns.  Annualising a one-month move is how the old pipeline produced a
  46,000,000% "1M return".
* Horizons of **one year or longer** are reported as **CAGR**.
* Volatility is the annualised standard deviation of daily returns
  (``σ_daily × √252``), quoted in percent.
* Risk-free rate compounds geometrically to a daily rate; dividing an annual
  rate by 252 overstates it.
* Sharpe uses the standard deviation of *excess* returns; Sortino uses
  downside deviation measured against the target over **all** observations,
  not the standard deviation of the negative subset (which is a different,
  much smaller, and much more flattering number).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from backend.analytics.nav import NavSeries, align_returns, resample_month_ends

TRADING_DAYS_PER_YEAR = 252

#: India 10-year G-Sec, the conventional risk-free proxy for INR funds.
RISK_FREE_ANNUAL = 0.065
RISK_FREE_DAILY = (1.0 + RISK_FREE_ANNUAL) ** (1.0 / TRADING_DAYS_PER_YEAR) - 1.0

#: Minimum observations before a dispersion statistic means anything.
MIN_OBS_RISK = 120           # ~6 trading months
MIN_OBS_BETA = 120

#: A fund whose annualised volatility is below this is effectively a cash
#: account; ratios that divide by σ explode and carry no information.
MIN_VOL_FOR_RATIO_PCT = 0.15

#: Ratios are clipped to a defensible display range.
RATIO_CLIP = 12.0

#: Trailing-return horizons: label → (calendar days, annualise?)
HORIZONS: dict[str, tuple[int, bool]] = {
    "1m": (30, False),
    "3m": (91, False),
    "6m": (182, False),
    "1y": (365, True),
    "2y": (730, True),
    "3y": (1095, True),
    "5y": (1826, True),
    "10y": (3652, True),
}


def _clean(value: float | None) -> float | None:
    """Reject NaN/inf so they never reach the database or the API."""
    if value is None:
        return None
    if not math.isfinite(value):
        return None
    return float(value)


def _clip_ratio(value: float | None) -> float | None:
    value = _clean(value)
    if value is None:
        return None
    return float(np.clip(value, -RATIO_CLIP, RATIO_CLIP))


# ── Trailing returns ──────────────────────────────────────────────────────────

def trailing_return(nav: NavSeries, days: int, annualise: bool) -> float | None:
    """
    Point-to-point return over ``days`` calendar days, in percent.

    ``annualise`` converts to CAGR; only pass it for horizons ≥ 1 year.
    """
    end_value = float(nav.adjusted.iloc[-1])
    start_value = nav.value_asof(nav.end - pd.Timedelta(days=days))
    if start_value is None or start_value <= 0 or end_value <= 0:
        return None

    growth = end_value / start_value
    if not annualise:
        return _clean((growth - 1.0) * 100.0)

    years = days / 365.25
    if years <= 0:
        return None
    return _clean((growth ** (1.0 / years) - 1.0) * 100.0)


def return_ytd(nav: NavSeries) -> float | None:
    """Calendar year-to-date return, absolute."""
    year_start = pd.Timestamp(year=nav.end.year - 1, month=12, day=31)
    start_value = nav.value_asof(year_start, tolerance_days=12)
    if start_value is None or start_value <= 0:
        return None
    return _clean((float(nav.adjusted.iloc[-1]) / start_value - 1.0) * 100.0)


def return_since_inception(nav: NavSeries) -> float | None:
    """CAGR from the first available NAV print."""
    if nav.history_years < 1.0:
        return None
    growth = float(nav.adjusted.iloc[-1]) / float(nav.adjusted.iloc[0])
    if growth <= 0:
        return None
    return _clean((growth ** (1.0 / nav.history_years) - 1.0) * 100.0)


def all_trailing_returns(nav: NavSeries) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for label, (days, annualise) in HORIZONS.items():
        out[f"return_{label}"] = trailing_return(nav, days, annualise)
    out["return_ytd"] = return_ytd(nav)
    out["return_since_inception"] = return_since_inception(nav)
    return out


# ── Dispersion / risk ─────────────────────────────────────────────────────────

def volatility(returns: np.ndarray) -> float | None:
    """Annualised standard deviation of daily returns, in percent."""
    if returns.size < MIN_OBS_RISK:
        return None
    return _clean(float(np.std(returns, ddof=1) * math.sqrt(TRADING_DAYS_PER_YEAR) * 100.0))


def downside_deviation(returns: np.ndarray, target_daily: float = RISK_FREE_DAILY) -> float | None:
    """
    Annualised downside deviation, in percent.

    Shortfalls are averaged over *every* observation (upside days contribute a
    zero), which is what makes this the correct Sortino denominator.
    """
    if returns.size < MIN_OBS_RISK:
        return None
    shortfall = np.minimum(returns - target_daily, 0.0)
    dd = math.sqrt(float(np.mean(shortfall ** 2)))
    return _clean(dd * math.sqrt(TRADING_DAYS_PER_YEAR) * 100.0)


def sharpe(returns: np.ndarray, vol_pct: float | None) -> float | None:
    """Annualised Sharpe ratio; ``None`` for near-cash funds where σ ≈ 0."""
    if returns.size < MIN_OBS_RISK or vol_pct is None or vol_pct < MIN_VOL_FOR_RATIO_PCT:
        return None
    excess = returns - RISK_FREE_DAILY
    sd = float(np.std(excess, ddof=1))
    if sd <= 0:
        return None
    return _clip_ratio(float(np.mean(excess) / sd) * math.sqrt(TRADING_DAYS_PER_YEAR))


def sortino(returns: np.ndarray, downside_pct: float | None) -> float | None:
    if returns.size < MIN_OBS_RISK or downside_pct is None or downside_pct < MIN_VOL_FOR_RATIO_PCT:
        return None
    excess_annual = float(np.mean(returns - RISK_FREE_DAILY)) * TRADING_DAYS_PER_YEAR * 100.0
    return _clip_ratio(excess_annual / downside_pct)


def max_drawdown(series: pd.Series) -> float | None:
    """Worst peak-to-trough decline, as a negative percentage."""
    if len(series) < 20:
        return None
    values = series.to_numpy(dtype="float64")
    peak = np.maximum.accumulate(values)
    drawdowns = values / peak - 1.0
    return _clean(float(drawdowns.min()) * 100.0)


def drawdown_recovery_days(series: pd.Series, threshold: float = 0.05) -> float | None:
    """
    Longest stretch, in calendar days, spent more than ``threshold`` below the
    running peak.  Answers "how long was I underwater?", which is what an
    investor actually feels.
    """
    if len(series) < 30:
        return None
    values = series.to_numpy(dtype="float64")
    peak = np.maximum.accumulate(values)
    underwater = values < peak * (1.0 - threshold)
    if not underwater.any():
        return 0.0

    index = series.index
    longest = 0
    start: int | None = None
    for i, flag in enumerate(underwater):
        if flag and start is None:
            start = i
        elif not flag and start is not None:
            longest = max(longest, (index[i] - index[start]).days)
            start = None
    if start is not None:
        longest = max(longest, (index[-1] - index[start]).days)
    return float(longest)


def calmar(cagr_pct: float | None, max_dd_pct: float | None) -> float | None:
    """CAGR divided by the depth of the worst drawdown."""
    if cagr_pct is None or max_dd_pct is None or max_dd_pct >= -0.5:
        return None
    return _clip_ratio(cagr_pct / abs(max_dd_pct))


def value_at_risk(returns: np.ndarray, confidence: float = 0.95) -> float | None:
    """Historical one-day VaR, expressed as a negative percentage."""
    if returns.size < MIN_OBS_RISK:
        return None
    return _clean(float(np.percentile(returns, (1.0 - confidence) * 100.0)) * 100.0)


# ── Benchmark-relative ────────────────────────────────────────────────────────

@dataclass(slots=True)
class BenchmarkStats:
    alpha: float | None = None
    beta: float | None = None
    r_squared: float | None = None
    tracking_error: float | None = None
    information_ratio: float | None = None
    up_capture: float | None = None
    down_capture: float | None = None


def benchmark_stats(fund_returns: pd.Series, bench_returns: pd.Series) -> BenchmarkStats:
    """
    Jensen's alpha, beta, R², tracking error, information ratio and
    up/down capture against a market proxy.

    Alpha is measured on *excess* returns (fund − rf regressed on
    benchmark − rf), which is the textbook definition; regressing raw returns
    — as the previous implementation did — folds the risk-free rate into the
    intercept and inflates alpha for every low-beta fund.
    """
    stats = BenchmarkStats()
    f, b = align_returns(fund_returns, bench_returns)
    if f.size < MIN_OBS_BETA:
        return stats

    fx = f - RISK_FREE_DAILY
    bx = b - RISK_FREE_DAILY

    var_b = float(np.var(bx, ddof=1))
    if var_b <= 0:
        return stats

    beta = float(np.cov(fx, bx, ddof=1)[0, 1] / var_b)
    alpha_daily = float(np.mean(fx) - beta * np.mean(bx))

    corr = float(np.corrcoef(f, b)[0, 1])
    active = f - b
    te = float(np.std(active, ddof=1) * math.sqrt(TRADING_DAYS_PER_YEAR) * 100.0)

    stats.beta = _clip_ratio(beta)
    stats.alpha = _clean(((1.0 + alpha_daily) ** TRADING_DAYS_PER_YEAR - 1.0) * 100.0)
    stats.r_squared = _clean(corr ** 2) if math.isfinite(corr) else None
    stats.tracking_error = _clean(te)
    if te > 0.05:
        annual_active = float(np.mean(active)) * TRADING_DAYS_PER_YEAR * 100.0
        stats.information_ratio = _clip_ratio(annual_active / te)

    up = b > 0
    down = b < 0
    if up.sum() >= 20 and float(np.mean(b[up])) != 0:
        stats.up_capture = _clean(float(np.mean(f[up]) / np.mean(b[up])) * 100.0)
    if down.sum() >= 20 and float(np.mean(b[down])) != 0:
        stats.down_capture = _clean(float(np.mean(f[down]) / np.mean(b[down])) * 100.0)

    return stats


# ── Consistency ───────────────────────────────────────────────────────────────

def rolling_return_stats(nav: NavSeries, window_days: int = 365) -> dict[str, float | None]:
    """
    Dispersion of rolling one-year returns — the honest measure of
    "consistency".  A fund that returned 40/−5/30 is not the same animal as one
    that returned 22/21/23, even when the CAGRs match.

    Computed on month-end NAVs so the windows are independent enough to be
    meaningful and cheap enough to run across the whole universe.
    """
    empty = {
        "rolling_1y_mean": None,
        "rolling_1y_std": None,
        "rolling_1y_best": None,
        "rolling_1y_worst": None,
        "rolling_1y_positive_pct": None,
    }
    monthly = resample_month_ends(nav.adjusted)
    months = max(1, round(window_days / 30.44))
    if len(monthly) < months + 6:
        return empty

    values = monthly.to_numpy(dtype="float64")
    rolled = values[months:] / values[:-months] - 1.0
    rolled = rolled[np.isfinite(rolled)]
    if rolled.size < 6:
        return empty

    rolled_pct = rolled * 100.0
    return {
        "rolling_1y_mean": _clean(float(np.mean(rolled_pct))),
        "rolling_1y_std": _clean(float(np.std(rolled_pct, ddof=1))),
        "rolling_1y_best": _clean(float(np.max(rolled_pct))),
        "rolling_1y_worst": _clean(float(np.min(rolled_pct))),
        "rolling_1y_positive_pct": _clean(float(np.mean(rolled > 0)) * 100.0),
    }


# ── Momentum ──────────────────────────────────────────────────────────────────

def momentum(nav: NavSeries) -> dict[str, float | None]:
    latest = float(nav.adjusted.iloc[-1])
    out: dict[str, float | None] = {}

    for label, days in (("1m", 30), ("3m", 91), ("6m", 182)):
        past = nav.value_asof(nav.end - pd.Timedelta(days=days))
        out[f"momentum_roc_{label}"] = (
            _clean((latest / past - 1.0) * 100.0) if past and past > 0 else None
        )

    ma_50 = _moving_average(nav.adjusted, 50)
    ma_200 = _moving_average(nav.adjusted, 200)
    out["ma_50d"] = ma_50
    out["ma_200d"] = ma_200
    out["ma_crossover"] = _clean(latest / ma_200) if ma_200 else None
    return out


def _moving_average(series: pd.Series, window: int) -> float | None:
    if len(series) < window:
        return None
    return _clean(float(series.to_numpy(dtype="float64")[-window:].mean()))


# ── Aggregate ─────────────────────────────────────────────────────────────────

@dataclass(slots=True)
class MetricSet:
    values: dict[str, float | None] = field(default_factory=dict)

    def __getitem__(self, key: str) -> float | None:
        return self.values.get(key)


def compute_all(
    nav: NavSeries,
    benchmark_returns: pd.Series | None = None,
    as_of: date | None = None,
) -> dict[str, float | None]:
    """
    Full metric vector for one scheme.  Anything the history cannot support is
    ``None`` — never a filled-in guess.
    """
    out: dict[str, float | None] = {}
    out.update(all_trailing_returns(nav))

    window_1y = nav.window(365)
    returns_1y = window_1y.pct_change().dropna().to_numpy(dtype="float64")

    vol = volatility(returns_1y)
    dd = downside_deviation(returns_1y)
    mdd = max_drawdown(window_1y)

    out["volatility_1y"] = vol
    out["downside_deviation_1y"] = dd
    out["sharpe_1y"] = sharpe(returns_1y, vol)
    out["sortino_1y"] = sortino(returns_1y, dd)
    out["max_drawdown_1y"] = mdd
    out["drawdown_recovery_days"] = drawdown_recovery_days(window_1y)
    out["var_95_1y"] = value_at_risk(returns_1y)
    out["calmar_1y"] = calmar(out["return_1y"], mdd)

    window_3y = nav.window(1095)
    out["max_drawdown_3y"] = max_drawdown(window_3y)
    vol_3y = volatility(window_3y.pct_change().dropna().to_numpy(dtype="float64"))
    out["volatility_3y"] = vol_3y

    stats = BenchmarkStats()
    if benchmark_returns is not None and len(benchmark_returns) > MIN_OBS_BETA:
        stats = benchmark_stats(window_1y.pct_change().dropna(), benchmark_returns)
    out["alpha_1y"] = stats.alpha
    out["beta_1y"] = stats.beta
    out["r_squared_1y"] = stats.r_squared
    out["tracking_error_1y"] = stats.tracking_error
    out["information_ratio_1y"] = stats.information_ratio
    out["up_capture_1y"] = stats.up_capture
    out["down_capture_1y"] = stats.down_capture

    out.update(rolling_return_stats(nav))
    out.update(momentum(nav))

    out["nav_days"] = float(len(nav))
    out["history_years"] = _clean(nav.history_years)
    out["nav_adjustments"] = float(nav.adjustments)
    return out
