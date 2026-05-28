"""
Shape + handler tests for StrongMotionChild.

Contract tests: every structural invariant a child must satisfy to
register with the router, plus behavioural checks on each tool against
synthetic COSMOS V1 records written into a temp dir (no real seismic
files — ADR 0042). Retargeted from the template / matlab_file shape
tests (ADR 0002 / ADR 0008 / ADR 0013 / ADR 0015 surface).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Generator
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from tailor.children.strong_motion import StrongMotionChild
from tailor.framework.interfaces import (
    ENTITY_ID_SCHEMA,
    CostEstimate,
    ToolDefinition,
    ValidationSchema,
)
from tailor.framework.router import RouterMCP

from ._synth import make_v1_text

ENTITY_ID_PATTERN = r"^[A-Za-z0-9_\-]{1,64}$"


@pytest.fixture
def sm_child() -> Generator[StrongMotionChild, None, None]:
    """StrongMotionChild backed by three synthetic V1 records + sidecar."""
    with TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        config_dir = root / "config"
        data_dir = root / "data"
        rec_dir = root / "records"
        config_dir.mkdir()
        data_dir.mkdir()
        rec_dir.mkdir()

        (rec_dir / "tarzana_ch1.v1").write_text(
            make_v1_text(
                [0.1, -0.5, 1.2, 1.927, -0.8, 0.3, -1.5, 0.05],
                dt=0.01, station="TARZANA", channel=1, azimuth=90,
            ),
            encoding="utf-8",
        )
        (rec_dir / "tarzana_ch2.v1").write_text(
            make_v1_text(
                [0.05, 0.4, -0.9, 0.6, -0.3, 0.2],
                dt=0.01, station="TARZANA", channel=2, azimuth=180,
            ),
            encoding="utf-8",
        )
        (rec_dir / "sylmar_ch1.raw").write_text(
            make_v1_text(
                [0.2, -0.7, 0.9, -0.4, 0.1],
                dt=0.02, station="SYLMAR", channel=1, azimuth=90,
            ),
            encoding="utf-8",
        )

        (rec_dir / "metadata.json").write_text(
            json.dumps({
                "tarzana_ch1.v1": {"site": "tarzana", "event": "northridge"},
                "tarzana_ch2.v1": {"site": "tarzana", "event": "northridge"},
                "sylmar_ch1.raw": {"site": "sylmar", "event": "northridge"},
            }),
            encoding="utf-8",
        )

        (config_dir / "user_config.json").write_text(
            json.dumps({"strong_motion": {"path": str(rec_dir)}}),
            encoding="utf-8",
        )

        yield StrongMotionChild(config_dir, data_dir)


VALID_PARAMS = {
    "seismic_list_records": {"limit": 10},
    "seismic_record_summary": {"file_id": "tarzana_ch1.v1"},
    "seismic_cohort_summary": {"metric": "pga_g", "group_by": "site"},
    "seismic_downsampled": {"file_id": "tarzana_ch1.v1", "interval": 2},
    "seismic_full_trace": {"file_id": "tarzana_ch1.v1", "precision": 3},
}


# ═══════════════════════════════════════════════════════════════
# ABC SURFACE
# ═══════════════════════════════════════════════════════════════


class TestRequiredAbstractSurface:
    def test_domain(self, sm_child: StrongMotionChild):
        assert sm_child.domain == "strong_motion"

    def test_display_name(self, sm_child: StrongMotionChild):
        assert sm_child.display_name == "Strong Motion (COSMOS V1)"

    def test_tool_definitions_five_tools_three_tiers(self, sm_child: StrongMotionChild):
        defs = sm_child.tool_definitions
        assert isinstance(defs, list)
        assert len(defs) == 5, "3 Tier-1 + 1 Tier-2 + 1 Tier-3"
        for td in defs:
            assert isinstance(td, ToolDefinition)
            assert td.tier in (1, 2, 3)
        assert {td.tier for td in defs} == {1, 2, 3}

    def test_param_schemas_match_tool_definitions(self, sm_child: StrongMotionChild):
        def_names = {td.name for td in sm_child.tool_definitions}
        schema_names = set(sm_child.param_schemas.keys())
        assert def_names == schema_names


# ═══════════════════════════════════════════════════════════════
# ENTITY_ID CONSISTENCY (ADR 0002)
# ═══════════════════════════════════════════════════════════════


class TestEntityIdConsistency:
    def test_every_tool_declares_entity_id_in_param_schemas(self, sm_child: StrongMotionChild):
        for tool_name, tool_schema in sm_child.param_schemas.items():
            assert "entity_id" in tool_schema, f"{tool_name} missing entity_id schema"
            entry = tool_schema["entity_id"]
            assert isinstance(entry, ValidationSchema)
            assert entry.type is str
            assert entry.required is False
            assert entry.pattern == ENTITY_ID_PATTERN

    def test_every_tool_declares_entity_id_in_tool_definitions(self, sm_child: StrongMotionChild):
        for td in sm_child.tool_definitions:
            assert "entity_id" in td.params, f"{td.name} missing entity_id param doc"
            entry = td.params["entity_id"]
            assert entry["type"] == "string"
            assert entry["required"] is False
            assert isinstance(entry["description"], str)
            assert entry["description"].strip()

    def test_canonical_entity_id_schema_pattern(self):
        assert ENTITY_ID_SCHEMA.type is str
        assert ENTITY_ID_SCHEMA.required is False
        assert ENTITY_ID_SCHEMA.pattern == ENTITY_ID_PATTERN


# ═══════════════════════════════════════════════════════════════
# ROUTER REGISTRATION
# ═══════════════════════════════════════════════════════════════


class TestRouterRegistration:
    def test_registers_without_error(self, sm_child: StrongMotionChild, tmp_path: Path):
        router = RouterMCP(name="test", data_dir=tmp_path)
        try:
            router.register_child(sm_child)
            assert "strong_motion" in router.registered_domains
            for td in sm_child.tool_definitions:
                assert td.name in router.registered_tools
        finally:
            router.close()


# ═══════════════════════════════════════════════════════════════
# EXECUTE — EVERY HANDLER RETURNS A DICT
# ═══════════════════════════════════════════════════════════════


class TestExecuteReturnsDict:
    @pytest.mark.parametrize("tool_name", list(VALID_PARAMS.keys()))
    def test_handler_returns_dict(self, sm_child: StrongMotionChild, tool_name: str):
        result = asyncio.run(sm_child.execute(tool_name, VALID_PARAMS[tool_name]))
        assert isinstance(result, dict)
        assert "error" not in result, f"{tool_name} errored: {result.get('error')}"

    def test_unknown_tool_returns_error_dict(self, sm_child: StrongMotionChild):
        result = asyncio.run(sm_child.execute("nonexistent", {}))
        assert "error" in result


# ═══════════════════════════════════════════════════════════════
# COST ESTIMATION
# ═══════════════════════════════════════════════════════════════


class TestEstimateCost:
    @pytest.mark.parametrize("tool_name", list(VALID_PARAMS.keys()))
    def test_returns_cost_estimate(self, sm_child: StrongMotionChild, tool_name: str):
        ce = asyncio.run(sm_child.estimate_cost(tool_name, VALID_PARAMS[tool_name]))
        assert isinstance(ce, CostEstimate)
        assert ce.tokens >= 0

    def test_tier3_advertises_cheaper_alternative(self, sm_child: StrongMotionChild):
        ce = asyncio.run(sm_child.estimate_cost(
            "seismic_full_trace", {"file_id": "tarzana_ch1.v1"},
        ))
        assert ce.has_cheaper_alternative
        assert ce.alternative_tokens > 0
        assert ce.alternative_tokens < ce.tokens
        assert ce.alternative_description.strip()


# ═══════════════════════════════════════════════════════════════
# HANDLER BEHAVIOUR
# ═══════════════════════════════════════════════════════════════


class TestListRecords:
    def test_lists_all_three_records(self, sm_child: StrongMotionChild):
        result = asyncio.run(sm_child.execute("seismic_list_records", {}))
        assert result["count"] == 3
        names = {r["filename"] for r in result["records"]}
        assert names == {"tarzana_ch1.v1", "tarzana_ch2.v1", "sylmar_ch1.raw"}

    def test_includes_channel_and_azimuth(self, sm_child: StrongMotionChild):
        result = asyncio.run(sm_child.execute("seismic_list_records", {}))
        ch1 = next(r for r in result["records"] if r["filename"] == "tarzana_ch1.v1")
        assert ch1["channel"] == 1
        assert ch1["azimuth"] == 90
        assert ch1["n_samples"] == 8


class TestRecordSummary:
    def test_computes_pga_arias_duration_spectrum(self, sm_child: StrongMotionChild):
        result = asyncio.run(sm_child.execute(
            "seismic_record_summary", {"file_id": "tarzana_ch1.v1"},
        ))
        assert result["pga_g"] == pytest.approx(1.927, abs=1e-6)
        assert result["arias_intensity_ms"] >= 0.0
        assert result["strong_motion_duration_s"] >= 0.0
        assert len(result["spectral_acceleration_g"]) == 5
        assert result["channel"] == 1
        assert result["azimuth"] == 90

    def test_missing_file_returns_error(self, sm_child: StrongMotionChild):
        result = asyncio.run(sm_child.execute(
            "seismic_record_summary", {"file_id": "does_not_exist.v1"},
        ))
        assert "error" in result

    def test_path_traversal_rejected(self, sm_child: StrongMotionChild):
        result = asyncio.run(sm_child.execute(
            "seismic_record_summary", {"file_id": "../escape.v1"},
        ))
        assert "error" in result


class TestCohortSummary:
    def test_groups_by_site(self, sm_child: StrongMotionChild):
        result = asyncio.run(sm_child.execute(
            "seismic_cohort_summary", {"metric": "pga_g", "group_by": "site"},
        ))
        assert set(result["groups"].keys()) == {"tarzana", "sylmar"}
        assert result["groups"]["tarzana"]["n"] == 2
        assert result["groups"]["sylmar"]["n"] == 1

    def test_no_group_by_aggregates_all_as_single_cohort(self, sm_child: StrongMotionChild):
        result = asyncio.run(sm_child.execute(
            "seismic_cohort_summary", {"metric": "pga_g"},
        ))
        assert set(result["groups"].keys()) == {"all"}
        assert result["groups"]["all"]["n"] == 3

    def test_group_by_without_sidecar_returns_error(self, tmp_path: Path):
        rec_dir = tmp_path / "no_sidecar"
        rec_dir.mkdir()
        (rec_dir / "a.v1").write_text(make_v1_text([0.1, 0.2, 0.3], dt=0.01), encoding="utf-8")
        cfg = tmp_path / "cfg"
        cfg.mkdir()
        (cfg / "user_config.json").write_text(
            json.dumps({"strong_motion": {"path": str(rec_dir)}}), encoding="utf-8",
        )
        child = StrongMotionChild(cfg, tmp_path / "data")
        result = asyncio.run(child.execute(
            "seismic_cohort_summary", {"metric": "pga_g", "group_by": "site"},
        ))
        assert "error" in result
        assert "metadata.json" in result["error"]


class TestDownsampled:
    def test_decimates_trace(self, sm_child: StrongMotionChild):
        result = asyncio.run(sm_child.execute(
            "seismic_downsampled", {"file_id": "tarzana_ch1.v1", "interval": 2},
        ))
        # 8 samples / interval 2 -> 4 (indices 0,2,4,6)
        assert len(result["samples"]) == 4
        assert result["units"] == "g"


class TestFullTrace:
    def test_returns_precision_reduced_samples(self, sm_child: StrongMotionChild):
        result = asyncio.run(sm_child.execute(
            "seismic_full_trace", {"file_id": "tarzana_ch1.v1", "precision": 1},
        ))
        assert len(result["samples"]) == 8
        for s in result["samples"]:
            assert round(s, 1) == s


# ═══════════════════════════════════════════════════════════════
# PARSE REFUSAL THROUGH THE CHILD (graceful, no breaker trip)
# ═══════════════════════════════════════════════════════════════


class TestParseRefusalSurfacing:
    def test_non_v1_file_surfaces_per_file_error_in_list(self, sm_child: StrongMotionChild):
        # A junk file in the records dir must surface a per-file error,
        # not abort the listing.
        (sm_child._sm_path / "junk.v1").write_text(
            "not a cosmos record at all\n", encoding="utf-8",
        )
        result = asyncio.run(sm_child.execute("seismic_list_records", {}))
        junk = next(r for r in result["records"] if r["filename"] == "junk.v1")
        assert "error" in junk

    def test_non_v1_file_summary_returns_error_dict(self, sm_child: StrongMotionChild):
        (sm_child._sm_path / "junk.raw").write_text(
            "time,accel\n0,0.1\n", encoding="utf-8",
        )
        result = asyncio.run(sm_child.execute(
            "seismic_record_summary", {"file_id": "junk.raw"},
        ))
        assert "error" in result


# ═══════════════════════════════════════════════════════════════
# ADR 0013 — PURGE_CACHE  /  VAULTABLE TOOLS
# ═══════════════════════════════════════════════════════════════


class TestPurgeCache:
    def test_returns_no_op_with_reason(self, sm_child: StrongMotionChild):
        result = sm_child.purge_cache()
        assert result["rows_purged"] == 0
        assert result["tables_touched"] == []
        assert "reason" in result
        assert "no derivative cache" in result["reason"]


class TestVaultableTools:
    def test_empty_until_renderer_lands(self, sm_child: StrongMotionChild):
        assert sm_child.vaultable_tools == []


# ═══════════════════════════════════════════════════════════════
# CONFIG VALIDATION
# ═══════════════════════════════════════════════════════════════


class TestConfigValidation:
    def test_missing_path_raises(self, tmp_path: Path):
        cfg = tmp_path / "cfg"
        cfg.mkdir()
        (cfg / "user_config.json").write_text(
            json.dumps({"strong_motion": {}}), encoding="utf-8",
        )
        with pytest.raises(ValueError):
            StrongMotionChild(cfg, tmp_path / "data")
