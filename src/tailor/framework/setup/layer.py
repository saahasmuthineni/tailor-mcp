"""
Setup Layer — Framework-tier bounded conductor surface (ADR 0040).

Four MCP tools (always-registered):

- ``tailor_setup_status`` — read-only status.
- ``tailor_setup_detect_schema`` — read-only schema detection.
- ``tailor_setup_confirm_schema`` — pure compute confirmation.
- ``tailor_setup_write_source_block`` — bounded write authority,
  source-key allowlist gated, audits ``SETUP_CONFIG_WRITE`` outcome.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from ..interfaces import ToolDefinition, ValidationSchema
from ..setup_help import _redact_home
from .sources import (
    SETUP_WRITE_KEY_ALLOWLIST,
    SOURCE_TYPE_ALLOWLIST,
    UnknownSourceKey,
    UnknownSourceType,
    build_source_block,
)

log = logging.getLogger("tailor.setup")


# ──────────────────────────────────────────────────────────────────────
# Tool descriptions — these drive Claude's natural-language inference
# (the discovery surface for terminal-averse recipients)
# ──────────────────────────────────────────────────────────────────────

_STATUS_DESCRIPTION = (
    "Return whether Tailor has any configured data sources yet, and "
    "if so which. Call this when the user asks 'is Tailor set up?' / "
    "'what's configured?' / 'show me my data sources' or as the "
    "opening move when a user starts a fresh session and you want "
    "to know whether to offer setup or analysis. Always safe to "
    "call; takes no parameters; returns a structured status dict."
)

_DETECT_DESCRIPTION = (
    "Read-only schema detection for a candidate data source. Call "
    "when the user says they want to start using Tailor with their "
    "own CSV / MATLAB / REDCap data and names a path. Returns the "
    "detected shape (CSV column names + best-guess timestamp "
    "column; MATLAB file inventory; REDCap export-directory file "
    "list) so you can summarize it for the user and confirm before "
    "writing config. Does NOT mutate user_config.json."
)

_CONFIRM_DESCRIPTION = (
    "Pure-compute confirmation of a detected schema. Call after "
    "tailor_setup_detect_schema and after the user has confirmed "
    "the detected shape looks right. Returns the same schema "
    "wrapped with a confirmation marker so the next call "
    "(write_source_block) carries proven-validated content. Does "
    "NOT mutate user_config.json."
)

_WRITE_DESCRIPTION = (
    "Bounded writer: persist a confirmed data-source configuration "
    "to user_config.json. Writes ONLY the allowlisted source-config "
    "keys (csv_dir / matlab_file / redcap_file) per ADR 0040; "
    "refuses any other key with PARAM_INVALID. Routes through the "
    "v7.5.0 multi-source-coexistence deep-merge writer so sibling "
    "source blocks are preserved. Emits a SETUP_CONFIG_WRITE audit "
    "row for IRB-grade provenance. The user must restart Claude "
    "Desktop after the write for the new source to appear in the "
    "tool surface."
)


# ──────────────────────────────────────────────────────────────────────
# Schema detection — read-only, structured returns
# ──────────────────────────────────────────────────────────────────────


def _detect_csv(path: Path) -> dict[str, Any]:
    """Wrap ``pilot._autodetect_csv_schema`` for the MCP surface."""
    # Local import to avoid a framework→tailor.pilot import cycle at
    # module load time. pilot.py imports framework.audit so the
    # opposite-direction import here is a cross-module call only on
    # invocation.
    from tailor.pilot import _autodetect_csv_schema

    if not path.exists():
        return {
            "ok": False,
            "error": f"Path does not exist: {path}",
            "remediation": (
                "Verify the directory path. CSV detect expects a "
                "directory containing *.csv files."
            ),
        }
    if not path.is_dir():
        return {
            "ok": False,
            "error": f"Path is not a directory: {path}",
            "remediation": (
                "CSV detect expects a directory of CSVs; for a "
                "single file pass its containing directory."
            ),
        }
    try:
        schema = _autodetect_csv_schema(path)
    except RuntimeError as exc:
        return {
            "ok": False,
            "error": str(exc),
            "remediation": (
                "Place one or more .csv files in the directory and "
                "retry. CSVs must have a header row."
            ),
        }
    schema_dict = asdict(schema) if is_dataclass(schema) else dict(schema)
    csv_count = len(list(path.glob("*.csv")))
    return {
        "ok": True,
        "source_type": "csv",
        "path": _redact_home(str(path)),
        "csv_count": csv_count,
        "schema": schema_dict,
    }


def _detect_matlab(path: Path) -> dict[str, Any]:
    """Inventory ``.mat`` files in the directory.

    Variable-level inventory (per ADR 0036) is the operator/RSE path
    through ``tailor pilot --source=matlab``; here the read-only MCP
    detection returns a file-count summary sufficient for Claude to
    confirm the user pointed at the right directory. ``variable_filter``
    in the written source_block remains optional (the matlab_file
    child auto-detects 1-D and 2-D numeric variables when absent).
    """
    if not path.exists():
        return {
            "ok": False,
            "error": f"Path does not exist: {path}",
        }
    if not path.is_dir():
        return {
            "ok": False,
            "error": f"Path is not a directory: {path}",
        }
    mat_files = sorted(path.glob("*.mat"))
    if not mat_files:
        return {
            "ok": False,
            "error": f"No .mat files in {path}",
            "remediation": (
                "Place one or more MATLAB .mat files (v5/v6/v7.2 — "
                "ADR 0036) in the directory and retry. HDF5-based v7.3 "
                "files are not yet supported."
            ),
        }
    return {
        "ok": True,
        "source_type": "matlab",
        "path": _redact_home(str(path)),
        "mat_file_count": len(mat_files),
        "mat_files_preview": [p.name for p in mat_files[:10]],
        "schema": {
            "variable_filter_note": (
                "Optional. Omit to let MATLABFileChild auto-detect "
                "1-D and 2-D numeric variables on each file. Specify "
                "as a list of variable names to restrict the inventory."
            ),
        },
    }


def _detect_redcap(path: Path) -> dict[str, Any]:
    """Probe a REDCap export directory for the required files.

    Verifies ``records.csv`` and ``project_metadata.csv`` exist (the
    canonical export filenames per ADR 0037). Operators with
    differently-named exports can override via the ``records_file`` /
    ``project_metadata_file`` schema keys in the subsequent
    ``write_source_block`` call.
    """
    if not path.exists():
        return {
            "ok": False,
            "error": f"Path does not exist: {path}",
        }
    if not path.is_dir():
        return {
            "ok": False,
            "error": f"Path is not a directory: {path}",
        }
    records = path / "records.csv"
    metadata = path / "project_metadata.csv"
    if not records.exists() and not metadata.exists():
        return {
            "ok": False,
            "error": (
                f"Neither records.csv nor project_metadata.csv found "
                f"in {path}"
            ),
            "remediation": (
                "Verify the path points at a REDCap export directory. "
                "Expected files: records.csv (per-record data) and "
                "project_metadata.csv (data dictionary with identifier "
                "flags per ADR 0037)."
            ),
        }
    return {
        "ok": True,
        "source_type": "redcap",
        "path": _redact_home(str(path)),
        "schema": {
            "records_file": "records.csv" if records.exists() else None,
            "project_metadata_file": (
                "project_metadata.csv" if metadata.exists() else None
            ),
            "records_present": records.exists(),
            "metadata_present": metadata.exists(),
            "unknown_field_allowlist_note": (
                "Defaults to empty (fail-closed per ADR 0037 — "
                "unknown fields treated as identifier-positive). "
                "Override with a list of field names a researcher "
                "has explicitly cleared as non-identifier."
            ),
        },
    }


_DETECTORS = {
    "csv": _detect_csv,
    "matlab": _detect_matlab,
    "redcap": _detect_redcap,
}


# ──────────────────────────────────────────────────────────────────────
# The Layer
# ──────────────────────────────────────────────────────────────────────


class SetupLayer:
    """Framework-tier bounded conductor surface for source-config setup.

    Always-registered per ADR 0040 (no runtime un-register convention
    exists in the framework as of v7.6.0; conditional registration
    rejected to enable mid-session add-source via the v7.5.0
    multi-source coexistence deep-merge writer).

    Bypasses biosensor-tier gates (consent, cost, circuit breaker,
    framework PHI scrub) per the framework-tier-layer pattern codified
    in ADR 0012 § Amendment v7.4.0. Param validation + audit still
    apply. The bounded-write contract is enforced by the source-key
    allowlist in :mod:`.sources`.
    """

    def __init__(self, *, config_dir: Path) -> None:
        self._config_dir = Path(config_dir)
        self._router = None  # Set by RouterMCP.register_setup_layer()
        log.info(
            "SetupLayer initialized (config_dir=%s)", self._config_dir,
        )

    @property
    def config_path(self) -> Path:
        """``user_config.json`` location for status / write paths."""
        return self._config_dir / "user_config.json"

    # ── Tool surface ──

    @property
    def tool_definitions(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                "tailor_setup_status",
                1,
                _STATUS_DESCRIPTION,
                {},
            ),
            ToolDefinition(
                "tailor_setup_detect_schema",
                1,
                _DETECT_DESCRIPTION,
                {
                    "source_type": {
                        "type": "string",
                        "description": (
                            "Required. One of 'csv' (directory of "
                            "*.csv files), 'matlab' (directory of "
                            "*.mat files), 'redcap' (REDCap export "
                            "directory containing records.csv + "
                            "project_metadata.csv)."
                        ),
                        "required": True,
                    },
                    "path": {
                        "type": "string",
                        "description": (
                            "Required. Absolute filesystem path to "
                            "the candidate source directory."
                        ),
                        "required": True,
                    },
                },
            ),
            ToolDefinition(
                "tailor_setup_confirm_schema",
                1,
                _CONFIRM_DESCRIPTION,
                {
                    "source_type": {
                        "type": "string",
                        "description": (
                            "Required. One of 'csv' / 'matlab' / "
                            "'redcap' — must match the source_type "
                            "passed to detect_schema."
                        ),
                        "required": True,
                    },
                    "path": {
                        "type": "string",
                        "description": (
                            "Required. The same path passed to "
                            "detect_schema."
                        ),
                        "required": True,
                    },
                    "schema": {
                        "type": "object",
                        "description": (
                            "Required. The schema dict returned by "
                            "detect_schema (or an operator-edited "
                            "version after the user confirmed the "
                            "shape)."
                        ),
                        "required": True,
                    },
                },
            ),
            ToolDefinition(
                "tailor_setup_write_source_block",
                1,
                _WRITE_DESCRIPTION,
                {
                    "source_type": {
                        "type": "string",
                        "description": (
                            "Required. One of 'csv' / 'matlab' / "
                            "'redcap'. Validated against the "
                            "SOURCE_TYPE_ALLOWLIST (ADR 0040)."
                        ),
                        "required": True,
                    },
                    "path": {
                        "type": "string",
                        "description": (
                            "Required. Absolute filesystem path to "
                            "the source directory. Written verbatim "
                            "into the source_block.path field."
                        ),
                        "required": True,
                    },
                    "validated_schema": {
                        "type": "object",
                        "description": (
                            "Required. The schema dict returned by "
                            "confirm_schema. Only keys recognized by "
                            "the chosen source_type are persisted "
                            "(see ADR 0040 § Decision)."
                        ),
                        "required": True,
                    },
                    "force": {
                        "type": "boolean",
                        "description": (
                            "Optional. When true, overwrite an "
                            "existing source_block of the same key. "
                            "When false (default), refuse with "
                            "FileExistsError-shaped error if the key "
                            "is already configured."
                        ),
                        "required": False,
                    },
                },
            ),
        ]

    @property
    def param_schemas(self) -> dict[str, dict[str, ValidationSchema]]:
        # source_type uses the v7.6.0 D1-closed allowed_values gate.
        source_type_schema = ValidationSchema(
            type=str,
            required=True,
            min_len=1,
            max_len=32,
            allowed_values=list(SOURCE_TYPE_ALLOWLIST),
        )
        path_schema = ValidationSchema(
            type=str, required=True, min_len=1, max_len=4096,
        )
        return {
            "tailor_setup_status": {},
            "tailor_setup_detect_schema": {
                "source_type": source_type_schema,
                "path": path_schema,
            },
            "tailor_setup_confirm_schema": {
                "source_type": source_type_schema,
                "path": path_schema,
                "schema": ValidationSchema(type=dict, required=True),
            },
            "tailor_setup_write_source_block": {
                "source_type": source_type_schema,
                "path": path_schema,
                "validated_schema": ValidationSchema(
                    type=dict, required=True,
                ),
                "force": ValidationSchema(type=bool, required=False),
            },
        }

    # ── Tool dispatch ──

    async def execute(self, tool_name: str, params: dict) -> dict:
        """Dispatch one of the four setup tools.

        Each branch is intentionally narrow — the load-bearing safety
        property is the bounded-write contract on ``write_source_block``
        (gated by the allowlist in :mod:`.sources`). The other three
        tools are read-only / pure compute.
        """
        if tool_name == "tailor_setup_status":
            return self._tool_status()
        if tool_name == "tailor_setup_detect_schema":
            return self._tool_detect_schema(params)
        if tool_name == "tailor_setup_confirm_schema":
            return self._tool_confirm_schema(params)
        if tool_name == "tailor_setup_write_source_block":
            return self._tool_write_source_block(params)
        return {"error": f"Unknown setup tool: {tool_name}"}

    # ── Tool implementations ──

    def _tool_status(self) -> dict[str, Any]:
        """Read user_config.json and report which sources are configured.

        Path fields applied through ``_redact_home`` to collapse
        ``Path.home()`` to ``~`` per HIPAA Safe Harbor
        §164.514(b)(2)(i)(R) — closes phi-irb-risk-reviewer WATCH-1
        (Lens 1) by extending the v6.10.2 SetupHelpLayer redaction
        pattern to the SetupLayer wire surface.
        """
        cfg_path = self.config_path
        redacted_path = _redact_home(str(cfg_path))
        if not cfg_path.exists():
            return {
                "status": "awaiting_setup",
                "configured_sources": [],
                "user_config_path": redacted_path,
                "user_config_exists": False,
                "available_source_types": list(SOURCE_TYPE_ALLOWLIST),
            }
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError) as exc:
            return {
                "status": "config_unreadable",
                "user_config_path": redacted_path,
                "error": str(exc),
                "available_source_types": list(SOURCE_TYPE_ALLOWLIST),
            }
        if not isinstance(cfg, dict):
            return {
                "status": "config_malformed",
                "user_config_path": redacted_path,
                "error": "user_config.json top-level is not an object",
                "available_source_types": list(SOURCE_TYPE_ALLOWLIST),
            }
        configured = [
            key for key in SETUP_WRITE_KEY_ALLOWLIST if cfg.get(key)
        ]
        return {
            "status": "configured" if configured else "awaiting_setup",
            "configured_sources": configured,
            "user_config_path": redacted_path,
            "user_config_exists": True,
            "available_source_types": list(SOURCE_TYPE_ALLOWLIST),
        }

    def _tool_detect_schema(self, params: dict) -> dict[str, Any]:
        source_type = params["source_type"]
        path = Path(params["path"])
        detector = _DETECTORS.get(source_type)
        if detector is None:
            # Should be unreachable — ParamValidator's allowed_values
            # gate fires first. Defense-in-depth.
            return {
                "ok": False,
                "error": (
                    f"Unknown source_type {source_type!r}. "
                    f"Allowed: {SOURCE_TYPE_ALLOWLIST}"
                ),
            }
        return detector(path)

    def _tool_confirm_schema(self, params: dict) -> dict[str, Any]:
        """Pure pass-through with confirmation marker.

        No filesystem access; no mutation. The user has reviewed the
        detected shape; this tool stamps the schema as
        operator-confirmed so the subsequent write tool can flag
        unconfirmed writes if they ever arise.
        """
        source_type = params["source_type"]
        path = params["path"]
        schema = params["schema"]
        if source_type not in SOURCE_TYPE_ALLOWLIST:
            return {
                "ok": False,
                "error": (
                    f"Unknown source_type {source_type!r}. "
                    f"Allowed: {SOURCE_TYPE_ALLOWLIST}"
                ),
            }
        return {
            "ok": True,
            "source_type": source_type,
            "path": _redact_home(path),
            "schema": schema,
            "confirmed": True,
        }

    def _tool_write_source_block(self, params: dict) -> dict[str, Any]:
        """Bounded writer — the load-bearing safety surface.

        Validates source_type → source_key mapping is allowlisted,
        builds the source_block via :func:`build_source_block`, calls
        the canonical writer ``pilot._write_user_config``, and returns
        the path written. Raises do NOT escape — they are caught and
        returned as structured error envelopes so the router records
        the audit row with full context.
        """
        # Local import — see _detect_csv() rationale.
        from tailor.pilot import _write_user_config

        source_type = params["source_type"]
        path = params["path"]
        validated_schema = params["validated_schema"]
        force = bool(params.get("force", False))

        try:
            source_key, source_block = build_source_block(
                source_type, path, validated_schema,
            )
        except UnknownSourceType as exc:
            return {
                "ok": False,
                "error": str(exc),
                "error_class": "UnknownSourceType",
            }
        except UnknownSourceKey as exc:
            # Should never fire — indicates a framework bug.
            return {
                "ok": False,
                "error": str(exc),
                "error_class": "UnknownSourceKey",
            }

        # Defense-in-depth: explicit allowlist check at the dispatch
        # site, in addition to the build_source_block check.  A bug in
        # build_source_block cannot widen the surface.
        if source_key not in SETUP_WRITE_KEY_ALLOWLIST:
            return {
                "ok": False,
                "error": (
                    f"source_key {source_key!r} is not in the "
                    f"bounded-write allowlist "
                    f"{SETUP_WRITE_KEY_ALLOWLIST}."
                ),
                "error_class": "DispatchAllowlistViolation",
            }

        try:
            written_path = _write_user_config(
                source_key, source_block, force=force,
            )
        except FileExistsError as exc:
            return {
                "ok": False,
                "error": str(exc),
                "error_class": "FileExistsError",
                "remediation": (
                    "The source is already configured. Pass force=true "
                    "to overwrite, or call tailor_setup_status to "
                    "confirm the current configuration."
                ),
            }
        except OSError as exc:
            return {
                "ok": False,
                "error": str(exc),
                "error_class": "OSError",
            }

        # ``written_path`` redacted through ``_redact_home`` to keep
        # username-bearing paths off the wire — same Lens 1 closure
        # as ``_tool_status``. The on-disk write itself uses the
        # un-redacted ``written_path`` (canonical writer's return);
        # only the wire response is redacted.
        return {
            "ok": True,
            "source_type": source_type,
            "source_key": source_key,
            "written_path": _redact_home(str(written_path)),
            "restart_required": True,
            "restart_message": (
                "Restart Claude Desktop to load the new source. "
                "Tailor's tool surface picks up the new "
                f"{source_key} block on the next "
                "`tailor serve` startup."
            ),
        }
