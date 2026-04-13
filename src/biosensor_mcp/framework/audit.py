"""
Biosensor-to-LLM Framework — Audit Log
=======================================
The durable record of every tool call the router dispatched.

The audit log is the backbone of reproducibility and IRB review for
LLM-assisted analyses in this framework. Every tool call is persisted
with timestamp, domain, tool name, access tier, parameters, token
estimate, outcome, latency, and (optionally) a study ``subject_id``
pulled from the call parameters. That row is intended to be durable
evidence — of how an analyst accessed participant data, in what order,
with what scope, and with what result — suitable for appendices,
protocol amendments, or replication packages.

See [docs/adr/0001-audit-log-as-backbone.md] for the architectural
decision behind this module.

This module also owns the JSON serialization helpers (``_dumps``,
``_loads``, ``JSON_BACKEND``) used across the framework. They live
here because the audit log is the heaviest user — every recorded
call serializes its params dict — and keeping the JSON backend
co-located with the consumer that exercises it most avoids a
separate one-function module.
"""

import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

# ── JSON backend (orjson with stdlib fallback) ──

try:
    import orjson as _orjson

    def _dumps(obj, **kw) -> str:
        return _orjson.dumps(obj, default=str).decode()

    def _loads(s):
        return _orjson.loads(s)

    JSON_BACKEND = "orjson"
except ImportError:
    import json as _json

    def _dumps(obj, **kw) -> str:
        return _json.dumps(obj, default=str)

    def _loads(s):
        return _json.loads(s)

    JSON_BACKEND = "json (orjson not installed)"


log = logging.getLogger("biosensor-mcp")


class AuditLog:
    """
    Every tool call logged to SQLite for reproducibility and IRB review.

    Captured per call: timestamp, domain, tool name, access tier,
    parameters, token estimate, outcome, latency, an optional error
    message, and an optional ``subject_id`` for studies that want to
    scope rows to a participant or cohort. ``subject_id`` is only
    populated when a caller supplies one — children are free to
    ignore it.

    Uses threading.local() so each thread gets its own SQLite connection —
    sqlite3 connections must not be shared across threads (check_same_thread
    defaults to True for good reason). The schema is created once on the
    first connection from any thread, and WAL mode allows concurrent readers.
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._local = threading.local()
        # Eagerly create the schema from the constructing thread
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                domain TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                tier INTEGER NOT NULL,
                params TEXT,
                token_estimate INTEGER,
                outcome TEXT NOT NULL,
                duration_ms INTEGER,
                error TEXT,
                subject_id TEXT
            )
        """)
        # Migrate pre-existing audit.db files that predate the subject_id
        # column. Mirrors VaultStorage._ensure_db()'s approach for
        # vault_notes.mtime_ns: detect via PRAGMA, ALTER TABLE if absent.
        cols = {
            row[1]
            for row in self._conn.execute("PRAGMA table_info(audit_log)").fetchall()
        }
        if "subject_id" not in cols:
            self._conn.execute("ALTER TABLE audit_log ADD COLUMN subject_id TEXT")
        self._conn.commit()

    @property
    def _conn(self) -> sqlite3.Connection:
        """Return (or lazily create) the per-thread SQLite connection."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(str(self.db_path))
            self._local.conn.execute("PRAGMA journal_mode=WAL")
        return self._local.conn

    def close(self):
        """Close the thread-local connection. Required on Windows to release file lock."""
        if hasattr(self._local, "conn") and self._local.conn is not None:
            self._local.conn.close()
            self._local.conn = None

    # A pathological caller can pass a multi-megabyte params dict and bloat
    # audit.db. Serialized params above this bound are truncated with a
    # marker — we still record *that* the call happened, but the params
    # column stays query-able. 50 KB is generous for structured args.
    _MAX_PARAMS_BYTES = 50_000

    def record(self, domain: str, tool_name: str, tier: int, params: dict,
               token_estimate: int, outcome: str, duration_ms: int,
               *, error: str | None = None,
               subject_id: str | None = None):
        params_json = _dumps(params)
        if isinstance(params_json, bytes):
            params_repr = params_json.decode("utf-8", errors="replace")
        else:
            params_repr = params_json
        if len(params_repr) > self._MAX_PARAMS_BYTES:
            params_repr = (
                params_repr[: self._MAX_PARAMS_BYTES]
                + f"...[truncated; original {len(params_repr)} bytes]"
            )
        self._conn.execute(
            "INSERT INTO audit_log"
            " (timestamp, domain, tool_name, tier, params, token_estimate,"
            "  outcome, duration_ms, error, subject_id)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (datetime.now(timezone.utc).isoformat(), domain, tool_name, tier,
             params_repr, token_estimate, outcome, duration_ms, error,
             subject_id),
        )
        self._conn.commit()
        log.info(
            f"AUDIT | {domain}.{tool_name} | tier={tier} "
            f"| tokens~{token_estimate} | {outcome} | {duration_ms}ms"
            + (f" | subject={subject_id}" if subject_id else "")
        )
