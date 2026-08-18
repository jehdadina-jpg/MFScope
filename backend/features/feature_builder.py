"""
Feature Builder
===============
Computes the full feature vector for every active scheme and writes it into
the fund_features table.  All features are computed point-in-time from data
already in the DB — no future data leakage.

Feature groups
--------------
1. Trailing returns          (1M / 3M / 6M / 1Y / 3Y / 5Y)
2. Risk metrics              (volatility, Sharpe, Sortino, alpha, beta, max drawdown)
3. Momentum                  (rate of change, MA crossover)
4. Fundamental / fund data   (expense ratio, AUM, manager tenure, portfolio turnover)
5. Relative rank             (category percentile rank)
6. News sentiment            (rolling 7d / 30d compound score, volume, spike detection)

Public interface
----------------
    builder = FeatureBuilder()
    df = await builder.build_features(scheme_id, as_of=date.today())
    await builder.build_all_features(as_of=date.today())
"""

from __future__ import annotations

import asyncio
import math
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd
from loguru import logger
from sqlalchemy import func, select

from backend.db.models import FundFeatures, FundMetadata, NAVRecord, NewsSentiment, Scheme
from backend.db.session import AsyncSessionLocal

# ── Constants ─────────────────────────────────────────────────────────────────

TRADING_DAYS_PER_YEAR = 252
RISK_FREE_RATE_ANNUAL = 0.065  # ~6.5% (approximate India 10-yr g-sec yield)
RISK_FREE_DAILY = RISK_FREE_RATE_ANNUAL / TRADING_DAYS_PER_YEAR

# Minimum required days for each metric type (includes buffer for market holidays)
MIN_DAYS_1M = 35
MIN_DAYS_3M = 95
MIN_DAYS_6M = 185
MIN_DAYS_1Y = 370
MIN_DAYS_3Y = 1100
MIN_DAYS_5Y = 1850


# ── NAV series helpers ────────────────────────────────────────────────────────

def _validate_nav_length(series: pd.Series, required_days: int) -> bool:
    """Check if NAV series has enough data points for calculation."""
    return len(series) >= required_days


def _risk_metrics_validated(nav_1y: pd.Series) -> bool:
    """Validate if NAV series has sufficient data for risk metrics calculation."""
    return _validate_nav_length(nav_1y, MIN_DAYS_1Y)


def _trailing_return_validated(
    series: pd.Series, 
    days: int, 
    min_required: int,
    scheme_code: str | None = None,
    metric_name: str | None = None
) -> float | None:
    """Calculate trailing return only if sufficient data exists."""
    if not _validate_nav_length(series, min_required):
        # Structured logging for validation failure
        logger.debug(
            "Validation failed for trailing return",
            extra={
                "validation_type": "return",
                "scheme_code": scheme_code or "UNKNOWN",
                "metric": metric_name or f"{days}d_return",
                "available_days": len(series),
                "required_days": min_required,
                "validation_result": "FAIL"
            }
        )
        return None
    
    # Proceed with calculation
    if len(series) < 2:
        return None
    end_val = series.iloc[-1]
    # Find the nav closest to `days` ago
    start_idx = max(0, len(series) - days)
    start_val = series.iloc[start_idx]
    if start_val == 0:
        return None
    raw = (end_val / start_val) - 1
    # Annualise
    years = days / 365
    if years <= 0:
        return None
    return ((1 + raw) ** (1 / years) - 1) * 100  # as percentage


def _trailing_return(series: pd.Series, days: int) -> float | None:
    """Annualised trailing return over `days` calendar days."""
    if len(series) < 2:
        return None
    end_val = series.iloc[-1]
    # Find the nav closest to `days` ago
    start_idx = max(0, len(series) - days)
    start_val = series.iloc[start_idx]
    if start_val == 0:
        return None
    raw = (end_val / start_val) - 1
    # Annualise
    years = days / 365
    if years <= 0:
        return None
    return ((1 + raw) ** (1 / years) - 1) * 100  # as percentage


def _daily_returns(series: pd.Series) -> pd.Series:
    return series.pct_change().dropna()


def _volatility(daily_rets: pd.Series) -> float | None:
    if len(daily_rets) < 20:
        return None
    return float(daily_rets.std() * math.sqrt(TRADING_DAYS_PER_YEAR) * 100)


def _sharpe(daily_rets: pd.Series) -> float | None:
    if len(daily_rets) < 20:
        return None
    excess = daily_rets - RISK_FREE_DAILY
    std = daily_rets.std()
    if std == 0:
        return None
    return float((excess.mean() / std) * math.sqrt(TRADING_DAYS_PER_YEAR))


