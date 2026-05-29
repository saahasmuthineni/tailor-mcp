"""
Parser tests for the COSMOS V1 strong-motion reader.

Covers the three behaviours the parser exists to guarantee:

* **Happy path** — a synthetic V1 record round-trips through the
  fixed-width slicer + G/10 conversion, and the recovered peak matches
  the constructed value (the Phase-0 spike's Northridge Tarzana
  channel-1 reference is 1.927 g; here we reproduce it from synthetic
  bytes rather than a real download — ADR 0042).
* **Typed parse refusal** — non-V1 input (plain text, binary/HDF5, a
  header with no data section) raises ``ParseRefusalError``, mirroring
  the MATLAB child's HDF5 magic-byte guard.
* **Format gotchas** — fixed-width 7-char slicing (not whitespace
  split) and dt recovery from the time column.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tailor.children.strong_motion.parser import (
    FIELD_WIDTH,
    ParseRefusalError,
    _is_data_block_start,
    _try_data_line,
    parse_v1_file,
    parse_v1_text,
)
from tailor.children.strong_motion.processing import StrongMotionProcessing

from ._synth import make_real_shaped_v1, make_v1_text

# The Phase-0 reference: raw PGA of Northridge Tarzana channel-1 (90°).
REFERENCE_PGA_G = 1.927


class TestHappyPath:
    def test_parses_synthetic_record_and_pga_matches_reference(self):
        accel_g = [0.10, -0.50, 1.20, REFERENCE_PGA_G, -0.80, 0.30, -1.50, 0.05]
        rec = parse_v1_text(make_v1_text(accel_g, dt=0.01))

        assert rec.npts == len(accel_g)
        assert rec.dt == pytest.approx(0.01)
        assert rec.channel == 1
        assert rec.azimuth == 90

        pga = StrongMotionProcessing.peak_acceleration_g(rec.accel_g)
        assert pga == pytest.approx(REFERENCE_PGA_G, abs=1e-6)

    def test_units_are_converted_from_g_over_10(self):
        # A single 19.27 G/10 sample must come back as 1.927 g.
        rec = parse_v1_text(make_v1_text([1.927, 0.0, -0.5], dt=0.02))
        assert max(abs(v) for v in rec.accel_g) == pytest.approx(1.927, abs=1e-6)
        assert "G/10" in rec.units_note or "g" in rec.units_note

    def test_dt_recovered_from_time_column(self):
        rec = parse_v1_text(make_v1_text([0.1, 0.2, 0.3, 0.4], dt=0.005))
        assert rec.dt == pytest.approx(0.005)
        assert rec.times_s[0] == pytest.approx(0.0)
        assert rec.times_s[1] == pytest.approx(0.005)


class TestFixedWidthSlicing:
    def test_adjacent_negative_values_not_split_on_whitespace(self):
        # A run of negatives packs 7-char fields that touch with no
        # separating space; whitespace-splitting would mis-count them.
        accel_g = [-1.234, -2.345, -3.456, -4.567]
        text = make_v1_text(accel_g, dt=0.01, pairs_per_line=4)
        rec = parse_v1_text(text)
        assert rec.npts == 4
        # All four negatives recovered in order — packed 7-char fields
        # (-12.340 etc. in G/10) touch with no separating space, so
        # whitespace-splitting would mis-parse them.
        assert rec.accel_g == pytest.approx(accel_g)

    def test_field_width_is_seven(self):
        assert FIELD_WIDTH == 7


class TestParseRefusal:
    def test_plain_text_is_refused(self):
        with pytest.raises(ParseRefusalError):
            parse_v1_text(
                "hello world\nthis is just a plain text file\n"
                "it has no seismic header at all\n"
            )

    def test_csv_like_input_is_refused(self):
        with pytest.raises(ParseRefusalError):
            parse_v1_text("time,accel\n0.0,0.1\n0.01,0.2\n0.02,0.3\n")

    def test_header_without_data_section_is_refused(self):
        # Carries the V1 signature but no acceleration-data marker.
        text = (
            "STATION X\n"
            "COSMOS V1 UNCORRECTED ACCELERATION RECORD\n"
            "CHANNEL 1 AZIMUTH 90\n"
            "ACCELERATION UNITS: G/10\n"
        )
        with pytest.raises(ParseRefusalError):
            parse_v1_text(text)

    def test_binary_hdf5_file_is_refused(self, tmp_path: Path):
        # An HDF5 `.mat` v7.3 file dropped in the records dir must be
        # refused before any text decode — mirrors the MATLAB guard.
        blob = tmp_path / "v73.v1"
        blob.write_bytes(b"\x89HDF\r\n\x1a\n" + b"\x00" * 256)
        with pytest.raises(ParseRefusalError):
            parse_v1_file(blob)

    def test_refusal_message_names_the_expectation(self):
        with pytest.raises(ParseRefusalError) as excinfo:
            parse_v1_text("random non-seismic content\n")
        assert "COSMOS V1" in str(excinfo.value)


class TestRealShapedFormat:
    """Network-free guard on the REAL CESMD V1 structure.

    Replicates what real-file validation (TARZANA.RAW) confirmed: a text
    header, a width-5 integer block, a width-10 float block, multiple
    concatenated channels with END-OF-DATA separators, and a
    'NO. OF POINTS = N' count line (not the synthetic 'N points of
    acceleration' marker).
    """

    def test_skips_header_blocks_and_reads_channel_1_only(self):
        ch1 = [0.0, 0.5, 1.927, -0.8, 0.3, -1.5, 0.2, 0.1]  # peak 1.927
        ch2 = [0.0, 0.2, -0.4, 0.5, -0.1]                    # peak 0.5
        rec = parse_v1_text(make_real_shaped_v1(ch1, ch2, dt=0.005))

        assert rec.channel == 1
        assert rec.azimuth == 90
        assert rec.npts == len(ch1)  # channel 1 only, stopped at separator
        # PGA is channel 1's peak (1.927), not channel 2's (0.5) — proves
        # the integer/float header blocks were skipped and the channel
        # separator halted the read.
        pga = StrongMotionProcessing.peak_acceleration_g(rec.accel_g)
        assert pga == pytest.approx(1.927, abs=1e-6)

    def test_no_of_points_count_line_is_parsed(self):
        ch1 = [0.0, 0.1, 0.2, 0.3]
        rec = parse_v1_text(make_real_shaped_v1(ch1, [0.0, 0.1], dt=0.01))
        assert rec.npts == 4


class TestParseFile:
    def test_round_trips_through_disk(self, tmp_path: Path):
        path = tmp_path / "record_a.v1"
        path.write_text(make_v1_text([0.0, 1.0, 1.927, -0.5], dt=0.01), encoding="utf-8")
        rec = parse_v1_file(path)
        assert rec.npts == 4
        assert max(abs(v) for v in rec.accel_g) == pytest.approx(1.927, abs=1e-6)


class TestBlankFieldMisalignmentGuard:
    """A blank interior fixed-width field must disqualify the data line,
    not be silently skipped. Skipping shifts the interleaved time/accel
    pairs into wrong positions — a silent wrong-answer path. Regression
    for the Gemini HIGH finding on PR #137.
    """

    @staticmethod
    def _field(v: float) -> str:
        f = f"{v:7.3f}"
        assert len(f) == FIELD_WIDTH  # guard the test's own assumption
        return f

    def test_clean_interleaved_line_parses(self):
        line = (
            self._field(0.0) + self._field(1.234)
            + self._field(0.010) + self._field(-2.345)
        )
        assert _try_data_line(line) == pytest.approx([0.0, 1.234, 0.010, -2.345])

    def test_blank_interior_field_is_refused_not_skipped(self):
        # time / accel / [BLANK FIELD] / accel: the old `continue` skipped
        # the blank and returned 4 misaligned floats that passed the
        # even-count check. The guard must return None instead.
        line = (
            self._field(0.0) + self._field(1.234)
            + " " * FIELD_WIDTH
            + self._field(0.010) + self._field(-2.345)
        )
        assert _try_data_line(line) is None


class TestDataBlockStartGuard:
    """_is_data_block_start must require >= 2 time/accel pairs, so a
    single-pair line (or a lone NaN time) can't be mistaken for the start
    of the multi-column data block. (Gemini MED, PR #137.)"""

    def test_single_pair_line_is_not_a_data_block_start(self):
        assert _is_data_block_start([0.0, 1.234]) is False

    def test_lone_nan_time_is_not_a_data_block_start(self):
        assert _is_data_block_start([float("nan"), 1.0]) is False

    def test_valid_multi_pair_increasing_time_is_a_data_block_start(self):
        # times = [0.0, 0.01, 0.02] — near origin and strictly increasing.
        assert _is_data_block_start([0.0, 1.0, 0.01, -2.0, 0.02, 0.5]) is True
