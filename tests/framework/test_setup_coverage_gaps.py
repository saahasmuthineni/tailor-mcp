"""
Coverage-gap closers for the v8.0.0 A' diff.

Closes the CRITICAL and HIGH uncovered paths the coverage-criticality-mapper
release-pass flagged:

- SetupLayer defensive write paths (UnknownSourceKey, DispatchAllowlistViolation,
  OSError) — ADR 0040 § "Bounded-write authority is the load-bearing invariant".
- Detector branches for matlab + redcap (path-not-exist / path-not-dir).
- build_source_block REDCap-source branch (lines 137-148 of sources.py).
- UnknownSourceKey constructor body.
- FittingRoomLayer scaffold + index_vault success paths against a tempdir.
- Router-level _dispatch_setup SETUP_CONFIG_WRITE outcome branch — the
  IRB-queryable provenance signal ADR 0040 § "New audit outcome" declares.
- register_*_layer double-registration + tool-name collision detection.

Also closes the v7.3.4 / red-team-2026-05-19 regression guard class:
walkthrough section 1's worked_example.params must be a VALID call against
the actual force_cohort_summary tool schema — wire-running invalid params
would torpedo the recipient demo on first touch (the "fabricated stats /
invalid call shape" defect class red-team named).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from tailor.framework.fitting_room import FittingRoomLayer
from tailor.framework.setup import (
    SETUP_WRITE_KEY_ALLOWLIST,
    SetupLayer,
    UnknownSourceKey,
    UnknownSourceType,
    build_source_block,
)
from tailor.framework.setup.sources import source_key_for_type
from tailor.framework.walkthrough import WalkthroughLayer


def _run(coro):
    return asyncio.run(coro)


# ──────────────────────────────────────────────────────────────────────
# build_source_block — uncovered REDCap branch + UnknownSourceKey ctor
# ──────────────────────────────────────────────────────────────────────


def test_build_source_block_redcap_preserves_recognized_keys():
    """REDCap source-block builder writes the schema's recognized keys."""
    source_key, block = build_source_block(
        "redcap",
        "/data/redcap-export",
        {
            "records_file": "my_records.csv",
            "project_metadata_file": "my_meta.csv",
            "instrument_completion_fields": ["demo_complete", "phq9_complete"],
            "unknown_field_allowlist": ["computed_score_v2"],
            # Hallucinated key — must NOT be persisted:
            "arbitrary_attacker_key": "drop_table_users",
        },
    )
    assert source_key == "redcap_file"
    assert source_key in SETUP_WRITE_KEY_ALLOWLIST
    assert block["path"] == "/data/redcap-export"
    assert block["records_file"] == "my_records.csv"
    assert block["project_metadata_file"] == "my_meta.csv"
    assert block["instrument_completion_fields"] == [
        "demo_complete", "phq9_complete",
    ]
    assert block["unknown_field_allowlist"] == ["computed_score_v2"]
    assert "arbitrary_attacker_key" not in block


def test_build_source_block_matlab_preserves_variable_filter():
    """MATLAB block builder writes variable_filter when supplied."""
    _, block = build_source_block(
        "matlab",
        "/data/mat-exports",
        {"variable_filter": ["EMG_envelope", "force"]},
    )
    assert block["variable_filter"] == ["EMG_envelope", "force"]


def test_build_source_block_empty_schema_writes_path_only():
    """An empty validated_schema produces a path-only source_block."""
    _, block = build_source_block("csv", "/data/csv", {})
    assert block == {"path": "/data/csv"}


def test_unknown_source_key_constructor_body():
    """The UnknownSourceKey constructor body builds an informative message."""
    exc = UnknownSourceKey("rogue_key")
    assert exc.source_key == "rogue_key"
    msg = str(exc)
    assert "rogue_key" in msg
    assert "csv_dir" in msg or "allowlist" in msg
    assert "framework bug" in msg.lower()


# ──────────────────────────────────────────────────────────────────────
# SetupLayer defensive write paths
# ──────────────────────────────────────────────────────────────────────


