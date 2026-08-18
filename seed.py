"""
One-shot seed script. Run once after first install:
    .venv/Scripts/python.exe seed.py
"""
import asyncio, httpx, csv, io, sys
from datetime import datetime
from pathlib import Path

async def main():
    # 1. Create tables with correct schema
    from backend.db.session import init_db, engine
    from sqlalchemy import text

    print("[1/4] Creating tables...")
    await init_db()

    # Verify nav_record uses INTEGER pk
    async with engine.connect() as conn:
        r = await conn.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='nav_record'"))
        ddl = r.scalar()
        if ddl and "BIGINT" in ddl:
            print("ERROR: nav_record still has BIGINT PK — drop mfscope.db and re-run")
            sys.exit(1)
        print("   Table schema OK")

    # 2. Seed schemes from mfapi.in
    print("[2/4] Fetching scheme master from mfapi.in...")
    async with httpx.AsyncClient(follow_redirects=True, timeout=60, verify=False) as client:
        r = await client.get("https://api.mfapi.in/mf",
                             headers={"User-Agent": "MFScope/0.1"})
        schemes_raw = r.json()
    print(f"   Got {len(schemes_raw)} schemes")

    async with engine.begin() as conn:
        for item in schemes_raw:
            code = str(item.get("schemeCode","")).strip()
            name = (item.get("schemeName") or "").strip()
            if not code or not name: continue
            amc  = name.split()[0]
            cat  = _infer_category(name)
            await conn.execute(text("""
                INSERT OR IGNORE INTO scheme
                    (scheme_code,scheme_name,amc_name,category,plan_type,option_type,is_active)
                VALUES (:code,:name,:amc,:cat,:plan,:opt,1)
            """), {"code":code,"name":name,"amc":amc,"cat":cat,
                   "plan":_infer_plan(name),"opt":_infer_option(name)})

    async with engine.connect() as conn:
        n = await conn.scalar(text("SELECT COUNT(*) FROM scheme"))
    print(f"   {n} schemes in DB")

    # 3. Fetch today's NAV
    print("[3/4] Fetching today's NAV from AMFI...")
    async with httpx.AsyncClient(follow_redirects=True, timeout=60, verify=False) as client:
        r = await client.get("https://www.amfiindia.com/spages/NAVAll.txt",
                             headers={"User-Agent": "MFScope/0.1"})
    content = r.text
    print(f"   Downloaded {len(content):,} chars")

    # Build code->id
    async with engine.connect() as conn:
        res = await conn.execute(text("SELECT scheme_code, id FROM scheme"))
        code_to_id = {row[0]: row[1] for row in res.all()}

    records = _parse_nav(content)
    print(f"   Parsed {len(records)} NAV rows")

    # Insert missing schemes from NAVAll and then NAV rows
    async with engine.begin() as conn:
        for r in records:
            if r["code"] not in code_to_id:
                await conn.execute(text("""
                    INSERT OR IGNORE INTO scheme
                        (scheme_code,isin_growth,isin_div_reinvest,scheme_name,
                         amc_name,category,plan_type,option_type,is_active)
                    VALUES (:code,:ig,:id2,:name,:amc,:cat,:plan,:opt,1)
                """), {"code":r["code"],"ig":r["isin_g"],"id2":r["isin_d"],
                       "name":r["name"],"amc":r["name"].split()[0],
                       "cat":_infer_category(r["name"]),
                       "plan":_infer_plan(r["name"]),"opt":_infer_option(r["name"])})

    # Refresh code_to_id after new inserts
    async with engine.connect() as conn:
        res = await conn.execute(text("SELECT scheme_code, id FROM scheme"))
        code_to_id = {row[0]: row[1] for row in res.all()}

    inserted = 0
    async with engine.begin() as conn:
        for r in records:
            sid = code_to_id.get(r["code"])
            if sid is None: continue
            await conn.execute(text("""
                INSERT OR IGNORE INTO nav_record (scheme_id, nav_date, nav)
                VALUES (:sid, :d, :nav)
            """), {"sid": sid, "d": r["nav_date"], "nav": r["nav"]})
            inserted += 1

    async with engine.connect() as conn:
        nav_count = await conn.scalar(text("SELECT COUNT(*) FROM nav_record"))
    print(f"   {nav_count} NAV rows in DB ({inserted} attempted)")

    # 4. Summary
    print("\n[4/4] Done!")
    async with engine.connect() as conn:
        schemes  = await conn.scalar(text("SELECT COUNT(*) FROM scheme"))
        navs     = await conn.scalar(text("SELECT COUNT(*) FROM nav_record"))
        sample   = await conn.execute(text("""
            SELECT s.scheme_name, s.category, n.nav, n.nav_date
            FROM nav_record n JOIN scheme s ON s.id=n.scheme_id
            ORDER BY s.scheme_name LIMIT 5
        """))
        print(f"   Schemes : {schemes}")
        print(f"   NAV rows: {navs}")
        print("   Sample:")
        for row in sample.all():
            print(f"     {row[3]}  {row[2]:.4f}  {row[1]:25s}  {row[0][:50]}")

    print("\n>> Restart the API server (start.bat) to see funds in the dashboard.")


