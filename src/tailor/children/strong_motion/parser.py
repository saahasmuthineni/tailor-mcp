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
  ``time, accel, time, accel, …`` in reading order across the data
  lines. Even-indexed fields are times (seconds), odd-indexed are
  accelerations (G/10). The sample interval ``dt`` is recovered from
  the time column.
* **Header blocks + multiple channels.** The real CESMD file interposes
  an integer header block (width-5 fields) and a float header block
  (width-10 fields) between the text header and the data, and
  concatenates all three channels in one file (each with its own
  header + ``----- END OF DATA FOR CHANNEL N -----`` separator). The
  data block is therefore found *structurally* — the first run of lines
  that slice cleanly into width-7 floats with a strictly-increasing time
  column starting near 0 — not by a marker keyword. Reading stops at the
  channel separator, so a parse returns channel 1 (the 90° horizontal
  that carries the 1.927 g reference peak).

Refusal (mirrors the MATLAB child's HDF5 magic-byte guard, inverted):
if the bytes/header do not match the COSMOS V1 shape — binary content,
a missing header signature, or no fixed-width acceleration data block —
the parser raises :class:`ParseRefusalError` with a message naming what
was expected, rather than returning a plausible-looking but wrong number.
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

# Patterns that declare the acceleration-point count. The real CESMD
# header uses "NO. OF POINTS = 12107"; synthetic fixtures may use
# "<N> points of acceleration data". The captured integer is the number
# of (time, accel) pairs in one channel's data block. Optional — when
# absent, the structural data-block scan determines the count.
_NPTS_PATTERNS = (
    re.compile(r"no\.?\s+of\s+points\s*=?\s*(\d+)", re.IGNORECASE),
    re.compile(r"(\d+)\s+points?\s+of\s+accel", re.IGNORECASE),
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


def _extract_npts(lines: list[str]) -> int | None:
    """First declared acceleration-point count, or ``None`` if absent."""
    for line in lines[:HEADER_SCAN_LINES]:
        for rx in _NPTS_PATTERNS:
            m = rx.search(line)
            if m:
                try:
                    return int(m.group(1))
                except (ValueError, IndexError):
                    continue
    return None


def _try_data_line(line: str) -> list[float] | None:
    """Parse a line as a strict fixed-width data line, or ``None``.

    A data line is sliced into ``FIELD_WIDTH``-char fields, EVERY one of
    which must parse as a float (any non-numeric chunk disqualifies the
    whole line), with an even field count >= 2 (interleaved time/accel
    pairs). This strictness is what lets the structural data-block scan
    skip the COSMOS header's integer block (width-5 fields) and float
    block (width-10 fields): sliced at 7 they yield chunks with interior
    spaces or a bare ``.`` that fail ``float()``.
    """
    stripped = line.rstrip()
    if not stripped:
        return None
    vals: list[float] = []
    for i in range(0, len(stripped), FIELD_WIDTH):
        chunk = stripped[i:i + FIELD_WIDTH].strip()
        if not chunk:
            continue
        try:
            vals.append(float(chunk))
        except ValueError:
            return None
    if len(vals) < 2 or len(vals) % 2 != 0:
        return None
    return vals


def _is_data_block_start(vals: list[float]) -> bool:
    """True if ``vals`` looks like the first line of the data block.

    Discriminates real data from any header line that happens to slice
    into clean floats: the time column (even-indexed fields) must be
    strictly increasing and start near the record origin (t0 < 1 s).
    """
    times = vals[0::2]
    if abs(times[0]) >= 1.0:
        return False
    return all(times[i] < times[i + 1] for i in range(len(times) - 1))


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

    declared_npts = _extract_npts(lines)

    # Locate the start of the data block structurally. The CESMD V1 file
    # interposes an integer header block (width-5 fields) and a float
    # header block (width-10 fields) between the text header and the
    # data; neither survives strict width-7 float slicing, so the first
    # line that both parses cleanly AND has a strictly-increasing time
    # column starting near 0 is the data start.
    data_start: int | None = None
    for idx, line in enumerate(lines):
        vals = _try_data_line(line)
        if vals is not None and _is_data_block_start(vals):
            data_start = idx
            break
    if data_start is None:
        raise ParseRefusalError(
            "COSMOS V1 header recognized but no acceleration-data block "
            "found (no fixed-width time/accel section with an increasing "
            "time column)."
        )

    # Collect the first contiguous run of data lines. The run ends at the
    # first non-data line — for the real multi-channel file that is the
    # '----- END OF DATA FOR CHANNEL 1 -----' separator, so we read only
    # channel 1 (the 90-deg horizontal). npts is a belt-and-suspenders cap.
    fields: list[float] = []
    for line in lines[data_start:]:
        vals = _try_data_line(line)
        if vals is None:
            break
        fields.extend(vals)
        if declared_npts and len(fields) >= 2 * declared_npts:
            break

    if len(fields) < 2:
        raise ParseRefusalError(
            "COSMOS V1 data block contained no parseable time/accel pairs."
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
        # Real header: "CHAN  1:  90 DEG". Channel from the CHAN token;
        # azimuth from the "<N> DEG" degree marker on the same line.
        channel=_extract_int(lines, r"chan(?:nel)?\.?\s*(\d+)"),
        azimuth=_extract_int(lines, r"(\d+)\s*deg"),
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
    """Best-effort station label.

    Prefers a header line naming the station (the real CESMD header has
    'STATION NO. 24436  34.160N, 118.534W ...'); falls back to the first
    non-empty line for synthetic fixtures that lead with the station name.
    """
    for line in lines[:HEADER_SCAN_LINES]:
        if "station" in line.lower() and line.strip():
            return line.strip()[:120]
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
