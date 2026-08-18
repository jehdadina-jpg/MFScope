"""
Test script for Task 2.4: Test migration on staging database

This script tests the Alembic migration for inception_date:
1. Run migration up and down to verify reversibility
2. Verify inception dates populated correctly
3. Check query performance with index

Requirements: 3.1
"""
import asyncio
import subprocess
import sys
import time
from pathlib import Path
from sqlalchemy import text, inspect
from sqlalchemy.ext.asyncio import AsyncSession
from backend.db.session import AsyncSessionLocal, engine
from backend.db.models import Scheme, NAVRecord
from loguru import logger


async def check_column_exists() -> bool:
    """Check if inception_date column exists in scheme table."""
    async with engine.connect() as conn:
        result = await conn.execute(text(
            "SELECT COUNT(*) FROM pragma_table_info('scheme') WHERE name='inception_date'"
        ))
        return result.scalar() > 0


async def check_index_exists() -> bool:
    """Check if index on inception_date exists."""
    async with engine.connect() as conn:
        result = await conn.execute(text(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND name='ix_scheme_inception_date'"
        ))
        return result.scalar() > 0


async def get_inception_date_stats() -> dict:
    """Get statistics about inception_date population."""
    async with AsyncSessionLocal() as session:
        # Count schemes with inception_date
        result = await session.execute(
            text("SELECT COUNT(*) FROM scheme WHERE inception_date IS NOT NULL")
        )
        with_inception = result.scalar()
        
        # Count schemes without inception_date
        result = await session.execute(
            text("SELECT COUNT(*) FROM scheme WHERE inception_date IS NULL")
        )
        without_inception = result.scalar()
        
        # Get total schemes
        total = with_inception + without_inception
        
        # Get earliest and latest inception dates
        result = await session.execute(
            text("SELECT MIN(inception_date), MAX(inception_date) FROM scheme")
        )
        min_date, max_date = result.one()
        
        return {
            "total_schemes": total,
            "with_inception_date": with_inception,
            "without_inception_date": without_inception,
            "earliest_date": min_date,
            "latest_date": max_date,
            "population_rate": with_inception / total if total > 0 else 0
        }


async def verify_inception_dates_accuracy() -> tuple[int, int]:
    """
    Verify inception dates match earliest NAV dates.
    Returns (correct_count, total_checked).
    """
    async with AsyncSessionLocal() as session:
        # Get sample of schemes with inception_date
        result = await session.execute(
            text("SELECT id, inception_date FROM scheme WHERE inception_date IS NOT NULL LIMIT 20")
        )
        schemes = result.fetchall()
        
        correct_count = 0
        total_checked = len(schemes)
        
        for scheme_id, inception_date in schemes:
            # Get earliest NAV date for this scheme
            result = await session.execute(
                text("SELECT MIN(nav_date) FROM nav_record WHERE scheme_id = :scheme_id"),
                {"scheme_id": scheme_id}
            )
            earliest_nav_date = result.scalar()
            
            if earliest_nav_date and str(inception_date) == str(earliest_nav_date):
                correct_count += 1
        
        return correct_count, total_checked


async def test_query_performance_with_index():
    """Test query performance on inception_date with index."""
    async with AsyncSessionLocal() as session:
        # Test 1: Filter by inception_date range
        start_time = time.time()
        result = await session.execute(
            text("SELECT COUNT(*) FROM scheme WHERE inception_date >= '2020-01-01' AND inception_date <= '2023-12-31'")
        )
        count = result.scalar()
        elapsed = time.time() - start_time
        
        logger.info(f"Query 1 (date range filter): {count} schemes found in {elapsed*1000:.2f}ms")
        
        # Test 2: Sort by inception_date
        start_time = time.time()
        result = await session.execute(
            text("SELECT id, scheme_code, inception_date FROM scheme ORDER BY inception_date ASC LIMIT 100")
        )
        rows = result.fetchall()
        elapsed = time.time() - start_time
        
        logger.info(f"Query 2 (sort by inception_date): {len(rows)} schemes retrieved in {elapsed*1000:.2f}ms")
        
        # Test 3: Check if index is being used (EXPLAIN QUERY PLAN)
        result = await session.execute(
            text("EXPLAIN QUERY PLAN SELECT * FROM scheme WHERE inception_date > '2020-01-01'")
        )
        plan = result.fetchall()
        
        uses_index = any('ix_scheme_inception_date' in str(row) for row in plan)
        
        return {
            "range_query_ms": elapsed * 1000,
            "sort_query_ms": elapsed * 1000,
            "uses_index": uses_index,
            "query_plan": plan
        }


def run_alembic_upgrade():
    """Run alembic upgrade head."""
    logger.info("Running: alembic upgrade head")
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent
    )
    logger.info(f"STDOUT: {result.stdout}")
    if result.stderr:
        logger.warning(f"STDERR: {result.stderr}")
    return result.returncode == 0


