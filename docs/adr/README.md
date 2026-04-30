# Architecture Decision Records

Short, numbered records for the architectural decisions that shape how
this framework behaves — especially the ones that a reviewer (a PI, an
IRB, an RSE inheriting the codebase) would want to understand *why*,
not just *what*.

An ADR captures:

1. **Context** — the problem or constraint the decision addresses.
2. **Decision** — what was chosen.
3. **Consequences** — what follows, positive and negative.
4. **Status** — accepted / superseded / deprecated.

Domain-specific numeric choices (e.g. the 0.5 m/s stop threshold, the
30-second spike-detection cooldown) are *not* ADRs — they live as
"Implementation notes" in [CLAUDE.md](../../CLAUDE.md) because they're
tuning parameters, not architectural stances.

## Index

| # | Title | Status |
|---|---|---|
| [0001](0001-audit-log-as-backbone.md) | Audit log is the backbone | Accepted |
| [0002](0002-subject-id-scoping.md) | `subject_id` as first-class audit column, optional on calls | Accepted |
| [0003](0003-phi-scrubber-seam.md) | PHI scrubbing is a seam, not a policy | Accepted |
| [0004](0004-structured-llm-instruction.md) | Structured `LLMInstruction` over freeform strings | Accepted |
| [0005](0005-cost-pre-estimation.md) | Pre-estimation, not post-billing, for cost gates | Accepted |
| [0006](0006-vault-overhaul-v6.md) | Vault overhaul (v6) — longitudinal research tool | Accepted |
| [0007](0007-rendering-layers-policy.md) | Rendering layers — source-of-truth markdown is plain; plugin views are additive | Accepted |
| [0008](0008-deterministic-by-construction-processing.md) | Analytical processing is deterministic by construction | Accepted |
| [0009](0009-vault-subject-keying.md) | Vault subject-keying — optional frontmatter, set-once, cross-subject preserved | Accepted |
| [0010](0010-adversarial-pairing.md) | Adversarial pairing — dissent is a seam, not a hope | Accepted |
| [0011](0011-promotion-policy.md) | Specialist promotion is governed by structural argument and severity | Accepted |
| [0012](0012-vault-phi-scrubber-bypass.md) | Vault dispatch bypasses the PHI-scrubber seam | Accepted |
| [0013](0013-cache-only-purge-on-consent-revocation.md) | Cache-only purge on consent revocation — mandatory, synchronous, fail-closed | Accepted |
| [0014](0014-coverage-criticality-invariant.md) | Coverage criticality is an invariant — newly-uncovered CRITICAL/HIGH code is a regression | Accepted |

### IRB-relevant decisions

ADRs that govern data-flow, consent, audit, and re-identification semantics
— the load-bearing reading list for an IRB committee or compliance reviewer:

- [0001](0001-audit-log-as-backbone.md) — what gets logged on every call
- [0003](0003-phi-scrubber-seam.md) — the no-op default and the institutional override seam
- [0009](0009-vault-subject-keying.md) — `subject_id` integrity and the set-once invariant
- [0013](0013-cache-only-purge-on-consent-revocation.md) — what happens to cached data when consent is revoked

## Template

Copy [0000-template.md](0000-template.md) when proposing a new
architectural decision. Number sequentially; do not reuse numbers
even if a prior ADR is superseded — mark the old one `Superseded by
NNNN` instead.
