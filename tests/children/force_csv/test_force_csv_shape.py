"""
Shape + behaviour tests for ForceCsvChild — the load-cell force
trace ChildMCP (off-blueprint Senefeld-meeting detour, 2026-05-04).

Mirrors ``tests/children/csv_dir/test_csv_shape.py`` for the parts
that are common (ABC surface, subject_id consistency per ADR 0002,
router registration, execute/estimate_cost shape, file_id traversal
defense). Adds force-domain coverage:

- ``mvc_window_mean`` correctness on the Sánchez-2015 250 ms window.
- ``bland_altman`` correctness on a hand-computed paired sample.
- ``force_label_event`` round-trips through SQLite and surfaces in
  ``force_file_detail``.
- ``purge_cache`` PRESERVES analyst-authored labels per ADR 0013.
- Cohort summary works with a metadata.json sidecar (ADR 0015 shape).
- Compare-trials side-by-sides 2-5 trials with per-file summaries.
- Raw-window time slicing falls back to sample_rate_hz when timestamps
  are absent.
"""

from __future__ import annotations

import asyncio
import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from biosensor_mcp.children.force_csv import ForceCsvChild
from biosensor_mcp.children.force_csv.child import (
    ALL_STREAM_TYPES,
    MAX_WINDOW_SECONDS,
    PROTOCOL_EVENT_TYPES,
)
from biosensor_mcp.framework.interfaces import (
    SUBJECT_ID_SCHEMA,
    CostEstimate,
    ToolDefinition,
    ValidationSchema,
)
from biosensor_mcp.framework.router import RouterMCP

SUBJECT_ID_PATTERN = r"^[A-Za-z0-9_\-]{1,64}$"

# ═══════════════════════════════════════════════════════════════
# FIXTURE BUILDERS
# ═══════════════════════════════════════════════════════════════


def _build_force_csv(
    n_samples: int,
    sample_rate_hz: float,
    peak: float,
    plateau_until_s: float,
    decline_to: float,
) -> str:
    """Build a synthetic isometric force trace.

    Shape: 0-0.2s ramp → plateau at ~peak → linear decline to
    decline_to at end. Reproduces the Wang 2026 / Hunter & Senefeld
    2024 protocol shape sufficient for time-to-50pct-drop and MVC
    window math to mean something.
    """
    rows = ["t_s,force"]
    plateau_end_idx = int(plateau_until_s * sample_rate_hz)
    decline_span = max(1, n_samples - plateau_end_idx)
    for i in range(n_samples):
        t = i / sample_rate_hz
        if i < plateau_end_idx:
            # Ramp first 20 samples then plateau
            if i < 20:
                v = peak * (i / 20)
            else:
                v = peak
        else:
            frac = (i - plateau_end_idx) / decline_span
            v = peak - frac * (peak - decline_to)
        rows.append(f"{t:.3f},{v:.3f}")
    return "\n".join(rows) + "\n"


@pytest.fixture
def force_child() -> ForceCsvChild:
    """ForceCsvChild backed by three synthetic isometric trials.

    50 Hz × 30 seconds = 1500 samples per trial. Each subject's
    trial has the same shape (ramp / plateau / decline) with peaks
    chosen so cohort statistics are non-degenerate.
    """
    with TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        config_dir = root / "config"
        data_dir = root / "data"
        csv_dir = root / "force_files"
        for d in (config_dir, data_dir, csv_dir):
            d.mkdir()

        trials = [
            ("S001_trial.csv", 100.0, 60.0),
            ("S002_trial.csv", 110.0, 65.0),
            ("S003_trial.csv", 95.0, 55.0),
        ]
        for fname, peak, decline_to in trials:
            (csv_dir / fname).write_text(
                _build_force_csv(
                    n_samples=1500,
                    sample_rate_hz=50.0,
                    peak=peak,
                    plateau_until_s=15.0,
                    decline_to=decline_to,
                ),
                encoding="utf-8",
            )

        (csv_dir / "metadata.json").write_text(
            json.dumps({
                "S001_trial.csv": {"sex": "F", "group": "control"},
                "S002_trial.csv": {"sex": "M", "group": "control"},
                "S003_trial.csv": {"sex": "F", "group": "test"},
            }),
            encoding="utf-8",
        )

        user_config = {
            "force_csv": {
                "path": str(csv_dir),
                "timestamp_column": "t_s",
                "sample_rate_hz": 50.0,
                "value_columns": {"force": "force"},
            },
        }
        (config_dir / "user_config.json").write_text(
            json.dumps(user_config), encoding="utf-8",
        )

        child = ForceCsvChild(config_dir, data_dir)
        try:
            yield child
        finally:
            # ForceCsvChild owns a SQLite WAL handle. On Windows the
            # TemporaryDirectory cleanup raises PermissionError unless
            # the handle is released first (see CLAUDE.md § "Implementation
            # notes" — `router.close()` on Windows).
            child.close()