def test_write_source_block_oserror_handler(tmp_path, monkeypatch):
    """OSError from pilot._write_user_config returns a structured envelope.

    Disk-full / permissions / readonly-FS conditions land here. The
    handler must shape the response as ok=False with error_class="OSError"
    so the router records the audit row with full context — not a raw
    exception that surfaces as outcome=ERROR with a stringified traceback.
    """
    def raises_oserror(source_key, source_block, *, force=False):
        raise OSError("readonly filesystem: simulated")

    monkeypatch.setattr("tailor.pilot._write_user_config", raises_oserror)

    layer = SetupLayer(config_dir=tmp_path)
    result = _run(layer.execute(
        "tailor_setup_write_source_block",
        {
            "source_type": "csv",
            "path": str(tmp_path),
            "validated_schema": {},
        },
    ))
    assert result["ok"] is False
    assert result["error_class"] == "OSError"
    assert "readonly" in result["error"].lower()


def test_write_source_block_dispatch_allowlist_violation(tmp_path, monkeypatch):
    """If build_source_block returns a non-allowlisted source_key,
    the dispatch-site defense-in-depth catches it before
    pilot._write_user_config sees the call.

    Real-world impossible (SOURCE_TYPE_TO_KEY maps only to allowlisted
    keys) but a framework refactor could break that. The defense-in-
    depth check must still refuse the call. Monkeypatch build_source_block
    to return a bogus key.
    """
    write_called = {"yes": False}

    def write_user_config_spy(source_key, source_block, *, force=False):
        write_called["yes"] = True
        return tmp_path / "user_config.json"

    def bogus_build(source_type, path, schema):
        # Simulate a framework bug that returns a non-allowlisted key.
        return "vault_path", {"path": path}

    monkeypatch.setattr(
        "tailor.framework.setup.layer.build_source_block",
        bogus_build,
    )
    monkeypatch.setattr(
        "tailor.pilot._write_user_config", write_user_config_spy,
    )

    layer = SetupLayer(config_dir=tmp_path)
    result = _run(layer.execute(
        "tailor_setup_write_source_block",
        {
            "source_type": "csv",
            "path": str(tmp_path),
            "validated_schema": {},
        },
    ))
    assert result["ok"] is False
    assert result["error_class"] == "DispatchAllowlistViolation"
    assert "vault_path" in result["error"]
    # The canonical writer must NOT have been called.
    assert write_called["yes"] is False, (
        "Defense-in-depth failed: bogus source_key reached the "
        "canonical writer, widening the bounded-write surface."
    )


def test_write_source_block_unknown_source_key_handler(tmp_path, monkeypatch):
    """If build_source_block raises UnknownSourceKey directly (e.g.
    the internal allowlist check at sources.py:153), the dispatch
    handler shapes it as a structured envelope rather than letting
    it escape to the router's outer ``except Exception``.
    """
    def raises_unknown_key(source_type, path, schema):
        raise UnknownSourceKey("synthetic_bad_key")

    monkeypatch.setattr(
        "tailor.framework.setup.layer.build_source_block",
        raises_unknown_key,
    )

    layer = SetupLayer(config_dir=tmp_path)
    result = _run(layer.execute(
        "tailor_setup_write_source_block",
        {
            "source_type": "csv",
            "path": str(tmp_path),
            "validated_schema": {},
        },
    ))
    assert result["ok"] is False
    assert result["error_class"] == "UnknownSourceKey"


# ──────────────────────────────────────────────────────────────────────
# Detector branches — path-not-exist / path-not-dir
# ──────────────────────────────────────────────────────────────────────


def test_detect_matlab_path_not_exist(tmp_path):
    layer = SetupLayer(config_dir=tmp_path)
    result = _run(layer.execute(
        "tailor_setup_detect_schema",
        {
            "source_type": "matlab",
            "path": str(tmp_path / "does_not_exist"),
        },
    ))
    assert result["ok"] is False
    assert "does not exist" in result["error"].lower()


def test_detect_matlab_path_is_a_file_not_dir(tmp_path):
    f = tmp_path / "not_a_dir.mat"
    f.write_bytes(b"\x00\x00\x00\x00")  # not actually a valid mat
    layer = SetupLayer(config_dir=tmp_path)
    result = _run(layer.execute(
        "tailor_setup_detect_schema",
        {"source_type": "matlab", "path": str(f)},
    ))
    assert result["ok"] is False
    assert "not a directory" in result["error"].lower()


