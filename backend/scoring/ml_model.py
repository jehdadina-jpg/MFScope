"""
ML Scoring Model  (v2 — Stretch Goal)
======================================
Trains an XGBoost regressor to predict forward 6-month risk-adjusted return
from features available at the time of prediction (strict point-in-time).

Key design decisions
--------------------
- Time-based train/test split (never random) — funds are time series.
- Forward label = Sharpe ratio over the *next* 180 days, computed from NAV data
  available after `feature_date`.  The label is therefore only available for
  historical rows; today's features have no label (inference mode).
- SHAP values are computed per prediction and stored in FundScore.shap_json.

Persistence
-----------
Trained model artefact is saved to  models/xgb_scorer.ubj  (XGBoost native
format).  The file is gitignored — regenerate with `python -m backend.scoring.ml_model`.

Public interface
----------------
    trainer = MLScorer()
    await trainer.train(cutoff_date=date(2024, 1, 1))
    await trainer.score_all(as_of=date.today())

    # Or load a pre-trained model:
    trainer = MLScorer()
    trainer.load()
    score, label = trainer.predict_single(feature_dict)
"""

from __future__ import annotations

import json
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from loguru import logger
from sqlalchemy import select

from backend.db.models import ConvictionLabel, FundFeatures, FundScore, NAVRecord, Scheme
from backend.db.session import AsyncSessionLocal
from backend.scoring.rule_based import _label  # reuse label mapping

MODEL_PATH = Path("models/xgb_scorer.ubj")

# Feature columns fed to the model (excludes ids, dates, target)
FEATURE_COLS = [
    "return_1m", "return_3m", "return_6m", "return_1y", "return_3y",
    "volatility_1y", "sharpe_1y", "sortino_1y", "alpha_1y", "beta_1y",
    "max_drawdown_1y", "drawdown_recovery_days",
    "momentum_roc_1m", "momentum_roc_3m", "ma_crossover",
    "expense_ratio", "aum_crore", "aum_growth_3m",
    "manager_tenure_years", "portfolio_turnover", "category_rank_pct",
    "sentiment_7d", "sentiment_30d", "news_volume_7d", "news_volume_spike",
    "category_avg_return_1y",
]


# ── Forward label computation ─────────────────────────────────────────────────

async def _compute_forward_sharpe(scheme_id: int, from_date: date, days: int = 180) -> float | None:
    """
    Compute Sharpe ratio of the scheme's NAV over the next `days` days
    starting from `from_date`.  Returns None if insufficient data.
    """
    from backend.features.feature_builder import (
        RISK_FREE_DAILY,
        TRADING_DAYS_PER_YEAR,
        _daily_returns,
    )
    end_date = from_date + timedelta(days=days)
    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            select(NAVRecord.nav_date, NAVRecord.nav)
            .where(NAVRecord.scheme_id == scheme_id)
            .where(NAVRecord.nav_date > from_date)
            .where(NAVRecord.nav_date <= end_date)
            .order_by(NAVRecord.nav_date)
        )
        data = rows.all()
    if len(data) < 20:
        return None
    series = pd.Series(
        [float(r.nav) for r in data],
        index=pd.DatetimeIndex([r.nav_date for r in data]),
    )
    daily_rets = _daily_returns(series)
    excess = daily_rets - RISK_FREE_DAILY
    std = daily_rets.std()
    if std == 0:
        return None
    return float((excess.mean() / std) * np.sqrt(TRADING_DAYS_PER_YEAR))


# ── Main ML scorer ────────────────────────────────────────────────────────────

