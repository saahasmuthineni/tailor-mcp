#!/usr/bin/env python3
"""
render_receipt.py — deterministic, stdlib-only SVG receipt for the
token-efficiency benchmark.

Takes the JSON emitted by ``benchmarks/token_efficiency.py`` and renders
a terminal-styled panel of the three headline scenarios (token counts +
reduction ratios) to ``docs/assets/benchmark-receipt.svg``.

The point of a *receipt* (over a recorded GIF) is that it cannot drift
silently: the numbers it shows are the benchmark's own output, and a
pytest freshness guard (``tests/test_benchmark_receipt.py``) re-runs the
measurement and asserts the checked-in SVG still matches. If a fixture
change moves a ratio, CI fails until the receipt is re-rendered.

Usage::

    python benchmarks/token_efficiency.py | python benchmarks/render_receipt.py
    python benchmarks/render_receipt.py --in results.json --out path.svg

The rendered numbers also live in a machine-readable
``<!-- benchmark-receipt-data: {...} -->`` comment so the guard can
extract exact values without HTML-parsing the visible text.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from xml.sax.saxutils import escape

# Visual language matched to the existing hand-built SVGs
# (docs/assets/footprint.svg, vault-insights.svg): dark panel, card
# rows with accent top-bars, the same palette + fonts.
_BG = "#0f1117"
_CARD = "#1a1f2e"
_CARD_STROKE = "#2d3748"
_CODE_BG = "#0d1117"
_TITLE = "#e2e8f0"
_BODY = "#94a3b8"
_MUTED = "#64748b"
_GREEN = "#22c55e"
_ACCENTS = ("#f97316", "#60a5fa", "#22c55e")  # orange / blue / green
_SANS = "-apple-system,Segoe UI,system-ui,sans-serif"
_MONO = "SF Mono,Fira Code,Consolas,monospace"

_WIDTH = 720
_HEIGHT = 360  # 2:1 — sane as a repo social-preview / launch-post card

# Scenario keys in the benchmark JSON → human label for the card.
_PER_QUERY_LABELS = {
    "single_subject_S004_fatigue": "SINGLE SUBJECT",
    "cohort_16_subjects_by_sex": "16-SUBJECT COHORT",
}
_SESSION_LABEL = "5-SESSION THREAD"


def _fmt_int(n: int) -> str:
    return f"{int(n):,}"


def build_receipt_data(benchmark: dict) -> dict:
    """Reduce the full benchmark JSON to the three values the receipt
    renders. Deterministic; order is fixed (single, cohort, session)."""
    by_scenario = {
        q["scenario"]: q for q in benchmark.get("per_query_efficiency", [])
    }
    cards: list[dict] = []

    for key, label in _PER_QUERY_LABELS.items():
        q = by_scenario.get(key)
        if q is None:
            raise ValueError(
                f"Required scenario {key!r} missing from benchmark data — "
                "is the input the JSON emitted by token_efficiency.py?"
            )
        cards.append(
            {
                "label": label,
                "question": q["question"],
                "baseline_tokens": int(q["baseline"]["tiktoken_cl100k_base"]),
                "tailor_tokens": int(q["tailor"]["tiktoken_cl100k_base"]),
                "ratio": round(float(q["ratio"]["tiktoken"]), 1),
            }
        )

    sessions = benchmark.get("session_persistence_efficiency")
    if not sessions:
        raise ValueError(
            "Missing or empty 'session_persistence_efficiency' in "
            "benchmark data — is the input the JSON emitted by "
            "token_efficiency.py?"
        )
    session = sessions[0]
    cards.append(
        {
            "label": _SESSION_LABEL,
            "question": session["question"],
            "baseline_tokens": int(session["baseline"]["tiktoken_cl100k_base"]),
            "tailor_tokens": int(session["tailor"]["tiktoken_cl100k_base"]),
            "ratio": round(float(session["ratio"]["tiktoken"]), 1),
        }
    )

    return {
        "tokenizer": benchmark.get("tokenizer_primary", "tiktoken cl100k_base"),
        "cards": cards,
    }


def extract_receipt_data(svg_text: str) -> dict:
    """Pull the embedded machine-readable block back out of a rendered
    SVG. Inverse of the comment written by :func:`render_svg`."""
    marker = "<!-- benchmark-receipt-data: "
    start = svg_text.index(marker) + len(marker)
    end = svg_text.index(" -->", start)
    return json.loads(svg_text[start:end])


def _text(x, y, s, *, fill, size, family=_SANS, weight=None,
          anchor="start", spacing=None) -> str:
    attrs = [
        f'fill="{fill}"',
        f'font-family="{family}"',
        f'font-size="{size}"',
        f'x="{x}"',
        f'y="{y}"',
        f'text-anchor="{anchor}"',
    ]
    if weight is not None:
        attrs.append(f'font-weight="{weight}"')
    if spacing is not None:
        attrs.append(f'letter-spacing="{spacing}"')
    return f"  <text {' '.join(attrs)}>{escape(str(s))}</text>"


def render_svg(data: dict) -> str:
    cards = data["cards"]
    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{_WIDTH}" '
        f'height="{_HEIGHT}" viewBox="0 0 {_WIDTH} {_HEIGHT}">'
    )
    # Machine-readable receipt data — the freshness guard parses this.
    parts.append(
        "  <!-- benchmark-receipt-data: "
        + json.dumps(data, separators=(",", ":"), sort_keys=True)
        + " -->"
    )
    # Background.
    parts.append(
        f'  <rect fill="{_BG}" x="0" y="0" width="{_WIDTH}" '
        f'height="{_HEIGHT}" rx="8" ry="8"/>'
    )
    # Title + subtitle.
    parts.append(
        _text(_WIDTH // 2, 34, "Token efficiency — measured, not claimed",
              fill=_TITLE, size=15, weight=600, anchor="middle")
    )
    parts.append(
        _text(_WIDTH // 2, 54,
              "Raw data to Claude vs. the same answer through Tailor's "
              "Tier-1 computed reports.",
              fill=_BODY, size=11, anchor="middle")
    )

    # Three cards.
    card_w = 224
    gap = 16
    x0 = (_WIDTH - (3 * card_w + 2 * gap)) // 2
    card_y = 80
    card_h = 198
    for i, card in enumerate(cards):
        cx = x0 + i * (card_w + gap)
        accent = _ACCENTS[i % len(_ACCENTS)]
        center = cx + card_w // 2
        parts.append(
            f'  <rect fill="{_CARD}" stroke="{_CARD_STROKE}" '
            f'stroke-width="1" x="{cx}" y="{card_y}" width="{card_w}" '
            f'height="{card_h}" rx="10" ry="10"/>'
        )
        parts.append(
            f'  <rect fill="{accent}" x="{cx}" y="{card_y}" '
            f'width="{card_w}" height="3" rx="2" ry="2"/>'
        )
        parts.append(
            _text(center, card_y + 26, card["label"], fill=_MUTED,
                  size=9, weight=700, anchor="middle", spacing=1)
        )
        parts.append(
            f'  <line stroke="{_CARD_STROKE}" stroke-width="1" '
            f'x1="{cx + 16}" y1="{card_y + 33}" x2="{cx + card_w - 16}" '
            f'y2="{card_y + 33}"/>'
        )
        # Raw → Tailor token rows.
        parts.append(
            _text(cx + 16, card_y + 58, "Raw to Claude", fill=_BODY, size=10)
        )
        parts.append(
            _text(cx + card_w - 16, card_y + 58,
                  f'{_fmt_int(card["baseline_tokens"])} tok', fill=_TITLE,
                  size=10, family=_MONO, anchor="end")
        )
        parts.append(
            _text(cx + 16, card_y + 78, "Through Tailor", fill=_BODY, size=10)
        )
        parts.append(
            _text(cx + card_w - 16, card_y + 78,
                  f'{_fmt_int(card["tailor_tokens"])} tok', fill=_GREEN,
                  size=10, family=_MONO, anchor="end")
        )
        # Big ratio.
        ratio_label = f'{card["ratio"]:.1f}×'
        parts.append(
            f'  <rect fill="{_CODE_BG}" x="{cx + 16}" y="{card_y + 92}" '
            f'width="{card_w - 32}" height="60" rx="6" ry="6"/>'
        )
        parts.append(
            _text(center, card_y + 132, ratio_label, fill=accent, size=32,
                  family=_MONO, weight=700, anchor="middle")
        )
        parts.append(
            _text(center, card_y + 172, "fewer tokens, identical answer",
                  fill=_MUTED, size=9, anchor="middle")
        )

    # Footer: reproduce block.
    footer_y = card_y + card_h + 32
    parts.append(
        f'  <rect fill="{_CODE_BG}" x="{x0}" y="{footer_y - 20}" '
        f'width="{3 * card_w + 2 * gap}" height="30" rx="6" ry="6"/>'
    )
    parts.append(
        _text(x0 + 12, footer_y, "$", fill=_GREEN, size=10, family=_MONO)
    )
    parts.append(
        _text(x0 + 26, footer_y,
              "pip install tiktoken && python benchmarks/token_efficiency.py "
              "| python benchmarks/render_receipt.py",
              fill=_TITLE, size=10, family=_MONO)
    )
    parts.append(
        _text(x0 + 3 * card_w + 2 * gap - 4, footer_y, data["tokenizer"],
              fill=_MUTED, size=9, family=_MONO, anchor="end")
    )

    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--in", dest="in_path", default="-",
        help="benchmark JSON path, or '-' for stdin (default: stdin)",
    )
    ap.add_argument(
        "--out", dest="out_path",
        default=str(Path(__file__).resolve().parent.parent
                    / "docs" / "assets" / "benchmark-receipt.svg"),
        help="output SVG path (default: docs/assets/benchmark-receipt.svg)",
    )
    args = ap.parse_args(argv)

    if args.in_path == "-":
        benchmark = json.load(sys.stdin)
    else:
        benchmark = json.loads(Path(args.in_path).read_text(encoding="utf-8"))

    data = build_receipt_data(benchmark)
    svg = render_svg(data)
    out = Path(args.out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(svg, encoding="utf-8")
    print(f"wrote {out} ({len(svg)} bytes)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
