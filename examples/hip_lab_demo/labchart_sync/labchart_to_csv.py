"""
labchart_to_csv — structure-sniffing normalizer for raw LabChart text
exports (Phase-2 safety net for the csv_synchronized_windows demo).

A raw LabChart "Export as text" file is not a clean CSV: it carries a
header preamble (``Interval=``, ``ChannelTitle=``, ``Range=`` ...),
is usually tab-delimited, may or may not include a time column, and
can have comment rows spliced into the middle of the data. A generic
CSV reader chokes on all of that.

This normalizer finds the numeric data block by *shape* rather than by
trusting any particular header layout:

  1. Detect the delimiter (tab / comma / semicolon) by which one
     produces the most all-numeric multi-column lines.
  2. The data block is every all-numeric line of the modal column
     width. Comment rows (non-numeric, or odd width) are simply not
     numeric, so they fall out for free — that handles a
     comment-interrupted data block with no special case.
  3. Channel names come from a ``ChannelTitle=`` line if present, else
     from a bare header row just above the data, else are synthesized.
  4. A time column is detected by shape: if column 0 is strictly
     increasing across every data row it IS the clock. Otherwise time
     is synthesized from ``Interval=`` (or, as a last resort, a 1.0 s
     row index).

Output is a clean comma-delimited CSV with a ``t_s`` time column first
— exactly the shape ``csv_dir`` + ``csv_synchronized_windows`` expect.

This is demo-support glue on the ``feature/csv-synchronized-windows``
branch — it lives under ``examples/``, not in framework code.

Usage
-----
    # Normalize one real LabChart export (Phase 2, at the lab):
    python labchart_to_csv.py recording.txt cleaned.csv

    # Run the fabricated-input self-test (built tonight, no real file):
    python labchart_to_csv.py --selftest
"""

from __future__ import annotations

import csv
import re
import sys
from collections import Counter
from pathlib import Path

_NUM_RE = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


def _split(line: str, delim: str) -> list[str]:
    return [tok.strip() for tok in line.split(delim)]


def _is_float(tok: str) -> bool:
    try:
        float(tok)
        return True
    except (ValueError, TypeError):
        return False


def _all_float(toks: list[str]) -> bool:
    return len(toks) >= 2 and all(_is_float(t) for t in toks)


def _detect_delimiter(lines: list[str]) -> str:
    """Pick the delimiter that yields the most all-numeric data lines."""
    best, best_score = ",", -1
    for delim in ("\t", ",", ";"):
        score = sum(1 for ln in lines if _all_float(_split(ln, delim)))
        if score > best_score:
            best, best_score = delim, score
    return best


def _sanitize(name: str, used: set[str]) -> str:
    """Turn a channel title into a safe, lowercase header token."""
    clean = re.sub(r"[^0-9a-zA-Z]+", "_", name.strip().lower()).strip("_")
    if not clean:
        clean = "ch"
    candidate = clean
    n = 2
    while candidate in used:
        candidate = f"{clean}_{n}"
        n += 1
    used.add(candidate)
    return candidate


def _find_channel_titles(lines: list[str]) -> list[str] | None:
    """Channel names from an explicit ``ChannelTitle=`` preamble line."""
    for ln in lines:
        if ln.lower().replace(" ", "").startswith("channeltitle="):
            rest = ln.split("=", 1)[1]
            toks = [t.strip() for t in re.split(r"[\t,]", rest) if t.strip()]
            return toks or None
    return None


def _find_interval(lines: list[str]) -> float | None:
    """Sampling interval (seconds) from an ``Interval=`` preamble line."""
    for ln in lines:
        if ln.lower().replace(" ", "").startswith("interval="):
            m = _NUM_RE.search(ln.split("=", 1)[1])
            if m:
                return float(m.group())
    return None


def _find_header_row(
    lines: list[str], delim: str, first_data_idx: int, width: int,
) -> list[str] | None:
    """A bare channel-name header row immediately above the data block.

    Skips LabChart metadata lines (those contain ``=``); stops at the
    first plausible non-numeric, correct-width line.
    """
    for i in range(first_data_idx - 1, -1, -1):
        line = lines[i]
        if "=" in line:
            continue  # metadata preamble line — keep scanning up
        toks = _split(line, delim)
        if len(toks) == width and not _all_float(toks):
            return toks
        return None
    return None


def _col0_strictly_increasing(data: list[list[str]]) -> bool:
    """Is column 0 a monotonic clock? Channels oscillate; a clock does
    not, so strict monotonicity is a reliable time-column signal."""
    if len(data) < 2:
        return False
    vals = [float(r[0]) for r in data]
    return all(b > a for a, b in zip(vals, vals[1:], strict=False))


