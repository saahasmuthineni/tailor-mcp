"""
Template Child MCP — ChildMCP Implementation Skeleton
========================================================
Copy this file to ``src/tailor/children/<yourdomain>/child.py``,
rename ``TemplateChild`` to ``<Yourdomain>Child``, and work through
the ``# FILL IN:`` markers.

The five substantive "blanks" (in order):

1. ``domain`` / ``display_name``
2. ``consent_info``
3. ``__init__`` — wire your data source (API client, BaseStorage
   subclass, file reader, etc.)
4. ``tool_definitions`` / ``param_schemas`` — rename the five stub
   tools to match your domain and adjust schemas
5. The ``execute()`` handler bodies

For a complete worked example, read
``src/tailor/children/running/child.py``. This template is
the distilled shape of that file without the Strava-specific glue.
"""

from __future__ import annotations

import logging
from pathlib import Path

from ...framework.interfaces import (
    ENTITY_ID_PARAM_DOC,
    ENTITY_ID_SCHEMA,
    ChildMCP,
    ConsentInfo,
    ConsentScope,
    CostEstimate,
    ToolDefinition,
    ValidationSchema,
)
from .processing import TemplateProcessing

log = logging.getLogger("tailor.template")

# ENTITY_ID_SCHEMA / ENTITY_ID_PARAM_DOC are imported from framework
# (see ADR 0002). Promoted in v6.2 so every child references the same
# definition; previously the constants were re-declared per-child.


# The stream names this template "exposes" in its Tier-2 and Tier-3
# tools. In a real child, this would be something like
# ``["heartrate", "glucose", "accelerometer_x", ...]`` — whatever
# your source produces.
ALL_STREAM_TYPES = ["signal_a", "signal_b"]


# ─────────────────────────────────────────────────────────────────
# OPTIONAL: domain-specific storage.
#
# Real children usually subclass ``BaseStorage`` from
# ``tailor.framework.storage`` for a thread-safe SQLite
# cache with WAL. A sketch looks like:
#
#     from ...framework.storage import BaseStorage
#
#     class TemplateStorage(BaseStorage):
#         def _schema_sql(self) -> str:
#             return '''
#                 CREATE TABLE IF NOT EXISTS records (
#                     id INTEGER PRIMARY KEY,
#                     data TEXT NOT NULL
#                 );
#             '''
#
# See ``running/child.py::RunningStorage`` for a full example.
# The template keeps a small in-memory ``self._fixtures`` dict
# instead, so that this skeleton can be instantiated end-to-end
# in a test without touching disk.
# ─────────────────────────────────────────────────────────────────


