# Changelog

All notable changes to this project are documented here.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims at [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [9.2.0] — 2026-06-12

### Added

- **`tailor inspect --data-dir DIR`** — point the inspector at a
  non-default data directory (one containing `audit.db` and
  `vault.db`). Precedence: flag > `$TAILOR_DATA_DIR` > the
  `~/.tailor/data` default. Previously the only override was setting
  the environment variable before launch — `--data-dir` was the
  reasonable first guess and didn't exist (the confusion that
  motivated this release). Fail-fast posture: an explicitly named
  directory that does not exist is rejected at the CLI boundary
  (argparse error, exit 2) rather than silently rendering or
  exporting the "No audit database yet" empty page; an existing
  directory without databases keeps that honest-empty state per
  [ADR 0043](docs/adr/0043-read-only-inspector-not-application.md).
  No ADR amendment: per the `tailor pilot --source` precedent
  (v7.5.0), flag additions to an existing verb ship as a minor bump;
  ADR 0043's surface contract governs the command count, not
  per-command flags.

## [9.1.0] — 2026-06-10

Read-only inspector. The audit log gains an independent,
non-model-mediated rendered channel per
[ADR 0043](docs/adr/0043-read-only-inspector-not-application.md).

### Added

- **`tailor inspect`** — seventh CLI verb (deliberate amendment of the
  ADR 0040 six-command surface). Serves a read-only, localhost-only
  (hard-coded `127.0.0.1`), no-controls, stdlib-only HTML page over
  `audit.db` and the `vault.db` index: gate activity by outcome with
  plain-language gate explanations, recent calls (collapsed
  `params`/`error`, home-redacted, HTML-escaped), consent timeline
  derived from approve/revoke audit rows (labeled derived-not-live),
  scrubber posture with a prominent no-op-scrubber warning, token
  estimate sums, vault index counts (titles/slugs only, never note
  bodies). Flags: `--port`, `--no-browser`, `--export FILE` (static
  artifact; prints an operator-managed-retention note). Plus a
  `/health` probe. SQLite opened strictly read-only (URI `mode=ro`,
  enforced by a grep-class test); any non-GET HTTP verb returns 405.
- **ADR 0043** — "the inspector is an inspector, not an application":
  the hard no-write / no-network / no-controls / no-deps boundary, the
  three-stage invocation ladder (Stage 1 summoned built now; Stage 2
  ambient opt-in and Stage 3 default-on designed and trigger-gated),
  the rejected MCP spawner tool with reversal condition, and the named
  ADR 0039 carve-out (raw `params`/`error` render on the operator
  surface because it is the custodian's own channel, not the
  hosted-LLM transcript the column allowlist protects).
- `docs/design/research-framing.md` gains a sixth retention category:
  inspector `--export` artifacts are operator-managed retention.

### Fixed (pre-merge, caught by PR review)

- Windows: read-only SQLite URIs are now built with `Path.as_uri()` —
  the prior hand-built `file:C:/...` form parses as a relative path on
  Windows and would have failed to open any database.
- Render guard for NULL `outcome` values in foreign or hand-edited
  audit databases.

## [9.0.0] — 2026-05-26

Public-flip preparation. Vocabulary made domain-agnostic to match the
architectural commitment, license switched to AGPL-3.0-or-later, and a
reproducible token-efficiency benchmark ships as a load-bearing artifact
backing the README's "657×–938× cheaper" claims.

### Changed (breaking)

- **License**: `Apache-2.0` → `AGPL-3.0-or-later`. Forward-only. Tagged
  releases through v8.0.0 remain Apache-2.0 in perpetuity for recipients
  who already received them; v9.0.0 onward is AGPL. Rationale: AGPL's
  network-trigger clause (§ 13) is the structural lever against
  extractive cloud reuse — a future cloud provider that forks Tailor
  must publish their modifications under AGPL.
- **`PHIScrubber` → `DataScrubber`** (framework class). The seam
  contract is unchanged — institutions still subclass it to wire their
  IRB-approved scrubbing policy. The child-level `RedcapPHIScrubber`
  retains its HIPAA-specific name per [ADR 0037](docs/adr/0037-redcap-child-scope-export-directory-only-with-deferred-live-api.md);
  HIPAA *is* the institutional policy that child enforces.
- **`subject_id` → `entity_id`** across the `audit_log` column, every
  child's `param_schemas`, every vault tool, the shared
  `ENTITY_ID_SCHEMA` + `ENTITY_ID_PARAM_DOC` constants in
  `framework.interfaces`, and vault note frontmatter. "Subject" was
  research-shaped; the framework's identity-scoping primitive applies
  to any deployment recipe.
- **`csv_cohort_summary` → `csv_group_summary`** on the generic
  `csv_dir` child only. The biometric children's sibling tools
  (`force_cohort_summary`, `emg_cohort_summary`, `redcap_cohort_summary`)
  retain their `_cohort_` names because they ARE cohort-shaped in the
  research sense; the rename applies only where the surface is
  data-agnostic.

### Added

