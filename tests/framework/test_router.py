"""
Tests for the parent router MCP.

Uses a minimal mock child to test the routing and security pipeline
without depending on Strava or any real data source.
"""

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from tailor.framework.audit import _loads
from tailor.framework.interfaces import (
    ChildMCP,
    CostEstimate,
    ToolDefinition,
    ValidationSchema,
)
from tailor.framework.router import RouterMCP

# ── Mock Child ──

class MockChild(ChildMCP):
    """Minimal child for testing the router pipeline."""

    def __init__(self, domain_name="test", cost=100):
        self._domain = domain_name
        self._cost = cost
        self._execute_count = 0

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
                f"{self._domain}_free_tool", 1,
                "A free tool for testing.",
                {"value": {"type": "integer", "description": "A value", "required": True}},
            ),
            ToolDefinition(
                f"{self._domain}_gated_tool", 2,
                "A consent-gated tool.",
                {"value": {"type": "integer", "description": "A value", "required": True}},
            ),
            ToolDefinition(
                f"{self._domain}_expensive_tool", 3,
                "A cost-gated tool.",
                {"value": {"type": "integer", "description": "A value", "required": True}},
            ),
        ]

    @property
    def param_schemas(self) -> dict:
        base = {"value": ValidationSchema(type=int, min=1, required=True)}
        return {
            f"{self._domain}_free_tool": base,
            f"{self._domain}_gated_tool": base,
            f"{self._domain}_expensive_tool": base,
        }

    async def execute(self, tool_name: str, params: dict) -> dict:
        self._execute_count += 1
        return {"result": "ok", "tool": tool_name, "params": params}

    async def estimate_cost(self, tool_name: str, params: dict) -> CostEstimate:
        return CostEstimate(
            tokens=self._cost,
            has_cheaper_alternative=self._cost > 10_000,
            alternative_tokens=self._cost // 10,
            alternative_description="Cheaper alternative",
        )

    def purge_cache(self, *, force: bool = False) -> dict:
        # Records the call so tests can assert revocation invoked it.
        self.purge_count = getattr(self, "purge_count", 0) + 1
        return {
            "rows_purged": 0,
            "tables_touched": [],
            "preserved": [],
            "reason": "MockChild has no real cache",
        }


class MockFailingChild(MockChild):
    """Child that always raises on execute."""

    async def execute(self, tool_name: str, params: dict) -> dict:
        raise RuntimeError("Simulated failure")


# ── Tests ──

def _run(coro):
    """Helper to run async code in tests."""
    return asyncio.run(coro)


class TestChildRegistration:
    def test_register_child(self):
        with TemporaryDirectory() as tmpdir:
            router = RouterMCP("test", Path(tmpdir))
            child = MockChild("alpha")
            router.register_child(child)
            assert "alpha" in router.registered_domains
            assert "alpha_free_tool" in router.registered_tools
            router.close()

    def test_duplicate_domain_rejected(self):
        with TemporaryDirectory() as tmpdir:
            router = RouterMCP("test", Path(tmpdir))
            router.register_child(MockChild("alpha"))
            with pytest.raises(ValueError, match="already registered"):
                router.register_child(MockChild("alpha"))
            router.close()

    def test_duplicate_tool_name_rejected(self):
        """A child whose tool names collide with an existing child must be rejected."""

        class CollidingChild(MockChild):
            """Returns a tool list that overlaps with MockChild("alpha")."""
            @property
            def tool_definitions(self) -> list[ToolDefinition]:
                return [
                    ToolDefinition(
                        "alpha_free_tool",  # same name as MockChild("alpha")
                        1,
                        "Colliding tool name",
                        {"value": {"type": "integer", "description": "v", "required": True}},
                    )
                ]

            @property
            def param_schemas(self) -> dict:
                return {"alpha_free_tool": {"value": ValidationSchema(type=int, required=True)}}

        with TemporaryDirectory() as tmpdir:
            router = RouterMCP("test", Path(tmpdir))
            router.register_child(MockChild("alpha"))
            # beta has different domain but a tool name that collides with alpha
            with pytest.raises(ValueError, match="already registered"):
                router.register_child(CollidingChild("beta"))
            router.close()


class TestTier1Dispatch:
    """Tier 1 tools should execute without any gates."""

    def test_free_tool_executes(self):
        with TemporaryDirectory() as tmpdir:
            router = RouterMCP("test", Path(tmpdir))
            router.register_child(MockChild("alpha"))
            result = _run(router._dispatch("alpha_free_tool", {"value": 42}))
            data = _loads(result[0].text)
            assert data["result"] == "ok"
            meta = data["_meta"]
            assert meta["tier"] == 1
            # Provenance stamps: package version, tool name, UTC timestamp.
            # These let any downstream consumer (a vault note, a paper
            # appendix) trace a result back to the exact code version.
            import tailor
            assert meta["package_version"] == tailor.__version__
            assert meta["tool_name"] == "alpha_free_tool"
            assert meta["called_at"].endswith("+00:00")
            router.close()

    def test_invalid_params_rejected(self):
        with TemporaryDirectory() as tmpdir:
            router = RouterMCP("test", Path(tmpdir))
            router.register_child(MockChild("alpha"))
            result = _run(router._dispatch("alpha_free_tool", {}))
            data = _loads(result[0].text)
            assert "error" in data
            router.close()

    def test_unknown_tool_rejected(self):
        with TemporaryDirectory() as tmpdir:
            router = RouterMCP("test", Path(tmpdir))
            result = _run(router._dispatch("nonexistent", {}))
            data = _loads(result[0].text)
            assert "Unknown tool" in data["error"]
            router.close()


class TestTier2ConsentGate:
    """Tier 2 tools require domain-scoped consent."""

    def test_blocked_without_consent(self):
        with TemporaryDirectory() as tmpdir:
            router = RouterMCP("test", Path(tmpdir))
            router.register_child(MockChild("alpha"))
            result = _run(router._dispatch("alpha_gated_tool", {"value": 1}))
            data = _loads(result[0].text)
            assert data["gate"] == "consent_required"
            assert data["domain"] == "alpha"
            router.close()

    def test_passes_after_consent(self):
        with TemporaryDirectory() as tmpdir:
            router = RouterMCP("test", Path(tmpdir))
            router.register_child(MockChild("alpha"))
            # Approve consent
            _run(router._dispatch("approve_consent_alpha", {}))
            # Now tool should work
            result = _run(router._dispatch("alpha_gated_tool", {"value": 1}))
            data = _loads(result[0].text)
            assert data["result"] == "ok"
            router.close()

    def test_consent_is_per_domain(self):
        with TemporaryDirectory() as tmpdir:
            router = RouterMCP("test", Path(tmpdir))
            router.register_child(MockChild("alpha"))
            router.register_child(MockChild("beta"))
            # Approve alpha only
            _run(router._dispatch("approve_consent_alpha", {}))
            # Alpha gated works
            r1 = _run(router._dispatch("alpha_gated_tool", {"value": 1}))
            assert _loads(r1[0].text)["result"] == "ok"
            # Beta gated blocked
            r2 = _run(router._dispatch("beta_gated_tool", {"value": 1}))
            assert _loads(r2[0].text)["gate"] == "consent_required"
            router.close()