def _sortino(daily_rets: pd.Series) -> float | None:
    if len(daily_rets) < 20:
        return None
    excess = daily_rets - RISK_FREE_DAILY
    downside = daily_rets[daily_rets < 0]
    if len(downside) == 0:
        return None
    downside_std = downside.std()
    if downside_std == 0:
        return None
    return float((excess.mean() / downside_std) * math.sqrt(TRADING_DAYS_PER_YEAR))


def _max_drawdown(series: pd.Series) -> float | None:
    if len(series) < 5:
        return None
    roll_max = series.cummax()
    drawdown = (series - roll_max) / roll_max
    return float(drawdown.min() * 100)  # negative percentage


def _drawdown_recovery_days(series: pd.Series) -> float | None:
    """Average days to recover from a drawdown > 5%."""
    if len(series) < 30:
        return None
    roll_max = series.cummax()
    in_drawdown = series < roll_max * 0.95
    recoveries: list[int] = []
    count = 0
    for dd in in_drawdown:
        if dd:
            count += 1
        elif count > 0:
            recoveries.append(count)
            count = 0
    if not recoveries:
        return 0.0
    return float(np.mean(recoveries))


def _alpha_beta(fund_rets: pd.Series, bench_rets: pd.Series) -> tuple[float | None, float | None]:
    """OLS alpha and beta vs a benchmark return series."""
    common = fund_rets.align(bench_rets, join="inner")
    f, b = common[0].dropna(), common[1].dropna()
    if len(f) < 20:
        return None, None
    try:
        beta, alpha = np.polyfit(b, f, 1)
        return float(alpha * TRADING_DAYS_PER_YEAR * 100), float(beta)
    except Exception:
        return None, None


def _momentum_roc(series: pd.Series, days: int) -> float | None:
    if len(series) < days + 1:
        return None
    start = series.iloc[-(days + 1)]
    end = series.iloc[-1]
    if start == 0:
        return None
    return float((end / start - 1) * 100)


def _moving_average(series: pd.Series, window: int) -> float | None:
    if len(series) < window:
        return None
    return float(series.rolling(window).mean().iloc[-1])


# ── Sentiment aggregation ─────────────────────────────────────────────────────

async def _load_sentiment(scheme_id: int, category: str, as_of: date) -> dict[str, float | None]:
    """
    Compute rolling sentiment signals for a scheme.
    Combines scheme-specific articles with category-level articles.
    """
    async with AsyncSessionLocal() as session:
        from backend.db.models import NewsArticle

        since_7d = as_of - timedelta(days=7)
        since_30d = as_of - timedelta(days=30)
        since_90d = as_of - timedelta(days=90)

        # Fetch sentiment rows linked to this scheme or its category
        stmt = (
            select(NewsSentiment.compound_score, NewsArticle.published_at)
            .join(NewsArticle, NewsSentiment.article_id == NewsArticle.id)
            .where(
                (NewsSentiment.scheme_id == scheme_id) | (NewsSentiment.category == category)
            )
            .where(NewsArticle.published_at >= since_90d.strftime("%Y-%m-%d"))
            .order_by(NewsArticle.published_at)
        )
        result = await session.execute(stmt)
        rows = result.all()

    if not rows:
        return {"sentiment_7d": None, "sentiment_30d": None,
                "news_volume_7d": None, "news_volume_spike": None}

    df = pd.DataFrame(rows, columns=["compound", "published_at"])
    df["published_at"] = pd.to_datetime(df["published_at"])
    df = df.dropna(subset=["published_at"])

    as_of_dt = pd.Timestamp(as_of)
    mask_7d = df["published_at"] >= (as_of_dt - pd.Timedelta(days=7))
    mask_30d = df["published_at"] >= (as_of_dt - pd.Timedelta(days=30))

    sentiment_7d = float(df.loc[mask_7d, "compound"].mean()) if mask_7d.any() else None
    sentiment_30d = float(df.loc[mask_30d, "compound"].mean()) if mask_30d.any() else None
    news_volume_7d = float(mask_7d.sum())

    # Volume spike: z-score of 7-day count vs 90-day rolling avg
    daily_counts = df.groupby(df["published_at"].dt.date).size()
    if len(daily_counts) >= 7:
        mean_count = daily_counts.mean()
        std_count = daily_counts.std()
        vol_7d_count = news_volume_7d
        news_volume_spike = float((vol_7d_count - mean_count * 7) / (std_count * math.sqrt(7) + 1e-9))
    else:
        news_volume_spike = None

    return {
        "sentiment_7d": sentiment_7d,
        "sentiment_30d": sentiment_30d,
        "news_volume_7d": news_volume_7d,
        "news_volume_spike": news_volume_spike,
    }


# ── Category averages ─────────────────────────────────────────────────────────

