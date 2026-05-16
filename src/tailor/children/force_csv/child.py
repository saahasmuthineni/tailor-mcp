"""
Force-CSV Child MCP — Load-Cell Force Traces (20-100 Hz)
=========================================================
ChildMCP for force-trace CSV files from a load cell — HUMAC,
BIOPAC, custom MR-conditional dynamometers per Wang & Senefeld
2026.  Single-channel force is the typical case at HIP-Lab-shape
rates (20-100 Hz × 1 channel); multi-channel is supported but not
canonical.

This child is the first node in a planned data-source family
(``force_csv``, future ``emg_csv``, future ``mrs_*``) that
composes via shared ``subject_id`` (ADR 0009), shared audit log
(ADR 0001), and the existing ``dispatch_internal`` cross-child
seam.  Composition is the load-bearing architectural argument
for the broader Senefeld-meeting demo.

Architectural decisions baked in:

- **Path B caching for analyst-authored labels only.** The
  framework owns a small SQLite ``force_event_labels`` table
  (mirrors RunningStorage.stop_labels).  ``purge_cache``
  PRESERVES labels on consent revocation per ADR 0013 — they
  are analyst-authored interpretive content, not participant
  biometric data.  This is the IRB-meaningful "annotations stay,
  biometric cache disappears" demo.
- **No biometric-data caching.** Source CSV files are read on
  demand; no derivative force-data cache.  Honest at the
  framework boundary; institutional retention applies to the
  source files.
- **``close()`` is real, not a stub.** Releases SQLite WAL on
  shutdown — required for Windows correctness (CLAUDE.md
  Implementation Notes).
- **``_load_user_config()`` modeled** on RunningChild so the
  convention is consistent across children.
- **Tier-1 ``note`` annotations** on every Tier-1 result —
  LLM-facing affordance making the tier discipline visible
  inside the payload itself.
- **Bland-Altman as a first-class Tier-1 tool** — directly
  mirrors the device-validation work HIP Lab publishes.
- **CSV-iteration helpers mirror ``csv_dir/child.py``.** The
  ``_resolve_file``, ``_read_csv``, ``_load_metadata_sidecar``,
  ``_extract_timestamps`` helpers are intentionally copied (not
  extracted to a shared module) per the project's premature-
  abstraction discipline — the third child (``emg_csv``) will
  be the right time to lift these into a shared module.
"""

from __future__ import annotations

import csv
import io
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from ...framework.audit import _loads
from ...framework.interfaces import (
    SUBJECT_ID_PARAM_DOC,
    SUBJECT_ID_SCHEMA,
    ChildMCP,
    ConsentInfo,
    ConsentScope,
    CostEstimate,
    ToolDefinition,
    ValidationSchema,
)
from ...framework.storage import BaseStorage
from ..csv_dir.processing import COHORT_METRICS, CSVProcessing
from .processing import ForceCsvProcessing

log = logging.getLogger("tailor.force_csv")

# Default column vocabulary for Tier-2 / Tier-3 narrowing.  Real
# deployments declare their own column names in user_config.json;
# the placeholder lists the typical single-channel force case
# plus the most common multi-channel additions (force_left,
# force_right) for bilateral dynamometers.
ALL_STREAM_TYPES = ["force", "force_left", "force_right"]

# Controlled vocabulary for protocol-event labels.  The Wang &
# Senefeld 2026 plantarflexor protocol reference shape:
#   baseline_mvc → sustained_start → mvc_probe (× N) → task_failure
# The vocabulary is open by design (analysts can pass other
# strings) — this constant exists for documentation, not enforcement.
PROTOCOL_EVENT_TYPES = (
    "baseline_mvc",
    "sustained_start",
    "mvc_probe",
    "task_failure",
    "rest_period_start",
    "other",
)

# Tier-3 raw-window cap.  At 100 Hz × 1 channel × 60s ≈ 6000
# samples ≈ ~15k tokens — under cost gate, safe.  Larger windows
# trigger CostGate naturally; this cap pre-empts confusing cost-
# gate dialogs at obviously-too-long requests.
MAX_WINDOW_SECONDS = 60.0

# Filename-safe pattern for file_id parameter — rejects path
# traversal sequences (no slashes, no '..' via pattern). Mirrors
# csv_dir/child.py.
FILE_ID_PATTERN = r"^[A-Za-z0-9_\-\.]{1,255}$"

# Maximum file size (bytes) the child will load into memory.
# At 100 Hz × 8 cols × ~30 bytes/row ≈ 24 KB/sec; 100 MB ≈ 70
# minutes of data. Mirrors csv_dir/child.py.
MAX_CSV_BYTES = 100 * 1024 * 1024  # 100 MB

# Upper bound on number of CSVs scanned in a single call. Tuned
# for typical pilot-study scale (5-20 participants per ADR 0009).
MAX_COHORT_FILES = 64

# Sidecar metadata filename. Optional; force_cohort_summary
# requires it (mirrors csv_dir/ADR 0015 contract).
METADATA_FILENAME = "metadata.json"


# ═══════════════════════════════════════════════════════════════
# FORCE-CSV STORAGE (analyst-authored labels only)
# ═══════════════════════════════════════════════════════════════

