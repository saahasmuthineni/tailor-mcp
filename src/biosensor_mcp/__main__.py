"""
CLI for Biosensor MCP.

Usage:
    biosensor-mcp serve      # Start MCP server (Claude Desktop calls this)
    biosensor-mcp setup      # Run Strava OAuth setup wizard
    biosensor-mcp status     # Diagnostic check
    biosensor-mcp demo       # Run analytics on synthetic data (no Strava needed)
    biosensor-mcp uninstall  # Clean removal
"""

import json
import logging
import os
import sys
from pathlib import Path

log = logging.getLogger("biosensor-mcp")

# Centralized config — see biosensor_mcp.config for env-var defaults.
from biosensor_mcp.config import CONFIG_DIR, DATA_DIR, LOG_DIR  # noqa: E402


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

    from biosensor_mcp.children.running import RunningChild
    from biosensor_mcp.framework.router import RouterMCP

    # Create parent router
    router = RouterMCP(
        name="biosensor-mcp",
        data_dir=DATA_DIR,
        cost_threshold=35_000,
        circuit_threshold=3,
        circuit_reset=300,
    )

    # Register running child
    running = RunningChild(config_dir=CONFIG_DIR, data_dir=DATA_DIR)
    router.register_child(running)

    # Vault integration (opt-in — requires vault_path in user_config.json)
    _ucfg_path = CONFIG_DIR / "user_config.json"
    _ucfg: dict = {}
    _vault_path = None
    if _ucfg_path.exists():
        try:
            _ucfg_text = _ucfg_path.read_text(encoding="utf-8")
            _ucfg = json.loads(_ucfg_text)
            if "vault_path" in _ucfg:
                _vault_path = Path(_ucfg["vault_path"]).expanduser()
        except json.JSONDecodeError as exc:
            # Most common cause: user hand-edited user_config.json and left
            # a trailing comma. Print loudly to stderr AND log — silent
            # failure leaves vault integration disabled with no breadcrumb,
            # which is a nightmare to debug on a research workstation.
            _banner = "=" * 60
            sys.stderr.write(
                f"\n{_banner}\n"
                f"ERROR: could not parse user_config.json\n"
                f"  File:   {_ucfg_path}\n"
                f"  Reason: {exc.msg} (line {exc.lineno}, column {exc.colno})\n"
                f"  Effect: vault integration is DISABLED.\n"
                f"  Fix:    validate the file with `python -m json.tool` "
                f"and restart the server.\n"
                f"{_banner}\n\n"
            )
            sys.stderr.flush()
            log.error(f"user_config.json parse error: {exc}")
        except OSError as exc:
            log.warning(
                f"Could not read {_ucfg_path}: {exc}. "
                f"Vault integration disabled until the file is readable."
            )

    if _vault_path:
        import logging as _log_mod
        _vlog = _log_mod.getLogger("biosensor-mcp")

        # Detect common cloud-sync providers by path components
        _CLOUD_MARKERS = (
            "onedrive", "icloud", "dropbox", "google drive", "googledrive",
            "box sync", "boxsync", "nextcloud", "mega",
        )
        _vault_str = str(_vault_path).lower().replace("\\", "/")
        _cloud_provider = next(
            (m for m in _CLOUD_MARKERS if m in _vault_str), None
        )
        if _cloud_provider:
            _vlog.warning(
                f"PRIVACY WARNING: vault_path appears to be inside a cloud-synced folder "
                f"({_cloud_provider} detected in path: {_vault_path}). "
                f"Computed biometric analytics WILL be uploaded to the cloud. "
                f"Set vault_path to a local folder if you want data to stay on this machine."
            )
        else:
            _vlog.warning(
                f"Vault enabled: run analytics will be written to {_vault_path}. "
                f"If this path is cloud-synced, computed fitness data will leave this machine."
            )
        from biosensor_mcp.framework.vault import VaultLayer, VaultWriter
        vaultable: set[str] = set()
        for _child in [running]:
            vaultable.update(getattr(_child, "vaultable_tools", []))
        # max_hr from user config (same source RunningChild reads from).
        # _ucfg is guaranteed to be a dict here — it is initialized to {} above
        # and only populated on successful parse; _vault_path is only set when
        # parsing succeeded.
        _max_hr = _ucfg.get("max_hr", 195)
        vault_writer = VaultWriter(
            vault_path=_vault_path,
            data_dir=DATA_DIR,
            vaultable_tools=vaultable,
            max_hr=_max_hr,
        )
        router.register_post_execute_hook(vault_writer)
        # VaultLayer is framework-level infrastructure, not a ChildMCP.
        # Backfill is decoupled from sibling tool names via backfill_config —
        # cross-child knowledge lives at the wiring site, not inside the vault.
        router.register_vault_layer(VaultLayer(
            vault_path=_vault_path,
            vault_writer=vault_writer,
            backfill_config={
                "list_tool": "strava_list_runs",
                "report_tool": "strava_run_report",
            },
        ))

    # Future children would register here:
    # cgm = CGMChild(config_dir=CONFIG_DIR, data_dir=DATA_DIR)
    # router.register_child(cgm)

    router.run()


