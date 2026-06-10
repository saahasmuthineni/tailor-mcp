"""
Tailor Inspector — read-only trust-visibility surface (ADR 0043).
=================================================================
``tailor inspect`` serves one localhost HTML page rendering what the
framework actually did — gate activity, recent audit rows, consent
events, scrubber posture, token estimates, vault index counts — read
straight from ``audit.db`` and ``vault.db`` through a channel the
model does not mediate.

The hard boundary, per ADR 0043 ("inspector, not application"):

- Never writes: SQLite opened read-only (URI ``mode=ro``); no
  non-GET route exists (anything but GET returns 405).
- Never binds beyond localhost: hard-coded ``127.0.0.1``.
- Never grows controls: no consent toggles, no config edits, no
  purge buttons. Acting on what you see happens through the existing
  surfaces (Claude Desktop chat, the ``tailor`` CLI).
- Adds no dependencies: stdlib only (``http.server``, ``sqlite3``,
  ``html``); inline styles; no JavaScript.

This package is a standalone reader of on-disk state. It never
registers with the router, never appears in ``tools/list``, and is
deliberately outside the security pipeline (it amends nothing in
ADR 0012 — see ADR 0043 § "outside the pipeline").
"""

from .queries import Filters, collect_page_model, connect_ro
from .render import render_page
from .server import export_page, make_server, run_inspector

__all__ = [
    "Filters",
    "collect_page_model",
    "connect_ro",
    "render_page",
    "run_inspector",
    "make_server",
    "export_page",
]
