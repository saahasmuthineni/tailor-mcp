"""
Strong-Motion Child MCP — COSMOS V1 Acceleration Records
=========================================================
Wraps a local directory of COSMOS Volume-1 (uncorrected acceleration)
strong-motion records and exposes tiered analytical tools through the
framework's security pipeline. Stdlib-only — the V1 format is
fixed-width text (see ``parser.py``); no optional extra, unlike the
MATLAB child's scipy dependency.

This is the launch worked-example child (issue #114): a researcher
points Tailor at strong-motion records they fetched from CESMD and asks
recognizable engineering questions — peak ground acceleration, Arias
intensity, significant duration, response spectra — without the raw
trace ever entering the LLM's context at Tier 1.

Config shape (in ``~/.tailor/user_config.json``):

.. code-block:: json

    {
      "strong_motion": {
        "path": "/path/to/cosmos/v1/directory"
      }
    }

Record files are recognized by extension (``.v1`` / ``.raw``,
case-insensitive). One file = one channel = one record.

Subject scoping per ADR 0002 / ADR 0009: ``entity_id`` is the
station-event code (one record). It is audit-log scoping only and does
NOT filter source data — there is one record per call.

ADR 0013 ``purge_cache``: no-op — the framework owns no derivative
cache. Records are re-parsed from disk on every call.
"""

from __future__ import annotations

import json
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
from .parser import ParseRefusalError, StrongMotionRecord, parse_v1_file
from .processing import RECORD_METRICS, SA_PERIODS, StrongMotionProcessing

log = logging.getLogger("tailor.strong_motion")

FILE_ID_PATTERN = r"^[A-Za-z0-9_\-\.]{1,255}$"

# 100 MB file-size cap; matches matlab_file.MAX_MAT_BYTES.
MAX_RECORD_BYTES = 100 * 1024 * 1024
# 64-record cohort cap; matches matlab/csv_dir (ADR 0009 pilot scale).
MAX_COHORT_FILES = 64
# Sidecar metadata filename per ADR 0015.
METADATA_FILENAME = "metadata.json"
# Recognized COSMOS V1 record extensions (case-insensitive).
RECORD_SUFFIXES = (".v1", ".raw")


