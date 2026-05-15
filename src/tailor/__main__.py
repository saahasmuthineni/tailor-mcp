"""
CLI for Tailor.

Usage:
    tailor serve            # Start MCP server (Claude Desktop calls this)
    tailor pilot            # Configure CSV-based multi-subject pilot (start here for the v6.2 use case)
    tailor fitting-room     # Scaffold a guided walkthrough you can drive from Claude Desktop (HIP Lab realistic by default); recipient tries on bundled work-in-progress (ADR 0024)
    tailor walkthrough      # Watch the framework's architectural claims in 5 sections on bundled HIP Lab fixtures (ADRs 0027 + 0029); pass --save-shareable for an emailable markdown transcript
    tailor setup            # Run Strava OAuth setup wizard
    tailor redcap reattest  # Re-attest the REDCap trust-root metadata after legitimate edits to project_metadata.csv (ADR 0003 § Amendment 2026-05-15)
    tailor status           # Diagnostic check
    tailor uninstall        # Clean removal

Deprecated (removal deferred to a future minor):
    tailor demo             # Renamed to `tailor walkthrough` in v7.1.0 per ADR 0035
    tailor tour             # Renamed to `tailor fitting-room` in v7.1.0 per ADR 0035
"""

import json
import logging
import sys
from pathlib import Path

log = logging.getLogger("tailor")