- **`benchmarks/token_efficiency.py` + `benchmarks/token_efficiency.md`** —
  reproducible measurement of the AI-economics claim in
  [ADR 0029](docs/adr/0029-token-reduction-as-analytical-quality.md).
  Per-query efficiency: 657.6× (single subject), 938.2× (16-subject
  cohort); session-persistence efficiency: 318.0× (cumulative across 5
  sessions). All measurements with `tiktoken cl100k_base`. The
  benchmark markdown includes assumptions, a quantitative
  prompt-caching counter-factual, and a Limitations section.
- **README license section** expanded from the bare text "Apache-2.0"
  to a ~35-line plain-English summary of AGPL-3.0-or-later's scope and
  the network-trigger nuance.
- **`docs/design/tailor-vocabulary.md` § "Vocabulary changes — v9.0.0"**
  enumerating the three renames in a table.

### Backward compatibility (durable state)

- **`audit_log` table**: `AuditLog.__init__` detects legacy
  `subject_id` column on boot and runs
  `ALTER TABLE audit_log RENAME COLUMN subject_id TO entity_id`. Every
  existing row preserved per [ADR 0001](docs/adr/0001-audit-log-as-backbone.md).
- **Vault note frontmatter**: `parser.split_frontmatter` aliases legacy
  `subject_id:` to `entity_id:` on read so notes written under the old
  name continue to load without migration.

No backward-compat for in-process callers — tool parameter names,
exported constants, and the audit-log column name break cleanly. That's
the v9.0.0 major-bump shape: API surface breaks, durable state migrates
transparently.

### Project framing

- The framework was always architecturally domain-agnostic; v9.0.0
  makes the externally-visible vocabulary match. Health research is
  the first deployment recipe shipped end-to-end, not the platform's
  identity. CLAUDE.md § "What This Project Is" updated; ADRs 0002,
  0003, 0009, 0015 each gain a `**Renamed in v9.0.0:**` header bullet
  documenting the rename's provenance + backward-compat mechanism.

## [8.0.0] — 2026-05-19

Recipient-experience MCP-offload. Three new framework-tier layers move
the walkthrough, fitting-room scaffolding, and source-config setup off
the CLI and onto MCP tools that Claude orchestrates conversationally.
Driven by a 2026-05-19 install-friction observation: a non-technical
recipient typed `--help` at a path prompt because terminals weren't a
familiar interface.

### Added

- **`SetupLayer`** (`framework/setup/`) exposes four MCP tools for
  source-config setup: `tailor_setup_status`,
  `tailor_setup_detect_schema`, `tailor_setup_confirm_schema`, and
  `tailor_setup_write_source_block`. Bounded-write authority is the
  load-bearing invariant — the write tool only writes the keys named
  in `SETUP_WRITE_KEY_ALLOWLIST = ("csv_dir", "matlab_file",
  "redcap_file")` with three layers of defense-in-depth.
- **`WalkthroughLayer`** (`framework/walkthrough/`) exposes
  `tailor_walkthrough_section(section: int)` with `min=1, max=5`.
  Replaces the v6.10.5 `tailor walkthrough` CLI showcase. Five
  sections cover the cohort thesis, router pipeline + audit row,
  three-tier consent + cost model, vault layer cross-session memory,
  and local-LLM guardian + deterministic processing.
- **`FittingRoomLayer`** (`framework/fitting_room/`) exposes three
  tools wrapping the pure helpers in the preserved
  `tailor.fitting_room` library module. Replaces the v6.9.0
  `tailor fitting-room` CLI command.
- **New `SETUP_CONFIG_WRITE` audit-log outcome** stamped on every
  successful `tailor_setup_write_source_block` call, with
  `domain="setup"` and `entity_id=NULL` (configuration is not
  subject-scoped per [ADR 0009](docs/adr/0009-vault-subject-keying.md)).
  An IRB reviewer reconstructs when Claude wrote configuration via
  `SELECT * FROM audit_log WHERE outcome='SETUP_CONFIG_WRITE'`.
- **[ADR 0040](docs/adr/0040-bounded-setup-time-conductor-surface.md)**
  codifies the bounded setup-time conductor surface as a carve-out
  from [ADR 0022](docs/adr/0022-local-llm-guardian.md)'s conductor-mode
  deferral.

### Removed (breaking)

- **Four CLI commands hard-removed** (no deprecation shim):
  `tailor walkthrough`, `tailor fitting-room`, `tailor tour`,
  `tailor demo`. The CLI surface contracts from 8 commands to 6:
  `serve / pilot / setup / redcap / status / uninstall`. Recipients
  now touch the terminal exactly once (`tailor pilot`) and everything
  else happens through Claude Desktop chat.
- **`src/tailor/tour.py`** (the v7.1.x re-export shim) deleted.
  Examples migrated to import from `tailor.fitting_room.main`
  directly. `wizard.py` PRESERVED — load-bearing for `cmd_setup`'s
  Strava OAuth wizard.

### Fixed

