"""
MATLAB File Child MCP — `.mat` Binary Format Ingestion
=========================================================
Wraps a local directory of MATLAB binary `.mat` files (v5/v6/v7.2)
and exposes tiered analytical tools through the framework's security
pipeline.

Forked from ``src/tailor/children/csv_dir/child.py``.

Config shape (in ``~/.tailor/user_config.json``):

.. code-block:: json

    {
      "matlab_file": {
        "path": "/path/to/mat/directory",
        "variable_filter": ["EMG_envelope", "force"]
      }
    }

``variable_filter`` is optional; absent means "all 1-D and 2-D numeric
variables auto-detected when each file is loaded."

Scope per ADR 0036: this child supports `.mat` v5/v6/v7.2 only. v7.3
HDF5-based files are detected via the magic bytes and rejected with a
clear error pointing at the deferred work. Real labs ship both formats;
v7.3 is held behind a future superseding ADR.

Subject scoping per ADR 0002 / ADR 0009: per-file (one `.mat` = one
subject) follows the csv_dir/force_csv/emg_csv lineage. Multi-subject
`.mat` files where variables-are-subjects (e.g. an 8-by-N envelope
matrix where rows are participants) are deferred — passing ``subject_id``
is audit-log scoping only and does NOT filter rows.

ADR 0013 ``purge_cache``: no-op — the framework owns no derivative
cache. Per F4 of the proposal-mode audit, results are re-parsed from
disk on every call rather than cached in memory.
"""

from __future__ import annotations

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
from .processing import COHORT_METRICS, MATLABProcessing

log = logging.getLogger("tailor.matlab_file")

FILE_ID_PATTERN = r"^[A-Za-z0-9_\-\.]{1,255}$"
VARIABLE_NAME_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]{0,63}$"

# 100 MB file-size cap; matches csv_dir.MAX_CSV_BYTES.
MAX_MAT_BYTES = 100 * 1024 * 1024
# 64 file cohort cap; matches csv_dir.MAX_COHORT_FILES (ADR 0009 pilot scale).
MAX_COHORT_FILES = 64
# Sidecar metadata filename per ADR 0015.
METADATA_FILENAME = "metadata.json"

# `.mat` v7.3 HDF5 magic bytes — the first 8 bytes of an HDF5 file are
# always `\x89HDF\r\n\x1a\n`. v5/v6/v7.2 files begin with a 116-byte text
# header starting "MATLAB 5.0 MAT-file" (or similar) — never with the HDF5
# signature. Detecting this gives us a clean refusal path for v7.3 without
# pulling h5py in just to read magic bytes.
HDF5_MAGIC = b"\x89HDF\r\n\x1a\n"