# Centralized config — see tailor.config for env-var defaults.
from tailor.config import CONFIG_DIR, DATA_DIR, LOG_DIR  # noqa: E402


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

    from tailor.children.running import RunningChild
    from tailor.framework.router import RouterMCP

    # Create parent router
    router = RouterMCP(
        name="tailor",
        data_dir=DATA_DIR,
        cost_threshold=35_000,
        circuit_threshold=3,
        circuit_reset=300,
    )

    # Register running child
    running = RunningChild(config_dir=CONFIG_DIR, data_dir=DATA_DIR)
    router.register_child(running)

    # CSV directory child (opt-in — requires csv_dir in user_config.json)
    csv_child = None

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

    csv_dir_config = _ucfg.get("csv_dir")
    if csv_dir_config:
        from tailor.children.csv_dir import CSVDirectoryChild
        csv_child = CSVDirectoryChild(config_dir=CONFIG_DIR, data_dir=DATA_DIR)
        router.register_child(csv_child)

    # force_csv child (opt-in — requires force_csv block in user_config.json).
    # Off-blueprint Senefeld-meeting detour scaffolding; mirrors csv_dir
    # opt-in shape so unconfigured deployments are behaviourally unchanged.
    force_child = None
    if _ucfg.get("force_csv"):
        from tailor.children.force_csv import ForceCsvChild
        force_child = ForceCsvChild(config_dir=CONFIG_DIR, data_dir=DATA_DIR)
        router.register_child(force_child)

    # emg_csv child (opt-in — requires emg_csv block in user_config.json).
    # Sibling to force_csv; same off-blueprint posture.
    emg_child = None
    if _ucfg.get("emg_csv"):
        from tailor.children.emg_csv import EmgCsvChild
        emg_child = EmgCsvChild(config_dir=CONFIG_DIR, data_dir=DATA_DIR)
        router.register_child(emg_child)

    # matlab_file child (opt-in — requires matlab_file block in user_config.json).
    # Requires the [matlab] optional extra: `pip install tailor-mcp[matlab]`.
    # Per ADR 0036, the child supports `.mat` v5/v6/v7.2 only; HDF5-based
    # v7.3 is held. ImportError on missing scipy must surface visibly so
    # the operator can act on it (closes proposal-mode audit F3 — the
    # silent-failure trap that produced v6.10.2's degraded-serve state).
    matlab_child = None
    if _ucfg.get("matlab_file"):
        try:
            from tailor.children.matlab_file import MATLABFileChild
            matlab_child = MATLABFileChild(config_dir=CONFIG_DIR, data_dir=DATA_DIR)
            router.register_child(matlab_child)
        except ImportError as exc:
            _banner = "=" * 60
            sys.stderr.write(
                f"\n{_banner}\n"
                f"ERROR: matlab_file is configured in user_config.json but "
                f"scipy is not installed.\n"
                f"  Reason: {exc}\n"
                f"  Fix:    pip install tailor-mcp[matlab]\n"
                f"  Effect: MATLAB tools NOT registered; other tools "
                f"work normally.\n"
                f"{_banner}\n\n"
            )
            sys.stderr.flush()
            log.error(f"matlab_file registration failed: {exc}")

    # redcap_file child (opt-in — requires redcap_file block in user_config.json).
    # Per ADR 0037, this is the export-directory path; live REDCap REST API
    # is deferred behind a future ADR. Stdlib-only; no optional extra needed.
    # Built-in structured-PHI scrubbing via RedcapPHIScrubber per ADR 0003
    # § Amendment 2026-05-14 (child-level seam parallel to the framework-
    # level seam). Identifier flags are read from project_metadata.csv;
    # unknown fields default to identifier-positive (fail-closed).
    #
    # Registration wrapped in try/except mirroring the matlab_file pattern
    # above. v7.3.0 shipped this block unguarded — a malformed
    # `{"redcap_file": {...}}` config (e.g., missing the required `path`
    # key) would raise ValueError during RedcapFileChild.__init__, abort
    # the entire `tailor serve` boot with rc=1, and take down running +
    # csv_dir + vault + local_llm alongside REDCap. v7.3.1 closes this
    # by mirroring the matlab_file pattern: surface the failure visibly
    # to stderr, leave other children registered.
    redcap_child = None
    if _ucfg.get("redcap_file"):
        try:
            from tailor.children.redcap import RedcapFileChild
            redcap_child = RedcapFileChild(config_dir=CONFIG_DIR, data_dir=DATA_DIR)
            router.register_child(redcap_child)
        except (ImportError, ValueError, OSError) as exc:
            _banner = "=" * 60
            sys.stderr.write(
                f"\n{_banner}\n"
                f"ERROR: redcap_file is configured in user_config.json but "
                f"the child could not register.\n"
                f"  Reason: {exc}\n"
                f"  Fix:    ensure redcap_file.path points to an existing "
                f"REDCap export directory.\n"
                f"  Effect: REDCap tools NOT registered; other tools "
                f"work normally.\n"
                f"{_banner}\n\n"
            )
            sys.stderr.flush()
            log.error(f"redcap_file registration failed: {exc}")

    # Predeclared so the local-LLM registration block below can read
    # vault_writer.storage without a NameError on no-vault deployments
    # (per ADR 0023 — substrate scan reads vault_storage; None means
    # "no vault wired, scan returns empty defensively").
    vault_writer = None
    if _vault_path:
        import logging as _log_mod
        _vlog = _log_mod.getLogger("tailor")

        # Detect common cloud-sync providers by path components.
        # "mobile documents" + "clouddocs" cover macOS iCloud canonical
        # paths (~/Library/Mobile Documents/com~apple~CloudDocs/ and
        # iCloud~* app containers) which do not contain the literal
        # substring "icloud". Kept in sync with pilot._CLOUD_MARKERS.
        _CLOUD_MARKERS = (
            "onedrive", "icloud", "mobile documents", "clouddocs",
            "dropbox", "google drive", "googledrive",
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
        from tailor.framework.vault import VaultLayer, VaultWriter
        vaultable: set[str] = set()
        _registered = [running]
        if csv_child is not None:
            _registered.append(csv_child)
        if force_child is not None:
            _registered.append(force_child)
        if emg_child is not None:
            _registered.append(emg_child)
        if matlab_child is not None:
            _registered.append(matlab_child)
        if redcap_child is not None:
            _registered.append(redcap_child)
        for _child in _registered:
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

    # Local-LLM guardian (per ADR 0022). Always registered; defaults to
    # NullBackend so existing deployments are behaviourally unchanged
    # until the operator opts in via user_config.json.
    #
    # Opt-in shape:
    #     {
    #       "local_llm": {
    #         "backend":  "ollama",
    #         "tier":     "guardian",
    #         "model":    "llama3.1:8b",
    #         "endpoint": "http://localhost:11434",
    #         "timeout_s": 60
    #       }
    #     }
    from tailor.framework.local_llm import (
        LocalLLMLayer,
        NullBackend,
        OllamaBackend,
    )

    local_llm_cfg = _ucfg.get("local_llm", {}) or {}
    local_llm_backend = NullBackend()
    backend_name = str(local_llm_cfg.get("backend", "null")).lower()
    if backend_name == "ollama":
        try:
            local_llm_backend = OllamaBackend(
                tier=local_llm_cfg.get("tier", "guardian"),
                model=local_llm_cfg.get("model"),
                endpoint=local_llm_cfg.get(
                    "endpoint", "http://localhost:11434",
                ),
                timeout_s=float(local_llm_cfg.get("timeout_s", 60.0)),
            )
        except Exception as exc:
            log.warning(
                f"Local-LLM Ollama backend init failed: {exc}; "
                f"falling back to NullBackend. Edit user_config.json "
                f"local_llm block to fix."
            )
    # ADR 0023 — wire vault_storage so the substrate scan can find
    # themes / moments / failure-modes for subjects in scope. None on
    # no-vault deployments; LocalLLMLayer._scan_related_substrate is
    # defensive against that case (returns []).
    _local_llm_vault_storage = (
        vault_writer.storage if vault_writer is not None else None
    )
    router.register_local_llm_layer(LocalLLMLayer(
        backend=local_llm_backend,
        vault_storage=_local_llm_vault_storage,
    ))

    # Setup-help layer (framework-level recipient diagnostic). Registered
    # only when no demo scaffold blocks are present in user_config.json —
    # the failure mode dad's transcript surfaced (recipient lands at a
    # bare `tailor serve` via web-Claude-mediated manual config
    # rather than `tailor fitting-room`, sees a sparse tool surface,
    # asks for `force_cohort_summary` which doesn't exist on this
    # server).
    # When the demo IS scaffolded (force_csv / emg_csv / csv_dir /
    # vault_path present), this layer is never constructed so the tool
    # cannot collide with real cohort tools.
    from tailor.framework.setup_help import (
        SetupHelpLayer,
        _demo_blocks_absent,
    )
    if _demo_blocks_absent(_ucfg):
        router.register_setup_help_layer(SetupHelpLayer(
            config_dir=CONFIG_DIR,
            data_dir=DATA_DIR,
        ))

    # Future children (CGM, sleep, ECG, EDF, FHIR) would register here
    # following the same opt-in pattern as csv_dir above.

    router.run()


def cmd_setup():
    """Run the OAuth setup wizard."""
    # Wizard is bundled inside the package (tailor.wizard) so it works
    # after pip install — the old path-walk approach broke in site-packages.
    from tailor.wizard import main as wizard_main
    wizard_main()


def cmd_pilot():
    """Run the CSV-based multi-subject pilot setup wizard."""
    from tailor.pilot import main as pilot_main
    sys.exit(pilot_main())


def cmd_fitting_room():
    """Scaffold a guided walkthrough you can drive from Claude Desktop.

    Companion to ``cmd_walkthrough``: ``walkthrough`` is the
    terminal-only architectural showcase you watch (ADR 0027);
    ``fitting-room`` is the active surface where you put on the
    bundled work-in-progress — copies bundled fixtures into a
    recipient-visible directory, writes ``user_config.json``,
    indexes the vault, and registers with Claude Desktop. See ADRs
    0024 and 0035.
    """
    from tailor.fitting_room import main as fitting_room_main
    sys.exit(fitting_room_main())


def cmd_tour():
    """Deprecated alias for ``cmd_fitting_room``. Removed in v7.2.0.

    Per ADR 0035: ``tailor tour`` was renamed to ``tailor
    fitting-room`` in v7.1.0 to match the recipient-experience-shaped
    naming principle (commands named after what the recipient is
    doing, not what the system is making). Both verbs continue to
    work; removal of the deprecation shim is deferred to a future
    minor (v7.2.0 release scope was re-aimed at Move 3 / MATLAB).
    """
    print(
        "[deprecation] `tailor tour` has been renamed to "
        "`tailor fitting-room` in v7.1.0 (per ADR 0035).\n"
        "              Both verbs work in this release; "
        "the alias removal target has been bumped to a "
        "future minor.\n",
        file=sys.stderr,
    )
    cmd_fitting_room()


def cmd_status():
    """Check configuration and connectivity."""
    print("Tailor — Status Check")
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
            try:
                count = conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0]
                print(f"  Cached activities: {count}")
                stream_count = conn.execute("SELECT COUNT(*) FROM streams").fetchone()[0]
                print(f"  Cached streams: {stream_count}")
            except sqlite3.OperationalError:
                # A fresh `tour` install creates the data directory but no
                # Strava-tier tables yet — treat the same as "table not yet
                # created" rather than aborting status mid-output.
                print("  Tables not yet created (no Strava sync run)")

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
        print(f"  Enabled: Yes -> {vault_path_cfg}")
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

    # Claude Desktop config — per ADR 0026, iterate every detected
    # config path (Classic + Microsoft Store sandboxes) and report
    # per-path registration state with recovery-instruction framing.
    print("\nClaude Desktop integration:")
    from tailor.pilot import _claude_desktop_config_paths

    paths = _claude_desktop_config_paths()
    if not paths:
        print("  Not supported on this platform (Linux)")
    else:
        registered_paths: list[Path] = []
        for cfg_path in paths:
            print(f"\n  Config: {cfg_path}")
            if not cfg_path.exists():
                print("    Status: Config file not found yet")
                continue
            try:
                raw = cfg_path.read_bytes().lstrip(b"\xef\xbb\xbf").decode("utf-8")
                config = json.loads(raw)
                servers = config.get("mcpServers", {})
                # Match both legacy biosensor-* and current tailor / tailor-*
                # so v6 -> v7 upgrade state shows correctly (per ADR 0031).
                tailor_keys = [k for k in servers if _is_orphan_entry_key(k)]
                if tailor_keys:
                    registered_paths.append(cfg_path)
                    print(f"    Registered: Yes ({', '.join(tailor_keys)})")
                    primary = servers.get("tailor") or servers.get(tailor_keys[0])
                    print(f"    Command: {primary.get('command', 'N/A')}")
                else:
                    print("    Registered: No tailor entries")
            except Exception as exc:
                print(f"    Error reading: {exc}")

        # Recovery-framed summary per ADR 0026 § "cmd_status framing
        # as recovery instructions, not state report".
        print()
        if not registered_paths:
            print("  Status: NOT registered — run `tailor fitting-room` or `pilot`.")
        elif len(registered_paths) == len(paths):
            if len(paths) == 1:
                print("  Status: Registered for Claude Desktop.")
            else:
                print(
                    "  Status: Registered for both Claude Desktop variants "
                    "(Classic + Microsoft Store)."
                )
        else:
            unregistered = [p for p in paths if p not in registered_paths]
            print(
                f"  Status: Registered for {len(registered_paths)} of "
                f"{len(paths)} detected configs."
            )
            print(
                "          If the Claude Desktop you're running is "
                "the unregistered variant,"
            )
            print(
                "          run `tailor fitting-room --force` to register "
                "in the missing one."
            )
            for p in unregistered:
                print(f"          (unregistered: {p})")

    print("\n" + "=" * 40)
    print("Done.")


