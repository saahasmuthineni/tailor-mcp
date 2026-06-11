"""
Developer/RSE entry point for the walkthrough library module:

    python -m tailor.demo
    python -m tailor.demo --save-shareable transcript.md
    python -m tailor.demo --save-shareable transcript.md --audience=public

The ``tailor walkthrough`` CLI verb was hard-removed in v8.0.0 per
ADR 0040 — the recipient path is the ``tailor_walkthrough_section``
MCP tool driven from Claude Desktop chat. This module-level runner is
the terminal path for developers, RSEs, and shareable-transcript
readers reproducing the walkthrough without Claude in the loop. It is
not a ``tailor`` CLI verb and does not amend the ADR 0040 / ADR 0043
seven-command surface contract.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .runner import run_demo


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m tailor.demo",
        description=(
            "Researcher first-look: five-section walkthrough of the "
            "framework's load-bearing claims against bundled demo "
            "cohort fixtures (ADR 0027). No Strava account, OAuth, or "
            "network access required."
        ),
    )
    from tailor import __version__

    default_shareable = (
        Path.home() / ".tailor" / f"shareable-walkthrough-v{__version__}.md"
    )
    parser.add_argument(
        "--save-shareable",
        metavar="PATH",
        nargs="?",
        default=None,
        const=str(default_shareable),
        help=(
            "also capture the walkthrough transcript into a "
            "self-contained shareable markdown file (default when no "
            f"PATH given: {default_shareable})"
        ),
    )
    parser.add_argument(
        "--audience",
        choices=["developer", "public"],
        default="developer",
        help=(
            "shareable-transcript register (per ADR 0030); only "
            "meaningful with --save-shareable"
        ),
    )
    args = parser.parse_args(argv)

    run_demo(
        save_shareable_path=(
            Path(args.save_shareable) if args.save_shareable else None
        ),
        audience=args.audience,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
