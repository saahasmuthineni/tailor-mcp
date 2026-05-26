# ADR 0015: Tier-1 cohort aggregation is a first-class surface; group identity travels via a metadata sidecar

- **Status:** Accepted
- **Date:** 2026-04-30
- **Renamed in v9.0.0 (2026-05-26):** the `csv_dir` cohort tool was renamed `csv_cohort_summary` → `csv_group_summary` as part of the public-flip domain-agnostic vocabulary sweep. The metadata-sidecar shape and cohort statistics contract are unchanged. The biometric children's sibling tools — `force_cohort_summary`, `emg_cohort_summary`, `redcap_cohort_summary` — retain their `_cohort_` names because they ARE cohort-shaped in the research sense; the rename applies only to the generic CSV-directory child where "group" is more accurate.
- **Related:** [ADR 0001 (Audit log is the backbone)](0001-audit-log-as-backbone.md), [ADR 0002 (entity_id scoping)](0002-subject-id-scoping.md), [ADR 0008 (Deterministic-by-construction processing)](0008-deterministic-by-construction-processing.md), [ADR 0009 (Vault entity-keying)](0009-vault-subject-keying.md), [ADR 0014 (Coverage criticality invariant)](0014-coverage-criticality-invariant.md), [CLAUDE.md § Three-Tier Access Model](../../CLAUDE.md#three-tier-access-model)

## Context

The framework's three-tier access model ([CLAUDE.md § Three-Tier
Access Model](../../CLAUDE.md#three-tier-access-model)) commits to a
load-bearing claim: *most analytical questions are answerable at
Tier 1 with zero raw biometric data leaving the machine.* The model
is correct in design — Tier-1 returns server-computed reports;
streams only travel under explicit consent (Tier 2) or cost approval
(Tier 3).

Until v6.5.0 the running code did not satisfy that claim for the
`csv_dir` child on any analytical question that requires *cross-file
aggregation*. The Tier-1 surface (`csv_summary_report`) returned
per-file mean/min/max/std with no cohort grouping and no curve
fitting. An LLM asked *"compare time-to-failure between male and
female subjects"* against a per-subject CSV directory had three
bad paths: (1) fabricate a cohort number from per-file `min`/`mean`
values — mathematically wrong, undetectable to non-experts but
visible to a domain expert; (2) escalate to Tier 2, pulling
`csv_downsampled` for every file in the directory and computing the
cohort statistic in-context — honest but firing the consent gate
N times mid-conversation and contradicting the *"no streams enter
LLM context"* claim Tier 1 is supposed to demonstrate; (3) refuse
to answer, exposing the gap as a structural limitation.

The proposal-mode audit on the v6.5.0 HIP-Lab demo plan named this
gap as the highest-leverage decision in the build:

> "*The single highest-leverage decision is whether to ship a
> `csv_group_summary` Tier-1 tool before the demo. Without it, Wow
> Moment 1 is structurally a Tier-2 demo dressed up as Tier-1.*"

The audit also surfaced the bound problem: cross-file aggregation
requires *group identity* per file — sex, study arm, age bucket,
condition. The `csv_dir` child to date had no mechanism for
per-file metadata. The two existing workarounds were both fragile:
(a) encode group in the filename (`S001_M.csv`) and parse it in the
LLM — works for one field, fragile under ambiguity, surfaces the
parsing logic into the LLM context where it should not be; (b)
pass a `group_map` parameter at every call — forces the caller to
re-construct the same mapping repeatedly, which is exactly the
state the architecture is supposed to externalize.

The question this ADR answers: *what is the smallest Tier-1 surface
that lets the framework's "no streams enter LLM context" claim
hold for cohort questions, and how does group identity travel
without leaking parsing logic into either the LLM or the caller?*

## Decision

Two new Tier-1 tools land on `CSVDirectoryChild`. Group identity
travels via a sidecar JSON file at `<csv_dir>/metadata.json`. The
demo walkthrough at `examples/hip_lab_demo/` is the proof-of-concept
that demonstrates the surface against a synthetic study.

**`csv_group_summary` (Tier 1, ~300 tokens).** Reduces every CSV in
the directory to a per-file scalar by metric, groups by a metadata
field, returns per-group n/mean/std/min/max plus the file list per
group. The metric vocabulary is the new module-level constant
`COHORT_METRICS` in
[`children/csv_dir/processing.py`](../../src/tailor/children/csv_dir/processing.py):
`mean`, `max` (alias `peak`), `min`, `std`, `first`, `last`,
`duration_s`, `time_to_50pct_drop_s`. The first two require no
timestamps; the latter two require a usable timestamp column on
each file. Files lacking the metadata sidecar entry, lacking the
group-by field, or failing to load are surfaced via
`missing_metadata`, `missing_group_field`, and `load_errors` keys
on the result so the LLM can flag the gap rather than silently
under-counting. The handler scans every CSV in the configured
directory up to a `MAX_COHORT_FILES` cap (default 64 — typical
pilot-study scale per ADR 0009). Files larger than `MAX_CSV_BYTES`
are skipped with a load error; a directory of any size that fits
within those caps reduces to a single result dict no larger than
~300 tokens regardless of input size.

**`csv_force_decline` (Tier 1, ~250 tokens).** Per-file fatigue
diagnostic over a single column: peak, peak index, peak time,
end value, total decline %, decline rate per minute, and
time-to-50%-drop. The tool is generic over any monotonically
fatigueing measurement (force, EMG envelope, power, attention)
— the column choice and what counts as "fatigue" are the caller's
domain question. The handler delegates to
`CSVProcessing.force_decline_summary` which is a pure function
of the values + timestamps; ADR 0008's no-PRNG, no-clock invariant
holds.

**`metadata.json` sidecar.** Optional file at `<csv_dir.path>/metadata.json`.
Schema: `{"<csv_filename>": {"<field>": <value>, ...}, ...}`.
Loaded on demand by the handler — never cached at init, so a user
editing the sidecar between calls sees the change on the next
invocation. The file is required for `csv_group_summary` and
ignored by every other tool. The sidecar is a JSON file (not YAML)
to match the existing `user_config.json` posture and avoid pulling
a YAML parser into the runtime dependency surface.

The shape of the new tools matches the existing ChildMCP contract:

- Tier 1, free, no consent gate. The cohort summary returns
  aggregate statistics; raw rows never enter the result. Honest
  on-architecture: *no streams cross into LLM context for any
  question answerable by these tools*.
- `entity_id` declared in both `tool_definitions` and
  `param_schemas` per ADR 0002. Audit-log scoping carries through
  unchanged.
- Pure-function processing per ADR 0008. `aggregate_metric`,
  `cohort_stats`, and `force_decline_summary` are all
  `@staticmethod` with no PRNG and no clock reads. The seeded-PRNG
  exception list in ADR 0008 is unchanged.
- `_meta` provenance stamps fire on every successful response
  unchanged. `scrubber_warning` continues to surface the default
  no-op scrubber when applicable per ADR 0003 / v6.3.1.

The sidecar mechanism is intentionally minimal:

- No required schema beyond the filename → field-map shape.
  Studies record whatever metadata is meaningful (sex, study arm,
  age bucket, recording condition, entity_id).
- No write API at the Tier-1 surface. The framework reads the
  sidecar; the deployer writes it (typically as part of dataset
  packaging from REDCap export, lab CSV dump, etc.). This matches
  the institutional-source-files pattern established in ADR 0013
  for csv_dir's purge-cache no-op: *the CSV files at csv_dir.path
  are institutional artifacts the deployer manages*.
- No automatic linkage to `entity_id`. A study can record
  `entity_id` as one of the metadata fields if it wants the
  audit-log scoping to match the cohort-grouping field; nothing
  forces it. A multi-subject CSV per-file (rare but possible)
  remains coherent because the sidecar lives at file granularity.
- **Out-of-band of the PHI-scrubber seam.** The sidecar is read by
  the cohort handler and used for grouping, but its contents never
  enter a tool result — `csv_group_summary` returns per-group
  *stats*, not per-subject metadata rows. ADR 0003's `DataScrubber`
  seam therefore never sees `metadata.json`. A deployer who packs
  HIPAA Safe Harbor §164.514(b)(2) identifiers (full DOB, ZIP at
  5-digit precision, full name, etc.) into the sidecar ships PHI
  the framework has no awareness of. The IRB-cleared posture
  treats `metadata.json` as institutional-source data: schema
  narrowed to research-meaningful fields (e.g. `age` in years not
  full DOB, condition code not free-text notes), bucketed where
  Safe Harbor demands, and reviewed at the source by the data
  pipeline that exports it. The framework guarantees only that the
  sidecar contents do not leak into LLM context unless the
  deployer asks for them; it does not police the schema.

## Criticality classification

Per [ADR 0014](0014-coverage-criticality-invariant.md), this ADR
declares the criticality classification of the new code regions in
the same change:

- **`children/csv_dir/processing.py:aggregate_metric`,
  `cohort_stats`, `force_decline_summary`** — **MEDIUM**. Pure-
  function analytics; mathematical correctness is the primary
  defence per ADR 0008. Coverage on the metric branches and the
  cohort-stats reducer is desirable; new uncovered code on these
  paths is a finding worth noting but not blocking.
- **`children/csv_dir/child.py:_handle_cohort_summary`,
  `_handle_force_decline`, `_load_metadata_sidecar`,
  `_extract_timestamps`** — **HIGH**. Child `execute()` paths
  per ADR 0014's HIGH taxonomy. The metadata-sidecar loader is the
  fail-closed boundary against malformed or missing sidecar files;
  the cohort handler is the structural fix for the *"no streams
  enter LLM context"* claim. New uncovered code on these paths
  after a diff is `COVERAGE REGRESSION`.
- **`children/csv_dir/child.py:tool_definitions`,
  `param_schemas`** — **HIGH**. Schema declaration paths
  (ADR 0014). New tools must declare `entity_id` in both surfaces
  per ADR 0002.
- **The new tool surface in router-reachable dispatch** —
  inherits from `framework/router.py`'s existing CRITICAL
  classification under ADR 0014. No new code lands in the router
  itself; the existing dispatch path is unchanged.

The `coverage-criticality-mapper` agent prompt cites this ADR's
classification on subsequent diffs touching these regions.

## Consequences

**Positive.**

- The framework's *"no streams enter LLM context"* claim becomes
  load-bearing for cohort questions, not just per-subject ones.
  Wow Moment 1 of the HIP-Lab demo can ground in the architecture
  rather than dressing up a Tier-2 escalation. Future ChildMCPs
  (CGM, EDF, sleep) inherit the cohort-aggregation pattern at
  Tier 1 by design.
- The metadata sidecar resolves the `csv_dir` per-file metadata
  gap with a pattern that matches research-dataset packaging
  conventions (data files + metadata table — REDCap, DataCite,
  Frictionless Data spec all use the shape). Studies do not have
  to encode metadata in filenames or pass `group_map` at every
  call.
- The two-step factoring (`aggregate_metric` reduces one file;
  `cohort_stats` reduces the cohort) is exposed as separately
  testable pure functions. Per ADR 0008 / ADR 0014, mathematical
  correctness is testable without integration infrastructure;
  the new tests in
  [`tests/children/csv_dir/test_csv_processing.py`](../../tests/children/csv_dir/test_csv_processing.py)
  cover both reducers as pure functions.
- The handler-level fail-closed paths (sidecar missing, sidecar
  malformed, file metadata missing the group field, file load
  error per CSV) are surfaced as named keys on the result rather
  than swallowed. The LLM sees the gap and can flag it back to
  the analyst rather than silently under-counting subjects.
- The `MAX_COHORT_FILES` cap bounds the Tier-1 cost — a directory
  of 1,000 CSVs returns an explicit error rather than scanning a
  thousand files synchronously and burning audit-log latency.

**Negative.**

- Two new Tier-1 tools widens the public CSV-child surface from
  five to seven. Any external caller reading the tool list as a
  fixed-shape contract has to re-derive. SemVer-minor bump
  reflects this — adding tools is additive but the count moves.
- The metadata sidecar adds documentation surface. The README
  examples and the demo walkthrough cite the schema; a future
  rename or schema extension has to update both. Mitigated by
  the `code-vs-roadmap-drift-auditor` agent's existing remit on
  documentation truthfulness.
- `csv_group_summary` is a fail-closed-on-missing-sidecar tool.
  An institution running `csv_dir` against a directory that
  predates this ADR will get a clear error from the new tool but
  no breakage on the five existing tools. Acceptable — the new
  tool requires the new convention; old tools are unchanged.
- The `time_to_50pct_drop_s` metric encodes a single threshold
  (50% of peak). Studies wanting other thresholds (75%, 90%,
  fatigue-test-specific cutoffs) will need either a new metric
  or a parameterised threshold. Deferred — the demo uses the 50%
  threshold; broadening the metric vocabulary lives behind a
  superseding ADR if the use case surfaces.

**Neutral.**

- The vault-tier surface is unchanged. Vault tools continue to
  bypass the biosensor-tier gates per ADR 0012; the cohort tool
  produces results that the LLM may then capture as a vault note
  via the existing `vault_capture_moment` / `vault_upsert_theme`
  surface. The cohort tool is intentionally not in
  `vaultable_tools` — the result is a snapshot, not a durable
  conclusion, and durable conclusions belong in themes/moments
  the analyst chooses to record.
- The `purge_cache` contract from ADR 0013 is unchanged. The CSV
  child's no-op rationale (institutional CSVs at the deployer's
  retention policy) extends to the metadata sidecar — the
  sidecar is also a deployer-managed file and is not framework-
  cached. A consent revocation under this ADR clears no derived
  state because there is no derived state.
