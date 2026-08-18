"""Quick DB status check"""
import asyncio
from backend.db.session import AsyncSessionLocal
from sqlalchemy import text

async def check():
    async with AsyncSessionLocal() as session:
        schemes = await session.scalar(text('SELECT COUNT(*) FROM scheme'))
        features = await session.scalar(text('SELECT COUNT(*) FROM fund_features'))
        scores = await session.scalar(text('SELECT COUNT(*) FROM fund_score'))
        nav = await session.scalar(text('SELECT COUNT(*) FROM nav_record'))
        
        print(f'Schemes: {schemes}')
        print(f'NAV Records: {nav}')
        print(f'Features: {features}')
        print(f'Scores: {scores}')
        
        if scores and scores > 0:
            # Check sample scores
            result = await session.execute(text(
                'SELECT conviction, COUNT(*) FROM fund_score GROUP BY conviction'
            ))
            print('\nConviction breakdown:')
            for row in result:
                print(f'  {row[0]}: {row[1]}')
            
            # Check score dates
            dates = await session.execute(text(
                'SELECT DISTINCT score_date FROM fund_score ORDER BY score_date DESC LIMIT 5'
            ))
            print('\nScore dates:')
            for row in dates:
                print(f'  {row[0]}')

asyncio.run(check())
