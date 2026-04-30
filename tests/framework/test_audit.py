"""
Tests for ``framework.audit`` — the audit log.

Subject-id round-tripping, legacy-DB migration, params-size truncation,
and the keyword-only ``error`` invariant on ``AuditLog.record()``.
"""

import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from biosensor_mcp.framework.audit import JSON_BACKEND, AuditLog, _dumps, _loads


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


class TestAuditLogScrubberId:
    """
    ``scrubber_id`` is the ADR 0003 audit-row stamp that distinguishes
    a deployment running the no-op default scrubber (``noop``) from one
    running an institutional subclass. The column is nullable because
    the seam-id is set by the router, not the caller — direct
    ``AuditLog.record()`` invocations from tests don't populate it.
    """

    def test_record_with_scrubber_id_round_trips(self):
        with TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "audit.db"
            audit = AuditLog(db)
            try:
                audit.record(
                    "running", "strava_run_report", 1, {}, 800, "SUCCESS", 15,
                    scrubber_id="noop",
                )
                audit.record(
                    "cgm", "cgm_daily_report", 1, {}, 400, "SUCCESS", 12,
                    scrubber_id="HIPAASafeHarborScrubber",
                )
                audit.record(
                    "running", "strava_list_runs", 1, {}, 200, "SUCCESS", 5,
                )
            finally:
                audit.close()

            conn = sqlite3.connect(str(db))
            try:
                rows = conn.execute(
                    "SELECT tool_name, scrubber_id FROM audit_log ORDER BY id"
                ).fetchall()
            finally:
                conn.close()

        assert rows == [
            ("strava_run_report", "noop"),
            ("cgm_daily_report", "HIPAASafeHarborScrubber"),
            ("strava_list_runs", None),
        ]

    def test_migrates_legacy_audit_db_without_scrubber_id(self):
        """A v6.1 audit.db (subject_id present, scrubber_id absent) must still open."""
        with TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "audit.db"

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
                    error TEXT,
                    subject_id TEXT
                )
            """)
            legacy.execute(
                "INSERT INTO audit_log (timestamp, domain, tool_name, tier, outcome, subject_id)"
                " VALUES (?,?,?,?,?,?)",
                ("2024-01-01T00:00:00Z", "running", "legacy_tool", 1, "SUCCESS", "P001"),
            )
            legacy.commit()
            legacy.close()

            audit = AuditLog(db)
            try:
                audit.record(
                    "running", "new_tool", 1, {}, 100, "SUCCESS", 5,
                    subject_id="P007", scrubber_id="noop",
                )
            finally:
                audit.close()

            conn = sqlite3.connect(str(db))
            try:
                rows = conn.execute(
                    "SELECT tool_name, subject_id, scrubber_id FROM audit_log ORDER BY id"
                ).fetchall()
            finally:
                conn.close()

        assert rows == [
            ("legacy_tool", "P001", None),
            ("new_tool", "P007", "noop"),
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


class TestJSONBackendCoercion:
    """
    The orjson-backed ``_dumps`` must coerce non-string dict keys the same
    way stdlib json does. Before the fix this raised ``TypeError: Dict key
    must be str`` at the router's cost-estimation step whenever a tool
    returned an int-keyed dict (e.g. ``compute_hr_zones`` which keyes by
    zone number 1..5). No test dispatched ``strava_run_report`` end-to-end
    through ``_dispatch``, so the regression was silent. Both backends
    must agree.
    """

    def test_int_keyed_dict_serializes(self):
        encoded = _dumps({1: 10, 2: 20, 3: 30})
        # Keys come back as strings — matches stdlib json's behavior.
        assert _loads(encoded) == {"1": 10, "2": 20, "3": 30}

    def test_mixed_str_and_int_keys(self):
        encoded = _dumps({"pct": 0.6, 1: "a", 2: "b"})
        assert _loads(encoded) == {"pct": 0.6, "1": "a", "2": "b"}

    def test_nested_hr_zones_shape_serializes(self):
        # The exact shape RunningChild.compute_hr_zones() returns.
        zones = {
            "zone_seconds": {1: 0, 2: 0, 3: 291, 4: 3270, 5: 39},
            "zone_pct": {1: 0.0, 2: 0.0, 3: 8.1, 4: 90.8, 5: 1.1},
            "avg_hr": 156,
        }
        round_tripped = _loads(_dumps(zones))
        assert round_tripped["avg_hr"] == 156
        assert round_tripped["zone_seconds"]["4"] == 3270
        assert round_tripped["zone_pct"]["3"] == 8.1


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
