"""
Tests for WalkthroughLayer (ADR 0040 — MCP-tool version of v6.12.0
architectural showcase).

Verifies the section payloads, parameter validation, and the
unknown-section refusal path.
"""

from __future__ import annotations

import asyncio

import pytest

from tailor.framework.walkthrough import WalkthroughLayer


def _run(coro):
    return asyncio.run(coro)


def test_tool_surface_is_single_tool():
    layer = WalkthroughLayer()
    tool_names = {td.name for td in layer.tool_definitions}
    assert tool_names == {"tailor_walkthrough_section"}


def test_param_schema_uses_int_with_min_max():
    """ADR 0040 mandates the integer-with-1..5 shape."""
    layer = WalkthroughLayer()
    schema = layer.param_schemas["tailor_walkthrough_section"]
    assert "section" in schema
    section_schema = schema["section"]
    assert section_schema.type is int
    assert section_schema.required is True
    assert section_schema.min == 1
    assert section_schema.max == 5


@pytest.mark.parametrize("section", [1, 2, 3, 4, 5])
def test_each_section_returns_required_keys(section):
    layer = WalkthroughLayer()
    result = _run(layer.execute(
        "tailor_walkthrough_section",
        {"section": section},
    ))
    assert result["section"] == section
    assert "title" in result
    assert "narrative" in result
    assert "worked_example" in result
    assert "adr_citations" in result
    assert "next_step" in result
    # ADR citations must include at least one ADR — every section
    # grounds itself in the project's design record.
    assert len(result["adr_citations"]) >= 1


def test_section_1_includes_token_cost_signal():
    """Section 1 IS the AI-economics demonstration; the token cost
    differential is its load-bearing claim.
    """
    layer = WalkthroughLayer()
    result = _run(layer.execute(
        "tailor_walkthrough_section", {"section": 1},
    ))
    assert "token" in result["narrative"].lower()
    assert "approximate_token_cost" in result["worked_example"]


def test_section_3_includes_three_tiers():
    layer = WalkthroughLayer()
    result = _run(layer.execute(
        "tailor_walkthrough_section", {"section": 3},
    ))
    we = result["worked_example"]
    assert "tier_1" in we
    assert "tier_2" in we
    assert "tier_3" in we


def test_unknown_section_returns_error():
    layer = WalkthroughLayer()
    # Direct execute bypasses validator gating; the layer's own
    # body must still refuse.
    result = _run(layer.execute(
        "tailor_walkthrough_section", {"section": 99},
    ))
    assert "error" in result


def test_returned_payload_is_a_fresh_copy(monkeypatch):
    """Mutating the returned dict must not affect subsequent calls."""
    layer = WalkthroughLayer()
    a = _run(layer.execute(
        "tailor_walkthrough_section", {"section": 1},
    ))
    a["title"] = "MUTATED"
    b = _run(layer.execute(
        "tailor_walkthrough_section", {"section": 1},
    ))
    assert b["title"] != "MUTATED"


def test_unknown_tool_returns_error():
    layer = WalkthroughLayer()
    result = _run(layer.execute("tailor_walkthrough_nope", {}))
    assert "error" in result
