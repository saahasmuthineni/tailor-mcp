"""
Vault Rescan — Bidirectional Sync via Filesystem mtime
======================================================
Markdown files are the source of truth.  The SQLite index is a
query-optimization view that must stay in sync with edits the user
makes directly in Obsidian.

Two entry points:

    revalidate_file(filename, vault_path, storage)
        Cheap mtime check + re-parse for a single file.  Invoked
        lazily at the top of every VaultLayer read handler so
        Obsidian edits are picked up on next access.

    rescan_vault(vault_path, storage)
        Full sweep — walks the vault, reconciles every file's
        mtime, and drops index rows whose files have been deleted.
        Exposed via the ``vault_rescan`` tool.

Both functions are defensive:  filesystem or parse errors are logged
and returned as counts rather than raised, so a single corrupt note
never poisons the rescan.
"""

import logging
from pathlib import Path

from .parser import (
    extract_tags,
    extract_wikilinks,
    resolve_link,
    split_frontmatter,
)
from .storage import VaultStorage

log = logging.getLogger("tailor.vault")


# ── Single-file revalidation (lazy path) ─────────────────────────

def revalidate_file(
    filename: str,
    vault_path: Path,
    storage: VaultStorage,
) -> bool:
    """
    Re-parse ``filename`` if its filesystem mtime differs from the
    mtime recorded in the index.  Returns True when a re-index
    occurred.  Silent no-op (returns False) when the file is
    missing, unchanged, or fails to parse.

    Safe to call at the top of every read handler — all exceptions
    are swallowed so rescan failures never block reads.
    """
    try:
        abs_path = (vault_path / filename).resolve()
        vault_resolved = vault_path.resolve()
        # Defence in depth — rescan should never follow paths that
        # escape the vault, even if storage somehow has a bad row.
        try:
            abs_path.relative_to(vault_resolved)
        except ValueError:
            return False

        if not abs_path.exists():
            # File gone — reflect it in the index.
            storage.delete_note(filename)
            return True

        observed = abs_path.stat().st_mtime_ns
        stored = storage.get_mtime_ns(filename)
        if stored is not None and stored == observed:
            return False

        _reindex_file(filename, abs_path, storage)
        return True
    except Exception as exc:  # pragma: no cover — defensive catch
        log.warning(f"revalidate_file({filename}) failed: {exc}")
        return False


# ── Full sweep ────────────────────────────────────────────────────

def rescan_vault(
    vault_path: Path,
    storage: VaultStorage,
) -> dict:
    """
    Walk the vault root, reconcile every ``.md`` file with the index,
    and drop rows for files that no longer exist.

    Returns a count dict: ``{added, modified, deleted, skipped}``.
    """
    counts = {"added": 0, "modified": 0, "deleted": 0, "skipped": 0}
    vault_resolved = vault_path.resolve()

    if not vault_resolved.exists():
        return counts

    seen: set[str] = set()
    for md_path in vault_resolved.rglob("*.md"):
        # Skip temp files created by the atomic-write pipeline
        if md_path.name.startswith(".vault_tmp_"):
            continue
        try:
            rel = md_path.resolve().relative_to(vault_resolved)
        except ValueError:
            continue
        filename = str(rel).replace("\\", "/")
        seen.add(filename)

        try:
            observed = md_path.stat().st_mtime_ns
            stored = storage.get_mtime_ns(filename)
            if stored is None:
                _reindex_file(filename, md_path, storage)
                counts["added"] += 1
            elif stored != observed:
                _reindex_file(filename, md_path, storage)
                counts["modified"] += 1
            else:
                counts["skipped"] += 1
        except Exception as exc:
            log.warning(f"rescan_vault: failed on {filename}: {exc}")

    # Drop index rows whose files disappeared. Re-verify existence at
    # delete time — if a user created a new file *during* our walk, it
    # won't be in `seen` but may well exist now, and we shouldn't drop
    # an index row for a real on-disk file.
    for indexed in storage.list_all_filenames():
        if indexed in seen:
            continue
        candidate = vault_resolved / indexed
        if candidate.exists():
            # Re-index rather than drop; file appeared after walk passed it.
            try:
                _reindex_file(indexed, candidate.resolve(), storage)
                counts["added"] += 1
            except Exception as exc:
                log.warning(f"rescan_vault: reindex of late-arriving {indexed} failed: {exc}")
            continue
        storage.delete_note(indexed)
        counts["deleted"] += 1

    return counts


