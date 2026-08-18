"""Test API scores endpoint"""
import asyncio
from backend.db.session import AsyncSessionLocal
from backend.api.main import list_funds

async def test():
    async with AsyncSessionLocal() as session:
        result = await list_funds(
            category=None, 
            conviction=None, 
            search=None, 
            sort_by='composite_score', 
            sort_dir='desc', 
            page=1, 
            page_size=5, 
            db=session
        )
        
        print(f'Total funds: {result.total}')
        print(f'Funds returned: {len(result.items)}')
        print('\nTop 5 funds:')
        for item in result.items:
            print(f'  - {item.scheme_name[:60]:<60} Score={item.composite_score}, Conviction={item.conviction}')

asyncio.run(test())