def cmd_walkthrough():
    """Researcher first-look — five-section walk through the framework's
    architectural claims against bundled HIP Lab fixtures. See ADRs
    0027, 0029, and 0035.

    Optional flags:
        --save-shareable [PATH]   Capture the walkthrough's stdout into
            a self-contained markdown file suitable for emailing or
            hosting at a static URL. PATH is optional; defaults to
            ``~/.tailor/shareable-walkthrough-vX.Y.Z.md``.
        --audience=<developer|public>   Default ``developer``. In
            ``public`` mode (per ADR 0030) the saved markdown gets
            per-persona reading panels + attribution-only footer + a
            render-time URL-allowlist hard-fail; suitable for the
            public mirror page. In ``developer`` mode the saved
            markdown carries ADR breadcrumbs for a co-developer
            reader (existing v6.12.0 behaviour). Has no effect when
            ``--save-shareable`` is not also passed.
    """
    from tailor import __version__ as _pkg_version
    from tailor.demo import run_demo

    args = sys.argv[2:]
    save_shareable: Path | None = None
    audience: str = "developer"
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--save-shareable":
            # `--save-shareable <path>` or `--save-shareable` (no path
            # -> default versioned path under CONFIG_DIR).
            if i + 1 < len(args) and not args[i + 1].startswith("--"):
                save_shareable = Path(args[i + 1]).expanduser().resolve()
                i += 2
                continue
            save_shareable = (
                CONFIG_DIR / f"shareable-walkthrough-v{_pkg_version}.md"
            )
            i += 1
            continue
        if arg.startswith("--save-shareable="):
            save_shareable = (
                Path(arg.split("=", 1)[1]).expanduser().resolve()
            )
            i += 1
            continue
        if arg == "--audience":
            if i + 1 < len(args) and not args[i + 1].startswith("--"):
                audience = args[i + 1]
                i += 2
                continue
            print(
                "Error: --audience requires a value (developer|public).",
                file=sys.stderr,
            )
            sys.exit(2)
        if arg.startswith("--audience="):
            audience = arg.split("=", 1)[1]
            i += 1
            continue
        i += 1

    if audience not in ("developer", "public"):
        print(
            f"Error: --audience must be 'developer' or 'public'; "
            f"got {audience!r}.",
            file=sys.stderr,
        )
        sys.exit(2)

    run_demo(save_shareable_path=save_shareable, audience=audience)


