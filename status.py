import sqlite3
conn = sqlite3.connect('mfscope.db')
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM scheme"); print('schemes:', cur.fetchone()[0])
cur.execute("SELECT COUNT(*) FROM nav_record"); print('nav rows:', cur.fetchone()[0])
cur.execute("SELECT COUNT(*) FROM fund_features"); print('features:', cur.fetchone()[0])
cur.execute("SELECT COUNT(*) FROM fund_score"); print('scores:', cur.fetchone()[0])
cur.execute("SELECT COUNT(*) FROM scheme WHERE category != 'Other'"); print('categorised schemes:', cur.fetchone()[0])
cur.execute("""
    SELECT scheme_id, COUNT(*) c FROM nav_record
    GROUP BY scheme_id HAVING c >= 30
""")
print('schemes with 30+ NAV rows:', len(cur.fetchall()))
cur.execute("SELECT category, COUNT(*) c FROM scheme GROUP BY category ORDER BY c DESC LIMIT 8")
print('Category breakdown:')
for r in cur.fetchall():
    print(f'  {r[1]:6d}  {r[0]}')
conn.close()
