# ADR 0036: MATLABFileChild v1 supports `.mat` v≤7.2 only; HDF5-based v7.3 deferred behind a future ADR

- **Status:** Accepted
- **Date:** 2026-05-14
- **Related:** [ADR 0003 (PHI-scrubber seam)](0003-phi-scrubber-seam.md), [ADR 0008 (Deterministic-by-construction processing)](0008-deterministic-by-construction-processing.md), [ADR 0011 (Promotion policy)](0011-promotion-policy.md), [ADR 0013 (Cache-only purge on consent revocation)](0013-cache-only-purge-on-consent-revocation.md), [ADR 0015 (Tier-1 cohort surface and metadata sidecar)](0015-tier-1-cohort-surface-and-metadata-sidecar.md), [CLAUDE.md § What This Project Is](../../CLAUDE.md#what-this-project-is)

## Context

v7.1.1 repositioned both the GitHub README hero and the PyPI hero
around a parallel-clause claim: *"The same architecture works on
whatever shape your data is already in — CSV directories today;
REDCap exports, EDF recordings, FHIR bundles, vendor sensor exports,
or any other source through a small `ChildMCP` extension that
inherits the full pipeline."* That clause is architectural in the
v7.1.1 release: at the time it shipped, the framework had exactly two
children — `running/` (a worked example wrapping the Strava API,
explicitly retained for teaching value and not a second source axis)
and `csv_dir/` (the generic CSV directory child). The source-agnostic
claim was a promise with one demonstrated shape.

Move 3 of the post-v7.1.1 strategic-positioning sequence (per memory:
`project-move-3-existence-proof-child`) ships one new `ChildMCP` as
the **existence proof** that the extension point is real. The
candidate pick was MATLAB (cheap, narrow strategic niche) vs. REDCap
(strategic, audience-anchored to academic medical centers). The boss
chose to bundle both in one v7.2.0 release; an in-session
context-budget reality test re-sequenced to MATLAB first (this ADR's
release) with REDCap held for v7.3.0 as a separate fresh-session
build.

The MATLAB candidate has a real scope decision the framework's lean
dependency posture forces: how do you support `.mat` files without
breaking the framework's three-dep install footprint
(`mcp`, `requests`, `orjson`)?

The dependency surface problem is structural. `scipy.io.loadmat` is
the canonical Python entry point for MATLAB binary files, but it
only handles `.mat` versions v5, v6, and v7.2 — the family of formats
that begin with a 116-byte plain-text header (`"MATLAB 5.0 MAT-file"`
or similar). Since MATLAB R2006b, the default save format for files
larger than 2GB has been v7.3, which is structurally different: HDF5
under the hood, requiring `h5py` rather than scipy, with a different
traversal pattern for ref-typed cell arrays and embedded struct
hierarchies. Real labs ship both formats — the same lab will have a
folder of v7.2 single-subject `.mat` files alongside a v7.3 dataset
that was too large to save in the legacy format.

Three credible alternatives were weighed against the existence-proof
goal:

1. **Hard-dep `scipy` + `h5py` from day one.** Bloats the install for
   the CSV/health-research majority who don't need MATLAB at all.
   Two heavy native-extension wheels (scipy ~30MB, h5py +HDF5 native
   libs) pulled in for every recipient regardless of whether they
   ever use MATLAB. The framework's lean three-dep posture
   (`pyproject.toml` lines 25–29) is a deliberate choice; adding two
   ~30MB wheels for one optional child would silently undo it.

2. **Silent best-effort h5py-if-available.** Try `import h5py` lazily
   on every load; fall back to scipy for v5/v6/v7.2 and to "format
   not supported" for v7.3 if h5py is missing. Ships undeclared
   format support — a future contributor reading the code can't
   reason about which formats are committed to and which are a
   silent best-effort. The `acknowledged_noop_scrubber`-style
   asymmetry that pattern produces is the opposite of the documented
   commitments the framework's other ADRs aim for.

3. **Defer MATLAB entirely until both formats are funded.** Kills the
   existence-proof Move 3 exists to deliver. Leaves the source-agnostic
   claim a one-shape promise indefinitely.

The question this ADR answers: *what `.mat` format scope does v1
support, and how is the deferred portion named so a future contributor
who reaches for `h5py` understands they would be shipping a format
the framework deliberately held?*

## Decision

`MATLABFileChild` v1 supports `.mat` versions **5, 6, and 7.2** only,
via `scipy.io.loadmat` pulled in as an **optional extra** declared in
`pyproject.toml`:

```toml
[project.optional-dependencies]
matlab = ["scipy>=1.10"]
```

Recipients install with `pip install tailor-mcp[matlab]` (or
`uv tool install tailor-mcp[matlab]`). The base install — the
recipient install path documented at
[README.md § Install](../../README.md) — does not pull scipy.

v7.3 (HDF5-based) `.mat` files are **detected and rejected** at the
child's `_load_mat` boundary by inspecting the first 8 bytes for the
HDF5 magic signature (`\x89HDF\r\n\x1a\n`). Detection runs before
scipy is invoked, so v7.3 files do not produce an opaque scipy
`NotImplementedError`; they produce a typed error envelope citing
this ADR:

```
<filename> is a `.mat` v7.3 (HDF5) file. v7.3 is not supported in
this child; see ADR 0036. Re-save the file with `-v7` in MATLAB or
convert via `scipy.io.savemat(..., format='5')` if you control the
export.
```

The child surface mirrors `csv_dir/` (per ADR 0015): four Tier-1
tools (`matlab_list_files`, `matlab_file_detail`,
`matlab_summary_report`, `matlab_cohort_summary`), one Tier-2
(`matlab_downsampled`), one Tier-3 (`matlab_raw_array`). The cohort
surface lands in v1, not deferred — the proposal-mode audit named
the same gap ADR 0015 closed for `csv_dir`: a cohort tool is what
makes the *"no streams enter LLM context"* claim hold for
cohort questions. Cohort group identity travels via the same
`metadata.json` sidecar pattern ADR 0015 codified —
`<matlab_dir>/metadata.json` keyed by filename.

`MATLABProcessing` is `@staticmethod` pure-function per ADR 0008. No
PRNG, no clock reads, no instance state. The numpy arrays scipy
returns are unwrapped to plain Python lists at the child boundary
(in `child.py`), so `processing.py` itself never imports numpy or
scipy and remains testable on a base install.

`purge_cache` returns the no-op-with-citable-reason dict matching
`csv_dir`'s posture (ADR 0013 § "Children with no framework-owned
cache"). Per the proposal-mode audit's F4 finding, the child
**does not cache parsed arrays in memory** — every Tier-1 call
re-parses the `.mat` file from disk. The cost of re-parsing is the
honest price of keeping the no-derivative-cache invariant true; an
in-memory cache would silently make the `purge_cache` no-op a lie
about retention.

Subject scoping is **per-file** (one `.mat` = one subject), matching
the `csv_dir` / `force_csv` / `emg_csv` lineage. Multi-subject `.mat`
files where variables-are-subjects (e.g. an 8-by-N envelope matrix
where rows are participants) are deferred — passing `subject_id` is
audit-log scoping only and does NOT filter row axes. This is a
deliberate scope bound, not a defect; a superseding ADR would need
to specify how variables-as-subjects maps onto ADR 0009's set-once
promotion semantics before that surface lands.

## Negative consequences

- **v7.3 file surprise.** A lab whose datasets are too large to save
  in v7.2 will get the typed-error envelope on every file. The error
  is honest and cites the conversion path, but the lab still cannot
  use the child without action. The framing in `consent_info` and
  the README must not over-promise: the source-agnostic claim says
  *"MATLAB"*, not *"every MATLAB format."* This ADR's existence makes
  the gap reviewable.

- **scipy as an optional dep introduces a configuration footgun.**
  A recipient who has `matlab_file` in `user_config.json` but never
  installed the `[matlab]` extra will see no MATLAB tools. The
  proposal-mode audit F3 surfaced this as the v6.10.2-shaped silent-
  failure trap. The mitigation is the explicit diagnostic in
  `__main__.py::cmd_serve` that writes a banner to stderr when the
  import fails: *"matlab_file is configured in user_config.json but
  scipy is not installed. Fix: pip install tailor-mcp[matlab]."*
  Stderr-from-Claude-Desktop is invisible at runtime (per ADR 0012's
  rationale for surfacing scrubber warnings in `_meta`); the
  diagnostic is correct for operator-driven `tailor serve` debugging
  but a future v2 may need to surface configured-but-unloaded
  children to the LLM transcript itself.

- **No parsed-array cache means Tier-1 calls re-parse on every call.**
  For a 50MB `.mat` file with 16 variables, loading takes ~200ms on
  modern hardware. A cohort summary across 64 files will re-parse
  each. This is intentional (per F4); the alternative — caching —
  would silently break ADR 0013's purge contract. If load time
  becomes a documented complaint, the resolution path is a per-call
  cache scoped to one router invocation, not a long-lived cache;
  that resolution will need its own ADR.

- **Variables-as-subjects is a real shape we don't support.** Sport-
  science and neuroimaging labs commonly store one matrix per
  modality with subjects on the row axis (e.g. an 8×1000 EMG envelope
  matrix). Per-file subject scoping under-counts these by treating
  the file as one subject; ADR 0009's set-once promotion semantics
  cannot adjudicate the variables-as-subjects case without an
  explicit framework decision. v1 leaves this as a known gap; a
  superseding ADR may codify a `subject_axis` declaration in the
  `matlab_file` config block.

  **Legibility commitment (added 2026-05-14 after red-team-reviewer
  OBJECTION, medium severity).** The deferral is honest only when
  the runtime distinguishes "your variable is unsupported by v1"
  from "you typoed the variable name." `matlab_cohort_summary`
  returns two separate lists — `variable_not_in_file` (the variable
  is absent from the file) and `variable_wrong_shape` (the variable
  exists but is not 1-D numeric). When `variable_wrong_shape` is
  non-empty, the result envelope adds a `variable_wrong_shape_note`
  citing this ADR and naming the deferral. A recipient diagnosing a
  failed cohort call gets enough information to distinguish a typo
  (rename and retry) from the shape deferral (split into per-subject
  files or wait for the superseding ADR). The test that pins this
  legibility is at
  `tests/children/matlab_file/test_matlab_shape.py::TestCohortSummary::test_wrong_shape_distinct_from_wrong_name`.

## Reversal condition

This ADR is reversed when **a first beachhead lab ships a v7.3 `.mat`
file the user reasonably expects to load**. "Reasonably expects" is
the empirical signal — the lab installed `tailor-mcp[matlab]`, hit
the v7.3 typed-error envelope, and the failure mode produced
either a real recipient-install-validator-style failure trail or an
explicit operator complaint. At that point a superseding ADR may:

1. Add `h5py` to the `[matlab]` extra (or split into `[matlab-v72]` /
   `[matlab-v73]`).
2. Extend `_load_mat` to dispatch on the HDF5 magic byte check —
   scipy path for v≤7.2, h5py path for v7.3.
3. Specify the v7.3 ref-typed cell / struct-array traversal contract
   for `processing.py`-eligible variable shapes.
4. Update `pyproject.toml` package-data globs if v7.3 fixtures ship
   bundled.

If no real lab hits the gap, the deferral is the right shape: a
correctness boundary held honestly rather than a silent best-effort
that maintainers cannot reason about.

## Alternatives considered

**Build a pure-Python `.mat` v5/v6 parser, no scipy dep.** Possible
(the v5/v6 binary format is documented in MATLAB's *MAT-File Format*
reference), but ~500 lines of binary-record parsing the framework
would now own and maintain forever. The marginal cost of the
optional dep is lower than the marginal cost of a hand-rolled parser
the framework's three-person-equivalent maintenance team would have
to keep correct as MATLAB minor versions drift. Rejected.

**Ship h5py + scipy together as one mandatory `[matlab]` extra.** The
scope-creep version. Doubles the install footprint of the optional
extra (h5py ≈ 5MB wheel + HDF5 system libs that may not be present
on a stripped Windows install) without solving a problem the
existence-proof needs. Rejected for v1; available as a superseding-
ADR target.

**Detect v7.3 silently and degrade to summary metadata only.** Show
the variable list (which we can read from the HDF5 superblock with
some effort) but refuse to return numeric arrays. The audit's F3
silent-failure-trap argument applies here too: a recipient who sees
*"my .mat file produced no data"* without the explicit format-version
explanation has no path to recovery. Rejected.

**Make the optional extra `tailor-mcp[matlab-v72]` to lampshade the
version constraint in the install command itself.** The naming
honestly signals the held v7.3 support, but at the cost of an
extras name that will be wrong when v7.3 lands and the extra
becomes simply `[matlab]`. The pragmatic decision: name the extra
`[matlab]` from the start; the README + this ADR carry the version
caveat. The extras name is a public API surface that should not
churn between v7.2.0 and the eventual v7.3-supporting release.
Rejected.
