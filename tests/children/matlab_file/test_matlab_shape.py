# ruff: noqa: I001, E402
"""
Shape + handler tests for MATLABFileChild.

Requires scipy (the [matlab] optional extra). The whole module skips
when scipy is unavailable via ``pytest.importorskip`` at the top.

Mirrors the csv_dir shape-test pattern (ADR 0002 / ADR 0008 / ADR 0013
contract surface).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Generator
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

scipy_io = pytest.importorskip("scipy.io")

import numpy as np

from tailor.children.matlab_file import MATLABFileChild
from tailor.framework.interfaces import (
    CostEstimate,
    SUBJECT_ID_SCHEMA,
    ToolDefinition,
    ValidationSchema,
)
from tailor.framework.router import RouterMCP

SUBJECT_ID_PATTERN = r"^[A-Za-z0-9_\-]{1,64}$"


@pytest.fixture
def matlab_child() -> Generator[MATLABFileChild, None, None]:
    """MATLABFileChild backed by two synthetic .mat fixtures + sidecar."""
    with TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        config_dir = root / "config"
        data_dir = root / "data"
        mat_dir = root / "mat_files"
        config_dir.mkdir()
        data_dir.mkdir()
        mat_dir.mkdir()

        # Subject A: ramp-and-decline force signal
        scipy_io.savemat(
            str(mat_dir / "subject_a.mat"),
            {
                "force": np.array([1.0, 2.0, 3.0, 4.0, 5.0, 4.0, 3.0, 2.0, 1.0]),
                "emg_env": np.array([0.1, 0.2, 0.3, 0.4, 0.5]),
            },
            format="5",
        )
        scipy_io.savemat(
            str(mat_dir / "subject_b.mat"),
            {
                "force": np.array([2.0, 4.0, 6.0, 4.0, 2.0]),
                "emg_env": np.array([0.2, 0.4, 0.6]),
            },
            format="5",
        )

        (mat_dir / "metadata.json").write_text(
            json.dumps({
                "subject_a.mat": {"sex": "F", "group": "control"},
                "subject_b.mat": {"sex": "M", "group": "test"},
            }),
            encoding="utf-8",
        )

        user_config = {"matlab_file": {"path": str(mat_dir)}}
        (config_dir / "user_config.json").write_text(
            json.dumps(user_config), encoding="utf-8",
        )

        yield MATLABFileChild(config_dir, data_dir)


VALID_PARAMS = {
    "matlab_list_files": {"limit": 10},
    "matlab_file_detail": {"file_id": "subject_a.mat"},
    "matlab_summary_report": {"file_id": "subject_a.mat"},
    "matlab_cohort_summary": {
        "variable": "force", "group_by": "sex", "metric": "mean",
    },
    "matlab_downsampled": {
        "file_id": "subject_a.mat", "variable": "force", "interval": 2,
    },
    "matlab_raw_array": {
        "file_id": "subject_a.mat", "variable": "force", "precision": 3,
    },
}


# ═══════════════════════════════════════════════════════════════
# ABC SURFACE
# ═══════════════════════════════════════════════════════════════


class TestRequiredAbstractSurface:
    def test_domain(self, matlab_child: MATLABFileChild):
        assert matlab_child.domain == "matlab_file"

    def test_display_name(self, matlab_child: MATLABFileChild):
        assert isinstance(matlab_child.display_name, str)
        assert matlab_child.display_name.strip()

    def test_tool_definitions_six_tools_three_tiers(
        self, matlab_child: MATLABFileChild,
    ):
        defs = matlab_child.tool_definitions
        assert isinstance(defs, list)
        assert len(defs) == 6
        for td in defs:
            assert isinstance(td, ToolDefinition)
            assert td.tier in (1, 2, 3)
        assert {td.tier for td in defs} == {1, 2, 3}

    def test_param_schemas_match_tool_definitions(
        self, matlab_child: MATLABFileChild,
    ):
        def_names = {td.name for td in matlab_child.tool_definitions}
        schema_names = set(matlab_child.param_schemas.keys())
        assert def_names == schema_names


# ═══════════════════════════════════════════════════════════════
# SUBJECT_ID CONSISTENCY (ADR 0002)
# ═══════════════════════════════════════════════════════════════


class TestSubjectIdConsistency:
    def test_every_tool_declares_subject_id_in_param_schemas(
        self, matlab_child: MATLABFileChild,
    ):
        for tool_name, tool_schema in matlab_child.param_schemas.items():
            assert "subject_id" in tool_schema, (
                f"{tool_name} missing subject_id in param_schemas"
            )
            entry = tool_schema["subject_id"]
            assert isinstance(entry, ValidationSchema)
            assert entry.type is str
            assert entry.required is False
            assert entry.pattern == SUBJECT_ID_PATTERN

    def test_every_tool_declares_subject_id_in_tool_definitions(
        self, matlab_child: MATLABFileChild,
    ):
        for td in matlab_child.tool_definitions:
            assert "subject_id" in td.params
            entry = td.params["subject_id"]
            assert entry["type"] == "string"
            assert entry["required"] is False
            assert isinstance(entry["description"], str)
            assert entry["description"].strip()

    def test_canonical_subject_id_schema_pattern(self):
        assert SUBJECT_ID_SCHEMA.type is str
        assert SUBJECT_ID_SCHEMA.required is False
        assert SUBJECT_ID_SCHEMA.pattern == SUBJECT_ID_PATTERN


# ═══════════════════════════════════════════════════════════════
# ROUTER REGISTRATION
# ═══════════════════════════════════════════════════════════════


class TestRouterRegistration:
    def test_registers_without_error(
        self, matlab_child: MATLABFileChild, tmp_path: Path,
    ):
        router = RouterMCP(name="test", data_dir=tmp_path)
        try:
            router.register_child(matlab_child)
            tool_names = {td.name for td in matlab_child.tool_definitions}
            for name in tool_names:
                assert name in router.registered_tools
        finally:
            router.close()


# ═══════════════════════════════════════════════════════════════
# EXECUTE — EVERY HANDLER RETURNS A DICT
# ═══════════════════════════════════════════════════════════════


class TestExecuteReturnsDict:
    @pytest.mark.parametrize("tool_name", list(VALID_PARAMS.keys()))
    def test_handler_returns_dict(
        self, matlab_child: MATLABFileChild, tool_name: str,
    ):
        params = VALID_PARAMS[tool_name]
        result = asyncio.run(matlab_child.execute(tool_name, params))
        assert isinstance(result, dict)

    def test_unknown_tool_returns_error_dict(
        self, matlab_child: MATLABFileChild,
    ):
        result = asyncio.run(matlab_child.execute("nonexistent", {}))
        assert "error" in result


# ═══════════════════════════════════════════════════════════════
# COST ESTIMATION
# ═══════════════════════════════════════════════════════════════


class TestEstimateCost:
    @pytest.mark.parametrize("tool_name", list(VALID_PARAMS.keys()))
    def test_returns_cost_estimate(
        self, matlab_child: MATLABFileChild, tool_name: str,
    ):
        params = VALID_PARAMS[tool_name]
        ce = asyncio.run(matlab_child.estimate_cost(tool_name, params))
        assert isinstance(ce, CostEstimate)

    def test_tier3_advertises_cheaper_alternative(
        self, matlab_child: MATLABFileChild,
    ):
        ce = asyncio.run(matlab_child.estimate_cost(
            "matlab_raw_array",
            {"file_id": "subject_a.mat", "variable": "force"},
        ))
        assert ce.has_cheaper_alternative
        assert ce.alternative_description
        assert ce.alternative_tokens is not None


# ═══════════════════════════════════════════════════════════════
# HANDLER BEHAVIOR
# ═══════════════════════════════════════════════════════════════


class TestListFiles:
    def test_lists_both_fixtures(self, matlab_child: MATLABFileChild):
        result = asyncio.run(matlab_child.execute("matlab_list_files", {}))
        assert result["count"] == 2
        filenames = {f["filename"] for f in result["files"]}
        assert filenames == {"subject_a.mat", "subject_b.mat"}

    def test_includes_variable_metadata(self, matlab_child: MATLABFileChild):
        result = asyncio.run(matlab_child.execute("matlab_list_files", {}))
        a_entry = next(f for f in result["files"] if f["filename"] == "subject_a.mat")
        var_names = {v["name"] for v in a_entry["variables"]}
        assert {"force", "emg_env"}.issubset(var_names)


class TestFileDetail:
    def test_reports_force_summary(self, matlab_child: MATLABFileChild):
        result = asyncio.run(matlab_child.execute(
            "matlab_file_detail", {"file_id": "subject_a.mat"},
        ))
        force_entry = next(v for v in result["variables"] if v["name"] == "force")
        assert force_entry["summary"]["count"] == 9
        assert force_entry["summary"]["max"] == 5.0

    def test_missing_file_returns_error(self, matlab_child: MATLABFileChild):
        result = asyncio.run(matlab_child.execute(
            "matlab_file_detail", {"file_id": "does_not_exist.mat"},
        ))
        assert "error" in result

    def test_path_traversal_rejected(self, matlab_child: MATLABFileChild):
        result = asyncio.run(matlab_child.execute(
            "matlab_file_detail", {"file_id": "../escape.mat"},
        ))
        assert "error" in result


class TestSummaryReport:
    def test_summarises_numeric_variables(self, matlab_child: MATLABFileChild):
        result = asyncio.run(matlab_child.execute(
            "matlab_summary_report", {"file_id": "subject_a.mat"},
        ))
        assert "force" in result["numeric_summaries"]
        assert "emg_env" in result["numeric_summaries"]
        assert result["numeric_summaries"]["force"]["max"] == 5.0


class TestCohortSummary:
    def test_groups_by_sex(self, matlab_child: MATLABFileChild):
        result = asyncio.run(matlab_child.execute(
            "matlab_cohort_summary",
            {"variable": "force", "group_by": "sex", "metric": "mean"},
        ))
        assert set(result["groups"].keys()) == {"F", "M"}
        # subject_a.mat mean force = 25/9 ≈ 2.778
        assert abs(result["groups"]["F"]["mean"] - 2.778) < 0.01

    def test_missing_metadata_returns_error(
        self, matlab_child: MATLABFileChild, tmp_path: Path,
    ):
        empty_dir = tmp_path / "empty_mat"
        empty_dir.mkdir()
        cfg = tmp_path / "cfg"
        cfg.mkdir()
        (cfg / "user_config.json").write_text(
            json.dumps({"matlab_file": {"path": str(empty_dir)}}),
            encoding="utf-8",
        )
        child = MATLABFileChild(cfg, tmp_path / "data")
        result = asyncio.run(child.execute(
            "matlab_cohort_summary",
            {"variable": "force", "group_by": "sex"},
        ))
        assert "error" in result
        assert "metadata.json" in result["error"]

    def test_wrong_shape_distinct_from_wrong_name(
        self, tmp_path: Path,
    ):
        """ADR 0036 legibility commitment: a 2-D cohort matrix and a
        typo in the variable name must surface distinctly so the
        recipient can act on the deferral without guessing."""
        mat_dir = tmp_path / "mat"
        mat_dir.mkdir()
        # Subject A: 1-D force (will succeed)
        scipy_io.savemat(
            str(mat_dir / "subject_a.mat"),
            {"force": np.array([1.0, 2.0, 3.0])},
            format="5",
        )
        # Subject B: 2-D cohort matrix (variables-as-subjects shape;
        # ADR 0036 § Negative consequences names this deferral)
        scipy_io.savemat(
            str(mat_dir / "subject_b.mat"),
            {"force": np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])},
            format="5",
        )
        # Subject C: no "force" variable at all (typo case)
        scipy_io.savemat(
            str(mat_dir / "subject_c.mat"),
            {"other_signal": np.array([1.0, 2.0])},
            format="5",
        )
        (mat_dir / "metadata.json").write_text(
            json.dumps({
                "subject_a.mat": {"sex": "F"},
                "subject_b.mat": {"sex": "M"},
                "subject_c.mat": {"sex": "F"},
            }),
            encoding="utf-8",
        )
        cfg = tmp_path / "cfg"
        cfg.mkdir()
        (cfg / "user_config.json").write_text(
            json.dumps({"matlab_file": {"path": str(mat_dir)}}),
            encoding="utf-8",
        )
        child = MATLABFileChild(cfg, tmp_path / "data")
        result = asyncio.run(child.execute(
            "matlab_cohort_summary",
            {"variable": "force", "group_by": "sex"},
        ))
        assert result["variable_not_in_file"] == ["subject_c.mat"]
        assert result["variable_wrong_shape"] == ["subject_b.mat"]
        assert "variable_wrong_shape_note" in result
        assert "ADR 0036" in result["variable_wrong_shape_note"]
        # subject_a still contributes to the group
        assert result["groups"]["F"]["n"] == 1


class TestDownsampled:
    def test_decimates_force(self, matlab_child: MATLABFileChild):
        result = asyncio.run(matlab_child.execute(
            "matlab_downsampled",
            {"file_id": "subject_a.mat", "variable": "force", "interval": 2},
        ))
        # 9 samples / interval 2 → 5 samples (indices 0, 2, 4, 6, 8)
        assert len(result["samples"]) == 5

    def test_missing_variable_returns_error(self, matlab_child: MATLABFileChild):
        result = asyncio.run(matlab_child.execute(
            "matlab_downsampled",
            {"file_id": "subject_a.mat", "variable": "missing", "interval": 2},
        ))
        assert "error" in result


class TestRawArray:
    def test_returns_precision_reduced_samples(self, matlab_child: MATLABFileChild):
        result = asyncio.run(matlab_child.execute(
            "matlab_raw_array",
            {"file_id": "subject_a.mat", "variable": "force", "precision": 1},
        ))
        assert len(result["samples"]) == 9
        # Precision 1 means at most 1 decimal place
        for s in result["samples"]:
            assert round(s, 1) == s


# ═══════════════════════════════════════════════════════════════
# ADR 0013 — PURGE_CACHE
# ═══════════════════════════════════════════════════════════════


class TestPurgeCache:
    def test_returns_no_op_with_reason(self, matlab_child: MATLABFileChild):
        result = matlab_child.purge_cache()
        assert result["rows_purged"] == 0
        assert result["tables_touched"] == []
        assert "reason" in result
        assert "framework owns no derivative cache" in result["reason"]


# ═══════════════════════════════════════════════════════════════
# ADR 0036 — v7.3 HDF5 REJECTION
# ═══════════════════════════════════════════════════════════════


class TestHDF5Rejection:
    def test_v73_file_rejected_with_clear_error(
        self, matlab_child: MATLABFileChild, tmp_path: Path,
    ):
        # Synthesize a fake v7.3 file by writing the HDF5 magic bytes.
        # We don't need a real HDF5 file — the magic-byte check fires
        # before scipy is involved.
        fake_v73 = matlab_child._mat_path / "v73_fake.mat"
        fake_v73.write_bytes(b"\x89HDF\r\n\x1a\n" + b"\x00" * 256)
        result = asyncio.run(matlab_child.execute(
            "matlab_file_detail", {"file_id": "v73_fake.mat"},
        ))
        assert "error" in result
        assert "v7.3" in result["error"]
        assert "ADR 0036" in result["error"]


# ═══════════════════════════════════════════════════════════════
# VAULTABLE TOOLS — EMPTY UNTIL RENDERER LANDS
# ═══════════════════════════════════════════════════════════════


class TestVaultableTools:
    def test_empty_until_renderer_lands(self, matlab_child: MATLABFileChild):
        assert matlab_child.vaultable_tools == []


# ═══════════════════════════════════════════════════════════════
# DATA_TYPES_FOR_TOOL — NARROWS PER-CALL
# ═══════════════════════════════════════════════════════════════


class TestDataTypesForTool:
    def test_streams_tools_narrow_to_requested_variable(
        self, matlab_child: MATLABFileChild,
    ):
        out = matlab_child.data_types_for_tool(
            "matlab_downsampled", {"variable": "EMG_envelope"},
        )
        assert out == ["EMG_envelope"]

    def test_tier1_tools_use_full_data_types(
        self, matlab_child: MATLABFileChild,
    ):
        out = matlab_child.data_types_for_tool("matlab_file_detail", {})
        assert out == matlab_child.consent_info.data_types
