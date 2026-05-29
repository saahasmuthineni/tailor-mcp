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
| [0002](0002-subject-id-scoping.md) | `entity_id` as first-class audit column, optional on calls | Accepted |
| [0003](0003-phi-scrubber-seam.md) | Data scrubbing is a seam, not a policy | Accepted |
| [0004](0004-structured-llm-instruction.md) | Structured `LLMInstruction` over freeform strings | Accepted |
| [0005](0005-cost-pre-estimation.md) | Pre-estimation, not post-billing, for cost gates | Accepted |
| [0006](0006-vault-overhaul-v6.md) | Vault Overhaul (v6) — longitudinal research tool | Accepted |
| [0007](0007-rendering-layers-policy.md) | Rendering layers — source-of-truth markdown is plain; plugin views are additive | Accepted |
| [0008](0008-deterministic-by-construction-processing.md) | Analytical processing is deterministic by construction | Accepted |
| [0009](0009-vault-subject-keying.md) | Vault entity-keying — optional frontmatter, set-once, cross-entity preserved | Accepted |
| [0010](0010-adversarial-pairing.md) | Adversarial pairing — dissent is a seam, not a hope | Accepted |
| [0011](0011-promotion-policy.md) | Specialist promotion is governed by structural argument and severity, not frequency alone | Accepted |
| [0012](0012-vault-phi-scrubber-bypass.md) | Framework-tier dispatch bypasses the PHI-scrubber seam | Accepted |
| [0013](0013-cache-only-purge-on-consent-revocation.md) | Cache-only purge on consent revocation — mandatory, synchronous, fail-closed | Accepted |
| [0014](0014-coverage-criticality-invariant.md) | Coverage criticality is an invariant — newly-uncovered CRITICAL or HIGH code is a regression | Accepted |
| [0015](0015-tier-1-cohort-surface-and-metadata-sidecar.md) | Tier-1 cohort aggregation is a first-class surface; group identity travels via a metadata sidecar | Accepted |
| [0016](0016-mcp-protocol-auditor.md) | MCP-protocol auditor — wire-level correctness is a seam, not a hope | Accepted |
| [0017](0017-adr-weigher-and-autonomous-session-cap.md) | ADR weigher gates premature-ADR drift in autonomous sessions | Accepted |
| [0018](0018-cross-tier-gps-precision-asymmetry.md) | Cross-tier GPS precision asymmetry — Safe Harbor vs consent substitution | Proposed |
| [0019](0019-cost-gate-tier-binding.md) | Cost gate binds on every tier whose ToolDefinition advertises a non-zero token range | Proposed |
| [0020](0020-typed-protocols-for-cross-component-seams.md) | Typed Protocols for cross-component seams — signature drift fails at type-check time | Proposed |
| [0021](0021-framework-honors-health-data-analysis-domain.md) | Project domain is health data analysis; framework must architecturally reflect that | Proposed |
| [0022](0022-local-llm-guardian.md) | Local LLM is framework-tier infrastructure; numbers from processing, prose from the local LLM | Proposed |
| [0023](0023-local-llm-cooperation-loop.md) | Local-LLM layer as substrate-vision contributor in a cooperation loop | Proposed |
| [0024](0024-wheel-distributed-tour-and-fixture-bundling.md) | Wheel-distributed tour and fixture bundling — generated artifacts ship, generators stay out | Accepted (superseded in part) |
| [0025](0025-cue-card-rehearsal-as-release-gate.md) | Cue-card rehearsal as a release-time gate; the cue card is a load-bearing artifact | Proposed |
| [0026](0026-claude-desktop-config-dual-path.md) | Claude Desktop config-path resolution under UWP sandboxing — dual-write to all paths | Accepted |
| [0027](0027-demo-as-researcher-first-look.md) | `tailor demo` is a researcher first-look, not operator self-verification | Accepted (superseded in part) |
| [0028](0028-recipient-install-validation-as-release-gate.md) | Recipient-install validation as a release-time gate | Accepted |
| [0029](0029-token-reduction-as-analytical-quality.md) | Token reduction is analytical quality, not just cost optimization | Accepted |
| [0030](0030-public-mirror-narrative-and-affordance-depth.md) | Public-mirror page deepens narratively; outbound affordances pruned to zero | Accepted (superseded in part by 0032) |
| [0031](0031-rename-to-tailor-and-wardrobe.md) | Project rename to Tailor + Wardrobe (counter-programming invariant) | Superseded in part (0033, 0034) |
| [0032](0032-retire-public-mirror-distribution.md) | Retire the public-mirror distribution path; wheel-handoff supersedes | Accepted |
| [0033](0033-complete-tailor-metaphor-workshop-side.md) | Complete the Tailor metaphor on the workshop side — positive identity over counter-programming | Accepted |
| [0034](0034-retire-tailor-migrate-subcommand.md) | Retire `tailor migrate` — the v6 → v7 migration population was empirically zero | Accepted |
| [0035](0035-cli-rename-walkthrough-and-fitting-room-and-recipient-experience-naming-principle.md) | CLI rename — walkthrough + fitting-room, and the recipient-experience naming principle | Accepted (superseded in part) |
| [0036](0036-matlab-child-scope-v72-only-with-deferred-hdf5.md) | MATLABFileChild v1 supports `.mat` v≤7.2 only; HDF5-based v7.3 deferred | Accepted |
| [0037](0037-redcap-child-scope-export-directory-only-with-deferred-live-api.md) | RedcapFileChild v1 supports export-directory wrapping only; live REST API deferred | Accepted |
| [0038](0038-vault-layer-is-data-source-agnostic.md) | Vault layer is data-source-agnostic | Proposed |
| [0039](0039-audit-log-is-llm-queryable-under-column-allowlist.md) | Audit log is LLM-queryable under a column allowlist | Accepted |
| [0040](0040-bounded-setup-time-conductor-surface.md) | Bounded setup-time conductor surface | Proposed |
| [0041](0041-license-apache-2-0-to-agpl-3-0-or-later.md) | License — Apache-2.0 → AGPL-3.0-or-later, effective v9.0.0 | Accepted |

### IRB-relevant decisions

ADRs that govern data-flow, consent, audit, and re-identification semantics
— the load-bearing reading list for an IRB committee or compliance reviewer:

- [0001](0001-audit-log-as-backbone.md) — what gets logged on every call
- [0003](0003-phi-scrubber-seam.md) — the no-op default and the institutional override seam
- [0009](0009-vault-subject-keying.md) — `entity_id` integrity and the set-once invariant
- [0013](0013-cache-only-purge-on-consent-revocation.md) — what happens to cached data when consent is revoked

## Template

Copy [0000-template.md](0000-template.md) when proposing a new
architectural decision. Number sequentially; do not reuse numbers
even if a prior ADR is superseded — mark the old one `Superseded by
NNNN` instead.
