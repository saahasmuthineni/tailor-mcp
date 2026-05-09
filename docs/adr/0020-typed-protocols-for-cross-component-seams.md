# ADR 0020: Typed Protocols for cross-component seams — signature drift fails at type-check time, not runtime

- **Status:** Proposed
- **Date:** 2026-05-01
- **Related:** [ADR 0001 (Audit log is the backbone)](0001-audit-log-as-backbone.md), [ADR 0008 (Deterministic by construction)](0008-deterministic-by-construction-processing.md), [ADR 0010 (Adversarial pairing)](0010-adversarial-pairing.md), [ADR 0011 (Promotion policy)](0011-promotion-policy.md), [ADR 0014 (Coverage criticality)](0014-coverage-criticality-invariant.md), [ADR 0016 (MCP-protocol auditor)](0016-mcp-protocol-auditor.md)

## Context

[ADR 0016](0016-mcp-protocol-auditor.md) named one instance of a wider
class of bug. The v6.5.0 demo-before-commit gate caught a ship-blocker
in which `mcp.server.Server.run()` had grown a third positional
argument (`initialization_options`) between SDK minor versions, and
the framework was still calling it with two. The TypeError surfaced
only when a real client connected; every in-process gate was green
because none of them actually called the SDK's `run()` method against
the wire. ADR 0016's response was to add a wire-level specialist
(`mcp-protocol-auditor`) that drives the framework as a real
subprocess and asserts wire-level correctness on every release.

That patch closed the SDK-boundary instance of the class. The class
itself is wider than the SDK boundary. The same shape lives at
internal seams the framework owns end-to-end. The post-execute hook
contract at [`framework/router.py:554-565`](../../src/tailor/framework/router.py)
calls each registered hook as `hook(domain, tool_name, result)` —
three positional arguments, no type annotation on the contract beyond
`Callable`, no Protocol declaration anywhere. `VaultWriter` registers
itself as a hook from
[`framework/vault/writer.py`](../../src/tailor/framework/vault/writer.py)
via `__main__.py`'s `router.register_post_execute_hook(vault_writer)`.
The framework wraps every hook invocation in `try / except Exception`
and now (post-v6.5.0) appends the failure to `_meta.hook_warnings` so
it surfaces in the wire payload — but the structural fix is partial.
A future fourth-arg add to the hook signature, or a kwarg-only
parameter, raises TypeError inside the same try/except. The hook
warning surfaces, but no test in the suite asserts that the canonical
demo call carries an *empty* `_meta.hook_warnings`. Pytest stays
green; vault writes silently stop; the framework's reorientation-tier
durability claim ([ADR 0001](0001-audit-log-as-backbone.md) audit
backbone, [ADR 0014](0014-coverage-criticality-invariant.md) HIGH
region on `vault/writer.py`) ships broken until a human reads a wire
payload by hand.

The post-execute hook is one of several internal seams with the same
shape. The audit row schema is partially codified in
[ADR 0001](0001-audit-log-as-backbone.md) as a column list but not as
a typed object the writer and reader both bind to. The `_meta`
provenance block is partially codified across v6.3.1
(`scrubber_warning`) and the v6.5.0 demo audit (`hook_warnings`) but
its field set lives only in router.py's emit site and a handful of
tests. The `ChildMCP` abstract surface is defined as an ABC with
abstract methods, which catches *missing* implementations at import
time but does not catch *signature drift* in a method's parameters or
return shape. Each seam encodes a contract the framework relies on
between two components; each contract is currently expressed as
docstrings, dictionary keys, and conventions enforced by code review.

The class of bug this gap admits is the same class
[ADR 0016](0016-mcp-protocol-auditor.md) addressed at the SDK
boundary, applied inward. A contributor reshapes one side of a seam
without updating the other; the call still type-checks because the
contract is untyped; pytest passes because no test exercises the
exact arity the change broke; the framework ships a silent regression
on a CRITICAL or HIGH region per
[ADR 0014](0014-coverage-criticality-invariant.md). The
`mcp-protocol-auditor` runtime gate catches some of these on its
release-time subprocess pass — but only the ones that surface through
the wire. A hook-arity drift that fails inside the silent try/except
is invisible to the protocol auditor's assertions because the
TypeError is caught before the wire response is built; the auditor
sees a successful response with a stuffed `hook_warnings` field and
no way to know that field should have been empty.

The question this ADR answers: *should the framework adopt a typed
Protocol contract on its load-bearing internal seams so signature
drift fails at type-check time, or rely on the agent-driven runtime
gate ADR 0016 already shipped?*