def _parse_nav(content: str) -> list[dict]:
    records = []
    for row in csv.reader(io.StringIO(content), delimiter=";"):
        if len(row) < 6: continue
        code, ig, id2, name, nav_s, date_s = (x.strip() for x in row[:6])
        if not code.isdigit(): continue
        try: nav = float(nav_s)
        except: continue
        d = None
        for fmt in ("%d-%b-%Y", "%d/%m/%Y", "%Y-%m-%d"):
            try: d = datetime.strptime(date_s, fmt).date().isoformat(); break
            except: pass
        if not d: continue
        records.append({"code":code,"isin_g":ig or None,"isin_d":id2 or None,
                         "name":name,"nav":nav,"nav_date":d})
    return records


_CAT_RULES = [
    ("defense|defence", "Defense"),
    (r"\bpsu\b", "PSU"),
    ("banking|financial service", "Banking & Financial Services"),
    ("pharma|health", "Pharma & Healthcare"),
    (r"\bit\b|technology", "IT/Technology"),
    ("infra", "Infrastructure"),
    ("consumption|fmcg|consumer", "Consumption"),
    ("energy|power|oil", "Energy"),
    ("nifty.?next.?50", "Index - Nifty Next 50"),
    ("nifty.?50\\b|nifty50", "Index - Nifty 50"),
    ("sensex", "Index - Sensex"),
    ("index|etf", "Index Other"),
    ("large.?&.?mid|large.?mid", "Large & Mid Cap"),
    ("large.?cap", "Large Cap"),
    ("mid.?cap", "Mid Cap"),
    ("small.?cap", "Small Cap"),
    ("flexi.?cap", "Flexi Cap"),
    ("multi.?cap", "Multi Cap"),
    ("elss|tax.?sav", "ELSS"),
    ("overnight", "Overnight"),
    ("liquid", "Liquid"),
    ("short.?dur", "Short Duration"),
    ("corporate.?bond", "Corporate Bond"),
    ("gilt", "Gilt"),
    ("aggressive.?hybrid", "Aggressive Hybrid"),
    ("balanced.?advantage|dynamic.?asset", "Balanced Advantage"),
    ("multi.?asset", "Multi-Asset"),
    ("international|global|overseas|fof", "International/FoF"),
    ("sectoral|thematic", "Sectoral/Thematic Other"),
    ("hybrid", "Multi-Asset"),
    ("debt|bond|income|credit", "Debt Other"),
]
import re as _re
_CAT_COMPILED = [(_re.compile(p, _re.I), c) for p, c in _CAT_RULES]

def _infer_category(name: str) -> str:
    for pat, cat in _CAT_COMPILED:
        if pat.search(name): return cat
    return "Other"

def _infer_plan(name: str) -> str:
    n = name.upper()
    if "DIRECT" in n: return "Direct"
    if "REGULAR" in n: return "Regular"
    return "Unknown"

def _infer_option(name: str) -> str:
    n = name.upper()
    if "IDCW" in n or "DIVIDEND" in n: return "Dividend"
    return "Growth"


if __name__ == "__main__":
    asyncio.run(main())
