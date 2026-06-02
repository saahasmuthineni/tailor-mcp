# ADR 0027: `tailor demo` is a researcher first-look, not operator self-verification

- **Status:** Accepted
- **Date:** 2026-05-06
- **Partially superseded by:** [ADR 0029 (Token reduction is analytical quality)](0029-token-reduction-as-analytical-quality.md) (2026-05-07) — § Negative consequences "the demo bypasses RouterMCP by design" (lines 174-193 below) and the framing-prose contract that names `_meta` in prose because the demo doesn't exercise the router. ADR 0027's central claim — cohort thesis as canonical first-look, no Strava data — is preserved as Section 1 of the v6.12.0 demo.
- **Partially superseded by:** [ADR 0035 (CLI rename: walkthrough + fitting-room)](0035-cli-rename-walkthrough-and-fitting-room-and-recipient-experience-naming-principle.md) (2026-05-14) — the CLI verb name (`tailor demo`) was renamed to `tailor walkthrough` per the recipient-experience-shaped naming principle. The substance of this ADR — researcher first-look against bundled demo cohort fixtures, the operator-vs-researcher framing correction, the `sample_data.py` preservation per ADR 0008 — is fully retained. The CLI alias `tailor demo` survives through v7.1.0 with a deprecation hint; it is removed in v7.2.0.
- **Partially superseded by:** [ADR 0038 (Vault layer is data-source-agnostic)](0038-vault-layer-is-data-source-agnostic.md) (2026-05-16, Proposed) — ADR 0027 reshaped the *demo data layer* but did not extend to the *vault layer*. The 2026-05-16 first-real-recipient user run + the v7.3.4 cycle's wire / cue-card audits surfaced that vault tool descriptions, orientation fallback prose, and the snapshot regenerator continued to treat the running child as canonical — Strava-shaping the orientation surface a science recipient sees on a demo cohort install. ADR 0038 codifies "vault layer is data-source-agnostic" as the structural invariant; v7.3.4 ships partial closure (demo hot-path); v7.4.0 ships the structural sweep.
- **Partially superseded by:** [ADR 0040 (Bounded setup-time conductor surface)](0040-bounded-setup-time-conductor-surface.md) (v8.0.0, 2026-05-19) — the `tailor walkthrough` CLI command (renamed from `tailor demo` by ADR 0035) was **hard-removed** in v8.0.0 with no deprecation shim, replaced by the `WalkthroughLayer` MCP tools. The researcher-first-look substance — cohort thesis as the canonical first surface, no Strava data — is retained inside the new MCP layer; only the CLI verb was retired.
- **Related:** [ADR 0008 (Deterministic-by-construction processing)](0008-deterministic-by-construction-processing.md), [ADR 0015 (Tier-1 cohort surface)](0015-tier-1-cohort-surface-and-metadata-sidecar.md), [ADR 0024 (Wheel-distributed tour and fixture bundling)](0024-wheel-distributed-tour-and-fixture-bundling.md), [ADR 0029 (Token reduction is analytical quality)](0029-token-reduction-as-analytical-quality.md)

## Context

Through v6.10.4, `tailor demo` was framed as **operator
self-verification** — *"Run analytics on synthetic data (operator
self-verification)"* per the inline help text at
[`__main__.py:10`](../../src/tailor/__main__.py). The
implementation reflected that framing: synthetic Strava-shaped
streams generated on the fly via
[`demo/sample_data.py`](../../src/tailor/demo/sample_data.py),
fed through the running child's `RunningChild.execute()` path,
printing `strava_run_report` / `strava_hr_analysis` /
`strava_pace_analysis` outputs. The implicit recipient of the demo
was the operator who had just installed the wheel and wanted to
confirm "my install works on my machine."

That framing has been wrong for the entirety of the v6.x cycle and
this ADR makes the correction explicit. Three structural reasons:

