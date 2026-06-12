# CLAUDE.md — Tailor

> **Note for human contributors:** This file is read automatically by Claude when working in this repo. If you're a human contributor, see [CONTRIBUTING.md](CONTRIBUTING.md) instead.

> **v9.2.0 (2026-06-12)** — `tailor inspect --data-dir DIR`. Minor
> bump. One new flag on the existing inspector verb; no breaking
> changes, no schema changes, no new commands (CLI surface stays
> seven per ADR 0043).
>
> The v9.1.0 inspector resolved its data directory only via
> `$TAILOR_DATA_DIR` / the `~/.tailor/data` default, so pointing it
> at any other `audit.db` + `vault.db` location meant setting an
> environment variable before launch — `--data-dir` was an operator's
> reasonable first guess on 2026-06-12 and didn't exist. The flag now
> overrides the env-var resolution per invocation (precedence: flag >
> `$TAILOR_DATA_DIR` > default) on both the serve and `--export`
> paths. Fail-fast posture: an explicitly named directory that does
> not exist is rejected at the CLI boundary (argparse error, exit 2)
> — a typo'd path silently rendering the honest-empty "No audit
> database yet" page is the same confusion class the flag closes. An
> existing directory without databases keeps the ADR 0043
> honest-empty contract. Inspector internals untouched:
> `run_inspector` / `export_page` always took `data_dir` as a
> parameter; only the CLI boundary changed. No ADR amendment — per
> the `tailor pilot --source` precedent (v7.5.0), flag additions to
> an existing verb ship as a minor bump + CHANGELOG; ADR 0043's
> surface contract governs command count, not per-command flags.
>
> **Gates: 1,820 passed, 3 scipy skips.** ruff clean; 76/76 security
> probe; CLI smoke clean (7 verbs discoverable, new flag in
> `inspect --help`, exit-2 typo guard verified); end-to-end
> `--export` provenance check against a populated non-default dir
> with a decoy `$TAILOR_DATA_DIR` confirmed flag-beats-env. Net-new
> tests: 3 (flag-overrides-env, nonexistent-dir exit 2,
> existing-empty-dir honest-empty — `tests/inspector/test_export.py`).
> `recipient-install-validator` file-gated on `__main__.py` —
> flagged, skipped per the v6.11.x falsification precedent (not an
> install-path change). `mcp-protocol-auditor` /
> `cue-card-rehearsal-auditor` NOT TRIGGERED (no router / wire-shape /
> ToolDefinition changes).

> **v9.1.0 (2026-06-10)** — Read-only inspector (`tailor inspect`).
> Minor bump. New feature, no breaking changes, no schema changes.
>
> Implements [ADR 0043](docs/adr/0043-read-only-inspector-not-application.md)
> ("inspector, not application"): a read-only, localhost-only,
> stdlib-only HTML visibility surface over `audit.db` and the
> `vault.db` index, running as a standalone process that never
> registers with the router. The audit log — previously consumable
> only via shell `sqlite3`, `tailor status`, or the model-mediated
> `audit_query` tool (ADR 0039) — gains an independent,
> **non-model-mediated** rendered channel: gate activity by outcome
> (refusal badges with plain-language gate explanations), recent
> calls with collapsed `params`/`error`, a consent timeline derived
> from approve/revoke audit rows (labeled derived-not-live), scrubber
> posture (prominent warning when the no-op default appears), token
> estimate sums, and vault index counts (titles/slugs only — Ledger
> headline, Wardrobe counts-only per ADR 0033).
>
> **New package `src/tailor/inspector/`** (`queries.py` read-only SQL
> via URI `mode=ro`, `render.py` pure HTML with all escaping +
> home-redaction, `server.py` GET-only `http.server` on hard-coded
> `127.0.0.1`). **CLI surface grows 6 → 7 commands** (`tailor
> inspect`; flags `--port` / `--no-browser` / `--export FILE`) — a
> deliberate, ADR-documented amendment of the ADR 0040 surface
> contract. Stage 1 (summoned) of the ADR 0043 invocation ladder
> only; Stages 2–3 (ambient opt-in, default-on) are designed,
> trigger-gated, and NOT built; the MCP spawner tool is rejected with
> a named reversal condition — the verification channel is not
> mediated by the entity it verifies.
>
> **ADR 0039 carve-out, named:** the page renders raw `params`/`error`
> (collapsed, home-redacted, HTML-escaped) because it is the
> operator-shell path rendered — the same custodian audience ADR 0039
> points at `sqlite3 audit.db` — not the hosted-LLM transcript the
> allowlist protects. Residual documented: foreign-user paths /
> child-written identifiers in `params` render verbatim under the
> custodian assumption. `--export` artifacts are operator-managed
> retention — named as the sixth retention category in
> `docs/design/research-framing.md`.
>
> **Gates: 1,712+ passed, 3 scipy skips.** ci-gate-runner SHIPPABLE;
> adr-weigher PASS (all five criteria); integration-auditor
> proposal-mode REVISE → 4 conditions closed; phi-irb-risk-reviewer
> WATCH → closed (sixth retention category + custodian assumption);
> coverage-criticality-mapper REGRESSION → closed (localhost-bind
> failure branch + redact_home fallback guards now tested);
> red-team-reviewer OBJECTION (medium) → closed (locked-DB honesty
> paths regression-guarded by forced-failure tests). PR-review bots
> caught two post-gate defects, both fixed pre-merge: a Windows
> SQLite URI bug (bare `file:C:/...` parses as relative —
> `Path.as_uri()` now) and a None-outcome render crash guard.
> CI matrix green across Ubuntu/Windows/macOS × 3.10–3.12 + DCO.
> `mcp-protocol-auditor` / `cue-card-rehearsal-auditor` NOT TRIGGERED
> (no router / wire-shape / ToolDefinition changes);
> `recipient-install-validator` file-gated on `__main__.py`, flagged,
> skipped per the v6.11.x falsification precedent. Shipped via
> PR #148 (built from the spec merged in PR #146).

