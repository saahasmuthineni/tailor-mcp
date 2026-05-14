# ADR 0037: RedcapFileChild v1 supports export-directory wrapping only; live REDCap REST API deferred behind a future ADR

- **Status:** Accepted
- **Date:** 2026-05-14
- **Related:** [ADR 0003 (PHI-scrubber seam)](0003-phi-scrubber-seam.md), [ADR 0008 (Deterministic-by-construction processing)](0008-deterministic-by-construction-processing.md), [ADR 0009 (Vault subject-keying)](0009-vault-subject-keying.md), [ADR 0011 (Promotion policy)](0011-promotion-policy.md), [ADR 0013 (Cache-only purge on consent revocation)](0013-cache-only-purge-on-consent-revocation.md), [ADR 0015 (Tier-1 cohort surface and metadata sidecar)](0015-tier-1-cohort-surface-and-metadata-sidecar.md), [ADR 0024 (Wheel-distributed tour and fixture bundling)](0024-wheel-distributed-tour-and-fixture-bundling.md), [ADR 0029 (Token reduction as analytical quality)](0029-token-reduction-as-analytical-quality.md), [ADR 0036 (MATLABFileChild scope)](0036-matlab-child-scope-v72-only-with-deferred-hdf5.md), [CLAUDE.md § What This Project Is](../../CLAUDE.md#what-this-project-is)

## Context

v7.1.1 repositioned the project around a parallel-clause claim:
*"The same architecture works on whatever shape your data is already
in — CSV directories today; REDCap exports, EDF recordings, FHIR
bundles, vendor sensor exports, or any other source through a small
`ChildMCP` extension that inherits the full pipeline."* That claim
named four held source axes; v7.2.0 shipped the first existence proof
(`MATLABFileChild`, per [ADR 0036](0036-matlab-child-scope-v72-only-with-deferred-hdf5.md))
and held REDCap for a fresh-session v7.3.0 build. This ADR is the
REDCap existence proof.

REDCap is the canonical clinical-research data-capture system at
academic medical centers — the audience the source-agnostic claim is
most pointedly aimed at. A REDCap project has two structural surfaces
a child could wrap:

1. **The export directory.** A REDCap administrator can export a
   project as CSV or JSON to a local directory, accompanied by a
   `project_metadata.csv` data dictionary that names every field, its
   type, validation rules, choice lists, and — critically — an
   `identifier` flag (`yes` / `no` / blank) set during IRB protocol
   approval to mark fields that contain participant identifiers.

2. **The live REST API.** REDCap servers expose a token-authenticated
   API that returns the same records on demand, with optional
   filtering by event, instrument, or record_id.

The export-directory path is the **lower-stakes shape**. It composes
on top of REDCap's existing IRB-approved export workflow — a workflow
the administrator has already authenticated and audited at the
REDCap-server level — and reduces the framework's role to "wrap files
on disk." The live REST API is the higher-stakes shape: it would
require the framework to hold REDCap API tokens, manage rate limits,
participate in REDCap's own audit trail, and adjudicate per-call
permissions that REDCap itself enforces server-side. Real labs will
eventually want both, but they are different products with different
threat models.

A second structural decision the candidate forces is the Tier-2
shape. The direct fork from `csv_dir` and `matlab_file` would be
`redcap_downsampled` — return every Nth record. The proposal-mode
audit found that shape **structurally incoherent** for record-oriented
data: "every 5th subject" is not a researcher's question; REDCap
records are not ordered along a meaningful axis (a subject's
record_id has no temporal interpretation). The three-tier model has
to bend for REDCap in a way it did not for the time-series children.
The deeper question the audit raised is whether the three-tier model
generalizes as "time-series decimation" or as something more
fundamental — and if the latter, what the REDCap surface looks like.

A third structural decision is PHI handling. REDCap is the first
source axis where the IRB-approved data dictionary structurally
answers the question [ADR 0003](0003-phi-scrubber-seam.md) deliberately
declined to answer ("what counts as PHI in this deployment?"). The
`identifier=yes/no` flag in `project_metadata.csv` is set by the IRB
protocol at REDCap project creation. ADR 0003's rationale — *the
framework cannot generically answer "what counts as PHI"* — is
correct, and unchanged. But for REDCap, the IRB has answered the
question per-field, in a structured input the framework can read.
That input did not exist for the children that motivated ADR 0003.

The question this ADR answers: *what REDCap surface does v1 support;
how does the three-tier model bend for record-oriented data; and
where does the per-field IRB-approved scrubbing policy live?*

## Decision

`RedcapFileChild` v1 supports **REDCap export-directory wrapping
only**. The child reads a directory containing one or more REDCap CSV
or JSON exports (`<project>.csv` / `<project>.json`) accompanied by a
REDCap data dictionary (`project_metadata.csv`). Live REST API access
is deferred behind a named reversal condition (below).

### Tool surface (six tools across three tiers)

Mirrors `matlab_file/` per ADR 0036 in count and tier distribution,
with the Tier-2 shape reshaped for record-oriented data:

| Tool | Tier | Description |
|------|------|-------------|
| `redcap_list_records` | 1 | List record_ids with event coverage and per-instrument completion flags |
| `redcap_record_detail` | 1 | Single-record summary (non-identifier fields only) |
| `redcap_summary_report` | 1 | Per-instrument completion counts, per-field cardinality and distribution |
| `redcap_cohort_summary` | 1 | Cross-record aggregation by metadata-sidecar group (n / mean / std / mode / first / last per group). Supports an `instrument` filter to scope the cohort to one form. |
| `redcap_records` | 2 | Required `instrument: str` parameter; returns all subjects' answers to that one form across all events, identifier-stripped. Consent-gated. |
| `redcap_raw_records` | 3 | All subjects, all events, all instruments, identifier-stripped. Cost-gated. |

The Tier-2 reshape is load-bearing. `redcap_records(instrument=...)`
replaces the would-be `redcap_downsampled` because record decimation
is not a coherent coarsening axis for record-oriented data — but
**form scope is**. Returning "all subjects' answers to the depression
inventory" is a real cohort question that exposes more than Tier 1
without exposing the full project. The instrument parameter is
required — there is no default — so the analyst's consent grant is
scoped to a named form the IRB approved, not to the project as a
whole.

The deeper architectural observation worth recording: **the three-tier
model generalizes as "progressively-revealing more data under
progressively-stronger consent" — not specifically as time-series
decimation.** `csv_dir` and `matlab_file` happen to use decimation
because their data is time-series; REDCap's coarsening axis is
instrument scope because REDCap data is form-organized. A future EDF
child's Tier 2 axis will likely be channel scope ("all subjects'
EMG channel"); a future FHIR child's Tier 2 axis will likely be
resource type ("all subjects' MedicationStatement resources"). The
ADR 0029 framing — *"no streams enter LLM context"* — generalizes to
*"no whole-project records enter LLM context at Tier 1; the analyst
escalates to a named, IRB-recognized scope at Tier 2."*

### Subject scoping (per [ADR 0009](0009-vault-subject-keying.md))

`record_id` is the `subject_id`. `redcap_event_name` is a **grouping
dimension** threaded through cohort tools but is **not** ADR 0009
subject scoping. REDCap's longitudinal-events structure means one
subject can have multiple records across events
(baseline / 3-month / 6-month / etc.); literal one-record = one-subject
is wrong for the ~70% of REDCap projects that use longitudinal arms.
The cohort tools accept an optional `event` parameter to filter to a
single event; absent that parameter, the cohort aggregates across all
events with `event` carried through as a `group_by`-eligible column.

Variables-as-subjects deferred — the same structural deferral as
ADR 0036. An instrument that asks one respondent about multiple
people (e.g. a parent reporting on each of their children, with
fields `child_1_name`, `child_2_name`, ...) cannot be auto-decomposed
into per-child subjects without a framework decision about how that
shape maps onto ADR 0009's set-once promotion semantics. v1 treats
such records as one subject (the respondent); a superseding ADR may
codify a `subject_axis` declaration in the `redcap_file` config block.

### Built-in PHI scrubber — a new seam parallel to ADR 0003

`RedcapPHIScrubber` lives at `src/tailor/children/redcap/scrubber.py`
and is invoked **inside the child's `execute()`** before returning,
not on the framework-level scrubber seam ADR 0003 codified. This is a
**new seam parallel to ADR 0003** — codified by a forthcoming
amendment to ADR 0003 that this ADR triggers.

The framework-level `PHIScrubber` (ADR 0003) stays no-op-default and
unchanged. The child-level seam handles **domain-specific structured
PHI input**: the `identifier=yes/no` flags in `project_metadata.csv`
that the IRB approved at protocol creation.

The two seams are complementary, not redundant:

- **Framework-level (ADR 0003).** Cross-domain pattern matchers
  (regex, heuristic, NLP) that are useful across any child. Stays
  no-op-default; institutions subclass with their own policy.
- **Child-level (this ADR).** Domain-specific structured input the
  child can read deterministically. REDCap today; FHIR resource type
  scrubbing tomorrow; EDF channel metadata after that. The child
  ships a policy-**aware-by-input** scrubber, not a policy.

The framework still does not ship a HIPAA Safe Harbor scrubber.
ADR 0003's argument — that the framework cannot define PHI generically
— is unchanged. What changes is that for REDCap, the IRB has defined
it per-field in a structured input the child can read.

Promotion path per [ADR 0011](0011-promotion-policy.md): if a third
structured-PHI domain wants child-level scrubbing (FHIR is the
likely candidate), that is the structural-argument signal for
promoting the child-level seam into a framework registry pattern.
Two domains is "happens to repeat"; three domains is a pattern.

### Audit-row provenance

ADR 0003's `scrubber_id` column on `audit_log` continues to record
the framework-level scrubber's identity. For REDCap calls it remains
`"noop"` — because the framework-level scrubber did not run.

A **new audit-log column `child_scrubber_id`** records the child's
internal scrub identity. For REDCap calls it is
`"redcap_metadata_flags"`. For `csv_dir`, `matlab_file`, and the
running child it is NULL (no child-level scrubber).

This is honest layering. The framework still did not scrub; the
child did, with a citable identity. An IRB reviewer reading audit
rows can distinguish a misconfigured deployment (`scrubber_id="noop"`
AND `child_scrubber_id IS NULL`) from a deployment with a working
child-level scrubber (`scrubber_id="noop"` AND
`child_scrubber_id="redcap_metadata_flags"`).

### Unknown-field default = identifier-positive (fail-closed)

The proposal-mode audit named the most-likely silent-failure path:
`project_metadata.csv` carries `identifier=yes` flags on the three
fields the IRB approved at protocol creation, but a mid-study field
addition (`emergency_contact_phone`) was added directly to the
REDCap project without a corresponding update to the exported data
dictionary. If the scrubber defaults unknown fields to
`identifier=no`, that field silently leaks.

`RedcapPHIScrubber` **defaults unknown fields to identifier-positive**
(stripped) until the analyst sees them in the result envelope's
`unknown_field_count` field and either updates `project_metadata.csv`
or explicitly allowlists the field in the `redcap_file` config block:

```json
"redcap_file": {
  "path": "/path/to/redcap/export",
  "unknown_field_allowlist": ["computed_score_v2"]
}
```

This defends against the same historical pattern ADR 0003 § Negative
consequences names: *"valid-looking audit rows with no scrubbing."*
The fail-closed default makes the analogous REDCap failure mode
("valid-looking results with a leaked identifier") structurally
impossible without an explicit operator opt-in that is itself audited.

### Legibility commitment

Parallel to ADR 0036's red-team-driven legibility commitment. The result envelopes
for `redcap_cohort_summary` and `redcap_record_detail` distinguish
four failure modes:

- `field_not_in_record` — the field name doesn't exist on the
  requested record.
- `field_marked_identifier_stripped` — the field exists; the
  scrubber stripped it because `project_metadata.csv` flagged it
  `identifier=yes`.
- `field_unknown_default_stripped` — the field exists; it isn't in
  `project_metadata.csv`; defaulted to stripped per fail-closed.
- `unknown_field_count` — total count of fields that hit the
  fail-closed default in this call.

A recipient diagnosing "where did my data go?" distinguishes all four
without guessing. Maps onto ADR 0036's `variable_not_in_file` vs
`variable_wrong_shape` pattern.

### Cohort grouping (ADR 0015 sidecar vs `project_metadata.csv`)

A confusion the audit surfaced and this ADR disambiguates: ADR 0015's
`metadata.json` sidecar and REDCap's `project_metadata.csv` are
**different files with different purposes**. They may coexist in the
same redcap directory:

| File | Schema | Purpose | Required by |
|------|--------|---------|-------------|
| `project_metadata.csv` | per-field-definition rows (name, type, identifier, validation, choices) | REDCap data dictionary | Every Tier-2 and Tier-3 tool; cohort tool when `instrument=` is used |
| `metadata.json` | `{filename: {field: value}}` per ADR 0015 | Cross-file cohort group identity | `redcap_cohort_summary` only, when `group_by` points at a sidecar-defined field |

`project_metadata.csv` is REDCap-native and ships from a REDCap
export. `metadata.json` is the framework's cohort-grouping sidecar
from ADR 0015 and is operator-authored. The two are orthogonal; a
REDCap project that doesn't need cross-file cohort grouping needs
only `project_metadata.csv`.

### Deterministic processing per ADR 0008

`RedcapProcessing` is `@staticmethod` pure-function per ADR 0008. No
PRNG, no clock reads, no instance state. CSV and JSON parsing happens
at the child boundary (`child.py`); `processing.py` operates on plain
Python lists and dicts. Cohort aggregation reuses the
`COHORT_METRICS` vocabulary established by ADR 0015 (mean / max /
min / std / first / last / mode / count) where it applies; the
REDCap-specific addition is `mode` for categorical fields, which the
existing time-series cohort surface did not need.

### Cache-only purge per ADR 0013

`purge_cache` returns the no-op-with-citable-reason dict matching the
`csv_dir` and `matlab_file` posture (ADR 0013 § "Children with no
framework-owned cache"). REDCap exports are read fresh from disk on
every call; the child holds no derivative cache. The cost is honest
re-parsing on every cohort call; the alternative (in-memory cache)
would silently make the purge no-op a lie about retention.

### Lean-dep posture preserved

REDCap CSV exports parse with stdlib `csv`; JSON exports with stdlib
`json`. No new optional dep. Contrast with ADR 0036, which required
`scipy` as an optional extra. The base install footprint remains the
three deps (`mcp`, `requests`, `orjson`) declared in
`pyproject.toml`.

### Synthetic-by-construction fixtures per ADR 0024

Bundled fixtures at `src/tailor/_fixtures/redcap_demo/` ship with the
wheel and exercise the REDCap-distinct surfaces a flat CSV cannot:
longitudinal events (baseline / 3-month / 6-month), arms (intervention
/ control), data access groups (site_a / site_b), at least one
repeating instrument (weekly check-in), and mixed identifier flags
including realistic ones (`participant_name=yes`, `dob=yes`,
`study_group=no`, `enrollment_date=no`, `phq9_score=no`). A flat
one-record-per-row fixture would be a `csv_dir` proof, not a REDCap
proof — and per ADR 0024's synthetic-by-construction precondition, all
identifying fields in the fixture are obviously synthetic
(`participant_name="Subject 001"`, `dob="1990-01-01"` for every
record) so no de-identified-real-data carve-out is needed.

## Negative consequences

- **No live REDCap REST API in v1.** A lab whose REDCap project is
  too large for a clean export, or whose IRB workflow specifically
  permits API-mediated access but not bulk export, cannot use the
  child until the deferral reverses. The framing in `consent_info`
  and the README must not over-promise: the source-agnostic claim
  says *"REDCap exports"*, not *"REDCap."* This ADR's existence makes
  the gap reviewable.

- **Variables-as-subjects deferral is real for REDCap too.** Family
  studies, multi-respondent instruments, and roster-shaped REDCap
  designs all encode multiple subjects per record. v1 treats the
  record's owner as the single subject; the unsupported respondents
  are invisible to ADR 0009 subject scoping. Same deferral discipline
  as ADR 0036's variables-as-subjects deferral; a superseding ADR may
  codify a `subject_axis` declaration.

- **The new `child_scrubber_id` audit column is a schema migration.**
  Existing `audit.db` files require an `ALTER TABLE audit_log ADD
  COLUMN child_scrubber_id TEXT` on the next router boot. This is the
  same migration shape as ADR 0002's `subject_id` addition; the
  framework's `BaseStorage` migration path is exercised, but a
  malformed manual edit to `audit.db` could fail the migration. The
  migration is idempotent (uses `IF NOT EXISTS` semantics on the
  column add) and writes a startup log line so a failed migration
  surfaces in operator stderr.

- **Fail-closed unknown-field default will produce
  `field_unknown_default_stripped` surprises early in REDCap
  deployments.** An analyst running a cohort tool against a REDCap
  project whose data dictionary is out of sync with the live project
  will see fields stripped that the IRB approved as non-identifier.
  The fix is the documented one (re-export `project_metadata.csv` or
  add the field to `unknown_field_allowlist`); the friction is real,
  and intentional. The alternative — silent identifier leakage — is
  the failure mode this ADR will not accept.

- **The child-level scrubber seam doubles the surface IRB reviewers
  must inspect.** A reviewer auditing a REDCap deployment now reads
  both `scrubber_id` and `child_scrubber_id` to know what scrubbed
  what. This is the cost of honest layering; the alternative
  (collapse both scrubbers into one identity) loses the distinction
  between framework-level no-policy and child-level structured-input
  policy. ADR 0003's amendment naming the parallel seam is the
  documentation lever; the audit-row layering is the structural
  lever.

- **REDCap's own audit trail and Tailor's audit log are two records.**
  A lab using both REDCap directly and Tailor on REDCap exports has
  two audit surfaces: REDCap's server-side log of who exported what,
  and Tailor's `audit.db` of what the analyst then did with the
  export. Reconciling them is the operator's job, not the framework's.
  v1 makes no attempt to thread REDCap's export ID into Tailor's audit
  rows; a future ADR may add `redcap_export_id` as an optional column
  the child reads from a sidecar.

## Reversal condition

This ADR is reversed when **a first beachhead lab hits a use-case
where it needs live REDCap REST API access against a running REDCap
server**. Identical empirical-signal shape to ADR 0036's v7.3
deferral and ADR 0032's repo-public-flip deferral: the lab is real,
has installed Tailor with the export-directory path, hit the gap,
and either produced a recipient-install-validator-style failure trail
or filed an explicit operator complaint. At that point a superseding
ADR may:

1. Add a `redcap_api` config block alongside `redcap_file` with token
   storage in the same pattern `~/.tailor/strava_token.json`
   establishes.
2. Specify rate-limit policy (REDCap's API rate limits are
   per-server-configurable; the framework will likely need a
   conservative default plus per-deployment override).
3. Specify how the live API's per-call permissions interact with the
   framework's consent gate. The first-cut hypothesis: the framework
   trusts the REDCap server's token-scoped permissions and treats
   ConsentGate as a Tailor-side opt-in layered on top, not a
   replacement.
4. Specify whether the live-API path bypasses
   `project_metadata.csv`-driven scrubbing or whether the API path
   fetches the data dictionary on the wire and applies the same
   identifier flags.
5. Codify whether the export-directory and live-API paths can coexist
   in one `redcap_file` config block or whether they are separate
   children sharing `RedcapProcessing`.

If no real lab hits the gap, the deferral is the right shape. The
export-directory path is the right v1 for the same reason
ADR 0036's v7.2-only scope is the right v1: it covers the cohort of
labs that already have an IRB-approved export workflow without making
the framework hold REDCap API tokens before there is a lab that needs
that.

## Alternatives considered

**Ship both export-directory and live-API in v1.** The "complete the
matrix" version. The cost is real: token storage, rate-limit policy,
REDCap-server-version compatibility (REDCap's API has changed across
major versions), and a doubled threat-model surface for an
existence-proof release whose argument is that the source-agnostic
claim is testable. The existence proof does not require live-API to
be the proof; it requires *one* working REDCap path that real labs
can install. Rejected for v1; available as a superseding-ADR target.

**Tier 2 as `redcap_downsampled` (every Nth record).** The naive fork
from `csv_dir` and `matlab_file`. Structurally incoherent because
REDCap records are not ordered along a meaningful axis. "Every 5th
record" produces a sample with no defensible interpretation — the
analyst cannot characterize what the sample represents to an IRB
reviewer. Rejected on first audit pass.

**Tier 2 as `redcap_event_collapse` (one event at a time, all
subjects, all instruments).** A coherent coarsening axis (event scope
is meaningful), but at the wrong granularity: returning every
instrument for one event is much closer to Tier 3 than Tier 2 in
data volume, and exposes more than the analyst likely consented to
when they intended to compare scores on one form. Rejected — the
`instrument`-scoped shape is the right granularity for "I want to see
how subjects answered this form."

**Tier 2 with both `event` and `instrument` parameters, both
optional.** The "full-axis-parameterized" version. Strictly more
flexible than the instrument-required shape, and tempting because it
collapses Tier 2 and Tier 3 into one tool with knobs. Rejected on the
ADR 0029 ground: the consent grant the analyst gives at the gate
should correspond to a named scope the IRB recognizes (one form), not
a flexible knob the analyst can dial open to "all events, all
instruments" inside one consent boundary. The required `instrument`
parameter is the structural lever that keeps Tier 2 narrower than
Tier 3.

**Ship a generic structured-PHI scrubber registry in the framework,
seeded by REDCap.** The "promote child-level seam to framework
pattern in v1" version. Per [ADR 0011](0011-promotion-policy.md), the
promotion bar is a structural argument **plus** demonstrated
repetition; one domain is "happens to need this." Rejected — the
framework gets the parallel seam codified by the ADR 0003 amendment,
but the registry pattern waits for the second or third structured-PHI
domain. FHIR is the likely next candidate; the framework absorbs the
pattern when there is something to abstract over.

**Default unknown fields to identifier-negative (pass-through).** The
"trust the data dictionary" version. Fails on the exact mid-study
field-addition path the audit surfaced. Rejected on the ADR 0003 §
Negative consequences ground: *valid-looking audit rows with no
scrubbing* is the historical failure mode the framework defends
against. Defaulting unknown fields to stripped is the v1
equivalent of ADR 0003's loud-stderr-warning posture.

**Build a REDCap-native scrubber that reads the data dictionary's
`field_annotation` free-text column to infer identifier status.**
REDCap field annotations sometimes carry semi-structured hints
(`@HIDDEN`, `@CALCTEXT`, etc.) that could be parsed. Rejected — the
`identifier=yes/no` column is the IRB-recognized structured input;
anything else is heuristic, and a heuristic scrubber is what ADR 0003
declined to ship in the framework. The child holds the line at "read
the IRB-approved structured input verbatim."
