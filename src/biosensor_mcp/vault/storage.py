"""
Vault Storage — SQLite Index for Vault Notes
=============================================
Tracks every note written by VaultWriter so VaultLayer can
query by domain, type, date, week, or anomaly status without
scanning the filesystem.

Extends framework BaseStorage — same threading model, same
connection lifecycle (WAL mode, thread-local connections).
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..framework.storage import BaseStorage
from ..framework.middleware import _dumps, _loads


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
                written_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_vault_domain ON vault_notes(domain);
            CREATE INDEX IF NOT EXISTS idx_vault_date   ON vault_notes(date);
            CREATE INDEX IF NOT EXISTS idx_vault_type   ON vault_notes(note_type);
            CREATE INDEX IF NOT EXISTS idx_vault_week   ON vault_notes(week);
        """

    # ── Write ──

    def upsert_note(
        self,
        filename: str,
        domain: str,
        note_type: str,
        frontmatter: dict,
        *,
        activity_id: Optional[int] = None,
        date: Optional[str] = None,
        week: Optional[str] = None,
        has_insight_notes: bool = False,
    ):
        """Insert or replace a note index entry."""
        self.execute(
            "INSERT OR REPLACE INTO vault_notes"
            " (filename, domain, note_type, activity_id, date, week,"
            "  has_insight_notes, frontmatter_json, written_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (
                filename, domain, note_type, activity_id, date, week,
                int(has_insight_notes),
                _dumps(frontmatter),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self.commit()

    def set_has_insight_notes(self, filename: str):
        """Mark a note as having insight notes appended."""
        self.execute(
            "UPDATE vault_notes SET has_insight_notes=1 WHERE filename=?",
            (filename,),
        )
        self.commit()

    # ── Query ──

    def get_note(self, filename: str) -> Optional[dict]:
        """Return index row for a specific file, or None."""
        row = self.fetchone(
            "SELECT filename, domain, note_type, activity_id, date, week,"
            "       has_insight_notes, frontmatter_json, written_at"
            " FROM vault_notes WHERE filename=?",
            (filename,),
        )
        return self._row_to_dict(row) if row else None

    def list_notes(
        self,
        domain: Optional[str] = None,
        note_type: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        week: Optional[str] = None,
        has_insight_notes: Optional[bool] = None,
        limit: int = 50,
    ) -> list[dict]:
        """Filtered list of notes, newest first."""
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

        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        params.append(limit)
        rows = self.fetchall(
            f"SELECT filename, domain, note_type, activity_id, date, week,"
            f"       has_insight_notes, frontmatter_json, written_at"
            f" FROM vault_notes{where}"
            f" ORDER BY written_at DESC LIMIT ?",
            tuple(params),
        )
        return [self._row_to_dict(r) for r in rows]

    def get_anomalous_notes(
        self, anomaly_type: Optional[str] = None, limit: int = 50
    ) -> list[dict]:
        """
        Return run_report notes where anomaly_count > 0.
        Optionally filter to a specific anomaly_type by scanning frontmatter.
        """
        rows = self.fetchall(
            "SELECT filename, domain, note_type, activity_id, date, week,"
            "       has_insight_notes, frontmatter_json, written_at"
            " FROM vault_notes"
            " WHERE note_type='run_report'"
            "   AND json_extract(frontmatter_json, '$.anomaly_count') > 0"
            " ORDER BY date DESC LIMIT ?",
            (limit,),
        )
        results = [self._row_to_dict(r) for r in rows]
        if anomaly_type:
            results = [
                r for r in results
                if anomaly_type in (r.get("frontmatter") or {}).get("anomaly_types", [])
            ]
        return results

    def count_notes(self, domain: Optional[str] = None) -> int:
        where = " WHERE domain=?" if domain else ""
        params = (domain,) if domain else ()
        row = self.fetchone(f"SELECT COUNT(*) FROM vault_notes{where}", params)
        return row[0] if row else 0

    def close(self):
        """Close the thread-local connection (required on Windows to release WAL lock)."""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    # ── Internal ──

    @staticmethod
    def _row_to_dict(row: tuple) -> dict:
        filename, domain, note_type, activity_id, date, week, \
            has_insight_notes, frontmatter_json, written_at = row
        fm = {}
        try:
            fm = _loads(frontmatter_json) if frontmatter_json else {}
        except Exception:
            pass
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
        }
