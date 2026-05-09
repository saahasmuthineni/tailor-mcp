"""
Shape + behaviour tests for EmgCsvChild — surface-EMG envelope
ChildMCP (off-blueprint Senefeld-meeting detour Phase 2, 2026-05-04).

Mirrors ``tests/children/force_csv/test_force_csv_shape.py`` for
the parts that are common (ABC surface, subject_id consistency
per ADR 0002, router registration, execute/estimate_cost shape,
file_id traversal defense, ADR 0013 label preservation, ADR 0015
cohort sidecar). Adds EMG-domain coverage:

- ``rms`` / ``mean_activation`` / ``integrated_emg`` correctness
  on hand-computed inputs.
- ``envelope_summary`` returns the documented shape with a
  meaningful fatigue_index_pct on a synthetic decline trace.
- Bland-Altman is intentionally absent from the surface.
"""

from __future__ import annotations

import asyncio
import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from tailor.children.emg_csv import EmgCsvChild
from tailor.children.emg_csv.child import (
    ALL_STREAM_TYPES,
    MAX_WINDOW_SECONDS,
    PROTOCOL_EVENT_TYPES,
)
from tailor.framework.interfaces import (
    SUBJECT_ID_SCHEMA,
    CostEstimate,
    ToolDefinition,
    ValidationSchema,
)
from tailor.framework.router import RouterMCP

SUBJECT_ID_PATTERN = r"^[A-Za-z0-9_\-]{1,64}$"


# ═══════════════════════════════════════════════════════════════
# FIXTURE BUILDERS
# ═══════════════════════════════════════════════════════════════


def _build_emg_envelope_csv(
    n_samples: int,
    sample_rate_hz: float,
    peak: float,
    plateau_until_s: float,
    decline_to: float,
) -> str:
    """Build a synthetic EMG envelope trace.

    Shape: ramp 0→peak in 0.5s, plateau at peak, then linear decline
    to decline_to. Approximates the amplitude decline observed in
    sustained-isometric EMG fatigue protocols.
    """
    rows = ["t_s,envelope"]
    plateau_end_idx = int(plateau_until_s * sample_rate_hz)
    decline_span = max(1, n_samples - plateau_end_idx)
    ramp_samples = max(1, int(0.5 * sample_rate_hz))
    for i in range(n_samples):
        t = i / sample_rate_hz
        if i < ramp_samples:
            v = peak * (i / ramp_samples)
        elif i < plateau_end_idx:
            v = peak
        else:
            frac = (i - plateau_end_idx) / decline_span
            v = peak - frac * (peak - decline_to)
        rows.append(f"{t:.3f},{v:.4f}")
    return "\n".join(rows) + "\n"


@pytest.fixture
def emg_child() -> EmgCsvChild:
    """EmgCsvChild backed by three synthetic envelope trials.

    100 Hz × 30 seconds = 3000 samples per trial. Each trial has
    a ramp / plateau / decline shape with peaks chosen so cohort
    statistics are non-degenerate.
    """
    with TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        config_dir = root / "config"
        data_dir = root / "data"
        csv_dir = root / "emg_files"
        for d in (config_dir, data_dir, csv_dir):
            d.mkdir()

        trials = [
            ("S001_emg.csv", 0.50, 0.30),
            ("S002_emg.csv", 0.55, 0.32),
            ("S003_emg.csv", 0.45, 0.28),
        ]
        for fname, peak, decline_to in trials:
            (csv_dir / fname).write_text(
                _build_emg_envelope_csv(
                    n_samples=3000,
                    sample_rate_hz=100.0,
                    peak=peak,
                    plateau_until_s=10.0,
                    decline_to=decline_to,
                ),
                encoding="utf-8",
            )

        (csv_dir / "metadata.json").write_text(
            json.dumps({
                "S001_emg.csv": {"sex": "F", "group": "control"},
                "S002_emg.csv": {"sex": "M", "group": "control"},
                "S003_emg.csv": {"sex": "F", "group": "test"},
            }),
            encoding="utf-8",
        )

        user_config = {
            "emg_csv": {
                "path": str(csv_dir),
                "timestamp_column": "t_s",
                "sample_rate_hz": 100.0,
                "value_columns": {"envelope": "envelope"},
            },
        }
        (config_dir / "user_config.json").write_text(
            json.dumps(user_config), encoding="utf-8",
        )

        child = EmgCsvChild(config_dir, data_dir)
        try:
            yield child
        finally:
            child.close()