1. **The framework's stated north star is researcher utility**, not
   operator hygiene. CLAUDE.md § "What This Project Is" names the
   audience as health researchers (academic medical centers, mHealth
   labs, sleep / CGM / cardiology groups) and the research-software
   engineers who support them. Operator self-verification is a means,
   not the end.
2. **The running child (Strava data) is a worked example, not the
   canonical use case.** CLAUDE.md states this explicitly: *"It is
   retained for teaching value; it is not the canonical use case."*
   A demo whose entire surface demonstrates the worked example
   silently positions it as canonical to every recipient who runs
   `tailor demo` for the first time.
3. **The first impression a recipient forms about what this tool
   does is load-bearing.** A PI or RSE running the demo to figure
   out "what does this do?" forms a mental model from the output
   they see. The Strava-output-shaped demo plants the model
   "tailor is a Strava analyzer" — the opposite of where the
   v6.5.0 cohort-surface release explicitly positioned the project.

The boss surfaced the framing tension in a 2026-05-06 session:
*"the demo SHOULD NOT HAVE MY STRAVA DATA OR ANYTHING RELATED,
the only point of the demo is to show the [lab] use."* That ask
is correcting a long-standing drift, not adding new direction —
the demo was contradicting CLAUDE.md's framing for the entire v6.x
cycle.

[ADR 0024](0024-wheel-distributed-tour-and-fixture-bundling.md)
§ "Negative consequences" already deferred a `demo` → `verify`
rename based on the operator-self-verification framing. With this
ADR's reframing, that rename becomes the wrong move (the
researcher-first-look surface should not be called `verify`).
ADR 0024 is amended in the same patch to forward-cite this ADR.

## Decision

`tailor demo` is reframed as a **researcher first-look** —
*"what does this framework do for the cohort-comparison thesis the
project is built around?"* — and the implementation is reshaped to
match.

Concrete mechanism:

- **The demo loads the bundled demo cohort realistic fixtures**
  (`src/tailor/_fixtures/cohort_demo_realistic/force/`,
  same fixtures `tour` scaffolds per ADR 0024). 16 synthetic
  subjects, 8 BU (bilateral) / 8 OE (one-extremity), an isometric
  task to volitional failure with a `metadata.json` sidecar.
  Rationale: real demo cohort shape, real metadata-sidecar
  pattern (per [ADR 0015](0015-tier-1-cohort-surface-and-metadata-sidecar.md)),
  no PRNG-on-demand-data — what the recipient sees in `demo` is
  what they would see in `tour`.
- **The demo exercises `csv_cohort_summary` and `csv_force_decline`
  through `CSVDirectoryChild.execute()`.** The data flow: copy
  fixtures into a tempdir, write a tempdir-scoped `user_config.json`
  with a `csv_dir` block pointing at the force fixtures, instantiate
  `CSVDirectoryChild`, call the cohort tools. Output is the result
  envelope the child returns; the router-added `_meta` block per
  [ADR 0001](0001-audit-log-as-backbone.md) is named in framing
  prose since `demo` does not exercise the router.
