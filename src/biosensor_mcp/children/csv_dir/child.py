"""
CSV Directory Child MCP — Generic CSV Ingestion
====================================================
Wraps a local directory of per-subject CSV files and exposes tiered
analytical tools through the framework's security pipeline.  No
OAuth, no vendor API, no credentials — pure file-reading against a
declared schema.

Forked from ``src/biosensor_mcp/children/template/child.py``.

Config shape (in ``~/.biosensor-mcp/user_config.json``):

.. code-block:: json

    {
      "csv_dir": {
        "path": "/path/to/csv/directory",
        "timestamp_column": "timestamp",
        "value_columns": {
          "heart_rate": "Heart rate (bpm)",
          "glucose": "Blood glucose (mg/dL)"
        },
        "timestamp_format": null
      }
    }
"""

from __future__ import annotations

import csv
import io
import json
import logging
from pathlib import Path

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
from .processing import COHORT_METRICS, CSVProcessing

log = logging.getLogger("biosensor-mcp.csv_dir")

# SUBJECT_ID_SCHEMA / SUBJECT_ID_PARAM_DOC are framework-level constants
# (see ADR 0002) — csv_* tools reference them via the import above.

# Filename-safe pattern for file_id parameter — rejects path
# traversal sequences (no slashes, no '..' via pattern).
FILE_ID_PATTERN = r"^[A-Za-z0-9_\-\.]{1,255}$"

# Maximum file size (bytes) the child will load into memory.
# Files larger than this return an error suggesting csv_downsampled.
MAX_CSV_BYTES = 100 * 1024 * 1024  # 100 MB

# Upper bound on number of CSVs csv_cohort_summary will scan in a single
# call. Keeps the Tier-1 cost predictable and bounded; a directory with
# more than this many files yields a clear error rather than silently
# scanning a few hundred files. Tuned for typical pilot-study scale (the
# project's stated audience: 5–20 participants, see ADR 0009).
MAX_COHORT_FILES = 64

# Sidecar metadata filename. Optional; csv_cohort_summary requires it
# (see ADR 0015). Schema: ``{"<csv_filename>": {"<field>": <value>, ...}}``.
METADATA_FILENAME = "metadata.json"


