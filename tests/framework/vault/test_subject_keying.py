"""
Tests for vault subject-keying — ADR 0009.

Pins the v6.2 behaviour against the failure modes the proposal-mode
auditor identified for the multi-subject pilot framing:

- Theme/moment entity_id round-trips through frontmatter + index.
- Set-once invariant on theme subject (reassignment is a hard error).
- list_notes / list_themes filter rows match-or-NULL when entity_id
  is provided (cross-subject + legacy notes stay visible).
- Evidence blocks carry "> Subject: ..." when written under a subject.
- Lazy rescan backfills the index from frontmatter for legacy vaults.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory


def _run(coro):
    return asyncio.run(coro)


def _setup() -> tuple:
    """Return (vault_path, data_path, layer) under a TemporaryDirectory.

    Caller is responsible for cleanup via the returned _cleanup() callback.
    """
    from tailor.framework.vault.layer import VaultLayer
    from tailor.framework.vault.writer import VaultWriter

    td = TemporaryDirectory()
    root = Path(td.name)
    vault_path = root / "vault"
    vault_path.mkdir()
    data_path = root / "data"
    data_path.mkdir()

    writer = VaultWriter(
        vault_path=vault_path,
        data_dir=data_path,
        vaultable_tools=set(),
    )
    layer = VaultLayer(vault_path=vault_path, vault_writer=writer)

    def _cleanup():
        layer.close()
        td.cleanup()

    return vault_path, data_path, layer, _cleanup


# ── Theme subject round-trip ─────────────────────────────────────────

class TestThemeSubjectRoundTrip:
    """Theme writes/reads with entity_id round-trip frontmatter + index."""

    def test_new_theme_with_subject_stamps_frontmatter(self):
        vault_path, _data_path, layer, cleanup = _setup()
        try:
            res = _run(layer.execute("vault_upsert_theme", {
                "slug": "hr-drift",
                "hypothesis": "HR drifts upward late in long runs",
                "evidence": "Mile-15 split shows +6 bpm over baseline",
                "entity_id": "P004",
            }))
            assert res.get("created") is True

            content = (vault_path / "themes/hr-drift.md").read_text(encoding="utf-8")
            assert 'entity_id: "P004"' in content
            # Evidence block carries the subject blockquote line
            assert "> Subject: P004" in content
        finally:
            cleanup()

    def test_new_theme_without_subject_omits_frontmatter_field(self):
        vault_path, _data_path, layer, cleanup = _setup()
        try:
            _run(layer.execute("vault_upsert_theme", {
                "slug": "cohort-hypothesis",
                "hypothesis": "Carb timing affects late-run drift across the cohort",
                "evidence": "First observation pending",
            }))
            content = (vault_path / "themes/cohort-hypothesis.md").read_text(encoding="utf-8")
            assert "entity_id:" not in content
            assert "> Subject:" not in content
        finally:
            cleanup()

    def test_theme_subject_persists_through_frontmatter_merge(self):
        """A second upsert (e.g. status update) must preserve entity_id."""
        vault_path, _data_path, layer, cleanup = _setup()
        try:
            _run(layer.execute("vault_upsert_theme", {
                "slug": "drift-p007",
                "hypothesis": "P007 shows late-run HR drift",
                "evidence": "Observed in week 1",
                "entity_id": "P007",
            }))
            # Second call: status flip, no entity_id passed
            _run(layer.execute("vault_upsert_theme", {
                "slug": "drift-p007",
                "status": "resolved",
                "resolution": "Confirmed in week 6 follow-up",
            }))
            content = (vault_path / "themes/drift-p007.md").read_text(encoding="utf-8")
            assert 'entity_id: "P007"' in content
        finally:
            cleanup()


# ── Set-once invariant ───────────────────────────────────────────────

class TestThemeSubjectSetOnce:
    """ADR 0009 set-once: reassignment is a hard error; promotion is fine."""

    def test_reassignment_returns_error(self):
        _vault_path, _data_path, layer, cleanup = _setup()
        try:
            _run(layer.execute("vault_upsert_theme", {
                "slug": "reassign-test",
                "hypothesis": "First framing",
                "evidence": "First observation",
                "entity_id": "P003",
            }))
            res = _run(layer.execute("vault_upsert_theme", {
                "slug": "reassign-test",
                "evidence": "Trying to retarget to P007",
                "entity_id": "P007",
            }))
            assert "error" in res
            assert "set-once" in res["error"]
            assert "P003" in res["error"] and "P007" in res["error"]
        finally:
            cleanup()

    def test_reassignment_rejection_does_not_mutate_file_or_evidence(self):
        # Integration-auditor H3 (overnight 2026-05-01): the set-once
        # invariant is enforced by raising an error, but no test asserts
        # that the on-disk theme file is *unchanged* after the rejected
        # reassignment. A future refactor that reorders "validate then
        # write" → "write then validate" would silently mutate the file
        # before raising. This pins the post-rejection state.
        vault_path, _data_path, layer, cleanup = _setup()
        try:
            _run(layer.execute("vault_upsert_theme", {
                "slug": "reassign-immutable-test",
                "hypothesis": "P003 fatigue pattern",
                "evidence": "Original observation",
                "entity_id": "P003",
            }))
            theme_path = vault_path / "themes/reassign-immutable-test.md"
            before = theme_path.read_text(encoding="utf-8")

            res = _run(layer.execute("vault_upsert_theme", {
                "slug": "reassign-immutable-test",
                "evidence": "Trying to retarget to P007",
                "entity_id": "P007",
            }))
            assert "error" in res

            after = theme_path.read_text(encoding="utf-8")
            assert before == after, (
                "rejected entity_id reassignment must not mutate the file. "
                "Set-once is a hard error per ADR 0009."
            )
            # The rejected evidence string must NOT appear anywhere on disk.
            assert "Trying to retarget to P007" not in after
        finally:
            cleanup()

    def test_promotion_from_unscoped_to_scoped_is_allowed(self):
        vault_path, _data_path, layer, cleanup = _setup()
        try:
            # Create unscoped theme
            _run(layer.execute("vault_upsert_theme", {
                "slug": "promote-test",
                "hypothesis": "Initially cohort-level",
                "evidence": "First observation",
            }))
            content = (vault_path / "themes/promote-test.md").read_text(encoding="utf-8")
            assert "entity_id:" not in content

            # Promote to subject-scoped
            res = _run(layer.execute("vault_upsert_theme", {
                "slug": "promote-test",
                "evidence": "Subject-specific follow-up for P004",
                "entity_id": "P004",
            }))
            assert "error" not in res

            content = (vault_path / "themes/promote-test.md").read_text(encoding="utf-8")
            assert 'entity_id: "P004"' in content
        finally:
            cleanup()


# ── Moment subject ───────────────────────────────────────────────────

class TestMomentSubject:
    def test_moment_with_subject_stamps_frontmatter(self):
        vault_path, _data_path, layer, cleanup = _setup()
        try:
            res = _run(layer.execute("vault_capture_moment", {
                "title": "Sleep gap before the long run",
                "body": "Slept ~4h two nights before; HR drift was elevated.",
                "entity_id": "P004",
                "date": "2026-04-15",
            }))
            assert res.get("captured") is True
            filename = res["filename"]
            content = (vault_path / filename).read_text(encoding="utf-8")
            assert 'entity_id: "P004"' in content
        finally:
            cleanup()


# ── Filtered queries: match OR NULL semantics ────────────────────────

class TestSubjectFilteredQueries:
    """ADR 0009 IS NULL branch: subject filters return matching + unscoped."""

    def test_list_themes_filter_returns_matching_and_unscoped(self):
        _vault_path, _data_path, layer, cleanup = _setup()
        try:
            _run(layer.execute("vault_upsert_theme", {
                "slug": "p004-only",
                "hypothesis": "P004-specific",
                "evidence": "P004 evidence",
                "entity_id": "P004",
            }))
            _run(layer.execute("vault_upsert_theme", {
                "slug": "p007-only",
                "hypothesis": "P007-specific",
                "evidence": "P007 evidence",
                "entity_id": "P007",
            }))
            _run(layer.execute("vault_upsert_theme", {
                "slug": "cohort",
                "hypothesis": "Cohort-level",
                "evidence": "Cohort evidence",
            })) # no entity_id

            # Filter for P004 — should return P004 + cohort, NOT P007
            res = _run(layer.execute("vault_list_themes", {"entity_id": "P004"}))
            slugs = {t["slug"] for t in res["themes"]}
            assert "p004-only" in slugs
            assert "cohort" in slugs
            assert "p007-only" not in slugs

            # Filter for P007 — should return P007 + cohort, NOT P004
            res = _run(layer.execute("vault_list_themes", {"entity_id": "P007"}))
            slugs = {t["slug"] for t in res["themes"]}
            assert "p007-only" in slugs
            assert "cohort" in slugs
            assert "p004-only" not in slugs

            # No filter — all three
            res = _run(layer.execute("vault_list_themes", {}))
            slugs = {t["slug"] for t in res["themes"]}
            assert slugs == {"p004-only", "p007-only", "cohort"}
        finally:
            cleanup()

    def test_list_notes_filter_returns_matching_and_unscoped(self):
        _vault_path, _data_path, layer, cleanup = _setup()
        try:
            _run(layer.execute("vault_capture_moment", {
                "title": "P004 observation",
                "body": "Body for P004",
                "entity_id": "P004",
                "date": "2026-04-10",
            }))
            _run(layer.execute("vault_capture_moment", {
                "title": "P007 observation",
                "body": "Body for P007",
                "entity_id": "P007",
                "date": "2026-04-11",
            }))
            _run(layer.execute("vault_capture_moment", {
                "title": "Cohort observation",
                "body": "Body without subject",
                "date": "2026-04-12",
            }))

            res = _run(layer.execute("vault_list_notes", {
                "kind": "moment",
                "entity_id": "P004",
            }))
            titles = {
                n["filename"].rsplit("/", 1)[-1]
                for n in res["notes"]
            }
            # P004 + cohort moments only — not P007
            assert any("p004" in t.lower() or "cohort" in t.lower() for t in titles)
            assert all("p007" not in t.lower() for t in titles)
        finally:
            cleanup()


# ── Lazy rescan backfill ─────────────────────────────────────────────

class TestRescanSubjectBackfill:
    """Existing v6.1 vault notes pick up entity_id on next rescan."""

    def test_rescan_backfills_subject_from_frontmatter(self):
        vault_path, _data_path, layer, cleanup = _setup()
        try:
            # Hand-write a theme file with entity_id in frontmatter — simulating
            # a v6.2 vault on disk that the SQLite index hasn't seen yet.
            (vault_path / "themes").mkdir(exist_ok=True)
            theme_md = (
                "---\n"
                "domain: vault\n"
                "note_type: theme\n"
                "kind: theme\n"
                'slug: "hand-written"\n'
                'title: "Hand-written theme"\n'
                'status: "open"\n'
                'opened: "2026-04-15"\n'
                'last_updated: "2026-04-15"\n'
                'date: "2026-04-15"\n'
                "linked_runs: []\n"
                "linked_themes: []\n"
                'entity_id: "P012"\n'
                'generated_at: "2026-04-15T10:00:00Z"\n'
                "tags:\n"
                "  - theme\n"
                "---\n"
                "# Hand-written theme\n\n"
                "## Hypothesis\n\nHypothesis for P012.\n\n"
                "## Evidence\n\n*(No evidence recorded yet.)*\n\n"
                "## Resolution\n\n*(Open — no resolution yet.)*\n"
            )
            (vault_path / "themes/hand-written.md").write_text(theme_md, encoding="utf-8")

            # Rescan — backfills the index from frontmatter
            res = _run(layer.execute("vault_rescan", {}))
            assert (res.get("added") or 0) >= 1

            # list_themes filter for P012 should find it
            res = _run(layer.execute("vault_list_themes", {"entity_id": "P012"}))
            slugs = {t["slug"] for t in res["themes"]}
            assert "hand-written" in slugs
        finally:
            cleanup()
