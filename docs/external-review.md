# External code review — primer for the reviewer

You've been asked to review **Biosensor MCP**, a local-first MCP server
for LLM-assisted analysis of biometric data in health research. This
document gets you oriented and tells you specifically what we want
skeptical eyes on.

If you're the maintainer reading this to brief a reviewer: hand them
this file (or a link to it) and nothing else.

---

## The 30-second pitch

Researchers with high-frequency biometric data (running streams, force
traces, EMG envelopes, CGM, etc.) face a dilemma:

- Hosted LLMs are convenient but inappropriate for participant
  biometric data.
- Local processing is appropriate but loses the analytical leverage
  hosted LLMs provide.
- Pasting summaries by hand loses provenance and makes IRB conversations
  hard.

This project threads that needle: a router that runs next to the data,
a tiered access model where most analytical questions resolve at
Tier 1 (server-computed summaries, no streams crossing the boundary),
explicit consent and cost gates for higher tiers, and a durable audit
log every call lands in.

It's built by a non-technical owner working with Claude Code. That's
relevant context: the codebase is well-instrumented but **has not been
peer-reviewed by a human RSE**. Your job is to be the missing peer
reviewer.

---

## What we're asking from you, in priority order

1. **Find what our internal agent roster cannot.** Our `.claude/agents/`
   directory has ~18 specialist subagents. They do excellent work within
   Claude's training distribution. They share the model's blind spots.
   We want you to find issues that don't surface from re-reading
   alone — class-of-failure issues, design assumptions that won't survive
   first contact with reality, things only a human who's worked at an
   academic medical center would notice.

