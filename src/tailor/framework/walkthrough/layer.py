"""
WalkthroughLayer — MCP-tool version of the v6.12.0 architectural showcase.

A single tool ``tailor_walkthrough_section(section: int)`` returns one
of five structured payloads describing the framework's architectural
claims. Claude narrates each section conversationally to the recipient
and invites them to call the relevant Tailor tools to exercise the
claim against real data.

This layer replaces the ``tailor walkthrough`` CLI command (per
ADR 0040). The architectural sections are unchanged from ADR 0027 +
ADR 0029; the surface is now MCP instead of stdout.
"""

from __future__ import annotations

import logging

from ..interfaces import ToolDefinition, ValidationSchema

log = logging.getLogger("tailor.walkthrough")


_WALKTHROUGH_DESCRIPTION = (
    "Conducted-tour MCP surface for Tailor's architectural claims. "
    "Call with section=1..5 to surface one of five structured "
    "narratives the framework was designed against: (1) Tier-1 "
    "cohort thesis — analytical answers without raw streams; (2) "
    "router pipeline with audit-log provenance; (3) three-tier "
    "consent + cost model on the same question; (4) vault layer for "
    "cross-session analytical memory; (5) local-LLM guardian over "
    "deterministic processing output. Call when the user says 'show "
    "me what Tailor can do' / 'walk me through it' / 'how does this "
    "work' / a request to see section N specifically. Each call "
    "returns the section's narrative prose, a worked-example payload "
    "(constants from a known-good HIP Lab fixture run), the relevant "
    "ADR citations, and a next-step prompt for the recipient. "
    "Replaces v6.10.5 `tailor walkthrough` CLI per ADR 0040."
)


# ──────────────────────────────────────────────────────────────────────
# Section payloads — narrative + worked-example output + ADR pointers
# ──────────────────────────────────────────────────────────────────────

