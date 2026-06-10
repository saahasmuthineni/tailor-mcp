# Contribution licensing — a decision to make before the first stranger PR

*Decision memo, 2026-06-10. Input to a possible future ADR (per
ADR 0041 § Reversal condition 4); not itself a decision. The decision
belongs to the boss.*

---

## The plain-language version (read this part)

Right now, anyone who contributes code to Tailor does so under the
same license the project ships under (AGPL). That's the friendliest
possible arrangement for contributors — no paperwork, no legal
ceremony. It has one quiet consequence: **every outside contribution
we merge permanently narrows what we can later do with the project's
license.** Selling commercial licenses, offering an
academic-institution exception, or selling the project outright would
each require either the agreement of every past contributor or a
rewrite of their code.

Today there is exactly one author, so every option is still open. The
repo went public two weeks ago; the first outside pull request can
arrive any day. Once it's merged, the default has been chosen by
accident. This memo exists so the choice is made on purpose.

**The decision in front of you:** keep maximum contributor
friendliness (and accept that commercial-licensing options decay), or
add lightweight paperwork now (and keep those options open). There is
also a cheap middle step we should take regardless.

---

## Where things stand

- `CONTRIBUTING.md` § License: contributions are accepted
  inbound-equals-outbound under AGPL-3.0-or-later. No CLA, no DCO.
- [ADR 0041](../adr/0041-license-apache-2-0-to-agpl-3-0-or-later.md)
  (the AGPL switch) explicitly **rejected** dual-licensing
  (Alternative 7) because it requires CLA machinery, and named
  "project goals shift to commercial licensing revenue" as Reversal
  condition 4 — requiring its own superseding ADR.
- The project currently has a single author, so relicensing rights
  are intact as of this writing.

So the status quo is not an oversight — it was decided, with a named
reversal condition. What's changed since ADR 0041: the repo is now
public, and the project is actively weighing commercial-value paths
(the subject of the current strategy thread). That is precisely the
condition the reversal clause anticipated. The question is live.

## The options

### Option 1 — Status quo: inbound = outbound, nothing added

**What it preserves:** the zero-friction contributor experience;
full consistency with ADR 0041.
**What it costs:** relicensing optionality decays monotonically with
every merged external PR of copyrightable size. Dual-licensing,
academic-exception licensing (ADR 0041 Reversal condition 1 names
this as the likely fallback!), and acquisition all get harder with
each contributor. Note the tension: ADR 0041's own fallback plan for
an institutional-adoption barrier assumes a relicensing flexibility
that this option erodes.

### Option 2 — Add a DCO (Developer Certificate of Origin)

Contributors add `Signed-off-by` to commits (`git commit -s`),
certifying they have the right to submit the code. Standard practice
(Linux kernel, GitLab); enforceable with a free GitHub app.

**What it preserves:** provenance hygiene — protection against
someone contributing code they don't own. Near-zero friction.
**What it does NOT do:** a DCO grants the project no relicensing
rights whatsoever. It is good hygiene, not optionality preservation.
Worth doing in either world, which is why it's the
"regardless" step.

### Option 3 — Adopt a CLA before accepting external code

Contributors sign a one-time agreement granting the project the right
to relicense their contribution (e.g., the Apache ICLA shape, or a
Fiduciary License Agreement that adds obligations on the project
side).

**What it preserves:** every commercial and licensing option,
permanently, regardless of how many contributors arrive.
**What it costs:** real friction and real political signal — some
contributors refuse CLAs on principle, especially in the AGPL
community Tailor just joined; it partially contradicts the
community-commons signal ADR 0041 chose AGPL to send. Adopting it
requires a superseding ADR per Reversal condition 4.

### Option 4 — DCO now + decision trigger on the first framework PR

DCO immediately (Option 2). Additionally, a written rule: **no
external PR touching `src/tailor/framework/` is merged until the
CLA question has been explicitly decided** (external PRs to
`children/`, `examples/`, and docs may proceed under DCO — they are
peripheral to any plausible commercial-licensing surface and easier
to rewrite if ever needed). This converts "decide now under
uncertainty" into "decide at the moment it becomes real, with the
option still intact."

**What it costs:** a slightly awkward contributor experience if a
great framework PR arrives before the decision is made; the
discipline to actually hold the line.

## Recommendation

**Option 4.** The DCO half is cheap and correct in every future. The
trigger half keeps the valuable option (the `framework/` copyright,
which is where any commercial-licensing value lives) intact without
paying the CLA's political cost before we know whether a commercial
path is actually being pursued. If the strategy work concludes that
commercial licensing is real, that conclusion plus this memo becomes
the superseding ADR that Reversal condition 4 already anticipates; if
it concludes otherwise, quietly drop the trigger and Option 1 resumes
with nothing lost.

What I'd ask the boss to decide, in order:

1. Adopt DCO now? (Low stakes; recommend yes.)
2. Hold framework-PR merges behind the CLA decision? (The real
   choice; recommend yes until the commercial question resolves.)
3. Is the commercial-licensing path live enough to warrant the
   superseding ADR now? (Honest answer as of this memo: not yet —
   it's one launch and one market signal away. Revisit after the
   distribution push.)
