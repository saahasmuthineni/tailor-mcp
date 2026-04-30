# ADR 0008: Analytical processing is deterministic by construction

- **Status:** Accepted
- **Date:** 2026-04-29
- **Related:** [ADR 0001 (Audit log)](0001-audit-log-as-backbone.md), [ADR 0005 (Cost pre-estimation)](0005-cost-pre-estimation.md), [ROADMAP.md § Deterministic mode with seed control](../../ROADMAP.md#deterministic-mode-with-seed-control), [ROADMAP.md § Real provenance hashing on derived metrics](../../ROADMAP.md#real-provenance-hashing-on-derived-metrics)

## Context

Reproducibility is one of the three problems this framework is built
against. An IRB reviewer or a co-author re-running an analysis months
later needs the same inputs to produce the same outputs — not "close
enough", but byte-identical where the data shape allows it. Without
that property, the audit log records *that* a tool was called, but
not *what number it would produce again* on the same call.

ROADMAP has carried "Deterministic mode + seed control" as deferred
S-effort work since v5. The roadmap entry framed it as a future
feature: a flag that pins every PRNG seed from a single audited entry
point so reviewers can re-run an analysis. That framing assumed the
analytical layer already contained pseudo-random sampling somewhere
— anomaly detection, downsampling variants — that needed to be
brought under a seed regime.

A drift audit on 2026-04-29 showed the assumption was wrong. The
analytical layer has no PRNG on its hot path. Every method on
`RunningProcessing` ([`children/running/processing.py`](../../src/biosensor_mcp/children/running/processing.py)),
`CSVProcessing` ([`children/csv_dir/processing.py`](../../src/biosensor_mcp/children/csv_dir/processing.py)),
and `TemplateProcessing` ([`children/template/processing.py`](../../src/biosensor_mcp/children/template/processing.py))
is a `@staticmethod` pure function over its arguments. None of them
import `random`, `numpy`, `secrets`, or any time-dependent function.
The only PRNG in the entire package is `_RNG = random.Random(42)` at
[`demo/sample_data.py:21`](../../src/biosensor_mcp/demo/sample_data.py),
which is already seeded, sits off the analytical dispatch path, and
is excluded from coverage in `pyproject.toml` alongside the rest of
`demo/*`.

In other words: the prerequisite for deterministic-mode (PRNG-free,
stateless, pure-functional processing) shipped silently. What
remains under the roadmap heading is a smaller piece — a router-
level audited "deterministic mode" stamp in `_meta` so a reviewer
can confirm the run was produced under the determinism invariant.
That stamp is only meaningful when paired with content-hashed
provenance, which is a separate roadmap item.

The question this ADR answers: *what is the project's actual
position on deterministic processing today, and how should
reviewers, contributors, and future code reason about it?*

## Decision

The analytical processing layer is **deterministic by
construction**. The invariant is enforced by review at PR time, not
by a runtime flag.

Concretely:

- Every method on a `*Processing` class is a `@staticmethod` pure
  function: output depends only on declared arguments. No instance
  state, no module-level mutable state, no I/O.
- No module under `src/biosensor_mcp/framework/` or
  `src/biosensor_mcp/children/*/processing.py` may import `random`,
  `numpy.random`, `secrets`, or any other PRNG, nor call
  `time.time()`, `datetime.now()`, or other clock-dependent
  functions on the analytical path. Time and clock calls in
  `framework/router.py`, `framework/audit.py`, `framework/cost.py`,
  `framework/vault/writer.py`, `framework/vault/renderer.py`,
  `framework/vault/layer.py`, `framework/vault/storage.py`, and
  `children/*/child.py` are permitted — they stamp audit rows,
  measure latency, write cache rows, and produce note frontmatter
  timestamps, none of which feed back into a `*Processing`
  numeric result. The vault-side reads (`renderer.py`, `layer.py`,
  `storage.py`) are timestamps in human-facing markdown frontmatter
  and SQLite index rows; they are explicitly named here per the
  v6.3.1 hygiene-pass BORDER NOTES so a future audit does not
  flag them as drift.
- The single permitted exception is `demo/sample_data.py`, which
  uses `random.Random(42)` to synthesize reproducible fixture data.
  It is seeded, off the dispatch path, and excluded from coverage.
  This file is named explicitly so a future contributor does not
  try to "fix" it by removing the seed.
- A future PR that introduces a PRNG, a clock read, or hidden
  module state into a `*Processing` class is a breaking change to
  this invariant and is rejected on principle, not on per-PR
  judgement. The same rule applies if a child registers a callable
  on the dispatch path that captures mutable state.

The complementary work that ROADMAP describes under "Deterministic
mode + seed control" is **partially resolved** by this ADR. What
remains is a router-level `deterministic_mode` flag stamped into the
`_meta` block (alongside `package_version`, `tool_name`, and
`called_at`), so a downstream reviewer can confirm a result was
produced under the invariant. That stamp is only meaningful when
paired with content-hashed provenance ([ROADMAP § Real provenance
hashing on derived metrics](../../ROADMAP.md#real-provenance-hashing-on-derived-metrics)),
because the hash is what lets a reviewer detect a violation of the
invariant after the fact. Shipping the stamp without the hash would
be cosmetic. It is therefore deferred as joint work with the
provenance-hashing item.

## Consequences

**Positive.**

- The same Tier-1 call with the same inputs returns the same
  numbers across machines, runs, and Python versions where stdlib
  semantics match. A reviewer re-running an analysis from the
  audit log gets byte-identical metric values without further
  framework support.
- The "Deterministic mode + seed control" roadmap item shrinks to
  the residual scope (router-level audited stamp, paired with
  provenance hashing). The bulk of the work — making the layer
  PRNG-free in the first place — is shipped.
- Future cross-cutting features (provenance hashing, deterministic
  replay, evaluation harness) can assume processing is referentially
  transparent. They retrofit cleanly.
- Contributors get a clear test for whether a proposed change
  belongs in `processing.py` or `child.py`: if it reads a clock,
  uses randomness, or touches I/O, it is `child.py`'s responsibility.

**Negative.**

- Some analytical patterns that are natural with randomness
  (Monte Carlo confidence bands, bootstrap resampling,
  randomized projections for high-dimensional summaries) cannot
  be added to a `*Processing` class without first negotiating an
  explicit seed-threading design. That design is the residual
  scope on the roadmap; until it lands, these patterns belong
  outside the framework or behind a future `deterministic_mode`
  contract.
- The invariant is enforced by review, not by a runtime guard.
  A contributor who adds `import random` to a processing module
  in a large diff can slip past a tired reviewer. Mitigation:
  this ADR names the rule explicitly so a `grep` for the import
  on any future audit catches the violation.

**Neutral.**

- The `demo/sample_data.py` PRNG is part of the contract, not an
  oversight. Removing or re-seeding it would break demo
  reproducibility. Future contributors should leave it alone.
- The invariant says nothing about determinism *across* Python
  minor versions or stdlib changes. Reproducibility is bounded by
  the runtime declared in the `_meta` block — not promised against
  every interpreter that exists.

## Alternatives considered

**Build the router-level `deterministic_mode` flag now.** Rejected.
The flag stamped into `_meta` is only auditable when paired with a
content hash that lets a reviewer verify the result actually came
from the declared inputs. Without provenance hashing, the stamp is
a self-attestation that a misbehaving contributor could add to any
result. The combined feature (flag + hash) is the next step on the
roadmap; shipping the flag alone would be a cosmetic governance
control, which is exactly the kind of feature ADR 0001 and ADR 0003
were written to keep out of the framework.

**Audit and remove the `demo/sample_data.py` PRNG.** Rejected. The
PRNG is seeded with a constant (`random.Random(42)`), runs entirely
inside the demo path, never reaches a child's `execute()` or a
`*Processing` method, and is excluded from coverage. Removing it
would require either a fixture file (drift risk over time) or a
deterministic generator that produces less realistic synthetic data
(loses teaching value). The current state is a worked example of
the invariant: PRNG is fine when it is seeded and isolated.

**Add a runtime PRNG-detection assertion at module-import time.**
Rejected. A `sys.modules` check after import that asserts no
processing module has imported `random` or `numpy.random` is
mechanically possible, but it is enforcement against an audience
of one (the project maintainer) for a property that a code review
already catches. The maintenance cost — special-casing test
imports, future legitimate uses behind `deterministic_mode`,
indirect imports through dependencies — exceeds the value. The ADR
itself is the enforcement mechanism: a contributor or reviewer
reading it knows the rule.

**Leave the roadmap entry as-is and write no ADR.** Rejected.
ROADMAP currently claims "Several analytical functions touch
pseudo-randomness (anomaly sampling, downsampling variants)" — the
drift audit shows that claim is false. Leaving the entry uncorrected
would let a contributor read the roadmap, conclude the layer needs a
seed-threading retrofit, and write code against a state of the world
that does not exist. The ADR records what shipped silently and
narrows the residual scope to what actually remains.
