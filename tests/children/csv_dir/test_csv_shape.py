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

        # Write metadata sidecar (ADR 0015) so csv_cohort_summary works.
        (csv_dir / "metadata.json").write_text(
            json.dumps({
                "fixture_a.csv": {"sex": "F", "group": "control"},
                "fixture_b.csv": {"sex": "M", "group": "test"},
            }),
            encoding="utf-8",
        )

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
    "csv_cohort_summary": {
        "column": "heart_rate", "group_by": "sex", "metric": "mean",
    },
    "csv_force_decline": {"file_id": "fixture_a.csv", "column": "heart_rate"},
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
        assert len(defs) == 7, "CSV child advertises 5 Tier-1 + 1 Tier-2 + 1 Tier-3"
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
                    "csv_cohort_summary",
                    "csv_force_decline",
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


class TestCohortSummaryHandler:
    """csv_cohort_summary handler — metadata sidecar contract (ADR 0015)."""

    def test_returns_per_group_stats_with_metadata(
        self, csv_child: CSVDirectoryChild,
    ):
        result = asyncio.run(csv_child.execute(
            "csv_cohort_summary",
            {"column": "heart_rate", "group_by": "sex", "metric": "mean"},
        ))
        assert isinstance(result, dict)
        assert "error" not in result
        assert result["column"] == "heart_rate"
        assert result["metric"] == "mean"
        assert result["group_by"] == "sex"
        assert result["subject_count"] == 2
        assert set(result["groups"].keys()) == {"M", "F"}
        for _group_label, stats in result["groups"].items():
            assert "n" in stats
            assert "mean" in stats
            assert "subjects" in stats
            assert isinstance(stats["subjects"], list)

    def test_missing_metadata_sidecar_returns_error(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_dir = root / "config"
            data_dir = root / "data"
            csv_dir = root / "csv_files"
            config_dir.mkdir()
            data_dir.mkdir()
            csv_dir.mkdir()
            (csv_dir / "a.csv").write_text(FIXTURE_CSV_A, encoding="utf-8")
            (config_dir / "user_config.json").write_text(json.dumps({
                "csv_dir": {
                    "path": str(csv_dir),
                    "value_columns": {"heart_rate": "Heart rate (bpm)"},
                },
            }), encoding="utf-8")
            child = CSVDirectoryChild(config_dir, data_dir)
            result = asyncio.run(child.execute(
                "csv_cohort_summary",
                {"column": "heart_rate", "group_by": "sex"},
            ))
            assert "error" in result
            assert "metadata.json" in result["error"]

    def test_malformed_metadata_returns_error(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_dir = root / "config"
            data_dir = root / "data"
            csv_dir = root / "csv_files"
            config_dir.mkdir()
            data_dir.mkdir()
            csv_dir.mkdir()
            (csv_dir / "a.csv").write_text(FIXTURE_CSV_A, encoding="utf-8")
            (csv_dir / "metadata.json").write_text(
                "[1, 2, 3]", encoding="utf-8",  # JSON array, not object
            )
            (config_dir / "user_config.json").write_text(json.dumps({
                "csv_dir": {
                    "path": str(csv_dir),
                    "value_columns": {"heart_rate": "Heart rate (bpm)"},
                },
            }), encoding="utf-8")
            child = CSVDirectoryChild(config_dir, data_dir)
            result = asyncio.run(child.execute(
                "csv_cohort_summary",
                {"column": "heart_rate", "group_by": "sex"},
            ))
            assert "error" in result
            assert "object" in result["error"].lower()

    def test_files_missing_metadata_are_listed(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_dir = root / "config"
            data_dir = root / "data"
            csv_dir = root / "csv_files"
            config_dir.mkdir()
            data_dir.mkdir()
            csv_dir.mkdir()
            (csv_dir / "a.csv").write_text(FIXTURE_CSV_A, encoding="utf-8")
            (csv_dir / "b.csv").write_text(FIXTURE_CSV_A, encoding="utf-8")
            # Only a.csv has metadata; b.csv should surface as missing.
            (csv_dir / "metadata.json").write_text(
                json.dumps({"a.csv": {"sex": "F"}}),
                encoding="utf-8",
            )
            (config_dir / "user_config.json").write_text(json.dumps({
                "csv_dir": {
                    "path": str(csv_dir),
                    "value_columns": {"heart_rate": "Heart rate (bpm)"},
                },
            }), encoding="utf-8")
            child = CSVDirectoryChild(config_dir, data_dir)
            result = asyncio.run(child.execute(
                "csv_cohort_summary",
                {"column": "heart_rate", "group_by": "sex"},
            ))
            assert "error" not in result
            assert result["missing_metadata"] == ["b.csv"]


class TestForceDeclineHandler:
    """csv_force_decline handler — per-file fatigue diagnostic (ADR 0015)."""

    def test_returns_decline_summary(self, csv_child: CSVDirectoryChild):
        result = asyncio.run(csv_child.execute(
            "csv_force_decline",
            {"file_id": "fixture_a.csv", "column": "heart_rate"},
        ))
        assert isinstance(result, dict)
        assert "error" not in result
        assert result["filename"] == "fixture_a.csv"
        assert result["column"] == "heart_rate"
        assert "peak" in result
        assert "decline_pct_total" in result

    def test_missing_file_returns_error(self, csv_child: CSVDirectoryChild):
        result = asyncio.run(csv_child.execute(
            "csv_force_decline",
            {"file_id": "does-not-exist.csv", "column": "heart_rate"},
        ))
        assert "error" in result

    def test_unknown_column_returns_error(self, csv_child: CSVDirectoryChild):
        result = asyncio.run(csv_child.execute(
            "csv_force_decline",
            {"file_id": "fixture_a.csv", "column": "no_such_column"},
        ))
        # The validator filters allowed_values; the handler is the
        # second guard. Either layer surfaces an error dict.
        assert "error" in result

    def test_oversize_csv_surfaces_oserror(
        self, monkeypatch, csv_child: CSVDirectoryChild,
    ):
        """force_decline OSError-on-read branch (child.py:845-846).

        Lower MAX_CSV_BYTES below the fixture file size; the size guard
        in _read_csv raises OSError, which the handler must catch and
        return as an error dict (not propagate)."""
        from biosensor_mcp.children.csv_dir import child as child_mod

        monkeypatch.setattr(child_mod, "MAX_CSV_BYTES", 10)  # tiny
        result = asyncio.run(csv_child.execute(
            "csv_force_decline",
            {"file_id": "fixture_a.csv", "column": "heart_rate"},
        ))
        assert "error" in result
        assert "too large" in result["error"].lower()


class TestCohortSummaryFailureBranches:
    """csv_cohort_summary fail-closed branches (ADR 0015 § Criticality
    classification — HIGH region per ADR 0014).

    These tests cover the newly-uncovered HIGH lines flagged by
    coverage-criticality-mapper on the v6.5.0 build:
    `_load_metadata_sidecar` JSONDecodeError + malformed-entry, the
    "csv dir not found" guard, MAX_COHORT_FILES cap, missing-group-field
    surface path, per-file load_errors path, and the unknown-metric
    defensive double-check."""

    def _make_child(
        self,
        tmpdir: Path,
        *,
        metadata: object = None,
        metadata_raw: str | None = None,
        extra_csvs: int = 0,
        omit_metadata: bool = False,
    ) -> CSVDirectoryChild:
        config_dir = tmpdir / "config"
        data_dir = tmpdir / "data"
        csv_dir = tmpdir / "csv_files"
        config_dir.mkdir()
        data_dir.mkdir()
        csv_dir.mkdir()

        (csv_dir / "a.csv").write_text(FIXTURE_CSV_A, encoding="utf-8")
        (csv_dir / "b.csv").write_text(FIXTURE_CSV_A, encoding="utf-8")
        for i in range(extra_csvs):
            (csv_dir / f"extra_{i:03d}.csv").write_text(
                FIXTURE_CSV_A, encoding="utf-8",
            )

        if not omit_metadata:
            if metadata_raw is not None:
                (csv_dir / "metadata.json").write_text(
                    metadata_raw, encoding="utf-8",
                )
            elif metadata is not None:
                (csv_dir / "metadata.json").write_text(
                    json.dumps(metadata), encoding="utf-8",
                )

        (config_dir / "user_config.json").write_text(json.dumps({
            "csv_dir": {
                "path": str(csv_dir),
                "value_columns": {"heart_rate": "Heart rate (bpm)"},
            },
        }), encoding="utf-8")
        return CSVDirectoryChild(config_dir, data_dir)

    def test_unparseable_sidecar_returns_error(self):
        """`_load_metadata_sidecar` JSONDecodeError catch (child.py:710-711)."""
        with TemporaryDirectory() as tmp:
            child = self._make_child(
                Path(tmp), metadata_raw="this is not json {{{",
            )
            result = asyncio.run(child.execute(
                "csv_cohort_summary",
                {"column": "heart_rate", "group_by": "sex"},
            ))
            assert "error" in result
            assert "could not read metadata.json" in result["error"]

    def test_sidecar_entry_not_dict_returns_error(self):
        """`_load_metadata_sidecar` malformed-entry branch (child.py:720-724)."""
        with TemporaryDirectory() as tmp:
            child = self._make_child(
                Path(tmp),
                metadata={"a.csv": 42, "b.csv": {"sex": "M"}},
            )
            result = asyncio.run(child.execute(
                "csv_cohort_summary",
                {"column": "heart_rate", "group_by": "sex"},
            ))
            assert "error" in result
            assert "must be a JSON object of fields" in result["error"]

    def test_csv_dir_missing_after_init_returns_error(self, monkeypatch):
        """`_handle_cohort_summary` csv-dir-not-found guard (child.py:736-737).

        Models the case where the configured directory was removed
        between init and execute — child.py logs a warning at init but
        does not raise; tool calls are expected to surface the error."""
        with TemporaryDirectory() as tmp:
            child = self._make_child(
                Path(tmp), metadata={"a.csv": {"sex": "F"}, "b.csv": {"sex": "M"}},
            )
            # Point the child at a nonexistent directory after init.
            child._csv_path = Path(tmp) / "nonexistent_dir"
            result = asyncio.run(child.execute(
                "csv_cohort_summary",
                {"column": "heart_rate", "group_by": "sex"},
            ))
            assert "error" in result
            assert "CSV directory not found" in result["error"]

    def test_too_many_files_returns_cap_error(self, monkeypatch):
        """`_handle_cohort_summary` MAX_COHORT_FILES cap (child.py:754-761).

        Lower the cap to 3, write 5 CSVs — handler returns explicit
        "too many files" error rather than scanning silently."""
        from biosensor_mcp.children.csv_dir import child as child_mod

        with TemporaryDirectory() as tmp:
            metadata = {"a.csv": {"sex": "F"}, "b.csv": {"sex": "M"}}
            for i in range(5):
                metadata[f"extra_{i:03d}.csv"] = {"sex": "F"}
            child = self._make_child(
                Path(tmp), metadata=metadata, extra_csvs=5,
            )
            monkeypatch.setattr(child_mod, "MAX_COHORT_FILES", 3)
            result = asyncio.run(child.execute(
                "csv_cohort_summary",
                {"column": "heart_rate", "group_by": "sex"},
            ))
            assert "error" in result
            assert "too many files" in result["error"]

    def test_files_missing_group_field_are_listed(self):
        """`_handle_cohort_summary` missing_group_field path (child.py:776-778).

        File has metadata but lacks the requested group_by field —
        surfaces as `missing_group_field`, not `missing_metadata`."""
        with TemporaryDirectory() as tmp:
            child = self._make_child(
                Path(tmp),
                metadata={
                    "a.csv": {"sex": "F", "age": 24},
                    "b.csv": {"age": 27},  # has metadata but no `sex`
                },
            )
            result = asyncio.run(child.execute(
                "csv_cohort_summary",
                {"column": "heart_rate", "group_by": "sex"},
            ))
            assert "error" not in result
            assert result["missing_group_field"] == ["b.csv"]
            assert "missing_metadata" not in result  # b.csv has metadata, just not the field

    def test_oversize_csv_surfaces_load_error(self, monkeypatch):
        """`_handle_cohort_summary` per-file load_errors path (child.py:783-785).

        A CSV that fails to load (size guard raises OSError) is captured
        in `load_errors` and the cohort proceeds with the others."""
        from biosensor_mcp.children.csv_dir import child as child_mod

        with TemporaryDirectory() as tmp:
            child = self._make_child(
                Path(tmp),
                metadata={
                    "a.csv": {"sex": "F"},
                    "b.csv": {"sex": "M"},
                },
            )
            monkeypatch.setattr(child_mod, "MAX_CSV_BYTES", 10)
            result = asyncio.run(child.execute(
                "csv_cohort_summary",
                {"column": "heart_rate", "group_by": "sex"},
            ))
            assert "error" not in result
            assert "load_errors" in result
            error_files = {e["filename"] for e in result["load_errors"]}
            assert error_files == {"a.csv", "b.csv"}

    def test_column_missing_in_file_surfaces_load_error(self):
        """`_handle_cohort_summary` column-not-found branch (child.py:787-792)."""
        with TemporaryDirectory() as tmp:
            csv_dir = Path(tmp) / "csv_files"
            config_dir = Path(tmp) / "config"
            data_dir = Path(tmp) / "data"
            csv_dir.mkdir()
            config_dir.mkdir()
            data_dir.mkdir()

            # a.csv has heart_rate; b.csv only has glucose.
            (csv_dir / "a.csv").write_text(FIXTURE_CSV_A, encoding="utf-8")
            (csv_dir / "b.csv").write_text(
                "timestamp,glucose\n2026-01-01T10:00:00Z,95\n",
                encoding="utf-8",
            )
            (csv_dir / "metadata.json").write_text(json.dumps({
                "a.csv": {"sex": "F"},
                "b.csv": {"sex": "M"},
            }), encoding="utf-8")

            (config_dir / "user_config.json").write_text(json.dumps({
                "csv_dir": {
                    "path": str(csv_dir),
                    "value_columns": {
                        "heart_rate": "Heart rate (bpm)",
                        "glucose": "Blood glucose (mg/dL)",
                    },
                },
            }), encoding="utf-8")
            child = CSVDirectoryChild(config_dir, data_dir)

            result = asyncio.run(child.execute(
                "csv_cohort_summary",
                {"column": "heart_rate", "group_by": "sex"},
            ))
            assert "error" not in result
            assert "load_errors" in result
            assert result["load_errors"][0]["filename"] == "b.csv"
            assert "heart_rate" in result["load_errors"][0]["error"]

    def test_unknown_metric_defensive_check_returns_error(self):
        """`_handle_cohort_summary` unknown-metric defensive double-check
        (child.py:801-805).

        ParamValidator should reject unknown metrics, but execute() is
        called directly here, bypassing the router. The handler's defensive
        ValueError catch must surface a clean error dict rather than
        propagate the exception."""
        with TemporaryDirectory() as tmp:
            child = self._make_child(
                Path(tmp),
                metadata={"a.csv": {"sex": "F"}, "b.csv": {"sex": "M"}},
            )
            result = asyncio.run(child.execute(
                "csv_cohort_summary",
                {
                    "column": "heart_rate",
                    "group_by": "sex",
                    "metric": "frobnicate",
                },
            ))
            assert "error" in result
            assert "Unknown metric" in result["error"]


class TestExtractTimestamps:
    """`_extract_timestamps` early-return paths (child.py:865-866, 872-873).

    Newly-added helper; coverage-criticality-mapper flagged the
    no-timestamp-column and parse-failure branches as uncovered."""

    def test_no_timestamp_column_returns_none(self):
        """No configured timestamp_column AND no header matches the
        detector — the helper returns None (child.py:865-866)."""
        with TemporaryDirectory() as tmp:
            csv_dir = Path(tmp) / "csv_files"
            config_dir = Path(tmp) / "config"
            data_dir = Path(tmp) / "data"
            csv_dir.mkdir()
            config_dir.mkdir()
            data_dir.mkdir()

            (csv_dir / "a.csv").write_text(
                "id,heart_rate,glucose\n1,72,95\n2,74,96\n",
                encoding="utf-8",
            )
            (config_dir / "user_config.json").write_text(json.dumps({
                "csv_dir": {
                    "path": str(csv_dir),
                    "value_columns": {
                        "heart_rate": "Heart rate (bpm)",
                        "glucose": "Blood glucose (mg/dL)",
                    },
                },
            }), encoding="utf-8")
            child = CSVDirectoryChild(config_dir, data_dir)

            result = asyncio.run(child.execute(
                "csv_force_decline",
                {"file_id": "a.csv", "column": "heart_rate"},
            ))
            assert "error" not in result
            # Without timestamps the temporal fields are absent.
            assert "decline_rate_per_min" not in result
            assert "time_to_50pct_drop_s" not in result

    def test_unparseable_timestamps_returns_none(self):
        """Configured timestamp column exists but rows have garbage
        — parse_timestamp returns None on first row, helper short-
        circuits to None (child.py:872-873)."""
        with TemporaryDirectory() as tmp:
            csv_dir = Path(tmp) / "csv_files"
            config_dir = Path(tmp) / "config"
            data_dir = Path(tmp) / "data"
            csv_dir.mkdir()
            config_dir.mkdir()
            data_dir.mkdir()

            (csv_dir / "a.csv").write_text(
                "timestamp,heart_rate\n"
                "not-a-date,72\n"
                "also-not-a-date,74\n",
                encoding="utf-8",
            )
            (config_dir / "user_config.json").write_text(json.dumps({
                "csv_dir": {
                    "path": str(csv_dir),
                    "timestamp_column": "timestamp",
                    "value_columns": {"heart_rate": "Heart rate (bpm)"},
                },
            }), encoding="utf-8")
            child = CSVDirectoryChild(config_dir, data_dir)

            result = asyncio.run(child.execute(
                "csv_force_decline",
                {"file_id": "a.csv", "column": "heart_rate"},
            ))
            assert "error" not in result
            # Unparseable timestamps → no temporal fields.
            assert "decline_rate_per_min" not in result


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


# ═══════════════════════════════════════════════════════════════
# UTF-8 BOM transparency (regression for v6.9.2 bug #2)
# ═══════════════════════════════════════════════════════════════


class TestBomTransparency:
    """v6.9.2 bug #2 — Excel-touched / PowerShell-redirected CSVs
    carry a leading byte-order mark.  Before v6.9.2 every CSV-open
    used ``encoding='utf-8'`` not ``'utf-8-sig'``, so the first
    column header silently became ``﻿<col>`` and every downstream
    tool returned ``column not found``.  Fixed across all four CSV-
    open sites in csv_dir/child.py (auto-detect, _read_headers,
    _read_csv, _quick_row_count).
    """

    def test_csv_with_leading_bom_reads_clean_first_header(
        self, tmp_path: Path,
    ):
        config_dir = tmp_path / "config"
        data_dir = tmp_path / "data"
        csv_dir = tmp_path / "csv_files"
        for d in (config_dir, data_dir, csv_dir):
            d.mkdir()
        (csv_dir / "fixture.csv").write_bytes(
            b"\xef\xbb\xbf" + FIXTURE_CSV_A.encode("utf-8"),
        )
        (config_dir / "user_config.json").write_text(
            json.dumps({
                "csv_dir": {
                    "path": str(csv_dir),
                    "timestamp_column": "timestamp",
                    "value_columns": {
                        "heart_rate": "Heart rate (bpm)",
                        "glucose": "Blood glucose (mg/dL)",
                    },
                },
            }),
            encoding="utf-8",
        )
        child = CSVDirectoryChild(config_dir, data_dir)
        try:
            result = asyncio.run(child.execute(
                "csv_list_files", {"limit": 5},
            ))
            assert "error" not in result
            cols = result["files"][0]["columns"]
            assert cols[0] == "timestamp"
            assert "﻿" not in cols[0]
            detail = asyncio.run(child.execute(
                "csv_file_detail", {"file_id": "fixture.csv"},
            ))
            assert "error" not in detail
        finally:
            # csv_dir child doesn't own a SQLite handle but be defensive.
            close = getattr(child, "close", None)
            if callable(close):
                close()