class TemplateChild(ChildMCP):
    """
    Template ChildMCP — five tools across all three tiers.

    | Tool                     | Tier | Purpose                           |
    |--------------------------|------|-----------------------------------|
    | ``example_list``         | 1    | Summary list of records           |
    | ``example_detail``       | 1    | Single-record detail              |
    | ``example_summary_report`` | 1  | Server-computed report (vaultable)|
    | ``example_downsampled``  | 2    | Downsampled stream (consent-gated)|
    | ``example_raw_stream``   | 3    | Raw per-sample stream (cost-gated)|

    Rename ``example_*`` to ``<yourdomain>_*`` when you fork this.
    The ``example_`` prefix is a grep anchor — if it still appears
    anywhere in your code after you finish, you forgot to rename
    something.
    """

    def __init__(self, config_dir: Path, data_dir: Path):
        # FILL IN: wire your data source here.
        # Real children typically own:
        #   - an API client (see ``running/strava_api.py``)
        #   - a ``BaseStorage`` subclass (see ``running/child.py::RunningStorage``)
        #   - optional user-config loading (max_hr, thresholds, etc.)
        self._config_dir = config_dir
        self._data_dir = data_dir
        self._processing = TemplateProcessing()

        # In-memory fixtures so this skeleton runs end-to-end in tests
        # without disk or network. Replace with real storage queries
        # in your child.
        self._fixtures: dict[int, dict] = {
            1: {
                "id": 1,
                "name": "Example Record A",
                "recorded_at": "2026-01-01T10:00:00Z",
                "signal_a": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
                "signal_b": [0.5, 0.7, 0.9, 1.1, 1.3, 1.5, 1.7, 1.9, 2.1, 2.3],
            },
            2: {
                "id": 2,
                "name": "Example Record B",
                "recorded_at": "2026-01-02T10:00:00Z",
                "signal_a": [10.0, 9.0, 8.0, 7.0, 6.0, 5.0, 4.0, 3.0, 2.0, 1.0],
                "signal_b": [2.3, 2.1, 1.9, 1.7, 1.5, 1.3, 1.1, 0.9, 0.7, 0.5],
            },
        }
        log.info(f"Template child initialized (records={len(self._fixtures)})")

    # ══════════════════════════════════════════════════════════
    # IDENTITY
    # ══════════════════════════════════════════════════════════

    @property
    def domain(self) -> str:
        # FILL IN: RENAME ME. Short lower-case identifier, unique
        # across all registered children. e.g. "cgm", "sleep", "ecg".
        return "example"

    @property
    def display_name(self) -> str:
        # FILL IN: RENAME ME. Human-readable label shown in the
        # consent prompt. e.g. "Glucose (Dexcom)".
        return "Example Domain (Template)"

    @property
    def vaultable_tools(self) -> list[str]:
        """
        Tools whose results become durable vault notes.

        Criterion: is this the kind of analytical output a
        researcher would cite, revisit, or compare across
        sessions? Server-computed reports usually qualify; raw
        stream dumps and transient lookups usually don't.
        """
        return ["example_summary_report"]

    # ══════════════════════════════════════════════════════════
    # CONSENT
    # ══════════════════════════════════════════════════════════

    @property
    def consent_info(self) -> ConsentInfo:
        # FILL IN: describe exactly what data this domain exposes
        # and why. The router uses this to build both the user-
        # facing consent prompt and the structured ``LLMInstruction``
        # (see ADR 0004).
        return ConsentInfo(
            data_types=["example signal A", "example signal B"],
            purpose="illustrate the consent prompt shape for a new child",
            scope=ConsentScope(
                duration="session",
                duration_human="until this conversation ends",
                covers_future_calls=True,
                revocable=True,
                # FILL IN: phrase the revoke instruction in terms
                # natural for your domain. "Say 'revoke CGM consent'..."
                revoke_instruction="Say 'revoke example consent' at any time.",
            ),
        )

    # Map a stream name to the subset of ``consent_info.data_types``
    # it actually covers. Used by ``data_types_for_tool`` to narrow
    # consent scope per-call on the streams tools.
    _STREAM_DATA_MAP: dict[str, list[str]] = {
        "signal_a": ["example signal A"],
        "signal_b": ["example signal B"],
    }

    def data_types_for_tool(self, tool_name: str, params: dict) -> list[str]:
        """
        Narrow consent scope per-call for the streams tools.

        If the caller only asked for ``signal_a``, only "example
        signal A" should appear in the consent prompt — not every
        data type this domain could theoretically touch.
        """
        if tool_name in ("example_downsampled", "example_raw_stream"):
            requested = params.get("streams")
            if requested:
                types: set[str] = set()
                for stream in requested:
                    types.update(self._STREAM_DATA_MAP.get(stream, []))
                if types:
                    return sorted(types)
        return self.consent_info.data_types

    # ══════════════════════════════════════════════════════════
    # TOOL SURFACE
    # ══════════════════════════════════════════════════════════

    @property
    def tool_definitions(self) -> list[ToolDefinition]:
        # FILL IN: rename each tool to match your domain; adjust
        # descriptions and params as needed. Keep the tier
        # distribution (a handful of Tier-1, maybe one Tier-2,
        # maybe one Tier-3) unless you have a strong reason — the
        # access tiers are the load-bearing data-minimization
        # mechanism; see CLAUDE.md.
        return [
            # ── Tier 1: Free (server-computed reports) ──
            ToolDefinition(
                "example_list", 1,
                "List available records with summary stats. ~200 tokens.",
                {
                    "limit": {"type": "integer", "description": "Max results (default 20)", "required": False},
                    "entity_id": ENTITY_ID_PARAM_DOC,
                },
            ),
            ToolDefinition(
                "example_detail", 1,
                "Get full details for a single record.",
                {
                    "record_id": {"type": "integer", "description": "Record ID", "required": True},
                    "entity_id": ENTITY_ID_PARAM_DOC,
                },
            ),
            ToolDefinition(
                "example_summary_report", 1,
                "Server-computed summary report over a record's signals. "
                "No raw samples leave the server. ~500 tokens.",
                {
                    "record_id": {"type": "integer", "description": "Record ID", "required": True},
                    "entity_id": ENTITY_ID_PARAM_DOC,
                },
            ),
            # ── Tier 2: Consent-gated (downsampled streams) ──
            ToolDefinition(
                "example_downsampled", 2,
                "Downsampled stream for visualization. ~3000-7000 tokens. "
                "Requires biometric consent.",
                {
                    "record_id": {"type": "integer", "description": "Record ID", "required": True},
                    "interval": {
                        "type": "integer",
                        "description": "Decimation interval (every Nth sample). Default 5.",
                        "required": False,
                    },
                    "streams": {
                        "type": "array",
                        "description": f"Which streams to include: {', '.join(ALL_STREAM_TYPES)}. Default: all.",
                        "required": False,
                    },
                    "entity_id": ENTITY_ID_PARAM_DOC,
                },
            ),
            # ── Tier 3: Cost-gated (raw per-sample streams) ──
            ToolDefinition(
                "example_raw_stream", 3,
                "Raw per-sample stream. ~25k-60k tokens. "
                "Requires consent + cost approval if over threshold.",
                {
                    "record_id": {"type": "integer", "description": "Record ID", "required": True},
                    "streams": {
                        "type": "array",
                        "description": f"Which streams: {', '.join(ALL_STREAM_TYPES)}. Default: all.",
                        "required": False,
                    },
                    "entity_id": ENTITY_ID_PARAM_DOC,
                },
            ),
        ]

    @property
    def param_schemas(self) -> dict[str, dict[str, ValidationSchema]]:
        # FILL IN: every tool in ``tool_definitions`` must have a
        # matching entry here. Every entry must include
        # ``"entity_id": ENTITY_ID_SCHEMA`` (ADR 0002 — caught by
        # ``test_template_shape.py::TestEntityIdConsistency``).
        return {
            "example_list": {
                "limit": ValidationSchema(type=int, min=1, max=100, default=20),
                "entity_id": ENTITY_ID_SCHEMA,
            },
            "example_detail": {
                "record_id": ValidationSchema(type=int, min=1, required=True),
                "entity_id": ENTITY_ID_SCHEMA,
            },
            "example_summary_report": {
                "record_id": ValidationSchema(type=int, min=1, required=True),
                "entity_id": ENTITY_ID_SCHEMA,
            },
            "example_downsampled": {
                "record_id": ValidationSchema(type=int, min=1, required=True),
                "interval": ValidationSchema(type=int, min=1, max=60, default=5),
                "streams": ValidationSchema(type=list, allowed_values=ALL_STREAM_TYPES),
                "entity_id": ENTITY_ID_SCHEMA,
            },
            "example_raw_stream": {
                "record_id": ValidationSchema(type=int, min=1, required=True),
                "streams": ValidationSchema(type=list, allowed_values=ALL_STREAM_TYPES),
                "entity_id": ENTITY_ID_SCHEMA,
            },
        }

    # ══════════════════════════════════════════════════════════
    # COST ESTIMATION (pre-execution, cheap)
    # ══════════════════════════════════════════════════════════

    async def estimate_cost(self, tool_name: str, params: dict) -> CostEstimate:
        """
        Estimate token cost BEFORE execution. See ADR 0005.

        Keep this cheap: read metadata/counts, never the full
        payload. Return ``CostEstimate(tokens=0)`` for tools where
        cost is negligible — the router will skip the cost gate.
        """
        # FILL IN: only the raw-stream tool is potentially expensive
        # enough to matter for the template. For your domain, also
        # estimate any other tool whose output scales with sample count.
        if tool_name != "example_raw_stream":
            return CostEstimate(tokens=0)

        # Illustrative only — real children should read stream
        # metadata (point counts) from storage and compute a
        # tokens-per-sample estimate. See
        # ``running/processing.py::estimate_stream_tokens``.
        return CostEstimate(
            tokens=40_000,
            has_cheaper_alternative=True,
            alternative_tokens=4_000,
            alternative_description=(
                "example_downsampled (every 5th sample) — "
                "preserves curve shape, ~10x cheaper"
            ),
        )

    def purge_cache(self, *, force: bool = False) -> dict:
        """
        Purge cached participant biometric data for this domain.
        See ADR 0013 — Cache-only purge on consent revocation.

        FILL IN: when you wire real storage above, replace this with
        a call into your storage layer that DELETEs from the tables
        holding raw biometric data (raw streams, raw activity rows)
        and PRESERVES analyst-authored tables (labels, annotations).
        Pattern: see ``running/child.py::RunningStorage.purge_biometric_cache``.
        Return rows_purged, tables_touched, preserved so the router's
        PURGE_CACHE audit row carries provenance.

        The skeleton has only an in-memory fixtures dict, so there
        is nothing on-disk to purge — return zero with a reason note.
        """
        return {
            "rows_purged": 0,
            "tables_touched": [],
            "preserved": [],
            "reason": (
                "TemplateChild ships with in-memory fixtures only; "
                "real children must DELETE rows from biometric tables "
                "and preserve analyst-authored tables here."
            ),
        }

    # ══════════════════════════════════════════════════════════
    # EXECUTION
    # ══════════════════════════════════════════════════════════

    async def execute(self, tool_name: str, params: dict) -> dict:
        """
        Dispatch to the correct handler.

        Params are already validated and cleaned by the router
        before this is called. The return value is wrapped by the
        router with a ``_meta`` provenance stamp.
        """
        handlers = {
            "example_list": self._handle_list,
            "example_detail": self._handle_detail,
            "example_summary_report": self._handle_summary_report,
            "example_downsampled": self._handle_downsampled,
            "example_raw_stream": self._handle_raw_stream,
        }
        handler = handlers.get(tool_name)
        if not handler:
            return {"error": f"Unknown tool: {tool_name}"}
        return await handler(params)

    # ── Tier 1 handlers ──

    async def _handle_list(self, params: dict) -> dict:
        # FILL IN: query your storage / API here. The echo
        # implementation just walks the in-memory fixtures.
        limit = params.get("limit", 20)
        records = list(self._fixtures.values())[:limit]
        return {
            "count": len(records),
            "records": [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "recorded_at": r["recorded_at"],
                }
                for r in records
            ],
        }

    async def _handle_detail(self, params: dict) -> dict:
        # FILL IN: look up a single record by id. Echo implementation:
        record = self._fixtures.get(params["record_id"])
        if not record:
            return {"error": f"Record {params['record_id']} not found"}
        return {
            "id": record["id"],
            "name": record["name"],
            "recorded_at": record["recorded_at"],
            "signal_a_samples": len(record["signal_a"]),
            "signal_b_samples": len(record["signal_b"]),
        }

    async def _handle_summary_report(self, params: dict) -> dict:
        # FILL IN: compute whatever server-side analytics matter
        # for your domain. This is the tool whose result becomes a
        # vault note — so include fields an analyst would cite.
        record = self._fixtures.get(params["record_id"])
        if not record:
            return {"error": f"Record {params['record_id']} not found"}
        return {
            "id": record["id"],
            "name": record["name"],
            "signal_a": self._processing.summarize(record["signal_a"]),
            "signal_b": self._processing.summarize(record["signal_b"]),
        }

    # ── Tier 2 handler (consent-gated) ──

    async def _handle_downsampled(self, params: dict) -> dict:
        record = self._fixtures.get(params["record_id"])
        if not record:
            return {"error": f"Record {params['record_id']} not found"}
        interval = params.get("interval", 5)
        requested = params.get("streams") or ALL_STREAM_TYPES
        out: dict = {"id": record["id"], "interval": interval, "streams": {}}
        for stream in requested:
            if stream in record:
                out["streams"][stream] = self._processing.downsample(
                    record[stream], interval
                )
        return out

    # ── Tier 3 handler (cost-gated) ──

    async def _handle_raw_stream(self, params: dict) -> dict:
        record = self._fixtures.get(params["record_id"])
        if not record:
            return {"error": f"Record {params['record_id']} not found"}
        requested = params.get("streams") or ALL_STREAM_TYPES
        return {
            "id": record["id"],
            "streams": {
                stream: record[stream]
                for stream in requested
                if stream in record
            },
        }
