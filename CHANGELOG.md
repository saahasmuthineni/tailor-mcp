# Changelog

All notable changes to this project are documented here.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims at [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [6.0.0] — 2026-04-23

Vault-only release: the router, security pipeline, children, CLI, and
demo are untouched. Every change in this version lives under
`biosensor_mcp.framework.vault` and makes the reorientation tier a real
longitudinal research tool rather than just a note archive.

### Added
- **Vault snapshot** (`vault_generate_snapshot`, `vault_get_snapshot`):
  a compressed `snapshot.md` at the vault root that summarises open
  themes, recent moments, weekly run aggregates, inbox depth, and vault
  health. Intended as the new "call this first" orientation tool in new
  sessions — one file instead of many.
- **Theme lifecycle enrichment** on `vault_upsert_theme`:
  - `reframed` status and automatic prior-framing preservation when a
    new hypothesis is supplied that differs from the one on disk. The
    old framing lands under a `## Prior Framings` section; status
    persists as `open` (reframed is transitional).
  - `thinking` parameter that appends a `### Thinking — TIMESTAMP`
    block inside the evidence log for partial-progress notes distinct
    from settled evidence.
  - Fold-back on resolution: when status flips to `resolved` or
    `rejected`, linked run and theme notes receive a one-line
    `> Theme [[slug]] resolved: …` annotation so browsing them
    surfaces the closed thread.
- **Evidence provenance** on `vault_upsert_theme`: optional
  `evidence_source_tier`, `evidence_source_tool`, `evidence_source_domain`,
  and `evidence_verification` parameters. When any is provided, the new
  evidence block carries a `> Source: …` blockquote so readers can trace
  which tool and data tier produced the observation.
- **Vault inbox** (`vault_inbox_add`, `vault_inbox_list`,
  `vault_inbox_drain`): a single `inbox.md` file at the vault root for
  low-friction capture of half-formed observations, plus a bulk drain
  operation that promotes items to moments, theme evidence, or
  discards them in one audited call.
- **Session divergence** on `vault_capture_session`: optional
  `divergence` parameter (max 1000 chars) recording what the
  analytical goal was versus what actually happened. Rendered as a
  `## Divergence` section on the summary moment and mirrored into
  frontmatter so it's searchable.
- **Analytical corrections** (`vault_correct_evidence`): mark a
  specific evidence block as superseded by timestamp. Inserts a
  `[CORRECTED <ts>]` blockquote after the targeted header and appends
  a new `### Evidence — … [correction]` block logging the correction
  itself. The original evidence is preserved (append-only invariant).
- **Vault health check** (`vault_health_check`): diagnostic sweep that
  returns stale themes, orphaned moments, themes without evidence,
  inbox depth, and counts by status. Use at session end to decide what
  to tidy up.
- `biosensor_mcp.framework.vault.storage.VaultStorage` gains
  `count_themes_by_status()`, `list_orphaned_moments()`, and
  `list_stale_themes()` helpers backing the health-check tool.
- `render_snapshot_note()` pure renderer in
  `biosensor_mcp.framework.vault.renderer`.
- `VaultWriter` gains `write_snapshot()`, `append_theme_thinking()`,
  `reframe_theme()`, `correct_theme_evidence()`, `append_inbox_item()`,
  `read_inbox()`, and `drain_inbox_items()` public methods.
- ADR 0006 — documents the vault overhaul and the governance patterns
  borrowed from personal knowledge-management practice.

### Changed
- Vault tool count: 15 → 22.
- `VaultLayer.tool_definitions`: added the seven new tools above.
- `render_moment_note()` accepts an optional `divergence` kwarg and
  renders a `## Divergence` section + frontmatter key when provided.
- `_format_evidence_block()` accepts optional provenance kwargs
  (`source_tier`, `source_tool`, `source_domain`, `verification`,
  `tag_suffix`, `timestamp`) and renders a provenance blockquote when
  any are set.
- `VaultWriter.append_theme_evidence()` gained matching optional
  kwargs; callers that don't pass them continue to get the v5
  behaviour.
- `vault_upsert_theme` `status` param now accepts `reframed` in
  addition to `open` / `resolved` / `rejected`.

### Also included (from the prior unreleased stream, shipping with 6.0.0)
- `RunningChild` now declares `subject_id` on all 12 `strava_*` tools
  in both `ToolDefinition.params` (MCP `list_tools` discoverability)
  and `param_schemas` (validator-side pattern enforcement:
  `^[A-Za-z0-9_\-]{1,64}$`). Closes the first half of the roadmap
  item "Per-subject parameter scoping on existing tools". The router
  plumbing and audit column from ADR 0002 were already in place; this
  is the declaration layer. Vault adoption remains deferred pending
  the vault subject-keying design question.
- `SUBJECT_ID_SCHEMA` and `SUBJECT_ID_PARAM_DOC` constants exported
  from `biosensor_mcp.children.running.child` so future children can
  copy the two-line pattern.
- `tests/children/running/test_child_schema.py` — schema declaration
  and pattern validation tests.
- `tests/framework/test_router.py::TestSubjectIdAuditScoping::test_subject_id_invalid_pattern_audits_as_param_invalid`
  — confirms that a rejected `subject_id` still lands in the audit
  row, so reviewers see on whose behalf a bad call was allegedly
  made.

## [5.0.0] — 2026-04-13

### Breaking
- **`framework.middleware` is gone.** Split into three topical
  modules with no re-export shims (per the v5.0.0 plan). Update
  imports as follows:
  - `from biosensor_mcp.framework.middleware import ParamValidator,`
    `CircuitBreaker, ConsentGate, PHIScrubber`
    → `from biosensor_mcp.framework.security import ...`
  - `from biosensor_mcp.framework.middleware import CostGate,`
    `TokenLedger, estimate_tokens`
    → `from biosensor_mcp.framework.cost import ...`
  - `from biosensor_mcp.framework.middleware import AuditLog,`
    `_dumps, _loads, JSON_BACKEND`
    → `from biosensor_mcp.framework.audit import ...`
  - The umbrella `from biosensor_mcp.framework import ...` keeps
    working unchanged for the public symbols (and now also exposes
    `PHIScrubber`, which had been omitted from `__all__`).
- **`biosensor_mcp.vault` moved to `biosensor_mcp.framework.vault`.**
  `VaultLayer` and `VaultWriter` are framework-level infrastructure;
  the previous top-level location was an asymmetry. Update:
  - `from biosensor_mcp.vault import VaultLayer, VaultWriter`
    → `from biosensor_mcp.framework.vault import VaultLayer, VaultWriter`
  - Submodule imports follow the same prefix shift
    (`biosensor_mcp.vault.layer` → `biosensor_mcp.framework.vault.layer`
    etc.).

### Added
- `biosensor_mcp.config` — single point of truth for environment-derived
  paths (`BIOSENSOR_CONFIG_DIR`, `BIOSENSOR_DATA_DIR`) and the
  `user_config.json` reader. `__main__.py` and `wizard.py` now route
  through it; child modules continue to own their domain-specific
  env vars (e.g. `STRAVA_STREAM_CACHE_TTL_DAYS` in the running child).
- `tests/conftest.py` — shared fixtures (`tmp_data_dir`,
  `tmp_vault_dirs`) and the `probe` marker registration.
- `tests/test_security_probe_pytest.py` — pytest wrapper that runs the
  standalone `tests/security_probe.py` under `pytest -m probe`. The
  standalone CLI invocation continues to work unchanged for CI's
  defense-in-depth check.

### Changed
- `tests/` mirrors the `src/` layout: `tests/framework/` for
  middleware tests (split into `test_security.py`, `test_cost.py`,
  `test_audit.py`), `tests/framework/vault/` for vault tests (drop
  the `test_vault_` prefix), `tests/children/running/` for
  domain-specific tests. `tests/security_probe.py` stays at the
  `tests/` root as a standalone script.
- **Repo reorganization pass** — hygiene files and documentation
  layout. `docs/` now splits into `assets/` (SVGs), `design/`
  (research-framing, design-context PDF), and `guides/` (Claude
  Desktop demo, VHS tape). Link references in README and CLAUDE.md
  updated.
- `CLAUDE.md` "Key Design Decisions" section now links to ADR files
  under `docs/adr/` for the five architectural decisions, and
  relocates the five domain-specific numeric choices (grade
  precision, 0.5 m/s stop threshold, 30 s spike cooldown, orjson
  fallback, `router.close()` on Windows) to an "Implementation
  notes" subsection.
- **Codebase review pass** (`claude/codebase-review-hl0tT`) — targeted bug fixes, test gaps, and CI guardrails. Highlights below; no public-API removals.
- Cost-estimation failure now **fails closed** in both `_dispatch()` and `dispatch_internal()`. Previously a broken `estimate_cost()` fell back to `CostEstimate(tokens=0)`, which silently bypassed the cost gate for Tier-3 calls. Audited as `COST_ESTIMATE_ERROR` / `COST_ESTIMATE_ERROR_INTERNAL`.
- `AuditLog.record()` serialises `params` through a **50 KB size bound**; oversized payloads are truncated with a `...[truncated; N bytes]` marker so a pathological caller cannot bloat `audit.db`.
- `AuditLog.record(error=...)` is now **keyword-only**. The 8th positional argument is no longer accepted. All in-tree call sites were updated; out-of-tree callers will see a `TypeError` with a clear traceback rather than a silently-mis-positioned row.
- `PHIScrubber` default (no-op) now emits a **one-time warning on first construction** and exposes a `scrubber_id` property (`"noop"` for the default, class name otherwise) for audit-trail traceability on misconfigured deployments.
- `dispatch_internal()` cost-gate + PARAM_INVALID audit rows now record `duration_ms` consistently with the public dispatch path (was hard-coded to `0`).
- `compute_hr_zones()` no longer accepts an unused `resting_hr` parameter (%MHR zones never used it). If Karvonen reserve is wanted, add it as a separate method rather than extending the signature.
- `compute_efficiency_factor()` no longer accepts an unused `grade` parameter. A grade-adjusted variant should live in a new method.
- **Repositioned the project** as local-first infrastructure for LLM-assisted analysis of high-frequency biometric data in health research workflows. The running/Strava child is retained as a worked example of the ChildMCP pattern, not the headline use case. README, `CLAUDE.md`, module docstrings, and `ChildMCP`/`children` docstrings rewritten to match. See `docs/design/research-framing.md`.
- `CLAUDE.md` file tree / tool count aligned with the actual code (`RunningChild` exposes 12 tools; vault ships `parser.py` and `rescan.py`; tests ship `test_vault_parser.py` and `test_vault_rescan.py`).

### Added
- `docs/adr/` — Architecture Decision Records. Five initial entries cover the audit log as backbone, `subject_id` scoping, the `PHIScrubber` seam, structured `LLMInstruction`, and cost pre-estimation. `docs/adr/README.md` indexes them; `docs/adr/0000-template.md` is the copy-template for future ADRs.
- `.github/SECURITY.md` — private vulnerability reporting path via GitHub security advisories; scope in/out list.
- `.github/CODEOWNERS` — flags `framework/`, `framework/vault/`, `docs/adr/`, CI workflows, and the security probe as review-required.
- `.github/dependabot.yml` — weekly `pip` + `github-actions` dependency updates, with minor/patch version bumps grouped to reduce review churn.
- `.github/ISSUE_TEMPLATE/new_child.md` — structured proposal template for new `ChildMCP` data sources (domain, consent scope, tier mapping, PHI considerations).
- `.pre-commit-config.yaml` — ruff (lint + format-check), trailing-whitespace, end-of-file-fixer, check-yaml, check-toml, mixed-line-ending. Ruff configuration continues to live in `pyproject.toml`.
- `.editorconfig` — cross-editor/cross-OS indentation + line-ending rules.
- `subject_id` column on the `audit_log` table — nullable `TEXT`, populated from the `subject_id` key in a call's parameters if present. Threaded through every `_audit.record()` call in `_dispatch`, `_dispatch_vault`, and `dispatch_internal`. Legacy `audit.db` files are migrated on open via `ALTER TABLE`, mirroring the pattern `VaultStorage` already uses for `mtime_ns`.
- `PHIScrubber` class in `framework.middleware` — a documented extension seam for institutional PHI-stripping policies. Default implementation is a no-op. The router instantiates one at construction time and calls `.scrub()` on every successful child result in both `_dispatch()` and `dispatch_internal()`, before the token estimate, audit row, and post-execute hooks fire. Not applied on the vault-dispatch path (vault tools are metadata, not biometric data).
- `_meta` provenance stamps on every successful result: `package_version` (from `biosensor_mcp.__version__`), `tool_name`, and a UTC `called_at` ISO-8601 timestamp. Applied in `_dispatch()`, `_dispatch_vault()`, and `dispatch_internal()`; `dispatch_internal()` additionally carries `source: "INTERNAL"` so cross-child call traces stay distinguishable.
- `docs/design/research-framing.md` — the longer-form document for health-research reviewers.
- `ROADMAP.md` (originally `docs/roadmap.md`, promoted to repo root in the codebase-review pass) — the list of explicitly deferred work the research-shift release did **not** implement, now with effort/impact triage and surfaced from README.
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
- Real PHI-scrubbing implementations behind the new `PHIScrubber` slot, per-subject scoping as an explicit tool parameter on existing children, deterministic replay, full content-hashed provenance, multi-analyst attribution on vault notes, vault-freeze snapshots for manuscript submission, new children (CGM / sleep / ECG / EDF / CSV / FHIR), a worked-example notebook on a public dataset, and an LLM-client evaluation harness. See [ROADMAP.md](ROADMAP.md) for the full list and rationale.

### Fixed
- `VaultWriter._atomic_write_abs()` no longer leaks file descriptors or temp files when `os.fdopen()` fails between `mkstemp()` and the `with` block, and logs a warning (rather than silently swallowing) when cleanup itself fails.
- `rescan_vault()` no longer drops an index row for a file that appeared on disk between the walk and the reconciliation pass — late-arriving files are re-indexed instead.
- `BaseStorage` docstring now documents the (pre-existing, surprising) transaction contract: `execute()` / `executemany()` do not auto-commit; callers must call `commit()`. Mirrored in per-method docstrings.
- `user_config.json` parse failures now print an attention-grabbing banner to stderr (file, line, column, effect, remediation) in addition to the existing warning log. Silently-degraded vault integration was a support nightmare on research workstations.
- Regression tests pin the three design decisions called out in `CLAUDE.md`: grade precision at 1 decimal through GAP, the 0.5 m/s stop threshold, and the 30 s spike-detection cooldown.
- CI: pytest now enforces `--cov-fail-under=60`; `mypy` runs informationally on `src/biosensor_mcp` (soft-introduction — `continue-on-error: true` until the existing 16 errors are addressed).
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