class TestTier3CostGate:
    """Tier 3 tools check cost and gate if expensive."""

    def test_cheap_passes_through(self):
        with TemporaryDirectory() as tmpdir:
            router = RouterMCP("test", Path(tmpdir), cost_threshold=35_000)
            router.register_child(MockChild("alpha", cost=1000))
            _run(router._dispatch("approve_consent_alpha", {}))
            result = _run(router._dispatch("alpha_expensive_tool", {"value": 1}))
            data = _loads(result[0].text)
            assert data["result"] == "ok"
            router.close()

    def test_expensive_triggers_gate(self):
        with TemporaryDirectory() as tmpdir:
            router = RouterMCP("test", Path(tmpdir), cost_threshold=35_000)
            router.register_child(MockChild("alpha", cost=50_000))
            _run(router._dispatch("approve_consent_alpha", {}))
            result = _run(router._dispatch("alpha_expensive_tool", {"value": 1}))
            data = _loads(result[0].text)
            assert data["gate"] == "cost_approval_required"
            assert data["options"]["full"]["tokens"] == 50_000
            assert "downsampled" in data["options"]
            router.close()


class TestCircuitBreakerIntegration:
    """Circuit breaker trips after repeated failures."""

    def test_trips_after_failures(self):
        with TemporaryDirectory() as tmpdir:
            router = RouterMCP(
                "test", Path(tmpdir), circuit_threshold=2, circuit_reset=60
            )
            router.register_child(MockFailingChild("alpha"))
            # Two failures should trip the breaker
            _run(router._dispatch("alpha_free_tool", {"value": 1}))
            _run(router._dispatch("alpha_free_tool", {"value": 1}))
            # Third call should be blocked by circuit breaker
            result = _run(router._dispatch("alpha_free_tool", {"value": 1}))
            data = _loads(result[0].text)
            assert "Circuit open" in data["error"]
            router.close()


class TestConsentApproval:
    """Dynamic consent approval tools."""

    def test_approve_known_domain(self):
        with TemporaryDirectory() as tmpdir:
            router = RouterMCP("test", Path(tmpdir))
            router.register_child(MockChild("alpha"))
            result = _run(router._dispatch("approve_consent_alpha", {}))
            data = _loads(result[0].text)
            assert data["approved"] is True
            assert data["domain"] == "alpha"
            router.close()

    def test_approve_unknown_domain(self):
        with TemporaryDirectory() as tmpdir:
            router = RouterMCP("test", Path(tmpdir))
            result = _run(router._dispatch("approve_consent_unknown", {}))
            data = _loads(result[0].text)
            assert "error" in data
            router.close()


class TestVaultLayerIntegration:
    """VaultLayer registration and dispatch bypass of consent/cost gates."""

    def _setup(self, tmpdir, backfill_config=None):
        """Register a router + one child + a vault layer pointing at tmp dirs."""
        from tailor.framework.vault import VaultLayer, VaultWriter
        root = Path(tmpdir)
        vault_path = root / "vault"
        vault_path.mkdir()
        data_dir = root / "data"
        data_dir.mkdir()

        router = RouterMCP("test", data_dir)
        router.register_child(MockChild("alpha"))

        writer = VaultWriter(
            vault_path=vault_path,
            data_dir=data_dir,
            vaultable_tools=set(),
            max_hr=195,
        )
        layer = VaultLayer(vault_path, writer, backfill_config=backfill_config)
        router.register_vault_layer(layer)
        return router, layer

    def test_register_vault_layer_adds_tools(self):
        with TemporaryDirectory() as tmpdir:
            router, _ = self._setup(tmpdir)
            assert "vault_list_notes" in router.registered_tools
            assert "vault_get_fitness_summary" in router.registered_tools
            router.close()

    def test_vault_not_in_registered_domains(self):
        """Vault is infrastructure, not a biosensor domain."""
        with TemporaryDirectory() as tmpdir:
            router, _ = self._setup(tmpdir)
            assert "vault" not in router.registered_domains
            assert "alpha" in router.registered_domains
            router.close()

    def test_no_consent_tools_for_vault(self):
        """approve_consent_vault should not be a valid domain (vault isn't in _children)."""
        with TemporaryDirectory() as tmpdir:
            router, _ = self._setup(tmpdir)
            # The consent handler only recognizes domains in _children.
            # Since vault is no longer a child, approve_consent_vault should fail.
            result = _run(router._dispatch("approve_consent_vault", {}))
            data = _loads(result[0].text)
            assert "error" in data
            assert "Unknown domain" in data["error"]
            # But child consent still works
            result2 = _run(router._dispatch("approve_consent_alpha", {}))
            data2 = _loads(result2[0].text)
            assert data2.get("approved") is True
            router.close()

    def test_vault_tool_dispatch_skips_consent(self):
        """Vault tools should execute without consent approval."""
        with TemporaryDirectory() as tmpdir:
            router, _ = self._setup(tmpdir)
            # No approve_consent_vault call — should still work
            result = _run(router._dispatch("vault_list_notes", {}))
            data = _loads(result[0].text)
            assert "error" not in data
            meta = data["_meta"]
            assert meta["domain"] == "vault"
            # Provenance stamps apply to vault dispatch too.
            import tailor
            assert meta["package_version"] == tailor.__version__
            assert meta["tool_name"] == "vault_list_notes"
            assert "called_at" in meta
            router.close()

    def test_vault_tool_validates_params(self):
        """Bad params are still rejected (param validation remains)."""
        with TemporaryDirectory() as tmpdir:
            router, _ = self._setup(tmpdir)
            # vault_read_note requires filename
            result = _run(router._dispatch("vault_read_note", {}))
            data = _loads(result[0].text)
            assert "error" in data
            router.close()

    def test_duplicate_vault_registration_rejected(self):
        with TemporaryDirectory() as tmpdir:
            router, layer = self._setup(tmpdir)
            with pytest.raises(ValueError, match="already registered"):
                router.register_vault_layer(layer)
            router.close()

    def test_vault_tool_cannot_be_called_internally(self):
        """dispatch_internal should reject vault tools."""
        with TemporaryDirectory() as tmpdir:
            router, _ = self._setup(tmpdir)
            result = _run(router.dispatch_internal("vault_list_notes", {}))
            assert "error" in result
            assert "internally" in result["error"].lower()
            router.close()


