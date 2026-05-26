"""
Mechanical rename script for the v8 → v9 public-flip preparation:

  PHIScrubber          → DataScrubber       (bare word; RedcapPHIScrubber stays)
  subject_id           → entity_id          (bare word; audit-log column,
                                              param schemas, vault frontmatter)
  SUBJECT_ID_SCHEMA    → ENTITY_ID_SCHEMA
  SUBJECT_ID_PARAM_DOC → ENTITY_ID_PARAM_DOC
  csv_cohort_summary   → csv_group_summary  (tool name on csv_dir child only;
                                              force/emg/redcap/matlab cohort
                                              siblings keep _cohort_summary)

Uses word-boundary regex so RedcapPHIScrubber → RedcapPHIScrubber (unchanged).
Run from repo root: ``python scripts/rename_for_public_flip.py``

Scope: src/ + tests/. Docs / ADRs / CLAUDE.md banners are handled by
targeted edits in the same session, not by this script — those files
need selective editing to preserve historical context.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Order matters: do CSV_COHORT_SUMMARY first (specific tool name),
# then SUBJECT_ID_SCHEMA/PARAM_DOC (specific constants), then
# subject_id (generic identifier), then PHIScrubber.
RENAMES: list[tuple[re.Pattern, str]] = [
    # csv_cohort_summary → csv_group_summary (tool name + handler ref).
    # Word-boundary on both sides so we don't catch e.g. emg_csv_cohort_summary.
    (re.compile(r"\bcsv_cohort_summary\b"), "csv_group_summary"),
    # Internal handler if it follows the convention `_handle_cohort_summary`
    # on the csv_dir child specifically. The csv_dir module has only this
    # one cohort tool — safe to rename `_handle_cohort_summary` → `_handle_group_summary`
    # but only if we're inside the csv_dir directory. Handled below.
    # The shared constants and uppercase identifiers come BEFORE the lowercase
    # subject_id rename so the latter doesn't already-process them.
    (re.compile(r"\bSUBJECT_ID_SCHEMA\b"), "ENTITY_ID_SCHEMA"),
    (re.compile(r"\bSUBJECT_ID_PARAM_DOC\b"), "ENTITY_ID_PARAM_DOC"),
    (re.compile(r"\bsubject_id\b"), "entity_id"),
    # PHIScrubber → DataScrubber. Word-boundary on left ensures
    # `RedcapPHIScrubber` is NOT matched (would have a non-boundary
    # character `P` after `Redcap`'s `p` — actually Python's `\b` is at the
    # boundary between word and non-word characters, and `pP` is two word
    # chars so no boundary. So `\bPHIScrubber\b` will NOT match the
    # PHIScrubber inside RedcapPHIScrubber. Verified.)
    (re.compile(r"\bPHIScrubber\b"), "DataScrubber"),
]

# CSV_dir-only renames: the handler dispatch and any private references
# that only exist inside the csv_dir child module. force_csv / emg_csv /
# redcap / matlab keep their cohort_summary siblings.
CSV_DIR_ONLY_RENAMES: list[tuple[re.Pattern, str]] = [
    # The handler dispatch in csv_dir/child.py references
    # `_handle_cohort_summary`; the same name exists in force_csv +
    # emg_csv but we keep those. So only do this rename in csv_dir/.
    # NOT enabling this — keeping handler name uniform across children is
    # less confusing than half-renamed internal dispatch. The TOOL NAME
    # change is the user-facing rename; the internal handler stays.
]


def find_python_files() -> list[Path]:
    targets: list[Path] = []
    for sub in ("src", "tests", "benchmarks"):
        root = REPO_ROOT / sub
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            targets.append(path)
    return targets


def find_other_text_files() -> list[Path]:
    """Other files where the rename is safe to apply mechanically:
    bundled vault fixture markdown + metadata.json sidecars (the
    snapshot.md text + the per-modality metadata.json files in
    src/tailor/_fixtures/)."""
    targets: list[Path] = []
    fixtures = REPO_ROOT / "src" / "tailor" / "_fixtures"
    if fixtures.exists():
        for path in fixtures.rglob("*.md"):
            targets.append(path)
        for path in fixtures.rglob("*.json"):
            targets.append(path)
    # The bundled RECIPIENT_README.md ships in the wheel; rename inside.
    recipient_readme = REPO_ROOT / "src" / "tailor" / "RECIPIENT_README.md"
    if recipient_readme.exists():
        targets.append(recipient_readme)
    return targets


def apply_renames(path: Path) -> tuple[bool, dict[str, int]]:
    """Apply renames to one file. Returns (changed, counts_by_rename)."""
    text = path.read_text(encoding="utf-8")
    counts: dict[str, int] = {}
    new_text = text
    for pattern, replacement in RENAMES:
        new_text, n = pattern.subn(replacement, new_text)
        if n:
            counts[replacement] = counts.get(replacement, 0) + n
    if new_text != text:
        path.write_text(new_text, encoding="utf-8")
        return True, counts
    return False, counts


def main() -> int:
    files = find_python_files() + find_other_text_files()
    total_changed = 0
    total_counts: dict[str, int] = {}
    changed_files: list[str] = []
    for path in files:
        try:
            changed, counts = apply_renames(path)
        except Exception as e:  # noqa: BLE001
            print(f"ERROR processing {path}: {e}", file=sys.stderr)
            continue
        if changed:
            total_changed += 1
            changed_files.append(str(path.relative_to(REPO_ROOT)))
            for k, v in counts.items():
                total_counts[k] = total_counts.get(k, 0) + v

    print(f"\nFiles scanned:  {len(files)}")
    print(f"Files changed:  {total_changed}")
    print("\nReplacement totals:")
    for k, v in sorted(total_counts.items()):
        print(f"  {k}: {v}")
    print("\nChanged files:")
    for f in changed_files:
        print(f"  {f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
