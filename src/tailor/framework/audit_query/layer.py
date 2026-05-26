"""
Audit Query Layer — Framework-Level IRB Reviewer Surface
=========================================================
Framework-level infrastructure that exposes a single read-only tool
(``audit_query``) over the audit log. Registered with the router
parallel to ``VaultLayer`` / ``LocalLLMLayer`` / ``SetupHelpLayer``;
skips biosensor-tier gates (consent, cost, circuit breaker, framework
PHI-scrub seam) — only param validation and audit apply.

Closes the v7.3.4 audit-log-over-promise gap. Before this layer the
recipient prompt "Show me what just happened in the audit log" had
no MCP tool to land on; the v7.3.4 fitting-room banner reworded the
prompt to vault-list-moments as a stopgap. With this layer the
original audit-log-shaped prompt is live again.

The B1 design (column allowlist, no raw params/error content) is the
load-bearing posture. ADR 0012 § Amendment v7.4.0 codifies the bypass
invariant + reversal condition (a future tool that surfaces raw
params/error must amend this layer with its own per-row scrubber —
the B2/B3 escalation path from the v7.4.0 proposal audit).

Tools:
    audit_query    Read structured columns from audit_log filtered by
                   time / subject / domain / tool / outcome. Returns
                   the B1 column allowlist — no ``params`` content,
                   no raw ``error`` strings (only ``has_error`` bool).
"""

from __future__ import annotations

import logging

from ..audit import AuditLog
from ..interfaces import (
    ENTITY_ID_PARAM_DOC,
    ENTITY_ID_SCHEMA,
    ToolDefinition,
    ValidationSchema,
)
from .parser import MAX_LOOKBACK_DAYS, SinceParseError, parse_since

log = logging.getLogger("tailor.audit_query")


_AUDIT_QUERY_DESCRIPTION = (
    "Read structured columns from the audit log — the IRB-grade query "
    "surface. Returns a list of audit rows ordered by timestamp "
    "descending; each row carries id, timestamp, domain, tool_name, "
    "tier, token_estimate, outcome, duration_ms, entity_id, "
    "scrubber_id, child_scrubber_id, source_metadata_fingerprint, and "
    "has_error (bool). The raw params content and raw error strings "
    "are NEVER returned — for those, drop to 'tailor status' or "
    "'sqlite3 audit.db' directly. Typical questions this answers: "
    "'did the PHI scrubber run on subject S004's last consent "
    "revocation?' (filter outcome=PURGE_CACHE / entity_id=S004); "
    "'what just failed in the last hour?' (since=1h / outcome=ERROR); "
    "'show me every REDCap trust-root re-attestation' "
    "(domain=redcap_file / tool=tailor_redcap_reattest). Use 'since' "
    f"to bound the window — max lookback is {MAX_LOOKBACK_DAYS} days; "
    "for longer history drop to sqlite3 directly. Cheap call: response "
    "is structured metadata only (~5-15k tokens at limit=100)."
)


