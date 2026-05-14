# ruff: noqa: I001, E402
"""
Shape + handler tests for RedcapFileChild.

Mirrors the matlab_file shape-test pattern (ADR 0002 / ADR 0008 / ADR
0013 / ADR 0037 contract surface).

Stdlib only — no scipy, no numpy. The REDCap child reads CSV/JSON
exports with stdlib ``csv`` and ``json``.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from collections.abc import Generator
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from tailor.children.redcap import RedcapFileChild, RedcapPHIScrubber
from tailor.framework.interfaces import (
    SUBJECT_ID_SCHEMA,
    CostEstimate,
    ToolDefinition,
    ValidationSchema,
)
from tailor.framework.router import RouterMCP

SUBJECT_ID_PATTERN = r"^[A-Za-z0-9_\-]{1,64}$"

FIXTURE_DIR = (
    Path(__file__).parent.parent.parent.parent
    / "src" / "tailor" / "_fixtures" / "redcap_demo"
)


@pytest.fixture
def redcap_child() -> Generator[RedcapFileChild, None, None]:
    """RedcapFileChild backed by the bundled synthetic fixtures."""
    with TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        config_dir = root / "config"
        data_dir = root / "data"
        redcap_dir = root / "redcap_export"
        config_dir.mkdir()
        data_dir.mkdir()
        redcap_dir.mkdir()

        for name in ("records.csv", "project_metadata.csv", "metadata.json"):
            shutil.copy(FIXTURE_DIR / name, redcap_dir / name)

        user_config = {
            "redcap_file": {
                "path": str(redcap_dir),
                "unknown_field_allowlist": ["recruitment_wave", "referral_source"],
            }
        }
        (config_dir / "user_config.json").write_text(
            json.dumps(user_config), encoding="utf-8",
        )

        yield RedcapFileChild(config_dir, data_dir)


VALID_PARAMS = {
    "redcap_list_records": {"limit": 50},
    "redcap_record_detail": {"record_id": "S001"},
    "redcap_summary_report": {"instrument": "phq9"},
    "redcap_cohort_summary": {
        "field": "phq9_score", "group_by": "study_group", "metric": "mean",
    },
    "redcap_records": {"instrument": "phq9"},
    "redcap_raw_records": {"precision": 4},
}


# ═══════════════════════════════════════════════════════════════
# ABC SURFACE
# ═══════════════════════════════════════════════════════════════


class TestToolSurface:
    def test_domain(self, redcap_child: RedcapFileChild):
        assert redcap_child.domain == "redcap_file"

    def test_display_name(self, redcap_child: RedcapFileChild):
        assert isinstance(redcap_child.display_name, str)
        assert redcap_child.display_name.strip()

    def test_six_tools_three_tiers(self, redcap_child: RedcapFileChild):
        defs = redcap_child.tool_definitions
        assert isinstance(defs, list)
        assert len(defs) == 6
        for td in defs:
            assert isinstance(td, ToolDefinition)
            assert td.tier in (1, 2, 3)
        assert {td.tier for td in defs} == {1, 2, 3}

    def test_tier_distribution(self, redcap_child: RedcapFileChild):
        """Four Tier-1, one Tier-2, one Tier-3 per ADR 0037."""
        tier_counts: dict[int, int] = {1: 0, 2: 0, 3: 0}
        for td in redcap_child.tool_definitions:
            tier_counts[td.tier] += 1
        assert tier_counts == {1: 4, 2: 1, 3: 1}

    def test_required_params_present(self, redcap_child: RedcapFileChild):
        defs_by_name = {td.name: td for td in redcap_child.tool_definitions}
        # redcap_record_detail requires record_id
        assert defs_by_name["redcap_record_detail"].params["record_id"]["required"] is True
        # redcap_cohort_summary requires field + group_by
        assert defs_by_name["redcap_cohort_summary"].params["field"]["required"] is True
        assert defs_by_name["redcap_cohort_summary"].params["group_by"]["required"] is True
        # redcap_records requires instrument
        assert defs_by_name["redcap_records"].params["instrument"]["required"] is True

    def test_param_schemas_match_tool_definitions(self, redcap_child: RedcapFileChild):
        def_names = {td.name for td in redcap_child.tool_definitions}
        schema_names = set(redcap_child.param_schemas.keys())
        assert def_names == schema_names

    def test_child_scrubber_id(self, redcap_child: RedcapFileChild):
        """Per ADR 0037: child_scrubber_id returns "redcap_metadata_flags"
        when the scrubber is wired."""
        assert redcap_child.child_scrubber_id == "redcap_metadata_flags"


# ═══════════════════════════════════════════════════════════════
# SUBJECT_ID CONSISTENCY (ADR 0002)
# ═══════════════════════════════════════════════════════════════


class TestSubjectIdConsistency:
    def test_every_tool_declares_subject_id_in_param_schemas(
        self, redcap_child: RedcapFileChild,
    ):
        for tool_name, tool_schema in redcap_child.param_schemas.items():
            assert "subject_id" in tool_schema, (
                f"{tool_name} missing subject_id in param_schemas"
            )
            entry = tool_schema["subject_id"]
            assert isinstance(entry, ValidationSchema)
            assert entry.type is str
            assert entry.required is False
            assert entry.pattern == SUBJECT_ID_PATTERN

    def test_every_tool_declares_subject_id_in_tool_definitions(
        self, redcap_child: RedcapFileChild,
    ):
        for td in redcap_child.tool_definitions:
            assert "subject_id" in td.params
            entry = td.params["subject_id"]
            assert entry["type"] == "string"
            assert entry["required"] is False

    def test_canonical_subject_id_schema_pattern(self):
        assert SUBJECT_ID_SCHEMA.type is str
        assert SUBJECT_ID_SCHEMA.required is False
        assert SUBJECT_ID_SCHEMA.pattern == SUBJECT_ID_PATTERN


# ═══════════════════════════════════════════════════════════════
# ROUTER REGISTRATION
# ═══════════════════════════════════════════════════════════════


class TestRouterRegistration:
    def test_registers_without_error(
        self, redcap_child: RedcapFileChild, tmp_path: Path,
    ):
        router = RouterMCP(name="test", data_dir=tmp_path)
        try:
            router.register_child(redcap_child)
            tool_names = {td.name for td in redcap_child.tool_definitions}
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
        self, redcap_child: RedcapFileChild, tool_name: str,
    ):
        params = VALID_PARAMS[tool_name]
        result = asyncio.run(redcap_child.execute(tool_name, params))
        assert isinstance(result, dict)

    def test_unknown_tool_returns_error_dict(
        self, redcap_child: RedcapFileChild,
    ):
        result = asyncio.run(redcap_child.execute("nonexistent", {}))
        assert "error" in result


# ═══════════════════════════════════════════════════════════════
# COST ESTIMATION
# ═══════════════════════════════════════════════════════════════


class TestEstimateCost:
    @pytest.mark.parametrize("tool_name", list(VALID_PARAMS.keys()))
    def test_returns_cost_estimate(
        self, redcap_child: RedcapFileChild, tool_name: str,
    ):
        ce = asyncio.run(redcap_child.estimate_cost(
            tool_name, VALID_PARAMS[tool_name],
        ))
        assert isinstance(ce, CostEstimate)

    def test_tier3_advertises_cheaper_alternative(
        self, redcap_child: RedcapFileChild,
    ):
        ce = asyncio.run(redcap_child.estimate_cost(
            "redcap_raw_records", {"precision": 6},
        ))
        assert ce.has_cheaper_alternative
        assert ce.alternative_description
        assert ce.alternative_tokens > 0

    def test_tier12_have_zero_cost(self, redcap_child: RedcapFileChild):
        for tool_name in (
            "redcap_list_records",
            "redcap_record_detail",
            "redcap_summary_report",
            "redcap_cohort_summary",
            "redcap_records",
        ):
            ce = asyncio.run(redcap_child.estimate_cost(
                tool_name, VALID_PARAMS[tool_name],
            ))
            assert ce.tokens == 0


# ═══════════════════════════════════════════════════════════════
# HANDLER BEHAVIOUR
# ═══════════════════════════════════════════════════════════════


class TestListRecords:
    def test_returns_sixteen_subjects(self, redcap_child: RedcapFileChild):
        result = asyncio.run(redcap_child.execute("redcap_list_records", {}))
        assert result["total_record_ids"] == 16

    def test_respects_limit(self, redcap_child: RedcapFileChild):
        result = asyncio.run(redcap_child.execute(
            "redcap_list_records", {"limit": 5},
        ))
        assert result["count"] == 5
        assert len(result["records"]) == 5

    def test_includes_event_coverage(self, redcap_child: RedcapFileChild):
        result = asyncio.run(redcap_child.execute(
            "redcap_list_records", {"limit": 50},
        ))
        # S001 has baseline + 3_month + 6_month
        s001 = next(r for r in result["records"] if r["record_id"] == "S001")
        assert set(s001["events"]) >= {"baseline", "3_month", "6_month"}

    def test_no_identifier_fields_in_payload(self, redcap_child: RedcapFileChild):
        result = asyncio.run(redcap_child.execute(
            "redcap_list_records", {"limit": 50},
        ))
        # participant_name and dob must not appear anywhere in the result
        as_json = json.dumps(result)
        assert "participant_name" not in as_json
        assert "Subject 001" not in as_json


class TestRecordDetail:
    def test_returns_known_record(self, redcap_child: RedcapFileChild):
        result = asyncio.run(redcap_child.execute(
            "redcap_record_detail", {"record_id": "S001"},
        ))
        assert "error" not in result
        assert result["record_id"] == "S001"
        assert result["n_events"] >= 3  # baseline, 3_month, 6_month

    def test_unknown_record_returns_error(self, redcap_child: RedcapFileChild):
        result = asyncio.run(redcap_child.execute(
            "redcap_record_detail", {"record_id": "S999"},
        ))
        assert "error" in result

    def test_identifier_fields_scrubbed(self, redcap_child: RedcapFileChild):
        result = asyncio.run(redcap_child.execute(
            "redcap_record_detail", {"record_id": "S001"},
        ))
        # Every event's fields dict must lack participant_name and dob.
        for event in result["events"]:
            assert "participant_name" not in event["fields"]
            assert "dob" not in event["fields"]
        # Identifier-stripped fields are surfaced via legibility.
        assert "participant_name" in result["field_marked_identifier_stripped"]
        assert "dob" in result["field_marked_identifier_stripped"]

    def test_legibility_fields_present(self, redcap_child: RedcapFileChild):
        result = asyncio.run(redcap_child.execute(
            "redcap_record_detail", {"record_id": "S001"},
        ))
        assert "field_marked_identifier_stripped" in result
        assert "field_unknown_default_stripped" in result
        assert "unknown_field_count" in result

    def test_event_filter(self, redcap_child: RedcapFileChild):
        result = asyncio.run(redcap_child.execute(
            "redcap_record_detail",
            {"record_id": "S001", "event": "baseline"},
        ))
        for event in result["events"]:
            assert event["redcap_event_name"] == "baseline"


class TestSummaryReport:
    def test_instrument_filter(self, redcap_child: RedcapFileChild):
        result = asyncio.run(redcap_child.execute(
            "redcap_summary_report", {"instrument": "phq9"},
        ))
        # phq9 questions surface in the field summaries
        assert "phq9_q1" in result["field_summaries"]
        assert result["field_summaries"]["phq9_q1"]["kind"] == "numeric"

    def test_no_instrument_filter_surfaces_all(self, redcap_child: RedcapFileChild):
        result = asyncio.run(redcap_child.execute(
            "redcap_summary_report", {},
        ))
        assert "n_records_scanned" in result
        # study_group is categorical
        if "study_group" in result["field_summaries"]:
            assert result["field_summaries"]["study_group"]["kind"] == "categorical"

    def test_identifier_fields_excluded(self, redcap_child: RedcapFileChild):
        result = asyncio.run(redcap_child.execute(
            "redcap_summary_report", {},
        ))
        assert "participant_name" not in result["field_summaries"]
        assert "dob" not in result["field_summaries"]

    def test_completion_counts(self, redcap_child: RedcapFileChild):
        result = asyncio.run(redcap_child.execute(
            "redcap_summary_report", {},
        ))
        # demographics has 16 completed (one row per subject at baseline)
        assert result["completion_counts"]["demographics"] == 16


class TestCohortSummary:
    def test_groups_by_study_group(self, redcap_child: RedcapFileChild):
        result = asyncio.run(redcap_child.execute(
            "redcap_cohort_summary",
            {"field": "phq9_score", "group_by": "study_group", "metric": "mean"},
        ))
        assert "groups" in result
        # Both intervention and control should appear
        assert set(result["groups"].keys()) >= {"intervention", "control"}

    def test_identifier_group_by_hard_errors(self, redcap_child: RedcapFileChild):
        """ADR 0037's named audit test: grouping by an identifier field
        must hard-error to prevent PHI leakage through group-key
        cardinality."""
        result = asyncio.run(redcap_child.execute(
            "redcap_cohort_summary",
            {"field": "phq9_score", "group_by": "dob"},
        ))
        assert "error" in result
        assert "identifier" in result["error"].lower()
        assert "dob" in result["error"]

    def test_identifier_field_hard_errors(self, redcap_child: RedcapFileChild):
        """Aggregating an identifier-flagged field is also rejected."""
        result = asyncio.run(redcap_child.execute(
            "redcap_cohort_summary",
            {"field": "participant_name", "group_by": "study_group"},
        ))
        assert "error" in result

    def test_fail_closed_unknown_group_by_hard_errors(
        self, redcap_child: RedcapFileChild,
    ):
        """B4 regression guard for the v7.3.0 phi-irb VIOLATION (Lens 1+8):
        cohort guards must use the fail-closed ``is_identifier`` predicate,
        not ``is_known_identifier``. A ``group_by`` pointing at a field
        absent from project_metadata.csv must hard-error (treated as
        identifier per ADR 0037's fail-closed default).
        """
        result = asyncio.run(redcap_child.execute(
            "redcap_cohort_summary",
            {
                "field": "phq9_score",
                "group_by": "synthetic_unknown_field",
            },
        ))
        assert "error" in result
        assert "identifier" in result["error"].lower()
        assert "synthetic_unknown_field" in result["error"]

    def test_fail_closed_unknown_field_hard_errors(
        self, redcap_child: RedcapFileChild,
    ):
        """B4 regression guard, second site: ``field`` pointing at an
        unknown field must hard-error under the same fail-closed default
        (B1 site 2 in src/tailor/children/redcap/child.py)."""
        result = asyncio.run(redcap_child.execute(
            "redcap_cohort_summary",
            {
                "field": "synthetic_unknown_field",
                "group_by": "study_group",
            },
        ))
        assert "error" in result
        assert "identifier" in result["error"].lower()
        assert "synthetic_unknown_field" in result["error"]

    def test_instrument_filter(self, redcap_child: RedcapFileChild):
        result = asyncio.run(redcap_child.execute(
            "redcap_cohort_summary",
            {
                "field": "phq9_score",
                "group_by": "study_group",
                "instrument": "phq9",
            },
        ))
        assert "error" not in result
        assert result["instrument_filter"] == "phq9"

    def test_unknown_field_count_surfaces(self, redcap_child: RedcapFileChild):
        """unknown_field_count is part of every cohort-result envelope."""
        result = asyncio.run(redcap_child.execute(
            "redcap_cohort_summary",
            {"field": "phq9_score", "group_by": "sex"},
        ))
        assert "unknown_field_count" in result
        assert isinstance(result["unknown_field_count"], int)

    def test_sidecar_group_by_works(self, redcap_child: RedcapFileChild):
        """ADR 0015 metadata.json group_by — recruitment_wave is not in
        project_metadata.csv but lives in the sidecar."""
        result = asyncio.run(redcap_child.execute(
            "redcap_cohort_summary",
            {"field": "phq9_score", "group_by": "recruitment_wave"},
        ))
        # Both wave_1 and wave_2 are populated in the fixture
        assert set(result["groups"].keys()) >= {"wave_1", "wave_2"}


class TestRecords:
    def test_returns_phq9_records(self, redcap_child: RedcapFileChild):
        result = asyncio.run(redcap_child.execute(
            "redcap_records", {"instrument": "phq9"},
        ))
        assert result["instrument"] == "phq9"
        assert result["n_records"] > 0

    def test_identifier_fields_scrubbed(self, redcap_child: RedcapFileChild):
        result = asyncio.run(redcap_child.execute(
            "redcap_records", {"instrument": "phq9"},
        ))
        # No record should contain participant_name or dob.
        for record in result["records"]:
            assert "participant_name" not in record
            assert "dob" not in record

    def test_event_filter(self, redcap_child: RedcapFileChild):
        result = asyncio.run(redcap_child.execute(
            "redcap_records",
            {"instrument": "phq9", "event": "baseline"},
        ))
        for record in result["records"]:
            assert record.get("redcap_event_name") == "baseline"


class TestRawRecords:
    def test_returns_all_subjects_all_events(self, redcap_child: RedcapFileChild):
        result = asyncio.run(redcap_child.execute(
            "redcap_raw_records", {"precision": 6},
        ))
        assert result["n_records"] > 16  # one row per subject per event

    def test_identifier_fields_scrubbed(self, redcap_child: RedcapFileChild):
        result = asyncio.run(redcap_child.execute(
            "redcap_raw_records", {"precision": 6},
        ))
        for record in result["records"]:
            assert "participant_name" not in record
            assert "dob" not in record

    def test_precision_reduction_on_numeric(self, redcap_child: RedcapFileChild):
        # Use precision 0 so the rounding effect is visible (any floats
        # in the fixture get floored to integers as floats).
        result = asyncio.run(redcap_child.execute(
            "redcap_raw_records", {"precision": 0},
        ))
        # phq9_score is "0", "1", "2", ... as strings in CSV; once
        # coerced and rounded to 0 places they should still round-trip.
        for record in result["records"]:
            score = record.get("phq9_score")
            if isinstance(score, float):
                assert round(score, 0) == score


# ═══════════════════════════════════════════════════════════════
# ADR 0013 — PURGE_CACHE
# ═══════════════════════════════════════════════════════════════


class TestPurgeCache:
    def test_returns_no_op_with_reason(self, redcap_child: RedcapFileChild):
        result = redcap_child.purge_cache()
        assert result["rows_purged"] == 0
        assert result["tables_touched"] == []
        assert "reason" in result
        assert "no derivative cache" in result["reason"]


# ═══════════════════════════════════════════════════════════════
# VAULTABLE TOOLS — EMPTY UNTIL RENDERER LANDS
# ═══════════════════════════════════════════════════════════════


class TestVaultableTools:
    def test_empty_until_renderer_lands(self, redcap_child: RedcapFileChild):
        assert redcap_child.vaultable_tools == []


# ═══════════════════════════════════════════════════════════════
# DATA_TYPES_FOR_TOOL — NARROWS PER-CALL
# ═══════════════════════════════════════════════════════════════


class TestDataTypesForTool:
    def test_tier2_narrows_to_named_instrument(
        self, redcap_child: RedcapFileChild,
    ):
        out = redcap_child.data_types_for_tool(
            "redcap_records", {"instrument": "phq9"},
        )
        assert out == ["REDCap instrument: phq9"]

    def test_tier3_advertises_full_project(self, redcap_child: RedcapFileChild):
        out = redcap_child.data_types_for_tool("redcap_raw_records", {})
        assert "full project" in out[0].lower()

    def test_tier1_uses_full_data_types(self, redcap_child: RedcapFileChild):
        out = redcap_child.data_types_for_tool("redcap_record_detail", {})
        assert out == redcap_child.consent_info.data_types


# ═══════════════════════════════════════════════════════════════
# CHILD SCRUBBER WIRING
# ═══════════════════════════════════════════════════════════════


class TestChildScrubberWiring:
    def test_scrubber_loaded_from_fixture(self, redcap_child: RedcapFileChild):
        """The fixture's project_metadata.csv flags participant_name
        and dob as identifiers; the scrubber recognises this without
        any further configuration."""
        scrubber = redcap_child._scrubber
        assert isinstance(scrubber, RedcapPHIScrubber)
        assert scrubber.is_known_identifier("participant_name")
        assert scrubber.is_known_identifier("dob")
        assert not scrubber.is_known_identifier("phq9_score")
        assert not scrubber.is_known_identifier("study_group")
