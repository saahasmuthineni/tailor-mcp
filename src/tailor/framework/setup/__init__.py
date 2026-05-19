"""
Setup Layer — Framework-Level Bounded Conductor Surface
========================================================

A bounded-write-authority framework-tier layer that lets the hosted LLM
configure data sources via MCP tools, parallel to the operator path
(``tailor pilot`` CLI wizard). Codified by
:doc:`ADR 0040 <../../../../docs/adr/0040-bounded-setup-time-conductor-surface>`.

Four tools:

- ``tailor_setup_status`` — read-only.
- ``tailor_setup_detect_schema`` — read-only schema detection.
- ``tailor_setup_confirm_schema`` — pure compute confirmation.
- ``tailor_setup_write_source_block`` — bounded writer (allowlisted
  source-keys only; emits ``SETUP_CONFIG_WRITE`` audit row).

The load-bearing safety property is the source-key allowlist in
:mod:`.sources` — see ``SETUP_WRITE_KEY_ALLOWLIST``.
"""

from __future__ import annotations

from .layer import SetupLayer
from .sources import (
    SETUP_WRITE_KEY_ALLOWLIST,
    SOURCE_TYPE_ALLOWLIST,
    UnknownSourceKey,
    UnknownSourceType,
    build_source_block,
    source_key_for_type,
)

__all__ = [
    "SetupLayer",
    "SETUP_WRITE_KEY_ALLOWLIST",
    "SOURCE_TYPE_ALLOWLIST",
    "UnknownSourceKey",
    "UnknownSourceType",
    "build_source_block",
    "source_key_for_type",
]