class CSVDirectoryChild(ChildMCP):
    """
    Generic CSV directory child — seven tools across all three tiers.

    | Tool                     | Tier | Purpose                                |
    |--------------------------|------|----------------------------------------|
    | ``csv_list_files``       | 1    | List CSV files with metadata           |
    | ``csv_file_detail``      | 1    | Single-file stats                      |
    | ``csv_summary_report``   | 1    | Server-computed report (vaultable)     |
    | ``csv_cohort_summary``   | 1    | Cross-file cohort aggregation by group |
    | ``csv_force_decline``    | 1    | Per-file fatigue diagnostic            |
    | ``csv_downsampled``      | 2    | Decimated rows (consent-gated)         |
    | ``csv_raw_stream``       | 3    | Full rows, reduced (cost-gated)        |
    """

    def __init__(self, config_dir: Path, data_dir: Path):
        self._config_dir = config_dir
        self._data_dir = data_dir
        self._processing = CSVProcessing()

        # Load csv_dir config from user_config.json
        cfg = self._load_user_config(config_dir)
        csv_cfg = cfg.get("csv_dir", {})

        raw_path = csv_cfg.get("path")
        if not raw_path:
            raise ValueError(
                "csv_dir.path is required in user_config.json. "
                "Set it to the directory containing your CSV files."
            )
        self._csv_path = Path(raw_path).expanduser().resolve()
        if not self._csv_path.is_dir():
            log.warning(
                f"csv_dir.path does not exist or is not a directory: "
                f"{self._csv_path}. Tools will return errors until "
                f"the directory is created."
            )
        self._timestamp_column: str | None = csv_cfg.get("timestamp_column")
        self._timestamp_format: str | None = csv_cfg.get("timestamp_format")

        # value_columns: {"col_name": "Human Label", ...}
        # If not configured, auto-detect numeric columns from the first CSV.
        configured_cols: dict[str, str] | None = csv_cfg.get("value_columns")
        if configured_cols:
            self._value_columns: dict[str, str] = configured_cols
        else:
            self._value_columns = self._auto_detect_columns()

        # Column names used as the equivalent of ALL_STREAM_TYPES
        self._column_names: list[str] | None = (
            list(self._value_columns.keys()) if self._value_columns else None
        )

        log.info(
            f"CSV directory child initialized "
            f"(path={self._csv_path}, "
            f"columns={self._column_names or 'auto-detect'})"
        )

    @staticmethod
    def _load_user_config(config_dir: Path) -> dict:
        """Load user_config.json; return empty dict on missing/error.

        ``utf-8-sig`` strips a leading BOM transparently (v6.9.2 —
        a config saved by Notepad / PowerShell-default ends up
        BOM-prefixed and would otherwise drop the first top-level
        key, silently disabling csv_dir registration).
        """
        path = config_dir / "user_config.json"
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError) as exc:
            log.warning(f"Could not read {path}: {exc}")
            return {}

    def _auto_detect_columns(self) -> dict[str, str]:
        """Scan the first CSV in the directory to discover numeric columns.

        Streams at most 20 rows — never loads the full file — so it is
        safe to run at init time regardless of CSV size.
        """
        if not self._csv_path.is_dir():
            return {}
        csvs = sorted(self._csv_path.glob("*.csv"))
        if not csvs:
            return {}
        try:
            with open(
                csvs[0], encoding="utf-8-sig", errors="replace", newline="",
            ) as f:
                reader = csv.DictReader(f)
                headers = list(reader.fieldnames or [])
                sample = [
                    row for row, _ in zip(reader, range(20), strict=False)
                ]
        except OSError:
            return {}
        if not headers:
            return {}
        ts_col = (
            self._timestamp_column
            or self._processing.detect_timestamp_column(headers)
        )
        result: dict[str, str] = {}
        for col in headers:
            if col == ts_col:
                continue
            for row in sample:
                if self._try_float(row.get(col) or "") is not None:
                    result[col] = col
                    break
        if result:
            log.info(f"Auto-detected numeric columns: {list(result.keys())}")
        return result

    # ══════════════════════════════════════════════════════════
    # IDENTITY
    # ══════════════════════════════════════════════════════════

    @property
    def domain(self) -> str:
        return "csv_dir"

    @property
    def display_name(self) -> str:
        return "CSV Directory"

    @property
    def vaultable_tools(self) -> list[str]:
        # No vaultable tools yet — csv_summary_report has no renderer in
        # VaultWriter._renderers, so registering it as vaultable causes
        # `VaultWriter: No renderer for tool: csv_summary_report` warnings
        # on every successful call when vault is enabled. Per the
        # vaultable-tool ↔ renderer contract enforced in
        # tests/test_serve_mcp_protocol.py::test_every_vaultable_tool_has_renderer,
        # adding a tool to this list requires landing a paired renderer
        # in framework/vault/writer.py first. (Surfaced by mcp-protocol-
        # auditor on the v6.5.0 release-time pass.)
        return []

    # ══════════════════════════════════════════════════════════
    # CONSENT
    # ══════════════════════════════════════════════════════════

    @property
    def consent_info(self) -> ConsentInfo:
        if self._value_columns:
            data_types = list(self._value_columns.values())
        else:
            data_types = ["tabular biosensor readings"]
        return ConsentInfo(
            data_types=data_types,
            purpose="analysis of CSV-formatted biosensor data files",
            scope=ConsentScope(
                duration="session",
                duration_human="until this conversation ends",
                covers_future_calls=True,
                revocable=True,
                revoke_instruction="Say 'revoke CSV consent' at any time.",
            ),
        )

    # Map column name to consent data type for scope narrowing.
    # Built dynamically from config.
    @property
    def _column_data_map(self) -> dict[str, list[str]]:
        if self._value_columns:
            return {col: [label] for col, label in self._value_columns.items()}
        return {}

    def data_types_for_tool(self, tool_name: str, params: dict) -> list[str]:
        if tool_name in ("csv_downsampled", "csv_raw_stream"):
            requested = params.get("columns")
            if requested and self._column_data_map:
                types: set[str] = set()
                for col in requested:
                    types.update(self._column_data_map.get(col, []))
                if types:
                    return sorted(types)
        return self.consent_info.data_types

    # ══════════════════════════════════════════════════════════
    # TOOL SURFACE
    # ══════════════════════════════════════════════════════════

    @property
    def tool_definitions(self) -> list[ToolDefinition]:
        col_desc = (
            f"Which columns: {', '.join(self._column_names)}. Default: all."
            if self._column_names
            else "Which columns to include. Default: all numeric columns."
        )
        return [
            # ── Tier 1: Free (server-computed) ──
            ToolDefinition(
                "csv_list_files", 1,
                "List CSV files in the configured directory with size and column names. ~200 tokens.",
                {
                    "limit": {"type": "integer", "description": "Max results (default 20)", "required": False},
                    "subject_id": SUBJECT_ID_PARAM_DOC,
                },
            ),
            ToolDefinition(
                "csv_file_detail", 1,
                "Single-file metadata and per-column summary statistics.",
                {
                    "file_id": {"type": "string", "description": "CSV filename", "required": True},
                    "subject_id": SUBJECT_ID_PARAM_DOC,
                },
            ),
            ToolDefinition(
                "csv_summary_report", 1,
                "Server-computed analytics: per-column summaries, time range, "
                "data completeness. No raw data leaves the server. ~800 tokens.",
                {
                    "file_id": {"type": "string", "description": "CSV filename", "required": True},
                    "subject_id": SUBJECT_ID_PARAM_DOC,
                },
            ),
            ToolDefinition(
                "csv_cohort_summary", 1,
                "Cross-file cohort aggregation. Groups every CSV in the "
                "directory by a metadata field declared in metadata.json, "
                "reduces the named column to a per-file scalar by metric, "
                "and returns per-group n/mean/std/min/max. Pure server-side "
                "computation — no rows reach LLM context. Requires "
                "metadata.json sidecar. ~300 tokens. See ADR 0015. To "
                "compose a structured natural-language response over this "
                "result without any biometric data leaving the analyst's "
                "machine, pass the result as resolved_context to "
                "ask_local_oracle (per ADR 0022).",
                {
                    "column": {"type": "string", "description": "Numeric column to aggregate", "required": True},
                    "group_by": {"type": "string", "description": "Metadata field name (e.g. 'sex', 'group')", "required": True},
                    "metric": {
                        "type": "string",
                        "description": (
                            "Per-file reduction: "
                            f"{', '.join(COHORT_METRICS)}. Default: mean."
                        ),
                        "required": False,
                    },
                    "subject_id": SUBJECT_ID_PARAM_DOC,
                },
            ),
            ToolDefinition(
                "csv_force_decline", 1,
                "Per-file fatigue diagnostic: peak, end value, decline %, "
                "decline rate per minute, and time-to-50%-drop. Generic over "
                "any monotonically-fatigueing column (force, EMG envelope, "
                "power). ~250 tokens. To compose a structured natural-"
                "language response over this result without any biometric "
                "data leaving the analyst's machine, pass the result as "
                "resolved_context to ask_local_oracle (per ADR 0022).",
                {
                    "file_id": {"type": "string", "description": "CSV filename", "required": True},
                    "column": {"type": "string", "description": "Numeric column to analyse", "required": True},
                    "subject_id": SUBJECT_ID_PARAM_DOC,
                },
            ),
            # ── Tier 2: Consent-gated (downsampled) ──
            ToolDefinition(
                "csv_downsampled", 2,
                "Decimated rows at every Nth interval for visualization. "
                "~3000-7000 tokens. Requires biometric consent.",
                {
                    "file_id": {"type": "string", "description": "CSV filename", "required": True},
                    "interval": {
                        "type": "integer",
                        "description": "Decimation interval (every Nth row). Default 5.",
                        "required": False,
                    },
                    "columns": {
                        "type": "array",
                        "description": col_desc,
                        "required": False,
                    },
                    "subject_id": SUBJECT_ID_PARAM_DOC,
                },
            ),
            # ── Tier 3: Cost-gated (full rows) ──
            ToolDefinition(
                "csv_raw_stream", 3,
                "Full per-row data with precision reduction. ~25k-60k tokens. "
                "Requires consent + cost approval if over threshold.",
                {
                    "file_id": {"type": "string", "description": "CSV filename", "required": True},
                    "columns": {
                        "type": "array",
                        "description": col_desc,
                        "required": False,
                    },
                    "subject_id": SUBJECT_ID_PARAM_DOC,
                },
            ),
        ]

    @property
    def param_schemas(self) -> dict[str, dict[str, ValidationSchema]]:
        return {
            "csv_list_files": {
                "limit": ValidationSchema(type=int, min=1, max=100, default=20),
                "subject_id": SUBJECT_ID_SCHEMA,
            },
            "csv_file_detail": {
                "file_id": ValidationSchema(
                    type=str, required=True, pattern=FILE_ID_PATTERN,
                ),
                "subject_id": SUBJECT_ID_SCHEMA,
            },
            "csv_summary_report": {
                "file_id": ValidationSchema(
                    type=str, required=True, pattern=FILE_ID_PATTERN,
                ),
                "subject_id": SUBJECT_ID_SCHEMA,
            },
            "csv_cohort_summary": {
                "column": ValidationSchema(
                    type=str,
                    required=True,
                    allowed_values=self._column_names,
                ),
                "group_by": ValidationSchema(
                    type=str, required=True, pattern=r"^[A-Za-z0-9_\-]{1,64}$",
                ),
                "metric": ValidationSchema(
                    type=str,
                    required=False,
                    allowed_values=list(COHORT_METRICS),
                    default="mean",
                ),
                "subject_id": SUBJECT_ID_SCHEMA,
            },
            "csv_force_decline": {
                "file_id": ValidationSchema(
                    type=str, required=True, pattern=FILE_ID_PATTERN,
                ),
                "column": ValidationSchema(
                    type=str,
                    required=True,
                    allowed_values=self._column_names,
                ),
                "subject_id": SUBJECT_ID_SCHEMA,
            },
            "csv_downsampled": {
                "file_id": ValidationSchema(
                    type=str, required=True, pattern=FILE_ID_PATTERN,
                ),
                "interval": ValidationSchema(type=int, min=1, max=1000, default=5),
                "columns": ValidationSchema(
                    type=list, allowed_values=self._column_names,
                ),
                "subject_id": SUBJECT_ID_SCHEMA,
            },
            "csv_raw_stream": {
                "file_id": ValidationSchema(
                    type=str, required=True, pattern=FILE_ID_PATTERN,
                ),
                "columns": ValidationSchema(
                    type=list, allowed_values=self._column_names,
                ),
                "subject_id": SUBJECT_ID_SCHEMA,
            },
        }

    # ══════════════════════════════════════════════════════════
    # COST ESTIMATION (pre-execution, cheap)
    # ══════════════════════════════════════════════════════════

    async def estimate_cost(self, tool_name: str, params: dict) -> CostEstimate:
        if tool_name != "csv_raw_stream":
            return CostEstimate(tokens=0)

        filepath = self._resolve_file(params.get("file_id", ""))
        if not filepath:
            return CostEstimate(tokens=0)

        row_count = self._quick_row_count(filepath)
        headers = self._read_headers(filepath)
        requested = params.get("columns")
        col_count = len(requested) if requested else len(headers)

        full_tokens = self._processing.estimate_row_tokens(row_count, col_count)
        ds_tokens = self._processing.estimate_row_tokens(
            max(1, row_count // 5), col_count,
        )

        return CostEstimate(
            tokens=full_tokens,
            has_cheaper_alternative=True,
            alternative_tokens=ds_tokens,
            alternative_description=(
                "csv_downsampled (every 5th row) — "
                "preserves trends, ~80% cheaper"
            ),
        )

    def purge_cache(self, *, force: bool = False) -> dict:
        """
        No-op for CSV-directory children: the framework does not own
        the source data.

        Per ADR 0013 § "Children with no framework-owned cache":
        the CSV files at ``csv_dir.path`` are institutional artifacts
        the deployer manages — likely a research-data-management
        system (REDCap export, lab CSV dump). The framework reads
        them and never writes a derivative cache. Revocation here is
        therefore correctly a no-op at the framework boundary;
        institution-side retention policy applies to the source
        files.
        """
        return {
            "rows_purged": 0,
            "tables_touched": [],
            "preserved": [],
            "reason": (
                "csv_dir reads institutional CSV files at csv_dir.path; "
                "the framework owns no derivative cache to purge. "
                "Source-file retention is the deployer's responsibility "
                "per ADR 0013."
            ),
        }

    # ══════════════════════════════════════════════════════════
    # EXECUTION
    # ══════════════════════════════════════════════════════════

    async def execute(self, tool_name: str, params: dict) -> dict:
        handlers = {
            "csv_list_files": self._handle_list_files,
            "csv_file_detail": self._handle_file_detail,
            "csv_summary_report": self._handle_summary_report,
            "csv_cohort_summary": self._handle_cohort_summary,
            "csv_force_decline": self._handle_force_decline,
            "csv_downsampled": self._handle_downsampled,
            "csv_raw_stream": self._handle_raw_stream,
        }
        handler = handlers.get(tool_name)
        if not handler:
            return {"error": f"Unknown tool: {tool_name}"}
        return await handler(params)

    # ── Private helpers ──

    def _resolve_file(self, file_id: str) -> Path | None:
        """Resolve file_id to path under csv_path.  Returns None if
        the file doesn't exist or escapes the configured directory."""
        if not file_id:
            return None
        candidate = (self._csv_path / file_id).resolve()
        # Security: prevent directory traversal
        try:
            candidate.relative_to(self._csv_path)
        except ValueError:
            return None
        if not candidate.is_file():
            return None
        return candidate

    @staticmethod
    def _read_headers(filepath: Path) -> list[str]:
        """Read just the header row from a CSV file.

        ``utf-8-sig`` strips a leading byte-order mark transparently
        so an Excel- or PowerShell-redirected CSV does not silently
        get ``\ufeff<col>`` as its first header (v6.9.0 footgun on
        real-world recipient CSVs; bundled fixtures had no BOM, so
        the demo worked while production data would not).
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

        If *max_bytes* is non-zero the file size is checked first and
        an ``OSError`` is raised when it exceeds the limit.
        ``utf-8-sig`` mirrors ``_read_headers`` for BOM transparency.
        """
        if max_bytes and filepath.stat().st_size > max_bytes:
            size_mb = filepath.stat().st_size / (1024 * 1024)
            limit_mb = max_bytes / (1024 * 1024)
            raise OSError(
                f"File is too large ({size_mb:.1f} MB, limit "
                f"{limit_mb:.1f} MB). Use csv_downsampled "
                f"for large files."
            )
        with open(filepath, encoding="utf-8-sig", errors="replace", newline="") as f:
            raw = f.read()
        if "\ufffd" in raw:
            log.warning(
                f"{filepath.name} contains non-UTF-8 bytes "
                f"(replaced with \ufffd). Consider re-encoding the file."
            )
        reader = csv.DictReader(io.StringIO(raw))
        headers = list(reader.fieldnames or [])
        rows = list(reader)
        return headers, rows

    @staticmethod
    def _quick_row_count(filepath: Path) -> int:
        """Fast line count minus header."""
        try:
            with open(filepath, encoding="utf-8-sig", errors="replace") as f:
                count = sum(1 for _ in f)
            return max(0, count - 1)  # subtract header
        except OSError:
            return 0

    @staticmethod
    def _try_float(value: str) -> float | None:
        """Attempt float conversion; return None on failure."""
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _numeric_values(self, rows: list[dict], column: str) -> list[float]:
        """Extract numeric values from a column, skipping non-numeric and None."""
        values: list[float] = []
        for row in rows:
            v = self._try_float(row.get(column) or "")
            if v is not None:
                values.append(v)
        return values

    # ── Tier 1 handlers ──

    async def _handle_list_files(self, params: dict) -> dict:
        limit = params.get("limit", 20)
        if not self._csv_path.is_dir():
            return {"error": f"CSV directory not found: {self._csv_path}"}

        files = sorted(self._csv_path.glob("*.csv"))[:limit]
        results = []
        for f in files:
            headers = self._read_headers(f)
            results.append({
                "filename": f.name,
                "size_bytes": f.stat().st_size,
                "columns": headers,
            })
        return {"count": len(results), "files": results}

    async def _handle_file_detail(self, params: dict) -> dict:
        filepath = self._resolve_file(params["file_id"])
        if not filepath:
            return {"error": f"File not found: {params['file_id']}"}

        try:
            headers, rows = self._read_csv(filepath, max_bytes=MAX_CSV_BYTES)
        except OSError as exc:
            return {"error": str(exc)}
        ts_col = self._timestamp_column or self._processing.detect_timestamp_column(headers)

        column_stats: dict[str, dict] = {}
        for col in headers:
            if col == ts_col:
                continue
            values = self._numeric_values(rows, col)
            if values:
                column_stats[col] = self._processing.summarize_column(values)
            else:
                column_stats[col] = {"count": len(rows), "type": "non-numeric"}

        result: dict = {
            "filename": filepath.name,
            "row_count": len(rows),
            "columns": headers,
            "column_stats": column_stats,
        }
        if ts_col and rows:
            first_ts = self._processing.parse_timestamp(
                rows[0].get(ts_col, ""), self._timestamp_format,
            )
            last_ts = self._processing.parse_timestamp(
                rows[-1].get(ts_col, ""), self._timestamp_format,
            )
            if first_ts and last_ts:
                result["time_range"] = {
                    "start": first_ts.isoformat(),
                    "end": last_ts.isoformat(),
                }
        return result

    async def _handle_summary_report(self, params: dict) -> dict:
        filepath = self._resolve_file(params["file_id"])
        if not filepath:
            return {"error": f"File not found: {params['file_id']}"}

        try:
            headers, rows = self._read_csv(filepath, max_bytes=MAX_CSV_BYTES)
        except OSError as exc:
            return {"error": str(exc)}
        ts_col = self._timestamp_column or self._processing.detect_timestamp_column(headers)

        # Per-column summaries
        summaries: dict[str, dict] = {}
        numeric_cols: list[str] = []
        for col in headers:
            if col == ts_col:
                continue
            values = self._numeric_values(rows, col)
            if values:
                summaries[col] = self._processing.summarize_column(values)
                numeric_cols.append(col)
            else:
                summaries[col] = {"count": len(rows), "type": "non-numeric"}

        # Data completeness (missing value percentage per column)
        completeness: dict[str, float] = {}
        total = len(rows)
        if total > 0:
            for col in headers:
                present = sum(
                    1 for r in rows
                    if (r.get(col) or "").strip()
                )
                completeness[col] = round(present / total * 100, 1)

        result: dict = {
            "filename": filepath.name,
            "row_count": len(rows),
            "column_count": len(headers),
            "column_summaries": summaries,
            "completeness_pct": completeness,
        }

        # Time range
        if ts_col and rows:
            first_ts = self._processing.parse_timestamp(
                rows[0].get(ts_col, ""), self._timestamp_format,
            )
            last_ts = self._processing.parse_timestamp(
                rows[-1].get(ts_col, ""), self._timestamp_format,
            )
            if first_ts and last_ts:
                result["time_range"] = {
                    "start": first_ts.isoformat(),
                    "end": last_ts.isoformat(),
                }

        return result

    def _load_metadata_sidecar(self) -> tuple[dict[str, dict] | None, str | None]:
        """Read the optional ``metadata.json`` sidecar.

        Returns ``(metadata_dict, error_message)``. The metadata dict
        maps ``filename → {field: value, ...}``. ``error_message`` is
        non-None only when the sidecar exists but is malformed; missing
        is not an error (the caller decides whether the absence is
        fatal — csv_cohort_summary requires it, others ignore it).

        ``utf-8-sig`` mirrors the CSV-read paths for BOM transparency
        (v6.9.2 — a sidecar saved by Excel / PowerShell-default
        carries a UTF-8 BOM which would silently drop the first key
        and break the cohort handler's filename lookup).
        """
        sidecar = self._csv_path / METADATA_FILENAME
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
        # Light validation: every value must itself be a dict so the
        # group_by lookup is well-typed.
        for fname, meta in data.items():
            if not isinstance(meta, dict):
                return None, (
                    f"{METADATA_FILENAME}: entry for {fname!r} must be "
                    f"a JSON object of fields"
                )
        return data, None

    async def _handle_cohort_summary(self, params: dict) -> dict:
        """Cross-file cohort aggregation.

        Per ADR 0015: scans every CSV in ``csv_dir.path`` (up to
        ``MAX_COHORT_FILES``), reduces the named column to a per-file
        scalar by metric, groups by the metadata field, returns
        per-group statistics. Pure server-side computation — no rows
        cross into LLM context.
        """
        if not self._csv_path.is_dir():
            return {"error": f"CSV directory not found: {self._csv_path}"}

        column = params["column"]
        group_by = params["group_by"]
        metric = params.get("metric", "mean")

        metadata, meta_err = self._load_metadata_sidecar()
        if meta_err:
            return {"error": meta_err}
        if not metadata:
            return {
                "error": (
                    f"csv_cohort_summary requires {METADATA_FILENAME} in "
                    f"{self._csv_path} (see ADR 0015 for schema)"
                ),
            }

        csvs = sorted(self._csv_path.glob("*.csv"))
        if len(csvs) > MAX_COHORT_FILES:
            return {
                "error": (
                    f"too many files ({len(csvs)}); cohort summary is "
                    f"capped at {MAX_COHORT_FILES} files"
                ),
            }

        # Bucket per-file scalars by group label.
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

            if column not in headers:
                load_errors.append({
                    "filename": f.name,
                    "error": f"column {column!r} not found",
                })
                continue

            values = self._numeric_values(rows, column)
            timestamps = self._extract_timestamps(rows, headers)

            try:
                scalar = self._processing.aggregate_metric(
                    values, timestamps, metric,
                )
            except ValueError as exc:
                # Unknown metric — surface once and stop iterating;
                # ParamValidator should catch this earlier but we
                # double-check here for safety.
                return {"error": str(exc)}

            by_group.setdefault(group, []).append(scalar)
            subjects_by_group.setdefault(group, []).append(f.name)

        groups: dict[str, dict] = {}
        for group_label, per_file in sorted(by_group.items()):
            stats = self._processing.cohort_stats(per_file)
            stats["subjects"] = subjects_by_group[group_label]
            groups[group_label] = stats

        result: dict = {
            "column": column,
            "metric": metric,
            "group_by": group_by,
            "subject_count": sum(len(s) for s in subjects_by_group.values()),
            "groups": groups,
        }
        if missing_metadata:
            result["missing_metadata"] = missing_metadata
        if missing_group_field:
            result["missing_group_field"] = missing_group_field
        if load_errors:
            result["load_errors"] = load_errors
        return result

    async def _handle_force_decline(self, params: dict) -> dict:
        """Per-file fatigue diagnostic.

        Per ADR 0015: peak, end, decline %, decline rate per minute,
        time-to-50%-drop. Pure server-side computation; no rows leave.
        """
        filepath = self._resolve_file(params["file_id"])
        if not filepath:
            return {"error": f"File not found: {params['file_id']}"}

        column = params["column"]

        try:
            headers, rows = self._read_csv(filepath, max_bytes=MAX_CSV_BYTES)
        except OSError as exc:
            return {"error": str(exc)}

        if column not in headers:
            return {"error": f"column {column!r} not found in {filepath.name}"}

        values = self._numeric_values(rows, column)
        timestamps = self._extract_timestamps(rows, headers)
        summary = self._processing.force_decline_summary(values, timestamps)
        summary["filename"] = filepath.name
        summary["column"] = column
        return summary

    def _extract_timestamps(self, rows: list[dict], headers: list[str]):
        """Best-effort timestamp column extraction; returns None if no
        usable timestamp column or if any row fails to parse."""
        ts_col = (
            self._timestamp_column
            or self._processing.detect_timestamp_column(headers)
        )
        if not ts_col:
            return None
        parsed = []
        for r in rows:
            t = self._processing.parse_timestamp(
                (r.get(ts_col) or ""), self._timestamp_format,
            )
            if t is None:
                return None
            parsed.append(t)
        return parsed

    # ── Tier 2 handler (consent-gated) ──

    async def _handle_downsampled(self, params: dict) -> dict:
        filepath = self._resolve_file(params["file_id"])
        if not filepath:
            return {"error": f"File not found: {params['file_id']}"}

        try:
            headers, rows = self._read_csv(filepath, max_bytes=MAX_CSV_BYTES)
        except OSError as exc:
            return {"error": str(exc)}
        interval = params.get("interval", 5)
        requested = params.get("columns")

        downsampled = self._processing.downsample_rows(rows, interval)

        # Filter to requested columns (plus timestamp)
        if requested:
            ts_col = self._timestamp_column or self._processing.detect_timestamp_column(headers)
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
            "original_rows": len(rows),
            "downsampled_rows": len(downsampled),
            "reduction_pct": round(
                (1 - len(downsampled) / max(len(rows), 1)) * 100, 1,
            ),
            "rows": downsampled,
        }

    # ── Tier 3 handler (cost-gated) ──

    async def _handle_raw_stream(self, params: dict) -> dict:
        filepath = self._resolve_file(params["file_id"])
        if not filepath:
            return {"error": f"File not found: {params['file_id']}"}

        try:
            headers, rows = self._read_csv(filepath, max_bytes=MAX_CSV_BYTES)
        except OSError as exc:
            return {"error": str(exc)}
        requested = params.get("columns")

        # Filter to requested columns (plus timestamp)
        if requested:
            ts_col = self._timestamp_column or self._processing.detect_timestamp_column(headers)
            keep = set(requested)
            if ts_col:
                keep.add(ts_col)
            rows = [
                {k: v for k, v in row.items() if k in keep}
                for row in rows
            ]

        # Precision reduction on numeric values
        reduced: list[dict] = []
        for row in rows:
            new_row: dict = {}
            for k, v in row.items():
                fv = self._try_float(v)
                if fv is not None:
                    new_row[k] = self._processing.reduce_precision(fv)
                else:
                    new_row[k] = v
            reduced.append(new_row)

        return {
            "filename": filepath.name,
            "row_count": len(reduced),
            "rows": reduced,
        }
