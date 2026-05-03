# ADR 0023: Local-LLM layer as substrate-vision contributor in a cooperation loop

- **Status:** Proposed
- **Date:** 2026-05-03
- **Related:** [ADR 0001 (Audit log is the backbone)](0001-audit-log-as-backbone.md), [ADR 0008 (Deterministic by construction)](0008-deterministic-by-construction-processing.md), [ADR 0009 (Vault subject-keying)](0009-vault-subject-keying.md), [ADR 0011 (Promotion policy)](0011-promotion-policy.md), [ADR 0012 (Vault PHI-scrubber bypass)](0012-vault-phi-scrubber-bypass.md), [ADR 0022 (Local-LLM guardian)](0022-local-llm-guardian.md), [CLAUDE.md § Architecture](../../CLAUDE.md#architecture)

## Context

[ADR 0022](0022-local-llm-guardian.md) established the local-LLM
guardian: numbers come from `processing.py`, prose comes from the local
LLM, and the `OracleResponse` contract enforces the boundary. The shape
that shipped under ADR 0022 is *purely reactive*. Hosted Claude calls
`ask_local_oracle` with a question and a resolved processing-call
result; the local LLM returns `numerical_claims + narrative +
ambiguity_axes + confidence + _meta`; hosted Claude integrates the
response and moves on. There is no loop. There is no second pass.
Nothing the local layer contributes back is information hosted Claude
did not already pre-fetch into the call.

This collapses the architectural argument for *why both layers exist*.
The local layer's only published value-add under the v0 contract is "a
smaller model that won't fabricate" — which is real, but does not
justify a separate framework-tier component parallel to `VaultLayer`.
A purely reactive composer over a resolved result is an implementation
detail of the hosted LLM's prompting strategy, not a load-bearing seam.

The load-bearing argument that *does* justify the separate component:
**the local layer can read the vault deterministically; hosted Claude
structurally cannot.** Vault content — themes, moments, failure-modes,
evidence blocks — lives on the analyst's machine and is keyed by
subject under [ADR 0009](0009-vault-subject-keying.md). Hosted Claude
sees only what is pre-fetched into a tool call. The local layer, by
contrast, runs in the same process as `VaultStorage` and can scan the
vault as part of every oracle call. This **substrate-vision asymmetry**
is the unique value the local layer is positioned to deliver — and
ADR 0022's v0 contract realises none of it.

ADR 0022 is `Status: Proposed` and amendment in place is cheap, but the
substrate-vision argument is genuinely new — ADR 0022 motivates the
local layer on fabrication-bounding and framing-claim strengthening
and does not name the asymmetry. Burying a new load-bearing argument
inside the existing ADR makes future readers miss it.

The question this ADR answers: *what is the smallest extension to the
ADR 0022 contract that makes the substrate-vision asymmetry mechanical
in the running code, and turns the one-shot oracle dump into a
cooperation loop hosted Claude can iterate against?*

## Decision

`OracleResponse` gains three fields, each with a sharp role, and the
`LocalLLMLayer` gains a deterministic vault-scan step the backend does
not own. The contract is additive — every existing `ask_local_oracle`
caller continues to work; new fields default to `[]`.

The rule, plain English: *the local layer reads the vault on every
oracle call; the local LLM names what hosted Claude should fetch next
and what it should ask the analyst; hosted Claude iterates.* The
asymmetry that justifies the separate framework-tier component is no
longer an argument in an ADR — it is a field hosted Claude reads on
every response.

The three new fields:

- **`related_substrate: list[dict]`** — populated deterministically in
  `LocalLLMLayer.execute()` after the backend returns. Surfaces
  themes, moments, and failure-modes referencing the subject(s) in
  scope that hosted Claude did not pre-fetch. Each entry carries
  `{"kind", "slug", "title", "subject_id", "status", "last_updated"}`.
  Capped at 20 entries; sorted `last_updated` descending. The backend
  is not consulted; this is a SQLite query over `VaultStorage`.
- **`next_best_calls: list[str]`** — LLM-generated. Specific Tier-1
  tool calls hosted Claude can make to raise oracle confidence on the
  current question, then re-invoke `ask_local_oracle` with expanded
  `resolved_context`. The local LLM names tools by their canonical
  framework names (e.g. `csv_force_decline`, `strava_run_report`).
- **`unresolved_intent: list[str]`** — LLM-generated. Questions hosted
  Claude should put to the analyst before the oracle can compose
  confidently. The split from `next_best_calls` is the load-bearing
  distinction: *fetch-this-data* belongs in `next_best_calls`,
  *ask-the-analyst* belongs in `unresolved_intent`. Hosted Claude
  reads which list a suggestion lives on and routes accordingly.

A fourth candidate field, `unresolved_substrate`, was considered and
dropped during planning. It overlapped with `next_best_calls` —
the framework's Tier-1 surface is small enough (~45 tools) that a
Guardian-tier model can map *missing data* to *tool name* inline. Three
sharp roles is better than four with one blurry overlap.

### Architectural placement

`related_substrate` is populated in `LocalLLMLayer.execute()`, after
`backend.compose(request)` returns. It is **not** the backend's
responsibility:

- The vault scan is deterministic; the backend boundary is for
  non-deterministic LLM composition. Putting the scan in the layer
  keeps [ADR 0008](0008-deterministic-by-construction-processing.md)'s
  determinism boundary clean — the backend remains the only
  non-deterministic surface and the scan does not need to be permitted.
- Every backend (current `NullBackend`, current `OllamaBackend`,
  future tier backends) inherits substrate vision automatically. The
  vault-scan code does not duplicate per backend.
- `NullBackend` gains substrate vision the moment vault wiring lands,
  with zero backend changes. The substrate-vision asymmetry is
  demonstrated mechanically by the no-op default — the layer surfaces
  vault content without any LLM in the loop.

The `LocalLLMLayer` constructor at
[`framework/local_llm/layer.py:50`](../../src/biosensor_mcp/framework/local_llm/layer.py)
gains an optional `vault_storage` parameter. When `None`, the
substrate scan is a defensive no-op returning `[]`; existing tests
that construct the layer without vault wiring continue to pass.
Wiring at `__main__.py` injects `vault_writer.storage` (a new public
property on `VaultWriter` exposing the `_storage` field currently
private at [`framework/vault/writer.py:96`](../../src/biosensor_mcp/framework/vault/writer.py)).

The substrate scan inherits the IS-NULL-or-match filter semantics
[ADR 0009](0009-vault-subject-keying.md) defines for vault queries:
when `subject_id` is provided, rows where `subject_id = ?` OR
`subject_id IS NULL` are returned. Cross-subject themes and v6.1-era
legacy notes remain visible to the substrate scan exactly as they
remain visible to `vault_search_notes`.

Vault content surfacing into the hosted-LLM-bound payload inherits
[ADR 0012](0012-vault-phi-scrubber-bypass.md)'s scrubber-bypass
decision rather than introducing a new flow. The `related_substrate`
entries are metadata fields — slug, title, status, subject_id,
timestamps — not raw biosensor stream content. The ADR 0012 invariant
holds.

### Audit-log column

A new `oracle_substrate_count INTEGER` column lands on `audit_log`,
matching the migration shape ADR 0022 already uses for the
`oracle_latency_ms` column at
[`framework/audit.py:192-198`](../../src/biosensor_mcp/framework/audit.py).
The column records, per oracle call, how many vault items were
surfaced into the hosted-LLM-bound payload. Without this column, the
audit log cannot answer *how much vault content did this oracle call
expose to the hosted LLM?* — an IRB-grade provenance question the new
flow makes load-bearing. The column extends the audit-log backbone
[ADR 0001](0001-audit-log-as-backbone.md) on the same row category
ADR 0022 introduced; no new row shape.

### Landing shape

This ADR governs two PRs, each independently revertible.

- **PR1 — deterministic substrate scan only.** Lands
  `related_substrate`, the layer-side scan helper, the
  `vault_storage` injection, the `oracle_substrate_count` audit
  column, and the `VaultWriter.storage` public property. `NullBackend`
  is untouched. Verifiable in a vault-fixture demo: a vault with one
  theme keyed to P003 is opened by the framework, an oracle call
  scoped to P003 is issued, and the response surfaces the theme in
  `related_substrate` with no LLM involvement.
- **PR2 — LLM-driven gap reasoning.** Lands `next_best_calls` and
  `unresolved_intent` via prompt extension on `OllamaBackend`, with
  defensive list-coercion matching the `ambiguity_axes` parser
  pattern at
  [`framework/local_llm/backends/ollama.py:173-185`](../../src/biosensor_mcp/framework/local_llm/backends/ollama.py).
  Verifiable only in judgment terms — does the prompt produce useful
  suggestions? — which is why it lands separately from PR1.

PR1 is mechanical and stands on its own merit. PR2 is
prompt-engineering-effectiveness-dependent and lands when prompt
quality can be measured against real session traces. Bundling them
would entangle a clean revert path with an experiment.

### Reversal conditions

- If real sessions show no iteration uptake on `next_best_calls` or
  `unresolved_intent` after a sustained pilot, the PR2 fields are
  removable without disturbing PR1. The deterministic substrate scan
  stands on its own merit and is the load-bearing claim of this ADR.
- If the substrate scan adds latency that other gates cannot
  accommodate, the field becomes opt-in via a configuration flag
  rather than removed. The asymmetry argument does not weaken; the
  enforcement shape adapts.

## Consequences

**Positive.**

- The substrate-vision asymmetry is realised by feature, not by
  argument. The case for two layers (local and hosted) becomes
  load-bearing in the running code rather than only in the ADR.
- Hosted Claude gains visibility into vault substrate it would
  otherwise have to remember to pre-fetch by slug. This closes a real
  session-continuity gap for analysts: a theme captured in week 2 is
  surfaced into a week-5 oracle call automatically when scoped to the
  same subject, without the analyst restating the theme.
- `NullBackend` inherits substrate vision for free. The layer-vs-
  backend split is demonstrated mechanically — a deployment running
  without any local LLM still gets vault substrate surfaced into
  oracle responses, which is the cleanest possible proof that the
  scan belongs to the layer and not to the backend.
- The contract is additive. Every existing `ask_local_oracle` caller
  continues to work; new fields default to `[]`. No SemVer break.
- The IRB story tightens. `oracle_substrate_count` makes "what got
  surfaced into the hosted LLM" auditable per call, on the same row
  category that already records model identity, prompt hash, and
  latency. A reviewer reconstructing what the hosted LLM saw on an
  oracle call reads two columns, not one.

**Negative.**

- The `ask_local_oracle` tool description grows from approximately
  1,500 to 2,500 tokens to teach hosted Claude to act on the new
  fields. Without acting on them, the fields are inert noise on the
  wire. Whether hosted Claude actually iterates on `next_best_calls`
  and `unresolved_intent` is a prompt-engineering question this ADR
  does not answer; the contract is in place but its effectiveness is
  unmeasured until real sessions land.
- The substrate scan adds latency to every oracle call. Mitigated by
  the cached SQLite index and the 20-entry cap, but the cost is
  non-zero and grows with vault size. A pathological vault (10,000+
  notes) on a slow disk could surface latency the layer's existing
  consumers do not budget for.
- `VaultWriter.storage` becomes part of the public framework
  interface. Future refactors of the vault writer must preserve the
  property or migrate the local-LLM layer to a different injection
  shape. The constraint is mild but real.
- The asymmetry between PR1 (mechanical, verifiable) and PR2
  (judgment-dependent, prompt-engineering) means the ADR ships its
  load-bearing claim with PR1 and its experimental claim with PR2.
  A reviewer reading the ADR after PR1 lands but before PR2 sees a
  contract surface larger than the implementation; the staging is
  intentional but the asymmetry is a real cost.

**Neutral.**

- ADR 0022's framing-claim — *no biometric streams leave the
  analyst's machine, ever, at any tier — including to hosted LLMs* —
  is unchanged. The substrate scan surfaces metadata about analyst-
  authored vault content, not biometric streams. The opt-in posture
  ADR 0022 ships with continues to govern.
- ADR 0008's determinism boundary is unchanged. The substrate scan
  is deterministic by construction; the backend remains the only
  non-deterministic surface in the local-LLM layer. The clock-read
  permit-list ADR 0022 already amended to name `local_llm/` covers
  the new code regions without further amendment.
- ADR 0009's set-once subject-keying invariant is unchanged. The
  substrate scan reads `subject_id` from frontmatter via
  `VaultStorage` and applies the IS-NULL-or-match filter; it does
  not write to the vault and cannot reassign a theme's subject.
- ADR 0012's vault-PHI-scrubber-bypass invariant is unchanged. The
  substrate scan returns metadata, not raw biometric streams; the
  invariant ADR 0012 names (vault inputs are not raw streams) covers
  this flow without amendment.
- ADR 0011's promotion policy frames how new specialists land; this
  ADR is a contract extension, not a new specialist, and lands via
  the structural-argument path the project has used since v6.3.0
  for ADR-grade code changes.

## Alternatives considered

**Substrate scan in the backend instead of the layer.** Rejected.
Every backend would reimplement the vault scan, including the
`NullBackend`, which would have to either skip substrate vision
(weakening the asymmetry argument the ADR rests on) or import vault
wiring it has no other reason to know about. Layer-side placement
keeps the determinism boundary clean and lets the no-op backend
inherit substrate vision for free — the cleanest possible proof that
the scan belongs to the layer.

**Four fields including `unresolved_substrate`.** Considered and
dropped during planning. The fourth field overlapped with
`next_best_calls`: the framework's Tier-1 surface is small enough
that any Guardian-tier model can map *missing data* to *tool name*
inline. Three fields with sharp roles is a tighter contract than
four with one blurry pair, and the contract surface hosted Claude
must learn is correspondingly smaller.

**Single PR landing all fields.** Rejected. PR1 (substrate scan) is
mechanically verifiable in a vault-fixture demo; PR2 (LLM-generated
gap reasoning) is judgment-dependent and lands when prompt
effectiveness can be measured. Bundling them entangles a clean
revert path with a prompt-engineering experiment. The two-PR shape
mirrors the ADR 0022 pattern of staging the contract before the
adoption — landing the seam before the migration.

**Separate "conferral vault" for LLM-to-LLM cooperation history.**
Considered and rejected as a separate decision. A new vault tier
dedicated to oracle-session history would split substrate, fragment
wikilinks, and not survive the existing `kind` segmentation argument
that ADRs 0006 and 0009 already lean on. The smaller pragmatic
version — a new `kind: oracle_session` written via post-execute hook
into the existing vault — is filed as deferred work, with the
promotion trigger *"real cooperation sessions show 3+-call iteration
patterns and IRB asks where the trail is."* The audit log carries
the necessary provenance in the meantime.

**Amend ADR 0022 in place rather than file ADR 0023.** Considered
seriously. ADR 0022 is `Status: Proposed`, so amendment is cheap.
Rejected because the substrate-vision-asymmetry argument is
genuinely new — ADR 0022 motivates the local layer on
fabrication-bounding and framing-claim strengthening, and does
*not* name the asymmetry. Burying a new load-bearing argument inside
an existing ADR makes future readers miss it. The
[ADR 0009](0009-vault-subject-keying.md) precedent applies: ADR 0002
deferred the vault-subject-keying question, and ADR 0009 filled the
slot as a separate decision rather than a retroactive amendment.
ADR 0023 follows the same shape — a discrete, citable record of the
cooperation-loop pattern as a load-bearing extension of ADR 0022.

**Verifier hook on vault-write to scan analyst-authored notes for
accidental PHI.** Out of scope. Different placement (write-time, not
read-time), different ADR territory. Filed as deferred and named
here so a reader looking for the verifier shape finds the deferral
record rather than re-relitigating it.

**`verify_against_substrate` / `challenge_my_claim` tool for
substrate-consistency checks on hosted Claude's draft synthesis.**
Out of scope. Different trust axis (substrate-consistency check on a
draft, not composition over numbers) and a separate tool surface.
Filed as deferred; named here for the same reason as the verifier
hook.
