"""
Synthetic COSMOS V1-shaped record builder for strong-motion tests.

No real seismic files are needed for CI (per ADR 0042 — real data is a
runtime download in the Phase-2 notebook, never bundled). This helper
emits a V1-shaped text record from a list of accelerations in g, so a
test can construct a record whose peak / Arias / duration it knows by
construction and assert the parser + analytics reproduce them.

The layout mirrors what ``parser.py`` expects: a text header carrying
the COSMOS V1 signature + a "<N> points of acceleration data" marker,
followed by a fixed-width 7-char data section with interleaved
time/accel pairs in G/10 units.
"""

from __future__ import annotations

from pathlib import Path


def _fmt7(x: float) -> str:
    """Format a number into exactly 7 characters (Fortran fixed-format)."""
    s = f"{x:7.3f}"
    # Synthetic values stay small enough to fit; guard against overflow
    # so a careless test value can't silently produce a >7-char field.
    return s if len(s) == 7 else s[-7:]


def make_v1_text(
    accel_g: list[float],
    dt: float,
    *,
    station: str = "TARZANA - NORTHRIDGE 1994",
    channel: int = 1,
    azimuth: int = 90,
    pairs_per_line: int = 4,
) -> str:
    """Build a COSMOS V1-shaped record string.

    ``accel_g`` is acceleration in g; values are written back out in
    G/10 (×10) so a round-trip through the parser's ÷10 returns g.
    """
    raw = [a * 10.0 for a in accel_g]  # g -> G/10
    times = [i * dt for i in range(len(accel_g))]
    npts = len(accel_g)

    header = [
        station,
        "COSMOS V1 UNCORRECTED ACCELERATION RECORD",
        f"CHANNEL {channel}   AZIMUTH {azimuth} DEG",
        "ACCELERATION UNITS: G/10  (DIVIDE BY 10 FOR G)",
        f"{npts} points of acceleration data follow",
    ]

    fields: list[str] = []
    for t, a in zip(times, raw, strict=True):
        fields.append(_fmt7(t))
        fields.append(_fmt7(a))

    per_line = pairs_per_line * 2
    data_lines = [
        "".join(fields[i:i + per_line])
        for i in range(0, len(fields), per_line)
    ]
    return "\n".join(header + data_lines) + "\n"


def write_v1_file(directory: Path, name: str, accel_g: list[float], dt: float, **kw) -> Path:
    """Write a synthetic V1 record to ``directory/name`` and return the path."""
    path = directory / name
    path.write_text(make_v1_text(accel_g, dt, **kw), encoding="utf-8")
    return path


def _cosmos_field(v: float, width: int) -> str:
    """Format a value the CESMD way: F-format with the leading zero dropped.

    The real file renders sub-1 magnitudes as ``.040`` / ``-.008`` (no
    leading zero), which is what makes a width-10 float-block field slice
    to a bare ``.`` at width 7 and fail parsing. Replicating that exactly
    is what gives the real-shaped fixture its discriminating power.
    """
    s = f"{v:.3f}"
    if s.startswith("0."):
        s = s[1:]
    elif s.startswith("-0."):
        s = "-" + s[2:]
    return s.rjust(width)


def make_real_shaped_v1(
    ch1_accel_g: list[float],
    ch2_accel_g: list[float],
    dt: float,
    *,
    ch1_azimuth: int = 90,
    ch2_azimuth: int = 180,
) -> str:
    """Build a record mimicking the REAL CESMD V1 structure.

    Faithful to ``TARZANA.RAW``: each channel has a text header, a width-5
    integer header block, a width-10 float header block (leading-dot
    style), a width-7 data block, and an
    ``----- END OF DATA FOR CHANNEL N -----`` separator. Two channels are
    concatenated so a parser that ignores the separator would bleed
    channel 2 into channel 1.
    """
    def channel_block(accel_g: list[float], chan: int, az: int) -> list[str]:
        raw = [a * 10.0 for a in accel_g]
        times = [i * dt for i in range(len(accel_g))]
        npts = len(accel_g)
        text = [
            "UNCORRECTED ACCELEROGRAM DATA              PROCESSED: 02/28/94",
            "NORTHRIDGE EARTHQUAKE",
            "STATION NO. 99999   34.000N, 118.000W   SMA-1  S/N 0001",
            "TEST - SYNTHETIC REAL-SHAPED RECORD",
            f"CHAN  {chan}:  {az} DEG",
            f"NO. OF POINTS =  {npts}  RECORD LENGTH = {round((npts - 1) * dt, 3)} SEC",
            "UNITS OF UNCOR ACCEL ARE SEC AND G/10.     MAX  =  9.999 G.",
        ]
        ints = [1, 1, 1, 3, 3, 0, 1, 1, 1, 2048, 0, 0, 0, 0, 0, 0]
        int_block = [
            "".join(f"{v:5d}" for v in ints),
            "".join(f"{0:5d}" for _ in range(16)),
        ]
        floats = [0.040, 0.583, 60.0, 0.160, 1.0, 1.859, 1.927, 8.352]
        float_block = ["".join(_cosmos_field(v, 10) for v in floats)]
        fields: list[str] = []
        for t, a in zip(times, raw, strict=True):
            fields.append(_cosmos_field(t, 7))
            fields.append(_cosmos_field(a, 7))
        data = ["".join(fields[i:i + 10]) for i in range(0, len(fields), 10)]
        sep = [f"/&  ----------  END OF DATA FOR CHANNEL  {chan}  ----------"]
        return text + int_block + float_block + data + sep

    lines = (
        channel_block(ch1_accel_g, 1, ch1_azimuth)
        + channel_block(ch2_accel_g, 2, ch2_azimuth)
    )
    return "\n".join(lines) + "\n"
