"""
Verification script to check inception_date population.
Samples a few schemes and verifies inception_date matches earliest NAV date.
"""
import asyncio
from sqlalchemy import select, func
from backend.db.session import AsyncSessionLocal
from backend.db.models import Scheme, NAVRecord
from loguru import logger


async def verify_sample_schemes():
    """Verify inception_date matches earliest NAV date for sample schemes."""
    async with AsyncSessionLocal() as session:
        # Get 10 random schemes with inception_date
        result = await session.execute(
            select(Scheme)
            .where(Scheme.inception_date.isnot(None))
            .limit(10)
        )
        sample_schemes = result.scalars().all()
        
        logger.info(f"Verifying {len(sample_schemes)} sample schemes...")
        
        all_correct = True
        
        for scheme in sample_schemes:
            # Get earliest NAV date for this scheme
            earliest_nav_query = select(func.min(NAVRecord.nav_date)).where(
                NAVRecord.scheme_id == scheme.id
            )
            result = await session.execute(earliest_nav_query)
            earliest_nav_date = result.scalar()
            
            if scheme.inception_date == earliest_nav_date:
                logger.success(
                    f"✓ {scheme.scheme_code}: inception_date={scheme.inception_date} "
                    f"matches earliest NAV={earliest_nav_date}"
                )
            else:
                logger.error(
                    f"✗ {scheme.scheme_code}: inception_date={scheme.inception_date} "
                    f"does NOT match earliest NAV={earliest_nav_date}"
                )
                all_correct = False
        
        if all_correct:
            logger.success("\n✓ All sample schemes verified successfully!")
        else:
            logger.error("\n✗ Some schemes have mismatched inception dates!")
        
        return all_correct


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("Inception Date Verification")
    logger.info("=" * 60)
    
    result = asyncio.run(verify_sample_schemes())
    exit(0 if result else 1)