- **`_redact_home()` extended to SetupLayer wire-egress paths**
  (`written_path`, `user_config_path`, echoed `path`). Path strings
  collapse `Path.home()` to `~` per HIPAA Safe Harbor
  §164.514(b)(2)(i)(R), extending the v6.10.2 SetupHelpLayer redaction
  pattern. Username-bearing path strings stay off the hosted-LLM
  transcript; on-disk artifacts carry the un-redacted operator intent.
- **v7.5.0 orphan-cleanup defect retired structurally.** Fitting-room
  is no longer a CLI command writing Claude Desktop config; pilot is
  the sole CLI writer. No siblings, no orphan-cleanup-too-greedy, no
  bug. Skipped the v7.5.1 patch entirely.

## [7.6.0] — 2026-05-19

Data-source-agnostic vault layer ([ADR 0038](docs/adr/0038-vault-layer-is-data-source-agnostic.md))
structural sweep. Closes the commitment that v7.3.4 partial-closed and
v7.4.0 / v7.5.0 deferred.

### Added

- **`ChildMCP.vault_note_kinds`** — new optional property on the
  `ChildMCP` ABC defaulting to `()`. The running child overrides to
  return `("run_report", "trend_report", "compare_runs")`.
  `VaultLayer._compute_kind_metadata()` walks registered children,
  unions child-declared kinds with the framework-tier base, and
  populates `self._allowed_kinds` dynamically.
- **`value_column ↔ column` API parity** — `csv_cohort_summary` and
  `csv_force_decline` rename `column` → `value_column` to match
  `force_cohort_summary` / `emg_cohort_summary`. Shipped without a
  deprecation alias per the pre-outreach timing window.
- **AST-class invariant test** at
  `tests/framework/vault/test_v76_vault_is_data_source_agnostic.py`
  asserts the vault layer carries zero domain-coupling to running.

### Fixed

- **`ParamValidator.validate()` enforces `allowed_values` on scalar
  `str` types** — a pre-existing structural defect (mcp-protocol-auditor
  D1). The validator only enforced `allowed_values` inside the `list`
  branch, leaving every `ValidationSchema(type=str, allowed_values=[...])`
  site as a dead constraint.

### Deprecated

- **`vault_get_fitness_summary`** — gains a `DEPRECATED in v7.6.0`
  prefix in its description and a one-shot `log.warning` on first
  call. Removal target: future v7.7.x+ when zero references remain
  across deployed cue cards and no third-party child depends on it.

## [7.5.0] — 2026-05-18

Multi-source coexistence in the pilot wizard. Researchers with mixed-modal
data can configure CSV + REDCap + MATLAB through the same wizard, one
command per source, no manual JSON editing.

### Added

- **`tailor pilot --source={csv,matlab,redcap}`** argparse dispatch.
  Backward-compat: no-arg `tailor pilot` keeps the v6.2.1 CSV-default
  behaviour.
- **F1 deep-merge `_write_user_config`** — multi-source coexistence by
  construction. A researcher running `tailor pilot --source=matlab`
  two weeks after `tailor pilot --source=csv` does not lose their
  `csv_dir` block. AST-class all-call-sites-sweep regression test
  enforces the contract.
- **New `ATTEST_INITIAL` audit outcome** — distinct from `REATTEST` for
  first-config attestation. Threads `child_scrubber_id` and
  `source_metadata_fingerprint` so an IRB reviewer can reconstruct
  trust-root state at first configuration.
- **L1 / L2 product-split codified** — ChildMCP onboarding split into
  configured ingest of a shipped source (researcher-accessible L1
  wizard) and authoring a new source axis (RSE-accessible L2 path via
  `docs/guides/build-your-own-child.md`).
- **[ADR 0001 § Amendment 2026-05-18](docs/adr/0001-audit-log-as-backbone.md)** —
  narrow five-precondition CLI-helper exemption from the
  "missing-row-is-worse-than-failed-call" invariant.

## [7.4.0] — 2026-05-16

Audit log is now LLM-queryable.

### Added

- **`AuditQueryLayer`** — fourth framework-tier layer (parallel to
  VaultLayer / LocalLLMLayer / SetupHelpLayer). Single MCP tool
  `audit_query` surfaces structured columns from `audit_log` under a
  12-column + 1-derived (`has_error`) allowlist. Never exposes raw
  `error` text or raw `params` content. `limit=100` hard cap;
  `order by id desc` default.
- **[ADR 0039](docs/adr/0039-audit-log-is-llm-queryable-under-column-allowlist.md)**
  codifies "audit log is LLM-queryable under column allowlist" as a
  structural invariant.
- **PyPI publish at v7.4.0** — `tailor-mcp` 7.4.0 live on PyPI;
  colleague-outreach authorized.

## [7.3.4] — 2026-05-16

Phase 2 first-time-user setup pass — first end-to-end pass. The 2026-05-16 first real outside-recipient walkthrough (Windows + Claude Desktop, non-technical friend) produced five findings that drove four scope-shape escalations. Every ship-blocker closed before any code was written. Partial closure of ADR 0038 (vault layer is data-source-agnostic) on the demo hot path; full structural sweep deferred to v7.4.0.