> **v9.0.2 (2026-06-02)** — Public-surface name scrub. Patch bump. No
> API or behavior change beyond variant/server-id and fixture-path
> renames described below.
>
> A collaborating research lab was named in the public repo and in the
> shipped PyPI wheel; this release removes that exposure. Concretely:
> a co-author's personal name removed entirely from all in-repo
> occurrences; a PI's name reduced to a single allowed published-paper
> citation ("Hunter & Senefeld 2024, J Physiol") wherever the
> scientific reference is load-bearing; the lab's name genericized to
> "cohort demo" or "demo cohort" throughout comments, docstrings,
> path names, and documentation. Three internal pitch artifacts were
> moved out of the repo and git-removed (they existed under a
> lab-named subdirectory of `examples/` and contained names that were
> appropriate for internal use but not for a public repo). No scientific content
> was altered; only the naming changed.
>
> **Concrete renames.** The bundled `_fixtures` demo directory
> (previously named for the lab) is now `cohort_demo_realistic`.
> The fitting-room demo variant (previously named for the lab) is now
> `cohort` (`tailor-fitting-room-cohort`); the demo path is
> `demos/cohort`. The realistic cue card and all related example
> scripts updated to use generic "cohort demo" / "demo cohort"
> naming throughout. `examples/cohort_demo/` replaces the
> lab-named examples directory.
>
> **Benchmark sync.** `benchmarks/token_efficiency.md` and
> `benchmarks/token_efficiency.py` updated to reflect the current
> fixture layout; the session-resume efficiency ratio is now **318.2x**
> (was 318.0x in the v9.0.0 artifact — minor numeric refinement from
> updated fixture token counts). Per-query ratios unchanged:
> 657.6x / 938.2x.
>
> **No router / security / child / CLI architecture changes.** The
> `child.py` and `framework/vault/layer.py` diffs are comment and
> docstring rewrites only — no ToolDefinition schema changes, no
> wire-shape changes. CUE_CARD.md is a path rename (from the
> lab-named directory to `cohort_demo/realistic/`); the tool
> mappings and parameter shapes are unchanged.
>
> **Gates: 1,509 passed, 2 skipped** (scipy-absent, orthogonal).
> Subprocess wire-test suite (98 passed, 1 skipped) confirmed clean
> in a dedicated re-run after flakiness observed in full-suite
> parallel run (port-contention on Windows). ruff clean. 76/76
> security probe. CLI smoke: 6 commands discoverable.
> `cue-card-rehearsal-auditor` / `mcp-protocol-auditor` glob-triggered
> by the child.py + vault/layer.py comment changes — no ToolDefinition
> schema or wire-shape changes in those files; gate composition
> surfaced, not attested. `recipient-install-validator` triggered
> by `_fixtures/` + `fitting_room.py` + `__main__.py` — opt-in only,
> not run (name-scrub fixture rename, not an install-path change).

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
>   ~$11.58 baseline vs ~$0.04 with Tailor at Sonnet 4.6 input
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
> identifier renames. One new ADR — [ADR 0041](docs/adr/0041-license-apache-2-0-to-agpl-3-0-or-later.md),
> recording the license switch. No new framework-tier layers. No
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
> wipes fitting-room's `tailor-fitting-room-cohort` Claude Desktop
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
> 8 new tools are MCP-tool surfaces not yet on the bundled demo cohort
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

