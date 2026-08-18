"""Quick DB status check"""
import sqlite3

conn = sqlite3.connect("mfscope.db")
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM scheme"); schemes = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM nav_record"); navs = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM fund_features"); features = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM fund_score"); scores = cur.fetchone()[0]

cur.execute("""
    SELECT scheme_id, COUNT(*) c
    FROM nav_record
    GROUP BY scheme_id
    HAVING c >= 30
""")
eligible = len(cur.fetchall())

print(f"""
MFScope Status
{'='*50}
Schemes          : {schemes:,}
NAV rows         : {navs:,}
Features built   : {features:,}
Scores computed  : {scores:,}
Schemes w/ 30+ NAV : {eligible:,}
{'='*50}
""")

if scores > 0:
    cur.execute("""
        SELECT s.scheme_name, fs.composite_score, fs.conviction
        FROM fund_score fs JOIN scheme s ON s.id=fs.scheme_id
        ORDER BY fs.composite_score DESC LIMIT 3
    """)
    print("Top 3 scored funds:")
    for name, score, conv in cur.fetchall():
        print(f"  {score:5.1f}  {conv:12s}  {name[:50]}")
else:
    print("Setup still running... check again in a few minutes")

conn.close()