VALID_PARAMS: dict[str, dict] = {
    "emg_list_files": {"limit": 10},
    "emg_file_detail": {"file_id": "S001_emg.csv"},
    "emg_envelope_summary": {"file_id": "S001_emg.csv"},
    "emg_cohort_summary": {
        "group_field": "sex",
        "value_column": "envelope",
        "metric": "max",
    },
    "emg_compare_trials": {
        "file_ids": ["S001_emg.csv", "S002_emg.csv"],
    },
    "emg_label_event": {
        "file_id": "S001_emg.csv",
        "t_seconds": 5.0,
        "event_type": "burst_onset",
        "label": "First burst",
    },
    "emg_downsampled": {
        "file_id": "S001_emg.csv",
        "interval": 5,
        "columns": ["envelope"],
    },
    "emg_raw_window": {
        "file_id": "S001_emg.csv",
        "start_seconds": 5.0,
        "end_seconds": 6.0,
        "columns": ["envelope"],
    },
}


# ═══════════════════════════════════════════════════════════════
# REQUIRED ABSTRACT SURFACE
# ═══════════════════════════════════════════════════════════════


class TestRequiredAbstractSurface:

    def test_domain_is_emg_csv(self, emg_child: EmgCsvChild):
        assert emg_child.domain == "emg_csv"

    def test_display_name_is_nonempty(self, emg_child: EmgCsvChild):
        assert emg_child.display_name.strip()

    def test_tool_definitions_count_is_eight(self, emg_child: EmgCsvChild):
        defs = emg_child.tool_definitions
        assert len(defs) == 8
        for td in defs:
            assert isinstance(td, ToolDefinition)
            assert td.tier in (1, 2, 3)

    def test_tool_definitions_cover_all_three_tiers(
        self, emg_child: EmgCsvChild,
    ):
        tiers = {td.tier for td in emg_child.tool_definitions}
        assert tiers == {1, 2, 3}

    def test_param_schemas_match_tool_definitions(
        self, emg_child: EmgCsvChild,
    ):
        def_names = {td.name for td in emg_child.tool_definitions}
        schema_names = set(emg_child.param_schemas.keys())
        assert def_names == schema_names

    def test_bland_altman_is_intentionally_absent(
        self, emg_child: EmgCsvChild,
    ):
        # Sibling force_csv has device_agreement; emg_csv does NOT.
        # See emg_csv/__init__.py for rationale.
        names = {td.name for td in emg_child.tool_definitions}
        assert not any("device_agreement" in n for n in names)
        assert not any("bland_altman" in n for n in names)


# ═══════════════════════════════════════════════════════════════
# SUBJECT_ID CONSISTENCY (ADR 0002)
# ═══════════════════════════════════════════════════════════════


class TestSubjectIdConsistency:

    def test_every_tool_declares_subject_id_in_param_schemas(
        self, emg_child: EmgCsvChild,
    ):
        for tool_name, tool_schema in emg_child.param_schemas.items():
            assert "subject_id" in tool_schema, (
                f"{tool_name} missing subject_id in param_schemas"
            )
            entry = tool_schema["subject_id"]
            assert isinstance(entry, ValidationSchema)
            assert entry.type is str
            assert entry.required is False
            assert entry.pattern == SUBJECT_ID_PATTERN

    def test_every_tool_declares_subject_id_in_tool_definitions(
        self, emg_child: EmgCsvChild,
    ):
        for tool_def in emg_child.tool_definitions:
            assert "subject_id" in tool_def.params
            entry = tool_def.params["subject_id"]
            assert entry["type"] == "string"
            assert entry["required"] is False
            assert isinstance(entry["description"], str)

    def test_exported_subject_id_schema_matches_canonical_pattern(self):
        assert SUBJECT_ID_SCHEMA.type is str
        assert SUBJECT_ID_SCHEMA.required is False
        assert SUBJECT_ID_SCHEMA.pattern == SUBJECT_ID_PATTERN


# ═══════════════════════════════════════════════════════════════
# ROUTER REGISTRATION
# ═══════════════════════════════════════════════════════════════