## Decision

Load-bearing cross-component seams adopt typed `Protocol` contracts.
Signature drift on these seams fails at type-check time rather than
at runtime, and the type-checker runs as a `ci-gate-runner` step on
every commit. Wire-level runtime audits per
[ADR 0016](0016-mcp-protocol-auditor.md) remain the second-line gate
for the SDK boundary and for serialization-shape claims that types
alone cannot express; the two gates compose, they do not substitute.

The rule is scoped. *Every cross-component call gets a Protocol* is
over-broad and would import a maintenance burden the project has not
priced in. The right scope is the seams the project has already
identified as load-bearing through its ADR set:

- **Router → post-execute-hook** — the seam at
  [`framework/router.py:554-565`](../../src/tailor/framework/router.py)
  whose silent try/except is the failure mode this ADR exists to
  close. Currently typed as `Callable`.
- **Audit row schema** — the contract between
  [`framework/audit.py`](../../src/tailor/framework/audit.py)'s
  `AuditLog.record()` and every caller. Partially codified in
  [ADR 0001](0001-audit-log-as-backbone.md) as a column list; the
  Protocol declares the field set as a `TypedDict`-shaped contract
  binding caller and writer.
- **`_meta` block fields** — the dictionary stamped onto every
  successful tool result at
  [`framework/router.py:570-587`](../../src/tailor/framework/router.py).
  Partial codifications across v6.3.1 (`scrubber_warning`) and
  v6.5.0 (`hook_warnings`) live in code and a few tests. The
  Protocol names the required and optional keys.
- **`ChildMCP` abstract surface** — already an ABC at
  [`framework/interfaces.py`](../../src/tailor/framework/interfaces.py).
  The Protocol companion narrows the structural typing on `execute`,
  `estimate_cost`, `purge_cache`, and the property accessors so an
  external child shipping a wrong return shape fails type-check
  rather than fails at first dispatch.
- **Future seams** — when a new ADR introduces a load-bearing
  cross-component seam, that ADR declares whether the seam takes a
  Protocol in the same change, in the same shape
  [ADR 0014](0014-coverage-criticality-invariant.md) requires new
  ADRs to declare their criticality classification. The default for
  load-bearing seams is "yes."

Concrete mechanism:

- **`framework/protocols.py`** is a new module declaring the typed
  Protocols. Each Protocol is named after the seam it contracts:
  `PostExecuteHook`, `AuditRowFields`, `MetaBlockFields`,
  `ChildMCPSurface`. Each Protocol cites the ADR or ADRs that
  established the seam. The module is import-time-cheap (no runtime
  side effects) and the Protocols use `typing.Protocol` /
  `typing.TypedDict` so they impose no runtime cost on the call
  sites that already exist.
- **Type-checker as a CI gate.** `mypy` (or `pyright`, picked at
  implementation time on the basis of which produces fewer false
  positives on the existing codebase) runs as a `ci-gate-runner`
  step alongside pytest, ruff, and the security probe. The gate is
  scoped to the seams in the Protocols module — a strict-mode pass
  on `framework/protocols.py` and on every call site of every typed
  seam, and a permissive-mode pass on the rest of the framework.
  Strict-mode-everywhere is rejected on the same engineering-cost
  grounds [ADR 0014](0014-coverage-criticality-invariant.md) gave
  for not chasing 100% coverage on entry points: the value lives at
  the load-bearing seams, not at every line.
- **Failure mode.** A signature-drift change on a typed seam fails
  the type-checker at PR time. The contributor either updates both
  sides of the seam in the same change, or supersedes the Protocol
  via a new ADR — the same shape
  [ADR 0014](0014-coverage-criticality-invariant.md)'s map uses for
  taxonomy changes.
- **Composition with [ADR 0016](0016-mcp-protocol-auditor.md).** The
  `mcp-protocol-auditor` continues to catch what types cannot
  express: `default=str` coercion artifacts, markdown round-trip
  lossiness, schema-key omissions in JSON payloads, post-execute
  hook *behavioural* failures (a hook that runs without raising but
  fails to write the file). The Protocols catch what the auditor
  cannot reach without subprocess timing it does not budget for:
  internal-seam arity drift that fails inside a silent try/except
  before the wire response is built. The auditor's existing test
  suite at `tests/test_serve_*` gains one new assertion — *the
  canonical demo call returns an empty `_meta.hook_warnings`* —
  which is the test the v6.5.0 audit named was missing.

