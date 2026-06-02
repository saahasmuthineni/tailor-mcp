# ADR 0033: Complete the Tailor metaphor on the workshop side — replace counter-programming with positive identity

- **Status:** Accepted
- **Date:** 2026-05-12
- **Supersedes (in part):** [ADR 0031 (Rename to Tailor + Wardrobe)](0031-rename-to-tailor-and-wardrobe.md) — the counter-programming invariant retires; the naming decisions (Tailor / Wardrobe / `tailor-mcp` / `tailor` / `~/.tailor/`) are retained
- **Related:**
  - [ADR 0003 (PHI scrubber as seam)](0003-phi-scrubber-seam.md) — the seam/stitch noun-verb pair lives in shipped vocabulary; the framework's institutional PHI scrubbers *stitch* the seam closed
  - [ADR 0014 (Coverage criticality invariant)](0014-coverage-criticality-invariant.md) — voice and structural pattern for codifying a previously-implicit invariant
  - [ADR 0021 (Project domain is health data analysis)](0021-framework-honors-health-data-analysis-domain.md) — mill / tailor producer-consumer split is consistent with the renderer-registration decouple
  - [ADR 0022 (Local-LLM guardian)](0022-local-llm-guardian.md) — LocalLLMLayer is a parallel seam to the vault layer, same noun-verb continuity
  - [`docs/design/tailor-vocabulary.md`](../design/tailor-vocabulary.md) — the normative reference enumerating the six tables this ADR commits to
  - [CLAUDE.md § What This Project Is / § Your Wardrobe](../../CLAUDE.md#what-this-project-is) — receives the cascade edits this ADR triggers (see § Doc-truth cascade)

## Context

[ADR 0031](0031-rename-to-tailor-and-wardrobe.md) shipped the v7.0.0
rename and introduced *Wardrobe* as the user-facing engine word. Its
identity work was structurally one-sided: three counter-programming
commitments stated as **negative rules** about what fashion-domain
language must not appear in branding, onboarding copy, and content
views. The rename had to ship fast — the architecture's data-agnostic
identity could not survive another minor cycle confined behind the
*Biosensor MCP* name — so the positive identity work was deferred. The
counter-programming bullets were the stopgap. ADR 0031 § Reversal
conditions named the stopgap shape obliquely: *"if the project
consistently fails to keep fashion-domain language out... the engine
word should be replaced."* The structural patch was a fence around the
metaphor, not a metaphor.

A 2026-05-12 strategic conversation walked the metaphor on its workshop
side. The natural-meaning-first test held: *Tailor*, *Wardrobe*, *Seam*,
*Stitch*, *Commission*, *Measure*, *Trim*, *Curate* all reach for the
same workshop-shaped image cluster without any of them landing on
lifestyle / boutique / haute-couture vocabulary. A grep across
[`docs/adr/`](.) confirmed the codebase already reaches for this
vocabulary: 214 occurrences of the thirteen-verb subset (curate /
source / commission / measure / trim / alter / mend / match / inspect /
preserve / revert / stitch / seam) across 30 ADRs. The vocabulary is
already shipped; what is missing is the commitment to it.

The structural problem the counter-programming invariant solved
remains real — a stranger encountering the project cold can read it as
fashion-adjacent — but the negative-rules shape is fragile. Counter-
programming requires the project to keep redirecting indefinitely
against the literal-clothing read. A positive metaphor identity does
the redirection by **occupying the workshop register first.** A reader
who encounters *Wardrobe* alongside *Seam*, *Stitch*, *Ledger*,
*Commission*, and *Inspect* — workshop and infrastructure words — does
not need the redirection to be re-stated in every paragraph. The
register does the work.

ADR 0031's reversal conditions named the runner-up engine words (Trove,
Cabinet, Keep) as the fallback if counter-programming proved
untenable. The fallback is not what this ADR is. *Wardrobe* is
retained; the counter-programming invariant retires. The replacement
is a positive identity commitment that this ADR codifies.

The question this ADR answers: *what is the project's positive
metaphor identity, and what is the smallest contract that makes it
load-bearing rather than aesthetic suggestion?*

## Decision

The project commits to a workshop-shaped metaphor identity. The full
vocabulary — six tables of nouns, verbs, the service hierarchy, the
audience model, the workshop-vs-lifestyle invariant, and the weak
beats — lives at
[`docs/design/tailor-vocabulary.md`](../design/tailor-vocabulary.md)
and is referenced normatively from this ADR. The ADR commits the
project to the vocabulary; the vocabulary file enumerates it. This
mirrors the pattern [ADR 0014](0014-coverage-criticality-invariant.md)
uses with the CRITICAL / HIGH / MEDIUM / LOW criticality map — the ADR
is the architectural record, the supporting file is the canonical
enumeration.