VALID_PARAMS: dict[str, dict] = {
    "force_list_files": {"limit": 10},
    "force_file_detail": {"file_id": "S001_trial.csv"},
    "force_summary": {"file_id": "S001_trial.csv"},
    "force_cohort_summary": {
        "group_field": "sex",
        "value_column": "force",
        "metric": "max",
    },
    "force_compare_trials": {
        "file_ids": ["S001_trial.csv", "S002_trial.csv"],
    },
    "force_device_agreement": {
        "device_a_values": [100.0, 110.0, 95.0, 105.0],
        "device_b_values": [102.0, 108.0, 96.0, 103.0],
        "device_a_label": "HUMAC",
        "device_b_label": "MR-conditional dyno",
        "metric_name": "baseline MVC",
    },
    "force_label_event": {
        "file_id": "S001_trial.csv",
        "t_seconds": 5.0,
        "event_type": "baseline_mvc",
        "label": "Initial peak",
    },
    "force_downsampled": {
        "file_id": "S001_trial.csv",
        "interval": 5,
        "columns": ["force"],
    },
    "force_raw_window": {
        "file_id": "S001_trial.csv",
        "start_seconds": 5.0,
        "end_seconds": 6.0,
        "columns": ["force"],
    },
}


# ═══════════════════════════════════════════════════════════════
# REQUIRED ABSTRACT SURFACE
# ═══════════════════════════════════════════════════════════════


class TestRequiredAbstractSurface:

    def test_domain_is_force_csv(self, force_child: ForceCsvChild):
        assert force_child.domain == "force_csv"

    def test_display_name_is_nonempty(self, force_child: ForceCsvChild):
        assert force_child.display_name.strip()

    def test_tool_definitions_count_is_nine(self, force_child: ForceCsvChild):
        defs = force_child.tool_definitions
        assert len(defs) == 9
        for td in defs:
            assert isinstance(td, ToolDefinition)
            assert td.tier in (1, 2, 3)

    def test_tool_definitions_cover_all_three_tiers(
        self, force_child: ForceCsvChild,
    ):
        tiers = {td.tier for td in force_child.tool_definitions}
        assert tiers == {1, 2, 3}

    def test_param_schemas_match_tool_definitions(
        self, force_child: ForceCsvChild,
    ):
        def_names = {td.name for td in force_child.tool_definitions}
        schema_names = set(force_child.param_schemas.keys())
        assert def_names == schema_names


# ═══════════════════════════════════════════════════════════════
# SUBJECT_ID CONSISTENCY (ADR 0002)
# ═══════════════════════════════════════════════════════════════


