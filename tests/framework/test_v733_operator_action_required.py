"""
v7.3.3 regression suite — OperatorActionRequired typed-exception taxonomy.

Covers the four invariants the v7.3.3 patch ratifies:

  T1  Marker class enforces non-empty ``recovery_action`` at construction.
      Misclassification (subclass without naming a remediation) becomes
      a TypeError at construction time, not silent runtime defeat.

  T2  Public-dispatch exception handler (router.py:739-751) exempts
      OperatorActionRequired from ``CircuitBreaker.record_failure``.
      Fires N consecutive raises and asserts the breaker stays closed
      so the recovery hint stays reachable on call N+1.

  T3  Internal-dispatch exception handler (router.py:1292-1304) does
      the same exemption — parity with T2. Closes the v7.3.3 B1 finding
      (auditor caught the v7.3.3 plan was site-specific to the public
      handler, missed the internal one).

  T4  Audit row on the exempt path still records outcome=ERROR with the
      full provenance kwargs (scrubber_id, child_scrubber_id,
      source_metadata_fingerprint, entity_id). Closes the v7.3.3 I2
      finding — without this, a future refactor could elide audit on
      exempt exceptions and the existing tests would still pass.

  T5  Genuine RuntimeError (the canonical flaky-upstream proxy) still
      trips the breaker. Regression guard against an over-broad
      exemption refactor that catches Exception instead of
      OperatorActionRequired.

  T6  ``RedcapMetadataFingerprintMismatch`` IS-A ``OperatorActionRequired``
      with ``recovery_action == 'tailor redcap reattest'``. Locks the
      inheritance contract — a future refactor of the REDCap exception
      that drops the parent class would unlink the exemption and fail
      this test loudly.
"""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from tailor.framework import OperatorActionRequired
from tailor.framework.audit import _loads
from tailor.framework.interfaces import (
    ChildMCP,
    CostEstimate,
    ToolDefinition,
    ValidationSchema,
)
from tailor.framework.router import RouterMCP


def _run(coro):
    return asyncio.run(coro)


# ──────────────────────────────────────────────────────────────────
# Mock children for breaker-exemption tests
# ──────────────────────────────────────────────────────────────────


class _BaseMockChild(ChildMCP):
    def __init__(self, domain_name: str):
        self._domain = domain_name

    @property
    def domain(self) -> str:
        return self._domain

    @property
    def display_name(self) -> str:
        return f"Test ({self._domain})"

    @property
    def tool_definitions(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                f"{self._domain}_tool", 1,
                "Free tool.",
                {"value": {"type": "integer", "description": "v", "required": True}},
            ),
        ]

    @property
    def param_schemas(self) -> dict:
        return {
            f"{self._domain}_tool": {
                "value": ValidationSchema(type=int, min=1, required=True),
            },
        }

    async def estimate_cost(self, tool_name: str, params: dict) -> CostEstimate:
        return CostEstimate(tokens=10, has_cheaper_alternative=False)

    def purge_cache(self, *, force: bool = False) -> dict:
        return {"rows_purged": 0, "tables_touched": [], "preserved": [], "reason": "mock"}


class _OperatorActionRaisingChild(_BaseMockChild):
    """Raises OperatorActionRequired on every execute()."""

    async def execute(self, tool_name: str, params: dict) -> dict:
        raise OperatorActionRequired(
            "Reattest required — trust root drifted.",
            recovery_action="tailor mockdomain reattest",
        )


class _RuntimeErrorRaisingChild(_BaseMockChild):
    """Raises plain RuntimeError on every execute()."""

    async def execute(self, tool_name: str, params: dict) -> dict:
        raise RuntimeError("Simulated upstream-flaky failure")


# ──────────────────────────────────────────────────────────────────
# T1 — Marker class construction-time contract
# ──────────────────────────────────────────────────────────────────


