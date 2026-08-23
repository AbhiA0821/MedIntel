from pathlib import Path
import threading
import duckdb

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "database" / "medintel.duckdb"

_db_lock = threading.Lock()
_shared_connection = None


class ProcessSharedDuckDBConnection:
    """Thread-safe process-level shared DuckDB connection wrapper."""
    def __init__(self, db_path):
        self._raw_con = duckdb.connect(str(db_path))
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
            _shared_connection = ProcessSharedDuckDBConnection(DB_PATH)
        return _shared_connection