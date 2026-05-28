"""
COSMOS V1 Strong-Motion Parser
================================
Reads a COSMOS Volume-1 (uncorrected acceleration) strong-motion
record into a plain-Python :class:`StrongMotionRecord`. Stdlib-only —
the V1 format is fixed-width text, so no special library is needed
(contrast the MATLAB child, which pulls in scipy).

This module owns *I/O and byte-level format knowledge*. The pure
analytics (PGA, Arias intensity, response spectra) live in
``processing.py`` and never touch a file — the ADR 0008
determinism-by-construction split. ``parse_v1_text`` itself is pure
(``str -> StrongMotionRecord``); only ``parse_v1_file`` reads bytes.

Format gotchas (calibrated against the Phase-0 spike on
``TARZANA.RAW`` from the Northridge ``ce24436r.zip`` CESMD record;
the exact header-keyword set and column width are re-validated against
the real file in the Phase-2 notebook):

* **Units are G/10.** The header declares acceleration in tenths of g;
  divide raw values by 10 to get g. A raw peak of ``19.27`` is
  ``1.927 g`` — the Northridge Tarzana channel-1 (90°) reference value.
* **Fixed-width 7-char columns.** The data section is Fortran
  fixed-format: each value occupies exactly 7 characters with no
  guaranteed separator (a leading-minus value like ``-12.345`` fills
  the field and can touch its neighbour). Splitting on whitespace
  silently corrupts the trace; slice at width 7 instead.
* **Interleaved time/accel pairs.** Data fields alternate
  ``time, accel, time, accel, …`` in reading order across all data
  lines. Even-indexed fields are times (seconds), odd-indexed are
  accelerations (G/10). The sample interval ``dt`` is recovered from
  the time column.

Refusal (mirrors the MATLAB child's HDF5 magic-byte guard, inverted):
if the bytes/header do not match the COSMOS V1 shape — binary content,
a missing header signature, or no acceleration data section — the
parser raises :class:`ParseRefusalError` with a message naming what was
expected, rather than returning a plausible-looking but wrong number.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# Fixed-width data column, in characters. See module docstring.
FIELD_WIDTH = 7

# How many header lines to scan for the COSMOS V1 signature + the
# acceleration-data marker. Real V1 headers are well under this.
HEADER_SCAN_LINES = 60

# Case-insensitive header tokens that mark a file as a COSMOS Volume-1
# (uncorrected acceleration) strong-motion record. Any one present in
# the header scan region clears the signature check. The set is
# deliberately broad — CESMD/CSMIP raw headers vary — and is the
# surface re-validated against the real TARZANA.RAW in Phase 2.
COSMOS_V1_HEADER_TOKENS = (
    "cosmos",
    "uncorrected",
    "csmip",
    "g/10",
    "strong motion",
    "strong-motion",
    "raw acceleration",
)

# A line declaring the acceleration-point count, e.g.
# "5001 points of acceleration data" or "5001 acceleration pts".
# The captured integer is the number of (time, accel) pairs.
_DATA_MARKER = re.compile(
    r"(\d+)\s+(?:points?\s+of\s+)?accel\w*(?:\s+(?:data|pts|points))?",
    re.IGNORECASE,
)

# Bytes that mark a non-V1 binary file we refuse up front, before any
# text decode. HDF5 (a `.mat` v7.3 mistakenly dropped in the dir) and a
# generic NUL byte (any binary blob) both fail the V1 text contract.
_HDF5_MAGIC = b"\x89HDF\r\n\x1a\n"


class ParseRefusalError(Exception):
    """Raised when input does not match the COSMOS V1 strong-motion shape.

    A typed refusal — distinct from a generic ``ValueError`` — so the
    child can catch exactly this condition and surface a clear,
    actionable message instead of a half-parsed trace.
    """


@dataclass
class StrongMotionRecord:
    """One parsed COSMOS V1 channel (one file = one record = one channel).

    ``accel_g`` is acceleration in g (raw G/10 already divided by 10).
    ``entity_id`` scoping (ADR 0009) keys on the station-event code; one
    record is one such code.
    """

    accel_g: list[float]
    times_s: list[float]
    dt: float
    npts: int
    station: str
    channel: int | None
    azimuth: int | None
    units_note: str


def _looks_binary(raw: bytes) -> bool:
    """True if the bytes are clearly not COSMOS V1 text."""
    if raw.startswith(_HDF5_MAGIC):
        return True
    # A COSMOS V1 file is plain ASCII/Latin-1 text; an embedded NUL is
    # the cheapest tell for an arbitrary binary blob.
    return b"\x00" in raw[:4096]


def _header_has_signature(lines: list[str]) -> bool:
    head = "\n".join(lines[:HEADER_SCAN_LINES]).lower()
    return any(token in head for token in COSMOS_V1_HEADER_TOKENS)


def _extract_int(lines: list[str], pattern: str) -> int | None:
    """First capture-group int matching ``pattern`` across header lines."""
    rx = re.compile(pattern, re.IGNORECASE)
    for line in lines[:HEADER_SCAN_LINES]:
        m = rx.search(line)
        if m:
            try:
                return int(m.group(1))
            except (ValueError, IndexError):
                continue
    return None


def _slice_fields(line: str) -> list[float]:
    """Slice a data line into ``FIELD_WIDTH``-char fields, float each.

    Non-empty fields that fail to parse are skipped (tolerates the
    occasional stray character without corrupting the trace); blank
    fields are ignored. A line with no numeric fields returns ``[]``.
    """
    out: list[float] = []
    for i in range(0, len(line), FIELD_WIDTH):
        chunk = line[i:i + FIELD_WIDTH].strip()
        if not chunk:
            continue
        try:
            out.append(float(chunk))
        except ValueError:
            continue
    return out


def parse_v1_text(text: str) -> StrongMotionRecord:
    """Parse COSMOS V1 record text into a :class:`StrongMotionRecord`.

    Pure: no file I/O, no clock, no PRNG. Raises
    :class:`ParseRefusalError` if ``text`` does not match the V1 shape.
    """
    lines = text.splitlines()
    if not _header_has_signature(lines):
        raise ParseRefusalError(
            "Not a COSMOS V1 strong-motion record: header is missing the "
            f"V1 signature (expected one of {list(COSMOS_V1_HEADER_TOKENS)} "
            "in the first header lines)."
        )

    # Locate the acceleration-data marker line; everything after it is
    # the fixed-width data section. The integer it carries is npts (the
    # number of time/accel pairs).
    marker_idx: int | None = None
    declared_npts: int | None = None
    for idx, line in enumerate(lines[:HEADER_SCAN_LINES]):
        m = _DATA_MARKER.search(line)
        if m:
            marker_idx = idx
            try:
                declared_npts = int(m.group(1))
            except (ValueError, IndexError):
                declared_npts = None
            break
    if marker_idx is None:
        raise ParseRefusalError(
            "COSMOS V1 header recognized but no acceleration-data section "
            "found (expected a line like '<N> points of acceleration data')."
        )

    # Flatten every numeric field from the data lines in reading order.
    fields: list[float] = []
    for line in lines[marker_idx + 1:]:
        parsed = _slice_fields(line)
        if not parsed and fields:
            # First all-non-numeric line after data has begun: treat as
            # a footer / trailer and stop.
            break
        fields.extend(parsed)

    if len(fields) < 2:
        raise ParseRefusalError(
            "COSMOS V1 data section contained no parseable time/accel pairs."
        )

    n_pairs = len(fields) // 2
    if declared_npts:
        n_pairs = min(n_pairs, declared_npts)

    times_s = [fields[2 * i] for i in range(n_pairs)]
    accel_g = [fields[2 * i + 1] / 10.0 for i in range(n_pairs)]  # G/10 -> g

    dt = _derive_dt(times_s)

    return StrongMotionRecord(
        accel_g=accel_g,
        times_s=times_s,
        dt=dt,
        npts=n_pairs,
        station=_extract_station(lines),
        channel=_extract_int(lines, r"chan(?:nel)?\.?\s*[:#]?\s*(\d+)"),
        azimuth=_extract_int(lines, r"azimuth\s*[:#]?\s*(\d+)"),
        units_note="raw values are G/10; divided by 10 to report g",
    )


def _derive_dt(times_s: list[float]) -> float:
    """Recover the sample interval from the time column.

    Uses the first strictly-positive consecutive difference. Raises if
    the time column never increases (a malformed record).
    """
    for prev, nxt in zip(times_s, times_s[1:], strict=False):
        delta = nxt - prev
        if delta > 0:
            return round(delta, 9)
    raise ParseRefusalError(
        "Could not determine sample interval: the time column does not "
        "increase. Expected interleaved time/accel pairs."
    )


def _extract_station(lines: list[str]) -> str:
    """Best-effort station label from the first non-empty header line."""
    for line in lines[:HEADER_SCAN_LINES]:
        stripped = line.strip()
        if stripped:
            return stripped[:120]
    return "unknown"


def parse_v1_file(path: Path) -> StrongMotionRecord:
    """Read a COSMOS V1 file from disk and parse it.

    The only I/O entry point. Refuses binary content (HDF5 magic, NUL
    bytes) before attempting a text decode, then delegates to
    :func:`parse_v1_text`.
    """
    raw = path.read_bytes()
    if _looks_binary(raw):
        raise ParseRefusalError(
            f"{path.name} is not a COSMOS V1 text record (binary content "
            "detected). v7.3 HDF5 `.mat` files and other binaries are not "
            "strong-motion V1 records."
        )
    # COSMOS V1 is ASCII; latin-1 decodes any byte without raising, so a
    # stray high byte degrades to a skipped field rather than a crash.
    text = raw.decode("latin-1")
    return parse_v1_text(text)
