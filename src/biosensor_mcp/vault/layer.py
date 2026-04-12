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
    vault_list_moments          Browse aha-moment notes.
    vault_capture_moment        Write a single aha-moment note.
    vault_capture_session       Session-boundary bundle: summary moment +
                                N theme updates in one audited call.
    vault_rescan                Full filesystem sweep — pick up user edits.
    vault_traverse_links        Neighbourhood of wikilinks (no bodies).
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..framework.interfaces import ToolDefinition, ValidationSchema
from .rescan import rescan_vault, revalidate_file
from .storage import VaultStorage
from .writer import VaultWriter, _is_relative_to

log = logging.getLogger("biosensor-mcp.vault")

# Max chars for vault_annotate_run notes
_MAX_NOTES_CHARS = 2000

# Allowed note kinds surfaced to users of the kind filter
_ALLOWED_KINDS = ("run_report", "trend_report", "compare_runs", "theme", "moment")

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
                          Example:
                              {"list_tool":   "strava_list_runs",
                               "report_tool": "strava_run_report"}
                          When None, vault_backfill returns a configuration error.
    """

    def __init__(
        self,
        vault_path: Path,
        vault_writer: VaultWriter,
        backfill_config: Optional[dict] = None,
    ):
        self._vault_path = vault_path
        self._writer = vault_writer
        self._storage: VaultStorage = vault_writer._storage
        self._backfill_config = backfill_config or {}
        self._router = None  # Set by RouterMCP.register_vault_layer()

    @property
    def tool_definitions(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                "vault_get_fitness_summary", 1,
                "Primary session orientation tool. Surfaces open themes and recent "
                "moments so you can resume prior analytical threads, plus a weekly "
                "fitness table aggregated from run notes — no Strava sync needed. "
                "Call this first in a new session. ~600–800 tokens.",
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
                "kind, and whether insight notes exist. Includes themes and moments "
                "alongside run/trend/compare notes.",
                {
                    "kind": {
                        "type": "string",
                        "description": (
                            "Filter by note kind: run_report | trend_report | "
                            "compare_runs | theme | moment"
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
                    "note_type": {
                        "type": "string",
                        "description": "Limit to a note type (optional)",
                        "required": False,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default 10, max 50)",
                        "required": False,
                    },
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
                },
            ),
            ToolDefinition(
                "vault_list_moments", 1,
                "List aha-moment notes (compact rows). ~300 tokens for 20 moments.",
                {
                    "date_from": {"type": "string", "required": False},
                    "date_to": {"type": "string", "required": False},
                    "theme": {
                        "type": "string",
                        "description": "Only moments linked to this theme slug",
                        "required": False,
                    },
                    "tag": {"type": "string", "required": False},
                    "limit": {"type": "integer", "required": False},
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
                    "tags": {"type": "array", "required": False},
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
                },
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

    @property
    def param_schemas(self) -> dict[str, dict[str, ValidationSchema]]:
        return {
            "vault_get_fitness_summary": {
                "weeks_back": ValidationSchema(type=int, min=1, max=52, default=8),
            },
            "vault_list_notes": {
                "kind": ValidationSchema(
                    type=str, allowed_values=list(_ALLOWED_KINDS),
                ),
                "note_type": ValidationSchema(
                    type=str, allowed_values=list(_ALLOWED_KINDS),
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
                    type=str, allowed_values=list(_ALLOWED_KINDS),
                ),
                "note_type": ValidationSchema(
                    type=str, allowed_values=list(_ALLOWED_KINDS),
                ),
                "limit": ValidationSchema(type=int, min=1, max=50, default=10),
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
                    type=str, allowed_values=["open", "resolved", "rejected"],
                ),
                "confidence": ValidationSchema(
                    type=str, allowed_values=["low", "medium", "high"],
                ),
                "linked_runs": ValidationSchema(type=list),
                "linked_themes": ValidationSchema(type=list),
                "tags": ValidationSchema(type=list),
                "title": ValidationSchema(type=str, max_len=200),
                "resolution": ValidationSchema(type=str, max_len=2000),
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
            },
            "vault_rescan": {},
            "vault_traverse_links": {
                "filename": ValidationSchema(type=str, required=True),
                "depth": ValidationSchema(type=int, min=1, max=3, default=1),
                "direction": ValidationSchema(
                    type=str, allowed_values=["out", "in", "both"],
                ),
            },
        }

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
        Primary session orientation: aggregate fitness snapshot from vault notes,
        plus open themes and recent moments so the LLM can resume prior
        analytical threads.  No Strava sync required.
        """
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
            total = self._storage.count_notes(domain="running")
            return {
                "summary": "No run notes found in the specified period.",
                "total_notes_in_vault": total,
                "weeks_back": weeks_back,
                "open_themes": theme_rows,
                "recent_moments": moment_rows,
                "note": (
                    "Call vault_backfill to generate notes for cached activities, "
                    "or run strava_sync + strava_run_report to create new ones."
                ),
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
        domain = _domain_for_kind(kind)
        notes = self._storage.list_notes(
            domain=domain,
            note_type=kind,
            date_from=params.get("date_from"),
            date_to=params.get("date_to"),
            has_insight_notes=params.get("has_insight_notes"),
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
            domain=_domain_for_kind(kind),
            note_type=kind,
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
            anomaly_type=anomaly_type, limit=limit
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
        limit = params.get("limit", 20)

        themes = self._storage.list_themes(status=status, limit=limit * 2 if tag else limit)

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
        for l in outgoing:
            target = l["target"]
            entry = self._storage.get_note(target)
            title = None
            if entry:
                title = (entry.get("frontmatter") or {}).get("title") or _title_from_filename(target)
            links.append({
                "target": target,
                "display": l.get("link_text"),
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

            # Merge frontmatter-level fields in place by rewriting only the
            # frontmatter block — body is preserved.
            try:
                updated_filename = self._merge_theme_frontmatter(slug, params, existing or {})
            except (ValueError, FileNotFoundError) as exc:
                return {"error": str(exc)}

            # Append new evidence, if any
            evidence = params.get("evidence")
            if evidence:
                try:
                    self._writer.append_theme_evidence(slug, evidence)
                except (ValueError, FileNotFoundError) as exc:
                    return {"error": str(exc)}

            return {
                "upserted": True,
                "created": False,
                "filename": updated_filename,
                "slug": slug,
                "note": "Frontmatter merged; evidence appended as a new block.",
            }

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

    def _merge_theme_frontmatter(
        self, slug: str, params: dict, existing_theme: dict
    ) -> str:
        """
        Rewrite only the YAML frontmatter of an existing theme note.
        Body (including the evidence log and resolution section) is
        preserved verbatim.  Returns the relative filename.
        """
        from .parser import split_frontmatter
        from .renderer import _yaml_scalar, _yaml_int_list, _yaml_string_list

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
        try:
            results["summary_filename"] = self._writer.write_moment({
                "title": summary["title"],
                "body": summary["body"],
                "linked_runs": summary.get("linked_runs") or [],
                "linked_themes": summary.get("linked_themes") or [],
                "tags": (summary.get("tags") or []) + ["session-summary"],
                "date": summary.get("date"),
            })
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
        except Exception:  # pragma: no cover
            pass

        if not self._storage.get_note(filename):
            return {"error": f"Note not found in vault index: {filename}"}

        visited: dict[str, dict] = {}
        edges: list[dict] = []
        frontier = {filename}

        for hop in range(depth):
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
                    for l in self._storage.get_outgoing_links(node):
                        tgt = l["target"]
                        edges.append({"source": node, "target": tgt, "direction": "out"})
                        next_frontier.add(tgt)
                if direction in ("in", "both"):
                    for l in self._storage.get_incoming_links(node):
                        src = l["source"]
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

def _domain_for_kind(kind: Optional[str]) -> Optional[str]:
    """Map a note kind to its storage domain; None means 'all domains'."""
    if kind in ("theme", "moment"):
        return "vault"
    if kind in ("run_report", "trend_report", "compare_runs"):
        return "running"
    return None


def _title_from_filename(filename: str) -> str:
    base = filename.rsplit("/", 1)[-1]
    if base.endswith(".md"):
        base = base[:-3]
    return base.replace("-", " ").strip()
