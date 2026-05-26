"""
Tests for RunningChild's declared tool surface.

Covers the roadmap item "Per-subject parameter scoping on existing
tools" (ADR 0002): every strava_* tool must declare ``entity_id``
in both ``tool_definitions`` (MCP discoverability via list_tools)
and ``param_schemas`` (validator-side pattern enforcement). No
router, no Strava — pure schema/ValidationSchema wiring.
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from tailor.children.running.child import (
    ENTITY_ID_SCHEMA,
    RunningChild,
)
from tailor.framework.interfaces import ValidationSchema
from tailor.framework.security import ParamValidator

ENTITY_ID_PATTERN = r"^[A-Za-z0-9_\-]{1,64}$"


@pytest.fixture
def running_child() -> RunningChild:
    """RunningChild instance backed by a throwaway data dir.

    The tests only touch declared properties (tool_definitions,
    param_schemas) so storage is never written. TemporaryDirectory
    is still needed because ``__init__`` opens a SQLite connection.
    """
    with TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        config_dir = root / "config"
        data_dir = root / "data"
        config_dir.mkdir()
        data_dir.mkdir()
        child = RunningChild(config_dir, data_dir)
        yield child
        child.close()


class TestSubjectIdDeclaredOnEveryTool:
    """Every strava_* tool declares entity_id in both surfaces."""

    def test_every_running_tool_declares_entity_id_in_param_schemas(
        self, running_child: RunningChild,
    ):
        schemas = running_child.param_schemas
        assert schemas, "param_schemas should not be empty"
        for tool_name, tool_schema in schemas.items():
            assert "entity_id" in tool_schema, (
                f"{tool_name} missing entity_id in param_schemas"
            )
            entry = tool_schema["entity_id"]
            assert isinstance(entry, ValidationSchema)
            assert entry.type is str
            assert entry.required is False
            assert entry.pattern == ENTITY_ID_PATTERN

    def test_every_running_tool_declares_entity_id_in_tool_definitions(
        self, running_child: RunningChild,
    ):
        defs = running_child.tool_definitions
        assert defs, "tool_definitions should not be empty"
        for tool_def in defs:
            assert "entity_id" in tool_def.params, (
                f"{tool_def.name} missing entity_id in tool_definitions.params"
            )
            entry = tool_def.params["entity_id"]
            assert entry["type"] == "string"
            assert entry["required"] is False
            assert isinstance(entry["description"], str)
            assert entry["description"].strip(), (
                f"{tool_def.name} entity_id description is empty"
            )

    def test_tool_definitions_and_param_schemas_cover_same_tools(
        self, running_child: RunningChild,
    ):
        """Sanity check: the two surfaces don't drift."""
        def_names = {td.name for td in running_child.tool_definitions}
        schema_names = set(running_child.param_schemas.keys())
        assert def_names == schema_names


class TestSubjectIdPatternValidation:
    """ParamValidator enforces ENTITY_ID_SCHEMA correctly against running schemas."""

    # Use strava_run_report (the canonical Tier-1 tool) as the test
    # bed; the schema is the same constant across every tool.
    TOOL_UNDER_TEST = "strava_run_report"

    @pytest.fixture
    def schema(self, running_child: RunningChild) -> dict[str, ValidationSchema]:
        return running_child.param_schemas[self.TOOL_UNDER_TEST]

    @pytest.mark.parametrize(
        "bad_value",
        [
            "",                       # empty string
            " P042",                  # leading space
            "P042 with spaces",       # internal spaces
            "P" * 65,                 # one past max length
            "P042;DROP",              # semicolon
            "P042/slash",             # forward slash
            "sübj",                   # non-ASCII
        ],
    )
    def test_entity_id_pattern_rejects_bad_values(
        self, schema: dict[str, ValidationSchema], bad_value: str,
    ):
        ok, err, _cleaned = ParamValidator.validate(
            schema, {"activity_id": 1, "entity_id": bad_value},
        )
        assert ok is False
        assert "entity_id" in err

    @pytest.mark.parametrize(
        "good_value",
        [
            "P042",
            "subj-001",
            "SUBJ_042",
            "a",
            "A" * 64,
            "0",                  # single digit is fine
            "P-042_v2",
        ],
    )
    def test_entity_id_pattern_accepts_good_values(
        self, schema: dict[str, ValidationSchema], good_value: str,
    ):
        ok, err, cleaned = ParamValidator.validate(
            schema, {"activity_id": 1, "entity_id": good_value},
        )
        assert ok is True, err
        assert cleaned["entity_id"] == good_value

    def test_entity_id_is_optional(
        self, schema: dict[str, ValidationSchema],
    ):
        """Omitting entity_id remains valid (preserves single-subject use case)."""
        ok, err, cleaned = ParamValidator.validate(
            schema, {"activity_id": 1},
        )
        assert ok is True, err
        assert "entity_id" not in cleaned


class TestExportedConstant:
    """ENTITY_ID_SCHEMA is importable and matches the expected pattern."""

    def test_exported_constant_matches_pattern(self):
        assert ENTITY_ID_SCHEMA.type is str
        assert ENTITY_ID_SCHEMA.required is False
        assert ENTITY_ID_SCHEMA.pattern == ENTITY_ID_PATTERN
