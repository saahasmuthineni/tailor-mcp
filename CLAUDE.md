# CLAUDE.md — Tailor

> **Note for human contributors:** This file is read automatically by Claude when working in this repo. If you're a human contributor, see [CONTRIBUTING.md](CONTRIBUTING.md) instead.

> **v9.0.0 (2026-05-26)** — Public-flip preparation. Major bump.
> Three domain-specific structural identifiers renamed to domain-
> agnostic equivalents; license switched Apache-2.0 →
> AGPL-3.0-or-later; new token-efficiency benchmark artifact backing
> [ADR 0029](docs/adr/0029-token-reduction-as-analytical-quality.md).
> The framework was always *architecturally* domain-agnostic
> (CLAUDE.md § "What This Project Is") — first shipped recipe is
> health research, platform identity is data-agnostic. The vocabulary
> was research-shaped, which biased a casual visitor's read. This
> release makes the externally-visible vocabulary match the
> architectural commitment.
>
> **Renames (forward-only; backward-compat on durable state).**
> Three identifiers swapped:
>
> - `PHIScrubber` (framework class) → `DataScrubber`. The seam
>   contract is unchanged — institutions still subclass it to wire
>   their IRB-approved scrubbing policy. The child-level
>   `RedcapPHIScrubber` retains its HIPAA-specific name per
>   [ADR 0037](docs/adr/0037-redcap-child-scope-export-directory-only-with-deferred-live-api.md)
>   § parallel-seam invariant — HIPAA *is* the institutional policy
>   that child enforces. The rename clarifies which scrubber is
>   domain-agnostic (framework) and which is institution-specific
>   (REDCap).
> - `subject_id` → `entity_id` across the `audit_log` column, every
>   child's `param_schemas`, every vault tool, the shared
>   `ENTITY_ID_SCHEMA` + `ENTITY_ID_PARAM_DOC` constants in
>   `framework.interfaces`, and vault note frontmatter. "Subject" is
>   research-shaped; the framework's identity-scoping primitive
>   applies to any deployment recipe (knowledge work, creative
>   archives, clinical workflows, family / household). 1,097
>   occurrences across 111 files; word-boundary regex driven by a
>   checked-in `scripts/rename_for_public_flip.py` so the recipe is
>   reproducible.
> - `csv_cohort_summary` → `csv_group_summary` on the generic
>   `csv_dir` child only. The biometric children's sibling tools
>   `force_cohort_summary` / `emg_cohort_summary` /
>   `redcap_cohort_summary` retain their `_cohort_` names because
>   they ARE cohort-shaped in the research sense; the rename
>   applies only where the surface is data-agnostic.
>
> **Backward compatibility for existing deployments.** Forward-only
> rename does not break v8.x users who upgrade in place:
>
> - `audit_log` table: `AuditLog.__init__` detects legacy `subject_id`
>   column on boot and runs `ALTER TABLE audit_log RENAME COLUMN
>   subject_id TO entity_id`. Every existing row preserved per
>   [ADR 0001](docs/adr/0001-audit-log-as-backbone.md)
>   durability invariant.
> - Vault note frontmatter: `parser.split_frontmatter` aliases legacy
>   `subject_id:` to `entity_id:` on read so notes written under the
>   old name continue to load without migration.
>
> No backward-compat for in-process callers — tool parameter names,
> exported constants, and the audit-log column name break cleanly.
> That's the v9.0.0 major-bump shape: API surface breaks, durable
> state migrates transparently.
>
> **License switched: Apache-2.0 → AGPL-3.0-or-later.** Forward-only.
> Tagged releases through v8.0.0 remain Apache-2.0 in perpetuity for
> recipients who already received them; v9.0.0 onward is AGPL.
> Rationale: AGPL's network-trigger clause (§ 13) is the structural
> lever against extractive cloud reuse — a future cloud provider that
> forks Tailor and offers "Tailor Cloud" as a managed service must
> publish their modifications under AGPL. For local-first deployments
> (the framework's primary use case) the network-trigger rarely fires
> in normal use, so AGPL adds minimal friction for individual
> researchers and institutional installs.
>
> **Token-efficiency benchmark — new artifact backing ADR 0029.**
> `benchmarks/token_efficiency.py` + `benchmarks/token_efficiency.md`
> ship a reproducible measurement of the "AI economics" claim in
> [ADR 0029](docs/adr/0029-token-reduction-as-analytical-quality.md).
> Two named scenarios:
>
> - **Per-query efficiency (Tier-1 surface vs raw CSV → LLM context).**
>   Single-subject S004 fatigue diagnostic: **657.6×** (48,006 vs 73
>   tokens). 16-subject cohort comparison stratified by sex:
>   **938.2×** (769,311 vs 820 tokens). The cohort baseline at 769K
>   tokens exceeds Claude Sonnet's 200K context window — the raw-CSV
>   approach is not just expensive at cohort scale, it is
>   structurally impossible without chunking.
> - **Session persistence efficiency (vault retrieval vs naive
>   reconstruction).** Single S004 thread resume: **318.0×**
>   (771,743 vs 2,427 tokens). Cumulative across 5 sessions: 318× —
>   ~$57.90 baseline vs ~$0.04 with Tailor at Sonnet 4.6 input
>   pricing.
>
> All measurements with `tiktoken cl100k_base` (industry-standard
> Claude proxy; Anthropic's tokenizer is not publicly distributed).
> The "at least 100× cheaper" claim ADR 0029 named as a conservative
> floor turns out to be **3.2× to 9.4× the floor** depending on
> scenario. The benchmark markdown carries an Assumptions table, a
> quantitative prompt-caching counter-factual (even optimal Anthropic
> prefix caching does not close the gap — under best-case caching
> Tailor is still ~106× cheaper on the cumulative scenario), and a
> Limitations section naming cases where the gap is smaller (one-shot
> analysis on tiny CSVs, datasets that do not decompose into
> per-subject scalars). Rigor calibrated for a skeptical engineer,
> not for marketing.
>
> **Doc sweep + ADR amendments.** Current-state documentation
> (README, CLAUDE.md § "What This Project Is" onward, ROADMAP active
> sections, docs/guides/, the four ADRs in scope: 0002, 0003, 0009,
> 0015) swept to use the new vocabulary. Historical sections
> preserved verbatim — CLAUDE.md banners for v6.x-v8.0, ROADMAP
> "Shipped (chronological)" section, CHANGELOG.md, docs/reports/* all
> left as-written. Each of the four in-scope ADRs gains a
> `**Renamed in v9.0.0:**` header bullet documenting the rename's
> provenance + backward-compat mechanism. `docs/design/tailor-
> vocabulary.md` gains a § "Vocabulary changes — v9.0.0" enumerating
> the three renames in a table. README license section expanded from
> the bare text `Apache-2.0.` to a ~35-line plain-English summary of
> AGPL-3.0-or-later's scope + the network-trigger nuance.
>
> **README hero repositioned.** From "personal AI server with
> research-grade trust" → **"Local data preprocessing for AI —
> structured summaries, governed access, auditable answers."**
> Problem-first narrative (raw data into LLM is expensive, unsafe,
> and produces worse answers); the benchmark numbers (657×–938× per
> query, 318× session persistence) sit in the first visible section
> as load-bearing proof, not back-channeled marketing.
>
> **Branch shape: 4 commits on `feature/v9-public-flip-prep`.**
> `b639b8e` rename + benchmarks → `6d3fd98` license file + SPDX
> identifier → `84f4c93` doc sweep → `d11a412` README license section.
> Plus this v9 banner + README hero + housekeeping in follow-up
> commits, then push + PR.
>
> **Gates: 1,588 pytest pass, 3 skipped** (scipy-not-installed —
> MATLAB child shape tests; orthogonal to this work). Backward-compat
> migration verified on a fresh `audit.db` and on a legacy `audit.db`
> with the v8 `subject_id` column (column rename runs at boot, rows
> preserved). Vault frontmatter alias verified on bundled
> `snapshot.md` (which carries the new key) and on a fixture written
> with the old key (parser surfaces both). `mcp-protocol-auditor` /
> `recipient-install-validator` / `cue-card-rehearsal-auditor` NOT
> TRIGGERED (no wire-shape changes, no install-path changes, no
> CUE_CARD.md edits — only identifier renames + new constant docs).
>
> **What did NOT change.** No router-pipeline / security-pipeline /
> child / vault-layer / CLI architecture changes beyond the
> identifier renames. No new ADRs. No new framework-tier layers. No
> new children. No new schema beyond the audit-column rename
> (column count unchanged; only the column NAME changed). The v9
> bump is vocabulary + license + benchmark artifact + documentation
> sweep. Public-flip-ready as of `feature/v9-public-flip-prep`'s
> latest tip; repo visibility flip is the boss's call, not landed in
> this branch.

> **v8.0.0 (2026-05-19)** — A' (recipient-experience MCP-offload). Major
> bump. Three new framework-tier layers (`SetupLayer`,
> `WalkthroughLayer`, `FittingRoomLayer`) per [ADR 0040](docs/adr/0040-bounded-setup-time-conductor-surface.md);
> four CLI commands hard-removed (`tailor walkthrough`, `tailor
> fitting-room`, `tailor tour`, `tailor demo`). Codifies a bounded
> setup-time conductor surface — a carve-out from [ADR 0022's](docs/adr/0022-local-llm-guardian.md)
> conductor-mode deferral scoped to setup-time-only via a hard-coded
> source-key allowlist. Driven by Taylor's 2026-05-19 macOS install
> friction: a non-technical recipient typed `--help` at a path prompt
> because terminals weren't a familiar interface — the architectural
> response is to move recipient-facing surfaces (walkthrough,
> fitting-room, source-config setup) off the CLI into MCP tools that
> Claude orchestrates conversationally.
>
> **Three new framework-tier layers — parallel to VaultLayer /
> LocalLLMLayer / SetupHelpLayer / AuditQueryLayer.** All bypass
> biosensor-tier gates (consent, cost, circuit breaker, framework
> PHI scrub) per [ADR 0012 § Amendment v7.4.0](docs/adr/0012-vault-phi-scrubber-bypass.md);
> only param validation + audit apply. Same `(None, tool_def)` sentinel
> in `_tool_map` + `_framework_layer_owner` routing pattern as the four
> existing layers.
>
> **`SetupLayer`** (`framework/setup/`) exposes four MCP tools for
> source-config setup: `tailor_setup_status` (read-only configured /
> awaiting state), `tailor_setup_detect_schema(source_type, path)`
> (read-only schema detection wrapping the v7.5.0 `pilot.py` helpers),
> `tailor_setup_confirm_schema(source_type, path, schema)` (pure
> compute confirmation), and `tailor_setup_write_source_block(
> source_type, path, validated_schema)` (the bounded write tool).
> `source_type` uses `allowed_values=["csv","matlab","redcap"]` against
> the v7.6.0 D1 closure in `ParamValidator`. Each tool's description
> is tuned for natural-language inference so terminal-averse recipients
> drive setup by saying *"Hi Claude, I have CSV data at ~/data/cohort/
> — set Tailor up to use it"*.
>
> **Bounded-write authority is the load-bearing invariant.**
> `tailor_setup_write_source_block` writes ONLY the source-config keys
> named in `SETUP_WRITE_KEY_ALLOWLIST = ("csv_dir", "matlab_file",
> "redcap_file")` — a hard-coded module-level constant at
> `framework/setup/sources.py`. Three layers of defense: (1)
> `ParamValidator.allowed_values` on `source_type` rejects unknown
> tokens; (2) `build_source_block` raises `UnknownSourceType` on any
> mismatched token; (3) the dispatch site in `_tool_write_source_block`
> re-checks the source_key against the allowlist before invoking the
> canonical writer. A bug in (2) cannot widen the surface because (3)
> independently refuses. The canonical writer is the v7.5.0 multi-
> source coexistence deep-merge `pilot._write_user_config` — no
> hand-rolled writer in the new tier.
>
> **`WalkthroughLayer`** (`framework/walkthrough/`) exposes a single
> tool `tailor_walkthrough_section(section: int)` with `min=1, max=5`.
> Replaces the v6.10.5 `tailor walkthrough` CLI showcase. Five sections
> return structured payloads Claude narrates conversationally to the
> recipient: (1) Tier-1 cohort thesis; (2) router pipeline + audit row;
> (3) three-tier consent + cost model; (4) vault layer cross-session
> memory; (5) local-LLM guardian + deterministic processing. Each
> payload carries narrative prose, a worked-example call shape +
> wire-verified result preview, ADR citations, and a next-step prompt.
>
> **`FittingRoomLayer`** (`framework/fitting_room/`) exposes three
> tools (`tailor_fitting_room_status` / `_scaffold` / `_index_vault`)
> that wrap the pure helpers in the preserved `tailor.fitting_room`
> library module. Replaces the v6.9.0 `tailor fitting-room` CLI
> command. Notably the new MCP path does NOT write Claude Desktop
> config — `tailor pilot` is now the sole CLI surface that does that,
> and the v7.5.0 Taylor-class orphan-cleanup defect (pilot wipes
> fitting-room's Claude Desktop registration) self-retires
> structurally under A' because fitting-room no longer registers with
> Claude Desktop at all.
>
> **CLI surface contracts from 8 commands to 6.** Four commands hard-
> removed: `tailor walkthrough` / `tailor fitting-room` / `tailor tour`
> / `tailor demo`. No deprecation shim. The remaining six —
> `serve / pilot / setup / redcap / status / uninstall` — are the
> operator/RSE surface. Recipients touch the terminal exactly once
> (`tailor pilot` for Claude Desktop registration + first source
> config); everything else happens through Claude Desktop chat.
> `src/tailor/tour.py` (the v7.1.x re-export shim) deleted. Examples
> migrated to import from `tailor.fitting_room.main` directly.
> `wizard.py` PRESERVED — load-bearing for `cmd_setup`'s Strava OAuth
> wizard.
>
> **New `SETUP_CONFIG_WRITE` audit-log outcome.** Every successful
> `tailor_setup_write_source_block` call emits a row with
> `outcome="SETUP_CONFIG_WRITE"` (not `"SUCCESS"`), `domain="setup"`,
> the framework `scrubber_id`, and `subject_id=NULL` (configuration is
> not subject-scoped per [ADR 0009](docs/adr/0009-vault-subject-keying.md)).
> An IRB reviewer querying `audit.db` reconstructs *"when did Claude
> write configuration on this machine"* via
> `SELECT * FROM audit_log WHERE outcome='SETUP_CONFIG_WRITE'`. The
> `audit_query` tool's outcome-filter description carries the new
> value in its common-values list; the schema is unconstrained
> `type=str` so the new value flows through without an allowlist
> amendment (same precedent as `ATTEST_INITIAL` per v7.5.0).
>
> **`_redact_home()` wire-egress defense (phi-irb WATCH-1 closure).**
> SetupLayer wire-response paths (`written_path`, `user_config_path`,
> echoed `path` on detect/confirm) collapse `Path.home()` to `~` per
> HIPAA Safe Harbor §164.514(b)(2)(i)(R) — extends the v6.10.2
> SetupHelpLayer redaction pattern to the SetupLayer surface so
> username-bearing path strings stay off the hosted-LLM chat
> transcript. On-disk artifacts (`~/.tailor/user_config.json`,
> `audit_log.params`) carry the un-redacted operator intent; the
> operator owns retention there per the ADR 0040 § Amendment retention
> contract.
>
> **ADR 0040 § Amendment 2026-05-19 — operator-managed retention
> contract (phi-irb VIOLATION Lens 6 closure).** Scope-bounds
> [ADR 0013's](docs/adr/0013-cache-only-purge-on-consent-revocation.md)
> *"revocation = no cache"* invariant to biosensor-cache tables
> (unchanged from ADR 0013), and explicitly names *"configuration
> written by SetupLayer is operator-managed retention"* as the
> SetupLayer retention contract. The biosensor-cache purge and the
> SetupLayer config write are separate retention surfaces by design.
> `docs/design/research-framing.md` § "Consent withdrawal under this
> profile" gains a fifth retention category (SetupLayer-written
> configuration) alongside biometric cache / analyst-authored notes /
> oracle audit rows / trust-root attestation rows. Reversal condition
> named: first real-world deployment that surfaces the configuration-
> retention-on-revocation problem during an IRB inquiry, OR an
> operator who needs an automated revocation-and-purge ritual to
> satisfy an institutional policy — either triggers a follow-on ADR.
>
> **Bug self-retirement.** The v7.5.0 orphan-cleanup defect Taylor's
> 2026-05-19 macOS run surfaced (pilot's `_is_orphan_entry_key`
> wipes fitting-room's `tailor-fitting-room-hip-lab` Claude Desktop
> entry as a "stale orphan") becomes structurally moot under A'.
> Fitting-room is no longer a CLI command writing Claude Desktop
> config; pilot is the sole CLI writer of Claude Desktop config.
> No siblings, no orphan-cleanup-too-greedy, no bug. Skipped the
> v7.5.1 patch entirely — architecture closes the defect class.
>
> **L1/L2 paragraph in CLAUDE.md § "Adding a New ChildMCP" amended.**
> The v7.5.0 paragraph deferred two wizard surfaces with named
> reversal conditions (Wizard-child MCP surface; LocalLLMLayer-folded
> wizard). Both reversal conditions remain accurate; A' is a sibling
> resolution scoped to setup-time-only via the bounded-write
> allowlist + retire-after-restart conditional-on-boot lifecycle. The
> paragraph now carries a "Partial sibling-resolution by ADR 0040
> (v8.0.0)" subsection naming the distinction.
>
> **Always-registered lifecycle.** The framework has no runtime
> un-register convention as of v7.6.0; `SetupHelpLayer` is
> conditionally REGISTERED at boot but no layer un-registers itself
> at runtime once a condition is met. ADR 0040 explicitly weighed
> conditional registration (SetupHelpLayer pattern) and rejected it:
> always-registered preserves the mid-session add-source path
> (`tailor_setup_write_source_block` after the first source is
> configured) that the v7.5.0 multi-source coexistence deep-merge
> writer was designed to enable. Tool-list bloat (4 setup tools
> always visible on configured deployments) is the small cost; the
> alternative would force a Claude Desktop restart for every
> additional source.
>
> **Gates: ci-gate-runner SHIPPABLE** (1548/1548 pytest, 3
> scipy-conditional skips, ruff clean, 76/76 security probe, CLI
> smoke clean — 6 commands discoverable, hard-removed verbs absent).
> **mcp-protocol-auditor PROTOCOL OK** (40 new subprocess wire tests
> at `tests/test_serve_v8_wire_audit.py` — all 8 new tools verified
> end-to-end, SETUP_CONFIG_WRITE outcome stamping verified, PARAM_INVALID
> gate confirmed on the source-type allowlist). **reproducibility-
> provenance-auditor CLEAN** (every touched in-scope file HOLDS;
> W5 AST contract updated 31→40 audit-record sites + 6→9 _meta
> stamping sites; SetupLayer routes through `pilot._write_user_config`
> canonical seam — no hand-rolled writer). **phi-irb-risk-reviewer
> VIOLATION + 2 WATCH → CLOSED** (Lens 6 retention CLOSED via ADR 0040
> § Amendment retention contract + research-framing.md fifth
> retention category; WATCH-1 Lens 1 Safe Harbor CLOSED via
> `_redact_home()` extension to SetupLayer wire surface; WATCH-2 Lens
> 2 consent re-prompt DEFERRED with named reversal condition).
> **red-team-reviewer OBJECTION (MEDIUM) → CLOSED** (walkthrough
> section 1 worked_example used invalid `metric="peak_force_N"` not
> in COHORT_METRICS, omitted required `value_column`, and carried
> fabricated std values 12.1/15.4 against real fixture stds 6.62/6.46
> — closed via valid `force_cohort_summary` params + wire-verified
> stats + AST-class regression guard test that asserts the
> worked_example would actually succeed if called). **coverage-
> criticality-mapper REGRESSION → CLOSED** (26 new tests at
> `tests/framework/test_setup_coverage_gaps.py` covering every
> CRITICAL + HIGH uncovered path including bounded-write defense-in-
> depth allowlist violation, REDCap source-block branch, all detector
> edge branches, register_*_layer collision detection, fitting-room
> scaffold + index_vault success + force + exception paths).
> **adr-weigher PASS** on ADR 0040 against all five criteria.
> **cue-card-rehearsal-auditor NOT TRIGGERED** (no CUE_CARD.md or
> ToolDefinition schema changes affecting an existing cue card — the
> 8 new tools are MCP-tool surfaces not yet on the bundled HIP Lab
> cue card). **recipient-install-validator SKIPPED** per v6.11.x
> falsification precedent.
>
> **Red-team-earning-its-keep moment.** Four upstream specialists
> (mcp-protocol-auditor, reproducibility-provenance-auditor, phi-irb-
> risk-reviewer, coverage-criticality-mapper) all returned confident
> verdicts before red-team-reviewer fired. Red-team caught a real
> defect none of the four named: the walkthrough section 1 worked-
> example was structurally broken on the wire (invalid params +
> fabricated stats) while pytest was green because the test envelope
> shape was correct. Same v7.3.4 D1 + audit-log-over-promise defect
> class — a load-bearing analytical claim broken on the wire while
> automated gates were green because the gates measure envelope
> correctness, not payload semantics. AST-class regression guard at
> `tests/framework/test_setup_coverage_gaps.py::test_walkthrough_section_1_worked_example_is_callable_against_real_tool`
> prevents the regression: it imports `COHORT_METRICS` from the actual
> tool and asserts the worked-example params are valid against the
> real schema. ADR 0010 (adversarial pairing) demonstrably earning its
> keep again.
>
> **Net-new test count: 128.** 62 initial layer tests (test_setup_layer,
> test_setup_source_allowlist, test_walkthrough_layer,
> test_fitting_room_layer) + 40 subprocess wire tests
> (test_serve_v8_wire_audit, added during mcp-protocol-auditor's
> audit) + 26 coverage-gap closers (test_setup_coverage_gaps, added
> during the red-team + coverage release-pass).
>
> **What did not change.** No router-pipeline / security-pipeline /
> child / vault-layer architecture changes beyond the three new
> framework-tier register hooks + three dispatch methods + the new
> `SETUP_CONFIG_WRITE` audit outcome value. Pilot CLI surface
> (`tailor pilot`) preserved unchanged. wizard.py preserved
> (load-bearing for Strava OAuth). fitting_room.py + demo/runner.py
> preserved as library modules (CLI dispatch deleted; pure helpers
> remain and are imported by the new MCP layers + the example
> scripts). The L1 wizard CLI surface is the operator/RSE path; the
> SetupLayer MCP surface adds a parallel recipient path. Both paths
> converge on the same `pilot._write_user_config` canonical writer.

> **v7.6.0 (2026-05-19)** — ADR 0038 structural sweep ships. Closes
> the data-source-agnostic vault-layer commitment that v7.3.4 partial-
> closed and v7.4.0 / v7.5.0 deferred. Minor bump: new
> `ChildMCP.vault_note_kinds` optional property + `value_column`
> parameter rename on `csv_cohort_summary` and `csv_force_decline`
> are public-API additions. The rename ships **without a deprecation
> alias** under the 2026-05-19 → 2026-05-20 pre-outreach window
> (recipient population for v7.4.0 / v7.5.0 cohort tools as of
> 2026-05-19 is the boss + Phase 0 family-testers; the v7.3.4
> `group_field → group_by` no-alias precedent applies cleanly until
> tomorrow's colleague outreach). If the merge slips past 2026-05-20,
> a v7.6.1 patch adds the alias per ADR 0038 § Amendment 2026-05-19
> § "Sub-item 6 — timing".
>
> **`ChildMCP.vault_note_kinds` — option (a) of the contract-surface
> menu (ADR 0038 § Amendment 2026-05-19, sub-item 1).** New optional
> property on the `ChildMCP` ABC defaulting to `()`. The running child
> overrides to return `("run_report", "trend_report", "compare_runs")`
> — the worked example of declaring child-specific vault note kinds.
> Other shipped children (csv_dir, matlab_file, redcap_file, force_csv,
> emg_csv, template) inherit the empty default without modification.
> `VaultLayer._compute_kind_metadata()` (new) walks
> `self._router._children` at `register_vault_layer()` time, unions
> child-declared kinds with the framework-tier base
> (`theme`, `moment`, `failure_mode`, `dashboard`, `snapshot`), and
> populates `self._allowed_kinds` + `self._kind_to_domain_map`. The
> hardcoded module-level `_ALLOWED_KINDS` tuple is replaced by
> `_FRAMEWORK_KIND_BASE` (framework-tier only). The module-level
> `_domain_for_kind` helper migrates to `VaultLayer._domain_for_kind`
> (instance method, consults the dynamic map). `param_schemas` for
> `vault_list_notes` / `vault_search_notes` now use
> `self._allowed_kinds` — the kind filter accepts any child-contributed
> kind without further code changes in the vault layer.
>
> **`value_column ↔ column` API parity reconciled.**
> `csv_cohort_summary` and `csv_force_decline` rename `column` →
> `value_column` to match `force_cohort_summary` / `emg_cohort_summary`
> (which use `value_column`). Param schema + handler + tool description
> + result envelope key all updated. The v7.3.4 D2 rename
> (`group_field → group_by`) closed half this asymmetry; v7.6.0 closes
> the other half. No alias per the timing argument above.
>
> **`vault_get_fitness_summary` deprecation hint lands.** The v6.0-era
> orientation tool gains a `DEPRECATED in v7.6.0` prefix in its
> ToolDefinition description + a one-shot `log.warning` on first call
> per VaultLayer instance. Audit row unchanged: normal
> `outcome="SUCCESS"` with `scrubber_id` threaded per the v7.3.1 all-
> call-sites-sweep rule — does NOT inherit ADR 0001 § Amendment
> 2026-05-18's CLI-helper carve-out (this is a router-tier audit
> surface, not a CLI helper). Removal target: future v7.7.x+ when
> BOTH conditions hold — (i) cue-card-rehearsal-auditor reports zero
> references across deployed cue cards, (ii) zero third-party children
> declare dependencies on the tool. Named-trigger pattern matches
> [ADR 0036](docs/adr/0036-matlab-child-scope-v72-only-with-deferred-hdf5.md)'s
> beachhead-lab condition; closes the indefinite-deferral failure
> shape ADR 0038's original § Alternatives named.
>
> **Internal helpers data-source-aware.**
> `_handle_fitness_summary`'s strava-remediation branch derives
> `strava_sync` / `strava_run_report` from `self._backfill_config`
> (new `sync_tool` key) with a generic fallback for non-running
> deployments. `_build_snapshot_payload`'s weekly running summary
> query is gated on `"run_report" in self._kind_to_domain_map` —
> closes the integration-auditor's I2 finding. The remaining
> running-domain queries in `_handle_fitness_summary` and
> `_find_run_note_by_activity_id` are correctly running-specific by
> contract (the former counts running notes to detect deployment
> shape; the latter resolves activity_ids that only running has);
> both are documented in the AST invariant test's allowlist.
>
> **Pre-implementation auditor pass — REVISE → PROCEED via amendment.**
> `integration-auditor --proposal-mode` on the initial v7.6.0 plan
> returned REVISE with 3 BLOCKING (B1 contract mechanism / B2 alias /
> B3 AST gate) + 4 IMPORTANT + 3 prior-decision conflicts. ADR 0038 §
> Amendment 2026-05-19 closed B1 (mechanism: option a), B2-timing
> (no alias on the 2026-05-19→2026-05-20 window), B3 (AST-class
> invariant test committed), I1 (deprecation-hint audit-row
> inheritance clarified), I4 (tighten direction; metric param already
> runtime-pinned to COHORT_METRICS on all three cohort tools — sweep
> ratification, no new constraint). Re-audit returned PROCEED with
> 3 carry-forward concerns (N1 build-your-own-child doc threading, N2
> AST-test allowlist precision, N3 removal-target named-trigger) —
> all three addressed in the implementation pass. N3 closed inline in
> the amendment with the cue-card-zero + zero-third-party-dependency
> trigger condition.
>
> **AST-class invariant test ships** (`tests/framework/vault/test_v76_vault_is_data_source_agnostic.py`).
> Parallel to v7.5.0's `test_user_config_json_write_sites_are_canonical`
> — walks `framework/vault/layer.py` AST and asserts (1) zero
> `domain="running"` keyword args outside an allowlist of structurally
> running-specific functions, (2) zero `strava_*` string literals
> outside `backfill_config`-derived sites, (3) `_ALLOWED_KINDS`
> module constant is gone (replaced by `_FRAMEWORK_KIND_BASE`), (4)
> module-level `_domain_for_kind` is gone (migrated to instance
> method). AST-class detection per the v7.3.2 W5 lesson — textual-
> window grep false-positives on adjacent comments and dict keys.
> Future regressions to v7.3.4-shape Strava coupling fail this test
> loudly rather than silently shipping.
>
> Net-new tests: AST invariant test + behavioral contract test
> covering default `vault_note_kinds`, RunningChild override,
> `_compute_kind_metadata` extension, dynamic `vault_list_notes`
> kind-schema, and one-shot deprecation log. Plus
> `tests/test_serve_v760_wire_audit.py` (21 wire tests, added by
> mcp-protocol-auditor as audit side effect). No router / security /
> child / CLI architecture changes beyond the new optional
> `ChildMCP.vault_note_kinds` property, `_compute_kind_metadata`
> registration hook, the cohort-tool API rename, and the
> `ParamValidator` D1 fix (3-line addition; see below). Minor bump.
>
> **mcp-protocol-auditor D1 closure — `ParamValidator.validate()`
> enforces `allowed_values` on scalar `str` types.** The auditor
> surfaced a pre-existing structural defect that v7.6.0's dynamic
> `_allowed_kinds` surface depended on: the validator enforced
> `allowed_values` only inside the `elif schema.type is list` branch,
> leaving every `ValidationSchema(type=str, allowed_values=[...])`
> site as a dead constraint. A `kind: "not_a_real_kind"` argument
> silently returned empty results instead of PARAM_INVALID. Fix:
> three lines added to the `elif schema.type is str` branch in
> `framework/security.py` reading `schema.allowed_values` and
> returning a validator error envelope on mismatch. Auditor's
> strict-xfail regression anchor at `tests/test_serve_v760_wire_audit.py::
> TestV2DynamicAllowedKinds::test_unknown_kind_rejected_param_invalid`
> flipped from XFAIL to PASS. Suite-wide impact: 1426/1426 pytest
> pass after the fix; no other test was silently passing because the
> constraint was dead. Audit-row outcome continues to record
> `outcome="PARAM_INVALID"` per `router.py:892`.
>
> **`→` → `--` ASCII fallback** in the deprecation hint description
> + stderr `log.warning` per the v6.10.1 cp1252 precedent. Prevents
> Windows recipient terminal-render corruption on the stderr surface
> that the `_make_cli_stdout_resilient()` shim doesn't cover.
>
> **Red-team OBJECTION (medium) → CLOSED.** `red-team-reviewer`
> caught what the four upstream specialists could not: the live
> operator-facing guide `docs/guides/local-llm-guardian.md:226`
> documented the worked example with the OLD `column:` parameter
> verbatim — a colleague following the published guide post-rename
> would hit PARAM_INVALID on the first cohort call. Same v6.9.1
> failure class the cue-card-rehearsal-auditor was promoted against,
> reached via the docs/guides surface (which the cue-card auditor's
> remit does not cover). Closed by a one-line edit to
> `docs/guides/local-llm-guardian.md:226` plus a forward-cite to
> ADR 0038 § Amendment 2026-05-19. Historical screenshot transcripts
> at `docs/diagnosis/captures/2026-05-09-*` preserved per the
> doc-truth principle. This is the ADR 0010 (adversarial pairing)
> earning-its-keep moment.
>
> **Gates: ci-gate-runner SHIPPABLE** (1426/1426 pytest, 3
> scipy-conditional skips, ruff clean, 76/76 security probe, CLI
> smoke clean — 9 commands discoverable). **mcp-protocol-auditor
> PROTOCOL OK** post-D1 closure (21 wire tests in
> `test_serve_v760_wire_audit.py`; D1 regression anchor flipped to
> PASS). **reproducibility-provenance-auditor CLEAN** (every touched
> file HOLDS against ADRs 0001 / 0002 / 0008 / 0009; two soft BORDER
> NOTES, one closed inline). **cue-card-rehearsal-auditor REHEARSAL
> OK** (all 5 tool-call prompts PASS; non-running deployment
> simulation confirms `_compute_kind_metadata()` correctly excludes
> running-child kinds when no running child registers). **red-team-
> reviewer OBJECTION (medium) → CLOSED** (`docs/guides/local-llm-
> guardian.md:226` rename closure + forward-cite). **recipient-install-
> validator SKIPPED** per v6.11.x falsification precedent (no
> `_fixtures/`, no `pyproject.toml` package-data globs, no `__main__.py`
> install-path logic touched beyond the additive `sync_tool` key in
> `backfill_config`).

> **v7.5.0 (2026-05-18)** — `tailor pilot --source={csv,matlab,redcap}`
> dispatch + multi-source coexistence + L1/L2 onboarding-surface split.
> First product surface in Tailor's history where the external researcher
> population is the explicit primary audience: a PI with mixed-modal
> data (biometric CSVs + REDCap survey + MATLAB force-plate exports)
> can now configure all three through the same wizard, one command per
> source, no manual JSON editing, no clobbering of sibling source
> blocks on re-runs. Targets the 2026-05-16 colleague/peer outreach
> authorization. Minor bump: new `--source` flag is a public-API
> addition; CSV path is the v6.2.1 backward-compat default; no shipped
> CLI surface breaks.
>
> **F1 deep-merge `_write_user_config` — multi-source coexistence by
> construction.** The proposal-mode auditor's catastrophic-misbehaviour-
> path was a researcher running `tailor pilot --source=matlab` two
> weeks after `tailor pilot --source=csv` and losing their `csv_dir`
> block — the pre-v7.5 full-overwrite writer would have eaten it. The
> v7.5 writer reads existing config with `utf-8-sig` (BOM-safe per the
> v6.9.2 precedent across 12 child sites), sets only the named source
> key, atomic tmp-then-replace. The `FileExistsError`-on-overwrite
> prompt shifted from "any user_config.json content present" to "this
> specific source_key conflicts" — sibling blocks survive by
> construction either way. AST-class all-call-sites-sweep regression
> test at `tests/test_pilot_wizard.py::test_user_config_json_write_sites_are_canonical`
> enforces the contract: any future user_config.json writer must
> either route through `pilot._write_user_config` (the canonical
> deep-merge seam) or appear in `KNOWN_WRITERS` with a citation
> explaining why fresh-write is correct for the target. Three known
> writers documented: `pilot._write_user_config` (deep-merge seam),
> `fitting_room._write_user_config` (post-rmtree demo-dir scope), and
> `runner._write_demo_user_config` (tempdir scope). The predicate is
> AST-class — write-target resolution through local + module name
> graphs — per the v7.3.2 W5 textual-window false-positive lesson;
> grep-class detection would false-positive on `cmd_serve` (which
> READS user_config.json while writing elsewhere).
>
> **`tailor pilot --source={csv,matlab,redcap}` argparse dispatch.**
> Backward-compat: no-arg `tailor pilot` keeps the v6.2.1 CSV-default
> behaviour. The MATLAB handler reuses
> [ADR 0036](docs/adr/0036-matlab-child-scope-v72-only-with-deferred-hdf5.md)'s
> scope-bound posture: lazy `scipy.io` import surfaces a friendly
> install hint and exits rc=1 on missing scipy (F2 closure — the
> v6.10.2 silent-failure trap class the proposal-mode auditor named);
> HDF5 magic-byte check on every `.mat` file BEFORE any
> `scipy.io.loadmat` call (F6 closure — v7.3 files get rejected
> inline with the ADR 0036 remediation hint instead of crashing
> variable enumeration with `NotImplementedError`); variable
> inventory across the first 32 parseable files drives an optional
> `variable_filter` prompt. The REDCap handler reuses
> `RedcapPHIScrubber.fingerprint` directly (F4 closure — no parallel
> canonical-form implementation in the wizard that could drift from
> the production seam) and displays the full per-field identifier
> listing at first config (boss decision 2026-05-18 — compact
> summary considered + rejected; first impression IS the trust root,
> and a flag-flip attack on `project_metadata.csv` must be visible
> at the moment of operator confirmation). `unknown_field_allowlist`
> defaults to empty (fail-closed per
> [ADR 0037](docs/adr/0037-redcap-child-scope-export-directory-only-with-deferred-live-api.md));
> wizard prose makes the fail-closed posture explicit (F7).
>
> **New `ATTEST_INITIAL` audit outcome — distinct from `REATTEST`.**
> First-config attestation has no cached fingerprint to compare
> against, so stretching `REATTEST`'s semantics (which is the
> drift-detected re-attestation ritual at `__main__.py:cmd_redcap_reattest`)
> would break audit-log honesty per ADR 0001. F5 closure introduces
> `ATTEST_INITIAL` as the operator-action outcome for first
> configuration. The wizard's `_write_attest_initial_audit_row`
> routes through `AuditLog.record()` (NOT a hand-rolled INSERT —
> v7.3.2 F-A precedent honored), threading
> `child_scrubber_id="redcap_metadata_flags"` and
> `source_metadata_fingerprint=<sha256>` so an IRB reviewer
> querying audit.db can reconstruct the trust-root state in effect
> at first configuration via
> `WHERE outcome='ATTEST_INITIAL' AND domain='redcap_file'`. The
> `audit_query` tool's outcome-filter description gains
> `ATTEST_INITIAL` in its common-values list; the schema
> validation is unconstrained `type=str` so the new value flows
> through without an allowlist amendment.
>
> **L1 / L2 product-split codified.** ChildMCP onboarding now has
> two distinct product surfaces: configured ingest of a shipped
> source axis (the L1 wizard, researcher-accessible) vs. authoring
> a new source axis (the L2 path, RSE-accessible). New
> `docs/guides/build-your-own-child.md` walks an RSE through copy →
> rename → implement the four abstract surfaces → register; CLAUDE.md
> § "Adding a New ChildMCP" updated with two paragraphs naming the
> split + the rejected alternatives. **Wizard-child MCP surface**
> deferred behind a reversal condition (first institutional ask for
> "add a source mid-conversation" ergonomics in an already-running
> install) — fails chicken-and-egg on first install and conflicts
> with [ADR 0022 § Out of scope](docs/adr/0022-local-llm-guardian.md)
> conductor-mode-deferred. **LocalLLMLayer-folded wizard** deferred
> behind a stricter reversal condition (`OracleResponse` schema
> extended to model file-mutation actions AND a 7B+ model
> demonstrably outperforms hand-coded heuristics on cross-source
> pattern matching) — wizard work is configuration authoring, a
> third category beyond numerical claims and analytical prose that
> the schema-as-contract invariant from ADR 0022 does not model.
> The boss adopted the (b) "two CLAUDE.md paragraphs with the
> ADR 0022 conflict argument as load-bearing WHY" answer per
> `adr-weigher`'s DEFER-NEEDS-BOSS-INPUT recommendation —
> reproposal-prevention preserved without ADR ceremony for a
> structural commitment that's already de facto in the codebase.
>
> **Gate composition pre-ship.** `integration-auditor --proposal-mode`
> REVISE (3 BLOCKING — F1 deep-merge, F2 lazy scipy, F3 utf-8-sig —
> all closed pre-implementation; 5 IMPORTANT including F4 scrubber
> reuse / F5 ATTEST_INITIAL semantics / F6 HDF5 pre-check / F7
> fail-closed prose / F8 smoke scope-cut — all addressed in code;
> 3 prior-decision conflicts addressed inline — **C1** kept the
> L1/L2 ADR out of this PR via a separate `adr-weigher` dispatch;
> **C2** verified the wizard does not read or modify the
> `local_llm` block in user_config.json, preserving the ADR 0022
> conductor-mode-deferred surface, and reused that exact argument
> as the load-bearing WHY for the L1/L2 split; **C3**
> recipient-install-validator posture resolved as the hybrid
> self-validation per the boss decision 2026-05-18 — fresh-venv
> install smoke this end, fresh-user-account install boss's end).
> `adr-weigher` DEFER-NEEDS-BOSS-INPUT on the L1/L2 product-split
> ADR candidate; boss chose option (b) CLAUDE.md paragraphs. **ci-
> gate-runner SHIPPABLE after a fix-and-rerun**: first pass returned
> BLOCKED on 3 ruff I001 import-order violations (one in the new
> ATTEST_INITIAL test, two pre-existing in `tests/smoke/` and
> `tests/test_serve_v740_wire_audit.py`); closed via
> `ruff check --fix`; re-run clean (1380/1380 pytest, 3
> scipy-conditional skips, ruff clean on src/+tests/, 76/76
> security probe, CLI smoke clean — `--source` flag visible,
> `--source=junk` cleanly rc=2, all 8 commands discoverable).
> **Fresh-venv install smoke (my end of C3) SHIPPABLE**: wheel at
> `dist/tailor_mcp-7.4.0-py3-none-any.whl` (filename version label
> not yet bumped — that's `release-shipper`'s job; the content is
> v7.5 feature surface) installed cleanly into a fresh venv in a
> tempdir; `tailor --help` enumerates all 8 commands;
> `tailor pilot --help` shows the new `--source` flag with the
> updated multi-source summary line; `tailor pilot --source=junk`
> exits rc=2 with argparse validation error. Boss's end of C3
> (fresh-user-account install + Claude Desktop registration on his
> own machine) NOT YET DONE — pending after this banner ships.
> **mcp-protocol-auditor PROTOCOL OK** (15 new wire tests in
> `tests/test_serve_v750_wire_audit.py` covering B1 ATTEST_INITIAL
> outcome filter + B2 row shape on the wire + B3 multi-source
> tools/list + B4 deep-merge preservation + B5 _meta correctness +
> B6 v7.4.0 regression; 3 non-blocking BORDER NOTES — version label
> on the wheel not yet bumped to 7.5.0, a Windows SQLite WAL
> teardown pattern worth replicating in
> `tests/_mcp_client.py:spawn_server`, and one assertion in B2 that
> reads awkwardly under empty-rows). **reproducibility-
> provenance-auditor CLEAN** (every touched file HOLDS against
> ADRs 0001 / 0002 / 0003 § Amendment 2026-05-15 / 0008 / 0009;
> NEEDS REVIEW on `audit.close()` discipline closed in code via
> `try/finally` mirroring the `__main__.py:cmd_redcap_reattest`
> sibling). **phi-irb-risk-reviewer WATCH** with WATCH-1
> (`scrubber_id` hardcode) closed in code
> (`_write_attest_initial_audit_row` now queries
> `PHIScrubber().scrubber_id` dynamically, mirroring the
> `__main__.py:cmd_redcap_reattest` sibling). **researcher-utility-
> reviewer ALIGNED** (PI LOAD-BEARING HIGH, Analyst/RSE
> LOAD-BEARING MEDIUM, IRB LOAD-BEARING HIGH; one BORDER on the
> `docs/guides/multi-subject-pilot.md:189-205` "What's still your
> responsibility" section being pre-v7.5 + not mentioning that
> ATTEST_INITIAL materially improves the IRB story — queued as
> doc-debt for the next doc-pass, not ship-blocking).
>
> **Red-team-reviewer caught a structural defect all five upstream
> specialists missed — OBJECTION (medium) closed pre-ship.** The
> 15 new wire tests in `tests/test_serve_v750_wire_audit.py`
> pre-seeded `ATTEST_INITIAL` rows via a test-local `_seed_audit_row`
> helper that hardcoded `scrubber_id="noop"` — the literal value
> the WATCH-1 fix was meant to eliminate. A future regression that
> re-hardcoded `"noop"` in `pilot._write_attest_initial_audit_row`
> would still pass every B1/B2 wire test because the test bypassed
> pilot.py entirely. **Same structural class as v7.3.2's F-F W5
> textual-window false-positive** — tests pass for adjacent reasons
> (the seed helper happens to produce the same string the WATCH-1
> fix produces under the default scrubber) rather than because the
> production code path is exercised. Closure: new B7 integration
> test class (`TestB7PilotWriteAttestInitialEndToEnd`) calls
> `pilot._write_attest_initial_audit_row` directly via a
> `pre_seed_fn` hook, queries `audit_query` on the wire, and asserts
> the row's `scrubber_id == PHIScrubber().scrubber_id` dynamically.
> A future regression that re-hardcodes `"noop"` would now break
> this test under any institutional subclass of the framework
> scrubber. This is the ADR 0010 (adversarial pairing) earning-its-
> keep moment that v7.3.2 W5, v7.3.3 F-G, and v6.10.4 named: the
> dissent layer catches the failure mode the same model produces
> in its confirmation-shaped craft persona.
>
> **WATCH-3 closed in this release via ADR 0001 § Amendment
> 2026-05-18 (NEW).** The wizard's audit-row-write failure policy
> (continue + stderr warn on `_write_attest_initial_audit_row`
> failure) sat in direct tension with ADR 0001 § Negative
> consequences "a missing row is worse than a failed call." Boss
> chose option (a) — ratify the wizard exemption — over option (b)
> refuse to commit a config the wizard could not audit. The
> amendment codifies a narrow five-precondition CLI-helper exemption
> applying ONLY to operator-action provenance rows (not router-tier
> dispatch audits, not child execute() writes, not participant-data
> audits): (1) CLI subcommand helper, (2) provenance-only row, (3)
> the helper's primary purpose is something else (config write,
> Claude Desktop registration, attestation ritual), (4) operator-
> reachable recovery path (re-running the subcommand writes a fresh
> row), (5) plain-language stderr surface on failure. Reversal
> condition named: if a second non-tool-call audit site adopts the
> pattern, promote to a framework primitive (`AuditLog.record_best_effort()`
> or similar) — same shape as ADR 0013's
> "third-domain-promotes-to-framework-registry" precedent.
>
> **Deferred WATCH finding (named with reversal condition; not
> ship-blocker).** WATCH-2: re-running `tailor pilot --source=redcap`
> against a different directory writes a second `ATTEST_INITIAL` row
> rather than a `REATTEST` — phi-irb classified as institutional-
> clarification territory. An IRB reviewer reconstructing
> trust-root transitions cannot tell from outcome alone whether
> row N+1 was a clean re-install (legitimate) or a tampered swap
> (incident). Deferred to v7.5.1; reversal condition is the first
> real-world deployment that re-configures REDCap against a new
> export directory and surfaces the ambiguity.
>
> **What did not change.** No router-pipeline / security-pipeline /
> child / vault-layer / CLI architecture changes beyond the
> argparse dispatch and the new audit-outcome value. No new ADRs
> (per the (b) two-CLAUDE.md-paragraphs decision); no new
> framework-tier components; no new ChildMCP subclasses; no schema
> changes (`audit_query`'s outcome filter accepted arbitrary
> strings before this release and still does). The L1 wizard
> extension is product-surface work atop existing children, not
> framework deepening. Net-new tests: 23 in `test_pilot_wizard.py`
> (F1 multi-source helper + dispatch + MATLAB scipy-missing /
> HDF5 magic-byte / scan partition + REDCap fingerprint reuse /
> ATTEST_INITIAL audit row / completion-field detection / BOM
> round-trip + AST-class all-call-sites-sweep) + 16 in
> `test_serve_v750_wire_audit.py` (15 from the
> mcp-protocol-auditor side-effect + 1 in the new B7 integration
> class closing red-team's OBJECTION). Patch quartet shape
> familiar from v7.3.x: each ship-blocker found by a pre-implementation
> gate; the implementation closed it before the next gate fired;
> the red-team gate caught the one all the others missed.
> Includes pending governance edits per L1/L2 onboarding split (ADR 0022 conductor-mode conflict + CLAUDE.md paragraph additions) and README.md pilot wizard table updates (v7.5.0 --source dispatch docs).

> **v7.4.0 (2026-05-16)** — New framework-tier `audit_query` layer: the
> audit log is now LLM-queryable under a B1 column allowlist (ADR 0039).
> Closes the v7.3.4-banner-deferred audit-log-over-promise gap — the
> fitting-room banner prompt "Show me what just happened in the audit
> log" now has an MCP tool to land on.
>
> **New framework-tier layer — `AuditQueryLayer`.** Fourth framework-tier
> layer (parallel to VaultLayer / LocalLLMLayer / SetupHelpLayer). Single
> MCP tool `audit_query` surfaces structured columns from `audit_log`
> under a 12-column + 1-derived allowlist: `id`, `timestamp`, `domain`,
> `tool_name`, `tier`, `outcome`, `subject_id`, `latency_ms`,
> `prompt_tokens`, `completion_tokens`, `scrubber_id`,
> `child_scrubber_id`, plus `has_error` (derived boolean — never exposes
> raw `error` text or raw `params` content). `AuditLog.query()` uses
> an explicit column SELECT, never `SELECT *`, with a `limit=100` hard
> cap and `order by id desc` default. Column filtering, outcome
> filtering, domain filtering, subject_id filtering, and time-range
> filtering are all supported. The layer bypasses biosensor-tier gates
> (consent, cost, circuit breaker, PHI scrub) per the framework-tier
> pattern; param validation and audit still apply. Registered in
> `__main__.py cmd_serve()` alongside VaultLayer and LocalLLMLayer.
>
> **ADR 0039 (NEW, Accepted).** Codifies "audit log is LLM-queryable
> under column allowlist" as a structural invariant. B1 allowlist
> construction argument: the audit log exists for reproducibility and
> IRB review; the allowlist enables the intended surface while the
> column exclusion of raw `params` and raw `error` content prevents
> re-identification via query parameters and prevents error-message
> egress. Cites ADRs 0001 / 0002 / 0003 / 0009 / 0012 / 0022.
>
> **ADR 0012 § Amendment v7.4.0.** The vault-PHI-scrubber-bypass doc
> gains a fourth framework-tier layer entry: AuditQueryLayer joins
> VaultLayer / LocalLLMLayer / SetupHelpLayer as a bypass-design
> justified by the same structural argument — the audit log is the
> analyst's Ledger, not participant biometric data; param validation
> and audit apply; PHI-scrub, consent, cost, and circuit-breaker do
> not.
>
> **Gates: ci-gate-runner SHIPPABLE** (1360/1360 pytest, 3
> scipy-conditional skips, ruff clean, 76/76 security probe, CLI smoke
> clean — 8 commands discoverable). **mcp-protocol-auditor TRIGGERED**
> (router.py + audit.py + __main__.py changes; W5 AST-class contract
> test extended from 28→31 audit-record sites and 5→6 `_meta` stamping
> sites; tool count updated 49→50 default / 70→71 fitting-room /
> 57→58 multiclient scipy-absent; 10 subprocess wire tests in
> `tests/test_serve_v740_wire_audit.py`). **mcp-protocol-auditor
> TRIGGERED — attest**: `--gates-confirmed="mcp-protocol-auditor:PROTOCOL
> OK"` (wire tests pass; allowlist column filtering verified on the
> wire; `has_error` derived field verified; `limit=100` cap verified;
> raw `params`/`error` columns verified absent from response).
> **cue-card-rehearsal-auditor NOT TRIGGERED** (no `CUE_CARD.md` or
> `ToolDefinition` schema changes in the v7.3.4 cue card; `audit_query`
> is not yet on the cue card — queued for the cue-card sweep in the
> next recipient-facing session). **recipient-install-validator
> TRIGGERED** (`__main__.py` modified — new `register_audit_query_layer`
> call). **recipient-install-validator SKIPPED** per v6.11.x falsification
> precedent: the `__main__.py` change is a single `register_audit_query_layer()`
> call at the serve-registration site — the same registration pattern
> as VaultLayer / LocalLLMLayer / SetupHelpLayer; no new install-path
> logic, no new failure class. The four prior registration calls are
> empirically clean on Windows + macOS (2026-05-12 + 2026-05-16
> recipient installs). **integration-auditor --proposal-mode REVISE**
> (pre-implementation: 3 BLOCKING + 4 IMPORTANT + 3 conflicts; B1
> allowlist design closes BLOCKING-1/2 by construction; BLOCKING-3
> closed by `limit=100` hard cap; all IMPORTANT findings addressed
> before implementation). **adr-weigher PASS** on all 5 criteria.
> **red-team-reviewer NO OBJECTION FOUND** across 6 probed failure
> modes. Net-new tests: 42 (32 unit in
> `tests/framework/test_v74_audit_query.py` + 10 subprocess wire in
> `tests/test_serve_v740_wire_audit.py`). Minor bump: new `audit_query`
> MCP tool is a public API addition (tool surface 49 → 50 on default
> config).

> **v7.3.4 (2026-05-16)** — Post-first-real-recipient-run hardening patch.
> 2026-05-16 first outside-recipient walkthrough (Windows + Claude Desktop,
> non-technical friend) produced 5 findings. Scope escalated through four
> shapes over the course of the session: A (narrow S004 fix) → Option 2
> (Senefeld-ready expansion) → γ (scope-box: meeting flexes, ship-quality
> binds) → Option B (AI-economics demonstration via configurable
> `cost_threshold`). Patch bump: all additions are additive (new operator-
> configurable default, new bundled fixture, new ADR Proposed). No public API
> breaks. Matches the v7.3.1 / v7.3.2 / v7.3.3 patch-bump precedent for
> observability + recipient-experience hardening.
>
> **Pre-implementation gates surfaced ship-blockers the original plan missed —
> again.** This is the fourth consecutive v7.3.x release where
> proposal-mode / wire / cue-card gates returned findings the pytest suite
> and ruff were structurally unable to see. `integration-auditor
> --proposal-mode` returned REVISE with **F1 + F3 BLOCKING** + 5 IMPORTANT +
> 6 prior-decision-conflicts: F3 caught a one-session illusion — the seeded
> `snapshot.md` delivers the orientation wow on session 1, but the next
> `vault_generate_snapshot` call overwrites it with `*(No recent run data.)*`
> Strava-shaped output, regressing the demo to the original failure shape on
> session 2. F1 caught that `_infer_note_type` classified bare `snapshot.md`
> as `note_type="unknown"`, making the fixture un-indexable. Both blocking
> findings were structural: no unit test exercises the cascade
> rescan → kind-filter → fixture read that a real recipient would follow.
> `mcp-protocol-auditor` wire returned **DEFECTS FOUND**: D1 — the cohort
> thesis silently returned `null` for every fatigue metric on bundled HIP Lab
> subjects because float-seconds timestamps (the fixture format) were not
> handled in `_extract_timestamps`; the demo's load-bearing analytical claim
> was broken on the wire while pytest was green because unit tests construct
> datetime fixtures by hand. D2 — `force_cohort_summary` used `group_field`
> while `csv_cohort_summary`'s sibling parameter is `group_by`, an API parity
> break that would fail LLM inference. `cue-card-rehearsal-auditor` returned
> **BLOCKED** on D5 (`value_column` description had no literal-header
> example), D6 (`SUBJECT_ID_PARAM_DOC` lacked `'S001'`/`'S004'` examples and
> overclaimed "does not filter data" for vault tools per ADR 0009), D7
> (`group_by` enumerated only `'sex'` missing the `'group'` axis). All
> ship-blockers closed in the implementation pass.
>
> **Cohort thesis hot path — D1 + D1-companion.** `_extract_timestamps` in
> both `force_csv/child.py` and `emg_csv/child.py` now falls back to
> float-seconds offset when no ISO-datetime column is found, matching the
> actual format of the bundled 100 Hz HIP Lab fixtures. Wire-verified:
> F=65.3 N mean, M=87.6 N mean, S004 peak=229 N / `time_to_50pct_drop_s`
> non-null on `metric=time_to_50pct_drop_s`. A companion key-mismatch
> (handler read `decline_pct` but the pure function returned
> `decline_pct_total`) surfaced during D1 wire verification and was closed
> in the same pass; S004 now returns `decline_pct=76.1%`.
>
> **API parity — D2 rename.** `force_cohort_summary` + `emg_cohort_summary`
> parameter renamed `group_field` → `group_by` across ToolDefinition,
> param_schema, handler, and result-dict key to match `csv_cohort_summary`.
> An LLM that has seen `csv_cohort_summary`'s schema now infers the correct
> parameter name on the first call across all three cohort tools. The
> `value_column` ↔ `column` asymmetry across the same three tools is
> acknowledged but deferred — that sweep is a wider refactor; v7.4.0 queue.
>
> **Vault layer de-Strava — F3 closure.** `_handle_fitness_summary` no longer
> returns `*(No recent run data.)*` on HIP Lab deployments; the Strava-specific
> Weekly Summary section in `renderer.py` is now conditional on there actually
> being running data. `_infer_note_type` in `rescan.py` maps `snapshot.md` →
> `"snapshot"` kind, and `_ALLOWED_KINDS` + the `vault_list_notes` tool
> description were both updated to include `"snapshot"`. `vault-smoke-validator`
> surfaced the `_ALLOWED_KINDS` gap as a kind-filter inconsistency during the
> release pass; closed in the same pass. Together these three changes make the
> vault layer data-source-agnostic on the demo hot path — the structural
> commitment [ADR 0038](docs/adr/0038-vault-layer-is-data-source-agnostic.md)
> (Proposed) codifies for v7.4.0's full sweep.
>
> **Bundled `snapshot.md` — orientation fixture.** A `snapshot.md` pre-seeded
> under `src/tailor/_fixtures/hip_lab_demo_realistic/vault/` ships in the
> wheel. A recipient's first session opens with a structured orientation:
> vault health, open themes, active analytical questions, and a "## Token cost
> shape" section with wire-audit-verified numbers (Tier 1 ~310 tokens · Tier 2
> ~6,750 · Tier 3 ~50,000 actual / ~24,000 pre-execution estimate). The
> fixture honors the ADR 0024 synthetic-by-construction precondition: no real
> participant data, no real researcher identities. A `regenerate-warning`
> banner in the `tailor fitting-room` success output tells recipients that
> re-running `vault_generate_snapshot` will overwrite the seeded orientation —
> the structural lesson from F3.
>
> **Option B — AI-economics demonstration (ADR 0029).** Pre-implementation
> tier-escalation wire audit confirmed the [ADR 0029](docs/adr/0029-token-reduction-as-analytical-quality.md)
> claim is empirically real on the bundled fixtures (164× token lift across
> the tier ladder) but the framework-default `cost_threshold=35_000` would not
> fire on the bundled 60s fixtures (Tier-3 pre-execution estimate ~24k < 35k
> threshold). `cost_threshold` is now operator-configurable from
> `user_config.json` with the `35_000` default preserved so existing
> deployments are behaviourally unchanged; the `tailor fitting-room` scaffold
> writes `cost_threshold: 15000` so the gate fires demonstrably on bundled
> fixtures. A fifth banner prompt ("Step me through the tier levels for subject
> four — what does each one cost?") and the new "## Token cost shape" section
> in `snapshot.md` ground the recipient's first impression in audit-verified
> numbers rather than aspirational framing. The `CostEstimate.alternative_
> description` ("force_downsampled (interval=10) → ~90% cheaper") surfaces
> through the ADR 0004 `LLMInstruction` envelope when the recipient probes
> Tier 3. A cost-estimator 2.1× under-estimate BORDER NOTE (estimate ~24k vs
> actual ~50k for one 60s subject at 100 Hz) is queued for v7.4.0
> calibration work — the gate fires at the right structural moment; the
> absolute accuracy is the quality-of-life follow-up.
>
> **Red-team caught an over-promise no other specialist could have named.**
> The fitting-room banner prompt "Show me what just happened in the audit log"
> had no MCP tool to land on — v7.3.4 has no `audit_query` tool; the audit
> log is accessible only via shell `sqlite3` or the `tailor status` CLI.
> `red-team-reviewer` named the aspirational framing as a medium OBJECTION
> post-implementation: the recipient who tries that prompt gets a confused LLM
> or a fabricated response, the exact failure class v7.3.x is named against.
> Closure: banner prompt reworded to "Show me the recent moments in the vault"
> (callable via `vault_list_moments`); `snapshot.md`'s audit-log section
> softened to acknowledge the MCP-callable audit query is v7.4.0 work; the
> queue carries the new `audit_query` tool as the top v7.4.0 item. Same
> ADR 0010 adversarial-pairing earning-its-keep moment the v7.3.3, v7.3.2,
> and v7.3.1 banners named: the dissent layer catches the failure mode the
> confirmation-shaped craft persona produces.
>
> **Schema description sweeps (D5, D6, D7, and SUBJECT_ID_PARAM_DOC).**
> `value_column` in `force_csv` and `emg_csv` tool descriptions now names
> literal column headers ("force", "envelope") so a recipient can read
> the schema and know what to type without opening the CSV. `group_by`
> description enumerates both `'sex'` and `'group'`. `SUBJECT_ID_PARAM_DOC`
> carries `'S001'`/`'S004'` literal examples and distinguishes biosensor-tier
> (audit-log scoping only; does not filter source data) from vault-tier
> (actively filters per ADR 0009 subject keying) to close the ADR 0009
> semantic drift the auditor named.
>
> **Recipient-ergonomics.** `README.md` Prerequisites section gains a per-OS
> one-liner table (PowerShell `irm`, winget, macOS/Linux curl) addressing the
> `uv` discovery friction the 2026-05-16 recipient hit. `tailor fitting-room`
> success banner reshaped: a single "Next step" clause leads, three
> science-shaped prompts follow, paths demoted to a labeled "Files & locations
> (for reference)" block so the initial impression is a prompt, not a menu.
>
> **ADR-0038 (Proposed) lands in this PR.** Codifies "vault layer is
> data-source-agnostic" as a structural invariant — the vault layer must not
> assume a running child is present or that subjects are athletes. v7.3.4
> ships partial closure (demo hot path de-Strava); v7.4.0 ships the full
> structural sweep (residual `_kind_to_domain` mapper, backfill config
> defaults, competing orientation tools). ADR 0027 gains a forward-cite
> footer to ADR 0038.
>
> **Gates: ci-gate-runner SHIPPABLE** (1318/1318 pytest, 3 scipy-conditional
> skips, ruff clean, 76/76 security probe, CLI smoke). **mcp-protocol-auditor
> PROTOCOL OK** (120/120 wire tests; 1 BORDER NOTE — `value_column` ↔
> `column` API parity queued v7.4.0). **reproducibility-provenance-auditor
> CLEAN** (every touched file HOLDS against ADRs 0001/0002/0003/0008/0009;
> new fixed-epoch construction blessed deterministic; 3 cosmetic BORDER NOTES
> recorded). **vault-smoke-validator SHIPPABLE** (all blocks pass; kind-filter
> inconsistency surfaced + closed). **phi-irb-risk-reviewer NO RISK** across
> all 6 threat-model lenses; synthetic-by-construction precondition honored in
> snapshot prose. **researcher-utility-reviewer ALIGNED** (PI LOAD-BEARING
> HIGH; Analyst LOAD-BEARING MEDIUM; IRB LOAD-BEARING-modifying LOW).
> **coverage-criticality-mapper REGRESSION → CLOSED** (2 new tests — ISO-
> datetime success path + legacy Strava `total_running > 0` branch).
> **red-team-reviewer OBJECTION (medium) → CLOSED** (audit-log over-promise
> reworded). cue-card-rehearsal-auditor TRIGGERED → all findings CLOSED
> pre-implementation. recipient-install-validator SKIPPED per v6.11.x
> falsification precedent (fitting_room.py + __main__.py changes are banner /
> config-reader prose, not new install-path logic; no new failure class).
> Net-new tests: 21 in `tests/test_v734_demo_readiness.py`.

> **v7.3.3 (2026-05-15)** — Closes the two red-team BORDER NOTES the v7.3.2
> banner explicitly deferred. The patch lands as a *typed-exception-taxonomy*
> patch rather than two point-fixes — one structural argument covers both
> defects, future children inherit the seam without re-deciding it, and
> [ADR 0003 § Amendment 2026-05-15 § Typed-exception taxonomy](docs/adr/0003-phi-scrubber-seam.md)
> ratifies the contract. Patch bump per the v7.3.1 / v7.3.2 precedent
> (additive marker class on the public surface; no API breaks; the audit
> row's provenance kwargs are unchanged on both exempt and non-exempt paths).
>
> **The class of failure the patch names.** The framework's `CircuitBreaker`
> exists to back off external systems that are *flaky* (transient network /
> rate-limit / intermittent upstream errors). Some legitimate runtime
> conditions are structurally different: the system is fine; the operator
> must take an out-of-band action (re-attest a trust root, rotate a
> credential, edit a config) before subsequent calls can succeed. Counting
> these conditions toward the breaker is a *taxonomy mismatch* — it hides
> the recovery affordance behind a generic "Circuit open for redcap_file"
> envelope for the next 5 minutes, exactly the window the operator most
> needs guidance. The same shape at the *catching* side is v7.3.2's
> deferred B2: a blanket `except Exception:` in
> `RedcapFileChild._detect_fingerprint_mismatch` swallows both "metadata file
> became unreadable since boot" (legitimate runtime drift) and "scrubber
> constructor signature changed" (programmer bug) under the same handler.
>
> **New framework primitive — `framework.security.OperatorActionRequired`.**
> Marker exception class co-located with `CircuitBreaker` (the component
> whose behavior it modifies). Constructor takes a keyword-only
> `recovery_action: str` and validates it is non-empty + non-whitespace
> at construction time — a subclass author who cannot name a remediation
> command gets a `TypeError` at construction, not silent runtime defeat.
> The required attribute is the *misuse guard*: a child author who reaches
> for the class for an upstream-flaky exception (defeating the breaker for
> paths that legitimately need it) either provides a sensible recovery hint
> or cannot construct the exception at all. Exported from
> `framework/__init__.py`.
>
> **Router exemption — both dispatch sites (B1 closure).**
> Proposal-mode audit caught a critical defect in the v7.3.3 initial plan:
> the proposal named only the public `_dispatch` exception handler at
> `router.py:741`, missing the internal cross-child dispatch handler at
> `router.py:1294`. A future cross-child REDCap call (an oracle tool
> grounding a claim against REDCap data, a vault-backfill path) would
> have tripped the breaker through the internal path while the public path
> left it closed — breaker state would diverge depending on which dispatch
> path triggered the mismatch, the same v7.3.1 all-call-sites-sweep lesson
> reproducing. The shipped patch applies the symmetric
> `isinstance(e, OperatorActionRequired)` check at BOTH sites; the audit row
> still records `outcome=ERROR` / `outcome=ERROR_INTERNAL` with the full
> v7.3.1 W5 invariant kwargs (`subject_id`, `scrubber_id`,
> `child_scrubber_id`, `source_metadata_fingerprint`). The exemption is
> *breaker-only*, not *audit-only* — and a new T4 test inspects the SQLite
> audit row directly to verify this on every exempt path.
>
> **B2 closure — drop the defensive try/except entirely.** Proposal-mode
> audit caught a load-bearing reality check: the initial plan proposed to
> *narrow* the blanket `except Exception:` to `(OSError, ValueError,
> UnicodeDecodeError, csv.Error)`. But `RedcapPHIScrubber.__init__` swallows
> exactly those classes internally (`scrubber.py:148` — `_load_metadata`
> stores a warning and returns instead of raising); the constructor as
> shipped raises *essentially nothing* on bad input. The proposed narrowing
> would have been a no-op against current behavior — catching only the
> exception class that *must* propagate (`TypeError` from a future signature
> change), which was the defect's stated motivation. The shipped fix drops
> the try/except entirely; per CLAUDE.md guidance ("Don't add error
> handling, fallbacks, or validation for scenarios that can't happen"),
> defensive code around an exception surface that doesn't exist is
> precisely the complexity to avoid. A new
> `test_signature_change_in_scrubber_propagates_loudly` test simulates a
> future signature change via monkey-patch and asserts the `TypeError`
> propagates through `child.execute()` rather than being absorbed.
>
> **Reparenting — `RedcapMetadataFingerprintMismatch` is-a
> `OperatorActionRequired`.** The reparent carries
> `recovery_action="tailor redcap reattest"`; existing v7.3.2 invariants
> on the exception (both fingerprints in `str(exc)` for IRB queryability;
> "ADR 0003" + "tailor redcap reattest" substring presence; no absolute
> on-disk path in the error message) are preserved verbatim. A new T6
> test class locks the inheritance contract — a future refactor of the
> REDCap exception that drops the parent class fails this test loudly
> rather than silently unlinking the breaker exemption.
>
> **Proposal-mode audit returned REVISE on the initial plan — 2 BLOCKING +
> 4 IMPORTANT closed pre-implementation.** B1 (the dual-dispatch-site
> miss) and B2 (the no-op narrowing) named above. IMPORTANT findings
> addressed in code: I1 — marker-class placement (`framework/security.py`
> adjacent to `CircuitBreaker` for semantic honesty, vs the initial plan's
> `framework/interfaces.py`); I2 — three missing audit-invariant test
> cases (T4 exempt-path audit row outcome stamp + W5 kwarg threading + the
> implicit consent-revocation interaction documented as orthogonal in the
> ADR); I3 — `dispatch_internal`'s `outcome="ERROR_INTERNAL"` outcome
> shape covered in T3; I4 — `OperatorActionRequired` semantics named
> explicitly in the ADR amendment (breaker exemption is per-exception-
> instance, consent state is orthogonal, `subject_id` propagation
> unchanged). N1 / N2 ratified inline (patch-bump per v7.3.1 / v7.3.2
> precedent; reversal condition for OperatorActionRequiredTransient named
> in the amendment).
>
> **Most-likely-misbehaviour-path adopted into the design.** Proposal-mode
> auditor's strongest find: future child authors might misclassify
> *upstream-flaky* exceptions as `OperatorActionRequired`, defeating the
> breaker for paths that legitimately need it. The structural fix —
> require the marker class carry a `recovery_action: str` attribute that
> surfaces verbatim — makes misclassification a *loud constructor error*
> rather than a *silent runtime defeat*. Same shape as v7.3.2's W5
> AST-class contract test replacing the grep-class one: turn structural
> failure modes into compile/construct-time errors rather than runtime
> drift.
>
> **No public API breaks.** `OperatorActionRequired` is additive (existing
> exception subclasses inherit by changing their parent class; downstream
> `except Exception` catches still see the class). No new abstract
> methods, no new schema, no new audit columns, no router-pipeline /
> security-pipeline / vault-layer / CLI architecture changes beyond the
> additive marker class and the symmetric isinstance check at the two
> exception handlers.
>
> **Red-team-reviewer caught a fifth defect all four upstream specialists
> missed (F-G closure pre-ship).** Adversarial pairing on the four
> upstream confident verdicts returned **OBJECTION (medium)** on a real
> defect. The B1 wire test claimed "the LLM keeps seeing the recovery
> hint on every mismatch call" — but the test passes because the test
> harness runs a background daemon thread (`_start_stderr_drain`) that
> actively drains the server's stderr. Production (Claude Desktop) does
> not run that thread; after ~8 OperatorActionRequired events the
> Windows OS pipe buffer (4KB) fills with `log.info` lines, the server
> stalls on its next write, stdin blocks, and the recovery affordance
> disappears — the **exact failure class v7.3.3 was meant to close**,
> reachable by a different path. Same structural shape as v7.3.2's W5
> grep-vs-AST catch: the test passes because adjacent infrastructure
> provides the property under test, but production has no such
> infrastructure. **F-G closure**: silence the router's logger output
> entirely for `OperatorActionRequired` instances at both exception
> handlers — the audit row + wire envelope already carry the full event
> + recovery hint; the rotating file handler is the durable debug trace
> for everything else. Removing the byte source eliminates the failure
> mode rather than reducing its severity; a structurally stronger fix
> than the earlier "log.info instead of log.error + exc_info" mitigation.
> Two new T8 regression tests lock the closure: one asserts zero log
> records emitted on the OperatorActionRequired path across 10 calls
> (2× the cited 4KB / 500-byte threshold); a sibling test asserts the
> RuntimeError path still emits `log.error` to guard against
> over-silencing. This is precisely the ADR 0010 (adversarial pairing)
> earning-its-keep moment that v7.3.2's W5, v6.10.4, and v6.4.0 named:
> the dissent layer catches the failure mode the same model produces in
> its confirmation-shaped craft persona.
>
> Gates: **ci-gate-runner SHIPPABLE** (1297/1297 pytest, 3 scipy-
> conditional skips, ruff clean, 76/76 security probe, CLI smoke).
> **mcp-protocol-auditor PROTOCOL OK** (40/40 — 14 new v7.3.3 wire
> tests at `tests/test_serve_v733_wire_audit.py` added as audit side
> effect, parallel to v7.3.2's pattern; the wire tests required
> `PYTHONUNBUFFERED=1 + bufsize=0` on `_spawn` to bypass pytest's
> stdout-capture buffering — a test-infra fix, separate from the
> production F-G closure). **reproducibility-provenance-auditor CLEAN**
> (every touched file HOLDS against ADRs 0001 / 0002 / 0003 / 0008;
> v7.3.1 all-call-sites-sweep invariant holds on the new exempt path;
> v7.3.2 W5 AST contract test continues to satisfy 28/28).
> **phi-irb-risk-reviewer NO RISK** across all six threat-model lenses.
> **red-team-reviewer OBJECTION (medium) → CLOSED by F-G pre-ship.**
> cue-card-rehearsal-auditor NOT TRIGGERED (no `CUE_CARD.md` or
> `ToolDefinition` schema changes). recipient-install-validator SKIPPED
> per v6.11.x falsification precedent (no install-path globs touched).
> Net-new tests: 31 (16 in `tests/framework/test_v733_operator_action_required.py`
> + 14 in `tests/test_serve_v733_wire_audit.py` + 1 in
> `tests/children/redcap/test_redcap_shape.py`).

> **v7.3.2 (2026-05-15)** — Closes the two remaining v7.3.0 WATCH findings deferred
> from v7.3.1: (a) `project_metadata.csv` is a trust root — a tampered file with
> every identifier flag flipped from `Y` to `N` would render `RedcapPHIScrubber`
> a no-op with no cryptographic provenance of the state the scrubber was constructed
> against; and (c) `redcap_summary_report`'s `top_values` and
> `redcap_cohort_summary`'s group counts could re-identify on low-cardinality
> non-identifier-flagged fields (the N=3-sites disclosure path v7.3.0's release-pass
> auditor named). Two framework primitives land — both shaped as seams the
> framework hosts rather than policies it ships, matching ADR 0003's structural
> argument.
>
> **ADR 0003 § Amendment 2026-05-15 (NEW)** ratifies the trust-root attestation
> seam and the small-cell suppression posture. Lands inside ADR 0003 (not 0037)
> because the primitive generalises across children — a future EDF channel-metadata
> manifest, FHIR profile descriptor, or vendor calibration sidecar all inherit the
> seam. ADR 0037 stays REDCap-specific; ADR 0003 stays the seam-definition home.
> The "promotion to a framework registry on third domain" condition matches
> ADR 0013's precedent.
>
> **(a) Trust-root fingerprint seam.** New `RedcapPHIScrubber.fingerprint` property
> computes SHA-256 over a canonical-form rendering of sorted
> `(field_name, identifier_flag)` tuples at scrubber construction time. The
> canonical-form distinction is load-bearing: Excel/PowerShell BOM/CRLF/whitespace
> round-trips do NOT trip the fingerprint (otherwise legitimate operator edits
> would false-positive); flag flips and field additions/removals DO. New
> `audit_log.source_metadata_fingerprint TEXT` column (domain-agnostic naming)
> plus `idx_audit_source_metadata_fingerprint` index lets an IRB reviewer query
> "which calls ran under fingerprint X" with one-line SQL. Threaded through every
> audit row a child writes via the existing `child_scrubber_id` stamping
> convention (matching the all-call-sites-sweep rule from v7.3.1). Surfaced in
> result `_meta.source_metadata_fingerprint` across all 5 dispatch paths so the
> LLM transcript carries the trust-root identity at the moment of disclosure.
> `RedcapFileChild.execute()` re-reads `project_metadata.csv` on every call and
> returns a typed `REDCAP_METADATA_FINGERPRINT_MISMATCH` error envelope on drift;
> **forward-only policy** per ADR 0003 § Amendment 2026-05-15 — prior calls' data
> stays in the LLM transcript (the framework cannot un-send bytes); consent stays
> granted (revocation is operator action).
>
> **(a) Operator recovery is an attestation ritual.** New `tailor redcap reattest`
> CLI subcommand. Prints the cached fingerprint (most recent
> `audit_log.source_metadata_fingerprint` for `domain='redcap_file'`), the new
> fingerprint computed from the current on-disk file, and a sorted field-by-field
> listing of the current trust-root state with each field's identifier flag
> (`ok` vs `IDENTIFIER`). The listing is the trust-affording artifact: a tamper
> attempt that flipped every flag is visibly displayed before the operator
> confirms; a legitimate edit (new instrument added mid-enrollment) is visibly
> displayed before the operator confirms. On `y`, writes a `REATTEST` audit row
> carrying the new fingerprint; the running `tailor serve` must be restarted to
> load the new attestation. The framework refuses to silently update fingerprints
> to match on-disk changes — that would defeat the seam.
>
> **(c) Small-cell suppression posture.** New
> `RedcapProcessing.apply_small_cell_suppression_to_top_values` and
> `apply_small_cell_suppression_to_groups` static helpers (per ADR 0008
> `@staticmethod` invariant). Below-threshold entries collapse into a single
> aggregate of shape `{value: "<small_cell_suppressed>", count: "<below_threshold>",
> suppressed_count: K}` for top_values and `{n: "<below_threshold>",
> suppressed_group_count: K}` for groups. Applied to BOTH `redcap_summary_report`
> `top_values` AND `redcap_cohort_summary` `groups` per the auditor's F4 finding
> — the cohort group-count surface is the higher-leverage re-identification path
> the initial plan missed. Default k=5 (HHS SDL baseline). Configurable via
> `redcap_file.small_cell_suppression_threshold` in `user_config.json`; validated
> `>= 2` at config-load time so a permissive k=1 misconfig is refused loudly
> rather than silently ignored. Studies with elevated re-identification risk
> (pediatric, mental health, rare-disease) opt up to k=10/k=11.
> `small_cell_suppression_threshold` surfaces at the top level of every result
> envelope where suppression was applied; a `small_cell_warning` field surfaces
> alongside whenever the framework default is in force rather than an explicit
> operator setting — parallels v6.3.1's `scrubber_warning` pattern, landed at the
> top of the child envelope (alongside `unknown_field_count`,
> `field_marked_identifier_stripped`) because the threshold is child-domain-specific
> and the router does not own per-child policy fields.
>
> **Proposal-mode audit caught three BLOCKING + three IMPORTANT pre-implementation.**
> F1 — fingerprint at consent-time only would leave Tier-1 REDCap calls unanchored
> on a fresh install since Tier-1 REDCap is not consent-gated per ADR 0037 —
> resolved by stamping at server boot (D1). F2 — `_meta` threading on all five
> sites — addressed by domain-conditional value
> (`child.child_source_metadata_fingerprint` on child paths, `None` on
> vault / local_llm / setup_help paths). F3 — raw-byte hash would false-positive
> on Excel BOM round-trips — addressed by canonical-form sorted tuples (D5).
> C1 — mid-session mismatch auto-revoke vs forward-only — resolved as forward-only
> (D2). C2 — REDCap-specific column naming vs domain-agnostic — resolved as
> `source_metadata_fingerprint` + ADR 0003 § Amendment placement (D4). C3 — k=5
> default vs required-config — resolved as default-with-warning (D7).
>
> No router / security / cost / audit-pipeline architectural changes beyond the
> additive column, the additive `_meta` field, and the additive interface
> property (`child_source_metadata_fingerprint` on `ChildMCP` with default
> `None`). No public API breaks; new CLI subcommand (`tailor redcap reattest`)
> is additive. Patch bump (additive `_meta` fields + additive audit column +
> new failure-class error envelope + new CLI subcommand match the v7.3.1
> patch-bump precedent for observability-only additions).
>
> **Release-pass fix cascade — 2 VIOLATIONs + 2 WATCH findings closed
> pre-merge.** `phi-irb-risk-reviewer` returned VIOLATION on two
> structural defects in the first-pass implementation, with
> `reproducibility-provenance-auditor` independently flagging the same
> first defect under its `BORDER NOTES`. **(F-A VIOLATION, Lens 2 + 3)**:
> `cmd_redcap_reattest` was hand-rolling a raw `sqlite3.INSERT` into
> `audit_log` rather than calling `AuditLog.record()`, leaving
> `scrubber_id` NULL on the REATTEST row — directly breaking ADR 0003's
> *"scrubber_id turns 'did we scrub?' into a fact on disk"* invariant,
> the same v7.3.0 banner-claim-falsification class the v7.3.1
> all-call-sites-sweep rule existed to catch (the rule fired on router
> sites; the CLI hand-rolled path slipped past). Rewrote to use
> `AuditLog.record()` — inherits the full schema, the migration logic,
> `scrubber_id="noop"` (framework default), and any future audit-column
> additions automatically. **(F-B VIOLATION, Lens 3)**: the mismatch
> path was returning a dict-with-error-key from
> `RedcapFileChild.execute()` rather than raising — the router's
> exception handler never fired, so the audit row was stamped
> `outcome="SUCCESS"` with the boot-time fingerprint while the on-disk
> fingerprint that triggered the mismatch lived only in the wire
> transcript. ADR 0003 § Amendment 2026-05-15's stated promise *"the
> audit log carries both fingerprints"* was unhonored as shipped.
> Switched to raising a new `RedcapMetadataFingerprintMismatch` typed
> exception carrying both fingerprints as attributes + in `str(exc)`;
> the router's existing exception handler records `outcome=ERROR` with
> the error column queryable via
> `WHERE error LIKE 'REDCAP_METADATA_FINGERPRINT_MISMATCH:%'`.
> **(F-C WATCH, Lens 1)**: small-cell suppression was applied to
> `top_values` and cohort `groups` only; `redcap_summary_report`'s
> `completion_counts` (the third aggregate count surface — `{instrument:
> count}`) was left unsuppressed, leaking small-N disclosure of the
> same shape the auditor's F4 finding closed for cohort groups. Added
> a third static helper `apply_small_cell_suppression_to_completion_counts`;
> wired into `_handle_summary_report`. **(F-D WATCH, Lens 6)**: added a
> 4th retention-category paragraph to `docs/design/research-framing.md`
> naming trust-root attestation rows alongside biometric cache,
> analyst notes, and oracle audit rows. IRB submissions citing Tailor
> against a REDCap protocol now have doc text to point at for the
> mismatch-disclosure question.
>
> Gates after fix cascade: **1266/1266 pytest** (1187 prior + 79 net
> new — 49 first-pass + 30 fix-pass: 5 completion_counts suppression
> tests + 1 router-side mismatch-error-audit verifier + 24 wire-level
> regression tests in `tests/test_serve_v732_wire_audit.py` added as a
> side-effect of the `mcp-protocol-auditor` run), 3 scipy-conditional
> skips. Ruff clean. `recipient-install-validator` SKIPPED per v6.11.x
> falsification precedent (no install-path globs touched).
>
> **mcp-protocol-auditor GAP closure — 28/0 audit-record-site invariant.**
> The auditor's first pass returned PROTOCOL OK with one GAP: the
> `local_llm` SUCCESS audit row didn't pass `source_metadata_fingerprint=`
> explicitly even though every other SUCCESS row did (DB default of NULL
> was semantically correct but the implicit-vs-explicit inconsistency
> broke the "all-call-sites sweep" rule from v7.3.1). The fix-pass made
> the local_llm site explicit, then pushed to full 28/0 closure across
> the 6 remaining framework-tier error/exception sites (vault
> PARAM_INVALID + ERROR, local_llm PARAM_INVALID + ERROR, setup_help
> PARAM_INVALID + ERROR). Every `audit.record()` site in `router.py`
> now threads the kwarg explicitly; the next sweep is trivial.
> `tests/test_serve_v732_wire_audit.py::TestW5AllCallSitesSweep::test_all_audit_record_sites_carry_source_metadata_fingerprint`
> asserts the 28/0 invariant by reading router source — fails loudly
> on any future regression.
>
> **Second-pass verdicts both clean.** `phi-irb-risk-reviewer` re-audit
> on the F-A through F-D fixes + first-pass 28/0 closure returned
> **NO RISK across all six threat-model lenses** (Safe Harbor, consent
> scope, audit-log completeness, scrubber asymmetry, subject_id
> integrity, retention) — every VIOLATION + WATCH from the first pass
> closed with regression-test coverage. `reproducibility-provenance-
> auditor` re-audit returned **CLEAN** on every touched in-scope file
> (audit, interfaces, router, redcap child / processing / scrubber,
> main); ADR 0001 + ADR 0003 § Amendment 2026-05-15 + ADR 0008
> invariants HOLD with file:line citations; the first-pass BORDER NOTE
> on `cmd_redcap_reattest` hand-rolled INSERT is closed.
>
> **Red-team-reviewer caught a structural defect all four upstream
> specialists missed — MEDIUM OBJECTION closed before ship.** The
> first-pass "28/0 audit-record-site invariant closure" claim was
> **factually wrong** — actual count was 26/2 (vault SUCCESS at
> `router.py:803`, setup_help SUCCESS at `router.py:1092` lacked the
> explicit `source_metadata_fingerprint=` kwarg). The W5 contract test
> meant to enforce the invariant had a textual-window false-positive:
> its 25-line scan after every `self._audit.record(` line was picking
> up the `source_metadata_fingerprint` field name out of the **adjacent
> `_meta` block dict literal** that follows each dispatch path's
> SUCCESS audit, not out of the audit-record call's actual keyword
> list. The test passed for the wrong reason. Behaviorally the wire
> and DB were unaffected (`AuditLog.record()` defaults the kwarg to
> None) but the v7.3.1 banner's all-call-sites-sweep rule had a
> structural teeth-gap exactly where the v7.3.2 banner claimed it had
> teeth. **F-E + F-F closures:** F-E adds explicit `source_metadata_
> fingerprint=None` at `router.py:803` (vault SUCCESS) and `:1092`
> (setup_help SUCCESS). F-F rewrites W5 with AST-based detection
> (`ast.walk` finds every `self._audit.record()` call node, inspects
> ONLY its `node.keywords` list, ignores textual adjacency) so future
> textual masking cannot recur. The W5 enforcement class is now
> **AST-class rather than grep-class** — strictly stronger than the
> v7.3.1 banner mandated. This is precisely the ADR 0010 (adversarial
> pairing) earning-its-keep moment that v6.10.4 and v6.4.0 named: the
> dissent layer catches the failure mode the same model produces in
> its confirmation-shaped craft persona.
>
> **Red-team BORDER NOTES recorded for v7.3.3.** (1) Circuit-breaker
> interaction with mismatch failures: 3 consecutive mismatches in 300
> seconds trips the circuit; for the next 5 minutes the LLM sees a
> generic "Circuit open for redcap_file" envelope rather than the
> mismatch's `tailor redcap reattest` recovery hint. ADR 0003 §
> Amendment 2026-05-15 names the recovery path but does not name the
> circuit-breaker interaction; no test exercises the multi-mismatch
> path. (2) Blanket `except Exception: return None` in
> `_detect_fingerprint_mismatch` swallows every exception from
> `RedcapPHIScrubber.__init__`; a future required-parameter refactor
> would silently disable mismatch detection without test coverage
> flagging it. Both deferred to v7.3.3 as known-debt; neither is a
> wire/DB-correctness defect today.
>
> Both auditors also independently flag a **cosmetic indentation
> BORDER NOTE** (`source_metadata_fingerprint=` lines sitting one
> column shallower than the sibling `child_scrubber_id=`) — ruff
> passes; deferred to the next reformatter pass.

> **v7.3.1 (2026-05-15)** — Bug-hunt-followup patch + structural gate-composition closure.
> Closes 3 VIOLATION-class defects + 4 HIGH findings surfaced by a 7-specialist max-depth
> audit against v7.3.0 HEAD (2026-05-14 overnight session), plus a 5th defect surfaced
> by boss-report-auditor adversarial pairing on the v7.3.1 draft itself, plus the team-
> shape closure of the structural gate-composition gap the hunt named. Two of the three
> original VIOLATIONs were direct falsifications of v7.3.0 banner claims — this banner
> names them as second-pass catches rather than glossing past. Patch-bump per v6.3.1
> precedent (the `scrubber_warning` `_meta` field landed as patch — observability-only
> additions to `_meta` are strictly additive on the read side and don't break consumers).
>
> **Banner-claim falsification 1 — IRB-stakes.** v7.3.0 claimed "failure rows leaving
> `child_scrubber_id` NULL — fixed by stamping at row-construction time." The fix landed
> correctly on `_dispatch` and `dispatch_internal` (13 sites) but missed the 5 audit-record
> sites in the consent handlers at `framework/router.py:1281, 1334, 1359, 1395, 1401`.
> On a REDCap deployment, an OHRP inquiry asking "did your child-level PHI scrubber run
> when consent was withdrawn?" CANNOT be answered from the audit log alone — the consent-
> revocation rows (the IRB-highest-leverage events in the entire audit history) silently
> recorded `child_scrubber_id` as NULL despite the REDCap child carrying an active
> `redcap_metadata_flags` scrubber. PHI agent and integration-auditor independently named
> the same 5 line numbers — reproducibility-grade finding. Commit `072b483` threads
> `child_scrubber_id` into all 5 sites + 5 new unit tests + wire-side end-to-end verifier
> in `tests/test_serve_v731_wire_audit.py::TestW3ConsentAuditRowsThreadChildScrubberId`.
>
> **Banner-claim falsification 2.** v7.3.0 framed REDCap as "registration block is opt-in-
> gated so default install path is unchanged" — true for default installs, materially
> misleading for any opt-in deployment with a malformed `redcap_file` block (missing
> required `path` key). `__main__.py:165-167` had no try/except, so
> `RedcapFileChild.__init__` raising `ValueError` aborted `tailor serve` with rc=1, taking
> down running + csv_dir + vault + local_llm. Same v6.10.2 SetupHelpLayer failure class.
> Commit `1e9c442` wraps the registration mirroring the matlab pattern 27 lines above;
> serve boots rc=0, operator banner on stderr, other tools registered. Subprocess
> regression test `test_v731_malformed_redcap_config_does_not_kill_serve` + wire-side
> `TestW4MisconfiguredRedcapBoots` cover this on the wire.
>
> **PHI Safe Harbor surface reduction.** `redcap/child.py` 11 error-envelope sites +
> `redcap/scrubber.py` 3 warning sites swapped raw-path interpolation for
> `<configured_redcap_path>` / `<configured_redcap_records_path>` /
> `<configured_redcap_metadata_path>` placeholders. Full path retained in stderr
> `log.warning` only — dev/operator debug surface preserved, LLM transcript +
> `audit_log.error` column de-identified per HIPAA Safe Harbor §164.514(b)(2)(i)(B + R).
> Coupling B fix per proposal-mode audit: scrubber.py sites reached the wire via
> `child_scrubber_warning` → `_scrubber_warning_block()` on every result envelope; without
> this extension, the Item 5 corruption tests would have locked the disclosure.
> Commit `b221e65`.
>
> **WATCH (b) closure — `child_scrubber_id` in `_meta`.** v7.3.0 banner deferred surfacing
> the new column on the wire. v7.3.1 closes it across 5 `_meta` stamping sites in
> `framework/router.py` (child dispatch:711, vault layer:801, local_llm layer:986,
> setup_help layer:1087, dispatch_internal:1240). The first 4 landed in commit 2; the
> setup_help site (5/5) was discovered by boss-report-auditor's G8 finding while auditing
> this very banner draft and landed in commit 7/7 — concrete evidence the chosen option 2
> is real, not theoretical. Wire-output shape uniformity across all dispatch paths.
> mcp-protocol-auditor wire-side test `test_meta_contains_child_scrubber_id_wire_side_three_sites`
> covers three reachable sites + a raw-wire byte inspection asserting JSON `null` (not
> Python `"None"` repr).
>
> **Three secondary fixes.** (a) `setup_help/__init__.py:221` one-char typo
> `"redcap_export"` → `"redcap_file"` (commit `94b5dc9`) closed an inverse-v6.10.2 trap
> where SetupHelpLayer was firing on working REDCap deployments. (b)
> `RedcapPHIScrubber._load_metadata` exception handler gains 3 regression tests on three
> failure modes (OSError via patched `builtins.open`, non-UTF-8 raw bytes, BOM-only file
> — third one activates a different fail-closed branch per proposal-mode auditor's
> prediction; same fail-closed invariant verified). (c) REDCap child added to vault
> writer's `_registered` list in `__main__.py:215` closing the v7.3.0 BORDER NOTE
> asymmetry (vaultable_tools collected for every child except redcap).
>
> **Structural finding closed — option 2 landed (commit `5ba80c7`).** The v7.3.0 cascade
> shipped with 3 VIOLATIONs because specialist agents fired on the *diff* and verified
> new code, but each VIOLATION was an *invariant the diff implied* — existing call sites
> that pre-existed v7.3.0 but now needed to satisfy a new contract. Three v7.3.x findings
> demonstrate the class (consent-handler audit threading, setup_help _meta, v6.3.1
> scrubber_id wiring). Boss chose option 2: extend `phi-irb-risk-reviewer` prompt with a
> new mandatory "Step 1.5 — All-call-sites sweep on new invariants" pre-Step-2 procedure.
> When a diff adds a new `audit_log` column, a new `_meta` field, a new `ChildMCP`
> property, or any other shared-invariant change, the auditor must grep for every
> existing call site of the invariant, diff against the diff's adds, and verify each
> untouched site either correctly inherits the default or threads the new value.
> Reversal condition named: if v7.4.x ships with zero defects caught by this rule, retire
> as ceremony.
>
> `ci-gate-runner` SHIPPABLE: **1187/1187 pytest** (verified post-commit-7 at 87b6b24;
> 1137 prior + 50 net new), 3 scipy-conditional skips, 82% coverage, ruff clean,
> 76/76 security probe, CLI smoke clean. `mcp-protocol-auditor` PROTOCOL OK on all 6
> v7.3.1 wire surfaces. `boss-report-auditor` REVISE → 10 gaps addressed.
> `recipient-install-validator` SKIPPED per v6.11.x falsification precedent.
> Patch bump.

> **v7.3.0 (2026-05-14)** — Move 3 / Part 2: REDCap existence-proof
> child — six-tool, three-tier REDCap-export source axis. Third
> non-CSV source axis demonstrated by the v7.1.1 source-agnostic
> claim (after the running child and matlab_file). New
> `src/tailor/children/redcap/` exposes `RedcapFileChild` with
> six tools across all three tiers, matching the csv_dir / matlab_file
> shape: `redcap_list_records`, `redcap_record_detail`,
> `redcap_summary_report`, `redcap_cohort_summary` (Tier 1);
> `redcap_records` (Tier 2 — instrument-scoped per the R2 ratified
> decision; `instrument` is a required parameter, not optional);
> `redcap_raw_records` (Tier 3). Cohort surface ships in v1 using the
> ADR 0015 `metadata.json` sidecar pattern unchanged. Opt-in via
> `redcap_file` block in `user_config.json`; default deployments
> behaviourally unchanged.
>
> [ADR 0037](docs/adr/0037-redcap-child-scope-export-directory-only-with-deferred-live-api.md)
> (NEW, Accepted) codifies the scope-bound: REDCap CSV export
> directories only (the artifact every REDCap project produces on
> demand); live REDCap REST API support deferred behind a future
> superseding ADR with a named reversal condition (first real-world
> deployment target identifies live-API as the load-bearing path).
> Same scope-bound posture as ADR 0036's HDF5 deferral. Critically,
> REDCap exports are stdlib-only — **no new optional extras**;
> contrast with v7.2.0's `[matlab]` extra. The lean three-dep base
> install posture (`mcp`, `requests`, `orjson`) is preserved.
>
> [ADR 0003 § Amendment 2026-05-14](docs/adr/0003-phi-scrubber-seam.md)
> introduces a **child-level PHI scrubber seam** parallel to the
> framework-level seam. REDCap is the forcing function: a REDCap
> project's `project_metadata.csv` carries per-field `identifier`
> flags (Y / N) that structurally answer the question ADR 0003
> declined to answer generically — *which fields are PHI?* — for this
> source axis. `RedcapPHIScrubber` reads those flags and scrubs
> flagged fields inside `RedcapFileChild.execute()` before the result
> returns to the framework-level seam. New `audit_log.child_scrubber_id`
> column records the child's internal scrubber identity
> (`"redcap_metadata_flags"` for REDCap calls; NULL for csv_dir /
> matlab_file / running which inherit the ABC default). Threaded on
> every child-related audit row per the existing `scrubber_id`
> stamping convention; legacy audit DBs migrate via `ALTER TABLE`.
>
> **The release-pass cascade caught two HIGH PHI/IRB VIOLATIONs
> pre-merge** — the structural reason the v7.3.0 banner is honest
> about this rather than glossing it as "tests added". (1)
> `phi-irb-risk-reviewer` found that `redcap_cohort_summary`'s
> per-field guards were using `is_known_identifier`, which returned
> `False` for unknown fields — silently bypassing the fail-closed
> defense ADR 0037 codified for the source axis where identifier flags
> are structurally available. Fixed by predicate swap to
> `is_identifier` (the inverse — returns `True` unless explicitly
> flagged non-identifier) plus regression tests on the unknown-field
> path. (2) `phi-irb-risk-reviewer` also found that failure rows on
> the dispatch path were leaving `child_scrubber_id` NULL, breaking
> the ADR 0001 audit-completeness invariant the new column exists to
> enforce; fixed by stamping the child's scrubber_id at row-construction
> time, not at success-path return. (3) `red-team-reviewer` returned
> OBJECTION (HIGH) on coverage — no end-to-end tests for the audit-row
> threading or the legacy-DB `ALTER TABLE` migration; closed by three
> new tests in the bundled fix pass. All three findings landed in
> a single bundled fix pass before this banner shipped.
> [ADR 0010](docs/adr/0010-adversarial-pairing.md) (adversarial
> pairing) is the structural reason the gate caught these pre-ship
> rather than post-recipient — the same shape that earned its keep on
> v6.10.4 and v6.4.0 keeps earning it here.
>
> Three WATCH findings deferred to v7.3.1 (institutional-clarification
> territory, not VIOLATIONs): (a) `project_metadata.csv` itself is a
> trust root — a tampered metadata file with all flags flipped to `N`
> would render `RedcapPHIScrubber` a no-op; needs a hash-stamp or
> consent-time fingerprint. (b) The `_meta` block on REDCap results
> should surface `child_scrubber_id` alongside the framework
> `scrubber_id` so misconfigured deployments are visible in the LLM
> transcript itself, parallel to the v6.3.1 `scrubber_warning` work.
> (c) `redcap_summary_report` `top_values` disclosure on permissively
> allowlisted fields could re-identify on low-cardinality
> non-identifier-flagged fields (e.g. study site with N=3 sites);
> needs a small-cell suppression threshold.
>
> `mcp-protocol-auditor` TRIGGERED (PROTOCOL OK; 15 wire-level + 4
> contract tests; side-effect of the audit was 19 new subprocess tests
> at `tests/test_serve_redcap_protocol.py`).
> `reproducibility-provenance-auditor` TRIGGERED (CLEAN; all
> ADR 0001 / 0002 / 0003 / 0008 / 0037 invariants HOLD).
> `phi-irb-risk-reviewer` TRIGGERED (CLEAN after the bundled fix pass;
> 2 HIGH VIOLATIONs CLOSED; 3 WATCH findings deferred to v7.3.1 as
> named above). `red-team-reviewer` OBJECTION (HIGH) → CLOSED by the
> bundled fix pass's 3 new tests. `researcher-utility-reviewer` runs
> pre-ship against this banner. `cue-card-rehearsal-auditor` ATTEST
> SKIP (no CUE_CARD.md changes; the demo cue card is HIP-Lab-specific
> and does not carry per-child operator prompts). `recipient-install-
> validator` SKIPPED per v6.11.x falsification precedent;
> registration block is opt-in-gated so default install path is
> unchanged. `ci-gate-runner` SHIPPABLE: 1137/1137 pytest (973 prior +
> 164 new — REDCap shape/processing/scrubber + mcp-protocol subprocess
> + bundled-fix-pass coverage tests), 82% coverage, ruff clean, 76/76
> probe, CLI smoke clean. Minor bump because a new child = public API
> addition (matches the v7.2.0 minor-bump precedent).

> **v7.2.0 (2026-05-14)** — Move 3 / Part 1: MATLAB existence-proof
> child lands as the second non-CSV source axis demonstrated by the
> v7.1.1 source-agnostic claim. New `src/tailor/children/matlab_file/`
> exposes `MATLABFileChild` (six tools across all three tiers,
> matching the csv_dir shape): `matlab_list_files`,
> `matlab_file_detail`, `matlab_summary_report`,
> `matlab_cohort_summary` (Tier 1); `matlab_downsampled` (Tier 2);
> `matlab_raw_array` (Tier 3). Cohort surface ships in v1 (not
> deferred) using the ADR 0015 `metadata.json` sidecar pattern unchanged
> — closes the proposal-mode F5 finding that MATLAB-shop datasets are
> cohort-shaped by construction. Opt-in via `matlab_file` block in
> `user_config.json`; default deployments behaviourally unchanged.
>
> [ADR 0036](docs/adr/0036-matlab-child-scope-v72-only-with-deferred-hdf5.md)
> (NEW, Accepted) codifies the scope-bound: `.mat` v5/v6/v7.2 only via
> scipy pulled in as an optional dep (`pip install tailor-mcp[matlab]`).
> v7.3 HDF5-based `.mat` is detected via magic bytes and rejected with
> a typed-error envelope citing the ADR; full v7.3 support is held
> behind a future superseding ADR with a named reversal condition
> (first beachhead lab hits the gap). Lean three-dep posture
> (`mcp`, `requests`, `orjson`) preserved on the base install.
>
> Move 3 / Part 2 (REDCap existence-proof child) **held for v7.3.0
> fresh-session build**. Originally bundled with MATLAB per the boss's
> 2026-05-14 protocol-1 ratification; in-session context-budget reality
> test re-sequenced to unbundled. REDCap-specific proposal-mode audit
> ran and ratified the PHI-defense posture (built-in REDCap PHI scrubber
> as ADR 0003 amendment) — the v7.3.0 session inherits that decision.
>
> `mcp-protocol-auditor` TRIGGERED (new child's execute() path);
> `reproducibility-provenance-auditor` TRIGGERED (new processing.py);
> `researcher-utility-reviewer` ran pre-release. `cue-card-rehearsal-
> auditor` ATTEST SKIP (no CUE_CARD.md changes; 6 new ToolDefinition
> schemas are MATLAB-specific and not yet on the cue card). `recipient-
> install-validator` SKIPPED per v6.11.x falsification precedent;
> registration block is opt-in-gated so default install path is
> unchanged. ci-gate-runner SHIPPABLE: 973/973 pytest (937 prior + 36
> new MATLAB tests; shape tests skip cleanly on machines without
> scipy), ruff clean, 76/76 probe, CLI smoke clean. Minor bump because
> a new child = public API addition.

> **v7.1.1 (2026-05-14)** — Source-agnostic positioning patch (Move 1 of
> three-move strategic-positioning sequence). `README.md` hero and
> `README_PYPI.md` intro gain a parallel bold-led clause naming the
> source-agnostic axis: "The same architecture works on whatever shape
> your data is already in — CSV directories today; REDCap exports, EDF
> recordings, FHIR bundles, vendor sensor exports, or any other source
> through a small `ChildMCP` extension that inherits the full pipeline
> (tier model, audit, scrubber seam, Wardrobe)." Slot 3 in the README hero;
> a new ¶3 in the PyPI intro. The two existing AI-economics bold sentences
> (slots 1+2 in README; ¶1+¶2 in PyPI) are unchanged — the $200/month →
> $2/month framing preserved at parity per boss's weight-preservation
> constraint. A 10-100× cost-per-question tie-back sentence closes each new
> clause to compound the AI-economics umbrella claim rather than diluting it.
>
> `integration-auditor --proposal-mode` returned REVISE on first pass with 3
> IMPORTANT findings addressed: F1 (template-child "four named blanks"
> overclaim — dropped); F2 (MATLAB not ROADMAP/ADR-grounded — dropped; kept
> four ROADMAP-held items: REDCap / EDF / FHIR / vendor sensor exports); F3
> (bold-emphasis ordering — source-agnostic landed in slot 3 to preserve AI-
> economics slots 1+2); C2 (line-range trimming risk — fixed by exact-string
> Edit, preserving the "first recipe shipped end-to-end" framing intact).
> Workshop-vs-lifestyle invariant per ADR 0033 + ADR 0035 Table 5 verified
> clean (no forbidden words; `Wardrobe` / `ChildMCP` / `Tailor` per Table 1).
>
> No `src/` logic changes; no `tests/` changes; no schema changes; no public
> API changes; no router/security/child/vault/CLI architecture changes. Patch
> bump. Gates: 946/946 pytest, ruff clean, 76/76 probe, CLI smoke clean.
> mcp-protocol-auditor NOT TRIGGERED (no framework/router/security/vault paths
> touched; prose-only). cue-card-rehearsal-auditor NOT TRIGGERED (no CUE_CARD.md
> or ToolDefinition schema changes). recipient-install-validator SKIPPED
> (README.md + README_PYPI.md are not ADR 0028 trigger globs; v6.11.x
> falsification grounds the opt-in skip).

> **v7.1.0 (2026-05-14)** — CLI rename: `tailor demo` → `tailor walkthrough`,
> `tailor tour` → `tailor fitting-room`. Old verbs preserved as one-cycle
> deprecation shims with stderr hints citing [ADR 0035](docs/adr/0035-cli-rename-walkthrough-and-fitting-room-and-recipient-experience-naming-principle.md);
> removal target bumped from v7.2.0 to a future minor (v7.2.0 scope was
> re-aimed at Move 3 / MATLAB child per the post-v7.1.1 strategic
> sequence; CLI cleanup is unrelated work). New `tailor fitting-room`
> heads-up prompt warns
> recipients to quit Claude Desktop before the command writes the MCP config.
> Default `--save-shareable` filename updated to `shareable-walkthrough-vX.Y.Z.md`.
>
> Codified by [ADR 0035](docs/adr/0035-cli-rename-walkthrough-and-fitting-room-and-recipient-experience-naming-principle.md)
> (NEW, ~370 lines): recipient-experience-shaped naming principle; recipient-
> evaluation-class scope; operator-class grandfathered list; vocab-doc update
> mandate. ADR 0024 + ADR 0026 + ADR 0027 each gain a Partially Superseded footer
> (CLI verb name only; substance retained). `docs/design/tailor-vocabulary.md`
> updated: `closet` added to always-forbidden (Table 5); `Fitting` removed from
> weak beats (Table 6; promoted to CLI name); new "Recipient-facing surfaces"
> section names walkthrough + fitting-room with etymology and naming principle.
>
> Structural: `src/tailor/tour.py` → `src/tailor/fitting_room.py` via `git mv`
> (history preserved); one-line re-export shim at `src/tailor/tour.py` maintains
> `from tailor.tour import main as tour_main` for `examples/` scripts until v7.2.0.
> Server-name `tailor-tour-{variant}` → `tailor-fitting-room-{variant}`; existing
> `_is_orphan_entry_key` prefix-cleaner handles both keys without modification
> (per ADR 0026 amendment). Setup_help dict fields renamed:
> `default_tour_target` → `default_scaffold_target`,
> `if_tour_keeps_failing` → `if_scaffold_keeps_failing`.
> `tests/test_tour_subcommand.py` → `tests/test_fitting_room_subcommand.py` via
> `git mv`. NEW `tests/test_cli_deprecation_hints.py` (3 test classes).
> 22+ test-assertion monkeypatch sites updated. Recipient-facing docs swept
> (README.md, README_PYPI.md, RECIPIENT_README.md, guides, diagnosis kit,
> examples, CUE_CARD.md, WINDOWS_QUICKSTART.md, ROADMAP.md, agent prompts).
>
> No router/security/vault/child architecture changes. No schema changes.
> No `framework/` changes beyond setup_help dict-field renames. Minor bump
> (7.0.13 → 7.1.0): new CLI verbs are public API additions; old verbs preserved
> non-breaking in this cycle; breaking removal deferred to v7.2.0.
> Gates: 946/946 pytest, ruff clean, 76/76 probe, CLI smoke clean.
> mcp-protocol-auditor NOT TRIGGERED (no framework/router/security/vault paths
> touched; `__main__.py` changes are CLI dispatch + shims only).
> cue-card-rehearsal-auditor ATTEST SKIP (CUE_CARD.md prose-only; zero
> ToolDefinition schema changes per ADR 0025).
> recipient-install-validator ATTEST SKIP (v6.11.x falsification + 2026-05-12
> macOS install + 2026-05-13 PyPI publish ground the opt-in skip; rename does
> not introduce a new install-path failure class).

> **v7.0.13 (2026-05-13)** — PyPI publish ship. `tailor-mcp` published
> to PyPI as the canonical install channel; `uv tool install tailor-mcp`
> replaces the `uv tool install git+https://...` URL form across every
> recipient-visible doc site. Closes the Phase 2 PyPI-publish
> deliverable.
>
> v7.0.13's shape **departs from the v7.0.12 banner's prediction** —
> that banner forecasted a "repo public-flip + PyPI publish" bundle.
> The repo public-flip is deferred to a future version under a
> three-condition trigger (see [ROADMAP.md § Held items](ROADMAP.md#held-items-revisit-when-the-trigger-fires)):
> (1) beachhead lab using Tailor on real data, (2) launch-narrative
> artifacts drafted, (3) boss separately decides he wants public
> scrutiny. Argument for unbundling: PyPI answers a tooling question
> ("is there a frictionless install path?") and the project is at YES
> on it; repo public-flip answers an audience question ("is the trust
> narrative going out into the world?") and the project is at NOT YET.
> The honest shipping shape matches that.
>
> New: GitHub Pages landing page at
> [saahasmuthineni.github.io/tailor-mcp-landing](https://saahasmuthineni.github.io/tailor-mcp-landing/)
> hosts a one-page project description with install command,
> architecture summary, and explicit "invited evaluation" framing; URL
> is `Homepage` in `pyproject.toml` so PyPI's sidebar resolves.
> `Repository` and `Issues` URLs removed since the repo stays private
> — source code is inspectable via the wheel; governance trail (ADRs,
> ROADMAP, design notes) stays private. Same posture an academic
> research tool typically distributes under.
>
> `integration-auditor --proposal-mode` returned REVISE on the initial
> PyPI-only plan with 4 BLOCKING + 5 IMPORTANT + 3 NICE-TO-HAVE
> findings + 3 prior-decision conflicts; all BLOCKING closed
> pre-publish. New `README_PYPI.md` authored for PyPI rendering (no
> Mermaid, no SVGs, no relative links, no GitHub-flavored callouts;
> ASCII architecture diagram; `pyproject.toml`'s `readme` field
> repointed) while `README.md` stays the GitHub README;
> `RECIPIENT_README.md` dead `examples/...WINDOWS_QUICKSTART.md`
> pointer removed (wheel doesn't bundle `examples/`); `tailor demo
> --save-shareable` install-URL emission swapped from
> `github.com/.../releases/download/...wheel.whl` → PyPI commands
> (`uvx --from tailor-mcp tailor demo`, `pipx run --spec tailor-mcp
> tailor demo`); `install_url_base` parameter on
> `_generate_shareable_markdown` retired along with the
> `TAILOR_DEMO_INSTALL_URL_BASE` env-var override;
> [ADR 0030](docs/adr/0030-public-mirror-narrative-and-affordance-depth.md)
> URL allowlist tightened from "wheel-release-asset only" to "zero
> outbound URLs" via a new **§ Amendment 2026-05-13** section + Status
> pointer. Three coupled tests in `tests/test_demo_runner.py` flipped
> to defend the new posture (assert PyPI install commands appear;
> assert github-releases URL does NOT appear; assert
> wheel-release-asset URL is REJECTED by the tightened allowlist).
>
> Other notable changes: PEP 639 license migration (`license = {text =
> "Apache-2.0"}` → SPDX `license = "Apache-2.0"` + `license-files =
> ["LICENSE"]`; redundant `License :: OSI Approved :: Apache Software
> License` classifier dropped); bundled-fixture citation softened from
> named-researcher form to literature-form (`Hunter & Senefeld 2024
> flagged in the J Physiol review` → `consistent with the J Physiol
> 2024 review literature on sex differences in human performance` —
> closes the named-person-on-publicly-distributed-artifact concern);
> doc-sweep of install commands across `CLAUDE.md` active section,
> `README.md`, `docs/guides/multi-subject-pilot.md`,
> `docs/diagnosis/phase-0-diagnosis-kit.md`, with historical banner
> references in CLAUDE.md v7.0.10 entry, ROADMAP Shipped section, and
> ADR 0031 preserved per the historical-record doc-truth principle.
>
> No `src/` logic changes beyond `runner.py` install-URL emission + URL
> allowlist refactor (the surface BLOCKING-4 + C1 named); no
> framework/router/security/child/vault changes; no schema changes; no
> public API changes beyond the `_generate_shareable_markdown`
> signature simplification (the `install_url_base` parameter is retired).
> Patch bump because release shape is distribution-channel pivot +
> doc-truth sweep, not feature work. Gates: ci-gate-runner SHIPPABLE
> (TBD pending demo-before-commit dispatch). mcp-protocol-auditor NOT
> TRIGGERED (no framework/router/security/vault paths touched).
> cue-card-rehearsal-auditor NOT TRIGGERED (no CUE_CARD.md or
> ToolDefinition schema changes). recipient-install-validator SKIPPED
> (`pyproject.toml` package-data globs untouched; `_fixtures/**` edit
> is a one-line citation in a vault moment fixture, not
> install-path-affecting; v6.11.x falsification grounds the opt-in skip
> per v6.11.1 policy).

> **v7.0.12 (2026-05-12)** — Phase 2 pre-flip doc-truth sweep. Governed by
> an `integration-auditor --proposal-mode` REVISE verdict (10 findings: 3
> BLOCKING / 4 IMPORTANT / 3 NICE-TO-HAVE) on the Phase 2 cheapest-pair
> plan (PyPI publish + repo public-flip). This is the **reversible half**;
> v7.0.13 carries the irreversible operations (repo public-flip + PyPI
> publish) and does not fire until this is on main and an incognito-browse
> dry-run passes.
>
> 2 files deleted: `install.ps1` + `install.sh` (zombie legacy curl-pipe
> scripts referencing the pre-pre-rename `biosensor-to-llm-middleware` URL;
> would 404 on a public repo; install path is `uv tool install` per Phase 0
> closure). 10 files modified: stale `biosensor-to-llm-middleware` URL →
> `tailor-mcp` in `.github/SECURITY.md`, `CONTRIBUTING.md`,
> `docs/adr/0002-subject-id-scoping.md`, `docs/adr/0003-phi-scrubber-seam.md`;
> hardcoded `c:\Users\saaha\Biosensor-to-LLM-Connector\` boss-machine paths →
> `<repo-root>` placeholder in `docs/diagnosis/phase-0-diagnosis-kit.md`
> (lines 43, 209); WINDOWS_QUICKSTART install framing rewritten from
> Python + pip to uv + `uv tool install` (same defect v7.0.4 paid to fix in
> README, missed in this guide); `src/tailor/demo/runner.py` default
> `install_url_base` env-var fallback updated from archived
> `biosensormcpdemo` mirror → `saahasmuthineni/tailor-mcp` Releases page per
> [ADR 0032](docs/adr/0032-retire-public-mirror-distribution-path.md);
> matching test renamed + assertion updated in `tests/test_demo_runner.py`;
> CI badge removed from `README.md` (Actions disabled per project memory;
> badge would render "no status" on a public repo) + synthetic-by-construction
> callout added per ADR 0024 § precondition; `ROADMAP.md` Phase 2
> `vocabulary-drift-auditor` § Killed entry updated (pytest invariant
> prototyped but deliberately not landed; enforcement reverts to PR review per
> ADR 0033 § Negative consequences).
>
> Four boss-decisions ratified before work began: D1 — accept v7.0.12/v7.0.13
> split (YES); D2 — delete install scripts (not rewrite); D3 — CONTRIBUTING.md
> tone work is Phase-3 debt; D4 — CI badge remove (Actions disabled).
>
> No `src/` logic changes; no schema changes; no public API changes; no
> router/security/child/vault/CLI architecture changes. Patch bump. Gates:
> 940/940 pytest, ruff clean, 76/76 probe, CLI smoke clean.
> mcp-protocol-auditor NOT TRIGGERED (no framework/router/security/vault paths
> touched; runner.py edit is string-literal + docstring only). cue-card-
> rehearsal-auditor NOT TRIGGERED (no CUE_CARD.md or ToolDefinition schema
> changes). recipient-install-validator NOT TRIGGERED (no ADR 0028 trigger
> glob paths modified; v6.11.x falsification grounds the opt-in skip).

> **v7.0.11 (2026-05-12)** — Governance/doc-truth patch. AI economics
> restored as top-billed framing per [ADR 0029](docs/adr/0029-token-reduction-as-analytical-quality.md)
> (Amended 2026-05-12). The v6.12.0 "Token efficiency is a useful side
> effect… not the headline" demotion sentence in CLAUDE.md § "Problems
> this is built against" was a drift downstream of what ADR 0029 actually
> decided ("token reduction as analytical quality, not JUST cost
> optimization"). This patch restores the framing under the boss's
> preferred umbrella name **AI economics** — a label that generalises
> across deployment recipes and doesn't date with cheaper models.
>
> ADR 0029 amended (new `## Amendment 2026-05-12 — AI economics as
> umbrella claim` section, ~90 lines): names the umbrella + three faces
> (analytical quality / cognitive amplification / cost-per-question as the
> same lever), the doc-truth cascade motivating this patch, and a symmetric
> reversal condition (if two independent published benchmarks show frontier
> models performing comparably on raw-stream context vs. structured summaries
> at sub-10k-token loads, retire the AI-economics claim and revert to
> "useful side effect"). CLAUDE.md § "Problems this is built against" gains
> a 4th named problem: "AI economics — structured answers instead of raw
> streams mean the AI's context goes to reasoning over the question, prior
> work, and audit trail rather than parsing data. The same architectural
> choice that satisfies the data-governance problem also makes the AI
> materially better at the question and reduces cost-per-question by 10–100×
> (ADR 0029, Amended)." Demotion sentence deleted. README hero clause
> updated: bold lead now ends with "…and turns a $200/month AI bill into a
> $2/month one while making the AI materially better at your question"; new
> bold sentence explains the mechanism. demo `runner.py` Section 3 closing
> prose + closing summary bullet sharpened from "analytical quality, not
> just billing" / "Tier 1 wins on analytical quality, not just on cost" →
> "analytical quality AND AI economics (cost-per-question and
> context-per-question are the same lever)". Prose-only changes inside
> `print()` calls; no logic changes.
>
> No `src/` logic changes; no schema changes; no public API changes; no
> router/security/child/vault/CLI architecture changes. Patch bump. Gates:
> 946/946 pytest, ruff clean, 76/76 probe, CLI smoke clean.
> mcp-protocol-auditor NOT TRIGGERED (no framework/router/security/vault
> paths touched; runner.py edit is print()-call prose only).
> cue-card-rehearsal-auditor NOT TRIGGERED (no CUE_CARD.md or ToolDefinition
> schema changes). recipient-install-validator SKIPPED (runner.py is in
> ADR 0028 trigger globs but edit is print()-call prose only — no
> install-path logic touched; v6.11.x falsification grounds the opt-in skip
> per v6.11.1 policy; v7.0.10 set the precedent for framing-only patches).

> **v7.0.10 (2026-05-12)** — Docs-only patch. README install-path
> framing + ROADMAP preamble swept to align with Phase 0 lenient-read
> closure (2026-05-12). The install commands themselves
> (`uv tool install git+...tailor-mcp.git` + `tailor tour`) were
> already correct post-rename; what was stale was the editorial framing
> around them — six callouts and table rows in `README.md`, plus two
> present-tense prose blocks in `ROADMAP.md` (the preamble at lines
> 18-26 and the Phase 0 section opener at lines 73-89) that both
> asserted *"no install has succeeded"* in present tense. The
> release-shipper's BORDER NOTE on the v7.0.10 initial PR flagged the
> ROADMAP preamble; the diff was expanded to sweep both ROADMAP blocks
> together so the same defect doesn't reproduce on the next pass.
> Anchor fix: four README cross-references to the Phase 0 ROADMAP
> header repointed to `#at-a-glance` (the Phase 0 header acquired a
> `*(closed…)*` suffix that rewrote its anchor). ADR count refreshed
> 31 → 34 (docs/adr/ counts verified). Closes the last active Phase 1
> ROADMAP deliverable ("Update README install commands to reflect the
> install path that survived Phase 0"); all four Phase 1 deliverables
> are now landed and Phase 2 unblocks. No `src/` or `tests/` changes;
> no public API changes; no router/security/child/vault/CLI
> architecture changes. Patch bump. Gates: 940/940 pytest, ruff clean,
> 76/76 probe, CLI smoke clean. mcp-protocol-auditor NOT TRIGGERED.
> cue-card-rehearsal-auditor NOT TRIGGERED. recipient-install-validator
> SKIPPED (README.md and ROADMAP.md not in ADR 0028 trigger globs;
> v6.11.x falsification grounds the skip).

> **v7.0.9 (2026-05-12)** — Governance/CLI-surface patch. `tailor migrate` subcommand
> and its associated startup warning retired per [ADR 0034](docs/adr/0034-retire-tailor-migrate-subcommand.md)
> (NEW, Accepted). The v6 → v7 migration population was empirically zero: no successful
> external v6 install ever happened across the v6.10.x patch quartet, the v6.11.x
> falsified recipient-install-validator, the 2026-05-09 self-driven Windows install, or
> the 2026-05-12 first true outside-recipient macOS install. `cmd_migrate`,
> `_emit_legacy_migration_warning_if_applicable`, and `_legacy_config_dir` deleted from
> `src/tailor/__main__.py`; `"migrate": cmd_migrate` removed from dispatch dict;
> startup-warning call removed from `main()`; module docstring row removed. `README.md`
> migrate row removed. [ADR 0031](docs/adr/0031-rename-to-tailor-and-wardrobe.md) status
> updated: now Superseded in part by ADR 0033 AND ADR 0034 (migration story closed;
> naming decisions and workshop-metaphor invariant retained). `ROADMAP.md` Phase 1
> struckthrough rows and v7.0.0 Shipped entry forward-cited to ADR 0034.
> `docs/diagnosis/phase-0-diagnosis-kit.md` Expected list updated. No
> router/security/child/vault/CLI architecture changes; no tests changed. Patch bump.
> Gates: 940/940 pytest, ruff clean, 76/76 probe, CLI smoke clean (7 commands, no
> `migrate`). mcp-protocol-auditor NOT TRIGGERED. cue-card-rehearsal-auditor NOT
> TRIGGERED. recipient-install-validator SKIPPED (`__main__.py` in trigger globs but
> change is pure deletion, no new install-path code; v6.11.x falsification + 2026-05-12
> macOS recipient install are the empirical substitute).

> **v7.0.8 (2026-05-12)** — Governance/team-shape patch. Phase 0 (install-path
> validation) closes under the lenient read of the [ROADMAP.md](ROADMAP.md)
> exit criterion at lines 99–100. Strict read requires two consecutive fresh-machine
> installs by outside recipients on different OSes; the 2026-05-09 Windows attempt
> was self-driven diagnosis on the boss's own machine (fresh user account, but
> boss-driven), and the 2026-05-12 macOS attempt was the first true outside recipient
> (friend installed, boss watched only). Lenient read: 2026-05-09 proved the
> technical install path on Windows-Store-Claude; 2026-05-12 proved the
> recipient-experience path on macOS; the EXIT INTENT — uninvolved third parties
> can install it — is satisfied. Boss made the closure call; protocol-4 conflict
> was surfaced before ratification.
>
> Phase 1 (ship-quality housekeeping) unblocks. The highest-leverage Phase 1
> deliverable is `tailor migrate` removal per ROADMAP framing — scaffolding for a
> v6 user population that turned out to be zero (validated by the 2026-05-12
> project-memory note on the hand-patched migrate path-rewrite gap). No `src/` or
> `tests/` changes; no schema changes; no public API changes; no
> router/security/child/vault/CLI architecture changes. Patch bump. ROADMAP.md
> Phase 0 and Phase 1 status rows + section headers updated. Gates: 940/940
> pytest, ruff clean, 76/76 probe, CLI smoke clean. mcp-protocol-auditor NOT
> TRIGGERED. cue-card-rehearsal-auditor NOT TRIGGERED. recipient-install-validator
> SKIPPED (no touched paths match trigger globs; v6.11.x falsification grounds the
> skip).

> **v7.0.7 (2026-05-12)** — Governance/team-shape patch. ADR 0033 (NEW,
> Accepted) completes the Tailor metaphor on the workshop side, closing the
> deferred half of ADR 0031. The counter-programming invariant (three negative
> rules about fashion language) retires; a positive workshop-shaped metaphor
> identity replaces it. ADR 0031 status flipped Accepted → Superseded in part
> by ADR 0033; naming decisions (Tailor / Wardrobe / `tailor-mcp` / `tailor` /
> `~/.tailor/`) retained.
>
> Load-bearing structural shifts: (1) **Counter-programming invariant retired**;
> replaced by the workshop-vs-lifestyle narrow-forbid list (6 always-forbidden
> words: couture, couturier, atelier, boutique, runway, showroom; 9
> lifestyle-register-only forbidden words) enforceable by grep. (2)
> **Wardrobe / Ledger split** — Audit history moves out of the Wardrobe (the
> customer's collection) to a separate Ledger (the tailor's record). The
> directory structure (`framework/audit.py` outside `framework/vault/`) already
> reflected this split before the terminology did. (3) **Six locked vocabulary
> tables** in new [`docs/design/tailor-vocabulary.md`](docs/design/tailor-vocabulary.md):
> 7 structural nouns (Tailor, Wardrobe, Threads, Fabric, Garment, Seam,
> Ledger), 12 relational verbs, service hierarchy (User → Tailor → AI/wearer),
> audience model, workshop-vs-lifestyle invariant, weak beats. (4) **Service
> hierarchy codified**: User is the principal; Tailor is the craftsperson in
> service to the user; AI is the wearer (collaborator on the team, outfitted
> by Tailor to act on the user's behalf). Boss framing: *"the real power of
> this tool should eventually circle to the human after all."*
>
> New artifacts: `docs/adr/0033-complete-tailor-metaphor-workshop-side.md`
> (~400 lines), `docs/design/tailor-vocabulary.md` (~175 lines). Amended:
> ADR 0031 (status flip + counter-programming invariant retirement closeout),
> `CLAUDE.md` § Your Wardrobe (Audit history → Ledger paragraph), `README.md`
> § Your Wardrobe (parallel split), `ROADMAP.md` (Phase 2 deliverable reshaped
> from `counter-programming-invariant-auditor` → `vocabulary-drift-auditor`
> with ADR 0033 retirement record).
>
> No `src/` or `tests/` changes; no public API changes; no
> router/security/child/vault/CLI architecture changes. Patch bump. Gates:
> ci-gate-runner SHIPPABLE (940/940 pytest, ruff clean, 76/76 probe, CLI smoke
> clean). mcp-protocol-auditor NOT TRIGGERED (no framework/router/security/
> vault paths touched). cue-card-rehearsal-auditor NOT TRIGGERED (no CUE_CARD.md
> or ToolDefinition schema changes). recipient-install-validator SKIPPED (no
> touched paths match trigger globs; v6.11.x falsification grounds the skip).

> **v7.0.6 (2026-05-09)** — Governance/team-shape patch. ADR 0032 (NEW,
> Accepted) retires the public-mirror distribution path codified in ADR 0030
> + ADR 0024 § 3.1. Wheel-handoff via personal email supersedes through Phase 1;
> GitHub Pages on source repo supersedes from Phase 2 PyPI publish onward. Boss
> framing: *"the public mirror is unneeded at this point since I can just send a
> wheel file from the private repo to anyone up until phase 1 when the pages
> become unnecessary anyways."* Mirror repo `saahasmuthineni/biosensormcpdemo`
> archived (not deleted) via `gh repo archive` on 2026-05-09 — legacy URL still
> resolves with the v6.13.0 snapshot for in-flight friend-shares; archive is
> reversible at any time via GitHub web UI.
>
> ADR 0030's zero-outbound-affordances rendering invariant is retained in full:
> the render-time URL allowlist at `src/tailor/demo/runner.py:336-365`, the
> per-persona panel schema at `src/tailor/demo/_personas.json`, the
> `--audience=public` flag, and the attribution-only footer copy all remain
> unchanged. ADR 0030 was two decisions in one file; ADR 0032 retires the first
> (distribution shape) and keeps the second (render shape). ADR 0030 status
> flipped Accepted → Superseded by ADR 0032 (in part). Cascade edits in feature
> commit `702fd97`: ADR 0030 status flip, ADR 0024 § 3.1 retirement closeout
> footer, `docs/guides/share-the-demo.md` rewritten as wheel-by-email path.
>
> No router/security/child/vault/CLI architecture changes; no `src/` or `tests/`
> changes; no public API changes. Patch bump. Gates: ci-gate-runner SHIPPABLE
> (940/940 pytest, ruff clean, 76/76 probe, CLI smoke clean).
> mcp-protocol-auditor NOT TRIGGERED. cue-card-rehearsal-auditor NOT TRIGGERED.
> recipient-install-validator SKIPPED (no touched paths match trigger globs;
> v6.11.x falsification grounds the skip).

> **v7.0.5 (2026-05-10)** — GitHub repo renamed `Biosensor-to-LLM-Connector` →
> `tailor-mcp` (closes [ADR 0031](docs/adr/0031-rename-to-tailor-and-wardrobe.md)
> § Negative consequences known-debt entry). Codebase doc-truth pass updating
> Project URLs in `pyproject.toml`, CI badge + install commands + clone
> instructions in `README.md`, install command in `CLAUDE.md` Running and
> Testing §, install commands in `docs/guides/multi-subject-pilot.md`,
> install command in `docs/diagnosis/phase-0-diagnosis-kit.md` (A6; local-FS
> dev-box paths at lines 43 and 209 intentionally preserved as working-copy refs),
> issues URL in `docs/external-review.md`, `TAILOR_CONFIG_DIR` example path in
> `examples/hip_lab_demo/beta/README.md`, migration-story URL + § Negative
> consequences known-debt closeout sub-bullet in
> `docs/adr/0031-rename-to-tailor-and-wardrobe.md`, and Phase 1 strikethrough
> row in `ROADMAP.md`. GitHub auto-redirect preserves existing clones.
> Vault project-folder cross-link (`projects/tailor/index.md`) updated
> out-of-band via Obsidian MCP.
>
> No `src/` changes; no test changes; no public API changes. Patch bump.
> Gates: ci-gate-runner SHIPPABLE (940/940 pytest, ruff clean, 76/76 probe,
> CLI smoke clean). mcp-protocol-auditor NOT TRIGGERED (no
> framework/router/security/vault paths touched). cue-card-rehearsal-auditor
> NOT TRIGGERED (no CUE_CARD.md or ToolDefinition schema changes).
> recipient-install-validator SKIPPED (opt-in heavyweight; v6.11.x
> falsification documented in project memory grounds the skip per v6.11.1
> opt-in policy).

> **v7.0.4 (2026-05-10)** — Phase 0 deliverable 2 patch (PATCH not
> RESTRUCTURE per the 2026-05-09 self-driven diagnosis). Closes the four
> findings the two attempts surfaced against `tailor tour` and the
> diagnosis kit. Single-file framework change, three doc/kit changes,
> seven new regression tests.
>
> **F4 (Phase 0, architectural — `tour.py`)**: `tailor tour` now detects
> Claude Desktop presence BEFORE registration (must run before the
> writer's lazy `%APPDATA%\Claude\` mkdir, which would otherwise hide
> the absent case via the framework's own side effect). New
> `_detect_claude_desktop_presence()` checks the classic config dir on
> Windows + every UWP `Claude_*` package dir + the macOS Application
> Support dir; Linux always returns False. When absent, the success
> banner prints `Tour scaffolded; Claude Desktop NOT DETECTED` with an
> install pointer instead of the misleading `"fully quit Claude Desktop,
> then re-open it"` ritual the recipient cannot perform. Tour still
> stages the config (per ADR 0026 § "First-time-install on a Store-only
> machine") so a future Claude Desktop install picks it up
> automatically; the verb in the banner shifts from `registered as ...`
> to `staged as ...` to be honest about what the framework actually did.
>
> **F5 (Phase 0, documentation — `tour.py` + `README.md`)**:
> tour-success message and README "what success looks like" both
> preempt the visual-asymmetry confusion attempt 2 surfaced — Claude
> Desktop renders Spotify as a green-card connector but Tailor as a
> "session-scoped server" in prose. Tailor cannot change Claude
> Desktop's UI; both surfaces now warn the recipient that the prose
> rendering is the normal local-MCP shape, not a degraded install.
>
> **F2 (kit-instrument — `phase-0-diagnosis-kit.md`)**: per-command
> `Tee-Object -Append` advice promoted from the deeper-buried capture
> protocol § 1 into the install-checklist itself, inline at every
> `tailor` invocation (A7, A8, A9, A13). Closes the PowerShell-5.1
> transcript-gap workaround that was only discoverable post-hoc on
> attempt 1 + 2.
>
> **F3 (documentation — `README.md`)**: Prerequisites section split
> into recipient-install (uv + Claude Desktop; Python on PATH **not**
> required — uv provisions its own) vs. developer-install (Python 3.10+).
> The earlier monolithic "Python 3.10+" claim led the attempt-1
> recipient to treat `python --version` returning command-not-found as
> a hard prerequisite failure even though `uv tool install` succeeded
> immediately afterward.
>
> Naming-collision fix: the 2026-05-09 snapshot referred to the
> deferred `_extract_timestamps` paired-iteration helper bug as "F4",
> colliding with Phase 0's structured F1–F5 finding labels. Renamed
> the legacy item to `_extract_timestamps` paired-iteration helper
> (the v6.10.1 banner already used "Bug 4", not "F4"). Phase 0
> F1–F5 stays canonical.
>
> Version sync: `__init__.py` was at `6.13.0` while `pyproject.toml`
> was at `7.0.0` (drift from the v7.0.0 rename's mechanical pass).
> Both now read `7.0.4`.
>
> Gates: pytest +7 new regression tests in
> `TestClaudeDesktopPresenceDetection` (5),
> `TestSuccessBannerHonestyOnAbsentClaudeDesktop` (3),
> `TestConnectorVsServerFraming` (2). No router/security/child/vault
> architecture changes; no public API changes; patch bump.
> mcp-protocol-auditor NOT TRIGGERED (no framework/router/security/vault
> paths touched). recipient-install-validator SKIPPED (v1 falsified
> per project memory; the 2026-05-09 self-driven diagnosis is the
> empirical substitute on this round).

> **v7.0.0 (2026-05-08)** — Project rename: `Biosensor MCP` → **Tailor**.
> The PyPI distribution is `tailor-mcp` (the bare `tailor` was taken on
> PyPI); the Python import name is `tailor` (`from tailor import ...`),
> the CLI command is `tailor` (e.g. `tailor serve`, `tailor tour`,
> `tailor demo`). Configuration paths move from `~/.biosensor-mcp/` to
> `~/.tailor/`; environment variables move from `BIOSENSOR_*` to
> `TAILOR_*`. A new `tailor migrate` subcommand handles the v6 → v7
> filesystem upgrade non-destructively (copies by default, `--move` to
> remove the legacy directory after copying). Claude Desktop cleanup
> logic (`_clean_claude_desktop_orphan_entries` + the new
> `_is_orphan_entry_key` matcher) cleans BOTH legacy `biosensor-*` keys
> AND current `tailor` / `tailor-*` keys so v6 → v7 upgrades don't leave
> orphan entries pointing at a removed binary.
>
> Engine word: **Wardrobe** (replaces the working term "substrate" used
> in design conversations). Wardrobe is the user-facing term for what
> the framework holds on the user's behalf — themes, moments, evidence,
> audit history, source data — the structured personal collection that
> lives entirely on the user's machine. Wardrobe pairs with Tailor as
> place-shape + character-shape (your Tailor curates your Wardrobe).
> Counter-programming commitment per ADR 0031: visual language stays
> non-fashion (no fabric / garment imagery, no haute-couture aesthetic)
> and onboarding copy actively redirects the literal-clothing read
> ("not clothes — your stuff"). Future contributors who drift toward
> fashion-domain language are in conflict with ADR 0031.
>
> Historical preservation: `CHANGELOG.md`, the 2026-05-05 vault moment
> file, and `docs/reports/*-2026-05-01.md` retain the legacy
> `biosensor-mcp` / `Biosensor MCP` references — they describe past
> state under the old name, and rewriting them would falsify the
> historical record. New release notes (this banner, ADR 0031, future
> changelog entries) use the new name.
>
> Structural changes: package directory renamed (`src/biosensor_mcp/`
> → `src/tailor/` via `git mv`, history preserved); 1,400+ string
> occurrences across ~120 files updated mechanically; 6 cleanup tests
> migrated to dual-prefix semantics; +13 net new tests verifying the
> migration matcher contract directly. Major version bump because
> package import name, CLI command, env vars, default paths, and
> Claude Desktop registration keys all changed — every existing v6
> install needs the new install command + a one-time migration. ADR
> 0031 codifies the rename, the Wardrobe naming decision, the
> counter-programming invariant, and the migration story.
>
> Gates: ci-gate-runner PASS (930/930 pytest, ruff clean, 76/76 probe,
> CLI smoke clean). mcp-protocol-auditor NOT TRIGGERED (no
> framework/router/security/vault behavioural paths touched — only
> import names changed). cue-card-rehearsal-auditor NOT TRIGGERED
> (CUE_CARD.md got the mechanical rename pass but no schema changes).
> recipient-install-validator SKIPPED (opt-in heavyweight; rename
> directly affects the recipient-install path so it would normally
> fire, but per v6.11.x falsification documented in project memory
> the validator silently parks; ADR 0031 documents the operator
> hand-validation path until ADR 0028's v2 escalation lands). Major bump.

> **v6.13.0 (2026-05-08)** — ADR 0030 (Public-mirror narrative + zero-outbound-affordances)
> lands with the `--audience=public` rendering shape for `tailor demo`. Per-persona
> panels (PI / analyst / IRB) are spliced after each of the 5 demo sections, attribution-only
> footer replaces dead-link breadcrumbs, and a render-time URL-allowlist hard-fail enforces
> the new zero-outbound-affordances invariant — a future contributor adding a Discord link
> gets a CI failure rather than a quietly-shipped public page.
>
> The integration-auditor REVISE → revise loop surfaced two significant findings before
> ship: F2 — the boss's personal email almost shipped onto a search-indexed public page;
> resolved by the boss's reframe ("my email doesn't need to go there; this demo should only
> work for people who know me personally; my name is enough") — replaced with zero-outbound
> + name-only attribution pattern. C1 — a recipient-threshold contradiction between ADR 0030
> prose and ADR 0024 § 3.1's ~10-evaluator threshold; resolved by trimming the ADR 0030
> framing rather than raising the threshold. Both findings are in the ADR 0030 decision
> record.
>
> Structural artifact: `src/tailor/demo/_personas.json` — a new single-source
> canonical schema for PI/analyst/IRB persona definitions + per-section panels for the 5
> demo sections (closes integration-auditor F1: personas were previously split across the
> researcher-utility-reviewer agent and inline runner logic). Shipped in the wheel via a
> `pyproject.toml` package-data glob extension.
>
> Gates: ci-gate-runner PASS (923/923 pytest, ruff clean, 76/76 probe, CLI smoke clean,
> 84% coverage). mcp-protocol-auditor NOT TRIGGERED (no framework/router/security/vault
> paths touched). cue-card-rehearsal-auditor NOT TRIGGERED (no CUE_CARD.md or ToolDefinition
> schema changes). recipient-install-validator SKIPPED (opt-in heavyweight; `__main__.py`
> change is CLI-flag-parser-only, not tour/pilot/wizard logic; v6.11.x falsification
> documented in project memory grounds the skip per v6.11.1 opt-in policy). ADR 0030 cites
> ADRs 0011 / 0024 / 0027 and the researcher-utility-reviewer persona definitions. +12 tests
> in `tests/test_demo_runner.py`; suite total now 923/923 pytest pass. Public API additions only —
> new `--audience` CLI flag, new `audience` kwarg on `run_demo`, new `_personas.json`
> resource. No router/security/child/vault/CLI architecture changes. Minor bump.

> **v6.12.0 (2026-05-08)** — `tailor demo` reshaped from a 3-call cohort
> first-look into a 5-section architectural showcase per
> [ADR 0029](docs/adr/0029-token-reduction-as-analytical-quality.md) (NEW, Proposed
> → Accepted on this ship): *"Token reduction is analytical quality, not just cost
> optimization; the demo demonstrates the architecture, not only the cohort thesis."*
> Section 1 preserves the ADR 0027 invariant (cohort thesis, `csv_cohort_summary` ×2 +
> `csv_force_decline` via `child.execute()`, no Strava data). Sections 2–5 exercise the
> framework's remaining load-bearing claims in sequence: Section 2 makes the router
> pipeline visible (`csv_summary_report` via `RouterMCP._dispatch`, prints `_meta` block
> + tails `audit.db` row with `subject_id="S001"` — ADR 0001); Section 3 walks the
> three-tier resolution model on a single question (Tier 1 scalar / Tier 2
> consent-gated downsampled / Tier 3 cost-gated raw — ADR 0005, demo router uses
> `cost_threshold=15_000` so bundled S001 fixture trips the gate); Section 4 writes a
> vault moment scoped to `subject_id="S001"` and prints the markdown source-of-truth
> (durable cross-session memory — ADR 0001 / ADR 0008); Section 5 calls
> `ask_local_oracle` with `NullBackend` and shows `related_substrate` auto-populated
> by the ADR 0023 substrate scan finding the Section 4 moment. New `--save-shareable
> [PATH]` CLI flag tees stdout into a self-contained markdown file (install command +
> transcript + breadcrumb footer) — suitable for emailing or static hosting. ADR 0024
> § 3.1 amended to codify a public release-only mirror at
> `saahasmuthineni/biosensormcpdemo` (GitHub Pages `https://saahasmuthineni.github.io/
> biosensormcpdemo/` verified live) as a friend-shareable distribution carve-out
> alongside Drive/email; source-repo privacy + synthetic-by-construction preconditions
> preserved. ADR 0027 header amended with "Partially superseded by ADR 0029"
> forward-cite. `recipient-install-validator` Step 6 assertion list updated for the
> new five-section demo output. New `docs/guides/share-the-demo.md` checklist for
> boss-side public-mirror setup ritual. +11 tests (898 → 909). Framework ADRs exercised
> by the demo: 0001 / 0005 / 0008 / 0022 / 0023 / 0027 / 0028 / 0029. No
> router/security/child/vault/CLI architecture changes beyond the demo runner rewrite
> and `--save-shareable` CLI flag addition. Minor bump.
>
> **v6.11.1 (2026-05-07)** — Post-first-wild-run amendment batch: governance/team-shape
> patch, no `src/` changes, no breaking API changes, no router/security/child/vault/CLI
> architecture changes. Five-file diff (+192/-15). Three ADR enforcement amendments: ADR
> 0016 (`mcp-protocol-auditor`) and ADR 0025 (`cue-card-rehearsal-auditor`) gain
> release-shipper attestation as the enforcement mechanism replacing the prior
> "mandatory before every release" prose; ADR 0028 (`recipient-install-validator`) gains
> operational hardening (halt-on-exit semantics, watcher discipline, progress emission)
> and a mandate-refinement section. `release-shipper` agent gains a "Pre-tag gate
> composition" section implementing a tiered policy: `ci-gate-runner` (mandatory, always),
> `mcp-protocol-auditor` + `cue-card-rehearsal-auditor` (attestation-required on affected
> paths, skippable with `--gates-confirmed`), `recipient-install-validator` (heavyweight
> opt-in, skippable with `--full-validate` flag). `recipient-install-validator` agent
> prompt hardened with halt-on-exit contract, structured progress emission, and watcher
> discipline for Windows Defender / AV interference. No `src/` changes; 898/898 pytest,
> ruff clean, 76/76 probe, CLI smoke PASS. Includes pending governance edits per ADRs
> 0016 / 0025 / 0028 (agent table row + ADR enforcement amendments + validator hardening).
> Patch bump.
>
> **v6.11.0 (2026-05-07)** — `recipient-install-validator` specialist + ADR 0028 land as a
> single bundled governance/team-shape release. Codifies the structural class of failure
> that produced the v6.10.1–v6.10.4 patch quartet: bugs that only appear when someone
> other than the developer installs the wheel on a clean Windows machine — cp1252 character
> crashes, degraded Claude Desktop configs, stale MCP server entries, dual config-path
> misses. The new specialist (`recipient-install-validator`, opus model) provisions a clean
> Windows 11 VM via VirtualBox + Vagrant, installs the freshly-built wheel via the
> documented recipient command, runs `tailor tour`, and verifies the install
> end-to-end against the wheel-installed package on a foreign machine — host-side gates
> running against the dev tree cannot see these failures. Gate is mandatory +
> file-touched-gated: fires when any of `tour.py`, `pilot.py`, `__main__.py`, `wizard.py`,
> `pyproject.toml` package-data globs, or `_fixtures/**` changes. ADR 0028 codifies the
> structural argument under ADR 0011's promotion policy, the eight-step install-ritual
> assertion list, and six alternatives considered + rejected. Accepted v1 gap named
> explicitly: no Claude Desktop pre-installed in base image, so ADR 0026 dual-write logic
> is exercised by mocked unit tests on host but not on a real Windows guest; v2 escalation
> path named in ADR 0028. VirtualBox 7.2.8 + Vagrant 2.4.9 empirically validated on Win 11
> Home despite `VirtualMachinePlatform = Enabled`; `boot_timeout=1800s` baked in (Hyper-V
> emulation mode is the reason). No `src/` changes, no `tests/` changes, no router/
> security/child/vault/CLI architecture changes. Pure governance/team-shape release.
> Includes pending governance edits per ADR 0028 (agent table row + ADR file). 898/898
> pytest, ruff clean, 76/76 probe, CLI smoke PASS. Minor bump.
>
> **v6.10.5 (2026-05-07)** — `tailor demo` reframed from
> synthetic-Strava operator self-verification to bundled HIP Lab cohort
> fixtures researcher first-look per [ADR 0027](docs/adr/0027-demo-as-researcher-first-look.md).
> The pre-v6.10.5 demo ran `run_demo` against synthetic Strava running
> streams, silently positioning the running child (Strava) as canonical
> for the entire v6.x cycle — a structural contradiction with CLAUDE.md's
> explicit framing that "Strava is a worked example… retained for teaching
> value; not the canonical use case." Boss surfaced the drift 2026-05-06.
> `src/tailor/demo/runner.py` rewritten: copies bundled
> `_fixtures/hip_lab_demo_realistic/force/` (16 synthetic subjects +
> `metadata.json` sidecar) into a tempdir, instantiates
> `CSVDirectoryChild`, exercises `csv_cohort_summary` (by sex, by group)
> + `csv_force_decline` on pinned subject S001 via `child.execute()`.
> Printed output is the real result envelope shape; closing prose names
> what the demo exercises (server-side computation, deterministic
> reproducibility per ADR 0008) and what it does not (router pipeline /
> audit / consent gates — pointer to `tailor tour` for the full
> router-mediated path). `demo/sample_data.py` preserved untouched per
> ADR 0008 § Alternatives explicit-rejection-of-removal clause.
> Deferred `demo` → `verify` rename KILLED: under the researcher-first-
> look reframe a surface named `verify` would be wrong; the deferred
> ROADMAP item is rewritten as KILLED with explanation in ADR 0027 §
> Negative consequences. Doc-truth drift cleanup: 9 recipient-visible
> drift sites patched (README.md ×3, CONTRIBUTING.md, tour.py module
> docstring, ROADMAP.md ×2, docs/guides/claude-desktop-demo.md ×2) —
> all caught by `red-team-reviewer` adversarial pass (ADR 0010). One
> known debt: `docs/assets/demo.svg` is an orphan asset still showing
> pre-v6.10.5 framing; not on first-look path; queued for a future
> doc-pass per ADR 0027 § Negative consequences. Release-pass agents:
> `ci-gate-runner` SHIPPABLE (898/898 pytest, ruff clean, 76/76 probe,
> CLI smoke PASS); `researcher-utility-reviewer` RESHAPE → resolved
> (PI LOAD-BEARING medium, analyst LOAD-BEARING medium, IRB audit-log
> over-claim trimmed); `red-team-reviewer` OBJECTION (medium) → resolved
> via 9-site doc-rename pass and ADR 0027 amendment. +8 tests in
> `tests/test_demo_runner.py` (890 → 898). No router / security / child /
> vault / CLI architecture changes. Patch bump.
>
> **v6.10.4 (2026-05-06)** — Dual-path Claude Desktop config resolution
> closes the Microsoft Store / Classic install mismatch on Windows. The
> Microsoft Store version of Claude Desktop runs in a UWP container that
> silently redirects `%APPDATA%\Claude\` to a per-package sandbox at
> `C:\Users\<user>\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\`.
> Pre-v6.10.4 wrote only the unredirected classic path; Store-installed
> Claude Desktop read from the sandbox; the recipient saw a "successfully
> registered" message and no biosensor tools after restart. Boss reported
> hitting this "a million times since day one"; dad hit it on the
> v6.10.3 install path tested 2026-05-06. Fix: `_claude_desktop_config_path()
> -> Path | None` refactored into `_claude_desktop_config_paths() ->
> list[Path]`. Windows: classic always included (created lazily on first
> write); Store sandbox paths included via prefix-glob
> `%LOCALAPPDATA%\Packages\Claude_*\LocalCache\Roaming\Claude\` — one
> entry per matching UWP package. New `_RegistrationResult` dataclass +
> shared `_write_registration_to_path` helper enforce per-path atomic
> semantics (read → clean siblings → add entry → atomic write), each path
> wrapped in try/except. PermissionError on one path does not abort writes
> to others; exit code 1 only if every path failed; `.tmp` artifacts
> unlinked on partial failure. `cmd_status` reframed to surface recovery
> instructions instead of engineering jargon. Three duplicated Windows
> branches in `__main__.py` collapsed into the single helper. Invariant
> locked: after a successful `tour --force`, exactly one `biosensor-*`
> entry exists in EACH detected Claude Desktop config; the entry is
> identical across configs. ADR 0026 NEW (cites ADRs 0010 / 0014 / 0024);
> ADR 0024 amended at lines 116 and 285 with historical-context framing.
> Release-pass agents: `integration-auditor --proposal-mode` REVISE (3
> BLOCKING + 5 IMPORTANT addressed in code before any Edit landed);
> `ci-gate-runner` SHIPPABLE (890/890 pytest, ruff clean, 76/76 probe,
> CLI smoke PASS); `red-team-reviewer` OBJECTION (medium) on
> release-artifact completeness + ADR 0024 stale-reference doc-truth —
> both addressed. CUE_CARD.md gains two new recovery rows for the
> dual-path surface. 876 → 890 tests (+14). No
> router/security/child/vault/CLI architecture changes; no public API
> changes; patch bump.
>
> **v6.10.3 (2026-05-06)** — Tour cleans sibling biosensor-* entries
> before adding its own. Closes the multi-entry coexistence trap surfaced
> by dad's 2026-05-06 post-v6.10.2 debrief: a recipient who had a bare
> `tailor` entry (no env block, no demo tools — written by
> web-Claude-mediated debugging during a failed v6.9.x install) would end
> up with TWO MCP servers after `tour --force`: the stale bare entry plus
> the new `biosensor-tour-<variant>` entry. With two servers both
> registered, `tailor_setup_help` leaked into the working-demo state,
> breaking the "invisible on a working demo" invariant the v6.10.2
> cue-card-rehearsal audit blessed. Fix: `_register_with_claude_desktop`
> strips every `biosensor-*` key from `mcpServers` (except the entry being
> written) before writing its own — symmetric with v6.9.2's prefix-match
> cleanup in `cmd_uninstall`. UX side effect: dad's recovery now takes two
> commands (`pip install --upgrade` + `tour --force`) instead of three
> (`uninstall` + `pip install` + `tour`). +2 regression tests in
> `TestClaudeDesktopRegistration`. 876/876 pytest, ruff clean, 76/76
> probe, CLI smoke PASS. No router/security/child architecture changes; no
> public API changes. Patch bump.
>
> **v6.10.2 (2026-05-06)** — Recipient-failure structural patch.
> Closes the v6.9.x failure loop where a `tailor tour` crash
> routed the recipient via web-Claude into a degraded `serve` state with
> no demo tools surfaced (dad's transcript: tour crash → web-Claude
> inspect → manual `serve` config → ask_local_oracle + strava_list_runs
> only → cue-card prompts fail on every csv_dir tool). Two structural
> fixes: (1) `SetupHelpLayer` — a new framework-tier layer parallel to
> `LocalLLMLayer` (per ADR 0022 shape) registered conditionally when
> `_demo_blocks_absent()` detects no `csv_dir` blocks in
> `user_config.json`. Surfaces a single diagnostic tool
> (`setup_help_get_status`) that tells an external Claude "run
> `tailor tour`", invisible on configured deployments. Home
> lat/lng redacted via `_redact_home()` (HIPAA Safe Harbor
> §164.514(b)(2)(i)(R)) before surfacing on the wire. (2)
> `RECIPIENT_README.md` bundled in the wheel (`pyproject.toml` `*.md`
> glob added to package-data) so an external Claude inspecting the .whl
> discovers `tailor tour` without source-code archaeology. ADR
> 0012 amended: Decision section extended to cover all three
> framework-tier PHI-scrubber bypass sites (vault + local_llm +
> setup_help) with per-layer invariants and reversal conditions; closes
> phi-irb-risk-reviewer Lens 4 finding. CUE_CARD.md recovery row added
> for the "tool list shows only ask_local_oracle + strava_list_runs"
> symptom. Release-pass agents: cue-card-rehearsal-auditor REHEARSAL OK
> (both configs, no regression); reproducibility-provenance-auditor CLEAN
> (ADRs 0001/0002/0003/0008 all HOLD); phi-irb-risk-reviewer WATCH ×2 —
> both addressed; mcp-protocol-auditor PROTOCOL OK (7 SH wire-tests
> SH1-SH7); ci-gate-runner PASS (874/874 pytest, ruff clean, 76/76
> probe, CLI smoke PASS). Tool surface: 50 when degraded (setup_help
> visible), 49 when scaffolded (baseline unchanged). Bug fixes +
> framework-tier layer addition; no router/security/child/vault/CLI
> architecture changes beyond the new framework-tier layer. Patch bump.
>
> **v6.10.1 (2026-05-06)** — Windows recipient resilience patch.
> Hardens four cp1252 / fresh-tour-install blockers caught during direct
> recipient testing of `tailor tour` on Windows 11 PowerShell
> cp1252: Bug 1 (`→` → `->` in `cmd_status`), Bug 2 (try/except
> sqlite3.OperationalError around the activities/streams SELECT — fresh
> tour install has no Strava-tier tables), Bug 3 (`←` → `<-` in
> `pilot.py`), Bug 5 (`❌`/`✅` → `[X]`/`[OK]` in `wizard.py`). New
> private helper `_make_cli_stdout_resilient()` in `__main__.py` adds a
> 3-layer defense (glyph swap + runtime stdout reconfigure + static guard
> at PR time); +17 regression tests (851 total); +8 subprocess tour-path
> MCP wire tests covering the previously-untested force_csv + emg_csv
> round-trip surface. Bug 4 (`_extract_timestamps` silent index-
> misalignment after red-team-reviewer HIGH OBJECTION) deferred to
> v6.11.0. ADR 0010 adversarial pairing demonstrably caught what
> confirmation-shape dispatch would have shipped: F4 silent index-
> misalignment (HIGH; reverted), wizard.py present-tense glyphs
> (medium; closed), demo/runner.py guard scope omission (low; closed).
> No router/security/child/vault/CLI architecture changes. Bug fixes
> only; no public API changes. Patch bump. Gates: 851/851 pytest, ruff
> clean, 76/76 probe, CLI smoke PASS.
>
> **v6.10.0 (2026-05-06)** — `cue-card-rehearsal-auditor` specialist +
> ADR 0025 land as a single bundled governance/team-shape release.
> Codifies the structural class of failure that produced both v6.9.1
> and v6.9.2 in the same week: schemas under-specified for
> prompt-driven parameter inference, invisible to gates that measure
> structural envelope correctness without inspecting payload semantics.
> New read-only specialist (`cue-card-rehearsal-auditor`, opus model,
> tools: Read/Grep/Glob) audits cue-card prompts against candidate
> ToolDefinition schemas and emits per-prompt verdicts (PASS /
> WRONG-TOOL / WRONG-PARAMS / AMBIGUOUS). First-run dogfood evidence
> is in [ADR 0025](docs/adr/0025-cue-card-rehearsal-as-release-gate.md)
> — REVIEW aggregate verdict with AMBIGUOUS on Step 2 cohort prompt,
> demonstrating the gate works without reaching past the schema into
> the v6.9.1 handler resolver. Promotes the cue card from one-off
> demo aid to load-bearing release artifact (descriptive, not
> aspirational — the v6.9.1 recovery rows at CUE_CARD.md:55-68
> already encoded this). Mandatory pre-tag trigger via
> `release-shipper`. Same governance/team-shape release shape as
> v6.3.0 (four new specialists that session, one new specialist here);
> no framework code changes, no router/security/child/vault/CLI
> architecture changes. ADR 0025 cites ADRs 0008, 0010, 0011, 0014,
> 0016. Gates: 834/834 pytest, ruff clean, 76/76 probe, CLI smoke
> PASS. Minor bump.
>
> **v6.9.2 (2026-05-06)** — Three v6.9.0 footguns hardened after the
> 2026-05-05 operator-vault wheel-review moment elevated them from
> "non-blocking" to load-bearing on the first real recipient debugging
> path. (1) `cmd_uninstall` now prefix-matches `biosensor-` so
> `biosensor-tour-<variant>` orphan entries are cleaned alongside
> `tailor` (red MCP indicator after clean uninstall). (2) All
> CSV-open and JSON-sidecar reads in `force_csv` (3 sites), `emg_csv`
> (3 sites), and `csv_dir` (6 sites) switched from `utf-8` to
> `utf-8-sig` for transparent BOM stripping — Excel- / PowerShell-saved
> files prepend a BOM that `utf-8` passes through as a literal prefix on
> the first-column header, silently breaking header lookups and sidecar
> filename matches. (3) `tour --force` now `rmtree`s the target dir
> before scaffolding so a broken scaffold can actually be recovered as
> `WINDOWS_QUICKSTART` documents. Structural lesson: the 2026-05-05
> moment correctly logged these as non-blocking at moment-write time,
> but "non-blocking" was the wrong assumption at next-recipient-failure
> time — two of the three bugs sat directly on dad's debugging path.
> Bug fixes only; no public API changes; no router/security/child
> architecture changes beyond the three corrected sites. +12 regression
> tests (834 total). Patch bump.
>
> **v6.9.1 (2026-05-06)** — Cohort-handler logical→physical column-alias
> resolution on `force_csv` + `emg_csv`; MRS spectra `csv_dir` block
> added to tour scaffolding. Closes the v6.9.0 first-prompt-failure
> footgun where `force_cohort_summary` / `emg_cohort_summary` returned
> 16 silent `column not found` load_errors when Claude guessed the
> logical name from operator prose (physical CSV header vs
> `value_columns` alias mismatch in `_handle_cohort_summary`). The 16
> 31P-MRS CSVs bundled in the wheel were unreachable after tour
> scaffolding because no `csv_dir` block was written for `mrs/` in
> `user_config.json`; now registered. 6 new regression tests: 2 in
> `TestCohortSummaryAliasResolution` on `force_csv`, 2 sibling tests on
> `emg_csv`, 1 updated user_config-shape assertion in
> `test_tour_subcommand.py`; `CUE_CARD.md` sharpened (Variant-C
> recovery + Variant-B force/emg rows). 822/822 pytest, ruff clean,
> 76/76 probe, CLI smoke PASS. No router/security/child-gate/vault/ADR
> architecture changes — two handler call-sites + one tour config block.
> No breaking changes; patch bump.
>
> **v6.9.0 (2026-05-04)** — Wheel-distributed `tour` subcommand + bundled
> HIP Lab realistic fixtures per [ADR 0024](docs/adr/0024-wheel-distributed-tour-and-fixture-bundling.md).
> New `tailor tour` CLI subcommand at `src/tailor/tour.py`
> scaffolds the HIP Lab realistic demo from bundled wheel fixtures into
> `~/.tailor/demos/hip-lab/`, copies bundled fixtures via
> `importlib.resources`, writes `user_config.json` with absolute paths,
> indexes the seed vault moment, and writes (or merges with) the
> recipient's Claude Desktop config — recipient never types an env var.
> Flags: `--variant`, `--target`, `--no-claude-desktop`, `--force`.
> Inherits `pilot.py`'s v6.2.1 atomic-write + BOM round-trip +
> deep-merge hardenings explicitly. Bundled fixtures: the HIP Lab
> realistic demo's 48 CSVs + 3 `metadata.json` sidecars + 1 seed vault
> moment migrate from `examples/hip_lab_demo/realistic/` to
> `src/tailor/_fixtures/hip_lab_demo_realistic/`; `pyproject.toml`
> package-data globs extend to `_fixtures/**/*.csv`,
> `_fixtures/**/*.json`, `_fixtures/**/*.md`. Distribution model:
> pre-built wheel via Drive/email; no PyPI publish; repo stays private.
> ADR 0024 codifies the synthetic-by-construction precondition —
> bundling under this pattern is permitted only for bytes that are
> synthetic by construction; real or de-identified-real cohort data
> require a superseding ADR. Wheel-size budget 10 MB; actual 1.26 MB.
> `examples/hip_lab_demo/realistic/setup.py` preserved as a thin shim
> delegating to `tour_main()`; `rehearse.py` rewritten to scaffold a
> fresh tour into a temp dir and run end-to-end checks against the
> recipient code path. `README.md`, `CUE_CARD.md`, `WINDOWS_QUICKSTART.md`
> updated; WINDOWS_QUICKSTART becomes a fully wheel-driven recipient guide.
> Deferred: legacy `demo` → `verify` rename (ROADMAP — `demo` is operator
> self-verification, `tour` is audience walkthrough; verb mismatch corrected
> next pass). 7-agent release pass: ci-gate-runner SHIPPABLE (818/818
> pytest, ruff clean, 76/76 probe, CLI smoke PASS); mcp-protocol-auditor
> PROTOCOL OK (wire surface 49 tools; 3 new subprocess regression tests);
> reproducibility-provenance-auditor CLEAN (all 4 invariants HOLD);
> researcher-utility-reviewer ALIGNED (PI + IRB = LOAD-BEARING medium;
> analyst = NEUTRAL); phi-irb-risk-reviewer WATCH → CLOSED (ADR 0024
> § "Synthetic-by-construction precondition" added before ship);
> coverage-criticality-mapper REVIEW not REGRESSION (one uncovered HIGH
> line closed, one tracked for next hygiene pass); red-team-reviewer NO
> OBJECTION FOUND. 23 new tests (20 in `test_tour_subcommand.py` + 3
> subprocess in `test_serve_mcp_protocol.py`). Total tool surface: 49
> (tour subcommand is absent from `tools/list` — CLI only, not MCP).
> No router/security/child/vault-layer/audit architecture changes.
> Public API additions only — no breaking changes; SemVer minor bump.
>
> **v6.8.1 (2026-05-03)** — C3 peak-tie systematic bias fix on CSV
> cohort tools. `time_to_50pct_drop_s` and `peak_index` in
> `CSVProcessing` now reference the LAST sample at peak value rather
> than the FIRST, via a new `_last_peak_index` module-level helper
> applied at both call sites (`aggregate_metric` for
> `time_to_50pct_drop_s` and `force_decline_summary` for
> `peak_index`). The original `values.index(peak)` returned the first
> occurrence, which systematically inflated decline-start estimates on
> real isometric force traces with ramp → plateau → decline shape —
> participants with longer plateau holds received larger positive bias,
> creating a between-groups confound in exactly the data shapes the
> cohort tools are designed to compare. Demo β data (per-second
> random-walk floats) has no peak ties and is numerically unchanged;
> the fix matters the moment any real isometric force trace loads.
> Three new regression tests: `test_time_to_50pct_drop_with_peak_plateau_uses_last_peak_index`
> (cohort path), `test_peak_plateau_indexes_to_last_peak_sample`
> (per-file path), and `test_peak_plateau_unique_peak_unaffected`
> (regression-guard for the unique-peak case). 676 → 679 tests;
> 85% coverage maintained; `processing.py` now at 99% coverage.
> Gates: pytest 679/679, ruff clean, security probe 76/76, CLI smoke
> PASS. No ADR — bug fix, not a decision (adr-weigher
> REJECT-NOT-ADR-WORTHY). No router/security/child/vault/CLI
> architecture changes beyond the two corrected call sites in
> `csv_dir/processing.py`. Public API unchanged; patch bump.
>
> **v6.8.0 (2026-05-03)** — Local-LLM cooperation-loop PR2: LLM-driven
> gap reasoning. Lands the second of two PRs governed by
> [ADR 0023](docs/adr/0023-local-llm-cooperation-loop.md), completing
> the cooperation-loop contract on top of v6.7.0's deterministic
> substrate scan. `OracleResponse` gains two LLM-generated fields:
> `next_best_calls: list[str]` (framework tool names the local LLM
> thinks would raise oracle confidence — bounded vocabulary) and
> `unresolved_intent: list[str]` (questions the local LLM thinks the
> analyst should answer — unbounded LLM-generated free text). The
> split is the load-bearing distinction: fetch-this-data belongs in
> `next_best_calls`; ask-the-analyst belongs in `unresolved_intent`.
> Hosted Claude reads which list a suggestion lives on and routes
> accordingly. Both default to `[]`; `NullBackend` inherits the empty
> contract by construction; `OllamaBackend` populates them via
> JSON-mode prompt extension with defensive list-coercion mirroring
> the existing `ambiguity_axes` pattern. Fallback path emits `[]` for
> both — the fallback is the structural signal that no LLM ran. The
> `ask_local_oracle` tool description is rewritten to teach hosted
> Claude the multi-pass cooperation loop (all three new fields:
> `related_substrate`, `next_best_calls`, `unresolved_intent`). Two
> new `audit_log` columns: `oracle_next_best_calls_count INTEGER` and
> `oracle_unresolved_intent_count INTEGER` — by symmetry with PR1's
> `oracle_substrate_count`. An IRB reviewer reconstructing what the
> hosted LLM saw on an oracle call queries counts from `audit.db`
> without parsing the response payload (ADR 0001). Both columns are
> NULL on pre-execute failures, 0 on successful empty emissions, and
> the actual length on populated emissions. 7-agent release pass per
> ADR 0010 / ADR 0011: ci-gate-runner SHIPPABLE; mcp-protocol-auditor
> PROTOCOL OK (added 4 subprocess regression tests during the audit);
> reproducibility-provenance-auditor CLEAN (4 invariants HOLD with one
> BORDER on docstring drift, fixed); researcher-utility-reviewer RESHAPE
> (IRB persona — closed by audit-column addition + operator-guide
> subsection); coverage-criticality-mapper REVIEW (zero newly-uncovered
> HIGH lines; all PR2 defensive-coercion branches covered);
> phi-irb-risk-reviewer WATCH (4 findings — all addressed in code +
> docs before ship: audit columns per Lens 3, operator-guide gap-
> reasoning egress subsection per Lens 1, ADR 0023 § Neutral
> consequences amended to distinguish PR1 metadata from PR2 LLM-text
> under ADR 0012 per Lens 4, research-framing.md § Consent withdrawal
> paragraph naming oracle audit rows as third retention category per
> Lens 6); red-team-reviewer OBJECTION (medium) on missing audit
> columns — confirmed phi-irb Lens 3, same fix closed both. ADR 0023
> amendments: § Audit-log columns (all three named); § Negative
> consequences token-estimate corrected; § Neutral consequences
> PR1 vs PR2 ADR 0012 distinction; § Landing shape PR2 entry. 15 new
> regression tests (12 PR2 contract/parser/fallback + 3 audit-column)
> plus 4 subprocess regression tests added by mcp-protocol-auditor
> during the release pass — 676/676 tests pass. Coverage 85%. Public
> API additions only — no breaking changes; SemVer minor bump. Total
> framework tool surface unchanged at 48. No router/security/child/CLI
> architecture changes beyond the two new audit columns and the
> `ask_local_oracle` tool-description rewrite.
>
> **v6.7.0 (2026-05-03)** — Local-LLM cooperation-loop release.
> Adds the deterministic substrate-vision feature (PR1 of [ADR 0023](docs/adr/0023-local-llm-cooperation-loop.md))
> on top of the v6.6.0 local-LLM guardian. Every successful
> `ask_local_oracle` call now surfaces a `related_substrate: list[dict]`
> field — themes / moments / failure-modes the analyst captured for
> the subject(s) in scope, automatically pulled from the vault.
> Hosted Claude no longer has to remember which slugs to grep; the
> local layer's structurally-unique vault read access is realised
> in code, not just in the ADR. The substrate-vision asymmetry
> argument (the local layer can read the vault deterministically;
> hosted Claude structurally cannot) is now load-bearing in running
> code rather than only in prose. New audit-log column
> `oracle_substrate_count` records how many vault items were
> surfaced per oracle call — IRB-grade provenance for the new flow.
> New `OracleResponse.substrate_scan_warning` field surfaces
> swallowed VaultStorage exceptions on the wire (parallels ADR 0003
> `scrubber_warning` seam — closes the stderr-only-warning gap that
> would otherwise be eaten by Claude Desktop). Architectural
> placement: substrate scan lives in `LocalLLMLayer.execute()` after
> `backend.compose()` returns, *not* in any backend; `NullBackend`
> inherits substrate vision for free. New public `VaultWriter.storage`
> property exposes the SQLite index for framework-tier read consumers
> without breaking the writer's hook interface. ADR 0009
> IS-NULL-or-match filter inherited via `VaultStorage.list_themes` /
> `list_notes` — cross-subject themes and v6.1-legacy notes remain
> visible to the substrate scan. ADR 0012 vault-PHI-bypass inherited
> — substrate entries are metadata only (kind, slug, title,
> subject_id, status, last_updated), no raw biometric streams.
> Substrate cap of 20 entries; sorted last_updated descending; dedup
> key is `(kind, slug)` so a theme and a moment sharing a slug both
> surface (they are distinct artifacts in different vault namespaces).
> `_collect_subjects` mirrors `_flatten_claims`'s scalar filter to
> avoid surfacing `_meta`-shaped sibling keys as bogus subjects (red-
> team-reviewer adversarial pairing on the release pass caught the
> false equivalence). 26 new regression tests (13 substrate-scan
> contract / behaviour tests, 5 mcp-protocol-auditor subprocess wire
> tests, 4 substrate_scan_warning + dedup contract tests, 4 audit-
> column / coverage-edge tests). 657/657 tests pass.
> 7-agent release pass per [ADR 0010](docs/adr/0010-adversarial-pairing.md) /
> [ADR 0011](docs/adr/0011-promotion-policy.md): ci-gate-runner
> SHIPPABLE; mcp-protocol-auditor PROTOCOL OK (added 5 subprocess
> regression tests during the audit); reproducibility-provenance-
> auditor CLEAN; researcher-utility-reviewer ALIGNED;
> phi-irb-risk-reviewer WATCH (3 findings — substrate_scan_warning
> for swallowed exceptions, operator-guide PHI warning for slug/title
> egress, Path A vs Path B documented for IS-NULL cross-subject
> surfacing); coverage-criticality-mapper REVIEW (2 newly-uncovered
> HIGH lines + cross-kind slug-collision correctness edge); red-team-
> reviewer OBJECTION on `_collect_subjects` heuristic mismatch with
> `_flatten_claims`. All substantive findings addressed in code; all
> deferred findings closed in `docs/guides/local-llm-guardian.md`,
> `docs/adr/0023-local-llm-cooperation-loop.md` (new IRB-relevant
> surface section), and `docs/design/research-framing.md` (substrate-
> vision paragraph added so the framing doc does not drift on next
> release). Public API additions only — no breaking changes; SemVer
> minor bump. PR2 of ADR 0023 (LLM-driven gap reasoning —
> `next_best_calls` + `unresolved_intent` via prompt extension on
> `OllamaBackend`) lands separately under the same ADR 0023 contract.
> Total framework tool surface unchanged at 48 (no new tools; the
> existing `ask_local_oracle` gains response fields).
>
> **v6.6.0 (2026-05-01)** — Local-LLM guardian release. Adds
> `framework/local_llm/` — a new framework-tier component (parallel to
> `framework/vault/`) that enables an LLM running on the analyst's machine
> to compose structured natural-language responses over deterministic
> processing output, with a hard architectural rule: numbers come from
> `processing.py`, prose comes from the local LLM, enforced by the
> `OracleResponse` schema. New [ADR 0022](docs/adr/0022-local-llm-guardian.md)
> (Proposed) codifies the commitment; ADR 0008 amended to extend its
> `@staticmethod`/no-PRNG permit-list to name the new backend files.
> Core types: `OracleRequest` / `OracleResponse` / `NumericalClaim` /
> `OracleMeta`. Default posture: `NullBackend` (no-op — existing deployments
> behaviorally unchanged); opt-in via `local_llm` block in `user_config.json`.
> Real backend: `OllamaBackend` (Ollama on `localhost:11434`, JSON-mode HTTP).
> Four named tiers: Scout (`llama3.2:1b`) / Sentinel (`phi3.5:3.8b`) /
> Guardian (`llama3.1:8b`) / Titan (`qwen2.5:14b`) — cited numerical claims
> identical across tiers; only the prose model differs. One new tool:
> `ask_local_oracle`. Six new `oracle_*` columns on `audit_log` for IRB-grade
> provenance. Cohort tools (`csv_cohort_summary` + `csv_force_decline`) gain
> oracle-mediation hints in tool descriptions; remaining 45 tools unchanged.
> Framing-claim strengthening (conditional on opt-in): "no biometric streams
> leave the analyst's machine, ever, at any tier — including to hosted LLMs."
> Operator guide at `docs/guides/local-llm-guardian.md` (tier table + Ollama
> setup + troubleshooting). 37 new regression tests: 28 unit (oracle contract,
> NullBackend, OllamaBackend mocked, LocalLLMLayer dispatch, hallucination-
> prevention invariant) + 2 audit-column regression + 1 strengthened
> hallucination guard + 6 subprocess (mcp-protocol-auditor). Total 632/632.
> 6-agent release pass: `ci-gate-runner` SHIPPABLE;
> `reproducibility-provenance-auditor` CLEAN; `mcp-protocol-auditor`
> PROTOCOL OK; `researcher-utility-reviewer` HOLD (HIGH) → 5 audit-log
> columns added before ship; `red-team-reviewer` OBJECTION (medium) →
> `oracle_latency_ms` 6th column added + hallucination test strengthened;
> `phi-irb-risk-reviewer` WATCH → operator-guide "Important precision"
> section added. Includes pending CLAUDE.md governance edits (architecture
> diagram + file-structure block updated for `local_llm/`) per ADR 0022.
> No router-pipeline, security-pipeline, child, vault-layer, or CLI
> architecture changes beyond the new `register_local_llm_layer()` hook.
> Public API additions only — no breaking changes; SemVer minor bump.
> Total framework tool surface: 25 (vault) + 12 (running) + 7 (csv_dir) +
> 3 (template) + 1 (local_llm) = 48 (was 47). Explicitly deferred per
> ADR 0022 § "Out of scope": verifier behavior on hosted-LLM responses,
> sanitizer/proxy mode, conductor-mode toggle, citation-grounding
> enforcement on manuscript drafts, migration of remaining 45 tools to
> oracle mediation, IRB-facing threat-model update for prompt-injection
> surface, performance characterization (cold-start / GPU vs CPU),
> pilot-wizard tier-detection, real Ollama end-to-end smoke (all
> OllamaBackend tests are mocked).
>
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
> Demo runs via `TAILOR_CONFIG_DIR=examples/hip_lab_demo/beta
> tailor serve` — isolated from the operator's
> `~/.tailor/user_config.json`, no pilot-wizard clobber risk.
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
> tests this by spawning `tailor serve` as a subprocess with
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
> and three prompts via the new `tailor pilot` CLI subcommand
> (`src/tailor/pilot.py`). The wizard auto-detects CSV schema
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
> `src/tailor/_fixtures/` so they ship in the wheel — wheel
> install and source-tree work identically. `docs/guides/multi-subject-pilot.md`
> rewritten to lead with `tailor pilot` as the primary path.
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

**Tailor is a local-first MCP framework that lets any MCP-speaking AI work with your own data — without that data ever leaving your machine, with every action recorded in a durable audit log, and with results stamped for reproducibility.**

The first deployment recipe shipped end-to-end is a health-research workflow: high-frequency biometric data, cohort analysis, IRB-grade audit trails, and the worked example of a Strava-API child. The intended users for this first recipe are health researchers (academic medical centers, mHealth labs, sleep/CGM/cardiology groups) and the research-software engineers who support them. The deliverables are a router that owns cross-cutting concerns, a ChildMCP extension point for new data sources, and a vault layer for durable cross-session analytical memory.

The framework generalises beyond health research — the architecture (router + ChildMCP plurality + Wardrobe + audit + consent + cost gates) is data-agnostic and use-case-agnostic. Future deployment recipes (knowledge work, clinical workflows, household / family contexts, creative archives) compose on the same engine. The research recipe is the first one shipped end-to-end, not the platform's identity.

### Your Wardrobe

Your **Wardrobe** is what your AI knows about you: the structured collection of your data and prior analytical work that lives entirely on your machine. *Not clothes — your stuff.* The Wardrobe accumulates:

- **Themes** — persistent questions / hypotheses you keep returning to (research questions for a PI; recurring threads for a writer; case formulations for a clinician)
- **Moments** — observations worth remembering across sessions (an aha; a captured mid-analysis insight; a clinical impression)
- **Evidence** — data that grounds a theme (a specific time-window, a specific cohort comparison, a specific trace)
- **Failure modes** — documented dead-ends so the AI doesn't suggest them again
- **Source data** — the biometric streams, CSVs, vault notes the AI reasons over

Tailor curates your Wardrobe — adds to it, retrieves from it, governs how the AI reaches into it — and never sends any of it to a service you didn't choose. Internally the framework still has component names like `vault/` (the markdown storage layer) and `framework/` (the security pipeline); user-facing language uses **Wardrobe** as the term for what those components hold collectively.

Alongside the Wardrobe, Tailor maintains a separate **Ledger** — the audit log. Every action Tailor took on your behalf is recorded in SQLite with timestamps, parameters, outcomes, `scrubber_id`, and optional `entity_id` scoping. The Ledger is the tailor's own record of work; the Wardrobe is yours. Both are local-first and held on your behalf, but they are accounted separately (per [ADR 0033](docs/adr/0033-complete-tailor-metaphor-workshop-side.md)). The audit-log backbone per [ADR 0001](docs/adr/0001-audit-log-as-backbone.md) is what the Ledger names; internally the audit log lives at `audit.db` in `framework/`, not in `framework/vault/`, so the directory structure already reflected the Ledger / Wardrobe split before this terminology did. v7.3.0 (per [ADR 0037](docs/adr/0037-redcap-child-scope-export-directory-only-with-deferred-live-api.md) + [ADR 0003 § Amendment](docs/adr/0003-phi-scrubber-seam.md)) adds a parallel `child_scrubber_id` column to record domain-specific structured-PHI scrubbers (e.g., REDCap's `redcap_metadata_flags`). The two columns let an IRB reviewer distinguish framework-level pattern-matching from child-level structured-input scrubbing.

Workshop-vs-lifestyle invariant per [ADR 0033](docs/adr/0033-complete-tailor-metaphor-workshop-side.md) (supersedes the counter-programming invariant from [ADR 0031](docs/adr/0031-rename-to-tailor-and-wardrobe.md)): the project's metaphor identity is **workshop-shaped**, not lifestyle-shaped. Tailor *commissions* fabric from mills (children), *trims* it to the tier the wearer (AI) needs, and *stitches* the seams with institutional implementations. The full vocabulary lives at [`docs/design/tailor-vocabulary.md`](docs/design/tailor-vocabulary.md); the narrow-forbid list (Table 5 — couture / atelier / boutique / runway / showroom / couturier always forbidden; nine more forbidden only in lifestyle-register usage) is enforceable by grep.

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
| [`reproducibility-provenance-auditor`](.claude/agents/reproducibility-provenance-auditor.md) | Audits a diff against the reproducibility/provenance invariants codified in ADRs 0001 / 0002 / 0008 / 0003 — no PRNG in processing, audit-log completeness, `_meta` stamping, `entity_id` propagation. Per-file HOLDS / BROKEN / NEEDS REVIEW with file:line + ADR citations | After any non-trivial diff that touches `framework/` or `children/*/processing.py`. Closes the ADR 0008 "enforced by review at PR time" gap |
| [`phi-irb-risk-reviewer`](.claude/agents/phi-irb-risk-reviewer.md) | Hostile-IRB-committee lens on code changes — six threat-model lenses (HIPAA Safe Harbor, consent scope, audit-log completeness, ADR 0003 scrubber asymmetry, ADR 0009 entity_id integrity, retention). Returns NO RISK / WATCH / VIOLATION with IRB / HIPAA / ADR citations | After any change touching `framework/security.py`, `framework/audit.py`, `framework/router.py`, `framework/vault/`, or any child's `execute()` path; before any release involving consent or data flow |
| [`mcp-protocol-auditor`](.claude/agents/mcp-protocol-auditor.md) | End-to-end subprocess MCP-protocol audit — drives `python -m tailor serve` as a real subprocess speaking JSON-RPC over stdio, asserts wire-level correctness on `initialize` / `tools/list` / `tools/call` / consent gate / cost gate / error envelopes / `_dumps` serialization seam. Catches the gate-evasion class no other specialist owns: upstream-mcp-SDK signature drift, missing schema keys, silent type coercion, markdown round-trip lossiness, post-execute hook silent failures | After any change touching `framework/router.py`, `framework/audit.py`, `framework/security.py`, `framework/vault/{layer,writer}.py`, or any child's `execute()` path; mandatory before every release. Promoted v6.5.0 after 5 protocol-adapter ship-blocker bugs surfaced in 90 minutes that 8 existing gates missed |
| [`cue-card-rehearsal-auditor`](.claude/agents/cue-card-rehearsal-auditor.md) | Read-only cue-card audit — maps each cue-card prompt against the registered ToolDefinition schemas and emits per-prompt verdicts (PASS / WRONG-TOOL / WRONG-PARAMS / AMBIGUOUS) with file:line citations. Catches the schema-under-specification class of failure: schemas that pass structural gates but silently fail when Claude infers parameters from operator prose | Before every release that ships or revises a cue card (`--cue-card=<path>` arg); whenever `CUE_CARD.md` or any `ToolDefinition` schema changes. Promoted v6.10.0 per [ADR 0025](docs/adr/0025-cue-card-rehearsal-as-release-gate.md) after v6.9.1 + v6.9.2 closed the same structural gap twice in one week |
| [`adr-weigher`](.claude/agents/adr-weigher.md) | Weighs a candidate ADR concept against five criteria (decision-shaped, reversal-changes-code, WHY-non-obvious, cites-prior-ADRs, severity) and returns `PASS / REJECT-NOT-ADR-WORTHY / DEFER-NEEDS-BOSS-INPUT / INSUFFICIENT-INPUT`. Read-only — produces a verdict, not an ADR | Before `adr-drafter` is invoked during autonomous overnight sessions — gates premature-ADR drift the same way [ADR 0011](docs/adr/0011-promotion-policy.md) gates premature-specialist drift. Per [ADR 0017](docs/adr/0017-adr-weigher-and-autonomous-session-cap.md), the autonomous-session ADR cap is six per session with `adr-weigher` as the binding quality constraint |
| [`recipient-install-validator`](.claude/agents/recipient-install-validator.md) | End-to-end recipient-install validation — provisions a clean Windows 11 base box via VirtualBox + Vagrant, installs the freshly-built wheel via the documented recipient command, runs `tailor fitting-room` (renamed from `tailor tour` in v7.1.0 per [ADR 0035](docs/adr/0035-cli-rename-walkthrough-and-fitting-room-and-recipient-experience-naming-principle.md)), validates per-path Claude Desktop config (per ADR 0026), exercises `tailor walkthrough` (renamed from `tailor demo` per ADR 0035; per ADR 0027), and runs wheel-install-dependent pytest in-guest. Catches the failure class that produced the v6.10.1–v6.10.4 patch quartet — bugs that exist between the wheel artifact and a stranger's machine, invisible to host-side gates that test against the dev tree | Mandatory + file-touched-gated. Fires when any of `fitting_room.py`, `tour.py` (re-export shim through v7.1.x), `pilot.py`, `__main__.py`, `wizard.py`, `pyproject.toml` package-data globs, or `_fixtures/**` are modified in a release branch. Promoted v6.11.0 per [ADR 0028](docs/adr/0028-recipient-install-validation-as-release-gate.md) — the gate composes at `release-shipper` with `ci-gate-runner` (host: dev-tree pytest) and `recipient-install-validator` (guest: wheel-installed package) |

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
- **`reproducibility-provenance-auditor`** — closes the ADR 0008 "enforced by review at PR time" gap. Audits diffs against the determinism (no PRNG / no clock / `@staticmethod` purity), audit-log completeness, `_meta` provenance, and `entity_id` propagation invariants.
- **`phi-irb-risk-reviewer`** — applies the IRB-committee-member lens. Six threat-model lenses (Safe Harbor, consent scope, audit completeness, scrubber asymmetry, entity_id integrity, retention) yield NO RISK / WATCH / VIOLATION verdicts with IRB / HIPAA / ADR citations.

These four ground the team in the project's stated goal (CLAUDE.md § "What This Project Is" — health researchers, audit trails, reproducibility, data governance). They land via the structural-argument + severity + cost-vs-frequency criteria of ADR 0011 rather than the generic 3+-uses default.

## Problems this is built against

1. **Data governance.** Hosted LLMs are the wrong home for participant biometric data. The tier model and local-first processing are the structural response.
2. **Reproducibility.** LLM-assisted analyses in chat windows leave no durable trace. The audit log (every call logged to SQLite, scoped by optional `entity_id`) and `_meta` provenance stamps are the response.
3. **Longitudinal analytical memory.** Observations made in one session disappear when the chat ends. The vault layer (themes, moments, evidence logs, append-only) is the response.
4. **AI economics.** Hosted LLMs face a finite context budget per question and a finite cost ceiling per deployment. Tier-1 server-side computation — *return the answer, not the data* — is simultaneously a cost lever (token-per-question collapses by 1–2 orders of magnitude on most analytical questions) and a cognition lever (freed context goes to reasoning over the analyst's prior Wardrobe, the audit log, the current question — not to data shuffling). The win compounds with the AI ecosystem rather than eroding with cheaper models: as AI is deployed against larger substrates, the per-question context-budget problem gets harder, not easier. Per [ADR 0029](docs/adr/0029-token-reduction-as-analytical-quality.md) (Amended 2026-05-12), this property is what makes AI-augmented work sustainable at the scale real substrates demand — and it generalizes across every deployment recipe Tailor will ever ship, not only the health-research worked example.

## Architecture

```
LLM client <--> RouterMCP (validate → circuit break → consent → cost → execute
                           → PHI scrub → audit + provenance stamp)
                   |                 ╲           ╲
              ChildMCP                VaultLayer  LocalLLMLayer ← framework-level
     (one per data source)            (reorientation tier;     (local-LLM guardian;
  e.g. RunningChild, CGMChild        Obsidian vault + index)   skips consent/cost gates)
              (may carry its own PHI scrubber per ADR 0003       ↑ ADR 0022; opt-in
               § Amendment 2026-05-14; e.g. RedcapPHIScrubber      via user_config
               reads project_metadata.csv identifier flags
               inside execute() before result returns to
               framework PHI scrub)
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
src/tailor/
  __init__.py              # Package metadata
  __main__.py              # CLI: serve | pilot | fitting-room | walkthrough |
                           #   setup | status | uninstall | --help
                           #   (deprecated v7.1.0 per ADR 0035: tour, demo)
  pilot.py                 # Multi-subject CSV pilot wizard (v6.2.1)
  fitting_room.py          # `tailor fitting-room` scaffolder — bundled
                           #   fixtures + Claude Desktop registration
                           #   (v6.9.0 / ADR 0024; renamed v7.1.0 per ADR 0035)
  tour.py                  # v7.1.x re-export shim for `tailor.tour` (legacy
                           #   import path); removal deferred to a future
                           #   minor per the v7.2.0 banner amendment
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
                           #   DataScrubber (no-op default — see ADR 0003)
    cost.py                # CostGate, TokenLedger, estimate_tokens
    audit.py               # AuditLog (with entity_id) + JSON helpers
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
    local_llm/             # Local-LLM guardian (framework-level
                           #   infrastructure, not a ChildMCP) — see ADR 0022
      __init__.py          # Public API exports
      oracle.py            # OracleRequest/Response/Meta + tier table
                           #   (Scout/Sentinel/Guardian/Titan)
      layer.py             # LocalLLMLayer — exposes ask_local_oracle tool
      backends/__init__.py # LocalLLMBackend ABC
      backends/null.py     # NullBackend — no-op default; surfaces claims
                           #   from resolved_context with no narrative
      backends/ollama.py   # OllamaBackend — talks to Ollama on
                           #   localhost:11434 via JSON-mode HTTP
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
      child.py             # CSVDirectoryChild(ChildMCP) — 7 tools, 3 tiers
      processing.py        # CSVProcessing — stateless analytics
    matlab_file/           # MATLAB `.mat` binary-format child (ADR 0036)
      __init__.py          # Exports MATLABFileChild, MATLABProcessing
      child.py             # MATLABFileChild(ChildMCP) — 6 tools, 3 tiers;
                           #   requires `tailor-mcp[matlab]` optional extra
      processing.py        # MATLABProcessing — stateless analytics
    redcap/                # REDCap export-directory child (ADR 0037)
      __init__.py          # Exports RedcapFileChild, RedcapProcessing, RedcapPHIScrubber
      child.py             # RedcapFileChild(ChildMCP) — 6 tools, 3 tiers
      processing.py        # RedcapProcessing — stateless analytics
      scrubber.py          # RedcapPHIScrubber — child-level structured-PHI seam (ADR 0003 § Amendment 2026-05-14)
    template/              # Runnable starting-point child (copy + rename)
      __init__.py          # Rename checklist for new children
      child.py             # TemplateChild(ChildMCP) — minimal 3-tier skeleton
      processing.py        # TemplateProcessing — stateless analytics stubs
  demo/
    __init__.py            # Exports run_demo
    sample_data.py         # Library-shaped synthetic-Strava generator
                           #   (preserved per ADR 0008 § Alternatives;
                           #   no longer the demo's data source — see ADR 0027)
    runner.py              # Researcher-first-look — runs CSV cohort tools
                           #   against bundled HIP Lab fixtures (ADR 0027)

tests/                     # Mirrors src/ layout
  conftest.py              # Shared fixtures (tmp_data_dir, tmp_vault_dirs)
                           #   + probe marker registration
  security_probe.py        # Standalone security probe (runs in CI, no pytest needed)
  test_security_probe_pytest.py   # @pytest.mark.probe wrapper around the standalone probe
  framework/
    test_router.py         # Router pipeline integration tests (includes VaultLayer)
    test_security.py       # ParamValidator / CircuitBreaker / ConsentGate / DataScrubber
    test_cost.py           # CostGate / TokenLedger / estimate_tokens
    test_audit.py          # AuditLog: entity_id, params truncation, keyword-only error
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
    matlab_file/
      test_matlab_shape.py     # Shape + handler tests (scipy-required; skip if missing)
      test_matlab_processing.py  # Pure-function tests (no scipy)
    redcap/
      test_redcap_shape.py     # Shape + handler tests for RedcapFileChild
      test_redcap_processing.py  # Pure-function analytics tests
      test_redcap_scrubber.py    # RedcapPHIScrubber identifier-flag enforcement tests
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
| 5a | `DataScrubber` (framework-level) | Cross-domain PHI-stripping seam at the router boundary; no-op default, subclass when an institutional policy applies across every child (e.g. regex-based pattern matchers). ADR 0003. |
| 5b | Child-level scrubber (e.g. `RedcapPHIScrubber`) | Domain-specific structured-input PHI seam wired inside a child's `execute()` before the result envelope returns. Used when the data source itself carries identifier metadata the framework cannot see (e.g. REDCap's `project_metadata.csv` `identifier=yes/no` flags). Parallel to the framework-level seam, not a replacement. ADR 0003 § Amendment 2026-05-14. |
| 6 | `AuditLog` + `TokenLedger` | Every call logged to SQLite with optional `entity_id` scoping; cumulative session spend |

Every successful result also carries a `_meta` block stamped with `package_version`, `tool_name`, UTC `called_at`, `domain`, `tier`, `scrubber_id`, and per-call + session token counts — plus `scrubber_warning` whenever the no-op default scrubber is active and `hook_warnings` when a post-execute hook raised. Minimum-viable provenance for results that may end up in a paper.

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
| `csv_group_summary` | 1 | Cross-file aggregation by metadata-sidecar group (n / mean / std / min / max per group). Requires `metadata.json` sidecar — see ADR 0015. |
| `csv_force_decline` | 1 | Per-file fatigue diagnostic — peak, decline %, decline rate, time-to-50%-drop. Generic over force / EMG envelope / power. |
| `csv_downsampled` | 2 | Decimated rows at every Nth interval |
| `csv_raw_stream` | 3 | Full per-row data with precision reduction |

Optional sidecar for cohort grouping: `<csv_dir.path>/metadata.json` with schema `{"<filename>": {"<field>": <value>, ...}}`. Required by `csv_group_summary`; ignored by every other tool. Schema matches REDCap / DataCite / Frictionless Data conventions. See [ADR 0015](docs/adr/0015-tier-1-cohort-surface-and-metadata-sidecar.md).

## MATLAB File Child — 6 Tools

Opt-in via `matlab_file` key in `user_config.json`. Wraps a local directory of MATLAB `.mat` binary files. Requires the `[matlab]` optional extra (`pip install tailor-mcp[matlab]` or `uv tool install tailor-mcp[matlab]`) — scipy is not in the base install. Per [ADR 0036](docs/adr/0036-matlab-child-scope-v72-only-with-deferred-hdf5.md), this child supports `.mat` versions v5/v6/v7.2 only; HDF5-based v7.3 is detected by magic-byte check and rejected with a typed error envelope pointing at the deferred work.

| Tool | Tier | Description |
|------|------|-------------|
| `matlab_list_files` | 1 | List `.mat` files with their variables, shapes, and dtypes |
| `matlab_file_detail` | 1 | Single-file metadata + per-variable summary stats |
| `matlab_summary_report` | 1 | Per-variable count/mean/std/min/max across one file |
| `matlab_cohort_summary` | 1 | Cross-file aggregation by metadata-sidecar group (same `metadata.json` pattern as `csv_dir`; see ADR 0015) |
| `matlab_downsampled` | 2 | Decimated 1-D variable at every Nth element |
| `matlab_raw_array` | 3 | Full 1-D numeric variable with precision reduction |

Subject scoping per [ADR 0009](docs/adr/0009-vault-subject-keying.md): one `.mat` file = one subject (matching the `csv_dir` / `force_csv` / `emg_csv` lineage). Multi-subject `.mat` files where variables-are-subjects (e.g. an 8×1000 envelope matrix where rows are participants) are deferred — `entity_id` is audit-log scoping only and does NOT filter axes. See ADR 0036 § Negative consequences.

Config shape in `~/.tailor/user_config.json`:

```json
"matlab_file": {
  "path": "/path/to/mat/directory",
  "variable_filter": ["EMG_envelope", "force"]
}
```

`variable_filter` is optional; absent means "all 1-D and 2-D numeric variables auto-detected per file." Cohort grouping uses the same `<matlab_dir>/metadata.json` sidecar schema as `csv_dir`: `{"<filename>": {"<field>": <value>, ...}}`.

## REDCap File Child — 6 Tools

Opt-in via `redcap_file` key in `user_config.json`. Wraps a local directory of REDCap CSV/JSON exports + the REDCap data dictionary (`project_metadata.csv`). Per [ADR 0037](docs/adr/0037-redcap-child-scope-export-directory-only-with-deferred-live-api.md), this child supports the export-directory path only; live REDCap REST API access is deferred behind a reversal condition ("first real-world target lab hits the API need").

| Tool | Tier | Description |
|------|------|-------------|
| `redcap_list_records` | 1 | List record_ids with per-instrument completion flags and longitudinal event coverage |
| `redcap_record_detail` | 1 | Single-record summary — non-identifier fields only, grouped by instrument |
| `redcap_summary_report` | 1 | Per-instrument completion counts + per-field cardinality and distribution |
| `redcap_cohort_summary` | 1 | Cross-record cohort aggregation by `group_by` (project_metadata.csv field or ADR 0015 sidecar). Refuses identifier-flagged group_by or field to prevent PHI leakage through group-key cardinality. |
| `redcap_records` | 2 | All subjects' answers to one named instrument across all events, identifier-stripped. `instrument` parameter is REQUIRED. Consent-gated. |
| `redcap_raw_records` | 3 | All subjects, all events, all instruments, identifier-stripped. Cost-gated. |

Subject scoping per [ADR 0009](docs/adr/0009-vault-subject-keying.md): `record_id` is the `entity_id`; `redcap_event_name` is a grouping dimension threaded through cohort tools but NOT ADR 0009 subject scoping (REDCap's longitudinal structure means one subject has multiple records across events). Variables-as-subjects shapes (one record asking about multiple respondents, e.g. family studies) are deferred — see ADR 0037 § Negative consequences.

**Built-in PHI scrubbing.** `RedcapPHIScrubber` reads `identifier=yes/no` flags from `project_metadata.csv` and strips matching fields from every result envelope before the child returns. Unknown fields default to identifier-positive (fail-closed) per ADR 0037; allowlist them via `unknown_field_allowlist` in the `redcap_file` config block. The scrubber is a new seam parallel to ADR 0003's framework-level seam — see [ADR 0003 § Amendment 2026-05-14](docs/adr/0003-phi-scrubber-seam.md).

Config shape in `~/.tailor/user_config.json`:

```json
"redcap_file": {
  "path": "/path/to/redcap/export/directory",
  "records_file": "records.csv",
  "project_metadata_file": "project_metadata.csv",
  "instrument_completion_fields": ["demographics_complete", "phq9_complete"],
  "unknown_field_allowlist": ["computed_score_v2"]
}
```

All keys optional except `path`. Defaults: `records_file="records.csv"`, `project_metadata_file="project_metadata.csv"`. Cohort grouping uses an optional `<redcap_dir>/metadata.json` sidecar per ADR 0015 — distinct from REDCap's `project_metadata.csv` data dictionary; both files may coexist with orthogonal purposes.

## Running and Testing

For end users (PIs, analysts), the canonical install path is uv (or
pipx) against the GitHub URL — no Python install, no venv ritual:

```bash
uv tool install tailor-mcp
tailor pilot     # Three-prompt wizard for the multi-subject CSV pilot
```

For development on the framework itself:

```bash
# Install in dev mode (editable, source tree on disk)
pip install -e ".[dev]"

# Run tests
pytest -v

# CLI smoke test
tailor --help

# Subcommands
tailor pilot         # Multi-subject CSV pilot setup wizard (v6.2.1+)
tailor fitting-room  # Recipient-driven walkthrough (HIP Lab realistic; ADRs 0024 + 0035)
tailor setup         # Strava OAuth wizard for the worked-example child
tailor walkthrough   # Researcher first-look — runs cohort tools on bundled HIP Lab fixtures (ADRs 0027 + 0035)
tailor serve        # Start MCP server (Claude Desktop calls this)
tailor status       # Diagnostic check
# Deprecated aliases (removal deferred to a future minor; one-cycle shims per ADR 0035):
tailor tour         # alias for `tailor fitting-room`
tailor demo         # alias for `tailor walkthrough`
```

## Key Design Decisions

Architectural decisions are captured as numbered ADRs under
[docs/adr/](docs/adr/) — one file per decision, each with its own
context / decision / consequences / alternatives. Summaries below link
to the full record.

- **[ADR 0001 — Audit log is the backbone](docs/adr/0001-audit-log-as-backbone.md).** Every tool call lands in `audit.db`: timestamp, domain, tool, tier, parameters, token estimate, outcome, latency, optional error, optional `entity_id`. Durable evidence of how an analyst accessed participant data — the single most load-bearing feature for research use.
- **[ADR 0002 — `entity_id` scoping](docs/adr/0002-subject-id-scoping.md).** First-class audit column, optional on calls. The router extracts `entity_id` from parameters and threads it to every audit row; children adopt it in `param_schemas` incrementally. Legacy `audit.db` migrates via `ALTER TABLE`.
- **[ADR 0003 — PHI scrubbing is a seam, not a policy](docs/adr/0003-phi-scrubber-seam.md).** `DataScrubber.scrub()` is a no-op by default; institutions subclass. The default emits a one-time warning on first construction and exposes `scrubber_id` so audit rows distinguish misconfigured deployments from real policies. Amended 2026-05-14 (triggered by [ADR 0037](docs/adr/0037-redcap-child-scope-export-directory-only-with-deferred-live-api.md)) to recognise a second parallel seam: child-level scrubbers (e.g. `RedcapPHIScrubber`) wired inside a child's `execute()` to handle domain-specific structured identifier metadata the framework-level seam cannot see.
- **[ADR 0004 — Structured `LLMInstruction`](docs/adr/0004-structured-llm-instruction.md).** Consent and cost gates return a JSON object with individually checkable `must_do`, `must_not_do`, and `on_ambiguous_reply` fields — not a free-text paragraph. Makes compliance auditable.
- **[ADR 0005 — Pre-estimation, not post-billing](docs/adr/0005-cost-pre-estimation.md).** `CostGate` calls `child.estimate_cost()` before execution using stream metadata (point counts), never the full payload. Estimator failures fail closed.
- **[ADR 0007 — Rendering-layers policy](docs/adr/0007-rendering-layers-policy.md).** Source-of-truth markdown is plain and AI-readable; plugin-enhanced views (Dataview, Templater) are additive. Any framework-emitted note that uses plugin syntax must ship a snapshot fallback so the same content renders for any reader. The dashboards refresh tool is the reference implementation.
- **[ADR 0008 — Analytical processing is deterministic by construction](docs/adr/0008-deterministic-by-construction-processing.md).** Every method on `RunningProcessing`, `CSVProcessing`, and `TemplateProcessing` is a `@staticmethod` pure function with no PRNG and no clock reads. The invariant is enforced by review at PR time. The same Tier-1 call with the same inputs returns the same numbers across machines — the ROADMAP "Deterministic mode" item is therefore partially resolved; what remains is a small router-level audited flag paired with content-hashed provenance.
- **[ADR 0009 — Vault subject-keying](docs/adr/0009-vault-subject-keying.md).** Themes carry an optional, set-once `entity_id` in frontmatter — promotion (None → P004) is allowed, reassignment (P003 → P007) is a hard error. Evidence blocks and moments stamp the subject of their writing call. List/search queries filter rows match-or-NULL when `entity_id` is provided so cross-subject themes and v6.1-era legacy notes stay visible. Resolves the design question ADR 0002 deliberately deferred.
- **[ADR 0015 — Tier-1 cohort surface + metadata sidecar](docs/adr/0015-tier-1-cohort-surface-and-metadata-sidecar.md).** Two new Tier-1 tools on the CSV directory child — `csv_group_summary` (cross-file aggregation by metadata-sidecar group) and `csv_force_decline` (per-file fatigue diagnostic). Group identity travels via `<csv_dir>/metadata.json` (schema `{filename: {field: value}}`, REDCap-shaped), required only by `csv_group_summary`. Closes the structural gap where the *"no streams enter LLM context"* claim could not hold for cohort questions: the per-file `csv_summary_report` could not satisfy *"compare X between groups A and B"* without either fabricating numbers or escalating to Tier 2. Pure-function processing per ADR 0008 unchanged.
- **[ADR 0016 — MCP-protocol auditor: wire-level correctness is a seam, not a hope](docs/adr/0016-mcp-protocol-auditor.md).** Promotes `mcp-protocol-auditor` as a permanent specialist after the v6.5.0 demo-before-commit gate surfaced 5 ship-blocker bugs in 90 minutes that 8 existing gates missed. The framework's MCP-protocol-adapter surface (the JSON-RPC adapter between internal abstractions and the wire format the `mcp` SDK serializes) was structurally untested — no agent in the prior roster drove the framework as a real subprocess speaking JSON-RPC over stdio. The new specialist closes that gap; its first run was the audit that justified its creation (recursive use). Cites ADRs 0001 / 0008 / 0010 / 0011 / 0014.
- **[ADR 0036 — MATLABFileChild v1 supports `.mat` v≤7.2 only](docs/adr/0036-matlab-child-scope-v72-only-with-deferred-hdf5.md).** The second non-CSV existence-proof child for v7.1.1's source-agnostic claim ships as the v7.2.0 release. `MATLABFileChild` exposes six tools (`matlab_list_files`, `matlab_file_detail`, `matlab_summary_report`, `matlab_cohort_summary`, `matlab_downsampled`, `matlab_raw_array`) at Tiers 1/2/3 with cohort surface in v1 (same `metadata.json` sidecar pattern as ADR 0015). Scope-bound: `.mat` v5/v6/v7.2 via `scipy.io.loadmat` pulled in as an optional dep (`tailor-mcp[matlab]`); HDF5-based v7.3 detected by magic-byte check and rejected with typed-error envelope. Reversal condition named: first beachhead lab hits the v7.3 gap. Preserves the framework's lean three-dep posture (`mcp`, `requests`, `orjson`) on the base install. REDCap (the other Move 3 candidate) is held for v7.3.0 fresh-session build with PHI-defense decision already ratified.
- **[ADR 0037 — RedcapFileChild scope-bound + deferred live-API + child-level PHI seam](docs/adr/0037-redcap-child-scope-export-directory-only-with-deferred-live-api.md).** Move 3 / Part 2 of the source-agnostic claim. Six tools (4 Tier-1 + 1 Tier-2 instrument-scoped + 1 Tier-3) wrap a local directory of REDCap CSV/JSON exports. Live REDCap REST API path deferred behind "first real-world target lab hits the API need" reversal condition — same shape as ADR 0036's HDF5 deferral. Built-in `RedcapPHIScrubber` ships as a new child-level seam parallel to ADR 0003's framework-level seam, reading `identifier=yes/no` flags from REDCap's IRB-approved `project_metadata.csv`. Three-tier model generalization observed: "progressively-revealing more access under progressively-stronger consent" — not specifically time-series decimation. Cites ADRs 0003 / 0008 / 0009 / 0011 / 0013 / 0015 / 0024 / 0029 / 0036.

### Implementation notes

Domain-specific tuning choices that inform behavior but aren't
architectural decisions in the ADR sense:

- **Grade precision at 1 decimal**: GAP calculation uses `cost = 1 + 0.03 * grade%`. Rounding grade to integer introduces ~3% split error. All other numerics are reduced more aggressively.
- **0.5 m/s stop threshold**: 0.3 m/s was too aggressive (flagged slow shuffles at end of hard efforts). 0.5 m/s (~1.8 km/h) is the designed "completely stopped" signal.
- **Spike detection 30-second cooldown**: A single Apple Watch sensor catchup burst can generate dozens of overlapping anomaly entries without the cooldown.
- **orjson with stdlib fallback**: `_dumps`/`_loads` wrappers in `framework/audit.py` are transparent to all consumers.
- **`router.close()` on Windows**: SQLite WAL connections must be explicitly closed before the process exits on Windows. Call `router.close()` in tests and server shutdown to release file locks.
- **`entity_id` on `strava_*` and vault tools**: All 12 running tools and all 25 vault tools declare an optional `entity_id` parameter (pattern `^[A-Za-z0-9_\-]{1,64}$`). For biosensor children it's audit-log scoping only — does not filter source data, since one authenticated Strava account may cover multiple study participants and `entity_id` is the caller's statement of which one this call is about. For vault tools (per ADR 0009) it additionally keys notes: themes have a set-once subject in frontmatter; evidence and moments stamp the subject of their writing call; list/search queries filter on it. The shared `ENTITY_ID_SCHEMA` and `ENTITY_ID_PARAM_DOC` constants live in `framework.interfaces`.

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `TAILOR_CONFIG_DIR` | `~/.tailor` | Token, user config, rate limit files |
| `TAILOR_DATA_DIR` | `~/.tailor/data` | SQLite databases |
| `STRAVA_STREAM_CACHE_TTL_DAYS` | `7` | Stream cache eviction |

User config at `~/.tailor/user_config.json`:
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
    "tailor": {
      "command": "~/.tailor/venv/bin/python",
      "args": ["-m", "tailor", "serve"],
      "env": {
        "TAILOR_CONFIG_DIR": "~/.tailor",
        "TAILOR_DATA_DIR": "~/.tailor/data"
      }
    }
  }
}
```

## Adding a New ChildMCP (new data source)

ChildMCP onboarding has two distinct product surfaces. **Configured ingest of a *shipped* source axis** — a researcher with `.csv`, `.mat`, or REDCap-export files whose shape one of the shipped children already understands — is served by the [`tailor pilot --source={csv,matlab,redcap}`](src/tailor/pilot.py) CLI wizard. **New-axis ingest** — a vendor format, an EDF recording, a FHIR bundle, a custom binary, or another shape no shipped child understands — is served by the template child at [`src/tailor/children/template/`](src/tailor/children/template/) and the RSE-shaped guide at [`docs/guides/build-your-own-child.md`](docs/guides/build-your-own-child.md). The split is intentional: the wizard targets researchers (single command, prompts, smoke check, atomic config write); the template + guide target the RSE supporting them (~1–2 days of focused Python work). The rest of this section covers the second path (L2); for L1 reach for the wizard.

Two alternative onboarding surfaces were considered and rejected for v7.5 with named reversal conditions. **Wizard-child MCP surface** — an `MCPWizardChild` exposing `wizard_configure_*` tools the hosted LLM calls during a conversation — fails on first install (chicken-and-egg: MCP must be running to configure MCP), opens a new write-authority surface on `user_config.json` from the hosted AI, and conflicts with [ADR 0022 § Out of scope](docs/adr/0022-local-llm-guardian.md), which explicitly defers conductor-mode (LLM-driven structural action on the framework's own state) behind a future superseding ADR. *Reversal condition:* first real institutional ask for "add a source mid-conversation" ergonomics on an already-running install. **Folding wizard governance into `LocalLLMLayer`** — the local-LLM guardian composes configuration via the oracle pipeline — conflicts with [ADR 0022's `OracleResponse` schema-as-contract invariant](docs/adr/0022-local-llm-guardian.md): wizard work is *configuration authoring*, a third category beyond numerical claims and analytical prose that the schema does not model. The contract is doing real work as a structural commitment; weakening it for ergonomics is a Chesterton's-fence violation. Wizard work is also deterministic data inspection + operator confirmation + atomic write — none of those benefit from generative inference. *Reversal condition:* `OracleResponse` schema extended to model file-mutation actions AND a 7B+ model demonstrably outperforms hand-coded heuristics on cross-source pattern matching against the bundled-child shapes.

**Partial sibling-resolution by [ADR 0040](docs/adr/0040-bounded-setup-time-conductor-surface.md) (v8.0.0).** A third recipient-experience friction class surfaced after the v7.5.0 paragraph shipped — *first-install* friction for terminal-averse recipients (Taylor's 2026-05-19 macOS run). This is structurally distinct from either reversal condition above: not mid-conversation-on-running-install (Wizard-child) and not file-mutation-via-prose (LocalLLM-folded wizard). ADR 0040 carves out a **setup-time-only** bounded conductor surface via a new framework-tier `SetupLayer` exposing four MCP tools (`tailor_setup_status` / `_detect_schema` / `_confirm_schema` / `_write_source_block`). The bound that distinguishes ADR 0040 from the surfaces deferred above is a **hard-coded source-key allowlist** (`csv_dir` / `matlab_file` / `redcap_file`) gating the single write tool, routed through `pilot._write_user_config`'s existing v7.5.0 deep-merge seam, with a new `SETUP_CONFIG_WRITE` audit-row outcome for IRB-grade provenance. Both reversal conditions above remain accurate for their respective surfaces; ADR 0040 does not supersede the Wizard-child deferral (mid-conversation on running install is still deferred) and does not stretch `OracleResponse` (the schema-as-contract invariant is preserved — SetupLayer tools are deterministic, not generative). The L1 wizard CLI surface (`tailor pilot`) remains the operator/RSE path; the SetupLayer MCP surface adds a parallel recipient path. CLI commands `tailor walkthrough` and `tailor fitting-room` are **hard-removed** in v8.0.0 (no deprecation shim) and replaced by `WalkthroughLayer` + `FittingRoomLayer` MCP tools.

Children are the framework's extension point. Each one wraps one data source (today: CSV directories, MATLAB `.mat` v5/v6/v7.2 files, REDCap exports; on the deferred queue: EDF recordings, FHIR bundles, vendor sensor exports) and exposes tiered tools; the router handles everything else uniformly.

Implement 4 abstract items and register:

```python
from tailor.framework import ChildMCP, ToolDefinition, CostEstimate, ValidationSchema, ConsentInfo

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
`src/tailor/children/template/` and rename. See its
`__init__.py` for the rename checklist.

## Framework-Level Infrastructure (Not a ChildMCP)

Components that represent durable cross-session state — not biosensor domains — register directly with the router and bypass the biosensor-tier gates (consent, cost, circuit breaker, PHI scrub). Param validation and audit still apply.

`VaultLayer` is the reference implementation of this pattern:

```python
# In __main__.py cmd_serve():
from tailor.framework.vault import VaultLayer

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
| `vault_get_fitness_summary` | **Deprecated v7.6.0** (per [ADR 0038 § Amendment 2026-05-19](docs/adr/0038-vault-layer-is-data-source-agnostic.md)). Older orientation tool: aggregate weekly fitness + open themes + recent moments by scanning the index. Prefer `vault_get_snapshot`. Removal target: future v7.7.x+ when cue-card and child-dependency conditions are met. |
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

`.github/workflows/ci.yml` runs on push/PR to `main` across Ubuntu, Windows, macOS × Python 3.10/3.11/3.12. Steps: install deps → `pytest -v` → `tailor --help`.