class TestVaultCaptureSessionIntegration:
    """
    End-to-end smoke for `vault_capture_session`:
      * One audit row per invocation (router records outer call only).
      * Summary moment + theme updates both land on disk.
      * Session state survives router close/reopen (fresh session sim).
      * Manual Obsidian edits to a theme file surface via vault_read_theme.
    """

    def _setup(self, tmpdir):
        from tailor.framework.vault import VaultLayer, VaultWriter
        root = Path(tmpdir)
        vault_path = root / "vault"
        vault_path.mkdir()
        data_dir = root / "data"
        data_dir.mkdir()

        router = RouterMCP("test", data_dir)
        router.register_child(MockChild("alpha"))
        writer = VaultWriter(
            vault_path=vault_path,
            data_dir=data_dir,
            vaultable_tools=set(),
            max_hr=195,
        )
        layer = VaultLayer(vault_path, writer)
        router.register_vault_layer(layer)
        return router, layer, vault_path, data_dir

    def test_single_audit_row_for_session_capture(self):
        import sqlite3
        with TemporaryDirectory() as tmpdir:
            router, _, vault_path, data_dir = self._setup(tmpdir)
            try:
                result = _run(router._dispatch("vault_capture_session", {
                    "summary": {
                        "title": "Weekly review",
                        "body": "Worked through drift hypothesis on Tue + Thu.",
                        "date": "2026-04-10",
                    },
                    "update_themes": [
                        {"slug": "drift", "hypothesis": "Drift on hot days.",
                         "evidence": "Mile 6 on 4/10: +8bpm."},
                    ],
                    "new_moments": [
                        {"title": "Thursday sub-observation",
                         "body": "Noted cooldown HR oddity.",
                         "date": "2026-04-10"},
                    ],
                }))
                data = _loads(result[0].text)
                assert data["summary_filename"] is not None
                assert len(data["theme_updates"]) == 1
                assert len(data["moment_filenames"]) == 1
                assert data["errors"] == []

                # Files must actually exist on disk
                assert (vault_path / data["summary_filename"]).exists()
                assert (vault_path / "themes/drift.md").exists()

                # Exactly one audit row for the outer call
                conn = sqlite3.connect(str(data_dir / "audit.db"))
                rows = conn.execute(
                    "SELECT tool_name, outcome FROM audit_log"
                    " WHERE tool_name='vault_capture_session'"
                ).fetchall()
                conn.close()
                assert len(rows) == 1
                assert rows[0] == ("vault_capture_session", "SUCCESS")
            finally:
                router.close()

    def test_fresh_session_surfaces_previous_moment(self):
        """Capture moment → close router → reopen → fitness summary sees it."""
        with TemporaryDirectory() as tmpdir:
            from tailor.framework.vault import VaultLayer, VaultWriter
            root = Path(tmpdir)
            vault_path = root / "vault"
            vault_path.mkdir()
            data_dir = root / "data"
            data_dir.mkdir()

            # --- Session 1: write a moment ---
            router1 = RouterMCP("test", data_dir)
            writer1 = VaultWriter(vault_path, data_dir, vaultable_tools=set())
            layer1 = VaultLayer(vault_path, writer1)
            router1.register_vault_layer(layer1)
            try:
                r = _run(router1._dispatch("vault_capture_moment", {
                    "title": "Tuesday Aha",
                    "body": "Drift explained by hydration.",
                    "date": "2026-04-10",
                }))
                assert "error" not in _loads(r[0].text)
            finally:
                router1.close()

            # --- Session 2: new router instance, same vault/data dirs ---
            router2 = RouterMCP("test", data_dir)
            writer2 = VaultWriter(vault_path, data_dir, vaultable_tools=set())
            layer2 = VaultLayer(vault_path, writer2)
            router2.register_vault_layer(layer2)
            try:
                r2 = _run(router2._dispatch("vault_get_fitness_summary", {}))
                data = _loads(r2[0].text)
                assert "recent_moments" in data
                assert any(m["title"] == "Tuesday Aha" for m in data["recent_moments"])
            finally:
                router2.close()

    def test_manual_obsidian_edit_surfaces_on_read(self):
        """Overwrite the theme file on disk → vault_read_theme reflects new text."""
        import os
        import time
        with TemporaryDirectory() as tmpdir:
            router, _, vault_path, _data_dir = self._setup(tmpdir)
            try:
                _run(router._dispatch("vault_upsert_theme", {
                    "slug": "drift",
                    "hypothesis": "Original prose.",
                }))
                path = vault_path / "themes/drift.md"
                replaced = path.read_text(encoding="utf-8").replace(
                    "Original prose.", "Hand-edited in Obsidian."
                )
                path.write_text(replaced, encoding="utf-8")
                future = time.time_ns() + 10_000_000_000
                os.utime(path, ns=(future, future))

                r = _run(router._dispatch("vault_read_theme", {"slug": "drift"}))
                data = _loads(r[0].text)
                assert "Hand-edited in Obsidian." in data["content"]
            finally:
                router.close()


class TestSubjectIdAuditScoping:
    """
    ``subject_id`` lifted into the audit log lets any analysis scope rows
    to a study participant or cohort. Existing children that don't pass
    one still work (the column stays NULL).
    """

    def test_subject_id_threaded_through_to_audit_row(self):
        import sqlite3
        with TemporaryDirectory() as tmpdir:
            router = RouterMCP("test", Path(tmpdir))
            router.register_child(MockChild("alpha"))
            _run(router._dispatch(
                "alpha_free_tool", {"value": 7, "subject_id": "P042"}
            ))
            router.close()
            conn = sqlite3.connect(str(Path(tmpdir) / "audit.db"))
            try:
                rows = conn.execute(
                    "SELECT tool_name, outcome, subject_id FROM audit_log"
                ).fetchall()
            finally:
                conn.close()
        assert rows == [("alpha_free_tool", "SUCCESS", "P042")]

    def test_subject_id_absent_leaves_column_null(self):
        import sqlite3
        with TemporaryDirectory() as tmpdir:
            router = RouterMCP("test", Path(tmpdir))
            router.register_child(MockChild("alpha"))
            _run(router._dispatch("alpha_free_tool", {"value": 7}))
            router.close()
            conn = sqlite3.connect(str(Path(tmpdir) / "audit.db"))
            try:
                rows = conn.execute(
                    "SELECT subject_id FROM audit_log"
                ).fetchall()
            finally:
                conn.close()
        assert rows == [(None,)]

    def test_subject_id_invalid_pattern_audits_as_param_invalid(self):
        """
        When a child declares a ``subject_id`` pattern (as RunningChild
        now does, per ADR 0002), a malformed value is rejected at
        validation. The audit row must still capture the submitted
        ``subject_id`` so an IRB reviewer can see on whose behalf the
        (rejected) call was allegedly made. The router extracts
        ``subject_id`` pre-validation precisely for this reason
        (router.py:305).
        """
        import sqlite3

        class ChildWithSubjectIdSchema(MockChild):
            @property
            def param_schemas(self) -> dict:
                return {
                    f"{self._domain}_free_tool": {
                        "value": ValidationSchema(type=int, min=1, required=True),
                        "subject_id": ValidationSchema(
                            type=str,
                            required=False,
                            pattern=r"^[A-Za-z0-9_\-]{1,64}$",
                        ),
                    },
                }

            @property
            def tool_definitions(self) -> list[ToolDefinition]:
                return [
                    ToolDefinition(
                        f"{self._domain}_free_tool", 1,
                        "A free tool for testing.",
                        {
                            "value": {"type": "integer", "description": "A value", "required": True},
                            "subject_id": {"type": "string", "description": "Subject", "required": False},
                        },
                    ),
                ]

        with TemporaryDirectory() as tmpdir:
            router = RouterMCP("test", Path(tmpdir))
            router.register_child(ChildWithSubjectIdSchema("alpha"))
            result = _run(router._dispatch(
                "alpha_free_tool", {"value": 7, "subject_id": "bad;value"},
            ))
            router.close()
            # Validation rejected the call.
            err_data = _loads(result[0].text)
            assert err_data.get("error"), "expected error payload on rejection"

            conn = sqlite3.connect(str(Path(tmpdir) / "audit.db"))
            try:
                rows = conn.execute(
                    "SELECT tool_name, outcome, subject_id FROM audit_log"
                ).fetchall()
            finally:
                conn.close()
        assert rows == [("alpha_free_tool", "PARAM_INVALID", "bad;value")]


class TestPHIScrubberSeam:
    """
    The router runs PHIScrubber.scrub() on every successful child result
    before tokens are counted, the row is audited, or post-execute hooks
    fire. Default is a no-op; a subclass can override to actually strip
    fields.
    """

    def test_default_scrubber_leaves_result_untouched(self):
        with TemporaryDirectory() as tmpdir:
            router = RouterMCP("test", Path(tmpdir))
            router.register_child(MockChild("alpha"))
            r = _run(router._dispatch("alpha_free_tool", {"value": 1}))
            data = _loads(r[0].text)
            assert data["result"] == "ok"
            assert data["tool"] == "alpha_free_tool"
            router.close()

    def test_subclass_scrubber_mutates_response(self):
        from tailor.framework.security import PHIScrubber

        class DropParamsScrubber(PHIScrubber):
            def scrub(self, result: dict) -> dict:
                # Drop everything except the outcome marker so we can prove
                # the scrubber actually ran.
                return {"result": result.get("result")}

        with TemporaryDirectory() as tmpdir:
            router = RouterMCP("test", Path(tmpdir))
            router.register_child(MockChild("alpha"))
            router._phi_scrubber = DropParamsScrubber()
            r = _run(router._dispatch("alpha_free_tool", {"value": 1}))
            data = _loads(r[0].text)
            assert data["result"] == "ok"
            assert "params" not in data  # scrubbed
            assert "tool" not in data    # scrubbed
            router.close()