class TestSubjectIdConsistency:

    def test_every_tool_declares_subject_id_in_param_schemas(
        self, force_child: ForceCsvChild,
    ):
        for tool_name, tool_schema in force_child.param_schemas.items():
            assert "subject_id" in tool_schema, (
                f"{tool_name} missing subject_id in param_schemas"
            )
            entry = tool_schema["subject_id"]
            assert isinstance(entry, ValidationSchema)
            assert entry.type is str
            assert entry.required is False
            assert entry.pattern == SUBJECT_ID_PATTERN

    def test_every_tool_declares_subject_id_in_tool_definitions(
        self, force_child: ForceCsvChild,
    ):
        for tool_def in force_child.tool_definitions:
            assert "subject_id" in tool_def.params
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

    def test_register_child_succeeds(
        self, tmp_data_dir: Path, force_child: ForceCsvChild,
    ):
        router = RouterMCP(name="test-force", data_dir=tmp_data_dir)
        try:
            router.register_child(force_child)
            assert "force_csv" in router.registered_domains
            for tool_name in (
                "force_list_files",
                "force_file_detail",
                "force_summary",
                "force_cohort_summary",
                "force_compare_trials",
                "force_device_agreement",
                "force_label_event",
                "force_downsampled",
                "force_raw_window",
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
        self, force_child: ForceCsvChild, tool_name: str,
    ):
        result = asyncio.run(
            force_child.execute(tool_name, VALID_PARAMS[tool_name])
        )
        assert isinstance(result, dict)
        assert "error" not in result, (
            f"{tool_name}.execute() unexpectedly errored: "
            f"{result.get('error')}"
        )


class TestEstimateCostShape:

    @pytest.mark.parametrize("tool_name", list(VALID_PARAMS.keys()))
    def test_estimate_cost_returns_cost_estimate(
        self, force_child: ForceCsvChild, tool_name: str,
    ):
        est = asyncio.run(
            force_child.estimate_cost(tool_name, VALID_PARAMS[tool_name])
        )
        assert isinstance(est, CostEstimate)
        assert est.tokens >= 0

    def test_raw_window_has_cheaper_alternative(
        self, force_child: ForceCsvChild,
    ):
        est = asyncio.run(
            force_child.estimate_cost(
                "force_raw_window", VALID_PARAMS["force_raw_window"],
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
        self, force_child: ForceCsvChild,
    ):
        types = force_child.data_types_for_tool("force_summary", {})
        assert types == force_child.consent_info.data_types

    def test_narrows_for_downsampled_with_columns(
        self, force_child: ForceCsvChild,
    ):
        types = force_child.data_types_for_tool(
            "force_downsampled", {"columns": ["force"]},
        )
        assert types == ["isometric force production"]

    def test_falls_back_when_columns_unspecified(
        self, force_child: ForceCsvChild,
    ):
        types = force_child.data_types_for_tool("force_downsampled", {})
        assert types == force_child.consent_info.data_types


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
        self, force_child: ForceCsvChild, malicious_id: str,
    ):
        result = asyncio.run(
            force_child.execute(
                "force_file_detail", {"file_id": malicious_id},
            )
        )
        assert "error" in result


# ═══════════════════════════════════════════════════════════════
# FORCE-DOMAIN BEHAVIOUR (mvc_window_mean, bland_altman)
# ═══════════════════════════════════════════════════════════════


class TestMvcWindowMean:

    def test_returns_mean_over_centered_window(
        self, force_child: ForceCsvChild,
    ):
        # Hand-computed: 7 samples at 100 Hz; window=250ms → 25 samples
        # → entire input. Result = mean of input.
        values = [10.0] * 7
        result = force_child._processing.mvc_window_mean(
            values, sample_rate_hz=100.0,
        )
        assert result == 10.0

    def test_returns_none_on_empty_input(self, force_child: ForceCsvChild):
        assert force_child._processing.mvc_window_mean([], 100.0) is None

    def test_returns_none_on_zero_sample_rate(
        self, force_child: ForceCsvChild,
    ):
        assert force_child._processing.mvc_window_mean(
            [1.0, 2.0], 0.0,
        ) is None

    def test_centers_window_on_peak(self, force_child: ForceCsvChild):
        # Peak at index 3 (value 5.0); 250ms@100Hz=25 samples,
        # half=12 → window covers entire 7-sample input.
        values = [1.0, 2.0, 3.0, 5.0, 4.0, 2.0, 1.0]
        result = force_child._processing.mvc_window_mean(values, 100.0)
        assert result == round(sum(values) / len(values), 3)

    def test_force_summary_returns_mvc_window_mean(
        self, force_child: ForceCsvChild,
    ):
        result = asyncio.run(
            force_child.execute(
                "force_summary", {"file_id": "S001_trial.csv"},
            )
        )
        assert result["mvc_window_mean_250ms"] is not None
        # Synthetic peak is 100; MVC window should be very close
        # because plateau is flat at ~100.
        assert 99.0 <= result["mvc_window_mean_250ms"] <= 101.0


