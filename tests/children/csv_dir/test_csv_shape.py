"""
Shape tests for CSVDirectoryChild — the generic CSV directory ChildMCP.

Ported from ``tests/children/template/test_template_shape.py``.
These are contract tests: they verify that the CSV child satisfies
every structural invariant a real child must satisfy to register
with the router.

What's covered:

* The ChildMCP ABC surface (``domain``, ``display_name``,
  ``tool_definitions``, ``param_schemas``) is non-empty and
  correctly typed.
* Every tool declares ``subject_id`` in both ``tool_definitions``
  (MCP discoverability) and ``param_schemas`` (validator-side
  pattern enforcement). See ADR 0002.
* The router's ``register_child`` accepts the child without
  raising; all five tool names appear in ``registered_tools``.
* ``execute()`` returns a dict for every tool (catches regressions
  where a handler raises or returns ``None``).
* ``estimate_cost()`` returns a ``CostEstimate``; the one Tier-3
  tool reports a cheaper alternative.
* ``data_types_for_tool`` narrows consent scope for column tools.
* Path-traversal attempts in ``file_id`` return error dicts.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from biosensor_mcp.children.csv_dir import CSVDirectoryChild
from biosensor_mcp.children.csv_dir.child import (
    SUBJECT_ID_SCHEMA,
)
from biosensor_mcp.framework.interfaces import (
    CostEstimate,
    ToolDefinition,
    ValidationSchema,
)
from biosensor_mcp.framework.router import RouterMCP

SUBJECT_ID_PATTERN = r"^[A-Za-z0-9_\-]{1,64}$"

# Fixture CSV content
FIXTURE_CSV_A = """\
timestamp,heart_rate,glucose
2026-01-01T10:00:00Z,72,95
2026-01-01T10:01:00Z,74,97
2026-01-01T10:02:00Z,73,96
2026-01-01T10:03:00Z,75,98
2026-01-01T10:04:00Z,76,99
2026-01-01T10:05:00Z,78,100
2026-01-01T10:06:00Z,80,102
2026-01-01T10:07:00Z,82,104
2026-01-01T10:08:00Z,79,101
2026-01-01T10:09:00Z,77,99
"""

FIXTURE_CSV_B = """\
timestamp,heart_rate,glucose
2026-01-02T10:00:00Z,68,92
2026-01-02T10:01:00Z,70,94
"""


# ═══════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════


@pytest.fixture
def csv_child() -> CSVDirectoryChild:
    """CSVDirectoryChild backed by fixture CSV files."""
    with TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        config_dir = root / "config"
        data_dir = root / "data"
        csv_dir = root / "csv_files"
        config_dir.mkdir()
        data_dir.mkdir()
        csv_dir.mkdir()

        # Write fixture CSVs
        (csv_dir / "fixture_a.csv").write_text(FIXTURE_CSV_A, encoding="utf-8")
        (csv_dir / "fixture_b.csv").write_text(FIXTURE_CSV_B, encoding="utf-8")

        # Write user_config.json with csv_dir section
        user_config = {
            "csv_dir": {
                "path": str(csv_dir),
                "timestamp_column": "timestamp",
                "value_columns": {
                    "heart_rate": "Heart rate (bpm)",
                    "glucose": "Blood glucose (mg/dL)",
                },
            },
        }
        (config_dir / "user_config.json").write_text(
            json.dumps(user_config), encoding="utf-8",
        )

        yield CSVDirectoryChild(config_dir, data_dir)


# Valid parameters for each tool
VALID_PARAMS = {
    "csv_list_files": {"limit": 10},
    "csv_file_detail": {"file_id": "fixture_a.csv"},
    "csv_summary_report": {"file_id": "fixture_a.csv"},
    "csv_downsampled": {"file_id": "fixture_a.csv", "interval": 2, "columns": ["heart_rate"]},
    "csv_raw_stream": {"file_id": "fixture_a.csv", "columns": ["heart_rate"]},
}


# ═══════════════════════════════════════════════════════════════
# REQUIRED ABSTRACT SURFACE
# ═══════════════════════════════════════════════════════════════


class TestRequiredAbstractSurface:
    """The ABC-required properties are non-empty and correctly typed."""

    def test_domain_is_nonempty_str(self, csv_child: CSVDirectoryChild):
        assert isinstance(csv_child.domain, str)
        assert csv_child.domain.strip()

    def test_display_name_is_nonempty_str(self, csv_child: CSVDirectoryChild):
        assert isinstance(csv_child.display_name, str)
        assert csv_child.display_name.strip()

    def test_tool_definitions_is_nonempty_list_of_tool_definition(
        self, csv_child: CSVDirectoryChild,
    ):
        defs = csv_child.tool_definitions
        assert isinstance(defs, list)
        assert len(defs) == 5, "CSV child advertises 3 Tier-1 + 1 Tier-2 + 1 Tier-3"
        for tool_def in defs:
            assert isinstance(tool_def, ToolDefinition)
            assert tool_def.tier in (1, 2, 3)

    def test_tool_definitions_cover_all_three_tiers(
        self, csv_child: CSVDirectoryChild,
    ):
        tiers = {td.tier for td in csv_child.tool_definitions}
        assert tiers == {1, 2, 3}

    def test_param_schemas_match_tool_definitions(
        self, csv_child: CSVDirectoryChild,
    ):
        def_names = {td.name for td in csv_child.tool_definitions}
        schema_names = set(csv_child.param_schemas.keys())
        assert def_names == schema_names


# ═══════════════════════════════════════════════════════════════
# SUBJECT_ID CONSISTENCY (ADR 0002)
# ═══════════════════════════════════════════════════════════════


class TestSubjectIdConsistency:
    """Every CSV tool declares subject_id in both surfaces."""

    def test_every_tool_declares_subject_id_in_param_schemas(
        self, csv_child: CSVDirectoryChild,
    ):
        schemas = csv_child.param_schemas
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
        self, csv_child: CSVDirectoryChild,
    ):
        defs = csv_child.tool_definitions
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
    """The router accepts the CSV child without raising."""

    def test_register_child_succeeds(self, tmp_data_dir: Path):
        router = RouterMCP(name="test-csv", data_dir=tmp_data_dir)
        try:
            with TemporaryDirectory() as tmp:
                root = Path(tmp)
                config_dir = root / "config"
                csv_dir = root / "csv_files"
                config_dir.mkdir()
                csv_dir.mkdir()
                (csv_dir / "test.csv").write_text(
                    "timestamp,value\n2026-01-01,42\n", encoding="utf-8",
                )
                user_config = {
                    "csv_dir": {
                        "path": str(csv_dir),
                        "value_columns": {"value": "Test value"},
                    },
                }
                (config_dir / "user_config.json").write_text(
                    json.dumps(user_config), encoding="utf-8",
                )
                child = CSVDirectoryChild(config_dir, tmp_data_dir)
                router.register_child(child)
                assert "csv_dir" in router.registered_domains
                for tool_name in (
                    "csv_list_files",
                    "csv_file_detail",
                    "csv_summary_report",
                    "csv_downsampled",
                    "csv_raw_stream",
                ):
                    assert tool_name in router.registered_tools
        finally:
            if hasattr(router, "close"):
                router.close()


# ═══════════════════════════════════════════════════════════════
# EXECUTE & ESTIMATE_COST SHAPE
# ═══════════════════════════════════════════════════════════════


class TestExecuteReturnsDicts:
    """Every tool's execute() handler returns a dict."""

    @pytest.mark.parametrize("tool_name", list(VALID_PARAMS.keys()))
    def test_execute_returns_dict(
        self, csv_child: CSVDirectoryChild, tool_name: str,
    ):
        result = asyncio.run(
            csv_child.execute(tool_name, VALID_PARAMS[tool_name])
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
        self, csv_child: CSVDirectoryChild, tool_name: str,
    ):
        est = asyncio.run(
            csv_child.estimate_cost(tool_name, VALID_PARAMS[tool_name])
        )
        assert isinstance(est, CostEstimate)
        assert est.tokens >= 0

    def test_raw_stream_has_cheaper_alternative(
        self, csv_child: CSVDirectoryChild,
    ):
        est = asyncio.run(
            csv_child.estimate_cost(
                "csv_raw_stream", VALID_PARAMS["csv_raw_stream"],
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
    """data_types_for_tool narrows consent scope on column tools."""

    def test_default_scope_for_non_column_tool(
        self, csv_child: CSVDirectoryChild,
    ):
        types = csv_child.data_types_for_tool("csv_summary_report", {})
        assert types == csv_child.consent_info.data_types

    def test_narrows_scope_for_downsampled_by_requested_column(
        self, csv_child: CSVDirectoryChild,
    ):
        types = csv_child.data_types_for_tool(
            "csv_downsampled", {"columns": ["heart_rate"]},
        )
        assert types == ["Heart rate (bpm)"]

    def test_narrows_scope_for_raw_stream(
        self, csv_child: CSVDirectoryChild,
    ):
        types = csv_child.data_types_for_tool(
            "csv_raw_stream", {"columns": ["glucose"]},
        )
        assert types == ["Blood glucose (mg/dL)"]

    def test_falls_back_to_full_scope_when_columns_not_specified(
        self, csv_child: CSVDirectoryChild,
    ):
        types = csv_child.data_types_for_tool("csv_downsampled", {})
        assert types == csv_child.consent_info.data_types


# ═══════════════════════════════════════════════════════════════
# COLUMN ALLOWED VALUES
# ═══════════════════════════════════════════════════════════════


class TestColumnAllowedValues:
    """The configured columns match what the column tools accept."""

    @pytest.mark.parametrize(
        "tool_name", ["csv_downsampled", "csv_raw_stream"],
    )
    def test_columns_allowed_values_match_config(
        self, csv_child: CSVDirectoryChild, tool_name: str,
    ):
        schema = csv_child.param_schemas[tool_name]["columns"]
        assert schema.allowed_values == ["heart_rate", "glucose"]


# ═══════════════════════════════════════════════════════════════
# FILE_ID SECURITY (path traversal)
# ═══════════════════════════════════════════════════════════════


class TestFileIdSecurity:
    """Path traversal attempts in file_id return error dicts."""

    @pytest.mark.parametrize("malicious_id", [
        "../etc/passwd",
        "../../secrets.csv",
        "..\\windows\\system.ini",
        "/absolute/path.csv",
    ])
    def test_traversal_attempt_returns_error(
        self, csv_child: CSVDirectoryChild, malicious_id: str,
    ):
        result = asyncio.run(
            csv_child.execute("csv_file_detail", {"file_id": malicious_id})
        )
        assert isinstance(result, dict)
        assert "error" in result


# ═══════════════════════════════════════════════════════════════
# MISSING PATH VALIDATION
# ═══════════════════════════════════════════════════════════════


class TestMissingPathValidation:
    """Missing csv_dir.path raises ValueError on init."""

    def test_missing_path_raises(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_dir = root / "config"
            data_dir = root / "data"
            config_dir.mkdir()
            data_dir.mkdir()
            # Config with csv_dir but no path
            user_config = {"csv_dir": {}}
            (config_dir / "user_config.json").write_text(
                json.dumps(user_config), encoding="utf-8",
            )
            with pytest.raises(ValueError, match="csv_dir.path is required"):
                CSVDirectoryChild(config_dir, data_dir)


# ═══════════════════════════════════════════════════════════════
# MALFORMED CSV HANDLING
# ═══════════════════════════════════════════════════════════════


class TestMalformedCsvHandling:
    """Malformed CSVs return results without crashing."""

    def test_inconsistent_columns_do_not_crash(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_dir = root / "config"
            data_dir = root / "data"
            csv_dir = root / "csv_files"
            config_dir.mkdir()
            data_dir.mkdir()
            csv_dir.mkdir()

            # CSV with inconsistent column counts
            (csv_dir / "bad.csv").write_text(
                "timestamp,heart_rate,glucose\n"
                "2026-01-01T10:00:00Z,72,95\n"
                "2026-01-01T10:01:00Z,74\n"       # missing glucose
                "2026-01-01T10:02:00Z,73,96\n",
                encoding="utf-8",
            )
            user_config = {
                "csv_dir": {
                    "path": str(csv_dir),
                    "timestamp_column": "timestamp",
                    "value_columns": {
                        "heart_rate": "Heart rate (bpm)",
                        "glucose": "Blood glucose (mg/dL)",
                    },
                },
            }
            (config_dir / "user_config.json").write_text(
                json.dumps(user_config), encoding="utf-8",
            )
            child = CSVDirectoryChild(config_dir, data_dir)

            # summary_report should not crash
            result = asyncio.run(
                child.execute("csv_summary_report", {"file_id": "bad.csv"})
            )
            assert isinstance(result, dict)
            assert "error" not in result
            assert result["row_count"] == 3

            # file_detail should not crash
            result = asyncio.run(
                child.execute("csv_file_detail", {"file_id": "bad.csv"})
            )
            assert isinstance(result, dict)
            assert "error" not in result


# ═══════════════════════════════════════════════════════════════
# AUTO-DETECTION
# ═══════════════════════════════════════════════════════════════


class TestAutoDetection:
    """Value columns are auto-detected when not configured."""

    def test_auto_detects_numeric_columns(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_dir = root / "config"
            data_dir = root / "data"
            csv_dir = root / "csv_files"
            config_dir.mkdir()
            data_dir.mkdir()
            csv_dir.mkdir()

            (csv_dir / "data.csv").write_text(
                "timestamp,heart_rate,notes\n"
                "2026-01-01T10:00:00Z,72,normal\n"
                "2026-01-01T10:01:00Z,74,elevated\n",
                encoding="utf-8",
            )
            user_config = {
                "csv_dir": {
                    "path": str(csv_dir),
                    # no value_columns — should auto-detect
                },
            }
            (config_dir / "user_config.json").write_text(
                json.dumps(user_config), encoding="utf-8",
            )
            child = CSVDirectoryChild(config_dir, data_dir)

            # heart_rate should be detected, notes should not
            assert child._column_names is not None
            assert "heart_rate" in child._column_names
            assert "notes" not in child._column_names
            assert "timestamp" not in child._column_names

    def test_auto_detect_streams_sample_only(self, monkeypatch):
        """Auto-detection must not load the full file.

        Regression: prior implementation called _read_csv() without
        max_bytes, loading the entire CSV into memory during init.
        A directory containing a file larger than MAX_CSV_BYTES must
        still initialize successfully and block oversized reads only
        at tool-call time.
        """
        from biosensor_mcp.children.csv_dir import child as child_mod

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_dir = root / "config"
            data_dir = root / "data"
            csv_dir = root / "csv_files"
            config_dir.mkdir()
            data_dir.mkdir()
            csv_dir.mkdir()

            # Write a CSV bigger than the (lowered) size guard.
            big = csv_dir / "big.csv"
            with open(big, "w", encoding="utf-8") as f:
                f.write("timestamp,heart_rate,notes\n")
                row = "2026-01-01T10:00:00Z,72," + ("x" * 200) + "\n"
                for _ in range(2000):
                    f.write(row)
            assert big.stat().st_size > 100_000

            user_config = {"csv_dir": {"path": str(csv_dir)}}
            (config_dir / "user_config.json").write_text(
                json.dumps(user_config), encoding="utf-8",
            )

            # Lower the guard below the CSV size for this test.
            monkeypatch.setattr(child_mod, "MAX_CSV_BYTES", 10_000)

            # Init must succeed without loading the full file.
            child = CSVDirectoryChild(config_dir, data_dir)
            assert child._column_names is not None
            assert "heart_rate" in child._column_names

            # Tool calls still enforce the size guard.
            result = asyncio.run(
                child.execute("csv_file_detail", {"file_id": "big.csv"})
            )
            assert "error" in result
            assert "too large" in result["error"].lower()
