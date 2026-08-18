"""Test API to find 500 error"""
import asyncio
import traceback
from backend.db.session import AsyncSessionLocal
from sqlalchemy import text

async def main():
    try:
        print("Testing database connection...")
        async with AsyncSessionLocal() as session:
            # Check scores
            result = await session.execute(text('SELECT COUNT(*) FROM fund_score'))
            score_count = result.scalar()
            print(f'✓ Scores in DB: {score_count}')
            
            # Check if risk columns exist
            try:
                result = await session.execute(text('SELECT risk_score, risk_level FROM fund_score LIMIT 1'))
                print(f'✓ Risk columns exist')
            except Exception as e:
                print(f'✗ Risk columns missing: {e}')
                print('Run: python add_risk_columns.py')
        
        # Test imports
        print("\nTesting API imports...")
        from backend.api.main import app
        print("✓ API imports successful")
        
        # Test endpoint manually
        print("\nTesting list_funds endpoint...")
        from backend.api.main import list_funds, get_session
        async with AsyncSessionLocal() as session:
            try:
                result = await list_funds(
                    category=None,
                    conviction=None,
                    search=None,
                    sort_by="composite_score",
                    sort_dir="desc",
                    page=1,
                    page_size=10,
                    db=session
                )
                print(f'✓ list_funds works! Total: {result.total}, Items: {len(result.items)}')
            except Exception as e:
                print(f'✗ list_funds error:')
                print(traceback.format_exc())
        
    except Exception as e:
        print(f'Error: {e}')
        print(traceback.format_exc())

if __name__ == "__main__":
    asyncio.run(main())
