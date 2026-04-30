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

Effort: S (days), M (weeks), L (month+). Impact reflects research value,
not engineering elegance.

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
[ADR 0008](docs/adr/0008-deterministic-by-construction-processing.md)
and the v6.2 shipped section for the drift-audit context).

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
  exposes 5 tiered analytical tools. Opt-in via `csv_dir` key in
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

---

## Contributing

These items are all roadmap-level, not ticketed. If one of them is
the reason you showed up, open a discussion or issue on GitHub first
— some have real design questions (especially the `subject_id` →
vault keying question and the per-analyst attribution one) that are
worth talking through before code.
