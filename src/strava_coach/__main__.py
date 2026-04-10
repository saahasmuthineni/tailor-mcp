"""
CLI for Strava Run Coach.

Usage:
    strava-coach serve      # Start MCP server (Claude Desktop calls this)
    strava-coach setup      # Run Strava OAuth setup wizard
    strava-coach status     # Diagnostic check
    strava-coach uninstall  # Clean removal
"""

import json
import os
import sys
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("STRAVA_CONFIG_DIR", Path.home() / ".strava-coach"))
DATA_DIR = Path(os.environ.get("STRAVA_DATA_DIR", CONFIG_DIR / "data"))
LOG_DIR = CONFIG_DIR / "logs"


def _setup_logging():
    """Configure logging with file rotation."""
    import logging
    from logging.handlers import RotatingFileHandler

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    handlers = [
        RotatingFileHandler(
            LOG_DIR / "server.log",
            maxBytes=5 * 1024 * 1024,  # 5 MB
            backupCount=3,
        ),
        logging.StreamHandler(sys.stderr),  # Explicit stderr — stdout is the MCP wire
    ]
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        handlers=handlers,
    )


def cmd_serve():
    """Start the MCP server via stdio."""
    _setup_logging()

    from strava_coach.framework.router import RouterMCP
    from strava_coach.children.running import RunningChild

    # Create parent router
    router = RouterMCP(
        name="strava-coaching",
        data_dir=DATA_DIR,
        cost_threshold=35_000,
        circuit_threshold=3,
        circuit_reset=300,
    )

    # Register running child
    running = RunningChild(config_dir=CONFIG_DIR, data_dir=DATA_DIR)
    router.register_child(running)

    # Future children would register here:
    # cgm = CGMChild(config_dir=CONFIG_DIR, data_dir=DATA_DIR)
    # router.register_child(cgm)

    router.run()


def cmd_setup():
    """Run the OAuth setup wizard."""
    # Wizard is bundled inside the package (strava_coach.wizard) so it works
    # after pip install — the old path-walk approach broke in site-packages.
    from strava_coach.wizard import main as wizard_main
    wizard_main()