async def _category_avg_return_1y(category: str, as_of: date) -> float | None:
    """Average 1-year return across all schemes in the same category."""
    # We pull this from already-computed features if available, otherwise return None
    async with AsyncSessionLocal() as session:
        stmt = (
            select(func.avg(FundFeatures.return_1y))
            .join(Scheme, FundFeatures.scheme_id == Scheme.id)
            .where(Scheme.category == category)
            .where(FundFeatures.feature_date == as_of)
        )
        result = await session.scalar(stmt)
    return float(result) if result is not None else None


# ── Main builder ──────────────────────────────────────────────────────────────

class FeatureBuilder:

    async def build_features(
        self,
        scheme_id: int,
        as_of: date | None = None,
        benchmark_series: pd.Series | None = None,
    ) -> dict[str, Any] | None:
        """
        Compute the full feature dict for one scheme as of `as_of`.
        Returns None if there is insufficient NAV history.
        """
        if as_of is None:
            as_of = date.today()

        # Load NAV history (5 years back)
        since = as_of - timedelta(days=365 * 5 + 30)
        async with AsyncSessionLocal() as session:
            scheme = await session.get(Scheme, scheme_id)
            if not scheme:
                return None

            nav_rows = await session.execute(
                select(NAVRecord.nav_date, NAVRecord.nav)
                .where(NAVRecord.scheme_id == scheme_id)
                .where(NAVRecord.nav_date >= since)
                .where(NAVRecord.nav_date <= as_of)
                .order_by(NAVRecord.nav_date)
            )
            nav_data = nav_rows.all()

            # Latest metadata
            meta_row = await session.scalar(
                select(FundMetadata)
                .where(FundMetadata.scheme_id == scheme_id)
                .order_by(FundMetadata.as_of_date.desc())
                .limit(1)
            )

        if len(nav_data) < 30:
            return None  # not enough history

        nav_series = pd.Series(
            [float(row.nav) for row in nav_data],
            index=pd.DatetimeIndex([row.nav_date for row in nav_data]),
            dtype=float,
        ).sort_index()

        daily_rets = _daily_returns(nav_series)

        # ── Returns ──────────────────────────────────────────────────────────
        # Use validated return calculations that check minimum data requirements
        r1m  = _trailing_return_validated(nav_series, 30, MIN_DAYS_1M, scheme.scheme_code, "return_1m")
        r3m  = _trailing_return_validated(nav_series, 90, MIN_DAYS_3M, scheme.scheme_code, "return_3m")
        r6m  = _trailing_return_validated(nav_series, 180, MIN_DAYS_6M, scheme.scheme_code, "return_6m")
        r1y  = _trailing_return_validated(nav_series, 365, MIN_DAYS_1Y, scheme.scheme_code, "return_1y")
        r3y  = _trailing_return_validated(nav_series, 365 * 3, MIN_DAYS_3Y, scheme.scheme_code, "return_3y")
        r5y  = _trailing_return_validated(nav_series, 365 * 5, MIN_DAYS_5Y, scheme.scheme_code, "return_5y")

        # ── Risk ─────────────────────────────────────────────────────────────
        cutoff_1y = nav_series.index[-1] - pd.Timedelta(days=365)
        nav_1y = nav_series[nav_series.index >= cutoff_1y]
        rets_1y = _daily_returns(nav_1y)
        
        # Validate sufficient data before calculating risk metrics
        if _risk_metrics_validated(nav_1y):
            vol   = _volatility(rets_1y)
            sharpe = _sharpe(rets_1y)
            sortino = _sortino(rets_1y)
            mdd = _max_drawdown(nav_1y)
            drd = _drawdown_recovery_days(nav_1y)

            # Alpha / beta vs benchmark (if provided, else skip)
            alpha, beta = None, None
            if benchmark_series is not None:
                bench_rets = _daily_returns(benchmark_series)
                alpha, beta = _alpha_beta(rets_1y, bench_rets)
        else:
            # Structured logging for validation failure on risk metrics
            logger.debug(
                "Validation failed for risk metrics",
                extra={
                    "validation_type": "risk_metrics",
                    "scheme_code": scheme.scheme_code,
                    "metrics": ["volatility_1y", "sharpe_1y", "sortino_1y", "alpha_1y", "beta_1y", "max_drawdown_1y"],
                    "available_days": len(nav_1y),
                    "required_days": MIN_DAYS_1Y,
                    "validation_result": "FAIL"
                }
            )
            vol = sharpe = sortino = mdd = drd = alpha = beta = None

        # ── Momentum ─────────────────────────────────────────────────────────
        roc_1m = _momentum_roc(nav_series, 21)
        roc_3m = _momentum_roc(nav_series, 63)
        ma50  = _moving_average(nav_series, 50)
        ma200 = _moving_average(nav_series, 200)
        ma_cross = float(nav_series.iloc[-1] / ma200) if ma200 and ma200 > 0 else None

        # ── Fundamental ───────────────────────────────────────────────────────
        expense_ratio = meta_row.expense_ratio if meta_row else None
        aum_crore = meta_row.aum_crore if meta_row else None
        manager_tenure = meta_row.manager_tenure_years if meta_row else None
        portfolio_turnover = meta_row.portfolio_turnover if meta_row else None

        # AUM growth: compare two latest metadata snapshots
        aum_growth_3m = await self._aum_growth(scheme_id)

        # Category rank percentile
        rank_pct = await self._category_rank_pct(scheme_id, scheme.category)

        # ── Sentiment ─────────────────────────────────────────────────────────
        sent = await _load_sentiment(scheme_id, scheme.category, as_of)

        # ── Category context ──────────────────────────────────────────────────
        cat_avg_1y = await _category_avg_return_1y(scheme.category, as_of)

        return {
            "scheme_id": scheme_id,
            "feature_date": as_of,
            # Returns
            "return_1m": r1m, "return_3m": r3m, "return_6m": r6m,
            "return_1y": r1y, "return_3y": r3y, "return_5y": r5y,
            # Risk
            "volatility_1y": vol,
            "sharpe_1y": sharpe,
            "sortino_1y": sortino,
            "alpha_1y": alpha,
            "beta_1y": beta,
            "max_drawdown_1y": mdd,
            "drawdown_recovery_days": drd,
            # Momentum
            "momentum_roc_1m": roc_1m,
            "momentum_roc_3m": roc_3m,
            "ma_50d": ma50,
            "ma_200d": ma200,
            "ma_crossover": ma_cross,
            # Fundamental
            "expense_ratio": expense_ratio,
            "aum_crore": aum_crore,
            "aum_growth_3m": aum_growth_3m,
            "manager_tenure_years": manager_tenure,
            "portfolio_turnover": portfolio_turnover,
            "category_rank_pct": rank_pct,
            # Sentiment
            **sent,
            # Context
            "category_avg_return_1y": cat_avg_1y,
            "sector_index_return_1m": None,  # populated separately if sector index NAV available
        }

    async def _aum_growth(self, scheme_id: int) -> float | None:
        async with AsyncSessionLocal() as session:
            rows = await session.execute(
                select(FundMetadata.aum_crore, FundMetadata.as_of_date)
                .where(FundMetadata.scheme_id == scheme_id)
                .order_by(FundMetadata.as_of_date.desc())
                .limit(2)
            )
            data = rows.all()
        if len(data) < 2 or data[1].aum_crore in (None, 0):
            return None
        return float((data[0].aum_crore - data[1].aum_crore) / data[1].aum_crore * 100)

    async def _category_rank_pct(self, scheme_id: int, category: str) -> float | None:
        async with AsyncSessionLocal() as session:
            meta = await session.scalar(
                select(FundMetadata)
                .where(FundMetadata.scheme_id == scheme_id)
                .order_by(FundMetadata.as_of_date.desc())
                .limit(1)
            )
        if meta is None or meta.category_rank is None or meta.category_total in (None, 0):
            return None
        # 0 = best rank, 1 = worst rank
        return float((meta.category_rank - 1) / meta.category_total)

    async def persist_features(self, features: dict[str, Any]) -> None:
        """Upsert a feature dict into fund_features table."""
        scheme_id = features["scheme_id"]
        feat_date = features["feature_date"]

        async with AsyncSessionLocal() as session:
            existing = await session.scalar(
                select(FundFeatures)
                .where(FundFeatures.scheme_id == scheme_id)
                .where(FundFeatures.feature_date == feat_date)
            )
            if existing:
                for k, v in features.items():
                    if hasattr(existing, k):
                        setattr(existing, k, v)
            else:
                obj = FundFeatures(**{k: v for k, v in features.items() if hasattr(FundFeatures, k)})
                session.add(obj)
            await session.commit()

    async def build_all_features(
        self,
        as_of: date | None = None,
        concurrency: int = 8,
    ) -> int:
        """
        Build and persist features for all active schemes.
        Uses a semaphore to limit DB concurrency.
        """
        if as_of is None:
            as_of = date.today()

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Scheme.id).where(Scheme.is_active == True)
            )
            scheme_ids = [row[0] for row in result.all()]

        logger.info(f"Building features for {len(scheme_ids)} schemes as of {as_of} …")

        sem = asyncio.Semaphore(concurrency)
        built = 0

        async def _one(sid: int) -> None:
            nonlocal built
            async with sem:
                try:
                    features = await self.build_features(sid, as_of=as_of)
                    if features:
                        await self.persist_features(features)
                        built += 1
                except Exception as exc:
                    logger.warning(f"Feature build failed for scheme {sid}: {exc}")

        await asyncio.gather(*[_one(sid) for sid in scheme_ids])
        logger.info(f"Feature build complete: {built}/{len(scheme_ids)} schemes.")
        return built