- **`sample_data.py` is preserved.** ADR 0008 § Alternatives
  explicitly considered and rejected removing the synthetic-Strava
  PRNG ("the synthetic-Strava data has teaching value and is
  exempted from the no-PRNG processing rule"). The module remains
  importable from `tailor.demo.sample_data` for the test at
  [`tests/framework/test_router.py:1054`](../../tests/framework/test_router.py)
  and the
  [`docs/guides/worked-example.ipynb`](../../docs/guides/worked-example.ipynb)
  notebook, both of which still consume it directly. The module's
  role narrows from "demo data source" to "library-shaped
  synthetic-Strava generator."
- **Output framing.** The demo prints two cohort-summary calls
  (peak force grouped by `sex`, peak force grouped by `group`),
  one force-decline diagnostic on a representative subject
  (`S001_force.csv`), then a closing block that lampshades the
  thesis explicitly: *"computed server-side from the bundled CSVs;
  in a Claude Desktop deployment the same calls come back wrapped
  with audit-log + `_meta` provenance per ADR 0001"* and a
  reproducibility-check note grounded in ADR 0008 (re-run, expect
  bit-identical numbers).

The rule, plain English: when a researcher runs `tailor
demo` cold, the framework gets one chance to demonstrate what it
is for. That's the cohort-comparison thesis the project's stated
use case is built around — not the worked example whose framing
warns against treating it as canonical.

## Consequences

### Positive

- **Recipient first-impression realigns with the project's stated
  framing.** A PI or RSE running `tailor demo` for the first
  time forms a correct mental model — "this is a cohort-research
  framework with deterministic processing and audit-log
  provenance" — instead of the prior model — "this is a Strava
  analyzer."
- **The demo becomes a true *researcher first-look*.** The output is
  shaped by what an analyst would want to see (cross-group
  comparison, fatigue diagnostic on a representative subject) rather
  than by what's easy to synthesize (one-runner dummy stream).
- **The reproducibility property is named explicitly.** ADR 0008's
  deterministic-by-construction invariant becomes a
  recipient-visible feature: re-run `demo`, expect bit-identical
  numbers. This is researcher utility (citable provenance) framed
  as a recipient-checkable property.
- **The deferred `demo` → `verify` rename is killed.** Per ADR 0024
  § Negative consequences, the rename was deferred *because* the
  operator-self-verification semantics weren't yet sharp. With the
  reframe to researcher-first-look, the rename becomes the wrong
  move — the surface should not be called `verify`. Closing the
  parking-lot item rather than carrying it forward.

### Negative

- **The demo now depends on bundled fixtures.** A wheel install
  that somehow lacks the
  `_fixtures/cohort_demo_realistic/force/` subtree (corrupted
  `pyproject.toml` `package-data` glob, a botched build) silently
  breaks the demo. Mitigated by a regression test that asserts the
  fixtures are loadable via `importlib.resources` — same shape as
  the v6.9.0 wheel-fixture-bundling regression suite per ADR 0024.
- **The Strava-shaped demo path is no longer a CLI surface.** A
  recipient who specifically wants to see the running child's
  output has to run `tailor setup` (Strava OAuth) or
  manually invoke `from tailor.demo.sample_data import ...`.
  Acceptable — the running child is "worked example" not canonical;
  CLAUDE.md and `children/running/__init__.py` both name it as
  such; a recipient who specifically wants to study it can still
  reach it through the README's worked-example walkthrough. The
  demo-as-Strava-showcase loss is intentional, not collateral.
- **Cohort tools require `metadata.json`.** Per ADR 0015, the
  sidecar pattern is the cohort-summary's contract. The demo's
  bundled fixtures include the sidecar, so the demo is unaffected,
  but a future maintainer who refactors the fixtures has to
  preserve the sidecar or the demo regresses. Test coverage names
  the sidecar dependency explicitly.
- **One asset was stale and unreferenced — resolved in v6.12.x cleanup.**
  `docs/assets/demo.svg` was a hand-rolled illustration showing
  "tailor demo · synthetic 60-min run" framing — it depicted
  the Strava-shaped pre-v6.10.5 demo. As of v6.10.5 it was not
  embedded in `README.md` (which embeds only `vault-insights.svg`
  and `footprint.svg`) and was not referenced by any docs guide.
  Listed here as known asset-render-debt; the v6.12.0 cleanup pass
  took the "remove the orphan SVG" branch of the named fork ("a
  future doc-pass may either remove the orphan SVG or replace it
  with a demo cohort visualization"). Replacement with a demo cohort
  visualization remains an open creative item; the orphan
  itself is gone. The `vhs` tape at `docs/guides/demo.tape` that
  produces `docs/assets/demo.gif` was unaffected — it runs
  `tailor demo` directly and is forward-compatible with the
  reshaped v6.12.0 demo's output.
- **The demo bypasses `RouterMCP` by design.** Calls go directly
  to `CSVDirectoryChild.execute()`, so the printed result envelopes
  do *not* carry the `_meta` block, `scrubber_warning`, audit-log
  row id, or `scrubber_id` that a Claude Desktop tool call would.
  This is intentional — wiring up a router for the demo would
  require a temp consent gate, a temp vault layer, and a tail-print
  of `audit.db` rows, all of which expand the demo's surface from
  "researcher first-look at the cohort thesis" to "router
  walkthrough." The IRB-relevant properties the framework offers
  (audit-log per ADR 0001, scrubber seam per ADR 0003, consent /
  cost gates per ADRs 0004 / 0005) are visible by running
  `tailor tour` and exercising the same tool inputs through
  Claude Desktop. The demo's closing prose is scoped to claim only
  what the demo's output demonstrates (server-side computation
  visible in the envelope shape, deterministic reproducibility
  verifiable by rerun); the router-pipeline properties are named
  as "what this demo does NOT exercise" with a pointer to `tour`.
  Surfaced explicitly here per the v6.10.5 researcher-utility-
  reviewer IRB-persona finding so the trade is durable rather
  than implicit.

### Neutral

- **Tour and demo become structurally adjacent.** Tour scaffolds
  bundled fixtures into the recipient's filesystem and registers
  with Claude Desktop; demo loads the same fixtures into a tempdir
  and runs the cohort tools directly. The fixture path and the
  config-shape logic are shared — though demo only needs the
  force/ subdir while tour scaffolds force/ + emg/ + mrs/ + vault/.
- **The v6.10.0 banner's `demo (operator self-verification)`
  parenthetical drifts.** Banner amendments per the v6.10.x
  pattern — the v6.10.5 banner names the reframe and the inline
  help text in `__main__.py` updates in the same patch.
- **`docs/guides/worked-example.ipynb` continues to work
  unchanged.** The notebook imports from `sample_data.py` directly,
  not via the demo runner; the runner rewrite does not affect it.
  Same for `tests/framework/test_router.py:1054`.

## Alternatives considered

**Keep the demo Strava-shaped; add a separate `demo-csv` subcommand.**
Rejected. Two demo subcommands forces the recipient to know which
one to run, and "which is canonical?" is exactly the question the
single-demo answer eliminates. The v6.5.0 cohort surface release
established that the cohort-comparison thesis is the canonical
use case; one demo, one canonical surface.

**Drop the demo entirely; let `tour` cover both researcher-first-look
and operator-self-verification.** Rejected on UX grounds. `tour`
writes durable state (scaffolded directory, Claude Desktop
registration); `demo` runs in a tempdir and writes nothing. A
recipient who just wants to see what the framework does without
committing to install state has no other surface — `tour` is for
the audience walkthrough, `demo` is for the casual first-look.
Different jobs, different idempotency contracts.

**Synthesize cohort-shaped CSV cohorts on the fly (no fixture
dependency).** Rejected. Synthesizing on the fly preserves the
ADR 0008 deterministic-by-construction property at the demo level
but breaks the structural adjacency to `tour` — a recipient running
`tour` after `demo` would see different numbers, which leaks the
synthesis-vs-fixture distinction across surfaces and erodes the
"this is what the framework computes" thesis. Bundled fixtures
(same fixtures `tour` uses) keep the demo's output predictable
and aligned with what the recipient sees in their actual install.

**Bundle a smaller cohort fixture (e.g. 4 subjects) for the
demo separately from the 16-subject fixture `tour` uses.** Rejected
on similar grounds. Two fixture sets diverges the demo and tour
surfaces; one fixture set keeps them aligned. The 16-subject
cohort runs in well under a second on the cohort tools' Tier-1
processing path, so size is not a performance concern.