class TestT1MarkerClassContract:
    def test_recovery_action_required_kwarg_only(self):
        # Must be keyword-only — supplying positionally fails.
        with pytest.raises(TypeError):
            OperatorActionRequired("message", "positional-recovery-action")

    def test_recovery_action_must_be_non_empty(self):
        with pytest.raises(TypeError, match="non-empty"):
            OperatorActionRequired("message", recovery_action="")

    def test_recovery_action_whitespace_rejected(self):
        with pytest.raises(TypeError, match="non-empty"):
            OperatorActionRequired("message", recovery_action="   ")

    def test_recovery_action_non_string_rejected(self):
        with pytest.raises(TypeError, match="non-empty"):
            OperatorActionRequired("message", recovery_action=None)

    def test_recovery_action_stored_and_accessible(self):
        exc = OperatorActionRequired(
            "msg", recovery_action="tailor foo reattest",
        )
        assert exc.recovery_action == "tailor foo reattest"
        assert str(exc) == "msg"

    def test_is_subclass_of_exception(self):
        assert issubclass(OperatorActionRequired, Exception)


# ──────────────────────────────────────────────────────────────────
# T2 — Public dispatch breaker exemption
# ──────────────────────────────────────────────────────────────────


class TestT2PublicDispatchExemption:
    def test_recovery_hint_reachable_after_multiple_mismatches(self):
        """Five consecutive OperatorActionRequired raises, breaker
        threshold=3. Without the exemption, call 4+ would see a generic
        CIRCUIT_OPEN envelope. With the exemption, every call surfaces
        the recovery-action message via the error envelope.
        """
        with TemporaryDirectory() as tmpdir:
            router = RouterMCP(
                "test", Path(tmpdir),
                circuit_threshold=3, circuit_reset=60,
            )
            try:
                router.register_child(_OperatorActionRaisingChild("opact"))
                for _ in range(5):
                    result = _run(router._dispatch("opact_tool", {"value": 1}))
                    data = _loads(result[0].text)
                    # The recovery-hint substring of the raised
                    # exception must propagate through to the wire
                    # error envelope — never the generic "Circuit
                    # open for opact" form.
                    assert "Reattest required" in data["error"]
                    assert "Circuit open" not in data["error"]
            finally:
                router.close()

    def test_breaker_state_stays_closed_on_operator_action(self):
        with TemporaryDirectory() as tmpdir:
            router = RouterMCP(
                "test", Path(tmpdir),
                circuit_threshold=3, circuit_reset=60,
            )
            try:
                router.register_child(_OperatorActionRaisingChild("opact"))
                for _ in range(5):
                    _run(router._dispatch("opact_tool", {"value": 1}))
                ok, _ = router._circuit.check("opact")
                assert ok is True, (
                    "breaker should not have tripped on exempt exception"
                )
            finally:
                router.close()


# ──────────────────────────────────────────────────────────────────
# T3 — Internal dispatch breaker exemption (parity with T2)
# ──────────────────────────────────────────────────────────────────


class TestT3InternalDispatchExemption:
    def test_breaker_state_stays_closed_on_internal_dispatch_operator_action(self):
        """Closes v7.3.3 B1: the v7.3.3 plan named only the public
        dispatch site; the auditor caught that _dispatch_internal also
        calls record_failure and must apply the same exemption for
        parity. Without this, breaker state would diverge depending on
        whether the OperatorActionRequired was raised via the public
        path or via a cross-child oracle call.
        """
        with TemporaryDirectory() as tmpdir:
            router = RouterMCP(
                "test", Path(tmpdir),
                circuit_threshold=3, circuit_reset=60,
            )
            try:
                router.register_child(_OperatorActionRaisingChild("opact"))
                for _ in range(5):
                    result = _run(router.dispatch_internal(
                        "opact_tool", {"value": 1},
                    ))
                    assert "Reattest required" in result["error"]
                ok, _ = router._circuit.check("opact")
                assert ok is True, (
                    "breaker should not have tripped on internal-dispatch "
                    "OperatorActionRequired raise — B1 regression"
                )
            finally:
                router.close()


# ──────────────────────────────────────────────────────────────────
# T4 — Audit row provenance on exempt path
# ──────────────────────────────────────────────────────────────────


