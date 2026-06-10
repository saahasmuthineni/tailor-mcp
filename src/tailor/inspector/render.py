"""
Inspector renderer — page model dicts → one HTML string.
=========================================================
Pure: data in, string out. All escaping and redaction happen here, at
the render boundary, so ``queries.py`` stays a faithful reader and no
un-escaped DB content can reach the browser by construction.

Two defenses applied to every DB-sourced string (ADR 0043):

- ``html.escape`` — audit ``params`` are LLM-authored,
  attacker-influenceable text; the inspector must not be an XSS
  vector. The server additionally sets a deny-all CSP.
- Home-redaction — every rendered string passes through
  :func:`redact_home`, collapsing ``Path.home()`` to ``~`` wherever it
  appears (substring, both separator styles). Same HIPAA Safe Harbor
  §164.514(b)(2)(i)(R) rationale as the v6.10.2 SetupHelpLayer and
  v8.0.0 SetupLayer precedents: the browser is a new egress surface
  and username-bearing paths stay off it.

No JavaScript; inline styles only; auto-refresh (served mode only)
via ``<meta http-equiv="refresh">``.
"""

from __future__ import annotations

import html
from pathlib import Path

from .queries import Filters, outcome_class

REFRESH_SECONDS = 5

# One plain-language sentence per refusal class, rendered under the
# gate-activity badges. Phrasing is self-contained — the page must not
# depend on any companion doc existing on the deployment.
GATE_EXPLANATIONS = {
    "CONSENT_BLOCKED": (
        "The consent gate refused the call: this domain requires "
        "per-session consent before Tier-2+ data moves, and consent "
        "was not on record."
    ),
    "COST_GATE_TRIGGERED": (
        "The cost gate refused the call: the pre-estimated token cost "
        "exceeded the configured ceiling, before any data was read."
    ),
    "CIRCUIT_OPEN": (
        "The circuit breaker refused the call: this domain failed "
        "repeatedly in a row and was temporarily blocked while it "
        "cools down."
    ),
    "PARAM_INVALID": (
        "Parameter validation refused the call before any work was "
        "done: a parameter failed its declared type, range, or "
        "pattern check."
    ),
}

_CSS = """
body { font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;
       margin: 0; background: #f6f7f9; color: #1c2733; }
main { max-width: 1100px; margin: 0 auto; padding: 1rem 1.5rem 3rem; }
h1 { font-size: 1.35rem; margin: .4rem 0; }
h2 { font-size: 1.05rem; margin: 1.6rem 0 .5rem; border-bottom: 1px solid #d6dce3;
     padding-bottom: .25rem; }
table { border-collapse: collapse; width: 100%; font-size: .85rem;
        background: #fff; }
th, td { border: 1px solid #d6dce3; padding: .3rem .5rem; text-align: left;
         vertical-align: top; }
th { background: #eef1f5; }
.badge { display: inline-block; padding: .1rem .55rem; border-radius: .8rem;
         font-size: .78rem; font-weight: 600; margin: .1rem .15rem; }
.badge.success { background: #e2f4e6; color: #176a2c; }
.badge.refusal { background: #fdeecd; color: #8a5a00; }
.badge.error   { background: #fbdcdc; color: #9c1f1f; }
.badge.other   { background: #e4e8ee; color: #3c4757; }
.badge.readonly { background: #dbe9fb; color: #134a8c; border: 1px solid #134a8c; }
.badge.warn { background: #9c1f1f; color: #fff; }
.muted { color: #5b6877; font-size: .82rem; }
.caveat { background: #fff8e6; border: 1px solid #e3c878; padding: .5rem .7rem;
          border-radius: .3rem; font-size: .84rem; margin: .4rem 0; }
.errbox { background: #fbdcdc; border: 1px solid #c96a6a; padding: .5rem .7rem;
          border-radius: .3rem; font-size: .84rem; margin: .4rem 0; }
.empty { background: #eef1f5; border: 1px dashed #b7c0cb; padding: .8rem;
         border-radius: .3rem; font-size: .88rem; }
details { margin: .1rem 0; }
details pre { white-space: pre-wrap; word-break: break-all; margin: .2rem 0;
              background: #f2f4f7; padding: .35rem; font-size: .78rem; }
footer { margin-top: 2.5rem; border-top: 1px solid #d6dce3; padding-top: .8rem;
         font-size: .82rem; color: #5b6877; }
"""


