import os
import sys
from pathlib import Path
import duckdb

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.connection import get_db_path


def init_database(db_path=None):
    """
    Initializes DuckDB tables idempotently using schema.sql.
    Preserves all existing data if tables already exist.
    """
    target_path = Path(db_path) if db_path else get_db_path()
    target_path.parent.mkdir(parents=True, exist_ok=True)

    schema_file = Path(__file__).resolve().parent / "schema.sql"
    if not schema_file.exists():
        raise FileNotFoundError(f"Database schema file not found at: {schema_file}")

    with open(schema_file, "r", encoding="utf-8") as file:
        schema = file.read()

    con = duckdb.connect(str(target_path))
    try:
        con.execute(schema)
        print(f"[DATABASE] Database and tables verified/created successfully at: {target_path}")
    finally:
        con.close()


if __name__ == "__main__":
    init_database()
