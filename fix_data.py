"""
fix_data.py — run once to populate real data:
  1. Fix category labels
  2. Backfill 3 years of NAV history for active Direct Growth funds
  3. Build features
  4. Score all
"""
import asyncio, re, sys, httpx
from datetime import date, datetime, timedelta
from sqlalchemy import text
from backend.db.session import engine

_RULES = [
    (r"defense|defence",                    "Defense"),
    (r"\bpsu\b",                            "PSU"),
    (r"banking|financial service",          "Banking & Financial Services"),
    (r"pharma|health",                      "Pharma & Healthcare"),
    (r"\bit\b|technology",                  "IT/Technology"),
    (r"infra",                              "Infrastructure"),
    (r"consumption|fmcg|consumer",          "Consumption"),
    (r"energy|power|oil",                   "Energy"),
    (r"nifty.?next.?50",                    "Index - Nifty Next 50"),
    (r"nifty.?50\b|nifty50",               "Index - Nifty 50"),
    (r"sensex",                             "Index - Sensex"),
    (r"index|etf",                          "Index Other"),
    (r"large.?&.?mid|large.?mid",           "Large & Mid Cap"),
    (r"large.?cap",                         "Large Cap"),
    (r"mid.?cap",                           "Mid Cap"),
    (r"small.?cap",                         "Small Cap"),
    (r"flexi.?cap",                         "Flexi Cap"),
    (r"multi.?cap",                         "Multi Cap"),
    (r"elss|tax.?sav",                      "ELSS"),
    (r"overnight",                          "Overnight"),
    (r"liquid",                             "Liquid"),
    (r"short.?dur",                         "Short Duration"),
    (r"corporate.?bond",                    "Corporate Bond"),
    (r"gilt",                               "Gilt"),
    (r"aggressive.?hybrid",                 "Aggressive Hybrid"),
    (r"balanced.?advantage|dynamic.?asset", "Balanced Advantage"),
    (r"multi.?asset",                       "Multi-Asset"),
    (r"international|global|overseas|fof",  "International/FoF"),
    (r"sectoral|thematic",                  "Sectoral/Thematic Other"),
    (r"hybrid",                             "Multi-Asset"),
    (r"debt|bond|income|credit",            "Debt Other"),
]
_COMPILED = [(re.compile(p, re.I), c) for p, c in _RULES]

def infer_cat(name: str) -> str:
    for pat, cat in _COMPILED:
        if pat.search(name): return cat
    return "Other"

def parse_date(s: str):
    for fmt in ("%d-%b-%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try: return datetime.strptime(s.strip(), fmt).date()
        except: pass
    return None


async def fix_categories():
    print("[1/4] Fixing category labels...")
    import sqlite3
    conn = sqlite3.connect("mfscope.db")
    cur = conn.cursor()
    cur.execute("SELECT id, scheme_name FROM scheme")
    rows = cur.fetchall()
    updated = 0
    for sid, name in rows:
        cat = infer_cat(name)
        cur.execute("UPDATE scheme SET category=? WHERE id=?", (cat, sid))
        updated += 1
    conn.commit()
    cur.execute("SELECT category, COUNT(*) c FROM scheme GROUP BY category ORDER BY c DESC LIMIT 10")
    print(f"  Updated {updated} schemes. Top categories:")
    for r in cur.fetchall():
        print(f"    {r[1]:6d}  {r[0]}")
    conn.close()


async def backfill_nav():
    print("\n[2/4] Backfilling 3-year NAV history...")
    import sqlite3
    conn = sqlite3.connect("mfscope.db")
    cur = conn.cursor()

    # Pick Direct Growth funds that have a recent NAV (active funds only)
    cur.execute("""
        SELECT s.id, s.scheme_code, s.scheme_name
        FROM scheme s
        JOIN nav_record n ON n.scheme_id = s.id
        WHERE (UPPER(s.scheme_name) LIKE '%DIRECT%' OR UPPER(s.scheme_name) LIKE '%GROWTH%')
          AND s.category != 'Other'
        GROUP BY s.id
        ORDER BY s.scheme_name
        LIMIT 2000
    """)
    targets = cur.fetchall()
    print(f"  Backfilling {len(targets)} Direct/Growth funds...")

    cutoff = (date.today() - timedelta(days=3*365)).isoformat()
    done = 0
    errors = 0

    async with httpx.AsyncClient(follow_redirects=True, timeout=15, verify=False) as client:
        for i, (sid, code, name) in enumerate(targets, 1):
            if i % 100 == 0:
                print(f"  {i}/{len(targets)} — {done} funds with new rows")
            try:
                r = await client.get(
                    f"https://api.mfapi.in/mf/{code}",
                    headers={"User-Agent": "MFScope/0.1"}
                )
                if r.status_code != 200:
                    errors += 1; continue
                data = r.json().get("data", [])
                inserted = 0
                for entry in data:
                    d = parse_date(entry.get("date", ""))
                    if not d or d.isoformat() < cutoff: continue
                    try: nav = float(entry["nav"])
                    except: continue
                    cur.execute(
                        "INSERT OR IGNORE INTO nav_record (scheme_id, nav_date, nav) VALUES (?,?,?)",
                        (sid, d.isoformat(), nav)
                    )
                    inserted += cur.rowcount
                if inserted > 0:
                    conn.commit()
                    done += 1
            except Exception as e:
                errors += 1

    conn.commit()
    cur.execute("SELECT COUNT(*) FROM nav_record")
    print(f"  Done. Total NAV rows now: {cur.fetchone()[0]}  errors: {errors}")
    conn.close()


async def build_features_and_scores():
    today = date.today()
    import sqlite3

    conn = sqlite3.connect("mfscope.db")
    cur = conn.cursor()
    # Only schemes with 30+ NAV rows
    cur.execute("""
        SELECT scheme_id, COUNT(*) c FROM nav_record
        GROUP BY scheme_id HAVING c >= 30
    """)
    eligible = [r[0] for r in cur.fetchall()]
    conn.close()
    print(f"\n[3/4] Building features for {len(eligible)} schemes with 30+ NAV rows...")

    from backend.features.feature_builder import FeatureBuilder
    builder = FeatureBuilder()

    built = 0
    for i, sid in enumerate(eligible, 1):
        if i % 100 == 0:
            print(f"  {i}/{len(eligible)} built={built}")
        try:
            features = await builder.build_features(sid, as_of=today)
            if features:
                await builder.persist_features(features)
                built += 1
        except Exception:
            pass
    print(f"  Features built: {built}")

    print("\n[4/4] Scoring...")
    from backend.scoring.rule_based import RuleBasedScorer
    scorer = RuleBasedScorer()
    n = await scorer.score_all(as_of=today)
    print(f"  Scores written: {n}")

    async with engine.connect() as conn2:
        sample = await conn2.execute(text("""
            SELECT s.scheme_name, s.category, fs.composite_score, fs.conviction
            FROM fund_score fs JOIN scheme s ON s.id=fs.scheme_id
            ORDER BY fs.composite_score DESC LIMIT 8
        """))
        print("\n  Top 8 by score:")
        for r in sample.all():
            print(f"    {r[2]:5.1f}  {r[3]:12s}  {r[1]:25s}  {r[0][:45]}")


async def main():
    await fix_categories()
    await backfill_nav()
    await build_features_and_scores()
    print("\nAll done! Restart the API to see live scores.")

if __name__ == "__main__":
    asyncio.run(main())