def redact_home(value: str) -> str:
    """Collapse every occurrence of ``Path.home()`` in ``value`` to ``~``.

    Substring (not just prefix) replacement, against both separator
    styles, so home paths embedded inside params JSON are caught too.
    Identity on failure; never raises.
    """
    if not isinstance(value, str) or not value:
        return value
    try:
        home = str(Path.home())
    except (RuntimeError, OSError):
        return value
    if not home or home in ("/", "\\"):
        return value
    for variant in {home, home.replace("\\", "/"), home.replace("/", "\\")}:
        stripped = variant.rstrip("/\\")
        if stripped:
            value = value.replace(stripped, "~")
    return value


def _e(value) -> str:
    """Render-safe text: stringify → home-redact → HTML-escape."""
    if value is None:
        return ""
    return html.escape(redact_home(str(value)), quote=True)


def _badge(outcome: str) -> str:
    return (
        f'<span class="badge {outcome_class(outcome)}">{_e(outcome)}</span>'
    )


def _details(label: str, content) -> str:
    if content in (None, ""):
        return '<span class="muted">—</span>'
    return (
        f"<details><summary>{_e(label)}</summary>"
        f"<pre>{_e(content)}</pre></details>"
    )


def _size(n) -> str:
    if n is None:
        return "?"
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


def _wal_caveat(section: dict) -> str:
    if not section.get("wal_pending"):
        return ""
    return (
        '<div class="caveat">A write-ahead-log sidecar with pending '
        "frames sits next to this database — recent activity may not "
        "yet be reflected here (the server is mid-write, or was not "
        "cleanly shut down). Refresh after the server checkpoints.</div>"
    )


def _errbox(section: dict) -> str:
    if not section.get("error"):
        return ""
    return (
        '<div class="errbox">Could not read this database right now: '
        f'{_e(section["error"])}. The database may be mid-checkpoint; '
        "refresh shortly. The inspector holds no lock and retries on "
        "the next request.</div>"
    )


def _header(model: dict) -> str:
    audit, vault = model["audit"], model["vault"]
    rows = []
    for label, s in (("audit.db", audit), ("vault.db", vault)):
        state = (
            f"{_size(s['size_bytes'])}, modified {_e(s['mtime'])}"
            if s["exists"] else "not present"
        )
        rows.append(f"<li><strong>{label}</strong> — {state}</li>")
    return f"""<h1>Tailor Inspector
  <span class="badge readonly">READ-ONLY</span></h1>
<p class="muted">tailor-mcp v{_e(model['version'])} &middot;
data dir <code>{_e(model['data_dir'])}</code> &middot;
generated {_e(model['generated_at'])} &middot;
{audit['row_count']} audit rows total</p>
<ul class="muted">{''.join(rows)}</ul>"""


def _filters_note(filters: Filters) -> str:
    parts = []
    for name in ("domain", "outcome", "entity_id", "since"):
        value = getattr(filters, name)
        if value:
            parts.append(f"{name}={value}")
    active = (
        "Filters: " + ", ".join(parts) if parts
        else "No filters active (add ?domain= / ?outcome= / "
             "?entity_id= / ?since= / ?limit= to the URL)."
    )
    notes = "".join(
        f'<div class="caveat">{_e(n)}</div>' for n in filters.notes
    )
    return f'<p class="muted">{_e(active)}</p>{notes}'


def _gate_activity(audit: dict) -> str:
    if not audit["outcome_counts"]:
        return (
            '<div class="empty">No calls in this window — when the '
            "framework dispatches tool calls they will appear here, "
            "grouped by gate outcome.</div>"
        )
    badges = "".join(
        f'{_badge(c["outcome"] or "")}'
        f'<span class="muted"> ×{c["count"]}</span> '
        for c in audit["outcome_counts"]
    )
    # Normalize None defensively — the live schema declares outcome
    # NOT NULL, but the inspector must not crash on a foreign or
    # hand-edited database (PR #148 review finding).
    seen = [(c["outcome"] or "") for c in audit["outcome_counts"]]
    seen_bases = {
        o[:-len("_INTERNAL")] if o.endswith("_INTERNAL") else o
        for o in seen
    }
    explanations = "".join(
        f"<li><strong>{_e(name)}</strong> — {_e(text)}</li>"
        for name, text in GATE_EXPLANATIONS.items()
        if name in seen_bases
    )
    expl_html = f"<ul class='muted'>{explanations}</ul>" if explanations else ""
    return f"<p>{badges}</p>{expl_html}"


