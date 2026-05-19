"""
LOAD-BEARING safety tests for ADR 0040's bounded-write contract.

Per ADR 0040, ``tailor_setup_write_source_block`` writes ONLY the
source-config keys named in :data:`SETUP_WRITE_KEY_ALLOWLIST`. Any
attempt to write a non-allowlisted key MUST be refused. This file
verifies the refusal path at every layer:

1. ``ParamValidator``'s ``allowed_values`` gate on ``source_type``
   (the v7.6.0 D1 closure) rejects unknown source-type tokens before
   they reach the layer at all.
2. :func:`build_source_block` raises :class:`UnknownSourceType` on
   any token outside :data:`SOURCE_TYPE_ALLOWLIST`.
3. The dispatch site's defense-in-depth check in
   :meth:`SetupLayer._tool_write_source_block` refuses any
   source_key not in :data:`SETUP_WRITE_KEY_ALLOWLIST`, even if
   :func:`build_source_block` were buggy.

If any of these tests fail, the bounded-write contract is broken and
the regression is a CRITICAL ADR-0040 violation.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from tailor.framework.setup import (
    SETUP_WRITE_KEY_ALLOWLIST,
    SOURCE_TYPE_ALLOWLIST,
    SetupLayer,
    UnknownSourceKey,
    UnknownSourceType,
    build_source_block,
    source_key_for_type,
)

# ──────────────────────────────────────────────────────────────────────
# Constants — the load-bearing values ADR 0040 codifies
# ──────────────────────────────────────────────────────────────────────


def test_source_type_allowlist_is_csv_matlab_redcap():
    """ADR 0040 § Decision names exactly three source types."""
    assert set(SOURCE_TYPE_ALLOWLIST) == {"csv", "matlab", "redcap"}


def test_write_key_allowlist_is_three_canonical_keys():
    """ADR 0040 § Decision names exactly three source-config keys."""
    assert set(SETUP_WRITE_KEY_ALLOWLIST) == {
        "csv_dir", "matlab_file", "redcap_file",
    }


def test_source_type_to_key_only_maps_to_allowlisted_keys():
    """Every source_type token maps to a key in the write allowlist.

    A regression that adds a token to :data:`SOURCE_TYPE_ALLOWLIST`
    without extending :data:`SETUP_WRITE_KEY_ALLOWLIST` would let
    callers smuggle a new write target through.
    """
    for source_type in SOURCE_TYPE_ALLOWLIST:
        key = source_key_for_type(source_type)
        assert key in SETUP_WRITE_KEY_ALLOWLIST


# ──────────────────────────────────────────────────────────────────────
# build_source_block refusal — UnknownSourceType for any unknown token
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("bad_source_type", [
    "edf", "fhir", "vendor", "running", "vault", "local_llm",
    "csv_dir", "matlab_file", "redcap_file",   # source_KEY confusion
    "", "CSV", "Csv", "  csv  ",
    "../csv",
])
def test_build_source_block_refuses_unknown_source_type(bad_source_type):
    with pytest.raises(UnknownSourceType):
        build_source_block(bad_source_type, "/tmp/x", None)


def test_source_key_for_type_refuses_unknown():
    with pytest.raises(UnknownSourceType):
        source_key_for_type("not_a_source")


# ──────────────────────────────────────────────────────────────────────
# Dispatch-level refusal — the defense-in-depth check
# ──────────────────────────────────────────────────────────────────────


def _run(coro):
    return asyncio.run(coro)


def test_write_source_block_refuses_unknown_source_type(tmp_path):
    """SetupLayer.execute path refuses pre-validator-bypass too.

    In normal operation ParamValidator's allowed_values gate fires
    first. But a future refactor that drops the validator (or a test
    harness that bypasses it) must still hit the refusal. Verify by
    calling SetupLayer.execute directly with a bad source_type.
    """
    layer = SetupLayer(config_dir=tmp_path)
    result = _run(layer.execute(
        "tailor_setup_write_source_block",
        {
            "source_type": "edf",  # not in the allowlist
            "path": str(tmp_path),
            "validated_schema": {},
        },
    ))
    assert result["ok"] is False
    assert result["error_class"] == "UnknownSourceType"


@pytest.mark.parametrize("source_type", ["csv", "matlab", "redcap"])
def test_write_source_block_only_writes_allowlisted_keys(
    source_type, tmp_path, monkeypatch,
):
    """Verify the WRITTEN key is one of the three allowlisted ones."""
    # Patch pilot._write_user_config to capture what gets written
    # without actually mutating the operator's ~/.tailor/.
    captured: dict = {}

    def fake_write(source_key, source_block, *, force=False):
        captured["source_key"] = source_key
        captured["source_block"] = source_block
        return tmp_path / "user_config.json"

    monkeypatch.setattr(
        "tailor.pilot._write_user_config", fake_write,
    )

    layer = SetupLayer(config_dir=tmp_path)
    result = _run(layer.execute(
        "tailor_setup_write_source_block",
        {
            "source_type": source_type,
            "path": str(tmp_path / source_type),
            "validated_schema": {},
        },
    ))

    assert result["ok"] is True, f"Write failed: {result}"
    assert captured["source_key"] in SETUP_WRITE_KEY_ALLOWLIST, (
        f"Wrote non-allowlisted key: {captured['source_key']!r}"
    )


def test_write_source_block_block_payload_only_carries_recognized_keys(
    tmp_path, monkeypatch,
):
    """A malformed validated_schema with arbitrary keys is dropped.

    build_source_block whitelists known per-source schema keys. An
    LLM hallucinating a ``local_llm`` field inside ``validated_schema``
    must not see that field flow into the written source_block.
    """
    captured: dict = {}

    def fake_write(source_key, source_block, *, force=False):
        captured["source_key"] = source_key
        captured["source_block"] = source_block
        return tmp_path / "user_config.json"

    monkeypatch.setattr(
        "tailor.pilot._write_user_config", fake_write,
    )

    layer = SetupLayer(config_dir=tmp_path)
    _run(layer.execute(
        "tailor_setup_write_source_block",
        {
            "source_type": "csv",
            "path": str(tmp_path / "csv"),
            "validated_schema": {
                "timestamp_column": "ts",
                "timestamp_format": "%Y-%m-%dT%H:%M:%S",
                "value_columns": {"hr": "heart_rate"},
                # Hallucinated keys — must NOT appear in source_block:
                "local_llm": {"backend": "ollama"},
                "vault_path": "/etc/passwd",
                "cost_threshold": 999999,
                "max_hr": 195,
                "arbitrary_attacker_key": "drop_table_users",
            },
        },
    ))

    block = captured["source_block"]
    assert "local_llm" not in block
    assert "vault_path" not in block
    assert "cost_threshold" not in block
    assert "max_hr" not in block
    assert "arbitrary_attacker_key" not in block
    # Verify the recognized keys ARE preserved.
    assert block["timestamp_column"] == "ts"
    assert "value_columns" in block


# ──────────────────────────────────────────────────────────────────────
# Param-validator gate — verify allowed_values fires (D1 closure)
# ──────────────────────────────────────────────────────────────────────


def test_param_validator_rejects_unknown_source_type():
    """ADR 0040 relies on the v7.6.0 D1 closure in ParamValidator.

    If this test fails, the D1 closure has regressed and unknown
    source_type tokens slip past the validator into the layer's
    execute path — silently widening the surface.
    """
    from tailor.framework.security import ParamValidator

    layer = SetupLayer(config_dir=Path("/tmp"))
    schemas = layer.param_schemas["tailor_setup_write_source_block"]
    validator = ParamValidator()
    ok, err, cleaned = validator.validate(
        schemas,
        {
            "source_type": "edf",
            "path": "/tmp/x",
            "validated_schema": {},
        },
    )
    assert ok is False, "ParamValidator failed to reject unknown source_type"
    assert "source_type" in err
    assert any(token in err for token in ("csv", "matlab", "redcap"))


# ──────────────────────────────────────────────────────────────────────
# Allowlist invariants — code-as-contract
# ──────────────────────────────────────────────────────────────────────


def test_unknown_source_key_is_a_value_error_subclass():
    """The error class is a ValueError subclass so generic ``except
    ValueError`` paths catch it; specific test setups can use the
    narrower class.
    """
    assert issubclass(UnknownSourceType, ValueError)
    assert issubclass(UnknownSourceKey, ValueError)
