# Tailor vocabulary

> **Normative reference for [ADR 0033](../adr/0033-complete-tailor-metaphor-workshop-side.md).**
> The ADR commits the project to this vocabulary; this file enumerates it.
> Changes to any of the six tables below land in the same change as a
> superseding or amending ADR — drift between code, ADRs, and this file
> is a documentation-truthfulness signal owned by
> [`code-vs-roadmap-drift-auditor`](../../.claude/agents/code-vs-roadmap-drift-auditor.md).

The vocabulary is **workshop-shaped**, not lifestyle-shaped. The
distinction is load-bearing — see § Table 5 below for the narrow-forbid
list that operationalises it.

## Table 1 — Structural nouns

| Word | What it names | Where it lives in code |
|---|---|---|
| **Tailor** | The framework — the craftsperson | `src/tailor/` |
| **Wardrobe** | The customer's collection — themes, moments, evidence, failure modes, source data | `framework/vault/` + child caches |
| **Thread** | Raw incoming data, prior to any framework processing | Wire-level input to a child's ingest path |
| **Fabric** | A mill's processing output — what a child returns from `execute()` | `children/*/processing.py` outputs |
| **Garment** | A broad family of AI-wearable analytical outfittings | `_meta`-stamped result envelopes |
| **Seam** | A framework extension boundary | `ChildMCP`, `PHIScrubber`, `LocalLLMBackend`, the writer hook |
| **Ledger** | The audit log — the tailor's record, separate from the wardrobe | `framework/audit.py`, `audit.db` |

The Ledger / Wardrobe split is load-bearing. The Wardrobe is the
customer's; the Ledger is the tailor's. They are accounted separately
even though both are local-first.

## Table 2 — Relational verbs

Twelve verbs naming what Tailor does. Each verb either already maps to
shipped code or names an extension shape the framework supports.

| Verb | Meaning | Anchor |
|---|---|---|
| **Curate** | Add to, retrieve from, govern access into the Wardrobe | Vault layer dispatch |
| **Source** | Mill pulls from an external feed | `children/running/strava_api.py` |
| **Commission** | Tailor asks a mill for specific fabric | Router → child dispatch |
| **Measure** | Pre-estimate cost before commissioning | [ADR 0005](../adr/0005-cost-pre-estimation.md) |
| **Trim** | Filter to a tier the wearer needs (replaces *Cut*; see § Weak beats) | Three-tier access model in `framework/router.py` |
| **Alter** | Refine an existing garment by supersession | `vault_correct_evidence` |
| **Mend** | Correct an error in place | `vault_correct_evidence` with propagate |
| **Match** | Cross-reference Wardrobe items | `vault_traverse_links` |
| **Inspect** | Audit at a seam | `mcp-protocol-auditor`, `coverage-criticality-mapper` |
| **Preserve** | Hold durably across sessions | Vault as source of truth |
| **Revert** | Undo by purging cached fabric (disambiguator: not Git revert) | [ADR 0013](../adr/0013-cache-only-purge-on-consent-revocation.md) |
| **Stitch** | Close a seam with a concrete implementation (verb form of Seam) | Institutional `PHIScrubber` subclasses; see [ADR 0003](../adr/0003-phi-scrubber-seam.md) |

## Table 3 — Service hierarchy (mill-tailor producer-consumer)

```
User  ─ owns ──▶  Wardrobe
  │
  ▼ commissions
Tailor  ─ commissions ──▶  Mill (child)
  │                          │
  ▼ outfits                  ▼ weaves
  AI  ─ wears ─▶  Garment ◀──┘
```

- **User** is the principal — owns the Wardrobe, owns the work, owns
  the vision.
- **Tailor** is the craftsperson — does the fitting in service to the
  user.
- **Mill** is a child (`ChildMCP` subclass). Each mill has its own
  analytical craft — see [ADR 0021](../adr/0021-framework-honors-health-data-analysis-domain.md).
  The framework respects the mill's craft and commissions specific
  fabric without telling the mill how to weave.
- **AI** is the wearer — a collaborator on the team, outfitted by
  Tailor, acts on the user's behalf.