class TestT4AuditRowProvenanceOnExemptPath:
    def test_exempt_path_records_outcome_error_with_full_provenance(self):
        """The breaker exemption must not elide the audit row. The row
        carries outcome=ERROR + the v7.3.1 W5 invariant columns
        (scrubber_id, child_scrubber_id, source_metadata_fingerprint).
        Closes v7.3.3 I2 — without this test, a future refactor could
        silently skip audit on exempt exceptions and the breaker tests
        would still pass.
        """
        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            router = RouterMCP(
                "test", data_dir,
                circuit_threshold=3, circuit_reset=60,
            )
            try:
                router.register_child(_OperatorActionRaisingChild("opact"))
                _run(router._dispatch(
                    "opact_tool", {"value": 1, "entity_id": "S001"},
                ))
            finally:
                router.close()

            db_path = data_dir / "audit.db"
            conn = sqlite3.connect(db_path)
            try:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT * FROM audit_log WHERE tool_name='opact_tool' "
                    "ORDER BY id DESC LIMIT 1"
                ).fetchone()
            finally:
                conn.close()
            assert row is not None, "audit row missing on exempt path"
            assert row["outcome"] == "ERROR"
            assert row["entity_id"] == "S001"
            assert "Reattest required" in row["error"]
            # W5 invariant columns must be threaded on exempt path too.
            assert "scrubber_id" in row.keys()
            assert "child_scrubber_id" in row.keys()
            assert "source_metadata_fingerprint" in row.keys()


# ──────────────────────────────────────────────────────────────────
# T5 — Regression guard: RuntimeError still trips the breaker
# ──────────────────────────────────────────────────────────────────


class TestT5RuntimeErrorStillTripsBreaker:
    def test_runtime_error_increments_breaker(self):
        """If a future refactor changes the exception-handler isinstance
        check from OperatorActionRequired to Exception, this test fails
        loudly. The breaker exists for flaky-upstream paths; that
        property must survive the exemption refactor.
        """
        with TemporaryDirectory() as tmpdir:
            router = RouterMCP(
                "test", Path(tmpdir),
                circuit_threshold=3, circuit_reset=60,
            )
            try:
                router.register_child(_RuntimeErrorRaisingChild("flaky"))
                for _ in range(3):
                    _run(router._dispatch("flaky_tool", {"value": 1}))
                result = _run(router._dispatch("flaky_tool", {"value": 1}))
                data = _loads(result[0].text)
                assert "Circuit open" in data["error"], (
                    "breaker did NOT trip on RuntimeError — the v7.3.3 "
                    "exemption was applied too broadly"
                )
            finally:
                router.close()


# ──────────────────────────────────────────────────────────────────
# T6 — Inheritance lock: REDCap mismatch is-a OperatorActionRequired
# ──────────────────────────────────────────────────────────────────


class TestT6RedcapMismatchInheritanceContract:
    def test_redcap_mismatch_inherits_operator_action_required(self):
        # Import locally because RedcapMetadataFingerprintMismatch lives
        # inside the optional child package.
        from tailor.children.redcap.child import RedcapMetadataFingerprintMismatch

        assert issubclass(RedcapMetadataFingerprintMismatch, OperatorActionRequired)

    def test_redcap_mismatch_carries_reattest_recovery_action(self):
        from tailor.children.redcap.child import RedcapMetadataFingerprintMismatch

        exc = RedcapMetadataFingerprintMismatch(
            fingerprint_at_boot="a" * 64,
            fingerprint_on_disk="b" * 64,
        )
        assert exc.recovery_action == "tailor redcap reattest"
        # The fingerprints must still propagate via str() for IRB
        # auditability — the v7.3.2 invariant the inheritance must not
        # break.
        assert "a" * 64 in str(exc)
        assert "b" * 64 in str(exc)


# ──────────────────────────────────────────────────────────────────
# T7 — AST contract: _detect_fingerprint_mismatch has no bare except
# ──────────────────────────────────────────────────────────────────


