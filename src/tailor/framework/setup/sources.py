"""
Source-key allowlist + per-source source_block builders.

This module is the load-bearing safety boundary for SetupLayer's write
authority. Per ADR 0040, ``tailor_setup_write_source_block`` writes
ONLY the keys named in :data:`SETUP_WRITE_KEY_ALLOWLIST`. Refusal of
non-allowlisted keys is verified by
``tests/framework/test_setup_source_allowlist.py``.

A future contributor adding a new shipped child (EDF, FHIR, vendor
sensor) MUST extend ``SETUP_WRITE_KEY_ALLOWLIST`` explicitly. Implicit
"if a ChildMCP declares it, allow it" paths are intentionally absent
to keep the bounded-write contract honest under refactoring.
"""

from __future__ import annotations

from typing import Any

# ──────────────────────────────────────────────────────────────────────
# Allowlists — the bounded-write contract
# ──────────────────────────────────────────────────────────────────────

# Source-type tokens accepted by the MCP setup tools.  Validated by
# ``ParamValidator`` with ``allowed_values`` — the v7.6.0 D1 closure
# in ``framework/security.py:79-91`` ensures the gate fires on
# ``type=str`` schemas (it did not on pre-D1 builds, but A' ships
# against v7.6.0 / D1-fixed builds).
SOURCE_TYPE_ALLOWLIST: tuple[str, ...] = ("csv", "matlab", "redcap")

# ``user_config.json`` top-level keys SetupLayer may write.  Every
# other key (``vault_path``, ``cost_threshold``, ``max_hr``,
# ``home_lat``, ``home_lng``, ``local_llm``, anything else) is REFUSED
# by ``tailor_setup_write_source_block`` with ``PARAM_INVALID``.
#
# The refusal gate lives in ``layer.py``'s ``execute()`` path; the
# allowlist also gates the source-block builder below so a malformed
# tool call cannot smuggle a non-allowlisted key through the
# ``build_source_block`` API either.
SETUP_WRITE_KEY_ALLOWLIST: tuple[str, ...] = (
    "csv_dir",
    "matlab_file",
    "redcap_file",
)

# Mapping from public source_type token → user_config.json source_key.
SOURCE_TYPE_TO_KEY: dict[str, str] = {
    "csv": "csv_dir",
    "matlab": "matlab_file",
    "redcap": "redcap_file",
}


# ──────────────────────────────────────────────────────────────────────
# Typed exceptions — distinguish "operator typed a wrong source name"
# from "framework bug widened the allowlist"
# ──────────────────────────────────────────────────────────────────────


class UnknownSourceType(ValueError):
    """Raised when ``source_type`` is not in :data:`SOURCE_TYPE_ALLOWLIST`."""

    def __init__(self, source_type: str) -> None:
        self.source_type = source_type
        super().__init__(
            f"Unknown source_type {source_type!r}. "
            f"Allowed: {SOURCE_TYPE_ALLOWLIST}"
        )


class UnknownSourceKey(ValueError):
    """Raised when a derived source_key is not in :data:`SETUP_WRITE_KEY_ALLOWLIST`.

    Should never raise in normal operation — :data:`SOURCE_TYPE_TO_KEY`
    is the only way to derive a key, and it maps only to allowlisted
    keys. Raising means a code path bypassed the mapping; the test
    suite asserts the invariant.
    """

    def __init__(self, source_key: str) -> None:
        self.source_key = source_key
        super().__init__(
            f"source_key {source_key!r} is not in the bounded-write "
            f"allowlist {SETUP_WRITE_KEY_ALLOWLIST}. "
            f"This indicates a framework bug — the allowlist must be "
            f"the only path that reaches the canonical writer."
        )


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────


def source_key_for_type(source_type: str) -> str:
    """Resolve a source_type token to its user_config.json source_key.

    Raises :class:`UnknownSourceType` for any token outside
    :data:`SOURCE_TYPE_ALLOWLIST`.
    """
    if source_type not in SOURCE_TYPE_ALLOWLIST:
        raise UnknownSourceType(source_type)
    return SOURCE_TYPE_TO_KEY[source_type]


def build_source_block(
    source_type: str,
    path: str,
    schema: dict[str, Any] | None,
) -> tuple[str, dict[str, Any]]:
    """Return ``(source_key, source_block)`` for ``write_source_block``.

    Validates that ``source_type`` is in the allowlist. Builds a
    per-source ``source_block`` dict from ``path`` + ``schema``:

    - ``csv`` → ``{"path": <path>, "timestamp_column": ...,
      "timestamp_format": ..., "value_columns": {...}}``
    - ``matlab`` → ``{"path": <path>, "variable_filter": [...]}``
      (omit ``variable_filter`` for the all-variables-auto-detected
      default)
    - ``redcap`` → ``{"path": <path>, "records_file": ...,
      "project_metadata_file": ..., "unknown_field_allowlist": [...]}``

    The returned ``source_key`` is one of
    :data:`SETUP_WRITE_KEY_ALLOWLIST` — verified via
    :func:`source_key_for_type`.
    """
    source_key = source_key_for_type(source_type)

    block: dict[str, Any] = {"path": path}

    if schema:
        if source_type == "csv":
            for k in ("timestamp_column", "timestamp_format", "value_columns"):
                if k in schema:
                    block[k] = schema[k]
        elif source_type == "matlab":
            if "variable_filter" in schema:
                block["variable_filter"] = schema["variable_filter"]
        elif source_type == "redcap":
            for k in (
                "records_file",
                "project_metadata_file",
                "instrument_completion_fields",
                "unknown_field_allowlist",
            ):
                if k in schema:
                    block[k] = schema[k]

    if source_key not in SETUP_WRITE_KEY_ALLOWLIST:
        # Defense in depth: should never trigger if SOURCE_TYPE_TO_KEY
        # only points at allowlisted keys.
        raise UnknownSourceKey(source_key)

    return source_key, block
