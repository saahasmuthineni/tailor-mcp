"""
Inspector server tests — wire-level assertions against a live
ThreadingHTTPServer on an ephemeral 127.0.0.1 port.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from tailor.inspector.server import BIND_HOST, make_server


@pytest.fixture
def live_server(populated_data_dir: Path):
    server = make_server(populated_data_dir, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://{BIND_HOST}:{server.server_address[1]}"
    try:
        yield base
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_binds_localhost_only(populated_data_dir: Path) -> None:
    server = make_server(populated_data_dir, port=0)
    try:
        assert server.server_address[0] == "127.0.0.1"
    finally:
        server.server_close()


def test_get_root_renders_key_sections(live_server: str) -> None:
    with urllib.request.urlopen(f"{live_server}/", timeout=10) as resp:
        assert resp.status == 200
        assert resp.headers["Content-Type"].startswith("text/html")
        assert resp.headers["X-Content-Type-Options"] == "nosniff"
        assert "default-src 'none'" in resp.headers[
            "Content-Security-Policy"
        ]
        body = resp.read().decode("utf-8")
    for marker in ("READ-ONLY", "Gate activity", "Recent calls",
                   "Consent timeline", "Scrubber posture",
                   "Token estimates", "Vault index"):
        assert marker in body


def test_get_with_query_filters(live_server: str) -> None:
    url = f"{live_server}/?domain=csv_dir&limit=2"
    with urllib.request.urlopen(url, timeout=10) as resp:
        body = resp.read().decode("utf-8")
    assert "csv_summary_report" in body or "csv_raw_stream" in body
    assert "strava_downsampled_streams" not in body


def test_health_route(live_server: str) -> None:
    with urllib.request.urlopen(f"{live_server}/health", timeout=10) as resp:
        assert resp.status == 200
        payload = json.loads(resp.read())
    assert payload == {"status": "ok", "read_only": True}


def test_post_returns_405(live_server: str) -> None:
    req = urllib.request.Request(
        f"{live_server}/", data=b"x=1", method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req, timeout=10)
    assert exc_info.value.code == 405
    assert exc_info.value.headers["Allow"] == "GET"


def test_delete_and_put_return_405(live_server: str) -> None:
    for method in ("DELETE", "PUT"):
        req = urllib.request.Request(f"{live_server}/", method=method)
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req, timeout=10)
        assert exc_info.value.code == 405


def test_unknown_path_404(live_server: str) -> None:
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(f"{live_server}/admin", timeout=10)
    assert exc_info.value.code == 404


def test_databases_untouched_by_requests(
    live_server: str, populated_data_dir: Path,
) -> None:
    """Serving requests must not change the database files at all."""
    audit = populated_data_dir / "audit.db"
    before = audit.read_bytes()
    for _ in range(3):
        urllib.request.urlopen(f"{live_server}/", timeout=10).read()
    assert audit.read_bytes() == before
