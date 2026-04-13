# ADR 0004: Structured `LLMInstruction` over freeform strings

- **Status:** Accepted
- **Date:** 2026-04-13

## Context

The router returns machine-readable prompts to the LLM client at two
points in the pipeline: when the consent gate needs a user to
approve access to biometric data, and when the cost gate needs
approval for a high-token Tier-3 call.

The default pattern in many MCP servers is to return a free-text
string describing the situation. That works for the LLM in the
moment — Claude, GPT, and similar models reliably comply with prose
instructions — but it fails as an auditable compliance record:

- A reviewer reading an audit row or a transcript cannot
  mechanically check "did the consent prompt state the data types?"
  without parsing prose.
- Individual must-do / must-not-do conditions are easy to miss in a
  paragraph.
- Ambiguous replies ("yes, but summarize it first") have no
  pre-declared resolution — the LLM makes something up.
- Different LLM clients will phrase or truncate prose differently,
  so the ground-truth record varies by client.

For a framework whose whole point is client-agnostic governance, the
instruction shape needs to be the same regardless of who's reading
it, and it needs to be checkable without NLP.

## Decision

The router returns instructions to the LLM as a structured
`LLMInstruction` JSON object with individually addressable fields:

- `must_do` — list of explicit things the LLM is required to do
  before proceeding (e.g. show the user the consent prompt, wait
  for reply).
- `must_not_do` — list of explicit prohibitions (e.g. do not invoke
  the tool again until consent is granted).
- `on_ambiguous_reply` — pre-declared resolution for unclear user
  responses (typically: re-ask, treat as denial).
- Additional fields per gate type (`data_types` on consent, token
  estimate on cost, etc.) carrying the data the LLM needs to render
  the prompt correctly.

Consent and cost gates both return this shape. Compliance checks can
inspect the fields directly instead of pattern-matching prose.

## Consequences

**Positive.**

- Auditable: "did the consent prompt include `data_types`?" is a
  `key in instruction` check, not a regex.
- Client-agnostic: every MCP client sees the same structured
  instruction. Renderers differ, but the ground truth is identical.
- Evaluation-harness-ready: the planned LLM-client evaluation
  harness (ROADMAP.md) can assert compliance per field rather than
  per phrase.
- Future gate types (e.g. an IRB-approval gate) slot in with the
  same shape.

**Negative.**

- LLM clients need to understand the structure. This is fine for
  Claude Desktop and typical MCP clients, but a bespoke client
  that returns the JSON verbatim to the user is worse UX than a
  prose string. Mitigation: the `must_do` entries include
  human-readable text that a naive client can render.
- Schema evolution requires care — adding a required field breaks
  any client that validates strictly. New fields should be optional
  with sensible defaults.

**Neutral.**

- Audit rows record the `outcome` (`CONSENT_REQUIRED`,
  `COST_APPROVAL_REQUIRED`) but not the full instruction. If
  per-field recall is needed, the instruction can be reconstructed
  from `domain` + `tool` + `tier` + configured policy — it's
  deterministic.

## Alternatives considered

- **Free-text prompts.** Rejected for the reasons above.
- **Structured prompt with a single `instructions` markdown string
  inside.** Rejected — still leaves the fields un-auditable; the
  structure is cosmetic.
- **Per-client adapter that translates to prose client-side.**
  Rejected as premature. If an MCP client needs prose, it can
  render `must_do` as a bulleted list itself.
