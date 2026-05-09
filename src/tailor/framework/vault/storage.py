"""
Vault Storage — SQLite Index for Vault Notes
=============================================
Tracks every note written by VaultWriter so VaultLayer can
query by domain, type, date, week, or anomaly status without
scanning the filesystem.

Extends framework BaseStorage — same threading model, same
connection lifecycle (WAL mode, thread-local connections).

Schema overview (v2 — reasoning persistence):
    vault_notes     — one row per written file (now with mtime_ns)
    vault_links     — wikilink graph (source → target)
    vault_tags      — inverted index on #hashtags
    vault_themes    — denormalised theme rows for fast list queries
"""

import logging
from datetime import datetime, timezone

from ..audit import _dumps, _loads
from ..storage import BaseStorage

log = logging.getLogger("tailor.vault")


class VaultStorage(BaseStorage):
    """
    SQLite index of vault notes.

    One row per written file. Re-writing a note (backfill or overwrite)
    uses INSERT OR REPLACE on the filename PRIMARY KEY.
    """

    def _schema_sql(self) -> str:
        return """
            CREATE TABLE IF NOT EXISTS vault_notes (
                filename TEXT PRIMARY KEY,
                domain TEXT NOT NULL,
                note_type TEXT NOT NULL,
                activity_id INTEGER,
                date TEXT,
                week TEXT,
                has_insight_notes INTEGER NOT NULL DEFAULT 0,
                frontmatter_json TEXT NOT NULL,
                written_at TEXT NOT NULL,
                mtime_ns INTEGER,
                subject_id TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_vault_domain ON vault_notes(domain);
            CREATE INDEX IF NOT EXISTS idx_vault_date   ON vault_notes(date);
            CREATE INDEX IF NOT EXISTS idx_vault_type   ON vault_notes(note_type);
            CREATE INDEX IF NOT EXISTS idx_vault_week   ON vault_notes(week);
            CREATE INDEX IF NOT EXISTS idx_vault_subject ON vault_notes(subject_id);

            CREATE TABLE IF NOT EXISTS vault_links (
                source TEXT NOT NULL,
                target TEXT NOT NULL,
                link_text TEXT,
                PRIMARY KEY (source, target)
            );
            CREATE INDEX IF NOT EXISTS idx_vault_links_source ON vault_links(source);
            CREATE INDEX IF NOT EXISTS idx_vault_links_target ON vault_links(target);

            CREATE TABLE IF NOT EXISTS vault_tags (
                filename TEXT NOT NULL,
                tag TEXT NOT NULL,
                PRIMARY KEY (filename, tag)
            );
            CREATE INDEX IF NOT EXISTS idx_vault_tags_tag ON vault_tags(tag);

            CREATE TABLE IF NOT EXISTS vault_themes (
                slug TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                opened TEXT NOT NULL,
                last_updated TEXT NOT NULL,
                linked_runs_json TEXT NOT NULL DEFAULT '[]',
                confidence TEXT,
                excerpt TEXT,
                subject_id TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_vault_themes_status ON vault_themes(status);
            CREATE INDEX IF NOT EXISTS idx_vault_themes_updated ON vault_themes(last_updated);
            CREATE INDEX IF NOT EXISTS idx_vault_themes_subject ON vault_themes(subject_id);
        """

    def _ensure_db(self):
        """Create tables and migrate legacy schemas in place."""
        super()._ensure_db()
        conn = self._get_conn()
        # vault_notes column migrations
        cols = {row[1] for row in conn.execute("PRAGMA table_info(vault_notes)").fetchall()}
        if "mtime_ns" not in cols:
            conn.execute("ALTER TABLE vault_notes ADD COLUMN mtime_ns INTEGER")
        if "subject_id" not in cols:
            # v6.2 — vault subject-keying (ADR 0009). Lazy backfill on
            # the next vault_rescan, which already parses frontmatter.
            conn.execute("ALTER TABLE vault_notes ADD COLUMN subject_id TEXT")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_vault_subject "
                "ON vault_notes(subject_id)"
            )
        # vault_themes column migrations
        theme_cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(vault_themes)").fetchall()
        }
        if "subject_id" not in theme_cols:
            conn.execute("ALTER TABLE vault_themes ADD COLUMN subject_id TEXT")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_vault_themes_subject "
                "ON vault_themes(subject_id)"
            )
        conn.commit()

    # ── Write (notes) ──

    def upsert_note(
        self,
        filename: str,
        domain: str,
        note_type: str,
        frontmatter: dict,
        *,
        activity_id: int | None = None,
        date: str | None = None,
        week: str | None = None,
        has_insight_notes: bool = False,
        mtime_ns: int | None = None,
        subject_id: str | None = None,
    ):
        """Insert or replace a note index entry."""
        self.execute(
            "INSERT OR REPLACE INTO vault_notes"
            " (filename, domain, note_type, activity_id, date, week,"
            "  has_insight_notes, frontmatter_json, written_at, mtime_ns,"
            "  subject_id)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                filename, domain, note_type, activity_id, date, week,
                int(has_insight_notes),
                _dumps(frontmatter),
                datetime.now(timezone.utc).isoformat(),
                mtime_ns,
                subject_id,
            ),
        )
        self.commit()

    def set_subject_id(self, filename: str, subject_id: str | None) -> None:
        """Update subject_id for an existing note (used by lazy rescan backfill)."""
        self.execute(
            "UPDATE vault_notes SET subject_id=? WHERE filename=?",
            (subject_id, filename),
        )
        self.commit()

    def set_has_insight_notes(self, filename: str):
        """Mark a note as having insight notes appended."""
        self.execute(
            "UPDATE vault_notes SET has_insight_notes=1 WHERE filename=?",
            (filename,),
        )
        self.commit()

    def set_mtime_ns(self, filename: str, mtime_ns: int):
        """Record the filesystem mtime observed on the last index update."""
        self.execute(
            "UPDATE vault_notes SET mtime_ns=? WHERE filename=?",
            (mtime_ns, filename),
        )
        self.commit()

    def get_mtime_ns(self, filename: str) -> int | None:
        row = self.fetchone(
            "SELECT mtime_ns FROM vault_notes WHERE filename=?",
            (filename,),
        )
        return row[0] if row and row[0] is not None else None

    def delete_note(self, filename: str):
        """Remove a note and all of its links/tags from the index."""
        self.execute("DELETE FROM vault_notes WHERE filename=?", (filename,))
        self.execute("DELETE FROM vault_links WHERE source=?", (filename,))
        self.execute("DELETE FROM vault_tags  WHERE filename=?", (filename,))
        self.commit()

    # ── Query (notes) ──

    def get_note(self, filename: str) -> dict | None:
        """Return index row for a specific file, or None."""
        row = self.fetchone(
            "SELECT filename, domain, note_type, activity_id, date, week,"
            "       has_insight_notes, frontmatter_json, written_at, subject_id"
            " FROM vault_notes WHERE filename=?",
            (filename,),
        )
        return self._row_to_dict(row) if row else None

    def list_notes(
        self,
        domain: str | None = None,
        note_type: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        week: str | None = None,
        has_insight_notes: bool | None = None,
        subject_id: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Filtered list of notes, newest first.

        ``subject_id`` filtering follows ADR 0009: when provided, returns
        rows whose subject_id matches OR is NULL (cross-subject themes
        and v6.1-era legacy notes both stay visible to a subject-filtered
        query). When absent, returns all rows.
        """
        clauses = []
        params: list = []

        if domain:
            clauses.append("domain=?")
            params.append(domain)
        if note_type:
            clauses.append("note_type=?")
            params.append(note_type)
        if date_from:
            clauses.append("date>=?")
            params.append(date_from)
        if date_to:
            clauses.append("date<=?")
            params.append(date_to)
        if week:
            clauses.append("week=?")
            params.append(week)
        if has_insight_notes is not None:
            clauses.append("has_insight_notes=?")
            params.append(int(has_insight_notes))
        if subject_id is not None:
            clauses.append("(subject_id=? OR subject_id IS NULL)")
            params.append(subject_id)

        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        params.append(limit)
        rows = self.fetchall(
            f"SELECT filename, domain, note_type, activity_id, date, week,"
            f"       has_insight_notes, frontmatter_json, written_at, subject_id"
            f" FROM vault_notes{where}"
            f" ORDER BY written_at DESC LIMIT ?",
            tuple(params),
        )
        return [self._row_to_dict(r) for r in rows]

    def list_all_filenames(self) -> list[str]:
        """Return every known filename in the index (for rescan reconciliation)."""
        rows = self.fetchall("SELECT filename FROM vault_notes")
        return [r[0] for r in rows]

    def get_anomalous_notes(
        self,
        anomaly_type: str | None = None,
        subject_id: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """
        Return run_report notes where anomaly_count > 0.
        Optionally filter to a specific anomaly_type by scanning frontmatter.
        ``subject_id`` filtering follows ADR 0009 (matching rows OR NULL).
        """
        clauses = ["note_type='run_report'",
                   "json_extract(frontmatter_json, '$.anomaly_count') > 0"]
        params: list = []
        if subject_id is not None:
            clauses.append("(subject_id=? OR subject_id IS NULL)")
            params.append(subject_id)
        params.append(limit)
        rows = self.fetchall(
            "SELECT filename, domain, note_type, activity_id, date, week,"
            "       has_insight_notes, frontmatter_json, written_at, subject_id"
            f" FROM vault_notes WHERE {' AND '.join(clauses)}"
            " ORDER BY date DESC LIMIT ?",
            tuple(params),
        )
        results = [self._row_to_dict(r) for r in rows]
        if anomaly_type:
            results = [
                r for r in results
                if anomaly_type in (r.get("frontmatter") or {}).get("anomaly_types", [])
            ]
        return results

    def count_notes(self, domain: str | None = None) -> int:
        where = " WHERE domain=?" if domain else ""
        params = (domain,) if domain else ()
        row = self.fetchone(f"SELECT COUNT(*) FROM vault_notes{where}", params)
        return row[0] if row else 0

    # ── Links ──

    def replace_links(
        self, source: str, links: list[tuple[str, str]]
    ) -> None:
        """
        Replace all outgoing links for ``source``.  Each entry is
        (target_filename, display_text); unresolved targets can use
        the raw wikilink text as both.
        """
        self.execute("DELETE FROM vault_links WHERE source=?", (source,))
        if links:
            self._get_conn().executemany(
                "INSERT OR REPLACE INTO vault_links (source, target, link_text) VALUES (?,?,?)",
                [(source, tgt, text) for (tgt, text) in links],
            )
        self.commit()

    def get_outgoing_links(self, source: str) -> list[dict]:
        rows = self.fetchall(
            "SELECT target, link_text FROM vault_links WHERE source=?",
            (source,),
        )
        return [{"target": r[0], "link_text": r[1]} for r in rows]

    def get_incoming_links(self, target: str) -> list[dict]:
        rows = self.fetchall(
            "SELECT source, link_text FROM vault_links WHERE target=?",
            (target,),
        )
        return [{"source": r[0], "link_text": r[1]} for r in rows]

    # ── Tags ──

    def replace_tags(self, filename: str, tags: list[str]) -> None:
        """Replace the tag set for ``filename``."""
        self.execute("DELETE FROM vault_tags WHERE filename=?", (filename,))
        deduped = sorted(set(t for t in tags if t))
        if deduped:
            self._get_conn().executemany(
                "INSERT OR REPLACE INTO vault_tags (filename, tag) VALUES (?,?)",
                [(filename, t) for t in deduped],
            )
        self.commit()

    def list_filenames_by_tag(self, tag: str) -> list[str]:
        rows = self.fetchall(
            "SELECT filename FROM vault_tags WHERE tag=? ORDER BY filename",
            (tag,),
        )
        return [r[0] for r in rows]

    def list_tags_for(self, filename: str) -> list[str]:
        rows = self.fetchall(
            "SELECT tag FROM vault_tags WHERE filename=? ORDER BY tag",
            (filename,),
        )
        return [r[0] for r in rows]

    # ── Themes ──

    def upsert_theme(
        self,
        slug: str,
        status: str,
        opened: str,
        last_updated: str,
        linked_runs: list | None = None,
        confidence: str | None = None,
        excerpt: str | None = None,
        subject_id: str | None = None,
    ) -> None:
        self.execute(
            "INSERT OR REPLACE INTO vault_themes"
            " (slug, status, opened, last_updated, linked_runs_json, confidence,"
            "  excerpt, subject_id)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (
                slug,
                status,
                opened,
                last_updated,
                _dumps(linked_runs or []),
                confidence,
                excerpt,
                subject_id,
            ),
        )
        self.commit()

    def get_theme(self, slug: str) -> dict | None:
        row = self.fetchone(
            "SELECT slug, status, opened, last_updated, linked_runs_json,"
            "       confidence, excerpt, subject_id"
            " FROM vault_themes WHERE slug=?",
            (slug,),
        )
        return self._theme_row(row) if row else None

    def get_theme_subject_id(self, slug: str) -> str | None:
        """Read just the subject_id of a theme (None if absent or theme missing).

        Used to enforce the ADR 0009 set-once invariant on theme subject:
        a vault_upsert_theme call passing a different non-null subject_id
        than the one already on disk is a hard error.
        """
        row = self.fetchone(
            "SELECT subject_id FROM vault_themes WHERE slug=?",
            (slug,),
        )
        return row[0] if row and row[0] is not None else None

    def list_themes(
        self,
        status: str | None = None,
        subject_id: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """List themes, newest first.

        ``subject_id`` filter follows ADR 0009: matches rows with that
        subject OR NULL (cross-subject hypotheses).
        """
        clauses = []
        params: list = []
        if status:
            clauses.append("status=?")
            params.append(status)
        if subject_id is not None:
            clauses.append("(subject_id=? OR subject_id IS NULL)")
            params.append(subject_id)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        params.append(limit)
        rows = self.fetchall(
            "SELECT slug, status, opened, last_updated, linked_runs_json,"
            "       confidence, excerpt, subject_id"
            f" FROM vault_themes{where}"
            " ORDER BY last_updated DESC LIMIT ?",
            tuple(params),
        )
        return [self._theme_row(r) for r in rows]

    def count_themes_by_status(self) -> dict[str, int]:
        """Return a {status: count} map across all themes."""
        rows = self.fetchall(
            "SELECT status, COUNT(*) FROM vault_themes GROUP BY status"
        )
        return {r[0]: r[1] for r in rows}

    def list_orphaned_moments(self) -> list[str]:
        """
        Return filenames of moment notes whose frontmatter's linked_themes
        is empty.  'Orphaned' = not associated with any theme.
        """
        rows = self.fetchall(
            "SELECT filename, frontmatter_json FROM vault_notes"
            " WHERE note_type='moment'"
        )
        out: list[str] = []
        for filename, fm_json in rows:
            try:
                fm = _loads(fm_json) if fm_json else {}
            except (ValueError, TypeError):
                continue
            if not (fm.get("linked_themes") or []):
                out.append(filename)
        return out

    def list_stale_themes(self, cutoff_date: str) -> list[str]:
        """
        Return slugs of themes whose last_updated predates ``cutoff_date``
        (inclusive of status == 'open' only; resolved/rejected don't rot).
        """
        rows = self.fetchall(
            "SELECT slug FROM vault_themes"
            " WHERE status='open' AND last_updated<?"
            " ORDER BY last_updated ASC",
            (cutoff_date,),
        )
        return [r[0] for r in rows]

    def delete_theme(self, slug: str) -> None:
        self.execute("DELETE FROM vault_themes WHERE slug=?", (slug,))
        self.commit()

    # close() is inherited from BaseStorage.

    # ── Internal ──

    @staticmethod
    def _row_to_dict(row: tuple) -> dict:
        filename, domain, note_type, activity_id, date, week, \
            has_insight_notes, frontmatter_json, written_at, subject_id = row
        fm = {}
        try:
            fm = _loads(frontmatter_json) if frontmatter_json else {}
        except (ValueError, TypeError) as exc:
            log.warning(
                f"Vault index has corrupt frontmatter_json for {filename}: {exc}. "
                f"Returning empty frontmatter; re-scan the vault to rebuild."
            )
        return {
            "filename": filename,
            "domain": domain,
            "note_type": note_type,
            "activity_id": activity_id,
            "date": date,
            "week": week,
            "has_insight_notes": bool(has_insight_notes),
            "frontmatter": fm,
            "written_at": written_at,
            "subject_id": subject_id,
        }

    @staticmethod
    def _theme_row(row: tuple) -> dict:
        slug, status, opened, last_updated, linked_runs_json, \
            confidence, excerpt, subject_id = row
        try:
            linked_runs = _loads(linked_runs_json) if linked_runs_json else []
        except (ValueError, TypeError) as exc:
            log.warning(
                f"Vault index has corrupt linked_runs_json for theme {slug!r}: {exc}. "
                f"Treating as empty."
            )
            linked_runs = []
        return {
            "slug": slug,
            "status": status,
            "opened": opened,
            "last_updated": last_updated,
            "linked_runs": linked_runs,
            "confidence": confidence,
            "excerpt": excerpt,
            "subject_id": subject_id,
        }