class TestRouterCanRegister:

    def test_register_child_succeeds(
        self, tmp_data_dir: Path, emg_child: EmgCsvChild,
    ):
        router = RouterMCP(name="test-emg", data_dir=tmp_data_dir)
        try:
            router.register_child(emg_child)
            assert "emg_csv" in router.registered_domains
            for tool_name in (
                "emg_list_files",
                "emg_file_detail",
                "emg_envelope_summary",
                "emg_cohort_summary",
                "emg_compare_trials",
                "emg_label_event",
                "emg_downsampled",
                "emg_raw_window",
            ):
                assert tool_name in router.registered_tools
        finally:
            if hasattr(router, "close"):
                router.close()


# ═══════════════════════════════════════════════════════════════
# EXECUTE & ESTIMATE_COST SHAPE
# ═══════════════════════════════════════════════════════════════


class TestExecuteReturnsDicts:

    @pytest.mark.parametrize("tool_name", list(VALID_PARAMS.keys()))
    def test_execute_returns_dict_no_error(
        self, emg_child: EmgCsvChild, tool_name: str,
    ):
        result = asyncio.run(
            emg_child.execute(tool_name, VALID_PARAMS[tool_name])
        )
        assert isinstance(result, dict)
        assert "error" not in result, (
            f"{tool_name}.execute() unexpectedly errored: "
            f"{result.get('error')}"
        )


class TestEstimateCostShape:

    @pytest.mark.parametrize("tool_name", list(VALID_PARAMS.keys()))
    def test_estimate_cost_returns_cost_estimate(
        self, emg_child: EmgCsvChild, tool_name: str,
    ):
        est = asyncio.run(
            emg_child.estimate_cost(tool_name, VALID_PARAMS[tool_name])
        )
        assert isinstance(est, CostEstimate)
        assert est.tokens >= 0

    def test_raw_window_has_cheaper_alternative(
        self, emg_child: EmgCsvChild,
    ):
        est = asyncio.run(
            emg_child.estimate_cost(
                "emg_raw_window", VALID_PARAMS["emg_raw_window"],
            )
        )
        assert est.has_cheaper_alternative is True
        assert est.alternative_tokens > 0
        assert est.alternative_tokens < est.tokens
        assert est.alternative_description.strip()


# ═══════════════════════════════════════════════════════════════
# CONSENT NARROWING (data_types_for_tool)
# ═══════════════════════════════════════════════════════════════


class TestDataTypesForTool:

    def test_default_scope_for_non_stream_tool(
        self, emg_child: EmgCsvChild,
    ):
        types = emg_child.data_types_for_tool("emg_envelope_summary", {})
        assert types == emg_child.consent_info.data_types

    def test_narrows_for_downsampled_with_columns(
        self, emg_child: EmgCsvChild,
    ):
        types = emg_child.data_types_for_tool(
            "emg_downsampled", {"columns": ["envelope"]},
        )
        assert types == ["surface electromyography envelope"]

    def test_falls_back_when_columns_unspecified(
        self, emg_child: EmgCsvChild,
    ):
        types = emg_child.data_types_for_tool("emg_downsampled", {})
        assert types == emg_child.consent_info.data_types


# ═══════════════════════════════════════════════════════════════
# FILE_ID SECURITY (path traversal)
# ═══════════════════════════════════════════════════════════════


class TestFileIdSecurity:

    @pytest.mark.parametrize("malicious_id", [
        "../etc/passwd",
        "../../secrets.csv",
        "/etc/passwd",
    ])
    def test_traversal_returns_error(
        self, emg_child: EmgCsvChild, malicious_id: str,
    ):
        result = asyncio.run(
            emg_child.execute(
                "emg_file_detail", {"file_id": malicious_id},
            )
        )
        assert "error" in result


# ═══════════════════════════════════════════════════════════════
# EMG-DOMAIN BEHAVIOUR (rms, mean_activation, integrated_emg)
# ═══════════════════════════════════════════════════════════════


