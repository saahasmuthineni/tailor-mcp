"""
Vault Writer — Post-Execute Hook + Atomic File Writes
=====================================================
VaultWriter is the bridge between the router pipeline and the Obsidian vault.

It is registered as a post-execute hook on RouterMCP:
    router.register_post_execute_hook(vault_writer)

After any vaultable tool succeeds the router calls:
    vault_writer(domain, tool_name, result)

Errors are always swallowed — a vault failure never breaks the MCP session.

Atomic writes use tempfile + os.replace() so Obsidian never sees a partial file.

Renderers live in a registry keyed by tool name.  The three core
biosensor renderers are registered by default; reorientation-tier
renderers (themes, moments) are registered by VaultLayer at wiring time.
"""

import logging
import os
import re
import tempfile
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from .renderer import (
    _format_evidence_block,
    render_compare_note,
    render_dashboard_note,
    render_failure_mode_note,
    render_moment_note,
    render_run_note,
    render_snapshot_note,
    render_theme_note,
    render_trend_note,
)
from .storage import VaultStorage

log = logging.getLogger("biosensor-mcp.vault")


# Type alias for a renderer callable: result dict → (filename, content)
Renderer = Callable[[dict], tuple[str, str]]


def _is_relative_to(path: Path, parent: Path) -> bool:
    """Path.is_relative_to() was added in Python 3.9; use it when available."""
    try:
        return path.is_relative_to(parent)
    except AttributeError:
        # Fallback for Python < 3.9
        try:
            path.relative_to(parent)
            return True
        except ValueError:
            return False


# Max chars for a single insight annotation block
_MAX_INSIGHT_CHARS = 2000

# Max chars for a single evidence block appended to a theme
_MAX_EVIDENCE_CHARS = 2000

# Non-printable control chars (except tab, newline, CR) that must not be stored
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _sanitize(text: str) -> str:
    """Strip null bytes and non-printable control chars."""
    return _CONTROL_RE.sub("", text)