Benefit is ultimately optimised to the User. The AI benefits greatly
as part of the loop. The Ledger audience (see Table 4) benefits via
inspectability.

## Table 4 — Audience model

Three audiences. A fourth (lifestyle / consumer) is explicitly out of
scope.

| Audience | Role | Examples |
|---|---|---|
| **User** | Customer; principal | The PI, the analyst, the clinician, the writer |
| **AI** | Wearer; collaborator | Claude, GPT, any MCP-speaking model |
| **Audit audience** | Inspector; witness | IRB boards, legal-discovery reviewers, regulatory auditors, peer reviewers, replication-study leads, security auditors |

The Audit audience is named explicitly because it is the audience
that reads the Ledger. The Wardrobe is curated for the User and read
by the AI; the Ledger is recorded by the Tailor and read by the Audit
audience. The framework's IRB-grade provenance claims are claims
about Ledger legibility.

## Table 5 — Workshop-vs-lifestyle invariant

This table replaces the three counter-programming bullets in
[ADR 0031 § Counter-programming invariant](../adr/0031-rename-to-tailor-and-wardrobe.md#counter-programming-invariant-load-bearing).
The new invariant is **narrow-forbid**: a small list of lifestyle-
register words that must not appear in framework-emitted surfaces.

**Always forbidden** (the lifestyle register is dominant — no
register switch can rescue these):

| Word | Reason |
|---|---|
| couture | Haute-couture register |
| couturier | Haute-couture register |
| atelier | Boutique aesthetic |
| boutique | Retail-lifestyle register |
| runway | Fashion-show register |
| showroom | Retail-display register |

**Forbidden in lifestyle-register usage** (permitted in workshop /
infrastructure register, but the burden is on the writer to make the
register unambiguous):

| Word | Workshop-permitted use | Lifestyle-forbidden use |
|---|---|---|
| collection | "the analyst's collection of evidence blocks" | "the new spring collection" |
| look | "what this evidence looks like to the IRB" | "the look of the season" |
| style | "the docstring style" | "personal style" |
| trend | "a rolling trend report" | "this season's trends" |
| designer | "a child's API designer" | "designer brands" |
| outfit | "outfit the AI with cohort tools" | "an outfit for spring" |
| brand | "brand of LLM backend" | "brand identity" |
| aesthetic | (avoid — almost always lifestyle) | "the aesthetic of the line" |
| showcase | (avoid — almost always lifestyle) | "a showcase of new looks" |

**Not on the forbidden list:**

- **Model** — LLM-domain collision dominates. *Model* is a working
  word in this project; the lifestyle reading is structurally
  impossible in context.
- **Wearer** — permitted in ADRs and contributor docs, **forbidden in
  user-facing onboarding copy.** The wearer concept matters
  architecturally (Table 3) but reads strangely on a first impression.
  Onboarding copy uses "your AI" instead.

## Table 6 — Weak beats and retroactive drops

**Weak beats — informal-prose-only.** These appear in walk-throughs,
README narrative, and ADR prose but **are not named architectural
vocabulary.** A code path or new component does not get one of these
as its primary name.

- Sew
- Baste
- Tack
- Hem
- Press
- Polish
- Fitting (as a session-event noun — *"this fitting"* is okay; a
  class named `Fitting` is not)
- Embroider

**Retroactive drops** (previously considered, now retired):

- **Fit** — head-on collision with the running child's fitness data,
  and a grab-bag verb rather than naming a single operation. Replaced
  by *Measure* + *Trim* depending on the operation.
- **Cut** — too parametric. *Cut* could mean either *Trim* (filter to
  a tier) or *Commission* (carve a specific fabric out of a thread).
  Replaced by *Trim* for the tier-filter case.

## How this file updates

Changes to any table land via a superseding or amending ADR. The
amending pattern is:

1. The ADR names the word, the table, and the change.
2. The ADR commits to the change in its Decision section.
3. This file is updated in the same change.
4. `code-vs-roadmap-drift-auditor` audits drift between this file and
   the ADR set on its existing cadence.
