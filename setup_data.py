"""
setup_data.py — Complete data setup for MFScope

Fixes categories, backfills 2yr NAV history concurrently, builds features, runs scorer.
Run: .venv\Scripts\python.exe setup_data.py
"""

import asyncio
import re
import sqlite3
from datetime import date, datetime, timedelta

import httpx

DB = "mfscope.db"
MFAPI = "https://api.mfapi.in/mf"
CUTOFF = (date.today() - timedelta(days=730)).isoformat()

# ── Category inference ────────────────────────────────────────────────────────
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
    # mfapi returns DD-MM-YYYY, try that first
    for fmt in ("%d-%m-%Y", "%d-%b-%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try: return datetime.strptime(s.strip(), fmt).date().isoformat()
        except: pass
    return None


# ── Step 1: Fix categories ────────────────────────────────────────────────────
def step1_fix_categories():
    print("\n[1/4] Fixing category labels...")
    conn = sqlite3.connect(DB)
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


# ── Step 2: Backfill NAV history (concurrent) ─────────────────────────────────
async def fetch_and_insert(client, sid, code, cutoff, sem):
    """Fetch NAV history for one scheme and insert into DB"""
    async with sem:
        try:
            r = await client.get(f"{MFAPI}/{code}")
            if r.status_code != 200:
                return 0
            data = r.json().get("data", [])
            
            conn = sqlite3.connect(DB)
            cur = conn.cursor()
            inserted = 0
            
            for entry in data:
                d = parse_date(entry.get("date", ""))
                if not d or d < cutoff:
                    continue
                try:
                    nav = float(entry["nav"])
                except (ValueError, KeyError):
                    continue
                cur.execute(
                    "INSERT OR IGNORE INTO nav_record (scheme_id, nav_date, nav) VALUES (?,?,?)",
                    (sid, d, nav)
                )
                inserted += cur.rowcount
            
            conn.commit()
            conn.close()
            return inserted
        except:
            return 0


async def step2_backfill_nav():
    print("\n[2/4] Backfilling 2-year NAV history from mfapi.in...")
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    # Target: schemes with current NAV, not 'Other' category
    cur.execute("""
        SELECT s.id, s.scheme_code
        FROM scheme s
        INNER JOIN nav_record n ON n.scheme_id = s.id
        WHERE s.category != 'Other'
        GROUP BY s.id
    """)
    targets = cur.fetchall()
    conn.close()
    
    print(f"  Targeting {len(targets)} active non-Other schemes")
    print(f"  Running with 20 concurrent workers...")

    sem = asyncio.Semaphore(20)
    total_inserted = 0
    
    async with httpx.AsyncClient(
        follow_redirects=True, timeout=30, verify=False,
        headers={"User-Agent": "MFScope/0.1"}
    ) as client:
        tasks = [fetch_and_insert(client, sid, code, CUTOFF, sem) for sid, code in targets]
        
        # Process in chunks to show progress
        chunk_size = 500
        for i in range(0, len(tasks), chunk_size):
            chunk = tasks[i:i+chunk_size]
            results = await asyncio.gather(*chunk)
            total_inserted += sum(results)
            print(f"  Progress: {min(i+chunk_size, len(tasks))}/{len(targets)} schemes processed, {total_inserted:,} NAV rows added")

    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM nav_record")
    print(f"  Done. Total NAV rows in DB: {cur.fetchone()[0]:,}")
    conn.close()


# ── Step 3 & 4: Features + Scores ────────────────────────────────────────────
async def step3_features_and_scores():
    today = date.today()

    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("""
        SELECT scheme_id, COUNT(*) c
        FROM nav_record
        GROUP BY scheme_id
        HAVING c >= 30
    """)
    eligible = [r[0] for r in cur.fetchall()]
    conn.close()

    print(f"\n[3/4] Building features for {len(eligible)} schemes with 30+ NAV rows...")

    from backend.features.feature_builder import FeatureBuilder
    builder = FeatureBuilder()

    built = 0
    for i, sid in enumerate(eligible, 1):
        if i % 500 == 0:
            print(f"  Progress: {i}/{len(eligible)} schemes processed, {built} features built")
        try:
            feat = await builder.build_features(sid, as_of=today)
            if feat:
                await builder.persist_features(feat)
                built += 1
        except:
            pass

    print(f"  Features built: {built}")

    print("\n[4/4] Running scorer...")
    from backend.scoring.rule_based import RuleBasedScorer
    scorer = RuleBasedScorer()
    n = await scorer.score_all(as_of=today)
    print(f"  Scores written: {n}")


# ── Summary ───────────────────────────────────────────────────────────────────
def summary():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM scheme");      s = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM nav_record");  n = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM fund_features"); f = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM fund_score");  sc = cur.fetchone()[0]
    
    print(f"\n{'='*70}")
    print(f"  MFScope Data Setup Complete")
    print(f"{'='*70}")
    print(f"  Schemes        : {s:,}")
    print(f"  NAV rows       : {n:,}")
    print(f"  Feature rows   : {f:,}")
    print(f"  Score rows     : {sc:,}")
    
    if sc > 0:
        cur.execute("""
            SELECT s.scheme_name, s.category, fs.composite_score, fs.conviction
            FROM fund_score fs JOIN scheme s ON s.id=fs.scheme_id
            ORDER BY fs.composite_score DESC LIMIT 5
        """)
        print(f"\n  Top 5 Scored Funds:")
        for r in cur.fetchall():
            print(f"    {r[2]:5.1f}  {r[3]:12s}  {r[1][:25]:25s}  {r[0][:35]}")
        
        print(f"\n  ✓ Data pipeline complete!")
        print(f"  ✓ Run start.bat to launch the dashboard")
        print(f"  ✓ Dashboard will now show live scores, returns, and conviction levels")
    else:
        print(f"\n  ⚠ No scores generated - check that NAV history was backfilled")
    
    print(f"{'='*70}\n")
    conn.close()


async def main():
    step1_fix_categories()
    await step2_backfill_nav()
    await step3_features_and_scores()
    summary()

if __name__ == "__main__":
    asyncio.run(main())
