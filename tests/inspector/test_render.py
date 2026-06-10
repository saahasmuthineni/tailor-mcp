"""
Inspector renderer tests — escaping, redaction, badges, caveats.

The renderer is pure (model dict in, HTML string out), so these tests
need no HTTP server and no real databases beyond the query fixtures.
"""

from __future__ import annotations

from pathlib import Path

from tailor.inspector.queries import Filters, collect_page_model
from tailor.inspector.render import redact_home, render_page


def _page(data_dir: Path, filters: Filters | None = None, **kw) -> str:
    model = collect_page_model(data_dir, filters or Filters())
    return render_page(model, **kw)


def test_script_in_params_renders_inert(populated_data_dir: Path) -> None:
    """Audit params are LLM-authored text — never an XSS vector."""
    page = _page(populated_data_dir)
    assert "<script>" not in page
    assert "&lt;script&gt;" in page


def test_home_redaction_on_params_and_error(
    populated_data_dir: Path,
) -> None:
    home = str(Path.home())
    page = _page(populated_data_dir)
    # The fixture wrote Path.home()-based paths into params AND error.
    assert home not in page
    assert "~/data" in page or "~\\data" in page or "~%5C" in page


def test_data_dir_header_is_home_redacted(tmp_path, monkeypatch) -> None:
    """The data-dir line itself redacts when under the real home."""
    # Render against a model whose data_dir string embeds home.
    from tailor.inspector.queries import Filters as F
    model = {
        "version": "0.0.0-test",
        "generated_at": "2026-06-10T00:00:00+00:00",
        "data_dir": str(Path.home() / ".tailor" / "data"),
        "filters": F(),
        "audit": {
            "path": "x", "exists": False, "error": None,
            "table_missing": False, "legacy_subject_id": False,
            "wal_pending": False, "row_count": 0, "outcome_counts": [],
            "recent_calls": [], "consent_events": [], "scrubbers": [],
            "child_scrubbers": [], "token_by_domain": [],
            "size_bytes": None, "mtime": None,
        },
        "vault": {
            "path": "x", "exists": False, "error": None,
            "table_missing": False, "wal_pending": False,
            "note_count": 0, "theme_count": 0, "notes_by_type": [],
            "themes_by_status": [], "latest_written_at": None,
            "size_bytes": None, "mtime": None,
        },
    }
    page = render_page(model)
    assert str(Path.home()) not in page
    assert "~/.tailor" in page or "~\\.tailor" in page


def test_outcome_badges_and_gate_explanations(
    populated_data_dir: Path,
) -> None:
    page = _page(populated_data_dir)
    for outcome in ("SUCCESS", "COST_GATE_TRIGGERED", "CONSENT_BLOCKED",
                    "ERROR"):
        assert outcome in page
    # Plain-language sentence under each refusal class present in the
    # window; CIRCUIT_OPEN did not occur, so its sentence is absent.
    assert "cost gate refused" in page
    assert "consent gate refused" in page
    assert "circuit breaker refused" not in page
    assert 'class="badge refusal"' in page


def test_derived_consent_caveat_present(populated_data_dir: Path) -> None:
    page = _page(populated_data_dir)
    assert "Derived from audit events" in page
    assert "live state lives in the running server" in page


def test_noop_scrubber_warning(populated_data_dir: Path) -> None:
    page = _page(populated_data_dir)
    assert "NO SCRUBBING POLICY" in page
    assert "noop" in page
    assert "redcap_metadata_flags" in page


def test_read_only_badge_and_footer(populated_data_dir: Path) -> None:
    page = _page(populated_data_dir)
    assert "READ-ONLY" in page
    assert "read-only mode" in page
    assert "use Claude Desktop chat or the" in page


def test_all_eight_sections_render(populated_data_dir: Path) -> None:
    page = _page(populated_data_dir)
    for heading in ("Gate activity", "Recent calls", "Consent timeline",
                    "Scrubber posture", "Token estimates", "Vault index"):
        assert heading in page
    assert "Tailor Inspector" in page  # header
    assert "<footer>" in page  # footer


def test_empty_states_are_honest(empty_data_dir: Path) -> None:
    page = _page(empty_data_dir)
    assert "No audit database yet" in page
    assert "tailor serve" in page
    assert "No vault index yet" in page
    # No traceback-shaped content on the empty path.
    assert "Traceback" not in page


def test_auto_refresh_served_not_exported(populated_data_dir: Path) -> None:
    served = _page(populated_data_dir, auto_refresh=True)
    exported = _page(populated_data_dir, auto_refresh=False)
    assert 'http-equiv="refresh"' in served
    assert 'http-equiv="refresh"' not in exported


def test_wal_caveat_renders_when_pending(populated_data_dir: Path) -> None:
    """A non-empty -wal sidecar surfaces the staleness caveat."""
    wal = populated_data_dir / "audit.db-wal"
    wal.write_bytes(b"x" * 32)
    try:
        page = _page(populated_data_dir)
        assert "may not yet be reflected" in page
    finally:
        wal.unlink()


def test_legacy_caveat_renders(legacy_audit_db: Path) -> None:
    page = _page(legacy_audit_db.parent)
    assert "predates the" in page
    assert "subject_id" in page


def test_filter_notes_render(populated_data_dir: Path) -> None:
    from tailor.inspector.queries import parse_filters
    f = parse_filters({"since": ["garbage"]})
    model = collect_page_model(populated_data_dir, f)
    page = render_page(model)
    assert "Ignored invalid since" in page


def test_redact_home_substring_and_identity() -> None:
    home = str(Path.home())
    assert redact_home(f"prefix {home}/x suffix") == "prefix ~/x suffix"
    assert redact_home("/somewhere/else") == "/somewhere/else"
    assert redact_home("") == ""
    assert redact_home(None) is None  # identity on non-str


def test_redact_home_mixed_separators() -> None:
    """Cross-platform path separators do not defeat the redaction —
    a home path embedded with the *other* OS's separator style still
    collapses (Safe Harbor posture; phi-irb border note)."""
    home = str(Path.home())
    flipped = (
        home.replace("/", "\\") if "/" in home else home.replace("\\", "/")
    )
    result = redact_home(f"saw {flipped}\\data in params")
    assert flipped not in result
    assert "~" in result