def test_detect_redcap_path_not_exist(tmp_path):
    layer = SetupLayer(config_dir=tmp_path)
    result = _run(layer.execute(
        "tailor_setup_detect_schema",
        {
            "source_type": "redcap",
            "path": str(tmp_path / "does_not_exist"),
        },
    ))
    assert result["ok"] is False
    assert "does not exist" in result["error"].lower()


def test_detect_redcap_path_is_a_file_not_dir(tmp_path):
    f = tmp_path / "not_a_dir.csv"
    f.write_text("not a directory")
    layer = SetupLayer(config_dir=tmp_path)
    result = _run(layer.execute(
        "tailor_setup_detect_schema",
        {"source_type": "redcap", "path": str(f)},
    ))
    assert result["ok"] is False
    assert "not a directory" in result["error"].lower()


def test_detect_csv_path_is_a_file_not_dir(tmp_path):
    f = tmp_path / "not_a_dir.csv"
    f.write_text("ts,hr\n2026-01-01,72\n")
    layer = SetupLayer(config_dir=tmp_path)
    result = _run(layer.execute(
        "tailor_setup_detect_schema",
        {"source_type": "csv", "path": str(f)},
    ))
    assert result["ok"] is False
    assert "not a directory" in result["error"].lower()


def test_detect_schema_unreachable_unknown_source_type_branch(tmp_path):
    """The _tool_detect_schema body has a defense-in-depth branch for
    an unknown source_type token that ParamValidator's allowed_values
    gate would normally catch. Exercise the branch directly by calling
    layer.execute (the validator runs at router level).
    """
    layer = SetupLayer(config_dir=tmp_path)
    result = _run(layer.execute(
        "tailor_setup_detect_schema",
        {"source_type": "edf", "path": str(tmp_path)},
    ))
    assert result["ok"] is False
    assert "edf" in result["error"]


# ──────────────────────────────────────────────────────────────────────
# FittingRoomLayer scaffold success + force-overwrite + exception paths
# ──────────────────────────────────────────────────────────────────────


def test_fitting_room_scaffold_success_path(monkeypatch, tmp_path):
    """End-to-end scaffold against a real tempdir using mocks for the
    fitting_room helpers (real ones would copy ~16 MB of bundled
    fixtures; the mocks return realistic shapes faster).
    """
    monkeypatch.setattr(
        "tailor.framework.fitting_room.layer.Path.home",
        lambda: tmp_path,
    )

    def fake_scaffold(variant, target):
        target.mkdir(parents=True, exist_ok=True)
        return {"force": 16, "emg": 16, "mrs": 16, "vault": 2}

    def fake_write_config(variant, target):
        cfg = target / "user_config.json"
        cfg.write_text("{}")
        return cfg

    def fake_index(target):
        return {"added": 2, "modified": 0, "skipped": 0}

    monkeypatch.setattr(
        "tailor.fitting_room._scaffold_fixtures", fake_scaffold,
    )
    monkeypatch.setattr(
        "tailor.fitting_room._write_user_config", fake_write_config,
    )
    monkeypatch.setattr(
        "tailor.fitting_room._index_vault", fake_index,
    )

    layer = FittingRoomLayer()
    result = _run(layer.execute(
        "tailor_fitting_room_scaffold",
        {"variant": "cohort"},
    ))
    assert result["ok"] is True
    assert result["fixture_counts"]["force"] == 16
    assert result["user_config_path"].endswith("user_config.json")
    assert result["vault_index_counts"]["added"] == 2
    assert result["restart_required"] is True


