"""
FittingRoomLayer — MCP-tool version of v6.9.0 fitting-room scaffolding.

Wraps the pure-logic helpers in :mod:`tailor.fitting_room` (which is
preserved as a library module — only the CLI dispatch in
``__main__.py:cmd_fitting_room`` is removed under ADR 0040). Three
tools:

- ``tailor_fitting_room_status`` — read-only filesystem check.
- ``tailor_fitting_room_scaffold`` — copy bundled fixtures + write
  demo user_config.json + index vault. Does NOT write Claude Desktop
  config (that's ``tailor pilot``'s job in the new architecture).
- ``tailor_fitting_room_index_vault`` — re-run vault rescan on the
  scaffolded directory (operator-recoverable after manual edits).
"""

from __future__ import annotations

import logging
from pathlib import Path

from ..interfaces import ToolDefinition, ValidationSchema

log = logging.getLogger("tailor.fitting_room")


_STATUS_DESCRIPTION = (
    "Return whether the bundled demo cohort fitting-room demo has been "
    "scaffolded on this machine. Call when the user asks 'is the "
    "demo set up?' / 'do I have the practice data?' or as a "
    "diagnostic before suggesting scaffold_demo. Always safe to "
    "call; takes no parameters."
)

_SCAFFOLD_DESCRIPTION = (
    "Copy the bundled demo cohort realistic fixtures into "
    "~/.tailor/demos/cohort/, write a demo user_config.json with "
    "the right paths + cost_threshold tuned to make the cost gate "
    "fire on bundled subjects, and index the seed vault. Call when "
    "the user says 'show me the demo' / 'scaffold the practice "
    "data' / 'set up the bundled fixtures'. Does NOT modify the "
    "user's actual ~/.tailor/user_config.json or Claude Desktop "
    "config — the scaffold is sandboxed in ~/.tailor/demos/cohort/. "
    "For Claude Desktop to surface the demo's tool set, the user "
    "needs to run `tailor pilot` to register Tailor (one-time "
    "bootstrap) then restart Claude Desktop."
)

_INDEX_DESCRIPTION = (
    "Re-run the vault index on the scaffolded demo directory. Call "
    "when the user has manually edited markdown files in the demo "
    "vault and wants the SQLite index to catch up. Read-only "
    "against ~/.tailor/user_config.json; the rescan is bounded to "
    "the demo's own vault."
)


def _demo_target_dir(variant: str = "cohort") -> Path:
    return Path.home() / ".tailor" / "demos" / variant


