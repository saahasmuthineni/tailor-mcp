"""
Vault Parser — Pure Markdown + Frontmatter + Wikilink Parsing
=============================================================
Stateless, I/O-free parsing helpers used by the rescan pipeline
and by VaultLayer to resolve wikilinks when rendering responses.

All functions work on strings; no filesystem, no database.
"""

import re
from typing import Optional


# ── Regexes ──────────────────────────────────────────────────────

# [[target]] or [[target|display]]
_WIKILINK_RE = re.compile(r"\[\[([^\[\]\|]+?)(?:\|([^\[\]]+?))?\]\]")

# #tag — allow slashes (Obsidian nested tags), must start with a letter
_TAG_RE = re.compile(r"(?<![\w`])#([A-Za-z][A-Za-z0-9_\-/]*)")

# Fenced code block delimiter (``` or ~~~)
_FENCE_RE = re.compile(r"^(```|~~~)")

# Inline code span (single or double backticks) — used to strip before tag scan
_INLINE_CODE_RE = re.compile(r"`[^`\n]*`")


# ── Frontmatter ───────────────────────────────────────────────────

def split_frontmatter(content: str) -> tuple[dict, str]:
    """
    Split a markdown file into (frontmatter_dict, body_str).

    Frontmatter is a YAML block delimited by ``---`` on the very first
    line and a matching ``---`` line somewhere below.  No PyYAML
    dependency — we only handle the scalar/flow-list forms that
    ``renderer.py`` actually emits.

    Returns ({}, content) if no frontmatter is present.
    """
    if not content.startswith("---"):
        return {}, content

    # Find the closing ---
    end = content.find("\n---", 3)
    if end == -1:
        return {}, content

    fm_block = content[4:end]
    # Body is everything after the closing --- (strip one leading newline)
    body = content[end + 4 :]
    if body.startswith("\n"):
        body = body[1:]

    fm = _parse_frontmatter_block(fm_block)
    return fm, body


def _parse_frontmatter_block(block: str) -> dict:
    """
    Parse a YAML frontmatter block into a flat dict.

    Supports:
        key: scalar      → str / int / float / bool
        key: [a, b, c]   → list of strings (flow sequence)
        key:             → list of strings from subsequent "  - item" lines
          - item1
          - item2
    """
    result: dict = {}
    lines = block.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue
        if ":" not in stripped:
            i += 1
            continue

        key, _, value = stripped.partition(":")
        key = key.strip()
        value = value.strip()

        # Block sequence: key: followed by "  - item" lines
        if value == "":
            items: list = []
            j = i + 1
            while j < len(lines):
                sub = lines[j]
                s = sub.lstrip()
                if s.startswith("- "):
                    items.append(_coerce_scalar(s[2:].strip()))
                    j += 1
                    continue
                if sub.strip() == "":
                    j += 1
                    continue
                break
            result[key] = items
            i = j
            continue

        # Flow sequence: key: [a, b, c]
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            if not inner:
                result[key] = []
            else:
                result[key] = [_coerce_scalar(s.strip()) for s in inner.split(",")]
            i += 1
            continue

        # Scalar
        result[key] = _coerce_scalar(value)
        i += 1

    return result


def _coerce_scalar(value: str):
    """Strip quotes and coerce to bool/int/float when unambiguous."""
    v = value.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
        return v[1:-1]
    if v == "true":
        return True
    if v == "false":
        return False
    if v in ("null", "~", ""):
        return ""
    try:
        if v.lstrip("-").isdigit():
            return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        return v


# ── Wikilinks ────────────────────────────────────────────────────

def extract_wikilinks(body: str) -> list[tuple[str, str]]:
    """
    Return a list of (target, display) pairs found in the body.

    ``[[foo]]``              → ("foo", "foo")
    ``[[foo|Nice Foo]]``     → ("foo", "Nice Foo")

    Links inside fenced code blocks are ignored.
    """
    out: list[tuple[str, str]] = []
    for line in _strip_fenced_code(body):
        for m in _WIKILINK_RE.finditer(line):
            target = m.group(1).strip()
            display = (m.group(2) or target).strip()
            if target:
                out.append((target, display))
    return out


# ── Tags ─────────────────────────────────────────────────────────

def extract_tags(body: str) -> list[str]:
    """
    Return a list of ``#tag`` strings (without the ``#``) found in the body.

    - Skips tags inside fenced code blocks (``` or ~~~).
    - Skips inline ``code`` spans.
    - Excludes numeric-only suffixes (e.g. "#123" is not a tag).

    Returned list preserves order and includes duplicates.  Callers
    that need a set should dedupe themselves.
    """
    out: list[str] = []
    for line in _strip_fenced_code(body):
        # Drop inline code spans before scanning for tags
        scan = _INLINE_CODE_RE.sub("", line)
        for m in _TAG_RE.finditer(scan):
            out.append(m.group(1))
    return out


def _strip_fenced_code(body: str) -> list[str]:
    """Yield lines with fenced code blocks removed."""
    result: list[str] = []
    in_fence = False
    for line in body.splitlines():
        if _FENCE_RE.match(line.lstrip()):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        result.append(line)
    return result


# ── Link resolution ──────────────────────────────────────────────

def resolve_link(target: str, known_filenames: set[str]) -> Optional[str]:
    """
    Resolve a wikilink ``target`` to a vault filename.

    Matches by stem (filename without ``.md``), case-insensitive.
    Handles the render pattern ``YYYY-MM-DD-activity-<id>`` used by
    ``renderer.py``.  Returns the canonical filename from
    ``known_filenames`` if found, else None.
    """
    if not target:
        return None
    t = target.strip()
    t_lower = t.lower()

    # Build a stem → filename lookup (last-write-wins for duplicate stems)
    lookup: dict[str, str] = {}
    for fn in known_filenames:
        stem = fn.rsplit("/", 1)[-1]
        if stem.endswith(".md"):
            stem = stem[:-3]
        lookup[stem.lower()] = fn

    # Direct stem match
    if t_lower in lookup:
        return lookup[t_lower]

    # Match with .md stripped from target
    if t_lower.endswith(".md") and t_lower[:-3] in lookup:
        return lookup[t_lower[:-3]]

    # Match by suffix (e.g. "activity-12345" matches "2025-04-10-activity-12345")
    for stem_lower, fn in lookup.items():
        if stem_lower.endswith("-" + t_lower) or stem_lower == t_lower:
            return fn

    return None
