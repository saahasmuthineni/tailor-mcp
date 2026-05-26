"""
Doc-sweep rename pass — v9.0.0 public-flip preparation, commit 3.

Applies word-boundary regex replacements to current-state documentation
while preserving historical sections (CLAUDE.md banners, ROADMAP
"Shipped" section, CHANGELOG.md entries describing past versions, and
docs/reports/* historical reports).

Targets (per boss instruction 2026-05-26):
- README.md                                              (full sweep)
- CLAUDE.md                                              (current-state only — sweep starts after the first occurrence of "## What This Project Is")
- ROADMAP.md                                             (current-state only — sweep stops at the first occurrence of "## Shipped (chronological)")
- docs/adr/0002, 0003, 0009, 0015                        (full sweep; amendment notes added separately)
- docs/guides/*.md (excluding demo.tape, .ipynb)         (full sweep)
- docs/design/tailor-vocabulary.md                       (full sweep; new entries added separately)

Skip entirely:
- CHANGELOG.md
- docs/reports/*
- All other ADRs (preserve their as-written voice)
- Project memory files under .claude/

Renames applied (same word-boundary patterns as the source-code sweep):
  PHIScrubber          -> DataScrubber
  subject_id           -> entity_id
  SUBJECT_ID_SCHEMA    -> ENTITY_ID_SCHEMA
  SUBJECT_ID_PARAM_DOC -> ENTITY_ID_PARAM_DOC
  csv_cohort_summary   -> csv_group_summary

Run: python scripts/rename_docs_sweep.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Order matters: specific tool name + specific identifiers before the
# bare subject_id pass.
RENAMES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bcsv_cohort_summary\b"), "csv_group_summary"),
    (re.compile(r"\bSUBJECT_ID_SCHEMA\b"), "ENTITY_ID_SCHEMA"),
    (re.compile(r"\bSUBJECT_ID_PARAM_DOC\b"), "ENTITY_ID_PARAM_DOC"),
    (re.compile(r"\bsubject_id\b"), "entity_id"),
    (re.compile(r"\bPHIScrubber\b"), "DataScrubber"),
]


def apply_renames(text: str) -> tuple[str, dict[str, int]]:
    counts: dict[str, int] = {}
    new = text
    for pat, repl in RENAMES:
        new, n = pat.subn(repl, new)
        if n:
            counts[repl] = counts.get(repl, 0) + n
    return new, counts


def sweep_full(path: Path) -> dict[str, int]:
    text = path.read_text(encoding="utf-8")
    new, counts = apply_renames(text)
    if new != text:
        path.write_text(new, encoding="utf-8")
    return counts


def sweep_after_marker(path: Path, marker: str) -> dict[str, int]:
    """Apply renames only to content AFTER the first occurrence of marker.
    Used for CLAUDE.md where the banner section before the marker is
    historical and must not be touched."""
    text = path.read_text(encoding="utf-8")
    idx = text.find(marker)
    if idx == -1:
        # If the marker isn't there, refuse to sweep — the file structure
        # doesn't match our assumptions and we'd risk modifying history.
        print(f"  WARN: marker {marker!r} not found in {path}; skipping",
              file=sys.stderr)
        return {}
    head, tail = text[:idx], text[idx:]
    new_tail, counts = apply_renames(tail)
    if new_tail != tail:
        path.write_text(head + new_tail, encoding="utf-8")
    return counts


def sweep_before_marker(path: Path, marker: str) -> dict[str, int]:
    """Apply renames only to content BEFORE the first occurrence of marker.
    Used for ROADMAP.md where the Shipped section after the marker
    describes past releases and must not be touched."""
    text = path.read_text(encoding="utf-8")
    idx = text.find(marker)
    if idx == -1:
        print(f"  WARN: marker {marker!r} not found in {path}; skipping",
              file=sys.stderr)
        return {}
    head, tail = text[:idx], text[idx:]
    new_head, counts = apply_renames(head)
    if new_head != head:
        path.write_text(new_head + tail, encoding="utf-8")
    return counts


def main() -> int:
    targets: list[tuple[Path, str, str | None]] = [
        # (path, mode, marker)
        (REPO_ROOT / "README.md", "full", None),
        (REPO_ROOT / "README_PYPI.md", "full", None),
        (REPO_ROOT / "CLAUDE.md", "after", "## What This Project Is"),
        (REPO_ROOT / "ROADMAP.md", "before", "## Shipped (chronological)"),
        # ADRs in scope
        (REPO_ROOT / "docs/adr/0002-subject-id-scoping.md", "full", None),
        (REPO_ROOT / "docs/adr/0003-phi-scrubber-seam.md", "full", None),
        (REPO_ROOT / "docs/adr/0009-vault-subject-keying.md", "full", None),
        (REPO_ROOT / "docs/adr/0015-tier-1-cohort-surface-and-metadata-sidecar.md",
         "full", None),
        # Guides — full sweep
        (REPO_ROOT / "docs/guides/build-your-own-child.md", "full", None),
        (REPO_ROOT / "docs/guides/claude-desktop-demo.md", "full", None),
        (REPO_ROOT / "docs/guides/local-llm-guardian.md", "full", None),
        (REPO_ROOT / "docs/guides/multi-subject-pilot.md", "full", None),
        (REPO_ROOT / "docs/guides/share-the-demo.md", "full", None),
        # Vocabulary doc (new entries appended separately)
        (REPO_ROOT / "docs/design/tailor-vocabulary.md", "full", None),
    ]

    total: dict[str, int] = {}
    changed_files: list[str] = []
    for path, mode, marker in targets:
        if not path.exists():
            print(f"  SKIP: {path} (not present)")
            continue
        try:
            if mode == "full":
                counts = sweep_full(path)
            elif mode == "after":
                assert marker is not None
                counts = sweep_after_marker(path, marker)
            elif mode == "before":
                assert marker is not None
                counts = sweep_before_marker(path, marker)
            else:
                print(f"  ERR: unknown mode {mode} for {path}", file=sys.stderr)
                continue
        except Exception as e:  # noqa: BLE001
            print(f"  ERR: {path}: {e}", file=sys.stderr)
            continue
        if counts:
            changed_files.append(str(path.relative_to(REPO_ROOT)))
            for k, v in counts.items():
                total[k] = total.get(k, 0) + v

    print(f"\nFiles scanned: {len(targets)}; changed: {len(changed_files)}")
    print("\nReplacement totals:")
    for k, v in sorted(total.items()):
        print(f"  {k}: {v}")
    print("\nChanged files:")
    for f in changed_files:
        print(f"  {f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