The five-sentence Decision spine — what the project is committing to,
in plain English:

1. **The framework is a craftsperson in service to the user.** The user
   is the principal — owns the wardrobe, the work, and the vision; the
   framework does the fitting.
2. **Children are mills.** Each child has its own craft (analytical
   processing); the framework commissions specific fabric but does not
   tell the mill how to weave.
3. **The AI is the wearer.** A collaborator on the team — wears the
   work, acts on the user's behalf in interaction. Not the principal
   beneficiary, but not external to the work either.
4. **Garments are the family of analytical artifacts the wearer is
   outfitted with.** Refinement varies; the wardrobe holds garments at
   every refinement level.
5. **The Wardrobe is the customer's. The Ledger is the tailor's.** They
   are separate; together they account for everything the framework
   holds on the customer's behalf.

The split between **Wardrobe** and **Ledger** is the structural shift
from [CLAUDE.md § Your Wardrobe](../../CLAUDE.md#your-wardrobe) as
shipped. The current bullet list places *Audit history* inside the
Wardrobe as one of six contents. This ADR moves Audit history out into
the Ledger concept. The shift is justified by the directory layout
already in place: [`framework/audit.py`](../../src/tailor/framework/audit.py)
and `audit.db` live in `framework/`, not in `framework/vault/`. The
vault layer (`framework/vault/`) is the Wardrobe's storage; the audit
log is a sibling component, not a contained one. The ADR formalises
what the file structure already implied. Without this justification
the Ledger split would look like accidental drift; with it, the ADR
records that the codebase structure was correct and the prose was
imprecise.

The ADR 0031 counter-programming invariant retires. ADR 0031's three
negative bullets (no fashion visual language; onboarding copy
redirects the clothing read; content views show diverse contents) are
replaced by the narrow-forbid list at
[`tailor-vocabulary.md` § Table 5](../design/tailor-vocabulary.md#table-5--workshop-vs-lifestyle-invariant)
— a list of thirteen lifestyle-register words categorised as **always
forbidden** (six: couture / couturier / atelier / boutique / runway /
showroom) or **forbidden in lifestyle-register usage** (nine:
collection / look / style / trend / designer / outfit / brand /
aesthetic / showcase). The narrow-forbid list is enforceable by grep;
the prior counter-programming bullets required taste-level judgment on
every PR.

*Model* is **not** on the forbidden list. LLM-domain collision
(`local_llm`, model tiers, ML model) dominates the fashion-domain
read; in this codebase the word *model* is unambiguous. *Wearer* is
**permitted in ADRs and contributor docs, forbidden in user-facing
onboarding copy** — the architectural concept matters (per the five-
sentence spine) but reads strangely on first impression. Onboarding
copy uses "your AI" instead.

The cascade edits this ADR triggers are enumerated in § Doc-truth
cascade below.

## Doc-truth cascade

Reviewer's checklist. Each item is a file that needs editing
downstream of this ADR landing. A PR that lands this ADR without the
cascade is in conflict with the ADR.

1. **[CLAUDE.md § Your Wardrobe](../../CLAUDE.md#your-wardrobe)** — the
   six-item bullet list at lines 1036–1042 currently lists *Audit
   history* alongside themes / moments / evidence / failure modes /
   source data. Move *Audit history* out of the Wardrobe bullet list
   into a sibling **Ledger** paragraph. The Wardrobe is the customer's
   collection; the Ledger is the tailor's record. Both are local-first
   and held on the user's behalf; they are accounted separately.
2. **[CLAUDE.md § What This Project Is](../../CLAUDE.md#what-this-project-is)**
   — the existing first paragraph is workshop-register-clean and needs
   no change. The "Tailor curates your Wardrobe" sentence near the end
   of § Your Wardrobe is consistent with this ADR and stays.
3. **[README.md](../../README.md)** — every passage that mirrors the
   CLAUDE.md Wardrobe bullet list updates in parallel. The README is
   the recipient-visible surface and is where the Ledger / Wardrobe
   split is most important. The README's onboarding copy may now
   define Wardrobe positively (no longer required to redirect *"not
   clothes — your stuff"* defensively, though the redirect is not
   forbidden where it reads naturally).
4. **[ROADMAP.md](../../ROADMAP.md)** — the deferred entry for a
   `counter-programming-invariant-auditor` agent reshapes. The
   narrow-forbid list at Table 5 is enforceable by grep, which moots
   the originally-proposed agent. The roadmap row either retires the
   item or reshapes it into a `vocabulary-drift-auditor` candidate
   under [ADR 0011](0011-promotion-policy.md)'s structural-argument
   gate. The latter is preferred so the deferred row carries an
   explicit retirement record.
5. **[ADR 0031](0031-rename-to-tailor-and-wardrobe.md)** — status
   flipped from `Accepted` to `Superseded in part by ADR 0033
   (counter-programming invariant retired; naming retained)` with a
   one-line forward-cite at the top of the file. The counter-
   programming section's three bullets remain readable for historical
   record (parallel to ADR 0031's own § Historical preservation
   pattern); the bullets are no longer the project's commitment.
6. **[`docs/design/tailor-vocabulary.md`](../design/tailor-vocabulary.md)**
   — new file, lands in the same change as this ADR. Six tables;
   normative reference from this ADR's Decision section.

Items 1–5 may land in the same commit as this ADR (the boss-architect
may flip the status to `Accepted` if so) or in a follow-on doc-truth
pass. Either order is acceptable; an ADR landing without the cascade
edits is in measurable conflict with itself and the next
`code-vs-roadmap-drift-auditor` run will flag it.

## Consequences

### Positive

- **The project gains a positive identity to occupy, not just a fence
  to defend.** A reader encountering *Wardrobe* alongside *Seam*,
  *Stitch*, *Ledger*, *Commission*, and *Inspect* receives a workshop
  register on first impression. The redirection that ADR 0031's
  counter-programming bullets had to perform on every surface now
  happens automatically because the vocabulary occupies the workshop
  slot first.
- **The narrow-forbid list at Table 5 is enforceable by grep**, which
  the prior three counter-programming bullets were not. A future PR
  that introduces *atelier* or *runway* is mechanically detectable; a
  future PR that introduces fashion-adjacent visual language under the
  prior invariant required taste-level review. The enforcement story
  is structurally cheaper than what it replaces.
- **The Ledger / Wardrobe split fixes a real conceptual conflation in
  the shipped CLAUDE.md.** Audit history is the tailor's record of
  what the framework did, not part of the customer's collection of
  themes / moments / evidence. The directory layout
  ([`framework/audit.py`](../../src/tailor/framework/audit.py) vs
  [`framework/vault/`](../../src/tailor/framework/vault/)) already
  reflected the split; this ADR aligns the prose with the structure.
  The IRB-grade audit story per [ADR 0001](0001-audit-log-as-backbone.md)
  is sharpened — the audit log has a name now, not just a directory.
- **The vocabulary lands in a file separate from the ADR.** Future
  amendments to a single table (adding a new verb, retiring a word
  from Table 5) do not require a new ADR if the spine of the metaphor
  is unchanged. They land via direct edits to
  [`tailor-vocabulary.md`](../design/tailor-vocabulary.md) with
  ADR-amendment level changes for spine-touching shifts. This mirrors
  [ADR 0014](0014-coverage-criticality-invariant.md)'s pattern: the
  criticality map can be extended without a new ADR; the criticality
  *taxonomy* (CRITICAL / HIGH / MEDIUM / LOW) requires one.
- **The mill / tailor producer-consumer framing in Table 3 aligns with
  [ADR 0021](0021-framework-honors-health-data-analysis-domain.md).**
  ADR 0021's decouple-prep commitment treats domains and tool names as
  opaque strings — the framework respects each child's analytical
  craft without special-casing it. The mill metaphor names exactly that
  commitment in user-facing language. The two ADRs reinforce each
  other rather than diverging.
- **`Seam` and `Stitch` are already shipped vocabulary**, not new
  invention. [ADR 0003](0003-phi-scrubber-seam.md) names the
  scrubber-seam pattern, [ADR 0022](0022-local-llm-guardian.md) names
  the local-LLM seam, [ADR 0020](0020-typed-protocols-for-cross-component-seams.md)
  names typed protocols for cross-component seams. This ADR commits to
  what is already there.

### Negative

- **Layering a second naming commitment compounds change-cost in
  principle.** Every recipient who absorbs the v7.0.0 rename must now
  also absorb the workshop-shaped vocabulary commitment. Under a
  mature distribution profile this would be a meaningful additional
  cost. **Under the current Phase 0 framing the cost falls on future
  recipients, not present ones** — recipient-install deliverable 3
  (different machines / recipients) was only proven 2026-05-10 (see
  CLAUDE.md v7.0.4 banner), deliverable 4+ remains unvalidated, and
  there is no established external recipient population yet for
  v7.0.0's vocabulary. Doing the metaphor commitment now means future
  recipients absorb both commitments at once — exactly the structural
  logic ADR 0031 used for the original rename ("doing the rename at
  v7.0.0 when the platform has one shipped recipe and limited adoption
  is dramatically cheaper than doing it later"). The tradeoff is named
  here so future readers see both sides of the reasoning rather than
  treating the bundling as obvious.
- **The narrow-forbid list at Table 5 has edge cases the
  counter-programming bullets did not.** *Collection* is permitted in
  workshop register ("the analyst's collection of evidence") and
  forbidden in lifestyle register ("the new spring collection"). The
  register distinction requires writer judgment, which is what Table 5
  asks the contributor to perform. Mitigated by the always-forbidden
  six-word list which carries no register ambiguity, and by the
  workshop-register that surrounds every authoring context in this
  codebase.
- **The Ledger split obsoletes some copy that recipients have already
  seen.** A v7.0.0–v7.0.6 recipient who read CLAUDE.md or README and
  formed the model "audit history is part of my Wardrobe" now has to
  re-form the model. The version-banner pattern (v7.0.x banners
  enumerate prior framings) absorbs the drift without falsifying past
  artifacts.
- **The vocabulary file is a new documentation surface that must stay
  in sync with the code and the ADRs.** Drift between
  [`tailor-vocabulary.md`](../design/tailor-vocabulary.md), the
  shipped code, and the ADR set is now a class of bug. Mitigated by
  the existing `code-vs-roadmap-drift-auditor` remit — the file is
  treated as documentation under that agent's existing scope and does
  not need a new specialist.

### Neutral

- **The naming decisions from ADR 0031 are unchanged.** The PyPI
  distribution is still `tailor-mcp`, the import name is still
  `tailor`, the CLI command is still `tailor`, the config dir is
  still `~/.tailor/`, the engine word is still *Wardrobe*. ADR 0031's
  table at § "Naming decisions, fully resolved" continues to hold.
  This ADR amends only the counter-programming portion of ADR 0031.
- **Internal architectural identifiers are unchanged.**
  [`framework/`](../../src/tailor/framework/),
  [`framework/vault/`](../../src/tailor/framework/vault/),
  `audit.db`, `RouterMCP`, `ChildMCP`, `VaultLayer` — no rename.
  Table 1's *Wardrobe* / *Ledger* / *Seam* / *Garment* terminology is
  user-facing aggregate naming, not a refactor of the code.
- **The first deployment recipe (demo cohort researcher first-look) is
  unchanged.** The bundled fixtures, `tailor tour`, `tailor demo`, and
  the demo runner's output (per [ADR 0027](0027-demo-as-researcher-first-look.md))
  do not change. The vocabulary commitment is about how the project
  describes itself; the worked-example recipe is what it does.
- **`mcp-protocol-auditor` and `cue-card-rehearsal-auditor` are
  unaffected.** Neither agent inspects user-facing prose vocabulary;
  both work at the protocol / schema level. This ADR introduces no
  new gates.

## Reversal conditions

This ADR can be revisited (or superseded) under any of the following
conditions:

1. **Onboarding tests reveal recipients still read the project as
   fashion despite the locked vocabulary.** If recipient-install
   validation, dad-as-recipient testing, or a future beachhead-lab-
   meeting-shape interaction surfaces consistent fashion-misread evidence, the
   runner-up engine words from
   [ADR 0031 § Alternative 3](0031-rename-to-tailor-and-wardrobe.md#alternative-3-different-engine-words-considered)
   reactivate. The fallback path is the same one ADR 0031 named (Trove
   / Cabinet / Keep as the closest replacements); this ADR does not
   open a different fallback path. A reversal that takes this branch
   supersedes both this ADR and the naming portion of ADR 0031.
2. **The architecture diverges from the workshop framing.** If a future
   major architectural shift (e.g. moving Tailor from local-first to a
   hybrid local-cloud topology, or shifting the framework's primary
   audience from individual users to institutional deployments) would
   make the *craftsperson-in-service* hierarchy structurally
   inaccurate, the vocabulary is revisited as part of that shift.
3. **The narrow-forbid list at Table 5 produces consistent false
   positives.** If contributors hit the always-forbidden six-word list
   on legitimate workshop-register usage (a hypothetical *atelier*
   that is genuinely workshop-shaped in context), the list is revised
   in a follow-up ADR amendment. The current six are picked because
   their lifestyle reading dominates in every register; the
   nine-word "forbidden in lifestyle register" list is where register
   ambiguity is expected to live.
4. **A trademark conflict materialises around any Table 1 noun.** Same
   shape as ADR 0031's reversal condition 2 — a credible cease-and-
   desist or a material trademark search hit triggers revisitation of
   the affected noun.

The reversal conditions are deliberately *not* "a contributor prefers
different verbs" or "the vocabulary feels imperfect." Metaphor choices
are always partly arbitrary; once chosen and shipped, the project's
self-description stabilises around them. Reversing them again carries
a cost (contributor re-learning, recipient re-onboarding, ADR cascade)
that is only worth paying for one of the structural conditions above.

## Alternatives considered

**Keep ADR 0031's counter-programming invariant; do nothing positive.**
The minimal-change option. The three negative-rules bullets continue
to govern, and the project relies on every PR reviewer to enforce
fashion-language discipline by taste. Rejected because ADR 0031 itself
named the counter-programming invariant as carrying *"an ongoing
maintenance cost that simpler naming choices would have avoided"* —
the cost was accepted as the price of the Tailor + Wardrobe pairing,
but accepting the cost does not mean leaving the invariant in its most
fragile form. The positive identity is structurally cheaper to
maintain than the negative one.

**Adopt the metaphor in prose but not in an ADR.** Write the
vocabulary file at [`docs/design/tailor-vocabulary.md`](../design/tailor-vocabulary.md)
and update CLAUDE.md / README copy to match, without an ADR. Rejected
on [ADR 0011](0011-promotion-policy.md) grounds and on the same
pattern [ADR 0014](0014-coverage-criticality-invariant.md) named:
*"a rule that diverges from the apparent default but lives only in...
a promotion-rationale paragraph is invisible to future readers."* The
counter-programming invariant lives in an ADR (ADR 0031); the
replacement must also live in an ADR or the replacement is silently
weaker than what it replaces. A future contributor reading ADR 0031
and finding its invariant still apparently load-bearing would either
re-enforce a retired rule or re-derive the absence by accident.

**Replace *Wardrobe* with a runner-up engine word (Trove, Cabinet,
Keep).** The fallback path ADR 0031 § Reversal conditions named. The
runner-up words have lower fashion-adjacent risk by construction.
Rejected because the structural problem the counter-programming
invariant solved is **register**, not the word *Wardrobe* itself.
*Wardrobe* paired with *Seam*, *Stitch*, *Ledger*, *Commission*, and
*Inspect* reads workshop-shaped; *Wardrobe* paired with no other
vocabulary commitment reads fashion-adjacent. Replacing the word is
fixing a symptom; commiting to the surrounding register is fixing the
structural cause. The runner-up words remain available under the
reversal-condition 1 fallback path; they are not the move now.

**Expand the metaphor further — name every framework concept in
workshop terms.** Could rename `framework/`, `RouterMCP`, `ChildMCP`,
`VaultLayer`, and every other internal identifier in workshop
vocabulary. Rejected on ADR 0031's existing line: internal
architectural identifiers describe the architecture, not the project's
identity, and renaming them produces churn without clarifying
anything. The vocabulary commitment is **aggregate user-facing
naming**, not a code-level refactor. The split between code-level
identifiers and user-facing aggregate terms is what makes the
metaphor sustainable — the framework gets to be a craftsperson in
prose without forcing every Python class to wear workshop clothing.

**Bundle this ADR with the v8.0.0 decouple per ADR 0021 instead of
landing in v7.0.x.** [ADR 0021](0021-framework-honors-health-data-analysis-domain.md)
identifies v8.0.0 as the decouple-ship cycle. The vocabulary
commitment could ride alongside that shift, when the framework's
*"children are mills"* commitment becomes architecturally
load-bearing rather than just metaphor-shaped. Rejected because the
counter-programming invariant in ADR 0031 is **currently in force on
every PR**, and leaving it in its fragile form for the duration of
v7.0.x means every contributor and every release-time check operates
under a rule the team has already concluded is suboptimal. The
metaphor commitment is independently load-bearing on prose surfaces
right now (CLAUDE.md, README, onboarding copy) regardless of when the
v8.0.0 architectural decouple lands. Bundling the two would slow
both.
