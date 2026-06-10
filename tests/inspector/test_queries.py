"""
Inspector query-layer tests — pure dict-shape assertions, no HTTP.

Also enforces two ADR 0043 invariants structurally:

- read-only: a write attempt through ``connect_ro`` raises;
- grep-class: no ``sqlite3.connect`` call without ``mode=ro`` exists
  anywhere in ``src/tailor/inspector/``.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from tailor.inspector.queries import (
    Filters,
    collect_audit,
    collect_page_model,
    collect_vault,
    connect_ro,
    outcome_class,
    parse_filters,
)


def test_collect_audit_outcome_counts(populated_data_dir: Path) -> None:
    audit = collect_audit(populated_data_dir / "audit.db", Filters())
    counts = {c["outcome"]: c["count"] for c in audit["outcome_counts"]}
    assert counts["SUCCESS"] == 4
    assert counts["COST_GATE_TRIGGERED"] == 1
    assert counts["CONSENT_BLOCKED"] == 1
    assert counts["ERROR"] == 1
    assert audit["row_count"] == 7
    assert audit["error"] is None
    assert audit["exists"] is True


def test_collect_audit_recent_calls_newest_first(
    populated_data_dir: Path,
) -> None:
    audit = collect_audit(populated_data_dir / "audit.db", Filters())
    calls = audit["recent_calls"]
    assert len(calls) == 7
    ids = [c["id"] for c in calls]
    assert ids == sorted(ids, reverse=True)
    # The newest row is the ERROR row with params + error populated.
    assert calls[0]["outcome"] == "ERROR"
    assert calls[0]["error"] is not None
    assert "script" in calls[0]["params"]


def test_collect_audit_filters(populated_data_dir: Path) -> None:
    db = populated_data_dir / "audit.db"
    by_domain = collect_audit(db, Filters(domain="csv_dir"))
    assert all(c["domain"] == "csv_dir" for c in by_domain["recent_calls"])
    assert len(by_domain["recent_calls"]) == 3

    by_outcome = collect_audit(db, Filters(outcome="CONSENT_BLOCKED"))
    assert len(by_outcome["recent_calls"]) == 1

    by_entity = collect_audit(db, Filters(entity_id="S004"))
    assert {c["entity_id"] for c in by_entity["recent_calls"]} == {"S004"}

    limited = collect_audit(db, Filters(limit=2))
    assert len(limited["recent_calls"]) == 2
    # outcome_counts still reflect the whole (unlimited) window.
    assert sum(c["count"] for c in limited["outcome_counts"]) == 7


def test_collect_audit_since_filter_integration(
    populated_data_dir: Path,
) -> None:
    """The ?since= path threaded through _where into real SQL — not
    just parse_filters in isolation (coverage-criticality MEDIUM)."""
    db = populated_data_dir / "audit.db"
    past = collect_audit(db, Filters(since="2000-01-01"))
    assert len(past["recent_calls"]) == 7
    future = collect_audit(db, Filters(since="2999-01-01"))
    assert future["recent_calls"] == []
    assert future["outcome_counts"] == []


def test_collect_audit_table_missing(tmp_path: Path) -> None:
    """audit.db exists but carries no audit_log table yet."""
    import sqlite3

    db = tmp_path / "audit.db"
    sqlite3.connect(str(db)).close()
    audit = collect_audit(db, Filters())
    assert audit["exists"] is True
    assert audit["table_missing"] is True
    assert audit["error"] is None


def test_collect_vault_table_missing(tmp_path: Path) -> None:
    import sqlite3

    db = tmp_path / "vault.db"
    sqlite3.connect(str(db)).close()
    vault = collect_vault(db)
    assert vault["exists"] is True
    assert vault["table_missing"] is True


def test_collect_audit_consent_timeline(populated_data_dir: Path) -> None:
    audit = collect_audit(populated_data_dir / "audit.db", Filters())
    events = audit["consent_events"]
    assert [e["action"] for e in events] == ["revoke", "approve"]
    assert all(e["domain"] == "running" for e in events)


def test_collect_audit_scrubber_posture(populated_data_dir: Path) -> None:
    audit = collect_audit(populated_data_dir / "audit.db", Filters())
    assert audit["scrubbers"] == [{"scrubber_id": "noop", "count": 7}]
    assert audit["child_scrubbers"] == [
        {"scrubber_id": "redcap_metadata_flags", "count": 1},
    ]


def test_collect_audit_token_totals(populated_data_dir: Path) -> None:
    audit = collect_audit(populated_data_dir / "audit.db", Filters())
    by_domain = {t["domain"]: t for t in audit["token_by_domain"]}
    assert by_domain["csv_dir"]["tokens"] == 420 + 52_000 + 100
    assert by_domain["csv_dir"]["calls"] == 3


def test_collect_audit_missing_db(empty_data_dir: Path) -> None:
    audit = collect_audit(empty_data_dir / "audit.db", Filters())
    assert audit["exists"] is False
    assert audit["error"] is None
    assert audit["recent_calls"] == []
    assert audit["row_count"] == 0


def test_collect_audit_legacy_subject_id(legacy_audit_db: Path) -> None:
    """A pre-v9 DB renders with subject_id aliased — never a crash."""
    audit = collect_audit(legacy_audit_db, Filters())
    assert audit["legacy_subject_id"] is True
    assert audit["row_count"] == 7
    by_id = {c["id"]: c for c in audit["recent_calls"]}
    assert by_id[1]["entity_id"] == "S004"

    # entity_id filtering works through the alias too? It does NOT —
    # the filter targets the entity_id column name. Pre-migration DBs
    # surface rows unfiltered rather than erroring; assert the
    # no-crash contract only.
    filtered = collect_audit(legacy_audit_db, Filters(domain="csv_dir"))
    assert len(filtered["recent_calls"]) == 3


def test_collect_vault_stats(populated_data_dir: Path) -> None:
    vault = collect_vault(populated_data_dir / "vault.db")
    assert vault["exists"] is True
    assert vault["note_count"] == 2
    assert vault["theme_count"] == 1
    types = {r["note_type"]: r["count"] for r in vault["notes_by_type"]}
    assert types == {"run": 1, "theme": 1}
    assert vault["themes_by_status"] == [{"status": "open", "count": 1}]
    assert vault["latest_written_at"] is not None


def test_collect_vault_missing_db(empty_data_dir: Path) -> None:
    vault = collect_vault(empty_data_dir / "vault.db")
    assert vault["exists"] is False
    assert vault["error"] is None


def test_collect_page_model_shape(populated_data_dir: Path) -> None:
    model = collect_page_model(populated_data_dir, Filters())
    from tailor import __version__
    assert model["version"] == __version__
    assert model["data_dir"] == str(populated_data_dir)
    assert model["audit"]["exists"] and model["vault"]["exists"]


# ── Error-capture honesty (ADR 0043: "never a 500") ──
#
# Forces the sqlite3.Error branches the fixtures can't reach (every
# fixture closes its writer, so no real lock ever occurs in CI). The
# red-team pass flagged these as asserted-but-unguarded: a regression
# turning the honest error state back into a crash would have shipped
# green.


def test_collect_audit_connect_failure_is_captured(
    populated_data_dir: Path, monkeypatch,
) -> None:
    import tailor.inspector.queries as q

    def locked(path):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(q, "connect_ro", locked)
    audit = q.collect_audit(populated_data_dir / "audit.db", Filters())
    assert audit["error"] == "database is locked"
    assert audit["recent_calls"] == []

    vault = q.collect_vault(populated_data_dir / "vault.db")
    assert vault["error"] == "database is locked"

    # End to end: the page renders the honest errbox, never raises.
    from tailor.inspector.render import render_page
    page = render_page(q.collect_page_model(populated_data_dir, Filters()))
    assert "Could not read this database right now" in page
    assert "database is locked" in page


def test_collect_audit_midquery_lock_is_captured(
    populated_data_dir: Path, monkeypatch,
) -> None:
    """The Windows mid-checkpoint shape: connect succeeds, a later
    statement raises. The per-section except must capture it."""
    import tailor.inspector.queries as q

    real_connect = q.connect_ro

    class FlakyConn:
        def __init__(self, conn):
            self._conn = conn
            self._calls = 0

        def execute(self, *args):
            self._calls += 1
            if self._calls > 1:
                raise sqlite3.OperationalError("database is locked")
            return self._conn.execute(*args)

        def close(self):
            self._conn.close()

    monkeypatch.setattr(
        q, "connect_ro", lambda path: FlakyConn(real_connect(path)),
    )
    audit = q.collect_audit(populated_data_dir / "audit.db", Filters())
    assert audit["error"] == "database is locked"

    vault = q.collect_vault(populated_data_dir / "vault.db")
    assert vault["error"] == "database is locked"


# ── Read-only invariant (ADR 0043) ──


def test_connect_ro_write_attempt_raises(populated_data_dir: Path) -> None:
    conn = connect_ro(populated_data_dir / "audit.db")
    try:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute(
                "INSERT INTO audit_log (timestamp, domain, tool_name, "
                "tier, outcome) VALUES ('x', 'x', 'x', 1, 'x')"
            )
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("DELETE FROM audit_log")
    finally:
        conn.close()


def test_connect_ro_never_creates(empty_data_dir: Path) -> None:
    with pytest.raises(sqlite3.OperationalError):
        connect_ro(empty_data_dir / "audit.db")
    assert not (empty_data_dir / "audit.db").exists()


def test_no_writable_connect_in_inspector_package() -> None:
    """Grep-class enforcement: every sqlite3.connect in the inspector
    package must carry mode=ro (acceptance criterion 3, ADR 0043)."""
    import tailor.inspector as pkg

    pkg_dir = Path(pkg.__file__).parent
    # connect_ro builds the URI on a prior line; assert the package
    # contains exactly one connect call site and the mode=ro literal.
    all_text = "".join(
        p.read_text(encoding="utf-8") for p in pkg_dir.glob("*.py")
    )
    assert all_text.count("sqlite3.connect(") == 1, (
        "inspector package must funnel every connection through "
        "connect_ro()"
    )
    assert "mode=ro" in all_text


# ── Filter parsing ──


def test_parse_filters_defaults() -> None:
    f = parse_filters({})
    assert f.domain is None and f.outcome is None and f.entity_id is None
    assert f.since is None and f.limit == 50 and f.notes == []


def test_parse_filters_values_and_clamps() -> None:
    f = parse_filters({
        "domain": ["csv_dir"], "outcome": ["SUCCESS"],
        "entity_id": ["S004"], "since": ["2026-06-01"],
        "limit": ["9999"],
    })
    assert f.domain == "csv_dir"
    assert f.since == "2026-06-01"
    assert f.limit == 500  # clamped to MAX_LIMIT


def test_parse_filters_invalid_inputs_noted_not_raised() -> None:
    f = parse_filters({"since": ["not-a-date"], "limit": ["abc"]})
    assert f.since is None
    assert f.invalid_since == "not-a-date"
    assert f.limit == 50
    assert len(f.notes) == 2


def test_outcome_class_mapping() -> None:
    assert outcome_class("SUCCESS") == "success"
    assert outcome_class("CONSENT_BLOCKED") == "refusal"
    assert outcome_class("COST_GATE_TRIGGERED") == "refusal"
    assert outcome_class("CIRCUIT_OPEN_INTERNAL") == "refusal"
    assert outcome_class("ERROR") == "error"
    assert outcome_class("PURGE_FAILED") == "error"
    assert outcome_class("SETUP_CONFIG_WRITE") == "success"
    assert outcome_class("SOMETHING_NEW") == "other"
