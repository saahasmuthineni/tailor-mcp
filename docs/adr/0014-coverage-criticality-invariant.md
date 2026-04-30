# ADR 0014: Coverage criticality is an invariant — newly-uncovered CRITICAL or HIGH code is a regression regardless of overall percentage

- **Status:** Accepted
- **Date:** 2026-04-30
- **Related:** [ADR 0001 (Audit log is the backbone)](0001-audit-log-as-backbone.md), [ADR 0003 (PHI scrubber as seam)](0003-phi-scrubber-seam.md), [ADR 0005 (Cost pre-estimation)](0005-cost-pre-estimation.md), [ADR 0009 (Vault subject-keying)](0009-vault-subject-keying.md), [ADR 0010 (Adversarial pairing)](0010-adversarial-pairing.md), [ADR 0011 (Promotion policy)](0011-promotion-policy.md), [ADR 0012 (Vault PHI-scrubber bypass)](0012-vault-phi-scrubber-bypass.md), [ADR 0013 (Cache-only purge on consent revocation)](0013-cache-only-purge-on-consent-revocation.md), [CLAUDE.md § Security Pipeline](../../CLAUDE.md#security-pipeline-cheapest-first)

## Context

The project has carried an 80% coverage floor in
[`pyproject.toml [tool.coverage]`](../../pyproject.toml) since the
v5-era CI hardening, enforced by `ci-gate-runner` on every commit.
The floor is necessary — a regression that drops total coverage
below 80% is a hard CI failure — but it is not sufficient. A 4-line
uncovered range in `framework/security.py` (PHI scrubbing, consent
gate, circuit breaker) is not the same finding as a 40-line uncovered
range in `__main__.py` (argparse plumbing). The percentage hides that
asymmetry: a diff can add untested code on the security-pipeline hot
path and still leave the overall percentage above 80%, because the
denominator is dominated by well-covered code elsewhere.

The `coverage-criticality-mapper` agent shipped in v6.3.0 to close
that gap. Its prompt at [`.claude/agents/coverage-criticality-mapper.md`](../../.claude/agents/coverage-criticality-mapper.md)
classifies every uncovered region by criticality — CRITICAL / HIGH /
MEDIUM / LOW — anchored on ADR-cited regions. The agent's promotion
rationale ([ADR 0011](0011-promotion-policy.md) §
"`coverage-criticality-mapper`") states the rule it enforces:
*"newly uncovered code in CRITICAL or HIGH regions = COVERAGE
REGRESSION regardless of overall percentage."* That sentence has
governed verdicts since v6.3.0, but it lives only inside an agent
prompt and a promotion-rationale paragraph. The rule is policy,
not architecture. A future contributor reshaping the agent — or a
future Claude session re-deriving the criticality map from first
principles — could weaken the rule without superseding any ADR.

The risk is not hypothetical. The project's stated goal is
research-software infrastructure for IRB-governed workflows, and
the load-bearing ADRs (0001 audit, 0003 scrubber seam, 0005 cost
gate, 0009 subject-keying, 0012 vault scrubber bypass, 0013 cache
purge) all describe code regions where a silent test-coverage gap
ships a silent compliance gap. The audit log records that a tool
was called; coverage on the audit-log code records that the
recording itself works. A regression on the latter is a regression
on the framework's reproducibility claim, not a percentage-point
move on a dashboard.

The question this ADR answers: *what is the smallest contract that
makes the criticality invariant load-bearing instead of agent-
suggestion, and how does the project keep the criticality map in
lockstep with the ADR set as new load-bearing regions land?*

## Decision

The coverage criticality invariant is codified as architecture: newly-
uncovered code in CRITICAL or HIGH regions is a `COVERAGE REGRESSION`
regardless of overall percentage. The 80% floor in `pyproject.toml`
remains a hard backstop, not a target. The floor catches gross
coverage collapse; the invariant catches the case where total
percentage looks healthy while load-bearing code newly slips through.

The criticality taxonomy below is the canonical map. A region that
does not appear here defaults to MEDIUM, and the absence is itself
a signal — when a new ADR introduces a load-bearing module, that
ADR declares the criticality classification and this ADR's map gets
extended in the same change.

- **CRITICAL — security pipeline, audit, router dispatch, vault writer,
  PHI-scrubber seam, cache-purge contract, vault-bypass dispatch.**
  Anchored on:
  - [ADR 0001](0001-audit-log-as-backbone.md) — `framework/audit.py`
    (AuditLog, JSON helpers). The audit log is the framework's
    durability claim; uncovered code here is uncovered evidence.
  - [ADR 0003](0003-phi-scrubber-seam.md) — `framework/security.py`
    (PHIScrubber and the wider security pipeline) and the
    PHI-scrub seam in `framework/router.py`. The seam is no-op by
    default and uncovered code on it ships a no-op no one knows
    is present.
  - [ADR 0005](0005-cost-pre-estimation.md) — `framework/cost.py`
    `CostGate` and the fail-closed estimator branch. ADR 0005's
    "estimator failures fail closed" guarantee depends on the
    failing branch being exercised.
  - [ADR 0009](0009-vault-subject-keying.md) — the `subject_id`
    propagation paths in `framework/router.py` and
    `framework/vault/writer.py`. A regression here breaks
    cross-subject filter integrity.
  - [ADR 0012](0012-vault-phi-scrubber-bypass.md) — the vault
    dispatch path in `framework/router.py` that intentionally
    skips the PHI-scrubber seam for analyst-authored content.
    Uncovered code here is uncovered policy.
  - [ADR 0013](0013-cache-only-purge-on-consent-revocation.md) —
    `_handle_consent_revocation` in `framework/router.py` and
    every child's `purge_cache` implementation. The fail-closed
    ordering ("purge first, then flip consent") only holds if the
    failure branch is tested.

  Uncovered code in CRITICAL is always a finding. Newly-uncovered
  code in CRITICAL after a diff is `COVERAGE REGRESSION` regardless
  of overall percentage.

- **HIGH — child execute paths, vault layer dispatch, schema validation,
  shared interfaces.** Anchored on:
  - The wider security pipeline in `framework/security.py`
    beyond the PHIScrubber seam (`ParamValidator`, `CircuitBreaker`,
    `ConsentGate`).
  - `framework/vault/layer.py` — the 25-tool vault dispatch path
    where ADRs 0006, 0007, and 0009 land at runtime.
  - `framework/interfaces.py` — `SUBJECT_ID_SCHEMA`,
    `ToolDefinition`, `ConsentInfo`, `LLMInstruction`. Cited by
    ADRs 0002, 0004, and 0009.
  - `children/*/child.py` — child `execute()` methods. The router
    dispatches to these and a coverage gap here means a Tier-1 or
    Tier-2 tool is shipping unexercised.

  Uncovered code in HIGH is a finding unless the caller cites a
  reason (e.g. an unreachable defensive branch). Newly-uncovered
  code in HIGH after a diff is `COVERAGE REGRESSION` on the same
  bar as CRITICAL.

- **MEDIUM — analytical processing, vault renderers, vault parsers,
  storage primitives.** Anchored on:
  - `children/*/processing.py` — pure-function analytics. Per
    [ADR 0008](0008-deterministic-by-construction-processing.md),
    mathematical correctness is the primary defence here and
    coverage is desirable but secondary.
  - `framework/vault/renderer.py`, `parser.py`, `rescan.py` —
    markdown rendering and index revalidation.
  - `framework/storage.py` — `BaseStorage` SQLite WAL pattern.

  Uncovered code in MEDIUM is a finding worth noting but not
  blocking, unless the missing region is mathematical-correctness-
  critical (e.g. a new processing method shipping with no tests).

- **LOW — entry points, demo, fixtures, wizard orchestration.**
  Anchored on:
  - `__main__.py` — argparse plumbing and the
    `mcp.server.stdio.run()` invocation.
  - `wizard.py`, `pilot.py` — interactive setup wizards.
  - `demo/*` — synthetic-data runners.
  - `_fixtures/*` — packaged CSV fixtures.

  Uncovered code in LOW is noted but not actionable. The percentage
  cost matters for the 80% floor; criticality does not. Several of
  these paths are explicitly excluded from the coverage denominator
  in [`pyproject.toml [tool.coverage.run].omit`](../../pyproject.toml).

The exception clause for LOW is named explicitly so a future
contributor does not try to "fix" it: `__main__.py`'s `run()` method
(the `mcp.server.stdio` invocation), the demo runners, and `wizard.py`'s
interactive flows are correctly LOW because they are not unit-testable
without integration infrastructure (a stdio harness, a synthetic OAuth
callback server, an interactive-prompt simulator) that would exceed
the test-shape value. The smoke check in `ci-gate-runner` and the
end-to-end pilot wizard exercise (per the v6.2.1 release banner) cover
these paths at the integration level, which is the correct grain.
A coverage gap here is structural, not a missing test.

Enforcement mechanism:

- **`coverage-criticality-mapper`** is the runtime enforcer. It runs
  after every `ci-gate-runner` PASS on non-trivial work, parses the
  coverage report against this ADR's map, and produces one of three
  verdicts: `COVERAGE OK`, `COVERAGE GAPS — REVIEW` (pre-existing
  CRITICAL or HIGH gaps), or `COVERAGE REGRESSION` (newly-uncovered
  CRITICAL or HIGH lines).
- **`ci-gate-runner`** continues to enforce the 80% floor. The two
  gates compose: `ci-gate-runner` fails on percentage collapse;
  `coverage-criticality-mapper` fails on criticality regression
  inside a passing percentage.
- **`red-team-reviewer`** ([ADR 0010](0010-adversarial-pairing.md))
  fires on any confident `COVERAGE OK` verdict against non-trivial
  work, attacking the verdict on whether the diff actually missed a
  CRITICAL region the map should have caught. The dissent does not
  have to win; it has to be visible so the main session cannot
  silently drop it during synthesis.
- **The criticality map below is the canonical source.** The
  `coverage-criticality-mapper` agent prompt cites this ADR; future
  reshapes of the agent are constrained by this ADR rather than
  free to redraw the taxonomy.

New regions land via ADR. When a future ADR introduces a module on
the critical path (e.g. a new framework component, a new dispatch
seam), that ADR declares the criticality classification in a
`## Criticality classification` section and updates this ADR's map
in the same change. The ADR template at
[`docs/adr/0000-template.md`](0000-template.md) gains an optional
`## Criticality classification` section so the prompt is visible at
draft time. ADRs that introduce no new code regions (governance,
team-shape, doc-policy) omit the section.

Reversal condition: this invariant tightens further (e.g. "CRITICAL
regions require 100% coverage") only via a superseding ADR with a
named scope and a migration plan for the existing CRITICAL gaps.
Loosening the invariant — re-classifying a CRITICAL region to HIGH
or MEDIUM, or weakening "regardless of overall percentage" to "if
overall percentage drops" — also requires a superseding ADR. The
agent's prompt cannot drift the rule; the rule lives here.

## Consequences

**Positive.**

- The criticality invariant becomes architecture rather than agent
  policy. A future contributor reshaping `coverage-criticality-mapper`
  is constrained by this ADR; a future Claude session reading the
  agent prompt finds a citable upstream source instead of free-floating
  taxonomy.
- The 80% floor is correctly framed as a backstop, not a target.
  Coverage at 84% with newly-uncovered code in `framework/security.py`
  is the failure mode this ADR exists to make visible — and it is
  exactly the case the percentage hides.
- The map's anchoring on ADR-cited regions ties coverage discipline
  to the project's stated load-bearing claims. A region is CRITICAL
  not because the agent's author thought so, but because [ADR 0001](0001-audit-log-as-backbone.md)
  or [ADR 0013](0013-cache-only-purge-on-consent-revocation.md) said
  the framework depends on it. The taxonomy is auditable against the
  ADR set.
- The "new ADR declares its own criticality" rule prevents map drift.
  When [ADR 0013](0013-cache-only-purge-on-consent-revocation.md)
  shipped a new contract on `_handle_consent_revocation`, the lack of
  this rule meant the agent's map only caught up by accident; with the
  rule in place, future ADRs land with the classification baked in.
- The exception clause for LOW (entry points, wizards, demo) prevents
  well-meaning contributors from chasing 100% coverage on paths whose
  test-shape value is dominated by integration smoke checks. The
  classification is justified, not aspirational.

**Negative.**

- The criticality map adds documentation surface that must stay in
  sync with the code. A region renamed or refactored without
  updating this ADR shows up as a `BORDER NOTES` flag from the
  agent ("file does not match any criticality category, defaulted
  to MEDIUM") rather than a hard failure — soft drift is possible.
  Mitigated by the ADR-declares-its-own-criticality rule and by
  `code-vs-roadmap-drift-auditor`'s existing remit on documentation
  truthfulness.
- Enforcement is still agent-driven at PR time, not CI-blocking.
  A reviewer who skips `coverage-criticality-mapper` on a non-trivial
  diff can land a `COVERAGE REGRESSION` without the gate firing.
  This is the same shape as [ADR 0008](0008-deterministic-by-construction-processing.md)'s
  "enforced by review at PR time" gap; the mitigation is structural
  (agent + adversarial pair, rather than CI workflow plumbing) and
  matches the project's tooling realities. A CI-blocking enforcement
  is a reasonable future tightening but lives behind a superseding
  ADR.
- The taxonomy's edge cases (a file split across criticality classes,
  a test file with unreachable branches, a file in `omit` that
  becomes load-bearing) require human judgment and are flagged via
  BORDER NOTES rather than mechanically resolved. Acceptable —
  edge cases that would otherwise be silently miscategorised at
  least become visible.

**Neutral.**

- The 80% floor in `pyproject.toml` is unchanged. Tightening or
  loosening the floor remains tuning, not architecture, per
  [ADR 0005](0005-cost-pre-estimation.md)'s pattern of treating
  numeric thresholds as adjustable without an ADR amendment. What
  this ADR codifies is the qualitative rule that sits on top of
  the quantitative floor.
- Existing pre-existing-uncovered code in CRITICAL or HIGH regions
  is debt, not regression. This ADR does not retroactively flag
  every gap as a failure; it flags newly-uncovered gaps from this
  point forward. Existing debt is tracked by the agent's
  `COVERAGE GAPS — REVIEW` verdict.
- The `omit` list in `pyproject.toml` (currently `__main__.py`,
  `wizard.py`, `demo/*`, `strava_api.py`) continues to reflect the
  LOW-region exception clause. Adding a file to `omit` is itself a
  decision the criticality map governs: a file added to `omit` must
  be classifiable as LOW under this ADR's exception clause, or the
  addition needs a superseding ADR.
- The "Refuse on conflict with codebase ground truth" Tier-2 rule
  that every specialist carries continues to apply.
  `coverage-criticality-mapper` already refuses dispatch instructions
  asking it to re-classify a CRITICAL gap to suppress a `COVERAGE
  REGRESSION` verdict; this ADR makes the refusal architecturally
  grounded rather than agent-prompt grounded.

## Alternatives considered

**Leave the rule in the agent prompt — defer codification.** Rejected
on the same grounds [ADR 0011](0011-promotion-policy.md) gave for its
own codification: a rule that diverges from the apparent default but
lives only in an agent prompt is invisible to future readers. A future
Claude session reads `pyproject.toml`, finds the 80% floor, and
either re-derives the criticality rule from first principles or lets
it drift back to "percentage above floor = pass." [ADR 0010](0010-adversarial-pairing.md)
established the precedent that load-bearing rules belong in ADRs
even when an agent prompt currently encodes them; this ADR applies
the same precedent.

**CI-blocking enforcement — fail the build on `COVERAGE REGRESSION`.**
Rejected for v6.4.1 with a named reversal condition. The project's
CI is intentionally minimal (per the project's "GitHub Actions
disabled" memory note, gates are validated locally and the agent
roster carries the load that a richer CI would). Wiring criticality
enforcement into a CI step would require either a CI workflow change
or a `pre-commit` hook the project does not currently use. The
agent + adversarial-pair shape matches the project's tooling and
shifts the enforcement to where the boss and the main session
actually meet diffs (PR review). A future tightening — making
`COVERAGE REGRESSION` a CI failure — is reasonable behind a
superseding ADR once the project adopts a CI plumbing pattern that
absorbs it cleanly.

**Per-file coverage thresholds in `pyproject.toml`.** Rejected.
Per-file thresholds (e.g. "framework/security.py requires 95%")
are mechanically simpler than an agent + ADR pair, but they fail
in the way the agent's existing prompt names: a file's load-bearingness
depends on what its lines do, not on the file path. A defensive
`raise` branch in `framework/security.py` that cannot be hit
without intentionally corrupting state is uncovered for a structural
reason, and a per-file threshold either flags it as a failure
(false positive) or accepts the gap silently (false negative). The
agent's per-line classification with diff cross-reference is the
right grain; per-file thresholds are too coarse.

**Drop the criticality classification — rely on the 80% floor alone.**
Rejected. The 80% floor's blind spot is precisely the case this
ADR exists to close: a diff that adds untested code on a load-bearing
hot path while the percentage stays above the floor. The floor is
a necessary backstop, not a sufficient signal. Removing the
qualitative rule re-creates the failure mode the
`coverage-criticality-mapper` agent was promoted under
[ADR 0011](0011-promotion-policy.md) to address.

**Make every region CRITICAL — eliminate the taxonomy.** Rejected.
Treating all uncovered code as a regression collapses the rule into
"100% coverage required everywhere," which conflicts with the LOW
exception clause for entry points and wizards (paths whose test-
shape value is dominated by integration smoke checks). A uniform
CRITICAL classification would force either chasing un-unit-testable
coverage or weakening the rule with ad-hoc exceptions — both of
which defeat the structural argument. The four-tier taxonomy
preserves the strong claim on CRITICAL and HIGH while honestly
naming the regions where unit coverage is the wrong tool.