### Fixed

- **Cohort thesis hot path (D1 + D1-companion).** `_extract_timestamps` in `force_csv/child.py` and `emg_csv/child.py` gains float-seconds fallback for bundled demo cohort 100 Hz fixtures. Handler key-mismatch (`decline_pct` vs `decline_pct_total`) closed; wire-verified peak and mean force values correct.
- **Vault layer de-Strava — F3 closure.** `_handle_fitness_summary`, `renderer.py` conditional Weekly Summary section, and `_infer_note_type` (`snapshot.md` → `"snapshot"` kind) updated. Vault layer is now data-source-agnostic on the demo hot path.

### Changed

- **API parity (D2).** `force_cohort_summary` + `emg_cohort_summary` parameter renamed `group_field` → `group_by` across ToolDefinition, param_schema, handler, and result-dict key. No deprecation alias per the pre-outreach timing window.
- **`cost_threshold` operator-configurable** from `user_config.json` (default `35_000` preserved; backwards-compatible). `tailor fitting-room` scaffold writes `cost_threshold: 15000` so the cost gate fires demonstrably on bundled fixtures.
- **Recipient ergonomics.** README gains per-OS `uv install` one-liner table. Fitting-room banner reshaped: single "Next step" leads, three science-shaped prompts, paths demoted to labelled "Files & locations" block; regenerate-warning added.
- **Schema description sweeps (D5, D6, D7).** `value_column`, `group_by`, and `SUBJECT_ID_PARAM_DOC` gain literal examples and semantic distinctions (biosensor-tier audit-only vs vault-tier filter per ADR 0009).

### Added

- **Bundled `snapshot.md` fixture** ships in the wheel under `_fixtures/cohort_demo_realistic/vault/`, including a "## Token cost shape" section with wire-audit-verified tier numbers.
- **AI-economics demonstration (ADR 0029 Option B).** Fifth banner prompt + "## Token cost shape" in `snapshot.md` ground the AI-economics claim in audit-verified numbers.
- **ADR 0038 (NEW, Proposed)** — "vault layer is data-source-agnostic" structural invariant. v7.3.4 ships partial closure (demo hot path); v7.4.0 ships the full sweep.
- **21 net-new tests** in `tests/test_v734_demo_readiness.py`.

## [7.3.3] — 2026-05-15

Closes the two red-team BORDER NOTES deferred from v7.3.2. Both addressed under a single structural argument — typed-exception taxonomy — rather than two point-fixes.

### Added

- **`OperatorActionRequired` marker class** (`framework.security`, co-located with `CircuitBreaker`). Constructor takes a keyword-only `recovery_action: str` argument validated as non-empty at construction; misclassification is a loud constructor error rather than a silent runtime defeat.
- **ADR 0003 § Amendment 2026-05-15 § Typed-exception taxonomy** ratifies the contract; reversal condition named.

### Fixed

- **Router breaker exemption at both dispatch sites (B1).** `isinstance(e, OperatorActionRequired)` check added at both `_dispatch` and `dispatch_internal` handlers. Audit row still records `outcome=ERROR` with full v7.3.1 W5 invariant kwargs. The initial plan named only the public dispatch site; proposal-mode audit caught the internal-path miss.
- **`RedcapMetadataFingerprintMismatch` reparented to `OperatorActionRequired`** with `recovery_action="tailor redcap reattest"`. v7.3.2 invariants preserved verbatim.
- **Drop defensive try/except in `_detect_fingerprint_mismatch` (B2).** The proposed narrowing to `(OSError, ValueError, ...)` was a no-op — `_load_metadata` already swallows those classes internally. Dropped entirely; future signature changes propagate rather than silently disabling mismatch detection.
- **Pipe-buffer stall path closed (F-G).** On Windows, ~8 `OperatorActionRequired` events fill the 4 KB OS pipe buffer, stall the server, and swallow the recovery hint. Fix: silence the router's logger output entirely on the exempt path — audit row + wire envelope already carry the full event and recovery hint. Two T8 regression tests lock closure.
- **31 net-new tests** (16 in `test_v733_operator_action_required.py`, 14 in `test_serve_v733_wire_audit.py`, 1 in `test_redcap_shape.py`).

## [7.3.2] — 2026-05-15

Closes the two remaining v7.3.0 WATCH findings deferred from v7.3.1: (a) `project_metadata.csv` trust-root attestation seam and (c) small-cell suppression for aggregate count surfaces. Both land as framework seams rather than per-child policies, matching ADR 0003's structural argument.

### Added

