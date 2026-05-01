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
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path, PurePath

# ── JSON backend (orjson with stdlib fallback) ──
#
# Wire-coercion contract (enforced by tests/test_serve_mcp_protocol.py):
#
#   datetime / date          → ISO-8601 string
#   pathlib.PurePath family  → str(path)
#   decimal.Decimal          → float (lossy on >double precision; the
#                              alternative is str-encoding which surprises
#                              every JSON consumer). Children that need
#                              exact decimals must convert explicitly.
#   set / frozenset          → sorted list (deterministic for replay)
#   bytes / bytearray        → utf-8 decoded str (replace on bad bytes)
#
# Anything not in the above list raises TypeError at serialize time. The
# old behaviour (``default=str``) silently coerced *everything* via
# ``repr()``, which let ``datetime.datetime(2026, 4, 30, ...)``-shaped
# Python repr strings reach the wire payload — surfaced by the v6.5.0
# mcp-protocol-auditor pass as a ship-blocker (H3). Strict typed
# coercion turns silent corruption into a loud audit-row ERROR that
# downstream consumers can detect.


def _wire_default(obj):
    """JSON ``default`` hook — typed coercion, never ``repr()``."""
    if isinstance(obj, datetime):
        # Naive datetimes are stamped UTC at the boundary so downstream
        # consumers don't have to guess the zone.
        if obj.tzinfo is None:
            obj = obj.replace(tzinfo=timezone.utc)
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, PurePath):
        return str(obj)
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (set, frozenset)):
        return sorted(obj, key=lambda x: (str(type(x).__name__), str(x)))
    if isinstance(obj, (bytes, bytearray)):
        return bytes(obj).decode("utf-8", errors="replace")
    raise TypeError(
        f"Object of type {type(obj).__name__} is not JSON-serializable; "
        f"add an explicit coercion in framework/audit.py:_wire_default "
        f"or convert at the child boundary before returning the result."
    )


try:
    import orjson as _orjson

    # OPT_NON_STR_KEYS matches stdlib json's key coercion. Without it, any
    # dict with non-string keys (e.g. compute_hr_zones' {1..5: count}) raises
    # "Dict key must be str" and the tool call is audited as ERROR. The two
    # backends should be behaviourally identical.
    _ORJSON_OPT = _orjson.OPT_NON_STR_KEYS

    def _dumps(obj, **kw) -> str:
        return _orjson.dumps(
            obj, default=_wire_default, option=_ORJSON_OPT,
        ).decode()

    def _loads(s):
        return _orjson.loads(s)

    JSON_BACKEND = "orjson"
except ImportError:
    import json as _json

    def _dumps(obj, **kw) -> str:
        return _json.dumps(obj, default=_wire_default)

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
                subject_id TEXT,
                scrubber_id TEXT
            )
        """)
        # Migrate pre-existing audit.db files that predate later columns.
        # Mirrors VaultStorage._ensure_db()'s approach for vault_notes.mtime_ns:
        # detect via PRAGMA, ALTER TABLE if absent. Each column added in a
        # different release ships its own one-line migration here.
        cols = {
            row[1]
            for row in self._conn.execute("PRAGMA table_info(audit_log)").fetchall()
        }
        if "subject_id" not in cols:
            self._conn.execute("ALTER TABLE audit_log ADD COLUMN subject_id TEXT")
        if "scrubber_id" not in cols:
            # v6.2 — closes the ADR 0003 doc-lie. The seam recorded its
            # scrubber identity in the property since v5; the audit row
            # never carried it until now.
            self._conn.execute("ALTER TABLE audit_log ADD COLUMN scrubber_id TEXT")
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
               subject_id: str | None = None,
               scrubber_id: str | None = None):
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
            "  outcome, duration_ms, error, subject_id, scrubber_id)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (datetime.now(timezone.utc).isoformat(), domain, tool_name, tier,
             params_repr, token_estimate, outcome, duration_ms, error,
             subject_id, scrubber_id),
        )
        self._conn.commit()
        log.info(
            f"AUDIT | {domain}.{tool_name} | tier={tier} "
            f"| tokens~{token_estimate} | {outcome} | {duration_ms}ms"
            + (f" | subject={subject_id}" if subject_id else "")
            + (f" | scrubber={scrubber_id}" if scrubber_id else "")
        )