def _recent_calls(audit: dict) -> str:
    calls = audit["recent_calls"]
    if not calls:
        return '<div class="empty">No calls match the current window.</div>'
    head = (
        "<tr><th>id</th><th>timestamp</th><th>domain</th><th>tool</th>"
        "<th>tier</th><th>outcome</th><th>ms</th><th>tokens</th>"
        "<th>entity_id</th><th>scrubber</th><th>params</th>"
        "<th>error</th></tr>"
    )
    body = []
    for c in calls:
        scrubber = _e(c["scrubber_id"])
        if c["child_scrubber_id"]:
            scrubber += f' <span class="muted">+ {_e(c["child_scrubber_id"])}</span>'
        body.append(
            f"<tr><td>{_e(c['id'])}</td><td>{_e(c['timestamp'])}</td>"
            f"<td>{_e(c['domain'])}</td><td>{_e(c['tool_name'])}</td>"
            f"<td>{_e(c['tier'])}</td><td>{_badge(c['outcome'] or '')}</td>"
            f"<td>{_e(c['duration_ms'])}</td><td>{_e(c['token_estimate'])}</td>"
            f"<td>{_e(c['entity_id'])}</td><td>{scrubber}</td>"
            f"<td>{_details('params', c['params'])}</td>"
            f"<td>{_details('error', c['error'])}</td></tr>"
        )
    return f"<table>{head}{''.join(body)}</table>"


def _consent_timeline(audit: dict) -> str:
    caveat = (
        '<div class="caveat">Derived from audit events — live state '
        "lives in the running server&#x27;s session. This timeline shows "
        "when consent was granted and revoked on the record, not the "
        "authoritative current state.</div>"
    )
    events = audit["consent_events"]
    if not events:
        return caveat + (
            '<div class="empty">No consent approve/revoke events in '
            "this window.</div>"
        )
    rows = "".join(
        f"<tr><td>{_e(ev['timestamp'])}</td><td>{_e(ev['domain'])}</td>"
        f"<td>{_e(ev['action'])}</td><td>{_badge(ev['outcome'] or '')}</td>"
        f"<td>{_e(ev['tool_name'])}</td></tr>"
        for ev in events
    )
    return caveat + (
        "<table><tr><th>timestamp</th><th>domain</th><th>action</th>"
        f"<th>outcome</th><th>tool</th></tr>{rows}</table>"
    )


def _scrubber_posture(audit: dict) -> str:
    rows = audit["scrubbers"]
    if not rows:
        return (
            '<div class="empty">No scrubber identities recorded in '
            "this window.</div>"
        )
    noop_warning = ""
    if any(r["scrubber_id"] == "noop" for r in rows):
        noop_warning = (
            '<div class="errbox"><span class="badge warn">NO SCRUBBING '
            "POLICY</span> The default no-op scrubber "
            "(<code>scrubber_id=noop</code>) appears in this window: no "
            "institutional PHI-scrubbing policy is configured at the "
            "framework seam (ADR 0003). Calls were NOT scrubbed by the "
            "framework-level seam.</div>"
        )
    framework = "".join(
        f'{_badge(r["scrubber_id"] or "(null)")}'
        f'<span class="muted"> ×{r["count"]}</span> '
        for r in rows
    )
    child = "".join(
        f'{_badge(r["scrubber_id"])}'
        f'<span class="muted"> ×{r["count"]}</span> '
        for r in audit["child_scrubbers"]
    )
    child_html = (
        f"<p>Child-level scrubbers (ADR 0003 two-seam model): {child}</p>"
        if child else
        '<p class="muted">No child-level scrubber rows in this window.</p>'
    )
    return f"{noop_warning}<p>Framework seam: {framework}</p>{child_html}"