class TestPHIScrubberAuditStamp:
    """
    Closes the ADR 0003 doc-lie: the documentation has claimed since v5
    that ``scrubber_id`` is recorded in audit rows so a misconfigured
    deployment running the no-op default is distinguishable from one
    running an institutional subclass. Until v6.2 the property existed
    on PHIScrubber but the router never read it. These tests pin the
    wire-up.
    """

    def test_default_scrubber_stamps_noop_in_meta_and_audit(self):
        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            router = RouterMCP("test", data_dir)
            try:
                router.register_child(MockChild("alpha"))
                r = _run(router._dispatch("alpha_free_tool", {"value": 1}))
                data = _loads(r[0].text)
                assert data["_meta"]["scrubber_id"] == "noop"

                # Audit row carries the same value
                import sqlite3
                conn = sqlite3.connect(str(data_dir / "audit.db"))
                try:
                    rows = conn.execute(
                        "SELECT scrubber_id FROM audit_log "
                        "WHERE outcome = 'SUCCESS' ORDER BY id DESC LIMIT 1"
                    ).fetchall()
                finally:
                    conn.close()
                assert rows == [("noop",)]
            finally:
                router.close()

    def test_subclass_scrubber_stamps_class_name(self):
        from tailor.framework.security import PHIScrubber

        class HIPAASafeHarborScrubber(PHIScrubber):
            def scrub(self, result: dict) -> dict:
                return result

        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            router = RouterMCP("test", data_dir)
            try:
                router.register_child(MockChild("alpha"))
                router._phi_scrubber = HIPAASafeHarborScrubber()
                r = _run(router._dispatch("alpha_free_tool", {"value": 1}))
                data = _loads(r[0].text)
                assert data["_meta"]["scrubber_id"] == "HIPAASafeHarborScrubber"

                import sqlite3
                conn = sqlite3.connect(str(data_dir / "audit.db"))
                try:
                    (sid,) = conn.execute(
                        "SELECT scrubber_id FROM audit_log "
                        "WHERE outcome = 'SUCCESS' ORDER BY id DESC LIMIT 1"
                    ).fetchone()
                finally:
                    conn.close()
                assert sid == "HIPAASafeHarborScrubber"
            finally:
                router.close()


class TestDispatchInternalProvenance:
    """
    Internal cross-child calls (used by vault backfill) must carry the
    same provenance stamps as Claude-facing calls. Otherwise vault notes
    written by backfill would be untraceable.

    v6.4.1 expanded coverage: every error branch on this path must be
    audit-row-tested too, because vault backfill goes through here and
    a silent ERROR on the backfill path would write a vault note with
    no audit trace of why it was empty.
    """

    def test_dispatch_internal_stamps_meta(self):
        with TemporaryDirectory() as tmpdir:
            router = RouterMCP("test", Path(tmpdir))
            try:
                router.register_child(MockChild("alpha"))
                result = _run(router.dispatch_internal(
                    "alpha_free_tool", {"value": 7}
                ))
                assert "_meta" in result
                meta = result["_meta"]
                import tailor
                assert meta["package_version"] == tailor.__version__
                assert meta["tool_name"] == "alpha_free_tool"
                assert meta["source"] == "INTERNAL"
            finally:
                router.close()

    def test_dispatch_internal_unknown_tool(self):
        with TemporaryDirectory() as tmpdir:
            router = RouterMCP("test", Path(tmpdir))
            try:
                router.register_child(MockChild("alpha"))
                result = _run(router.dispatch_internal("nope", {}))
                assert "error" in result
                assert "Unknown tool" in result["error"]
            finally:
                router.close()

    def test_dispatch_internal_rejects_vault_tools(self):
        """Vault tools are LLM-facing; calling them via internal dispatch
        would bypass the documented vault-dispatch path and ADR 0012's
        invariants."""
        from tailor.framework.vault import VaultLayer, VaultWriter
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            vault_root = root / "vault"
            vault_root.mkdir()
            data_dir = root / "data"
            data_dir.mkdir()
            router = RouterMCP("test", data_dir)
            try:
                router.register_child(MockChild("alpha"))
                writer = VaultWriter(vault_path=vault_root, data_dir=data_dir,
                                     vaultable_tools=set(), max_hr=195)
                router.register_vault_layer(VaultLayer(vault_root, writer))
                result = _run(router.dispatch_internal("vault_list_notes", {}))
                assert "error" in result
                assert "cannot be called internally" in result["error"]
            finally:
                router.close()

    def test_dispatch_internal_param_invalid_writes_audit_row(self):
        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            router = RouterMCP("test", data_dir)
            try:
                router.register_child(MockChild("alpha"))
                # alpha_free_tool requires value: int, min=1; sending None.
                result = _run(router.dispatch_internal(
                    "alpha_free_tool", {"value": None}
                ))
                assert "error" in result
                import sqlite3
                conn = sqlite3.connect(str(data_dir / "audit.db"))
                try:
                    (outcome,) = conn.execute(
                        "SELECT outcome FROM audit_log "
                        "WHERE tool_name='alpha_free_tool' "
                        "ORDER BY id DESC LIMIT 1"
                    ).fetchone()
                finally:
                    conn.close()
                assert outcome == "PARAM_INVALID_INTERNAL"
            finally:
                router.close()

    def test_dispatch_internal_circuit_open_writes_audit_row(self):
        """Trip the circuit breaker on the public path, then verify
        the internal path observes it."""
        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            router = RouterMCP("test", data_dir)
            try:
                router.register_child(MockFailingChild("alpha"))
                # Trip the breaker — 3 consecutive failures.
                for _ in range(3):
                    _run(router._dispatch("alpha_free_tool", {"value": 1}))
                result = _run(router.dispatch_internal(
                    "alpha_free_tool", {"value": 1}
                ))
                assert "error" in result
                import sqlite3
                conn = sqlite3.connect(str(data_dir / "audit.db"))
                try:
                    (outcome,) = conn.execute(
                        "SELECT outcome FROM audit_log "
                        "WHERE tool_name='alpha_free_tool' AND outcome LIKE '%INTERNAL' "
                        "ORDER BY id DESC LIMIT 1"
                    ).fetchone()
                finally:
                    conn.close()
                assert outcome == "CIRCUIT_OPEN_INTERNAL"
            finally:
                router.close()

    def test_dispatch_internal_consent_blocked_for_tier2(self):
        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            router = RouterMCP("test", data_dir)
            try:
                router.register_child(MockChild("alpha"))
                # No approve_consent_alpha — Tier 2 should block.
                result = _run(router.dispatch_internal(
                    "alpha_gated_tool", {"value": 1}
                ))
                assert "error" in result
                assert "Consent not approved" in result["error"]
                import sqlite3
                conn = sqlite3.connect(str(data_dir / "audit.db"))
                try:
                    (outcome,) = conn.execute(
                        "SELECT outcome FROM audit_log "
                        "WHERE tool_name='alpha_gated_tool' "
                        "ORDER BY id DESC LIMIT 1"
                    ).fetchone()
                finally:
                    conn.close()
                assert outcome == "CONSENT_BLOCKED_INTERNAL"
            finally:
                router.close()

    def test_dispatch_internal_cost_estimate_error_fails_closed(self):
        """A child whose estimate_cost raises must NOT slip past the
        cost gate with a synthetic 0-token estimate. ADR 0005 invariant
        on the internal dispatch path."""
        class CostBrokenChild(MockChild):
            async def estimate_cost(self, tool_name, params):
                raise RuntimeError("simulated estimator crash")

        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            router = RouterMCP("test", data_dir, cost_threshold=35_000)
            try:
                router.register_child(CostBrokenChild("alpha"))
                _run(router._dispatch("approve_consent_alpha", {}))
                result = _run(router.dispatch_internal(
                    "alpha_expensive_tool", {"value": 1}
                ))
                assert "error" in result
                assert "estimate" in result["error"].lower()
                import sqlite3
                conn = sqlite3.connect(str(data_dir / "audit.db"))
                try:
                    (outcome,) = conn.execute(
                        "SELECT outcome FROM audit_log "
                        "WHERE tool_name='alpha_expensive_tool' "
                        "ORDER BY id DESC LIMIT 1"
                    ).fetchone()
                finally:
                    conn.close()
                assert outcome == "COST_ESTIMATE_ERROR_INTERNAL"
            finally:
                router.close()

    def test_dispatch_internal_cost_gate_blocks_over_threshold(self):
        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            router = RouterMCP("test", data_dir, cost_threshold=35_000)
            try:
                router.register_child(MockChild("alpha", cost=50_000))
                _run(router._dispatch("approve_consent_alpha", {}))
                result = _run(router.dispatch_internal(
                    "alpha_expensive_tool", {"value": 1}
                ))
                assert "error" in result
                assert "Cost gate" in result["error"]
                import sqlite3
                conn = sqlite3.connect(str(data_dir / "audit.db"))
                try:
                    (outcome,) = conn.execute(
                        "SELECT outcome FROM audit_log "
                        "WHERE tool_name='alpha_expensive_tool' "
                        "ORDER BY id DESC LIMIT 1"
                    ).fetchone()
                finally:
                    conn.close()
                assert outcome == "COST_GATE_INTERNAL"
            finally:
                router.close()

    def test_dispatch_internal_execute_exception_writes_audit_row(self):
        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            router = RouterMCP("test", data_dir)
            try:
                router.register_child(MockFailingChild("alpha"))
                result = _run(router.dispatch_internal(
                    "alpha_free_tool", {"value": 1}
                ))
                assert "error" in result
                assert "Simulated failure" in result["error"]
                import sqlite3
                conn = sqlite3.connect(str(data_dir / "audit.db"))
                try:
                    (outcome,) = conn.execute(
                        "SELECT outcome FROM audit_log "
                        "WHERE tool_name='alpha_free_tool' "
                        "ORDER BY id DESC LIMIT 1"
                    ).fetchone()
                finally:
                    conn.close()
                assert outcome == "ERROR_INTERNAL"
            finally:
                router.close()

    def test_dispatch_internal_threads_subject_id_into_audit_row(self):
        """ADR 0009 invariant on the internal dispatch path: vault
        backfill calls children through dispatch_internal carrying a
        subject_id; the audit row must record it so a multi-subject
        retrospective can answer "which participant did this backfill
        touch?". Until v6.4.1 no test asserted this — the red-team
        v6.4.1 secondary finding."""
        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            router = RouterMCP("test", data_dir)
            try:
                router.register_child(MockChild("alpha"))
                _run(router.dispatch_internal(
                    "alpha_free_tool",
                    {"value": 1, "subject_id": "P007"},
                ))
                import sqlite3
                conn = sqlite3.connect(str(data_dir / "audit.db"))
                try:
                    (sid,) = conn.execute(
                        "SELECT subject_id FROM audit_log "
                        "WHERE tool_name='alpha_free_tool' "
                        "ORDER BY id DESC LIMIT 1"
                    ).fetchone()
                finally:
                    conn.close()
                assert sid == "P007", (
                    "subject_id must propagate from params into the "
                    "INTERNAL audit row (ADR 0009); vault backfill "
                    "subject-keying depends on this"
                )
            finally:
                router.close()

    def test_dispatch_internal_phi_scrub_seam_fires(self):
        """Internal cross-child calls (vault backfill) must traverse the
        same PHI-scrub seam as Claude-facing calls. Otherwise vault notes
        written by backfill would carry an un-scrubbed view."""
        from tailor.framework.security import PHIScrubber

        class StripIdScrubber(PHIScrubber):
            def scrub(self, result):
                result.pop("params", None)  # simulate stripping a field
                return result

        with TemporaryDirectory() as tmpdir:
            router = RouterMCP("test", Path(tmpdir))
            try:
                router.register_child(MockChild("alpha"))
                router._phi_scrubber = StripIdScrubber()
                result = _run(router.dispatch_internal(
                    "alpha_free_tool", {"value": 1}
                ))
                assert "params" not in result, (
                    "PHI-scrubber must run on dispatch_internal too — "
                    "ADR 0003 invariant on the cross-child path"
                )
                assert result["_meta"]["scrubber_id"] == "StripIdScrubber"
            finally:
                router.close()
            router.close()


