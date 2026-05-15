"""
Tests for RedcapPHIScrubber — the child-level PHI seam codified by
ADR 0003 § Amendment 2026-05-14 and ADR 0037.

Tests cover:
- Both naming conventions for project_metadata.csv (snake_case API
  export AND human-readable Data Dictionary download).
- Positive identifier values (y, yes, Y, Yes, YES).
- Fail-closed default on unknown fields.
- unknown_field_allowlist override of fail-closed default.
- Legibility-dict contract for scrub_record / scrub_records.
- scrubber_id == "redcap_metadata_flags".
- child_scrubber_warning surfaces on missing project_metadata.csv.
- Does NOT inherit from framework.security.PHIScrubber (parallel
  seam, not hierarchical).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tailor.children.redcap import RedcapPHIScrubber
from tailor.framework.security import PHIScrubber

# ═══════════════════════════════════════════════════════════════
# FIXTURE BUILDERS
# ═══════════════════════════════════════════════════════════════


SNAKE_CASE_HEADER = "field_name,form_name,field_type,identifier\n"
HUMAN_READABLE_HEADER = (
    '"Variable / Field Name","Form Name","Field Type","Identifier?"\n'
)


def _write_snake_case_metadata(tmp_path: Path) -> Path:
    """Write a snake_case (API export) project_metadata.csv."""
    path = tmp_path / "project_metadata.csv"
    rows = [
        SNAKE_CASE_HEADER,
        "record_id,demographics,text,\n",
        "participant_name,demographics,text,y\n",
        "dob,demographics,text,y\n",
        "sex,demographics,radio,\n",
        "phq9_score,phq9,calc,\n",
    ]
    path.write_text("".join(rows), encoding="utf-8")
    return path


def _write_human_readable_metadata(tmp_path: Path) -> Path:
    """Write a human-readable (Data Dictionary download) project_metadata.csv."""
    path = tmp_path / "project_metadata.csv"
    rows = [
        HUMAN_READABLE_HEADER,
        '"record_id","demographics","text",""\n',
        '"participant_name","demographics","text","y"\n',
        '"dob","demographics","text","y"\n',
        '"sex","demographics","radio",""\n',
        '"phq9_score","phq9","calc",""\n',
    ]
    path.write_text("".join(rows), encoding="utf-8")
    return path


# ═══════════════════════════════════════════════════════════════
# COLUMN-NAMING CONVENTIONS
# ═══════════════════════════════════════════════════════════════


class TestSnakeCaseProjectMetadata:
    def test_loads_identifier_flags(self, tmp_path: Path):
        meta = _write_snake_case_metadata(tmp_path)
        scrubber = RedcapPHIScrubber(meta)
        assert scrubber.is_known_identifier("participant_name")
        assert scrubber.is_known_identifier("dob")
        assert not scrubber.is_known_identifier("sex")
        assert not scrubber.is_known_identifier("phq9_score")


class TestHumanReadableProjectMetadata:
    def test_loads_identifier_flags(self, tmp_path: Path):
        meta = _write_human_readable_metadata(tmp_path)
        scrubber = RedcapPHIScrubber(meta)
        assert scrubber.is_known_identifier("participant_name")
        assert scrubber.is_known_identifier("dob")
        assert not scrubber.is_known_identifier("sex")
        assert not scrubber.is_known_identifier("phq9_score")


class TestNamingConventionsAgree:
    """ADR 0037: the scrubber must produce identical results from both
    naming conventions."""

    def test_is_identifier_matches_across_formats(self, tmp_path: Path):
        snake_dir = tmp_path / "s"
        human_dir = tmp_path / "h"
        snake_dir.mkdir()
        human_dir.mkdir()
        snake = RedcapPHIScrubber(_write_snake_case_metadata(snake_dir))
        human = RedcapPHIScrubber(_write_human_readable_metadata(human_dir))
        for field in (
            "record_id", "participant_name", "dob", "sex", "phq9_score",
        ):
            assert snake.is_known_identifier(field) == human.is_known_identifier(field)
            assert snake.is_unknown(field) == human.is_unknown(field)


# ═══════════════════════════════════════════════════════════════
# IDENTIFIER-FLAG VARIATIONS
# ═══════════════════════════════════════════════════════════════


class TestPositiveIdentifierValues:
    def test_lowercase_y(self, tmp_path: Path):
        path = tmp_path / "project_metadata.csv"
        path.write_text(
            SNAKE_CASE_HEADER + "name1,form,text,y\n",
            encoding="utf-8",
        )
        scrubber = RedcapPHIScrubber(path)
        assert scrubber.is_known_identifier("name1")

    def test_yes(self, tmp_path: Path):
        path = tmp_path / "project_metadata.csv"
        path.write_text(
            SNAKE_CASE_HEADER + "name1,form,text,yes\n",
            encoding="utf-8",
        )
        scrubber = RedcapPHIScrubber(path)
        assert scrubber.is_known_identifier("name1")

    def test_uppercase_Y(self, tmp_path: Path):
        path = tmp_path / "project_metadata.csv"
        path.write_text(
            SNAKE_CASE_HEADER + "name1,form,text,Y\n",
            encoding="utf-8",
        )
        scrubber = RedcapPHIScrubber(path)
        assert scrubber.is_known_identifier("name1")

    def test_capitalized_Yes(self, tmp_path: Path):
        path = tmp_path / "project_metadata.csv"
        path.write_text(
            SNAKE_CASE_HEADER + "name1,form,text,Yes\n",
            encoding="utf-8",
        )
        scrubber = RedcapPHIScrubber(path)
        assert scrubber.is_known_identifier("name1")

    def test_uppercase_YES(self, tmp_path: Path):
        path = tmp_path / "project_metadata.csv"
        path.write_text(
            SNAKE_CASE_HEADER + "name1,form,text,YES\n",
            encoding="utf-8",
        )
        scrubber = RedcapPHIScrubber(path)
        assert scrubber.is_known_identifier("name1")

    def test_blank_is_negative(self, tmp_path: Path):
        path = tmp_path / "project_metadata.csv"
        path.write_text(
            SNAKE_CASE_HEADER + "name1,form,text,\n",
            encoding="utf-8",
        )
        scrubber = RedcapPHIScrubber(path)
        assert not scrubber.is_known_identifier("name1")

    def test_lowercase_n_is_negative(self, tmp_path: Path):
        # REDCap's negative flag is blank; "n" / "no" should also be
        # treated as negative (defensive).
        path = tmp_path / "project_metadata.csv"
        path.write_text(
            SNAKE_CASE_HEADER + "name1,form,text,n\n",
            encoding="utf-8",
        )
        scrubber = RedcapPHIScrubber(path)
        assert not scrubber.is_known_identifier("name1")


# ═══════════════════════════════════════════════════════════════
# FAIL-CLOSED DEFAULT
# ═══════════════════════════════════════════════════════════════


class TestFailClosedDefault:
    def test_unknown_field_is_identifier_by_default(self, tmp_path: Path):
        meta = _write_snake_case_metadata(tmp_path)
        scrubber = RedcapPHIScrubber(meta)
        # A field that isn't in project_metadata.csv:
        assert scrubber.is_identifier("emergency_contact_phone")
        assert scrubber.is_unknown("emergency_contact_phone")

    def test_known_non_identifier_is_kept(self, tmp_path: Path):
        meta = _write_snake_case_metadata(tmp_path)
        scrubber = RedcapPHIScrubber(meta)
        assert not scrubber.is_identifier("sex")
        assert not scrubber.is_identifier("phq9_score")

    def test_missing_metadata_strips_everything(self, tmp_path: Path):
        # No project_metadata.csv at the expected path → fail-closed
        # default kicks in for every field.
        nonexistent = tmp_path / "missing.csv"
        scrubber = RedcapPHIScrubber(nonexistent)
        assert scrubber.is_identifier("anything")
        assert scrubber.is_identifier("phq9_score")
        assert scrubber.is_identifier("sex")

    def test_allowlist_overrides_fail_closed(self, tmp_path: Path):
        meta = _write_snake_case_metadata(tmp_path)
        scrubber = RedcapPHIScrubber(
            meta, unknown_field_allowlist=["computed_score_v2"],
        )
        # Field not in metadata + in allowlist → kept.
        assert not scrubber.is_identifier("computed_score_v2")
        # Field not in metadata + not in allowlist → still stripped.
        assert scrubber.is_identifier("other_unknown_field")

    def test_allowlist_does_not_override_known_identifier(self, tmp_path: Path):
        meta = _write_snake_case_metadata(tmp_path)
        scrubber = RedcapPHIScrubber(
            meta, unknown_field_allowlist=["participant_name"],
        )
        # Even though participant_name is in the allowlist, the data
        # dictionary still flags it as identifier=y. Known wins.
        assert scrubber.is_identifier("participant_name")


# ═══════════════════════════════════════════════════════════════
# PER-RECORD SCRUBBING
# ═══════════════════════════════════════════════════════════════


class TestScrubRecord:
    def test_strips_marked_identifiers(self, tmp_path: Path):
        meta = _write_snake_case_metadata(tmp_path)
        scrubber = RedcapPHIScrubber(meta)
        record = {
            "participant_name": "Subject 001",
            "dob": "1990-01-01",
            "sex": "F",
            "phq9_score": 12,
        }
        scrubbed, legibility = scrubber.scrub_record(record)
        assert "participant_name" not in scrubbed
        assert "dob" not in scrubbed
        assert scrubbed["sex"] == "F"
        assert scrubbed["phq9_score"] == 12

    def test_marked_legibility_list(self, tmp_path: Path):
        meta = _write_snake_case_metadata(tmp_path)
        scrubber = RedcapPHIScrubber(meta)
        record = {"participant_name": "x", "dob": "1990-01-01", "sex": "F"}
        _, legibility = scrubber.scrub_record(record)
        assert set(legibility["field_marked_identifier_stripped"]) == {
            "participant_name", "dob",
        }
        assert legibility["field_unknown_default_stripped"] == []

    def test_unknown_legibility_list(self, tmp_path: Path):
        meta = _write_snake_case_metadata(tmp_path)
        scrubber = RedcapPHIScrubber(meta)
        record = {
            "sex": "F",
            "phq9_score": 5,
            "emergency_contact_phone": "555-1234",
            "after_thought_field": "x",
        }
        scrubbed, legibility = scrubber.scrub_record(record)
        # Both unknowns are stripped.
        assert "emergency_contact_phone" not in scrubbed
        assert "after_thought_field" not in scrubbed
        # And both appear in the unknown legibility list.
        assert set(legibility["field_unknown_default_stripped"]) == {
            "emergency_contact_phone", "after_thought_field",
        }
        assert legibility["unknown_field_count"] == 2

    def test_allowlist_keeps_unknown(self, tmp_path: Path):
        meta = _write_snake_case_metadata(tmp_path)
        scrubber = RedcapPHIScrubber(
            meta, unknown_field_allowlist=["computed_score_v2"],
        )
        record = {"sex": "F", "computed_score_v2": 7.5}
        scrubbed, legibility = scrubber.scrub_record(record)
        assert scrubbed["computed_score_v2"] == 7.5
        assert legibility["field_unknown_default_stripped"] == []


# ═══════════════════════════════════════════════════════════════
# BATCH SCRUBBING
# ═══════════════════════════════════════════════════════════════


class TestScrubRecords:
    def test_aggregates_unique_names(self, tmp_path: Path):
        meta = _write_snake_case_metadata(tmp_path)
        scrubber = RedcapPHIScrubber(meta)
        records = [
            {"participant_name": "A", "dob": "1990-01-01", "sex": "F"},
            {"participant_name": "B", "dob": "1990-01-01", "sex": "M"},
            {"participant_name": "C", "sex": "F"},
        ]
        scrubbed, legibility = scrubber.scrub_records(records)
        # All three records had participant_name + dob stripped (unique
        # name list, not multiplied).
        assert set(legibility["field_marked_identifier_stripped"]) == {
            "participant_name", "dob",
        }
        # No unknown fields → empty list and zero count.
        assert legibility["field_unknown_default_stripped"] == []
        assert legibility["unknown_field_count"] == 0

    def test_total_unknown_count_aggregates(self, tmp_path: Path):
        meta = _write_snake_case_metadata(tmp_path)
        scrubber = RedcapPHIScrubber(meta)
        records = [
            {"sex": "F", "after_thought_field": "x"},
            {"sex": "M", "after_thought_field": "y"},
        ]
        _, legibility = scrubber.scrub_records(records)
        # The unique unknown name is one; the per-record count sums to
        # two (one strip per record).
        assert legibility["field_unknown_default_stripped"] == [
            "after_thought_field",
        ]
        assert legibility["unknown_field_count"] == 2

    def test_preserves_record_count(self, tmp_path: Path):
        meta = _write_snake_case_metadata(tmp_path)
        scrubber = RedcapPHIScrubber(meta)
        records = [
            {"sex": "F"}, {"sex": "M"}, {"sex": "F"},
        ]
        scrubbed, _ = scrubber.scrub_records(records)
        assert len(scrubbed) == 3


# ═══════════════════════════════════════════════════════════════
# AUDIT-ROW IDENTITY + WARNING
# ═══════════════════════════════════════════════════════════════


class TestScrubberId:
    def test_returns_canonical_identifier(self, tmp_path: Path):
        meta = _write_snake_case_metadata(tmp_path)
        scrubber = RedcapPHIScrubber(meta)
        assert scrubber.scrubber_id == "redcap_metadata_flags"

    def test_identifier_constant_even_with_missing_metadata(
        self, tmp_path: Path,
    ):
        scrubber = RedcapPHIScrubber(tmp_path / "missing.csv")
        assert scrubber.scrubber_id == "redcap_metadata_flags"


class TestChildScrubberWarning:
    def test_no_warning_when_metadata_present(self, tmp_path: Path):
        meta = _write_snake_case_metadata(tmp_path)
        scrubber = RedcapPHIScrubber(meta)
        assert scrubber.child_scrubber_warning is None

    def test_warning_when_metadata_missing(self, tmp_path: Path):
        scrubber = RedcapPHIScrubber(tmp_path / "missing.csv")
        warning = scrubber.child_scrubber_warning
        assert warning is not None
        assert "project_metadata.csv not found" in warning
        assert "fail-closed" in warning.lower()
        assert "ADR 0037" in warning

    def test_warning_when_metadata_lacks_required_columns(
        self, tmp_path: Path,
    ):
        path = tmp_path / "project_metadata.csv"
        path.write_text(
            "some_random_col,other_col\nfoo,bar\n",
            encoding="utf-8",
        )
        scrubber = RedcapPHIScrubber(path)
        assert scrubber.child_scrubber_warning is not None


# ═══════════════════════════════════════════════════════════════
# SEAM TOPOLOGY (PARALLEL, NOT HIERARCHICAL)
# ═══════════════════════════════════════════════════════════════


class TestSeamTopology:
    def test_does_not_inherit_from_framework_phi_scrubber(self):
        """ADR 0037 § 'Built-in PHI scrubber — a new seam parallel to
        ADR 0003': the seams are intentionally parallel, not
        hierarchical. The child-level scrubber must not be a subclass
        of framework.security.PHIScrubber."""
        assert not issubclass(RedcapPHIScrubber, PHIScrubber)

    def test_is_a_distinct_class(self):
        assert RedcapPHIScrubber is not PHIScrubber


# ═══════════════════════════════════════════════════════════════
# CORRUPT METADATA — FAIL-CLOSED ACROSS THREE FAILURE MODES
# ═══════════════════════════════════════════════════════════════
#
# Closes the v7.3.1 coverage regression on RedcapPHIScrubber._load_metadata
# the bug hunt's coverage-criticality-mapper named CRITICAL: the exception
# handler at scrubber.py:132 (now ~135 post-v7.3.1 path-placeholder edit)
# was code-correct but had no executable test. A malformed metadata file
# would silently activate fail-closed mode with a warning; without a test,
# any future refactor that broke fail-closed (e.g., changing the empty-map
# default to allowlist-all-unknowns) would land green.
#
# Plus a parallel test for the field_col-is-None branch at scrubber.py:116,
# which per the proposal-mode auditor's note may activate on the BOM-only
# fixture instead of the exception handler — encoding="utf-8-sig" strips
# a leading BOM transparently, so a BOM-only file yields fieldnames=[]
# and hits the column-resolution failure branch, not the parse-error one.


class TestFailClosedOnCorruptProjectMetadata:
    """Three failure modes; same fail-closed invariant on each.

    Regression for the v7.3.0 coverage gap CRITICAL-classified by the
    bug hunt's coverage-criticality-mapper (per ADR 0014 § "Newly-
    uncovered code in CRITICAL or HIGH regions is COVERAGE REGRESSION
    regardless of overall percentage"). The PHI-scrubber seam is
    CRITICAL per ADR 0003 + ADR 0037.
    """

    def test_fail_closed_on_os_error_opening_metadata(self, tmp_path: Path, monkeypatch):
        """OSError on open() → exception handler fires → fail closed.

        Hits the exception handler at scrubber.py:135 (post-v7.3.1
        path-substitution). OSError is the most reliable
        cross-platform trigger for the exception handler arm of
        (OSError, csv.Error, ValueError) — file-locked / permission-
        denied / device-disconnected paths all surface as OSError.
        Patches builtins.open to raise so we don't depend on
        platform-specific permission behaviour or global csv module
        state (the field_size_limit alternative would mutate global
        state shared with other tests).
        """
        meta = tmp_path / "project_metadata.csv"
        # Write a valid-shape file so the existence check passes; the
        # patched open() is what makes the read fail.
        meta.write_text("field_name,identifier\nx,\n", encoding="utf-8")

        import builtins
        original_open = builtins.open

        def _raising_open(path, *args, **kwargs):
            if str(path) == str(meta):
                raise OSError("simulated read failure")
            return original_open(path, *args, **kwargs)

        monkeypatch.setattr(builtins, "open", _raising_open)
        scrubber = RedcapPHIScrubber(meta)
        assert scrubber.child_scrubber_warning is not None, (
            "scrubber should set _warning on OSError during metadata read"
        )
        # Path-disclosure regression — v7.3.1 item 2 + Coupling B fix.
        assert str(tmp_path) not in scrubber.child_scrubber_warning, (
            f"absolute path leaked into child_scrubber_warning despite v7.3.1 "
            f"placeholder substitution: {scrubber.child_scrubber_warning!r}"
        )
        assert "<configured_redcap_metadata_path>" in scrubber.child_scrubber_warning, (
            "placeholder marker missing — v7.3.1 path-substitution regressed"
        )
        assert "ADR 0037" in scrubber.child_scrubber_warning, (
            "ADR citation missing — operator-debug surface lost"
        )
        # Fail-closed: every unknown field is treated as identifier.
        assert scrubber.is_identifier("any_field_name") is True
        assert scrubber.is_identifier("phq9_score") is True

    def test_fail_closed_on_non_utf8_bytes(self, tmp_path: Path):
        """Non-UTF-8 byte sequence raises UnicodeDecodeError → fail closed.

        UnicodeDecodeError is a subclass of ValueError, caught by the
        handler at scrubber.py:132. The file is written as raw bytes
        with a Latin-1-only character that breaks the utf-8-sig decoder.
        """
        meta = tmp_path / "project_metadata.csv"
        # 0xFF on its own is invalid as a UTF-8 start byte.
        meta.write_bytes(
            b"field_name,form_name,field_type,identifier\n"
            b"\xff\xff_bad_bytes,demographics,text,y\n"
        )
        scrubber = RedcapPHIScrubber(meta)
        assert scrubber.child_scrubber_warning is not None
        assert str(tmp_path) not in scrubber.child_scrubber_warning
        assert "<configured_redcap_metadata_path>" in scrubber.child_scrubber_warning
        assert "ADR 0037" in scrubber.child_scrubber_warning
        # Fail-closed.
        assert scrubber.is_identifier("anything") is True

    def test_fail_closed_on_bom_only_file(self, tmp_path: Path):
        """BOM-only file → fieldnames empty → field_col is None branch.

        Per the proposal-mode auditor's prediction: encoding="utf-8-sig"
        transparently strips a leading BOM, so a BOM-only file presents
        an empty stream to csv.DictReader. fieldnames is None or empty;
        _resolve_column returns None; the warning emitted is the one at
        scrubber.py:116, NOT the parse-error handler at :132. Different
        branch, same fail-closed invariant.
        """
        meta = tmp_path / "project_metadata.csv"
        # UTF-8 BOM with no body at all.
        meta.write_bytes(b"\xef\xbb\xbf")
        scrubber = RedcapPHIScrubber(meta)
        assert scrubber.child_scrubber_warning is not None, (
            "BOM-only file should activate the field_col-is-None branch"
        )
        assert str(tmp_path) not in scrubber.child_scrubber_warning
        # Path-disclosure regression: this branch's warning was also
        # path-leaking pre-v7.3.1 per Coupling B; verify placeholder
        # substitution holds on this branch too.
        assert "<configured_redcap_metadata_path>" in scrubber.child_scrubber_warning, (
            f"path placeholder missing on field_col-is-None branch warning: "
            f"{scrubber.child_scrubber_warning!r}"
        )
        assert "ADR 0037" in scrubber.child_scrubber_warning
        # Fail-closed invariant holds on this branch too.
        assert scrubber.is_identifier("anything") is True