- **Trust-root fingerprint primitive.** `RedcapPHIScrubber.fingerprint` computes SHA-256 over a canonical-form rendering of sorted `(field_name, identifier_flag)` tuples. BOM/CRLF/whitespace round-trips do NOT trip; flag flips and field additions/removals DO.
- **`audit_log.source_metadata_fingerprint TEXT` column** + `idx_audit_source_metadata_fingerprint` index. Domain-agnostic naming so future EDF / FHIR / vendor-sensor children inherit the seam without column renames. `ALTER TABLE` migration on legacy audit DBs.
- **Fingerprint threaded across 19 audit-call sites + 5 `_meta` blocks.** `ChildMCP.child_source_metadata_fingerprint` interface property added (default `None`); `RedcapFileChild` overrides; no breaking change for other children.
- **`RedcapFileChild` fingerprint-mismatch detection at `execute()`.** Re-reads `project_metadata.csv` on every call; on drift returns typed `REDCAP_METADATA_FINGERPRINT_MISMATCH` error envelope pointing operator at `tailor redcap reattest`. Forward-only policy per ADR 0003 § Amendment 2026-05-15.
- **`tailor redcap reattest` CLI subcommand.** Prints cached + new fingerprints and a sorted field-by-field trust-root listing. On `y`, writes a `REATTEST` audit row.
- **Small-cell suppression.** `RedcapProcessing.apply_small_cell_suppression_to_top_values`, `…_to_groups`, and `…_to_completion_counts` static helpers. Below-threshold entries collapse into a sentinel. Default k=5 (HHS SDL baseline); configurable via `redcap_file.small_cell_suppression_threshold`; validated ≥ 2 at config-load time.
- **`small_cell_suppression_threshold` + `small_cell_warning`** surfaced in every result envelope where suppression was applied.
- **ADR 0003 § Amendment 2026-05-15 (NEW)** — reversal condition named (promote to `ChildMCP` abstract method on third domain using the seam).
- **49+ net-new tests** (fingerprint/canonical-state, small-cell processing, mismatch detection, reattest CLI).

### Fixed

- **(F-A)** `cmd_redcap_reattest` was hand-rolling a raw `sqlite3.INSERT`, leaving `scrubber_id` NULL on `REATTEST` rows. Rewrote to use `AuditLog.record()`.
- **(F-B)** Mismatch path returned a dict-with-error-key rather than raising; audit row was stamped `outcome="SUCCESS"`. Switched to raising typed `RedcapMetadataFingerprintMismatch`.
- **(F-C)** `completion_counts` (`{instrument: count}`) was left unsuppressed despite `top_values` and cohort `groups` being suppressed.
- **(F-F / W5)** Audit-record-site invariant test rewritten from textual-window scan to AST-based detection (`ast.walk` on `self._audit.record()` call nodes, inspecting only `node.keywords`). Enforcement class is now AST-class; textual-adjacency false-positives that fooled v7.3.1 cannot recur.

## [7.3.1] — 2026-05-15

Bug-hunt followup patch + structural gate-composition closure. Closes three VIOLATION-class defects and four HIGH findings from a seven-specialist max-depth audit against v7.3.0, plus a fifth defect surfaced by adversarial pairing on this banner's draft. Two VIOLATIONs were direct falsifications of v7.3.0 banner claims — documented as second-pass catches.

### Fixed

- **Banner-claim falsification 1 (IRB-stakes).** v7.3.0 claimed `child_scrubber_id` was threaded into all failure rows. Five consent-handler audit-record sites (`framework/router.py:1281, 1334, 1359, 1395, 1401`) were missed. On a REDCap deployment, consent-revocation audit rows — the highest-leverage IRB events — silently recorded `child_scrubber_id` as NULL. All five sites corrected; five unit tests + wire-side verifier `TestW3ConsentAuditRowsThreadChildScrubberId`.
- **Banner-claim falsification 2.** A malformed `redcap_file` block (missing required `path` key) caused `tailor serve` to exit rc=1, taking down the entire server (running + csv_dir + vault + local_llm). `__main__.py` registration wrapped in try/except mirroring the MATLAB pattern. Subprocess regression test + `TestW4MisconfiguredRedcapBoots`.
- **PHI Safe Harbor surface reduction.** 11 `redcap/child.py` error-envelope sites and 3 `redcap/scrubber.py` warning sites swap raw-path interpolation for `<configured_redcap_path>` placeholders. Full paths retained in stderr `log.warning` only (HIPAA Safe Harbor §164.514(b)(2)(i)(B + R)).
- **`setup_help/__init__.py:221` typo** — `"redcap_export"` → `"redcap_file"`. Closed an inverse-v6.10.2 trap where `SetupHelpLayer` fired on working REDCap deployments.
- **REDCap child added to `vault_writer._registered` list** — closing the v7.3.0 asymmetry where vaultable_tools were collected for every child except REDCap.

### Added

- **`child_scrubber_id` surfaced in `_meta`** across all five dispatch paths (child dispatch, vault layer, local_llm layer, setup_help layer, dispatch_internal). Wire-output shape uniform across all paths.
- **Structural gate-composition closure (option 2).** `phi-irb-risk-reviewer` prompt extended with mandatory "Step 1.5 — All-call-sites sweep on new invariants": when a diff adds a new `audit_log` column, `_meta` field, or `ChildMCP` property, every existing call site must be verified.
- **50 net-new tests** (1137 prior → 1187); 18 wire-level regression tests in `tests/test_serve_v731_wire_audit.py`.
## [7.3.0] — 2026-05-14