class ForceCsvStorage(BaseStorage):
    """
    SQLite cache for ``force_csv`` — analyst-authored protocol-
    event labels only.  The schema mirrors RunningStorage's
    ``stop_labels`` pattern: small table, analyst-authored
    interpretive content, preserved on consent revocation per
    ADR 0013 § Decision.

    No biometric data is cached here.  Force-trace CSV files
    live on the analyst's machine and are read on demand.
    """

    def _schema_sql(self) -> str:
        return """
            CREATE TABLE IF NOT EXISTS force_event_labels (
                file_id TEXT NOT NULL,
                t_seconds REAL NOT NULL,
                event_type TEXT NOT NULL,
                label TEXT NOT NULL,
                notes TEXT,
                labeled_at TEXT NOT NULL,
                subject_id TEXT,
                PRIMARY KEY (file_id, t_seconds, event_type)
            );
        """

    def save_label(
        self,
        file_id: str,
        t_seconds: float,
        event_type: str,
        label: str,
        notes: str | None = None,
        subject_id: str | None = None,
    ) -> None:
        self.execute(
            "INSERT OR REPLACE INTO force_event_labels"
            " (file_id, t_seconds, event_type, label, notes, labeled_at, subject_id)"
            " VALUES (?,?,?,?,?,?,?)",
            (
                file_id,
                t_seconds,
                event_type,
                label,
                notes,
                datetime.now(timezone.utc).isoformat(),
                subject_id,
            ),
        )
        self.commit()

    def get_labels(
        self, file_id: str, subject_id: str | None = None,
    ) -> list[dict]:
        if subject_id is None:
            rows = self.fetchall(
                "SELECT t_seconds, event_type, label, notes, labeled_at, subject_id"
                " FROM force_event_labels WHERE file_id = ?"
                " ORDER BY t_seconds",
                (file_id,),
            )
        else:
            # ADR 0009 IS-NULL-or-match filter so cross-subject
            # legacy rows stay visible.
            rows = self.fetchall(
                "SELECT t_seconds, event_type, label, notes, labeled_at, subject_id"
                " FROM force_event_labels"
                " WHERE file_id = ? AND (subject_id IS NULL OR subject_id = ?)"
                " ORDER BY t_seconds",
                (file_id, subject_id),
            )
        return [
            {
                "t_seconds": r[0],
                "event_type": r[1],
                "label": r[2],
                "notes": r[3],
                "labeled_at": r[4],
                "subject_id": r[5],
            }
            for r in rows
        ]

    def label_count(self) -> int:
        row = self.fetchone("SELECT COUNT(*) FROM force_event_labels")
        return int(row[0]) if row else 0


# ═══════════════════════════════════════════════════════════════
# CHILD IMPLEMENTATION
# ═══════════════════════════════════════════════════════════════

