"""
Setup Help Layer — Framework-Level Recipient Diagnostic
=========================================================
Framework-level infrastructure that exposes a single recipient-facing
diagnostic tool when ``tailor serve`` is started without the
demo scaffold installed (no ``force_csv``, ``emg_csv``, ``csv_dir``,
or ``vault_path`` in ``user_config.json``).

The trigger condition is exactly the dad-style failure documented in
the v6.10.2 release notes: the recipient installed the wheel, ran
``tailor serve`` directly (via web-Claude-mediated manual
config rather than the canonical ``tailor fitting-room`` — renamed
from ``tailor tour`` in v7.1.0 per ADR 0035), and now sits in front
of a server with only ``ask_local_oracle`` and the running child's
12 strava tools — none of which match the cue-card prompts
(``force_cohort_summary``, ``emg_cohort_summary``, etc.).

Why a layer and not a ChildMCP: registering through ``register_child``
auto-generates ``approve_consent_<domain>`` + ``revoke_consent_<domain>``
tools per the framework convention. A consent surface for a static
help tool is nonsensical. Layer registration via the existing
``(None, tool_def)`` sentinel + ``_framework_layer_owner`` pattern
(parallel to ``VaultLayer`` and ``LocalLLMLayer``) keeps the dispatch
pipeline narrow: param validation + execute + audit, no consent /
cost / circuit / PHI scrub.

The layer is registered conditionally in ``__main__.cmd_serve``: only
when none of the demo blocks are present in ``user_config.json``.
When the demo scaffold IS installed, this tool does not exist in
``tools/list``, so Claude cannot pick it preferentially for routine
queries (closes the v6.9.1 prose-to-schema-inference trap).
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from ..interfaces import ToolDefinition, ValidationSchema

log = logging.getLogger("tailor.setup_help")


def _redact_home(value: str) -> str:
    """Return ``value`` with ``Path.home()`` collapsed to ``~``.

    Closes the v6.10.2 phi-irb-risk-reviewer Lens 1 finding:
    ``Path.home()`` resolves to a username-bearing path on every
    supported platform (``C:\\Users\\<name>\\...`` on Windows;
    ``/Users/<name>/...`` on macOS; ``/home/<name>/...`` on Linux).
    HIPAA Safe Harbor §164.514(b)(2)(i)(R) treats a bare OS username
    as a "unique identifying characteristic" on participant-recipient
    deployments. The recipient-is-analyst case is the documented
    deployment shape, but the redaction is cheap and removes the
    asymmetry: every diagnostic path the LLM sees is now home-relative.

    Identity-on-failure: a non-string input or a path that does not
    contain ``Path.home()`` is returned unchanged. The redaction is
    additive and never raises.
    """
    if not isinstance(value, str):
        return value
    try:
        home = str(Path.home())
    except (RuntimeError, OSError):
        return value
    if not home:
        return value
    # Normalise both sides to forward slashes for the comparison so
    # cross-platform path separators do not defeat the redaction.
    home_n = home.replace("\\", "/").rstrip("/")
    value_n = value.replace("\\", "/")
    if value_n == home_n:
        return "~"
    if value_n.startswith(home_n + "/"):
        return "~" + value_n[len(home_n):]
    return value


_SETUP_HELP_DESCRIPTION = (
    "RECIPIENT SETUP DIAGNOSTIC. This Tailor server is running but the "
    "demo scaffold has not been installed yet. If you are trying to call "
    "force_cohort_summary, emg_cohort_summary, force_summary, "
    "emg_envelope_summary, csv_summary_report, csv_group_summary, "
    "csv_force_decline, or any vault_* tool and they appear missing, "
    "call this tool — it returns step-by-step terminal instructions for "
    "the recipient to scaffold the demo cohort via `tailor fitting-room`, "
    "then restart Claude Desktop. Always safe to call; takes no "
    "parameters; returns instructions only."
)


class SetupHelpLayer:
    """
    Framework-level diagnostic surface that fires only when the server
    is started with no demo scaffold installed.

    Conditional registration: see ``__main__.cmd_serve`` — the layer
    is only constructed and registered when ``user_config.json``
    contains no ``force_csv`` / ``emg_csv`` / ``csv_dir`` / ``vault_path``
    blocks. When the demo IS scaffolded, this tool does not exist on
    the wire surface.
    """

    def __init__(
        self,
        *,
        config_dir: Path,
        data_dir: Path,
    ) -> None:
        self._config_dir = config_dir
        self._data_dir = data_dir
        self._router = None  # Set by RouterMCP.register_setup_help_layer()
        log.info(
            "SetupHelpLayer registered (config_dir=%s, data_dir=%s)",
            config_dir, data_dir,
        )

    @property
    def tool_definitions(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                "tailor_setup_help",
                1,
                _SETUP_HELP_DESCRIPTION,
                {},
            ),
        ]

    @property
    def param_schemas(self) -> dict[str, dict[str, ValidationSchema]]:
        return {"tailor_setup_help": {}}

    async def execute(self, tool_name: str, params: dict) -> dict:
        """Return scaffolding instructions + diagnostic state."""
        if tool_name != "tailor_setup_help":
            return {"error": f"Unknown setup-help tool: {tool_name}"}

        config_dir_exists = self._config_dir.exists()
        user_config_path = self._config_dir / "user_config.json"
        user_config_exists = user_config_path.exists()
        default_scaffold_target = (
            Path.home() / ".tailor" / "demos" / "cohort"
        )
        scaffold_target_exists = default_scaffold_target.exists()

        return {
            "diagnosis": (
                "This tailor server is running but no demo "
                "scaffold has been installed. The expected recipient "
                "path is `tailor fitting-room` (renamed from `tailor "
                "tour` in v7.1.0 per ADR 0035; the legacy verb still "
                "works through v7.1.0), which copies bundled synthetic "
                "fixtures, writes user_config.json, indexes the seed "
                "vault, and registers a Claude Desktop entry. Without "
                "it, only the running (Strava) child + the local-LLM "
                "guardian are loaded — none of the demo tools "
                "(force_cohort_summary, emg_cohort_summary, vault_*) "
                "exist on this server."
            ),
            "recipient_steps": [
                "Open a terminal (PowerShell on Windows; Terminal on "
                "macOS).",
                "Run: tailor fitting-room",
                "If that errors with 'scaffold already exists', "
                "run: tailor fitting-room --force",
                "Fully quit Claude Desktop (right-click the system-tray "
                "icon and choose Quit on Windows; Cmd+Q on macOS — "
                "closing the window is not enough).",
                "Re-open Claude Desktop and start a fresh chat.",
                "Try: 'List the available Tailor tools.' — you "
                "should see force_csv_*, emg_csv_*, vault_*, strava_* "
                "tools.",
            ],
            "diagnostics": {
                "config_dir": _redact_home(str(self._config_dir)),
                "config_dir_exists": config_dir_exists,
                "user_config_path": _redact_home(str(user_config_path)),
                "user_config_exists": user_config_exists,
                "default_scaffold_target": _redact_home(
                    str(default_scaffold_target),
                ),
                "default_scaffold_target_exists": scaffold_target_exists,
                "tailor_config_dir_env": _redact_home(
                    os.environ.get(
                        "TAILOR_CONFIG_DIR", "(not set)",
                    ),
                ),
                "tailor_data_dir_env": _redact_home(
                    os.environ.get(
                        "TAILOR_DATA_DIR", "(not set)",
                    ),
                ),
                "python_executable": _redact_home(sys.executable),
            },
            "if_scaffold_keeps_failing": (
                "Send a screenshot of the terminal output from "
                "`tailor fitting-room` to the project owner. The most "
                "common Windows failure mode (cp1252 encoding crashes) "
                "was patched in v6.10.1; if the wheel installed is "
                "v6.9.x, upgrading the wheel is the fix."
            ),
        }


def _demo_blocks_absent(user_config: dict) -> bool:
    """True when ``user_config.json`` has no demo / vault blocks.

    Trigger condition for SetupHelpLayer registration in
    ``__main__.cmd_serve``. Strava-only deployments (the documented
    pre-v6.5 default) match this predicate; in practice no real users
    are in that state, and registering the diagnostic on a Strava-only
    server is harmless because the tool name is namespaced and the
    description explicitly leads with "RECIPIENT SETUP DIAGNOSTIC" so
    Claude won't pick it for vague queries.
    """
    keys_signalling_scaffold = (
        "force_csv", "emg_csv", "csv_dir", "vault_path",
        "matlab_file", "redcap_file",
    )
    return not any(user_config.get(key) for key in keys_signalling_scaffold)


__all__ = ["SetupHelpLayer", "_demo_blocks_absent", "_redact_home"]