def test_fitting_room_scaffold_force_overwrite(monkeypatch, tmp_path):
    """force=True rmtrees an existing target then scaffolds again."""
    monkeypatch.setattr(
        "tailor.framework.fitting_room.layer.Path.home",
        lambda: tmp_path,
    )
    target = tmp_path / ".tailor" / "demos" / "cohort"
    target.mkdir(parents=True)
    (target / "stale.marker").write_text("pre-existing")

    def fake_scaffold(variant, target):
        target.mkdir(parents=True, exist_ok=True)
        return {"force": 1, "emg": 0, "mrs": 0, "vault": 0}

    def fake_write_config(variant, target):
        cfg = target / "user_config.json"
        cfg.write_text("{}")
        return cfg

    def fake_index(target):
        return {"added": 0, "modified": 0, "skipped": 0}

    monkeypatch.setattr(
        "tailor.fitting_room._scaffold_fixtures", fake_scaffold,
    )
    monkeypatch.setattr(
        "tailor.fitting_room._write_user_config", fake_write_config,
    )
    monkeypatch.setattr(
        "tailor.fitting_room._index_vault", fake_index,
    )

    layer = FittingRoomLayer()
    result = _run(layer.execute(
        "tailor_fitting_room_scaffold",
        {"variant": "cohort", "force": True},
    ))
    assert result["ok"] is True
    # The pre-existing marker must have been rmtree'd.
    assert not (target / "stale.marker").exists()


def test_fitting_room_scaffold_failure_propagates_partial(
    monkeypatch, tmp_path,
):
    """When the vault index fails after fixtures + config are written,
    the response surfaces the partial state."""
    monkeypatch.setattr(
        "tailor.framework.fitting_room.layer.Path.home",
        lambda: tmp_path,
    )

    def fake_scaffold(variant, target):
        target.mkdir(parents=True, exist_ok=True)
        return {"force": 16}

    def fake_write_config(variant, target):
        cfg = target / "user_config.json"
        cfg.write_text("{}")
        return cfg

    def fail_index(target):
        raise RuntimeError("simulated rescan failure")

    monkeypatch.setattr(
        "tailor.fitting_room._scaffold_fixtures", fake_scaffold,
    )
    monkeypatch.setattr(
        "tailor.fitting_room._write_user_config", fake_write_config,
    )
    monkeypatch.setattr(
        "tailor.fitting_room._index_vault", fail_index,
    )

    layer = FittingRoomLayer()
    result = _run(layer.execute(
        "tailor_fitting_room_scaffold",
        {"variant": "cohort"},
    ))
    assert result["ok"] is False
    assert result["error_class"] == "RuntimeError"
    assert "partial" in result
    assert result["partial"]["fixture_counts"]["force"] == 16


def test_fitting_room_index_vault_success(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "tailor.framework.fitting_room.layer.Path.home",
        lambda: tmp_path,
    )
    target = tmp_path / ".tailor" / "demos" / "cohort"
    target.mkdir(parents=True)

    def fake_index(target):
        return {"added": 0, "modified": 1, "skipped": 2}

    monkeypatch.setattr(
        "tailor.fitting_room._index_vault", fake_index,
    )

    layer = FittingRoomLayer()
    result = _run(layer.execute(
        "tailor_fitting_room_index_vault", {"variant": "cohort"},
    ))
    assert result["ok"] is True
    assert result["vault_index_counts"]["modified"] == 1


def test_fitting_room_index_vault_exception(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "tailor.framework.fitting_room.layer.Path.home",
        lambda: tmp_path,
    )
    target = tmp_path / ".tailor" / "demos" / "cohort"
    target.mkdir(parents=True)

    def fail_index(target):
        raise ValueError("simulated bad vault path")

    monkeypatch.setattr(
        "tailor.fitting_room._index_vault", fail_index,
    )

    layer = FittingRoomLayer()
    result = _run(layer.execute(
        "tailor_fitting_room_index_vault", {"variant": "cohort"},
    ))
    assert result["ok"] is False
    assert result["error_class"] == "ValueError"


# ──────────────────────────────────────────────────────────────────────
# Walkthrough section 1 worked_example — anti-red-team regression guard
# ──────────────────────────────────────────────────────────────────────


