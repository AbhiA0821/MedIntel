import os
from pathlib import Path
import threading
import duckdb

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def get_db_path() -> Path:
    """Resolves DuckDB database path, prioritizing DUCKDB_PATH env var with fallback to project default."""
    env_path = os.getenv("DUCKDB_PATH")
    if env_path and env_path.strip():
        p = Path(env_path.strip())
        if not p.is_absolute():
            p = PROJECT_ROOT / p
    else:
        p = PROJECT_ROOT / "database" / "medintel.duckdb"

    try:
        p.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return p


DB_PATH = get_db_path()

_db_lock = threading.Lock()
_shared_connection = None


class ProcessSharedDuckDBConnection:
    """Thread-safe process-level shared DuckDB connection wrapper."""
    def __init__(self, db_path, read_only=False):
        p = Path(db_path)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        try:
            self._raw_con = duckdb.connect(str(p), read_only=read_only)
        except duckdb.IOException:
            self._raw_con = duckdb.connect(str(p), read_only=True)
        self._lock = threading.Lock()

    def execute(self, query, params=None):
        with self._lock:
            if params is not None:
                return self._raw_con.execute(query, params)
            return self._raw_con.execute(query)

    def executemany(self, query, params):
        with self._lock:
            return self._raw_con.executemany(query, params)

    def cursor(self):
        return self

    def close(self):
        # Prevent closing shared process handle
        pass


def get_connection(read_only: bool = False):
    global _shared_connection
    with _db_lock:
        if _shared_connection is None:
            _shared_connection = ProcessSharedDuckDBConnection(DB_PATH, read_only=read_only)
        return _shared_connection