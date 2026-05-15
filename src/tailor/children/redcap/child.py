"""
REDCap File Child MCP — Export-Directory Ingestion
=====================================================
Wraps a local directory of REDCap CSV/JSON exports + a REDCap data
dictionary (``project_metadata.csv``) and exposes tiered analytical
tools through the framework's security pipeline.

Scope per ADR 0037: this child supports REDCap **export-directory
wrapping only**. The live REDCap REST API is deferred behind a future
superseding ADR.

Built-in PHI scrubbing per ADR 0003 § Amendment 2026-05-14: the child
ships ``RedcapPHIScrubber``, a parallel seam to the framework-level
``PHIScrubber``. The child-level scrubber reads ``project_metadata.csv``
identifier flags set by the IRB at protocol creation and strips
identifier-flagged fields from every Tier-1+ result before return.
Unknown fields default to identifier-positive (fail-closed).

Subject scoping per ADR 0009: ``record_id`` is the ``subject_id``.
``redcap_event_name`` is a grouping dimension (NOT subject scoping)
because longitudinal REDCap projects emit one row per
(subject, event) — literal "one record = one subject" is wrong for
the ~70% of REDCap projects that use longitudinal arms. The cohort
tools accept an optional ``event`` parameter to filter to a single
event; absent that parameter the cohort aggregates across all events.

Config shape (in ``~/.tailor/user_config.json``):

.. code-block:: json

    {
      "redcap_file": {
        "path": "/path/to/redcap/export",
        "records_file": "records.csv",
        "project_metadata_file": "project_metadata.csv",
        "instrument_completion_fields": ["demographics_complete", "phq9_complete"],
        "unknown_field_allowlist": ["computed_score_v2"]
      }
    }

All keys except ``path`` are optional. Defaults:
``records_file="records.csv"``,
``project_metadata_file="project_metadata.csv"``.

ADR 0013 ``purge_cache``: no-op — the framework owns no derivative
cache. Records are re-parsed from disk on every call.
"""

from __future__ import annotations

import csv
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
from .processing import (
    COHORT_METRICS,
    DEFAULT_SMALL_CELL_THRESHOLD,
    RedcapProcessing,
)
from .scrubber import RedcapPHIScrubber

log = logging.getLogger("tailor.redcap")


class RedcapMetadataFingerprintMismatch(Exception):
    """Per ADR 0003 § Amendment 2026-05-15 — trust-root attestation
    drift detected.

    Raised by ``RedcapFileChild._detect_fingerprint_mismatch`` when the
    on-disk fingerprint of ``project_metadata.csv`` differs from the
    scrubber's cached fingerprint at server-boot time. The router's
    exception handler records an ``outcome=ERROR`` audit row carrying
    both fingerprints in the error column (``error LIKE
    'REDCAP_METADATA_FINGERPRINT_MISMATCH:%'``) — queryable by IRB
    review to correlate any disclosure with the trust-root state
    actually on disk at the moment of detection.

    ``__str__`` returns the operator-facing message including both
    fingerprints in a parseable form so the LLM transcript carries the
    same information the audit row carries. Closes the
    phi-irb-risk-reviewer Lens 3 VIOLATION-2 finding that a
    dict-return shape would leak the on-disk fingerprint only into the
    wire transcript while the audit row stamped the wrong (boot-time)
    value under outcome=SUCCESS.
    """

    def __init__(
        self,
        fingerprint_at_boot: str,
        fingerprint_on_disk: str,
    ):
        self.fingerprint_at_boot = fingerprint_at_boot
        self.fingerprint_on_disk = fingerprint_on_disk
        super().__init__(
            f"REDCAP_METADATA_FINGERPRINT_MISMATCH: "
            f"project_metadata.csv has changed since this server boot. "
            f"The scrubber's identifier-flag attestation is no longer "
            f"current. Run `tailor redcap reattest` to review the new "
            f"state and re-attest, then restart `tailor serve` to "
            f"reload the trust root. "
            f"fingerprint_at_boot={fingerprint_at_boot} "
            f"fingerprint_on_disk={fingerprint_on_disk}. "
            f"See ADR 0003 § Amendment 2026-05-15."
        )

RECORD_ID_PATTERN = r"^[A-Za-z0-9_\-\.]{1,255}$"
INSTRUMENT_NAME_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]{0,63}$"
FIELD_NAME_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]{0,63}$"
EVENT_NAME_PATTERN = r"^[A-Za-z0-9_\-]{1,64}$"
GROUP_BY_PATTERN = r"^[A-Za-z0-9_\-]{1,64}$"

# Cap on records returned in one call. Matches the pilot-scale cap
# established by csv_dir.MAX_COHORT_FILES (64) / ADR 0009 but scaled
# up because REDCap records are smaller per-unit than CSV files.
MAX_RECORDS = 10_000

# Sidecar metadata filename per ADR 0015 (cohort grouping sidecar —
# separate from project_metadata.csv, the REDCap data dictionary).
METADATA_FILENAME = "metadata.json"

# REDCap-reserved columns that are not data fields (they describe the
# row, not the participant's answers). Excluded from per-field
# summaries and identifier scrubbing because they're structural.
REDCAP_STRUCTURAL_COLUMNS = frozenset({
    "record_id",
    "redcap_event_name",
    "redcap_repeat_instrument",
    "redcap_repeat_instance",
    "redcap_data_access_group",
})