2. **Tell us where prose-claims diverge from code.** Many of our
   load-bearing claims are ADRs (decisions captured in markdown under
   `docs/adr/`). If a claim ("every tool call lands in the audit log",
   "the PHI scrubber is no-op by default but loud about it", "Tier-1
   processing is deterministic") fails to match what the code does,
   that's the highest-yield finding you can produce.

3. **Render a gut-feel verdict on the IRB claim.** We claim this
   codebase is the right backbone for an IRB-approvable research
   workflow. We've never tested that against a real IRB submission.
   If you've worked at an AMC, your instinct is more valuable than any
   automated audit we can run.

---

## How to spend your time

Three time budgets. Pick the one that matches your availability.

### 30 minutes — orientation only

1. [`README.md`](../README.md) (5 min) — audience-segmented overview.
2. [`CLAUDE.md`](../CLAUDE.md) (10 min) — definitive system description,
   maintained in lockstep with code.
3. [ADR 0001](adr/0001-audit-log-as-backbone.md),
   [ADR 0003](adr/0003-phi-scrubber-seam.md),
   [ADR 0008](adr/0008-deterministic-by-construction-processing.md)
   (15 min) — the three load-bearing decisions.

After 30 min you should be able to say in your own words: *what this
project is, what its load-bearing claims are, what its authors are
worried about.*

### 2 hours — substantive review

Add to the above:

- [`src/biosensor_mcp/framework/router.py`](../src/biosensor_mcp/framework/router.py) —
  the security pipeline (`validate → circuit break → consent → cost →
  execute → scrub → audit`).
- [`src/biosensor_mcp/framework/security.py`](../src/biosensor_mcp/framework/security.py) —
  gate primitives (`ParamValidator`, `CircuitBreaker`, `ConsentGate`,
  `PHIScrubber`).
- [`src/biosensor_mcp/framework/audit.py`](../src/biosensor_mcp/framework/audit.py) —
  the audit-log shape, JSON serialization seam.
- [ADR 0009 — subject_id integrity](adr/0009-vault-subject-keying.md),
  [ADR 0010 — adversarial pairing](adr/0010-adversarial-pairing.md),
  [ADR 0012 — vault PHI bypass](adr/0012-vault-phi-scrubber-bypass.md),
  [ADR 0013 — cache purge on consent revocation](adr/0013-cache-only-purge-on-consent-revocation.md).
- One ChildMCP implementation —
  [`src/biosensor_mcp/children/csv_dir/child.py`](../src/biosensor_mcp/children/csv_dir/child.py)
  is the most representative.

This is where the highest concentration of decision-shaped logic lives,
and where dissent has the highest expected value.

### Weekend — full audit

Add:

- [`src/biosensor_mcp/framework/vault/`](../src/biosensor_mcp/framework/vault/) —
  durable analytical memory (writer, layer, renderer, parser).
- [`src/biosensor_mcp/framework/local_llm/`](../src/biosensor_mcp/framework/local_llm/) —
  opt-in local-LLM guardian. See
  [ADR 0022](adr/0022-local-llm-guardian.md) and
  [ADR 0023](adr/0023-local-llm-cooperation-loop.md).
- The full ADR set under [`docs/adr/`](adr/).
- One overnight report under [`docs/reports/`](reports/) to see how
  autonomous-session work is triaged.

---

## Known issues we already track

Don't spend time noting these — they're already in our backlog or
explicitly accepted by an ADR:

- **Test-coverage gaps in CRITICAL/HIGH regions** are enforced by the
  `coverage-criticality-mapper` agent
  ([ADR 0014](adr/0014-coverage-criticality-invariant.md)), not by a
  hard percentage threshold. New gaps surface, we close them next
  release.
- **No real PHI scrubber implementation** — the seam is no-op by design
  ([ADR 0003](adr/0003-phi-scrubber-seam.md)). Institutional subclasses
  are an integration concern, not a framework gap.
- **Vault tools bypass the PHI-scrubber seam** — by design, codified as
  [ADR 0012](adr/0012-vault-phi-scrubber-bypass.md). If you disagree
  with that *decision* specifically, that's a high-value disagreement.
- **Single-account-per-domain assumption** in the consent gate / cache
  purge logic
  ([ADR 0013 § Negative consequences](adr/0013-cache-only-purge-on-consent-revocation.md)).
  A multi-participant deployment sharing one Strava account would need
  subject-scoped purge.
- **GitHub Actions CI is currently disabled** on this repository.
  Local gates run on every release via `ci-gate-runner`.

---

## Where we'd love you to look hard

Six places where we suspect blind spots:

1. **The `_meta` provenance stamp.** Every result is supposed to carry
   one. Could you find a code path where a tool result reaches the LLM
   *without* a `_meta` block? See `framework/router.py`.
2. **ADR 0008 deterministic-by-construction claim.** We assert no PRNG,
   no clock reads, no hidden state in any `processing.py` module. The
   `reproducibility-provenance-auditor` agent enforces this, but the
   agent is also Claude. Is there a determinism leak we'd structurally
   miss?
3. **ADR 0001 audit-log completeness.** We claim every call lands in
   the audit log. Is there a return path where the LLM gets a result
   but the audit row doesn't get written?
4. **Consent withdrawal semantics.** ADR 0013 added cache-only purge
   on revocation. If a subject asks to be removed from a study
   mid-cohort, does the abstraction actually handle it, or do we
   discover a gap?
5. **The vault → LLM surface.** ADR 0012 codifies that vault content
   bypasses the PHI scrubber on the argument that the analyst's notes
   aren't participant biometric data. Is that argument airtight, or
   could biometric data sneak into vault content via analyst typing
   patterns?
6. **The local-LLM guardian end-to-end claim.** ADR 0022 + 0023. We
   claim "no biometric streams leave the analyst's machine when the
   local-LLM is opted in." Is that claim correct end-to-end?

These are the questions where, if you find something, the finding
matters most.

---

## How to leave feedback

Three channels, choose whichever fits your style.

- **GitHub issue** — open one with a `[REVIEW]` prefix at
  https://github.com/saahasmuthineni/Biosensor-to-LLM-Connector/issues.
  Best for discrete findings.
- **Pull request** — branch from `main`, propose specific changes;
  we'll merge or discuss.
- **Email or written note** — direct to the maintainer; we'll triage
  and file an issue ourselves or respond directly.

Severity tiers we use internally (mirror them if useful):

- **VIOLATION** — a load-bearing claim is false.
- **WATCH** — the claim holds today but the abstraction is fragile.
- **NO RISK** — claim holds, no concern.

**A "NO OBJECTION FOUND" verdict is also valuable.** It's the explicit
statement that you looked and didn't find anything, which is
information we can't otherwise distinguish from "didn't actually look."
Cite which files and ADRs you reviewed.

---

## Acknowledgment

If you'd like, your review will be acknowledged in `CLAUDE.md` and in
the relevant ADRs. If a finding leads to a substantive change, the
commit message and PR will credit you. If your review changes a
load-bearing decision, you'll be cited in the resulting ADR's
"Reviewers" section.

If you'd prefer the review remain anonymous, that's also fine — we'll
record the change without the citation.

---

## A note on this project's working style

This codebase is built by a non-technical owner ("the boss")
collaborating with Claude Code. The 18-specialist agent roster you'll
see in `.claude/agents/` is internal infrastructure, not an external
team. Every one of those agents is LLM-mediated. They share Claude's
priors — which is *exactly* why your role exists.

If you find yourself thinking "an LLM would never catch this," you've
found the highest-value class of finding. Send it our way.