def cmd_demo():
    """Deprecated alias for ``cmd_walkthrough``. Removal deferred.

    Per ADR 0035: ``tailor demo`` was renamed to ``tailor walkthrough``
    in v7.1.0 to match the recipient-experience-shaped naming
    principle (commands named after what the recipient is doing, not
    what the system is making). Both verbs continue to work; removal
    of the deprecation shim is deferred to a future minor (v7.2.0
    release scope was re-aimed at Move 3 / MATLAB).

    Forwards every ``sys.argv`` argument transparently to
    ``cmd_walkthrough`` — flag parsing reads ``sys.argv[2:]`` so the
    deprecated invocation produces identical behavior to the new
    verb.
    """
    print(
        "[deprecation] `tailor demo` has been renamed to "
        "`tailor walkthrough` in v7.1.0 (per ADR 0035).\n"
        "              Both verbs work in this release; "
        "the alias removal target has been bumped to a "
        "future minor.\n",
        file=sys.stderr,
    )
    cmd_walkthrough()


def _is_orphan_entry_key(key: str) -> bool:
    """Match any Claude Desktop ``mcpServers`` key that the framework has
    ever written, across both the legacy ``biosensor-*`` (v6 and earlier)
    and the current ``tailor`` / ``tailor-*`` (v7+) naming conventions.

    Legacy (v6.x):
      - ``biosensor-mcp``               (pilot wizard / manual install)
      - ``biosensor-tour-<variant>``    (tour subcommand, ADR 0024)
      - any ``biosensor-*``             (defensive — matches v6.9.2 contract)

    Current (v7.0+, per ADR 0031):
      - ``tailor``                      (pilot wizard / manual install)
      - ``tailor-tour-<variant>``       (tour subcommand)
      - any ``tailor-*``                (defensive symmetry with v6.9.2)

    Dual-prefix matching is the migration story: a v6 user upgrading to v7
    has stale ``biosensor-*`` keys that need to be cleaned alongside the
    new ``tailor`` keys whenever the framework re-registers or uninstalls.
    """
    return (
        key == "tailor"
        or key.startswith("tailor-")
        or key.startswith("biosensor-")
    )


