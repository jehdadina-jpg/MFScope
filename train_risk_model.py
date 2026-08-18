"""
Train the Risk Assessment Model
================================
Trains an XGBoost model to predict risk levels based on volatility,
drawdown, and stability metrics.
"""

import asyncio
from backend.scoring.risk_model import RiskModel
from loguru import logger


async def main():
    logger.info("Starting risk model training...")
    
    try:
        # Add risk columns if not exists
        logger.info("Ensuring database schema is up to date...")
        from add_risk_columns import add_risk_columns
        await add_risk_columns()
        
        # Train the model
        model = RiskModel()
        metrics = await model.train()
        
        logger.success("✓ Risk model training complete!")
        logger.info(f"  MAE: {metrics['mae']:.4f}")
        logger.info(f"  R²: {metrics['r2']:.4f}")
        logger.info(f"  Training samples: {metrics['n_train']}")
        logger.info(f"  Test samples: {metrics['n_test']}")
        logger.info(f"  Model saved to: models/risk_scorer.ubj")
        
        # Score all funds
        logger.info("\nScoring risk for all funds...")
        scored = await model.score_all_risks()
        logger.success(f"✓ Risk scoring complete: {scored} funds scored")
        
        print("\n" + "="*60)
        print("Risk assessment model is ready!")
        print("Funds now have risk scores (0-100) and levels (Low/Medium/High)")
        print("="*60)
        
    except ImportError as e:
        logger.error(f"Missing ML dependencies: {e}")
        logger.info("Install with: pip install xgboost scikit-learn shap")
    except Exception as e:
        logger.error(f"Training failed: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())