# ── Internal ─────────────────────────────────────────────────────

def _reindex_file(filename: str, abs_path: Path, storage: VaultStorage) -> None:
    """
    Re-parse a file and upsert the index row, including links + tags.
    Caller supplies a resolved path — this function does no path
    validation itself.
    """
    content = abs_path.read_text(encoding="utf-8")
    mtime_ns = abs_path.stat().st_mtime_ns

    fm, body = split_frontmatter(content)

    note_type = _coerce_str(fm.get("note_type")) or _infer_note_type(filename)
    domain = _coerce_str(fm.get("domain")) or _infer_domain(filename)

    activity_id = fm.get("activity_id") or fm.get("strava_id")
    try:
        activity_id_int: int | None = int(activity_id) if activity_id else None
    except (TypeError, ValueError):
        activity_id_int = None

    date = _coerce_str(fm.get("date")) or _coerce_str(fm.get("date_end"))
    week = _coerce_str(fm.get("week"))
    has_insight_notes = bool(fm.get("has_insight_notes"))
    # ADR 0009 — vault subject-keying. Notes carry an optional subject_id
    # in frontmatter; lazy backfill happens here on every rescan/revalidate.
    subject_id = _coerce_str(fm.get("subject_id"))

    storage.upsert_note(
        filename=filename,
        domain=domain,
        note_type=note_type,
        frontmatter=fm,
        activity_id=activity_id_int,
        date=date,
        week=week,
        has_insight_notes=has_insight_notes,
        mtime_ns=mtime_ns,
        subject_id=subject_id,
    )

    # Reindex wikilinks — resolve against the current filename universe
    known = set(storage.list_all_filenames())
    resolved_links: list[tuple[str, str]] = []
    for (target, display) in extract_wikilinks(body):
        canonical = resolve_link(target, known) or target
        resolved_links.append((canonical, display))
    storage.replace_links(filename, resolved_links)

    # Tags — union of frontmatter.tags and inline #hashtags
    tags: list[str] = []
    fm_tags = fm.get("tags")
    if isinstance(fm_tags, list):
        tags.extend(str(t) for t in fm_tags if t)
    tags.extend(extract_tags(body))
    storage.replace_tags(filename, tags)

    # If this is a theme, mirror a row in vault_themes for fast listing
    if note_type == "theme":
        slug = _theme_slug_from_filename(filename)
        storage.upsert_theme(
            slug=slug,
            status=_coerce_str(fm.get("status")) or "open",
            opened=_coerce_str(fm.get("opened")) or (date or ""),
            last_updated=_coerce_str(fm.get("last_updated")) or (date or ""),
            linked_runs=list(fm.get("linked_runs") or []),
            confidence=_coerce_str(fm.get("confidence")),
            excerpt=_first_non_heading_line(body),
            subject_id=subject_id,
        )
    elif note_type == "theme_removed":  # pragma: no cover — defensive
        storage.delete_theme(_theme_slug_from_filename(filename))


def _coerce_str(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, str):
        return v
    return str(v)


def _infer_note_type(filename: str) -> str:
    """Heuristic: map the vault subdirectory to a note_type."""
    if filename.startswith("themes/"):
        return "theme"
    if filename.startswith("moments/"):
        return "moment"
    if filename.startswith("failure-modes/"):
        return "failure_mode"
    if filename.startswith("dashboards/"):
        return "dashboard"
    if filename.startswith("running/trends/"):
        return "trend_report"
    if filename.startswith("running/compare/"):
        return "compare_runs"
    if filename.startswith("running/"):
        return "run_report"
    return "unknown"


def _infer_domain(filename: str) -> str:
    if (
        filename.startswith("themes/")
        or filename.startswith("moments/")
        or filename.startswith("failure-modes/")
        or filename.startswith("dashboards/")
    ):
        return "vault"
    if filename.startswith("running/"):
        return "running"
    return "vault"


def _theme_slug_from_filename(filename: str) -> str:
    base = filename.rsplit("/", 1)[-1]
    if base.endswith(".md"):
        base = base[:-3]
    return base


def _first_non_heading_line(body: str, max_chars: int = 200) -> str:
    for line in body.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        return s[:max_chars]
    return ""