class AuditQueryLayer:
    """
    Framework-level IRB-reviewer surface over the audit log.

    Skips consent, cost, circuit breaker, and framework PHI scrub by
    construction: the response shape is a column allowlist (framework-
    emitted structured metadata), not biosensor stream content. ADR
    0012 § Amendment v7.4.0 codifies the bypass invariant + reversal
    condition.
    """

    def __init__(self, audit_log: AuditLog) -> None:
        self._audit_log = audit_log
        self._router = None  # Set by RouterMCP.register_audit_query_layer()
        log.info("AuditQueryLayer initialized")

    @property
    def tool_definitions(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                "audit_query",
                1,
                _AUDIT_QUERY_DESCRIPTION,
                {
                    "since": {
                        "type": "string",
                        "description": (
                            "Time-window lower bound. Accepts relative "
                            "forms like '1h' / '24h' / '7d' / '1w' "
                            "(case-insensitive, positive integers) OR "
                            "ISO 8601 timestamp "
                            "('2026-05-16T12:00:00Z'). Naive ISO "
                            "timestamps are coerced to UTC. Max "
                            f"lookback {MAX_LOOKBACK_DAYS} days; "
                            "negative durations and future timestamps "
                            "are rejected."
                        ),
                        "required": True,
                    },
                    "entity_id": ENTITY_ID_PARAM_DOC,
                    "domain": {
                        "type": "string",
                        "description": (
                            "Optional. Exact match against the row's "
                            "domain. Examples: 'running', 'csv_dir', "
                            "'force_csv', 'emg_csv', 'matlab_file', "
                            "'redcap_file', 'vault', 'local_llm', "
                            "'setup_help', 'audit_query', 'setup' "
                            "(SetupLayer per ADR 0040), 'walkthrough' "
                            "(WalkthroughLayer per ADR 0040), "
                            "'fitting_room' (FittingRoomLayer per "
                            "ADR 0040)."
                        ),
                        "required": False,
                    },
                    "tool": {
                        "type": "string",
                        "description": (
                            "Optional. Exact match against the row's "
                            "tool_name (e.g. 'csv_group_summary', "
                            "'vault_upsert_theme')."
                        ),
                        "required": False,
                    },
                    "outcome": {
                        "type": "string",
                        "description": (
                            "Optional. Exact match against the row's "
                            "outcome. Common values: 'SUCCESS', "
                            "'ERROR', 'PARAM_INVALID', 'CIRCUIT_OPEN', "
                            "'CONSENT_BLOCKED', 'COST_BLOCKED', "
                            "'PURGE_CACHE', 'PURGE_FAILED', 'REATTEST' "
                            "(re-attestation against drift via "
                            "`tailor redcap reattest`), "
                            "'ATTEST_INITIAL' (first-config "
                            "attestation via `tailor pilot "
                            "--source=redcap`), 'SETUP_CONFIG_WRITE' "
                            "(SetupLayer bounded source-block write via "
                            "`tailor_setup_write_source_block` per "
                            "ADR 0040), plus the *_INTERNAL "
                            "variants from cross-child dispatch."
                        ),
                        "required": False,
                    },
                    "limit": {
                        "type": "integer",
                        "description": (
                            "Optional. Max rows to return. Default 50, "
                            "hard cap 100."
                        ),
                        "required": False,
                    },
                    "include_self": {
                        "type": "boolean",
                        "description": (
                            "Optional. When false, rows with "
                            "tool_name='audit_query' are excluded. "
                            "Default true so audit-query usage is "
                            "visible in the audit trail by default."
                        ),
                        "required": False,
                    },
                },
            ),
        ]

    @property
    def param_schemas(self) -> dict[str, dict[str, ValidationSchema]]:
        return {
            "audit_query": {
                "since": ValidationSchema(
                    type=str, required=True, min_len=1, max_len=64,
                ),
                "entity_id": ENTITY_ID_SCHEMA,
                "domain": ValidationSchema(
                    type=str, required=False, min_len=1, max_len=64,
                ),
                "tool": ValidationSchema(
                    type=str, required=False, min_len=1, max_len=128,
                ),
                "outcome": ValidationSchema(
                    type=str, required=False, min_len=1, max_len=64,
                ),
                "limit": ValidationSchema(
                    type=int, required=False, min=1, max=100,
                ),
                "include_self": ValidationSchema(
                    type=bool, required=False,
                ),
            },
        }

    async def execute(self, tool_name: str, params: dict) -> dict:
        """Dispatch the layer's single tool."""
        if tool_name != "audit_query":
            return {"error": f"Unknown audit_query tool: {tool_name}"}

        # Parse `since`. Failure surfaces as a structured error envelope
        # so the router's dispatch records the audit row with the
        # original input intact rather than as a raised exception that
        # loses caller context.
        try:
            since_iso = parse_since(params["since"])
        except SinceParseError as exc:
            return {
                "error": str(exc),
                "original_since": exc.original,
            }

        rows = self._audit_log.query(
            since=since_iso,
            entity_id=params.get("entity_id"),
            domain=params.get("domain"),
            tool=params.get("tool"),
            outcome=params.get("outcome"),
            limit=params.get("limit", 50),
            include_self=params.get("include_self", True),
        )

        scope_parts = [f"since={since_iso}"]
        for key in ("entity_id", "domain", "tool", "outcome"):
            val = params.get(key)
            if val is not None:
                scope_parts.append(f"{key}={val}")
        scope_parts.append(f"limit={params.get('limit', 50)}")
        if not params.get("include_self", True):
            scope_parts.append("include_self=false")

        return {
            "rows": rows,
            "row_count": len(rows),
            "scope_statement": " ".join(scope_parts),
        }
