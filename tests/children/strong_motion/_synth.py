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