class VaultWriter:
    """
    Callable post-execute hook.  Wires analytics output → Obsidian vault.

    Args:
        vault_path:       Absolute path to the Obsidian vault root.
        data_dir:         The MCP data directory (used to locate vault.db).
        vaultable_tools:  Set of tool names whose results should be archived.
        max_hr:           User-configured max heart rate (for run note rendering).
    """

    def __init__(
        self,
        vault_path: Path,
        data_dir: Path,
        vaultable_tools: set[str],
        max_hr: int = 195,
    ):
        self._vault_path = vault_path
        self._storage = VaultStorage(data_dir / "vault.db")
        self._vaultable_tools = vaultable_tools
        self._max_hr = max_hr

        # Renderer registry — seed with core biosensor renderers.
        # Wrappers adapt signatures so every entry is result -> (filename, content).
        self._renderers: dict[str, Renderer] = {
            "strava_run_report": self._render_run,
            "strava_trend_report": lambda r: render_trend_note(r),
            "strava_compare_runs": lambda r: render_compare_note(r),
            "vault_theme": lambda r: render_theme_note(r),
            "vault_moment": lambda r: render_moment_note(r),
            "vault_snapshot": lambda r: render_snapshot_note(r),
        }

    # ── Hook interface ──

    def __call__(self, domain: str, tool_name: str, result: dict) -> None:
        """Post-execute hook.  Errors are always swallowed."""
        if tool_name not in self._vaultable_tools:
            return
        try:
            self._write(domain, tool_name, result)
        except Exception as exc:
            log.warning(f"VaultWriter: {exc}")

    # ── Registry ──

    def register_renderer(self, tool_name: str, renderer: Renderer) -> None:
        """Register (or replace) a renderer for ``tool_name``."""
        self._renderers[tool_name] = renderer

    # ── Public write API ──

    def write_note(self, tool_name: str, result: dict) -> str:
        """
        Render and write a note.  Raises on error.
        Returns the relative filename (e.g. "running/2025-04-10-activity-123.md").
        """
        filename, content = self._render(tool_name, result)
        self._atomic_write(filename, content)
        self._index_note(filename, tool_name, result, content)
        return filename

    def write_theme(self, theme: dict) -> str:
        """
        Create or overwrite a theme note.  ``theme`` is passed directly
        to ``render_theme_note``.  Use ``append_theme_evidence`` to add
        subsequent evidence entries instead of rewriting the whole file.
        """
        filename, content = render_theme_note(theme)
        self._atomic_write(filename, content)
        self._index_note(filename, "vault_theme", {}, content)
        return filename

    def write_moment(self, moment: dict) -> str:
        """Write a moment note.  ``moment`` is passed directly to the renderer."""
        filename, content = render_moment_note(moment)
        self._atomic_write(filename, content)
        self._index_note(filename, "vault_moment", {}, content)
        return filename

    def write_snapshot(self, snapshot: dict) -> str:
        """
        Write ``snapshot.md`` in the vault root.  The snapshot is a
        compressed state note — new sessions read it first to orient
        quickly without scanning every source note.
        """
        filename, content = render_snapshot_note(snapshot)
        self._atomic_write(filename, content)
        self._index_note(filename, "vault_snapshot", {}, content)
        return filename

    def append_theme_evidence(
        self,
        slug: str,
        evidence: str,
        *,
        source_tier: int | None = None,
        source_tool: str | None = None,
        source_domain: str | None = None,
        verification: str | None = None,
        tag_suffix: str = "",
    ) -> str:
        """
        Append a timestamped evidence block to ``themes/<slug>.md``.

        Inserts before the ``## Resolution`` header when present, otherwise
        before end-of-file.  Rewrites the whole file atomically.  Returns
        the relative filename.  Raises ValueError on bad input,
        FileNotFoundError if the theme note does not exist.

        Optional provenance kwargs stamp the evidence block with a
        ``> Source: …`` blockquote so readers can see which tool / tier /
        verification level the observation came from.
        """
        evidence = _sanitize(evidence.strip())
        if not evidence:
            raise ValueError("Evidence must not be empty.")
        if len(evidence) > _MAX_EVIDENCE_CHARS:
            raise ValueError(
                f"Evidence too long: {len(evidence)} chars (max {_MAX_EVIDENCE_CHARS})."
            )

        slug = _sanitize(slug.strip())
        if not slug or "/" in slug or slug.startswith("."):
            raise ValueError(f"Invalid theme slug: {slug!r}")

        filename = f"themes/{slug}.md"
        abs_path = self._safe_path(filename)
        if not abs_path.exists():
            raise FileNotFoundError(f"Theme note not found: {filename}")

        existing = abs_path.read_text(encoding="utf-8")
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        block = _format_evidence_block(
            evidence,
            source_tier=source_tier,
            source_tool=source_tool,
            source_domain=source_domain,
            verification=verification,
            tag_suffix=tag_suffix,
            timestamp=timestamp,
        )

        # Drop the placeholder if this is the first evidence entry
        placeholder = "*(No evidence recorded yet.)*"
        if placeholder in existing:
            updated = existing.replace(placeholder + "\n", block, 1)
            if updated == existing:  # fallback if newline stripped
                updated = existing.replace(placeholder, block, 1)
        else:
            # Insert before ## Resolution if present, else append at end
            resolution_header = "\n## Resolution"
            idx = existing.find(resolution_header)
            if idx != -1:
                updated = existing[:idx].rstrip() + "\n\n" + block + "\n" + existing[idx + 1:]
            else:
                updated = existing.rstrip() + "\n\n" + block

        # Refresh last_updated stamp
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        updated = re.sub(
            r'^last_updated:\s*".*?"$',
            f'last_updated: "{today}"',
            updated,
            count=1,
            flags=re.MULTILINE,
        )

        self._atomic_write_abs(abs_path, updated)
        # Re-index so wikilinks/tags/theme row all reflect the new body
        self._index_note(filename, "vault_theme", {}, updated)
        log.info(f"VaultWriter: evidence appended to {filename}")
        return filename

    def append_theme_thinking(self, slug: str, thinking: str) -> str:
        """
        Append a ``### Thinking — TIMESTAMP`` block to a theme note.

        Mirrors ``append_theme_evidence`` but uses a distinct block header
        so 'partial progress' entries are visually separable from settled
        evidence in Obsidian.
        """
        thinking = _sanitize(thinking.strip())
        if not thinking:
            raise ValueError("Thinking entry must not be empty.")
        if len(thinking) > _MAX_EVIDENCE_CHARS:
            raise ValueError(
                f"Thinking entry too long: {len(thinking)} chars "
                f"(max {_MAX_EVIDENCE_CHARS})."
            )

        slug = _sanitize(slug.strip())
        if not slug or "/" in slug or slug.startswith("."):
            raise ValueError(f"Invalid theme slug: {slug!r}")

        filename = f"themes/{slug}.md"
        abs_path = self._safe_path(filename)
        if not abs_path.exists():
            raise FileNotFoundError(f"Theme note not found: {filename}")

        existing = abs_path.read_text(encoding="utf-8")
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        block = f"### Thinking — {timestamp}\n\n{thinking}\n"

        # Place before ## Resolution if present, else append at end
        resolution_header = "\n## Resolution"
        idx = existing.find(resolution_header)
        if idx != -1:
            updated = existing[:idx].rstrip() + "\n\n" + block + "\n" + existing[idx + 1:]
        else:
            updated = existing.rstrip() + "\n\n" + block

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        updated = re.sub(
            r'^last_updated:\s*".*?"$',
            f'last_updated: "{today}"',
            updated,
            count=1,
            flags=re.MULTILINE,
        )

        self._atomic_write_abs(abs_path, updated)
        self._index_note(filename, "vault_theme", {}, updated)
        log.info(f"VaultWriter: thinking appended to {filename}")
        return filename

    def reframe_theme(
        self, slug: str, new_hypothesis: str, old_hypothesis: str
    ) -> str:
        """
        Move the current hypothesis into a dated ``## Prior Framings``
        entry and replace ``## Hypothesis`` with ``new_hypothesis``.

        Idempotent on repeated calls with the same arguments: subsequent
        reframes append fresh dated entries above the existing ones.
        """
        new_hypothesis = _sanitize(new_hypothesis.strip())
        old_hypothesis = _sanitize((old_hypothesis or "").strip())
        if not new_hypothesis:
            raise ValueError("New hypothesis must not be empty.")

        slug = _sanitize(slug.strip())
        filename = f"themes/{slug}.md"
        abs_path = self._safe_path(filename)
        if not abs_path.exists():
            raise FileNotFoundError(f"Theme note not found: {filename}")

        existing = abs_path.read_text(encoding="utf-8")
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Replace the ## Hypothesis block text with new_hypothesis.
        hyp_header = "## Hypothesis"
        hyp_idx = existing.find(hyp_header)
        if hyp_idx == -1:
            raise ValueError(f"Theme {slug!r} has no '## Hypothesis' section.")
        # Find the next top-level '## ' header after hypothesis
        after_header_idx = hyp_idx + len(hyp_header)
        next_section_idx = existing.find("\n## ", after_header_idx)
        if next_section_idx == -1:
            next_section_idx = len(existing)

        new_section = f"{hyp_header}\n\n{new_hypothesis}\n\n"
        updated = existing[:hyp_idx] + new_section + existing[next_section_idx + 1 :]

        # Insert or extend ## Prior Framings above next major section.
        prior_block = (
            f"### {today}\n\n"
            f"{old_hypothesis if old_hypothesis else '*(No prior hypothesis recorded.)*'}\n"
        )
        prior_header = "## Prior Framings"
        if prior_header in updated:
            # Append a new dated entry at the top of the existing section
            # (directly after the header line).
            marker = prior_header + "\n"
            pos = updated.find(marker) + len(marker)
            # Skip any leading blank line after the header
            if updated[pos : pos + 1] == "\n":
                pos += 1
            updated = updated[:pos] + "\n" + prior_block + "\n" + updated[pos:]
        else:
            # Create the section immediately after the Hypothesis block.
            pf_block = f"## Prior Framings\n\n{prior_block}\n"
            # Reparse next-section boundary (content shifted).
            hyp_idx2 = updated.find(hyp_header)
            after_hyp2 = hyp_idx2 + len(new_section)
            updated = updated[:after_hyp2] + pf_block + updated[after_hyp2:]

        # Refresh last_updated
        updated = re.sub(
            r'^last_updated:\s*".*?"$',
            f'last_updated: "{today}"',
            updated,
            count=1,
            flags=re.MULTILINE,
        )

        self._atomic_write_abs(abs_path, updated)
        self._index_note(filename, "vault_theme", {}, updated)
        log.info(f"VaultWriter: theme {slug} reframed")
        return filename

    def correct_theme_evidence(
        self,
        slug: str,
        evidence_timestamp: str,
        correction: str,
        corrected_by: str | None = None,
        *,
        propagate_to_referencing_notes: bool = False,
    ) -> dict:
        """
        Insert a ``> [CORRECTED <ts>]: …`` blockquote immediately after the
        ``### Evidence — <evidence_timestamp>`` header, then append a new
        evidence block tagged ``[correction]`` logging the correction itself.

        Preserves the original evidence block verbatim — the append-only
        invariant of the evidence log is maintained.

        When ``propagate_to_referencing_notes`` is True, scans the SQLite
        link index for notes that wikilink to this theme and appends a
        ``> [!warning]`` callout to each one's ``## Corrections`` section
        (creating the section if needed).  The append is idempotent on
        the (theme_slug, evidence_timestamp) pair — re-running with the
        same args does not duplicate markers.

        Returns a dict:
            {
                "filename":      str — the corrected theme note,
                "propagated_to": list[str] — referencing notes that received a
                                 callout (empty when propagate=False, or when
                                 propagate=True but nothing references this
                                 theme).
            }
        """
        correction = _sanitize(correction.strip())
        if not correction:
            raise ValueError("Correction text must not be empty.")
        if len(correction) > _MAX_EVIDENCE_CHARS:
            raise ValueError(
                f"Correction too long: {len(correction)} chars "
                f"(max {_MAX_EVIDENCE_CHARS})."
            )

        slug = _sanitize(slug.strip())
        if not slug or "/" in slug or slug.startswith("."):
            raise ValueError(f"Invalid theme slug: {slug!r}")

        filename = f"themes/{slug}.md"
        abs_path = self._safe_path(filename)
        if not abs_path.exists():
            raise FileNotFoundError(f"Theme note not found: {filename}")

        existing = abs_path.read_text(encoding="utf-8")
        target_header = f"### Evidence — {evidence_timestamp}"
        idx = existing.find(target_header)
        if idx == -1:
            raise ValueError(
                f"Evidence block with timestamp {evidence_timestamp!r} not "
                f"found in {filename}."
            )

        now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        by_suffix = f" (by {corrected_by})" if corrected_by else ""
        marker_line = (
            f"> [CORRECTED {now_ts}]:{by_suffix} {correction}"
        )

        # Insert after the header's newline.
        newline_after = existing.find("\n", idx)
        if newline_after == -1:
            updated = existing + "\n" + marker_line + "\n"
        else:
            # Place the marker right after the header line.
            updated = (
                existing[: newline_after + 1]
                + marker_line
                + "\n"
                + existing[newline_after + 1 :]
            )

        self._atomic_write_abs(abs_path, updated)
        self._index_note(filename, "vault_theme", {}, updated)

        # Also append a new evidence block tagged [correction] so the
        # correction itself is a first-class entry in the log.
        self.append_theme_evidence(
            slug,
            f"Correction of {evidence_timestamp}: {correction}",
            tag_suffix="[correction]",
        )

        propagated: list[str] = []
        if propagate_to_referencing_notes:
            propagated = self._propagate_correction_to_referencing_notes(
                theme_filename=filename,
                theme_slug=slug,
                evidence_timestamp=evidence_timestamp,
                correction=correction,
                corrected_by=corrected_by,
                correction_timestamp=now_ts,
            )

        log.info(
            f"VaultWriter: correction inserted on {filename} "
            f"(propagated to {len(propagated)})"
        )
        return {"filename": filename, "propagated_to": propagated}

    def _propagate_correction_to_referencing_notes(
        self,
        *,
        theme_filename: str,
        theme_slug: str,
        evidence_timestamp: str,
        correction: str,
        corrected_by: str | None,
        correction_timestamp: str,
    ) -> list[str]:
        """
        For every note that wikilinks to ``theme_filename``, append a
        ``> [!warning]``-styled correction callout under a ``## Corrections``
        section (created if missing).  Idempotent on (theme_slug,
        evidence_timestamp): re-running with the same identifiers leaves
        the file unchanged.

        Append-only: never rewrites or removes existing callouts.  Each
        propagation event leaves a new callout pointing at the evidence
        timestamp it superseded.
        """
        sources = self._storage.get_incoming_links(target=theme_filename)
        propagated: list[str] = []
        marker_token = f"[CORRECTED-EV {evidence_timestamp}]"
        by_suffix = f" (by {corrected_by})" if corrected_by else ""
        callout = (
            f"> [!warning] {marker_token} {correction_timestamp}{by_suffix}\n"
            f"> Theme [[{theme_slug}]] evidence at `{evidence_timestamp}` "
            f"was superseded.\n"
            f"> {correction}\n"
        )

        for row in sources:
            source = row.get("source")
            if not source or source == theme_filename:
                continue
            try:
                src_path = self._safe_path(source)
            except ValueError:
                continue
            if not src_path.exists():
                continue
            try:
                content = src_path.read_text(encoding="utf-8")
            except OSError:
                continue

            # Idempotency: same (theme, evidence_timestamp) pair already on file?
            if marker_token in content and f"[[{theme_slug}]]" in content:
                # Look for the precise pairing on adjacent lines to avoid
                # false-match across unrelated callouts in the same file.
                if self._already_propagated(content, marker_token, theme_slug):
                    continue

            updated = self._append_corrections_callout(content, callout)
            if updated == content:
                continue
            try:
                self._atomic_write_abs(src_path, updated)
            except OSError as exc:
                log.warning(
                    f"VaultWriter: propagation skipped {source}: {exc}"
                )
                continue
            try:
                self._index_note(source, "vault_correction_propagation", {}, updated)
            except Exception as exc:  # pragma: no cover — defensive
                log.warning(
                    f"VaultWriter: re-index after propagation failed for {source}: {exc}"
                )
            propagated.append(source)

        return propagated

    @staticmethod
    def _already_propagated(content: str, marker_token: str, theme_slug: str) -> bool:
        """
        True iff a callout with the same marker token already exists in the
        same window as a wikilink to the theme slug.  Tolerates re-runs
        (idempotent propagation) without false-matching unrelated content
        that happens to mention either token in isolation.
        """
        lines = content.splitlines()
        target_link = f"[[{theme_slug}]]"
        for i, line in enumerate(lines):
            if marker_token in line and line.lstrip().startswith(">"):
                # Check the next 3 callout-continuation lines for the link.
                for j in range(i, min(len(lines), i + 4)):
                    if target_link in lines[j]:
                        return True
        return False

    @staticmethod
    def _append_corrections_callout(content: str, callout: str) -> str:
        """
        Append ``callout`` to a ``## Corrections`` section.  If the section
        does not exist, create it at end-of-file.  Always preserves all
        existing content.
        """
        section_header = "## Corrections"
        if section_header in content:
            # Append to the end of the existing section: place callout at EOF.
            tail = content if content.endswith("\n") else content + "\n"
            return tail + "\n" + callout
        # Create the section at EOF.
        tail = content if content.endswith("\n") else content + "\n"
        return tail + "\n" + section_header + "\n\n" + callout

    # ── Failure-mode notes (v6.1) ──

    def write_failure_mode(self, failure_mode: dict) -> str:
        """
        Create or overwrite a failure-mode note.  ``failure_mode`` is
        passed directly to ``render_failure_mode_note``.  Use
        ``append_failure_mode_evidence`` to add subsequent evidence
        entries instead of rewriting the whole file.
        """
        filename, content = render_failure_mode_note(failure_mode)
        self._atomic_write(filename, content)
        self._index_note(filename, "vault_failure_mode", {}, content)
        return filename

    def update_failure_mode_metadata(
        self,
        slug: str,
        *,
        status: str | None = None,
        related_themes: list | None = None,
        related_subjects: list | None = None,
        tags: list | None = None,
        title: str | None = None,
    ) -> str:
        """
        Patch a failure-mode note's frontmatter in place — preserves the
        body (including the entire append-only evidence log) verbatim.

        Body sections (symptom / diagnosis / mitigation) are intentionally
        not editable through this method.  Update them by hand in
        Obsidian; the index revalidates lazily on next read.
        """
        slug = _sanitize(slug.strip())
        if not slug or "/" in slug or slug.startswith("."):
            raise ValueError(f"Invalid failure-mode slug: {slug!r}")

        filename = f"failure-modes/{slug}.md"
        abs_path = self._safe_path(filename)
        if not abs_path.exists():
            raise FileNotFoundError(f"Failure-mode note not found: {filename}")

        existing = abs_path.read_text(encoding="utf-8")
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        if status is not None:
            if status not in ("active", "mitigated", "superseded"):
                raise ValueError(
                    f"Invalid status: {status!r} "
                    "(active | mitigated | superseded)."
                )
            existing = re.sub(
                r'^status:\s*.*$', f'status: "{status}"',
                existing, count=1, flags=re.MULTILINE,
            )

        if title is not None:
            title = _sanitize(title.strip())
            if title:
                existing = re.sub(
                    r'^title:\s*.*$', f'title: "{title}"',
                    existing, count=1, flags=re.MULTILINE,
                )

        if related_themes is not None:
            existing = self._replace_yaml_list(
                existing, "related_themes",
                [_sanitize(str(t).strip()) for t in related_themes if t],
            )

        if related_subjects is not None:
            existing = self._replace_yaml_list(
                existing, "related_subjects",
                [_sanitize(str(s).strip()) for s in related_subjects if s],
            )

        if tags is not None:
            merged = ["failure_mode"] + [
                _sanitize(str(t).strip()) for t in tags if t
            ]
            # Tags is rendered as a YAML block with `tags:` line followed
            # by "  - …" entries. Replace the whole block, ending at "---".
            existing = self._replace_yaml_tags(existing, merged)

        existing = re.sub(
            r'^last_updated:\s*.*$', f'last_updated: "{today}"',
            existing, count=1, flags=re.MULTILINE,
        )

        self._atomic_write_abs(abs_path, existing)
        self._index_note(filename, "vault_failure_mode", {}, existing)
        return filename

    @staticmethod
    def _replace_yaml_list(content: str, key: str, items: list) -> str:
        """
        Replace a single-line ``key: [...]`` list value in the YAML
        frontmatter.  The renderer always emits these as one-line lists
        (via ``_yaml_string_list``), so this only needs to handle the
        single-line form.
        """
        rendered = "[]" if not items else (
            "[" + ", ".join(f'"{i}"' for i in items) + "]"
        )
        return re.sub(
            rf'^{re.escape(key)}:\s*.*$',
            f'{key}: {rendered}',
            content, count=1, flags=re.MULTILINE,
        )

    @staticmethod
    def _replace_yaml_tags(content: str, tags: list) -> str:
        """
        Replace the multi-line ``tags:`` block in YAML frontmatter,
        preserving everything before/after.  The renderer emits:

            tags:
              - failure_mode
              - other

        followed by ``---``.  We replace from the ``tags:`` line through
        the final ``  - …`` entry, before the closing ``---``.
        """
        # Deduplicate while preserving order.
        seen: set = set()
        deduped: list = []
        for t in tags:
            if t and t not in seen:
                seen.add(t)
                deduped.append(t)
        replacement = "tags:\n" + "\n".join(f"  - {t}" for t in deduped)
        # Match `tags:` followed by 1+ "  - …" entries, stopping at `---`
        # or the next top-level key (a line not starting with whitespace).
        return re.sub(
            r'^tags:\s*\n(?:[ \t]+-[^\n]*\n)+',
            replacement + "\n",
            content, count=1, flags=re.MULTILINE,
        )

    def append_failure_mode_evidence(
        self,
        slug: str,
        evidence: str,
        *,
        source_tier: int | None = None,
        source_tool: str | None = None,
        source_domain: str | None = None,
        verification: str | None = None,
    ) -> str:
        """
        Append a timestamped evidence block to ``failure-modes/<slug>.md``.

        Mirrors ``append_theme_evidence`` but for failure-mode notes.
        Preserves the append-only invariant of the evidence log.
        """
        evidence = _sanitize(evidence.strip())
        if not evidence:
            raise ValueError("Evidence must not be empty.")
        if len(evidence) > _MAX_EVIDENCE_CHARS:
            raise ValueError(
                f"Evidence too long: {len(evidence)} chars (max {_MAX_EVIDENCE_CHARS})."
            )

        slug = _sanitize(slug.strip())
        if not slug or "/" in slug or slug.startswith("."):
            raise ValueError(f"Invalid failure-mode slug: {slug!r}")

        filename = f"failure-modes/{slug}.md"
        abs_path = self._safe_path(filename)
        if not abs_path.exists():
            raise FileNotFoundError(f"Failure-mode note not found: {filename}")

        existing = abs_path.read_text(encoding="utf-8")
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        block = _format_evidence_block(
            evidence,
            source_tier=source_tier,
            source_tool=source_tool,
            source_domain=source_domain,
            verification=verification,
            timestamp=timestamp,
        )

        placeholder = "*(No evidence recorded yet.)*"
        if placeholder in existing:
            updated = existing.replace(placeholder + "\n", block, 1)
            if updated == existing:
                updated = existing.replace(placeholder, block, 1)
        else:
            updated = existing.rstrip() + "\n\n" + block

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        updated = re.sub(
            r'^last_updated:\s*".*?"$',
            f'last_updated: "{today}"',
            updated,
            count=1,
            flags=re.MULTILINE,
        )

        self._atomic_write_abs(abs_path, updated)
        self._index_note(filename, "vault_failure_mode", {}, updated)
        log.info(f"VaultWriter: evidence appended to {filename}")
        return filename

    # ── Dashboards (v6.1, ADR 0007 dual-output) ──

    def write_dashboard(
        self,
        *,
        name: str,
        title: str,
        description: str,
        columns: list[str],
        rows: list[list],
        dataview_query: str | None = None,
        dataview_note: str | None = None,
        last_updated: str | None = None,
    ) -> str:
        """
        Materialise a dashboard note (ADR 0007 dual-output).  The
        snapshot table is the source-of-truth view; the optional
        Dataview block is an additive view that renders only when the
        Dataview plugin is installed.
        """
        filename, content = render_dashboard_note(
            name=name,
            title=title,
            description=description,
            columns=columns,
            rows=rows,
            dataview_query=dataview_query,
            dataview_note=dataview_note,
            last_updated=last_updated,
        )
        self._atomic_write(filename, content)
        self._index_note(filename, "vault_dashboard", {}, content)
        return filename

    # ── Inbox (v6) ──

    def append_inbox_item(self, text: str, tags: list[str] | None = None) -> str:
        """
        Append a timestamped entry to ``inbox.md`` in the vault root.
        Creates the file if missing.  Returns the written line.
        """
        text = _sanitize(text.strip())
        if not text:
            raise ValueError("Inbox item must not be empty.")
        if len(text) > 2000:
            raise ValueError(
                f"Inbox item too long: {len(text)} chars (max 2000)."
            )

        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        tag_part = ""
        if tags:
            tag_part = " " + " ".join(
                f"#{_sanitize(str(t).strip()).lstrip('#')}"
                for t in tags if t and str(t).strip()
            )
        line = f"- **{timestamp}:** {text}{tag_part}"

        inbox_path = self._safe_path("inbox.md")
        existing = ""
        if inbox_path.exists():
            existing = inbox_path.read_text(encoding="utf-8")
        if existing and not existing.endswith("\n"):
            existing += "\n"
        updated = existing + line + "\n"
        self._atomic_write_abs(inbox_path, updated)
        return line

    def read_inbox(self) -> list[dict]:
        """Parse ``inbox.md`` into a list of ``{timestamp, text, tags, raw}``."""
        inbox_path = self._safe_path("inbox.md")
        if not inbox_path.exists():
            return []
        content = inbox_path.read_text(encoding="utf-8")
        items: list[dict] = []
        for line in content.splitlines():
            stripped = line.rstrip()
            if not stripped.startswith("- **"):
                continue
            # Format: "- **<ts>:** <body> [#tag ...]"
            try:
                ts_start = stripped.index("**") + 2
                ts_end = stripped.index(":**", ts_start)
                ts = stripped[ts_start:ts_end]
                body = stripped[ts_end + 3 :].strip()
            except ValueError:
                continue
            tokens = body.split()
            tags = [t[1:] for t in tokens if t.startswith("#") and len(t) > 1]
            text_tokens = [t for t in tokens if not t.startswith("#")]
            items.append({
                "timestamp": ts,
                "text": " ".join(text_tokens).strip(),
                "tags": tags,
                "raw": stripped,
            })
        return items

    def drain_inbox_items(self, indices_to_remove: set[int]) -> None:
        """Rewrite ``inbox.md`` without the lines at ``indices_to_remove``."""
        inbox_path = self._safe_path("inbox.md")
        if not inbox_path.exists():
            return
        content = inbox_path.read_text(encoding="utf-8")
        lines = content.splitlines()
        # Build list of (is_item, line); we preserve non-item lines verbatim.
        kept: list[str] = []
        item_idx = 0
        for raw in lines:
            if raw.startswith("- **"):
                if item_idx not in indices_to_remove:
                    kept.append(raw)
                item_idx += 1
            else:
                kept.append(raw)
        updated = "\n".join(kept)
        if updated and not updated.endswith("\n"):
            updated += "\n"
        self._atomic_write_abs(inbox_path, updated)

    def append_insight_notes(self, filename: str, notes: str) -> None:
        """
        Append a timestamped insight section to an existing note.
        Updates the SQLite index to reflect has_insight_notes=True.

        Raises ValueError on bad input, FileNotFoundError if note missing.
        """
        notes = _sanitize(notes.strip())
        if not notes:
            raise ValueError("Insight notes must not be empty.")
        if len(notes) > _MAX_INSIGHT_CHARS:
            raise ValueError(
                f"Insight notes too long: {len(notes)} chars (max {_MAX_INSIGHT_CHARS})."
            )

        # Path traversal check
        abs_path = self._safe_path(filename)

        if not abs_path.exists():
            raise FileNotFoundError(f"Note not found: {filename}")

        existing = abs_path.read_text(encoding="utf-8")

        # Replace the placeholder stub if present; otherwise append
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        block = f"\n\n### Insight — {timestamp}\n\n{notes}\n"

        stub = "*(No insight notes yet.)*"
        if stub in existing:
            updated = existing.replace(stub, notes, 1)
        else:
            updated = existing.rstrip() + block

        # Update has_insight_notes: false → true in frontmatter
        updated = updated.replace("has_insight_notes: false", "has_insight_notes: true", 1)

        self._atomic_write_abs(abs_path, updated)
        self._storage.set_has_insight_notes(filename)
        # Refresh mtime_ns so rescan doesn't immediately re-parse this file
        try:
            self._storage.set_mtime_ns(filename, abs_path.stat().st_mtime_ns)
        except OSError:
            pass
        log.info(f"VaultWriter: insight notes appended to {filename}")

    def close(self):
        """Release SQLite connection (required on Windows)."""
        self._storage.close()

    # ── Internal ──

    def _write(self, domain: str, tool_name: str, result: dict) -> None:
        filename, content = self._render(tool_name, result)
        self._atomic_write(filename, content)
        self._index_note(filename, tool_name, result, content)
        log.info(f"VaultWriter: wrote {filename}")

    def _render(self, tool_name: str, result: dict) -> tuple[str, str]:
        """Dispatch to the registered renderer. Returns (filename, content)."""
        renderer = self._renderers.get(tool_name)
        if renderer is None:
            raise ValueError(f"No renderer for tool: {tool_name}")
        return renderer(result)

    def _render_run(self, result: dict) -> tuple[str, str]:
        """
        Adapter for ``render_run_note`` — builds activity_data from the
        result dict (as RunningChild now embeds metadata directly).
        """
        activity_data = {
            "id": result.get("activity_id"),
            "name": result.get("activity_name"),
            "start_date": result.get("start_date"),
            "distance": result.get("distance"),
            "moving_time": result.get("moving_time"),
            "average_heartrate": result.get("average_heartrate"),
            "max_heartrate": result.get("max_heartrate"),
        }
        return render_run_note(result, activity_data, max_hr=self._max_hr)

    def _atomic_write(self, relative_filename: str, content: str) -> None:
        """Resolve to vault_path, validate, then write atomically."""
        abs_path = self._safe_path(relative_filename)
        self._atomic_write_abs(abs_path, content)

    def _atomic_write_abs(self, abs_path: Path, content: str) -> None:
        """Atomic write: temp file → os.replace(). Obsidian never sees partial."""
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        # Write to a temp file in the same directory so os.replace is atomic
        fd, tmp_path = tempfile.mkstemp(
            dir=abs_path.parent, prefix=".vault_tmp_", suffix=".md"
        )
        # Two failure modes to handle cleanly:
        #   1. os.fdopen() itself raises — the fd was never transferred,
        #      so we must close it explicitly, then unlink the tmp file.
        #   2. write()/os.replace() raises — fdopen's `with` closed the
        #      fd; we just need to unlink the tmp file if it still exists.
        fd_transferred = False
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                fd_transferred = True
                f.write(content)
            os.replace(tmp_path, abs_path)
        except Exception:
            if not fd_transferred:
                try:
                    os.close(fd)
                except OSError:
                    pass
            # os.replace() is atomic — if it succeeded, tmp_path is gone;
            # if it failed, tmp_path still exists. Either way, best-effort
            # unlink is safe.
            try:
                os.unlink(tmp_path)
            except FileNotFoundError:
                pass
            except OSError as unlink_err:
                log.warning(
                    f"Failed to clean up vault tmp file {tmp_path}: {unlink_err}"
                )
            raise

    def _safe_path(self, relative_filename: str) -> Path:
        """
        Resolve relative_filename inside vault_path.
        Raises ValueError if the resolved path escapes the vault root.
        """
        resolved = (self._vault_path / relative_filename).resolve()
        vault_resolved = self._vault_path.resolve()
        if not _is_relative_to(resolved, vault_resolved):
            raise ValueError(f"Path traversal detected: {relative_filename}")
        return resolved

    def _index_note(
        self, filename: str, tool_name: str, result: dict, content: str
    ) -> None:
        """
        Extract key fields and write to VaultStorage index, including
        mtime_ns, wikilinks, tags, and (for themes) a vault_themes row.
        Delegates to rescan._reindex_file so the write-path and the
        rescan-path share a single parser.
        """
        abs_path = self._safe_path(filename)
        # Import here to avoid a circular import at module load.
        from .rescan import _reindex_file

        _reindex_file(filename, abs_path, self._storage)