class FittingRoomLayer:
    """Framework-tier wrapper around ``tailor.fitting_room`` helpers."""

    def __init__(self) -> None:
        self._router = None  # Set by RouterMCP.register_fitting_room_layer()
        log.info("FittingRoomLayer initialized")

    @property
    def tool_definitions(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                "tailor_fitting_room_status",
                1,
                _STATUS_DESCRIPTION,
                {},
            ),
            ToolDefinition(
                "tailor_fitting_room_scaffold",
                1,
                _SCAFFOLD_DESCRIPTION,
                {
                    "variant": {
                        "type": "string",
                        "description": (
                            "Optional. Currently only 'cohort' is "
                            "shipped; defaults to 'cohort'."
                        ),
                        "required": False,
                    },
                    "force": {
                        "type": "boolean",
                        "description": (
                            "Optional. When true, scaffold even if "
                            "the target directory already exists "
                            "(matches the v6.9.0 CLI's --force "
                            "semantics: rmtree + re-scaffold)."
                        ),
                        "required": False,
                    },
                },
            ),
            ToolDefinition(
                "tailor_fitting_room_index_vault",
                1,
                _INDEX_DESCRIPTION,
                {
                    "variant": {
                        "type": "string",
                        "description": (
                            "Optional. Currently only 'cohort'."
                        ),
                        "required": False,
                    },
                },
            ),
        ]

    @property
    def param_schemas(self) -> dict[str, dict[str, ValidationSchema]]:
        variant_schema = ValidationSchema(
            type=str,
            required=False,
            min_len=1,
            max_len=32,
            allowed_values=["cohort"],
        )
        return {
            "tailor_fitting_room_status": {},
            "tailor_fitting_room_scaffold": {
                "variant": variant_schema,
                "force": ValidationSchema(type=bool, required=False),
            },
            "tailor_fitting_room_index_vault": {
                "variant": variant_schema,
            },
        }

    async def execute(self, tool_name: str, params: dict) -> dict:
        if tool_name == "tailor_fitting_room_status":
            return self._tool_status(params.get("variant", "cohort"))
        if tool_name == "tailor_fitting_room_scaffold":
            return self._tool_scaffold(
                params.get("variant", "cohort"),
                bool(params.get("force", False)),
            )
        if tool_name == "tailor_fitting_room_index_vault":
            return self._tool_index_vault(
                params.get("variant", "cohort"),
            )
        return {"error": f"Unknown fitting-room tool: {tool_name}"}

    # ── Tool implementations ──

    def _tool_status(self, variant: str) -> dict:
        target = _demo_target_dir(variant)
        return {
            "variant": variant,
            "target_dir": str(target),
            "exists": target.exists(),
            "user_config_exists": (target / "user_config.json").exists(),
            "vault_dir_exists": (target / "vault").exists(),
            "vault_db_exists": (target / "data" / "vault.db").exists(),
        }

    def _tool_scaffold(self, variant: str, force: bool) -> dict:
        # Local imports — keep framework→tailor.fitting_room edge
        # lazy so a future top-level reorganisation doesn't break
        # framework module load.
        import shutil

        from tailor.fitting_room import (
            _index_vault,
            _scaffold_fixtures,
            _write_user_config,
        )

        target = _demo_target_dir(variant)

        if target.exists():
            if not force:
                return {
                    "ok": False,
                    "error": (
                        f"Target directory already exists: {target}. "
                        f"Pass force=true to rmtree and re-scaffold."
                    ),
                    "error_class": "TargetExists",
                }
            shutil.rmtree(target)

        target.mkdir(parents=True, exist_ok=True)

        try:
            fixture_counts = _scaffold_fixtures(variant, target)
        except Exception as exc:
            return {
                "ok": False,
                "error": f"Fixture scaffold failed: {exc}",
                "error_class": type(exc).__name__,
            }

        try:
            config_path = _write_user_config(variant, target)
        except Exception as exc:
            return {
                "ok": False,
                "error": f"user_config write failed: {exc}",
                "error_class": type(exc).__name__,
                "partial": {"fixture_counts": fixture_counts},
            }

        try:
            index_counts = _index_vault(target)
        except Exception as exc:
            return {
                "ok": False,
                "error": f"Vault index failed: {exc}",
                "error_class": type(exc).__name__,
                "partial": {
                    "fixture_counts": fixture_counts,
                    "config_path": str(config_path),
                },
            }

        return {
            "ok": True,
            "variant": variant,
            "target_dir": str(target),
            "fixture_counts": fixture_counts,
            "user_config_path": str(config_path),
            "vault_index_counts": index_counts,
            "restart_required": True,
            "restart_message": (
                "Restart Claude Desktop to refresh the tool surface. "
                "The demo's tools become visible once `tailor serve` "
                "next boots against the scaffolded user_config.json."
            ),
        }

    def _tool_index_vault(self, variant: str) -> dict:
        from tailor.fitting_room import _index_vault

        target = _demo_target_dir(variant)
        if not target.exists():
            return {
                "ok": False,
                "error": (
                    f"Target directory does not exist: {target}. "
                    f"Run tailor_fitting_room_scaffold first."
                ),
                "error_class": "TargetMissing",
            }
        try:
            counts = _index_vault(target)
        except Exception as exc:
            return {
                "ok": False,
                "error": str(exc),
                "error_class": type(exc).__name__,
            }
        return {
            "ok": True,
            "variant": variant,
            "target_dir": str(target),
            "vault_index_counts": counts,
        }
