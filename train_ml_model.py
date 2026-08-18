"""
Train the ML scoring model
===========================
This script trains the XGBoost model and saves it to models/xgb_scorer.ubj
"""

import asyncio
from backend.scoring.ml_model import MLScorer
from loguru import logger

async def main():
    logger.info("Starting ML model training...")
    
    try:
        scorer = MLScorer()
        metrics = await scorer.train()
        
        logger.success("✓ Model training complete!")
        logger.info(f"  MAE: {metrics['mae']:.4f}")
        logger.info(f"  R²: {metrics['r2']:.4f}")
        logger.info(f"  Training samples: {metrics['n_train']}")
        logger.info(f"  Test samples: {metrics['n_test']}")
        logger.info(f"  Model saved to: models/xgb_scorer.ubj")
        
        print("\n" + "="*60)
        print("ML model is ready! You can now use ML scoring in addition")
        print("to the rule-based scoring system.")
        print("="*60)
        
    except ImportError as e:
        logger.error(f"Missing ML dependencies: {e}")
        logger.info("Install ML dependencies with: pip install xgboost scikit-learn shap")
    except Exception as e:
        logger.error(f"Training failed: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main())
