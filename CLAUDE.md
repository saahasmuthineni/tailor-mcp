# CLAUDE.md — Biosensor MCP

> **v6.5.0 (2026-04-30)** — Tier-1 cohort surface release. Adds two
> Tier-1 tools to the CSV directory child — `csv_cohort_summary`
> (cross-file aggregation by metadata-sidecar group) and
> `csv_force_decline` (per-file fatigue diagnostic) — closing the
> structural gap proposal-mode auditor flagged on v6.5 pre-build:
> per-file `csv_summary_report` cannot satisfy cohort questions
> without either fabricating numbers or escalating to Tier 2,
> contradicting the *"no streams enter LLM context"* claim Tier 1 is
> meant to demonstrate. New
> [ADR 0015](docs/adr/0015-tier-1-cohort-surface-and-metadata-sidecar.md)
> codifies the cohort surface and the metadata-sidecar pattern (group
> identity travels via `<csv_dir>/metadata.json`, schema
> `{filename: {field: value}}` — matches REDCap / DataCite /
> Frictionless packaging conventions; ADR cites 0001 / 0002 / 0008 /
> 0009 / 0014). The `COHORT_METRICS` vocabulary covers `mean`,
> `max` (alias `peak`), `min`, `std`, `first`, `last`, `duration_s`,
> `time_to_50pct_drop_s` — non-parametric threshold-crossing fatigue
> diagnostic; explicit curve-fitting (exponential τ, polynomial)
> deferred behind a superseding ADR per ADR 0015 § Alternatives.
> Pure-function processing per ADR 0008 unchanged: `aggregate_metric`
> reduces one file to a scalar, `cohort_stats` reduces a cohort to
> summary stats, both `@staticmethod` with no PRNG and no clock
> reads. Handler-level fail-closed: missing sidecar → explicit
> error; malformed → typed error; per-file metadata gaps surface as
> `missing_metadata` / `missing_group_field` keys on the result so
> the LLM can flag silent under-counts. `MAX_COHORT_FILES` cap (64)
> matches ADR 0009's pilot-study scale. 46 new regression tests
> (28 pure-function + 18 handler/branch — including the three
> sidecar fail-closed paths the proposal-mode audit named, the
> MAX_COHORT_FILES cap, the unknown-metric defensive double-check,
> and the `_extract_timestamps` no-timestamp-col / parse-failure
> branches that closed the v6.5.0 coverage-criticality regression
> on `csv_dir/child.py` HIGH-region paths). New
> `examples/hip_lab_demo/` walkthrough is
> the proof-of-concept: 16 synthetic subjects (8M/8F) on an
> intermittent isometric task to volitional failure, sized to mimic
> the active research thread of Hunter & Senefeld (*J Physiol* 2024,
> 602.17, 4129-4156, "Sex differences in human performance").
> Walkthrough lampshades
> data-shape concessions openly (1 Hz EMG envelope is
> post-rectification — real surface EMG is 1–2 kHz raw; "real
> version would ingest from the rectification/envelope stage").
> Demo runs via `BIOSENSOR_CONFIG_DIR=examples/hip_lab_demo/beta
> biosensor-mcp serve` — isolated from the operator's
> `~/.biosensor-mcp/user_config.json`, no pilot-wizard clobber risk.
> Public API additions only — no breaking changes; SemVer minor
> bump. CSV directory child surface widens from 5 to 7 tools. Total
> framework tool surface 25 (vault) + 12 (running) + 7 (csv_dir) +
> 3 (template) = 47 (was 45). 4-backstop release pass per
> ADR 0010 / 0011 (red-team-reviewer,
> reproducibility-provenance-auditor, phi-irb-risk-reviewer,
> researcher-utility-reviewer); vault-smoke-validator on the demo
> seed-moment vault. Demo-before-commit gate per Protocol 5 caught a
> real ship-blocker no specialist gate did: `framework/router.py:983`
> was calling `Server.run(read, write)` against the mcp 1.27.0 SDK
> whose signature now requires a third `initialization_options`
> argument. The TypeError surfaced only when a real MCP client tried
> to connect — every automated gate (pytest, ruff, security probe,
> CLI `--help` smoke) was green because none of them actually start
> the stdio server. Fix: pass `server.create_initialization_options()`
> as the third arg. New `tests/test_serve_startup_smoke.py` regression-
> tests this by spawning `biosensor-mcp serve` as a subprocess with
> `stdin=DEVNULL` and asserting no Python traceback in stderr; closes
> the gate-evasion class for upstream-mcp-SDK signature drift. Total
> regression tests on this release: 47 (46 cohort + 1 serve smoke).
>
> **v6.4.1 (2026-04-30)** — coverage-hardening release closing four
> CRITICAL untested regions identified by the v6.3.0 hygiene pass and
> the v6.4.0 release-time backstops. Adds 16 new regression tests:
> 11 in `TestDispatchInternalProvenance` covering the cross-child
> internal dispatch path's happy path + 7 error branches
> (PARAM_INVALID_INTERNAL, CIRCUIT_OPEN_INTERNAL,
> CONSENT_BLOCKED_INTERNAL, COST_ESTIMATE_ERROR_INTERNAL,
> COST_GATE_INTERNAL, ERROR_INTERNAL, vault-tool-rejection) plus
> PHI-scrub seam parity and ADR 0009 subject_id propagation; 1 test
> for cost-estimator fail-closed on the public path
> (`framework/router.py:411-422`); 1 test for unknown-domain
> revocation guard (`framework/router.py:857`); 1 test for
> orjson stdlib fallback (`framework/audit.py:50-59`) via
> `sys.modules` patching + `importlib.reload`; 2 tests for vault
> writer atomic-write cleanup covering both documented failure modes
> (fdopen-itself-raises and write-after-fd-transfer per
> `framework/vault/writer.py:1041-1058`); 1 schema test for the new
> `vault_search_notes` `kind` parameter. New
> [ADR 0014](docs/adr/0014-coverage-criticality-invariant.md)
> codifies the coverage-criticality invariant the
> `coverage-criticality-mapper` agent has enforced by convention
> since v6.3.0: newly-uncovered code in CRITICAL or HIGH regions is a
> COVERAGE REGRESSION regardless of overall percentage. CRITICAL
> taxonomy maps to ADRs 0001 / 0003 / 0005 / 0009 / 0012 / 0013;
> enforcement is agent-driven at PR time (same shape as ADR 0008's
> permit-list invariant). One researcher-visible feature:
> `vault_search_notes` ToolDefinition now surfaces the canonical
> `kind` parameter alongside the legacy `note_type` alias, matching
> `vault_list_notes` / `vault_read_note` (closes the v6.3.0 drift-
> auditor finding). 4-backstop release pass per ADR 0010 / ADR 0011:
> ci-gate-runner caught 7 ruff violations on the first run (E702 x6,
> F841 x1) — fixed; red-team-reviewer OBJECTION (medium) on two
> findings — both remediated with additional regression tests
> (`test_atomic_write_cleans_up_when_fdopen_itself_raises`,
> `test_dispatch_internal_threads_subject_id_into_audit_row`);
> researcher-utility-reviewer ALIGNED with caveat (engineering
> hygiene was being marketed as researcher utility on the analyst
> persona — caveat applied to banner / synthesis); reproducibility-
> provenance-auditor CLEAN. Boss-report-auditor returned REVISE on
> first synthesis pass (PI persona framing leaked the same
> engineering-hygiene-as-researcher-utility pattern); trimmed to
> factual test-posture-parity claim. Final synthesis SHIPPABLE.
> Package coverage 84% (was 82%); framework-level coverage at the
> tested paths rose into the 88% range. 526 tests pass. No public
> API changes — patch bump. SemVer-friendly.
>
> **v6.4.0 (2026-04-30)** — cache-only purge on consent revocation.
> Closes the v6.3.0 hygiene-pass Lens 6 retention WATCH (cached
> participant biometric data surviving `revoke_consent_*`) with a
> framework-tier mechanism backed by [ADR 0013](docs/adr/0013-cache-only-purge-on-consent-revocation.md).
> New abstract method `ChildMCP.purge_cache(*, force: bool = False) -> dict`
> on every child (mandatory, no default no-op — explicit rejection of
> the ADR 0003 default-no-op trap). The router's
> `_handle_consent_revocation` runs purge-before-revoke synchronously
> (`framework/router.py:841-940`); purge failure aborts revocation
> with consent intact and a `PURGE_FAILED` audit row, unless
> `force_revoke=True` swallows the error. Every successful revocation
> writes a paired `PURGE_CACHE` row carrying `scrubber_id`,
> `force_revoke`, and the child's full `purge_result` dict
> (rows_purged, tables_touched, preserved, errors) — closes the
> red-team / phi-irb-risk-reviewer audit-row provenance gap caught
> on the v6.4.0 release-time backstop pass. RunningChild deletes
> `streams` + `activities`, preserves `stop_labels` (analyst-authored
> interpretation, not biometric data); CSVDirectoryChild and
> TemplateChild return citable no-op dicts. SemVer minor bump
> because adding an abstract method is breaking for any external
> ChildMCP subclass. 4-backstop release pass per ADR 0010 / ADR 0011
> (red-team, researcher-utility, phi-irb-risk-reviewer,
> reproducibility-provenance-auditor): 3 backstops found gaps,
> 2 fixed in code/ADR before ship, 1 documented as known limitation
> (single-account-per-domain assumption embedded in the abstract
> method's signature; future multi-participant child sharing one
> account will need subject-scoped purge — fix path named in
> ADR 0013 § Negative consequences). 6 new regression tests across
> `TestPurgeCacheOnConsentRevocation` (5) and
> `TestRunningChildPurgeBiometricCache` (1); full suite 510/510.
> `docs/design/research-framing.md` gains a new "Consent withdrawal
> under this profile" section codifying the IRB-profile language
> ADR 0013's reversal condition cites. `docs/adr/0013-...md` cites
> ADRs 0001 / 0003 / 0009 / 0012. No router pipeline /
> security-pipeline / vault-layer architecture changes beyond the
> revocation-handler rewrite. Deferred: v6.4.1 coverage-hardening
> release scope (refined plan pending boss approval),
> `vault_search_notes` kind-filter inconsistency.
>
> **v6.3.1 (2026-04-30)** — hygiene-pass patch release. Three IRB-
> blocking VIOLATIONS surfaced by the v6.3.0 hall-of-fame team
> hygiene pass are patched, each bound by a regression test so the
> defects cannot silently come back: consent-handler audit rows
> (`framework/router.py:802, :835`) now carry `scrubber_id` per
> ADR 0003; Tier-1 `strava_stop_analysis`
> (`children/running/processing.py:544-558`) coarsens GPS to 3
> decimals (~111 m), drops the `near_home` boolean, and buckets
> `distance_from_home_m` to 100 m so triangulation across stops
> cannot localise the residence — closes a HIPAA Safe Harbor
> §164.514(b)(2)(i)(B) re-identification path; default
> `PHIScrubber` now surfaces a `scrubber_warning` field into every
> successful `_meta` block (`framework/security.py`,
> `framework/router.py` x3 sites) so a misconfigured deployment is
> visible inside the LLM transcript itself, satisfying ADR 0003's
> "loudly" requirement in any deployment shape (Claude Desktop
> swallows stderr). 8 new regression tests (504 = 496 + 8). New
> [ADR 0012 — Vault dispatch bypasses the PHI-scrubber seam](docs/adr/0012-vault-phi-scrubber-bypass.md)
> records the previously inline-only "Skipped by design" decision
> with named invariants and reversal conditions; cites ADRs 0003 /
> 0007 / 0009. [ADR 0008](docs/adr/0008-deterministic-by-construction-processing.md)
> amended: clock-read permit-list widened to name
> `vault/renderer.py`, `vault/layer.py`, `vault/storage.py` per
> v6.3.0 BORDER NOTES drift two compliance auditors independently
> flagged. Documentation drift fixed: README.md (four actively-
> false claims, broken anchor, `_meta` example version, "What's
> next" table reconciled), CLAUDE.md (file-structure block adds
> `pilot.py` + `_fixtures/`, "22 tools (v6.0)" → "25 tools (v6.1)",
> banner agent count "10" → "14", roster table adds
> `code-vs-roadmap-drift-auditor` and `roadmap-framing-auditor`),
> ROADMAP.md (ADR 0008 cite corrected to ADR 0003 in scrubber_id
> wire-up paragraph), `framework/vault/layer.py:137-140`
> (`vault_list_notes` description now lists all 7 allowed kind
> values; `failure_mode` and `dashboard` were previously
> undiscoverable from the tool schema). No router, security-
> pipeline, child, or vault-layer architecture changes — surface
> changes are corrective. Deferred: Lens 6 retention WATCH (cached
> PHI survives consent revocation; design call pending), CRITICAL-
> region coverage debt (`dispatch_internal`, cost-estimator fail-
> closed, vault snapshot atomic-write paths, audit orjson
> fallback), `vault_search_notes` kind-filter inconsistency.
>
> **v6.3.0 (2026-04-30)** — hall-of-fame team expansion. Governance /
> team-shape release. No router, security-pipeline, child, vault-layer,
> or CLI architecture changes. Adds four new specialist agents under
> `.claude/agents/` per [ADR 0011 — promotion policy](docs/adr/0011-promotion-policy.md):
> `researcher-utility-reviewer` (per-persona PI/analyst/IRB verdicts,
> canonical persona definitions), `coverage-criticality-mapper` (extends
> ci-gate-runner with ADR-anchored CRITICAL/HIGH/MEDIUM/LOW
> classification), `reproducibility-provenance-auditor` (closes the
> ADR 0008 "enforced by review at PR time" gap — audits diffs against
> determinism / audit-completeness / `_meta` / `subject_id` propagation
> invariants), and `phi-irb-risk-reviewer` (hostile-IRB-committee lens
> across six threat-model lenses: Safe Harbor, consent scope,
> audit-log completeness, ADR 0003 scrubber asymmetry, ADR 0009
> `subject_id` integrity, retention). One reshape: `integration-auditor`
> gains optional `--invariant=schema-drift` mode (per ADR 0011, this
> folds correctly into an existing agent rather than a new specialist).
> Adversarial pairing restored and codified in
> [ADR 0010 — adversarial pairing](docs/adr/0010-adversarial-pairing.md):
> `boss-report-auditor` + `red-team-reviewer` rows and Tier-2
> adversarial backstops sub-section added to CLAUDE.md (silently
> overwritten in v6.2.1's banner update; now hard-protected).
> BORDER NOTES side-channel added across all 14 specialist prompts.
> `release-shipper` gains hard-fail on dirty working tree with
> `--include-pending=<file>:<reason>` opt-in restricted to a governance-
> shape allowlist. Two new ADRs: ADR 0010 (adversarial pairing) and
> ADR 0011 (promotion policy — project-local override of the global
> "3+ uses" bar; four picks split 2/2 across old vs new bar, which is
> the load-bearing demonstration). Dogfood: `researcher-utility-reviewer`
> returned ALIGNED on v6.3.0 work itself; `boss-report-auditor` caught
> 7 framing gaps in the initial demo before dispatch.
>
> **v6.2.1 (2026-04-29)** — pilot-wizard release. Collapses the
> seven-step multi-subject pilot quickstart into two terminal commands
> and three prompts via the new `biosensor-mcp pilot` CLI subcommand
> (`src/biosensor_mcp/pilot.py`). The wizard auto-detects CSV schema
> across all files in the directory, writes `user_config.json`
> atomically, optionally registers with Claude Desktop on Win/macOS,
> and runs an end-to-end smoke check. Ships three audit-driven
> hardenings baked in from day one: F1 smoke check scans every CSV
> (not just alphabetically first — closes the "P001 looks fine, P004
> breaks at runtime" failure mode); F2 Claude Desktop config write is
> atomic via `os.replace`, BOM-round-tripped, and deep-merges into
> existing `mcpServers` (preserves sibling MCP servers); C3
> cloud-sync warning on `csv_dir.path` mirrors the existing
> `vault_path` warning (OneDrive, iCloud, Dropbox, Box, Google Drive,
> pCloud, Nextcloud, MEGA). Synthetic CSV fixtures (P001/P002/P003)
> moved from `examples/` into the package at
> `src/biosensor_mcp/_fixtures/` so they ship in the wheel — wheel
> install and source-tree work identically. `docs/guides/multi-subject-pilot.md`
> rewritten to lead with `biosensor-mcp pilot` as the primary path.
> 9 new tests in `tests/test_pilot_wizard.py`; full suite 496/496.
> New `ROADMAP.md` deferred entry: `setup` → `setup-strava` rename
> (disambiguation handled in `--help` text for now; re-evaluate when
> external doc references stabilise). No router, security-pipeline,
> child, or vault-layer architecture changes. References
> [ADR 0009](docs/adr/0009-vault-subject-keying.md) for vault
> subject-keying context carried forward from v6.2.0.
>
> **v6.2.0 (2026-04-29)** — pilot-ready release. Closes the
> multi-subject vault failure mode the proposal-mode auditor named
> for the v6.2 framing (one PI + one analyst, 5–20 participants,
> light IRB; locked at
> [docs/design/research-framing.md](docs/design/research-framing.md)).
> Adds [ADR 0009 — Vault subject-keying](docs/adr/0009-vault-subject-keying.md):
> themes carry an optional, set-once `subject_id` in frontmatter;
> evidence and moments stamp the subject of their writing call;
> list/search filters use the IS-NULL branch so cross-subject themes
> and v6.1-legacy notes stay visible. All 25 vault tools now declare
> `subject_id` in their schemas. Adds [ADR 0008 — Analytical
> processing is deterministic by construction](docs/adr/0008-deterministic-by-construction-processing.md):
> records the invariant that already shipped silently (every
> processing method is a `@staticmethod` pure function with no PRNG).
> Closes the ADR 0003 doc-lie by wiring `scrubber_id` into a new
> `audit_log` column and every `_meta` block. Promotes
> `SUBJECT_ID_SCHEMA` to `framework.interfaces` (was triplicated
> across the three child modules). Ships a multi-subject pilot
> quickstart at [`docs/guides/multi-subject-pilot.md`](docs/guides/multi-subject-pilot.md)
> with three synthetic-participant CSV fixtures under
> `examples/multi_subject_pilot/`. No router or security-pipeline
> architecture changes; existing v6.1 vaults upgrade in place via
> lazy rescan.
>
> **v6.1.1 (2026-04-29)** — docs/governance release. Adds the
> boss-architect protocols section to CLAUDE.md (five Tier-1 rules
> governing the main session at the boss-facing boundary: intent →
> options, pre-implementation audit, plain-language framing,
> anti-sycophancy / conflict pushback, demo-before-commit; plus a
> "failure modes to watch" callout naming main-session sycophancy as
> the structural risk the boss cannot self-detect). Adds
> `docs/design/operating-model.md` — a two-tier architecture memo
> covering the boss ↔ main-session ↔ specialist-agent hierarchy,
> heritage citations (PARC / Bell Labs / Apollo / Mac team / Brooks),
> and the agent roster in plain terms. All 8 agent prompts gain a
> "Refuse on conflict with codebase ground truth" hard rule as a
> Tier-2 anti-sycophancy backstop, tailored per agent.
> `integration-auditor` also gains `--proposal-mode` for
> pre-implementation defensive imagining. No router, security, child,
> vault, or CLI changes.
>
> **v6.1.0 (2026-04-29)** — vault-only release. Adds the rendering-
> layers policy ([ADR 0007](docs/adr/0007-rendering-layers-policy.md)),
> three new vault tools (failure-mode lifecycle, dashboards refresh),
> correction propagation across referencing notes, and a positioning
> document for Anthropic Managed Agents
> ([docs/design/managed-agents-compat.md](docs/design/managed-agents-compat.md)).
> 25 vault tools (was 22). No router, security, child, or CLI changes.
>
> **v6.0 (2026-04-23)** — vault-only release. The reorientation tier
> gained seven governance features (snapshot, inbox, health check,
> evidence provenance, theme lifecycle enrichment, corrections,
> session divergence); see
> [ADR 0006](docs/adr/0006-vault-overhaul-v6.md). No router, security,
> child, or CLI changes.

## What This Project Is

**Local-first infrastructure for LLM-assisted analysis of high-frequency biometric data — built for health research workflows where data governance, audit trails, and reproducibility matter.**

The intended users are health researchers (academic medical centers, mHealth labs, sleep/CGM/cardiology groups) and the research-software engineers who support them. The deliverables are a router that owns cross-cutting concerns, a ChildMCP extension point for new data sources, and a vault layer for durable cross-session analytical memory.

The running child (Strava data) is one **worked example** of the ChildMCP pattern — a complete, copyable template for wrapping a streaming biometric source. It is retained for teaching value; it is not the canonical use case.

## Workflow: manager mode

Manager mode is the default working style on this repo. The general conventions — invocation pattern, reporting cadence, when to interrupt vs proceed — live in `~/.claude/CLAUDE.md` (the global file) so they're consistent across projects. The **promote at 3+ uses** bar named there is overridden project-locally by [ADR 0011 — promotion-policy](docs/adr/0011-promotion-policy.md): specialist additions land via structural argument + severity grounding + per-agent maintenance estimate, with frequency-based 3+-uses as the fallback signal when no structural argument exists. This section names the **specialists this repo provides**.

| Agent | Owns | When to fire |
|---|---|---|
| [`vault-smoke-validator`](.claude/agents/vault-smoke-validator.md) | End-to-end vault behaviour against a temp vault | After any change to `framework/vault/` |
| [`ci-gate-runner`](.claude/agents/ci-gate-runner.md) | pytest + ruff + security probe + CLI smoke, with failure forensics | Before any commit/PR; whenever asking "is the working tree shippable?" |
| [`integration-auditor`](.claude/agents/integration-auditor.md) | Diff-vs-base audit: what's *lost* vs *gained*, classifies losses as Justified / Suspicious / Needs review | Before merging any non-trivial branch — answers "is anything load-bearing being quietly removed?" |
| [`release-shipper`](.claude/agents/release-shipper.md) | Version bump → CLAUDE.md banner → ROADMAP.md → commit → push → PR; **executes `gh pr merge --admin --merge <PR>` once the boss says "ship it"** | When a feature is ready to ship. Boss approves the merge; the agent runs the mechanics. Also accepts merge-only invocations against an existing PR. |
| [`adr-drafter`](.claude/agents/adr-drafter.md) | Drafts a numbered ADR matching the existing voice | When the boss says "ADR this" or a non-obvious decision needs a permanent record |
| [`code-vs-roadmap-drift-auditor`](.claude/agents/code-vs-roadmap-drift-auditor.md) | Audits docs against code: false claims, partly-shipped "deferred" items, load-bearing code missing from any roadmap or ADR | Before any roadmap revision, before major version-cycle planning, or when a reviewer might check claims against code. Single purpose: "is the project's documentation true?" |
| [`roadmap-framing-auditor`](.claude/agents/roadmap-framing-auditor.md) | Given a target end-state framing, renders KEEP / RESHAPE / KILL verdicts per roadmap item; identifies items the framing demands that aren't on the menu | When the boss asks "is the roadmap right under framing X?" or before any major version-cycle planning |
| [`triage-debugger`](.claude/agents/triage-debugger.md) | Diagnoses a single failure, reports root cause + suggested fix without applying it. Spawnable by *any* agent | When ci-gate-runner, integration-auditor, vault-smoke-validator, or the main session hits a failure they want triaged |
| [`boss-report-auditor`](.claude/agents/boss-report-auditor.md) | Second-translator audit: reads the main session's draft boss-facing report against the raw findings and flags suppressions, softenings, omissions, and tone slips before the boss sees the report | After the main session has drafted a plain-language report on non-trivial work but before it goes to the boss — Tier-2 anti-sycophancy backstop on protocol 3 ([ADR 0010](docs/adr/0010-adversarial-pairing.md)) |
| [`red-team-reviewer`](.claude/agents/red-team-reviewer.md) | Adversarial pairing on a confident upstream verdict (PASS, Justified, all-pass, "high confidence" root cause). Returns either a cited objection or NO OBJECTION FOUND with evidence of having looked | After any agent returns a confident verdict on non-trivial work — makes dissent visible rather than implicit ([ADR 0010](docs/adr/0010-adversarial-pairing.md)) |
| [`researcher-utility-reviewer`](.claude/agents/researcher-utility-reviewer.md) | Per-persona researcher-utility verdict (PI, analyst/RSE, IRB reviewer) on any non-trivial artifact — `RESEARCHER-LOAD-BEARING / NEUTRAL / RESEARCHER-NOISE` with severity and citable persona-job grounding | Before every non-trivial release; after any `boss-report-auditor` REVISE verdict; on demand. North-star backstop per [ADR 0011](docs/adr/0011-promotion-policy.md) |
| [`coverage-criticality-mapper`](.claude/agents/coverage-criticality-mapper.md) | Classifies uncovered code by criticality (CRITICAL / HIGH / MEDIUM / LOW) anchored on ADR-cited regions; flags newly-uncovered CRITICAL/HIGH lines as `COVERAGE REGRESSION` regardless of overall percentage | After every `ci-gate-runner` PASS on non-trivial work; spawnable from `red-team-reviewer` when its dissent target is a CI PASS |
| [`reproducibility-provenance-auditor`](.claude/agents/reproducibility-provenance-auditor.md) | Audits a diff against the reproducibility/provenance invariants codified in ADRs 0001 / 0002 / 0008 / 0003 — no PRNG in processing, audit-log completeness, `_meta` stamping, `subject_id` propagation. Per-file HOLDS / BROKEN / NEEDS REVIEW with file:line + ADR citations | After any non-trivial diff that touches `framework/` or `children/*/processing.py`. Closes the ADR 0008 "enforced by review at PR time" gap |
| [`phi-irb-risk-reviewer`](.claude/agents/phi-irb-risk-reviewer.md) | Hostile-IRB-committee lens on code changes — six threat-model lenses (HIPAA Safe Harbor, consent scope, audit-log completeness, ADR 0003 scrubber asymmetry, ADR 0009 subject_id integrity, retention). Returns NO RISK / WATCH / VIOLATION with IRB / HIPAA / ADR citations | After any change touching `framework/security.py`, `framework/audit.py`, `framework/router.py`, `framework/vault/`, or any child's `execute()` path; before any release involving consent or data flow |
| [`mcp-protocol-auditor`](.claude/agents/mcp-protocol-auditor.md) | End-to-end subprocess MCP-protocol audit — drives `python -m biosensor_mcp serve` as a real subprocess speaking JSON-RPC over stdio, asserts wire-level correctness on `initialize` / `tools/list` / `tools/call` / consent gate / cost gate / error envelopes / `_dumps` serialization seam. Catches the gate-evasion class no other specialist owns: upstream-mcp-SDK signature drift, missing schema keys, silent type coercion, markdown round-trip lossiness, post-execute hook silent failures | After any change touching `framework/router.py`, `framework/audit.py`, `framework/security.py`, `framework/vault/{layer,writer}.py`, or any child's `execute()` path; mandatory before every release. Promoted v6.5.0 after 5 protocol-adapter ship-blocker bugs surfaced in 90 minutes that 8 existing gates missed |

The agents are checked into the repo so the team is reproducible across machines. Per `.gitignore`: `.claude/*` ignores per-machine settings; `!.claude/agents/` re-includes the roster. New specialists land via [ADR 0011 — promotion-policy](docs/adr/0011-promotion-policy.md): structural argument + severity + per-agent maintenance estimate, with frequency-based 3+-uses as the fallback signal in the absence of a structural argument. The deferred roster (parked candidates with named promotion triggers) lives in [docs/design/operating-model.md § Deferred roster](docs/design/operating-model.md).

## Boss-architect protocols (Tier 1 — main-session discipline)

The boss is a non-technical conceptual architect. His one interface is the Claude Code main session; the agent roster is internal infrastructure he does not address directly. The full philosophy lives in [docs/design/operating-model.md](docs/design/operating-model.md). The five rules below govern the main session's behaviour at the boss-facing boundary. They are load-bearing — these are exactly the places where default LLM behaviour collapses to sycophancy or premature execution.

### 1. Intent → options before dispatch

When the boss states a vague conceptual intent ("make this better for researchers", "this should be cleaner", "I want X to work"), the main session must NOT immediately dispatch implementation. First produce 2–3 options:

- Each option stated in product/researcher terms (what would the analyst notice?), not technical terms
- Each with one explicit tradeoff
- One "do nothing" option always present as a default

The boss picks one or refines intent. Only then does technical work begin. Skip this step only when the intent is already implementation-shaped ("rename function X to Y", "fix the typo on line 42").

### 2. Pre-implementation audit on non-trivial work

After the boss picks an option, before code is written, the main session dispatches `integration-auditor` in `--proposal-mode` (or an equivalent defensive-imagining pass) on the *plan*. Surfaces failure modes, conflicts with prior ADRs, and the most likely way the change misbehaves. The boss decides whether the risks are acceptable before implementation begins.

"Non-trivial" means: anything touching public API, user-visible surfaces, the security pipeline, persistence, or a load-bearing ADR. Typo fixes, comment edits, and one-line refactors skip this gate.

### 3. Plain-language decision-framing on every boss-facing report

The main session never hands the boss a raw technical report. Every integration of agent findings produced for the boss must include:

- 3–5 lines in plain language stating what was found and why it matters
- An explicit "decision the boss owns" framing — what choice is in front of him, not what the team just did
- Technical detail collapsed into a footnote / expandable block / second pass the boss can ignore

If a finding can't be plain-language-justified to a non-expert, that's a signal the finding may be weakly evidenced — re-examine before surfacing.

### 4. Anti-sycophancy and mandatory conflict pushback

This is the load-bearing rule. The main session must push back on the boss when his intent conflicts with:

- An existing ADR
- A claim in CLAUDE.md or ROADMAP.md
- Documented shipped behaviour
- A prior decision the boss himself approved

Pushback means: surface the conflict in plain language *before* proceeding, name the source (ADR number, CLAUDE.md section, etc.), and ask the boss to either revise the intent or override the prior decision explicitly. Do not silently pick a side. Do not paper over the conflict. Do not invent objections to seem thoughtful, but do not suppress real ones because the boss seems committed to the idea.

The boss is non-technical and cannot catch these conflicts himself. Pushback is the main session's responsibility, not his — and absence of pushback over time is a sycophancy signal, not evidence of correctness.

### 5. Demo-before-commit on non-trivial work

For any non-trivial change (same definition as protocol 2), the main session presents a demo to the boss before commit. The demo is:

- A before/after example, a markdown walkthrough, or a representative output of the new behaviour
- A statement of "what the boss should look at" — not "here's what we did"
- An explicit confirmation request before the change is committed

This moves misalignment-detection earlier (when revising is cheap) than the existing release-shipper "ship it" gate (which fires only at PR merge).

### Failure modes to watch

The most important failure to detect, **and the one the boss cannot detect himself**: the main session never pushing back. If a month passes with no protocol-4 invocations, that is not evidence the boss has been right — it is evidence the rule has quietly collapsed. The structural backstop is to periodically have a strategy specialist (e.g. `code-vs-roadmap-drift-auditor`) re-read recent boss-facing reports and check for unsurfaced conflicts the main session should have raised.

### Tier-2 adversarial backstops

Protocols 3 and 4 above are enforced by the entity they constrain (the main session is both the translator and the judge of whether the translation is honest). That is the structural sycophancy gap a non-technical boss cannot detect from the outside. Per [ADR 0010 — adversarial pairing](docs/adr/0010-adversarial-pairing.md), two specialists exist as designed-in checks:

- **`boss-report-auditor`** — fires after the main session drafts a boss-facing report on non-trivial work, *before* the report goes to the boss. Reads the raw agent findings alongside the draft and flags suppressions, softenings, and omissions. It is the **second translator**: the main session is the first, this agent is the check on the first. The main session does not get to skip this step on non-trivial work — its absence is itself the failure mode.
- **`red-team-reviewer`** — fires after any agent returns a confident PASS / Justified / SHIPPABLE / "high confidence" verdict on non-trivial work. Produces either a cited objection or an explicit NO OBJECTION FOUND with evidence of having looked. The dissent does not have to win; it has to be **visible** so the main session cannot silently drop it during synthesis.

Both agents are tuned for refusal on conflict with codebase ground truth. Adversarial pairing is the structural import — when an agent's prompt is "do this craft well", default LLM behaviour is confirmation; when an agent's prompt is "find a flaw or prove there isn't one", the same model produces dissent. Pairing them on every high-stakes verdict is the cheapest available patch on the team's biggest gap.

When *not* to fire them: trivial work (typo fixes, comment edits, one-line refactors). Same "non-trivial" definition as protocol 2.

### Researcher-utility and compliance backstops

Per [ADR 0011 — promotion-policy](docs/adr/0011-promotion-policy.md), four additional specialists ground the team in the project's stated north star (researcher utility) and in the architecturally codified compliance / reproducibility invariants:

- **`researcher-utility-reviewer`** — reads any non-trivial artifact through three baked-in personas (PI, analyst/RSE, IRB reviewer) and renders per-persona verdicts. Catches the failure mode where the team builds for engineering elegance instead of researcher utility. Its `## Personas` section is the canonical reference; other agents (notably `phi-irb-risk-reviewer`) cite it.
- **`coverage-criticality-mapper`** — extends `ci-gate-runner`'s coverage report with criticality classification anchored on ADR-cited regions. Newly-uncovered code in CRITICAL or HIGH regions is `COVERAGE REGRESSION` regardless of overall percentage.
- **`reproducibility-provenance-auditor`** — closes the ADR 0008 "enforced by review at PR time" gap. Audits diffs against the determinism (no PRNG / no clock / `@staticmethod` purity), audit-log completeness, `_meta` provenance, and `subject_id` propagation invariants.
- **`phi-irb-risk-reviewer`** — applies the IRB-committee-member lens. Six threat-model lenses (Safe Harbor, consent scope, audit completeness, scrubber asymmetry, subject_id integrity, retention) yield NO RISK / WATCH / VIOLATION verdicts with IRB / HIPAA / ADR citations.

These four ground the team in the project's stated goal (CLAUDE.md § "What This Project Is" — health researchers, audit trails, reproducibility, data governance). They land via the structural-argument + severity + cost-vs-frequency criteria of ADR 0011 rather than the generic 3+-uses default.

## Problems this is built against

1. **Data governance.** Hosted LLMs are the wrong home for participant biometric data. The tier model and local-first processing are the structural response.
2. **Reproducibility.** LLM-assisted analyses in chat windows leave no durable trace. The audit log (every call logged to SQLite, scoped by optional `subject_id`) and `_meta` provenance stamps are the response.
3. **Longitudinal analytical memory.** Observations made in one session disappear when the chat ends. The vault layer (themes, moments, evidence logs, append-only) is the response.

Token efficiency is a useful side effect of computing summaries server-side. It is not the headline.

## Architecture

```
LLM client <--> RouterMCP (validate → circuit break → consent → cost → execute
                           → PHI scrub → audit + provenance stamp)
                   |                 ╲
              ChildMCP                VaultLayer   ← framework-level
     (one per data source)      (reorientation tier;  skips consent/cost gates)
  e.g. RunningChild, CGMChild    Obsidian vault + SQLite index
```

**Two persistence tiers, architecturally distinct:**

| Tier | Purpose | Storage | Lifecycle |
|------|---------|---------|-----------|
| **Biosensor** (ChildMCP) | Ingest, cache, rate-limit raw data | SQLite (`activities.db`) | Ephemeral — rebuildable by re-sync |
| **Reorientation** (VaultLayer) | Cross-session analytical memory | Obsidian vault (markdown + frontmatter) | Durable — canonical record |

Markdown files in the Obsidian vault are the **source of truth** for analytical knowledge; `vault.db` is a query-optimization index. Obsidian is the human-facing view of the same data the LLM accesses via vault tools.

**Key principle**: Behavioral rules (consent gates, cost gates, access tiers, PHI scrubbing) live server-side, not in the LLM. Any LLM client gets identical enforcement. Vault tools skip the biosensor-tier gates (the analyst's notes are not participant biometric data), including the PHI-scrubbing seam — only param validation and audit apply.

## File Structure

```
src/biosensor_mcp/
  __init__.py              # Package metadata
  __main__.py              # CLI: serve | pilot | setup | status | demo | uninstall | --help
  pilot.py                 # Multi-subject CSV pilot wizard (v6.2.1)
  wizard.py                # Strava OAuth wizard (localhost callback server)
  config.py                # Centralised env-var + user_config.json reader
  _fixtures/               # Synthetic per-subject CSVs shipped in the wheel
                           #   for the pilot smoke check (v6.2.1)
  framework/
    __init__.py            # Public API exports
    interfaces.py          # ChildMCP ABC, ToolDefinition, CostEstimate,
                           #   ValidationSchema, ConsentInfo, ConsentScope,
                           #   CostContext, LLMInstruction
    router.py              # RouterMCP — security pipeline + dispatch +
                           #   _meta provenance stamps, PHI-scrub seam
    security.py            # ParamValidator, CircuitBreaker, ConsentGate,
                           #   PHIScrubber (no-op default — see ADR 0003)
    cost.py                # CostGate, TokenLedger, estimate_tokens
    audit.py               # AuditLog (with subject_id) + JSON helpers
                           #   (_dumps, _loads, JSON_BACKEND)
    storage.py             # BaseStorage — thread-safe SQLite with WAL
    vault/                 # Reorientation tier (framework-level
                           #   infrastructure, not a ChildMCP)
      __init__.py          # Exports VaultLayer, VaultWriter
      layer.py             # VaultLayer — 25 tools (v6.1)
      writer.py            # Post-execute hook; atomic file writes → Obsidian
      renderer.py          # Pure markdown (run/trend/compare/theme/moment/snapshot)
      parser.py            # Frontmatter / YAML parsing for vault notes
      rescan.py            # Filesystem → SQLite index revalidation
      storage.py           # VaultStorage — SQLite index of vault notes
  children/
    __init__.py            # Docstring framing children as the extension
                           #   point for new data sources
    running/               # Worked example — see __init__.py
      __init__.py          # Exports RunningChild; framed as a template
      child.py             # RunningChild(ChildMCP) — 12 tools, 3 tiers
      processing.py        # RunningProcessing — stateless analytics
      strava_api.py        # OAuth + rate-limited Strava API client
    csv_dir/               # Generic CSV directory child
      __init__.py          # Exports CSVDirectoryChild, CSVProcessing
      child.py             # CSVDirectoryChild(ChildMCP) — 5 tools, 3 tiers
      processing.py        # CSVProcessing — stateless analytics
    template/              # Runnable starting-point child (copy + rename)
      __init__.py          # Rename checklist for new children
      child.py             # TemplateChild(ChildMCP) — minimal 3-tier skeleton
      processing.py        # TemplateProcessing — stateless analytics stubs
  demo/
    __init__.py            # Exports run_demo
    sample_data.py         # Synthetic 60-minute run data (reproducible, stdlib-only)
    runner.py              # Demo runner — execute analytics on synthetic data

tests/                     # Mirrors src/ layout
  conftest.py              # Shared fixtures (tmp_data_dir, tmp_vault_dirs)
                           #   + probe marker registration
  security_probe.py        # Standalone security probe (runs in CI, no pytest needed)
  test_security_probe_pytest.py   # @pytest.mark.probe wrapper around the standalone probe
  framework/
    test_router.py         # Router pipeline integration tests (includes VaultLayer)
    test_security.py       # ParamValidator / CircuitBreaker / ConsentGate / PHIScrubber
    test_cost.py           # CostGate / TokenLedger / estimate_tokens
    test_audit.py          # AuditLog: subject_id, params truncation, keyword-only error
    vault/
      test_layer.py        # VaultLayer handler tests
      test_renderer.py     # Markdown renderer tests
      test_writer.py       # VaultWriter atomic write + frontmatter tests
      test_parser.py       # Vault frontmatter parser tests
      test_rescan.py       # Vault index revalidation tests
  children/
    running/
      test_child_schema.py # Schema contract tests for RunningChild tools
      test_processing.py   # Pure-function analytics tests (no I/O)
    csv_dir/
      test_csv_shape.py    # Shape contract tests (ported from template)
      test_csv_processing.py  # Pure-function analytics tests
    template/
      test_template_shape.py     # Shape contract tests for the template child
      test_template_processing.py # Pure-function analytics tests
```

## Security Pipeline (Cheapest First)

| Layer | Class | Purpose |
|-------|-------|---------|
| 1 | `ParamValidator` | Type/range/pattern checks — reject before any work |
| 2 | `CircuitBreaker` | Block domain after 3 consecutive failures; auto-reset after 5 min |
| 3 | `ConsentGate` | Per-domain biometric consent, session-scoped, revocable |
| 4 | `CostGate` | Pre-estimate tokens before execution; gate if > 35,000 tokens |
| 5 | `PHIScrubber` | Institutional PHI-stripping seam; no-op default, subclass-per-child when a real policy exists |
| 6 | `AuditLog` + `TokenLedger` | Every call logged to SQLite with optional `subject_id` scoping; cumulative session spend |

Every successful result also carries a `_meta` block stamped with `package_version`, `tool_name`, and a UTC `called_at` timestamp — minimum-viable provenance for results that may end up in a paper.

## Three-Tier Access Model

The tier model is a technical implementation of data minimization — the question "at what resolution does the analyst actually need this?" made executable.

| Tier | What the LLM Sees | Tokens (running example) | Gate |
|------|-----------------|--------|------|
| 1 — Free | Server-computed reports (splits, zones, drift, decoupling, EF, trends) | 200–1,500 | None |
| 2 — Consent | Downsampled streams at 5–30s for visualization | 3,000–7,000 | Biometric consent |
| 3 — Cost | Per-timestamp streams with precision reduction | 25,000–60,000 | Consent + cost approval |

Most analytical questions are answerable at Tier 1 with zero raw biometric data leaving the machine. Token counts are illustrative and come from the running child; other domains will have different baselines.

## Running Child (worked example) — 12 Tools

| Tool | Tier | Description |
|------|------|-------------|
| `strava_sync` | 1 | Pull recent activities from Strava into local cache |
| `strava_list_runs` | 1 | List recent runs with summary stats |
| `strava_activity_detail` | 1 | Single-activity overview |
| `strava_hr_analysis` | 1 | Zone distribution, drift, anomalies |
| `strava_pace_analysis` | 1 | Mile splits, run/walk classification |
| `strava_stop_analysis` | 1 | Pause detection with GPS + saved labels |
| `strava_label_stop` | 1 | Persist stop label to SQLite |
| `strava_run_report` | 1 | Comprehensive: decoupling, EF, drift, phases, GAP |
| `strava_trend_report` | 1 | Rolling weekly volume, avg pace, avg HR |
| `strava_compare_runs` | 1 | Side-by-side comparison of 2–5 runs |
| `strava_downsampled_streams` | 2 | HR, pace, GPS at 5–30s intervals |
| `strava_full_streams` | 3 | Per-second data with precision reduction |

## CSV Directory Child — 7 Tools

Opt-in via `csv_dir` key in `user_config.json`. Wraps a local directory of per-subject CSV files — no OAuth, no vendor API. The "ingest a directory" pattern complementing the running child's "wrap an API" pattern.

| Tool | Tier | Description |
|------|------|-------------|
| `csv_list_files` | 1 | List CSV files with size and column names |
| `csv_file_detail` | 1 | Single-file metadata + per-column stats |
| `csv_summary_report` | 1 | Per-column summaries, time range, completeness |
| `csv_cohort_summary` | 1 | Cross-file aggregation by metadata-sidecar group (n / mean / std / min / max per group). Requires `metadata.json` sidecar — see ADR 0015. |
| `csv_force_decline` | 1 | Per-file fatigue diagnostic — peak, decline %, decline rate, time-to-50%-drop. Generic over force / EMG envelope / power. |
| `csv_downsampled` | 2 | Decimated rows at every Nth interval |
| `csv_raw_stream` | 3 | Full per-row data with precision reduction |

Optional sidecar for cohort grouping: `<csv_dir.path>/metadata.json` with schema `{"<filename>": {"<field>": <value>, ...}}`. Required by `csv_cohort_summary`; ignored by every other tool. Schema matches REDCap / DataCite / Frictionless Data conventions. See [ADR 0015](docs/adr/0015-tier-1-cohort-surface-and-metadata-sidecar.md).

## Running and Testing

For end users (PIs, analysts), the canonical install path is uv (or
pipx) against the GitHub URL — no Python install, no venv ritual:

```bash
uv tool install git+https://github.com/saahasmuthineni/Biosensor-to-LLM-Connector.git
biosensor-mcp pilot     # Three-prompt wizard for the multi-subject CSV pilot
```

For development on the framework itself:

```bash
# Install in dev mode (editable, source tree on disk)
pip install -e ".[dev]"

# Run tests
pytest -v

# CLI smoke test
biosensor-mcp --help

# Subcommands
biosensor-mcp pilot      # Multi-subject CSV pilot setup wizard (v6.2.1+)
biosensor-mcp setup      # Strava OAuth wizard for the worked-example child
biosensor-mcp demo       # Run analytics on synthetic data (no setup needed)
biosensor-mcp serve      # Start MCP server (Claude Desktop calls this)
biosensor-mcp status     # Diagnostic check
```

## Key Design Decisions

Architectural decisions are captured as numbered ADRs under
[docs/adr/](docs/adr/) — one file per decision, each with its own
context / decision / consequences / alternatives. Summaries below link
to the full record.

- **[ADR 0001 — Audit log is the backbone](docs/adr/0001-audit-log-as-backbone.md).** Every tool call lands in `audit.db`: timestamp, domain, tool, tier, parameters, token estimate, outcome, latency, optional error, optional `subject_id`. Durable evidence of how an analyst accessed participant data — the single most load-bearing feature for research use.
- **[ADR 0002 — `subject_id` scoping](docs/adr/0002-subject-id-scoping.md).** First-class audit column, optional on calls. The router extracts `subject_id` from parameters and threads it to every audit row; children adopt it in `param_schemas` incrementally. Legacy `audit.db` migrates via `ALTER TABLE`.
- **[ADR 0003 — PHI scrubbing is a seam, not a policy](docs/adr/0003-phi-scrubber-seam.md).** `PHIScrubber.scrub()` is a no-op by default; institutions subclass. The default emits a one-time warning on first construction and exposes `scrubber_id` so audit rows distinguish misconfigured deployments from real policies.
- **[ADR 0004 — Structured `LLMInstruction`](docs/adr/0004-structured-llm-instruction.md).** Consent and cost gates return a JSON object with individually checkable `must_do`, `must_not_do`, and `on_ambiguous_reply` fields — not a free-text paragraph. Makes compliance auditable.
- **[ADR 0005 — Pre-estimation, not post-billing](docs/adr/0005-cost-pre-estimation.md).** `CostGate` calls `child.estimate_cost()` before execution using stream metadata (point counts), never the full payload. Estimator failures fail closed.
- **[ADR 0007 — Rendering-layers policy](docs/adr/0007-rendering-layers-policy.md).** Source-of-truth markdown is plain and AI-readable; plugin-enhanced views (Dataview, Templater) are additive. Any framework-emitted note that uses plugin syntax must ship a snapshot fallback so the same content renders for any reader. The dashboards refresh tool is the reference implementation.
- **[ADR 0008 — Analytical processing is deterministic by construction](docs/adr/0008-deterministic-by-construction-processing.md).** Every method on `RunningProcessing`, `CSVProcessing`, and `TemplateProcessing` is a `@staticmethod` pure function with no PRNG and no clock reads. The invariant is enforced by review at PR time. The same Tier-1 call with the same inputs returns the same numbers across machines — the ROADMAP "Deterministic mode" item is therefore partially resolved; what remains is a small router-level audited flag paired with content-hashed provenance.
- **[ADR 0009 — Vault subject-keying](docs/adr/0009-vault-subject-keying.md).** Themes carry an optional, set-once `subject_id` in frontmatter — promotion (None → P004) is allowed, reassignment (P003 → P007) is a hard error. Evidence blocks and moments stamp the subject of their writing call. List/search queries filter rows match-or-NULL when `subject_id` is provided so cross-subject themes and v6.1-era legacy notes stay visible. Resolves the design question ADR 0002 deliberately deferred.
- **[ADR 0015 — Tier-1 cohort surface + metadata sidecar](docs/adr/0015-tier-1-cohort-surface-and-metadata-sidecar.md).** Two new Tier-1 tools on the CSV directory child — `csv_cohort_summary` (cross-file aggregation by metadata-sidecar group) and `csv_force_decline` (per-file fatigue diagnostic). Group identity travels via `<csv_dir>/metadata.json` (schema `{filename: {field: value}}`, REDCap-shaped), required only by `csv_cohort_summary`. Closes the structural gap where the *"no streams enter LLM context"* claim could not hold for cohort questions: the per-file `csv_summary_report` could not satisfy *"compare X between groups A and B"* without either fabricating numbers or escalating to Tier 2. Pure-function processing per ADR 0008 unchanged.
- **[ADR 0016 — MCP-protocol auditor: wire-level correctness is a seam, not a hope](docs/adr/0016-mcp-protocol-auditor.md).** Promotes `mcp-protocol-auditor` as a permanent specialist after the v6.5.0 demo-before-commit gate surfaced 5 ship-blocker bugs in 90 minutes that 8 existing gates missed. The framework's MCP-protocol-adapter surface (the JSON-RPC adapter between internal abstractions and the wire format the `mcp` SDK serializes) was structurally untested — no agent in the prior roster drove the framework as a real subprocess speaking JSON-RPC over stdio. The new specialist closes that gap; its first run was the audit that justified its creation (recursive use). Cites ADRs 0001 / 0008 / 0010 / 0011 / 0014.

### Implementation notes

Domain-specific tuning choices that inform behavior but aren't
architectural decisions in the ADR sense:

- **Grade precision at 1 decimal**: GAP calculation uses `cost = 1 + 0.03 * grade%`. Rounding grade to integer introduces ~3% split error. All other numerics are reduced more aggressively.
- **0.5 m/s stop threshold**: 0.3 m/s was too aggressive (flagged slow shuffles at end of hard efforts). 0.5 m/s (~1.8 km/h) is the designed "completely stopped" signal.
- **Spike detection 30-second cooldown**: A single Apple Watch sensor catchup burst can generate dozens of overlapping anomaly entries without the cooldown.
- **orjson with stdlib fallback**: `_dumps`/`_loads` wrappers in `framework/audit.py` are transparent to all consumers.
- **`router.close()` on Windows**: SQLite WAL connections must be explicitly closed before the process exits on Windows. Call `router.close()` in tests and server shutdown to release file locks.
- **`subject_id` on `strava_*` and vault tools**: All 12 running tools and all 25 vault tools declare an optional `subject_id` parameter (pattern `^[A-Za-z0-9_\-]{1,64}$`). For biosensor children it's audit-log scoping only — does not filter source data, since one authenticated Strava account may cover multiple study participants and `subject_id` is the caller's statement of which one this call is about. For vault tools (per ADR 0009) it additionally keys notes: themes have a set-once subject in frontmatter; evidence and moments stamp the subject of their writing call; list/search queries filter on it. The shared `SUBJECT_ID_SCHEMA` and `SUBJECT_ID_PARAM_DOC` constants live in `framework.interfaces`.

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `BIOSENSOR_CONFIG_DIR` | `~/.biosensor-mcp` | Token, user config, rate limit files |
| `BIOSENSOR_DATA_DIR` | `~/.biosensor-mcp/data` | SQLite databases |
| `STRAVA_STREAM_CACHE_TTL_DAYS` | `7` | Stream cache eviction |

User config at `~/.biosensor-mcp/user_config.json`:
```json
{
  "max_hr": 185, "resting_hr": 55,
  "home_lat": 42.360, "home_lng": -71.058,
  "csv_dir": {
    "path": "/path/to/csv/directory",
    "timestamp_column": "timestamp",
    "timestamp_format": "%Y-%m-%dT%H:%M:%S",
    "value_columns": {
      "heart_rate": "Heart rate (bpm)",
      "glucose": "Blood glucose (mg/dL)"
    }
  }
}
```

## Claude Desktop Integration

```json
{
  "mcpServers": {
    "biosensor-mcp": {
      "command": "~/.biosensor-mcp/venv/bin/python",
      "args": ["-m", "biosensor_mcp", "serve"],
      "env": {
        "BIOSENSOR_CONFIG_DIR": "~/.biosensor-mcp",
        "BIOSENSOR_DATA_DIR": "~/.biosensor-mcp/data"
      }
    }
  }
}
```

## Adding a New ChildMCP (new data source)

Children are the framework's extension point. Each one wraps one data source (CSV directory, EDF file, FHIR bundle, REDCap export, vendor API) and exposes tiered tools; the router handles everything else uniformly.

Implement 4 abstract items and register:

```python
from biosensor_mcp.framework import ChildMCP, ToolDefinition, CostEstimate, ValidationSchema, ConsentInfo

class CGMChild(ChildMCP):
    @property
    def domain(self) -> str: return "cgm"

    @property
    def display_name(self) -> str: return "Glucose (Dexcom)"

    @property
    def consent_info(self) -> ConsentInfo:
        return ConsentInfo(
            data_types=["glucose levels", "meal markers"],
            purpose="glycemic analysis and trends",
        )

    @property
    def tool_definitions(self) -> list[ToolDefinition]:
        return [ToolDefinition("cgm_daily_report", 1, "Time-in-range, variability", {...})]

    @property
    def param_schemas(self) -> dict: ...

    async def execute(self, tool_name, params) -> dict: ...

    async def estimate_cost(self, tool_name, params) -> CostEstimate: ...

# In __main__.py cmd_serve():
router.register_child(CGMChild(config_dir, data_dir))
# Router auto-generates approve_consent_cgm + revoke_consent_cgm
```

For a runnable starting point that already passes shape tests, copy
`src/biosensor_mcp/children/template/` and rename. See its
`__init__.py` for the rename checklist.

## Framework-Level Infrastructure (Not a ChildMCP)

Components that represent durable cross-session state — not biosensor domains — register directly with the router and bypass the biosensor-tier gates (consent, cost, circuit breaker, PHI scrub). Param validation and audit still apply.

`VaultLayer` is the reference implementation of this pattern:

```python
# In __main__.py cmd_serve():
from biosensor_mcp.framework.vault import VaultLayer

router.register_vault_layer(VaultLayer(
    vault_path=vault_path,
    vault_writer=vault_writer,
    backfill_config={                       # decouples from sibling tool names;
        "list_tool": "strava_list_runs",    # cross-child knowledge lives at the
        "report_tool": "strava_run_report", # wiring site, not inside the vault
    },
))
```

Key differences from a ChildMCP:
- No `domain`, `consent_info`, or `estimate_cost()` — these are biosensor-tier concerns
- Dispatch skips circuit breaker, consent gate, cost gate, PHI-scrub seam, and post-execute hooks
- Only param validation + audit apply
- Tools must still have unique names (collision with any registered child is rejected)

### VaultLayer — 25 Tools (v6.1)

All tools are Tier 1 and skip the biosensor-tier gates.

Orientation & browse:
| Tool | Description |
|------|-------------|
| `vault_get_snapshot` | Read `snapshot.md` — fastest session-start orientation. Falls back to `vault_get_fitness_summary` when no snapshot exists. |
| `vault_generate_snapshot` | (Re)write `snapshot.md` with open themes, recent moments, weekly run aggregates, and vault health. Call at session end. |
| `vault_get_fitness_summary` | Older orientation tool: aggregate weekly fitness + open themes + recent moments by scanning the index. |
| `vault_list_notes` / `vault_read_note` / `vault_search_notes` | Browse, read, full-text search. Kind filter accepts `failure_mode` and `dashboard` in v6.1. |
| `vault_list_anomalies` | Runs with `anomaly_count > 0`. |
| `vault_traverse_links` | Wikilink neighbourhood of a note (no bodies). |

Themes & moments:
| Tool | Description |
|------|-------------|
| `vault_list_themes` / `vault_read_theme` | Compact rows or full body of a persistent hypothesis. |
| `vault_upsert_theme` | Create or update. Supports reframe (new hypothesis → `## Prior Framings`), thinking entries, evidence provenance (`evidence_source_*` + `evidence_verification`), and fold-back on resolution. |
| `vault_correct_evidence` | Mark a specific evidence block as superseded by timestamp; preserves the original. New `propagate=true` mode appends a `[!warning]` callout to every note that wikilinks to the theme (idempotent on the (slug, evidence_timestamp) pair). |
| `vault_list_moments` / `vault_capture_moment` | Aha-moment notes. |
| `vault_capture_session` | Session-boundary bundle: summary moment + N theme updates + N moments + optional `divergence`. |

Failure-modes (v6.1):
| Tool | Description |
|------|-------------|
| `vault_log_failure_mode` | Create or update a failure-mode note — symptom / diagnosis / mitigation + append-only evidence log. The "how we got it wrong" counterpart to themes. Body sections are creation-only; metadata (status, related_themes, related_subjects, tags) updates in-place to preserve the evidence log. |
| `vault_list_failure_modes` | Compact listing — slug, status, opened, last_updated, related_theme_count. |

Annotation & maintenance:
| Tool | Description |
|------|-------------|
| `vault_annotate_run` | Persist insight notes back to a run note. |
| `vault_backfill` | LLM-driven, server-orchestrated note generation for cached activities. |
| `vault_rescan` | Full filesystem sweep — reconcile SQLite index with user edits. |
| `vault_refresh_dashboards` | Materialise `dashboards/open-themes.md`, `active-failure-modes.md`, and `recent-moments.md` from the SQLite index. ADR 0007 dual-output: snapshot table is always rendered (source of truth); optional Dataview live-query block above renders only with the plugin. |
| `vault_health_check` | Stale themes, orphaned moments, themes without evidence, inbox depth, counts by status. |

Inbox (low-friction capture):
| Tool | Description |
|------|-------------|
| `vault_inbox_add` | Append a timestamped line to `inbox.md`. |
| `vault_inbox_list` | Parse inbox lines into structured items. |
| `vault_inbox_drain` | Bulk process items: promote to moment / append to theme as evidence / discard. |

## Further reading

- [README.md](README.md) — audience-facing overview.
- [docs/design/research-framing.md](docs/design/research-framing.md) — the longer-form document aimed at health-research reviewers and RSEs.
- [docs/design/managed-agents-compat.md](docs/design/managed-agents-compat.md) — Path A (local-first) vs Path B (Anthropic Managed Agents over network MCP), threat models, and which deployment shape suits which IRB profile.
- [docs/adr/](docs/adr/) — Architecture Decision Records for the framework's load-bearing choices.
- [ROADMAP.md](ROADMAP.md) — explicitly deferred work with effort/impact triage (real PHI scrubbing, new children, deterministic replay, full provenance hashing, per-subject tool-parameter scoping, multi-analyst vault attribution, vault freeze, worked-example notebook, evaluation harness).

## CI

`.github/workflows/ci.yml` runs on push/PR to `main` across Ubuntu, Windows, macOS × Python 3.10/3.11/3.12. Steps: install deps → `pytest -v` → `biosensor-mcp --help`.
