"""
Vault Layer — Framework-level Cross-Session Reorientation
=========================================================
The vault layer is NOT a ChildMCP.  It's the reorientation tier:
durable analytical memory that persists across sessions via an
Obsidian vault (markdown + frontmatter, indexed in SQLite).

Architectural distinction from biosensor children:
    Biosensor tier (RunningChild, CGMChild, ...):
        Ephemeral — raw data ingestion, cached locally, rebuildable
        by re-syncing from the upstream source.
    Reorientation tier (VaultLayer):
        Durable — analytical knowledge, canonical record.
        Markdown files are the source of truth; vault.db is a
        query-optimization index.

Vault tools skip consent/cost/circuit gates — they read local
metadata, not biometric data.  Param validation and audit still apply.

Tools:
    vault_get_fitness_summary   Primary orientation tool for a new session.
    vault_list_notes            Browse notes with optional filters.
    vault_read_note             Read full body of a specific note.
    vault_search_notes          Full-text search across note bodies.
    vault_list_anomalies        Runs with anomaly_count > 0.
    vault_annotate_run          Write analytical insights back to a note.
    vault_backfill              Generate notes for activities missing one
                                (LLM-driven, server-orchestrated via
                                configurable backfill_config).

Reasoning-persistence tools (narrative continuity across sessions):
    vault_list_themes           Browse persistent hypotheses (compact rows).
    vault_read_theme            Full body of a theme + resolved wikilinks.
    vault_upsert_theme          Create or update a theme; evidence appends.
    vault_correct_evidence      Mark a specific evidence block superseded;
                                optionally propagates a callout to every
                                note that wikilinks the theme.
    vault_log_failure_mode      Create or update a failure-mode note (the
                                'how we got it wrong' counterpart to themes).
    vault_list_failure_modes    Compact listing of failure-mode notes.
    vault_list_moments          Browse aha-moment notes.
    vault_capture_moment        Write a single aha-moment note.
    vault_capture_session       Session-boundary bundle: summary moment +
                                N theme updates in one audited call.
    vault_refresh_dashboards    Materialise dashboards/* as plain-markdown
                                snapshots (ADR 0007 dual-output).
    vault_rescan                Full filesystem sweep — pick up user edits.
    vault_traverse_links        Neighbourhood of wikilinks (no bodies).
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

from ..interfaces import (
    ENTITY_ID_PARAM_DOC,
    ENTITY_ID_SCHEMA,
    ToolDefinition,
    ValidationSchema,
)
from .rescan import rescan_vault, revalidate_file
from .storage import VaultStorage
from .writer import VaultWriter, _is_relative_to

log = logging.getLogger("tailor.vault")

# Max chars for vault_annotate_run notes
_MAX_NOTES_CHARS = 2000

# Framework-tier vault note kinds — owned by VaultLayer itself.
# Child-specific kinds (e.g. run_report from RunningChild) are
# contributed via each child's ``vault_note_kinds`` property and
# unioned at ``register_vault_layer()`` time. See ADR 0038 §
# Amendment 2026-05-19.
_FRAMEWORK_KIND_BASE: tuple[str, ...] = (
    "theme", "moment", "failure_mode", "dashboard", "snapshot",
)

# Framework-tier kind → storage domain mapping. Child-contributed
# kinds are added to ``VaultLayer._kind_to_domain_map`` at
# registration time. ``failure_mode``, ``dashboard``, and
# ``snapshot`` intentionally absent — they span domains and resolve
# to None ("all domains") in ``VaultLayer._domain_for_kind``.
_FRAMEWORK_KIND_TO_DOMAIN: dict[str, str] = {
    "theme": "vault",
    "moment": "vault",
}

# Max nodes returned by vault_traverse_links (prevents runaway traversal)
_TRAVERSE_MAX_NODES = 40


class VaultLayer:
    """
    Framework-level reorientation layer backed by an Obsidian vault.

    Registered directly on RouterMCP via ``register_vault_layer()``, not
    as a ChildMCP.  The router skips consent, cost, and circuit breaker
    gates for vault tools — only param validation and audit apply.

    Args:
        vault_path:       Absolute path to the vault root.
        vault_writer:     Shared VaultWriter instance (owns storage + rendering).
        backfill_config:  Maps generic roles to sibling tool names,
                          decoupling backfill from hardcoded domain knowledge.
                          Example (generic shape — wiring site supplies
                          actual tool names per registered child):
                              {"list_tool":   "<child>_list",
                               "report_tool": "<child>_report",
                               "sync_tool":   "<child>_sync"}
                          When None, vault_backfill returns a configuration error.
                          ``sync_tool`` is optional; the vault layer's
                          remediation prose falls back to generic
                          "your biosensor sync tool" framing when
                          ``sync_tool`` is absent.
    """

    def __init__(
        self,
        vault_path: Path,
        vault_writer: VaultWriter,
        backfill_config: dict | None = None,
    ):
        self._vault_path = vault_path
        self._writer = vault_writer
        self._storage: VaultStorage = vault_writer._storage
        self._backfill_config = backfill_config or {}
        self._router = None  # Set by RouterMCP.register_vault_layer()
        # Kind metadata: starts framework-tier-only; ``_compute_kind_metadata()``
        # extends with child-contributed kinds at registration time. See
        # ADR 0038 § Amendment 2026-05-19.
        self._allowed_kinds: tuple[str, ...] = _FRAMEWORK_KIND_BASE
        self._kind_to_domain_map: dict[str, str] = dict(_FRAMEWORK_KIND_TO_DOMAIN)
        # Per-instance one-shot deprecation flag for vault_get_fitness_summary
        # (sub-item 7 of ADR 0038 § Amendment 2026-05-19). Declared here
        # explicitly rather than via setattr to close the
        # reproducibility-provenance-auditor BORDER NOTE on instance-state
        # drift; does not feed any analytical numeric result.
        self._fitness_summary_deprecation_logged: bool = False

    def _compute_kind_metadata(self) -> None:
        """Extend allowed kinds + kind→domain map from registered children.

        Called by ``RouterMCP.register_vault_layer()`` immediately after
        ``self._router`` is wired. Iterates ``self._router._children``,
        reads each child's ``vault_note_kinds``, and extends the
        framework-tier base. See ADR 0038 § Amendment 2026-05-19 for
        the rationale (child-owned contract surface, not wiring-site
        parameterisation).
        """
        if self._router is None:
            return
        child_kinds: list[str] = []
        for child in self._router._children.values():
            kinds = getattr(child, "vault_note_kinds", ())
            for kind in kinds:
                if kind in self._kind_to_domain_map:
                    continue  # Framework-tier or earlier-registered child wins.
                child_kinds.append(kind)
                self._kind_to_domain_map[kind] = child.domain
        # Preserve framework base ordering, then append child kinds.
        self._allowed_kinds = (*_FRAMEWORK_KIND_BASE, *child_kinds)

    def _domain_for_kind(self, kind: str | None) -> str | None:
        """Map a note kind to its storage domain via the instance map.

        Framework-tier kinds resolve via ``_FRAMEWORK_KIND_TO_DOMAIN``;
        child-contributed kinds resolve via the map populated at
        ``_compute_kind_metadata()`` time. Unknown kinds return None
        ("all domains") — same fallthrough as the v6.0-era module helper.
        """
        if kind is None:
            return None
        return self._kind_to_domain_map.get(kind)

    @property
    def tool_definitions(self) -> list[ToolDefinition]:
        defs = [
            ToolDefinition(
                "vault_get_fitness_summary", 1,
                "DEPRECATED in v7.6.0 -- prefer ``vault_get_snapshot`` for fast "
                "session orientation. This v6.0-era tool remains callable but "
                "will be removed in a future v7.7.x+ release when the cue-card-"
                "rehearsal-auditor reports zero references to it across any "
                "deployed cue card AND no third-party child declares "
                "dependencies on it (see ADR 0038 § Amendment 2026-05-19, "
                "sub-item 7). Behaviour unchanged: surfaces open themes and "
                "recent moments so you can resume prior analytical threads, "
                "plus a weekly aggregate table for any registered biosensor "
                "child (skipped on deployments without one). Call "
                "vault_get_snapshot first when a snapshot.md exists; this is "
                "the fallback. ~600–800 tokens.",
                {
                    "weeks_back": {
                        "type": "integer",
                        "description": "How many weeks of history to include (default 8, max 52)",
                        "required": False,
                    },
                },
            ),
            ToolDefinition(
                "vault_list_notes", 1,
                "Browse vault notes with optional filters. Shows filename, date, "
                "kind, and whether insight notes exist. Covers framework-tier "
                "kinds (themes, moments, failure modes, dashboards, snapshots) "
                "and any per-activity report kinds contributed by registered "
                "biosensor children — call ``vault_list_notes`` with no kind "
                "filter to see everything in the vault.",
                {
                    "kind": {
                        "type": "string",
                        "description": (
                            "Filter by note kind. Framework-tier kinds: "
                            "theme | moment | failure_mode | dashboard | "
                            "snapshot. Additional kinds contributed by "
                            "registered biosensor children (e.g. run_report, "
                            "trend_report, compare_runs from the running "
                            "child) are also accepted; the full allowed set "
                            "is validated at param-check time."
                        ),
                        "required": False,
                    },
                    "note_type": {
                        "type": "string",
                        "description": "Alias for 'kind' (legacy). Same allowed values.",
                        "required": False,
                    },
                    "date_from": {
                        "type": "string",
                        "description": "Earliest date (YYYY-MM-DD)",
                        "required": False,
                    },
                    "date_to": {
                        "type": "string",
                        "description": "Latest date (YYYY-MM-DD)",
                        "required": False,
                    },
                    "has_insight_notes": {
                        "type": "boolean",
                        "description": "If true, only return notes with insight annotations",
                        "required": False,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default 20, max 100)",
                        "required": False,
                    },
                },
            ),
            ToolDefinition(
                "vault_read_note", 1,
                "Read the full body of a vault note, including any insight annotations "
                "from prior sessions.",
                {
                    "filename": {
                        "type": "string",
                        "description": "Relative filename (e.g. 'running/2025-04-10-activity-12345678.md')",
                        "required": True,
                    },
                },
            ),
            ToolDefinition(
                "vault_search_notes", 1,
                "Full-text search across vault note bodies. "
                "Useful for finding runs that match a keyword or analytical observation.",
                {
                    "query": {
                        "type": "string",
                        "description": "Search term",
                        "required": True,
                    },
                    "kind": {
                        "type": "string",
                        "description": (
                            "Filter by note kind. Framework-tier kinds: "
                            "theme | moment | failure_mode | dashboard | "
                            "snapshot. Additional kinds contributed by "
                            "registered biosensor children (e.g. run_report, "
                            "trend_report, compare_runs from the running "
                            "child) are also accepted; the full allowed set "
                            "is validated at param-check time."
                        ),
                        "required": False,
                    },
                    "note_type": {
                        "type": "string",
                        "description": "Alias for 'kind' (legacy). Same allowed values.",
                        "required": False,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default 10, max 50)",
                        "required": False,
                    },
                    "entity_id": ENTITY_ID_PARAM_DOC,
                },
            ),
            ToolDefinition(
                "vault_list_anomalies", 1,
                "Return runs with anomaly_count > 0, newest first. "
                "Optionally filter to a specific anomaly type (e.g. 'hr_spike').",
                {
                    "anomaly_type": {
                        "type": "string",
                        "description": "Specific anomaly type to filter (optional)",
                        "required": False,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default 20)",
                        "required": False,
                    },
                },
            ),
            ToolDefinition(
                "vault_annotate_run", 1,
                "Write analytical insights back to a run note so they're available "
                "in future sessions. Max 2000 characters. "
                "Use this to persist observations that would otherwise be lost when the "
                "conversation ends.",
                {
                    "filename": {
                        "type": "string",
                        "description": "Relative filename of the note to annotate",
                        "required": True,
                    },
                    "notes": {
                        "type": "string",
                        "description": "Analytical observations and insights (max 2000 chars)",
                        "required": True,
                    },
                },
            ),
            ToolDefinition(
                "vault_backfill", 1,
                "Generate vault notes for activities cached locally that don't "
                "yet have a note. LLM-driven, server-orchestrated — the LLM decides "
                "when to run it; the server iterates activities and writes notes.",
                {
                    "limit": {
                        "type": "integer",
                        "description": "Max activities to process (default 50, max 200)",
                        "required": False,
                    },
                },
            ),

            # ── Reasoning-persistence tools ──

            ToolDefinition(
                "vault_list_themes", 1,
                "List persistent hypotheses (themes) tracked across runs. "
                "Returns compact rows: slug, status, last_updated, linked_run "
                "count, confidence, and a one-line excerpt — no bodies. "
                "~300 tokens for 20 themes.",
                {
                    "status": {
                        "type": "string",
                        "description": "Filter: open | resolved | rejected",
                        "required": False,
                    },
                    "tag": {
                        "type": "string",
                        "description": "Only themes tagged with this tag",
                        "required": False,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default 20, max 100)",
                        "required": False,
                    },
                },
            ),
            ToolDefinition(
                "vault_read_theme", 1,
                "Read the full body of a theme note, including hypothesis, "
                "evidence log, and resolution. Picks up user edits made in "
                "Obsidian via mtime revalidation.",
                {
                    "slug": {
                        "type": "string",
                        "description": "Theme slug (e.g. 'dehydration-drift')",
                        "required": True,
                    },
                },
            ),
            ToolDefinition(
                "vault_upsert_theme", 1,
                "Create or update a theme note. If the theme exists: status, "
                "confidence, linked_runs, and tags merge; 'evidence' APPENDS a "
                "new timestamped block (existing evidence is never overwritten). "
                "If new: a fresh theme note is written.",
                {
                    "slug": {
                        "type": "string",
                        "description": "Theme slug (lowercase, dashes)",
                        "required": True,
                    },
                    "hypothesis": {
                        "type": "string",
                        "description": "Short prose statement of the hypothesis",
                        "required": False,
                    },
                    "evidence": {
                        "type": "string",
                        "description": (
                            "New evidence block to APPEND. Max 2000 chars. "
                            "Do not include prior evidence — only the new observation."
                        ),
                        "required": False,
                    },
                    "status": {
                        "type": "string",
                        "description": "open | resolved | rejected",
                        "required": False,
                    },
                    "confidence": {
                        "type": "string",
                        "description": "low | medium | high",
                        "required": False,
                    },
                    "linked_runs": {
                        "type": "array",
                        "description": "List of activity_ids this theme relates to",
                        "required": False,
                    },
                    "linked_themes": {
                        "type": "array",
                        "description": "List of other theme slugs related to this one",
                        "required": False,
                    },
                    "tags": {
                        "type": "array",
                        "description": "Additional tags (merged with existing)",
                        "required": False,
                    },
                    "title": {
                        "type": "string",
                        "description": "Human title (defaults to titlecased slug)",
                        "required": False,
                    },
                    "resolution": {
                        "type": "string",
                        "description": (
                            "Resolution prose, used when status != open."
                        ),
                        "required": False,
                    },
                    "thinking": {
                        "type": "string",
                        "description": (
                            "Partial-progress note (max 2000 chars) appended as "
                            "a '### Thinking — TIMESTAMP' block. Use when a "
                            "session worked on the theme without resolving it."
                        ),
                        "required": False,
                    },
                    "evidence_source_tier": {
                        "type": "integer",
                        "description": (
                            "Provenance: data tier (1-3) the evidence was "
                            "derived from."
                        ),
                        "required": False,
                    },
                    "evidence_source_tool": {
                        "type": "string",
                        "description": (
                            "Provenance: tool that produced the evidence (e.g. "
                            "'force_cohort_summary', 'csv_summary_report', "
                            "'strava_run_report')."
                        ),
                        "required": False,
                    },
                    "evidence_source_domain": {
                        "type": "string",
                        "description": (
                            "Provenance: child domain (e.g. 'force_csv', "
                            "'csv_dir', 'redcap_file', 'running')."
                        ),
                        "required": False,
                    },
                    "evidence_verification": {
                        "type": "string",
                        "description": (
                            "Provenance: observed | computed | inferred | "
                            "unverified."
                        ),
                        "required": False,
                    },
                },
            ),
            ToolDefinition(
                "vault_list_moments", 1,
                "List aha-moment notes (compact rows). ~300 tokens for 20 moments.",
                {
                    "date_from": {
                        "type": "string",
                        "description": "Filter to moments dated on or after this YYYY-MM-DD.",
                        "required": False,
                    },
                    "date_to": {
                        "type": "string",
                        "description": "Filter to moments dated on or before this YYYY-MM-DD.",
                        "required": False,
                    },
                    "theme": {
                        "type": "string",
                        "description": "Only moments linked to this theme slug",
                        "required": False,
                    },
                    "tag": {
                        "type": "string",
                        "description": "Filter to moments carrying this tag in frontmatter.",
                        "required": False,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results to return (default 20).",
                        "required": False,
                    },
                },
            ),
            ToolDefinition(
                "vault_capture_moment", 1,
                "Write a single aha-moment note. Use for one-shot observations "
                "that don't fit an existing theme — insights, surprising patterns, "
                "questions worth remembering.",
                {
                    "title": {
                        "type": "string",
                        "description": "Short human title (required)",
                        "required": True,
                    },
                    "body": {
                        "type": "string",
                        "description": "1–3 paragraphs of prose (required)",
                        "required": True,
                    },
                    "linked_runs": {
                        "type": "array",
                        "description": "Activity_ids the moment references",
                        "required": False,
                    },
                    "linked_themes": {
                        "type": "array",
                        "description": "Theme slugs the moment supports or contradicts",
                        "required": False,
                    },
                    "tags": {
                        "type": "array",
                        "description": "Frontmatter tags for the moment (strings).",
                        "required": False,
                    },
                    "date": {
                        "type": "string",
                        "description": "YYYY-MM-DD (defaults to today)",
                        "required": False,
                    },
                },
            ),
            ToolDefinition(
                "vault_capture_session", 1,
                "Call this tool before the session ends when substantive analytical "
                "discussion occurred. Capture key aha-moments and update any themes "
                "with new evidence. This is how narrative persists across sessions — "
                "unwritten reasoning is lost when the conversation closes. Bundles "
                "one summary moment plus N theme updates into a single audited call.",
                {
                    "summary": {
                        "type": "object",
                        "description": (
                            "Summary moment to record, with fields: title, body, "
                            "linked_runs?, linked_themes?, tags?, date?. "
                            "Required — the session's top-line takeaway."
                        ),
                        "required": True,
                    },
                    "update_themes": {
                        "type": "array",
                        "description": (
                            "Optional list of theme updates. Each item takes the same "
                            "fields as vault_upsert_theme."
                        ),
                        "required": False,
                    },
                    "new_moments": {
                        "type": "array",
                        "description": (
                            "Optional list of additional moments (beyond the summary). "
                            "Each item takes the same fields as vault_capture_moment."
                        ),
                        "required": False,
                    },
                    "divergence": {
                        "type": "string",
                        "description": (
                            "Optional prose (max 1000 chars) recording what the "
                            "session's analytical goal was versus what actually "
                            "happened. Rendered as a '## Divergence' section "
                            "on the summary moment and stored in frontmatter."
                        ),
                        "required": False,
                    },
                },
            ),
            ToolDefinition(
                "vault_health_check", 1,
                "Diagnostic sweep of vault maintenance state: stale themes, "
                "orphaned moments, themes with no evidence, inbox depth, and "
                "total counts. Use to decide what to tidy up at session end.",
                {
                    "stale_threshold_days": {
                        "type": "integer",
                        "description": "Days since last_updated to flag a theme as stale (default 30).",
                        "required": False,
                    },
                },
            ),
            ToolDefinition(
                "vault_correct_evidence", 1,
                "Mark a specific evidence block as superseded. Inserts a "
                "'[CORRECTED <ts>]' blockquote after the targeted evidence "
                "block's header and appends a new evidence block tagged "
                "[correction]. The original block is preserved (append-only "
                "invariant).",
                {
                    "theme_slug": {
                        "type": "string",
                        "description": "Slug of the theme containing the evidence.",
                        "required": True,
                    },
                    "evidence_timestamp": {
                        "type": "string",
                        "description": (
                            "ISO timestamp from the '### Evidence — <ts>' header "
                            "of the block being corrected."
                        ),
                        "required": True,
                    },
                    "correction": {
                        "type": "string",
                        "description": "Explanation + replacement text (max 2000 chars).",
                        "required": True,
                    },
                    "corrected_by": {
                        "type": "string",
                        "description": "Tool or session that discovered the error.",
                        "required": False,
                    },
                    "propagate": {
                        "type": "boolean",
                        "description": (
                            "When true, append a '[!warning]' callout to "
                            "every note that wikilinks to this theme so "
                            "downstream readers see the supersession in "
                            "context. Append-only and idempotent."
                        ),
                        "required": False,
                    },
                },
            ),
            ToolDefinition(
                "vault_log_failure_mode", 1,
                "Create or update a failure-mode note — a durable record "
                "of an analytical pattern that has gone wrong before, with "
                "symptom / diagnosis / mitigation and an append-only "
                "evidence log. New evidence APPENDS (existing entries are "
                "never overwritten). Mirrors the theme lifecycle but is "
                "scoped to 'how we got it wrong'.",
                {
                    "slug": {
                        "type": "string",
                        "description": "Slug (lowercase, dashes).",
                        "required": True,
                    },
                    "title": {
                        "type": "string",
                        "description": "Short human title (defaults to titlecased slug).",
                        "required": False,
                    },
                    "symptom": {
                        "type": "string",
                        "description": (
                            "1–3 sentences — what the failure looks like "
                            "from the analyst's seat. Required when creating."
                        ),
                        "required": False,
                    },
                    "diagnosis": {
                        "type": "string",
                        "description": (
                            "Why it happened (what went wrong upstream). "
                            "Required when creating."
                        ),
                        "required": False,
                    },
                    "mitigation": {
                        "type": "string",
                        "description": "How to avoid recurrence. Required when creating.",
                        "required": False,
                    },
                    "status": {
                        "type": "string",
                        "description": "active | mitigated | superseded (default active).",
                        "required": False,
                    },
                    "evidence": {
                        "type": "string",
                        "description": (
                            "New evidence block to APPEND (max 2000 chars). "
                            "On create, becomes the first evidence entry."
                        ),
                        "required": False,
                    },
                    "related_themes": {
                        "type": "array",
                        "description": "Theme slugs implicated by this failure.",
                        "required": False,
                    },
                    "related_subjects": {
                        "type": "array",
                        "description": "Subject_ids it has affected.",
                        "required": False,
                    },
                    "tags": {
                        "type": "array",
                        "description": "Additional tags (merged with existing).",
                        "required": False,
                    },
                    "evidence_source_tier": {
                        "type": "integer",
                        "description": "Provenance: data tier (1-3) the evidence came from.",
                        "required": False,
                    },
                    "evidence_source_tool": {
                        "type": "string",
                        "description": "Provenance: tool that produced the evidence.",
                        "required": False,
                    },
                    "evidence_source_domain": {
                        "type": "string",
                        "description": "Provenance: child domain.",
                        "required": False,
                    },
                    "evidence_verification": {
                        "type": "string",
                        "description": "observed | computed | inferred | unverified.",
                        "required": False,
                    },
                },
            ),
            ToolDefinition(
                "vault_list_failure_modes", 1,
                "List failure-mode notes (compact rows). Returns slug, "
                "status, opened, last_updated, related_theme_count, and "
                "title — no bodies. ~300 tokens for 20 entries.",
                {
                    "status": {
                        "type": "string",
                        "description": "Filter: active | mitigated | superseded.",
                        "required": False,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default 20, max 100).",
                        "required": False,
                    },
                },
            ),
            ToolDefinition(
                "vault_inbox_add", 1,
                "Append a low-friction capture to 'inbox.md' in the vault "
                "root. Use for half-formed observations that aren't yet a "
                "moment or theme evidence. Drain later with vault_inbox_drain.",
                {
                    "text": {
                        "type": "string",
                        "description": "Free-form observation (max 2000 chars).",
                        "required": True,
                    },
                    "tags": {
                        "type": "array",
                        "description": "Optional hashtags to annotate the item.",
                        "required": False,
                    },
                },
            ),
            ToolDefinition(
                "vault_inbox_list", 1,
                "Return parsed items from 'inbox.md' (timestamp + text + tags). "
                "Use to review uncurated captures before draining.",
                {
                    "limit": {
                        "type": "integer",
                        "description": "Max items returned (default 20).",
                        "required": False,
                    },
                },
            ),
            ToolDefinition(
                "vault_inbox_drain", 1,
                "Process inbox items in bulk. Each item specifies an index "
                "and an action (moment | evidence | discard). Successful "
                "items are removed from 'inbox.md'.",
                {
                    "items": {
                        "type": "array",
                        "description": (
                            "List of {index, action, ...action-specific-fields}. "
                            "action=moment requires title/body; action=evidence "
                            "requires theme_slug."
                        ),
                        "required": True,
                    },
                },
            ),
            ToolDefinition(
                "vault_generate_snapshot", 1,
                "Regenerate the compressed vault state note at 'snapshot.md' — "
                "open themes, recent moments, weekly run aggregates, vault "
                "health, and any warnings. Call at the end of substantive "
                "analytical sessions so the next session has a fast orientation.",
                {
                    "written_by": {
                        "type": "string",
                        "description": "Session identifier recorded in frontmatter.",
                        "required": False,
                    },
                },
            ),
            ToolDefinition(
                "vault_get_snapshot", 1,
                "Read 'snapshot.md' from the vault root. This is the new "
                "'call first' tool — one file, compressed, versus the wider "
                "sweep of vault_get_fitness_summary. Falls back to the "
                "fitness-summary shape when no snapshot exists.",
                {},
            ),
            ToolDefinition(
                "vault_rescan", 1,
                "Walk the vault on disk and reconcile the SQLite index: pick up "
                "user edits made in Obsidian, drop notes that were deleted. "
                "Returns counts for added/modified/deleted/skipped. The router "
                "also revalidates each note lazily on read, so explicit rescan is "
                "only needed after large bulk edits.",
                {},
            ),
            ToolDefinition(
                "vault_refresh_dashboards", 1,
                "Materialise the standard dashboards under 'dashboards/' as "
                "plain-markdown snapshot tables (ADR 0007 dual-output). "
                "Refreshes 'open-themes', 'active-failure-modes', and "
                "'recent-moments' from the SQLite index. Each dashboard is "
                "always readable without the Dataview plugin; an optional "
                "'```dataview' block above the snapshot renders for analysts "
                "who do have the plugin.",
                {
                    "with_dataview_blocks": {
                        "type": "boolean",
                        "description": (
                            "When true, include the Dataview live-query "
                            "block above each snapshot table (default true)."
                        ),
                        "required": False,
                    },
                },
            ),
            ToolDefinition(
                "vault_traverse_links", 1,
                "Return the wikilink neighbourhood of a note: titles and frontmatter "
                "of linked notes, no bodies. Use this to see which themes a run "
                "supports, which runs a theme references, etc. ~400 tokens per depth=1.",
                {
                    "filename": {
                        "type": "string",
                        "description": "Starting note (relative vault path)",
                        "required": True,
                    },
                    "depth": {
                        "type": "integer",
                        "description": "Traversal depth (1–3, default 1)",
                        "required": False,
                    },
                    "direction": {
                        "type": "string",
                        "description": "out | in | both (default: both)",
                        "required": False,
                    },
                },
            ),
        ]
        # v6.2 — surface optional entity_id on every vault tool so LLM
        # clients discover it via list_tools. ADR 0002 (audit-scoping)
        # + ADR 0009 (vault subject-keying). setdefault is idempotent if
        # any tool ever declares its own entity_id schema.
        for td in defs:
            td.params.setdefault("entity_id", dict(ENTITY_ID_PARAM_DOC))
        return defs

    @property
    def param_schemas(self) -> dict[str, dict[str, ValidationSchema]]:
        schemas = {
            "vault_get_fitness_summary": {
                "weeks_back": ValidationSchema(type=int, min=1, max=52, default=8),
            },
            "vault_list_notes": {
                "kind": ValidationSchema(
                    type=str, allowed_values=list(self._allowed_kinds),
                ),
                "note_type": ValidationSchema(
                    type=str, allowed_values=list(self._allowed_kinds),
                ),
                "date_from": ValidationSchema(type=str, pattern=r"^\d{4}-\d{2}-\d{2}$"),
                "date_to": ValidationSchema(type=str, pattern=r"^\d{4}-\d{2}-\d{2}$"),
                "has_insight_notes": ValidationSchema(type=bool),
                "limit": ValidationSchema(type=int, min=1, max=100, default=20),
            },
            "vault_read_note": {
                "filename": ValidationSchema(type=str, required=True),
            },
            "vault_search_notes": {
                "query": ValidationSchema(type=str, required=True),
                "kind": ValidationSchema(
                    type=str, allowed_values=list(self._allowed_kinds),
                ),
                "note_type": ValidationSchema(
                    type=str, allowed_values=list(self._allowed_kinds),
                ),
                "limit": ValidationSchema(type=int, min=1, max=50, default=10),
                # entity_id is intentionally not listed here. The
                # setdefault loop in __init__ (search for "for tn,
                # schema in self.param_schemas.items()") injects
                # ENTITY_ID_SCHEMA into every vault tool's schema.
                # If that loop is ever refactored, this tool's
                # entity_id surface goes silent — add it explicitly
                # before touching the loop. Other vault tools follow
                # the same pattern; this comment exists because
                # vault_search_notes was the v6.4.1 reproducibility-
                # auditor BORDER NOTE.
            },
            "vault_list_anomalies": {
                "anomaly_type": ValidationSchema(type=str),
                "limit": ValidationSchema(type=int, min=1, max=100, default=20),
            },
            "vault_annotate_run": {
                "filename": ValidationSchema(type=str, required=True),
                "notes": ValidationSchema(type=str, required=True),
            },
            "vault_backfill": {
                "limit": ValidationSchema(type=int, min=1, max=200, default=50),
            },
            "vault_list_themes": {
                "status": ValidationSchema(
                    type=str, allowed_values=["open", "resolved", "rejected"],
                ),
                "tag": ValidationSchema(type=str),
                "limit": ValidationSchema(type=int, min=1, max=100, default=20),
            },
            "vault_read_theme": {
                "slug": ValidationSchema(
                    type=str, required=True, pattern=r"^[a-z0-9][a-z0-9\-]{0,63}$",
                ),
            },
            "vault_upsert_theme": {
                "slug": ValidationSchema(
                    type=str, required=True, pattern=r"^[a-z0-9][a-z0-9\-]{0,63}$",
                ),
                "hypothesis": ValidationSchema(type=str, max_len=2000),
                "evidence": ValidationSchema(type=str, max_len=2000),
                "status": ValidationSchema(
                    type=str,
                    allowed_values=["open", "resolved", "rejected", "reframed"],
                ),
                "confidence": ValidationSchema(
                    type=str, allowed_values=["low", "medium", "high"],
                ),
                "linked_runs": ValidationSchema(type=list),
                "linked_themes": ValidationSchema(type=list),
                "tags": ValidationSchema(type=list),
                "title": ValidationSchema(type=str, max_len=200),
                "resolution": ValidationSchema(type=str, max_len=2000),
                "thinking": ValidationSchema(type=str, max_len=2000),
                "evidence_source_tier": ValidationSchema(type=int, min=1, max=3),
                "evidence_source_tool": ValidationSchema(type=str, max_len=200),
                "evidence_source_domain": ValidationSchema(type=str, max_len=200),
                "evidence_verification": ValidationSchema(
                    type=str,
                    allowed_values=["observed", "computed", "inferred", "unverified"],
                ),
            },
            "vault_list_moments": {
                "date_from": ValidationSchema(type=str, pattern=r"^\d{4}-\d{2}-\d{2}$"),
                "date_to": ValidationSchema(type=str, pattern=r"^\d{4}-\d{2}-\d{2}$"),
                "theme": ValidationSchema(type=str),
                "tag": ValidationSchema(type=str),
                "limit": ValidationSchema(type=int, min=1, max=100, default=20),
            },
            "vault_capture_moment": {
                "title": ValidationSchema(type=str, required=True, max_len=200),
                "body": ValidationSchema(type=str, required=True, max_len=4000),
                "linked_runs": ValidationSchema(type=list),
                "linked_themes": ValidationSchema(type=list),
                "tags": ValidationSchema(type=list),
                "date": ValidationSchema(type=str, pattern=r"^\d{4}-\d{2}-\d{2}$"),
            },
            "vault_capture_session": {
                # summary is a dict; validator passes through unknown types,
                # so we hand-validate inside the handler.
                "update_themes": ValidationSchema(type=list, max_len=20),
                "new_moments": ValidationSchema(type=list, max_len=20),
                "divergence": ValidationSchema(type=str, max_len=1000),
            },
            "vault_health_check": {
                "stale_threshold_days": ValidationSchema(
                    type=int, min=1, max=3650, default=30,
                ),
            },
            "vault_correct_evidence": {
                "theme_slug": ValidationSchema(
                    type=str, required=True, pattern=r"^[a-z0-9][a-z0-9\-]{0,63}$",
                ),
                "evidence_timestamp": ValidationSchema(
                    type=str, required=True, max_len=40,
                ),
                "correction": ValidationSchema(
                    type=str, required=True, max_len=2000,
                ),
                "corrected_by": ValidationSchema(type=str, max_len=200),
                "propagate": ValidationSchema(type=bool, default=False),
            },
            "vault_log_failure_mode": {
                "slug": ValidationSchema(
                    type=str, required=True, pattern=r"^[a-z0-9][a-z0-9\-]{0,63}$",
                ),
                "title": ValidationSchema(type=str, max_len=200),
                "symptom": ValidationSchema(type=str, max_len=2000),
                "diagnosis": ValidationSchema(type=str, max_len=2000),
                "mitigation": ValidationSchema(type=str, max_len=2000),
                "status": ValidationSchema(
                    type=str,
                    allowed_values=["active", "mitigated", "superseded"],
                ),
                "evidence": ValidationSchema(type=str, max_len=2000),
                "related_themes": ValidationSchema(type=list),
                "related_subjects": ValidationSchema(type=list),
                "tags": ValidationSchema(type=list),
                "evidence_source_tier": ValidationSchema(type=int, min=1, max=3),
                "evidence_source_tool": ValidationSchema(type=str, max_len=200),
                "evidence_source_domain": ValidationSchema(type=str, max_len=200),
                "evidence_verification": ValidationSchema(
                    type=str,
                    allowed_values=["observed", "computed", "inferred", "unverified"],
                ),
            },
            "vault_list_failure_modes": {
                "status": ValidationSchema(
                    type=str,
                    allowed_values=["active", "mitigated", "superseded"],
                ),
                "limit": ValidationSchema(type=int, min=1, max=100, default=20),
            },
            "vault_inbox_add": {
                "text": ValidationSchema(type=str, required=True, max_len=2000),
                "tags": ValidationSchema(type=list),
            },
            "vault_inbox_list": {
                "limit": ValidationSchema(type=int, min=1, max=100, default=20),
            },
            "vault_inbox_drain": {
                "items": ValidationSchema(type=list, required=True, max_len=50),
            },
            "vault_generate_snapshot": {
                "written_by": ValidationSchema(type=str, max_len=200),
            },
            "vault_get_snapshot": {},
            "vault_rescan": {},
            "vault_refresh_dashboards": {
                "with_dataview_blocks": ValidationSchema(type=bool, default=True),
            },
            "vault_traverse_links": {
                "filename": ValidationSchema(type=str, required=True),
                "depth": ValidationSchema(type=int, min=1, max=3, default=1),
                "direction": ValidationSchema(
                    type=str, allowed_values=["out", "in", "both"],
                ),
            },
        }
        # v6.2 — every vault tool accepts entity_id for audit-scoping
        # and (where the handler supports it) note keying. ADR 0002 +
        # ADR 0009. setdefault preserves any tool that ever wants a
        # narrower schema.
        for tool_schemas in schemas.values():
            tool_schemas.setdefault("entity_id", ENTITY_ID_SCHEMA)
        return schemas

    async def execute(self, tool_name: str, params: dict) -> dict:
        handlers = {
            "vault_get_fitness_summary": self._handle_fitness_summary,
            "vault_list_notes": self._handle_list_notes,
            "vault_read_note": self._handle_read_note,
            "vault_search_notes": self._handle_search_notes,
            "vault_list_anomalies": self._handle_list_anomalies,
            "vault_annotate_run": self._handle_annotate_run,
            "vault_backfill": self._handle_backfill,
            "vault_list_themes": self._handle_list_themes,
            "vault_read_theme": self._handle_read_theme,
            "vault_upsert_theme": self._handle_upsert_theme,
            "vault_list_moments": self._handle_list_moments,
            "vault_capture_moment": self._handle_capture_moment,
            "vault_capture_session": self._handle_capture_session,
            "vault_rescan": self._handle_rescan,
            "vault_traverse_links": self._handle_traverse_links,
            "vault_generate_snapshot": self._handle_generate_snapshot,
            "vault_get_snapshot": self._handle_get_snapshot,
            "vault_health_check": self._handle_health_check,
            "vault_correct_evidence": self._handle_correct_evidence,
            "vault_log_failure_mode": self._handle_log_failure_mode,
            "vault_list_failure_modes": self._handle_list_failure_modes,
            "vault_refresh_dashboards": self._handle_refresh_dashboards,
            "vault_inbox_add": self._handle_inbox_add,
            "vault_inbox_list": self._handle_inbox_list,
            "vault_inbox_drain": self._handle_inbox_drain,
        }
        handler = handlers.get(tool_name)
        if not handler:
            return {"error": f"Unknown vault tool: {tool_name}"}
        return await handler(params)

    def close(self) -> None:
        """Release SQLite connections (required on Windows)."""
        self._writer.close()

    # ══════════════════════════════════════════════════════════
    # HANDLERS
    # ══════════════════════════════════════════════════════════

    async def _handle_fitness_summary(self, params: dict) -> dict:
        """
        Primary session orientation: aggregate fitness snapshot from vault
        notes, plus open themes and recent moments so the LLM can resume
        prior analytical threads.

        DEPRECATED in v7.6.0 per ADR 0038 § Amendment 2026-05-19: prefer
        ``vault_get_snapshot``. One-time stderr log on first call per
        process surfaces the deprecation without flooding the audit log.
        """
        # One-shot deprecation warning per process (not per call).
        # Surfaces on stderr only — the audit row carries the call
        # normally (router-tier audit, not CLI-helper carve-out per
        # ADR 0001 § Amendment 2026-05-18; see ADR 0038 § Amendment
        # 2026-05-19 sub-item 7).
        if not self._fitness_summary_deprecation_logged:
            log.warning(
                "vault_get_fitness_summary is DEPRECATED in v7.6.0 -- "
                "prefer vault_get_snapshot. Removal target: future "
                "v7.7.x+ when cue-card and child-dependency conditions "
                "are met per ADR 0038 Amendment 2026-05-19."
            )
            self._fitness_summary_deprecation_logged = True
        weeks_back = params.get("weeks_back", 8)
        from datetime import datetime, timedelta, timezone
        cutoff = (datetime.now(timezone.utc) - timedelta(weeks=weeks_back)).strftime("%Y-%m-%d")

        notes = self._storage.list_notes(
            note_type="run_report",
            date_from=cutoff,
            limit=200,
        )

        # Open themes and recent moments surface regardless of whether
        # the running period has any notes — they may still exist.
        open_themes = self._storage.list_themes(status="open", limit=5)
        theme_rows = [
            {
                "slug": t["slug"],
                "status": t["status"],
                "last_updated": t["last_updated"],
                "linked_run_count": len(t.get("linked_runs") or []),
                "confidence": t.get("confidence"),
                "excerpt": t.get("excerpt"),
            }
            for t in open_themes
        ]

        moment_notes = self._storage.list_notes(
            domain="vault",
            note_type="moment",
            limit=5,
        )
        moment_rows = [
            {
                "filename": n["filename"],
                "date": n["date"],
                "title": (n.get("frontmatter") or {}).get("title") or _title_from_filename(n["filename"]),
                "linked_runs": (n.get("frontmatter") or {}).get("linked_runs") or [],
                "linked_themes": (n.get("frontmatter") or {}).get("linked_themes") or [],
            }
            for n in moment_notes
        ]

        if not notes:
            total_running = self._storage.count_notes(domain="running")
            total_all = self._storage.count_notes()
            non_running = total_all - total_running
            if total_running > 0:
                summary_msg = "No run notes found in the specified period."
                # Tool names derived from ``backfill_config`` per ADR 0038 §
                # Amendment 2026-05-19 — wiring site supplies the actual
                # per-child names; vault layer falls back to generic prose.
                sync_tool = self._backfill_config.get("sync_tool")
                report_tool = self._backfill_config.get("report_tool")
                if sync_tool and report_tool:
                    remediation = (
                        "Call vault_backfill to generate notes for cached "
                        f"activities, or run {sync_tool} + {report_tool} "
                        "to create new ones."
                    )
                else:
                    remediation = (
                        "Call vault_backfill to generate notes for cached "
                        "activities, or run your biosensor sync + report "
                        "tools to create new ones."
                    )
            elif non_running > 0:
                summary_msg = (
                    "No biosensor run data is registered in this deployment; "
                    "themes and moments below reflect the current analytical "
                    "thread."
                )
                remediation = (
                    "Call vault_get_snapshot for hand-written orientation prose "
                    "(if available) or vault_list_moments / vault_list_themes "
                    "to browse what's in the vault."
                )
            else:
                summary_msg = "Vault is empty."
                remediation = (
                    "Capture a moment with vault_capture_moment, open a "
                    "theme with vault_upsert_theme, or scaffold the "
                    "guided demo with the tailor_fitting_room_scaffold "
                    "tool."
                )
            return {
                "summary": summary_msg,
                "total_notes_in_vault": total_all,
                "weeks_back": weeks_back,
                "open_themes": theme_rows,
                "recent_moments": moment_rows,
                "note": remediation,
            }

        # Aggregate by ISO week
        from collections import defaultdict
        weeks: dict = defaultdict(lambda: {
            "runs": 0, "total_miles": 0.0, "total_minutes": 0.0,
            "hrs": [], "anomaly_count": 0, "has_insights": 0,
        })

        for n in notes:
            fm = n.get("frontmatter", {})
            week = fm.get("week") or n.get("week") or "unknown"
            w = weeks[week]
            w["runs"] += 1
            w["total_miles"] += float(fm.get("distance_miles", 0) or 0)
            w["total_minutes"] += float(fm.get("duration_min", 0) or 0)
            if fm.get("avg_hr"):
                w["hrs"].append(int(fm["avg_hr"]))
            w["anomaly_count"] += int(fm.get("anomaly_count", 0) or 0)
            if n.get("has_insight_notes"):
                w["has_insights"] += 1

        rows = []
        for week_key in sorted(weeks.keys(), reverse=True):
            w = weeks[week_key]
            avg_hr = round(sum(w["hrs"]) / len(w["hrs"])) if w["hrs"] else None
            rows.append({
                "week": week_key,
                "runs": w["runs"],
                "total_miles": round(w["total_miles"], 1),
                "total_minutes": round(w["total_minutes"], 1),
                "avg_hr": avg_hr,
                "anomalies": w["anomaly_count"],
                "insight_notes": w["has_insights"],
            })

        return {
            "weeks_back": weeks_back,
            "total_runs": len(notes),
            "weekly_summary": rows,
            "open_themes": theme_rows,
            "recent_moments": moment_rows,
            "note": (
                "Aggregated from vault note frontmatter. "
                "open_themes and recent_moments preserve analytical threads "
                "across sessions — read their bodies with vault_read_theme / "
                "vault_read_note if relevant to the current question."
            ),
        }

    async def _handle_list_notes(self, params: dict) -> dict:
        kind = params.get("kind") or params.get("note_type")
        domain = self._domain_for_kind(kind)
        notes = self._storage.list_notes(
            domain=domain,
            note_type=kind,
            date_from=params.get("date_from"),
            date_to=params.get("date_to"),
            has_insight_notes=params.get("has_insight_notes"),
            entity_id=params.get("entity_id"),
            limit=params.get("limit", 20),
        )
        return {
            "count": len(notes),
            "kind_filter": kind,
            "notes": [
                {
                    "filename": n["filename"],
                    "kind": n["note_type"],
                    "note_type": n["note_type"],  # legacy alias
                    "date": n["date"],
                    "week": n["week"],
                    "activity_id": n["activity_id"],
                    "has_insight_notes": n["has_insight_notes"],
                }
                for n in notes
            ],
        }

    async def _handle_read_note(self, params: dict) -> dict:
        filename = params["filename"]

        # Pick up user edits in Obsidian before reading the index
        try:
            revalidate_file(filename, self._vault_path, self._storage)
        except Exception as exc:  # pragma: no cover
            log.warning(f"vault_read_note: revalidate_file failed: {exc}")

        # Security: must exist in index
        index_entry = self._storage.get_note(filename)
        if not index_entry:
            return {"error": f"Note not found in vault index: {filename}"}

        # Security: path traversal guard
        try:
            abs_path = (self._vault_path / filename).resolve()
            vault_resolved = self._vault_path.resolve()
            if not _is_relative_to(abs_path, vault_resolved):
                return {"error": "Invalid filename (path traversal detected)"}
        except Exception:
            return {"error": "Invalid filename"}

        if not abs_path.exists():
            return {"error": f"Note file not found on disk: {filename}"}

        content = abs_path.read_text(encoding="utf-8")
        return {
            "filename": filename,
            "note_type": index_entry["note_type"],
            "date": index_entry["date"],
            "has_insight_notes": index_entry["has_insight_notes"],
            "content": content,
        }

    async def _handle_search_notes(self, params: dict) -> dict:
        query = params["query"].lower()
        kind = params.get("kind") or params.get("note_type")
        limit = params.get("limit", 10)

        # Search across running + vault domains (themes and moments included)
        candidates = self._storage.list_notes(
            domain=self._domain_for_kind(kind),
            note_type=kind,
            entity_id=params.get("entity_id"),
            limit=500,
        )

        matches = []
        for n in candidates:
            try:
                # Lazy mtime check so user edits in Obsidian are searchable
                revalidate_file(n["filename"], self._vault_path, self._storage)

                abs_path = (self._vault_path / n["filename"]).resolve()
                if not abs_path.exists():
                    continue
                content = abs_path.read_text(encoding="utf-8").lower()
                if query in content:
                    idx = content.find(query)
                    start = max(0, idx - 100)
                    end = min(len(content), idx + 100)
                    snippet = "..." + content[start:end].replace("\n", " ") + "..."
                    matches.append({
                        "filename": n["filename"],
                        "date": n["date"],
                        "kind": n["note_type"],
                        "note_type": n["note_type"],  # legacy alias
                        "snippet": snippet,
                    })
            except Exception:
                continue
            if len(matches) >= limit:
                break

        return {
            "query": params["query"],
            "count": len(matches),
            "results": matches,
        }

    async def _handle_list_anomalies(self, params: dict) -> dict:
        anomaly_type = params.get("anomaly_type")
        limit = params.get("limit", 20)
        notes = self._storage.get_anomalous_notes(
            anomaly_type=anomaly_type,
            entity_id=params.get("entity_id"),
            limit=limit,
        )
        return {
            "count": len(notes),
            "anomaly_type_filter": anomaly_type,
            "notes": [
                {
                    "filename": n["filename"],
                    "date": n["date"],
                    "activity_id": n["activity_id"],
                    "anomaly_count": (n.get("frontmatter") or {}).get("anomaly_count", 0),
                    "anomaly_types": (n.get("frontmatter") or {}).get("anomaly_types", []),
                    "has_insight_notes": n["has_insight_notes"],
                }
                for n in notes
            ],
        }

    async def _handle_annotate_run(self, params: dict) -> dict:
        filename = params["filename"]
        notes = params["notes"]

        # Security: must exist in index
        index_entry = self._storage.get_note(filename)
        if not index_entry:
            return {"error": f"Note not found in vault index: {filename}"}

        try:
            self._writer.append_insight_notes(filename, notes)
        except (ValueError, FileNotFoundError) as exc:
            return {"error": str(exc)}

        return {
            "annotated": True,
            "filename": filename,
            "note": "Insight notes appended. They will be visible in future sessions.",
        }

    async def _handle_backfill(self, params: dict) -> dict:
        """
        LLM-driven, server-orchestrated backfill.

        The LLM decides *when* to run backfill; the server iterates
        cached activities and writes missing notes.  Cross-child tool
        names come from ``self._backfill_config``, so the vault has no
        hardcoded knowledge of sibling domains.
        """
        limit = params.get("limit", 50)

        if self._router is None:
            return {"error": "Backfill requires router reference (not available)."}

        list_tool = self._backfill_config.get("list_tool")
        report_tool = self._backfill_config.get("report_tool")
        if not list_tool or not report_tool:
            return {
                "error": (
                    "Backfill is not configured. The vault layer must be "
                    "initialized with backfill_config={'list_tool': ..., "
                    "'report_tool': ...} to enable this tool."
                )
            }

        # Get activity list through Router → source child (e.g. RunningChild)
        list_result = await self._router.dispatch_internal(list_tool, {"limit": limit})
        if "error" in list_result:
            return {"error": f"Failed to list activities: {list_result['error']}"}

        activities = list_result.get("activities", [])
        if not activities:
            return {"written": 0, "skipped": 0, "errors": 0, "note": "No cached activities found."}

        written = 0
        skipped = 0
        errors = 0
        filenames = []
        failed_ids: list[dict] = []

        for activity in activities:
            activity_id = activity.get("id")
            if not activity_id:
                continue

            # Derive expected filename
            date_str = (activity.get("start_date") or "")[:10]
            if not date_str:
                skipped += 1
                continue
            expected_filename = f"running/{date_str}-activity-{activity_id}.md"

            # Skip if already in index
            if self._storage.get_note(expected_filename):
                skipped += 1
                continue

            try:
                # Generate run report through Router → source child
                # Full security pipeline: validation, consent, audit
                report = await self._router.dispatch_internal(
                    report_tool, {"activity_id": activity_id}
                )
                if "error" in report:
                    skipped += 1
                    continue

                filename = self._writer.write_note(report_tool, report)
                filenames.append(filename)
                written += 1

            except Exception as exc:
                log.warning(f"vault_backfill: failed for activity {activity_id}: {exc}")
                errors += 1
                failed_ids.append({"activity_id": activity_id, "error": str(exc)})

        return {
            "written": written,
            "skipped": skipped,
            "errors": errors,
            "filenames": filenames[:20],  # cap response size
            "failed": failed_ids,
            "note": f"Generated {written} new notes. {skipped} already existed or had no streams."
            + (f" {errors} failed — see 'failed' for details." if errors else ""),
        }

    # ══════════════════════════════════════════════════════════
    # REASONING-PERSISTENCE HANDLERS
    # ══════════════════════════════════════════════════════════

    async def _handle_list_themes(self, params: dict) -> dict:
        status = params.get("status")
        tag = params.get("tag")
        entity_id = params.get("entity_id")
        limit = params.get("limit", 20)

        themes = self._storage.list_themes(
            status=status,
            entity_id=entity_id,
            limit=limit * 2 if tag else limit,
        )

        # Tag filter is applied post-hoc to keep the storage surface small.
        if tag:
            tagged = set(self._storage.list_filenames_by_tag(tag))
            themes = [t for t in themes if f"themes/{t['slug']}.md" in tagged]
            themes = themes[:limit]

        return {
            "count": len(themes),
            "status_filter": status,
            "tag_filter": tag,
            "themes": [
                {
                    "slug": t["slug"],
                    "status": t["status"],
                    "opened": t["opened"],
                    "last_updated": t["last_updated"],
                    "linked_run_count": len(t.get("linked_runs") or []),
                    "confidence": t.get("confidence"),
                    "excerpt": t.get("excerpt"),
                }
                for t in themes
            ],
        }

    async def _handle_read_theme(self, params: dict) -> dict:
        slug = params["slug"]
        filename = f"themes/{slug}.md"

        # Pick up Obsidian edits
        try:
            revalidate_file(filename, self._vault_path, self._storage)
        except Exception as exc:  # pragma: no cover
            log.warning(f"vault_read_theme: revalidate_file failed: {exc}")

        index_entry = self._storage.get_note(filename)
        theme_row = self._storage.get_theme(slug)
        if not index_entry and not theme_row:
            return {"error": f"Theme not found: {slug}"}

        try:
            abs_path = (self._vault_path / filename).resolve()
            vault_resolved = self._vault_path.resolve()
            if not _is_relative_to(abs_path, vault_resolved):
                return {"error": "Invalid theme slug (path traversal detected)"}
        except Exception:
            return {"error": "Invalid theme slug"}

        if not abs_path.exists():
            return {"error": f"Theme file not found on disk: {filename}"}

        content = abs_path.read_text(encoding="utf-8")

        # Resolve outgoing wikilinks to titles for quick navigation
        outgoing = self._storage.get_outgoing_links(filename)
        links = []
        for link in outgoing:
            target = link["target"]
            entry = self._storage.get_note(target)
            title = None
            if entry:
                title = (entry.get("frontmatter") or {}).get("title") or _title_from_filename(target)
            links.append({
                "target": target,
                "display": link.get("link_text"),
                "title": title,
                "exists": bool(entry),
            })

        return {
            "slug": slug,
            "filename": filename,
            "status": (theme_row or {}).get("status"),
            "confidence": (theme_row or {}).get("confidence"),
            "linked_runs": (theme_row or {}).get("linked_runs") or [],
            "content": content,
            "links": links,
        }

    async def _handle_upsert_theme(self, params: dict) -> dict:
        slug = params["slug"]
        filename = f"themes/{slug}.md"

        # ADR 0009 — vault subject-keying. Optional, set-once.
        new_entity_id = params.get("entity_id")
        new_entity_id = str(new_entity_id).strip() if new_entity_id else None

        existing = self._storage.get_theme(slug)
        abs_path = (self._vault_path / filename).resolve()
        on_disk = abs_path.exists()

        # If a body exists on disk, prefer append semantics for evidence.
        if existing or on_disk:
            # Pick up any Obsidian edits first
            try:
                revalidate_file(filename, self._vault_path, self._storage)
            except Exception as exc:  # pragma: no cover
                log.warning(f"vault_upsert_theme: revalidate_file failed: {exc}")
            existing = self._storage.get_theme(slug) or existing

            # Enforce set-once on theme subject. Promotion (None → P004)
            # is allowed; reassignment (P003 → P007) is a hard error.
            current_subject = (existing or {}).get("entity_id")
            if (
                new_entity_id is not None
                and current_subject is not None
                and new_entity_id != current_subject
            ):
                return {
                    "error": (
                        f"Theme {slug!r} is already scoped to subject "
                        f"{current_subject!r}; cannot reassign to "
                        f"{new_entity_id!r}. Open a new theme and "
                        f"reframe-link the old one if a different scope is "
                        f"genuinely needed (ADR 0009 set-once invariant)."
                    )
                }
            effective_entity_id = new_entity_id or current_subject

            # Reframe detection: new hypothesis that differs from the one
            # on disk means the old framing is preserved under
            # ## Prior Framings and the body's hypothesis is replaced.
            # The user may also send status="reframed" as an explicit
            # signal; either way, status persists as "open" (reframed is
            # a transitional event, not a terminal state).
            new_hypothesis = (params.get("hypothesis") or "").strip()
            reframed = False
            if new_hypothesis:
                old_hypothesis = self._read_theme_hypothesis(slug) or ""
                if old_hypothesis and old_hypothesis != new_hypothesis:
                    try:
                        self._writer.reframe_theme(
                            slug, new_hypothesis, old_hypothesis
                        )
                        reframed = True
                    except (ValueError, FileNotFoundError) as exc:
                        return {"error": str(exc)}

            # Normalize status: "reframed" is a signal, not a stored state.
            effective_params = dict(params)
            if effective_params.get("status") == "reframed":
                effective_params["status"] = "open"

            # Merge frontmatter-level fields in place by rewriting only the
            # frontmatter block — body is preserved.
            try:
                updated_filename = self._merge_theme_frontmatter(
                    slug, effective_params, existing or {},
                    entity_id=effective_entity_id,
                )
            except (ValueError, FileNotFoundError) as exc:
                return {"error": str(exc)}

            # Append new evidence, if any
            evidence = params.get("evidence")
            if evidence:
                try:
                    self._writer.append_theme_evidence(
                        slug,
                        evidence,
                        source_tier=params.get("evidence_source_tier"),
                        source_tool=params.get("evidence_source_tool"),
                        source_domain=params.get("evidence_source_domain"),
                        verification=params.get("evidence_verification"),
                        entity_id=new_entity_id,
                    )
                except (ValueError, FileNotFoundError) as exc:
                    return {"error": str(exc)}

            # Append thinking block, if provided (Feature 2B)
            thinking = params.get("thinking")
            if thinking:
                try:
                    self._writer.append_theme_thinking(slug, thinking)
                except (ValueError, FileNotFoundError) as exc:
                    return {"error": str(exc)}

            # Fold-back on resolution (Feature 2C): when the theme reaches
            # a terminal state, annotate linked run + theme notes so
            # browsing them surfaces that this thread closed.
            final_status = effective_params.get("status") or (existing or {}).get("status") or "open"
            if final_status in ("resolved", "rejected"):
                resolution_text = (
                    params.get("resolution")
                    or f"Theme {slug} marked {final_status}."
                )
                try:
                    self._foldback_resolution(
                        slug,
                        final_status,
                        resolution_text,
                        linked_runs=params.get("linked_runs")
                        or (existing or {}).get("linked_runs") or [],
                        linked_themes=params.get("linked_themes") or [],
                    )
                except Exception as exc:  # pragma: no cover
                    log.warning(f"vault_upsert_theme: foldback failed: {exc}")

            response = {
                "upserted": True,
                "created": False,
                "filename": updated_filename,
                "slug": slug,
                "note": "Frontmatter merged; evidence appended as a new block.",
            }
            if reframed:
                response["reframed"] = True
                response["note"] = (
                    "Theme reframed: prior hypothesis preserved under "
                    "## Prior Framings."
                )
            return response

        # New theme — write the full note
        if not params.get("hypothesis"):
            return {
                "error": (
                    "Creating a new theme requires 'hypothesis'. "
                    "Subsequent calls may omit it to append evidence."
                )
            }

        theme = {
            "slug": slug,
            "title": params.get("title"),
            "hypothesis": params.get("hypothesis"),
            "status": params.get("status") or "open",
            "confidence": params.get("confidence"),
            "linked_runs": params.get("linked_runs") or [],
            "linked_themes": params.get("linked_themes") or [],
            "tags": params.get("tags") or [],
            "resolution": params.get("resolution"),
            "entity_id": new_entity_id,
        }
        ev = params.get("evidence")
        if ev:
            theme["evidence"] = [ev]

        try:
            filename = self._writer.write_theme(theme)
        except (ValueError, FileNotFoundError) as exc:
            return {"error": str(exc)}

        return {
            "upserted": True,
            "created": True,
            "filename": filename,
            "slug": slug,
            "note": "New theme note created. Future calls will append evidence.",
        }

    def _read_theme_hypothesis(self, slug: str) -> str | None:
        """Extract the current ``## Hypothesis`` prose from the theme file."""
        filename = f"themes/{slug}.md"
        try:
            abs_path = self._writer._safe_path(filename)  # type: ignore[attr-defined]
        except ValueError:
            return None
        if not abs_path.exists():
            return None
        content = abs_path.read_text(encoding="utf-8")
        header = "## Hypothesis"
        idx = content.find(header)
        if idx == -1:
            return None
        after = idx + len(header)
        next_idx = content.find("\n## ", after)
        if next_idx == -1:
            next_idx = len(content)
        section = content[after:next_idx].strip()
        if section.startswith("*(No hypothesis yet."):
            return None
        return section or None

    def _foldback_resolution(
        self,
        slug: str,
        status: str,
        resolution_text: str,
        linked_runs: list,
        linked_themes: list,
    ) -> None:
        """
        Best-effort: append a one-line annotation to each linked note
        recording that this theme reached a terminal state.
        """
        marker = (
            f"> Theme [[{slug}]] {status}: {resolution_text.strip()}"
        )

        # Run notes — find by activity_id
        for activity_id in linked_runs:
            run_note = self._find_run_note_by_activity_id(activity_id)
            if not run_note:
                continue
            self._append_under_section(run_note, "## Insights", marker)

        # Theme notes — filename is themes/<slug>.md
        for other_slug in linked_themes:
            other_slug = str(other_slug).strip()
            if not other_slug or other_slug == slug:
                continue
            other_filename = f"themes/{other_slug}.md"
            if not self._storage.get_note(other_filename):
                continue
            self._append_under_section(other_filename, "## Linked Themes", marker)

    def _find_run_note_by_activity_id(self, activity_id) -> str | None:
        """Best-effort: locate a run note whose frontmatter has this activity_id."""
        try:
            aid_int = int(activity_id)
        except (TypeError, ValueError):
            return None
        # Scan run_report notes; small in practice.
        notes = self._storage.list_notes(
            domain="running", note_type="run_report", limit=500
        )
        for n in notes:
            if n.get("activity_id") == aid_int:
                return n["filename"]
        return None

    def _append_under_section(
        self, filename: str, section_header: str, marker_line: str
    ) -> None:
        """
        Append ``marker_line`` immediately before the next ``## `` header
        after ``section_header``, or at end of file if no next section.
        If the marker line is already present, do nothing (idempotent).
        """
        try:
            abs_path = self._writer._safe_path(filename)  # type: ignore[attr-defined]
        except ValueError:
            return
        if not abs_path.exists():
            return
        content = abs_path.read_text(encoding="utf-8")
        if marker_line in content:
            return

        hdr_idx = content.find(section_header)
        if hdr_idx == -1:
            # Section missing — create it at end of file.
            updated = content.rstrip() + f"\n\n{section_header}\n\n{marker_line}\n"
        else:
            after_hdr = hdr_idx + len(section_header)
            next_section = content.find("\n## ", after_hdr)
            if next_section == -1:
                updated = content.rstrip() + f"\n\n{marker_line}\n"
            else:
                updated = (
                    content[:next_section].rstrip()
                    + f"\n\n{marker_line}\n\n"
                    + content[next_section + 1 :]
                )

        try:
            self._writer._atomic_write_abs(abs_path, updated)  # type: ignore[attr-defined]
            self._writer._index_note(  # type: ignore[attr-defined]
                filename,
                self._storage.get_note(filename).get("note_type", "unknown")
                if self._storage.get_note(filename) else "unknown",
                {},
                updated,
            )
        except Exception as exc:  # pragma: no cover
            log.warning(f"_append_under_section({filename}) failed: {exc}")

    def _merge_theme_frontmatter(
        self,
        slug: str,
        params: dict,
        existing_theme: dict,
        *,
        entity_id: str | None = None,
    ) -> str:
        """
        Rewrite only the YAML frontmatter of an existing theme note.
        Body (including the evidence log and resolution section) is
        preserved verbatim.  Returns the relative filename.
        """
        from .parser import split_frontmatter
        from .renderer import _yaml_int_list, _yaml_scalar, _yaml_string_list

        filename = f"themes/{slug}.md"
        abs_path = self._writer._safe_path(filename)  # type: ignore[attr-defined]
        if not abs_path.exists():
            raise FileNotFoundError(f"Theme note missing: {filename}")

        content = abs_path.read_text(encoding="utf-8")
        fm, body = split_frontmatter(content)

        # Merge scalar fields — new values override existing, else keep
        def _pick(key: str, default=None):
            return params.get(key) if params.get(key) is not None else fm.get(key, default)

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        title = _pick("title", slug.replace("-", " ").title())
        status = _pick("status", existing_theme.get("status") or "open")
        confidence = _pick("confidence", existing_theme.get("confidence"))
        opened = fm.get("opened") or existing_theme.get("opened") or today
        last_updated = today

        # Merge list fields — union of existing + new
        def _merge_list(key: str):
            merged: list = []
            for item in (fm.get(key) or []) + list(params.get(key) or []):
                if item not in merged:
                    merged.append(item)
            return merged

        linked_runs = _merge_list("linked_runs")
        linked_themes = _merge_list("linked_themes")
        tags = _merge_list("tags")
        if "theme" not in tags:
            tags = ["theme"] + tags

        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        fm_lines = [
            "---",
            "domain: vault",
            "note_type: theme",
            "kind: theme",
            f"slug: {_yaml_scalar(slug)}",
            f"title: {_yaml_scalar(title)}",
            f"status: {_yaml_scalar(status)}",
            f"opened: {_yaml_scalar(opened)}",
            f"last_updated: {_yaml_scalar(last_updated)}",
            f"date: {_yaml_scalar(last_updated)}",
            f"linked_runs: {_yaml_int_list([int(x) for x in linked_runs if x is not None])}",
            f"linked_themes: {_yaml_string_list(linked_themes)}",
        ]
        # Preserve set-once entity_id across frontmatter rewrites — read
        # whatever is already on disk, fall back to the caller-supplied
        # value (which has already been validated by _handle_upsert_theme).
        effective_subject = entity_id or fm.get("entity_id")
        if effective_subject:
            fm_lines.append(f"entity_id: {_yaml_scalar(effective_subject)}")
        if confidence:
            fm_lines.append(f"confidence: {_yaml_scalar(confidence)}")
        fm_lines.append(f'generated_at: "{now_iso}"')
        fm_lines.append("tags:")
        fm_lines += [f"  - {t}" for t in tags]
        fm_lines.append("---")

        new_content = "\n".join(fm_lines) + "\n" + body
        self._writer._atomic_write_abs(abs_path, new_content)  # type: ignore[attr-defined]
        self._writer._index_note(filename, "vault_theme", {}, new_content)  # type: ignore[attr-defined]

        # Also handle status flip → append resolution prose into the
        # Resolution section if provided.
        resolution = params.get("resolution")
        if resolution and status != "open":
            # Re-read, replace the Resolution stub/placeholder
            current = abs_path.read_text(encoding="utf-8")
            placeholders = [
                "*(Open — no resolution yet.)*",
                f"*(Status: {status}. No resolution notes recorded.)*",
            ]
            replaced = False
            for ph in placeholders:
                if ph in current:
                    current = current.replace(ph, resolution.strip(), 1)
                    replaced = True
                    break
            if not replaced:
                # Append to the existing Resolution block
                header = "\n## Resolution\n\n"
                if header in current:
                    current = current.rstrip() + f"\n\n{resolution.strip()}\n"
            self._writer._atomic_write_abs(abs_path, current)  # type: ignore[attr-defined]
            self._writer._index_note(filename, "vault_theme", {}, current)  # type: ignore[attr-defined]

        return filename

    async def _handle_list_moments(self, params: dict) -> dict:
        date_from = params.get("date_from")
        date_to = params.get("date_to")
        theme_filter = params.get("theme")
        tag = params.get("tag")
        limit = params.get("limit", 20)

        notes = self._storage.list_notes(
            domain="vault",
            note_type="moment",
            date_from=date_from,
            date_to=date_to,
            entity_id=params.get("entity_id"),
            limit=limit * 2 if (theme_filter or tag) else limit,
        )

        if tag:
            tagged = set(self._storage.list_filenames_by_tag(tag))
            notes = [n for n in notes if n["filename"] in tagged]

        if theme_filter:
            notes = [
                n for n in notes
                if theme_filter in ((n.get("frontmatter") or {}).get("linked_themes") or [])
            ]

        notes = notes[:limit]
        return {
            "count": len(notes),
            "theme_filter": theme_filter,
            "tag_filter": tag,
            "moments": [
                {
                    "filename": n["filename"],
                    "date": n["date"],
                    "title": (n.get("frontmatter") or {}).get("title") or _title_from_filename(n["filename"]),
                    "linked_runs": (n.get("frontmatter") or {}).get("linked_runs") or [],
                    "linked_themes": (n.get("frontmatter") or {}).get("linked_themes") or [],
                }
                for n in notes
            ],
        }

    async def _handle_capture_moment(self, params: dict) -> dict:
        try:
            filename = self._writer.write_moment({
                "title": params["title"],
                "body": params["body"],
                "linked_runs": params.get("linked_runs") or [],
                "linked_themes": params.get("linked_themes") or [],
                "tags": params.get("tags") or [],
                "date": params.get("date"),
                "entity_id": params.get("entity_id"),  # ADR 0009
            })
        except (ValueError, KeyError, FileNotFoundError) as exc:
            return {"error": str(exc)}

        return {
            "captured": True,
            "filename": filename,
            "note": "Moment recorded. It will be visible in future sessions.",
        }

    async def _handle_capture_session(self, params: dict) -> dict:
        """
        Session-boundary bundle.  Writes:
          1. The required summary moment (must have title + body).
          2. Zero or more theme updates (each merges + optionally appends evidence).
          3. Zero or more additional moments.

        Audited as a single tool call (the router records one audit row);
        internal failures are aggregated into the response.
        """
        summary = params.get("summary")
        if not isinstance(summary, dict) or not summary.get("title") or not summary.get("body"):
            return {
                "error": (
                    "'summary' must be an object with 'title' and 'body' fields. "
                    "This is the top-line takeaway for the session."
                )
            }

        results: dict = {
            "summary_filename": None,
            "theme_updates": [],
            "moment_filenames": [],
            "errors": [],
        }

        # 1) Summary moment
        divergence = params.get("divergence")
        try:
            summary_payload = {
                "title": summary["title"],
                "body": summary["body"],
                "linked_runs": summary.get("linked_runs") or [],
                "linked_themes": summary.get("linked_themes") or [],
                "tags": (summary.get("tags") or []) + ["session-summary"],
                "date": summary.get("date"),
            }
            if divergence:
                summary_payload["divergence"] = divergence
            results["summary_filename"] = self._writer.write_moment(summary_payload)
        except Exception as exc:
            results["errors"].append({"stage": "summary", "error": str(exc)})

        # 2) Theme updates — reuse the upsert handler so semantics stay identical
        for i, update in enumerate(params.get("update_themes") or []):
            if not isinstance(update, dict) or not update.get("slug"):
                results["errors"].append({"stage": f"theme_update[{i}]", "error": "missing slug"})
                continue
            sub = await self._handle_upsert_theme(update)
            results["theme_updates"].append({
                "slug": update["slug"],
                **({"error": sub["error"]} if "error" in sub else {
                    "filename": sub.get("filename"),
                    "created": sub.get("created", False),
                }),
            })

        # 3) Additional moments
        for i, moment in enumerate(params.get("new_moments") or []):
            if not isinstance(moment, dict) or not moment.get("title") or not moment.get("body"):
                results["errors"].append({"stage": f"new_moment[{i}]", "error": "missing title/body"})
                continue
            try:
                fn = self._writer.write_moment({
                    "title": moment["title"],
                    "body": moment["body"],
                    "linked_runs": moment.get("linked_runs") or [],
                    "linked_themes": moment.get("linked_themes") or [],
                    "tags": moment.get("tags") or [],
                    "date": moment.get("date"),
                })
                results["moment_filenames"].append(fn)
            except Exception as exc:
                results["errors"].append({"stage": f"new_moment[{i}]", "error": str(exc)})

        results["note"] = (
            "Session captured. These notes will be surfaced by "
            "vault_get_fitness_summary in the next session."
        )
        return results

    async def _handle_generate_snapshot(self, params: dict) -> dict:
        written_by = params.get("written_by") or "claude-session"
        snapshot = self._build_snapshot_payload(written_by)
        try:
            filename = self._writer.write_snapshot(snapshot)
        except (ValueError, FileNotFoundError) as exc:
            return {"error": str(exc)}
        return {
            "generated": True,
            "filename": filename,
            "open_theme_count": len(snapshot["open_themes"]),
            "recent_moment_count": len(snapshot["recent_moments"]),
            "note": (
                "Snapshot regenerated. Future sessions should call "
                "vault_get_snapshot first for fast orientation."
            ),
        }

    async def _handle_get_snapshot(self, params: dict) -> dict:
        snapshot_path = (self._vault_path / "snapshot.md").resolve()
        vault_resolved = self._vault_path.resolve()
        if not _is_relative_to(snapshot_path, vault_resolved):
            return {"error": "Invalid snapshot path."}
        if not snapshot_path.exists():
            # Fall back to fitness summary
            fallback = await self._handle_fitness_summary({})
            return {
                "snapshot_exists": False,
                "fallback": fallback,
                "note": (
                    "No snapshot.md yet — call vault_generate_snapshot at the "
                    "end of a session to create one."
                ),
            }
        content = snapshot_path.read_text(encoding="utf-8")
        from .parser import split_frontmatter
        fm, _body = split_frontmatter(content)
        return {
            "snapshot_exists": True,
            "filename": "snapshot.md",
            "frontmatter": fm,
            "content": content,
        }

    def _build_snapshot_payload(self, written_by: str) -> dict:
        """
        Gather the data the snapshot renderer expects from live storage
        and the filesystem.
        """
        from collections import defaultdict
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        moment_cutoff = (now - timedelta(days=14)).strftime("%Y-%m-%d")
        week_cutoff = (now - timedelta(weeks=4)).strftime("%Y-%m-%d")
        stale_cutoff = (now - timedelta(days=30)).strftime("%Y-%m-%d")

        # Open themes (with evidence counts)
        open_themes_rows = self._storage.list_themes(status="open", limit=20)
        open_themes: list[dict] = []
        stale_themes: list[str] = []
        for t in open_themes_rows:
            slug = t["slug"]
            ev_count = self._count_theme_evidence_blocks(slug)
            open_themes.append({
                "slug": slug,
                "status": t["status"],
                "confidence": t.get("confidence") or "—",
                "evidence_count": ev_count,
            })
            if t.get("last_updated") and str(t["last_updated"]) < stale_cutoff:
                stale_themes.append(slug)

        # Recent moments (last 14 days)
        recent_note_rows = self._storage.list_notes(
            domain="vault", note_type="moment", date_from=moment_cutoff, limit=20,
        )
        recent_moments = [
            {
                "date": n["date"],
                "title": (n.get("frontmatter") or {}).get("title")
                or _title_from_filename(n["filename"]),
                "linked_themes": (n.get("frontmatter") or {}).get("linked_themes") or [],
            }
            for n in recent_note_rows
        ]

        # Weekly summary (last 4 weeks of run notes). Data-source-aware
        # per ADR 0038 § Amendment 2026-05-19: the running-specific
        # query fires only when a registered child contributes the
        # ``run_report`` kind. On deployments without a running child
        # (demo cohort, REDCap-only, MATLAB-only), the query short-
        # circuits to empty and the renderer drops the Weekly Summary
        # section per v7.3.4's F3 partial closure.
        if "run_report" in self._kind_to_domain_map:
            run_rows = self._storage.list_notes(
                domain=self._kind_to_domain_map["run_report"],
                note_type="run_report",
                date_from=week_cutoff, limit=500,
            )
        else:
            run_rows = []
        weeks: dict = defaultdict(lambda: {
            "runs": 0, "total_miles": 0.0, "hrs": [],
        })
        for n in run_rows:
            fm = n.get("frontmatter", {}) or {}
            week = fm.get("week") or n.get("week") or "unknown"
            w = weeks[week]
            w["runs"] += 1
            w["total_miles"] += float(fm.get("distance_miles", 0) or 0)
            if fm.get("avg_hr"):
                w["hrs"].append(int(fm["avg_hr"]))
        weekly_summary = []
        for week_key in sorted(weeks.keys(), reverse=True)[:4]:
            w = weeks[week_key]
            avg_hr = round(sum(w["hrs"]) / len(w["hrs"])) if w["hrs"] else None
            weekly_summary.append({
                "week": week_key,
                "runs": w["runs"],
                "total_miles": round(w["total_miles"], 1),
                "avg_hr": avg_hr,
            })

        # Counts
        notes_indexed = self._storage.count_notes()
        resolved_rows = self._storage.list_themes(status="resolved", limit=10000)
        moments_total = len(self._storage.list_notes(
            domain="vault", note_type="moment", limit=10000,
        ))

        inbox_items = self._count_inbox_items()

        warnings: list[str] = []
        themes_without_evidence = [
            t["slug"] for t in open_themes_rows
            if self._count_theme_evidence_blocks(t["slug"]) == 0
        ]
        if themes_without_evidence:
            warnings.append(
                "Open themes with no evidence: " + ", ".join(themes_without_evidence)
            )
        orphaned = self._list_orphaned_moments()
        if orphaned:
            warnings.append(
                f"{len(orphaned)} moment(s) not linked to any theme."
            )

        return {
            "written_by": written_by,
            "open_themes": open_themes,
            "recent_moments": recent_moments,
            "weekly_summary": weekly_summary,
            "vault_health": {
                "notes_indexed": notes_indexed,
                "themes_open": len(open_themes_rows),
                "themes_resolved": len(resolved_rows),
                "moments": moments_total,
                "stale_themes": stale_themes,
                "inbox_items": inbox_items,
            },
            "warnings": warnings,
        }

    def _count_theme_evidence_blocks(self, slug: str) -> int:
        """Count ``### Evidence —`` headers in the theme file."""
        filename = f"themes/{slug}.md"
        try:
            abs_path = self._writer._safe_path(filename)  # type: ignore[attr-defined]
        except ValueError:
            return 0
        if not abs_path.exists():
            return 0
        content = abs_path.read_text(encoding="utf-8")
        return content.count("### Evidence —")

    def _count_inbox_items(self) -> int:
        inbox_path = self._vault_path / "inbox.md"
        if not inbox_path.exists():
            return 0
        content = inbox_path.read_text(encoding="utf-8")
        # Count the bullet-entry headers we emit
        return sum(1 for line in content.splitlines() if line.startswith("- **"))

    def _list_orphaned_moments(self) -> list[str]:
        """Return filenames of moments with no linked_themes."""
        notes = self._storage.list_notes(
            domain="vault", note_type="moment", limit=10000,
        )
        out = []
        for n in notes:
            fm = n.get("frontmatter") or {}
            if not (fm.get("linked_themes") or []):
                out.append(n["filename"])
        return out

    async def _handle_health_check(self, params: dict) -> dict:
        from datetime import datetime, timedelta, timezone

        stale_days = params.get("stale_threshold_days", 30)
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=stale_days)
        ).strftime("%Y-%m-%d")

        stale_themes = self._storage.list_stale_themes(cutoff)
        orphaned_moments = self._storage.list_orphaned_moments()
        by_status = self._storage.count_themes_by_status()

        open_theme_rows = self._storage.list_themes(status="open", limit=10000)
        themes_without_evidence = [
            t["slug"] for t in open_theme_rows
            if self._count_theme_evidence_blocks(t["slug"]) == 0
        ]

        total_moments = len(self._storage.list_notes(
            domain="vault", note_type="moment", limit=10000,
        ))

        total_themes = sum(by_status.values())

        return {
            "stale_threshold_days": stale_days,
            "stale_themes": stale_themes,
            "orphaned_moments": orphaned_moments,
            "themes_without_evidence": themes_without_evidence,
            "inbox_item_count": self._count_inbox_items(),
            "total_notes": self._storage.count_notes(),
            "total_themes": total_themes,
            "total_moments": total_moments,
            "themes_by_status": {
                "open": by_status.get("open", 0),
                "resolved": by_status.get("resolved", 0),
                "rejected": by_status.get("rejected", 0),
            },
        }

    async def _handle_correct_evidence(self, params: dict) -> dict:
        propagate = bool(params.get("propagate", False))
        try:
            result = self._writer.correct_theme_evidence(
                slug=params["theme_slug"],
                evidence_timestamp=params["evidence_timestamp"],
                correction=params["correction"],
                corrected_by=params.get("corrected_by"),
                propagate_to_referencing_notes=propagate,
            )
        except (ValueError, FileNotFoundError) as exc:
            return {"error": str(exc)}
        propagated = result["propagated_to"]
        note = (
            "Correction marker inserted and a [correction] evidence "
            "block appended. Original evidence preserved."
        )
        if propagate:
            note += (
                f" Propagated correction callout to {len(propagated)} "
                "referencing note(s)."
            )
        return {
            "corrected": True,
            "filename": result["filename"],
            "propagated_to": propagated,
            "note": note,
        }

    async def _handle_log_failure_mode(self, params: dict) -> dict:
        """
        Create or update a failure-mode note.

        On create: requires symptom + diagnosis + mitigation; writes the
        full note via VaultWriter.write_failure_mode and (if provided)
        appends an initial evidence block.

        On update: any of (status, related_themes, related_subjects,
        tags) may be merged in; if ``evidence`` is provided, it APPENDS
        a new timestamped evidence block — the existing log is never
        rewritten.
        """
        slug = params["slug"]
        filename = f"failure-modes/{slug}.md"
        try:
            revalidate_file(filename, self._vault_path, self._storage)
        except Exception as exc:  # pragma: no cover — defensive
            log.warning(f"vault_log_failure_mode: revalidate_file failed: {exc}")
        existing = self._storage.get_note(filename)

        evidence = params.get("evidence")
        provenance = {
            "source_tier": params.get("evidence_source_tier"),
            "source_tool": params.get("evidence_source_tool"),
            "source_domain": params.get("evidence_source_domain"),
            "verification": params.get("evidence_verification"),
        }

        if existing is None:
            # Fresh note — require the structural fields.
            missing = [
                k for k in ("symptom", "diagnosis", "mitigation")
                if not (params.get(k) or "").strip()
            ]
            if missing:
                return {
                    "error": (
                        "Creating a failure-mode requires: "
                        + ", ".join(missing)
                    ),
                }
            failure_mode = {
                "slug": slug,
                "title": params.get("title"),
                "symptom": params["symptom"],
                "diagnosis": params["diagnosis"],
                "mitigation": params["mitigation"],
                "status": params.get("status") or "active",
                "related_themes": params.get("related_themes") or [],
                "related_subjects": params.get("related_subjects") or [],
                "tags": params.get("tags") or [],
            }
            if evidence:
                failure_mode["evidence"] = evidence
            try:
                written = self._writer.write_failure_mode(failure_mode)
            except (ValueError, OSError) as exc:
                return {"error": str(exc)}
            return {
                "created": True,
                "filename": written,
                "evidence_appended": bool(evidence),
                "note": (
                    "Failure-mode created. Use vault_log_failure_mode "
                    "again with `evidence` to APPEND new entries; the "
                    "log is never overwritten."
                ),
            }

        # Update path — frontmatter-only mutations (preserve body + the
        # entire append-only evidence log).  Body sections (symptom,
        # diagnosis, mitigation) are intentionally read-only via this
        # tool: edit them by hand in Obsidian and the index will pick
        # the change up on next read.
        body_attempts = [
            k for k in ("symptom", "diagnosis", "mitigation")
            if (params.get(k) or "").strip()
        ]
        if body_attempts:
            return {
                "error": (
                    f"Body sections cannot be updated through "
                    f"vault_log_failure_mode after creation: "
                    f"{', '.join(body_attempts)}. Edit "
                    f"failure-modes/{slug}.md directly in Obsidian."
                ),
            }

        fm = dict(existing.get("frontmatter") or {})
        new_status = params.get("status")
        if new_status and new_status not in ("active", "mitigated", "superseded"):
            return {
                "error": (
                    f"Invalid status: {new_status!r} "
                    "(active | mitigated | superseded)."
                ),
            }

        merged_related_themes = None
        if params.get("related_themes") is not None:
            merged_related_themes = list(dict.fromkeys([
                *(fm.get("related_themes") or []),
                *(params.get("related_themes") or []),
            ]))
        merged_related_subjects = None
        if params.get("related_subjects") is not None:
            merged_related_subjects = list(dict.fromkeys([
                *(str(s) for s in (fm.get("related_subjects") or [])),
                *(str(s) for s in (params.get("related_subjects") or [])),
            ]))
        merged_tags = None
        if params.get("tags") is not None:
            merged_tags = list(dict.fromkeys([
                *(fm.get("tags") or []),
                *(params.get("tags") or []),
            ]))

        try:
            written = self._writer.update_failure_mode_metadata(
                slug,
                status=new_status,
                related_themes=merged_related_themes,
                related_subjects=merged_related_subjects,
                tags=merged_tags,
                title=params.get("title"),
            )
        except (ValueError, FileNotFoundError, OSError) as exc:
            return {"error": str(exc)}

        evidence_appended = False
        if evidence:
            try:
                self._writer.append_failure_mode_evidence(
                    slug,
                    evidence,
                    source_tier=provenance["source_tier"],
                    source_tool=provenance["source_tool"],
                    source_domain=provenance["source_domain"],
                    verification=provenance["verification"],
                )
                evidence_appended = True
            except (ValueError, FileNotFoundError) as exc:
                return {"error": str(exc)}

        return {
            "updated": True,
            "filename": written,
            "evidence_appended": evidence_appended,
            "status": new_status or fm.get("status") or "active",
        }

    async def _handle_list_failure_modes(self, params: dict) -> dict:
        """
        Compact listing of failure-mode notes.  Filters by status
        (active | mitigated | superseded) when supplied; otherwise
        returns all known failure-modes.  Body is never returned.
        """
        status = params.get("status")
        limit = params.get("limit", 20)

        rows = self._storage.list_notes(
            domain="vault", note_type="failure_mode",
            entity_id=params.get("entity_id"),
            limit=max(limit * 2, limit),
        )
        out: list[dict] = []
        for row in rows:
            fm = row.get("frontmatter") or {}
            row_status = fm.get("status") or "active"
            if status and row_status != status:
                continue
            slug = (
                fm.get("slug")
                or row["filename"].rsplit("/", 1)[-1].rsplit(".md", 1)[0]
            )
            out.append({
                "slug": slug,
                "title": fm.get("title") or slug.replace("-", " ").title(),
                "status": row_status,
                "opened": fm.get("opened"),
                "last_updated": fm.get("last_updated") or row.get("date"),
                "related_theme_count": len(fm.get("related_themes") or []),
                "related_subject_count": len(fm.get("related_subjects") or []),
            })
            if len(out) >= limit:
                break

        return {
            "count": len(out),
            "status_filter": status,
            "failure_modes": out,
        }

    async def _handle_refresh_dashboards(self, params: dict) -> dict:
        """
        Materialise the standard dashboards under ``dashboards/`` from
        the live SQLite index.  ADR 0007 dual-output: every dashboard
        ships a plain-markdown snapshot table (always rendered) plus an
        optional Dataview live-query block (renders only with the
        plugin).  The two views are derived from the same source so
        they cannot disagree about anything except freshness.
        """
        with_dv = bool(params.get("with_dataview_blocks", True))
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        written: list[dict] = []

        # 1) Open themes dashboard
        themes = self._storage.list_themes(status="open", limit=200)
        theme_rows = [
            [
                f"[[{t['slug']}]]",
                t.get("confidence") or "—",
                t.get("last_updated") or "—",
                len(t.get("linked_runs") or []),
                (t.get("excerpt") or "").replace("|", "\\|")[:80],
            ]
            for t in themes
        ]
        themes_filename = self._writer.write_dashboard(
            name="open-themes",
            title="Open themes",
            description=(
                "Persistent hypotheses currently being tracked. Click any "
                "row to open the theme note."
            ),
            columns=["Theme", "Confidence", "Last updated", "Linked runs", "Excerpt"],
            rows=theme_rows,
            dataview_query=(
                "TABLE confidence, last_updated, length(linked_runs) AS \"Runs\"\n"
                "FROM \"themes\"\nWHERE status = \"open\"\nSORT last_updated DESC"
            ) if with_dv else None,
            last_updated=now_iso,
        )
        written.append({"name": "open-themes", "filename": themes_filename, "rows": len(theme_rows)})

        # 2) Active failure-modes dashboard
        fm_rows_raw = self._storage.list_notes(
            domain="vault", note_type="failure_mode", limit=200,
        )
        fm_rows: list[list] = []
        for row in fm_rows_raw:
            fm = row.get("frontmatter") or {}
            if (fm.get("status") or "active") != "active":
                continue
            slug = (
                fm.get("slug")
                or row["filename"].rsplit("/", 1)[-1].rsplit(".md", 1)[0]
            )
            fm_rows.append([
                f"[[{slug}]]",
                fm.get("title") or slug.replace("-", " ").title(),
                fm.get("opened") or "—",
                fm.get("last_updated") or "—",
                len(fm.get("related_themes") or []),
            ])
        fm_filename = self._writer.write_dashboard(
            name="active-failure-modes",
            title="Active failure-modes",
            description=(
                "Open analytical failure-modes — patterns this study has "
                "gotten wrong before that have not yet been mitigated."
            ),
            columns=["Failure-mode", "Title", "Opened", "Last updated", "Related themes"],
            rows=fm_rows,
            dataview_query=(
                "TABLE title, opened, last_updated, length(related_themes) AS \"Themes\"\n"
                "FROM \"failure-modes\"\nWHERE status = \"active\"\nSORT last_updated DESC"
            ) if with_dv else None,
            last_updated=now_iso,
        )
        written.append({"name": "active-failure-modes", "filename": fm_filename, "rows": len(fm_rows)})

        # 3) Recent moments dashboard
        moments = self._storage.list_notes(
            domain="vault", note_type="moment", limit=20,
        )
        moment_rows: list[list] = []
        for row in moments:
            fm = row.get("frontmatter") or {}
            slug_path = row["filename"]
            display_slug = slug_path.rsplit("/", 1)[-1].rsplit(".md", 1)[0]
            moment_rows.append([
                f"[[{display_slug}]]",
                fm.get("title") or display_slug,
                row.get("date") or fm.get("date") or "—",
                len(fm.get("linked_themes") or []),
            ])
        moments_filename = self._writer.write_dashboard(
            name="recent-moments",
            title="Recent moments",
            description=(
                "Latest aha-moments captured in the vault — surfacing "
                "session-level analytical observations."
            ),
            columns=["Moment", "Title", "Date", "Linked themes"],
            rows=moment_rows,
            dataview_query=(
                "TABLE title, date, length(linked_themes) AS \"Themes\"\n"
                "FROM \"moments\"\nSORT date DESC\nLIMIT 20"
            ) if with_dv else None,
            last_updated=now_iso,
        )
        written.append({"name": "recent-moments", "filename": moments_filename, "rows": len(moment_rows)})

        return {
            "refreshed": True,
            "with_dataview_blocks": with_dv,
            "dashboards": written,
            "note": (
                "Dashboards rewritten. The snapshot tables render for "
                "any reader; the Dataview blocks (if present) render "
                "only inside Obsidian with the Dataview plugin."
            ),
        }

    async def _handle_inbox_add(self, params: dict) -> dict:
        text = params["text"]
        tags = params.get("tags") or []
        try:
            line = self._writer.append_inbox_item(text, tags=tags)
        except (ValueError, FileNotFoundError) as exc:
            return {"error": str(exc)}
        return {
            "added": True,
            "line": line,
            "note": "Inbox item appended to inbox.md.",
        }

    async def _handle_inbox_list(self, params: dict) -> dict:
        limit = params.get("limit", 20)
        try:
            items = self._writer.read_inbox()
        except ValueError as exc:
            return {"error": str(exc)}
        return {
            "count": len(items),
            "items": [
                {
                    "index": i,
                    "timestamp": it["timestamp"],
                    "text": it["text"],
                    "tags": it["tags"],
                }
                for i, it in enumerate(items[:limit])
            ],
        }

    async def _handle_inbox_drain(self, params: dict) -> dict:
        items = params.get("items") or []
        try:
            current = self._writer.read_inbox()
        except ValueError as exc:
            return {"error": str(exc)}

        moments_created = 0
        evidence_appended = 0
        discarded = 0
        errors: list[dict] = []
        to_remove: set[int] = set()

        for entry in items:
            if not isinstance(entry, dict):
                errors.append({"item": entry, "error": "not an object"})
                continue
            idx = entry.get("index")
            action = entry.get("action")
            if not isinstance(idx, int) or idx < 0 or idx >= len(current):
                errors.append({"index": idx, "error": "index out of range"})
                continue
            item = current[idx]

            if action == "discard":
                to_remove.add(idx)
                discarded += 1
                continue
            if action == "moment":
                title = entry.get("title") or (item["text"][:60] or "Inbox item")
                body = entry.get("body") or item["text"]
                try:
                    self._writer.write_moment({
                        "title": title,
                        "body": body,
                        "linked_runs": entry.get("linked_runs") or [],
                        "linked_themes": entry.get("linked_themes") or [],
                        "tags": entry.get("tags") or item.get("tags") or [],
                        "date": entry.get("date"),
                    })
                    to_remove.add(idx)
                    moments_created += 1
                except Exception as exc:
                    errors.append({"index": idx, "error": str(exc)})
                continue
            if action == "evidence":
                theme_slug = entry.get("theme_slug")
                if not theme_slug:
                    errors.append({"index": idx, "error": "missing theme_slug"})
                    continue
                try:
                    self._writer.append_theme_evidence(
                        theme_slug,
                        entry.get("text") or item["text"],
                        source_tier=entry.get("evidence_source_tier"),
                        source_tool=entry.get("evidence_source_tool"),
                        source_domain=entry.get("evidence_source_domain"),
                        verification=entry.get("evidence_verification"),
                    )
                    to_remove.add(idx)
                    evidence_appended += 1
                except Exception as exc:
                    errors.append({"index": idx, "error": str(exc)})
                continue

            errors.append({"index": idx, "error": f"unknown action: {action!r}"})

        if to_remove:
            try:
                self._writer.drain_inbox_items(to_remove)
            except Exception as exc:  # pragma: no cover
                errors.append({"stage": "rewrite", "error": str(exc)})

        return {
            "moments_created": moments_created,
            "evidence_appended": evidence_appended,
            "discarded": discarded,
            "errors": errors,
        }

    async def _handle_rescan(self, params: dict) -> dict:
        counts = rescan_vault(self._vault_path, self._storage)
        return {
            **counts,
            "note": (
                "Full vault sweep complete. The router also revalidates each "
                "note lazily on read, so explicit rescan is mainly useful "
                "after large bulk edits or migrations."
            ),
        }

    async def _handle_traverse_links(self, params: dict) -> dict:
        filename = params["filename"]
        depth = params.get("depth", 1)
        direction = params.get("direction", "both")

        # Revalidate the start node so fresh edits are seen
        try:
            revalidate_file(filename, self._vault_path, self._storage)
        except Exception as exc:  # pragma: no cover
            log.debug(f"revalidate_file({filename}) failed: {exc}")

        if not self._storage.get_note(filename):
            return {"error": f"Note not found in vault index: {filename}"}

        visited: dict[str, dict] = {}
        edges: list[dict] = []
        frontier = {filename}

        for _hop in range(depth):
            next_frontier: set[str] = set()
            for node in frontier:
                if node in visited:
                    continue
                entry = self._storage.get_note(node)
                if entry is None:
                    visited[node] = {"filename": node, "exists": False}
                    continue
                visited[node] = {
                    "filename": node,
                    "exists": True,
                    "kind": entry["note_type"],
                    "date": entry["date"],
                    "title": (entry.get("frontmatter") or {}).get("title")
                    or _title_from_filename(node),
                    "tags": self._storage.list_tags_for(node),
                }
                if len(visited) >= _TRAVERSE_MAX_NODES:
                    break

                if direction in ("out", "both"):
                    for link in self._storage.get_outgoing_links(node):
                        tgt = link["target"]
                        edges.append({"source": node, "target": tgt, "direction": "out"})
                        next_frontier.add(tgt)
                if direction in ("in", "both"):
                    for link in self._storage.get_incoming_links(node):
                        src = link["source"]
                        edges.append({"source": src, "target": node, "direction": "in"})
                        next_frontier.add(src)
            frontier = next_frontier - set(visited.keys())
            if len(visited) >= _TRAVERSE_MAX_NODES:
                break

        return {
            "start": filename,
            "depth": depth,
            "direction": direction,
            "nodes": list(visited.values()),
            "edges": edges,
            "truncated": len(visited) >= _TRAVERSE_MAX_NODES,
        }


# ══════════════════════════════════════════════════════════
# MODULE-LEVEL HELPERS
# ══════════════════════════════════════════════════════════

# Note: ``_domain_for_kind`` migrated to ``VaultLayer._domain_for_kind``
# in v7.6.0 (ADR 0038 § Amendment 2026-05-19). The instance method
# consults ``self._kind_to_domain_map`` which is populated from
# registered children's ``vault_note_kinds`` at registration time,
# rather than hardcoding ``run_report → running``.


def _title_from_filename(filename: str) -> str:
    base = filename.rsplit("/", 1)[-1]
    if base.endswith(".md"):
        base = base[:-3]
    return base.replace("-", " ").strip()
