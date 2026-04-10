"""
Tests for the framework's security middleware.

These are domain-agnostic — they validate the pipeline that sits
between Claude and any biosensor child MCP.
"""

import time
import pytest
from strava_coach.framework.middleware import (
    CircuitBreaker,
    ConsentGate,
    CostGate,
    ParamValidator,
    TokenLedger,
    estimate_tokens,
)
from strava_coach.framework.interfaces import ValidationSchema


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
