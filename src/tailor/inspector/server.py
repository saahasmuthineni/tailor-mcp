"""
Inspector server — stdlib http.server plumbing (ADR 0043).
===========================================================
Serves the rendered page on hard-coded ``127.0.0.1``. There is no flag
to widen the bind address — networked/multi-user inspection is ROADMAP
Phase 5C territory behind a separate ADR.

Route surface, complete:

- ``GET /``        → the page (query params filter the audit window)
- ``GET /health``  → ``{"status": "ok", "read_only": true}``
- any other path   → 404
- any non-GET verb → 405 (no write route exists, by construction)

Every response carries a deny-all Content-Security-Policy (inline
styles only) and ``X-Content-Type-Options: nosniff`` — defense in
depth behind the renderer's escaping.
"""

from __future__ import annotations

import json
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .queries import collect_page_model, parse_filters
from .render import render_page

# Hard-coded per ADR 0043 — never widened, no override flag.
BIND_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

_SECURITY_HEADERS = (
    ("Content-Security-Policy",
     "default-src 'none'; style-src 'unsafe-inline'"),
    ("X-Content-Type-Options", "nosniff"),
    ("Cache-Control", "no-store"),
)


def build_page(data_dir: Path, query_string: str = "",
               *, auto_refresh: bool = True) -> str:
    """Collect the model and render — shared by serve and export."""
    filters = parse_filters(parse_qs(query_string))
    model = collect_page_model(data_dir, filters)
    return render_page(model, auto_refresh=auto_refresh)


class InspectorHandler(BaseHTTPRequestHandler):
    """GET-only handler. The server instance carries ``data_dir``."""

    server_version = "TailorInspector"
    protocol_version = "HTTP/1.1"

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for name, value in _SECURITY_HEADERS:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 — http.server naming contract
        split = urlsplit(self.path)
        if split.path == "/health":
            body = json.dumps({"status": "ok", "read_only": True})
            self._send(200, "application/json", body.encode("utf-8"))
            return
        if split.path != "/":
            self._send(404, "text/plain; charset=utf-8", b"not found")
            return
        page = build_page(self.server.data_dir, split.query)  # type: ignore[attr-defined]
        self._send(200, "text/html; charset=utf-8", page.encode("utf-8"))

    def _method_not_allowed(self) -> None:
        # The inspector has no write route; 405 every non-GET verb so
        # the no-write boundary is visible on the wire, not just in
        # the absence of handlers.
        self.send_response(405)
        self.send_header("Allow", "GET")
        self.send_header("Content-Length", "0")
        for name, value in _SECURITY_HEADERS:
            self.send_header(name, value)
        self.end_headers()

    do_POST = _method_not_allowed  # noqa: N815 — http.server naming contract
    do_PUT = _method_not_allowed  # noqa: N815
    do_DELETE = _method_not_allowed  # noqa: N815
    do_PATCH = _method_not_allowed  # noqa: N815
    do_HEAD = _method_not_allowed  # noqa: N815

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        # Quiet by default; per-request access lines are noise for a
        # localhost single-operator page.
        pass


class InspectorServer(ThreadingHTTPServer):
    """ThreadingHTTPServer that carries the data dir for the handler."""

    daemon_threads = True

    def __init__(self, data_dir: Path, port: int):
        self.data_dir = data_dir
        super().__init__((BIND_HOST, port), InspectorHandler)
        # Belt-and-braces assertion of the ADR 0043 localhost boundary:
        # if anything ever rebinds this server, fail loudly.
        bound_host = self.server_address[0]
        if bound_host != BIND_HOST:
            raise AssertionError(
                f"inspector must bind {BIND_HOST}, got {bound_host}"
            )


def make_server(data_dir: Path, port: int = 0) -> InspectorServer:
    """Construct (but do not run) the server. ``port=0`` → ephemeral."""
    return InspectorServer(data_dir, port)


def run_inspector(data_dir: Path, *, port: int = DEFAULT_PORT,
                  open_browser: bool = True) -> int:
    """Serve until interrupted. Returns a process exit code."""
    try:
        server = make_server(data_dir, port)
    except OSError as exc:
        print(
            f"Could not bind http://{BIND_HOST}:{port} — {exc}. "
            f"Is another inspector running? Try --port.",
            file=sys.stderr,
        )
        return 1
    actual_port = server.server_address[1]
    url = f"http://{BIND_HOST}:{actual_port}/"
    print(f"Tailor Inspector (read-only) serving on {url}")
    print("Press Ctrl-C to stop.")
    if open_browser:
        # Off-thread so a slow browser launch never blocks the first
        # request; failures are non-fatal (headless boxes).
        threading.Timer(0.2, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
    return 0


def export_page(data_dir: Path, out_path: Path) -> int:
    """Render once to a static, self-contained HTML file and return 0.

    The CI-friendly and screenshot path (``tailor inspect --export``).
    """
    out_path = out_path.expanduser()
    page = build_page(data_dir, auto_refresh=False)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(page, encoding="utf-8")
    print(f"Wrote {out_path}")
    # Retention contract per ADR 0043 / ADR 0040 § Amendment shape: the
    # export is an operator-created artifact outside any purge path.
    print(
        "Note: this export contains audit metadata (tool calls, "
        "outcomes, entity IDs); it is yours to manage and is not "
        "removed by any Tailor purge or consent-revocation path."
    )
    return 0