_SECTION_PAYLOADS: dict[int, dict] = {
    1: {
        "section": 1,
        "title": "Tier-1 cohort thesis — answers, not streams",
        "narrative": (
            "Tier 1 returns a server-computed answer to a cohort "
            "question. Raw biometric streams never enter the LLM's "
            "context. On bundled HIP Lab fixtures (16 synthetic "
            "subjects, 8M/8F, intermittent isometric force task to "
            "volitional failure), `force_cohort_summary` reduces "
            "100 Hz force traces to per-group mean/std/min/max in "
            "~310 tokens — the same question via Tier-3 raw streams "
            "would cost ~50,000 tokens. The example values below "
            "are wire-verified against the bundled fixtures (per "
            "red-team-reviewer 2026-05-19) — call the tool yourself "
            "to reproduce them."
        ),
        "worked_example": {
            "tool": "force_cohort_summary",
            "params": {
                "metric": "mean",
                "value_column": "force_N",
                "group_by": "sex",
            },
            "approximate_token_cost": 310,
            "example_result_shape": {
                "groups": [
                    {"sex": "F", "n": 8, "mean": 65.28, "std": 6.62},
                    {"sex": "M", "n": 8, "mean": 87.62, "std": 6.46},
                ],
            },
        },
        "adr_citations": [
            "ADR 0015 (Tier-1 cohort surface + metadata sidecar)",
            "ADR 0008 (deterministic-by-construction processing)",
            "ADR 0029 (token reduction as analytical quality)",
        ],
        "next_step": (
            "Try `force_cohort_summary` with metric='mean', "
            "value_column='force_N', and group_by='sex' against the "
            "bundled HIP Lab fixtures, or ask Claude to walk through "
            "section 2 for the router pipeline view."
        ),
    },
    2: {
        "section": 2,
        "title": "Router pipeline — every call is audit-log-provenanced",
        "narrative": (
            "Every tool call passes through the RouterMCP's "
            "validate → circuit-break → consent → cost → execute → "
            "PHI-scrub → audit pipeline. Each call lands a row in "
            "`audit.db` with timestamp, domain, tool_name, tier, "
            "parameters, token estimate, outcome, latency, optional "
            "subject_id, and the scrubber identity. An IRB reviewer "
            "can reconstruct what was accessed, by whom, when, and "
            "at what resolution from `audit.db` alone."
        ),
        "worked_example": {
            "tool_called": "csv_summary_report",
            "audit_row_shape": {
                "id": 1,
                "timestamp": "2026-05-19T04:46:14Z",
                "domain": "csv_dir",
                "tool_name": "csv_summary_report",
                "tier": 1,
                "outcome": "SUCCESS",
                "token_estimate": 102,
                "duration_ms": 11,
                "subject_id": None,
                "scrubber_id": "noop",
                "source_metadata_fingerprint": None,
            },
            "meta_block_shape": {
                "tokens_this_call": 102,
                "session_total_tokens": 102,
                "domain": "csv_dir",
                "tier": 1,
                "package_version": "<read from tailor.__version__ at "
                "call time; this string is illustrative only>",
                "tool_name": "csv_summary_report",
                "called_at": "2026-05-19T04:46:14Z",
                "scrubber_id": "noop",
            },
        },
        "adr_citations": [
            "ADR 0001 (audit log as backbone)",
            "ADR 0002 (subject_id scoping)",
            "ADR 0003 (PHI scrubber seam)",
            "ADR 0039 (audit log is LLM-queryable under column allowlist)",
        ],
        "next_step": (
            "Try `audit_query` with since='1h' to see your own "
            "recent calls. Or ask Claude to walk through section 3 "
            "for the three-tier consent + cost model."
        ),
    },
    3: {
        "section": 3,
        "title": "Three-tier access model — same question, three resolutions",
        "narrative": (
            "Tailor's three-tier model is data minimisation made "
            "executable. Tier 1 returns scalars (no gate, hundreds of "
            "tokens). Tier 2 returns downsampled streams for "
            "visualisation (consent gate, thousands of tokens). "
            "Tier 3 returns per-timestamp data (consent + cost gates, "
            "tens of thousands of tokens). On the same question — "
            "`subject S004's force decline over time` — the three "
            "tiers cost ~310 / ~6,750 / ~50,000 tokens respectively. "
            "Most analytical questions resolve at Tier 1."
        ),
        "worked_example": {
            "tier_1": {
                "tool": "csv_force_decline",
                "params": {"subject_id": "S004"},
                "tokens": 310,
                "gates": [],
                "result_shape": {
                    "peak_N": 229.0,
                    "decline_pct": 76.1,
                    "time_to_50pct_drop_s": 42.7,
                },
            },
            "tier_2": {
                "tool": "csv_downsampled",
                "params": {"subject_id": "S004", "interval_s": 5},
                "tokens": 6750,
                "gates": ["consent"],
            },
            "tier_3": {
                "tool": "csv_raw_stream",
                "params": {"subject_id": "S004"},
                "tokens": 50000,
                "tier3_pre_execution_estimate": 24000,
                "gates": ["consent", "cost"],
            },
            "cost_threshold_default": 35000,
            "cost_threshold_demo_default": 15000,
        },
        "adr_citations": [
            "ADR 0005 (cost pre-estimation)",
            "ADR 0019 (cost gate tier binding)",
            "ADR 0029 (token reduction as analytical quality)",
        ],
        "next_step": (
            "Approve consent for csv_dir and try Tier 2; or try Tier "
            "3 to see the cost gate fire with an LLMInstruction "
            "envelope. Section 4 covers the vault layer."
        ),
    },
    4: {
        "section": 4,
        "title": "Vault layer — cross-session analytical memory",
        "narrative": (
            "Observations made in one session disappear when the "
            "chat ends. The vault layer is Tailor's response — a "
            "structured collection of themes (persistent questions), "
            "moments (aha observations), evidence (data grounding a "
            "theme), and failure modes. Notes are markdown files in "
            "an Obsidian-compatible vault; SQLite indexes them for "
            "fast LLM queries. Capturing a moment scoped to "
            "subject_id='S004' creates a durable note an analyst "
            "(or Claude in a future session) can find by filtering "
            "the index."
        ),
        "worked_example": {
            "tool": "vault_capture_moment",
            "params": {
                "subject_id": "S004",
                "title": "S004 force decline pattern",
                "body": "S004 shows 76% decline over 60 s...",
            },
            "result_shape": {
                "slug": "s004-force-decline-pattern",
                "kind": "moment",
                "subject_id": "S004",
                "vault_path": "moments/s004-force-decline-pattern.md",
                "tokens": 180,
            },
        },
        "adr_citations": [
            "ADR 0006 (vault overhaul v6)",
            "ADR 0007 (rendering-layers policy)",
            "ADR 0009 (vault subject keying)",
            "ADR 0038 (vault layer is data-source-agnostic)",
        ],
        "next_step": (
            "Try `vault_capture_moment` to add a note for one of "
            "your subjects, then `vault_list_moments` to see it. "
            "Section 5 covers the local-LLM guardian."
        ),
    },
    5: {
        "section": 5,
        "title": "Local-LLM guardian — numerical claims from deterministic processing",
        "narrative": (
            "Per ADR 0022, the local-LLM guardian composes prose "
            "over deterministic processing output. The hard rule: "
            "numbers come from `processing.py`, prose comes from a "
            "local model on the analyst's machine, enforced by the "
            "`OracleResponse` schema. The default backend is "
            "`NullBackend` (no-op — existing deployments unchanged); "
            "opt-in to a real local model via the `local_llm` block "
            "in `user_config.json`. With `NullBackend`, the oracle "
            "still surfaces `related_substrate` from the vault index "
            "(per ADR 0023's cooperation-loop substrate scan), so "
            "even the no-op path is useful."
        ),
        "worked_example": {
            "tool": "ask_local_oracle",
            "params": {
                "intent": "summarize_subject_force_pattern",
                "resolved_context": {
                    "subject_id": "S004",
                    "peak_N": 229.0,
                    "decline_pct": 76.1,
                },
            },
            "result_shape": {
                "claims": [
                    {
                        "type": "numeric",
                        "field": "peak_N",
                        "value": 229.0,
                    },
                ],
                "narrative": (
                    "Composed by local LLM when backend != null; "
                    "empty under NullBackend."
                ),
                "related_substrate": [
                    {
                        "kind": "moment",
                        "slug": "s004-force-decline-pattern",
                        "subject_id": "S004",
                    },
                ],
                "next_best_calls": [],
                "unresolved_intent": [],
            },
        },
        "adr_citations": [
            "ADR 0022 (local-LLM guardian)",
            "ADR 0023 (local-LLM cooperation loop)",
        ],
        "next_step": (
            "If Ollama is available locally, configure the "
            "`local_llm` block in user_config.json with backend='ollama'. "
            "Otherwise the NullBackend still surfaces vault substrate "
            "via `ask_local_oracle`."
        ),
    },
}


