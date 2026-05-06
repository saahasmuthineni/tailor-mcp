# Roadmap

Work that's explicitly deferred — what the framework is *not* yet, and
why each item matters for the research framing. Each section is a
one- or two-sentence pitch plus context; no implementation details.

## At a glance

| Item | Effort | Impact | Unblocks |
|---|---|---|---|
| [New ChildMCPs (CGM / sleep / ECG / EDF / FHIR)](#new-childmcps-for-research-relevant-data-sources) *(template skeleton + CSV child shipped — see that section)* | M–L | High | Broader adoption |
| ~~[Per-subject `subject_id` on vault tools](#per-subject-parameter-scoping-on-vault-tools)~~ *(shipped in v6.2 — see [ADR 0009](docs/adr/0009-vault-subject-keying.md))* | — | — | — |
| [Real PHI-scrubbing implementations](#real-phi-scrubbing-implementations-behind-the-phiscrubber-slot) | M | High | Any deployment with actual PHI |
| [Per-analyst attribution on vault evidence](#per-analyst-attribution-on-vault-evidence-blocks) | S | Medium | Multi-analyst studies |
| [Deterministic mode + seed control](#deterministic-mode-with-seed-control) *(prerequisite shipped silently; residual scope is the audited-flag-plus-provenance-hash pairing — see [ADR 0008](docs/adr/0008-deterministic-by-construction-processing.md))* | XS | Low | Reproducible paper results |
| [Provenance hashing on derived metrics](#real-provenance-hashing-on-derived-metrics) | M | Medium | Byte-level reviewer traceability |
| [Vault-freeze for manuscript submission](#freeze-vault-operation-for-manuscript-submission) | S | Medium | Submission-ready snapshots |
| ~~[Worked-example notebook](#worked-example-notebook-against-a-published-analytical-question)~~ *(shipped — [docs/guides/worked-example.ipynb](docs/guides/worked-example.ipynb))* | — | — | — |
| [LLM-client evaluation harness](#evaluation-harness-for-llm-client-behavior) | M | Medium | Making the governance claim measurable |
| [CLI UX: rename `setup` → `setup-strava`](#cli-ux-rename-setup--setup-strava) | XS | Low | Disambiguating the two wizards |
| [CLI UX: rename legacy `demo` → `verify`](#cli-ux-rename-legacy-demo--verify) | XS | Low | Naming the operator-self-verification path correctly alongside `tour` |
| [Pre-existing csv_dir HIGH-region coverage debt (v6.5.1)](#pre-existing-csv_dir-high-region-coverage-debt-v651) | XS | Low | Cleaner ADR-0014 baseline |
| ~~[Local-LLM guardian](#local-llm-guardian)~~ *(shipped in v6.6 — see [ADR 0022](docs/adr/0022-local-llm-guardian.md))* | — | — | — |
| [PHI sidecar-schema validator (deferred)](#phi-sidecar-schema-validator-deferred) | S | High | Stronger IRB-cleared posture for csv_dir |

Effort: S (days), M (weeks), L (month+). Impact reflects research value,
not engineering elegance.

## Shipped in v6.10.2 (2026-05-06)

- `SetupHelpLayer` — new framework-tier layer (parallel to `LocalLLMLayer` per ADR 0022 shape) registered conditionally when `_demo_blocks_absent()` detects no `csv_dir` blocks in `user_config.json`. Surfaces a single diagnostic tool (`setup_help_get_status`) that routes an external Claude to `biosensor-mcp tour`; invisible on configured deployments (SH7 wire-test confirms). `_redact_home()` strips HIPAA Safe Harbor §164.514(b)(2)(i)(R) address components before surfacing on the wire. 16 unit tests (trigger predicate, layer surface, redaction, dispatch, audit-row provenance). 7 new subprocess wire-tests SH1-SH7 added by mcp-protocol-auditor.
- `RECIPIENT_README.md` bundled in the wheel (`pyproject.toml` `*.md` glob added to package-data). An external Claude inspecting the .whl now discovers `biosensor-mcp tour` as the recovery path without source-code archaeology — the structural lesson from dad's transcript.
- ADR 0012 amended: Decision section extended to all three framework-tier PHI-scrubber bypass sites (vault + local_llm + setup_help) with per-layer invariants and reversal conditions. Closes phi-irb-risk-reviewer Lens 4 finding.
- CUE_CARD.md recovery row added for the "tool list shows only ask_local_oracle + strava_list_runs" symptom.
- Tool surface: 50 when degraded (setup_help visible), 49 when scaffolded (baseline unchanged). Patch bump.
- Structural lesson: an external Claude inspecting the wheel must be able to discover `biosensor-mcp tour` without source-code archaeology. `SetupHelpLayer` is the in-chat fallback when wheel-inspection fails.

## Shipped in v6.10.1 (2026-05-06)

- Fixed four Windows recipient demo blockers found during direct `biosensor-mcp tour` testing on Windows 11 PowerShell cp1252: Bug 1 (`→` → `->` in `cmd_status`), Bug 2 (OperationalError guard around Strava-tier SELECT on fresh tour install), Bug 3 (`←` → `<-` in `pilot.py`), Bug 5 (unicode glyphs `❌`/`✅` → `[X]`/`[OK]` in `wizard.py`).
- New private `_make_cli_stdout_resilient()` in `__main__.py`: reconfigures sys.stdout/sys.stderr with `errors='replace'` so future non-cp1252 glyphs degrade to `?` rather than crashing. 3-layer defense: static glyph removal + runtime reconfigure + static guard test suite.
- +17 regression tests (851 total): 10 in `test_cli_windows_resilience.py` (5 parametrized static-guard, 3 stdout-helper, 2 fresh-tour-install); +8 subprocess tour-path MCP wire tests in `test_serve_mcp_protocol.py` covering previously-untested force_csv + emg_csv wire surface.
- Bug 4 (`_extract_timestamps` paired-iteration refactor) deferred to v6.11.0: red-team-reviewer HIGH OBJECTION — minimal fix produced 40% systematic error in `time_to_50pct_drop_s` on mixed-defect CSVs via silent index-misalignment. ADR 0010 adversarial pairing demonstrably caught this. No API changes; patch bump.

## Shipped in v6.10.0 (2026-05-06)

- `cue-card-rehearsal-auditor` specialist promoted per [ADR 0025](docs/adr/0025-cue-card-rehearsal-as-release-gate.md). Read-only agent (opus model, tools: Read/Grep/Glob) audits cue-card prompts against ToolDefinition schemas and emits per-prompt verdicts (PASS / WRONG-TOOL / WRONG-PARAMS / AMBIGUOUS). Closes the structural class of failure responsible for both v6.9.1 and v6.9.2: schemas whose envelope passes structural gates but silently fails when Claude infers parameters from operator prose. Mandatory pre-tag trigger wired into `release-shipper`.
- ADR 0025 cites ADRs 0008, 0010, 0011, 0014, 0016. First-run dogfood evidence included: REVIEW aggregate, AMBIGUOUS verdict on Step 2 cohort prompt demonstrates the gate fires on real under-specification without false-positiving on structural envelope correctness. Deferred (named in ROADMAP): `emg_cohort_summary.value_column` schema hygiene; CUE_CARD.md v6.9.0-footgun recovery row retention decision (boss-decision item).
- Same governance/team-shape release shape as v6.3.0 (no framework code changes); 834/834 pytest, ruff clean, 76/76 probe, CLI smoke PASS. Minor bump.

## Shipped in v6.9.2 (2026-05-06)

- Hardened `cmd_uninstall` to prefix-match `biosensor-` so `biosensor-tour-<variant>` orphan Claude Desktop entries are cleaned alongside `biosensor-mcp`; extracted `_clean_claude_desktop_biosensor_entries()` helper (7 new tests in `test_uninstall_cleanup.py`).
- Switched all CSV-open and JSON-sidecar reads in `force_csv` (3 sites), `emg_csv` (3 sites), and `csv_dir` (6 sites) from `utf-8` to `utf-8-sig` for transparent BOM stripping — Excel- / PowerShell-saved data would otherwise silently corrupt first-column header lookups and sidecar filename matches (`TestBomTransparency` in each shape suite, +4 tests).
- Fixed `tour --force` to `rmtree` the target dir before scaffolding so a broken scaffold can be recovered as `WINDOWS_QUICKSTART` documents (+1 test in `test_tour_subcommand.py`).
- +12 regression tests total; 834 pass. Bug fixes only; patch bump.

## Shipped in v6.9.1 (2026-05-06)

- Fixed cohort-handler logical→physical column-alias resolution in `force_csv` and `emg_csv` children. `_handle_cohort_summary` now maps `value_columns` logical alias names to physical CSV header names before metric dispatch, closing the v6.9.0 first-prompt-failure footgun (16 silent `column not found` load_errors when Claude guessed the logical name from operator prose).
- Registered the 16 bundled 31P-MRS CSVs in the `tour` scaffolding output. The files were bundled in the wheel but `user_config.json` had no `csv_dir` block for `mrs/`; they were unreachable via any tool until this fix.
- 6 new regression tests: `TestCohortSummaryAliasResolution` (2 tests) in `force_csv` and `emg_csv` shape suites; updated user_config-shape assertion in `test_tour_subcommand.py`.
- `CUE_CARD.md` sharpened: Variant-C recovery steps clarified; Variant-B rows added for `force_cohort_summary` / `emg_cohort_summary` tools.

## Shipped in v6.9.0 (2026-05-04)

- Wheel-distributed `biosensor-mcp tour` CLI subcommand ([ADR 0024](docs/adr/0024-wheel-distributed-tour-and-fixture-bundling.md)). Scaffolds the HIP Lab realistic demo from bundled wheel fixtures into `~/.biosensor-mcp/demos/hip-lab/`; copies 48 CSVs + 3 metadata sidecars + 1 seed vault moment via `importlib.resources`; writes `user_config.json` with absolute paths; merges Claude Desktop config — recipient never types an env var. Flags: `--variant`, `--target`, `--no-claude-desktop`, `--force`. Inherits `pilot.py`'s atomic-write + BOM round-trip + deep-merge hardenings.
- HIP Lab realistic fixtures bundled into the wheel. Migrated from `examples/hip_lab_demo/realistic/` to `src/biosensor_mcp/_fixtures/hip_lab_demo_realistic/`; `pyproject.toml` package-data globs extended. Distribution: pre-built wheel via Drive/email; no PyPI publish; wheel size 1.26 MB (budget 10 MB).
- ADR 0024 codifies synthetic-by-construction precondition — bundling permitted only for bytes that are synthetic by construction; real or de-identified cohort data require a superseding ADR.
- `examples/hip_lab_demo/realistic/setup.py` preserved as thin shim delegating to `tour_main()`; `rehearse.py` rewritten to rehearse the recipient code path against a temp dir; `WINDOWS_QUICKSTART.md` becomes a fully wheel-driven recipient guide.
- Deferred (named in ROADMAP): legacy `biosensor-mcp demo` → `verify` rename; PyPI publish path when recipient set crosses ~10.
- 23 new tests (20 `test_tour_subcommand.py` + 3 subprocess `test_serve_mcp_protocol.py`); 818/818 passed. 7-agent release pass clean.

## Shipped in v6.8.1 (2026-05-03)

- C3 peak-tie systematic bias fix in `csv_dir/processing.py`. New `_last_peak_index` module-level helper scans values from the end backward; applied at both call sites (`aggregate_metric` for `time_to_50pct_drop_s`, `force_decline_summary` for `peak_index`). Eliminates the systematic inflation of `time_to_50pct_drop_s` on isometric force traces with ramp → plateau → decline shape: participants with longer plateau holds received larger positive bias, creating a between-groups confound for `csv_cohort_summary` comparisons. Three new regression tests closing the plateau / unique-peak regression paths. 676 → 679 tests; 85% coverage; `processing.py` at 99%. No architecture changes; patch bump.

## Shipped in v6.8.0 (2026-05-03)

- Local-LLM cooperation-loop pattern, PR2 (LLM-driven gap reasoning). [ADR 0023](docs/adr/0023-local-llm-cooperation-loop.md). New `OracleResponse.next_best_calls` and `OracleResponse.unresolved_intent` fields completing the cooperation-loop contract; `OllamaBackend` JSON-mode prompt extension with defensive list-coercion; `NullBackend` empty-default inheritance by construction; `ask_local_oracle` tool description rewritten to teach hosted Claude the multi-pass cooperation loop; two new `audit_log` columns (`oracle_next_best_calls_count`, `oracle_unresolved_intent_count`) by symmetry with PR1's `oracle_substrate_count`. ADR 0023 amended: § Audit-log columns names all three, § Negative consequences token-estimate corrected (~290 measured vs ~2500 estimated), § Neutral consequences PR1/PR2 ADR 0012 distinction added. Operator guide: "Important precision — gap-reasoning egress" subsection added. Research-framing § Consent withdrawal: oracle audit rows named as third retention category. 15 new regression tests (12 PR2 contract/parser/fallback + 3 audit-column) + 4 subprocess tests from mcp-protocol-auditor; 676/676 pass. Coverage 85%. 7-agent release pass clean (all WATCH/OBJECTION findings addressed before ship). No new tools — `ask_local_oracle` gains response fields only.

## Shipped in v6.7.0 (2026-05-03)

- Local-LLM cooperation-loop pattern, PR1 (substrate-vision asymmetry made executable). [ADR 0023](docs/adr/0023-local-llm-cooperation-loop.md). New `OracleResponse.related_substrate` field; new `audit_log.oracle_substrate_count` column; new public `VaultWriter.storage` property; `(kind, slug)` substrate dedup; `substrate_scan_warning` parallel to `scrubber_warning` for swallowed VaultStorage exceptions; `_collect_subjects` scalar-filtered to mirror `_flatten_claims`. 26 new regression tests; 657/657 pass. 7-agent release pass clean. Operator guide gains substrate-metadata-egress + Path-A-vs-B warnings.

## Shipped in v6.6.0 (2026-05-01)

Local-LLM guardian release. SemVer minor bump — public API additions
only, no breaking changes.

- Added `framework/local_llm/` — a new framework-tier component (parallel
  to `framework/vault/`) providing an `ask_local_oracle` tool that enables
  a local LLM to compose structured natural-language responses over
  deterministic processing output. Numbers from `processing.py`; prose from
  the local LLM; `OracleResponse` schema enforces the separation.
- `LocalLLMBackend` ABC with `NullBackend` (no-op default; existing
  deployments behaviorally unchanged) and `OllamaBackend` (Ollama on
  `localhost:11434`, JSON-mode HTTP). Opt-in via `local_llm` block in
  `user_config.json`.
- Four named tiers: Scout (`llama3.2:1b`) / Sentinel (`phi3.5:3.8b`) /
  Guardian (`llama3.1:8b`) / Titan (`qwen2.5:14b`). Cited numerical claims
  identical across tiers; only the prose model differs.
- Six new `oracle_*` columns on `audit_log` for IRB-grade provenance
  (model, tier, backend, backend_latency_ms, oracle_latency_ms, claim_count).
- `router.register_local_llm_layer()` hook; layer bypasses consent/cost/
  circuit-breaker/PHI-scrub gates (same pattern as `VaultLayer`).
- [ADR 0022](docs/adr/0022-local-llm-guardian.md) (Proposed); ADR 0008
  amended to extend permit-list to name new backend files.
- Operator guide: `docs/guides/local-llm-guardian.md`.
- Total tool surface: 48 (was 47).
- 37 new regression tests; full suite 632/632.

Deferred (ADR 0022 § "Out of scope"): verifier behavior on hosted-LLM
responses, sanitizer/proxy mode, conductor-mode toggle, citation-grounding
enforcement, migration of remaining 45 tools to oracle mediation, IRB
prompt-injection threat-model update, performance characterization,
pilot-wizard tier-detection, real Ollama end-to-end smoke.

## Shipped in v6.5.0 (2026-04-30)

Tier-1 cohort surface release. SemVer minor bump — public API
additions only, no breaking changes. CSV directory child surface
widens from 5 to 7 tools.

- **Two new Tier-1 tools on the CSV directory child** —
  `csv_cohort_summary` (cross-file aggregation by metadata-sidecar
  group; returns per-group n/mean/std/min/max plus subjects-per-group)
  and `csv_force_decline` (per-file fatigue diagnostic; peak, decline %,
  decline rate per minute, time-to-50%-drop). Both Tier 1 — no
  consent gate, no cost gate, no rows in LLM context.
- **`COHORT_METRICS` vocabulary** — `mean`, `max` (alias `peak`),
  `min`, `std`, `first`, `last`, `duration_s`, `time_to_50pct_drop_s`.
  Non-parametric threshold-crossing fatigue diagnostic; explicit
  curve-fitting (exponential τ, polynomial) deferred per ADR 0015
  Alternatives.
- **Metadata sidecar pattern** — optional `<csv_dir>/metadata.json`
  with schema `{filename: {field: value}}`, required by
  `csv_cohort_summary`, ignored by every other tool. Matches
  REDCap / DataCite / Frictionless Data packaging conventions.
- **46 new regression tests** — 28 pure-function tests for
  `aggregate_metric` (15), `cohort_stats` (5), `force_decline_summary`
  (8); 18 handler/branch tests covering both new tools plus every
  fail-closed path coverage-criticality-mapper flagged on the v6.5.0
  build (sidecar JSONDecodeError + malformed-entry, csv-dir-not-found
  guard, MAX_COHORT_FILES cap, missing-group-field surface, per-file
  load_errors path, unknown-metric defensive double-check, force-
  decline OSError-on-read, `_extract_timestamps` no-timestamp-col +
  parse-failure). 576/576 tests pass.
- **ADR 0015 — Tier-1 cohort surface + metadata sidecar.** Codifies
  the cohort surface and the sidecar pattern; cites ADRs 0001 / 0002 /
  0008 / 0009 / 0014. Includes a Criticality classification section
  per ADR 0014: new processing methods are MEDIUM, new child
  handlers are HIGH.
- **`examples/hip_lab_demo/` walkthrough** — proof-of-concept
  against a synthetic 16-subject (8M / 8F) intermittent isometric task
  to volitional failure. Sized to mimic the active research thread
  of Senefeld + Hunter (*J Physiol* 2024, sex differences in human
  performance). Three scripted wow moments demonstrate (1) cohort
  comparison at Tier 1 with no streams in LLM context, (2) vault
  cross-session memory surfacing a prior subject-keyed moment alongside
  fresh data, (3) audit-log export as IRB continuing-review evidence.
- **4-backstop release pass** (ADR 0010 / 0011) — red-team-reviewer,
  reproducibility-provenance-auditor, phi-irb-risk-reviewer,
  researcher-utility-reviewer; vault-smoke-validator on the demo
  seed-moment vault.
- **Framework startup fix + new serve-subprocess smoke test** —
  Demo-before-commit (Protocol 5) caught a TypeError in
  `framework/router.py:983` that all automated gates missed:
  `Server.run(read, write)` was missing the third
  `initialization_options` argument required by mcp 1.27.0. Fix is
  one line (`server.create_initialization_options()`). New
  `tests/test_serve_startup_smoke.py` runs `biosensor-mcp serve` as
  a subprocess with closed stdin and asserts no traceback — closes
  the gate-evasion class for upstream-mcp-SDK signature drift. The
  CLI `--help` smoke test does not exercise stdio_server, so this
  bug shipped past every specialist's PASS verdict and only
  surfaced when a real MCP client tried to connect. 577/577 tests
  pass (was 576).

## Shipped in v6.4.1 (2026-04-30)

Coverage-hardening patch closing four CRITICAL untested regions. No
public API changes. 526/526 tests pass; package coverage 84% (was 82%).

- **16 new regression tests** — `TestDispatchInternalProvenance` expanded
  with 11 tests covering all error branches on the internal dispatch path
  (PARAM_INVALID_INTERNAL, CIRCUIT_OPEN_INTERNAL, CONSENT_BLOCKED_INTERNAL,
  COST_ESTIMATE_ERROR_INTERNAL, COST_GATE_INTERNAL, ERROR_INTERNAL,
  vault-tool-rejection, PHI-scrub seam, subject_id propagation); 1 test
  for cost-estimator fail-closed on the public path; 1 test for
  unknown-domain revocation guard; 1 orjson stdlib fallback test via
  `sys.modules` patching; 2 vault writer atomic-write cleanup tests
  covering both failure paths; 1 schema test for `vault_search_notes`
  `kind` parameter.
- **ADR 0014** — Coverage criticality is an invariant: newly-uncovered
  CRITICAL or HIGH code is a COVERAGE REGRESSION regardless of overall
  percentage. CRITICAL taxonomy maps to ADRs 0001 / 0003 / 0005 / 0009 /
  0012 / 0013; enforcement is agent-driven at PR time.
- **`vault_search_notes` ToolDefinition** — surfaces canonical `kind`
  parameter alongside legacy `note_type` alias; closes v6.3.0
  drift-auditor finding.
- **4-backstop release pass** — red-team OBJECTION on two findings
  remediated; researcher-utility-reviewer ALIGNED with caveat;
  boss-report-auditor REVISE remediated; reproducibility-provenance-auditor
  CLEAN.

## Shipped in v6.4.0 (2026-04-30)

Cache-only purge on consent revocation. SemVer minor bump (breaking:
`ChildMCP.purge_cache` is now a mandatory abstract method). No router
pipeline, security-pipeline, or vault-layer architecture changes beyond
the revocation-handler rewrite.

- **New abstract method `ChildMCP.purge_cache(*, force: bool = False) -> dict`** —
  mandatory on all children; explicit rejection of the ADR 0003 default-no-op
  trap. Returns `{rows_purged, tables_touched, preserved, errors}`.
- **Router revocation handler rewrite** — `_handle_consent_revocation`
  runs purge-before-revoke synchronously; purge failure aborts revocation
  with consent intact and a `PURGE_FAILED` audit row unless `force_revoke=True`.
- **Paired `PURGE_CACHE` audit row** — every successful revocation writes a
  `PURGE_CACHE` row carrying `scrubber_id`, `force_revoke`, and the child's
  full `purge_result` dict; closes the red-team / phi-irb audit-row provenance
  gap caught on the release-time backstop pass.
- **RunningChild** — deletes `streams` + `activities` tables; preserves
  `stop_labels` (analyst-authored interpretation, not biometric data).
- **CSVDirectoryChild and TemplateChild** — return citable no-op dicts.
- **6 new regression tests** — `TestPurgeCacheOnConsentRevocation` (5) and
  `TestRunningChildPurgeBiometricCache` (1); full suite 510/510.
- **ADR 0013** — Cache-only purge on consent revocation; cites ADRs 0001 /
  0003 / 0009 / 0012; names single-account-per-domain limitation.
- **`docs/design/research-framing.md`** — new "Consent withdrawal under this
  profile" section codifying the IRB-profile language ADR 0013 cites.
- **4-backstop release pass** (ADR 0010 / ADR 0011) — red-team, researcher-
  utility, phi-irb-risk-reviewer, reproducibility-provenance-auditor; 3 found
  gaps, 2 fixed before ship, 1 documented as known limitation.
- **Closes Lens 6 retention WATCH** from v6.3.0 hygiene-pass hall-of-fame
  team expansion.

## Shipped in v6.3.1 (2026-04-30)

Hygiene-pass patch release. Three IRB-blocking VIOLATIONS patched with
regression tests; documentation drift corrected; ADR 0012 added; ADR
0008 permit-list amended. No router, security-pipeline, child, or
vault-layer architecture changes.

- **VIOLATION: consent-row `scrubber_id` absent** — `framework/router.py`
  consent-handler audit rows (approve and revoke paths) now carry
  `scrubber_id` per ADR 0003. Regression test in `tests/framework/test_router.py`.
- **VIOLATION: Tier-1 GPS re-identification path** — `strava_stop_analysis`
  coarsens GPS to 3 decimal places (~111 m), drops the `near_home`
  boolean, and buckets `distance_from_home_m` to 100 m — closes the
  HIPAA Safe Harbor §164.514(b)(2)(i)(B) triangulation path. Regression
  test in `tests/children/running/test_processing.py`.
- **VIOLATION: `PHIScrubber` warning swallowed by Claude Desktop** —
  `framework/security.py` new `scrubber_warning` property; three
  `_meta` stamping sites in `framework/router.py` inject the warning
  into the LLM transcript so misconfigured deployments are visible
  regardless of deployment shape.
- **8 new regression tests** (total 504 = 496 + 8).
- **ADR 0012** — Vault dispatch bypasses the PHI-scrubber seam: records
  the previously inline-only "Skipped by design" decision with named
  invariants and reversal conditions; cites ADRs 0003 / 0007 / 0009.
- **ADR 0008 amended** — clock-read permit-list widened to name
  `vault/renderer.py`, `vault/layer.py`, `vault/storage.py` per
  v6.3.0 BORDER NOTES drift two compliance auditors independently
  flagged.
- **Documentation drift fixed** — README.md (four actively-false
  claims, broken anchor, `_meta` example version, "What's next" table);
  CLAUDE.md (file-structure block, tool count, agent count, roster
  table); `vault/layer.py:137-140` (`vault_list_notes` kind-filter now
  lists all 7 allowed values).

## Shipped in v6.3.0 (2026-04-30)

Hall-of-fame team-expansion release. Governance / team-shape only — no
router, security-pipeline, child, vault-layer, or CLI architecture
changes. The release ships four new specialist agents, one integration-
auditor reshape, two new ADRs, and several process hard-rails.

- **4 new specialist agents** land per ADR 0011's promotion policy
  (`researcher-utility-reviewer`, `coverage-criticality-mapper`,
  `reproducibility-provenance-auditor`, `phi-irb-risk-reviewer`).
- **`integration-auditor` reshape** — gains optional
  `--invariant=schema-drift` mode for new-ChildMCP / `param_schema`
  PR-time validation against ADR 0002. Per ADR 0011, this folds into
  an existing agent rather than spawning a fifth new specialist.
- **Adversarial pairing restored and codified** — `boss-report-auditor`
  and `red-team-reviewer` rows + Tier-2 adversarial backstops
  sub-section added to CLAUDE.md. ADR 0010 makes this a permanent
  structural requirement, not an easily-overwritten banner detail.
- **BORDER NOTES side-channel** added across all 10 specialist prompts.
- **ADR 0010** (adversarial-pairing pattern — second-translator +
  adversarial-verdict structure).
- **ADR 0011** (promotion-policy override — project-local structural-
  argument + severity + cost-vs-frequency bar; frequency-based "3+ uses"
  is the fallback; four picks split 2/2 across old vs new bar).
- **`release-shipper` hard-fail on dirty working tree** — new pre-flight
  rail with `--include-pending=<file>:<reason>` opt-in restricted to a
  governance-shape allowlist; reasons must cite ADR/PR/issue or contain
  ≥5 words; trail dual-recorded in release commit body + banner summary.

## Shipped in v6.2.1 (2026-04-29)

The pilot-wizard release. Closes the install-and-configure friction for
non-technical PIs by collapsing the seven-step multi-subject pilot
quickstart into two terminal commands and three prompts. No router,
security-pipeline, child, or vault-layer architecture changes.

- **`biosensor-mcp pilot` CLI subcommand** (`src/biosensor_mcp/pilot.py`) —
  three-prompt wizard: auto-detects CSV schema across all files in the
  directory, writes `user_config.json` atomically, optionally registers
  with Claude Desktop on Win/macOS (skipped on Linux), runs an end-to-end
  smoke check against every CSV file.
- **F1 — full-directory smoke check** — wizard scans every CSV in the
  directory, not just the alphabetically first one. Closes the
  "P001 looks fine, P004 breaks at runtime" failure mode named by the
  audit.
- **F2 — atomic Claude Desktop config write** — `os.replace` + BOM
  round-trip + deep-merge into existing `mcpServers`. Preserves sibling
  MCP servers; asks user to quit Claude Desktop first to avoid clobbering
  an open config.
- **C3 — cloud-sync warning on `csv_dir.path`** — mirrors the existing
  `vault_path` warning for OneDrive, iCloud, Dropbox, Box, Google Drive,
  pCloud, Nextcloud, and MEGA.
- **Synthetic CSV fixtures moved into package** — P001/P002/P003 moved
  from `examples/multi_subject_pilot/csv/` to
  `src/biosensor_mcp/_fixtures/multi_subject_pilot/csv/`. pyproject.toml
  `package-data` globs `_fixtures/**/*.csv`. Wheel install and source-tree
  work identically.
- **`docs/guides/multi-subject-pilot.md` rewritten** — `biosensor-mcp pilot`
  is now the primary path; manual setup demoted to advanced fallback.
  Install command updated to `uv tool install git+...`.
- **9 new tests** in `tests/test_pilot_wizard.py`; full suite 496/496 green.
- **Deferred: `setup` → `setup-strava` rename** — disambiguation currently
  handled in `--help` text; re-evaluate when external doc references
  stabilise (see ROADMAP entry below).

## Shipped in v6.2.0 (2026-04-29)

The pilot-ready release. Closes the multi-subject vault failure mode
the proposal-mode auditor named for the v6.2 framing (a friendly
academic lab, one PI + one analyst, 5–20 participants, light IRB).
Also closes two latent governance-claim doc-lies the drift audit
surfaced. No router or security-pipeline architecture changes;
existing v6.1 vaults upgrade in place via lazy rescan.

- **[ADR 0009 — Vault subject-keying](docs/adr/0009-vault-subject-keying.md)** —
  resolves the design question ADR 0002 deliberately deferred. Themes
  carry an optional, set-once `subject_id` in frontmatter; evidence
  and moments stamp the subject of their writing call; search and
  list queries filter by subject when one is provided, with cross-
  subject themes and v6.1-era legacy notes preserved via the IS-NULL
  branch.
- **`subject_id` on all 25 vault tools** — surfaced in `param_schemas`
  and rendered in tool listings so LLM clients discover the
  parameter via `list_tools`. Storage-layer migrations
  (`vault_notes.subject_id`, `vault_themes.subject_id`) follow the
  same `ALTER TABLE` pattern `audit_log` used.
- **[ADR 0008 — Analytical processing is deterministic by construction](docs/adr/0008-deterministic-by-construction-processing.md)** —
  records the invariant the codebase already shipped: every method on
  `RunningProcessing`, `CSVProcessing`, and `TemplateProcessing` is a
  `@staticmethod` pure function with no PRNG and no clock reads. Names
  the residual scope on the deterministic-mode roadmap entry (the
  audited-flag-plus-provenance-hash pairing).
- **`scrubber_id` in audit-log column + `_meta` block** — closes the
  ADR 0003 doc-lie. The property existed on `PHIScrubber` since v5;
  v6.2 wires the value into a new `audit_log.scrubber_id` column and
  stamps it on every `_meta` block so a misconfigured `noop`
  deployment is visibly distinguishable from one running an
  institutional subclass.
- **`SUBJECT_ID_SCHEMA` promotion to `framework.interfaces`** —
  removes the triplicated `ValidationSchema` declarations across the
  three child modules. Children re-export via existing imports;
  vault layer references the framework-level constant directly.
- **[Multi-subject pilot quickstart](docs/guides/multi-subject-pilot.md)** —
  PI-facing walkthrough from `git clone` to a working multi-subject
  vault in roughly fifteen minutes. Bundled
  `examples/multi_subject_pilot/` with three synthetic-participant
  CSV fixtures, a deterministic regenerator script, a portable
  `user_config.example.json`, and a directory README pointing back
  at the guide.
- **Locked v6.2 deployment-shape framing in
  [`docs/design/research-framing.md`](docs/design/research-framing.md)** —
  names the target shape (Camp A-light) and explicitly defers the
  fuller institutional and personal-craft framings to v6.3+.

## Shipped in v6.1.1 (2026-04-29)

Docs and governance release. No Python code touched; no router, security,
child, vault, or CLI changes.

- **Boss-architect protocols in CLAUDE.md** — five Tier-1 rules governing
  the main session at the boss-facing boundary: intent → options before
  dispatch, pre-implementation audit on non-trivial work, plain-language
  decision-framing on every boss-facing report, anti-sycophancy and
  mandatory conflict pushback, demo-before-commit. Plus a "failure modes to
  watch" callout naming main-session sycophancy as the structural risk the
  boss cannot self-detect.
- **[docs/design/operating-model.md](docs/design/operating-model.md)** —
  two-tier architecture memo covering the boss ↔ main-session ↔
  specialist-agent hierarchy, heritage citations (PARC / Bell Labs / Apollo
  / Mac team / Brooks), and the agent roster in plain terms.
- **Agent hard rule — Refuse on conflict with codebase ground truth** — all
  8 agent prompts gain a Tier-2 anti-sycophancy backstop tailored per agent
  (e.g. adr-drafter refuses to draft an ADR contradicting an accepted ADR;
  integration-auditor refuses to classify a clearly-suspicious deletion as
  Justified without evidence).
- **integration-auditor `--proposal-mode`** — new Mode B for
  pre-implementation defensive imagining on a proposal description rather
  than a diff. Own pre-flight, evaluation procedure, and report format.

## Shipped in v6.1.0 (2026-04-29)

The vault layer gained dual-output rendering policy plus three new
tools that round out the analytical-memory model. No router, security,
or child changes.

- **[ADR 0007 — Rendering-layers policy](docs/adr/0007-rendering-layers-policy.md)** —
  source-of-truth markdown stays plain and AI-readable; plugin-enhanced
  views (Dataview, Templater) are additive only. Framework-emitted
  notes that include plugin syntax must ship a snapshot fallback so
  the same content renders for any reader.
- **`vault_refresh_dashboards`** — materialises `dashboards/open-themes.md`,
  `active-failure-modes.md`, and `recent-moments.md` from the live
  SQLite index. Each dashboard ships an always-rendered snapshot table
  plus an optional Dataview live-query block above it. Reference
  implementation of ADR 0007 dual-output.
- **Failure-mode lifecycle** — `vault_log_failure_mode` and
  `vault_list_failure_modes` add the "how we got it wrong" counterpart
  to themes. Symptom / diagnosis / mitigation are body-only and set on
  creation; metadata (status, related_themes, related_subjects, tags)
  updates in place to preserve the append-only evidence log.
- **Correction propagation** — `vault_correct_evidence` gained a
  `propagate=true` mode that appends a `[!warning]` callout to every
  note that wikilinks to the corrected theme. Idempotent on the
  `(theme_slug, evidence_timestamp)` pair, so re-running the same
  correction never duplicates markers.
- **[docs/design/managed-agents-compat.md](docs/design/managed-agents-compat.md)** —
  positions Biosensor MCP relative to Anthropic Managed Agents over
  network MCP. Path A (local-first orchestration, default) vs Path B
  (Managed Agent calling the local router); both preserve the same
  governance pipeline.

## Shipped in v6.0 (2026-04-23)

The vault overhaul ported seven governance features from personal
knowledge-management practice into the VaultLayer; these items are no
longer on the roadmap and are documented in
[ADR 0006](docs/adr/0006-vault-overhaul-v6.md) and the v6.0 CHANGELOG
entry:

- **Vault snapshot** — compressed `snapshot.md` state note
  (`vault_generate_snapshot` + `vault_get_snapshot`).
- **Vault inbox** — low-friction capture pipeline
  (`vault_inbox_add` / `_list` / `_drain`).
- **Vault health check** — diagnostic sweep over stale themes,
  orphaned moments, and unprocessed inbox items.
- **Evidence provenance** — source tier / tool / domain / verification
  stamped on evidence blocks.
- **Theme lifecycle enrichment** — reframing with prior-framings
  preservation, thinking entries distinct from evidence, and
  fold-back of resolutions onto linked notes.
- **Analytical corrections** — `vault_correct_evidence` marks
  superseded blocks without rewriting them.
- **Session divergence** — optional `divergence` field on
  `vault_capture_session` recording goal-vs-actual.

---

## Real PHI-scrubbing implementations behind the `PHIScrubber` slot

`PHIScrubber.scrub()` ships today as a documented no-op seam. The
roadmap items are institutional-policy-specific implementations:
transforms that drop or hash identifying fields before results leave
the router, bound to the specific shape of a CGM child, a sleep child,
a FHIR-bundle child, etc. Getting this right requires an actual study
to anchor the policy against; it is deliberately not a framework-level
decision.

As of v6.2 (2026-04-29), the `scrubber_id` is recorded in a dedicated
column on every `audit_log` row and stamped on every `_meta` block
returned to the LLM. A deployment running the no-op default is
distinguishable from one running an institutional subclass at query
time *and* in any individual response. Earlier doc claims of this
behaviour predated the wire-up; v6.2 closed the gap (see
[ADR 0003](docs/adr/0003-phi-scrubber-seam.md) for the seam decision
and the v6.2 shipped section for the drift-audit context). v6.3.1
additionally surfaces the no-op warning into every successful result's
`_meta` block so a misconfigured deployment is visible inside the LLM
transcript itself, not only in stderr (which is swallowed by Claude
Desktop's spawned-subprocess process model).

## New ChildMCPs for research-relevant data sources

Each of these is a candidate worked-example child for a research
group that doesn't want to start from scratch:

- **CGM child** against OhioT1DM or the Jaeb Diabetes Research
  Center's public datasets — time-in-range, glycemic variability,
  meal-response curves, nocturnal hypoglycemia flagging.
- **Sleep child** against PhysioNet's Sleep-EDF — stage durations,
  efficiency, latency, fragmentation indices, REM/NREM structure.
- **ECG child** against MIT-BIH — rhythm classification, HRV windows,
  QT intervals, beat-level anomaly flagging.
- ~~**Generic CSV directory child**~~ **Shipped** — see
  `src/biosensor_mcp/children/csv_dir/`. Given a directory of
  per-subject CSVs with a declared timestamp column and value schema,
  exposes 7 tiered analytical tools (v6.5.0 added `csv_cohort_summary` +
  `csv_force_decline` per ADR 0015). Opt-in via `csv_dir` key in
  `user_config.json`.
- **EDF file child** — direct ingestion of European Data Format
  recordings common in sleep and EEG research.
- **FHIR bundle child** — ingestion of FHIR bundles for lab values,
  medication histories, or vitals. Bridges clinical data into the
  same governance pipeline.

**Shipped**: a minimal `children/template/` skeleton — three Tier-1
tools, one Tier-2, one Tier-3, with every abstract method stubbed
out, param schemas illustrated, and `subject_id` wired throughout.
New children fork from `src/biosensor_mcp/children/template/` rather
than reading the running child end-to-end. Shape-contract tests at
`tests/children/template/test_template_shape.py` are copyable as a
starting point for the new child's own tests.

## Per-subject parameter scoping on vault tools

**Shipped in v6.2 (2026-04-29).** [ADR 0009](docs/adr/0009-vault-subject-keying.md)
documents the design; all 25 vault tools now declare `subject_id` in
their schemas; `vault_notes` and `vault_themes` carry nullable
`subject_id` columns; `vault_upsert_theme` enforces a set-once
invariant; evidence and moment renderers stamp the subject of the
writing call; list and search tools filter by `subject_id` with the
IS-NULL branch preserving cross-subject and v6.1-legacy visibility.
Existing v6.1 vaults upgrade in place via lazy rescan — no markdown
rewrites required.

**Not shipped (v6.3+):** subject-aware search ranking, cross-subject
theme aggregation tools, multi-analyst attribution interaction with
subjects, and vault-freeze export-by-subject. See the ADR for the
full out-of-scope list.

## Per-analyst attribution on vault evidence blocks

Evidence blocks on theme notes are currently timestamped but
unattributed. In multi-analyst studies, "who recorded this
observation" is load-bearing context. A vault-writer parameter for
analyst identity, threaded through to the evidence block's
frontmatter and rendered in the Obsidian view, is the clean version.

## Deterministic mode with seed control

**Partially shipped — see [ADR 0008](docs/adr/0008-deterministic-by-construction-processing.md).**
The 2026-04-29 drift audit confirmed that no analytical function in
`framework/` or any `children/*/processing.py` touches pseudo-
randomness, reads a clock, or holds module state — every method is a
`@staticmethod` pure function. The same Tier-1 call with the same
inputs returns the same numbers across machines, runs, and Python
versions where stdlib semantics match, *without* any runtime flag.

What remains under this heading is a small, deferred residual: a
router-level `deterministic_mode` flag stamped into the `_meta`
block, paired with content-hashed provenance (the next item) so a
reviewer can confirm a result was actually produced under the
invariant. The flag is cosmetic without the hash; ADR 0008 commits
to deferring it as joint work with the provenance-hashing item.

## Real provenance hashing on derived metrics

The `_meta` block stamps package version, tool name, and call
timestamp today. The full version is a hash chain from raw-data input
through intermediate processing stages to each derived metric — so a
paper reviewer can trace every published number to the exact code
version and exact input bytes that produced it. The `_meta` stamps
are intended to make this retrofit localized.

## "Freeze vault" operation for manuscript submission

A tool or CLI command that snapshots the vault state (markdown files,
index rows, associated audit rows, the exact code version running at
snapshot time) into a single archive suitable for attaching to a
manuscript submission. Complements the audit log as the canonical
"state of the analysis at submission" artifact.

## Worked-example notebook against a published analytical question

**Shipped** (first pass) — [docs/guides/worked-example.ipynb](docs/guides/worked-example.ipynb).
A 10-minute end-to-end walkthrough on the bundled synthetic run data:
router wiring, a Tier-1 call, the audit row, the Tier-2 consent gate
firing and being approved, a vault theme round-tripping to
Obsidian-compatible markdown. No Strava account, OAuth, or network.

What's still deferred: a second notebook against a *public dataset*
answering a *published analytical question*. That version demonstrates
the framework on a reference result an outside reviewer can check,
rather than on synthetic data. Best paired with the CGM or Sleep
child once one of those lands — OhioT1DM or PhysioNet Sleep-EDF are
natural candidates.

## Evaluation harness for LLM-client behavior

Different LLM clients (Claude Desktop, Claude API directly, third-
party MCP clients) will vary in how they handle the consent and cost
gate prompts. An evaluation harness that replays scripted analytical
conversations through different clients and measures gate compliance,
scope drift (did the LLM expand the scope of a consent it was
granted?), and vault-recall accuracy (did the LLM actually consult
existing themes before writing a new one?) would make the "client-
agnostic governance" claim measurable.

## CLI UX: rename `setup` → `setup-strava`

After v6.2.1, the framework ships two wizard subcommands under
generic English verbs: `biosensor-mcp setup` (Strava OAuth, the
worked-example child) and `biosensor-mcp pilot` (the multi-subject
CSV setup, the v6.2 flagship use case). Disambiguation today lives
in `--help` text only; the cleaner long-term answer is to rename
`setup` → `setup-strava` so each verb names what it actually
configures. Deferred from v6.2.1 because the doc-churn cost (every
README, every quickstart, every notebook reference) exceeds the
present UX gain — the disambiguation note in `--help` is doing the
heavy lifting fine for now. Re-evaluate when external doc
references stabilise or when a third wizard joins the lineup.

## CLI UX: rename legacy `demo` → `verify`

`biosensor-mcp demo` today runs `run_demo` from
[`src/biosensor_mcp/demo/runner.py`](src/biosensor_mcp/demo/runner.py)
against the bundled synthetic running-data sample — it prints
analytics output to the terminal and is structurally an
*operator self-verification path* ("does my install work?"), not a
live-audience walkthrough. v6.9.0 added
[`biosensor-mcp tour`](docs/adr/0024-wheel-distributed-tour-and-fixture-bundling.md)
as the live-audience walkthrough surface. The legacy `demo` should
rename to `verify` (or `selftest`) so the verb names what it
actually does and `tour` vs `demo` doesn't read as redundant or
swappable. Deferred from v6.9.0 because the doc-churn cost (every
README, CLAUDE.md banner cross-reference, the `coverage.run.omit`
glob in `pyproject.toml`, possible external docs) exceeds the
present UX gain — the live-audience surface is already correctly
named on the `tour` side, and the ADR 0024 cite path makes the
distinction clear to anyone reading the codebase. Re-evaluate when
external doc references stabilise or when a third operator-side
verification utility ships.

## Pre-existing csv_dir HIGH-region coverage debt (v6.5.1)

The v6.5.0 release pass identified 34 lines of pre-existing HIGH-region
test debt in [`csv_dir/child.py`](src/biosensor_mcp/children/csv_dir/child.py)
across init, config-load, consent-property, and pre-v6.5 handler error
paths (lines 105, 137, 140-142, 151, 154, 164-165, 167, 198, 209, 228,
428, 464, 492, 501, 519-520, 542, 558-559, 583, 615, 640, 644-645, 659).
Not a regression per [ADR 0014](docs/adr/0014-coverage-criticality-invariant.md)
— these were uncovered before v6.5.0 — but visible to the
[`coverage-criticality-mapper`](.claude/agents/coverage-criticality-mapper.md)
agent on every diff and on the radar as deferred work. Closing them is
mechanical: regression tests for the OSError, config-malformed, and
handler-error branches in the pre-v6.5 surface. Ships as v6.5.1 patch
with no public API change. ~few hours of work.

## PHI sidecar-schema validator (deferred)

[ADR 0015](docs/adr/0015-tier-1-cohort-surface-and-metadata-sidecar.md)
documents that the `metadata.json` sidecar sits *out-of-band* of the
[ADR 0003](docs/adr/0003-phi-scrubber-seam.md) PHI-scrubber seam — the
sidecar is read by the cohort handler and used for grouping but its
contents never enter a tool result, so `PHIScrubber.scrub()` does not
see it. A deployer can therefore pack HIPAA Safe Harbor §164.514(b)(2)
identifiers (full DOB, full ZIP at 5-digit precision, MRN, full name,
etc.) into the sidecar and the framework will not police it. The
v6.5.0 remediation was documentation-only — caveats in the demo README
and ADR 0015 § sidecar mechanism — and the structural gap remains as
a documented known limitation analogous to
[ADR 0013](docs/adr/0013-cache-only-purge-on-consent-revocation.md)'s
single-account-per-domain caveat. The v6.6 fix is a code-level
validator: a `csv_dir.metadata_schema` config knob declaring
allowed / denied field names, enforced at child init, fail-closed
(the framework refuses to start with a sidecar that contains a
denied-name field). Pattern matches ADR 0003's seam shape —
institutional configuration, not a built-in policy. ~1–2 days work
plus a new ADR codifying the fail-closed contract. Ships as v6.6
minor scope.

---

## Contributing

These items are all roadmap-level, not ticketed. If one of them is
the reason you showed up, open a discussion or issue on GitHub first
— some have real design questions (especially the `subject_id` →
vault keying question and the per-analyst attribution one) that are
worth talking through before code.