class TestRunningChildEndToEnd:
    """
    End-to-end dispatch of the canonical Tier-1 tool against synthetic
    run data. Until this class was added, no test pushed a realistic
    report dict through ``_dispatch``: unit tests hit compute_* functions
    directly, and the router tests used a MockChild that returned
    string-keyed dicts. That left the orjson strict-key behaviour
    (``compute_hr_zones`` keyes by zone int 1..5) undetected — every
    real strava_run_report call failed with ``{"error": "Dict key must
    be str"}`` and was audited as ERROR.

    These tests are the floor: every supported Tier-1 tool must return
    a usable dict through the full router pipeline, on every supported
    JSON backend.
    """

    @staticmethod
    def _seeded_router(tmpdir: str) -> tuple[RouterMCP, int]:
        """Build a router with a RunningChild pre-seeded with one synthetic run."""
        import json

        from tailor.children.running import RunningChild
        from tailor.demo.sample_data import (
            SAMPLE_ACTIVITY_ID,
            generate_sample_activity,
            generate_sample_streams,
        )

        config_dir = Path(tmpdir) / "config"
        data_dir = Path(tmpdir) / "data"
        config_dir.mkdir()
        data_dir.mkdir()
        (config_dir / "user_config.json").write_text(
            json.dumps({"max_hr": 185, "resting_hr": 52})
        )
        (config_dir / "tokens.json").write_text(json.dumps({
            "client_id": "demo", "client_secret": "demo",
            "access_token": "demo", "refresh_token": "demo", "expires_at": 0,
        }))

        router = RouterMCP("e2e-test", data_dir)
        child = RunningChild(config_dir=config_dir, data_dir=data_dir)
        router.register_child(child)
        child._storage.save_activity(SAMPLE_ACTIVITY_ID, generate_sample_activity())
        child._storage.save_streams(SAMPLE_ACTIVITY_ID, generate_sample_streams())
        return router, SAMPLE_ACTIVITY_ID

    def test_strava_run_report_roundtrips_through_dispatch(self):
        with TemporaryDirectory() as tmpdir:
            router, activity_id = self._seeded_router(tmpdir)
            try:
                chunks = _run(router._dispatch(
                    "strava_run_report", {"activity_id": activity_id}
                ))
                result = _loads(chunks[0].text)
            finally:
                router.close()

        # The serialization bug surfaced as {"error": "Dict key must be str"}.
        assert "error" not in result, f"dispatch failed: {result.get('error')}"
        assert result["activity_id"] == activity_id

        # hr_zones is the canonical int-keyed dict. Orjson coerces keys to
        # strings; stdlib does the same. Accept either — what matters is
        # that the call succeeded and the zone rollup is present.
        assert "hr_zones" in result
        zone_seconds = result["hr_zones"]["zone_seconds"]
        assert sum(zone_seconds.values()) > 0

        # _meta is unconditional on success.
        assert result["_meta"]["tool_name"] == "strava_run_report"
        assert result["_meta"]["tier"] == 1

    def test_strava_run_report_audit_row_is_success_not_error(self):
        """The bug audited the call as ERROR while returning an error dict."""
        import sqlite3

        with TemporaryDirectory() as tmpdir:
            router, activity_id = self._seeded_router(tmpdir)
            data_dir = router.data_dir
            try:
                _run(router._dispatch(
                    "strava_run_report", {"activity_id": activity_id}
                ))
            finally:
                router.close()

            conn = sqlite3.connect(str(data_dir / "audit.db"))
            try:
                (outcome,) = conn.execute(
                    "SELECT outcome FROM audit_log "
                    "WHERE tool_name = 'strava_run_report' "
                    "ORDER BY id DESC LIMIT 1"
                ).fetchone()
            finally:
                conn.close()

        assert outcome == "SUCCESS", (
            f"expected SUCCESS, got {outcome!r} — indicates the tool "
            f"raised inside the router's pipeline"
        )