REDCap existence-proof child + child-level PHI scrubber seam.

### Added

- **`RedcapFileChild`** — six tools across all three tiers
  (`redcap_list_records`, `redcap_record_detail`,
  `redcap_summary_report`, `redcap_cohort_summary`, `redcap_records`,
  `redcap_raw_records`). Opt-in via `redcap_file` block in
  `user_config.json`.
- **[ADR 0037](docs/adr/0037-redcap-child-scope-export-directory-only-with-deferred-live-api.md)** —
  scope-bounded to REDCap CSV export directories; live REDCap REST
  API support deferred behind a named reversal condition. No new
  optional extras (REDCap exports are stdlib-only).
- **[ADR 0003 § Amendment 2026-05-14](docs/adr/0003-phi-scrubber-seam.md)** —
  child-level PHI scrubber seam parallel to the framework-level seam.
  `RedcapPHIScrubber` reads `identifier=yes/no` flags from
  `project_metadata.csv` and scrubs flagged fields inside
  `RedcapFileChild.execute()` before the result returns to the
  framework-level seam.
- **New `audit_log.child_scrubber_id` column** records the child's
  internal scrubber identity (`"redcap_metadata_flags"` for REDCap
  calls; NULL for csv_dir / matlab_file / running which inherit the
  ABC default).

## [7.2.0] — 2026-05-14

MATLAB existence-proof child as the second non-CSV source axis.

### Added

- **`MATLABFileChild`** — six tools across all three tiers
  (`matlab_list_files`, `matlab_file_detail`, `matlab_summary_report`,
  `matlab_cohort_summary`, `matlab_downsampled`, `matlab_raw_array`).
  Opt-in via `matlab_file` block in `user_config.json`.
- **[ADR 0036](docs/adr/0036-matlab-child-scope-v72-only-with-deferred-hdf5.md)** —
  scope-bounded to `.mat` v5/v6/v7.2 via scipy pulled in as an optional
  dep (`pip install tailor-mcp[matlab]`). v7.3 HDF5-based `.mat` is
  detected via magic bytes and rejected with a typed-error envelope.

## [7.1.1] — 2026-05-14

Source-agnostic framework claim. Documentation and internal structural language formalised to reflect that the framework is not specific to any data domain — the running (Strava) child and CSV biometric children are deployment recipes, not the platform's identity. This claim is the named milestone that the MATLAB child (v7.2.0) and REDCap child (v7.3.0) demonstrate in code.

### Changed

- **Framework framing** updated in `CLAUDE.md`, module docstrings, and `ChildMCP`/`children` docstrings to reflect data-source-agnostic architecture.
- **`docs/design/` updated** to platform framing consistent with the v5.0.0/v7.0.0 research-shift and rename.
## [7.1.0] — 2026-05-14

CLI rename to match recipient-experience naming principle.

### Changed

- **CLI verbs renamed**: `tailor demo` → `tailor walkthrough`,
  `tailor tour` → `tailor fitting-room`. Old verbs preserved as
  one-cycle deprecation shims with stderr hints citing
  [ADR 0035](docs/adr/0035-cli-rename-walkthrough-and-fitting-room-and-recipient-experience-naming-principle.md).
- **`src/tailor/tour.py` → `src/tailor/fitting_room.py`** via `git mv`
  (history preserved); one-line re-export shim at the old path.
- **Server-name** `tailor-tour-{variant}` →
  `tailor-fitting-room-{variant}`; the existing
  `_is_orphan_entry_key` prefix-cleaner handles both keys.

### Added

- **[ADR 0035](docs/adr/0035-cli-rename-walkthrough-and-fitting-room-and-recipient-experience-naming-principle.md)** —
  recipient-experience-shaped naming principle, recipient-evaluation-class
  scope, operator-class grandfathered list.
- **`docs/design/tailor-vocabulary.md`** — new "Recipient-facing
  surfaces" section names walkthrough + fitting-room with etymology
  and naming principle.

## [7.0.13] — 2026-05-13

PyPI publish. The `tailor-mcp` package is live on PyPI; the canonical install path switches from hand-delivered wheel to `uv tool install tailor-mcp`. Unbundles the PyPI publish decision (tooling question: YES) from the repo public-flip decision (audience question: NOT YET), per ROADMAP Phase 2.

### Added

- **`tailor-mcp` published to PyPI.** `uv tool install tailor-mcp` is the install command. Any recipient with PyPI access can now install without a back-channel.
- **PyPI/public-flip decoupled from repo public-flip.** The repo remains private under the three-condition public-flip trigger (held item, ROADMAP § Held).

## [7.0.10] — 2026-05-12

README install-command update pass. Phase 1 closed — all four Phase 1 housekeeping deliverables have now landed (GitHub repo rename v7.0.6, `tailor migrate` retired v7.0.9, README updated v7.0.10). Phase 2 (public-launch readiness) unblocks.

### Changed

- **README install commands** updated to reflect the Phase 0–proven install path. Six framing callouts and table rows revised; four `#phase-0--install-path-validation` anchors repointed to `#at-a-glance`; ADR count refreshed 31 → 34.

