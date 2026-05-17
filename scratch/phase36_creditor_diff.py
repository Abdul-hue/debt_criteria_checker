"""Read-only: dev vs fresh CreditorCriteria name set difference."""
import sqlite3
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DEV = BASE / "db.sqlite3"
FRESH = BASE / "db_fresh.sqlite3"


def names(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.execute("SELECT creditor_name FROM debt_app_creditorcriteria ORDER BY creditor_name")
    rows = {r[0] for r in cur.fetchall()}
    conn.close()
    return rows


dev = names(DEV)
fresh = names(FRESH)
only_dev = sorted(dev - fresh)
only_fresh = sorted(fresh - dev)
print(f"dev={len(dev)} fresh={len(fresh)} only_dev={len(only_dev)} only_fresh={len(only_fresh)}")
for n in only_dev:
    print(n)
