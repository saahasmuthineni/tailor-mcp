"""
Strava OAuth Setup Wizard
=========================
Runs a temporary localhost server to capture the OAuth callback.

Bundled inside the package so it works after pip install:
    python -m strava_coach setup     # via CLI entry point
    python -m strava_coach.wizard    # direct invocation

Previously lived at the project root (setup_wizard.py), which broke
for pip-installed users because the path walked three levels above
__file__ and landed in site-packages/, not the project directory.
"""

import http.server
import json
import os
import sys
import threading
import urllib.parse
import webbrowser
from pathlib import Path

import requests

CONFIG_DIR = Path(os.environ.get("STRAVA_CONFIG_DIR", Path.home() / ".strava-coach"))
TOKEN_FILE = CONFIG_DIR / "tokens.json"
CALLBACK_PORT = 8189
REDIRECT_URI = f"http://localhost:{CALLBACK_PORT}/callback"
SCOPES = "read,activity:read_all"


def _secure_token_file(path: Path) -> None:
    """
    Restrict token file to owner-read-only.

    On Unix: uses os.chmod(0o600) — removes group/other permissions.
    On Windows: os.chmod() only controls the read-only attribute and
    does NOT apply Unix ACL bits. Instead we use icacls to grant access
    only to the current user and strip inherited Everyone permissions.
    """
    if sys.platform == "win32":
        import subprocess
        username = os.environ.get("USERNAME", "")
        # Remove inherited permissions, grant current user full control
        subprocess.run(
            ["icacls", str(path), "/inheritance:r",
             "/grant:r", f"{username}:F"],
            capture_output=True, check=False,
        )
    else:
        os.chmod(path, 0o600)


def _describe_permissions(path: Path) -> str:
    """Return a human-readable description of the file's effective permissions."""
    if sys.platform == "win32":
        return "owner-only (Windows ACL via icacls)"
    else:
        mode = oct(os.stat(path).st_mode)[-3:]
        return f"owner-read-only ({mode})"


def main():
    print("\n  Strava OAuth Setup Wizard")
    print("  " + "=" * 30 + "\n")

    # Get credentials
    client_id = input("  Strava Client ID: ").strip()
    client_secret = input("  Strava Client Secret: ").strip()

    if not client_id or not client_secret:
        print("  ❌ Both Client ID and Client Secret are required.")
        sys.exit(1)

    # Build auth URL
    auth_url = (
        f"https://www.strava.com/oauth/authorize"
        f"?client_id={client_id}"
        f"&response_type=code"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
        f"&scope={SCOPES}"
        f"&approval_prompt=force"
    )

    # Capture the authorization code
    auth_code = [None]
    server_ready = threading.Event()

    class CallbackHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            if "code" in params:
                auth_code[0] = params["code"][0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"""
                <html><body style="font-family: system-ui; text-align: center; padding: 60px;">
                <h1>Authorized!</h1>
                <p>You can close this tab and return to the terminal.</p>
                </body></html>
                """)
            else:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Authorization failed.")

        def log_message(self, format, *args):
            pass  # Suppress server logs

    server = http.server.HTTPServer(("localhost", CALLBACK_PORT), CallbackHandler)
    server.timeout = 120

    def serve():
        server_ready.set()
        while auth_code[0] is None:
            server.handle_request()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    server_ready.wait()

    print(f"\n  Opening browser for Strava authorization...")
    print(f"  If it doesn't open, visit: {auth_url}\n")
    webbrowser.open(auth_url)

    # Wait for callback
    thread.join(timeout=120)
    server.server_close()

    if not auth_code[0]:
        print("  ❌ Timed out waiting for authorization.")
        sys.exit(1)

    # Exchange code for tokens
    print("  Exchanging authorization code for tokens...")
    resp = requests.post(
        "https://www.strava.com/oauth/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": auth_code[0],
            "grant_type": "authorization_code",
        },
        timeout=(5, 30),
    )

    if resp.status_code != 200:
        print(f"  ❌ Token exchange failed: {resp.text}")
        sys.exit(1)

    token_data = resp.json()
    tokens = {
        "client_id": client_id,
        "client_secret": client_secret,
        "access_token": token_data["access_token"],
        "refresh_token": token_data["refresh_token"],
        "expires_at": token_data["expires_at"],
        "athlete_id": token_data.get("athlete", {}).get("id"),
        "athlete_name": f"{token_data.get('athlete', {}).get('firstname', '')} {token_data.get('athlete', {}).get('lastname', '')}".strip(),
    }

    # Save tokens with platform-appropriate permissions
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(json.dumps(tokens, indent=2))
    _secure_token_file(TOKEN_FILE)

    perm_desc = _describe_permissions(TOKEN_FILE)
    print(f"\n  ✅ Authenticated as: {tokens['athlete_name']}")
    print(f"  Tokens saved to: {TOKEN_FILE}")
    print(f"  Permissions: {perm_desc}\n")


if __name__ == "__main__":
    main()