class TestRms:

    def test_rms_of_zeros_is_zero(self, emg_child: EmgCsvChild):
        assert emg_child._processing.rms([0.0, 0.0, 0.0]) == 0.0

    def test_rms_of_unit_vector(self, emg_child: EmgCsvChild):
        # rms([1, 1, 1, 1]) = sqrt(4/4) = 1
        assert emg_child._processing.rms([1.0, 1.0, 1.0, 1.0]) == 1.0

    def test_rms_handcomputed(self, emg_child: EmgCsvChild):
        # rms([1, 2, 3]) = sqrt((1+4+9)/3) = sqrt(14/3) ≈ 2.16025
        result = emg_child._processing.rms([1.0, 2.0, 3.0])
        assert math.isclose(result, 2.1602, abs_tol=0.001)

    def test_rms_returns_none_on_empty(self, emg_child: EmgCsvChild):
        assert emg_child._processing.rms([]) is None


class TestMeanActivation:

    def test_mean_activation_handcomputed(self, emg_child: EmgCsvChild):
        assert emg_child._processing.mean_activation(
            [1.0, 2.0, 3.0, 4.0],
        ) == 2.5

    def test_returns_none_on_empty(self, emg_child: EmgCsvChild):
        assert emg_child._processing.mean_activation([]) is None


class TestIntegratedEmg:

    def test_constant_envelope(self, emg_child: EmgCsvChild):
        # 4 samples at 100 Hz, all = 1.0; trapezoidal integral
        # = 3 segments × (1+1)/2 × 0.01 = 0.03
        result = emg_child._processing.integrated_emg(
            [1.0, 1.0, 1.0, 1.0], sample_rate_hz=100.0,
        )
        assert math.isclose(result, 0.03, abs_tol=0.001)

    def test_returns_none_on_empty(self, emg_child: EmgCsvChild):
        assert emg_child._processing.integrated_emg([], 100.0) is None

    def test_returns_none_on_zero_rate(self, emg_child: EmgCsvChild):
        assert emg_child._processing.integrated_emg([1.0, 2.0], 0.0) is None

    def test_single_sample_returns_zero(self, emg_child: EmgCsvChild):
        assert emg_child._processing.integrated_emg([5.0], 100.0) == 0.0


class TestEnvelopeSummary:

    def test_returns_documented_shape(self, emg_child: EmgCsvChild):
        result = asyncio.run(
            emg_child.execute(
                "emg_envelope_summary", {"file_id": "S001_emg.csv"},
            )
        )
        for key in (
            "filename", "envelope_column", "sample_rate_hz",
            "n_samples", "duration_s",
            "peak_envelope_window_mean", "end_window_mean",
            "fatigue_index_pct",
            "mean_activation", "rms", "integrated_emg",
            "note",
        ):
            assert key in result, f"missing key: {key}"

    def test_fatigue_index_positive_on_decline_trace(
        self, emg_child: EmgCsvChild,
    ):
        # Synthetic trace: peaks 0.50, declines to 0.30. Fatigue
        # index should be positive (peak window > end window).
        result = asyncio.run(
            emg_child.execute(
                "emg_envelope_summary", {"file_id": "S001_emg.csv"},
            )
        )
        assert result["fatigue_index_pct"] is not None
        assert result["fatigue_index_pct"] > 0

    def test_peak_window_close_to_synthetic_peak(
        self, emg_child: EmgCsvChild,
    ):
        result = asyncio.run(
            emg_child.execute(
                "emg_envelope_summary", {"file_id": "S001_emg.csv"},
            )
        )
        # Synthetic peak is 0.50; plateau is flat so window mean
        # should be very close.
        assert 0.48 <= result["peak_envelope_window_mean"] <= 0.51

    def test_envelope_summary_errors_on_missing_sample_rate(
        self, tmp_data_dir: Path,
    ):
        # Build a fixture with NO sample rate and NO timestamp column.
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_dir = root / "config"
            csv_dir = root / "emg_files"
            for d in (config_dir, csv_dir):
                d.mkdir()
            (csv_dir / "trial.csv").write_text(
                "envelope\n0.1\n0.2\n0.3\n0.2\n0.1\n",
                encoding="utf-8",
            )
            (config_dir / "user_config.json").write_text(
                json.dumps({"emg_csv": {"path": str(csv_dir)}}),
                encoding="utf-8",
            )
            child = EmgCsvChild(config_dir, tmp_data_dir)
            try:
                result = asyncio.run(
                    child.execute(
                        "emg_envelope_summary", {"file_id": "trial.csv"},
                    )
                )
                assert "error" in result
                assert "sample rate" in result["error"].lower()
            finally:
                child.close()