> **Earlier release history (v7.6.0 and before): see [CHANGELOG.md](CHANGELOG.md).**
> The full per-version banner history (v3.0 → v8.0.0) lives in CHANGELOG.md and in
> this file's git history. The v7.6.0 → v6.0 banners were pruned from CLAUDE.md on
> 2026-05-29 to cut per-session context cost (the banner stack was the largest thing
> in the file and is redundant with CHANGELOG.md). v9.0.0 (current) and v8.0.0 (prior
> major — carries the current six-command CLI + framework-layer architecture) are
> retained inline above as live orientation. Pruned banners were preserved verbatim
> in git history per the doc-truth / historical-record principle — removed from the
> live steering doc, not rewritten.

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
| [`recipient-install-validator`](.claude/agents/recipient-install-validator.md) | End-to-end recipient-install validation — provisions a clean Windows 11 base box via VirtualBox + Vagrant, installs the freshly-built wheel via the documented recipient command, runs `tailor pilot` (the sole recipient-facing CLI touch per ADR 0040 / v8.0.0), validates per-path Claude Desktop config (per ADR 0026), exercises the `WalkthroughLayer` / `FittingRoomLayer` MCP tools that replaced the hard-removed `walkthrough` / `fitting-room` CLI verbs (per ADR 0040), and runs wheel-install-dependent pytest in-guest. Catches the failure class that produced the v6.10.1–v6.10.4 patch quartet — bugs that exist between the wheel artifact and a stranger's machine, invisible to host-side gates that test against the dev tree | Mandatory + file-touched-gated. Fires when any of `fitting_room.py`, `pilot.py`, `__main__.py`, `wizard.py`, `pyproject.toml` package-data globs, or `_fixtures/**` are modified in a release branch. Promoted v6.11.0 per [ADR 0028](docs/adr/0028-recipient-install-validation-as-release-gate.md) — the gate composes at `release-shipper` with `ci-gate-runner` (host: dev-tree pytest) and `recipient-install-validator` (guest: wheel-installed package) |

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
  __main__.py              # CLI: serve | pilot | setup | redcap | status |
                           #   inspect | uninstall | --help (seven-command
                           #   surface per ADR 0043; was six per ADR 0040 /
                           #   v8.0.0; walkthrough + fitting-room remain MCP
                           #   framework layers)
  pilot.py                 # Multi-subject CSV pilot wizard (v6.2.1)
  fitting_room.py          # Library module — pure scaffolder/index helpers
                           #   wrapped by FittingRoomLayer MCP tools (CLI verb
                           #   hard-removed v8.0.0 / ADR 0040; helpers retained)
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
    setup/                 # SetupLayer — bounded setup-time conductor
                           #   surface, 4 MCP tools (ADR 0040)
    setup_help/            # SetupHelpLayer — conditionally registered
                           #   when no source is configured (v6.10.2)
    audit_query/           # AuditQueryLayer — audit_query tool under
                           #   column allowlist (ADR 0039)
    walkthrough/           # WalkthroughLayer — 5-section recipient
                           #   walkthrough as MCP tool (ADR 0040)
    fitting_room/          # FittingRoomLayer — status/scaffold/index
                           #   MCP tools wrapping fitting_room.py (ADR 0040)
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
    force_csv/             # Force-trial CSV child (multimodal-physiology
                           #   family; opt-in via force_csv config key)
      __init__.py          # Exports ForceCsvChild, ForceCsvProcessing
      child.py             # ForceCsvChild(ChildMCP) — 9 tools, 3 tiers;
                           #   Bland-Altman device agreement, event labels
      processing.py        # ForceCsvProcessing — stateless analytics
    emg_csv/               # EMG-envelope CSV child (sibling to force_csv;
                           #   opt-in via emg_csv config key)
      __init__.py          # Exports EmgCsvChild, EmgCsvProcessing
      child.py             # EmgCsvChild(ChildMCP) — 8 tools, 3 tiers;
                           #   fatigue diagnostics, event labels
      processing.py        # EmgCsvProcessing — stateless analytics
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
    strong_motion/         # COSMOS V1 strong-motion child (issue #114; stdlib-only)
      __init__.py          # Exports StrongMotionChild, StrongMotionProcessing
      child.py             # StrongMotionChild(ChildMCP) — 5 tools, 3 tiers
      parser.py            # COSMOS V1 fixed-width text parser (no scipy)
      processing.py        # StrongMotionProcessing — stateless analytics
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
                           #   against bundled demo cohort fixtures (ADR 0027)
  inspector/               # Read-only trust-visibility surface (ADR 0043) —
                           #   standalone process, NOT a framework layer;
                           #   never registers with the router
    __init__.py            # Exports run_inspector, render_page, export_page
    queries.py             # Read-only SQL (URI mode=ro) → plain dicts
    render.py              # Dicts → HTML (all escaping + home-redaction here)
    server.py              # http.server on hard-coded 127.0.0.1; GET-only

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
    force_csv/
      test_force_csv_shape.py      # Shape + handler tests for ForceCsvChild
      test_force_csv_processing.py # Pure-function tests (MVC window, Bland-Altman)
    emg_csv/
      test_emg_csv_shape.py        # Shape + handler tests for EmgCsvChild
      test_emg_csv_processing.py   # Pure-function tests (RMS, iEMG, fatigue index)
    matlab_file/
      test_matlab_shape.py     # Shape + handler tests (scipy-required; skip if missing)
      test_matlab_processing.py  # Pure-function tests (no scipy)
    redcap/
      test_redcap_shape.py     # Shape + handler tests for RedcapFileChild
      test_redcap_processing.py  # Pure-function analytics tests
      test_redcap_scrubber.py    # RedcapPHIScrubber identifier-flag enforcement tests
    strong_motion/
      test_strong_motion_shape.py      # Shape + handler tests for StrongMotionChild
      test_strong_motion_parser.py     # COSMOS V1 fixed-width parser tests
      test_strong_motion_processing.py # Pure-function analytics tests (PGA, Arias, Sa)
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

