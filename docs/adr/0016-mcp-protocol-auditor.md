# ADR 0016: MCP-protocol auditor — wire-level correctness is a seam, not a hope

- **Status:** Accepted
- **Date:** 2026-04-30
- **Related:** [ADR 0001 (Audit log is the backbone)](0001-audit-log-as-backbone.md), [ADR 0008 (Deterministic by construction)](0008-deterministic-by-construction-processing.md), [ADR 0010 (Adversarial pairing)](0010-adversarial-pairing.md), [ADR 0011 (Promotion policy)](0011-promotion-policy.md), [ADR 0014 (Coverage criticality)](0014-coverage-criticality-invariant.md), [CLAUDE.md § Workflow: manager mode](../../CLAUDE.md#workflow-manager-mode)

## Context

The framework presents itself to LLM clients as an MCP server. Every
behavioural claim the project makes — audit-log integrity, consent
gating, cost pre-estimation, deterministic processing — depends on the
JSON-RPC adapter between the framework's internal abstractions
(`ChildMCP`, `VaultLayer`, the security pipeline) and the wire format
the `mcp` SDK serializes. The adapter is structurally distinct from
the abstractions it adapts. An ADR-grade invariant that holds inside
the framework can still ship broken on the wire if the adapter is
silently miscoded.

The v6.5.0 demo-before-commit gate (Protocol 5) made that gap
visible. A real Claude Desktop client connecting to the framework
surfaced **5 ship-blocker bugs in the protocol-adapter surface in 90
minutes**, none of which had been caught by 578 pytest tests, eight
specialist agent gates, or a red-team adversarial pass:

1. `Server.run()` missing a third positional argument due to `mcp`
   1.27.0 SDK signature drift — the server failed to start at all
   under the shipped pin.
2. Two vault tools shipping with parameter schemas missing the
   `description` key — `tools/list` succeeded inside Python but
   produced malformed JSON-RPC the client rejected.
3. `_dumps(default=str)` silently stringifying `datetime`, `Path`,
   and `Decimal` instances into wire payloads — `_meta.called_at`
   arriving as a Python `repr` rather than ISO-8601, downstream of
   every successful tool call.
4. Vault markdown round-trip never verified through a real client —
   YAML frontmatter, fenced code blocks, and unicode survived the
   internal renderer but were never tested across the JSON-RPC
   boundary.
5. Post-execute hook failures swallowed silently — vault writes
   could fail without surfacing to the caller, breaking the
   reorientation tier's durability claim.

The common cause is that the framework's MCP-protocol-adapter surface
was structurally untested. No agent in the existing roster owned it.
[ADR 0010](0010-adversarial-pairing.md)'s `red-team-reviewer` and
[ADR 0014](0014-coverage-criticality-invariant.md)'s
`coverage-criticality-mapper` defend against suppression and
percentage-blind regression respectively, but both operate on
in-process artifacts. `ci-gate-runner` runs pytest in-process;
`vault-smoke-validator` drives `VaultLayer` via Python imports;
`integration-auditor` reads diffs. **Nothing today actually opens a
JSON-RPC channel against the framework.** Every gate in the existing
team trusts that the adapter is correct because the adapter has not
been a separable concern in the team's mental model.

The class of bug this gap admits is not hypothetical and not
exhaustively enumerable from inside Python. SDK signature drift
between `mcp` minor versions is upstream of the framework's control;
schema-key omissions pass type-checking because the dictionaries are
syntactically valid; `default=str` is a deliberate fallback that
becomes a bug only when serialization happens to encounter a type the
framework's tests didn't construct; markdown round-trip lossiness
shows up only when the JSON-RPC encoder and the markdown renderer
both touch the same string. Each is invisible to a gate that does not
speak the wire format.

The question this ADR answers: *what is the smallest structural seam
that gives the framework a wire-level correctness gate without
reshaping the existing roster, and where does that seam fire?*

## Decision

A new specialist, `mcp-protocol-auditor`, owns wire-level correctness
of the MCP-protocol-adapter surface. The agent drives `python -m
tailor serve` as a real subprocess speaking JSON-RPC over
stdio, and asserts wire-level correctness on every protocol surface
the framework exposes.

The rule, plain English: any change touching the protocol-adapter
surface fires `mcp-protocol-auditor` before it ships, and every
release is gated on a `PROTOCOL OK` verdict from a fresh run against
the release working tree. Wire-level claims belong to a wire-level
gate; in-process gates do not substitute.

Concrete mechanism:

- **`.claude/agents/mcp-protocol-auditor.md`** (model: sonnet) is the
  specialist's prompt. Its remit: drive a real subprocess, speak the
  MCP handshake (`initialize` → `notifications/initialized`), exercise
  `tools/list` and `tools/call` across all registered children and
  the vault layer, inject error cases (unknown tool, missing required
  parameter, consent-blocked call, cost-gated call), and assert
  wire-level correctness. The agent searches raw JSON payloads for
  Python `repr` artifacts (`datetime.datetime(`, `PosixPath(`,
  `WindowsPath(`, `Decimal('`, `<class '`) — any hit is a
  `default=str` coercion bug. Markdown-bearing responses are checked
  byte-equal modulo cross-platform newline normalization. `_meta`
  blocks are checked for parseable ISO-8601 `called_at`, version
  match against `__version__`, and tool-name match.
- **The agent owns regression tests, not just verdicts.** New
  subprocess tests land under `tests/test_serve_*` and run as part
  of the standard pytest discovery so `ci-gate-runner` picks them
  up automatically. The shared subprocess client fixture lives at
  `tests/_mcp_client.py`. The audit's first run on v6.5.0 added 13
  such tests covering the five bug classes above.
- **Firing triggers.** The agent fires after any change to
  `framework/router.py`, `framework/audit.py`, `framework/security.py`,
  `framework/vault/layer.py`, `framework/vault/writer.py`, or any
  child's `execute()` path. It fires mandatory before every release,
  matching the "before every release" cadence the four
  [ADR 0011](0011-promotion-policy.md) specialists adopted.
- **Adversarial pairing.** A confident `PROTOCOL OK` verdict against
  non-trivial work is paired with `red-team-reviewer` per
  [ADR 0010](0010-adversarial-pairing.md). The dissent does not have
  to win; it has to be visible. The agent's prompt carries the
  uniform "Refuse on conflict with codebase ground truth" Tier-2
  rule and the BORDER NOTES side-channel.
- **Promotion grounding.** The agent lands under
  [ADR 0011](0011-promotion-policy.md)'s structural-argument rule.
  Structural argument: the protocol-adapter surface is the address
  at which every other gate's claims meet a real client, and no
  existing specialist drives that surface. Severity grounding: the
  v6.5.0 demo surfaced five ship-blockers in 90 minutes, two of
  which (the SDK signature drift and the silent serialization
  coercion) would have shipped to a real PI under the existing
  gates. Maintenance estimate: one run per release plus on-demand
  runs after adapter-surface changes — well below the per-agent
  fire-frequency the existing roster carries.

The agent's first run on the v6.5.0 working tree audited the
adapter, fixed all five bugs, added the 13 subprocess tests, and
returned `PROTOCOL OK`. 591/591 tests pass after the audit. The
audit is the bootstrap precedent — recursive use was authorized by
the boss to demonstrate the agent against the gap that motivated
its existence.

## Consequences

**Positive.**

- The framework's wire-level claims now have a wire-level gate.
  Every behavioural ADR ([ADR 0001](0001-audit-log-as-backbone.md)
  audit integrity, [ADR 0005](0005-cost-pre-estimation.md) cost
  gating, [ADR 0008](0008-deterministic-by-construction-processing.md)
  determinism downstream of `_dumps`,
  [ADR 0009](0009-vault-subject-keying.md) `subject_id` propagation
  through `_meta`) gains a structural defence at the address where
  the claim actually meets a client. The audit log records that a
  call happened; the protocol auditor records that the recording
  arrives at the client without coercion artifacts.
- The bug class the v6.5.0 demo named is structurally addressed,
  not patched. SDK signature drift, missing schema keys, silent
  type coercion, markdown round-trip lossiness, and post-execute
  hook silent failures all share the property that they are
  invisible to in-process testing. A specialist that drives a real
  subprocess catches them by construction.
- Demo-before-commit (Protocol 5) is no longer the project's
  earliest wire-level signal. The boss's first encounter with a
  ship-blocker stops being the gate; the agent fires before the
  demo and the demo becomes confirmation rather than discovery.
- The agent composes cleanly with the existing roster.
  `coverage-criticality-mapper` continues to own per-line coverage
  classification on a complementary axis; `red-team-reviewer`
  pairs with the new agent's confident verdicts;
  `reproducibility-provenance-auditor` continues to enforce the
  determinism invariant in-process and the protocol auditor
  enforces it on the wire downstream of the same pipeline. No
  existing specialist's remit shrinks.
- The 13 regression tests added on the bootstrap run encode the
  bug classes as permanent contract assertions. A future
  contributor who breaks `_dumps` or omits a `description` key
  fails pytest before the agent ever fires again — the agent's
  output is durable beyond its runtime.

**Negative.**

- The agent adds subprocess overhead on every release. A full audit
  run is multi-second per surface, materially slower than an
  in-process pytest pass. Acceptable because the agent fires
  per-release, not per-commit, and the cost is bounded by the
  number of registered tools (currently 47 across vault, running,
  csv_dir, and template).
- Subprocess MCP tests are more brittle than in-process tests on
  CI runners with timing variance. The agent's prompt names this
  explicitly and budgets longer timeouts than a unit test would
  carry. A flaky CI run on a subprocess test is a known cost; the
  alternative (no wire-level gate) is the failure mode this ADR
  exists to prevent.
- The agent's coverage of upstream-SDK drift is reactive, not
  predictive. It catches signature drift on the run after the SDK
  pin moves, not at pin-bump time. Mitigated by the
  before-every-release trigger — the worst case is a release blocked
  by a `PROTOCOL ERROR` verdict on a fresh subprocess run, which is
  exactly the failure mode the gate is designed to surface.

**Neutral.**

- The agent does not introduce new code regions in the framework
  itself. Per [ADR 0014](0014-coverage-criticality-invariant.md),
  the files the auditor focuses on (`framework/router.py`,
  `framework/audit.py`, `framework/security.py`,
  `framework/vault/layer.py`, `framework/vault/writer.py`) are
  already CRITICAL or HIGH. This ADR adds a new gate over existing
  critical regions; the criticality map in
  [ADR 0014](0014-coverage-criticality-invariant.md) is unchanged.
- The agent has no authority to overturn other gates. A
  `PROTOCOL OK` verdict does not waive coverage-criticality or
  reproducibility-provenance findings; those gates fire on
  in-process artifacts the protocol auditor does not inspect. The
  team's command structure is unchanged — the agent widens the
  surface of detected regressions, not the synthesizer-of-record
  role.
- The "Refuse on conflict with codebase ground truth" Tier-2 rule
  every specialist carries continues to apply. The agent refuses
  dispatch instructions asking it to suppress a wire-level finding
  to unblock a release; the refusal is architecturally grounded
  rather than agent-prompt grounded.

Reversal condition: tightening this rule — for example, making
`PROTOCOL ERROR` a CI-blocking gate rather than agent-driven PR-time
enforcement — lives behind a superseding ADR with a named scope and
a migration plan, matching the precedent set by
[ADR 0014](0014-coverage-criticality-invariant.md). Loosening the
rule — relaxing the "before every release" trigger, narrowing the
surface the agent owns, or weakening the wire-level assertions —
also requires a superseding ADR. The agent's prompt cannot drift the
rule; the rule lives here.

## Alternatives considered

**Extend `ci-gate-runner` to include subprocess MCP tests instead of
adding a new specialist.** Rejected. `ci-gate-runner`'s remit is
pytest + ruff + security probe + CLI smoke with failure forensics —
each of those surfaces is in-process and bounded by pytest's
discovery model. Folding subprocess MCP audits into the same agent
would either dilute its specialization (an agent that does too many
crafts produces weaker verdicts on each) or force the wire-level
checks to fit inside pytest's timing and isolation model, which is
the constraint the bugs slipped through in the first place. The
[ADR 0010](0010-adversarial-pairing.md) precedent is that adversarial
framing produces dissent precisely because the agent's prompt is
narrow and adversarial; the same precedent applies to wire-level
adversarial framing against in-process abstractions. A separate
specialist preserves the structural separation that makes the new
gate effective.

**Make wire-level checks CI-blocking — fail the build on a
`PROTOCOL ERROR` verdict.** Rejected for v6.5.0 with a named
reversal condition, on the same grounds
[ADR 0014](0014-coverage-criticality-invariant.md) gave for the
coverage-criticality invariant. The project's CI is intentionally
minimal (per the project's "GitHub Actions disabled" memory note,
gates are validated locally and the agent roster carries the load
that a richer CI would). Wiring subprocess MCP audits into a CI
step would require either a CI workflow change or a subprocess
harness the project does not currently maintain in CI. The
agent + adversarial-pair shape matches the project's tooling and
shifts the enforcement to where the boss and the main session
actually meet diffs (PR review and pre-release demo). A future
tightening — making `PROTOCOL ERROR` a CI failure — is reasonable
behind a superseding ADR once the project adopts a CI plumbing
pattern that absorbs subprocess MCP tests cleanly.

**Rely on demo-before-commit (Protocol 5) alone — accept that real
clients catch wire-level bugs at the demo boundary.** Rejected on
severity grounds. The v6.5.0 demo did catch the five
ship-blockers, which is exactly the data point that motivates this
ADR — but Protocol 5 is the boss's interface to the system, not a
gate the system applies to itself. Catching ship-blockers at the
demo means the boss does the wire-level discovery work the agent
roster should be doing on his behalf. The structural argument named
in [ADR 0011](0011-promotion-policy.md) — specialists land before
the third incident on severity-dominant cases — applies directly
here: a wire-level regression that ships past the demo to a real PI
costs the project's research credibility, which is the
severity-dominant case Protocol 5 alone cannot prevent.

**Add per-test pytest markers (`@pytest.mark.protocol`) instead of a
dedicated agent.** Rejected. Markers organize tests within pytest's
in-process discovery; they do not cross the JSON-RPC boundary. A
marker-based shape would either still run inside pytest's process
model (which is the constraint the bugs slipped through) or require
an out-of-process runner that re-creates the agent's role under a
different name. The 13 subprocess tests the agent's bootstrap run
added are valuable as durable contract assertions, but they are
artifacts of the agent's work, not a substitute for the agent. A
marker without a specialist who drives the surface end-to-end on
every release leaves the same structural hole the in-process tests
already had.

**Spawn a long-running protocol harness as a standalone process and
poll it from CI.** Rejected on engineering-cost grounds. A persistent
harness would require state management (process lifecycle,
restart-on-crash, per-test isolation) the project does not currently
need for any other gate. The agent's per-run subprocess shape is
ephemeral by construction — every run starts cold, drives a fresh
server against fresh temp directories, and exits. The cost is paid
per run rather than amortised, which matches the per-release fire
frequency the agent is calibrated for. A persistent harness optimises
for a frequency the project does not have.

## v6.11.x amendments — enforcement mechanism

The original ADR 0016 wording said the agent is *"mandatory before every release."* That mandate was load-bearing for the gate's structural argument but its **enforcement mechanism** was unspecified. As of v6.11.0, `release-shipper.md` did not reference `mcp-protocol-auditor`; the gate fired only when the main session in release prep "remembered" to spawn it. That is convention, not enforcement.

The 2026-05-08 cross-ADR review (sparked by the `recipient-install-validator` first-wild-run that exposed the same gap on ADR 0028) closes this. The actual enforcement is **attestation-required at release-shipper pre-flight**:

- `release-shipper.md` § "Pre-tag gate composition" inspects `git diff --name-only main...HEAD` against this agent's trigger globs (`framework/router.py`, `framework/audit.py`, `framework/security.py`, `framework/vault/{layer,writer}.py`, `children/*/child.py`).
- If any trigger matches and the caller has not passed `--gates-confirmed=mcp-protocol:<verdict>`, release-shipper hard-refuses with the same shape as the dirty-working-tree refusal.
- The verdict string is recorded verbatim in the release commit body (`## Pre-tag gates attested`). release-shipper does not parse verdict semantics — the boss is the authority on whether the verdict is acceptable. A deliberately-false attestation becomes a deliberately-false statement in the durable audit record.

**Why attestation rather than inline re-spawn.** The agent runs in minutes, not seconds, but most releases do not touch its trigger globs. Attestation makes the convention auditable at the cost of one flag while letting the boss run the gate at any point during release prep — not specifically at release-shipper invocation. The cost-vs-frequency tradeoff per [ADR 0011](0011-promotion-policy.md) is the load-bearing argument for the policy choice.

The original "mandatory before every release" wording stands on the record; the v6.11.x amendment refines what mandatory *means* mechanically. The structural argument (wire-level correctness is a seam, not a hope) is unchanged.