class TestBlandAltman:

    def test_handcomputed_two_pairs(self, force_child: ForceCsvChild):
        # A=[100, 110], B=[102, 108]; diffs=[-2, +2]; bias=0; SD=2.828
        result = force_child._processing.bland_altman([100.0, 110.0], [102.0, 108.0])
        assert result["n_pairs"] == 2
        assert result["mean_difference"] == 0.0
        assert math.isclose(result["sd_difference"], 2.828, abs_tol=0.01)

    def test_returns_error_on_length_mismatch(
        self, force_child: ForceCsvChild,
    ):
        result = force_child._processing.bland_altman([1.0, 2.0], [1.0])
        assert "error" in result

    def test_returns_error_on_single_pair(self, force_child: ForceCsvChild):
        result = force_child._processing.bland_altman([1.0], [2.0])
        assert "error" in result

    def test_handler_wraps_with_labels_and_metric(
        self, force_child: ForceCsvChild,
    ):
        result = asyncio.run(
            force_child.execute(
                "force_device_agreement", VALID_PARAMS["force_device_agreement"],
            )
        )
        assert result["device_a_label"] == "HUMAC"
        assert result["device_b_label"] == "MR-conditional dyno"
        assert result["metric_name"] == "baseline MVC"
        assert result["n_pairs"] == 4
        assert "upper_loa" in result
        assert "lower_loa" in result


# ═══════════════════════════════════════════════════════════════
# LABEL PERSISTENCE + ADR 0013 PRESERVATION
# ═══════════════════════════════════════════════════════════════


class TestLabelPersistenceAndPurge:

    def test_label_persists_and_surfaces_in_file_detail(
        self, force_child: ForceCsvChild,
    ):
        save = asyncio.run(
            force_child.execute(
                "force_label_event",
                {
                    "file_id": "S001_trial.csv",
                    "t_seconds": 12.5,
                    "event_type": "mvc_probe",
                    "label": "First MVC probe",
                    "subject_id": "S001",
                },
            )
        )
        assert save.get("saved") is True

        detail = asyncio.run(
            force_child.execute(
                "force_file_detail", {"file_id": "S001_trial.csv"},
            )
        )
        assert detail["label_count"] >= 1
        labels = detail["event_labels"]
        assert any(
            label["t_seconds"] == 12.5 and label["event_type"] == "mvc_probe"
            for label in labels
        )

    def test_purge_cache_preserves_force_event_labels(
        self, force_child: ForceCsvChild,
    ):
        # Save a label first
        asyncio.run(
            force_child.execute(
                "force_label_event",
                {
                    "file_id": "S002_trial.csv",
                    "t_seconds": 8.0,
                    "event_type": "task_failure",
                    "label": "Volitional failure",
                },
            )
        )
        result = force_child.purge_cache()
        assert result["rows_purged"] == 0
        assert "force_event_labels" in result["preserved"]
        # Confirm label is still there post-purge
        detail = asyncio.run(
            force_child.execute(
                "force_file_detail", {"file_id": "S002_trial.csv"},
            )
        )
        assert any(
            label["event_type"] == "task_failure"
            for label in detail["event_labels"]
        )

    def test_close_releases_storage(self, force_child: ForceCsvChild):
        # Should not raise.
        force_child.close()


# ═══════════════════════════════════════════════════════════════
# COHORT SUMMARY (ADR 0015 sidecar shape)
# ═══════════════════════════════════════════════════════════════


