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
"""

import logging
from pathlib import Path
from typing import Optional

from ..framework.interfaces import ToolDefinition, ValidationSchema
from .storage import VaultStorage
from .writer import VaultWriter, _is_relative_to

log = logging.getLogger("biosensor-mcp.vault")

# Max chars for vault_annotate_run notes
_MAX_NOTES_CHARS = 2000


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
                "Primary session orientation tool. Returns weekly fitness table "
                "aggregated from vault notes — no Strava sync needed. "
                "Call this first in a new session to orient yourself. ~400 tokens.",
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
                "type, and whether insight notes exist.",
                {
                    "note_type": {
                        "type": "string",
                        "description": "Filter: run_report | trend_report | compare_runs",
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
        ]

    @property
    def param_schemas(self) -> dict[str, dict[str, ValidationSchema]]:
        return {
            "vault_get_fitness_summary": {
                "weeks_back": ValidationSchema(type=int, min=1, max=52, default=8),
            },
            "vault_list_notes": {
                "note_type": ValidationSchema(
                    type=str,
                    allowed_values=["run_report", "trend_report", "compare_runs"],
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
                "note_type": ValidationSchema(type=str),
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
        Primary session orientation: aggregate fitness snapshot from vault notes.
        No Strava sync required.
        """
        weeks_back = params.get("weeks_back", 8)
        from datetime import datetime, timedelta, timezone
        cutoff = (datetime.now(timezone.utc) - timedelta(weeks=weeks_back)).strftime("%Y-%m-%d")

        notes = self._storage.list_notes(
            note_type="run_report",
            date_from=cutoff,
            limit=200,
        )

        if not notes:
            total = self._storage.count_notes(domain="running")
            return {
                "summary": "No run notes found in the specified period.",
                "total_notes_in_vault": total,
                "weeks_back": weeks_back,
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
            "note": (
                "Aggregated from vault note frontmatter. "
                "Insight columns show how many notes in each week have annotations."
            ),
        }

    async def _handle_list_notes(self, params: dict) -> dict:
        notes = self._storage.list_notes(
            domain="running",
            note_type=params.get("note_type"),
            date_from=params.get("date_from"),
            date_to=params.get("date_to"),
            has_insight_notes=params.get("has_insight_notes"),
            limit=params.get("limit", 20),
        )
        return {
            "count": len(notes),
            "notes": [
                {
                    "filename": n["filename"],
                    "note_type": n["note_type"],
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
        note_type = params.get("note_type")
        limit = params.get("limit", 10)

        candidates = self._storage.list_notes(
            domain="running",
            note_type=note_type,
            limit=500,
        )

        matches = []
        for n in candidates:
            try:
                abs_path = (self._vault_path / n["filename"]).resolve()
                if not abs_path.exists():
                    continue
                content = abs_path.read_text(encoding="utf-8").lower()
                if query in content:
                    # Find context snippet around the match
                    idx = content.find(query)
                    start = max(0, idx - 100)
                    end = min(len(content), idx + 100)
                    snippet = "..." + content[start:end].replace("\n", " ") + "..."
                    matches.append({
                        "filename": n["filename"],
                        "date": n["date"],
                        "note_type": n["note_type"],
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
