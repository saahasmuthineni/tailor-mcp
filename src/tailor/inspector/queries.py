"""
Inspector queries — read-only SQL → plain dicts.
=================================================
Pure given a database path: every function opens a short-lived
read-only connection (URI ``mode=ro``), reads, closes, and returns
plain dicts/lists. No connection is ever held across requests — the
Windows WAL file-lock discipline from the ``router.close()`` precedent
(CLAUDE.md § Implementation notes) applied to the reader side.

The read-only invariant is structural: the only ``sqlite3.connect``
call in this package lives in :func:`connect_ro` and always carries
``mode=ro``. A grep-class test (``tests/inspector/test_queries.py``)
enforces that no bare writable connect ever lands here.

Honesty requirements (ADR 0043):

- A missing database is a normal state, not an error — callers get
  ``{"exists": False, ...}`` and the renderer shows an empty state.
- A non-empty ``-wal`` sidecar means a ``mode=ro`` reader may not see
  un-checkpointed recent writes; surfaced as ``wal_pending`` so the
  page can render a staleness caveat instead of silently
  under-reporting.
- Any ``sqlite3.Error`` (e.g. Windows ``database is locked`` during a
  checkpoint) is captured into the section model as an error string,
  never raised through to a 500.
- Legacy pre-v9 databases whose ``subject_id`` column has not been
  renamed yet (AuditLog.__init__ does the rename, and may not have run
  since upgrade) are detected via ``PRAGMA table_info`` and aliased.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# Outcome classes for the gate-activity section. The vocabulary is
# open-ended by design (the audit `outcome` column is unconstrained
# TEXT); unknown values render as-is in a neutral style. `*_INTERNAL`
# variants emitted by dispatch_internal() map to the same class as
# their base outcome.
REFUSAL_OUTCOMES = frozenset({
    "CONSENT_BLOCKED", "COST_GATE_TRIGGERED", "CIRCUIT_OPEN",
    "PARAM_INVALID",
})
ERROR_OUTCOMES = frozenset({
    "ERROR", "PURGE_FAILED", "COST_ESTIMATE_ERROR",
})
SUCCESS_OUTCOMES = frozenset({
    "SUCCESS", "PURGE_CACHE", "SETUP_CONFIG_WRITE", "REATTEST",
    "ATTEST_INITIAL",
})

DEFAULT_LIMIT = 50
MAX_LIMIT = 500

# Display columns for the recent-calls table, in render order. Each may
# be absent on a legacy database; _select_expr() degrades to NULL (or
# the subject_id alias for entity_id) so the inspector never crashes on
# a pre-migration file.
_CALL_COLUMNS = (
    "id", "timestamp", "domain", "tool_name", "tier", "outcome",
    "duration_ms", "token_estimate", "entity_id", "scrubber_id",
    "child_scrubber_id", "params", "error",
)


def outcome_class(outcome: str) -> str:
    """Map an audit outcome value to a render class.

    ``*_INTERNAL`` variants classify with their base outcome.
    """
    base = outcome or ""
    if base.endswith("_INTERNAL"):
        base = base[: -len("_INTERNAL")]
    if base in REFUSAL_OUTCOMES:
        return "refusal"
    if base in ERROR_OUTCOMES:
        return "error"
    if base in SUCCESS_OUTCOMES:
        return "success"
    return "other"


def connect_ro(db_path: Path) -> sqlite3.Connection:
    """Open ``db_path`` strictly read-only via SQLite URI ``mode=ro``.

    Raises ``sqlite3.OperationalError`` if the file does not exist
    (mode=ro never creates) or cannot be opened. A short busy timeout
    keeps transient Windows checkpoint locks from surfacing as
    immediate failures without ever blocking the writer for long.
    """
    # Path.as_uri() yields a correctly percent-encoded file:// URI on
    # every platform (file:///C:/... on Windows). A hand-built
    # "file:C:/..." form lacks the leading slash, so SQLite's URI
    # parser treats it as a RELATIVE path and fails to open the
    # database on Windows (PR #148 review finding). resolve() makes
    # the path absolute, which as_uri() requires.
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    return sqlite3.connect(uri, uri=True, timeout=2.0)


def wal_pending(db_path: Path) -> bool:
    """True when a non-empty ``-wal`` sidecar sits next to ``db_path``.

    A ``mode=ro`` connection cannot checkpoint, so un-replayed WAL
    frames mean the page may not reflect the most recent writes. The
    renderer turns this into a visible staleness caveat.
    """
    try:
        wal = db_path.with_name(db_path.name + "-wal")
        return wal.exists() and wal.stat().st_size > 0
    except OSError:
        return False


@dataclass
class Filters:
    """Validated query-param filters for the audit window."""

    domain: str | None = None
    outcome: str | None = None
    entity_id: str | None = None
    since: str | None = None
    limit: int = DEFAULT_LIMIT
    # Set when a supplied ?since= failed ISO parsing and was ignored —
    # rendered as a note rather than silently dropped.
    invalid_since: str | None = None
    notes: list[str] = field(default_factory=list)


def parse_filters(params: dict) -> Filters:
    """Build :class:`Filters` from a parsed query-string dict.

    ``params`` maps names to lists (``urllib.parse.parse_qs`` shape).
    Invalid values are ignored with a note, never raised: the page must
    render under any query string.
    """
    def first(name: str) -> str | None:
        values = params.get(name) or []
        value = values[0].strip() if values else ""
        return value or None

    f = Filters(
        domain=first("domain"),
        outcome=first("outcome"),
        entity_id=first("entity_id"),
    )

    raw_since = first("since")
    if raw_since is not None:
        try:
            datetime.fromisoformat(raw_since)
            f.since = raw_since
        except ValueError:
            f.invalid_since = raw_since
            f.notes.append(
                f"Ignored invalid since={raw_since!r} (not an ISO date)."
            )

    raw_limit = first("limit")
    if raw_limit is not None:
        try:
            f.limit = max(1, min(int(raw_limit), MAX_LIMIT))
        except ValueError:
            f.notes.append(
                f"Ignored invalid limit={raw_limit!r}; using {DEFAULT_LIMIT}."
            )
    return f


def _file_stat(path: Path) -> dict:
    """Size + UTC mtime for the header; never raises."""
    try:
        st = path.stat()
        return {
            "size_bytes": st.st_size,
            "mtime": datetime.fromtimestamp(
                st.st_mtime, tz=timezone.utc,
            ).isoformat(timespec="seconds"),
        }
    except OSError:
        return {"size_bytes": None, "mtime": None}


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {
        row[1]
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }


def _select_expr(present: set[str], name: str) -> str:
    """Column expression tolerant of legacy/partial schemas."""
    if name in present:
        return name
    if name == "entity_id" and "subject_id" in present:
        # Pre-v9 file whose rename migration hasn't run yet.
        return "subject_id AS entity_id"
    return f"NULL AS {name}"


def _where(filters: Filters) -> tuple[str, list]:
    """Bound-parameter WHERE clause from the validated filters.

    Filter values are NEVER string-interpolated into SQL — everything
    caller-influenceable travels as a bound parameter.
    """
    clauses: list[str] = []
    args: list = []
    if filters.since:
        clauses.append("timestamp >= ?")
        args.append(filters.since)
    if filters.domain:
        clauses.append("domain = ?")
        args.append(filters.domain)
    if filters.outcome:
        clauses.append("outcome = ?")
        args.append(filters.outcome)
    if filters.entity_id:
        clauses.append("entity_id = ?")
        args.append(filters.entity_id)
    if not clauses:
        return "", []
    return " WHERE " + " AND ".join(clauses), args


def collect_audit(audit_path: Path, filters: Filters) -> dict:
    """Everything the page needs from ``audit.db``, in one dict."""
    section: dict = {
        "path": str(audit_path),
        "exists": audit_path.exists(),
        "error": None,
        "table_missing": False,
        "legacy_subject_id": False,
        "wal_pending": False,
        "row_count": 0,
        "outcome_counts": [],
        "recent_calls": [],
        "consent_events": [],
        "scrubbers": [],
        "child_scrubbers": [],
        "token_by_domain": [],
        **_file_stat(audit_path),
    }
    if not section["exists"]:
        return section
    section["wal_pending"] = wal_pending(audit_path)

    try:
        conn = connect_ro(audit_path)
    except sqlite3.Error as exc:
        section["error"] = str(exc)
        return section
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "audit_log" not in tables:
            section["table_missing"] = True
            return section

        cols = _table_columns(conn, "audit_log")
        section["legacy_subject_id"] = (
            "subject_id" in cols and "entity_id" not in cols
        )

        where_sql, where_args = _where(filters)

        section["row_count"] = conn.execute(
            "SELECT COUNT(*) FROM audit_log"
        ).fetchone()[0]

        section["outcome_counts"] = [
            {"outcome": row[0], "count": row[1],
             "klass": outcome_class(row[0])}
            for row in conn.execute(
                f"SELECT outcome, COUNT(*) FROM audit_log{where_sql} "
                f"GROUP BY outcome ORDER BY COUNT(*) DESC",
                where_args,
            ).fetchall()
        ]

        select_cols = ", ".join(
            _select_expr(cols, name) for name in _CALL_COLUMNS
        )
        section["recent_calls"] = [
            dict(zip(_CALL_COLUMNS, row, strict=True))
            for row in conn.execute(
                f"SELECT {select_cols} FROM audit_log{where_sql} "
                f"ORDER BY id DESC LIMIT ?",
                [*where_args, filters.limit],
            ).fetchall()
        ]

        # Consent timeline — derived from approve/revoke audit rows;
        # live state lives in the running server's session (ADR 0043).
        consent_clauses = (
            "(tool_name LIKE 'approve_consent_%' "
            "OR tool_name LIKE 'revoke_consent_%')"
        )
        consent_where = (
            where_sql + " AND " + consent_clauses
            if where_sql else " WHERE " + consent_clauses
        )
        section["consent_events"] = [
            {
                "timestamp": row[0],
                "tool_name": row[1],
                "domain": row[2],
                "outcome": row[3],
                "action": (
                    "approve"
                    if row[1].startswith("approve_consent_")
                    else "revoke"
                ),
            }
            for row in conn.execute(
                f"SELECT timestamp, tool_name, domain, outcome "
                f"FROM audit_log{consent_where} "
                f"ORDER BY id DESC LIMIT 50",
                where_args,
            ).fetchall()
        ]

        section["scrubbers"] = [
            {"scrubber_id": row[0], "count": row[1]}
            for row in conn.execute(
                f"SELECT scrubber_id, COUNT(*) FROM audit_log{where_sql} "
                f"GROUP BY scrubber_id ORDER BY COUNT(*) DESC",
                where_args,
            ).fetchall()
        ] if "scrubber_id" in cols else []

        if "child_scrubber_id" in cols:
            child_where = (
                where_sql + " AND child_scrubber_id IS NOT NULL"
                if where_sql
                else " WHERE child_scrubber_id IS NOT NULL"
            )
            section["child_scrubbers"] = [
                {"scrubber_id": row[0], "count": row[1]}
                for row in conn.execute(
                    f"SELECT child_scrubber_id, COUNT(*) "
                    f"FROM audit_log{child_where} "
                    f"GROUP BY child_scrubber_id ORDER BY COUNT(*) DESC",
                    where_args,
                ).fetchall()
            ]

        token_col = (
            "COALESCE(token_estimate, 0)"
            if "token_estimate" in cols else "0"
        )
        section["token_by_domain"] = [
            {"domain": row[0], "tokens": row[1], "calls": row[2]}
            for row in conn.execute(
                f"SELECT domain, SUM({token_col}), COUNT(*) "
                f"FROM audit_log{where_sql} "
                f"GROUP BY domain ORDER BY SUM({token_col}) DESC",
                where_args,
            ).fetchall()
        ]
    except sqlite3.Error as exc:
        # Windows mid-checkpoint locks land here; honest error state,
        # never a crash (ADR 0043 § consequences).
        section["error"] = str(exc)
    finally:
        conn.close()
    return section


def collect_vault(vault_db_path: Path) -> dict:
    """Index counts only — titles/slugs, never note bodies (ADR 0033)."""
    section: dict = {
        "path": str(vault_db_path),
        "exists": vault_db_path.exists(),
        "error": None,
        "table_missing": False,
        "wal_pending": False,
        "note_count": 0,
        "theme_count": 0,
        "notes_by_type": [],
        "themes_by_status": [],
        "latest_written_at": None,
        **_file_stat(vault_db_path),
    }
    if not section["exists"]:
        return section
    section["wal_pending"] = wal_pending(vault_db_path)

    try:
        conn = connect_ro(vault_db_path)
    except sqlite3.Error as exc:
        section["error"] = str(exc)
        return section
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "vault_notes" not in tables:
            section["table_missing"] = True
            return section

        section["note_count"] = conn.execute(
            "SELECT COUNT(*) FROM vault_notes"
        ).fetchone()[0]
        section["notes_by_type"] = [
            {"note_type": row[0], "count": row[1]}
            for row in conn.execute(
                "SELECT note_type, COUNT(*) FROM vault_notes "
                "GROUP BY note_type ORDER BY COUNT(*) DESC"
            ).fetchall()
        ]
        section["latest_written_at"] = conn.execute(
            "SELECT MAX(written_at) FROM vault_notes"
        ).fetchone()[0]

        if "vault_themes" in tables:
            section["theme_count"] = conn.execute(
                "SELECT COUNT(*) FROM vault_themes"
            ).fetchone()[0]
            section["themes_by_status"] = [
                {"status": row[0], "count": row[1]}
                for row in conn.execute(
                    "SELECT status, COUNT(*) FROM vault_themes "
                    "GROUP BY status ORDER BY COUNT(*) DESC"
                ).fetchall()
            ]
    except sqlite3.Error as exc:
        section["error"] = str(exc)
    finally:
        conn.close()
    return section


def collect_page_model(data_dir: Path, filters: Filters) -> dict:
    """The full page model: header + audit + vault sections."""
    from tailor import __version__

    return {
        "version": __version__,
        "generated_at": datetime.now(timezone.utc).isoformat(
            timespec="seconds",
        ),
        "data_dir": str(data_dir),
        "filters": filters,
        "audit": collect_audit(data_dir / "audit.db", filters),
        "vault": collect_vault(data_dir / "vault.db"),
    }