class ForceCsvChild(ChildMCP):
    """
    Force-trace CSV ingest child.  9 tools across 3 tiers.

    | Tool                          | Tier | Purpose                                   |
    |-------------------------------|------|-------------------------------------------|
    | ``force_list_files``          | 1    | List trial files with sample-rate metadata|
    | ``force_file_detail``         | 1    | Per-file metadata + per-column summary    |
    | ``force_summary``             | 1    | Peak / decline / time-to-50pct-drop       |
    | ``force_cohort_summary``      | 1    | Cross-file aggregation by sidecar group   |
    | ``force_compare_trials``      | 1    | Side-by-side comparison of 2-5 trials     |
    | ``force_device_agreement``    | 1    | Bland-Altman paired-device validation     |
    | ``force_label_event``         | 1    | Analyst-authored protocol-event annotation|
    | ``force_downsampled``         | 2    | Decimated streams for visualization       |
    | ``force_raw_window``          | 3    | Raw samples within a bounded time window  |
    """

    def __init__(self, config_dir: Path, data_dir: Path):
        self._config_dir = config_dir
        self._data_dir = data_dir
        self._processing = ForceCsvProcessing()
        self._csv_processing = CSVProcessing()  # for shared helpers
        self._storage = ForceCsvStorage(data_dir / "force_csv.db")

        cfg = self._load_user_config().get("force_csv", {})
        raw_path = cfg.get("path")
        self._csv_dir: Path | None = (
            Path(raw_path).expanduser().resolve() if raw_path else None
        )
        if self._csv_dir is not None and not self._csv_dir.is_dir():
            log.warning(
                f"force_csv.path does not exist or is not a directory: "
                f"{self._csv_dir}. Tools will return errors until the "
                f"directory is created."
            )
        self._timestamp_column: str | None = cfg.get("timestamp_column")
        self._timestamp_format: str | None = cfg.get("timestamp_format")
        self._sample_rate_hz: float | None = cfg.get("sample_rate_hz")
        self._value_columns: dict[str, str] = cfg.get("value_columns", {})
        self._default_force_column: str = self._value_columns.get(
            "force", "force",
        )
        log.info(
            f"ForceCsvChild initialized "
            f"(csv_dir={self._csv_dir}, sample_rate_hz={self._sample_rate_hz}, "
            f"labels_in_storage={self._storage.label_count()})"
        )

    def _load_user_config(self) -> dict:
        """
        Load user-specific settings from ~/.tailor/user_config.json.

        Mirrors RunningChild._load_user_config so the convention
        is consistent.  Supported keys under ``force_csv``:

          path              — directory of force CSV files
          timestamp_column  — column name carrying timestamps
          timestamp_format  — strptime format if non-ISO
          sample_rate_hz    — declared sample rate (used for
                              cost estimation and MVC window math
                              when timestamps are absent)
          value_columns     — alias map {logical: actual_header},
                              ``force`` key sets the default for
                              force_summary / force_compare_trials
        """
        config_file = self._config_dir / "user_config.json"
        if config_file.exists():
            try:
                return _loads(config_file.read_text())
            except Exception as exc:
                log.warning(f"Could not read user_config.json: {exc}")
        return {}

    def close(self) -> None:
        """Release SQLite WAL on shutdown — required for Windows."""
        self._storage.close()

    def purge_cache(self, *, force: bool = False) -> dict:
        """
        Purge participant biometric cache on consent revocation.

        Per ADR 0013 — this child owns NO biometric cache (force
        CSVs are read from source files on the analyst's machine,
        not cached as derivative data).  The only thing in
        SQLite is the ``force_event_labels`` table — analyst-
        authored protocol-event annotations.

        Per ADR 0013 § Decision: analyst-authored interpretive
        content is PRESERVED on consent revocation (it is the
        analyst's professional product, not the participant's
        biometric data).  This mirrors RunningChild's preservation
        of ``stop_labels`` and is the IRB-meaningful demonstration
        of the cache-only-purge contract.

        Returns provenance: 0 rows purged, no tables touched,
        ``force_event_labels`` named in ``preserved`` so a future
        IRB query can confirm which tables this child considers
        analyst-authored vs biometric.
        """
        return {
            "rows_purged": 0,
            "tables_touched": [],
            "preserved": ["force_event_labels"],
            "reason": (
                "force_csv reads source CSV files on demand and "
                "owns no biometric cache.  The force_event_labels "
                "table holds analyst-authored protocol-event "
                "annotations and is preserved per ADR 0013 § "
                "Decision (analyst's professional product, not "
                "participant biometric data)."
            ),
        }

    @property
    def domain(self) -> str:
        return "force_csv"

    @property
    def display_name(self) -> str:
        return "Force trace (load cell)"

    @property
    def vaultable_tools(self) -> list[str]:
        """
        Tools whose results become durable vault notes.

        Per-file derived statistics (``force_summary``,
        ``force_file_detail``) and paired-device validation
        (``force_device_agreement``) are the kind of analytical
        output an analyst cites, revisits, and compares across
        sessions.

        Until paired renderers land in framework/vault/writer.py,
        registering here would emit "No renderer for tool"
        warnings on every successful call (per the
        vaultable-tool ↔ renderer contract enforced in
        tests/test_serve_mcp_protocol.py). Empty for now;
        renderer landing is a follow-on.
        """
        return []

    @property
    def consent_info(self) -> ConsentInfo:
        return ConsentInfo(
            data_types=["isometric force production"],
            purpose=(
                "neuromuscular performance and fatigability analysis "
                "(MVC strength, force decline, time to task failure, "
                "device-validation agreement)"
            ),
            scope=ConsentScope(
                duration="session",
                duration_human="until this conversation ends",
                covers_future_calls=True,
                revocable=True,
                revoke_instruction=(
                    "Say 'revoke force_csv consent' at any time."
                ),
            ),
        )

    _STREAM_DATA_MAP: dict[str, list[str]] = {
        "force": ["isometric force production"],
        "force_left": ["isometric force production"],
        "force_right": ["isometric force production"],
    }

    def data_types_for_tool(self, tool_name: str, params: dict) -> list[str]:
        if tool_name in ("force_downsampled", "force_raw_window"):
            requested = params.get("columns")
            if requested:
                types: set[str] = set()
                for col in requested:
                    types.update(self._STREAM_DATA_MAP.get(col, []))
                if types:
                    return sorted(types)
        return self.consent_info.data_types

    @property
    def tool_definitions(self) -> list[ToolDefinition]:
        return [
            # ── Tier 1: Free (server-computed reports) ──
            ToolDefinition(
                "force_list_files", 1,
                "List force trial files with sample-rate, channel count, "
                "and duration metadata. ~200 tokens.",
                {
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default 50)",
                        "required": False,
                    },
                    "subject_id": SUBJECT_ID_PARAM_DOC,
                },
            ),
            ToolDefinition(
                "force_file_detail", 1,
                "Per-file metadata + per-column summary statistics + any "
                "analyst-authored protocol-event labels for this file. "
                "~500 tokens.",
                {
                    "file_id": {
                        "type": "string",
                        "description": "Filename within force_csv.path",
                        "required": True,
                    },
                    "subject_id": SUBJECT_ID_PARAM_DOC,
                },
            ),
            ToolDefinition(
                "force_summary", 1,
                "Per-file fatigability diagnostic: peak force (Sánchez 250 ms "
                "MVC window), time-to-50pct-drop, decline rate, total work. "
                "Computed server-side; no raw samples transmitted. ~300 tokens.",
                {
                    "file_id": {
                        "type": "string",
                        "description": "Filename within force_csv.path",
                        "required": True,
                    },
                    "force_column": {
                        "type": "string",
                        "description": (
                            "Column name carrying force values. "
                            "Defaults to force_csv.value_columns.force."
                        ),
                        "required": False,
                    },
                    "subject_id": SUBJECT_ID_PARAM_DOC,
                },
            ),
            ToolDefinition(
                "force_cohort_summary", 1,
                "Cross-file aggregation by metadata-sidecar group "
                "(matches csv_cohort_summary, ADR 0015). Reduces each "
                "trial to one scalar via metric, then aggregates by "
                "group. Requires metadata.json sidecar. ~600 tokens.",
                {
                    "group_by": {
                        "type": "string",
                        "description": "Metadata field to group by (e.g. 'sex', 'group').",
                        "required": True,
                    },
                    "value_column": {
                        "type": "string",
                        "description": (
                            "Numeric column to reduce per file. Use the "
                            "logical name from your force_csv.value_columns "
                            "config (e.g. 'force' for a force-trace column)."
                        ),
                        "required": True,
                    },
                    "metric": {
                        "type": "string",
                        "description": (
                            f"Per-file reducer. One of: {', '.join(COHORT_METRICS)}"
                        ),
                        "required": True,
                    },
                    "subject_id": SUBJECT_ID_PARAM_DOC,
                },
            ),
            ToolDefinition(
                "force_compare_trials", 1,
                "Side-by-side comparison of 2-5 trial files: peak, decline, "
                "time-to-50pct, total duration. ~800 tokens.",
                {
                    "file_ids": {
                        "type": "array",
                        "description": "List of 2-5 file IDs to compare",
                        "required": True,
                    },
                    "force_column": {
                        "type": "string",
                        "description": "Column carrying force values",
                        "required": False,
                    },
                    "subject_id": SUBJECT_ID_PARAM_DOC,
                },
            ),
            ToolDefinition(
                "force_device_agreement", 1,
                "Bland-Altman paired-device validation analysis. Given a "
                "list of paired (device_a_value, device_b_value) measurements "
                "on the same subjects, returns mean difference (bias), 95% "
                "limits of agreement, and per-pair differences for plotting. "
                "Mirrors the analysis Wang & Senefeld 2026 use for HUMAC vs "
                "MR-conditional dyno comparison. ~400 tokens.",
                {
                    "device_a_values": {
                        "type": "array",
                        "description": "Per-subject measurement from device A",
                        "required": True,
                    },
                    "device_b_values": {
                        "type": "array",
                        "description": "Per-subject measurement from device B (same length, same subject order)",
                        "required": True,
                    },
                    "device_a_label": {
                        "type": "string",
                        "description": "Human-readable name for device A (e.g. 'HUMAC')",
                        "required": False,
                    },
                    "device_b_label": {
                        "type": "string",
                        "description": "Human-readable name for device B (e.g. 'MR-conditional dyno')",
                        "required": False,
                    },
                    "metric_name": {
                        "type": "string",
                        "description": "What's being compared (e.g. 'baseline MVC', 'time to task failure')",
                        "required": False,
                    },
                    "subject_id": SUBJECT_ID_PARAM_DOC,
                },
            ),
            ToolDefinition(
                "force_label_event", 1,
                "Persist an analyst-authored protocol-event label for a "
                "specific timepoint in a file. Labels persist across sessions "
                "and are PRESERVED on consent revocation per ADR 0013 "
                "(analyst-authored, not biometric).",
                {
                    "file_id": {
                        "type": "string",
                        "description": "Filename within force_csv.path",
                        "required": True,
                    },
                    "t_seconds": {
                        "type": "number",
                        "description": "Timepoint in seconds from file start",
                        "required": True,
                    },
                    "event_type": {
                        "type": "string",
                        "description": (
                            f"Event category. Recommended vocabulary: "
                            f"{', '.join(PROTOCOL_EVENT_TYPES)}. Other strings allowed."
                        ),
                        "required": True,
                    },
                    "label": {
                        "type": "string",
                        "description": "Short human-readable label",
                        "required": True,
                    },
                    "notes": {
                        "type": "string",
                        "description": "Optional details",
                        "required": False,
                    },
                    "subject_id": SUBJECT_ID_PARAM_DOC,
                },
            ),
            # ── Tier 2: Consent-gated (downsampled streams) ──
            ToolDefinition(
                "force_downsampled", 2,
                "Decimated force stream at every Nth sample for visualization. "
                "~3000-7000 tokens. Requires biometric consent.",
                {
                    "file_id": {
                        "type": "string",
                        "description": "Filename within force_csv.path",
                        "required": True,
                    },
                    "interval": {
                        "type": "integer",
                        "description": "Decimation interval (default 10 — ~10 Hz from 100 Hz)",
                        "required": False,
                    },
                    "columns": {
                        "type": "array",
                        "description": (
                            f"Which columns to include: {', '.join(ALL_STREAM_TYPES)}. Default: force only."
                        ),
                        "required": False,
                    },
                    "subject_id": SUBJECT_ID_PARAM_DOC,
                },
            ),
            # ── Tier 3: Cost-gated (raw windowed streams) ──
            ToolDefinition(
                "force_raw_window", 3,
                f"Raw per-sample force data within a bounded time window. "
                f"Hard cap: {MAX_WINDOW_SECONDS} seconds (rejects obviously-"
                "too-long requests pre-empting the cost gate). Requires "
                "consent + cost approval if over threshold.",
                {
                    "file_id": {
                        "type": "string",
                        "description": "Filename within force_csv.path",
                        "required": True,
                    },
                    "start_seconds": {
                        "type": "number",
                        "description": "Window start (seconds from file start)",
                        "required": True,
                    },
                    "end_seconds": {
                        "type": "number",
                        "description": (
                            f"Window end (seconds). Must be within "
                            f"{MAX_WINDOW_SECONDS}s of start_seconds."
                        ),
                        "required": True,
                    },
                    "columns": {
                        "type": "array",
                        "description": (
                            f"Which columns: {', '.join(ALL_STREAM_TYPES)}. Default: force only."
                        ),
                        "required": False,
                    },
                    "subject_id": SUBJECT_ID_PARAM_DOC,
                },
            ),
        ]

    @property
    def param_schemas(self) -> dict[str, dict[str, ValidationSchema]]:
        return {
            "force_list_files": {
                "limit": ValidationSchema(type=int, min=1, max=500, default=50),
                "subject_id": SUBJECT_ID_SCHEMA,
            },
            "force_file_detail": {
                "file_id": ValidationSchema(
                    type=str, required=True, pattern=FILE_ID_PATTERN,
                ),
                "subject_id": SUBJECT_ID_SCHEMA,
            },
            "force_summary": {
                "file_id": ValidationSchema(
                    type=str, required=True, pattern=FILE_ID_PATTERN,
                ),
                "force_column": ValidationSchema(type=str),
                "subject_id": SUBJECT_ID_SCHEMA,
            },
            "force_cohort_summary": {
                "group_by": ValidationSchema(
                    type=str, required=True, pattern=r"^[A-Za-z0-9_\-]{1,64}$",
                ),
                "value_column": ValidationSchema(type=str, required=True),
                "metric": ValidationSchema(
                    type=str, required=True, allowed_values=list(COHORT_METRICS),
                ),
                "subject_id": SUBJECT_ID_SCHEMA,
            },
            "force_compare_trials": {
                "file_ids": ValidationSchema(
                    type=list, min_len=2, max_len=5, required=True,
                ),
                "force_column": ValidationSchema(type=str),
                "subject_id": SUBJECT_ID_SCHEMA,
            },
            "force_device_agreement": {
                "device_a_values": ValidationSchema(
                    type=list, min_len=2, max_len=500, required=True,
                ),
                "device_b_values": ValidationSchema(
                    type=list, min_len=2, max_len=500, required=True,
                ),
                "device_a_label": ValidationSchema(type=str),
                "device_b_label": ValidationSchema(type=str),
                "metric_name": ValidationSchema(type=str),
                "subject_id": SUBJECT_ID_SCHEMA,
            },
            "force_label_event": {
                "file_id": ValidationSchema(
                    type=str, required=True, pattern=FILE_ID_PATTERN,
                ),
                "t_seconds": ValidationSchema(type=float, min=0.0, required=True),
                "event_type": ValidationSchema(type=str, required=True),
                "label": ValidationSchema(type=str, required=True),
                "notes": ValidationSchema(type=str),
                "subject_id": SUBJECT_ID_SCHEMA,
            },
            "force_downsampled": {
                "file_id": ValidationSchema(
                    type=str, required=True, pattern=FILE_ID_PATTERN,
                ),
                "interval": ValidationSchema(type=int, min=1, max=10000, default=10),
                "columns": ValidationSchema(type=list, allowed_values=ALL_STREAM_TYPES),
                "subject_id": SUBJECT_ID_SCHEMA,
            },
            "force_raw_window": {
                "file_id": ValidationSchema(
                    type=str, required=True, pattern=FILE_ID_PATTERN,
                ),
                "start_seconds": ValidationSchema(type=float, min=0.0, required=True),
                "end_seconds": ValidationSchema(type=float, min=0.0, required=True),
                "columns": ValidationSchema(type=list, allowed_values=ALL_STREAM_TYPES),
                "subject_id": SUBJECT_ID_SCHEMA,
            },
        }

    # ══════════════════════════════════════════════════════════
    # COST ESTIMATION
    # ══════════════════════════════════════════════════════════

    async def estimate_cost(self, tool_name: str, params: dict) -> CostEstimate:
        """Metadata-driven estimate per ADR 0005 — file size and
        declared sample rate, never the full payload."""
        if tool_name != "force_raw_window":
            return CostEstimate(tokens=0)

        rate = self._sample_rate_hz or 100.0
        window_s = max(0.0, params["end_seconds"] - params["start_seconds"])
        col_count = len(params.get("columns") or ["force"])
        full_tokens = int(window_s * rate * col_count * 4)
        ds_tokens = max(int(full_tokens / 10), 1)  # default downsample interval=10

        return CostEstimate(
            tokens=full_tokens,
            has_cheaper_alternative=True,
            alternative_tokens=ds_tokens,
            alternative_description=(
                "force_downsampled (interval=10) — ~90% cheaper, "
                "preserves curve shape for visualization"
            ),
        )

    # ══════════════════════════════════════════════════════════
    # CSV-iteration helpers (mirror csv_dir/child.py)
    # ══════════════════════════════════════════════════════════

    def _resolve_file(self, file_id: str) -> Path | None:
        """Resolve file_id to path under csv_dir.  Returns None if
        the file doesn't exist or escapes the configured directory.

        Directory-traversal defense: ``relative_to`` raises if the
        resolved path leaves the configured root.
        """
        if not file_id or self._csv_dir is None:
            return None
        candidate = (self._csv_dir / file_id).resolve()
        try:
            candidate.relative_to(self._csv_dir)
        except ValueError:
            return None
        if not candidate.is_file():
            return None
        return candidate

    @staticmethod
    def _read_headers(filepath: Path) -> list[str]:
        """Read just the header row from a CSV file.

        ``utf-8-sig`` strips a leading byte-order mark transparently so
        an Excel- or PowerShell-redirected CSV does not silently get
        ``﻿t_s`` as its first header (v6.9.0 footgun on real-world
        recipient CSVs; bundled fixtures had no BOM and so the demo
        worked fine while production data would not).
        """
        try:
            with open(filepath, encoding="utf-8-sig", errors="replace", newline="") as f:
                reader = csv.reader(f)
                return next(reader, [])
        except OSError:
            return []

    @staticmethod
    def _read_csv(
        filepath: Path, *, max_bytes: int = 0,
    ) -> tuple[list[str], list[dict]]:
        """Read a CSV file.  Returns (headers, rows).

        ``utf-8-sig`` mirrors ``_read_headers`` for BOM transparency.
        """
        if max_bytes and filepath.stat().st_size > max_bytes:
            size_mb = filepath.stat().st_size / (1024 * 1024)
            limit_mb = max_bytes / (1024 * 1024)
            raise OSError(
                f"File is too large ({size_mb:.1f} MB, limit "
                f"{limit_mb:.1f} MB). Use force_downsampled "
                f"for large files."
            )
        with open(filepath, encoding="utf-8-sig", errors="replace", newline="") as f:
            raw = f.read()
        if "�" in raw:
            log.warning(
                f"{filepath.name} contains non-UTF-8 bytes "
                f"(replaced with �). Consider re-encoding the file."
            )
        reader = csv.DictReader(io.StringIO(raw))
        headers = list(reader.fieldnames or [])
        rows = list(reader)
        return headers, rows

    @staticmethod
    def _try_float(value: str) -> float | None:
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _numeric_values(self, rows: list[dict], column: str) -> list[float]:
        values: list[float] = []
        for row in rows:
            v = self._try_float(row.get(column) or "")
            if v is not None:
                values.append(v)
        return values

    def _extract_timestamps(self, rows: list[dict], headers: list[str]):
        """Best-effort timestamp column extraction; returns None if no
        usable timestamp column or if any row fails to parse.

        Two paths: (1) ISO-datetime strings via parse_timestamp; (2)
        float-seconds offsets via the v7.3.4 fallback below. The float-
        seconds path is the standard biomedical signal shape (``t_s``
        column = elapsed seconds from trial start) that the bundled
        HIP Lab fixtures use; without it, time-based fatigue metrics
        like ``time_to_50pct_drop_s`` and ``duration_s`` silently
        returned null on the cohort thesis hot path (mcp-protocol-
        auditor D1, v7.3.4)."""
        from datetime import datetime, timedelta, timezone
        ts_col = (
            self._timestamp_column
            or self._csv_processing.detect_timestamp_column(headers)
        )
        if not ts_col:
            return None
        parsed = []
        for r in rows:
            t = self._csv_processing.parse_timestamp(
                (r.get(ts_col) or ""), self._timestamp_format,
            )
            if t is None:
                break
            parsed.append(t)
        else:
            return parsed
        epoch = datetime(2000, 1, 1, tzinfo=timezone.utc)
        parsed = []
        for r in rows:
            v = r.get(ts_col)
            if v in (None, ""):
                return None
            try:
                offset_s = float(v)
            except (TypeError, ValueError):
                return None
            parsed.append(epoch + timedelta(seconds=offset_s))
        return parsed

    def _load_metadata_sidecar(
        self,
    ) -> tuple[dict[str, dict] | None, str | None]:
        """Read the optional ``metadata.json`` sidecar.

        ``utf-8-sig`` mirrors the CSV-read paths' BOM transparency
        (v6.9.2 — a recipient's ``metadata.json`` saved by Excel or
        PowerShell carries a UTF-8 BOM, which would silently drop the
        first key from the dict and break the cohort handler's
        filename lookup).
        """
        if self._csv_dir is None:
            return None, None
        sidecar = self._csv_dir / METADATA_FILENAME
        if not sidecar.is_file():
            return None, None
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            return None, f"could not read {METADATA_FILENAME}: {exc}"
        if not isinstance(data, dict):
            return None, (
                f"{METADATA_FILENAME} must be a JSON object mapping "
                f"filename to metadata fields"
            )
        for fname, meta in data.items():
            if not isinstance(meta, dict):
                return None, (
                    f"{METADATA_FILENAME}: entry for {fname!r} must be "
                    f"a JSON object of fields"
                )
        return data, None

    def _resolve_force_column(
        self, headers: list[str], requested: str | None,
    ) -> str | None:
        """Resolve which header carries force values.

        Order of preference:
          1. The ``force_column`` parameter if non-empty
          2. ``force_csv.value_columns.force`` from user_config
          3. A column literally named ``force``
          4. None (caller surfaces error)
        """
        if requested:
            return requested
        if self._default_force_column in headers:
            return self._default_force_column
        if "force" in headers:
            return "force"
        return None

    def _derive_sample_rate(
        self, timestamps, declared_rate: float | None,
    ) -> float | None:
        """Derive a sample rate. Prefer config; else infer from
        timestamp spacing."""
        if declared_rate and declared_rate > 0:
            return declared_rate
        if not timestamps or len(timestamps) < 2:
            return None
        deltas = [
            (timestamps[i + 1] - timestamps[i]).total_seconds()
            for i in range(len(timestamps) - 1)
        ]
        positive = [d for d in deltas if d > 0]
        if not positive:
            return None
        mean_delta = sum(positive) / len(positive)
        if mean_delta <= 0:
            return None
        return round(1.0 / mean_delta, 3)

    # ══════════════════════════════════════════════════════════
    # EXECUTION
    # ══════════════════════════════════════════════════════════

    async def execute(self, tool_name: str, params: dict) -> dict:
        handlers = {
            "force_list_files": self._handle_list_files,
            "force_file_detail": self._handle_file_detail,
            "force_summary": self._handle_force_summary,
            "force_cohort_summary": self._handle_cohort_summary,
            "force_compare_trials": self._handle_compare_trials,
            "force_device_agreement": self._handle_device_agreement,
            "force_label_event": self._handle_label_event,
            "force_downsampled": self._handle_downsampled,
            "force_raw_window": self._handle_raw_window,
        }
        handler = handlers.get(tool_name)
        if not handler:
            return {"error": f"Unknown tool: {tool_name}"}
        return await handler(params)

    # ── Tier 1 handlers ──

    async def _handle_list_files(self, params: dict) -> dict:
        if self._csv_dir is None:
            return {"error": "force_csv.path not configured in user_config.json"}
        if not self._csv_dir.is_dir():
            return {"error": f"force_csv directory not found: {self._csv_dir}"}

        limit = params.get("limit", 50)
        files = sorted(self._csv_dir.glob("*.csv"))[:limit]
        results = []
        for f in files:
            headers = self._read_headers(f)
            results.append({
                "filename": f.name,
                "size_bytes": f.stat().st_size,
                "columns": headers,
            })
        return {
            "csv_dir": str(self._csv_dir),
            "sample_rate_hz": self._sample_rate_hz,
            "count": len(results),
            "files": results,
            "note": (
                "Computed server-side from filesystem listing — no raw "
                "samples transmitted."
            ),
        }

    async def _handle_file_detail(self, params: dict) -> dict:
        filepath = self._resolve_file(params["file_id"])
        if not filepath:
            return {"error": f"File not found: {params['file_id']}"}

        try:
            headers, rows = self._read_csv(filepath, max_bytes=MAX_CSV_BYTES)
        except OSError as exc:
            return {"error": str(exc)}

        ts_col = (
            self._timestamp_column
            or self._csv_processing.detect_timestamp_column(headers)
        )
        column_stats: dict[str, dict] = {}
        for col in headers:
            if col == ts_col:
                continue
            values = self._numeric_values(rows, col)
            if values:
                column_stats[col] = self._csv_processing.summarize_column(values)
            else:
                column_stats[col] = {"count": len(rows), "type": "non-numeric"}

        timestamps = self._extract_timestamps(rows, headers)
        duration_s: float | None = None
        if timestamps and len(timestamps) >= 2:
            duration_s = round(
                (timestamps[-1] - timestamps[0]).total_seconds(), 3,
            )
        sample_rate = self._derive_sample_rate(timestamps, self._sample_rate_hz)

        labels = self._storage.get_labels(
            params["file_id"], subject_id=params.get("subject_id"),
        )
        result: dict = {
            "filename": filepath.name,
            "row_count": len(rows),
            "columns": headers,
            "column_stats": column_stats,
            "duration_s": duration_s,
            "sample_rate_hz": sample_rate,
            "event_labels": labels,
            "label_count": len(labels),
            "note": (
                "Computed server-side. Per-column summary + analyst-"
                "authored event labels; no raw samples transmitted."
            ),
        }
        if ts_col and rows:
            first_ts = self._csv_processing.parse_timestamp(
                rows[0].get(ts_col, ""), self._timestamp_format,
            )
            last_ts = self._csv_processing.parse_timestamp(
                rows[-1].get(ts_col, ""), self._timestamp_format,
            )
            if first_ts and last_ts:
                result["time_range"] = {
                    "start": first_ts.isoformat(),
                    "end": last_ts.isoformat(),
                }
        return result

    async def _handle_force_summary(self, params: dict) -> dict:
        filepath = self._resolve_file(params["file_id"])
        if not filepath:
            return {"error": f"File not found: {params['file_id']}"}

        try:
            headers, rows = self._read_csv(filepath, max_bytes=MAX_CSV_BYTES)
        except OSError as exc:
            return {"error": str(exc)}

        force_column = self._resolve_force_column(
            headers, params.get("force_column"),
        )
        if force_column is None or force_column not in headers:
            return {
                "error": (
                    f"force column not found. Tried: "
                    f"{params.get('force_column') or self._default_force_column}. "
                    f"Available columns: {headers}"
                ),
            }

        values = self._numeric_values(rows, force_column)
        if not values:
            return {
                "error": (
                    f"No numeric values in column {force_column!r} "
                    f"for {filepath.name}"
                ),
            }
        timestamps = self._extract_timestamps(rows, headers)
        sample_rate = self._derive_sample_rate(timestamps, self._sample_rate_hz)

        decline = self._csv_processing.force_decline_summary(values, timestamps)
        mvc_window = (
            self._processing.mvc_window_mean(values, sample_rate)
            if sample_rate
            else None
        )

        return {
            "filename": filepath.name,
            "force_column": force_column,
            "sample_rate_hz": sample_rate,
            "n_samples": len(values),
            "peak": decline.get("peak"),
            "mvc_window_mean_250ms": mvc_window,
            "end_value": decline.get("end_value"),
            "decline_pct": decline.get("decline_pct_total"),
            "decline_rate_per_min": decline.get("decline_rate_per_min"),
            "time_to_50pct_drop_s": decline.get("time_to_50pct_drop_s"),
            "duration_s": decline.get("duration_s"),
            "note": (
                "Computed server-side via load-and-reduce pass. MVC "
                "uses Sánchez-2015 250 ms window definition (mean over "
                "window centered on peak, not instantaneous peak). "
                "Decline metrics share the v6.8.1 last-peak-tie fix "
                "from CSVProcessing. No raw samples transmitted."
            ),
        }

    async def _handle_cohort_summary(self, params: dict) -> dict:
        if self._csv_dir is None:
            return {"error": "force_csv.path not configured"}
        if not self._csv_dir.is_dir():
            return {"error": f"force_csv directory not found: {self._csv_dir}"}

        # Resolve logical → physical column name through the same
        # alias map that ``_resolve_force_column`` honors for the
        # per-file tools.  Without this resolver, a non-technical
        # caller passing the logical name ``force`` against a CSV
        # whose actual header is ``force_N`` got 16 silent
        # ``column not found`` load_errors and an empty cohort —
        # the v6.9.0 first-prompt-failure footgun.  Mirrors the
        # behaviour ``force_summary`` already provides via
        # ``_resolve_force_column``.
        value_column = self._value_columns.get(
            params["value_column"], params["value_column"],
        )
        group_by = params["group_by"]
        metric = params["metric"]

        metadata, meta_err = self._load_metadata_sidecar()
        if meta_err:
            return {"error": meta_err}
        if not metadata:
            return {
                "error": (
                    f"force_cohort_summary requires {METADATA_FILENAME} in "
                    f"{self._csv_dir} (see ADR 0015 for schema)"
                ),
            }

        csvs = sorted(self._csv_dir.glob("*.csv"))
        if len(csvs) > MAX_COHORT_FILES:
            return {
                "error": (
                    f"too many files ({len(csvs)}); cohort summary is "
                    f"capped at {MAX_COHORT_FILES} files"
                ),
            }

        by_group: dict[str, list[float | None]] = {}
        subjects_by_group: dict[str, list[str]] = {}
        missing_metadata: list[str] = []
        missing_group_field: list[str] = []
        load_errors: list[dict] = []

        for f in csvs:
            file_meta = metadata.get(f.name)
            if file_meta is None:
                missing_metadata.append(f.name)
                continue
            group = file_meta.get(group_by)
            if group is None:
                missing_group_field.append(f.name)
                continue
            group = str(group)

            try:
                headers, rows = self._read_csv(f, max_bytes=MAX_CSV_BYTES)
            except OSError as exc:
                load_errors.append({"filename": f.name, "error": str(exc)})
                continue

            if value_column not in headers:
                load_errors.append({
                    "filename": f.name,
                    "error": f"column {value_column!r} not found",
                })
                continue

            values = self._numeric_values(rows, value_column)
            timestamps = self._extract_timestamps(rows, headers)
            try:
                scalar = self._csv_processing.aggregate_metric(
                    values, timestamps, metric,
                )
            except ValueError as exc:
                return {"error": str(exc)}

            by_group.setdefault(group, []).append(scalar)
            subjects_by_group.setdefault(group, []).append(f.name)

        groups: dict[str, dict] = {}
        for group_label, per_file in sorted(by_group.items()):
            stats = self._csv_processing.cohort_stats(per_file)
            stats["subjects"] = subjects_by_group[group_label]
            groups[group_label] = stats

        result: dict = {
            "value_column": value_column,
            "metric": metric,
            "group_by": group_by,
            "subject_count": sum(len(s) for s in subjects_by_group.values()),
            "groups": groups,
            "note": (
                "Computed server-side via per-file reduction then "
                "cohort-level aggregation. No per-subject raw data "
                "transmitted."
            ),
        }
        if missing_metadata:
            result["missing_metadata"] = missing_metadata
        if missing_group_field:
            result["missing_group_field"] = missing_group_field
        if load_errors:
            result["load_errors"] = load_errors
        return result

    async def _handle_compare_trials(self, params: dict) -> dict:
        file_ids = params["file_ids"]
        force_column_param = params.get("force_column")

        comparisons: list[dict] = []
        errors: list[dict] = []
        for file_id in file_ids:
            filepath = self._resolve_file(file_id)
            if not filepath:
                errors.append({"file_id": file_id, "error": "file not found"})
                continue
            try:
                headers, rows = self._read_csv(filepath, max_bytes=MAX_CSV_BYTES)
            except OSError as exc:
                errors.append({"file_id": file_id, "error": str(exc)})
                continue
            force_column = self._resolve_force_column(headers, force_column_param)
            if force_column is None or force_column not in headers:
                errors.append({
                    "file_id": file_id,
                    "error": f"force column not found in {file_id}",
                })
                continue
            values = self._numeric_values(rows, force_column)
            if not values:
                errors.append({
                    "file_id": file_id,
                    "error": f"no numeric values in {force_column!r}",
                })
                continue
            timestamps = self._extract_timestamps(rows, headers)
            sample_rate = self._derive_sample_rate(
                timestamps, self._sample_rate_hz,
            )
            decline = self._csv_processing.force_decline_summary(
                values, timestamps,
            )
            mvc_window = (
                self._processing.mvc_window_mean(values, sample_rate)
                if sample_rate
                else None
            )
            comparisons.append({
                "file_id": file_id,
                "force_column": force_column,
                "sample_rate_hz": sample_rate,
                "peak": decline.get("peak"),
                "mvc_window_mean_250ms": mvc_window,
                "decline_pct": decline.get("decline_pct_total"),
                "decline_rate_per_min": decline.get("decline_rate_per_min"),
                "time_to_50pct_drop_s": decline.get("time_to_50pct_drop_s"),
                "duration_s": decline.get("duration_s"),
            })

        result: dict = {
            "n_trials": len(comparisons),
            "comparisons": comparisons,
            "note": (
                "Per-trial summaries computed server-side via load-and-"
                "reduce pass. No raw streams transmitted. Each entry "
                "uses the same numerical contract as force_summary."
            ),
        }
        if errors:
            result["errors"] = errors
        return result

    async def _handle_device_agreement(self, params: dict) -> dict:
        result = self._processing.bland_altman(
            params["device_a_values"],
            params["device_b_values"],
        )
        if "error" in result:
            return {"error": result["error"]}
        return {
            "device_a_label": params.get("device_a_label", "device A"),
            "device_b_label": params.get("device_b_label", "device B"),
            "metric_name": params.get("metric_name", "measurement"),
            **result,
            "note": (
                "Bland-Altman paired-device agreement analysis "
                "(Bland & Altman 1986). Mean difference = bias; "
                "95% LoA = bias ± 1.96·SD of differences."
            ),
        }

    async def _handle_label_event(self, params: dict) -> dict:
        try:
            self._storage.save_label(
                file_id=params["file_id"],
                t_seconds=params["t_seconds"],
                event_type=params["event_type"],
                label=params["label"],
                notes=params.get("notes"),
                subject_id=params.get("subject_id"),
            )
        except Exception as exc:
            log.error(f"force_label_event save failed: {exc}", exc_info=True)
            return {"error": f"Could not save label: {exc}"}
        return {
            "saved": True,
            "file_id": params["file_id"],
            "t_seconds": params["t_seconds"],
            "event_type": params["event_type"],
            "label": params["label"],
            "note": (
                "Label persisted in force_event_labels table. "
                "Preserved on consent revocation per ADR 0013 "
                "(analyst-authored interpretive content)."
            ),
        }

    # ── Tier 2 handler (consent-gated) ──

    async def _handle_downsampled(self, params: dict) -> dict:
        filepath = self._resolve_file(params["file_id"])
        if not filepath:
            return {"error": f"File not found: {params['file_id']}"}

        try:
            headers, rows = self._read_csv(filepath, max_bytes=MAX_CSV_BYTES)
        except OSError as exc:
            return {"error": str(exc)}

        interval = params.get("interval", 10)
        requested = params.get("columns")

        downsampled = self._csv_processing.downsample_rows(rows, interval)

        # Filter to requested columns (plus timestamp).
        if requested:
            ts_col = (
                self._timestamp_column
                or self._csv_processing.detect_timestamp_column(headers)
            )
            keep = set(requested)
            if ts_col:
                keep.add(ts_col)
            downsampled = [
                {k: v for k, v in row.items() if k in keep}
                for row in downsampled
            ]

        return {
            "filename": filepath.name,
            "interval": interval,
            "columns_included": list(requested) if requested else ["force"],
            "original_rows": len(rows),
            "downsampled_rows": len(downsampled),
            "reduction_pct": round(
                (1 - len(downsampled) / max(len(rows), 1)) * 100, 1,
            ),
            "rows": downsampled,
        }

    # ── Tier 3 handler (cost-gated) ──

    async def _handle_raw_window(self, params: dict) -> dict:
        window_s = params["end_seconds"] - params["start_seconds"]
        if window_s <= 0:
            return {
                "error": (
                    f"end_seconds ({params['end_seconds']}) must be "
                    f"strictly greater than start_seconds "
                    f"({params['start_seconds']})"
                )
            }
        if window_s > MAX_WINDOW_SECONDS:
            return {
                "error": (
                    f"Requested window {window_s:.1f}s exceeds hard "
                    f"cap of {MAX_WINDOW_SECONDS}s. Use force_downsampled "
                    "for longer reads."
                )
            }

        filepath = self._resolve_file(params["file_id"])
        if not filepath:
            return {"error": f"File not found: {params['file_id']}"}

        try:
            headers, rows = self._read_csv(filepath, max_bytes=MAX_CSV_BYTES)
        except OSError as exc:
            return {"error": str(exc)}

        timestamps = self._extract_timestamps(rows, headers)
        sample_rate = self._derive_sample_rate(timestamps, self._sample_rate_hz)

        # Slice by time window.
        start_idx, end_idx = self._slice_indices(
            timestamps, sample_rate,
            params["start_seconds"], params["end_seconds"],
            n_rows=len(rows),
        )
        if start_idx is None:
            return {
                "error": (
                    "Cannot slice by time window: no usable timestamps "
                    "and no declared sample_rate_hz. Set force_csv."
                    "sample_rate_hz in user_config.json or include a "
                    "timestamp column."
                ),
            }
        windowed = rows[start_idx:end_idx]

        requested = params.get("columns")
        if requested:
            ts_col = (
                self._timestamp_column
                or self._csv_processing.detect_timestamp_column(headers)
            )
            keep = set(requested)
            if ts_col:
                keep.add(ts_col)
            windowed = [
                {k: v for k, v in row.items() if k in keep}
                for row in windowed
            ]

        # Precision reduction on numeric values.
        reduced: list[dict] = []
        for row in windowed:
            new_row: dict = {}
            for k, v in row.items():
                fv = self._try_float(v)
                if fv is not None:
                    new_row[k] = self._csv_processing.reduce_precision(fv)
                else:
                    new_row[k] = v
            reduced.append(new_row)

        return {
            "filename": filepath.name,
            "start_seconds": params["start_seconds"],
            "end_seconds": params["end_seconds"],
            "sample_rate_hz": sample_rate,
            "columns_included": list(requested) if requested else ["force"],
            "row_count": len(reduced),
            "rows": reduced,
        }

    @staticmethod
    def _slice_indices(
        timestamps,
        sample_rate: float | None,
        start_s: float,
        end_s: float,
        n_rows: int,
    ) -> tuple[int | None, int | None]:
        """Resolve (start_idx, end_idx) for a time window.

        Prefers timestamp-based slicing when available; falls back
        to sample-rate-based row indexing. Returns (None, None) if
        neither is available.
        """
        if timestamps:
            t0 = timestamps[0]
            target_start = (start_s, end_s)
            start_idx = 0
            end_idx = n_rows
            for i, t in enumerate(timestamps):
                rel = (t - t0).total_seconds()
                if rel >= target_start[0]:
                    start_idx = i
                    break
            for i, t in enumerate(timestamps):
                rel = (t - t0).total_seconds()
                if rel >= target_start[1]:
                    end_idx = i
                    break
            return start_idx, end_idx
        if sample_rate and sample_rate > 0:
            start_idx = max(0, int(round(start_s * sample_rate)))
            end_idx = min(n_rows, int(round(end_s * sample_rate)))
            return start_idx, end_idx
        return None, None