class RedcapFileChild(ChildMCP):
    """
    REDCap export-directory child — six tools across all three tiers.

    | Tool                       | Tier | Purpose                                |
    |----------------------------|------|----------------------------------------|
    | ``redcap_list_records``    | 1    | List record_ids with completion flags  |
    | ``redcap_record_detail``   | 1    | Single-record summary (non-identifier) |
    | ``redcap_summary_report``  | 1    | Per-instrument completion + per-field stats |
    | ``redcap_cohort_summary``  | 1    | Cross-record aggregation by group      |
    | ``redcap_records``         | 2    | All subjects' answers to one instrument |
    | ``redcap_raw_records``     | 3    | All subjects, all events, all fields   |
    """

    def __init__(self, config_dir: Path, data_dir: Path):
        self._config_dir = config_dir
        self._data_dir = data_dir
        self._processing = RedcapProcessing()

        cfg = self._load_user_config(config_dir)
        redcap_cfg = cfg.get("redcap_file", {})

        raw_path = redcap_cfg.get("path")
        if not raw_path:
            raise ValueError(
                "redcap_file.path is required in user_config.json. "
                "Set it to the directory containing your REDCap exports."
            )
        self._redcap_path = Path(raw_path).expanduser().resolve()
        if not self._redcap_path.is_dir():
            log.warning(
                f"redcap_file.path does not exist or is not a directory: "
                f"{self._redcap_path}. Tools will return errors until the "
                f"directory is created."
            )

        self._records_filename: str = redcap_cfg.get("records_file", "records.csv")
        self._project_metadata_filename: str = redcap_cfg.get(
            "project_metadata_file", "project_metadata.csv",
        )
        self._instrument_completion_fields: list[str] = list(
            redcap_cfg.get("instrument_completion_fields", []) or []
        )
        unknown_field_allowlist = redcap_cfg.get("unknown_field_allowlist") or []
        if not isinstance(unknown_field_allowlist, list):
            log.warning(
                "redcap_file.unknown_field_allowlist must be a list of field "
                "names; ignoring non-list value."
            )
            unknown_field_allowlist = []

        # ADR 0003 § Amendment 2026-05-15 — small-cell suppression
        # threshold. Optional config; defaults to k=5 (HHS SDL
        # baseline). Validated >= 2 at config-load time so a permissive
        # k=1 misconfig is refused loudly here rather than silently
        # ignored at call time. We also track whether the operator set
        # the threshold explicitly — when the default is in force, the
        # child surfaces a small_cell_warning in every result envelope
        # so the deployment-time setting is visible to IRB review.
        raw_threshold = redcap_cfg.get("small_cell_suppression_threshold")
        self._small_cell_default_in_force = raw_threshold is None
        if raw_threshold is None:
            self._small_cell_threshold = DEFAULT_SMALL_CELL_THRESHOLD
        else:
            try:
                parsed = int(raw_threshold)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"redcap_file.small_cell_suppression_threshold must be an "
                    f"integer >= 2; got {raw_threshold!r}"
                ) from exc
            if parsed < 2:
                raise ValueError(
                    f"redcap_file.small_cell_suppression_threshold must be "
                    f">= 2; got {parsed} (k=1 disables suppression and is "
                    f"refused as a permissive misconfiguration; see ADR 0003 "
                    f"§ Amendment 2026-05-15)"
                )
            self._small_cell_threshold = parsed

        # Initialise the child-level scrubber once at construction
        # time. It tolerates a missing project_metadata.csv (its
        # ``child_scrubber_warning`` property surfaces the
        # misconfiguration into result _meta blocks).
        self._scrubber = RedcapPHIScrubber(
            project_metadata_path=self._redcap_path / self._project_metadata_filename,
            unknown_field_allowlist=unknown_field_allowlist,
        )

        log.info(
            f"REDCap file child initialized "
            f"(path={self._redcap_path}, "
            f"records_file={self._records_filename}, "
            f"project_metadata_file={self._project_metadata_filename})"
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
        return "redcap_file"

    @property
    def display_name(self) -> str:
        return "REDCap Export"

    @property
    def vaultable_tools(self) -> list[str]:
        # No paired renderer in VaultWriter._renderers yet. Same posture
        # as matlab_file / csv_dir.
        return []

    @property
    def child_scrubber_id(self) -> str | None:
        """Per ADR 0037 — surfaced into the audit-log
        ``child_scrubber_id`` column. The framework reads this on
        SUCCESS rows.
        """
        return self._scrubber.scrubber_id if self._scrubber else None

    @property
    def child_source_metadata_fingerprint(self) -> str | None:
        """Per ADR 0003 § Amendment 2026-05-15 — SHA-256 fingerprint of
        the scrubber's canonical-form trust-root state at construction
        time. Stamped into the audit-log ``source_metadata_fingerprint``
        column and surfaced into result ``_meta`` so an IRB reviewer
        can correlate any disclosure with the
        ``project_metadata.csv`` state in force when the disclosure
        occurred.
        """
        return self._scrubber.fingerprint if self._scrubber else None

    # ══════════════════════════════════════════════════════════
    # CONSENT
    # ══════════════════════════════════════════════════════════

    @property
    def consent_info(self) -> ConsentInfo:
        data_types = ["REDCap participant records"]
        return ConsentInfo(
            data_types=data_types,
            purpose="analysis of REDCap-captured participant records",
            scope=ConsentScope(
                duration="session",
                duration_human="until this conversation ends",
                covers_future_calls=True,
                revocable=True,
                revoke_instruction="Say 'revoke REDCap consent' at any time.",
            ),
        )

    def data_types_for_tool(self, tool_name: str, params: dict) -> list[str]:
        if tool_name == "redcap_records":
            instrument = params.get("instrument")
            if instrument:
                return [f"REDCap instrument: {instrument}"]
        if tool_name == "redcap_raw_records":
            return ["REDCap all instruments (full project export)"]
        return self.consent_info.data_types

    # ══════════════════════════════════════════════════════════
    # TOOL SURFACE
    # ══════════════════════════════════════════════════════════

    @property
    def tool_definitions(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                "redcap_list_records", 1,
                "List REDCap record_ids with per-instrument completion "
                "flags and longitudinal-event coverage. Identifier fields "
                "are never included. ~500 tokens.",
                {
                    "limit": {
                        "type": "integer",
                        "description": "Max records (default 50, max 500)",
                        "required": False,
                    },
                    "subject_id": SUBJECT_ID_PARAM_DOC,
                },
            ),
            ToolDefinition(
                "redcap_record_detail", 1,
                "Single-record summary: non-identifier fields only, "
                "grouped by instrument. Identifier fields are stripped per "
                "project_metadata.csv flags; unknown fields are stripped "
                "by fail-closed default (see legibility fields in the "
                "result). ~800 tokens.",
                {
                    "record_id": {
                        "type": "string",
                        "description": "REDCap record_id",
                        "required": True,
                    },
                    "event": {
                        "type": "string",
                        "description": (
                            "Optional redcap_event_name filter "
                            "(longitudinal projects)"
                        ),
                        "required": False,
                    },
                    "subject_id": SUBJECT_ID_PARAM_DOC,
                },
            ),
            ToolDefinition(
                "redcap_summary_report", 1,
                "Server-computed analytics across the project: "
                "per-instrument completion counts; per-field "
                "cardinality and distribution. No identifier fields "
                "surface. ~1500 tokens.",
                {
                    "instrument": {
                        "type": "string",
                        "description": (
                            "Optional instrument name to narrow the "
                            "report to one form."
                        ),
                        "required": False,
                    },
                    "subject_id": SUBJECT_ID_PARAM_DOC,
                },
            ),
            ToolDefinition(
                "redcap_cohort_summary", 1,
                "Cross-record cohort aggregation: groups records by "
                "``group_by`` (a field name in project_metadata.csv "
                "OR a sidecar metadata.json field per ADR 0015), "
                "reduces ``field`` to a per-record scalar via "
                "``metric``, returns per-group n/mean/std/min/max (or "
                "mode/cardinality for categorical fields). Refuses to "
                "group by identifier-flagged fields to prevent PHI "
                "leakage through group-key cardinality. ~600 tokens.",
                {
                    "field": {
                        "type": "string",
                        "description": (
                            "Field to aggregate (must be non-identifier)"
                        ),
                        "required": True,
                    },
                    "group_by": {
                        "type": "string",
                        "description": (
                            "Grouping field (must be non-identifier; can "
                            "be a project_metadata.csv field or a "
                            "metadata.json sidecar field per ADR 0015)"
                        ),
                        "required": True,
                    },
                    "metric": {
                        "type": "string",
                        "description": (
                            f"Per-record reduction: {', '.join(COHORT_METRICS)}. "
                            "Default: mean."
                        ),
                        "required": False,
                    },
                    "instrument": {
                        "type": "string",
                        "description": (
                            "Optional instrument filter (cohort scoped to "
                            "records with this instrument completed)"
                        ),
                        "required": False,
                    },
                    "event": {
                        "type": "string",
                        "description": (
                            "Optional redcap_event_name filter"
                        ),
                        "required": False,
                    },
                    "subject_id": SUBJECT_ID_PARAM_DOC,
                },
            ),
            ToolDefinition(
                "redcap_records", 2,
                "Tier-2: returns all subjects' answers to one named "
                "instrument across all events, identifier-stripped. "
                "Required ``instrument`` parameter — there is no "
                "default; consent is scoped to a named form the IRB "
                "approved, not the whole project. ~5000-15000 tokens. "
                "Requires consent.",
                {
                    "instrument": {
                        "type": "string",
                        "description": "REDCap instrument (form) name",
                        "required": True,
                    },
                    "event": {
                        "type": "string",
                        "description": (
                            "Optional redcap_event_name filter"
                        ),
                        "required": False,
                    },
                    "subject_id": SUBJECT_ID_PARAM_DOC,
                },
            ),
            ToolDefinition(
                "redcap_raw_records", 3,
                "Tier-3: all subjects, all events, all instruments, "
                "identifier-stripped. ~30k-100k tokens. Requires "
                "consent + cost approval.",
                {
                    "precision": {
                        "type": "integer",
                        "description": (
                            "Decimal places to keep for numeric fields "
                            "(default 6)"
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
            "redcap_list_records": {
                "limit": ValidationSchema(type=int, min=1, max=500, default=50),
                "subject_id": SUBJECT_ID_SCHEMA,
            },
            "redcap_record_detail": {
                "record_id": ValidationSchema(
                    type=str, required=True, pattern=RECORD_ID_PATTERN,
                ),
                "event": ValidationSchema(
                    type=str, required=False, pattern=EVENT_NAME_PATTERN,
                ),
                "subject_id": SUBJECT_ID_SCHEMA,
            },
            "redcap_summary_report": {
                "instrument": ValidationSchema(
                    type=str, required=False, pattern=INSTRUMENT_NAME_PATTERN,
                ),
                "subject_id": SUBJECT_ID_SCHEMA,
            },
            "redcap_cohort_summary": {
                "field": ValidationSchema(
                    type=str, required=True, pattern=FIELD_NAME_PATTERN,
                ),
                "group_by": ValidationSchema(
                    type=str, required=True, pattern=GROUP_BY_PATTERN,
                ),
                "metric": ValidationSchema(
                    type=str, required=False,
                    allowed_values=list(COHORT_METRICS), default="mean",
                ),
                "instrument": ValidationSchema(
                    type=str, required=False, pattern=INSTRUMENT_NAME_PATTERN,
                ),
                "event": ValidationSchema(
                    type=str, required=False, pattern=EVENT_NAME_PATTERN,
                ),
                "subject_id": SUBJECT_ID_SCHEMA,
            },
            "redcap_records": {
                "instrument": ValidationSchema(
                    type=str, required=True, pattern=INSTRUMENT_NAME_PATTERN,
                ),
                "event": ValidationSchema(
                    type=str, required=False, pattern=EVENT_NAME_PATTERN,
                ),
                "subject_id": SUBJECT_ID_SCHEMA,
            },
            "redcap_raw_records": {
                "precision": ValidationSchema(
                    type=int, min=0, max=12, default=6,
                ),
                "subject_id": SUBJECT_ID_SCHEMA,
            },
        }

    # ══════════════════════════════════════════════════════════
    # COST ESTIMATION
    # ══════════════════════════════════════════════════════════

    async def estimate_cost(self, tool_name: str, params: dict) -> CostEstimate:
        if tool_name != "redcap_raw_records":
            return CostEstimate(tokens=0)
        records = self._load_records()
        if not records:
            return CostEstimate(tokens=0)
        field_count = max(1, len(records[0].keys()))
        full_tokens = len(records) * field_count * 8
        alt_tokens = max(1, full_tokens // 5)
        return CostEstimate(
            tokens=full_tokens,
            has_cheaper_alternative=True,
            alternative_tokens=alt_tokens,
            alternative_description=(
                "redcap_records(instrument=<name>) — returns one form's "
                "answers across all subjects rather than the full project; "
                "consent scope narrows to the IRB-recognized instrument."
            ),
        )

    def purge_cache(self, *, force: bool = False) -> dict:
        """Per ADR 0013 — institutional source data, no derivative cache."""
        return {
            "rows_purged": 0,
            "tables_touched": [],
            "preserved": [],
            "reason": (
                "redcap_file reads CSV/JSON exports at redcap_file.path; "
                "the framework owns no derivative cache."
            ),
        }

    # ══════════════════════════════════════════════════════════
    # EXECUTION
    # ══════════════════════════════════════════════════════════

    async def execute(self, tool_name: str, params: dict) -> dict:
        # ADR 0003 § Amendment 2026-05-15 — trust-root fingerprint
        # check. Re-read project_metadata.csv from disk and compare its
        # canonical-form fingerprint to the scrubber's cached value. On
        # mismatch, RAISE RedcapMetadataFingerprintMismatch so the
        # router's exception handler records an ERROR audit row (per
        # ADR 0001 audit-completeness invariant), with the error column
        # carrying BOTH fingerprints in parseable form. A dict-return
        # would mis-record as SUCCESS and leak the on-disk fingerprint
        # only into the wire transcript — phi-irb-risk-reviewer
        # 2026-05-15 Lens 3 VIOLATION-2 closure.
        self._detect_fingerprint_mismatch()

        handlers = {
            "redcap_list_records": self._handle_list_records,
            "redcap_record_detail": self._handle_record_detail,
            "redcap_summary_report": self._handle_summary_report,
            "redcap_cohort_summary": self._handle_cohort_summary,
            "redcap_records": self._handle_records,
            "redcap_raw_records": self._handle_raw_records,
        }
        handler = handlers.get(tool_name)
        if not handler:
            return {"error": f"Unknown tool: {tool_name}"}
        return await handler(params)

    def _detect_fingerprint_mismatch(self) -> None:
        """Per ADR 0003 § Amendment 2026-05-15 — re-read
        ``project_metadata.csv`` from disk and compare its canonical-form
        fingerprint to the scrubber's cached fingerprint. Raises
        :class:`RedcapMetadataFingerprintMismatch` on drift; returns
        ``None`` when the fingerprints agree (including the case where
        the on-disk file is missing — the scrubber's own fail-closed
        path handles that and surfaces via ``child_scrubber_warning``).

        Raising rather than returning a dict ensures the router's
        exception handler at ``_dispatch`` records an ``outcome=ERROR``
        audit row carrying both fingerprints in the error column —
        queryable by IRB review via
        ``SELECT * FROM audit_log WHERE error LIKE 'REDCAP_METADATA_FINGERPRINT_MISMATCH:%'``.
        Closes the audit-completeness gap a dict-return shape would
        leave open (the on-disk fingerprint would be wire-only and the
        outcome would be mis-stamped SUCCESS).
        """
        if self._scrubber is None:
            return None
        candidate_path = self._redcap_path / self._project_metadata_filename
        if not candidate_path.is_file():
            # File became unreadable since boot. Don't fire mismatch —
            # the scrubber's existing missing-file path handles this
            # (every field gets stripped fail-closed). Letting it fall
            # through to the handler is the right shape.
            return None
        try:
            candidate = RedcapPHIScrubber(
                project_metadata_path=candidate_path,
                unknown_field_allowlist=[],
            )
        except Exception:
            return None
        if candidate.fingerprint == self._scrubber.fingerprint:
            return None
        raise RedcapMetadataFingerprintMismatch(
            fingerprint_at_boot=self._scrubber.fingerprint,
            fingerprint_on_disk=candidate.fingerprint,
        )

    # ──────────────────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────────────────

    def _records_file_path(self) -> Path:
        return self._redcap_path / self._records_filename

    def _load_records(self) -> list[dict]:
        """Re-parse records on every call. Per ADR 0013: no in-memory
        cache; the alternative would make the purge no-op a retention
        lie.

        Supports both CSV and JSON exports, dispatched by file
        extension. Returns ``[]`` on any read/parse error (the handler
        layer translates that into an error envelope).
        """
        path = self._records_file_path()
        if not path.is_file():
            return []
        suffix = path.suffix.lower()
        try:
            if suffix == ".json":
                content = path.read_text(encoding="utf-8-sig")
                data = json.loads(content)
                if isinstance(data, list):
                    return [
                        {str(k): v for k, v in row.items()}
                        for row in data
                        if isinstance(row, dict)
                    ]
                return []
            # Default: CSV. utf-8-sig strips the Excel/PowerShell BOM.
            with open(path, encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                rows: list[dict] = []
                for row in reader:
                    if len(rows) >= MAX_RECORDS:
                        break
                    rows.append(dict(row))
                return rows
        except (OSError, json.JSONDecodeError, csv.Error, UnicodeDecodeError) as exc:
            log.warning(f"Could not read {path}: {exc}")
            return []

    def _records_for_subject(
        self, records: list[dict], record_id: str,
    ) -> list[dict]:
        """Return all rows for a given record_id (longitudinal projects
        emit multiple rows per subject across events)."""
        return [r for r in records if (r.get("record_id") or "") == record_id]

    def _records_for_event(
        self, records: list[dict], event: str | None,
    ) -> list[dict]:
        if not event:
            return records
        return [r for r in records if (r.get("redcap_event_name") or "") == event]

    @staticmethod
    def _instrument_completion_field_for(instrument: str) -> str:
        """REDCap convention: ``{instrument}_complete`` is the
        per-instrument completion status field."""
        return f"{instrument}_complete"

    def _records_for_instrument(
        self, records: list[dict], instrument: str | None,
    ) -> list[dict]:
        """Filter records to those where the instrument's completion
        field is populated. If ``instrument`` is ``None``, returns the
        full list.
        """
        if not instrument:
            return records
        complete_field = self._instrument_completion_field_for(instrument)
        filtered: list[dict] = []
        for r in records:
            value = r.get(complete_field)
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            filtered.append(r)
        return filtered

    def _load_cohort_sidecar(self) -> dict | None:
        """Load ADR 0015 metadata.json sidecar; return ``None`` if absent.

        Schema: ``{<record_id>: {<field>: <value>, ...}}``. Distinct
        from project_metadata.csv (the REDCap data dictionary).
        """
        sidecar = self._redcap_path / METADATA_FILENAME
        if not sidecar.is_file():
            return None
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError) as exc:
            log.warning(f"Could not read {sidecar}: {exc}")
            return None
        if not isinstance(data, dict):
            return None
        return data

    def _apply_scrubber_to_records(
        self, records: list[dict],
    ) -> tuple[list[dict], dict]:
        """Apply the child-level scrubber and return
        ``(scrubbed_records, legibility_aggregate)``. Preserves
        structural REDCap columns (record_id, redcap_event_name, etc.)
        because they describe the row, not the participant's answers,
        and we need them downstream for grouping / filtering.
        """
        # Split off structural columns first; scrub the rest; rejoin.
        scrubbable_records: list[dict] = []
        structural_columns: list[dict] = []
        for r in records:
            structural = {
                k: v for k, v in r.items() if k in REDCAP_STRUCTURAL_COLUMNS
            }
            non_structural = {
                k: v for k, v in r.items() if k not in REDCAP_STRUCTURAL_COLUMNS
            }
            scrubbable_records.append(non_structural)
            structural_columns.append(structural)
        scrubbed, legibility = self._scrubber.scrub_records(scrubbable_records)
        joined: list[dict] = []
        for s, struct in zip(scrubbed, structural_columns, strict=True):
            merged = {**struct, **s}
            joined.append(merged)
        return joined, legibility

    def _legibility_for_envelope(self, legibility: dict) -> dict:
        """Standardize the legibility-commitment subset of the result
        envelope per ADR 0037. Three of the four named fields come from
        the scrubber's aggregate; ``field_not_in_record`` is added by
        callers that asked for a specific named field.
        """
        return {
            "field_marked_identifier_stripped":
                legibility.get("field_marked_identifier_stripped", []),
            "field_unknown_default_stripped":
                legibility.get("field_unknown_default_stripped", []),
            "unknown_field_count":
                legibility.get("unknown_field_count", 0),
        }

    def _scrubber_warning_block(self) -> dict:
        """If the child-level scrubber surfaces a warning (e.g. missing
        project_metadata.csv), include it in the result envelope so the
        misconfiguration is visible in the LLM transcript.
        """
        warning = self._scrubber.child_scrubber_warning
        if warning is None:
            return {}
        return {"child_scrubber_warning": warning}

    def _small_cell_envelope_fields(self) -> dict:
        """Per ADR 0003 § Amendment 2026-05-15 — surface the
        deployment-time small-cell threshold (and the default-in-force
        warning when applicable) at the top level of every result
        envelope where suppression was applied. Symmetric intent to
        ``scrubber_warning``'s deployment-misconfig surface, landed at
        the top level of the child envelope alongside other child-level
        legibility fields.
        """
        out: dict = {
            "small_cell_suppression_threshold": self._small_cell_threshold,
        }
        if self._small_cell_default_in_force:
            out["small_cell_warning"] = (
                "small_cell_suppression_threshold is at the framework "
                f"default (k={DEFAULT_SMALL_CELL_THRESHOLD}, HHS SDL "
                "baseline). Studies with elevated re-identification risk "
                "(pediatric, mental health, rare-disease populations) "
                "should opt up to a higher k via the "
                "`small_cell_suppression_threshold` key in the "
                "`redcap_file` block of user_config.json. See ADR 0003 "
                "§ Amendment 2026-05-15."
            )
        return out

    def _field_values_for_records(
        self, records: list[dict], field: str,
    ) -> list:
        """Pull ``field`` out of each record. Returns the raw values
        (not coerced) so callers can decide what kind of summary to
        produce.
        """
        return [r.get(field) for r in records if field in r]

    def _detect_instruments(self, records: list[dict]) -> list[str]:
        """Infer the set of instruments from the per-instrument
        completion columns present in the records. REDCap convention:
        any column whose name ends in ``_complete`` is an
        instrument-completion field for the instrument named by the
        prefix.

        Order-preserving across rows so the result is deterministic
        regardless of dict-iteration order on older Python versions.
        """
        seen_columns: list[str] = []
        seen_set: set[str] = set()
        for r in records:
            for k in r.keys():
                if (
                    k.endswith("_complete")
                    and k not in REDCAP_STRUCTURAL_COLUMNS
                    and k not in seen_set
                ):
                    seen_columns.append(k)
                    seen_set.add(k)
        # Reduce *_complete → instrument names.
        suffix_len = len("_complete")
        out: list[str] = []
        for col in seen_columns:
            instrument = col[:-suffix_len]
            if instrument and instrument not in out:
                out.append(instrument)
        return out

    # ──────────────────────────────────────────────────────────
    # Tier 1 handlers
    # ──────────────────────────────────────────────────────────

    async def _handle_list_records(self, params: dict) -> dict:
        if not self._redcap_path.is_dir():
            return {"error": "Directory not found: <configured_redcap_path>"}
        records = self._load_records()
        if not records:
            return {
                "error": (
                    "No records found at "
                    "<configured_redcap_records_path>. Ensure the file "
                    "exists and is CSV or JSON."
                ),
                **self._scrubber_warning_block(),
            }
        limit = params.get("limit", 50)
        # Group by record_id; one record_id may have many rows
        # (longitudinal projects emit one row per event).
        by_subject: dict[str, dict] = {}
        instrument_names = self._detect_instruments(records)
        for r in records:
            rid = r.get("record_id") or ""
            if not rid:
                continue
            entry = by_subject.setdefault(rid, {
                "record_id": rid,
                "events": [],
                "instruments_completed": 0,
            })
            event = r.get("redcap_event_name") or ""
            if event and event not in entry["events"]:
                entry["events"].append(event)
            entry["instruments_completed"] += (
                self._processing.count_instruments_completed(
                    r,
                    [self._instrument_completion_field_for(i)
                     for i in instrument_names],
                )
            )
        subjects = list(by_subject.values())[:limit]
        envelope: dict = {
            "count": len(subjects),
            "total_record_ids": len(by_subject),
            "instrument_names": instrument_names,
            "records": subjects,
        }
        envelope.update(self._scrubber_warning_block())
        return envelope

    async def _handle_record_detail(self, params: dict) -> dict:
        if not self._redcap_path.is_dir():
            return {"error": "Directory not found: <configured_redcap_path>"}
        record_id = params["record_id"]
        event_filter = params.get("event")
        records = self._load_records()
        subject_rows = self._records_for_subject(records, record_id)
        if not subject_rows:
            return {
                "error": f"record_id not found: {record_id}",
                **self._scrubber_warning_block(),
            }
        if event_filter:
            subject_rows = self._records_for_event(subject_rows, event_filter)
            if not subject_rows:
                return {
                    "error": (
                        f"record_id {record_id} has no rows for event "
                        f"{event_filter}"
                    ),
                    **self._scrubber_warning_block(),
                }
        scrubbed_rows, legibility = self._apply_scrubber_to_records(subject_rows)
        # Build per-event entries that surface non-identifier field
        # values. The LLM gets non-identifier fields it can reason
        # over; identifier fields are gone.
        events: list[dict] = []
        for row in scrubbed_rows:
            event_entry = {
                "redcap_event_name": row.get("redcap_event_name") or "",
                "redcap_repeat_instrument": row.get("redcap_repeat_instrument") or "",
                "redcap_repeat_instance": row.get("redcap_repeat_instance") or "",
                "fields": {
                    k: v for k, v in row.items()
                    if k not in REDCAP_STRUCTURAL_COLUMNS
                },
            }
            events.append(event_entry)
        envelope = {
            "record_id": record_id,
            "n_events": len(events),
            "events": events,
            **self._legibility_for_envelope(legibility),
        }
        envelope.update(self._scrubber_warning_block())
        return envelope

    async def _handle_summary_report(self, params: dict) -> dict:
        if not self._redcap_path.is_dir():
            return {"error": "Directory not found: <configured_redcap_path>"}
        instrument = params.get("instrument")
        records = self._load_records()
        if not records:
            return {
                "error": "No records at <configured_redcap_records_path>",
                **self._scrubber_warning_block(),
            }
        scoped = self._records_for_instrument(records, instrument)
        scrubbed, legibility = self._apply_scrubber_to_records(scoped)

        # Per-instrument completion counts: count rows where
        # {instrument}_complete == "2" for every detected instrument.
        instrument_names = self._detect_instruments(records)
        completion_counts: dict[str, int] = {}
        for inst in instrument_names:
            field = self._instrument_completion_field_for(inst)
            count = 0
            for r in scoped:
                value = r.get(field)
                if value is not None and str(value).strip() == "2":
                    count += 1
            completion_counts[inst] = count
        # Per ADR 0003 § Amendment 2026-05-15 — apply small-cell
        # suppression to completion_counts. A study with N=2 enrolled
        # at a pilot site discloses the count directly through this
        # surface even when top_values + cohort groups are correctly
        # suppressed (phi-irb-risk-reviewer 2026-05-15 Lens 1 WATCH).
        # Replaces the count value with the "<below_threshold>"
        # sentinel; the instrument name key is structural metadata
        # (not a participant identifier per HIPAA Safe Harbor) so it
        # stays queryable.
        completion_counts = (
            self._processing.apply_small_cell_suppression_to_completion_counts(
                completion_counts, self._small_cell_threshold,
            )
        )

        # Per-field summaries — only fields that survived scrubbing.
        field_names: list[str] = []
        seen: set[str] = set()
        for r in scrubbed:
            for k in r.keys():
                if k in REDCAP_STRUCTURAL_COLUMNS:
                    continue
                if k.endswith("_complete"):
                    # Status fields are surfaced via completion_counts,
                    # not per-field distributions.
                    continue
                if k not in seen:
                    seen.add(k)
                    field_names.append(k)
        field_summaries: dict[str, dict] = {}
        for f in field_names:
            values = [r.get(f) for r in scrubbed]
            summary = self._processing.summarize_field(values)
            # Per ADR 0003 § Amendment 2026-05-15 — apply small-cell
            # suppression to categorical top_values so a low-cardinality
            # non-identifier-flagged field (e.g. study site with N=3
            # sites) cannot re-identify through count disclosure.
            if "top_values" in summary:
                summary["top_values"] = (
                    self._processing.apply_small_cell_suppression_to_top_values(
                        summary["top_values"],
                        self._small_cell_threshold,
                    )
                )
            field_summaries[f] = summary

        envelope = {
            "n_records_scanned": len(scoped),
            "instrument_filter": instrument,
            "completion_counts": completion_counts,
            "field_summaries": field_summaries,
            **self._legibility_for_envelope(legibility),
            **self._small_cell_envelope_fields(),
        }
        envelope.update(self._scrubber_warning_block())
        return envelope

    async def _handle_cohort_summary(self, params: dict) -> dict:
        if not self._redcap_path.is_dir():
            return {"error": "Directory not found: <configured_redcap_path>"}
        field = params["field"]
        group_by = params["group_by"]
        metric = params.get("metric", "mean")
        instrument = params.get("instrument")
        event_filter = params.get("event")

        # Identifier-group_by guard. The single most important defence
        # against silent PHI leakage in this tool — per ADR 0037's
        # explicit audit-named test. Grouping by an identifier field
        # would surface the identifier values as group keys even
        # though the field is "stripped" from individual records.
        if self._scrubber.is_identifier(group_by):
            return {
                "error": (
                    f"Cannot group by identifier-flagged (or unknown — "
                    f"defaults to identifier per fail-closed ADR 0037) "
                    f"field '{group_by}'; this would leak PHI through "
                    "group-key cardinality. Re-run with group_by "
                    "pointing at a non-identifier field."
                ),
                **self._scrubber_warning_block(),
            }
        # And separately: refuse to aggregate an identifier-flagged
        # field. The scrubber would strip it from individual records
        # anyway, but aggregating it first then stripping would
        # surface identifier statistics — a separate leakage shape.
        if self._scrubber.is_identifier(field):
            return {
                "error": (
                    f"Cannot aggregate identifier-flagged (or unknown — "
                    f"defaults to identifier per fail-closed ADR 0037) "
                    f"field '{field}'; identifier fields cannot be "
                    "summarized or returned. Re-run with field pointing "
                    "at a non-identifier field."
                ),
                **self._scrubber_warning_block(),
            }

        records = self._load_records()
        if not records:
            return {
                "error": "No records at <configured_redcap_records_path>",
                **self._scrubber_warning_block(),
            }
        scoped = self._records_for_event(
            self._records_for_instrument(records, instrument),
            event_filter,
        )
        sidecar = self._load_cohort_sidecar()

        # Resolve the group_by value for each record:
        #   1. Prefer a project_metadata.csv field (i.e. a column in
        #      the record itself).
        #   2. Fall back to the ADR 0015 metadata.json sidecar keyed
        #      by record_id.
        per_group: dict[str, list] = {}
        missing_group_field: list[str] = []
        field_not_in_record_count = 0
        for r in scoped:
            group_value = r.get(group_by)
            if group_value is None or (
                isinstance(group_value, str) and not group_value.strip()
            ):
                if sidecar is not None:
                    rid = r.get("record_id") or ""
                    meta_entry = sidecar.get(rid) or {}
                    group_value = meta_entry.get(group_by)
            if group_value is None or (
                isinstance(group_value, str) and not group_value.strip()
            ):
                missing_group_field.append(r.get("record_id") or "")
                continue
            if field not in r:
                field_not_in_record_count += 1
                continue
            field_value = r.get(field)
            # Skip blanks — they're "no answer", not "answered nothing".
            # Counting them would skew cohort_stats toward categorical
            # because blank strings are non-numeric.
            if field_value is None or (
                isinstance(field_value, str) and not field_value.strip()
            ):
                continue
            per_group.setdefault(str(group_value), []).append(field_value)

        # Per group: produce the headline metric AND surface the
        # distributional context (n, kind, range stats for numeric;
        # mode + cardinality for categorical). The metric is the
        # caller's chosen headline; cohort_stats gives the analyst
        # enough context to read it.
        groups: dict[str, dict] = {}
        for group_key, group_values in sorted(per_group.items()):
            try:
                metric_value = self._processing.aggregate_metric(
                    group_values, metric,
                )
            except ValueError as exc:
                return {
                    "error": str(exc),
                    **self._scrubber_warning_block(),
                }
            group_stats = self._processing.cohort_stats(group_values)
            # Surface the headline metric under its name. For metrics
            # that cohort_stats already exposes (mean/min/max/std on
            # numeric data) this is a same-value overwrite; for the
            # categorical-only metrics (mode/count) this fills in the
            # row the caller asked for.
            group_stats["metric_value"] = metric_value
            groups[group_key] = group_stats

        # Per ADR 0003 § Amendment 2026-05-15 — apply small-cell
        # suppression to cohort group counts. The higher-leverage
        # re-identification path the auditor's F4 finding named: a
        # study with N=3 sites discloses site-level identity directly
        # through cohort group counts even when top_values is
        # correctly suppressed. Applied AFTER cohort_stats is computed
        # per group; small-N groups collapse into one aggregate entry.
        groups = self._processing.apply_small_cell_suppression_to_groups(
            groups, self._small_cell_threshold,
        )

        # Surface scrubber legibility on the aggregate. We aggregate
        # over scoped to know if the field itself was unknown-stripped
        # (which would silently produce no group values).
        _, agg_legibility = self._apply_scrubber_to_records(scoped)

        envelope = {
            "field": field,
            "group_by": group_by,
            "metric": metric,
            "instrument_filter": instrument,
            "event_filter": event_filter,
            "n_records_scanned": len(scoped),
            "groups": groups,
            "missing_group_field": missing_group_field,
            "field_not_in_record_count": field_not_in_record_count,
            **self._legibility_for_envelope(agg_legibility),
            **self._small_cell_envelope_fields(),
        }
        envelope.update(self._scrubber_warning_block())
        return envelope

    # ──────────────────────────────────────────────────────────
    # Tier 2 handler
    # ──────────────────────────────────────────────────────────

    async def _handle_records(self, params: dict) -> dict:
        if not self._redcap_path.is_dir():
            return {"error": "Directory not found: <configured_redcap_path>"}
        instrument = params["instrument"]
        event_filter = params.get("event")
        records = self._load_records()
        if not records:
            return {
                "error": "No records at <configured_redcap_records_path>",
                **self._scrubber_warning_block(),
            }
        scoped = self._records_for_event(
            self._records_for_instrument(records, instrument),
            event_filter,
        )
        scrubbed, legibility = self._apply_scrubber_to_records(scoped)
        envelope = {
            "instrument": instrument,
            "event_filter": event_filter,
            "n_records": len(scrubbed),
            "records": scrubbed,
            **self._legibility_for_envelope(legibility),
        }
        envelope.update(self._scrubber_warning_block())
        return envelope

    # ──────────────────────────────────────────────────────────
    # Tier 3 handler
    # ──────────────────────────────────────────────────────────

    async def _handle_raw_records(self, params: dict) -> dict:
        if not self._redcap_path.is_dir():
            return {"error": "Directory not found: <configured_redcap_path>"}
        precision = params.get("precision", 6)
        records = self._load_records()
        if not records:
            return {
                "error": "No records at <configured_redcap_records_path>",
                **self._scrubber_warning_block(),
            }
        scrubbed, legibility = self._apply_scrubber_to_records(records)
        # Precision reduction on numeric fields.
        reduced: list[dict] = []
        for r in scrubbed:
            out_row: dict = {}
            for k, v in r.items():
                if (
                    k not in REDCAP_STRUCTURAL_COLUMNS
                    and self._processing.is_numeric_value(v)
                ):
                    try:
                        out_row[k] = round(float(v), precision)
                    except (TypeError, ValueError):
                        out_row[k] = v
                else:
                    out_row[k] = v
            reduced.append(out_row)
        envelope = {
            "n_records": len(reduced),
            "precision": precision,
            "records": reduced,
            **self._legibility_for_envelope(legibility),
        }
        envelope.update(self._scrubber_warning_block())
        return envelope