## Force CSV Child — 9 Tools

Opt-in via `force_csv` key in `user_config.json`. Wraps a local directory of force-trial CSV files (dynamometry / force-plate traces) — the first member of the multimodal-physiology child family alongside `emg_csv`. Shares `metadata.json` sidecar cohort grouping with `csv_dir` per [ADR 0015](docs/adr/0015-tier-1-cohort-surface-and-metadata-sidecar.md); per-trial analyst event labels persist to SQLite (`force_csv.db`).

| Tool | Tier | Description |
|------|------|-------------|
| `force_list_files` | 1 | List force-trial files with sample-rate, channel count, columns |
| `force_file_detail` | 1 | Per-file metadata + per-column summary statistics |
| `force_summary` | 1 | Per-file fatigability diagnostic: peak force (Sánchez 250 ms window), decline %, time-to-50%-drop |
| `force_cohort_summary` | 1 | Cross-file aggregation by metadata-sidecar group |
| `force_compare_trials` | 1 | Side-by-side comparison of 2–5 trial files |
| `force_device_agreement` | 1 | Bland-Altman paired-device validation (bias, limits of agreement) |
| `force_label_event` | 1 | Persist an analyst-authored protocol-event label for a trial |
| `force_downsampled` | 2 | Decimated force stream at every Nth sample |
| `force_raw_window` | 3 | Raw per-sample force within a bounded time window (cost-gated) |

Config shape: `force_csv` block with `path` (required), plus optional `timestamp_column`, `timestamp_format`, `sample_rate_hz`, and `value_columns` (e.g. `{"force": "Force (N)"}`). Cohort grouping uses the same `<force_csv.path>/metadata.json` sidecar schema as `csv_dir`.

## EMG CSV Child — 8 Tools