class WalkthroughLayer:
    """Framework-tier conducted-tour surface (single tool, 5 sections)."""

    def __init__(self) -> None:
        self._router = None  # Set by RouterMCP.register_walkthrough_layer()
        log.info("WalkthroughLayer initialized (5 sections)")

    @property
    def tool_definitions(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                "tailor_walkthrough_section",
                1,
                _WALKTHROUGH_DESCRIPTION,
                {
                    "section": {
                        "type": "integer",
                        "description": (
                            "Required. One of 1..5. (1) Tier-1 "
                            "cohort thesis; (2) router pipeline + "
                            "audit log; (3) three-tier consent + "
                            "cost model; (4) vault layer + "
                            "cross-session memory; (5) local-LLM "
                            "guardian + deterministic processing."
                        ),
                        "required": True,
                    },
                },
            ),
        ]

    @property
    def param_schemas(self) -> dict[str, dict[str, ValidationSchema]]:
        return {
            "tailor_walkthrough_section": {
                "section": ValidationSchema(
                    type=int,
                    required=True,
                    min=1,
                    max=5,
                ),
            },
        }

    async def execute(self, tool_name: str, params: dict) -> dict:
        if tool_name != "tailor_walkthrough_section":
            return {"error": f"Unknown walkthrough tool: {tool_name}"}
        section = int(params["section"])
        payload = _SECTION_PAYLOADS.get(section)
        if payload is None:
            return {
                "error": f"section must be 1..5, got {section}",
            }
        # Defensive copy so the LLM can't mutate the module-level
        # constants in a future framework-tier post-execute hook.
        return dict(payload)
