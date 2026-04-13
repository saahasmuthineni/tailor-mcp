# Roadmap

Work that came up during the research-shift planning and is explicitly
deferred. Each item is a one- or two-sentence description plus why it
matters for the research framing. No implementation details — this
document is a list, not a design doc.

## Real PHI-scrubbing implementations behind the `PHIScrubber` slot

`PHIScrubber.scrub()` ships today as a documented no-op seam. The
roadmap items are institutional-policy-specific implementations:
transforms that drop or hash identifying fields before results leave
the router, bound to the specific shape of a CGM child, a sleep child,
a FHIR-bundle child, etc. Getting this right requires an actual study
to anchor the policy against; it is deliberately not a framework-level
decision.

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
- **Generic CSV directory child** — given a directory of per-subject
  CSVs with a declared timestamp column and value schema, expose
  tiered analytical tools. The lowest-lift path from bespoke
  per-study scripts to framework-governed tooling.
- **EDF file child** — direct ingestion of European Data Format
  recordings common in sleep and EEG research.
- **FHIR bundle child** — ingestion of FHIR bundles for lab values,
  medication histories, or vitals. Bridges clinical data into the
  same governance pipeline.

## Per-subject parameter scoping on existing tools

The research-shift release makes `subject_id` a first-class column on
the audit log and threads it through the router from call parameters
to every audit row in that dispatch path. What it does **not** yet do
is require or even accept `subject_id` as a declared tool parameter
on existing children (running, vault). Adding it cleanly means
deciding how the vault keys notes by subject — which is a design
question worth answering deliberately rather than retrofitting.

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

One end-to-end walkthrough — from raw dataset through tiered access,
vault theme creation, evidence accumulation, and final derived
metric — against a published analytical question on a public dataset.
This is the document an RSE sends to a PI to explain what the
framework actually buys them.

## Evaluation harness for LLM-client behavior

Different LLM clients (Claude Desktop, Claude API directly, third-
party MCP clients) will vary in how they handle the consent and cost
gate prompts. An evaluation harness that replays scripted analytical
conversations through different clients and measures gate compliance,
scope drift (did the LLM expand the scope of a consent it was
granted?), and vault-recall accuracy (did the LLM actually consult
existing themes before writing a new one?) would make the "client-
agnostic governance" claim measurable.