class TestT7DetectFingerprintMismatchHasNoBareExcept:
    """Closes the v7.3.3 phi-irb-risk-reviewer BORDER NOTE: a future
    cleanup pass could re-wrap the candidate-scrubber construction in
    ``except Exception:`` and only the ADR text would carry the change
    rationale — no test would fail. This AST-class assertion makes the
    B2 fix structurally enforced, parallel to v7.3.2's W5 AST contract
    test that catches textual-window false positives.
    """

    def test_no_except_exception_in_detect_fingerprint_mismatch(self):
        import ast
        import inspect
        import textwrap

        from tailor.children.redcap.child import RedcapFileChild

        source = textwrap.dedent(
            inspect.getsource(RedcapFileChild._detect_fingerprint_mismatch)
        )
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            handler_type = node.type
            # except: (no class)
            assert handler_type is not None, (
                "bare `except:` block present in _detect_fingerprint_mismatch — "
                "violates the v7.3.3 B2 fix posture (drops blanket "
                "exception handling so future programmer errors propagate)"
            )
            # except Exception / except BaseException
            if isinstance(handler_type, ast.Name):
                assert handler_type.id not in ("Exception", "BaseException"), (
                    f"`except {handler_type.id}:` block present in "
                    f"_detect_fingerprint_mismatch — violates the v7.3.3 B2 "
                    f"fix posture; see ADR 0003 § Amendment 2026-05-15 § "
                    f"Typed-exception taxonomy"
                )


# ──────────────────────────────────────────────────────────────────
# T8 — Stderr-byte budget invariant on OperatorActionRequired path
# ──────────────────────────────────────────────────────────────────


class TestT8OperatorActionRequiredEmitsNoLoggerOutput:
    """Closes the v7.3.3 red-team-reviewer OBJECTION (F-G): the
    breaker-exemption claim ("recovery affordance reachable in
    production") was conditional on the MCP client draining stderr.
    Production (Claude Desktop) does not run a stderr drain thread;
    after ~8 mismatches the OS pipe buffer (4KB on Windows) fills,
    the server stalls on its next stderr write, stdin blocks, and
    the recovery affordance is hidden behind a different failure
    mode — the exact class v7.3.3 was meant to close.

    Closure: the router's exception handler must NOT emit any logger
    output for OperatorActionRequired instances. The audit row and
    the wire envelope already carry the full event + recovery hint;
    the rotating file handler is the durable debug trace. Silencing
    the stderr-bound StreamHandler at the source eliminates the
    byte source that would fill the pipe buffer.
    """

    def test_operator_action_required_path_emits_no_log_records(self, caplog):
        with TemporaryDirectory() as tmpdir:
            router = RouterMCP(
                "test", Path(tmpdir),
                circuit_threshold=3, circuit_reset=60,
            )
            try:
                router.register_child(_OperatorActionRaisingChild("opact"))
                caplog.clear()
                # Fire 10 calls — 2× the 4KB / 500-byte threshold the
                # red-team objection cited.
                for _ in range(10):
                    _run(router._dispatch("opact_tool", {"value": 1}))
            finally:
                router.close()
            # No log record at any level for the tailor logger should
            # have been emitted by the exception handler on the
            # OperatorActionRequired path.
            tailor_records = [
                r for r in caplog.records
                if r.name.startswith("tailor")
                and ("opact_tool" in r.getMessage() or "requires operator action" in r.getMessage())
            ]
            assert tailor_records == [], (
                "Router emitted log record(s) for OperatorActionRequired "
                "path — violates the v7.3.3 F-G stderr-byte-budget "
                "closure. Records: "
                + "\n".join(f"  {r.levelname} {r.getMessage()}" for r in tailor_records)
            )

    def test_runtime_error_path_still_emits_log_record(self, caplog):
        """Regression guard: silencing OperatorActionRequired must NOT
        silence the genuine-error path. A programmer-error RuntimeError
        should still produce a log.error + exc_info traceback for
        operator visibility.
        """
        import logging

        with TemporaryDirectory() as tmpdir:
            router = RouterMCP(
                "test", Path(tmpdir),
                circuit_threshold=10, circuit_reset=60,
            )
            try:
                router.register_child(_RuntimeErrorRaisingChild("flaky"))
                caplog.clear()
                caplog.set_level(logging.ERROR, logger="tailor")
                _run(router._dispatch("flaky_tool", {"value": 1}))
            finally:
                router.close()
            err_records = [
                r for r in caplog.records
                if r.name.startswith("tailor") and r.levelno == logging.ERROR
                and "flaky_tool" in r.getMessage()
            ]
            assert err_records, (
                "Router did NOT emit log.error for genuine RuntimeError — "
                "the F-G silencing was applied too broadly and now "
                "hides programmer-error diagnostics"
            )
