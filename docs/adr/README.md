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

## Template

Copy [0000-template.md](0000-template.md) when proposing a new
architectural decision. Number sequentially; do not reuse numbers
even if a prior ADR is superseded — mark the old one `Superseded by
NNNN` instead.