class MATLABFileChild(ChildMCP):
    """
    MATLAB `.mat` file child — six tools across all three tiers.

    | Tool                       | Tier | Purpose                                |
    |----------------------------|------|----------------------------------------|
    | ``matlab_list_files``      | 1    | List `.mat` files + their variables    |
    | ``matlab_file_detail``     | 1    | Single-file metadata + per-variable summary stats |
    | ``matlab_summary_report``  | 1    | Per-variable scalars across the file   |
    | ``matlab_cohort_summary``  | 1    | Cross-file aggregation by metadata-sidecar group |
    | ``matlab_downsampled``     | 2    | Decimated 1-D variable (consent-gated) |
    | ``matlab_raw_array``       | 3    | Full numeric array, precision-reduced (cost-gated) |
    """

    def __init__(self, config_dir: Path, data_dir: Path):
        # Lazy scipy import — surfaces a clear error if the operator has
        # the matlab_file block in user_config.json but never installed
        # the [matlab] extra. Per the proposal-mode audit F3, the missing-
        # scipy case must be visible to the user, not silent.
        try:
            import scipy.io  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "MATLABFileChild requires scipy. Install with: "
                "pip install tailor-mcp[matlab]"
            ) from exc

        self._config_dir = config_dir
        self._data_dir = data_dir
        self._processing = MATLABProcessing()

        cfg = self._load_user_config(config_dir)
        mat_cfg = cfg.get("matlab_file", {})

        raw_path = mat_cfg.get("path")
        if not raw_path:
            raise ValueError(
                "matlab_file.path is required in user_config.json. "
                "Set it to the directory containing your .mat files."
            )
        self._mat_path = Path(raw_path).expanduser().resolve()
        if not self._mat_path.is_dir():
            log.warning(
                f"matlab_file.path does not exist or is not a directory: "
                f"{self._mat_path}. Tools will return errors until the "
                f"directory is created."
            )
        variable_filter = mat_cfg.get("variable_filter")
        if variable_filter and not isinstance(variable_filter, list):
            log.warning(
                "matlab_file.variable_filter must be a list of variable "
                "names; ignoring non-list value."
            )
            variable_filter = None
        self._variable_filter: list[str] | None = variable_filter

        log.info(
            f"MATLAB file child initialized "
            f"(path={self._mat_path}, "
            f"variable_filter={self._variable_filter or 'auto-detect'})"
        )

    @staticmethod
    def _load_user_config(config_dir: Path) -> dict:
        """Load user_config.json; return empty dict on missing/error."""
        path = config_dir / "user_config.json"
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError) as exc:
            log.warning(f"Could not read {path}: {exc}")
            return {}

    # ══════════════════════════════════════════════════════════
    # IDENTITY
    # ══════════════════════════════════════════════════════════

    @property
    def domain(self) -> str:
        return "matlab_file"

    @property
    def display_name(self) -> str:
        return "MATLAB File (.mat)"

    @property
    def vaultable_tools(self) -> list[str]:
        # No paired renderer in VaultWriter._renderers yet. Same posture
        # csv_dir adopted after the v6.5.0 mcp-protocol-auditor finding;
        # adding a tool here requires landing a renderer first.
        return []

    # ══════════════════════════════════════════════════════════
    # CONSENT
    # ══════════════════════════════════════════════════════════

    @property
    def consent_info(self) -> ConsentInfo:
        if self._variable_filter:
            data_types = list(self._variable_filter)
        else:
            data_types = ["MATLAB numeric variables"]
        return ConsentInfo(
            data_types=data_types,
            purpose="analysis of MATLAB binary `.mat` numeric variables",
            scope=ConsentScope(
                duration="session",
                duration_human="until this conversation ends",
                covers_future_calls=True,
                revocable=True,
                revoke_instruction="Say 'revoke MATLAB consent' at any time.",
            ),
        )

    def data_types_for_tool(self, tool_name: str, params: dict) -> list[str]:
        if tool_name in ("matlab_downsampled", "matlab_raw_array"):
            requested = params.get("variable")
            if requested:
                return [requested]
        return self.consent_info.data_types

    # ══════════════════════════════════════════════════════════
    # TOOL SURFACE
    # ══════════════════════════════════════════════════════════

    @property
    def tool_definitions(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                "matlab_list_files", 1,
                "List `.mat` files in the configured directory with their "
                "variable names, shapes, and dtypes. ~250 tokens.",
                {
                    "limit": {"type": "integer", "description": "Max files (default 20)", "required": False},
                    "subject_id": SUBJECT_ID_PARAM_DOC,
                },
            ),
            ToolDefinition(
                "matlab_file_detail", 1,
                "Single-file metadata: variables, shapes, dtypes, total bytes. "
                "Per-variable summary stats for numeric arrays.",
                {
                    "file_id": {"type": "string", "description": "`.mat` filename", "required": True},
                    "subject_id": SUBJECT_ID_PARAM_DOC,
                },
            ),
            ToolDefinition(
                "matlab_summary_report", 1,
                "Server-computed analytics across all numeric variables in a "
                "file: count/mean/std/min/max per variable. No raw arrays "
                "leave the server. ~800 tokens.",
                {
                    "file_id": {"type": "string", "description": "`.mat` filename", "required": True},
                    "subject_id": SUBJECT_ID_PARAM_DOC,
                },
            ),
            ToolDefinition(
                "matlab_cohort_summary", 1,
                "Cross-file cohort aggregation: groups every `.mat` in the "
                "directory by a metadata.json sidecar field, reduces the "
                "named variable to a per-file scalar, returns per-group "
                "n/mean/std/min/max. Requires metadata.json sidecar (per "
                "ADR 0015). ~350 tokens.",
                {
                    "variable": {"type": "string", "description": "Numeric variable name", "required": True},
                    "group_by": {"type": "string", "description": "Metadata field (e.g. 'sex', 'group')", "required": True},
                    "metric": {
                        "type": "string",
                        "description": (
                            f"Per-file reduction: {', '.join(COHORT_METRICS)}. "
                            "Default: mean."
                        ),
                        "required": False,
                    },
                    "subject_id": SUBJECT_ID_PARAM_DOC,
                },
            ),
            ToolDefinition(
                "matlab_downsampled", 2,
                "Decimated 1-D variable at every Nth interval for "
                "visualization. ~3000-7000 tokens. Requires consent.",
                {
                    "file_id": {"type": "string", "description": "`.mat` filename", "required": True},
                    "variable": {"type": "string", "description": "Variable name (must be 1-D numeric)", "required": True},
                    "interval": {
                        "type": "integer",
                        "description": "Decimation interval. Default 5.",
                        "required": False,
                    },
                    "subject_id": SUBJECT_ID_PARAM_DOC,
                },
            ),
            ToolDefinition(
                "matlab_raw_array", 3,
                "Full 1-D numeric variable with precision reduction. "
                "~25k-60k tokens. Requires consent + cost approval.",
                {
                    "file_id": {"type": "string", "description": "`.mat` filename", "required": True},
                    "variable": {"type": "string", "description": "Variable name (must be 1-D numeric)", "required": True},
                    "precision": {
                        "type": "integer",
                        "description": "Decimal places to keep. Default 4.",
                        "required": False,
                    },
                    "subject_id": SUBJECT_ID_PARAM_DOC,
                },
            ),
        ]

    @property
    def param_schemas(self) -> dict[str, dict[str, ValidationSchema]]:
        return {
            "matlab_list_files": {
                "limit": ValidationSchema(type=int, min=1, max=100, default=20),
                "subject_id": SUBJECT_ID_SCHEMA,
            },
            "matlab_file_detail": {
                "file_id": ValidationSchema(type=str, required=True, pattern=FILE_ID_PATTERN),
                "subject_id": SUBJECT_ID_SCHEMA,
            },
            "matlab_summary_report": {
                "file_id": ValidationSchema(type=str, required=True, pattern=FILE_ID_PATTERN),
                "subject_id": SUBJECT_ID_SCHEMA,
            },
            "matlab_cohort_summary": {
                "variable": ValidationSchema(type=str, required=True, pattern=VARIABLE_NAME_PATTERN),
                "group_by": ValidationSchema(type=str, required=True, pattern=r"^[A-Za-z0-9_\-]{1,64}$"),
                "metric": ValidationSchema(
                    type=str, required=False, allowed_values=list(COHORT_METRICS), default="mean",
                ),
                "subject_id": SUBJECT_ID_SCHEMA,
            },
            "matlab_downsampled": {
                "file_id": ValidationSchema(type=str, required=True, pattern=FILE_ID_PATTERN),
                "variable": ValidationSchema(type=str, required=True, pattern=VARIABLE_NAME_PATTERN),
                "interval": ValidationSchema(type=int, min=1, max=1000, default=5),
                "subject_id": SUBJECT_ID_SCHEMA,
            },
            "matlab_raw_array": {
                "file_id": ValidationSchema(type=str, required=True, pattern=FILE_ID_PATTERN),
                "variable": ValidationSchema(type=str, required=True, pattern=VARIABLE_NAME_PATTERN),
                "precision": ValidationSchema(type=int, min=0, max=12, default=4),
                "subject_id": SUBJECT_ID_SCHEMA,
            },
        }

    # ══════════════════════════════════════════════════════════
    # COST ESTIMATION
    # ══════════════════════════════════════════════════════════

    async def estimate_cost(self, tool_name: str, params: dict) -> CostEstimate:
        if tool_name != "matlab_raw_array":
            return CostEstimate(tokens=0)

        filepath = self._resolve_file(params.get("file_id", ""))
        if not filepath:
            return CostEstimate(tokens=0)

        # Cheap pre-estimate: file size in bytes / 8 (typical float64) gives
        # element count; assume 12 tokens per number after precision reduction.
        try:
            byte_size = filepath.stat().st_size
        except OSError:
            return CostEstimate(tokens=0)
        approx_elements = max(1, byte_size // 8)
        full_tokens = approx_elements * 12
        ds_tokens = max(1, full_tokens // 5)
        return CostEstimate(
            tokens=full_tokens,
            has_cheaper_alternative=True,
            alternative_tokens=ds_tokens,
            alternative_description=(
                "matlab_downsampled (every 5th element) — "
                "preserves curve shape, ~80% cheaper"
            ),
        )

    def purge_cache(self, *, force: bool = False) -> dict:
        """Per ADR 0013 — institutional source data, no derivative cache."""
        return {
            "rows_purged": 0,
            "tables_touched": [],
            "preserved": [],
            "reason": (
                "matlab_file reads `.mat` files at matlab_file.path; the "
                "framework owns no derivative cache to purge. Source-file "
                "retention is the deployer's responsibility per ADR 0013."
            ),
        }

    # ══════════════════════════════════════════════════════════
    # EXECUTION
    # ══════════════════════════════════════════════════════════

    async def execute(self, tool_name: str, params: dict) -> dict:
        handlers = {
            "matlab_list_files": self._handle_list_files,
            "matlab_file_detail": self._handle_file_detail,
            "matlab_summary_report": self._handle_summary_report,
            "matlab_cohort_summary": self._handle_cohort_summary,
            "matlab_downsampled": self._handle_downsampled,
            "matlab_raw_array": self._handle_raw_array,
        }
        handler = handlers.get(tool_name)
        if not handler:
            return {"error": f"Unknown tool: {tool_name}"}
        return await handler(params)

    # ── Private helpers ──

    def _resolve_file(self, file_id: str) -> Path | None:
        if not file_id:
            return None
        candidate = (self._mat_path / file_id).resolve()
        try:
            candidate.relative_to(self._mat_path)
        except ValueError:
            return None
        if not candidate.is_file():
            return None
        return candidate

    @staticmethod
    def _is_hdf5(filepath: Path) -> bool:
        """Detect `.mat` v7.3 (HDF5) format by magic bytes."""
        try:
            with open(filepath, "rb") as f:
                head = f.read(8)
            return head == HDF5_MAGIC
        except OSError:
            return False

    def _load_mat(self, filepath: Path) -> dict | str:
        """Load `.mat` v5/v6/v7.2 into a name→numpy-array dict.

        Returns an error string for any failure mode the user can
        recover from (size cap, v7.3 unsupported, scipy parse error).
        Re-parses on every call by design (ADR 0013, F4).
        """
        try:
            byte_size = filepath.stat().st_size
        except OSError as exc:
            return f"Could not stat {filepath.name}: {exc}"
        if byte_size > MAX_MAT_BYTES:
            size_mb = byte_size / (1024 * 1024)
            limit_mb = MAX_MAT_BYTES / (1024 * 1024)
            return (
                f"File too large ({size_mb:.1f} MB, limit {limit_mb:.1f} MB)."
            )
        if self._is_hdf5(filepath):
            return (
                f"{filepath.name} is a `.mat` v7.3 (HDF5) file. v7.3 is not "
                "supported in this child; see ADR 0036. Re-save the file "
                "with `-v7` in MATLAB or convert via "
                "`scipy.io.savemat(..., format='5')` if you control the "
                "export."
            )
        try:
            import scipy.io  # lazy import; module-level import was at __init__
            raw = scipy.io.loadmat(str(filepath), squeeze_me=True)
        except NotImplementedError as exc:
            return (
                f"Could not parse {filepath.name}: {exc}. "
                "This may be a `.mat` v7.3 file that slipped past the magic-"
                "byte check; see ADR 0036."
            )
        except (OSError, ValueError) as exc:
            return f"Could not parse {filepath.name}: {exc}"
        # Strip scipy's metadata keys (those starting with `__`).
        return {k: v for k, v in raw.items() if not k.startswith("__")}

    def _numeric_1d(self, array) -> list[float] | None:
        """Coerce a scipy-loaded variable to a 1-D Python float list, or
        ``None`` if it cannot be (string, struct, multi-dim with > 1 axis
        of size > 1, etc.)."""
        try:
            shape = array.shape
        except AttributeError:
            return None
        # 0-D scalar wrapped in a numpy array
        if shape == ():
            try:
                return [float(array.item())]
            except (TypeError, ValueError):
                return None
        # 1-D
        if len(shape) == 1:
            try:
                return [float(v) for v in array]
            except (TypeError, ValueError):
                return None
        # 2-D with one singleton axis (column or row vector)
        if len(shape) == 2 and 1 in shape:
            try:
                flat = array.flatten()
                return [float(v) for v in flat]
            except (TypeError, ValueError):
                return None
        return None

    def _variable_shape_str(self, array) -> str:
        try:
            return self._processing.describe_shape(tuple(array.shape))
        except AttributeError:
            return "scalar"

    def _variable_dtype_str(self, array) -> str:
        try:
            return str(array.dtype)
        except AttributeError:
            return type(array).__name__

    def _enumerate_variables(self, vars_dict: dict) -> list[dict]:
        """Surface variables as [{name, shape, dtype}] in stable order."""
        out: list[dict] = []
        for name in sorted(vars_dict.keys()):
            if self._variable_filter and name not in self._variable_filter:
                continue
            arr = vars_dict[name]
            out.append({
                "name": name,
                "shape": self._variable_shape_str(arr),
                "dtype": self._variable_dtype_str(arr),
            })
        return out

    def _load_metadata_sidecar(self) -> dict | None:
        """Load metadata.json sidecar; return ``None`` if absent.

        Per ADR 0015: schema is ``{"<filename>": {"<field>": <value>, ...}}``.
        """
        sidecar = self._mat_path / METADATA_FILENAME
        if not sidecar.is_file():
            return None
        try:
            return json.loads(sidecar.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError) as exc:
            log.warning(f"Could not read {sidecar}: {exc}")
            return None

    # ── Tier 1 handlers ──

    async def _handle_list_files(self, params: dict) -> dict:
        limit = params.get("limit", 20)
        if not self._mat_path.is_dir():
            return {"error": f"Directory not found: {self._mat_path}"}
        files = sorted(self._mat_path.glob("*.mat"))[:limit]
        results = []
        for f in files:
            vars_dict = self._load_mat(f)
            if isinstance(vars_dict, str):
                results.append({
                    "filename": f.name,
                    "size_bytes": f.stat().st_size,
                    "error": vars_dict,
                })
                continue
            results.append({
                "filename": f.name,
                "size_bytes": f.stat().st_size,
                "variables": self._enumerate_variables(vars_dict),
            })
        return {"count": len(results), "files": results}

    async def _handle_file_detail(self, params: dict) -> dict:
        filepath = self._resolve_file(params["file_id"])
        if not filepath:
            return {"error": f"File not found: {params['file_id']}"}
        vars_dict = self._load_mat(filepath)
        if isinstance(vars_dict, str):
            return {"error": vars_dict}
        variables: list[dict] = []
        for name in sorted(vars_dict.keys()):
            if self._variable_filter and name not in self._variable_filter:
                continue
            arr = vars_dict[name]
            entry: dict = {
                "name": name,
                "shape": self._variable_shape_str(arr),
                "dtype": self._variable_dtype_str(arr),
            }
            values = self._numeric_1d(arr)
            if values is not None:
                entry["summary"] = self._processing.summarize_array(values)
            else:
                entry["summary"] = {"unavailable": "not 1-D numeric"}
            variables.append(entry)
        return {
            "filename": filepath.name,
            "size_bytes": filepath.stat().st_size,
            "variables": variables,
        }

    async def _handle_summary_report(self, params: dict) -> dict:
        filepath = self._resolve_file(params["file_id"])
        if not filepath:
            return {"error": f"File not found: {params['file_id']}"}
        vars_dict = self._load_mat(filepath)
        if isinstance(vars_dict, str):
            return {"error": vars_dict}
        summaries: dict[str, dict] = {}
        skipped: list[str] = []
        for name in sorted(vars_dict.keys()):
            if self._variable_filter and name not in self._variable_filter:
                continue
            values = self._numeric_1d(vars_dict[name])
            if values is None:
                skipped.append(name)
                continue
            summaries[name] = self._processing.summarize_array(values)
        return {
            "filename": filepath.name,
            "numeric_summaries": summaries,
            "skipped_non_numeric": skipped,
        }

    async def _handle_cohort_summary(self, params: dict) -> dict:
        variable = params["variable"]
        group_by = params["group_by"]
        metric = params.get("metric", "mean")

        if not self._mat_path.is_dir():
            return {"error": f"Directory not found: {self._mat_path}"}

        sidecar = self._load_metadata_sidecar()
        if sidecar is None:
            return {
                "error": (
                    f"matlab_cohort_summary requires {METADATA_FILENAME} in "
                    f"{self._mat_path}. Schema per ADR 0015: "
                    "{filename: {field: value}}."
                ),
            }

        files = sorted(self._mat_path.glob("*.mat"))
        if len(files) > MAX_COHORT_FILES:
            return {
                "error": (
                    f"Cohort has {len(files)} files; cap is "
                    f"{MAX_COHORT_FILES}. Move out-of-scope files or "
                    "narrow the directory."
                ),
            }

        per_group: dict[str, list[float]] = {}
        missing_metadata: list[str] = []
        missing_group_field: list[str] = []
        variable_not_in_file: list[str] = []
        variable_wrong_shape: list[str] = []
        load_errors: list[dict] = []

        for f in files:
            meta = sidecar.get(f.name)
            if meta is None:
                missing_metadata.append(f.name)
                continue
            if group_by not in meta:
                missing_group_field.append(f.name)
                continue
            vars_dict = self._load_mat(f)
            if isinstance(vars_dict, str):
                load_errors.append({"filename": f.name, "error": vars_dict})
                continue
            if variable not in vars_dict:
                variable_not_in_file.append(f.name)
                continue
            values = self._numeric_1d(vars_dict[variable])
            if values is None:
                # The variable exists but its shape isn't 1-D numeric (e.g.
                # an 8×1000 cohort matrix where rows are subjects). v1
                # defers variables-as-subjects per ADR 0036; surfacing this
                # distinctly from a typo lets the recipient diagnose without
                # guessing.
                variable_wrong_shape.append(f.name)
                continue
            try:
                scalar = self._processing.aggregate_metric(values, metric)
            except ValueError as exc:
                return {"error": str(exc)}
            if scalar is None:
                continue
            group_key = str(meta[group_by])
            per_group.setdefault(group_key, []).append(scalar)

        groups = {
            key: self._processing.cohort_stats(scalars)
            for key, scalars in sorted(per_group.items())
        }
        result: dict = {
            "variable": variable,
            "group_by": group_by,
            "metric": metric,
            "n_files_scanned": len(files),
            "groups": groups,
            "missing_metadata": missing_metadata,
            "missing_group_field": missing_group_field,
            "variable_not_in_file": variable_not_in_file,
            "variable_wrong_shape": variable_wrong_shape,
            "load_errors": load_errors,
        }
        if variable_wrong_shape:
            result["variable_wrong_shape_note"] = (
                f"{len(variable_wrong_shape)} file(s) contained the variable "
                "but not as 1-D numeric (e.g. a 2-D cohort matrix). "
                "Variables-as-subjects shapes are deferred per ADR 0036; "
                "re-shape upstream or split into per-subject files."
            )
        return result

    # ── Tier 2 handler ──

    async def _handle_downsampled(self, params: dict) -> dict:
        filepath = self._resolve_file(params["file_id"])
        if not filepath:
            return {"error": f"File not found: {params['file_id']}"}
        variable = params["variable"]
        interval = params.get("interval", 5)
        vars_dict = self._load_mat(filepath)
        if isinstance(vars_dict, str):
            return {"error": vars_dict}
        if variable not in vars_dict:
            return {"error": f"Variable not found: {variable}"}
        values = self._numeric_1d(vars_dict[variable])
        if values is None:
            return {"error": f"Variable {variable} is not 1-D numeric."}
        return {
            "filename": filepath.name,
            "variable": variable,
            "interval": interval,
            "samples": self._processing.downsample(values, interval),
        }

    # ── Tier 3 handler ──

    async def _handle_raw_array(self, params: dict) -> dict:
        filepath = self._resolve_file(params["file_id"])
        if not filepath:
            return {"error": f"File not found: {params['file_id']}"}
        variable = params["variable"]
        precision = params.get("precision", 4)
        vars_dict = self._load_mat(filepath)
        if isinstance(vars_dict, str):
            return {"error": vars_dict}
        if variable not in vars_dict:
            return {"error": f"Variable not found: {variable}"}
        values = self._numeric_1d(vars_dict[variable])
        if values is None:
            return {"error": f"Variable {variable} is not 1-D numeric."}
        return {
            "filename": filepath.name,
            "variable": variable,
            "precision": precision,
            "samples": self._processing.reduce_precision(values, precision),
        }