def normalize_labchart_export(
    src_path: str | Path,
    dst_path: str | Path,
    channel_names: list[str] | None = None,
) -> dict:
    """Normalize one LabChart text export to a clean ``csv_dir`` CSV.

    Returns a summary dict (rows, channels, time_source, delimiter).
    Raises ``ValueError`` when no numeric data block can be found.
    """
    text = Path(src_path).read_text(encoding="utf-8-sig", errors="replace")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        raise ValueError(f"{src_path}: file is empty")

    delim = _detect_delimiter(lines)

    numeric: list[tuple[int, list[str]]] = [
        (i, _split(ln, delim))
        for i, ln in enumerate(lines)
        if _all_float(_split(ln, delim))
    ]
    if not numeric:
        raise ValueError(f"{src_path}: no numeric data block found")

    modal_w = Counter(len(toks) for _, toks in numeric).most_common(1)[0][0]
    data_lines = [(i, toks) for i, toks in numeric if len(toks) == modal_w]
    data = [toks for _, toks in data_lines]
    if len(data) < 2:
        raise ValueError(f"{src_path}: data block too short ({len(data)} rows)")
    first_data_idx = data_lines[0][0]

    has_time = _col0_strictly_increasing(data)
    interval = _find_interval(lines)

    if has_time:
        n_channels = modal_w - 1
        time_tokens = [r[0] for r in data]
        channel_cols = [[r[c] for r in data] for c in range(1, modal_w)]
    else:
        n_channels = modal_w
        if interval is None:
            interval = 1.0  # last resort — row index as the clock
        time_tokens = [f"{i * interval:.6f}" for i in range(len(data))]
        channel_cols = [[r[c] for r in data] for c in range(modal_w)]

    # Resolve channel names: explicit arg > ChannelTitle= > bare header
    # row > synthesized. Drop a leading time label when the count
    # implies one.
    titles = channel_names or _find_channel_titles(lines)
    if titles is None:
        titles = _find_header_row(lines, delim, first_data_idx, modal_w)
    if titles and len(titles) == modal_w and has_time:
        titles = titles[1:]  # the header row included the time column
    if not titles or len(titles) != n_channels:
        titles = [f"ch{i + 1}" for i in range(n_channels)]

    used: set[str] = {"t_s"}
    names = [_sanitize(t, used) for t in titles]

    with open(dst_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["t_s", *names])
        for i in range(len(data)):
            writer.writerow(
                [time_tokens[i], *[channel_cols[c][i] for c in range(n_channels)]]
            )

    return {
        "rows": len(data),
        "channels": names,
        "time_source": "column" if has_time else f"interval={interval}",
        "delimiter": {"\t": "tab", ",": "comma", ";": "semicolon"}[delim],
    }


# ═══════════════════════════════════════════════════════════════════
# Fabricated-input self-test — built tonight, no real LabChart file
# available. Exercises the four export variants the demo plan names.
# ═══════════════════════════════════════════════════════════════════

