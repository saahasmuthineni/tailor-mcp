# Overnight report — 2026-06-10

*Branch: `claude/fable-repo-monetization-dhngdk`. Context: the
value-of-Tailor strategy thread (claim the MCP-governance position;
surface the trust artifacts; de-niche the first impression; protect
licensing optionality). This was the Week-1/Week-2 build work from
the one-month plan.*

---

## What's on the branch (plain language)

**1. A business-data worked example** — `examples/business_demo/`.
Twelve synthetic retail stores, 90 days of daily sales each, served
by the *existing* generic CSV child — zero framework changes. A
visitor who asks "is this only for health data?" now gets a
five-minute walkthrough on revenue data: region comparison computed
server-side, anomaly (a two-week store closure) found from a
~400-token summary, audit-log receipt at the end. Every number in
the README and cue card is verified by a `rehearse.py` script
against the real tool output (exit 0 = demo-ready), following the
cue-card-accuracy lesson from ADR 0025.

**2. The governance-pattern spec** —
`docs/design/mcp-governance-pattern.md`. The category-position
artifact from the strategy thread: Tailor's governance layer (tiers,
gate pipeline, structured refusals, audit schema, provenance stamps,
plugin contract) written as a pattern *any* MCP server author can
adopt, with Tailor as the reference implementation. This is the
"publish the spec, own the position" move. Linked from the README.

**3. The honest comparison draft** — `docs/launch-comparison.md`.
The Khoj / Open WebUI / AnythingLLM piece the roadmap's Phase 3
Direction B sketched: they're applications doing retrieval, Tailor
is middleware doing governed computation; per-call gates vs
per-user roles; audit log vs chat history. Generous to all three
where they're genuinely better. Facts checked against their public
docs on 2026-06-10; the draft carries a re-verify-before-publishing
note because all three ship fast.

**4. A licensing-optionality decision memo** —
`docs/reports/contribution-licensing-options-2026-06-10.md`. The
repo is public and accepts contributions with no DCO/CLA; every
merged external PR permanently narrows the dual-license /
academic-exception / sale options. The memo lays out four options
and recommends: DCO now (cheap, correct in every future) + hold
external `framework/` PRs behind an explicit CLA decision. **Nothing
was changed** — this is your call, and ADR 0041 anticipated it
(Reversal condition 4).

**5. Two additive README sentences** linking the pattern doc and the
business demo. No positioning changes — see the open decision below.

## Decisions you own (in priority order)

1. **DCO / CLA** — read the licensing memo. The clock on this one is
   "whenever the first stranger PR arrives," which is not under our
   control. Recommended: adopt the memo's Option 4.
2. **A framing tension to resolve before launch.** The existing
   `docs/launch-strategy.md` says *"Don't try to be generic — the
   specificity of force-plate data is what makes 938× believable."*
   The strategy thread (and tonight's pattern doc + business demo)
   pushes the generic governance position. My read: these compose
   rather than conflict — lead launch *posts* with the specific
   benchmark, let the *repo* show breadth (business demo) and the
   *spec* claim the category. But that's a judgment call about the
   project's voice, and it's yours, not mine.
3. **Publish or hold the comparison piece.** It's drafted as a
   launch-week artifact. If launch stays parked, it keeps; if you
   greenlight the distribution push, the facts need a same-week
   re-verify.

## Found while working (not fixed, flagged)

- **Stale recipient-facing docs:** `examples/cohort_demo/realistic/`
  README + CUE_CARD still instruct `tailor fitting-room` (and
  reference `tailor tour`), both hard-removed in v8.0.0 per ADR 0040.
  A non-technical recipient following those docs today hits "no such
  command." Not fixed overnight because the correct replacement
  phrasing (FittingRoomLayer MCP tools driven from Claude Desktop
  chat) deserves a deliberate doc-truth pass with the cue-card
  auditor, not a 3am guess. Recommend queueing it.

## Gates

- Full pytest: **1,665 passed, 3 skipped** (scipy-absent MATLAB
  skips, known/orthogonal). No `src/` changes on this branch — the
  work is examples + docs + two README sentences.
- ruff: clean on the CI-enforced scope (`src tests`) and on all new
  Python (`examples/business_demo/`). Eight pre-existing findings sit
  outside CI scope (`benchmarks/`, the worked-example notebook, two
  older example scripts) — untouched, noting for completeness.
- `examples/business_demo/rehearse.py`: exit 0, all assertions pass;
  cue-card numbers are wire-verified.
