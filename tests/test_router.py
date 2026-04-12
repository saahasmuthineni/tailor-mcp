"""
Tests for the parent router MCP.

Uses a minimal mock child to test the routing and security pipeline
without depending on Strava or any real data source.
"""

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from biosensor_mcp.framework.interfaces import (
    ChildMCP,
    CostEstimate,
    ToolDefinition,
    ValidationSchema,
)
from biosensor_mcp.framework.middleware import _loads
from biosensor_mcp.framework.router import RouterMCP

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
            assert data["_meta"]["tier"] == 1
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
        from biosensor_mcp.vault import VaultLayer, VaultWriter
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
            assert data["_meta"]["domain"] == "vault"
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
        from biosensor_mcp.vault import VaultLayer, VaultWriter
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
            from biosensor_mcp.vault import VaultLayer, VaultWriter
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
