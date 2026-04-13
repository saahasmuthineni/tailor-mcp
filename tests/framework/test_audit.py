"""
Tests for ``framework.audit`` — the audit log.

Subject-id round-tripping, legacy-DB migration, params-size truncation,
and the keyword-only ``error`` invariant on ``AuditLog.record()``.
"""

import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from biosensor_mcp.framework.audit import AuditLog


class TestAuditLogSubjectId:
    """
    ``subject_id`` is the research-framing hook that lets audit rows be
    scoped to a study participant or cohort. The column is nullable, so
    existing children that don't pass one keep working unchanged.
    """

    def test_record_with_subject_id_round_trips(self):
        with TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "audit.db"
            audit = AuditLog(db)
            try:
                audit.record(
                    "cgm", "cgm_daily_report", 1, {"date": "2026-04-10"},
                    400, "SUCCESS", 12, subject_id="P042",
                )
                audit.record(
                    "running", "strava_run_report", 1, {}, 800, "SUCCESS", 15,
                )
            finally:
                audit.close()

            conn = sqlite3.connect(str(db))
            try:
                rows = conn.execute(
                    "SELECT tool_name, subject_id FROM audit_log ORDER BY id"
                ).fetchall()
            finally:
                conn.close()

        assert rows == [
            ("cgm_daily_report", "P042"),
            ("strava_run_report", None),
        ]

    def test_migrates_legacy_audit_db_without_subject_id(self):
        """An audit.db created before the reframe must still open."""
        with TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "audit.db"

            # Simulate a legacy schema: no subject_id column, one row.
            legacy = sqlite3.connect(str(db))
            legacy.execute("""
                CREATE TABLE audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    tier INTEGER NOT NULL,
                    params TEXT,
                    token_estimate INTEGER,
                    outcome TEXT NOT NULL,
                    duration_ms INTEGER,
                    error TEXT
                )
            """)
            legacy.execute(
                "INSERT INTO audit_log (timestamp, domain, tool_name, tier, outcome)"
                " VALUES (?,?,?,?,?)",
                ("2024-01-01T00:00:00Z", "running", "legacy_tool", 1, "SUCCESS"),
            )
            legacy.commit()
            legacy.close()

            # Opening AuditLog on the legacy file should silently ALTER TABLE.
            audit = AuditLog(db)
            try:
                audit.record(
                    "running", "new_tool", 1, {}, 100, "SUCCESS", 5,
                    subject_id="P007",
                )
            finally:
                audit.close()

            conn = sqlite3.connect(str(db))
            try:
                rows = conn.execute(
                    "SELECT tool_name, subject_id FROM audit_log ORDER BY id"
                ).fetchall()
            finally:
                conn.close()

        assert rows == [
            ("legacy_tool", None),
            ("new_tool", "P007"),
        ]


class TestAuditParamsSizeBound:
    """
    Oversized params dicts must be truncated before hitting SQLite —
    otherwise a single pathological caller can bloat audit.db beyond
    the point where routine queries stay fast.
    """

    def test_oversized_params_truncated_with_marker(self):
        with TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "audit.db"
            audit = AuditLog(db)
            try:
                # 200 KB of junk — well over the 50 KB cap.
                huge = {"blob": "x" * 200_000}
                audit.record(
                    "test_domain", "big_tool", 1, huge, 0, "SUCCESS", 0,
                )
            finally:
                audit.close()

            conn = sqlite3.connect(str(db))
            try:
                (stored,) = conn.execute(
                    "SELECT params FROM audit_log"
                ).fetchone()
            finally:
                conn.close()

        assert "...[truncated;" in stored
        # 50_000 cap + ~40-char marker → well under 60 KB
        assert len(stored) < 60_000

    def test_normal_params_not_truncated(self):
        with TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "audit.db"
            audit = AuditLog(db)
            try:
                audit.record(
                    "test_domain", "small_tool", 1,
                    {"activity_id": 12345}, 0, "SUCCESS", 0,
                )
            finally:
                audit.close()

            conn = sqlite3.connect(str(db))
            try:
                (stored,) = conn.execute(
                    "SELECT params FROM audit_log"
                ).fetchone()
            finally:
                conn.close()

        assert "truncated" not in stored
        assert "12345" in stored


class TestAuditErrorKeywordOnly:
    """
    `error` on AuditLog.record is keyword-only: the signature
    previously accepted 8 positional args and mistakes slipped
    through silently. Making it keyword-only surfaces the error.
    """

    def test_positional_error_rejected(self):
        with TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "audit.db"
            audit = AuditLog(db)
            try:
                with pytest.raises(TypeError):
                    # 8th positional arg (error) no longer accepted.
                    audit.record(
                        "d", "t", 1, {}, 0, "FAIL", 0, "boom",  # noqa: B008
                    )
            finally:
                audit.close()

    def test_keyword_error_roundtrips(self):
        with TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "audit.db"
            audit = AuditLog(db)
            try:
                audit.record(
                    "d", "t", 1, {}, 0, "FAIL", 0, error="boom",
                )
            finally:
                audit.close()

            conn = sqlite3.connect(str(db))
            try:
                (err,) = conn.execute(
                    "SELECT error FROM audit_log"
                ).fetchone()
            finally:
                conn.close()

        assert err == "boom"