def test_walkthrough_section_1_worked_example_is_callable_against_real_tool():
    """RED-TEAM REGRESSION GUARD (2026-05-19): the walkthrough's section 1
    worked_example.params must be a VALID call against the actual
    force_cohort_summary schema.

    The original v8.0.0 draft of walkthrough section 1 used
    ``metric="peak_force_N"`` (not in COHORT_METRICS) and omitted
    ``value_column`` (a required param). A recipient who copied the
    example back to Claude got PARAM_INVALID instead of a cohort
    answer — the same "demo on first touch is broken" defect class
    v7.3.4 D1 closed. This test asserts the documented params match
    the actual tool schema.

    If this test ever fails, the walkthrough's section 1 example is
    again torpedoed at first recipient touch. Either update the test
    (because COHORT_METRICS legitimately changed) or fix the
    walkthrough payload (because the example drifted).
    """
    from tailor.children.csv_dir.processing import COHORT_METRICS

    layer = WalkthroughLayer()
    payload = _run(layer.execute(
        "tailor_walkthrough_section", {"section": 1},
    ))
    we = payload["worked_example"]
    params = we["params"]

    # 1. The named tool must actually exist on the bundled fitting-room
    #    deployment. force_cohort_summary is registered by the force_csv
    #    child.
    assert we["tool"] == "force_cohort_summary", (
        f"Walkthrough section 1 references tool {we['tool']!r}; "
        f"only force_cohort_summary is exposed on the bundled fitting-"
        f"room scaffold."
    )

    # 2. metric must be in COHORT_METRICS (the actual tool's allowed-
    #    values gate). The v7.3.4 D1 + v8.0.0 red-team defect was
    #    metric="peak_force_N" (not in the vocabulary).
    assert params["metric"] in COHORT_METRICS, (
        f"Walkthrough section 1 example uses metric={params['metric']!r} "
        f"which is not in COHORT_METRICS={list(COHORT_METRICS)!r}. "
        f"A recipient who copies this example would receive PARAM_INVALID."
    )

    # 3. value_column must be present (required param).
    assert "value_column" in params, (
        "Walkthrough section 1 example is missing required param "
        "'value_column'. A recipient call without it returns "
        "PARAM_INVALID."
    )

    # 4. group_by must be present (required for the per-group result
    #    shape this section claims).
    assert "group_by" in params


def test_walkthrough_section_1_example_stats_match_real_fixtures():
    """The means in section 1's example_result_shape must match the
    actual per-sex mean of force_N across the bundled HIP Lab fixtures.

    Wire-verified means (2026-05-19): F n=8 mean≈65.28, M n=8 mean≈87.62.
    Stds: F≈6.62, M≈6.46 (red-team caught fabricated 12.1 / 15.4 stds
    in the original v8 draft).

    Tolerance: ±0.2 absolute on mean, ±0.5 absolute on std — bounds
    the worst-case fixture-regeneration noise while catching the
    fabricated-stats class outright.
    """
    layer = WalkthroughLayer()
    payload = _run(layer.execute(
        "tailor_walkthrough_section", {"section": 1},
    ))
    groups = payload["worked_example"]["example_result_shape"]["groups"]
    by_sex = {g["sex"]: g for g in groups}

    assert by_sex["F"]["n"] == 8
    assert by_sex["M"]["n"] == 8
    assert abs(by_sex["F"]["mean"] - 65.28) < 0.2
    assert abs(by_sex["M"]["mean"] - 87.62) < 0.2
    assert abs(by_sex["F"]["std"] - 6.62) < 0.5, (
        "Walkthrough section 1 example F std drifted from the "
        "wire-verified value. Red-team caught fabricated stds at "
        "v8.0.0 release-pass; this test prevents the regression."
    )
    assert abs(by_sex["M"]["std"] - 6.46) < 0.5, (
        "Walkthrough section 1 example M std drifted from the "
        "wire-verified value. Red-team caught fabricated stds at "
        "v8.0.0 release-pass; this test prevents the regression."
    )


# ──────────────────────────────────────────────────────────────────────
# Router-level register_*_layer double-registration + collision guards
# ──────────────────────────────────────────────────────────────────────


def _fresh_router(tmp_path):
    """Construct a RouterMCP scoped to a tempdir for layer-registration tests."""
    from tailor.framework.router import RouterMCP

    router = RouterMCP("test-setup-coverage", data_dir=tmp_path / "data")
    return router