# ═══════════════════════════════════════════════════════════════
# LABEL PERSISTENCE + ADR 0013 PRESERVATION
# ═══════════════════════════════════════════════════════════════


class TestLabelPersistenceAndPurge:

    def test_label_persists_and_surfaces_in_file_detail(
        self, emg_child: EmgCsvChild,
    ):
        save = asyncio.run(
            emg_child.execute(
                "emg_label_event",
                {
                    "file_id": "S001_emg.csv",
                    "t_seconds": 12.5,
                    "event_type": "mvc_probe",
                    "label": "EMG burst at probe",
                    "subject_id": "S001",
                },
            )
        )
        assert save.get("saved") is True

        detail = asyncio.run(
            emg_child.execute(
                "emg_file_detail", {"file_id": "S001_emg.csv"},
            )
        )
        assert detail["label_count"] >= 1
        assert any(
            label["t_seconds"] == 12.5 and label["event_type"] == "mvc_probe"
            for label in detail["event_labels"]
        )

    def test_purge_cache_preserves_emg_event_labels(
        self, emg_child: EmgCsvChild,
    ):
        asyncio.run(
            emg_child.execute(
                "emg_label_event",
                {
                    "file_id": "S002_emg.csv",
                    "t_seconds": 8.0,
                    "event_type": "task_failure",
                    "label": "Volitional failure",
                },
            )
        )
        result = emg_child.purge_cache()
        assert result["rows_purged"] == 0
        assert "emg_event_labels" in result["preserved"]
        detail = asyncio.run(
            emg_child.execute(
                "emg_file_detail", {"file_id": "S002_emg.csv"},
            )
        )
        assert any(
            label["event_type"] == "task_failure"
            for label in detail["event_labels"]
        )

    def test_close_releases_storage(self, emg_child: EmgCsvChild):
        emg_child.close()


# ═══════════════════════════════════════════════════════════════
# COHORT SUMMARY (ADR 0015 sidecar shape)
# ═══════════════════════════════════════════════════════════════


class TestCohortSummary:

    def test_cohort_groups_by_sex(self, emg_child: EmgCsvChild):
        result = asyncio.run(
            emg_child.execute(
                "emg_cohort_summary",
                {
                    "group_field": "sex",
                    "value_column": "envelope",
                    "metric": "max",
                },
            )
        )
        assert "groups" in result
        assert "F" in result["groups"]
        assert "M" in result["groups"]
        assert result["groups"]["F"]["n"] == 2
        assert result["groups"]["M"]["n"] == 1

    def test_cohort_returns_error_when_metadata_missing(
        self, tmp_data_dir: Path,
    ):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_dir = root / "config"
            csv_dir = root / "emg_files"
            for d in (config_dir, csv_dir):
                d.mkdir()
            (csv_dir / "trial.csv").write_text(
                _build_emg_envelope_csv(100, 100.0, 0.5, 0.5, 0.3),
                encoding="utf-8",
            )
            (config_dir / "user_config.json").write_text(
                json.dumps({
                    "emg_csv": {
                        "path": str(csv_dir),
                        "sample_rate_hz": 100.0,
                    },
                }),
                encoding="utf-8",
            )
            child = EmgCsvChild(config_dir, tmp_data_dir)
            try:
                result = asyncio.run(
                    child.execute(
                        "emg_cohort_summary",
                        {
                            "group_field": "sex",
                            "value_column": "envelope",
                            "metric": "max",
                        },
                    )
                )
                assert "error" in result
                assert "metadata.json" in result["error"]
            finally:
                child.close()


# ═══════════════════════════════════════════════════════════════
# UTF-8 BOM transparency (regression for v6.9.2 bug #2)
# ═══════════════════════════════════════════════════════════════