def _clean_claude_desktop_orphan_entries() -> dict[Path, list[str]]:
    """Remove every framework-written entry from every detected Claude
    Desktop config (Classic + Microsoft Store sandboxes per ADR 0026).

    Matches both the legacy ``biosensor-*`` keys (v6.x) and the current
    ``tailor`` / ``tailor-*`` keys (v7.0+) — see ``_is_orphan_entry_key``
    for the full match set and ADR 0031 for the migration story.

    Without this dual-prefix match, ``tailor uninstall`` would leave stale
    ``biosensor-tour-hip-lab`` entries from a v6 install pointing at a
    removed binary, so Claude Desktop would show a red MCP indicator after
    a clean v7 uninstall (the v6.9.2 bug applied to the v6->v7 transition).

    Returns a mapping ``{path: [removed_keys, ...]}`` for every detected
    path; the value is an empty list when the config does not exist, has
    no matching entries, or could not be parsed. Sibling MCP servers
    (any key not matching ``_is_orphan_entry_key``) are preserved.
    """
    from tailor.pilot import _claude_desktop_config_paths

    results: dict[Path, list[str]] = {}
    for config_path in _claude_desktop_config_paths():
        if not config_path.exists():
            results[config_path] = []
            continue
        try:
            raw = config_path.read_bytes().lstrip(b"\xef\xbb\xbf").decode("utf-8")
            config = json.loads(raw)
            servers = config.get("mcpServers", {})
            removed = [k for k in list(servers) if _is_orphan_entry_key(k)]
            for key in removed:
                del servers[key]
            if removed:
                config_path.write_text(json.dumps(config, indent=2))
            results[config_path] = removed
        except (OSError, ValueError):
            results[config_path] = []
    return results


