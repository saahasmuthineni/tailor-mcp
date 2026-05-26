"""
Tests for ``framework.security`` — pre-execution gates.

ParamValidator, CircuitBreaker, ConsentGate, DataScrubber. These are
domain-agnostic by design: the same checks apply to any biosensor
child registered with the router.
"""

import time

from tailor.framework.interfaces import ValidationSchema
from tailor.framework.security import (
    CircuitBreaker,
    ConsentGate,
    ParamValidator,
    DataScrubber,
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

    def test_int_coercion_typeerror_returns_explicit_failure(self):
        # framework/security.py:65-69 — the int-coercion except branch.
        # Coverage-criticality-mapper flagged this CRITICAL because a
        # non-castable value silently slipping past the validator would
        # reach child.execute() unchecked.
        schema = {"limit": ValidationSchema(type=int, min=1, max=100)}
        ok, err, _ = ParamValidator.validate(schema, {"limit": "not-a-number"})
        assert ok is False
        assert "must be an integer" in err
        # Also: a list (TypeError on int(value)) takes the same branch.
        ok2, err2, _ = ParamValidator.validate(schema, {"limit": [1, 2]})
        assert ok2 is False
        assert "must be an integer" in err2

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


class TestPHIScrubber:
    """
    DataScrubber is the per-institution PHI-stripping seam. The default
    implementation is a no-op — but subclassing and returning a modified
    dict must work, so the seam is actually useful.
    """

    def test_default_is_noop(self):
        scrubber = DataScrubber()
        result = {"value": 42, "note": "no change"}
        assert scrubber.scrub(result) is result

    def test_subclass_can_strip_fields(self):
        class DropNameScrubber(DataScrubber):
            def scrub(self, result: dict) -> dict:
                result.pop("participant_name", None)
                return result

        scrubber = DropNameScrubber()
        scrubbed = scrubber.scrub(
            {"value": 42, "participant_name": "J. Doe"}
        )
        assert "participant_name" not in scrubbed
        assert scrubbed["value"] == 42

    def test_noop_warning_emitted_at_most_once_per_process(self, caplog):
        """
        ADR 0003 says the no-op default must surface "loudly" — but a
        researcher running tests or a long session shouldn't get that
        warning printed once per construction. ``_noop_warning_emitted``
        is class-level for exactly this reason. Until this test landed
        the contract was undefended: any refactor moving the flag to
        instance-level would silently regress.
        """
        # The warning may already have fired in earlier tests — what
        # matters is that further constructions do not re-emit it.
        DataScrubber._noop_warning_emitted = False  # reset class flag
        caplog.clear()
        with caplog.at_level("WARNING", logger="tailor"):
            DataScrubber()
            DataScrubber()
            DataScrubber()
        noop_warnings = [
            r for r in caplog.records
            if "DataScrubber default is a no-op" in r.getMessage()
        ]
        assert len(noop_warnings) == 1, (
            f"expected exactly one no-op warning across 3 constructions; "
            f"got {len(noop_warnings)}"
        )

    def test_subclass_construction_does_not_emit_noop_warning(self, caplog):
        """
        Only the base DataScrubber emits the no-op warning; a subclass
        (which presumably has a real policy) must not trip it.
        """
        class RealScrubber(DataScrubber):
            def scrub(self, result: dict) -> dict:
                return result

        DataScrubber._noop_warning_emitted = False
        caplog.clear()
        with caplog.at_level("WARNING", logger="tailor"):
            RealScrubber()
            RealScrubber()
        noop_warnings = [
            r for r in caplog.records
            if "DataScrubber default is a no-op" in r.getMessage()
        ]
        assert noop_warnings == []

    def test_scrubber_id_distinguishes_noop_from_subclass(self):
        """
        ``scrubber_id`` is the per-instance string the router stamps into
        ``_meta`` and the ``audit_log.scrubber_id`` column on every call.
        Default no-op returns ``"noop"``; subclasses return their class
        name. End-to-end wire-up is covered by
        ``test_router.TestPHIScrubberAuditStamp``; this test just pins
        the property's contract.
        """
        class CustomScrubber(DataScrubber):
            def scrub(self, result: dict) -> dict:
                return result

        assert DataScrubber().scrubber_id == "noop"
        assert CustomScrubber().scrubber_id == "CustomScrubber"