class TestBomTransparency:
    """Sibling regression to ForceCsv's TestBomTransparency — covers
    the same v6.9.2 fix on EmgCsvChild's CSV-open paths.
    """

    def test_csv_with_leading_bom_reads_clean_first_header(
        self, tmp_data_dir: Path,
    ):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_dir = root / "config"
            csv_dir = root / "emg_files"
            for d in (config_dir, csv_dir):
                d.mkdir()
            body = _build_emg_envelope_csv(
                n_samples=300, sample_rate_hz=100.0, peak=0.5,
                plateau_until_s=2.0, decline_to=0.3,
            )
            (csv_dir / "S001_emg.csv").write_bytes(
                b"\xef\xbb\xbf" + body.encode("utf-8"),
            )
            (config_dir / "user_config.json").write_text(
                json.dumps({
                    "emg_csv": {
                        "path": str(csv_dir),
                        "sample_rate_hz": 100.0,
                        "value_columns": {"envelope": "envelope"},
                    },
                }),
                encoding="utf-8",
            )
            child = EmgCsvChild(config_dir, tmp_data_dir)
            try:
                result = asyncio.run(child.execute(
                    "emg_list_files", {"limit": 5},
                ))
                assert "error" not in result
                cols = result["files"][0]["columns"]
                assert cols[0] == "t_s"
                assert "﻿" not in cols[0]
                summary = asyncio.run(child.execute(
                    "emg_envelope_summary", {"file_id": "S001_emg.csv"},
                ))
                assert "error" not in summary
            finally:
                child.close()


# ═══════════════════════════════════════════════════════════════
# COHORT SUMMARY — logical→physical column alias resolution
# (regression for v6.9.0 first-prompt failure)
# ═══════════════════════════════════════════════════════════════


def _build_emg_alias_fixture(
    config_dir: Path, csv_dir: Path, *, header: str, alias_logical: str,
) -> None:
    trials = [
        ("S001_emg.csv", "F", 0.50, 0.30),
        ("S002_emg.csv", "M", 0.55, 0.32),
        ("S003_emg.csv", "F", 0.45, 0.28),
    ]
    for fname, _sex, peak, decline_to in trials:
        body = _build_emg_envelope_csv(
            n_samples=3000, sample_rate_hz=100.0, peak=peak,
            plateau_until_s=10.0, decline_to=decline_to,
        ).replace(",envelope\n", f",{header}\n", 1)
        (csv_dir / fname).write_text(body, encoding="utf-8")
    (csv_dir / "metadata.json").write_text(
        json.dumps({fname: {"sex": sex} for fname, sex, _, _ in trials}),
        encoding="utf-8",
    )
    user_config = {
        "emg_csv": {
            "path": str(csv_dir),
            "timestamp_column": "t_s",
            "sample_rate_hz": 100.0,
            "value_columns": {alias_logical: header},
        },
    }
    (config_dir / "user_config.json").write_text(
        json.dumps(user_config), encoding="utf-8",
    )


class TestCohortSummaryAliasResolution:
    """Sibling regression to ForceCsv's TestCohortSummaryAliasResolution.

    Closes the same defect on EmgCsvChild — the cohort handler must
    honor ``user_config.emg_csv.value_columns`` so a caller passing
    the logical name ``envelope`` against a CSV with header
    ``envelope_uV`` does not get 16 silent ``column not found``
    load_errors and an empty cohort.
    """

    def test_logical_alias_resolves_to_physical_header(self, tmp_data_dir):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_dir = root / "config"
            csv_dir = root / "emg_files"
            for d in (config_dir, csv_dir):
                d.mkdir()
            _build_emg_alias_fixture(
                config_dir, csv_dir,
                header="envelope_uV", alias_logical="envelope",
            )
            child = EmgCsvChild(config_dir, tmp_data_dir)
            try:
                result = asyncio.run(child.execute(
                    "emg_cohort_summary",
                    {
                        "group_field": "sex",
                        "value_column": "envelope",
                        "metric": "max",
                    },
                ))
                assert "error" not in result
                assert result["subject_count"] == 3
                assert "F" in result["groups"]
                assert "M" in result["groups"]
                assert "load_errors" not in result
            finally:
                child.close()

    def test_physical_header_and_logical_alias_produce_same_groups(
        self, tmp_data_dir,
    ):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_dir = root / "config"
            csv_dir = root / "emg_files"
            for d in (config_dir, csv_dir):
                d.mkdir()
            _build_emg_alias_fixture(
                config_dir, csv_dir,
                header="envelope_uV", alias_logical="envelope",
            )
            child = EmgCsvChild(config_dir, tmp_data_dir)
            try:
                via_logical = asyncio.run(child.execute(
                    "emg_cohort_summary",
                    {
                        "group_field": "sex",
                        "value_column": "envelope",
                        "metric": "max",
                    },
                ))
                via_physical = asyncio.run(child.execute(
                    "emg_cohort_summary",
                    {
                        "group_field": "sex",
                        "value_column": "envelope_uV",
                        "metric": "max",
                    },
                ))
                assert via_logical["groups"] == via_physical["groups"]
                assert via_logical["subject_count"] == via_physical[
                    "subject_count"
                ]
            finally:
                child.close()