def cmd_redcap():
    """Dispatch subcommands grouped under ``tailor redcap``.

    Currently supports:
        tailor redcap reattest   # Re-attest project_metadata.csv after a legitimate edit

    The two-token surface (``redcap reattest`` rather than
    ``redcap-reattest``) leaves room for additional REDCap-specific
    operator subcommands without inflating the top-level command list.
    """
    if len(sys.argv) < 3:
        print("Usage: tailor redcap <subcommand>")
        print("Subcommands: reattest")
        sys.exit(1)
    subcmd = sys.argv[2]
    if subcmd == "reattest":
        cmd_redcap_reattest()
    elif subcmd in ("--help", "-h", "help"):
        print(cmd_redcap.__doc__)
        sys.exit(0)
    else:
        print(f"Unknown REDCap subcommand: {subcmd}")
        print("Available subcommands: reattest")
        sys.exit(1)


def cmd_redcap_reattest():
    """Re-attest the REDCap trust-root metadata fingerprint.

    Per ADR 0003 § Amendment 2026-05-15. The operator runs this command
    after a legitimate edit to ``project_metadata.csv`` (e.g. adding a
    new survey instrument's fields mid-enrollment, the common REDCap
    workflow) to re-establish the cryptographic attestation of the
    trust-root state.

    Behaviour:

    1. Loads the configured REDCap export directory from
       ``user_config.json``.
    2. Constructs a fresh ``RedcapPHIScrubber`` against the current
       on-disk ``project_metadata.csv`` and computes its canonical-form
       fingerprint.
    3. Reads the most recent ``source_metadata_fingerprint`` stamped in
       ``audit.db`` for ``domain='redcap_file'`` — the cached attestation.
    4. Prints (a) the cached fingerprint, (b) the new fingerprint, (c)
       a sorted field-by-field listing of the current trust-root state
       so the operator can visually confirm the file looks correct.
       A tamper attempt that flipped every flag to ``N`` is displayed
       visibly before the operator confirms.
    5. Prompts for ``yes`` to attest, anything else to abort.
    6. On attest, writes a ``REATTEST`` audit row to ``audit.db``
       capturing the new fingerprint. The running ``tailor serve``
       process is **not** affected — the operator must restart it
       (``Ctrl-C`` then re-launch, or restart Claude Desktop which
       re-spawns the server) so the new file is loaded at child
       construction time.

    The framework does **not** silently update fingerprints to match
    on-disk changes. The reattest ritual is the trust-affording
    surface; without it, fingerprint mismatch fails-closed at every
    REDCap tool call.
    """
    import sqlite3

    user_config = CONFIG_DIR / "user_config.json"
    if not user_config.exists():
        print(
            f"Error: {user_config} not found. Configure REDCap first via "
            f"`tailor pilot` or by adding a `redcap_file` block to "
            f"user_config.json.",
            file=sys.stderr,
        )
        sys.exit(1)
    try:
        cfg = json.loads(user_config.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Error: could not parse {user_config}: {exc}", file=sys.stderr)
        sys.exit(1)
    redcap_cfg = cfg.get("redcap_file")
    if not redcap_cfg or not isinstance(redcap_cfg, dict):
        print(
            "Error: no `redcap_file` block in user_config.json. Nothing to "
            "re-attest. See ADR 0037 for the REDCap config shape.",
            file=sys.stderr,
        )
        sys.exit(1)
    raw_path = redcap_cfg.get("path")
    if not raw_path:
        print(
            "Error: redcap_file.path is required in user_config.json.",
            file=sys.stderr,
        )
        sys.exit(1)
    redcap_dir = Path(raw_path).expanduser().resolve()
    metadata_filename = redcap_cfg.get(
        "project_metadata_file", "project_metadata.csv",
    )
    metadata_path = redcap_dir / metadata_filename
    if not metadata_path.is_file():
        print(
            f"Error: project_metadata.csv not found at "
            f"{metadata_path}. Cannot attest a missing file. Place the "
            f"REDCap data dictionary at this path and re-run.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Load the current state.
    from tailor.children.redcap.scrubber import RedcapPHIScrubber
    try:
        candidate = RedcapPHIScrubber(
            project_metadata_path=metadata_path,
            unknown_field_allowlist=[],
        )
    except Exception as exc:
        print(
            f"Error: could not parse {metadata_path}: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)
    new_fingerprint = candidate.fingerprint

    # Look up the most-recent cached fingerprint.
    audit_path = DATA_DIR / "audit.db"
    cached_fingerprint: str | None = None
    if audit_path.exists():
        try:
            with sqlite3.connect(str(audit_path)) as conn:
                cur = conn.execute(
                    "SELECT source_metadata_fingerprint FROM audit_log "
                    "WHERE domain = ? AND source_metadata_fingerprint IS NOT NULL "
                    "ORDER BY id DESC LIMIT 1",
                    ("redcap_file",),
                )
                row = cur.fetchone()
                if row is not None:
                    cached_fingerprint = row[0]
        except sqlite3.OperationalError:
            # audit.db exists but the column / table may not yet have
            # been migrated by a serve invocation. Treat as no prior
            # attestation rather than failing.
            cached_fingerprint = None

    # Render the operator-facing report.
    print("Tailor — REDCap trust-root reattest")
    print("=" * 60)
    print(f"\nproject_metadata.csv: {metadata_path}")
    print(f"\nCached fingerprint   : {cached_fingerprint or '(no prior attestation in audit.db)'}")
    print(f"New fingerprint      : {new_fingerprint}")
    if cached_fingerprint == new_fingerprint:
        print(
            "\nFingerprints agree — the trust-root state on disk matches "
            "the cached attestation. No reattest needed."
        )
        sys.exit(0)
    print()
    if candidate.child_scrubber_warning:
        print(f"[warning] {candidate.child_scrubber_warning}\n")
    print("Current trust-root state (sorted by field_name):")
    print("-" * 60)
    state = candidate.canonical_state
    if not state:
        print("  (empty — project_metadata.csv loaded but no field rows)")
    else:
        for name, is_identifier in state:
            flag = "IDENTIFIER" if is_identifier else "ok"
            print(f"  {name:40s}  {flag}")
    print("-" * 60)
    print(
        f"\n{len(state)} field(s) total; "
        f"{sum(1 for _, f in state if f)} flagged as identifier."
    )
    print(
        "\nReview the listing above. A tamper attempt would show every "
        "identifier field flipped to `ok`. A legitimate edit (new "
        "instrument added) shows the new fields with their expected flags."
    )
    print(
        "\nAttesting will write a REATTEST row to audit.db with the new "
        "fingerprint. You will need to restart `tailor serve` (Ctrl-C "
        "then re-launch, or restart Claude Desktop) for the running "
        "server to pick up the new trust-root state."
    )
    confirm = input("\nAttest the new fingerprint? (yes/no): ").strip().lower()
    if confirm != "yes":
        print("Cancelled. No audit row written.")
        sys.exit(0)

    # Write the REATTEST audit row via AuditLog.record() — NOT a
    # hand-rolled INSERT. The hand-rolled path was the v7.3.2 first-pass
    # implementation; phi-irb-risk-reviewer + reproducibility-provenance-
    # auditor independently named it as a defect (the REATTEST row would
    # leak NULL into scrubber_id, breaking ADR 0003's "scrubber_id turns
    # 'did we scrub?' into a fact on disk" invariant). Routing through
    # the canonical helper inherits the migration logic, the scrubber_id
    # default, and any future audit-column additions automatically.
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    from tailor.framework.audit import AuditLog
    from tailor.framework.security import PHIScrubber
    audit_log = AuditLog(audit_path)
    framework_scrubber = PHIScrubber()
    try:
        audit_log.record(
            domain="redcap_file",
            tool_name="redcap_reattest",
            tier=0,
            params={
                "cached_fingerprint": cached_fingerprint,
                "new_fingerprint": new_fingerprint,
            },
            token_estimate=0,
            outcome="REATTEST",
            duration_ms=0,
            scrubber_id=framework_scrubber.scrubber_id,
            child_scrubber_id="redcap_metadata_flags",
            source_metadata_fingerprint=new_fingerprint,
        )
    finally:
        audit_log.close()
    print(
        f"\nAttested. New fingerprint {new_fingerprint[:16]}... recorded."
    )
    print(
        "Restart `tailor serve` for the running server to pick up the "
        "new trust-root state."
    )


def cmd_uninstall():
    """Clean removal."""
    print("Tailor — Uninstall")
    print("This will remove:")
    print(f"  - Config directory: {CONFIG_DIR}")
    print("  - Claude Desktop MCP registration (every detected config)")
    confirm = input("\nProceed? (yes/no): ").strip().lower()
    if confirm != "yes":
        print("Cancelled.")
        return

    # Remove from every Claude Desktop config (Classic + Microsoft
    # Store sandboxes per ADR 0026).
    try:
        per_path = _clean_claude_desktop_orphan_entries()
        for cfg_path, removed in per_path.items():
            for key in removed:
                print(f"Removed '{key}' from {cfg_path}")
    except Exception as e:
        print(f"Warning: Could not update Claude Desktop configs: {e}")

    import shutil
    if CONFIG_DIR.exists():
        shutil.rmtree(CONFIG_DIR)
        print(f"Removed {CONFIG_DIR}")

    print("Uninstall complete. Restart Claude Desktop to apply.")


def _make_cli_stdout_resilient() -> None:
    """Stop a stray non-cp1252 character from crashing a recipient demo.

    Windows PowerShell 5 (the parent-recipient default) drives Python with
    a cp1252 stdout. Any glyph outside cp1252 (arrows, checkmarks, etc.)
    raises UnicodeEncodeError under the default ``errors='strict'`` handler
    — observed live during the v6.10.0 max-debug-hunt when ``cmd_status``
    crashed mid-output on the right-arrow at line 352. We can't enumerate
    every future glyph; switch the error handler so an unrepresentable
    character degrades to '?' instead of aborting the command.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(errors="replace")
        except (OSError, ValueError):
            pass


def main():
    _make_cli_stdout_resilient()
    commands = {
        "serve": cmd_serve,
        "pilot": cmd_pilot,
        "fitting-room": cmd_fitting_room,
        "walkthrough": cmd_walkthrough,
        "setup": cmd_setup,
        # `redcap` is a parent verb that dispatches its own subcommand
        # from sys.argv[2] (currently only `reattest`). Per ADR 0003
        # § Amendment 2026-05-15.
        "redcap": cmd_redcap,
        "status": cmd_status,
        "uninstall": cmd_uninstall,
        # Deprecated aliases — one-cycle shim per ADR 0035; removal target
        # bumped from v7.2.0 to a future minor (v7.2.0 scope = Move 3 / MATLAB).
        # Each maps to a wrapper function that prints a stderr deprecation
        # hint then calls the new verb's handler. Listed last so the --help
        # output groups them visually.
        "tour": cmd_tour,
        "demo": cmd_demo,
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