- Per-tool token estimates are unchanged for the existing five
  tools. The two new tools enter the existing pre-estimation
  path (ADR 0005) with `tokens=0` for Tier 1 — the framework's
  cost gate is a no-op on free tools and the result size is
  bounded server-side by the cohort-stats reduction.

## Alternatives considered

**Encode group in filename, parse in LLM.** Rejected. Works for one
field at a time and breaks under any of: filename containing
characters that look like delimiters, study with two grouping
axes (sex × condition), file-naming convention drift mid-study.
Forces the parsing logic into the LLM context where it has no
business living — the architecture pitch is *"behavioral rules
live server-side, not in the LLM"* (CLAUDE.md § Architecture).
Filename-encoded groups violate that on the load-bearing surface.

**Per-call `group_map` parameter — caller passes the file-to-group
mapping at every call.** Rejected. Re-construction at every call
is exactly the cost the architecture is supposed to externalize.
Also fails when the LLM hits context boundaries between calls and
the second call's group_map drifts from the first. The sidecar
externalizes the mapping into one durable place.

**YAML sidecar instead of JSON.** Rejected. The project's existing
config artifact (`user_config.json`) is JSON; the audit row format
is JSON; the `_meta` provenance is JSON; the test fixtures write
JSON. Adding a YAML dependency to the runtime surface for one
optional sidecar is the wrong tradeoff. JSON is also less
expressive than YAML in ways that are precisely the constraints
we want — no anchors, no merge keys, no folded multi-line strings
that produce surprising whitespace. The schema is filename →
flat field map; JSON's exact level of expressiveness fits.

