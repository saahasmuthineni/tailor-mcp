"""
Biosensor-to-LLM Framework — Base Storage
==========================================
Thread-safe SQLite-backed local cache with WAL mode and connection pooling.

SQLite is used deliberately: it's stdlib, single-file, inspectable with
any SQL tool, and simple to archive or attach to a replication package.
For the research workflows this framework targets, that set of properties
matters more than write throughput.

Children extend this for domain-specific tables by overriding
``_schema_sql()``. Each thread gets its own persistent connection via
``threading.local()``, avoiding connect/close overhead while respecting
SQLite's thread safety.
"""

import logging
import sqlite3
import threading
from pathlib import Path

log = logging.getLogger("tailor")


class BaseStorage:
    """
    Thread-safe SQLite storage base class.

    Usage:
        class MyStorage(BaseStorage):
            def _schema_sql(self) -> str:
                return '''
                    CREATE TABLE IF NOT EXISTS my_data (
                        id INTEGER PRIMARY KEY,
                        payload TEXT NOT NULL
                    );
                '''

    Transaction contract:
        ``execute()`` and ``executemany()`` do NOT auto-commit — this
        is deliberate so callers can batch multiple statements into a
        single transaction. Callers are responsible for invoking
        ``commit()`` once the batch is complete. Forgetting to commit
        is the single most common foot-gun when extending this class.

        Note that ``AuditLog.record()`` follows a different convention
        (auto-commits after every insert) because each audit row is an
        independent unit of evidence with no batching context.
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._ensure_db()

    def _get_conn(self) -> sqlite3.Connection:
        """Return (or lazily create) a per-thread connection."""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(str(self.db_path))
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA cache_size=-8000")  # 8 MB page cache
            self._local.conn = conn
        return conn

    def _ensure_db(self):
        """Create tables defined by _schema_sql()."""
        sql = self._schema_sql()
        if sql:
            conn = self._get_conn()
            conn.executescript(sql)
            conn.commit()

    def _schema_sql(self) -> str:
        """Override in children to define domain-specific tables."""
        return ""

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """Run a single statement. Caller must ``commit()`` to persist."""
        return self._get_conn().execute(sql, params)

    def executemany(self, sql: str, params_list: list[tuple]):
        """Run a batch. Caller must ``commit()`` to persist."""
        self._get_conn().executemany(sql, params_list)

    def commit(self):
        """Persist any pending writes from execute()/executemany()."""
        self._get_conn().commit()

    def fetchone(self, sql: str, params: tuple = ()) -> tuple | None:
        return self._get_conn().execute(sql, params).fetchone()

    def fetchall(self, sql: str, params: tuple = ()) -> list[tuple]:
        return self._get_conn().execute(sql, params).fetchall()

    def close(self):
        """Close the thread-local connection. Required on Windows to release WAL file lock."""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None