class TestConsentHandlerScrubberIdAuditStamp:
    """
    Regression coverage for v6.3.1 hygiene-pass finding: until v6.3.1 the
    ``approve_consent_*`` and ``revoke_consent_*`` handlers wrote audit
    rows with NULL ``scrubber_id``, breaking the ADR 0003 promise that
    every audit row carries scrubber identity. The two timeline-anchor
    rows (when consent was granted / revoked) were the only ones in
    audit.db that did not distinguish a real-PHI-policy deployment from
    the no-op default.
    """

    def test_approve_consent_audit_row_carries_scrubber_id(self):
        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            router = RouterMCP("test", data_dir)
            try:
                router.register_child(MockChild("alpha"))
                _run(router._dispatch("approve_consent_alpha", {}))

                import sqlite3
                conn = sqlite3.connect(str(data_dir / "audit.db"))
                try:
                    (sid,) = conn.execute(
                        "SELECT scrubber_id FROM audit_log "
                        "WHERE tool_name = 'approve_consent_alpha' "
                        "ORDER BY id DESC LIMIT 1"
                    ).fetchone()
                finally:
                    conn.close()
                assert sid == "noop", (
                    "approve_consent_* audit row must carry scrubber_id "
                    "(ADR 0003); got NULL/None means the consent timeline "
                    "rows are indistinguishable between scrubbed and "
                    "no-op deployments."
                )
            finally:
                router.close()

    def test_revoke_consent_audit_row_carries_scrubber_id(self):
        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            router = RouterMCP("test", data_dir)
            try:
                router.register_child(MockChild("alpha"))
                _run(router._dispatch("approve_consent_alpha", {}))
                _run(router._dispatch("revoke_consent_alpha", {}))

                import sqlite3
                conn = sqlite3.connect(str(data_dir / "audit.db"))
                try:
                    (sid,) = conn.execute(
                        "SELECT scrubber_id FROM audit_log "
                        "WHERE tool_name = 'revoke_consent_alpha' "
                        "ORDER BY id DESC LIMIT 1"
                    ).fetchone()
                finally:
                    conn.close()
                assert sid == "noop"
            finally:
                router.close()


class TestNoopScrubberWarningSurfacedInMeta:
    """
    Regression coverage for v6.3.1 hygiene-pass finding: stderr warnings
    on default-scrubber construction are swallowed by Claude Desktop's
    spawned-subprocess process model. ADR 0003 promised the no-op
    default surfaces "loudly" — but no analyst reads the rolling log.
    The fix surfaces the warning into every successful ``_meta`` block
    so the LLM transcript itself shows the misconfiguration, satisfying
    ADR 0003 in any deployment shape.
    """

    def test_default_scrubber_emits_warning_in_meta(self):
        with TemporaryDirectory() as tmpdir:
            router = RouterMCP("test", Path(tmpdir))
            try:
                router.register_child(MockChild("alpha"))
                r = _run(router._dispatch("alpha_free_tool", {"value": 1}))
                data = _loads(r[0].text)
                assert "scrubber_warning" in data["_meta"], (
                    "default PHIScrubber must surface its warning into "
                    "_meta so the LLM transcript shows the no-op state"
                )
                assert "no-op" in data["_meta"]["scrubber_warning"]
                assert "ADR 0003" in data["_meta"]["scrubber_warning"]
            finally:
                router.close()

    def test_subclass_scrubber_omits_warning_from_meta(self):
        from tailor.framework.security import PHIScrubber

        class HIPAASafeHarborScrubber(PHIScrubber):
            def scrub(self, result: dict) -> dict:
                return result

        with TemporaryDirectory() as tmpdir:
            router = RouterMCP("test", Path(tmpdir))
            try:
                router.register_child(MockChild("alpha"))
                router._phi_scrubber = HIPAASafeHarborScrubber()
                r = _run(router._dispatch("alpha_free_tool", {"value": 1}))
                data = _loads(r[0].text)
                assert "scrubber_warning" not in data["_meta"], (
                    "subclass scrubbers must not stamp the no-op warning"
                )
            finally:
                router.close()

    def test_vault_dispatch_meta_carries_warning_under_default(self):
        """Vault path uses dict-merge syntax for the conditional add;
        prove it lands in the ``_meta`` block too."""
        from tailor.framework.vault import VaultLayer, VaultWriter
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            vault_root = root / "vault"
            vault_root.mkdir()
            data_dir = root / "data"
            data_dir.mkdir()
            router = RouterMCP("test", data_dir)
            try:
                router.register_child(MockChild("alpha"))
                writer = VaultWriter(
                    vault_path=vault_root,
                    data_dir=data_dir,
                    vaultable_tools=set(),
                    max_hr=195,
                )
                router.register_vault_layer(VaultLayer(vault_root, writer))
                r = _run(router._dispatch("vault_list_notes", {}))
                data = _loads(r[0].text)
                assert "scrubber_warning" in data["_meta"]
            finally:
                router.close()