**Embed metadata in CSV header rows.** Rejected. CSV is a
positional format and `csv.DictReader` treats the first row as
column headers. Multi-row metadata above the header would require
a custom parser, breaks every external CSV-reading tool the
analyst already uses (Excel, pandas, R), and conflates
participant-level metadata with column metadata. The sidecar is
out-of-band by design.

**Add curve-fitting (exponential, polynomial) to Tier 1.**
Rejected for v6.5.0 with a named reversal condition. The HIP-Lab
demo's `time_to_50pct_drop_s` metric is the simplest fatigue
diagnostic that satisfies the demo's stated cohort question
without introducing a curve-fitting dependency (numpy, scipy)
into the runtime. A future demand for explicit decay-constant
fitting (PCr recovery τ in muscle metabolism studies, exponential
washout in pharmacokinetics) lives behind a superseding ADR
that decides the dependency-surface tradeoff. The current
fatigue diagnostic is honest about what it is — a non-parametric
threshold-crossing measure — and nameable as such in the demo
walkthrough.

**Make metadata mandatory at child init time, fail closed if
absent.** Rejected. The five existing tools (`csv_list_files`,
`csv_file_detail`, `csv_summary_report`, `csv_downsampled`,
`csv_raw_stream`) are useful with no metadata at all — a single-
subject directory or an exploratory CSV dump. Mandating metadata
breaks those use cases for a feature only `csv_group_summary`
needs. The fail-closed-at-tool-call-time pattern is the right
grain: tools that need metadata require it; tools that don't,
ignore it.

**Defer to v6.6.x; ship the HIP-Lab demo as a Tier-2 escalation.**
Rejected. The boss's audit-driven decision (Path B) was explicit:
the *"real architecture underneath"* pitch is undercut if the
architecture has to dress up to make the claim land. Deferring
the cohort tool means the demo either fabricates Tier-1 numbers
(audit's path-A failure mode) or escalates to Tier-2 16 times
mid-demo (audit's path-B failure mode). Neither lands the
architectural pitch. Shipping the cohort tool with the demo is
the structurally correct fix — and the new tools benefit every
future ChildMCP, not just the demo.
