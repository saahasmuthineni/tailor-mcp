"""
Shape tests for TemplateChild — the skeleton for new ChildMCPs.

These are contract tests: they verify that the template satisfies
every structural invariant a real child must satisfy to register
with the router. When you fork the template into a new domain,
copy this file and retarget the assertions at your own child —
the tests are the unambiguous shape contract.

What's covered:

* The ChildMCP ABC surface (``domain``, ``display_name``,
  ``tool_definitions``, ``param_schemas``) is non-empty and
  correctly typed.
* Every tool declares ``subject_id`` in both ``tool_definitions``
  (MCP discoverability) and ``param_schemas`` (validator-side
  pattern enforcement). See ADR 0002.
* The router's ``register_child`` accepts the template without
  raising; all five tool names appear in ``registered_tools``.
* ``execute()`` returns a dict for every tool (catches regressions
  where a handler raises ``NotImplementedError`` or returns ``None``).
* ``estimate_cost()`` returns a ``CostEstimate``; the one Tier-3
  tool reports a cheaper alternative.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from biosensor_mcp.children.template import TemplateChild
from biosensor_mcp.children.template.child import (
    ALL_STREAM_TYPES,
    SUBJECT_ID_SCHEMA,
)
from biosensor_mcp.framework.interfaces import (
    CostEstimate,
    ToolDefinition,
    ValidationSchema,
)
from biosensor_mcp.framework.router import RouterMCP

SUBJECT_ID_PATTERN = r"^[A-Za-z0-9_\-]{1,64}$"


# ═══════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════


@pytest.fixture
def template_child() -> TemplateChild:
    """TemplateChild instance backed by a throwaway config/data dir."""
    with TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        config_dir = root / "config"
        data_dir = root / "data"
        config_dir.mkdir()
        data_dir.mkdir()
        yield TemplateChild(config_dir, data_dir)


# Valid parameters for each tool — used by the execute/estimate
# shape tests below. Keeping these in one place makes it obvious
# which fields each tool expects.
VALID_PARAMS = {
    "example_list": {"limit": 10},
    "example_detail": {"record_id": 1},
    "example_summary_report": {"record_id": 1},
    "example_downsampled": {"record_id": 1, "interval": 2, "streams": ["signal_a"]},
    "example_raw_stream": {"record_id": 1, "streams": ["signal_a"]},
}


# ═══════════════════════════════════════════════════════════════
# REQUIRED ABSTRACT SURFACE
# ═══════════════════════════════════════════════════════════════


class TestRequiredAbstractSurface:
    """The ABC-required properties are non-empty and correctly typed."""

    def test_domain_is_nonempty_str(self, template_child: TemplateChild):
        assert isinstance(template_child.domain, str)
        assert template_child.domain.strip()

    def test_display_name_is_nonempty_str(self, template_child: TemplateChild):
        assert isinstance(template_child.display_name, str)
        assert template_child.display_name.strip()

    def test_tool_definitions_is_nonempty_list_of_tool_definition(
        self, template_child: TemplateChild,
    ):
        defs = template_child.tool_definitions
        assert isinstance(defs, list)
        assert len(defs) == 5, "template advertises 3 Tier-1 + 1 Tier-2 + 1 Tier-3"
        for tool_def in defs:
            assert isinstance(tool_def, ToolDefinition)
            assert tool_def.tier in (1, 2, 3)

    def test_tool_definitions_cover_all_three_tiers(
        self, template_child: TemplateChild,
    ):
        tiers = {td.tier for td in template_child.tool_definitions}
        assert tiers == {1, 2, 3}, (
            "template should illustrate all three access tiers"
        )

    def test_param_schemas_match_tool_definitions(
        self, template_child: TemplateChild,
    ):
        def_names = {td.name for td in template_child.tool_definitions}
        schema_names = set(template_child.param_schemas.keys())
        assert def_names == schema_names


# ═══════════════════════════════════════════════════════════════
# SUBJECT_ID CONSISTENCY (ADR 0002)
# ═══════════════════════════════════════════════════════════════


class TestSubjectIdConsistency:
    """Every template tool declares subject_id in both surfaces."""

    def test_every_tool_declares_subject_id_in_param_schemas(
        self, template_child: TemplateChild,
    ):
        schemas = template_child.param_schemas
        assert schemas, "param_schemas should not be empty"
        for tool_name, tool_schema in schemas.items():
            assert "subject_id" in tool_schema, (
                f"{tool_name} missing subject_id in param_schemas"
            )
            entry = tool_schema["subject_id"]
            assert isinstance(entry, ValidationSchema)
            assert entry.type is str
            assert entry.required is False
            assert entry.pattern == SUBJECT_ID_PATTERN

    def test_every_tool_declares_subject_id_in_tool_definitions(
        self, template_child: TemplateChild,
    ):
        defs = template_child.tool_definitions
        assert defs, "tool_definitions should not be empty"
        for tool_def in defs:
            assert "subject_id" in tool_def.params, (
                f"{tool_def.name} missing subject_id in tool_definitions.params"
            )
            entry = tool_def.params["subject_id"]
            assert entry["type"] == "string"
            assert entry["required"] is False
            assert isinstance(entry["description"], str)
            assert entry["description"].strip()

    def test_exported_subject_id_schema_matches_canonical_pattern(self):
        assert SUBJECT_ID_SCHEMA.type is str
        assert SUBJECT_ID_SCHEMA.required is False
        assert SUBJECT_ID_SCHEMA.pattern == SUBJECT_ID_PATTERN


# ═══════════════════════════════════════════════════════════════
# ROUTER REGISTRATION
# ═══════════════════════════════════════════════════════════════


class TestRouterCanRegister:
    """The router accepts the template without raising."""

    def test_register_child_succeeds(self, tmp_data_dir: Path):
        router = RouterMCP(name="test-template", data_dir=tmp_data_dir)
        try:
            with TemporaryDirectory() as tmp:
                child = TemplateChild(Path(tmp), tmp_data_dir)
                router.register_child(child)
                assert "example" in router.registered_domains
                for tool_name in (
                    "example_list",
                    "example_detail",
                    "example_summary_report",
                    "example_downsampled",
                    "example_raw_stream",
                ):
                    assert tool_name in router.registered_tools
        finally:
            # Keep Windows SQLite file locks happy.
            if hasattr(router, "close"):
                router.close()


# ═══════════════════════════════════════════════════════════════
# EXECUTE & ESTIMATE_COST SHAPE
# ═══════════════════════════════════════════════════════════════


class TestExecuteReturnsDicts:
    """Every tool's execute() handler returns a dict."""

    @pytest.mark.parametrize("tool_name", list(VALID_PARAMS.keys()))
    def test_execute_returns_dict(
        self, template_child: TemplateChild, tool_name: str,
    ):
        result = asyncio.run(
            template_child.execute(tool_name, VALID_PARAMS[tool_name])
        )
        assert isinstance(result, dict), (
            f"{tool_name}.execute() should return a dict, got {type(result)}"
        )
        assert "error" not in result, (
            f"{tool_name}.execute() unexpectedly errored: {result.get('error')}"
        )