class TestPurgeCacheOnConsentRevocation:
    """
    ADR 0013 — Cache-only purge on consent revocation.

    The IRB invariant is "revocation = no cache". Until v6.4.0
    ``ConsentGate.revoke()`` flipped an in-memory dict and left
    cached PHI on disk indefinitely. v6.4.0 wires
    ``child.purge_cache()`` into the revoke pipeline with fail-closed
    ordering: purge first, then flip consent. If purge raises,
    consent stays approved and the caller sees the error.
    """

    def test_revoke_triggers_purge_cache_and_writes_paired_audit_row(self):
        """Successful revocation produces both a PURGE_CACHE audit row
        AND a SUCCESS row for the revoke tool itself, both stamped
        with scrubber_id (ADR 0001 + ADR 0003 invariants paired)."""
        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            router = RouterMCP("test", data_dir)
            try:
                child = MockChild("alpha")
                router.register_child(child)
                _run(router._dispatch("approve_consent_alpha", {}))
                r = _run(router._dispatch("revoke_consent_alpha", {}))
                data = _loads(r[0].text)

                assert data["revoked"] is True
                assert "purge_result" in data
                assert getattr(child, "purge_count", 0) == 1, (
                    "child.purge_cache must be called exactly once "
                    "during a successful revocation"
                )

                import sqlite3
                conn = sqlite3.connect(str(data_dir / "audit.db"))
                try:
                    rows = conn.execute(
                        "SELECT tool_name, outcome, scrubber_id "
                        "FROM audit_log WHERE domain='alpha' "
                        "ORDER BY id"
                    ).fetchall()
                finally:
                    conn.close()
                tool_names = [r[0] for r in rows]
                outcomes = [r[1] for r in rows]
                scrubbers = [r[2] for r in rows]
                assert "purge_cache" in tool_names, (
                    "every successful revocation must produce a "
                    "PURGE_CACHE audit row per ADR 0013"
                )
                assert "PURGE_CACHE" in outcomes
                assert all(s == "noop" for s in scrubbers), (
                    "all revocation-path audit rows must carry "
                    "scrubber_id (ADR 0003)"
                )
            finally:
                router.close()

    def test_revoke_without_prior_approval_skips_purge(self):
        """Short-circuit when consent was never approved — calling
        purge on an empty cache is correct but unnecessary, and the
        absence of a PURGE_CACHE audit row keeps the trail honest."""
        with TemporaryDirectory() as tmpdir:
            router = RouterMCP("test", Path(tmpdir))
            try:
                child = MockChild("alpha")
                router.register_child(child)
                r = _run(router._dispatch("revoke_consent_alpha", {}))
                data = _loads(r[0].text)
                assert data["revoked"] is False
                assert getattr(child, "purge_count", 0) == 0, (
                    "purge must NOT be called when no consent was "
                    "previously approved — there's nothing to purge"
                )
            finally:
                router.close()

    def test_revoke_fails_closed_when_purge_raises(self):
        """Fail-closed: purge exception aborts revocation. Consent
        stays approved so the participant sees a loud signal that
        cleanup did not complete."""
        class PurgeFailingChild(MockChild):
            def purge_cache(self, *, force=False):
                raise OSError("simulated cache lock")

        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            router = RouterMCP("test", data_dir)
            try:
                child = PurgeFailingChild("alpha")
                router.register_child(child)
                _run(router._dispatch("approve_consent_alpha", {}))
                r = _run(router._dispatch("revoke_consent_alpha", {}))
                data = _loads(r[0].text)

                assert data["revoked"] is False
                assert "error" in data
                assert "fail-closed" in data["error"]
                assert router._consent.is_approved("alpha"), (
                    "fail-closed: consent must remain approved when "
                    "purge fails (per ADR 0013)"
                )

                import sqlite3
                conn = sqlite3.connect(str(data_dir / "audit.db"))
                try:
                    (outcome,) = conn.execute(
                        "SELECT outcome FROM audit_log "
                        "WHERE tool_name='revoke_consent_alpha' "
                        "ORDER BY id DESC LIMIT 1"
                    ).fetchone()
                finally:
                    conn.close()
                assert outcome == "PURGE_FAILED"
            finally:
                router.close()

    def test_force_revoke_swallows_purge_error(self):
        """Escape hatch: ``force_revoke=True`` revokes consent even
        when the cache file is locked by an external process. Used
        rarely — the audit row records that force was used."""
        class PurgeFailingChild(MockChild):
            def purge_cache(self, *, force=False):
                if not force:
                    raise OSError("simulated cache lock")
                return {
                    "rows_purged": 0, "tables_touched": [],
                    "preserved": [], "errors": ["simulated cache lock"],
                }

        with TemporaryDirectory() as tmpdir:
            router = RouterMCP("test", Path(tmpdir))
            try:
                router.register_child(PurgeFailingChild("alpha"))
                _run(router._dispatch("approve_consent_alpha", {}))
                r = _run(router._dispatch(
                    "revoke_consent_alpha", {"force_revoke": True}
                ))
                data = _loads(r[0].text)
                assert data["revoked"] is True
                assert not router._consent.is_approved("alpha")
            finally:
                router.close()

    def test_purge_result_lands_in_audit_row_for_irb_retrospective(self):
        """ADR 0013 § "Paired audit rows" claims the audit row carries
        the rows-purged count + any partial-failure errors so an IRB
        retrospective reading audit.db six months later can answer
        "was data actually purged on this revocation?" — and not just
        "was force_revoke flag passed?". Three v6.4.0 backstops (red-
        team, phi-irb, reproducibility) flagged this as a doc-vs-code
        gap pre-fix; this test pins the closure."""
        class PartialFailChild(MockChild):
            def purge_cache(self, *, force=False):
                # Simulates the "force=True swallows errors" path.
                return {
                    "rows_purged": 7,
                    "tables_touched": ["streams"],
                    "preserved": ["stop_labels"],
                    "errors": ["activities table locked"],
                }

        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            router = RouterMCP("test", data_dir)
            try:
                router.register_child(PartialFailChild("alpha"))
                _run(router._dispatch("approve_consent_alpha", {}))
                _run(router._dispatch(
                    "revoke_consent_alpha", {"force_revoke": True}
                ))

                import sqlite3
                conn = sqlite3.connect(str(data_dir / "audit.db"))
                try:
                    (params_json,) = conn.execute(
                        "SELECT params FROM audit_log "
                        "WHERE outcome='PURGE_CACHE' "
                        "ORDER BY id DESC LIMIT 1"
                    ).fetchone()
                finally:
                    conn.close()
                params = _loads(params_json)
                assert "purge_result" in params, (
                    "PURGE_CACHE audit row must carry the child's "
                    "purge_result so an IRB retrospective can "
                    "reconstruct what was purged (ADR 0013)"
                )
                assert params["purge_result"]["rows_purged"] == 7
                assert params["purge_result"]["errors"] == [
                    "activities table locked"
                ], (
                    "partial-failure errors must be recoverable from "
                    "the audit row — they cannot live only in the "
                    "response payload (red-team v6.4.0 finding)"
                )
            finally:
                router.close()


class TestRunningChildPurgeBiometricCache:
    """
    Storage-level contract for the only real-data child currently in
    the framework. Pinned because RunningStorage is the reference
    pattern other ChildMCP authors copy when implementing purge_cache.
    """

    def test_purge_deletes_streams_and_activities_preserves_labels(self):
        from tailor.children.running.child import RunningStorage
        with TemporaryDirectory() as tmpdir:
            storage = RunningStorage(Path(tmpdir) / "activities.db")
            try:
                # Seed three rows in each table.
                storage.save_activity(1, {"id": 1, "name": "run-1"})
                storage.save_activity(2, {"id": 2, "name": "run-2"})
                storage.save_streams(1, {"hr": [120, 130, 140]})
                storage.save_streams(2, {"hr": [110, 120]})
                storage.save_stop_label(1, 0, "traffic light", "red light at 5th & main")
                storage.save_stop_label(1, 1, "water stop", None)

                result = storage.purge_biometric_cache()

                assert result["rows_purged"] == 4
                assert set(result["tables_touched"]) == {"streams", "activities"}
                assert result["preserved"] == ["stop_labels"]

                # Biometric tables empty
                assert storage.fetchall("SELECT * FROM activities") == []
                assert storage.fetchall("SELECT * FROM streams") == []
                # Analyst-authored labels preserved
                labels = storage.fetchall("SELECT * FROM stop_labels")
                assert len(labels) == 2, (
                    "stop_labels are analyst-authored interpretation "
                    "and must survive a biometric-cache purge"
                )
            finally:
                storage.close()


class TestPublicPathCostEstimatorFailClosed:
    """
    ADR 0005: a broken estimator must NOT slip past the cost gate
    with a synthetic 0-token estimate. The public dispatch path's
    fail-closed branch (router.py:411-422) was untested until v6.4.1
    — this pins the invariant on the Claude-facing path.
    """

    def test_public_dispatch_cost_estimate_error_writes_audit_row(self):
        class CostBrokenChild(MockChild):
            async def estimate_cost(self, tool_name, params):
                raise RuntimeError("simulated estimator crash")

        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            router = RouterMCP("test", data_dir, cost_threshold=35_000)
            try:
                router.register_child(CostBrokenChild("alpha"))
                _run(router._dispatch("approve_consent_alpha", {}))
                result = _run(router._dispatch(
                    "alpha_expensive_tool", {"value": 1}
                ))
                data = _loads(result[0].text)
                assert "error" in data
                assert "estimate" in data["error"].lower()
                import sqlite3
                conn = sqlite3.connect(str(data_dir / "audit.db"))
                try:
                    (outcome,) = conn.execute(
                        "SELECT outcome FROM audit_log "
                        "WHERE tool_name='alpha_expensive_tool' "
                        "ORDER BY id DESC LIMIT 1"
                    ).fetchone()
                finally:
                    conn.close()
                assert outcome == "COST_ESTIMATE_ERROR"
            finally:
                router.close()


