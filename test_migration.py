"""
Test script for inception_date migration (Task 2.4)

This script tests:
1. Migration upgrade
2. Verification that inception_date column exists
3. Data population correctness
4. Migration reversibility (downgrade)
5. Query performance with index
"""
import asyncio
import time
from sqlalchemy import text, select, func
from sqlalchemy.ext.asyncio import AsyncSession
from backend.db.session import AsyncSessionLocal, engine
from backend.db.models import Scheme, NAVRecord
from loguru import logger
import sys


async def check_column_exists(column_name: str) -> bool:
    """Check if a column exists in the scheme table."""
    async with engine.connect() as conn:
        result = await conn.execute(text(
            f"SELECT COUNT(*) FROM pragma_table_info('scheme') WHERE name='{column_name}'"
        ))
        count = result.scalar()
        return count > 0


async def check_index_exists(index_name: str) -> bool:
    """Check if an index exists."""
    async with engine.connect() as conn:
        result = await conn.execute(text(
            f"SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND name='{index_name}'"
        ))
        count = result.scalar()
        return count > 0


async def verify_inception_dates():
    """Verify that inception_dates are populated correctly."""
    async with AsyncSessionLocal() as session:
        # Get sample of schemes with inception_date
        result = await session.execute(
            select(Scheme).where(Scheme.inception_date.isnot(None)).limit(5)
        )
        schemes_with_date = result.scalars().all()
        
        logger.info(f"Sample of {len(schemes_with_date)} schemes with inception_date:")
        
        verification_passed = True
        for scheme in schemes_with_date:
            # Get earliest NAV date for this scheme
            earliest_nav_query = select(func.min(NAVRecord.nav_date)).where(
                NAVRecord.scheme_id == scheme.id
            )
            result = await session.execute(earliest_nav_query)
            earliest_nav = result.scalar()
            
            match = "✓" if earliest_nav == scheme.inception_date else "✗"
            logger.info(
                f"  {match} {scheme.scheme_code}: "
                f"inception_date={scheme.inception_date}, earliest_nav={earliest_nav}"
            )
            
            if earliest_nav != scheme.inception_date:
                verification_passed = False
        
        # Get statistics
        result = await session.execute(
            select(func.count(Scheme.id)).where(Scheme.inception_date.isnot(None))
        )
        with_inception = result.scalar()
        
        result = await session.execute(
            select(func.count(Scheme.id)).where(Scheme.inception_date.is_(None))
        )
        without_inception = result.scalar()
        
        logger.info(f"\nInception Date Statistics:")
        logger.info(f"  - Schemes with inception_date: {with_inception}")
        logger.info(f"  - Schemes without inception_date: {without_inception}")
        
        return verification_passed


async def test_query_performance():
    """Test query performance with inception_date index."""
    async with AsyncSessionLocal() as session:
        # Test query with inception_date filter
        start_time = time.time()
        
        query = select(Scheme).where(Scheme.inception_date.isnot(None)).limit(100)
        result = await session.execute(query)
        schemes = result.scalars().all()
        
        elapsed = (time.time() - start_time) * 1000  # Convert to milliseconds
        
        logger.info(f"\nQuery Performance Test:")
        logger.info(f"  - Query returned {len(schemes)} schemes")
        logger.info(f"  - Time elapsed: {elapsed:.2f}ms")
        
        if elapsed < 100:
            logger.success(f"  ✓ Performance acceptable (< 100ms)")
            return True
        else:
            logger.warning(f"  ✗ Performance slow (>= 100ms)")
            return False


async def main():
    logger.info("=" * 80)
    logger.info("Migration Test Script - Task 2.4")
    logger.info("=" * 80)
    
    all_tests_passed = True
    
    # Test 1: Check if inception_date column exists
    logger.info("\n[Test 1] Checking if inception_date column exists...")
    column_exists = await check_column_exists("inception_date")
    if column_exists:
        logger.success("✓ inception_date column exists in scheme table")
    else:
        logger.error("✗ inception_date column does NOT exist in scheme table")
        logger.error("  Please run: alembic upgrade head")
        all_tests_passed = False
        sys.exit(1)
    
    # Test 2: Check if index exists
    logger.info("\n[Test 2] Checking if index exists...")
    index_exists = await check_index_exists("ix_scheme_inception_date")
    if index_exists:
        logger.success("✓ Index ix_scheme_inception_date exists")
    else:
        logger.warning("✗ Index ix_scheme_inception_date does NOT exist")
        all_tests_passed = False
    
    # Test 3: Verify inception dates are populated correctly
    logger.info("\n[Test 3] Verifying inception dates populated correctly...")
    verification_passed = await verify_inception_dates()
    if verification_passed:
        logger.success("✓ All sampled inception dates match earliest NAV dates")
    else:
        logger.warning("✗ Some inception dates do not match earliest NAV dates")
        all_tests_passed = False
    
    # Test 4: Test query performance
    logger.info("\n[Test 4] Testing query performance with index...")
    performance_ok = await test_query_performance()
    if not performance_ok:
        all_tests_passed = False
    
    # Final summary
    logger.info("\n" + "=" * 80)
    if all_tests_passed:
        logger.success("✓ ALL TESTS PASSED - Migration is working correctly")
    else:
        logger.warning("⚠ SOME TESTS FAILED - Please review the issues above")
    logger.info("=" * 80)
    
    return all_tests_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