class StrongMotionChild(ChildMCP):
    """
    Strong-motion COSMOS V1 child — five tools across all three tiers.

    | Tool                       | Tier | Purpose                              |
    |----------------------------|------|--------------------------------------|
    | ``seismic_list_records``   | 1    | List V1 record files + channel meta  |
    | ``seismic_record_summary`` | 1    | PGA, Arias, duration, Sa(T)          |
    | ``seismic_cohort_summary`` | 1    | Cross-record stats (optional sidecar)|
    | ``seismic_downsampled``    | 2    | Decimated acceleration trace         |
    | ``seismic_full_trace``     | 3    | Full per-sample acceleration trace   |
    """

    def __init__(self, config_dir: Path, data_dir: Path):
        self._config_dir = config_dir
        self._data_dir = data_dir
        self._processing = StrongMotionProcessing()

        cfg = self._load_user_config(config_dir)
        sm_cfg = cfg.get("strong_motion", {})
        if not isinstance(sm_cfg, dict):
            raise ValueError(
                "strong_motion block in user_config.json must be a JSON "
                "object (got a non-object value)."
            )

        raw_path = sm_cfg.get("path")
        if not raw_path:
            raise ValueError(
                "strong_motion.path is required in user_config.json. "
                "Set it to the directory containing your COSMOS V1 records."
            )
        if not isinstance(raw_path, str):
            # A non-string path (number / bool / list) would raise
            # TypeError in Path(), which __main__'s registration guard
            # does not catch — crashing serve boot for every child. Raise
            # ValueError instead so registration fails gracefully.
            raise ValueError(
                "strong_motion.path must be a string (the directory "
                "containing your COSMOS V1 records)."
            )
        self._sm_path = Path(raw_path).expanduser().resolve()
        if not self._sm_path.is_dir():
            log.warning(
                f"strong_motion.path does not exist or is not a directory: "
                f"{self._sm_path}. Tools will return errors until the "
                f"directory is created."
            )
        log.info(f"Strong-motion child initialized (path={self._sm_path})")

    @staticmethod
    def _load_user_config(config_dir: Path) -> dict:
        """Load user_config.json; return empty dict on missing/error."""
        path = config_dir / "user_config.json"
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError) as exc:
            log.warning(f"Could not read {path}: {exc}")
            return {}
        if not isinstance(data, dict):
            # A top-level non-object user_config.json would AttributeError
            # on the caller's .get(); fail soft to an empty config.
            log.warning(f"{path} is not a JSON object; ignoring.")
            return {}
        return data

    # ══════════════════════════════════════════════════════════
    # IDENTITY
    # ══════════════════════════════════════════════════════════

    @property
    def domain(self) -> str:
        return "strong_motion"

    @property
    def display_name(self) -> str:
        return "Strong Motion (COSMOS V1)"

    @property
    def vaultable_tools(self) -> list[str]:
        # No paired renderer in VaultWriter._renderers yet — same posture
        # as matlab_file/csv_dir. Adding a vaultable tool here requires
        # landing a renderer first.
        return []

    # ══════════════════════════════════════════════════════════
    # CONSENT
    # ══════════════════════════════════════════════════════════

    @property
    def consent_info(self) -> ConsentInfo:
        return ConsentInfo(
            data_types=[
                "ground acceleration (PGA)",
                "seismic event acceleration trace",
            ],
            purpose=(
                "strong-motion seismic record analysis (peak acceleration, "
                "Arias intensity, response spectra)"
            ),
            scope=ConsentScope(
                duration="session",
                duration_human="until this conversation ends",
                covers_future_calls=True,
                revocable=True,
                revoke_instruction="Say 'revoke strong motion consent' at any time.",
            ),
        )

    # ══════════════════════════════════════════════════════════
    # TOOL SURFACE
    # ══════════════════════════════════════════════════════════

    @property
    def tool_definitions(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                "seismic_list_records", 1,
                "List COSMOS V1 strong-motion record files in the configured "
                "directory with station, channel, azimuth, and sample count. "
                "~250 tokens.",
                {
                    "limit": {"type": "integer", "description": "Max records (default 20)", "required": False},
                    "entity_id": ENTITY_ID_PARAM_DOC,
                },
            ),
            ToolDefinition(
                "seismic_record_summary", 1,
                "Server-computed engineering summary for one record: peak "
                "ground acceleration (g), Arias intensity (m/s), 5-95% "
                "significant duration (s), and 5%-damped spectral "
                "acceleration Sa(T) at T="
                f"{', '.join(str(p) for p in SA_PERIODS)} s. No raw trace "
                "leaves the server. ~600 tokens.",
                {
                    "file_id": {"type": "string", "description": "Record filename (.v1 / .raw)", "required": True},
                    "entity_id": ENTITY_ID_PARAM_DOC,
                },
            ),
            ToolDefinition(
                "seismic_cohort_summary", 1,
                "Cross-record cohort aggregation: reduces every record in the "
                "directory to one scalar (pga_g, arias_intensity, or "
                "strong_motion_duration_s) and returns n/mean/std/min/max. "
                "Groups by a metadata.json sidecar field if 'group_by' is "
                "given (per ADR 0015); otherwise aggregates all records as a "
                "single cohort. ~350 tokens.",
                {
                    "metric": {
                        "type": "string",
                        "description": (
                            f"Per-record scalar: {', '.join(RECORD_METRICS)}. "
                            "Default: pga_g."
                        ),
                        "required": False,
                    },
                    "group_by": {
                        "type": "string",
                        "description": "Optional metadata.json field (e.g. 'site', 'event'). Requires sidecar.",
                        "required": False,
                    },
                    "entity_id": ENTITY_ID_PARAM_DOC,
                },
            ),
            ToolDefinition(
                "seismic_downsampled", 2,
                "Decimated acceleration trace (every Nth sample) for plotting. "
                "~3000-7000 tokens. Requires consent.",
                {
                    "file_id": {"type": "string", "description": "Record filename (.v1 / .raw)", "required": True},
                    "interval": {
                        "type": "integer",
                        "description": "Decimation interval. Default 5.",
                        "required": False,
                    },
                    "entity_id": ENTITY_ID_PARAM_DOC,
                },
            ),
            ToolDefinition(
                "seismic_full_trace", 3,
                "Full per-sample acceleration trace with precision reduction. "
                "~25k-60k tokens. Requires consent + cost approval.",
                {
                    "file_id": {"type": "string", "description": "Record filename (.v1 / .raw)", "required": True},
                    "precision": {
                        "type": "integer",
                        "description": "Decimal places to keep. Default 4.",
                        "required": False,
                    },
                    "entity_id": ENTITY_ID_PARAM_DOC,
                },
            ),
        ]

    @property
    def param_schemas(self) -> dict[str, dict[str, ValidationSchema]]:
        return {
            "seismic_list_records": {
                "limit": ValidationSchema(type=int, min=1, max=100, default=20),
                "entity_id": ENTITY_ID_SCHEMA,
            },
            "seismic_record_summary": {
                "file_id": ValidationSchema(type=str, required=True, pattern=FILE_ID_PATTERN),
                "entity_id": ENTITY_ID_SCHEMA,
            },
            "seismic_cohort_summary": {
                "metric": ValidationSchema(
                    type=str, required=False,
                    allowed_values=list(RECORD_METRICS), default="pga_g",
                ),
                "group_by": ValidationSchema(
                    type=str, required=False, pattern=r"^[A-Za-z0-9_\-]{1,64}$",
                ),
                "entity_id": ENTITY_ID_SCHEMA,
            },
            "seismic_downsampled": {
                "file_id": ValidationSchema(type=str, required=True, pattern=FILE_ID_PATTERN),
                "interval": ValidationSchema(type=int, min=1, max=1000, default=5),
                "entity_id": ENTITY_ID_SCHEMA,
            },
            "seismic_full_trace": {
                "file_id": ValidationSchema(type=str, required=True, pattern=FILE_ID_PATTERN),
                "precision": ValidationSchema(type=int, min=0, max=12, default=4),
                "entity_id": ENTITY_ID_SCHEMA,
            },
        }

    # ══════════════════════════════════════════════════════════
    # COST ESTIMATION
    # ══════════════════════════════════════════════════════════

    async def estimate_cost(self, tool_name: str, params: dict) -> CostEstimate:
        if tool_name != "seismic_full_trace":
            return CostEstimate(tokens=0)

        filepath = self._resolve_file(params.get("file_id", ""))
        if not filepath:
            return CostEstimate(tokens=0)
        try:
            byte_size = filepath.stat().st_size
        except OSError:
            return CostEstimate(tokens=0)
        # Cheap pre-estimate: V1 data is two 7-char fields per sample
        # (time + accel); ~8 tokens per emitted accel value after
        # precision reduction.
        approx_samples = max(1, byte_size // (2 * 7))
        full_tokens = approx_samples * 8
        ds_tokens = max(1, full_tokens // 5)
        return CostEstimate(
            tokens=full_tokens,
            has_cheaper_alternative=True,
            alternative_tokens=ds_tokens,
            alternative_description=(
                "seismic_downsampled (every 5th sample) — "
                "preserves trace shape, ~80% cheaper"
            ),
        )

    def purge_cache(self, *, force: bool = False) -> dict:
        """Per ADR 0013 — institutional source data, no derivative cache."""
        return {
            "rows_purged": 0,
            "tables_touched": [],
            "preserved": [],
            "reason": (
                "strong_motion reads COSMOS V1 files at strong_motion.path; "
                "the framework owns no derivative cache to purge. Source-file "
                "retention is the deployer's responsibility per ADR 0013."
            ),
        }

    # ══════════════════════════════════════════════════════════
    # EXECUTION
    # ══════════════════════════════════════════════════════════

    async def execute(self, tool_name: str, params: dict) -> dict:
        handlers = {
            "seismic_list_records": self._handle_list_records,
            "seismic_record_summary": self._handle_record_summary,
            "seismic_cohort_summary": self._handle_cohort_summary,
            "seismic_downsampled": self._handle_downsampled,
            "seismic_full_trace": self._handle_full_trace,
        }
        handler = handlers.get(tool_name)
        if not handler:
            return {"error": f"Unknown tool: {tool_name}"}
        return await handler(params)

    # ── Private helpers ──

    def _list_record_files(self) -> list[Path]:
        if not self._sm_path.is_dir():
            return []
        try:
            return sorted(
                p for p in self._sm_path.iterdir()
                if p.is_file() and p.suffix.lower() in RECORD_SUFFIXES
            )
        except OSError as exc:
            # Directory became unreadable (permissions / I/O) after the
            # is_dir() check — return empty rather than crash the tool.
            log.error(f"Failed to list {self._sm_path}: {exc}")
            return []

    def _resolve_file(self, file_id: str) -> Path | None:
        if not file_id:
            return None
        candidate = (self._sm_path / file_id).resolve()
        try:
            candidate.relative_to(self._sm_path)
        except ValueError:
            return None
        if not candidate.is_file():
            return None
        return candidate

    def _load_record(self, filepath: Path) -> StrongMotionRecord | str:
        """Parse a record; return an error string for recoverable failures.

        Catches :class:`ParseRefusalError` here (rather than letting it
        propagate to the router) so a single non-V1 file surfaces a clear
        per-file error instead of tripping the per-domain circuit breaker.
        Re-parses on every call by design (ADR 0013).
        """
        try:
            byte_size = filepath.stat().st_size
        except OSError as exc:
            return f"Could not stat {filepath.name}: {exc}"
        if byte_size > MAX_RECORD_BYTES:
            size_mb = byte_size / (1024 * 1024)
            limit_mb = MAX_RECORD_BYTES / (1024 * 1024)
            return f"File too large ({size_mb:.1f} MB, limit {limit_mb:.1f} MB)."
        try:
            return parse_v1_file(filepath)
        except (ParseRefusalError, OSError) as exc:
            return str(exc)

    def _record_scalar(self, rec: StrongMotionRecord, metric: str) -> float | None:
        if metric == "pga_g":
            return self._processing.peak_acceleration_g(rec.accel_g)
        if metric == "arias_intensity":
            return self._processing.arias_intensity(rec.accel_g, rec.dt)
        if metric == "strong_motion_duration_s":
            return self._processing.strong_motion_duration(rec.accel_g, rec.dt)
        return None  # pragma: no cover — guarded by allowed_values

    def _load_metadata_sidecar(self) -> dict | None:
        """Load metadata.json sidecar; return ``None`` if absent (ADR 0015)."""
        sidecar = self._sm_path / METADATA_FILENAME
        if not sidecar.is_file():
            return None
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError) as exc:
            log.warning(f"Could not read {sidecar}: {exc}")
            return None
        if not isinstance(data, dict):
            log.warning(f"{sidecar} is not a JSON object; ignoring sidecar.")
            return None
        return data

    # ── Tier 1 handlers ──

    async def _handle_list_records(self, params: dict) -> dict:
        limit = params.get("limit", 20)
        if not self._sm_path.is_dir():
            return {"error": f"Directory not found: {self._sm_path}"}
        files = self._list_record_files()[:limit]
        results: list[dict] = []
        for f in files:
            try:
                size_bytes = f.stat().st_size
            except OSError:
                # File vanished / became inaccessible between listing and
                # this stat — report it rather than crashing the whole
                # listing tool. (stat() once, guarded; reused in both
                # branches below.)
                size_bytes = 0
            rec = self._load_record(f)
            if isinstance(rec, str):
                results.append({
                    "filename": f.name,
                    "size_bytes": size_bytes,
                    "error": rec,
                })
                continue
            results.append({
                "filename": f.name,
                "size_bytes": size_bytes,
                "station": rec.station,
                "channel": rec.channel,
                "azimuth": rec.azimuth,
                "n_samples": rec.npts,
                "dt_s": rec.dt,
            })
        return {"count": len(results), "records": results}

    async def _handle_record_summary(self, params: dict) -> dict:
        filepath = self._resolve_file(params["file_id"])
        if not filepath:
            return {"error": f"File not found: {params['file_id']}"}
        rec = self._load_record(filepath)
        if isinstance(rec, str):
            return {"error": rec}

        pga = self._processing.peak_acceleration_g(rec.accel_g)
        arias = self._processing.arias_intensity(rec.accel_g, rec.dt)
        duration = self._processing.strong_motion_duration(rec.accel_g, rec.dt)
        spectrum = self._processing.response_spectrum_sa(rec.accel_g, rec.dt)
        return {
            "filename": filepath.name,
            "station": rec.station,
            "channel": rec.channel,
            "azimuth": rec.azimuth,
            "n_samples": rec.npts,
            "dt_s": rec.dt,
            "record_duration_s": round((rec.npts - 1) * rec.dt, 6) if rec.npts > 1 else 0.0,
            "units_note": rec.units_note,
            "pga_g": round(pga, 6) if pga is not None else None,
            "arias_intensity_ms": round(arias, 6),
            "strong_motion_duration_s": duration,
            "spectral_acceleration_g": spectrum,
        }

    async def _handle_cohort_summary(self, params: dict) -> dict:
        metric = params.get("metric", "pga_g")
        group_by = params.get("group_by")

        if not self._sm_path.is_dir():
            return {"error": f"Directory not found: {self._sm_path}"}

        sidecar: dict | None = None
        if group_by:
            sidecar = self._load_metadata_sidecar()
            if sidecar is None:
                return {
                    "error": (
                        f"seismic_cohort_summary with group_by requires "
                        f"{METADATA_FILENAME} in {self._sm_path}. Schema per "
                        "ADR 0015: {filename: {field: value}}. Omit group_by "
                        "to aggregate all records as a single cohort."
                    ),
                }

        files = self._list_record_files()
        if len(files) > MAX_COHORT_FILES:
            return {
                "error": (
                    f"Cohort has {len(files)} records; cap is "
                    f"{MAX_COHORT_FILES}. Narrow the directory."
                ),
            }

        per_group: dict[str, list[float]] = {}
        missing_metadata: list[str] = []
        missing_group_field: list[str] = []
        load_errors: list[dict] = []

        for f in files:
            if group_by:
                meta = sidecar.get(f.name)
                if not isinstance(meta, dict):
                    missing_metadata.append(f.name)
                    continue
                if group_by not in meta:
                    missing_group_field.append(f.name)
                    continue
                group_key = str(meta[group_by])
            else:
                group_key = "all"

            rec = self._load_record(f)
            if isinstance(rec, str):
                load_errors.append({"filename": f.name, "error": rec})
                continue
            scalar = self._record_scalar(rec, metric)
            if scalar is None:
                continue
            per_group.setdefault(group_key, []).append(scalar)

        groups = {
            key: self._processing.cohort_stats(scalars)
            for key, scalars in sorted(per_group.items())
        }
        return {
            "metric": metric,
            "group_by": group_by,
            "n_records_scanned": len(files),
            "groups": groups,
            "missing_metadata": missing_metadata,
            "missing_group_field": missing_group_field,
            "load_errors": load_errors,
        }

    # ── Tier 2 handler ──

    async def _handle_downsampled(self, params: dict) -> dict:
        filepath = self._resolve_file(params["file_id"])
        if not filepath:
            return {"error": f"File not found: {params['file_id']}"}
        interval = params.get("interval", 5)
        rec = self._load_record(filepath)
        if isinstance(rec, str):
            return {"error": rec}
        return {
            "filename": filepath.name,
            "channel": rec.channel,
            "azimuth": rec.azimuth,
            "interval": interval,
            "dt_s": rec.dt,
            "units": "g",
            "samples": self._processing.downsample(rec.accel_g, interval),
        }

    # ── Tier 3 handler ──

    async def _handle_full_trace(self, params: dict) -> dict:
        filepath = self._resolve_file(params["file_id"])
        if not filepath:
            return {"error": f"File not found: {params['file_id']}"}
        precision = params.get("precision", 4)
        rec = self._load_record(filepath)
        if isinstance(rec, str):
            return {"error": rec}
        return {
            "filename": filepath.name,
            "channel": rec.channel,
            "azimuth": rec.azimuth,
            "n_samples": rec.npts,
            "dt_s": rec.dt,
            "precision": precision,
            "units": "g",
            "samples": self._processing.reduce_precision(rec.accel_g, precision),
        }
