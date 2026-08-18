import asyncio
import sqlite3
from datetime import date
from backend.features.feature_builder import FeatureBuilder

async def test():
    # Get one scheme with 30+ NAV rows
    conn = sqlite3.connect("mfscope.db")
    cur = conn.cursor()
    cur.execute("""
        SELECT scheme_id, COUNT(*) c
        FROM nav_record
        GROUP BY scheme_id
        HAVING c >= 30
        LIMIT 1
    """)
    sid = cur.fetchone()[0]
    conn.close()
    
    print(f"Testing feature build for scheme_id={sid}")
    
    builder = FeatureBuilder()
    try:
        feat = await builder.build_features(sid, as_of=date.today())
        if feat:
            print(f"✓ Features built successfully")
            print(f"  return_1y: {feat.get('return_1y')}")
            print(f"  sharpe_1y: {feat.get('sharpe_1y')}")
            print(f"  expense_ratio: {feat.get('expense_ratio')}")
            await builder.persist_features(feat)
            print(f"✓ Features persisted to DB")
        else:
            print("✗ build_features returned None (insufficient data)")
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()

asyncio.run(test())