def cmd_setup():
    """Run the OAuth setup wizard."""
    # Wizard is bundled inside the package (biosensor_mcp.wizard) so it works
    # after pip install — the old path-walk approach broke in site-packages.
    from biosensor_mcp.wizard import main as wizard_main
    wizard_main()


def cmd_status():
    """Check configuration and connectivity."""
    print("Biosensor MCP — Status Check")
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

    # Vault integration
    user_config_2 = CONFIG_DIR / "user_config.json"
    vault_path_cfg = None
    if user_config_2.exists():
        try:
            _cfg2 = json.loads(user_config_2.read_text())
            if "vault_path" in _cfg2:
                vault_path_cfg = Path(_cfg2["vault_path"]).expanduser()
        except (OSError, ValueError) as exc:
            print(f"  Warning: could not parse {user_config_2}: {exc}")
    print("\nVault integration:")
    if vault_path_cfg:
        print(f"  Enabled: Yes → {vault_path_cfg}")
        print(f"  Vault exists: {vault_path_cfg.exists()}")
        vault_db = DATA_DIR / "vault.db"
        if vault_db.exists():
            import sqlite3 as _sq
            try:
                with _sq.connect(str(vault_db)) as _vc:
                    _n = _vc.execute("SELECT COUNT(*) FROM vault_notes").fetchone()[0]
                print(f"  Notes indexed: {_n}")
            except Exception:
                print("  Notes indexed: (db not yet initialised)")
    else:
        print("  Enabled: No (add vault_path to user_config.json to enable)")

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
            if "biosensor-mcp" in servers:
                print("  Registered: Yes")
                print(f"  Command: {servers['biosensor-mcp'].get('command', 'N/A')}")
            else:
                print("  Registered: No — run 'biosensor-mcp setup' or add manually")
        except Exception as e:
            print(f"  Error reading: {e}")
    else:
        print("  Not found — Claude Desktop may not be installed")

    print("\n" + "=" * 40)
    print("Done.")


def cmd_demo():
    """Run analytics on synthetic data — no Strava account needed."""
    from biosensor_mcp.demo import run_demo
    run_demo()


def cmd_uninstall():
    """Clean removal."""
    print("Biosensor MCP — Uninstall")
    print("This will remove:")
    print(f"  - Config directory: {CONFIG_DIR}")
    print("  - Claude Desktop MCP registration")
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
            raw = config_path.read_bytes().lstrip(b"\xef\xbb\xbf").decode("utf-8")
            config = json.loads(raw)
            if "biosensor-mcp" in config.get("mcpServers", {}):
                del config["mcpServers"]["biosensor-mcp"]
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
        "demo": cmd_demo,
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
