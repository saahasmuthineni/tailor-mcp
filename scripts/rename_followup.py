"""
Follow-up rename pass — handles cases the v1 word-boundary script
intentionally skipped:

  SUBJECT_ID_PATTERN                  → ENTITY_ID_PATTERN
  TestSubjectIdConsistency / class    → TestEntityIdConsistency
  test_*_subject_id_*                 → test_*_entity_id_*  (function names)
  prose references in _personas.json  → entity_id / DataScrubber

Run from repo root: python scripts/rename_followup.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Order matters: do uppercase tokens first, then mixed-case identifiers,
# then the relaxed-boundary subject_id pass (matches inside Python
# identifiers like `_subject_id_audit`).
RENAMES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"SUBJECT_ID_PATTERN"), "ENTITY_ID_PATTERN"),
    (re.compile(r"SubjectIdConsistency"), "EntityIdConsistency"),
    (re.compile(r"SubjectId\b"), "EntityId"),
    # Relaxed: match subject_id even when surrounded by underscores
    # (function/class names like _handle_subject_id_query).
    (re.compile(r"subject_id"), "entity_id"),
]


def targets() -> list[Path]:
    out: list[Path] = []
    for sub in ("src", "tests", "benchmarks"):
        root = REPO_ROOT / sub
        if not root.exists():
            continue
        out.extend(root.rglob("*.py"))
    fixtures = REPO_ROOT / "src" / "tailor" / "_fixtures"
    if fixtures.exists():
        out.extend(fixtures.rglob("*.md"))
        out.extend(fixtures.rglob("*.json"))
    personas = REPO_ROOT / "src" / "tailor" / "demo" / "_personas.json"
    if personas.exists():
        out.append(personas)
    return out


def apply(path: Path) -> dict[str, int]:
    text = path.read_text(encoding="utf-8")
    counts: dict[str, int] = {}
    new_text = text
    for pat, repl in RENAMES:
        new_text, n = pat.subn(repl, new_text)
        if n:
            counts[repl] = counts.get(repl, 0) + n
    if new_text != text:
        # Preserve files we're INTENTIONALLY keeping subject_id in:
        # the audit-log migration block and the vault parser
        # backward-compat block. Skip those two files entirely.
        rel = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
        if rel in ("src/tailor/framework/audit.py",
                   "src/tailor/framework/vault/parser.py"):
            return {}
        path.write_text(new_text, encoding="utf-8")
    return counts


def main() -> int:
    files = targets()
    total: dict[str, int] = {}
    changed = 0
    for p in files:
        try:
            counts = apply(p)
        except Exception as e:  # noqa: BLE001
            print(f"ERROR processing {p}: {e}", file=sys.stderr)
            continue
        if counts:
            changed += 1
            for k, v in counts.items():
                total[k] = total.get(k, 0) + v
    print(f"Files scanned: {len(files)}; changed: {changed}")
    for k, v in sorted(total.items()):
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