def _token_estimates(audit: dict) -> str:
    rows = audit["token_by_domain"]
    if not rows:
        return '<div class="empty">No calls in this window.</div>'
    body = "".join(
        f"<tr><td>{_e(r['domain'])}</td><td>{_e(r['tokens'])}</td>"
        f"<td>{_e(r['calls'])}</td></tr>"
        for r in rows
    )
    return (
        '<p class="muted">Sums of per-call estimates recorded at call '
        "time — not a billing record.</p>"
        "<table><tr><th>domain</th><th>token estimate (sum)</th>"
        f"<th>calls</th></tr>{body}</table>"
    )


def _vault_stats(vault: dict) -> str:
    if not vault["exists"]:
        return (
            '<div class="empty">No vault index yet — vault integration '
            "is opt-in (add <code>vault_path</code> to "
            "user_config.json).</div>"
        )
    if vault.get("table_missing"):
        return (
            '<div class="empty">vault.db exists but carries no notes '
            "index yet.</div>"
        )
    parts = [_errbox(vault), _wal_caveat(vault)]
    notes = "".join(
        f"<tr><td>{_e(r['note_type'])}</td><td>{_e(r['count'])}</td></tr>"
        for r in vault["notes_by_type"]
    )
    themes = "".join(
        f"<tr><td>{_e(r['status'])}</td><td>{_e(r['count'])}</td></tr>"
        for r in vault["themes_by_status"]
    )
    parts.append(
        f"<p class='muted'>{vault['note_count']} notes indexed, "
        f"{vault['theme_count']} themes; most recent write "
        f"{_e(vault['latest_written_at']) or '—'}. Index counts only — "
        "note bodies are never rendered here (ADR 0033 Ledger/Wardrobe "
        "asymmetry).</p>"
    )
    if notes:
        parts.append(
            "<table><tr><th>note type</th><th>count</th></tr>"
            f"{notes}</table>"
        )
    if themes:
        parts.append(
            "<table><tr><th>theme status</th><th>count</th></tr>"
            f"{themes}</table>"
        )
    return "".join(parts)


def _audit_body(audit: dict, filters: Filters) -> str:
    """Sections 2–6, or the honest empty/error states."""
    if not audit["exists"]:
        return (
            '<div class="empty">No audit database yet — has '
            "<code>tailor serve</code> run? Every tool call the router "
            "dispatches lands in <code>audit.db</code>; once the server "
            "has handled a call, this page renders it.</div>"
        )
    if audit.get("table_missing"):
        return (
            '<div class="empty">audit.db exists but the audit_log '
            "table has not been created yet — has "
            "<code>tailor serve</code> finished booting?</div>"
        )
    legacy = ""
    if audit.get("legacy_subject_id"):
        legacy = (
            '<div class="caveat">This audit database predates the '
            "v9.0.0 <code>subject_id → entity_id</code> rename (the "
            "migration runs on the next <code>tailor serve</code> "
            "boot). Rows are shown with the legacy column aliased.</div>"
        )
    return (
        _errbox(audit) + _wal_caveat(audit) + legacy
        + _filters_note(filters)
        + "<h2>Gate activity</h2>" + _gate_activity(audit)
        + "<h2>Recent calls</h2>" + _recent_calls(audit)
        + "<h2>Consent timeline</h2>" + _consent_timeline(audit)
        + "<h2>Scrubber posture</h2>" + _scrubber_posture(audit)
        + "<h2>Token estimates</h2>" + _token_estimates(audit)
    )


def render_page(model: dict, *, auto_refresh: bool = True) -> str:
    """The one page: eight sections, served and export mode alike."""
    audit = model["audit"]
    filters: Filters = model["filters"]
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tailor Inspector</title>
{f'<meta http-equiv="refresh" content="{REFRESH_SECONDS}">' if auto_refresh
 else '<!-- static export: auto-refresh omitted -->'}
<style>{_CSS}</style>
</head>
<body>
<main>
{_header(model)}
{_audit_body(audit, filters)}
<h2>Vault index</h2>
{_vault_stats(model['vault'])}
<footer>
The inspector is read-only; it opened the databases in read-only mode
and exposes no write or control affordance. To act on anything you see,
use Claude Desktop chat or the <code>tailor</code> CLI. The consent
gates, cost gates, and scrubber seams rendered above are enforced
server-side by the router pipeline — this page is the independent,
model-unmediated view of that enforcement (ADR 0043).
</footer>
</main>
</body>
</html>
"""
