"""Build features + scores for all eligible schemes"""
import asyncio
import sqlite3
from datetime import date
from backend.features.feature_builder import FeatureBuilder
from backend.scoring.rule_based import RuleBasedScorer

async def main():
    today = date.today()
    
    # Get eligible schemes (30+ NAV rows)
    conn = sqlite3.connect("mfscope.db")
    cur = conn.cursor()
    cur.execute("""
        SELECT scheme_id, COUNT(*) c
        FROM nav_record
        GROUP BY scheme_id
        HAVING c >= 30
    """)
    eligible = [r[0] for r in cur.fetchall()]
    conn.close()
    
    print(f"Building features for {len(eligible)} schemes...")
    
    builder = FeatureBuilder()
    built = 0
    failed = 0
    
    for i, sid in enumerate(eligible, 1):
        if i % 500 == 0:
            print(f"  [{i}/{len(eligible)}] built={built} failed={failed}")
        try:
            feat = await builder.build_features(sid, as_of=today)
            if feat:
                await builder.persist_features(feat)
                built += 1
            else:
                failed += 1
        except Exception as e:
            failed += 1
    
    print(f"\n✓ Features: {built} built, {failed} failed")
    
    print(f"\nRunning scorer...")
    scorer = RuleBasedScorer()
    n = await scorer.score_all(as_of=today)
    print(f"✓ Scores: {n} written")
    
    # Show top 5
    conn = sqlite3.connect("mfscope.db")
    cur = conn.cursor()
    cur.execute("""
        SELECT s.scheme_name, s.category, fs.composite_score, fs.conviction
        FROM fund_score fs
        JOIN scheme s ON s.id = fs.scheme_id
        WHERE fs.score_date = ?
        ORDER BY fs.composite_score DESC
        LIMIT 5
    """, (today,))
    print(f"\nTop 5 funds:")
    for name, cat, score, conv in cur.fetchall():
        print(f"  {score:5.1f}  {conv:12s}  {cat[:20]:20s}  {name[:40]}")
    conn.close()

asyncio.run(main())
