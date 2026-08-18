"""
Data migration script to populate inception_date for all schemes.

For each scheme, queries the earliest NAV date from the nav_record table
and updates scheme.inception_date with this value.

Requirements: 3.1
"""
import asyncio
from sqlalchemy import text, select, func
from sqlalchemy.ext.asyncio import AsyncSession
from backend.db.session import AsyncSessionLocal, engine
from backend.db.models import Scheme, NAVRecord
from loguru import logger


async def populate_inception_dates():
    """
    Populate inception_date for all schemes based on earliest NAV date.
    
    For each scheme:
    1. Query the earliest nav_date from nav_record table
    2. Update scheme.inception_date with this date
    3. Log schemes where inception_date cannot be determined
    """
    async with AsyncSessionLocal() as session:
        # Check if inception_date column exists
        async with engine.connect() as conn:
            result = await conn.execute(text(
                "SELECT COUNT(*) FROM pragma_table_info('scheme') WHERE name='inception_date'"
            ))
            column_exists = result.scalar()
            
            if not column_exists:
                logger.error("❌ inception_date column does not exist. Please run alembic migration first.")
                logger.info("Run: alembic upgrade head")
                return
        
        logger.info("Starting inception_date population for all schemes...")
        
        # Get all schemes
        result = await session.execute(select(Scheme))
        schemes = result.scalars().all()
        total_schemes = len(schemes)
        
        updated_count = 0
        skipped_count = 0
        no_data_count = 0
        
        logger.info(f"Processing {total_schemes} schemes...")
        
        for scheme in schemes:
            # Query earliest NAV date for this scheme
            earliest_nav_query = select(func.min(NAVRecord.nav_date)).where(
                NAVRecord.scheme_id == scheme.id
            )
            result = await session.execute(earliest_nav_query)
            earliest_date = result.scalar()
            
            if earliest_date is None:
                # No NAV data for this scheme
                logger.warning(
                    f"No NAV data found for scheme_code={scheme.scheme_code}, "
                    f"scheme_name='{scheme.scheme_name[:50]}'. Inception date cannot be determined."
                )
                no_data_count += 1
                continue
            
            # Update scheme with inception date
            scheme.inception_date = earliest_date
            updated_count += 1
            
            if updated_count % 100 == 0:
                logger.info(f"Progress: {updated_count}/{total_schemes} schemes updated")
        
        # Commit all updates
        await session.commit()
        
        logger.success(
            f"✓ Inception date population complete!\n"
            f"  - Updated: {updated_count} schemes\n"
            f"  - No NAV data: {no_data_count} schemes\n"
            f"  - Total processed: {total_schemes} schemes"
        )
        
        # Log schemes without NAV data for reference
        if no_data_count > 0:
            logger.info(f"Run the following query to see schemes without NAV data:")
            logger.info("SELECT scheme_code, scheme_name FROM scheme WHERE inception_date IS NULL;")


async def verify_population():
    """Verify inception_date population by showing statistics."""
    async with AsyncSessionLocal() as session:
        # Count schemes with inception_date
        result = await session.execute(
            select(func.count(Scheme.id)).where(Scheme.inception_date.isnot(None))
        )
        with_inception = result.scalar()
        
        # Count schemes without inception_date
        result = await session.execute(
            select(func.count(Scheme.id)).where(Scheme.inception_date.is_(None))
        )
        without_inception = result.scalar()
        
        # Get earliest and latest inception dates
        result = await session.execute(
            select(func.min(Scheme.inception_date), func.max(Scheme.inception_date))
        )
        min_date, max_date = result.one()
        
        logger.info(
            f"Inception Date Statistics:\n"
            f"  - Schemes with inception_date: {with_inception}\n"
            f"  - Schemes without inception_date: {without_inception}\n"
            f"  - Earliest inception date: {min_date}\n"
            f"  - Latest inception date: {max_date}"
        )


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("Data Migration: Populate Inception Dates")
    logger.info("=" * 60)
    
    asyncio.run(populate_inception_dates())
    
    logger.info("\n" + "=" * 60)
    logger.info("Verification")
    logger.info("=" * 60)
    
    asyncio.run(verify_population())