# ═══════════════════════════════════════════════════════════════
# COMPARE TRIALS
# ═══════════════════════════════════════════════════════════════


class TestCompareTrials:

    def test_compare_two_trials_returns_per_trial_summary(
        self, emg_child: EmgCsvChild,
    ):
        result = asyncio.run(
            emg_child.execute(
                "emg_compare_trials",
                {"file_ids": ["S001_emg.csv", "S002_emg.csv"]},
            )
        )
        assert result["n_trials"] == 2
        for entry in result["comparisons"]:
            assert entry["peak_envelope_window_mean"] is not None
            assert entry["fatigue_index_pct"] is not None
            assert entry["rms"] is not None
            assert entry["integrated_emg"] is not None


# ═══════════════════════════════════════════════════════════════
# RAW WINDOW (time slicing + cap)
# ═══════════════════════════════════════════════════════════════


class TestRawWindow:

    def test_window_within_cap_returns_rows(
        self, emg_child: EmgCsvChild,
    ):
        result = asyncio.run(
            emg_child.execute(
                "emg_raw_window",
                {
                    "file_id": "S001_emg.csv",
                    "start_seconds": 5.0,
                    "end_seconds": 6.0,
                    "columns": ["envelope"],
                },
            )
        )
        assert result["row_count"] > 0
        # 100 Hz × 1 second ≈ 100 rows
        assert 90 <= result["row_count"] <= 110

    def test_window_exceeding_cap_returns_error(
        self, emg_child: EmgCsvChild,
    ):
        result = asyncio.run(
            emg_child.execute(
                "emg_raw_window",
                {
                    "file_id": "S001_emg.csv",
                    "start_seconds": 0.0,
                    "end_seconds": MAX_WINDOW_SECONDS + 5.0,
                },
            )
        )
        assert "error" in result
        assert "cap" in result["error"].lower()

    def test_inverted_window_returns_error(
        self, emg_child: EmgCsvChild,
    ):
        result = asyncio.run(
            emg_child.execute(
                "emg_raw_window",
                {
                    "file_id": "S001_emg.csv",
                    "start_seconds": 5.0,
                    "end_seconds": 4.0,
                },
            )
        )
        assert "error" in result


# ═══════════════════════════════════════════════════════════════
# COLUMN ALLOWED VALUES + PROTOCOL VOCABULARY
# ═══════════════════════════════════════════════════════════════


class TestColumnAllowedValues:

    @pytest.mark.parametrize(
        "tool_name", ["emg_downsampled", "emg_raw_window"],
    )
    def test_columns_allowed_values_match_constant(
        self, emg_child: EmgCsvChild, tool_name: str,
    ):
        schema = emg_child.param_schemas[tool_name]["columns"]
        assert schema.allowed_values == ALL_STREAM_TYPES


class TestProtocolEventVocabulary:

    def test_vocabulary_includes_canonical_lifecycle(self):
        for required in (
            "baseline_mvc", "sustained_start", "mvc_probe",
            "task_failure", "rest_period_start", "burst_onset", "other",
        ):
            assert required in PROTOCOL_EVENT_TYPES

    def test_emg_vocabulary_extends_force_vocabulary(self):
        # The shared lifecycle terms must be present so paired
        # EMG + force trials share event_type strings.
        from tailor.children.force_csv.child import (
            PROTOCOL_EVENT_TYPES as FORCE_VOCAB,
        )
        for term in FORCE_VOCAB:
            assert term in PROTOCOL_EVENT_TYPES, (
                f"force_csv vocabulary term {term!r} missing from emg_csv"
            )