class MLScorer:

    def __init__(self) -> None:
        self._model = None
        self._explainer = None

    # ── Training ──────────────────────────────────────────────────────────────

    async def build_training_data(
        self,
        cutoff_date: date,
        forward_days: int = 180,
    ) -> tuple[pd.DataFrame, pd.Series]:
        """
        Build (X, y) for training.
        - X = feature rows with feature_date < cutoff_date
        - y = forward Sharpe computed from NAV after feature_date
        Only rows where forward Sharpe can be computed are included.
        """
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(FundFeatures)
                .where(FundFeatures.feature_date < cutoff_date)
                .order_by(FundFeatures.feature_date)
            )
            rows = list(result.scalars().all())

        logger.info(f"Computing forward labels for {len(rows)} historical feature rows …")
        records: list[dict] = []
        for feat in rows:
            fwd_sharpe = await _compute_forward_sharpe(
                feat.scheme_id, feat.feature_date, days=forward_days
            )
            if fwd_sharpe is None:
                continue
            d = {col: getattr(feat, col, None) for col in FEATURE_COLS}
            d["_target"] = fwd_sharpe
            records.append(d)

        df = pd.DataFrame(records)
        X = df[FEATURE_COLS].fillna(df[FEATURE_COLS].median())
        y = df["_target"]
        logger.info(f"Training dataset: {len(X)} rows, {len(FEATURE_COLS)} features.")
        return X, y

    async def train(
        self,
        cutoff_date: date | None = None,
        forward_days: int = 180,
        xgb_params: dict | None = None,
    ) -> dict[str, float]:
        """
        Train XGBoost regressor.  Saves model to MODEL_PATH.
        Returns a dict of evaluation metrics on the test split.
        """
        try:
            import xgboost as xgb
            from sklearn.metrics import mean_absolute_error, r2_score
            from sklearn.model_selection import TimeSeriesSplit
        except ImportError as e:
            raise RuntimeError(f"ML deps not installed: {e}") from e

        if cutoff_date is None:
            cutoff_date = date.today() - timedelta(days=forward_days + 30)

        X, y = await self.build_training_data(cutoff_date, forward_days)
        if len(X) < 50:
            raise ValueError(f"Insufficient training data: only {len(X)} rows.")

        # Time-based split: last 20% of rows are the test set
        split_idx = int(len(X) * 0.80)
        X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
        y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

        params = xgb_params or {
            "n_estimators": 300,
            "learning_rate": 0.05,
            "max_depth": 5,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "reg_alpha": 0.1,
            "reg_lambda": 1.0,
            "random_state": 42,
            "n_jobs": -1,
        }

        model = xgb.XGBRegressor(**params)
        model.fit(
            X_train, y_train,
            eval_set=[(X_test, y_test)],
            verbose=False,
        )

        # Evaluate
        y_pred = model.predict(X_test)
        metrics = {
            "mae": float(mean_absolute_error(y_test, y_pred)),
            "r2":  float(r2_score(y_test, y_pred)),
            "n_train": len(X_train),
            "n_test":  len(X_test),
        }
        logger.info(f"XGBoost training done: MAE={metrics['mae']:.4f}, R²={metrics['r2']:.4f}")

        # Save model
        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        model.save_model(str(MODEL_PATH))
        self._model = model
        logger.info(f"Model saved to {MODEL_PATH}")

        return metrics

    # ── Inference ─────────────────────────────────────────────────────────────

    def load(self) -> None:
        """Load a previously trained model from disk."""
        try:
            import xgboost as xgb
        except ImportError as e:
            raise RuntimeError(f"xgboost not installed: {e}") from e
        if not MODEL_PATH.exists():
            raise FileNotFoundError(f"No model found at {MODEL_PATH}. Run train() first.")
        self._model = xgb.XGBRegressor()
        self._model.load_model(str(MODEL_PATH))
        logger.info(f"Model loaded from {MODEL_PATH}")

    def predict_single(self, feature_dict: dict[str, Any]) -> tuple[float, ConvictionLabel, dict]:
        """
        Predict for a single feature dict.
        Returns (composite_score 0-100, label, shap_dict).
        """
        if self._model is None:
            self.load()
        import shap

        df = pd.DataFrame([{col: feature_dict.get(col) for col in FEATURE_COLS}])
        df = df.fillna(df.median())

        raw_pred: float = float(self._model.predict(df)[0])

        # Map predicted Sharpe to 0-100 score
        # Empirical mapping: Sharpe 2.0+ → 100, -1.0 → 0
        score = float(np.clip((raw_pred + 1.0) / 3.0 * 100, 0, 100))
        label = _label(score)

        # SHAP explanation
        if self._explainer is None:
            self._explainer = shap.TreeExplainer(self._model)
        shap_values = self._explainer.shap_values(df)
        shap_dict = {col: round(float(shap_values[0][i]), 4) for i, col in enumerate(FEATURE_COLS)}

        return score, label, shap_dict

    async def score_all(self, as_of: date | None = None) -> int:
        """Score all schemes that have feature rows for `as_of` using the ML model."""
        if as_of is None:
            as_of = date.today()

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(FundFeatures)
                .where(FundFeatures.feature_date == as_of)
            )
            feats = list(result.scalars().all())

        if not feats:
            logger.warning(f"No features for {as_of}.")
            return 0

        written = 0
        async with AsyncSessionLocal() as session:
            for feat in feats:
                d = {col: getattr(feat, col, None) for col in FEATURE_COLS}
                try:
                    score, label, shap_dict = self.predict_single(d)
                except Exception as exc:
                    logger.warning(f"ML predict failed for scheme {feat.scheme_id}: {exc}")
                    continue

                existing = await session.scalar(
                    select(FundScore)
                    .where(FundScore.scheme_id == feat.scheme_id)
                    .where(FundScore.score_date == as_of)
                )
                if existing:
                    existing.composite_score = score
                    existing.conviction = label.value
                    existing.model_version = "xgb_v1"
                    existing.shap_json = json.dumps(shap_dict)
                else:
                    session.add(FundScore(
                        scheme_id=feat.scheme_id,
                        score_date=as_of,
                        composite_score=score,
                        conviction=label.value,
                        model_version="xgb_v1",
                        shap_json=json.dumps(shap_dict),
                    ))
                written += 1

            await session.commit()

        logger.info(f"ML scoring complete: {written} scores written.")
        return written


# ── Standalone training entry point ──────────────────────────────────────────

if __name__ == "__main__":
    import asyncio

    async def main():
        scorer = MLScorer()
        metrics = await scorer.train()
        print(f"Training metrics: {metrics}")

    asyncio.run(main())
