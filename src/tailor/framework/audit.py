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


log = logging.getLogger("tailor")


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
        # ADR 0022 commits to a new audit-log row category for oracle
        # calls capturing model_id, model_version_hash, latency,
        # confidence, oracle-tier-codename, and prompt_hash. Adding the
        # columns here closes the ADR-vs-code drift the
        # researcher-utility-reviewer surfaced before commit. Each
        # column is NULL for non-oracle dispatch paths.
        if "oracle_model_id" not in cols:
            self._conn.execute(
                "ALTER TABLE audit_log ADD COLUMN oracle_model_id TEXT"
            )
        if "oracle_model_version_hash" not in cols:
            self._conn.execute(
                "ALTER TABLE audit_log ADD COLUMN oracle_model_version_hash TEXT"
            )
        if "oracle_tier" not in cols:
            self._conn.execute(
                "ALTER TABLE audit_log ADD COLUMN oracle_tier TEXT"
            )
        if "oracle_confidence" not in cols:
            self._conn.execute(
                "ALTER TABLE audit_log ADD COLUMN oracle_confidence REAL"
            )
        if "oracle_prompt_hash" not in cols:
            self._conn.execute(
                "ALTER TABLE audit_log ADD COLUMN oracle_prompt_hash TEXT"
            )
        if "oracle_latency_ms" not in cols:
            # ADR 0022 commits to oracle latency as a queryable audit
            # column distinct from the router's `duration_ms`: this one
            # is the backend's compose() wall-clock alone (HTTP +
            # on-device inference), not the router pipeline's total.
            self._conn.execute(
                "ALTER TABLE audit_log ADD COLUMN oracle_latency_ms INTEGER"
            )
        if "oracle_substrate_count" not in cols:
            # ADR 0023 — substrate-vision asymmetry codified by feature.
            # Records, per oracle call, how many vault items were
            # surfaced into the hosted-LLM-bound payload via
            # related_substrate. NULL on non-oracle paths and on
            # oracle pre-execute failures.
            self._conn.execute(
                "ALTER TABLE audit_log ADD COLUMN oracle_substrate_count INTEGER"
            )
        if "oracle_next_best_calls_count" not in cols:
            # ADR 0023 PR2 — gap-reasoning auditable per call. Counts
            # the framework-tool suggestions the local LLM emitted
            # into the hosted-LLM-bound payload via next_best_calls.
            # Mirrors oracle_substrate_count by symmetry: an IRB
            # reviewer reconstructing what the hosted LLM saw on an
            # oracle call should be able to query "how many tool
            # suggestions and how many analyst-questions did the
            # local LLM emit?" from audit.db without parsing the
            # response payload. NULL on non-oracle paths and on
            # oracle pre-execute failures.
            self._conn.execute(
                "ALTER TABLE audit_log ADD COLUMN "
                "oracle_next_best_calls_count INTEGER"
            )
        if "oracle_unresolved_intent_count" not in cols:
            # ADR 0023 PR2 — see oracle_next_best_calls_count above;
            # the analyst-question half of the same audit-completeness
            # contract.
            self._conn.execute(
                "ALTER TABLE audit_log ADD COLUMN "
                "oracle_unresolved_intent_count INTEGER"
            )
        if "child_scrubber_id" not in cols:
            # ADR 0003 § Amendment 2026-05-14 + ADR 0037 — the
            # child-level structured-PHI seam. Framework-level
            # scrubber_id records cross-domain pattern matchers
            # (regex, heuristic, NLP). child_scrubber_id records
            # domain-specific structured-PHI scrubbers like
            # RedcapPHIScrubber that read project_metadata.csv
            # identifier flags. NULL for children that ship no
            # child-level scrubber (csv_dir, matlab_file, running,
            # template).
            self._conn.execute(
                "ALTER TABLE audit_log ADD COLUMN child_scrubber_id TEXT"
            )
        if "source_metadata_fingerprint" not in cols:
            # ADR 0003 § Amendment 2026-05-15 — trust-root attestation
            # seam. Records the cryptographic fingerprint (SHA-256 over
            # canonical-form) of the structured metadata input the
            # child-level scrubber relied on at call time. Domain-
            # agnostic naming: any future child whose scrubber reads a
            # structured input (FHIR profile descriptor, EDF channel
            # manifest, vendor calibration sidecar) writes its
            # fingerprint here. NULL on dispatch paths with no child-
            # level scrubber, and on children whose scrubber does not
            # expose a `fingerprint` property.
            self._conn.execute(
                "ALTER TABLE audit_log ADD COLUMN "
                "source_metadata_fingerprint TEXT"
            )
            # Indexed because the natural IRB-review query is "which
            # calls ran under fingerprint X" — full-table scans become
            # slow on multi-year audit databases.
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS "
                "idx_audit_source_metadata_fingerprint "
                "ON audit_log(source_metadata_fingerprint)"
            )
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
               scrubber_id: str | None = None,
               child_scrubber_id: str | None = None,
               source_metadata_fingerprint: str | None = None,
               oracle_model_id: str | None = None,
               oracle_model_version_hash: str | None = None,
               oracle_tier: str | None = None,
               oracle_confidence: float | None = None,
               oracle_prompt_hash: str | None = None,
               oracle_latency_ms: int | None = None,
               oracle_substrate_count: int | None = None,
               oracle_next_best_calls_count: int | None = None,
               oracle_unresolved_intent_count: int | None = None):
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
            "  outcome, duration_ms, error, subject_id, scrubber_id,"
            "  child_scrubber_id, source_metadata_fingerprint,"
            "  oracle_model_id, oracle_model_version_hash,"
            "  oracle_tier, oracle_confidence, oracle_prompt_hash,"
            "  oracle_latency_ms, oracle_substrate_count,"
            "  oracle_next_best_calls_count, oracle_unresolved_intent_count)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (datetime.now(timezone.utc).isoformat(), domain, tool_name, tier,
             params_repr, token_estimate, outcome, duration_ms, error,
             subject_id, scrubber_id, child_scrubber_id,
             source_metadata_fingerprint,
             oracle_model_id, oracle_model_version_hash, oracle_tier,
             oracle_confidence, oracle_prompt_hash, oracle_latency_ms,
             oracle_substrate_count, oracle_next_best_calls_count,
             oracle_unresolved_intent_count),
        )
        self._conn.commit()
        log.info(
            f"AUDIT | {domain}.{tool_name} | tier={tier} "
            f"| tokens~{token_estimate} | {outcome} | {duration_ms}ms"
            + (f" | subject={subject_id}" if subject_id else "")
            + (f" | scrubber={scrubber_id}" if scrubber_id else "")
            + (f" | oracle_model={oracle_model_id}" if oracle_model_id else "")
        )

    # ── Query (B1 column allowlist) ──
    #
    # The audit log is a trust root; a tool that re-egresses its rows to
    # an LLM transcript widens the IRB-stakes surface. The B1 design
    # (ADR 0012 § Amendment v7.4.0) restricts the return shape to
    # *structured* columns — no `params` content, no raw `error`
    # strings. The error column is reduced to ``has_error`` (bool) so
    # the v7.3.1 path-redaction posture stays intact: legacy rows that
    # predate v7.3.1 may carry raw on-disk paths in `error`, and the
    # framework PHIScrubber default is no-op (ADR 0003) so trusting it
    # to re-scrub at surface time would be wishful thinking. Researchers
    # needing full error content drop to ``tailor status`` or
    # ``sqlite3 audit.db``.
    #
    # The allowlist is enforced by explicit SELECT (never SELECT *) so
    # a future sensitive column added by ALTER TABLE cannot silently
    # become part of the response shape.

    # Identifier literals only — these names are interpolated into the
    # SELECT clause of query() via f-string. Adding a caller-controlled
    # value here would re-open the injection vector the explicit-SELECT
    # enforcement closes. Defense is structural-by-convention; preserve
    # the constraint when extending.
    _QUERY_COLUMNS = (
        "id", "timestamp", "domain", "tool_name", "tier",
        "token_estimate", "outcome", "duration_ms",
        "subject_id", "scrubber_id", "child_scrubber_id",
        "source_metadata_fingerprint",
    )
    _MAX_QUERY_LIMIT = 100

    def query(
        self,
        *,
        since: str,
        subject_id: str | None = None,
        domain: str | None = None,
        tool: str | None = None,
        outcome: str | None = None,
        limit: int = 50,
        include_self: bool = True,
    ) -> list[dict]:
        """Read audit rows under the B1 column allowlist.

        Returns a list of dicts ordered by ``timestamp`` descending,
        each carrying the keys in :data:`_QUERY_COLUMNS` plus a derived
        ``has_error`` (bool). The raw ``params`` and ``error`` columns
        are never returned — see the module-level comment above for the
        IRB-stakes argument.

        Args:
            since: ISO-8601 timestamp; rows where
                ``timestamp >= since`` match. The caller is expected
                to validate/parse relative forms (``"1h"`` etc.) before
                calling.
            subject_id: optional. When provided, applies an
                IS-NULL-or-match filter per ADR 0009 — framework-tier
                rows that wrote NULL stay visible alongside the
                requested subject's rows.
            domain: optional. Exact match.
            tool: optional. Exact match against ``audit_log.tool_name``.
            outcome: optional. Exact match against ``audit_log.outcome``.
            limit: optional. Clamped to :data:`_MAX_QUERY_LIMIT`.
                Default 50.
            include_self: optional. When ``False``, excludes rows where
                ``tool_name == "audit_query"``. Default ``True`` so the
                tool's own usage is visible by default — closes the
                ADR 0001 recursion gap an IRB reviewer would otherwise
                only see by dropping to raw SQL.
        """
        limit = min(max(1, int(limit)), self._MAX_QUERY_LIMIT)

        where_clauses = ["timestamp >= ?"]
        sql_params: list = [since]

        if subject_id is not None:
            where_clauses.append("(subject_id IS NULL OR subject_id = ?)")
            sql_params.append(subject_id)
        if domain is not None:
            where_clauses.append("domain = ?")
            sql_params.append(domain)
        if tool is not None:
            where_clauses.append("tool_name = ?")
            sql_params.append(tool)
        if outcome is not None:
            where_clauses.append("outcome = ?")
            sql_params.append(outcome)
        if not include_self:
            where_clauses.append("tool_name != ?")
            sql_params.append("audit_query")

        sql_params.append(limit)

        select_cols = ", ".join(self._QUERY_COLUMNS)
        sql = (
            f"SELECT {select_cols}, "
            "CASE WHEN error IS NULL THEN 0 ELSE 1 END AS has_error "
            f"FROM audit_log WHERE {' AND '.join(where_clauses)} "
            "ORDER BY timestamp DESC LIMIT ?"
        )

        cursor = self._conn.execute(sql, sql_params)
        keys = list(self._QUERY_COLUMNS) + ["has_error"]
        rows = []
        for row in cursor.fetchall():
            # strict=True: the SELECT explicitly lists _QUERY_COLUMNS;
            # any length mismatch is a structural bug worth raising.
            d = dict(zip(keys, row, strict=True))
            d["has_error"] = bool(d["has_error"])
            rows.append(d)
        return rows
