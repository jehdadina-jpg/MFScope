"""
Add risk assessment columns to fund_score table
"""
import asyncio
from sqlalchemy import text
from backend.db.session import AsyncSessionLocal, engine
from loguru import logger


async def add_risk_columns():
    """Add risk_score, risk_level, and risk_shap_json columns to fund_score."""
    async with engine.begin() as conn:
        # Check if columns already exist
        result = await conn.execute(text(
            "SELECT COUNT(*) FROM pragma_table_info('fund_score') WHERE name='risk_score'"
        ))
        exists = result.scalar()
        
        if exists:
            logger.info("Risk columns already exist, skipping migration")
            return
        
        logger.info("Adding risk assessment columns to fund_score table...")
        
        # Add columns
        await conn.execute(text("ALTER TABLE fund_score ADD COLUMN risk_score FLOAT"))
        await conn.execute(text("ALTER TABLE fund_score ADD COLUMN risk_level VARCHAR(16)"))
        await conn.execute(text("ALTER TABLE fund_score ADD COLUMN risk_shap_json TEXT"))
        
        logger.success("✓ Risk columns added successfully")


if __name__ == "__main__":
    asyncio.run(add_risk_columns())
