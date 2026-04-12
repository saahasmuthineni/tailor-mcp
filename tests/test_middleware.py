"""
Tests for the framework's security middleware.

These are domain-agnostic — they validate the pipeline that sits
between Claude and any biosensor child MCP.
"""

import sqlite3
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from biosensor_mcp.framework.interfaces import ValidationSchema
from biosensor_mcp.framework.middleware import (
    AuditLog,
    CircuitBreaker,
    ConsentGate,
    CostGate,
    ParamValidator,
    PHIScrubber,
    TokenLedger,
    estimate_tokens,
)


class TestCircuitBreaker:
    def test_starts_closed(self):
        cb = CircuitBreaker(threshold=3)
        ok, msg = cb.check("test")
        assert ok is True

    def test_trips_after_threshold(self):
        cb = CircuitBreaker(threshold=3, reset_after=60)
        cb.record_failure("test")
        cb.record_failure("test")
        cb.record_failure("test")
        ok, msg = cb.check("test")
        assert ok is False
        assert "Circuit open" in msg

    def test_success_resets_failures(self):
        cb = CircuitBreaker(threshold=3)
        cb.record_failure("test")
        cb.record_failure("test")
        cb.record_success("test")
        cb.record_failure("test")
        ok, _ = cb.check("test")
        assert ok is True  # Reset by success

    def test_scoped_per_key(self):
        cb = CircuitBreaker(threshold=2)
        cb.record_failure("running")
        cb.record_failure("running")
        ok_run, _ = cb.check("running")
        ok_cgm, _ = cb.check("cgm")
        assert ok_run is False
        assert ok_cgm is True

    def test_auto_reset_after_cooldown(self):
        cb = CircuitBreaker(threshold=1, reset_after=0.1)
        cb.record_failure("test")
        ok1, _ = cb.check("test")
        assert ok1 is False
        time.sleep(0.15)
        ok2, _ = cb.check("test")
        assert ok2 is True


class TestConsentGate:
    def test_default_denied(self):
        gate = ConsentGate()
        ok, err = gate.check("running")
        assert ok is False
        assert "CONSENT_REQUIRED" in err

    def test_approve_grants_access(self):
        gate = ConsentGate()
        gate.approve("running")
        ok, _ = gate.check("running")
        assert ok is True

    def test_per_domain_scoping(self):
        gate = ConsentGate()
        gate.approve("running")
        ok_run, _ = gate.check("running")
        ok_cgm, _ = gate.check("cgm")
        assert ok_run is True
        assert ok_cgm is False  # Not approved

    def test_approved_domains_list(self):
        gate = ConsentGate()
        gate.approve("running")
        gate.approve("sleep")
        assert set(gate.approved_domains) == {"running", "sleep"}


class TestCostGate:
    def test_below_threshold(self):
        gate = CostGate(threshold=35_000)
        assert gate.should_gate(20_000) is False

    def test_at_threshold(self):
        gate = CostGate(threshold=35_000)
        assert gate.should_gate(35_000) is True

    def test_above_threshold(self):
        gate = CostGate(threshold=35_000)
        assert gate.should_gate(50_000) is True

    def test_custom_threshold(self):
        gate = CostGate(threshold=10_000)
        assert gate.should_gate(10_000) is True
        assert gate.should_gate(9_999) is False


class TestParamValidator:
    def test_valid_int(self):
        schema = {"limit": ValidationSchema(type=int, min=1, max=100, default=20)}
        ok, err, cleaned = ParamValidator.validate(schema, {"limit": 50})
        assert ok is True
        assert cleaned["limit"] == 50

    def test_default_applied(self):
        schema = {"limit": ValidationSchema(type=int, default=20)}
        ok, err, cleaned = ParamValidator.validate(schema, {})
        assert ok is True
        assert cleaned["limit"] == 20

    def test_required_missing(self):
        schema = {"id": ValidationSchema(type=int, required=True)}
        ok, err, cleaned = ParamValidator.validate(schema, {})
        assert ok is False
        assert "required" in err.lower()

    def test_int_out_of_range(self):
        schema = {"limit": ValidationSchema(type=int, min=1, max=100)}
        ok, err, _ = ParamValidator.validate(schema, {"limit": 200})
        assert ok is False

    def test_string_pattern(self):
        schema = {"date": ValidationSchema(type=str, pattern=r"^\d{4}-\d{2}-\d{2}$")}
        ok1, _, _ = ParamValidator.validate(schema, {"date": "2026-01-15"})
        ok2, _, _ = ParamValidator.validate(schema, {"date": "not-a-date"})
        assert ok1 is True
        assert ok2 is False

    def test_list_validation(self):
        schema = {
            "ids": ValidationSchema(type=list, min_len=2, max_len=5, required=True)
        }
        ok1, _, _ = ParamValidator.validate(schema, {"ids": [1, 2, 3]})
        ok2, _, _ = ParamValidator.validate(schema, {"ids": [1]})
        assert ok1 is True
        assert ok2 is False

    def test_list_allowed_values(self):
        schema = {
            "streams": ValidationSchema(
                type=list, allowed_values=["heartrate", "velocity_smooth"]
            )
        }
        ok1, _, _ = ParamValidator.validate(schema, {"streams": ["heartrate"]})
        ok2, err, _ = ParamValidator.validate(schema, {"streams": ["invalid"]})
        assert ok1 is True
        assert ok2 is False
        assert "invalid" in err.lower()

    def test_extra_params_passed_through(self):
        schema = {"limit": ValidationSchema(type=int, default=20)}
        ok, _, cleaned = ParamValidator.validate(schema, {"limit": 10, "extra": "val"})
        assert ok is True
        assert cleaned["extra"] == "val"


class TestTokenLedger:
    def test_tracks_totals(self):
        ledger = TokenLedger()
        ledger.add("running", "strava_run_report", 800)
        ledger.add("running", "strava_hr_analysis", 400)
        assert ledger.total == 1200

    def test_tracks_by_domain(self):
        ledger = TokenLedger()
        ledger.add("running", "report", 800)
        ledger.add("cgm", "glucose_report", 500)
        by_domain = ledger.by_domain()
        assert by_domain["running"] == 800
        assert by_domain["cgm"] == 500

    def test_summary(self):
        ledger = TokenLedger()
        ledger.add("running", "report", 800)
        s = ledger.summary()
        assert s["session_total_tokens"] == 800
        assert s["call_count"] == 1


class TestTokenEstimation:
    def test_estimates_from_dict(self):
        data = {"key": "value", "number": 42}
        tokens = estimate_tokens(data)
        assert tokens > 0

    def test_larger_data_more_tokens(self):
        small = {"a": 1}
        large = {"data": list(range(1000))}
        assert estimate_tokens(large) > estimate_tokens(small)


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


class TestPHIScrubber:
    """
    PHIScrubber is the per-institution PHI-stripping seam. The default
    implementation is a no-op — but subclassing and returning a modified
    dict must work, so the seam is actually useful.
    """

    def test_default_is_noop(self):
        scrubber = PHIScrubber()
        result = {"value": 42, "note": "no change"}
        assert scrubber.scrub(result) is result

    def test_subclass_can_strip_fields(self):
        class DropNameScrubber(PHIScrubber):
            def scrub(self, result: dict) -> dict:
                result.pop("participant_name", None)
                return result

        scrubber = DropNameScrubber()
        scrubbed = scrubber.scrub(
            {"value": 42, "participant_name": "J. Doe"}
        )
        assert "participant_name" not in scrubbed
        assert scrubbed["value"] == 42