class TestEstimateCostShape:
    """estimate_cost returns a CostEstimate; Tier-3 offers alternative."""

    @pytest.mark.parametrize("tool_name", list(VALID_PARAMS.keys()))
    def test_estimate_cost_returns_cost_estimate(
        self, template_child: TemplateChild, tool_name: str,
    ):
        est = asyncio.run(
            template_child.estimate_cost(tool_name, VALID_PARAMS[tool_name])
        )
        assert isinstance(est, CostEstimate)
        assert est.tokens >= 0

    def test_raw_stream_has_cheaper_alternative(
        self, template_child: TemplateChild,
    ):
        est = asyncio.run(
            template_child.estimate_cost(
                "example_raw_stream", VALID_PARAMS["example_raw_stream"],
            )
        )
        assert est.has_cheaper_alternative is True
        assert est.alternative_tokens > 0
        assert est.alternative_tokens < est.tokens
        assert est.alternative_description.strip()


# ═══════════════════════════════════════════════════════════════
# CONSENT SCOPE (data_types_for_tool narrowing)
# ═══════════════════════════════════════════════════════════════


class TestDataTypesForTool:
    """data_types_for_tool narrows consent scope on streams tools."""

    def test_default_scope_for_non_streams_tool(
        self, template_child: TemplateChild,
    ):
        types = template_child.data_types_for_tool("example_summary_report", {})
        assert types == template_child.consent_info.data_types

    def test_narrows_scope_for_downsampled_by_requested_stream(
        self, template_child: TemplateChild,
    ):
        types = template_child.data_types_for_tool(
            "example_downsampled", {"streams": ["signal_a"]},
        )
        assert types == ["example signal A"]

    def test_narrows_scope_for_raw_stream(
        self, template_child: TemplateChild,
    ):
        types = template_child.data_types_for_tool(
            "example_raw_stream", {"streams": ["signal_b"]},
        )
        assert types == ["example signal B"]

    def test_falls_back_to_full_scope_when_streams_not_specified(
        self, template_child: TemplateChild,
    ):
        types = template_child.data_types_for_tool("example_downsampled", {})
        assert types == template_child.consent_info.data_types


# ═══════════════════════════════════════════════════════════════
# SANITY: ALL_STREAM_TYPES matches the downsampled/raw tools' allowed_values
# ═══════════════════════════════════════════════════════════════


class TestStreamAllowedValues:
    """The ALL_STREAM_TYPES constant is what the streams tools accept."""

    @pytest.mark.parametrize(
        "tool_name", ["example_downsampled", "example_raw_stream"],
    )
    def test_streams_allowed_values_match_constant(
        self, template_child: TemplateChild, tool_name: str,
    ):
        schema = template_child.param_schemas[tool_name]["streams"]
        assert schema.allowed_values == ALL_STREAM_TYPES
