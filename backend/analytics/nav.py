"""
NAV series hygiene
==================
Everything downstream (returns, volatility, drawdown, Sharpe, the score) is a
function of one object: a clean, corporate-action-adjusted NAV series indexed
by calendar date.  Get this wrong and every number in the product is wrong.

Two problems the raw AMFI feed has
----------------------------------
1. **Corporate actions.**  When an IDCW plan pays out, or units are split /
   re-denominated, or a portfolio is side-pocketed, the NAV gaps down
   overnight.  Naively that reads as a −30% day.  The fix is the same one used
   for split-adjusted equity prices: walk backwards and scale the pre-event
   history by the gap factor so the series becomes continuous in *total
   return* terms.

2. **Calendar vs. trading days.**  An Indian fund publishes ~250 NAVs a year.
   The old code did ``series.iloc[len(series) - 365]`` to get "one year ago",
   which actually reaches back ~1.45 years and inflates every 1Y number.
   Anchoring must be by date, with a tolerance window for holidays.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

# Detecting a corporate action needs two agreeing signals, not one.
#
# An absolute threshold alone is wrong in both directions.  Too tight and it
# rewrites genuine crashes: a silver fund with 52% annualised volatility really
# can fall 20% in a session, and "correcting" that turns a −40% drawdown into a
# +246% return.  Too loose and it misses side-pocketing in a credit fund, where
# a 6% overnight gap is unmistakably an event because the fund's entire annual
# volatility is 1%.
#
# So a move must be extreme *in absolute terms* and extreme *relative to that
# fund's own recent volatility* before we treat it as an event.  A −20% day is
# 6σ for a silver fund (left alone) and 200σ for a liquid fund (adjusted).
CORPORATE_ACTION_DROP = -0.20
CORPORATE_ACTION_JUMP = 0.50

#: Sigma multiples required alongside the absolute thresholds above.
DROP_SIGMA_MULTIPLE = 8.0
JUMP_SIGMA_MULTIPLE = 10.0

#: Debt-like funds get a second, tighter rule: below this annualised
#: volatility no market move can produce the gap, so a smaller absolute
#: threshold is safe and catches side-pocketing.
LOW_VOL_ANNUAL_PCT = 4.0
LOW_VOL_DROP = -0.03
LOW_VOL_SIGMA_MULTIPLE = 12.0

#: Trailing window for the volatility estimate.  A full year, so a crash is
#: measured against a period that already contains turbulence.
SIGMA_WINDOW = 250
SIGMA_MIN_OBS = 40

#: How far either side of an anchor date we will accept a NAV print.
ANCHOR_TOLERANCE_DAYS = 10


class NavSeries:
    """
    A cleaned NAV history for one scheme.

    Attributes
    ----------
    raw : pd.Series
        As-published NAV, deduplicated, sorted, non-positive values removed.
    adjusted : pd.Series
        ``raw`` with corporate actions neutralised.  Use this for every
        return, risk and momentum calculation.
    adjustments : int
        Number of corporate actions detected and neutralised.
    """

    __slots__ = ("raw", "adjusted", "adjustments", "_index_values")

    def __init__(self, raw: pd.Series) -> None:
        self.raw = raw
        self.adjusted, self.adjustments = adjust_for_corporate_actions(raw)
        self._index_values = self.adjusted.index.values

    # ── Basic facts ──────────────────────────────────────────────────────────

    def __len__(self) -> int:
        return len(self.adjusted)

    @property
    def start(self) -> pd.Timestamp:
        return self.adjusted.index[0]

    @property
    def end(self) -> pd.Timestamp:
        return self.adjusted.index[-1]

    @property
    def latest_nav(self) -> float:
        return float(self.raw.iloc[-1])

    @property
    def history_years(self) -> float:
        return (self.end - self.start).days / 365.25

    # ── Date-anchored lookup ─────────────────────────────────────────────────

    def value_asof(
        self,
        anchor: pd.Timestamp | date,
        tolerance_days: int = ANCHOR_TOLERANCE_DAYS,
    ) -> float | None:
        """
        Latest NAV at or before ``anchor``.  Returns ``None`` when the closest
        print is further than ``tolerance_days`` away, or when the series
        simply does not reach back that far — the caller must then report the
        metric as unavailable rather than silently using the wrong window.
        """
        anchor_ts = pd.Timestamp(anchor)
        if anchor_ts < self.start - pd.Timedelta(days=tolerance_days):
            return None

        pos = int(np.searchsorted(self._index_values, anchor_ts.to_datetime64(), side="right")) - 1
        if pos < 0:
            # Anchor predates the first print but is inside tolerance.
            pos = 0
        found = self.adjusted.index[pos]
        if abs((found - anchor_ts).days) > tolerance_days:
            return None
        value = float(self.adjusted.iloc[pos])
        return value if value > 0 else None

    def window(self, days: int) -> pd.Series:
        """Trailing slice covering the last ``days`` calendar days."""
        cutoff = self.end - pd.Timedelta(days=days)
        return self.adjusted[self.adjusted.index >= cutoff]

    def daily_returns(self, days: int | None = None) -> pd.Series:
        series = self.adjusted if days is None else self.window(days)
        if len(series) < 2:
            return pd.Series(dtype=float)
        return series.pct_change().dropna()


# ── Construction ──────────────────────────────────────────────────────────────

def build_series(dates, values) -> pd.Series:
    """Assemble a clean, sorted, deduplicated, strictly-positive NAV series."""
    series = pd.Series(
        np.asarray(values, dtype="float64"),
        index=pd.DatetimeIndex(pd.to_datetime(list(dates))),
        dtype="float64",
    )
    series = series[np.isfinite(series.to_numpy()) & (series > 0)]
    series = series[~series.index.duplicated(keep="last")]
    return series.sort_index()


def _trailing_sigma(returns: np.ndarray) -> np.ndarray:
    """
    Backward-looking daily standard deviation at every point.

    Uses an expanding window until ``SIGMA_WINDOW`` observations are available,
    then a rolling one.  Points with too little history fall back to the
    series-wide sigma so early prints are not judged against noise.
    """
    frame = pd.Series(returns, dtype="float64")
    rolling = frame.shift(1).rolling(SIGMA_WINDOW, min_periods=SIGMA_MIN_OBS).std(ddof=1)
    overall = float(np.std(returns, ddof=1)) if returns.size > 2 else np.nan
    sigma = rolling.fillna(overall).to_numpy(dtype="float64")
    # A zero sigma (a fund that has literally not moved) would make every
    # subsequent move infinitely significant.
    return np.where(np.isfinite(sigma) & (sigma > 1e-9), sigma, np.inf)


def adjust_for_corporate_actions(series: pd.Series) -> tuple[pd.Series, int]:
    """
    Neutralise unit splits, re-denominations, payouts and side-pocketing.

    At every detected discontinuity the *entire preceding* history is rescaled
    by the gap factor, so the series keeps its real latest NAV but gains a
    continuous total-return path — the same convention as a split-adjusted
    equity price series.

    See the thresholds above for why detection needs both an absolute and a
    volatility-relative test to agree.
    """
    if len(series) < 5:
        return series, 0

    values = series.to_numpy(dtype="float64", copy=True)
    ratios = values[1:] / values[:-1] - 1.0
    if not np.isfinite(ratios).all():
        ratios = np.nan_to_num(ratios, nan=0.0, posinf=0.0, neginf=0.0)

    sigma = _trailing_sigma(ratios)
    annual_vol_pct = sigma * np.sqrt(252.0) * 100.0

    split_like = (ratios <= CORPORATE_ACTION_DROP) & (ratios <= -DROP_SIGMA_MULTIPLE * sigma)
    payout_like = (
        (annual_vol_pct < LOW_VOL_ANNUAL_PCT)
        & (ratios <= LOW_VOL_DROP)
        & (ratios <= -LOW_VOL_SIGMA_MULTIPLE * sigma)
    )
    jump_like = (ratios >= CORPORATE_ACTION_JUMP) & (ratios >= JUMP_SIGMA_MULTIPLE * sigma)

    breaks = np.flatnonzero(split_like | payout_like | jump_like)
    if breaks.size == 0:
        return series, 0

    # Apply from the newest break backwards so each factor compounds correctly.
    for idx in breaks[::-1]:
        previous = values[idx]
        if previous <= 0:
            continue
        values[: idx + 1] *= values[idx + 1] / previous

    return pd.Series(values, index=series.index, dtype="float64"), int(breaks.size)


def resample_month_ends(series: pd.Series) -> pd.Series:
    """Month-end NAV, used for rolling-window consistency measures."""
    if series.empty:
        return series
    return series.resample("ME").last().dropna()


# ── Benchmark construction ────────────────────────────────────────────────────

def blend_benchmark(series_list: list[pd.Series], min_members: int = 3) -> pd.Series | None:
    """
    Build a market proxy from a set of index-tracking NAV series.

    Uses the **cross-sectional median daily return** rather than an average of
    levels: medians are robust to a single fund's tracking glitch, and working
    in return space means funds with different NAV bases and different launch
    dates can all contribute.  The result is re-based to 100.
    """
    if len(series_list) < min_members:
        return None

    frame = pd.DataFrame({i: s for i, s in enumerate(series_list)})
    returns = frame.pct_change()
    # Require a quorum each day so a lone straggler cannot define the market.
    quorum = returns.notna().sum(axis=1) >= min_members
    median = returns[quorum].median(axis=1).dropna()
    if median.empty:
        return None

    level = (1.0 + median).cumprod() * 100.0
    return level


def align_returns(fund: pd.Series, benchmark: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    """Inner-join two return series on date and return them as bare arrays."""
    if fund.empty or benchmark.empty:
        return np.empty(0), np.empty(0)
    joined = pd.concat({"f": fund, "b": benchmark}, axis=1, join="inner").dropna()
    if joined.empty:
        return np.empty(0), np.empty(0)
    return joined["f"].to_numpy(dtype="float64"), joined["b"].to_numpy(dtype="float64")


def trading_gap_days(series: pd.Series, as_of: date) -> int:
    """Calendar days between the last NAV print and ``as_of``."""
    if series.empty:
        return 10**6
    return (pd.Timestamp(as_of) - series.index[-1]).days