## [7.0.9] — 2026-05-12

Retire `tailor migrate` subcommand. The v6 user population was empirically zero; the migrate path was over-engineered scaffolding for a migration no external recipient ever needed.

### Removed (breaking)

- **`tailor migrate` subcommand** hard-removed. No deprecation shim; no external machine ever held a v6 install state.
- **Startup migration warning** (stderr line when `~/.biosensor-mcp/` exists and `~/.tailor/` is absent) also retired.

### Added

- **ADR 0034** — rationale for removal; reversal condition named (promote back if a real v6 user is discovered).

## [7.0.8] — 2026-05-12

Phase 0 closure under lenient read of exit criterion. The 2026-05-12 macOS install — a friend ran the wheel install and `tailor tour` on their own Mac, with the project author watching but not touching the machine — satisfied the lenient read. The strict read (two fully unassisted outside-recipient installs on different OSes) remains open and is being satisfied opportunistically. Phase 1 work unblocks per the project author's call.

### Changed

- **CLAUDE.md banner updated.** v7.0.8 banner documents Phase 0 lenient-read closure; v7.0.0 banner retained intact as historical record (banner-stacking convention, established v6.11.1).

## [7.0.6] — 2026-05-10

Retire public-mirror distribution channel + GitHub repo rename (`Biosensor-to-LLM-Connector` → `tailor-mcp`) as a doc-truth pass.

### Removed

- **Public-mirror distribution channel retired** per ADR 0032. The hand-delivered GitHub URL wheel method is the sole distribution path until the PyPI publish at v7.0.13.

### Changed

- **GitHub repo renamed** from `Biosensor-to-LLM-Connector` to `tailor-mcp`. GitHub auto-redirect preserves existing clones. Closes ADR 0031 § Negative consequences "repo name still carries old identity" known-debt entry.

### Added

- **ADR 0032** — retire public-mirror rationale; reversal condition named.

## [7.0.4] — 2026-05-09

Install-path diagnosis — PATCH-not-RESTRUCTURE verdict. A 2026-05-09 self-driven diagnosis on a fresh `tailor-recipient` user account (Windows, Microsoft Store Claude Desktop) confirmed: the existing `uv tool install + tailor tour + Claude Desktop restart` ritual is achievable for non-developer recipients with targeted patches. A single-binary executable, Docker container, or one-shot installer is not required.

### Fixed

- **Windows install friction points** logged and resolved during the diagnosis pass. Specific findings documented in CLAUDE.md v7.0.4 banner (cp1252 encoding, dual-path Claude Desktop config, sibling-entry cleanup, Microsoft Store sandbox paths).

### Changed

- **Phase 0 PATCH verdict recorded.** Restructure shape (PyInstaller / Nuitka, Docker, one-shot installer) explicitly deferred as not load-bearing for Phase 0 exit.
## [7.0.0] — 2026-05-08

Project rename: `Biosensor MCP` → **Tailor** (per [ADR 0031](docs/adr/0031-rename-to-tailor-and-wardrobe.md)).
The first major version bump in the project's history. Every prior
release shipped under the old name; v7.0.0 establishes the new identity
and provides a non-destructive migration path.

### Changed (breaking)

- **PyPI distribution name**: `biosensor-mcp` → `tailor-mcp` (the bare
  `tailor` is taken on PyPI; `tailor-mcp` matches the historical
  pattern and is available).
- **Python import name**: `biosensor_mcp` → `tailor`.
  `from biosensor_mcp import ...` → `from tailor import ...`.
- **CLI command**: `biosensor-mcp` → `tailor`. `biosensor-mcp serve` →
  `tailor serve`; same shape for `pilot`, `tour`, `setup`, `status`,
  `demo`, `uninstall`.
- **Config + data directories**: `~/.biosensor-mcp/` → `~/.tailor/`.
- **Environment variables**: `BIOSENSOR_CONFIG_DIR` →
  `TAILOR_CONFIG_DIR`; `BIOSENSOR_DATA_DIR` → `TAILOR_DATA_DIR`;
  `BIOSENSOR_DEMO_INSTALL_URL_BASE` → `TAILOR_DEMO_INSTALL_URL_BASE`.
- **Claude Desktop registration keys**: `biosensor-mcp` → `tailor`;
  `biosensor-tour-<variant>` → `tailor-tour-<variant>`.
- **Diagnostic tool name**: `biosensor_setup_help` →
  `tailor_setup_help` (user-visible to AIs via tools/list).
- **Display name throughout docs and code**: `Biosensor MCP` → `Tailor`.

### Added

- **`tailor migrate` subcommand** for non-destructive v6 → v7
  filesystem upgrade. Copies `~/.biosensor-mcp/` to `~/.tailor/` by
  default; `--move` to remove the legacy directory after copying.
  Refuses to overwrite a non-empty destination.
- **Startup migration warning**: `tailor` emits a single stderr line
  when `~/.biosensor-mcp/` exists and `~/.tailor/` is absent or empty,
  pointing the user at `tailor migrate`. Non-blocking; auto-prompts
  would silently park during `tailor serve` (Claude Desktop subprocess).