This ADR's promotion grounding cites
[ADR 0011](0011-promotion-policy.md). The structural argument is
named: typed seams defend the framework's load-bearing claims at the
addresses where those claims are encoded as code-level contracts
between components, and no existing mechanism defends them at
type-check time. The severity grounding is that a silent post-execute
hook regression breaks the reorientation tier's durability claim
([ADR 0001](0001-audit-log-as-backbone.md)) without an external
signal — exactly the severity-asymmetric case
[ADR 0011](0011-promotion-policy.md) named as a structural-argument
override of a frequency-based bar. The maintenance estimate is
bounded: a Protocol per seam, declared once, updated only when the
seam itself changes (which is by construction an ADR-shaped event).

## Consequences

**Positive.**

- Signature drift on load-bearing seams fails at PR time rather than
  at the demo, the release, or — worst case — in a real PI's session.
  The post-execute hook silent-catch failure mode that motivated this
  ADR becomes structurally impossible: a hook reshape that breaks the
  contract fails the type-checker before the silent try/except ever
  executes.
- The `_meta` block and audit row schema gain a single source of
  truth that downstream readers can bind against. v6.3.1's
  `scrubber_warning` add and v6.5.0's `hook_warnings` add both
  required updating multiple call sites and tests by inspection;
  with the Protocol in place, a new field is declared once and
  every call site is mechanically checked.
- The two-gate composition lines up cleanly. Types catch arity and
  field-set drift; the [ADR 0016](0016-mcp-protocol-auditor.md)
  protocol auditor catches behavioural and serialization drift. The
  failure modes are complementary; neither gate is asked to do the
  other's job. This matches the
  [ADR 0010](0010-adversarial-pairing.md) precedent that gates work
  best when scoped narrowly.
- Future ADRs that introduce a new load-bearing seam name their
  Protocol in the same change, mirroring
  [ADR 0014](0014-coverage-criticality-invariant.md)'s
  declares-its-own-criticality rule. The discipline against drift
  is the same discipline applied to a different invariant.
- External `ChildMCP` implementers (the framework's stated extension
  point) get a typed contract to bind against. A child shipped from
  outside this repository that violates the surface fails the
  contributor's type-check before it touches the framework's CI.

**Negative.**

- A type-checker is a new tool in the gate roster. mypy or pyright
  has its own configuration surface, its own version-pin discipline,
  and its own false-positive failure mode on edge cases (forward
  references, conditional imports, dynamic dispatch). The gate
  scope is narrowed to the Protocols module and its call sites
  precisely to bound this cost; strict-mode-everywhere is the
  cliff this ADR explicitly does not jump off.
- Protocols carry a small documentation-truthfulness burden. A
  Protocol that disagrees with the runtime shape of the seam it
  describes is worse than no Protocol — it lies in the type-checker's
  voice. Mitigated by the same enforcement
  [ADR 0014](0014-coverage-criticality-invariant.md) named for its
  criticality map: `code-vs-roadmap-drift-auditor` reads the
  Protocols module against the code on its existing cadence and
  flags drift.
- The migration is not free. Each existing seam gets its Protocol in
  one PR; the audit row schema in particular touches every call site
  of `AuditLog.record()`. The cost is paid once per seam and mostly
  in mechanical edits. Acceptable because the failure mode it
  addresses is silent regression on CRITICAL regions per
  [ADR 0014](0014-coverage-criticality-invariant.md).

**Neutral.**

- The runtime behaviour of the framework is unchanged. Protocols
  are pure typing constructs; they impose no runtime overhead, no
  import-time side effects, and no behavioural change on the
  dispatch path. A v6.5.x or v6.6.x release that ships this ADR
  changes only what a type-checker reports and what a contributor's
  PR-time experience looks like.
- The criticality map in
  [ADR 0014](0014-coverage-criticality-invariant.md) is unchanged.
  This ADR adds a new gate over existing critical regions; the
  regions themselves and their classifications stay where they are.
- The "Refuse on conflict with codebase ground truth" Tier-2 rule
  every specialist carries continues to apply.
  `ci-gate-runner` (which gains the type-check step) and
  `mcp-protocol-auditor` both refuse dispatch instructions asking
  them to suppress a Protocol violation or a wire-level finding to
  unblock a release; the refusal is architecturally grounded by
  this ADR plus [ADR 0016](0016-mcp-protocol-auditor.md).