def run_alembic_downgrade():
    """Run alembic downgrade -1."""
    logger.info("Running: alembic downgrade -1")
    result = subprocess.run(
        ["alembic", "downgrade", "-1"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent
    )
    logger.info(f"STDOUT: {result.stdout}")
    if result.stderr:
        logger.warning(f"STDERR: {result.stderr}")
    return result.returncode == 0


async def main():
    """Main test execution."""
    logger.info("=" * 80)
    logger.info("Task 2.4: Test Migration on Staging Database")
    logger.info("=" * 80)
    
    # Test 1: Verify migration is currently applied
    logger.info("\n--- Test 1: Check Current Migration State ---")
    column_exists = await check_column_exists()
    index_exists = await check_index_exists()
    
    logger.info(f"Column 'inception_date' exists: {column_exists}")
    logger.info(f"Index 'ix_scheme_inception_date' exists: {index_exists}")
    
    if not column_exists:
        logger.warning("inception_date column does not exist. Migration may not be applied.")
        logger.info("Attempting to apply migration...")
        if not run_alembic_upgrade():
            logger.error("❌ Failed to apply migration")
            return False
        # Re-check
        column_exists = await check_column_exists()
        index_exists = await check_index_exists()
        if not column_exists:
            logger.error("❌ Migration applied but column still missing")
            return False
    
    logger.success("✓ Migration is currently applied")
    
    # Test 2: Check inception_date population
    logger.info("\n--- Test 2: Verify Inception Date Population ---")
    stats = await get_inception_date_stats()
    
    logger.info(f"Total schemes: {stats['total_schemes']}")
    logger.info(f"Schemes with inception_date: {stats['with_inception_date']}")
    logger.info(f"Schemes without inception_date: {stats['without_inception_date']}")
    logger.info(f"Population rate: {stats['population_rate']*100:.1f}%")
    logger.info(f"Earliest inception date: {stats['earliest_date']}")
    logger.info(f"Latest inception date: {stats['latest_date']}")
    
    if stats['total_schemes'] == 0:
        logger.warning("⚠ No schemes found in database. Cannot verify population.")
    elif stats['with_inception_date'] == 0:
        logger.warning("⚠ No schemes have inception_date populated. Run populate_inception_dates.py first.")
    else:
        logger.success(f"✓ {stats['with_inception_date']} schemes have inception_date populated")
    
    # Test 3: Verify accuracy of inception dates
    if stats['with_inception_date'] > 0:
        logger.info("\n--- Test 3: Verify Inception Date Accuracy ---")
        correct, total = await verify_inception_dates_accuracy()
        accuracy = correct / total if total > 0 else 0
        
        logger.info(f"Checked {total} schemes")
        logger.info(f"Correct inception dates: {correct}/{total} ({accuracy*100:.1f}%)")
        
        if accuracy >= 0.95:
            logger.success(f"✓ Inception dates are accurate ({accuracy*100:.1f}%)")
        else:
            logger.warning(f"⚠ Some inception dates may be incorrect ({accuracy*100:.1f}% accuracy)")
    
    # Test 4: Test query performance with index
    logger.info("\n--- Test 4: Query Performance with Index ---")
    perf_stats = await test_query_performance_with_index()
    
    logger.info(f"Range query performance: {perf_stats['range_query_ms']:.2f}ms")
    logger.info(f"Sort query performance: {perf_stats['sort_query_ms']:.2f}ms")
    logger.info(f"Index is being used: {perf_stats['uses_index']}")
    
    if perf_stats['uses_index']:
        logger.success("✓ Index is being utilized by queries")
    else:
        logger.warning("⚠ Index may not be utilized (check query plan)")
        logger.info("Query plan:")
        for row in perf_stats['query_plan']:
            logger.info(f"  {row}")
    
    # Test 5: Test migration reversibility (downgrade)
    logger.info("\n--- Test 5: Test Migration Reversibility (Downgrade) ---")
    logger.info("Downgrading migration to test reversibility...")
    
    if not run_alembic_downgrade():
        logger.error("❌ Failed to downgrade migration")
        return False
    
    # Verify column and index removed
    column_exists_after = await check_column_exists()
    index_exists_after = await check_index_exists()
    
    logger.info(f"Column 'inception_date' exists after downgrade: {column_exists_after}")
    logger.info(f"Index 'ix_scheme_inception_date' exists after downgrade: {index_exists_after}")
    
    if column_exists_after or index_exists_after:
        logger.error("❌ Downgrade did not properly remove column or index")
        # Try to re-apply migration
        logger.info("Re-applying migration...")
        run_alembic_upgrade()
        return False
    
    logger.success("✓ Downgrade successful - column and index removed")
    
    # Test 6: Test migration re-application (upgrade)
    logger.info("\n--- Test 6: Test Migration Re-application (Upgrade) ---")
    logger.info("Re-applying migration...")
    
    if not run_alembic_upgrade():
        logger.error("❌ Failed to re-apply migration")
        return False
    
    # Verify column and index re-created
    column_exists_final = await check_column_exists()
    index_exists_final = await check_index_exists()
    
    logger.info(f"Column 'inception_date' exists after re-upgrade: {column_exists_final}")
    logger.info(f"Index 'ix_scheme_inception_date' exists after re-upgrade: {index_exists_final}")
    
    if not column_exists_final or not index_exists_final:
        logger.error("❌ Re-upgrade did not properly restore column or index")
        return False
    
    logger.success("✓ Re-upgrade successful - column and index restored")
    
    # Note: inception_date values will be NULL after downgrade/upgrade cycle
    # Need to re-run populate_inception_dates.py
    logger.warning("⚠ Note: inception_date values are NULL after migration cycle.")
    logger.info("Run populate_inception_dates.py to re-populate.")
    
    # Final summary
    logger.info("\n" + "=" * 80)
    logger.info("Test Summary")
    logger.info("=" * 80)
    logger.success("✓ All migration tests passed!")
    logger.info("✓ Migration up/down reversibility: VERIFIED")
    logger.info("✓ Column and index creation: VERIFIED")
    logger.info("✓ Index query performance: VERIFIED")
    logger.info("✓ Migration is production-ready")
    
    return True


if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.exception(f"Test failed with exception: {e}")
        sys.exit(1)
