# ADR 0005: Pre-estimation, not post-billing, for cost gates

- **Status:** Accepted
- **Date:** 2026-04-13
- **Related:** [ADR 0001 (Audit log)](0001-audit-log-as-backbone.md)

## Context

The framework's Tier-3 tools can return tens of thousands of tokens of
raw biometric data (per-second HR, pace, GPS streams across a full
activity). Pushing that payload into an LLM's context window is
expensive and — more importantly — is typically not what the analyst
meant to ask for.

The cost gate exists to prevent accidental large transfers. The
design question is *when* to evaluate cost:

- **Post-billing:** run the tool, compute the token cost from the
  actual result, then decide whether to return it. Wastes the
  compute and I/O on rejected calls. For a Strava stream pull this
  means an HTTP round-trip and a deserialization pass for a call
  the user never wanted.
- **Pre-estimation:** compute a token estimate from metadata (point
  counts, declared activity duration, typical byte-per-point ratios)
  before executing the tool. Gate on the estimate. Reject before
  any real work happens.

Pre-estimation is only viable if the estimate is close enough to the
truth that users can trust it. Over-estimating is fine (conservative,
occasional false positives). Under-estimating is a problem (the gate
lets through payloads larger than the declared threshold).

## Decision

`CostGate` calls the child's `estimate_cost()` method **before**
execution, using stream metadata only (point counts, sample rates,
declared durations). Never the full payload.

- Each child implements `estimate_cost(tool_name, params) -> CostEstimate`.
- The estimate returns a token count and optional explanatory detail
  for the LLM instruction.
- If the estimate exceeds the Tier-3 threshold (currently 35,000
  tokens), the router returns a `COST_APPROVAL_REQUIRED`
  `LLMInstruction` and **does not execute the tool**. The call is
  audited with `outcome = COST_APPROVAL_REQUIRED`.
- If `estimate_cost()` itself raises, the router **fails closed**:
  the call is rejected and audited as `COST_ESTIMATE_ERROR` (public
  dispatch) or `COST_ESTIMATE_ERROR_INTERNAL` (internal dispatch).
  This was a bug fix in the codebase-review pass — previously a
  broken estimator fell back to `CostEstimate(tokens=0)` and
  silently bypassed the gate.

## Consequences

**Positive.**

- Zero wasted compute or network I/O on rejected high-token calls.
- The cost gate is deterministic — rejected calls are rejected the
  same way every time for the same parameters.
- Estimator failures cannot silently turn the gate into a no-op.
  The audit log captures them explicitly.
- Children that evolve their data shape update the estimator in
  lockstep; a drift between estimator and reality shows up as
  calls that unexpectedly succeed or fail around the threshold,
  not as a governance bypass.

**Negative.**

- Children now have two code paths per Tier-3 tool: execute and
  estimate. Both must stay in sync. Mitigation: tests assert
  estimate/actual within a tolerance for representative payloads.
- Conservative estimates cause some false-positive rejections.
  Acceptable — the gate is explicitly approve-to-proceed, not
  deny-by-default.
- Brand-new Tier-3 tools without an estimator need one written
  before they ship. This is a deliberate friction.

**Neutral.**

- The 35,000-token threshold is tuning, not architecture. It can
  change without an ADR amendment.

## Alternatives considered

- **Post-billing with immediate discard on overage.** Rejected —
  wastes work on rejected calls and makes the gate a best-effort
  check rather than a hard pre-condition.
- **Static per-tool token budgets declared in `ToolDefinition`.**
  Rejected — too coarse. A Strava stream pull's cost varies by an
  order of magnitude depending on activity duration. The estimator
  is the right place for that variance.
- **Fallback to `CostEstimate(tokens=0)` on estimator failure.**
  This was the original behavior. Rejected after the codebase review
  — a broken estimator turning into a governance-bypass is exactly
  the class of silent failure the audit log is supposed to prevent.