Reversal condition: tightening this rule — for example, extending
strict-mode type-checking to the entire framework, or adding new
seams to the Protocols module on a non-ADR-driven basis — lives
behind a superseding ADR with a named scope and a migration plan.
Loosening the rule — removing a Protocol, weakening the type-check
gate, or relaxing the ADR-declares-its-own-Protocol rule for new
seams — also requires a superseding ADR. The Protocols module
cannot drift the rule; the rule lives here.

## Alternatives considered

**Amend [ADR 0016](0016-mcp-protocol-auditor.md) with the broader
scope rather than file a separate ADR.** The runtime-protocol-audit
ADR and this typed-Protocol ADR address the same class of bug from
two angles: 0016 from the wire, 0020 from the type system. An
amendment would consolidate the structural lesson into one record.
Two arguments against and one for: against, the failure modes the
two gates catch are non-overlapping (types catch internal-seam
arity drift inside silent try/except; the runtime auditor catches
behavioural and serialization drift on the wire), and an amended
0016 would carry two distinct mechanisms with two distinct
maintenance regimes under one heading, which is the shape that
makes ADRs hard to read months later. Also against, the precedent
the project has established
([ADR 0014](0014-coverage-criticality-invariant.md)'s criticality
map, [ADR 0011](0011-promotion-policy.md)'s promotion policy) is
that decisions which extend a prior ADR's structural lesson land as
new ADRs that cite the prior one rather than as amendments — the
Related-ADR header is the load-bearing link. For: a single record
is easier to onboard a future contributor onto than two
cross-referenced ones. **The boss reviews this with coffee and
picks; both shapes are defensible. The Decision section above
assumes the new-ADR shape. If the boss prefers the amendment, the
mechanical edit is to fold the Decision section's Protocol scope
into 0016's Decision and retire 0020.**

**Runtime assertions in tests — extend the
[ADR 0016](0016-mcp-protocol-auditor.md) protocol auditor's
existing shape with internal-seam arity assertions.** Rejected on
the structural argument the auditor's own ADR named: the runtime
gate fires per release on a real subprocess; arity drift on an
internal seam fails at *call time* during a tool dispatch that may
not be exercised on every release run. The auditor catches
behavioural drift it can observe on the wire; it cannot catch
arity drift on a hook that fails inside a try/except whose error
path is one of many wire-shape outcomes. A test suite that asserts
an empty `_meta.hook_warnings` on the canonical call closes the
specific instance, but every new internal seam re-creates the same
gap, and the project would carry a growing set of "assert this
specific empty list" tests as the framework's structural defence.
Type-check time is the right address.

**Docstring-only contracts — keep the status quo.** Rejected. The
status quo is the failure mode this ADR exists to address. The
post-execute hook's signature is documented in the
`register_post_execute_hook` docstring at
[`framework/router.py:146-153`](../../src/tailor/framework/router.py)
("Signature: hook(domain: str, tool_name: str, result: dict) ->
None") and a future SDK-style add to the framework's own contract —
e.g. passing a fourth `subject_id` argument to hooks for ADR 0009
propagation — would update the docstring without a mechanical check
that every registered hook supports the new arity. Docstrings are
documentation; types are enforced documentation. The class of bug
the v6.5.0 demo named is exactly the bug docstring-only contracts
do not catch.

**A typed registry layer between router and hook implementations
— intercept registration through a wrapper that adapts old hook
signatures to new ones.** Rejected on engineering-cost grounds. A
registry layer is the most defensive option (a hook reshape would
not break old hooks because the registry would adapt them) and
also the highest complexity. The framework currently registers
hooks at startup in `__main__.py`'s `cmd_serve()` and never
re-registers; the cost of an adaptation layer would buy resilience
against a problem the framework does not have. Typed Protocols at
the seam are the cheaper, less indirected fix for the actual
failure mode, and they fail loudly at type-check time rather than
silently adapting incompatible signatures (silent adaptation has
its own failure mode). The registry layer would be the right
choice for a framework whose hooks are registered dynamically by
external plugins; this is not that framework.

**Trust upstream library type stubs — rely on `mcp` SDK stubs to
catch SDK-boundary drift, do nothing for internal seams.** Rejected
because it solves only the boundary case [ADR 0016](0016-mcp-protocol-auditor.md)
already addressed via runtime audit, and does nothing for the
internal seams that motivate this ADR. The post-execute hook,
audit row schema, and `_meta` block are framework-internal seams
the `mcp` SDK does not type for the framework. SDK stubs are
useful where they exist (and where the project trusts the upstream
maintainer's discipline on minor-version stubs, which the v6.5.0
signature drift suggests is not always warranted) but they are
not the structural answer to the framework's own contracts.
