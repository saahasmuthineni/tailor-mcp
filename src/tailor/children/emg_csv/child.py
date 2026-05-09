"""
EMG-CSV Child MCP — Surface-EMG Envelope Traces (~50–500 Hz)
============================================================
ChildMCP for surface-EMG rectified-envelope CSV files.  Default
assumption is single-channel envelope at ~100 Hz; multi-channel
(``envelope_ch1`` … ``envelope_ch4``) is supported via the
``columns`` parameter for bilateral or multi-muscle protocols.

Second sibling in the planned data-source family (``force_csv``,
``emg_csv`` (this child), future ``mrs_*``) — see ``__init__.py``
for the multimodal-composition framing.

Architectural decisions baked in:

- **Path B caching for analyst-authored labels only.**  Mirrors
  ``ForceCsvStorage`` exactly (``emg_event_labels`` table).
  ``purge_cache`` PRESERVES labels per ADR 0013.
- **No biometric-data caching.**  Source CSV files read on demand.
- **CSV-iteration helpers copied from force_csv/child.py** verbatim
  with citation comments.  Per project anti-premature-abstraction
  discipline, helper extraction to a shared module is deferred to
  the moment the fourth caller materializes.  Three callers
  (``csv_dir``, ``force_csv``, ``emg_csv``) is the boundary for
  copy-with-citation; four would be the boundary for shared module.
- **Time-domain analytics only** (Phase 2 scope).  Spectral
  median-frequency-shift is documented as deferred (see
  ``__init__.py``).
- **Bland-Altman intentionally omitted** — EMG device-validation
  has different conventions (cross-talk, electrode-placement
  reproducibility) than the paired-paired shape that fits force
  device validation.
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
from .processing import EmgCsvProcessing

log = logging.getLogger("tailor.emg_csv")

# Default column vocabulary for Tier-2 / Tier-3 narrowing.  Real
# deployments declare their own column names in user_config.json;
# the placeholder lists the typical single-channel envelope case
# plus bilateral / multi-muscle additions.
ALL_STREAM_TYPES = [
    "envelope",
    "envelope_ch1",
    "envelope_ch2",
    "envelope_ch3",
    "envelope_ch4",
]

# Controlled vocabulary for protocol-event labels.  Mirrors the
# force_csv vocabulary so an analyst can apply the same lifecycle
# to paired EMG + force trials.
PROTOCOL_EVENT_TYPES = (
    "baseline_mvc",
    "sustained_start",
    "mvc_probe",
    "task_failure",
    "rest_period_start",
    "burst_onset",
    "other",
)

# Tier-3 raw-window cap.  At 500 Hz × 1 channel × 30s ≈ 15000
# samples ≈ ~37k tokens — under cost gate, safe.  Larger windows
# trigger CostGate naturally.
MAX_WINDOW_SECONDS = 30.0

# Filename-safe pattern for file_id parameter — rejects path
# traversal sequences.  Mirrors force_csv / csv_dir.
FILE_ID_PATTERN = r"^[A-Za-z0-9_\-\.]{1,255}$"

# Maximum file size (bytes) the child will load into memory.
MAX_CSV_BYTES = 100 * 1024 * 1024  # 100 MB

# Upper bound on number of CSVs scanned in a single call.
MAX_COHORT_FILES = 64

# Sidecar metadata filename per ADR 0015.
METADATA_FILENAME = "metadata.json"


# ═══════════════════════════════════════════════════════════════
# EMG-CSV STORAGE (analyst-authored labels only)
# ═══════════════════════════════════════════════════════════════

class EmgCsvStorage(BaseStorage):
    """
    SQLite cache for ``emg_csv`` — analyst-authored protocol-
    event labels only.  Schema mirrors ``ForceCsvStorage``
    exactly; the table name differs so the two children's
    label tables coexist in the same data dir without collision.
    """

    def _schema_sql(self) -> str:
        return """
            CREATE TABLE IF NOT EXISTS emg_event_labels (
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
            "INSERT OR REPLACE INTO emg_event_labels"
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
                " FROM emg_event_labels WHERE file_id = ?"
                " ORDER BY t_seconds",
                (file_id,),
            )
        else:
            # ADR 0009 IS-NULL-or-match filter so cross-subject
            # legacy rows stay visible.
            rows = self.fetchall(
                "SELECT t_seconds, event_type, label, notes, labeled_at, subject_id"
                " FROM emg_event_labels"
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
        row = self.fetchone("SELECT COUNT(*) FROM emg_event_labels")
        return int(row[0]) if row else 0


# ═══════════════════════════════════════════════════════════════
# CHILD IMPLEMENTATION
# ═══════════════════════════════════════════════════════════════

class EmgCsvChild(ChildMCP):
    """
    Surface-EMG envelope CSV ingest child.  8 tools across 3 tiers.

    | Tool                          | Tier | Purpose                                    |
    |-------------------------------|------|--------------------------------------------|
    | ``emg_list_files``            | 1    | List EMG trial files with sample-rate meta |
    | ``emg_file_detail``           | 1    | Per-file metadata + per-column summary     |
    | ``emg_envelope_summary``      | 1    | RMS / MAV / iEMG / fatigue index           |
    | ``emg_cohort_summary``        | 1    | Cross-file aggregation by sidecar group    |
    | ``emg_compare_trials``        | 1    | Side-by-side comparison of 2-5 trials      |
    | ``emg_label_event``           | 1    | Analyst-authored protocol-event annotation |
    | ``emg_downsampled``           | 2    | Decimated streams for visualization        |
    | ``emg_raw_window``            | 3    | Raw samples within a bounded time window   |

    Bland-Altman intentionally absent (see ``__init__.py``).
    """

    def __init__(self, config_dir: Path, data_dir: Path):
        self._config_dir = config_dir
        self._data_dir = data_dir
        self._processing = EmgCsvProcessing()
        self._csv_processing = CSVProcessing()  # for shared helpers
        self._storage = EmgCsvStorage(data_dir / "emg_csv.db")

        cfg = self._load_user_config().get("emg_csv", {})
        raw_path = cfg.get("path")
        self._csv_dir: Path | None = (
            Path(raw_path).expanduser().resolve() if raw_path else None
        )
        if self._csv_dir is not None and not self._csv_dir.is_dir():
            log.warning(
                f"emg_csv.path does not exist or is not a directory: "
                f"{self._csv_dir}. Tools will return errors until the "
                f"directory is created."
            )
        self._timestamp_column: str | None = cfg.get("timestamp_column")
        self._timestamp_format: str | None = cfg.get("timestamp_format")
        self._sample_rate_hz: float | None = cfg.get("sample_rate_hz")
        self._value_columns: dict[str, str] = cfg.get("value_columns", {})
        self._default_envelope_column: str = self._value_columns.get(
            "envelope", "envelope",
        )
        log.info(
            f"EmgCsvChild initialized "
            f"(csv_dir={self._csv_dir}, sample_rate_hz={self._sample_rate_hz}, "
            f"labels_in_storage={self._storage.label_count()})"
        )

    def _load_user_config(self) -> dict:
        """Mirrors ForceCsvChild._load_user_config.  Supported keys
        under ``emg_csv``:

          path              — directory of EMG envelope CSV files
          timestamp_column  — column name carrying timestamps
          timestamp_format  — strptime format if non-ISO
          sample_rate_hz    — declared envelope rate
          value_columns     — alias map; ``envelope`` key sets the
                              default for envelope_summary etc.
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

        Per ADR 0013 — this child owns NO biometric cache (EMG
        envelope CSVs are read from source files on the analyst's
        machine, not cached as derivative data).  The only thing
        in SQLite is the ``emg_event_labels`` table — analyst-
        authored protocol-event annotations.

        Per ADR 0013 § Decision: analyst-authored interpretive
        content is PRESERVED on consent revocation.  Mirrors the
        force_csv preservation contract; same IRB-meaningful
        "annotations stay, biometric cache disappears" demo.
        """
        return {
            "rows_purged": 0,
            "tables_touched": [],
            "preserved": ["emg_event_labels"],
            "reason": (
                "emg_csv reads source CSV files on demand and owns "
                "no biometric cache.  The emg_event_labels table "
                "holds analyst-authored protocol-event annotations "
                "and is preserved per ADR 0013 § Decision."
            ),
        }

    @property
    def domain(self) -> str:
        return "emg_csv"

    @property
    def display_name(self) -> str:
        return "EMG envelope (surface electrodes)"

    @property
    def vaultable_tools(self) -> list[str]:
        """
        Until paired renderers land in framework/vault/writer.py,
        registering vaultable tools causes "No renderer for tool"
        warnings on every successful call.  Empty for now;
        renderer landing is a follow-on (matches force_csv posture).
        """
        return []

    @property
    def consent_info(self) -> ConsentInfo:
        return ConsentInfo(
            data_types=["surface electromyography envelope"],
            purpose=(
                "neuromuscular activation and fatigue analysis "
                "(amplitude, mean activation, integrated EMG, "
                "fatigue index)"
            ),
            scope=ConsentScope(
                duration="session",
                duration_human="until this conversation ends",
                covers_future_calls=True,
                revocable=True,
                revoke_instruction=(
                    "Say 'revoke emg_csv consent' at any time."
                ),
            ),
        )

    _STREAM_DATA_MAP: dict[str, list[str]] = {
        "envelope": ["surface electromyography envelope"],
        "envelope_ch1": ["surface electromyography envelope"],
        "envelope_ch2": ["surface electromyography envelope"],
        "envelope_ch3": ["surface electromyography envelope"],
        "envelope_ch4": ["surface electromyography envelope"],
    }

    def data_types_for_tool(self, tool_name: str, params: dict) -> list[str]:
        if tool_name in ("emg_downsampled", "emg_raw_window"):
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
                "emg_list_files", 1,
                "List EMG envelope trial files with sample-rate, "
                "channel count, and duration metadata. ~200 tokens.",
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
                "emg_file_detail", 1,
                "Per-file metadata + per-column summary statistics + "
                "any analyst-authored protocol-event labels for this "
                "file. ~500 tokens.",
                {
                    "file_id": {
                        "type": "string",
                        "description": "Filename within emg_csv.path",
                        "required": True,
                    },
                    "subject_id": SUBJECT_ID_PARAM_DOC,
                },
            ),
            ToolDefinition(
                "emg_envelope_summary", 1,
                "Per-file fatigue diagnostic: RMS, mean activation "
                "(MAV), integrated EMG, peak-window mean (Sánchez "
                "250 ms shape), end-window mean, and fatigue index "
                "(peak-vs-end percent decline). Time-domain only — "
                "spectral median-frequency-shift is deferred. "
                "~400 tokens.",
                {
                    "file_id": {
                        "type": "string",
                        "description": "Filename within emg_csv.path",
                        "required": True,
                    },
                    "envelope_column": {
                        "type": "string",
                        "description": (
                            "Column carrying envelope values. "
                            "Defaults to emg_csv.value_columns.envelope."
                        ),
                        "required": False,
                    },
                    "subject_id": SUBJECT_ID_PARAM_DOC,
                },
            ),
            ToolDefinition(
                "emg_cohort_summary", 1,
                "Cross-file aggregation by metadata-sidecar group "
                "(matches csv_cohort_summary, ADR 0015). Reduces each "
                "trial to one scalar via metric, then aggregates by "
                "group. Requires metadata.json sidecar. ~600 tokens.",
                {
                    "group_field": {
                        "type": "string",
                        "description": "Metadata field to group by (e.g. 'sex')",
                        "required": True,
                    },
                    "value_column": {
                        "type": "string",
                        "description": "Envelope column to reduce per file",
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
                "emg_compare_trials", 1,
                "Side-by-side comparison of 2-5 trial files: peak "
                "window mean, end window mean, fatigue index, RMS, "
                "iEMG. ~800 tokens.",
                {
                    "file_ids": {
                        "type": "array",
                        "description": "List of 2-5 file IDs to compare",
                        "required": True,
                    },
                    "envelope_column": {
                        "type": "string",
                        "description": "Column carrying envelope values",
                        "required": False,
                    },
                    "subject_id": SUBJECT_ID_PARAM_DOC,
                },
            ),
            ToolDefinition(
                "emg_label_event", 1,
                "Persist an analyst-authored protocol-event label for "
                "a specific timepoint in a file. Labels persist across "
                "sessions and are PRESERVED on consent revocation per "
                "ADR 0013. Vocabulary mirrors force_csv so paired EMG "
                "+ force trials share lifecycle terms.",
                {
                    "file_id": {
                        "type": "string",
                        "description": "Filename within emg_csv.path",
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
                "emg_downsampled", 2,
                "Decimated envelope stream at every Nth sample for "
                "visualization. ~3000-7000 tokens. Requires biometric "
                "consent.",
                {
                    "file_id": {
                        "type": "string",
                        "description": "Filename within emg_csv.path",
                        "required": True,
                    },
                    "interval": {
                        "type": "integer",
                        "description": "Decimation interval (default 10)",
                        "required": False,
                    },
                    "columns": {
                        "type": "array",
                        "description": (
                            f"Which columns to include: "
                            f"{', '.join(ALL_STREAM_TYPES)}. "
                            f"Default: envelope only."
                        ),
                        "required": False,
                    },
                    "subject_id": SUBJECT_ID_PARAM_DOC,
                },
            ),
            # ── Tier 3: Cost-gated (raw windowed streams) ──
            ToolDefinition(
                "emg_raw_window", 3,
                f"Raw per-sample envelope data within a bounded time "
                f"window. Hard cap: {MAX_WINDOW_SECONDS} seconds. "
                "Requires consent + cost approval if over threshold.",
                {
                    "file_id": {
                        "type": "string",
                        "description": "Filename within emg_csv.path",
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
                            f"Window end. Must be within "
                            f"{MAX_WINDOW_SECONDS}s of start_seconds."
                        ),
                        "required": True,
                    },
                    "columns": {
                        "type": "array",
                        "description": (
                            f"Which columns: {', '.join(ALL_STREAM_TYPES)}. "
                            f"Default: envelope only."
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
            "emg_list_files": {
                "limit": ValidationSchema(type=int, min=1, max=500, default=50),
                "subject_id": SUBJECT_ID_SCHEMA,
            },
            "emg_file_detail": {
                "file_id": ValidationSchema(
                    type=str, required=True, pattern=FILE_ID_PATTERN,
                ),
                "subject_id": SUBJECT_ID_SCHEMA,
            },
            "emg_envelope_summary": {
                "file_id": ValidationSchema(
                    type=str, required=True, pattern=FILE_ID_PATTERN,
                ),
                "envelope_column": ValidationSchema(type=str),
                "subject_id": SUBJECT_ID_SCHEMA,
            },
            "emg_cohort_summary": {
                "group_field": ValidationSchema(
                    type=str, required=True, pattern=r"^[A-Za-z0-9_\-]{1,64}$",
                ),
                "value_column": ValidationSchema(type=str, required=True),
                "metric": ValidationSchema(
                    type=str, required=True, allowed_values=list(COHORT_METRICS),
                ),
                "subject_id": SUBJECT_ID_SCHEMA,
            },
            "emg_compare_trials": {
                "file_ids": ValidationSchema(
                    type=list, min_len=2, max_len=5, required=True,
                ),
                "envelope_column": ValidationSchema(type=str),
                "subject_id": SUBJECT_ID_SCHEMA,
            },
            "emg_label_event": {
                "file_id": ValidationSchema(
                    type=str, required=True, pattern=FILE_ID_PATTERN,
                ),
                "t_seconds": ValidationSchema(type=float, min=0.0, required=True),
                "event_type": ValidationSchema(type=str, required=True),
                "label": ValidationSchema(type=str, required=True),
                "notes": ValidationSchema(type=str),
                "subject_id": SUBJECT_ID_SCHEMA,
            },
            "emg_downsampled": {
                "file_id": ValidationSchema(
                    type=str, required=True, pattern=FILE_ID_PATTERN,
                ),
                "interval": ValidationSchema(type=int, min=1, max=10000, default=10),
                "columns": ValidationSchema(type=list, allowed_values=ALL_STREAM_TYPES),
                "subject_id": SUBJECT_ID_SCHEMA,
            },
            "emg_raw_window": {
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
        if tool_name != "emg_raw_window":
            return CostEstimate(tokens=0)

        rate = self._sample_rate_hz or 100.0
        window_s = max(0.0, params["end_seconds"] - params["start_seconds"])
        col_count = len(params.get("columns") or ["envelope"])
        full_tokens = int(window_s * rate * col_count * 4)
        ds_tokens = max(int(full_tokens / 10), 1)

        return CostEstimate(
            tokens=full_tokens,
            has_cheaper_alternative=True,
            alternative_tokens=ds_tokens,
            alternative_description=(
                "emg_downsampled (interval=10) — ~90% cheaper, "
                "preserves envelope shape for visualization"
            ),
        )

    # ══════════════════════════════════════════════════════════
    # CSV-iteration helpers (mirror force_csv/child.py verbatim)
    # ══════════════════════════════════════════════════════════
    # Per project anti-premature-abstraction discipline, these are
    # copied not extracted.  Three callers (csv_dir, force_csv,
    # emg_csv) is the boundary for copy-with-citation; four would
    # be the boundary for shared module extraction.

    def _resolve_file(self, file_id: str) -> Path | None:
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
        # ``utf-8-sig`` transparently strips a leading BOM — see
        # ForceCsvProcessing._read_headers v6.9.2 docstring for the
        # full rationale (v6.9.0 footgun on Excel-touched CSVs).
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
        if max_bytes and filepath.stat().st_size > max_bytes:
            size_mb = filepath.stat().st_size / (1024 * 1024)
            limit_mb = max_bytes / (1024 * 1024)
            raise OSError(
                f"File is too large ({size_mb:.1f} MB, limit "
                f"{limit_mb:.1f} MB). Use emg_downsampled "
                f"for large files."
            )
        with open(filepath, encoding="utf-8-sig", errors="replace", newline="") as f:
            raw = f.read()
        if "�" in raw:
            log.warning(
                f"{filepath.name} contains non-UTF-8 bytes "
                f"(replaced with �). Consider re-encoding."
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
                return None
            parsed.append(t)
        return parsed

    def _load_metadata_sidecar(
        self,
    ) -> tuple[dict[str, dict] | None, str | None]:
        # ``utf-8-sig`` for BOM transparency — see ForceCsvChild's
        # _load_metadata_sidecar v6.9.2 docstring for full rationale.
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

    def _resolve_envelope_column(
        self, headers: list[str], requested: str | None,
    ) -> str | None:
        if requested:
            return requested
        if self._default_envelope_column in headers:
            return self._default_envelope_column
        if "envelope" in headers:
            return "envelope"
        return None

    def _derive_sample_rate(
        self, timestamps, declared_rate: float | None,
    ) -> float | None:
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
            "emg_list_files": self._handle_list_files,
            "emg_file_detail": self._handle_file_detail,
            "emg_envelope_summary": self._handle_envelope_summary,
            "emg_cohort_summary": self._handle_cohort_summary,
            "emg_compare_trials": self._handle_compare_trials,
            "emg_label_event": self._handle_label_event,
            "emg_downsampled": self._handle_downsampled,
            "emg_raw_window": self._handle_raw_window,
        }
        handler = handlers.get(tool_name)
        if not handler:
            return {"error": f"Unknown tool: {tool_name}"}
        return await handler(params)

    # ── Tier 1 handlers ──

    async def _handle_list_files(self, params: dict) -> dict:
        if self._csv_dir is None:
            return {"error": "emg_csv.path not configured in user_config.json"}
        if not self._csv_dir.is_dir():
            return {"error": f"emg_csv directory not found: {self._csv_dir}"}

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

    async def _handle_envelope_summary(self, params: dict) -> dict:
        filepath = self._resolve_file(params["file_id"])
        if not filepath:
            return {"error": f"File not found: {params['file_id']}"}

        try:
            headers, rows = self._read_csv(filepath, max_bytes=MAX_CSV_BYTES)
        except OSError as exc:
            return {"error": str(exc)}

        envelope_column = self._resolve_envelope_column(
            headers, params.get("envelope_column"),
        )
        if envelope_column is None or envelope_column not in headers:
            return {
                "error": (
                    f"envelope column not found. Tried: "
                    f"{params.get('envelope_column') or self._default_envelope_column}. "
                    f"Available columns: {headers}"
                ),
            }

        values = self._numeric_values(rows, envelope_column)
        if not values:
            return {
                "error": (
                    f"No numeric values in column {envelope_column!r} "
                    f"for {filepath.name}"
                ),
            }
        timestamps = self._extract_timestamps(rows, headers)
        sample_rate = self._derive_sample_rate(timestamps, self._sample_rate_hz)

        if not sample_rate:
            return {
                "error": (
                    "envelope_summary requires a sample rate — set "
                    "emg_csv.sample_rate_hz in user_config.json or "
                    "include a timestamp column."
                ),
            }

        summary = self._processing.envelope_summary(values, sample_rate)
        if "error" in summary:
            return summary

        return {
            "filename": filepath.name,
            "envelope_column": envelope_column,
            "sample_rate_hz": sample_rate,
            **summary,
            "note": (
                "Computed server-side via load-and-reduce pass. Time-"
                "domain analytics only (RMS, MAV, iEMG, peak-vs-end "
                "fatigue index). Spectral median-frequency-shift is a "
                "deferred follow-on per emg_csv/__init__.py. No raw "
                "samples transmitted."
            ),
        }

    async def _handle_cohort_summary(self, params: dict) -> dict:
        if self._csv_dir is None:
            return {"error": "emg_csv.path not configured"}
        if not self._csv_dir.is_dir():
            return {"error": f"emg_csv directory not found: {self._csv_dir}"}

        # Resolve logical → physical column name through the same
        # alias map that ``_resolve_envelope_column`` honors for the
        # per-file tools.  Closes the cohort-handler asymmetry the
        # v6.9.0 first-prompt-failure investigation surfaced
        # (sibling fix in force_csv/child.py:_handle_cohort_summary).
        value_column = self._value_columns.get(
            params["value_column"], params["value_column"],
        )
        group_field = params["group_field"]
        metric = params["metric"]

        metadata, meta_err = self._load_metadata_sidecar()
        if meta_err:
            return {"error": meta_err}
        if not metadata:
            return {
                "error": (
                    f"emg_cohort_summary requires {METADATA_FILENAME} in "
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
            group = file_meta.get(group_field)
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
            "group_field": group_field,
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
        envelope_column_param = params.get("envelope_column")

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
            envelope_column = self._resolve_envelope_column(
                headers, envelope_column_param,
            )
            if envelope_column is None or envelope_column not in headers:
                errors.append({
                    "file_id": file_id,
                    "error": f"envelope column not found in {file_id}",
                })
                continue
            values = self._numeric_values(rows, envelope_column)
            if not values:
                errors.append({
                    "file_id": file_id,
                    "error": f"no numeric values in {envelope_column!r}",
                })
                continue
            timestamps = self._extract_timestamps(rows, headers)
            sample_rate = self._derive_sample_rate(
                timestamps, self._sample_rate_hz,
            )
            if not sample_rate:
                errors.append({
                    "file_id": file_id,
                    "error": "no sample rate (set emg_csv.sample_rate_hz)",
                })
                continue
            summary = self._processing.envelope_summary(values, sample_rate)
            if "error" in summary:
                errors.append({"file_id": file_id, "error": summary["error"]})
                continue
            comparisons.append({
                "file_id": file_id,
                "envelope_column": envelope_column,
                "sample_rate_hz": sample_rate,
                "peak_envelope_window_mean": summary.get("peak_envelope_window_mean"),
                "end_window_mean": summary.get("end_window_mean"),
                "fatigue_index_pct": summary.get("fatigue_index_pct"),
                "rms": summary.get("rms"),
                "integrated_emg": summary.get("integrated_emg"),
                "duration_s": summary.get("duration_s"),
            })

        result: dict = {
            "n_trials": len(comparisons),
            "comparisons": comparisons,
            "note": (
                "Per-trial summaries computed server-side via load-and-"
                "reduce pass. No raw streams transmitted."
            ),
        }
        if errors:
            result["errors"] = errors
        return result

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
            log.error(f"emg_label_event save failed: {exc}", exc_info=True)
            return {"error": f"Could not save label: {exc}"}
        return {
            "saved": True,
            "file_id": params["file_id"],
            "t_seconds": params["t_seconds"],
            "event_type": params["event_type"],
            "label": params["label"],
            "note": (
                "Label persisted in emg_event_labels table. Preserved "
                "on consent revocation per ADR 0013 (analyst-authored "
                "interpretive content)."
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
            "columns_included": list(requested) if requested else ["envelope"],
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
                    f"cap of {MAX_WINDOW_SECONDS}s. Use emg_downsampled "
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

        start_idx, end_idx = self._slice_indices(
            timestamps, sample_rate,
            params["start_seconds"], params["end_seconds"],
            n_rows=len(rows),
        )
        if start_idx is None:
            return {
                "error": (
                    "Cannot slice by time window: no usable timestamps "
                    "and no declared sample_rate_hz. Set emg_csv."
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
            "columns_included": list(requested) if requested else ["envelope"],
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
