"""
RedcapPHIScrubber — Child-level PHI scrubbing for REDCap exports.

Per ADR 0037 + ADR 0003 § Amendment 2026-05-14: this class is a
**parallel seam** to the framework-level ``PHIScrubber``, not a
subclass. Both seams may run on the same call; they answer different
questions:

- ``framework.security.PHIScrubber`` (ADR 0003): cross-domain pattern
  matchers (regex / heuristic / NLP). No-op default.
- ``RedcapPHIScrubber`` (this file): domain-specific structured input.
  Reads the IRB-approved ``identifier=yes/no`` flags from REDCap's
  ``project_metadata.csv`` data dictionary and strips flagged fields
  from every record before return.

Audit-row provenance: the framework-level ``scrubber_id`` continues to
report the framework-level scrubber identity (``"noop"`` if the
default is in place). A separate ``child_scrubber_id`` column records
this child's scrubber identity (``"redcap_metadata_flags"``). An IRB
reviewer can distinguish a misconfigured deployment (both NULL/noop)
from a deployment with a working child-level scrubber (noop framework,
``redcap_metadata_flags`` child).

Fail-closed default per ADR 0037 § "Unknown-field default": fields
not present in ``project_metadata.csv`` are treated as
identifier-positive (stripped) until the operator explicitly
allowlists them via ``unknown_field_allowlist`` in the ``redcap_file``
config block. This defends against the silent-leak failure mode where
a mid-study field addition was not reflected in the exported data
dictionary.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path

log = logging.getLogger("tailor.redcap.scrubber")


# REDCap's ``identifier`` column carries one of these values for a
# positive flag; anything else (including blank, ``"n"``, ``"no"``,
# ``"0"``) is treated as a negative flag. We accept the case variants
# REDCap exports have historically emitted across versions.
POSITIVE_IDENTIFIER_VALUES = frozenset({"y", "yes", "Y", "Yes", "YES"})

# Column-name aliases. The REDCap API export uses snake_case
# (``field_name``, ``identifier``); the Data Dictionary CSV download
# uses human-readable headers (``Variable / Field Name``,
# ``Identifier?``). We support both so the scrubber works regardless
# of which export shape the operator hands us.
FIELD_NAME_ALIASES = ("field_name", "Variable / Field Name")
IDENTIFIER_ALIASES = ("identifier", "Identifier?")


class RedcapPHIScrubber:
    """Child-level PHI scrubber for REDCap exports.

    Constructor loads ``project_metadata.csv`` once and caches the
    identifier flag for each field. Subsequent ``scrub_record()`` /
    ``scrub_records()`` calls are pure lookups against that map.

    Does NOT inherit from ``framework.security.PHIScrubber``. The two
    seams are intentionally parallel, not hierarchical — see ADR 0037
    § "Built-in PHI scrubber — a new seam parallel to ADR 0003".
    """

    def __init__(
        self,
        project_metadata_path: Path,
        unknown_field_allowlist: list[str] | None = None,
    ):
        self._project_metadata_path = project_metadata_path
        self._unknown_field_allowlist: frozenset[str] = frozenset(
            unknown_field_allowlist or []
        )
        # field_name → bool (True = identifier, strip). Empty if file
        # missing/unreadable — combined with the fail-closed default,
        # missing metadata means every field is stripped (except the
        # allowlist).
        self._identifier_map: dict[str, bool] = {}
        self._warning: str | None = None
        self._load_metadata()

    # ──────────────────────────────────────────────────────────────
    # Construction-time metadata loading
    # ──────────────────────────────────────────────────────────────

    def _load_metadata(self) -> None:
        """Parse project_metadata.csv into ``self._identifier_map``.

        Supports both naming conventions (API snake_case +
        human-readable Data Dictionary download). On any failure to
        read or parse, the map stays empty and ``self._warning`` is
        populated so callers can surface the misconfiguration loudly.
        """
        if not self._project_metadata_path.is_file():
            self._warning = (
                "RedcapPHIScrubber: project_metadata.csv not found at "
                "<configured_redcap_metadata_path>. Fail-closed default in "
                "effect — every field will be treated as identifier-"
                "positive and stripped unless explicitly allowlisted "
                "via unknown_field_allowlist. See ADR 0037."
            )
            log.warning(
                f"RedcapPHIScrubber: project_metadata.csv not found at "
                f"{self._project_metadata_path}. Fail-closed default in effect."
            )
            return
        try:
            with open(
                self._project_metadata_path, encoding="utf-8-sig", newline=""
            ) as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames or []
                field_col = self._resolve_column(fieldnames, FIELD_NAME_ALIASES)
                ident_col = self._resolve_column(fieldnames, IDENTIFIER_ALIASES)
                if field_col is None or ident_col is None:
                    self._warning = (
                        "RedcapPHIScrubber: could not locate "
                        f"field-name column (looked for {FIELD_NAME_ALIASES}) "
                        f"or identifier column (looked for {IDENTIFIER_ALIASES}) "
                        "in <configured_redcap_metadata_path>. Fail-closed "
                        "default in effect. See ADR 0037."
                    )
                    log.warning(
                        f"RedcapPHIScrubber: column resolution failed in "
                        f"{self._project_metadata_path}. Fail-closed default "
                        f"in effect."
                    )
                    return
                for row in reader:
                    name = (row.get(field_col) or "").strip()
                    if not name:
                        continue
                    flag = (row.get(ident_col) or "").strip()
                    self._identifier_map[name] = flag in POSITIVE_IDENTIFIER_VALUES
        except (OSError, csv.Error, ValueError) as exc:
            self._warning = (
                "RedcapPHIScrubber: could not parse "
                f"<configured_redcap_metadata_path>: {type(exc).__name__}. "
                "Fail-closed default in effect. See ADR 0037."
            )
            log.warning(
                f"RedcapPHIScrubber: could not parse "
                f"{self._project_metadata_path}: {exc}. Fail-closed default "
                f"in effect."
            )
            return

    @staticmethod
    def _resolve_column(fieldnames: list[str], aliases: tuple[str, ...]) -> str | None:
        """Return the first alias present in ``fieldnames``, or ``None``."""
        for alias in aliases:
            if alias in fieldnames:
                return alias
        return None

    # ──────────────────────────────────────────────────────────────
    # Identity (audit-row provenance)
    # ──────────────────────────────────────────────────────────────

    @property
    def scrubber_id(self) -> str:
        """Stamped into the audit-log ``child_scrubber_id`` column."""
        return "redcap_metadata_flags"

    @property
    def child_scrubber_warning(self) -> str | None:
        """Surfaced into result ``_meta`` blocks when metadata is
        missing or unreadable. Mirrors
        ``framework.security.PHIScrubber.scrubber_warning`` shape so a
        deployment with a broken child scrubber is visible in the LLM
        transcript on every call.
        """
        return self._warning

    # ──────────────────────────────────────────────────────────────
    # Per-field classification
    # ──────────────────────────────────────────────────────────────

    def is_identifier(self, field_name: str) -> bool:
        """Return True if the field should be stripped from results.

        Decision order:
            1. Field is in the identifier map AND flag is True  → True
            2. Field is in the identifier map AND flag is False → False
            3. Field is in unknown_field_allowlist              → False
               (operator-asserted override of fail-closed default)
            4. Field is in NEITHER map                          → True
               (FAIL-CLOSED DEFAULT per ADR 0037)
        """
        if field_name in self._identifier_map:
            return self._identifier_map[field_name]
        if field_name in self._unknown_field_allowlist:
            return False
        return True

    def is_unknown(self, field_name: str) -> bool:
        """Return True if the field is not in project_metadata.csv
        AND not in the allowlist. Used by callers to populate the
        ``field_unknown_default_stripped`` legibility field.
        """
        return (
            field_name not in self._identifier_map
            and field_name not in self._unknown_field_allowlist
        )

    def is_known_identifier(self, field_name: str) -> bool:
        """Return True if the field exists in project_metadata.csv
        AND is explicitly flagged as identifier-positive. Distinguishes
        ``field_marked_identifier_stripped`` from
        ``field_unknown_default_stripped`` in result envelopes.
        """
        return self._identifier_map.get(field_name, False)

    # ──────────────────────────────────────────────────────────────
    # Per-record / batch scrubbing
    # ──────────────────────────────────────────────────────────────

    def scrub_record(self, record: dict) -> tuple[dict, dict]:
        """Return ``(scrubbed_record, legibility_dict)``.

        The scrubbed record has all identifier-flagged fields removed.
        The legibility dict carries three lists/counts so callers can
        distinguish the four failure modes ADR 0037 names:

            - field_marked_identifier_stripped: fields whose project
              metadata flagged identifier=yes
            - field_unknown_default_stripped: fields stripped because
              they hit the fail-closed default
            - unknown_field_count: count of fields in the second list
        """
        scrubbed: dict = {}
        marked: list[str] = []
        unknown_stripped: list[str] = []
        for name, value in record.items():
            if self.is_known_identifier(name):
                marked.append(name)
                continue
            if self.is_unknown(name):
                unknown_stripped.append(name)
                continue
            scrubbed[name] = value
        legibility = {
            "field_marked_identifier_stripped": marked,
            "field_unknown_default_stripped": unknown_stripped,
            "unknown_field_count": len(unknown_stripped),
        }
        return scrubbed, legibility

    def scrub_records(self, records: list[dict]) -> tuple[list[dict], dict]:
        """Batch variant. Aggregates legibility across records:
        unique field names (not multiplied by record count), total
        unknown count summed across all records (for callers that want
        a "how many fields got stripped" rough magnitude).
        """
        scrubbed_records: list[dict] = []
        marked_set: set[str] = set()
        unknown_set: set[str] = set()
        total_unknown = 0
        for record in records:
            scrubbed, legibility = self.scrub_record(record)
            scrubbed_records.append(scrubbed)
            marked_set.update(legibility["field_marked_identifier_stripped"])
            unknown_set.update(legibility["field_unknown_default_stripped"])
            total_unknown += legibility["unknown_field_count"]
        return scrubbed_records, {
            "field_marked_identifier_stripped": sorted(marked_set),
            "field_unknown_default_stripped": sorted(unknown_set),
            "unknown_field_count": total_unknown,
        }
