"""
Seed / Sync Authoritative Google OAuth Users in DuckDB
"""
import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.connection import get_connection

def sync_users():
    con = get_connection()
    try:
        con.execute("UPDATE AuthorizedDoctors SET email = 'pviraj1025@gmail.com' WHERE doctor_id = 'DOC001'")
        con.execute("UPDATE AuthorizedDoctors SET email = 'pawarsamarth4912@gmail.com' WHERE doctor_id = 'DOC002'")
        con.execute("UPDATE AuthorizedDoctors SET email = 'shreyasutar15@gmail.com' WHERE doctor_id = 'DOC003'")
        con.execute("UPDATE AuthorizedDoctors SET email = '1230821edits@gmail.com' WHERE doctor_id = 'REC001'")
        rows = con.execute("SELECT doctor_id, doctor_name, email, specialty, role FROM AuthorizedDoctors").fetchall()
        print("Updated AuthorizedDoctors rows in DuckDB:")
        for r in rows:
            print(" ", r)
    finally:
        con.close()

if __name__ == "__main__":
    sync_users()
