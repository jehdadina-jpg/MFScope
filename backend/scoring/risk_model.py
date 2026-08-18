"""
ML Risk Assessment Model
=========================
Predicts risk level (Low/Medium/High) for mutual funds based on historical
volatility, drawdown, and stability metrics.

Risk Categories
---------------
- Low Risk    (0-33):  Stable, low volatility, small drawdowns
- Medium Risk (34-66): Moderate volatility, acceptable drawdowns
- High Risk   (67-100): High volatility, large drawdowns, unstable

Training Features
-----------------
- Volatility metrics: 1Y volatility, rolling vol std dev
- Drawdown metrics: Max drawdown, drawdown frequency, recovery time
- Stability: Beta, return consistency, AUM volatility
- Market conditions: Category volatility ranking

Model
-----
XGBoost classifier predicting risk score 0-100, mapped to Low/Medium/High.

Usage
-----
    model = RiskModel()
    await model.train()
    risk_score, risk_level = await model.predict_risk(scheme_id, as_of=date.today())
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd
from loguru import logger
from sqlalchemy import select

from backend.db.models import FundFeatures, FundScore, Scheme
from backend.db.session import AsyncSessionLocal

MODEL_PATH = Path("models/risk_scorer.ubj")

RiskLevel = Literal["Low", "Medium", "High"]

# Risk feature columns
RISK_FEATURES = [
    "volatility_1y",
    "max_drawdown_1y",
    "drawdown_recovery_days",
    "beta_1y",
    "return_1m", "return_3m", "return_6m", "return_1y",  # for consistency calc
    "aum_growth_3m",  # AUM stability
]


# ── Risk level mapping ────────────────────────────────────────────────────────

def _risk_level(score: float) -> RiskLevel:
    """Map 0-100 risk score to Low/Medium/High."""
    if score <= 33:
        return "Low"
    if score <= 66:
        return "Medium"
    return "High"


# ── Label computation (training targets) ──────────────────────────────────────

def _compute_risk_labels(df: pd.DataFrame) -> pd.Series:
    """
    Compute risk labels for training based on actual volatility and drawdown.
    Higher volatility + larger drawdowns = higher risk score.
    """
    # Normalize each metric to 0-100 percentile
    vol_pct = df["volatility_1y"].rank(pct=True) * 100
    dd_pct = df["max_drawdown_1y"].abs().rank(pct=True) * 100  # abs because drawdown is negative
    beta_pct = df["beta_1y"].abs().rank(pct=True) * 100
    
    # Return consistency (lower std dev = lower risk)
    df["_ret_std"] = df[["return_1m", "return_3m", "return_6m", "return_1y"]].std(axis=1)
    ret_consistency_pct = (1 - df["_ret_std"].rank(pct=True)) * 100  # invert: lower std = lower risk
    
    # Weighted risk score
    risk_score = (
        vol_pct * 0.35
        + dd_pct * 0.35
        + beta_pct * 0.20
        + ret_consistency_pct * 0.10
    ).clip(0, 100)
    
    return risk_score


# ── Main risk model ───────────────────────────────────────────────────────────

class RiskModel:

    def __init__(self) -> None:
        self._model = None
        self._explainer = None

    # ── Training ──────────────────────────────────────────────────────────────

    async def train(
        self,
        cutoff_date: date | None = None,
        xgb_params: dict | None = None,
    ) -> dict[str, float]:
        """
        Train XGBoost regressor to predict risk score 0-100.
        Returns evaluation metrics.
        """
        try:
            import xgboost as xgb
            from sklearn.metrics import mean_absolute_error, r2_score
        except ImportError as e:
            raise RuntimeError(f"ML deps not installed: {e}") from e

        if cutoff_date is None:
            cutoff_date = date.today() - timedelta(days=30)

        # Load all historical features
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(FundFeatures, Scheme.category)
                .join(Scheme, FundFeatures.scheme_id == Scheme.id)
                .where(FundFeatures.feature_date < cutoff_date)
                .order_by(FundFeatures.feature_date)
            )
            rows = result.all()

        if len(rows) < 100:
            raise ValueError(f"Insufficient training data: only {len(rows)} rows.")

        logger.info(f"Building risk training dataset from {len(rows)} feature rows …")

        # Build DataFrame
        records: list[dict] = []
        for feat, category in rows:
            d = {col: getattr(feat, col, None) for col in RISK_FEATURES}
            d["category"] = category
            records.append(d)

        df = pd.DataFrame(records)
        
        # Compute risk labels
        df["_risk_target"] = _compute_risk_labels(df)
        
        # Prepare features
        X = df[RISK_FEATURES].fillna(df[RISK_FEATURES].median())
        y = df["_risk_target"]

        # Time-based split
        split_idx = int(len(X) * 0.80)
        X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
        y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

        # Train XGBoost
        params = xgb_params or {
            "n_estimators": 200,
            "learning_rate": 0.05,
            "max_depth": 4,
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
            "r2": float(r2_score(y_test, y_pred)),
            "n_train": len(X_train),
            "n_test": len(X_test),
        }

        logger.info(f"Risk model training done: MAE={metrics['mae']:.4f}, R²={metrics['r2']:.4f}")

        # Save model
        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        model.save_model(str(MODEL_PATH))
        self._model = model
        logger.info(f"Risk model saved to {MODEL_PATH}")

        return metrics

    # ── Inference ─────────────────────────────────────────────────────────────

    def load(self) -> None:
        """Load a previously trained risk model from disk."""
        try:
            import xgboost as xgb
        except ImportError as e:
            raise RuntimeError(f"xgboost not installed: {e}") from e
        if not MODEL_PATH.exists():
            raise FileNotFoundError(f"No risk model at {MODEL_PATH}. Run train() first.")
        self._model = xgb.XGBRegressor()
        self._model.load_model(str(MODEL_PATH))
        logger.info(f"Risk model loaded from {MODEL_PATH}")

    def predict_single(
        self,
        feature_dict: dict[str, Any],
    ) -> tuple[float, RiskLevel, dict]:
        """
        Predict risk for a single feature dict.
        Returns (risk_score 0-100, risk_level, shap_dict).
        """
        if self._model is None:
            self.load()
        import shap

        df = pd.DataFrame([{col: feature_dict.get(col) for col in RISK_FEATURES}])
        df = df.fillna(df.median())

        raw_pred: float = float(self._model.predict(df)[0])
        risk_score = float(np.clip(raw_pred, 0, 100))
        risk_level = _risk_level(risk_score)

        # SHAP explanation
        if self._explainer is None:
            self._explainer = shap.TreeExplainer(self._model)
        shap_values = self._explainer.shap_values(df)
        shap_dict = {
            col: round(float(shap_values[0][i]), 4)
            for i, col in enumerate(RISK_FEATURES)
        }

        return risk_score, risk_level, shap_dict

    async def score_all_risks(self, as_of: date | None = None) -> int:
        """
        Score risk for all schemes with features on `as_of` date.
        Updates FundScore with risk_score and risk_level.
        """
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
                d = {col: getattr(feat, col, None) for col in RISK_FEATURES}
                try:
                    risk_score, risk_level, shap_dict = self.predict_single(d)
                except Exception as exc:
                    logger.warning(f"Risk predict failed for scheme {feat.scheme_id}: {exc}")
                    continue

                # Update existing FundScore or create if missing
                existing = await session.scalar(
                    select(FundScore)
                    .where(FundScore.scheme_id == feat.scheme_id)
                    .where(FundScore.score_date == as_of)
                )
                if existing:
                    existing.risk_score = risk_score
                    existing.risk_level = risk_level
                    # Store risk SHAP in a separate field or append to existing shap_json
                    risk_shap_str = json.dumps({"risk_shap": shap_dict})
                    existing.risk_shap_json = risk_shap_str
                else:
                    # Create minimal score entry with risk only
                    session.add(FundScore(
                        scheme_id=feat.scheme_id,
                        score_date=as_of,
                        composite_score=50.0,  # placeholder
                        conviction="Hold",
                        model_version="risk_v1",
                        risk_score=risk_score,
                        risk_level=risk_level,
                        risk_shap_json=json.dumps({"risk_shap": shap_dict}),
                    ))
                written += 1

            await session.commit()

        logger.info(f"Risk scoring complete: {written} scores updated.")
        return written


# ── Standalone training entry point ──────────────────────────────────────────

if __name__ == "__main__":
    import asyncio

    async def main():
        model = RiskModel()
        metrics = await model.train()
        print(f"Risk model training metrics: {metrics}")

    asyncio.run(main())
