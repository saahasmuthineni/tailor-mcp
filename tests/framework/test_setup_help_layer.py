"""
Tests for the framework-level SetupHelpLayer (v6.10.2).

Covers:
- The trigger-condition predicate ``_demo_blocks_absent``.
- Layer construction and tool surface.
- Dispatch through the router (param validation + execute + audit).
- Conditional registration: layer only constructs when no demo blocks
  in user_config.json (the v6.10.2 cue-card-rehearsal-auditor /
  prose-to-schema-inference safety property).
- Audit-row provenance (domain="setup_help", entity_id=None,
  scrubber_id stamped).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from tailor.framework.router import RouterMCP
from tailor.framework.setup_help import (
    SetupHelpLayer,
    _demo_blocks_absent,
    _redact_home,
)

# ── Trigger predicate ──


def test_demo_blocks_absent_on_empty_config():
    assert _demo_blocks_absent({}) is True


def test_demo_blocks_absent_on_strava_only_config():
    """Strava-only deployments are documented but unpopulated.

    Per CLAUDE.md the running child is a 'worked example' retained for
    teaching value, not the canonical use case. Treating Strava-only
    as 'demo blocks absent' is the v6.10.2 design decision.
    """
    assert _demo_blocks_absent({"max_hr": 195, "resting_hr": 55}) is True


@pytest.mark.parametrize("scaffolded_key", [
    "force_csv", "emg_csv", "csv_dir", "vault_path",
    "matlab_file", "redcap_file",
])
def test_demo_blocks_present_disables_diagnostic(scaffolded_key):
    cfg = {scaffolded_key: "/some/path"}
    assert _demo_blocks_absent(cfg) is False


def test_redcap_file_block_disables_setup_help_diagnostic():
    cfg = {"redcap_file": {"path": "/tmp/redcap"}}
    assert _demo_blocks_absent(cfg) is False


def test_matlab_file_block_disables_setup_help_diagnostic():
    cfg = {"matlab_file": {"path": "/tmp/matlab"}}
    assert _demo_blocks_absent(cfg) is False


def test_demo_blocks_present_when_any_scaffold_block_present():
    cfg = {
        "force_csv": {"path": "/tmp/force"},
        "emg_csv": {"path": "/tmp/emg"},
    }
    assert _demo_blocks_absent(cfg) is False


# ── Layer surface ──


def test_layer_exposes_single_tool(tmp_path):
    layer = SetupHelpLayer(config_dir=tmp_path, data_dir=tmp_path / "data")
    tools = layer.tool_definitions
    assert len(tools) == 1
    assert tools[0].name == "tailor_setup_help"
    assert tools[0].tier == 1
    # The description must name the missing tools by name so Claude's
    # deferred-tool-search routes recipient prompts here when those
    # tools are queried.
    desc = tools[0].description
    assert "force_cohort_summary" in desc
    assert "emg_cohort_summary" in desc
    assert "tailor fitting-room" in desc


def test_layer_param_schema_is_empty(tmp_path):
    layer = SetupHelpLayer(config_dir=tmp_path, data_dir=tmp_path / "data")
    assert layer.param_schemas == {"tailor_setup_help": {}}


# ── Direct execute ──


@pytest.mark.asyncio
async def test_execute_returns_recipient_steps(tmp_path):
    layer = SetupHelpLayer(config_dir=tmp_path, data_dir=tmp_path / "data")
    result = await layer.execute("tailor_setup_help", {})
    assert "diagnosis" in result
    assert "recipient_steps" in result
    assert isinstance(result["recipient_steps"], list)
    # The first command surfaced must be `tailor fitting-room`
    # (renamed from `tailor tour` in v7.1.0 per ADR 0035).
    assert any("tailor fitting-room" in s for s in result["recipient_steps"])
    assert "diagnostics" in result
    # Diagnostic paths are home-redacted (phi-irb Lens 1 closure):
    # tmp_path lives under Path.home() on Windows, so the rendered
    # path either starts with `~` (when redacted) or equals the raw
    # tmp_path string (when tmp_path is outside home, e.g. on Linux
    # CI runners where /tmp is not under home).
    rendered = result["diagnostics"]["config_dir"]
    assert rendered == _redact_home(str(tmp_path))


@pytest.mark.asyncio
async def test_execute_redacts_home_from_diagnostic_paths(tmp_path, monkeypatch):
    """Lens 1 closure regression: no diagnostic field leaks the OS
    username to the LLM payload via Path.home() prefix.

    HIPAA Safe Harbor §164.514(b)(2)(i)(R) treats the OS username as
    a unique identifying characteristic on participant-recipient
    deployments. The redaction collapses Path.home() to '~' across
    every path-shaped diagnostic field.
    """
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))  # Windows
    config_dir = fake_home / ".tailor"
    config_dir.mkdir()
    layer = SetupHelpLayer(
        config_dir=config_dir, data_dir=config_dir / "data",
    )
    result = await layer.execute("tailor_setup_help", {})

    # On platforms where Path.home() resolves via HOME / USERPROFILE,
    # the redaction must apply; otherwise the test exits without a
    # bogus assertion. The pure-function _redact_home test below
    # covers the redaction logic in isolation.
    if str(Path.home()) == str(fake_home):
        diag = result["diagnostics"]
        for key in (
            "config_dir", "user_config_path", "default_scaffold_target",
        ):
            assert str(fake_home) not in diag[key], (
                f"diagnostic field {key} leaked the home path "
                f"{fake_home} into the LLM payload (rendered: "
                f"{diag[key]})"
            )


def test_redact_home_collapses_home_to_tilde(monkeypatch, tmp_path):
    fake_home = tmp_path / "h"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
    assert _redact_home(str(fake_home)) == "~"
    assert _redact_home(str(fake_home / "demos" / "hip-lab")) == (
        "~/demos/hip-lab"
    )
    # Identity on non-home paths.
    assert _redact_home("/usr/local/bin/python") == "/usr/local/bin/python"
    # Identity on non-strings.
    assert _redact_home(None) is None
    assert _redact_home(42) == 42


@pytest.mark.asyncio
async def test_execute_unknown_tool_returns_error(tmp_path):
    layer = SetupHelpLayer(config_dir=tmp_path, data_dir=tmp_path / "data")
    result = await layer.execute("bogus_tool", {})
    assert "error" in result


# ── Router-level dispatch ──


@pytest.fixture
def router_with_setup_help(tmp_path):
    router = RouterMCP(
        name="tailor", data_dir=tmp_path / "data",
    )
    layer = SetupHelpLayer(config_dir=tmp_path, data_dir=tmp_path / "data")
    router.register_setup_help_layer(layer)
    yield router
    router.close()


def test_register_setup_help_layer_adds_tool_to_map(router_with_setup_help):
    router = router_with_setup_help
    assert "tailor_setup_help" in router.registered_tools
    assert (
        router._framework_layer_owner["tailor_setup_help"] == "setup_help"
    )


def test_register_setup_help_layer_twice_is_an_error(tmp_path):
    router = RouterMCP(name="tailor", data_dir=tmp_path / "data")
    try:
        layer = SetupHelpLayer(config_dir=tmp_path, data_dir=tmp_path / "data")
        router.register_setup_help_layer(layer)
        with pytest.raises(ValueError, match="already registered"):
            router.register_setup_help_layer(SetupHelpLayer(
                config_dir=tmp_path, data_dir=tmp_path / "data",
            ))
    finally:
        router.close()


@pytest.mark.asyncio
async def test_dispatch_setup_help_writes_audit_row(router_with_setup_help, tmp_path):
    router = router_with_setup_help
    response = await router._dispatch("tailor_setup_help", {})
    assert len(response) == 1
    payload = json.loads(response[0].text)
    assert "diagnosis" in payload
    assert payload["_meta"]["domain"] == "setup_help"
    assert payload["_meta"]["tier"] == 1
    assert payload["_meta"]["scrubber_id"]
    # v7.3.1: child_scrubber_id must be present-but-None on framework-level
    # layers (parallel to vault + local_llm; no child in scope).  Regression
    # guard for the boss-report-auditor G8 finding — setup_help was the 5th
    # _meta site initially missed when items 1 + 6 of v7.3.1 landed.
    assert "child_scrubber_id" in payload["_meta"], (
        f"setup_help _meta missing child_scrubber_id key. "
        f"v7.3.1 G8 regression — keys present: "
        f"{sorted(payload['_meta'].keys())}"
    )
    assert payload["_meta"]["child_scrubber_id"] is None, (
        f"setup_help is a framework-level layer with no child; "
        f"got {payload['_meta']['child_scrubber_id']!r}"
    )

    # Audit row must record domain="setup_help" with entity_id=None
    # (server-state diagnostic; not per-subject).
    audit_db = tmp_path / "data" / "audit.db"
    with sqlite3.connect(str(audit_db)) as conn:
        rows = conn.execute(
            "SELECT domain, tool_name, outcome, entity_id, scrubber_id "
            "FROM audit_log WHERE tool_name = 'tailor_setup_help'"
        ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "setup_help"
    assert rows[0][1] == "tailor_setup_help"
    assert rows[0][2] == "SUCCESS"
    assert rows[0][3] is None  # entity_id intentionally absent
    assert rows[0][4]  # scrubber_id stamped per ADR 0003