def _burst_block(
    n_rows: int,
    *,
    with_time: bool,
    interval: float,
    n_bursts: int = 0,
    delim: str = "\t",
) -> list[str]:
    """Build numeric data rows; ``n_bursts`` torque bursts if > 0."""
    rows: list[str] = []
    burst_len = max(1, n_rows // (n_bursts * 3)) if n_bursts else 0
    for i in range(n_rows):
        active = False
        if n_bursts:
            cycle = n_rows // n_bursts
            pos = i % cycle
            active = burst_len <= pos < 2 * burst_len
        torque = 30.0 if active else 2.0
        quad = 50.0 if active else 7.0
        calf = 35.0 if active else 6.0
        cells = [f"{torque:.3f}", f"{quad:.3f}", f"{calf:.3f}"]
        if with_time:
            cells = [f"{i * interval:.4f}", *cells]
        rows.append(delim.join(cells))
    return rows


def _selftest() -> int:
    """Build the fabricated variants, normalize each, assert clean
    output. Returns 0 on success, 1 on any failure."""
    import tempfile

    failures: list[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        status = "PASS" if cond else "FAIL"
        print(f"  [{status}] {name}" + (f" - {detail}" if detail else ""))
        if not cond:
            failures.append(name)

    with tempfile.TemporaryDirectory() as tmp:
        tmpd = Path(tmp)

        # ── V1: full Interval=/ChannelTitle= header, explicit time col ──
        v1 = tmpd / "v1.txt"
        v1.write_text(
            "Interval=\t0.001 s\n"
            "ChannelTitle=\tTorque\tQuad EMG\tCalf EMG\n"
            "Range=\t10 V\t10 V\t10 V\n"
            + "\n".join(_burst_block(40, with_time=True, interval=0.001))
            + "\n",
            encoding="utf-8",
        )
        out1 = tmpd / "v1.csv"
        info1 = normalize_labchart_export(v1, out1)
        h1, rows1 = _read(out1)
        check(
            "V1 full header + time column",
            h1 == ["t_s", "torque", "quad_emg", "calf_emg"]
            and len(rows1) == 40 and info1["time_source"] == "column",
            f"header={h1} rows={len(rows1)}",
        )

        # ── V2: comment-interrupted data block ──
        v2_data = _burst_block(40, with_time=True, interval=0.002)
        v2_lines = (
            ["Interval=\t0.002 s", "ChannelTitle=\tTorque\tQuad EMG\tCalf EMG"]
            + v2_data[:18]
            + ["#* subject shifted in the chair", "Comment\trep boundary"]
            + v2_data[18:]
        )
        v2 = tmpd / "v2.txt"
        v2.write_text("\n".join(v2_lines) + "\n", encoding="utf-8")
        out2 = tmpd / "v2.csv"
        normalize_labchart_export(v2, out2)
        _h2, rows2 = _read(out2)
        check(
            "V2 comment-interrupted data block",
            len(rows2) == 40,
            f"kept {len(rows2)}/40 data rows, comments dropped",
        )

        # ── V3: interval-implied time (no time column in the data) ──
        v3 = tmpd / "v3.txt"
        v3.write_text(
            "Interval=\t0.004 s\n"
            "ChannelTitle=\tTorque\tQuad EMG\tCalf EMG\n"
            + "\n".join(_burst_block(25, with_time=False, interval=0.004))
            + "\n",
            encoding="utf-8",
        )
        out3 = tmpd / "v3.csv"
        info3 = normalize_labchart_export(v3, out3)
        h3, rows3 = _read(out3)
        synth_ok = (
            abs(float(rows3[0][0]) - 0.0) < 1e-9
            and abs(float(rows3[2][0]) - 0.008) < 1e-9
        )
        check(
            "V3 interval-implied time synthesized",
            h3[0] == "t_s" and synth_ok and "interval" in info3["time_source"],
            f"t_s[0..2]={[r[0] for r in rows3[:3]]}",
        )

        # ── V4: minimal header (bare channel names, time column) ──
        v4 = tmpd / "v4.txt"
        v4.write_text(
            "time\ttorque\tquad\tcalf\n"
            + "\n".join(_burst_block(30, with_time=True, interval=0.01))
            + "\n",
            encoding="utf-8",
        )
        out4 = tmpd / "v4.csv"
        normalize_labchart_export(v4, out4)
        h4, rows4 = _read(out4)
        check(
            "V4 minimal header (bare channel names)",
            h4 == ["t_s", "torque", "quad", "calf"] and len(rows4) == 30,
            f"header={h4}",
        )

        # ── V5: end-to-end — normalize a realistic recording, then run
        #        csv_synchronized_windows on the cleaned output ──
        v5 = tmpd / "v5.txt"
        v5.write_text(
            "Interval=\t0.01 s\n"
            "ChannelTitle=\tTorque\tQuad EMG\tCalf EMG\n"
            "Range=\t10 V\t10 V\t10 V\n"
            + "\n".join(
                _burst_block(600, with_time=True, interval=0.01, n_bursts=3)
            )
            + "\n",
            encoding="utf-8",
        )
        clean_dir = tmpd / "clean"
        clean_dir.mkdir()
        normalize_labchart_export(v5, clean_dir / "S001.csv")
        epochs = _run_tool(clean_dir)
        check(
            "V5 end-to-end: normalized file runs through the tool",
            epochs == 3,
            f"csv_synchronized_windows detected {epochs} epochs (expected 3)",
        )

    print()
    if failures:
        print(f"SELF-TEST FAILED: {len(failures)} failure(s) — {failures}")
        return 1
    print("SELF-TEST PASSED: all 5 fabricated-input checks clean")
    return 0


def _read(path: Path) -> tuple[list[str], list[list[str]]]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        rows = list(reader)
    return header, rows


def _run_tool(csv_dir: Path) -> int:
    """Drive csv_synchronized_windows over a normalized CSV directory;
    return the epoch count for the single recording."""
    import asyncio
    import json
    import tempfile

    from tailor.children.csv_dir import CSVDirectoryChild

    with tempfile.TemporaryDirectory() as tmp:
        cfg = Path(tmp) / "config"
        dat = Path(tmp) / "data"
        cfg.mkdir()
        dat.mkdir()
        (cfg / "user_config.json").write_text(json.dumps({
            "csv_dir": {
                "path": str(csv_dir),
                "timestamp_column": "t_s",
                "value_columns": {
                    "torque": "Torque",
                    "quad_emg": "Quad EMG",
                    "calf_emg": "Calf EMG",
                },
            },
        }), encoding="utf-8")
        child = CSVDirectoryChild(cfg, dat)
        result = asyncio.run(child.execute(
            "csv_synchronized_windows", {"file_id": "S001.csv"},
        ))
        if "error" in result:
            raise AssertionError(f"tool errored: {result['error']}")
        return result["epoch_count"]


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("--selftest", "-t"):
        print("labchart_to_csv - fabricated-input self-test\n")
        return _selftest()
    if argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    src = argv[0]
    dst = argv[1] if len(argv) > 1 else str(Path(src).with_suffix(".csv"))
    info = normalize_labchart_export(src, dst)
    print(f"Normalized {src} -> {dst}")
    print(f"  rows={info['rows']}  channels={info['channels']}")
    print(f"  delimiter={info['delimiter']}  time={info['time_source']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