class TestCohortSummary:

    def test_cohort_groups_by_sex(self, force_child: ForceCsvChild):
        result = asyncio.run(
            force_child.execute(
                "force_cohort_summary",
                {
                    "group_field": "sex",
                    "value_column": "force",
                    "metric": "max",
                },
            )
        )
        assert "groups" in result
        # F = S001 + S003 (peaks 100, 95); M = S002 (peak 110)
        assert "F" in result["groups"]
        assert "M" in result["groups"]
        assert result["groups"]["F"]["n"] == 2
        assert result["groups"]["M"]["n"] == 1
        # max metric on F group spans peaks ~100 and ~95
        assert 94.0 <= result["groups"]["F"]["mean"] <= 101.0
        assert 109.0 <= result["groups"]["M"]["mean"] <= 111.0

    def test_cohort_returns_error_when_metadata_missing(
        self, tmp_data_dir: Path,
    ):
        # Build a fixture WITHOUT the sidecar.
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_dir = root / "config"
            csv_dir = root / "force_files"
            for d in (config_dir, csv_dir):
                d.mkdir()
            (csv_dir / "trial.csv").write_text(
                _build_force_csv(100, 50.0, 100.0, 1.0, 50.0),
                encoding="utf-8",
            )
            (config_dir / "user_config.json").write_text(
                json.dumps({"force_csv": {"path": str(csv_dir)}}),
                encoding="utf-8",
            )
            child = ForceCsvChild(config_dir, tmp_data_dir)
            try:
                result = asyncio.run(
                    child.execute(
                        "force_cohort_summary",
                        {
                            "group_field": "sex",
                            "value_column": "force",
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
    """v6.9.2 bug #2 — Excel-touched / PowerShell-redirected CSVs
    carry a leading byte-order mark.  Before v6.9.2 every CSV-open
    used ``encoding='utf-8'`` not ``'utf-8-sig'``, so the first
    column header was silently rendered as ``﻿t_s`` and every
    downstream tool returned ``column not found`` errors.

    Bundled fixtures had no BOM and so the demo worked while real
    recipient data did not.
    """

    def test_csv_with_leading_bom_reads_clean_first_header(
        self, tmp_data_dir: Path,
    ):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_dir = root / "config"
            csv_dir = root / "force_files"
            for d in (config_dir, csv_dir):
                d.mkdir()
            body = _build_force_csv(
                n_samples=200, sample_rate_hz=50.0, peak=100.0,
                plateau_until_s=2.0, decline_to=60.0,
            )
            (csv_dir / "S001_trial.csv").write_bytes(
                b"\xef\xbb\xbf" + body.encode("utf-8"),
            )
            (config_dir / "user_config.json").write_text(
                json.dumps({
                    "force_csv": {
                        "path": str(csv_dir),
                        "sample_rate_hz": 50.0,
                        "value_columns": {"force": "force"},
                    },
                }),
                encoding="utf-8",
            )
            child = ForceCsvChild(config_dir, tmp_data_dir)
            try:
                result = asyncio.run(child.execute(
                    "force_list_files", {"limit": 5},
                ))
                assert "error" not in result
                cols = result["files"][0]["columns"]
                # First header must be clean t_s, not ﻿t_s
                assert cols[0] == "t_s"
                assert "﻿" not in cols[0]
                # And force_summary must succeed because the column
                # name resolves cleanly through to the body parse.
                summary = asyncio.run(child.execute(
                    "force_summary", {"file_id": "S001_trial.csv"},
                ))
                assert "error" not in summary
                assert summary["peak"] is not None
            finally:
                child.close()

    def test_metadata_sidecar_with_leading_bom_loads_cleanly(
        self, tmp_data_dir: Path,
    ):
        """v6.9.2 — JSON sidecar BOM expansion.

        A ``metadata.json`` saved by Excel / PowerShell-default
        carries a UTF-8 BOM. Before v6.9.2, ``_load_metadata_sidecar``
        used ``encoding='utf-8'`` so the BOM became part of the first
        top-level key — silently dropping the first file from the
        cohort lookup. The cohort handler would then surface that
        file in ``missing_metadata`` even though the operator
        believed it was registered.
        """
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_dir = root / "config"
            csv_dir = root / "force_files"
            for d in (config_dir, csv_dir):
                d.mkdir()
            for fname, peak in (
                ("S001_trial.csv", 100.0),
                ("S002_trial.csv", 110.0),
            ):
                (csv_dir / fname).write_text(
                    _build_force_csv(
                        n_samples=200, sample_rate_hz=50.0, peak=peak,
                        plateau_until_s=2.0, decline_to=60.0,
                    ),
                    encoding="utf-8",
                )
            sidecar_body = json.dumps({
                "S001_trial.csv": {"sex": "F"},
                "S002_trial.csv": {"sex": "M"},
            })
            (csv_dir / "metadata.json").write_bytes(
                b"\xef\xbb\xbf" + sidecar_body.encode("utf-8"),
            )
            (config_dir / "user_config.json").write_text(
                json.dumps({
                    "force_csv": {
                        "path": str(csv_dir),
                        "sample_rate_hz": 50.0,
                        "value_columns": {"force": "force"},
                    },
                }),
                encoding="utf-8",
            )
            child = ForceCsvChild(config_dir, tmp_data_dir)
            try:
                result = asyncio.run(child.execute(
                    "force_cohort_summary",
                    {
                        "group_field": "sex",
                        "value_column": "force",
                        "metric": "max",
                    },
                ))
                assert "error" not in result
                # Both files must appear; without the BOM-strip fix,
                # the first file (S001) would land in missing_metadata
                # because the dict key would have a BOM prefix.
                assert result["subject_count"] == 2
                assert "missing_metadata" not in result
                assert "F" in result["groups"]
                assert "M" in result["groups"]
            finally:
                child.close()


# ═══════════════════════════════════════════════════════════════
# COHORT SUMMARY — logical→physical column alias resolution
# (regression for v6.9.0 first-prompt failure)
# ═══════════════════════════════════════════════════════════════


def _build_alias_fixture(
    config_dir: Path, csv_dir: Path, *, header: str, alias_logical: str,
) -> dict:
    """Build a fixture where the CSV physical header differs from the
    logical name in ``user_config.value_columns`` — the exact shape of
    the HIP Lab tour deployment.
    """
    trials = [
        ("S001_trial.csv", "F", 100.0, 60.0),
        ("S002_trial.csv", "M", 110.0, 65.0),
        ("S003_trial.csv", "F", 95.0, 55.0),
    ]
    for fname, _sex, peak, decline_to in trials:
        body = _build_force_csv(
            n_samples=1500, sample_rate_hz=50.0, peak=peak,
            plateau_until_s=15.0, decline_to=decline_to,
        ).replace(",force\n", f",{header}\n", 1)
        (csv_dir / fname).write_text(body, encoding="utf-8")
    (csv_dir / "metadata.json").write_text(
        json.dumps({fname: {"sex": sex} for fname, sex, _, _ in trials}),
        encoding="utf-8",
    )
    user_config = {
        "force_csv": {
            "path": str(csv_dir),
            "timestamp_column": "t_s",
            "sample_rate_hz": 50.0,
            "value_columns": {alias_logical: header},
        },
    }
    (config_dir / "user_config.json").write_text(
        json.dumps(user_config), encoding="utf-8",
    )
    return user_config


class TestCohortSummaryAliasResolution:
    """Regression: cohort handler must honor the logical→physical
    column alias map declared in ``user_config.value_columns`` —
    same contract as ``force_summary`` / ``force_compare_trials``.

    Without this resolver, a recipient running the HIP Lab tour
    cue-card prompt got 16 silent ``column not found`` load_errors
    on every file because Claude inferred the logical name
    ``force`` from the prose while the CSV header was ``force_N``.
    """

    def test_logical_alias_resolves_to_physical_header(self, tmp_data_dir):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_dir = root / "config"
            csv_dir = root / "force_files"
            for d in (config_dir, csv_dir):
                d.mkdir()
            _build_alias_fixture(
                config_dir, csv_dir,
                header="force_N", alias_logical="force",
            )
            child = ForceCsvChild(config_dir, tmp_data_dir)
            try:
                result = asyncio.run(child.execute(
                    "force_cohort_summary",
                    {
                        "group_field": "sex",
                        "value_column": "force",
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
            csv_dir = root / "force_files"
            for d in (config_dir, csv_dir):
                d.mkdir()
            _build_alias_fixture(
                config_dir, csv_dir,
                header="force_N", alias_logical="force",
            )
            child = ForceCsvChild(config_dir, tmp_data_dir)
            try:
                via_logical = asyncio.run(child.execute(
                    "force_cohort_summary",
                    {
                        "group_field": "sex",
                        "value_column": "force",
                        "metric": "max",
                    },
                ))
                via_physical = asyncio.run(child.execute(
                    "force_cohort_summary",
                    {
                        "group_field": "sex",
                        "value_column": "force_N",
                        "metric": "max",
                    },
                ))
                # Both must produce the same group statistics.
                # _meta differs (different called_at, token totals).
                assert via_logical["groups"] == via_physical["groups"]
                assert via_logical["subject_count"] == via_physical[
                    "subject_count"
                ]
            finally:
                child.close()


# ═══════════════════════════════════════════════════════════════
# COMPARE TRIALS (side-by-side)
# ═══════════════════════════════════════════════════════════════


class TestCompareTrials:

    def test_compare_two_trials_returns_per_trial_summary(
        self, force_child: ForceCsvChild,
    ):
        result = asyncio.run(
            force_child.execute(
                "force_compare_trials",
                {"file_ids": ["S001_trial.csv", "S002_trial.csv"]},
            )
        )
        assert result["n_trials"] == 2
        comparisons = result["comparisons"]
        assert len(comparisons) == 2
        for entry in comparisons:
            assert entry["peak"] is not None
            assert entry["mvc_window_mean_250ms"] is not None
            assert entry["sample_rate_hz"] is not None

    def test_compare_three_trials_orders_by_input(
        self, force_child: ForceCsvChild,
    ):
        result = asyncio.run(
            force_child.execute(
                "force_compare_trials",
                {
                    "file_ids": [
                        "S003_trial.csv", "S001_trial.csv", "S002_trial.csv",
                    ],
                },
            )
        )
        comparisons = result["comparisons"]
        assert [c["file_id"] for c in comparisons] == [
            "S003_trial.csv", "S001_trial.csv", "S002_trial.csv",
        ]


# ═══════════════════════════════════════════════════════════════
# RAW WINDOW (time slicing + cap)
# ═══════════════════════════════════════════════════════════════


class TestRawWindow:

    def test_window_within_cap_returns_rows(
        self, force_child: ForceCsvChild,
    ):
        result = asyncio.run(
            force_child.execute(
                "force_raw_window",
                {
                    "file_id": "S001_trial.csv",
                    "start_seconds": 5.0,
                    "end_seconds": 6.0,
                    "columns": ["force"],
                },
            )
        )
        assert result["row_count"] > 0
        # 50 Hz × 1 second ≈ 50 rows
        assert 40 <= result["row_count"] <= 60

    def test_window_exceeding_cap_returns_error(
        self, force_child: ForceCsvChild,
    ):
        result = asyncio.run(
            force_child.execute(
                "force_raw_window",
                {
                    "file_id": "S001_trial.csv",
                    "start_seconds": 0.0,
                    "end_seconds": MAX_WINDOW_SECONDS + 10.0,
                },
            )
        )
        assert "error" in result
        assert "cap" in result["error"].lower()

    def test_inverted_window_returns_error(
        self, force_child: ForceCsvChild,
    ):
        result = asyncio.run(
            force_child.execute(
                "force_raw_window",
                {
                    "file_id": "S001_trial.csv",
                    "start_seconds": 5.0,
                    "end_seconds": 4.0,
                },
            )
        )
        assert "error" in result


# ═══════════════════════════════════════════════════════════════
# COLUMN ALLOWED VALUES
# ═══════════════════════════════════════════════════════════════


class TestColumnAllowedValues:

    @pytest.mark.parametrize(
        "tool_name", ["force_downsampled", "force_raw_window"],
    )
    def test_columns_allowed_values_match_constant(
        self, force_child: ForceCsvChild, tool_name: str,
    ):
        schema = force_child.param_schemas[tool_name]["columns"]
        assert schema.allowed_values == ALL_STREAM_TYPES


# ═══════════════════════════════════════════════════════════════
# PROTOCOL EVENT VOCABULARY
# ═══════════════════════════════════════════════════════════════


class TestProtocolEventVocabulary:

    def test_vocabulary_includes_canonical_lifecycle(self):
        for required in (
            "baseline_mvc", "sustained_start", "mvc_probe",
            "task_failure", "rest_period_start", "other",
        ):
            assert required in PROTOCOL_EVENT_TYPES