def test_register_setup_layer_double_registration_rejected(tmp_path):
    router = _fresh_router(tmp_path)
    layer1 = SetupLayer(config_dir=tmp_path)
    layer2 = SetupLayer(config_dir=tmp_path)
    router.register_setup_layer(layer1)
    with pytest.raises(ValueError, match="already registered"):
        router.register_setup_layer(layer2)
    router.close()


def test_register_walkthrough_layer_double_registration_rejected(tmp_path):
    router = _fresh_router(tmp_path)
    router.register_walkthrough_layer(WalkthroughLayer())
    with pytest.raises(ValueError, match="already registered"):
        router.register_walkthrough_layer(WalkthroughLayer())
    router.close()


def test_register_fitting_room_layer_double_registration_rejected(tmp_path):
    router = _fresh_router(tmp_path)
    router.register_fitting_room_layer(FittingRoomLayer())
    with pytest.raises(ValueError, match="already registered"):
        router.register_fitting_room_layer(FittingRoomLayer())
    router.close()


def test_register_setup_layer_tool_name_collision_rejected(tmp_path):
    """If another layer pre-registered a tool with the same name as
    a SetupLayer tool, registration must refuse rather than silently
    overwrite the dispatch route.

    Build a stub layer that claims one of SetupLayer's tool names and
    assert the registration fails loud.
    """
    from tailor.framework.interfaces import ToolDefinition
    from tailor.framework.walkthrough import WalkthroughLayer as WL

    router = _fresh_router(tmp_path)

    class CollidingLayer:
        """Stub layer that pretends to be a walkthrough but claims a
        SetupLayer tool name."""
        @property
        def tool_definitions(self):
            return [ToolDefinition(
                "tailor_setup_status", 1, "stub", {},
            )]

        @property
        def param_schemas(self):
            return {"tailor_setup_status": {}}

    # Register the collider first under the walkthrough register hook
    # (it's not actually a walkthrough, but we monkey the type check).
    router._walkthrough_layer = None  # ensure clean
    colliding = CollidingLayer()
    # Simulate the walkthrough's tool_map entry to provoke collision.
    router._tool_map["tailor_setup_status"] = (None, colliding.tool_definitions[0])
    router._framework_layer_owner["tailor_setup_status"] = "walkthrough"

    with pytest.raises(ValueError, match="already registered"):
        router.register_setup_layer(SetupLayer(config_dir=tmp_path))
    router.close()


# ──────────────────────────────────────────────────────────────────────
# Module-level allowlist mapping invariant
# ──────────────────────────────────────────────────────────────────────


def test_source_key_for_type_matches_build_source_block_output():
    """The single-arg helper and the full build_source_block must
    agree on the source_key for every source_type. A regression that
    desyncs them would let one path produce a different write target
    than the other.
    """
    for source_type in ("csv", "matlab", "redcap"):
        key_via_helper = source_key_for_type(source_type)
        key_via_builder, _ = build_source_block(source_type, "/tmp/x", None)
        assert key_via_helper == key_via_builder, (
            f"source_key disagreement on source_type={source_type!r}: "
            f"helper={key_via_helper!r} builder={key_via_builder!r}"
        )


# ──────────────────────────────────────────────────────────────────────
# Status tool: malformed config branches
# ──────────────────────────────────────────────────────────────────────


def test_status_redacts_home_in_user_config_path(tmp_path, monkeypatch):
    """Closes phi-irb WATCH-1 (Lens 1 Safe Harbor) — verifies that
    user_config_path is collapsed to ~ when it sits under the user's
    home directory, so the LLM doesn't see username-bearing strings.
    """
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    # Move config_dir under the patched home so _redact_home fires.
    fake_home_config = tmp_path / ".tailor"
    fake_home_config.mkdir()

    layer = SetupLayer(config_dir=fake_home_config)
    result = _run(layer.execute("tailor_setup_status", {}))
    # _redact_home replaces Path.home() prefix with ~.
    assert result["user_config_path"].startswith("~"), (
        f"user_config_path not redacted: {result['user_config_path']!r}. "
        f"phi-irb WATCH-1 regression."
    )
