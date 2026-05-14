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