class TestUnknownDomainRevocation:
    """The revocation handler's unknown-domain guard at router.py:857
    was uncovered until v6.4.1. A user mistyping a domain name should
    get a clean error, not silently flip an unrelated consent."""

    def test_revoke_unknown_domain_returns_error(self):
        with TemporaryDirectory() as tmpdir:
            router = RouterMCP("test", Path(tmpdir))
            try:
                router.register_child(MockChild("alpha"))
                r = _run(router._dispatch(
                    "revoke_consent_typo_domain", {}
                ))
                data = _loads(r[0].text)
                assert "error" in data
                assert "Unknown domain" in data["error"]
                # Alpha consent unaffected.
                assert not router._consent.is_approved("alpha")
            finally:
                router.close()


class TestOrjsonStdlibFallback:
    """
    audit.py wraps json/orjson behind ``_dumps``/``_loads`` so the
    audit serializer falls back to stdlib when orjson is absent.
    Pip-minimal deployments hit this branch every call. Until v6.4.1
    no test exercised it — the ADR 0001 backbone had an unverified
    serialization path in stripped installs.
    """

    def test_stdlib_fallback_loads_when_orjson_absent(self):
        import importlib
        import sys
        # Save the real module so we can restore it cleanly.
        real_orjson = sys.modules.get("orjson")
        real_audit = sys.modules.get("tailor.framework.audit")
        try:
            # Force ImportError on next `import orjson`.
            sys.modules["orjson"] = None
            # Reload the audit module under the no-orjson regime.
            import tailor.framework.audit as audit_mod
            reloaded = importlib.reload(audit_mod)
            assert reloaded.JSON_BACKEND == "json (orjson not installed)", (
                "stdlib fallback must declare itself in JSON_BACKEND so "
                "deployments can surface the choice"
            )
            # Round-trip a non-trivial dict.
            payload = {"force_revoke": True, "rows_purged": 42, "tables": ["a", "b"]}
            text = reloaded._dumps(payload)
            assert reloaded._loads(text) == payload
        finally:
            # Restore the real environment so subsequent tests get orjson back.
            if real_orjson is not None:
                sys.modules["orjson"] = real_orjson
            else:
                sys.modules.pop("orjson", None)
            if real_audit is not None:
                importlib.reload(real_audit)


class TestVaultWriterAtomicWriteCleanup:
    """
    Atomic-write error cleanup at vault/writer.py:1041-1058 — if
    writing the temp file or replace() fails, the tmp file must not
    be left behind. ADR 0007 graceful-degradation invariant; until
    v6.4.1 the cleanup path was untested.
    """

    def test_atomic_write_cleans_up_tmp_on_write_failure(self, monkeypatch):
        """Path 2: fd transferred to fdopen successfully, then write()
        raises mid-stream. Triggers the `fd_transferred=True` branch."""
        from tailor.framework.vault.writer import VaultWriter
        with TemporaryDirectory() as tmpdir:
            vault_path = Path(tmpdir) / "vault"
            vault_path.mkdir()
            data_dir = Path(tmpdir) / "data"
            data_dir.mkdir()
            writer = VaultWriter(
                vault_path=vault_path, data_dir=data_dir,
                vaultable_tools=set(), max_hr=195,
            )
            try:
                target = vault_path / "broken.md"

                # Force the write step to raise mid-write.
                import os as os_mod
                real_fdopen = os_mod.fdopen

                def boom_fdopen(fd, *args, **kwargs):
                    f = real_fdopen(fd, *args, **kwargs)
                    def explode(_):
                        raise OSError("simulated mid-write failure")
                    f.write = explode
                    return f

                monkeypatch.setattr(os_mod, "fdopen", boom_fdopen)

                with pytest.raises(OSError):
                    writer._atomic_write_abs(target, "any content")

                # No vault_tmp file lingering — cleanup ran.
                tmp_files = list(vault_path.glob(".vault_tmp_*"))
                assert tmp_files == [], (
                    f"atomic-write must clean up temp files on failure "
                    f"(ADR 0007); found leftovers: {tmp_files}"
                )
                assert not target.exists(), (
                    "target must not exist after a mid-write failure"
                )
            finally:
                writer.close()

    def test_atomic_write_cleans_up_when_fdopen_itself_raises(self, monkeypatch):
        """Path 1: fd-not-transferred. fdopen raises before the
        `with` block opens — the except clause must close fd
        explicitly via the ``not fd_transferred`` branch (writer.py:
        1043-1046). Red-team v6.4.1 finding: the previous test only
        covered Path 2."""
        from tailor.framework.vault.writer import VaultWriter
        with TemporaryDirectory() as tmpdir:
            vault_path = Path(tmpdir) / "vault"
            vault_path.mkdir()
            data_dir = Path(tmpdir) / "data"
            data_dir.mkdir()
            writer = VaultWriter(
                vault_path=vault_path, data_dir=data_dir,
                vaultable_tools=set(), max_hr=195,
            )
            try:
                target = vault_path / "broken_fdopen.md"

                import os as os_mod

                def fdopen_raises(fd, *args, **kwargs):
                    # Caller must close fd because we never wrap it —
                    # the ``not fd_transferred`` branch is what does that.
                    raise OSError("simulated fdopen failure (fd-table exhaustion)")

                monkeypatch.setattr(os_mod, "fdopen", fdopen_raises)

                with pytest.raises(OSError):
                    writer._atomic_write_abs(target, "any content")

                tmp_files = list(vault_path.glob(".vault_tmp_*"))
                assert tmp_files == [], (
                    f"atomic-write must clean up temp files even when "
                    f"fdopen itself raises (ADR 0007 path 1); found "
                    f"leftovers: {tmp_files}"
                )
                assert not target.exists()
            finally:
                writer.close()


class TestVaultSearchNotesKindFilter:
    """
    Researcher-visible v6.4.1 fix: vault_search_notes' ToolDefinition
    surfaces the canonical ``kind`` parameter alongside the legacy
    ``note_type`` alias, matching vault_list_notes / vault_read_note.
    Until v6.4.1 a client reading the tool schema saw only note_type.
    """

    def test_search_notes_tool_definition_surfaces_kind_parameter(self):
        from tailor.framework.vault import VaultLayer, VaultWriter
        with TemporaryDirectory() as tmpdir:
            vault_path = Path(tmpdir) / "vault"
            vault_path.mkdir()
            data_dir = Path(tmpdir) / "data"
            data_dir.mkdir()
            writer = VaultWriter(
                vault_path=vault_path, data_dir=data_dir,
                vaultable_tools=set(), max_hr=195,
            )
            try:
                layer = VaultLayer(vault_path, writer)
                # Find the search_notes ToolDefinition
                tool_def = next(
                    t for t in layer.tool_definitions
                    if t.name == "vault_search_notes"
                )
                params = tool_def.params
                assert "kind" in params, (
                    "vault_search_notes must surface 'kind' as the "
                    "canonical filter parameter (v6.3.0 drift fix)"
                )
                assert "failure_mode" in params["kind"]["description"]
                assert "dashboard" in params["kind"]["description"]
                # note_type should still work as an alias for backward compat
                assert "note_type" in params
                assert "alias" in params["note_type"]["description"].lower()
            finally:
                writer.close()
