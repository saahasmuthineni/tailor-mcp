# Changelog

All notable changes to this project are documented here.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims at [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- **Repositioned the project** as local-first infrastructure for LLM-assisted analysis of high-frequency biometric data in health research workflows. The running/Strava child is retained as a worked example of the ChildMCP pattern, not the headline use case. README, `CLAUDE.md`, module docstrings, and `ChildMCP`/`children` docstrings rewritten to match. See `docs/research-framing.md`.
- `CLAUDE.md` file tree / tool count aligned with the actual code (`RunningChild` exposes 12 tools; vault ships `parser.py` and `rescan.py`; tests ship `test_vault_parser.py` and `test_vault_rescan.py`).

### Added
- `subject_id` column on the `audit_log` table — nullable `TEXT`, populated from the `subject_id` key in a call's parameters if present. Threaded through every `_audit.record()` call in `_dispatch`, `_dispatch_vault`, and `dispatch_internal`. Legacy `audit.db` files are migrated on open via `ALTER TABLE`, mirroring the pattern `VaultStorage` already uses for `mtime_ns`.
- `PHIScrubber` class in `framework.middleware` — a documented extension seam for institutional PHI-stripping policies. Default implementation is a no-op. The router instantiates one at construction time and calls `.scrub()` on every successful child result in both `_dispatch()` and `dispatch_internal()`, before the token estimate, audit row, and post-execute hooks fire. Not applied on the vault-dispatch path (vault tools are metadata, not biometric data).
- `_meta` provenance stamps on every successful result: `package_version` (from `biosensor_mcp.__version__`), `tool_name`, and a UTC `called_at` ISO-8601 timestamp. Applied in `_dispatch()`, `_dispatch_vault()`, and `dispatch_internal()`; `dispatch_internal()` additionally carries `source: "INTERNAL"` so cross-child call traces stay distinguishable.
- `docs/research-framing.md` — the longer-form document for health-research reviewers.
- `docs/roadmap.md` — the list of explicitly deferred work the research-shift release did **not** implement.
- Tests: audit-log `subject_id` round-trip + legacy-schema migration; `PHIScrubber` no-op default and subclass-override path; `_meta` provenance assertions across `_dispatch`, `_dispatch_vault`, and `dispatch_internal`; security-probe checks for `subject_id` scoping and provenance stamps.
- Ruff linting & formatting configuration in `pyproject.toml`.
- Dedicated `lint` job in the CI workflow (runs before the OS × Python test matrix).
- pip download cache in the CI test jobs.
- `concurrency: cancel-in-progress` on CI — redundant runs against the same ref are cancelled.
- Coverage XML artifact uploaded per matrix cell.
- `py.typed` marker so downstream consumers can see the package's type hints.
- `CONTRIBUTING.md`, `CHANGELOG.md`, GitHub issue / PR templates.
- `.gitignore` now covers IDE metadata, tooling caches (ruff, mypy, coverage), OS cruft, and installer backups.

### Deferred
- Real PHI-scrubbing implementations behind the new `PHIScrubber` slot, per-subject scoping as an explicit tool parameter on existing children, deterministic replay, full content-hashed provenance, multi-analyst attribution on vault notes, vault-freeze snapshots for manuscript submission, new children (CGM / sleep / ECG / EDF / CSV / FHIR), a worked-example notebook on a public dataset, and an LLM-client evaluation harness. See `docs/roadmap.md` for the full list and rationale.

### Fixed
- README troubleshooting now lists the correct OAuth callback port (`8189`, matching `wizard.py`). Previously documented `8899`.
- Strava `client_secret` is now read with `getpass.getpass()` instead of `input()`, so it no longer echoes to the terminal or appears in shell scrollback.
- Parse failures on `user_config.json` now emit a warning instead of being silently swallowed — the vault no longer disables itself without a breadcrumb.
- Corrupt rows in the vault SQLite index now log a warning on row decode instead of silently returning empty values.
- Corrupt `rate_limit.json` now logs a warning instead of silently resetting the counter.
- Internal dispatch path cost-estimation failures now log (parity with the public dispatch path).

## [4.0.0] — earlier

- Reframed the project as a biosensor-to-LLM middleware framework. Strava running data is the reference implementation.
- Added `VaultLayer` (framework-level reorientation tier) and `VaultWriter` post-execute hook — per-analysis Obsidian notes with SQLite index.
- Packaged the OAuth setup wizard inside the installed package so it works post-`pip install`.
- Cross-platform token-file ACLs (`icacls` on Windows, `chmod 0o600` elsewhere).
- Cloud-sync provider detection for vault paths; warns when computed analytics would leave the machine.

## [3.0.0] and earlier

- Initial router/child architecture, Strava integration, security pipeline (ParamValidator → CircuitBreaker → ConsentGate → CostGate → AuditLog + TokenLedger).