Opt-in via `emg_csv` key in `user_config.json`. Sibling to `force_csv` — wraps a local directory of EMG-envelope trial CSV files with the same off-the-blueprint posture. Fatigue diagnostics (RMS, mean activation, integrated EMG, fatigue index) over rectified/smoothed envelope traces; per-trial analyst event labels persist to SQLite (`emg_csv.db`). Shares `metadata.json` sidecar cohort grouping with `csv_dir` per [ADR 0015](docs/adr/0015-tier-1-cohort-surface-and-metadata-sidecar.md).

| Tool | Tier | Description |
|------|------|-------------|
| `emg_list_files` | 1 | List EMG envelope trial files with sample-rate, channel count, columns |
| `emg_file_detail` | 1 | Per-file metadata + per-column summary statistics |
| `emg_envelope_summary` | 1 | Per-file fatigue diagnostic: RMS, mean activation, integrated EMG, fatigue index |
| `emg_cohort_summary` | 1 | Cross-file aggregation by metadata-sidecar group |
| `emg_compare_trials` | 1 | Side-by-side comparison of 2–5 trial files |
| `emg_label_event` | 1 | Persist an analyst-authored protocol-event label for a trial |
| `emg_downsampled` | 2 | Decimated envelope stream at every Nth sample |
| `emg_raw_window` | 3 | Raw per-sample envelope within a bounded time window (cost-gated) |

Config shape mirrors `force_csv`: an `emg_csv` block with `path` (required) plus the same optional `timestamp_column` / `timestamp_format` / `sample_rate_hz` / `value_columns` keys.

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

## Strong Motion Child — 5 Tools

Opt-in via `strong_motion` key in `user_config.json`. Wraps a local directory of COSMOS Volume-1 (uncorrected acceleration) strong-motion records — the earthquake-engineering worked example shipped for the launch (issue #114). Stdlib-only: the COSMOS V1 format is fixed-width text, so unlike `matlab_file` it needs no optional extra. Record files are recognized by extension (`.v1` / `.raw`, case-insensitive); one file = one channel = one record.

| Tool | Tier | Description |
|------|------|-------------|
| `seismic_list_records` | 1 | List V1 record files with channel metadata |
| `seismic_record_summary` | 1 | Peak ground acceleration, Arias intensity, significant duration, response spectra Sa(T) |
| `seismic_cohort_summary` | 1 | Cross-record aggregation by metadata-sidecar group (same `metadata.json` pattern as `csv_dir`; see ADR 0015) |
| `seismic_downsampled` | 2 | Decimated acceleration trace at every Nth sample |
| `seismic_full_trace` | 3 | Full per-sample acceleration trace with precision reduction |

Subject scoping per [ADR 0002](docs/adr/0002-subject-id-scoping.md) / [ADR 0009](docs/adr/0009-vault-subject-keying.md): `entity_id` is the station-event code (one record). It is audit-log scoping only and does NOT filter source data — there is one record per call. `purge_cache` is a no-op per [ADR 0013](docs/adr/0013-cache-only-purge-on-consent-revocation.md): the framework owns no derivative cache; records are re-parsed from disk on every call.

Config shape in `~/.tailor/user_config.json`:

```json
"strong_motion": {
  "path": "/path/to/cosmos/v1/directory"
}
```

`path` is the only key. Cohort grouping uses the same `<strong_motion_dir>/metadata.json` sidecar schema as `csv_dir` (`{"<filename>": {"<field>": <value>, ...}}`).

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

# Subcommands (seven-command surface per ADR 0043; six per ADR 0040 + inspect)
tailor serve         # Start MCP server (Claude Desktop calls this)
tailor pilot         # Multi-subject CSV pilot setup wizard (v6.2.1+)
tailor setup         # Strava OAuth wizard for the worked-example child
tailor redcap        # REDCap export-directory setup + re-attestation
tailor status        # Diagnostic check
tailor inspect       # Read-only localhost page over audit.db + vault.db
                     #   (--port / --no-browser / --export FILE /
                     #   --data-dir DIR; ADR 0043)
tailor uninstall     # Remove Tailor's Claude Desktop registration + state
# Recipient walkthrough + fitting-room are no longer CLI verbs — they run as
# WalkthroughLayer / FittingRoomLayer MCP tools driven from Claude Desktop
# chat (hard-removed in v8.0.0, no shim, per ADR 0040).
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
