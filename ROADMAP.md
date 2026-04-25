# Roadmap

Work that's explicitly deferred — what the framework is *not* yet, and
why each item matters for the research framing. Each section is a
one- or two-sentence pitch plus context; no implementation details.

## At a glance

| Item | Effort | Impact | Unblocks |
|---|---|---|---|
| [New ChildMCPs (CGM / sleep / ECG / EDF / FHIR)](#new-childmcps-for-research-relevant-data-sources) *(template skeleton + CSV child shipped — see that section)* | M–L | High | Broader adoption |
| [Per-subject `subject_id` on vault tools](#per-subject-parameter-scoping-on-vault-tools) | S–M | Medium | Multi-participant vault organization |
| [Real PHI-scrubbing implementations](#real-phi-scrubbing-implementations-behind-the-phiscrubber-slot) | M | High | Any deployment with actual PHI |
| [Per-analyst attribution on vault evidence](#per-analyst-attribution-on-vault-evidence-blocks) | S | Medium | Multi-analyst studies |
| [Deterministic mode + seed control](#deterministic-mode-with-seed-control) | S | Medium | Reproducible paper results |
| [Provenance hashing on derived metrics](#real-provenance-hashing-on-derived-metrics) | M | Medium | Byte-level reviewer traceability |
| [Vault-freeze for manuscript submission](#freeze-vault-operation-for-manuscript-submission) | S | Medium | Submission-ready snapshots |
| ~~[Worked-example notebook](#worked-example-notebook-against-a-published-analytical-question)~~ *(shipped — [docs/guides/worked-example.ipynb](docs/guides/worked-example.ipynb))* | — | — | — |
| [LLM-client evaluation harness](#evaluation-harness-for-llm-client-behavior) | M | Medium | Making the governance claim measurable |

Effort: S (days), M (weeks), L (month+). Impact reflects research value,
not engineering elegance.

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

As of the codebase-review pass, the no-op default emits a one-time
warning on first construction and exposes a `scrubber_id` property
(`"noop"` vs subclass name) so audit rows on a misconfigured
deployment are distinguishable from ones produced under a real
policy.

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

The research-shift release makes `subject_id` a first-class column on
the audit log and threads it through the router from call parameters
to every audit row in that dispatch path. `RunningChild` now declares
`subject_id` on all 12 `strava_*` tools (audit scoping for data
access; see ADR 0002 update). What remains is vault adoption.

Declaring `subject_id` on vault tools is not a mechanical copy of the
running-child work: the vault organizes analytical memory across
sessions, and adding per-subject scoping means deciding how vault
notes and themes are *keyed* by subject — do evidence blocks carry a
subject, do themes span subjects, does `vault_search_notes` filter by
subject, what happens to cross-subject insights, how do existing
un-keyed notes migrate? That's a design question worth answering
deliberately rather than retrofitting.

## Per-analyst attribution on vault evidence blocks

Evidence blocks on theme notes are currently timestamped but
unattributed. In multi-analyst studies, "who recorded this
observation" is load-bearing context. A vault-writer parameter for
analyst identity, threaded through to the evidence block's
frontmatter and rendered in the Obsidian view, is the clean version.

## Deterministic mode with seed control

Several analytical functions touch pseudo-randomness (anomaly
sampling, downsampling variants). For reproducibility-critical
analyses, a deterministic-mode flag that pins every seed from a
single audited entry point would let reviewers re-run an analysis and
get byte-identical outputs. Coordinated with provenance hashing,
below.

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

---

## Contributing

These items are all roadmap-level, not ticketed. If one of them is
the reason you showed up, open a discussion or issue on GitHub first
— some have real design questions (especially the `subject_id` →
vault keying question and the per-analyst attribution one) that are
worth talking through before code.