def cmd_status():
    """Check configuration and connectivity."""
    print("Strava Run Coach — Status Check")
    print("=" * 40)

    # Config dir
    print(f"\nConfig directory: {CONFIG_DIR}")
    print(f"  Exists: {CONFIG_DIR.exists()}")

    # Tokens
    token_file = CONFIG_DIR / "tokens.json"
    print(f"\nTokens file: {token_file}")
    print(f"  Exists: {token_file.exists()}")
    if token_file.exists():
        try:
            tokens = json.loads(token_file.read_text())
            print(f"  Client ID: {tokens.get('client_id', 'MISSING')}")
            print(f"  Has access token: {'access_token' in tokens}")
            print(f"  Has refresh token: {'refresh_token' in tokens}")
            import time
            expires = tokens.get("expires_at", 0)
            if expires > time.time():
                mins = int((expires - time.time()) / 60)
                print(f"  Token valid: Yes (expires in {mins} minutes)")
            else:
                print("  Token valid: No (expired — auto-refreshes on next use)")
            # Show platform-accurate permission description (#18)
            if sys.platform == "win32":
                print("  Permissions: owner-only (Windows ACL via icacls)")
            else:
                mode = oct(token_file.stat().st_mode)[-3:]
                print(f"  Permissions: {mode}")
        except Exception as e:
            print(f"  Error reading: {e}")

    # User config
    user_config = CONFIG_DIR / "user_config.json"
    print(f"\nUser config: {user_config}")
    if user_config.exists():
        try:
            cfg = json.loads(user_config.read_text())
            print(f"  max_hr: {cfg.get('max_hr', '(default 195)')}")
            print(f"  resting_hr: {cfg.get('resting_hr', '(default 60)')}")
        except Exception as e:
            print(f"  Error: {e}")
    else:
        print("  Not found — using defaults (max_hr=195, resting_hr=60)")
        print(f"  Create {user_config} to customize.")

    # Database
    import sqlite3
    db_path = DATA_DIR / "activities.db"
    print(f"\nDatabase: {db_path}")
    print(f"  Exists: {db_path.exists()}")
    if db_path.exists():
        with sqlite3.connect(str(db_path)) as conn:
            count = conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0]
            print(f"  Cached activities: {count}")
            stream_count = conn.execute("SELECT COUNT(*) FROM streams").fetchone()[0]
            print(f"  Cached streams: {stream_count}")

    # Audit log
    audit_path = DATA_DIR / "audit.db"
    print(f"\nAudit log: {audit_path}")
    print(f"  Exists: {audit_path.exists()}")
    if audit_path.exists():
        with sqlite3.connect(str(audit_path)) as conn:
            try:
                count = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
                print(f"  Total logged calls: {count}")
            except sqlite3.OperationalError:
                print("  Table not yet created")

    # Claude Desktop config
    print("\nClaude Desktop integration:")
    if sys.platform == "darwin":
        config_path = Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    elif sys.platform == "win32":
        config_path = Path(os.environ.get("APPDATA", "")) / "Claude" / "claude_desktop_config.json"
    else:
        config_path = Path.home() / ".config" / "Claude" / "claude_desktop_config.json"

    print(f"  Config: {config_path}")
    if config_path.exists():
        try:
            # Strip UTF-8 BOM if present — PowerShell 5 writes one with
            # -Encoding UTF8, which Python's json.loads() rejects.
            raw = config_path.read_bytes().lstrip(b"\xef\xbb\xbf").decode("utf-8")
            config = json.loads(raw)
            servers = config.get("mcpServers", {})
            if "strava-coaching" in servers:
                print("  Registered: Yes")
                print(f"  Command: {servers['strava-coaching'].get('command', 'N/A')}")
            else:
                print("  Registered: No — run 'strava-coach setup' or add manually")
        except Exception as e:
            print(f"  Error reading: {e}")
    else:
        print("  Not found — Claude Desktop may not be installed")

    print("\n" + "=" * 40)
    print("Done.")


def cmd_uninstall():
    """Clean removal."""
    print("Strava Run Coach — Uninstall")
    print("This will remove:")
    print(f"  - Config directory: {CONFIG_DIR}")
    print(f"  - Claude Desktop MCP registration")
    confirm = input("\nProceed? (yes/no): ").strip().lower()
    if confirm != "yes":
        print("Cancelled.")
        return

    # Remove from Claude Desktop config
    if sys.platform == "darwin":
        config_path = Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    elif sys.platform == "win32":
        config_path = Path(os.environ.get("APPDATA", "")) / "Claude" / "claude_desktop_config.json"
    else:
        config_path = Path.home() / ".config" / "Claude" / "claude_desktop_config.json"

    if config_path.exists():
        try:
            config = json.loads(config_path.read_text())
            if "strava-coaching" in config.get("mcpServers", {}):
                del config["mcpServers"]["strava-coaching"]
                config_path.write_text(json.dumps(config, indent=2))
                print("Removed from Claude Desktop config.")
        except Exception as e:
            print(f"Warning: Could not update config: {e}")

    import shutil
    if CONFIG_DIR.exists():
        shutil.rmtree(CONFIG_DIR)
        print(f"Removed {CONFIG_DIR}")

    print("Uninstall complete. Restart Claude Desktop to apply.")


def main():
    commands = {
        "serve": cmd_serve,
        "setup": cmd_setup,
        "status": cmd_status,
        "uninstall": cmd_uninstall,
    }

    if len(sys.argv) < 2 or sys.argv[1] in ("--help", "-h", "help"):
        print(__doc__)
        print(f"Commands: {', '.join(commands)}")
        sys.exit(0)

    cmd = sys.argv[1]
    if cmd in commands:
        commands[cmd]()
    else:
        print(f"Unknown command: {cmd}")
        print(f"Available: {', '.join(commands)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
