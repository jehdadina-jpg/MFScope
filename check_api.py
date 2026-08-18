import asyncio, httpx, sqlite3

async def main():
    conn = sqlite3.connect("mfscope.db")
    cur = conn.cursor()
    # Get a few non-Other schemes and their codes
    cur.execute("""
        SELECT s.id, s.scheme_code, s.scheme_name, s.category
        FROM scheme s
        JOIN nav_record n ON n.scheme_id = s.id
        WHERE s.category != 'Other'
        LIMIT 5
    """)
    samples = cur.fetchall()
    conn.close()

    print("Sample schemes from DB:")
    for sid, code, name, cat in samples:
        print(f"  id={sid} code={code} cat={cat} name={name[:60]}")

    print("\nTesting mfapi calls:")
    async with httpx.AsyncClient(timeout=10, verify=False) as client:
        for sid, code, name, cat in samples:
            r = await client.get(f"https://api.mfapi.in/mf/{code}",
                                 headers={"User-Agent": "MFScope/0.1"})
            data = r.json()
            nav_data = data.get("data", [])
            meta = data.get("meta", {})
            print(f"  code={code} status={r.status_code} nav_rows={len(nav_data)} fund_name={meta.get('fund_name','')[:40]}")
            if nav_data:
                print(f"    latest: {nav_data[0]}")
                print(f"    oldest: {nav_data[-1]}")

asyncio.run(main())