- **Wardrobe** as the user-facing engine word for what the framework
  holds on the user's behalf — themes, moments, evidence, failure
  modes, audit history, source data. Replaces the working term
  *"substrate"* used in design conversations. Internal architectural
  identifiers (`vault/`, `framework/`, `audit.db`) are unchanged;
  *Wardrobe* is the user-facing aggregate term.
- **Counter-programming invariant** per ADR 0031 — visual language
  stays non-fashion, onboarding copy actively redirects the literal-
  clothing read, content shown in any "your Wardrobe" view is
  visibly diverse from first impression. PRs adding fashion-domain
  language are in conflict with ADR 0031.
- **Dual-prefix Claude Desktop cleanup**: `_clean_claude_desktop_orphan_entries`
  + `_is_orphan_entry_key` helper match BOTH legacy `biosensor-*` and
  current `tailor` / `tailor-*` keys so v6 → v7 upgrades don't leave
  orphan entries pointing at a removed binary. Generalises the v6.9.2
  prefix-match contract to handle future prefix changes.
- **+13 tests** verifying the migration matcher contract directly:
  `TestOrphanEntryKeyMatcher` class (5 tests) + four legacy / current
  cleanup-scenario tests in `tests/test_uninstall_cleanup.py`.

### Migration

A v6 user upgrades by:

1. `pip install --upgrade tailor-mcp` (or re-running the
   `uv tool install` command from the GitHub URL).
2. `tailor migrate` to copy `~/.biosensor-mcp/` to `~/.tailor/`.
3. `tailor tour --force` (or `tailor pilot`) to re-register with
   Claude Desktop under the new key. The dual-prefix cleanup removes
   any stale `biosensor-*` entries automatically.
4. Update any shell rc files / CI workflows / Claude Desktop config
   `env` blocks that set `BIOSENSOR_CONFIG_DIR` /
   `BIOSENSOR_DATA_DIR` to the new `TAILOR_*` names.

The startup warning fires on every `tailor` invocation while step 2
is pending, so the migration is hard to miss.

### Historical preservation

- `CHANGELOG.md` (this file's pre-v7.0.0 entries), the dated session
  reports under `docs/reports/*-2026-05-01.md`, and the 2026-05-05
  vault moment file retain the legacy `biosensor-mcp` /
  `Biosensor MCP` references — they describe past state under the
  old name, and rewriting them would falsify the historical record.

### Architecture preserved (intentionally NOT changed)

- Internal architectural identifiers — `framework/`, `vault/`,
  `local_llm/`, `children/`, `RouterMCP`, `VaultLayer`, `ChildMCP`,
  `RunningChild`, `audit.db`, `vault.db` — describe the architecture,
  not the project's identity.
- Domain-term language — *"biosensor children"*, *"biosensor-tier
  gates"*, *"biosensor data"* — describes the kind of data those
  components handle (biological sensor data), which the framework
  still does. The framework continues to ship with the running
  child (Strava) and four CSV-based biosensor children (csv_dir,
  force_csv, emg_csv, template).
- The first deployment recipe (demo cohort researcher first-look) is
  unchanged in content; it carries the new naming.

### Verification

- pytest: 930 passed (917 prior + 13 net new for the migration matcher)
- ruff: clean
- security probe: 76/76 passed
- CLI smoke (`tailor --help`): clean
- mcp-protocol-auditor: NOT TRIGGERED (no router/security/vault
  behavioural paths touched — only import names changed)
- recipient-install-validator: SKIPPED per the v6.11.x silent-park
  falsification documented in project memory; operator hand-validation
  is the v7.0.0 backstop until ADR 0028's v2 escalation lands

## [Unreleased]

### Fixed
- `framework.audit._dumps` passes `orjson.OPT_NON_STR_KEYS` so int-keyed
  dicts (e.g. `compute_hr_zones`' `{1..5: count}`) serialize the same way
  stdlib json would coerce them. Before the fix, any tool result
  containing a non-string dict key raised `TypeError: Dict key must be
  str` inside the router's cost-estimation step, causing the call to be
  audited as `ERROR` and returning `{"error": "Dict key must be str"}`
  to the LLM. Every `strava_run_report` call on the orjson backend hit
  this — surfaced by the new worked-example notebook, which was the
  first thing to take a realistic result through the full
  `router._dispatch` pipeline. Regression coverage added in
  `tests/framework/test_audit.py::TestJSONBackendCoercion` and
  `tests/framework/test_router.py::TestRunningChildEndToEnd`.

### Added
- **10-minute worked-example notebook** at
  [docs/guides/worked-example.ipynb](docs/guides/worked-example.ipynb).
  End-to-end walkthrough of router wiring, a Tier-1 call, the audit
  row, the Tier-2 consent gate, and a vault theme round-tripping to
  Obsidian markdown — all on bundled synthetic run data, no OAuth, no
  network. Marked as shipped in [ROADMAP.md](ROADMAP.md).

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
