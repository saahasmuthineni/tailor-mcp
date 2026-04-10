"""
Tests for the parent router MCP.

Uses a minimal mock child to test the routing and security pipeline
without depending on Strava or any real data source.
"""

import asyncio
import pytest
from pathlib import Path
from tempfile import TemporaryDirectory

from strava_coach.framework.interfaces import (
    ChildMCP,
    ToolDefinition,
    CostEstimate,
    ValidationSchema,
)
from strava_coach.framework.router import RouterMCP
from strava_coach.framework.middleware import _loads


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
    return asyncio.get_event_loop().run_until_complete(coro)


class TestChildRegistration:
    def test_register_child(self):
        with TemporaryDirectory() as tmpdir:
            router = RouterMCP("test", Path(tmpdir))
            child = MockChild("alpha")
            router.register_child(child)
            assert "alpha" in router.registered_domains
            assert "alpha_free_tool" in router.registered_tools

    def test_duplicate_domain_rejected(self):
        with TemporaryDirectory() as tmpdir:
            router = RouterMCP("test", Path(tmpdir))
            router.register_child(MockChild("alpha"))
            with pytest.raises(ValueError, match="already registered"):
                router.register_child(MockChild("alpha"))

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

    def test_invalid_params_rejected(self):
        with TemporaryDirectory() as tmpdir:
            router = RouterMCP("test", Path(tmpdir))
            router.register_child(MockChild("alpha"))
            result = _run(router._dispatch("alpha_free_tool", {}))
            data = _loads(result[0].text)
            assert "error" in data

    def test_unknown_tool_rejected(self):
        with TemporaryDirectory() as tmpdir:
            router = RouterMCP("test", Path(tmpdir))
            result = _run(router._dispatch("nonexistent", {}))
            data = _loads(result[0].text)
            assert "Unknown tool" in data["error"]


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

    def test_approve_unknown_domain(self):
        with TemporaryDirectory() as tmpdir:
            router = RouterMCP("test", Path(tmpdir))
            result = _run(router._dispatch("approve_consent_unknown", {}))
            data = _loads(result[0].text)
            assert "error" in data
