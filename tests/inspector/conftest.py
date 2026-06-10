"""
Fixtures for the inspector test suite.

Audit fixtures are built by calling the real ``AuditLog.record()``
against a tmp path — never hand-written INSERTs — so the fixture
schema can't drift from the production writer. The one exception is
the *legacy* fixture, which deliberately renames ``entity_id`` back to
``subject_id`` after writing, to simulate a pre-v9 database whose boot
migration has not run yet.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tailor.framework.audit import AuditLog
from tailor.framework.vault.storage import VaultStorage


def populate_audit(db_path: Path) -> AuditLog:
    """Write a representative spread of rows via the real writer."""
    audit = AuditLog(db_path)
    audit.record(
        domain="csv_dir", tool_name="csv_summary_report", tier=1,
        params={"file": "S004.csv"}, token_estimate=420,
        outcome="SUCCESS", duration_ms=12,
        entity_id="S004", scrubber_id="noop",
    )
    audit.record(
        domain="csv_dir", tool_name="csv_raw_stream", tier=3,
        params={"file": "S004.csv"}, token_estimate=52_000,
        outcome="COST_GATE_TRIGGERED", duration_ms=3,
        entity_id="S004", scrubber_id="noop",
    )
    audit.record(
        domain="running", tool_name="strava_downsampled_streams", tier=2,
        params={"activity_id": 7}, token_estimate=0,
        outcome="CONSENT_BLOCKED", duration_ms=2, scrubber_id="noop",
    )
    audit.record(
        domain="running", tool_name="approve_consent_running", tier=1,
        params={}, token_estimate=0, outcome="SUCCESS", duration_ms=1,
        scrubber_id="noop",
    )
    audit.record(
        domain="running", tool_name="revoke_consent_running", tier=1,
        params={}, token_estimate=0, outcome="SUCCESS", duration_ms=1,
        scrubber_id="noop",
    )
    audit.record(
        domain="redcap_file", tool_name="redcap_record_detail", tier=1,
        params={"record_id": "R01"}, token_estimate=300,
        outcome="SUCCESS", duration_ms=8, entity_id="R01",
        scrubber_id="noop", child_scrubber_id="redcap_metadata_flags",
    )
    audit.record(
        domain="csv_dir", tool_name="csv_file_detail", tier=1,
        params={"file": str(Path.home() / "data" / "S004.csv"),
                "note": "<script>alert(1)</script>"},
        token_estimate=100, outcome="ERROR", duration_ms=5,
        error=f"could not read {Path.home() / 'data' / 'S004.csv'}",
        scrubber_id="noop",
    )
    return audit


@pytest.fixture
def populated_data_dir(tmp_path: Path) -> Path:
    """A data dir whose audit.db + vault.db carry representative rows."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    audit = populate_audit(data_dir / "audit.db")
    audit.close()

    storage = VaultStorage(data_dir / "vault.db")
    storage.upsert_note(
        filename="runs/2026-06-01-am.md", domain="running",
        note_type="run", frontmatter={"date": "2026-06-01"},
        date="2026-06-01", entity_id="S004",
    )
    storage.upsert_note(
        filename="themes/aerobic-decoupling.md", domain="running",
        note_type="theme", frontmatter={},
    )
    storage.upsert_theme(
        slug="aerobic-decoupling", status="open",
        opened="2026-05-01", last_updated="2026-06-01",
    )
    storage.commit()
    storage.close()
    return data_dir


@pytest.fixture
def empty_data_dir(tmp_path: Path) -> Path:
    """A data dir with no databases at all — the honest-empty case."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return data_dir


@pytest.fixture
def legacy_audit_db(tmp_path: Path) -> Path:
    """A pre-v9 audit.db still carrying ``subject_id``.

    Built with the real writer, then the column is renamed *back* —
    contents stay production-shaped, only the column name regresses.
    """
    import sqlite3

    db_path = tmp_path / "audit.db"
    audit = populate_audit(db_path)
    audit.close()
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "ALTER TABLE audit_log RENAME COLUMN entity_id TO subject_id"
    )
    conn.commit()
    conn.close()
    return db_path
