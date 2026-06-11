# Handoff — launch-blocker cleanup (pre-launch doc-truth pass)

*Implementation brief, written 2026-06-11 to be dropped into a fresh
Claude Code session on this repo. Branch from current `main` (v9.1.0,
post-PR #149). Read CLAUDE.md first — all boss-architect protocols
and the specialist-gate culture apply. Every claim below was verified
against the tree at the commit this brief lands in.*

---

## Ground rules for this session

- **Every commit needs a DCO sign-off** (`git commit -s`) — enforced
  by `.github/workflows/dco.yml` since PR #147. Forgetting it fails
  CI with the offending SHA named.
- Docs-truth work, almost no code: nothing here touches
  `framework/`, children, or the MCP surface. If you find yourself
  editing those, stop — the scope has drifted.
- **Specialists that fire:** `cue-card-rehearsal-auditor` is
  **mandatory** for item 1 (CUE_CARD.md changes trigger it per
  ADR 0025 — this gate exists because wrong cue-card params shipped
  twice in one week once). `boss-report-auditor` before the final
  report. `ci-gate-runner` before the PR.
- **Specialists that do NOT fire:** `mcp-protocol-auditor` (no wire
  changes), `recipient-install-validator` (do not touch
  `_fixtures/**`, `pilot.py`, `__main__.py`, `wizard.py`, or
  pyproject package-data — none of this work needs them).

## Item 1 — De-stale `examples/cohort_demo/realistic/` (the main job)

**Problem:** the recipient-facing demo docs still instruct CLI verbs
hard-removed in v8.0.0 (ADR 0040): `tailor fitting-room` and
`tailor tour`. A recipient following them today hits "no such
command." Verified occurrences:

- `README.md` — TL;DR block, "Pre-meeting setup" § 2, fallback
  table (three rows tell the operator to run
  `tailor fitting-room --force`), recovery-prompts section
- `CUE_CARD.md` — recovery-prompt table rows (vault-not-indexed,
  partial-registration, Microsoft-Store rows all say re-run
  `fitting-room`)
- `WINDOWS_QUICKSTART.md:42,102,197-199`
- `generate.py:337` and `setup.py:11` (comments only)

**The correct current flow to rewrite around** (read these before
editing): `src/tailor/framework/fitting_room/` exposes three MCP
tools — `tailor_fitting_room_status` / `tailor_fitting_room_scaffold`
/ `tailor_fitting_room_index_vault` — wrapping the preserved
`tailor.fitting_room` library helpers (CLAUDE.md v8.0.0 banner;
ADR 0040). Recipients drive them from Claude Desktop chat ("set up
the demo fitting room"); the only CLI touch in the recipient path is
`tailor pilot`. Get exact tool names and param shapes from
`framework/fitting_room/layer.py`, not from this brief.

**Care points:**

- The "fallback if something breaks live" rows must be rewritten as
  chat-driven recoveries (ask Claude to call
  `tailor_fitting_room_scaffold` with force) — verify the force
  parameter's actual name/shape in the layer source before writing
  it into a cue card.
- `rehearse.py` imports the library module directly and should be
  unaffected — but **run it** (`python
  examples/cohort_demo/realistic/rehearse.py`) before and after to
  prove the doc pass changed no behavior.
- Historical ADRs (0024, 0027, 0035) mention the old verbs as
  history — leave them verbatim per the doc-truth convention
  (historical record is not rewritten).
- After editing CUE_CARD.md, run `cue-card-rehearsal-auditor
  --cue-card=examples/cohort_demo/realistic/CUE_CARD.md` and close
  any WRONG-TOOL / WRONG-PARAMS verdicts before the PR.

## Item 2 — Replace `docs/guides/demo.tape` (boss-refined scope)

**Problem:** the tape records `tailor walkthrough` (removed v8.0.0).
**Fact that shapes the fix:** its output `docs/assets/demo.gif` does
not exist and nothing in the repo embeds it — the pipeline is broken
*and* unconsumed.

**Decided direction (2026-06-11):** rebuild the tape to record the
**benchmark run** — `pip install tiktoken && python
benchmarks/token_efficiency.py` — ending on the printed ratios
(657.6× / 938.2× / 318.2×). It is the launch's load-bearing claim,
deterministic, and terminal-native. Then embed the rendered GIF in
README next to "The numbers" table.

- Keep the tape's existing cosmetic settings (theme, font, 960×540)
  as the starting point; trim total runtime to ~30s (use VHS
  `Sleep`/`Hide` to skip pip-install noise).
- Rendering needs the `vhs` binary (charmbracelet/vhs single-binary
  release). Try to install it in-session; **fallback if the
  environment can't run it:** ship the corrected tape +
  `docs/guides/` render instructions and note the GIF as a
  human-render step. Either outcome removes the falsehood.
- The Claude-Desktop chat beats remain a separate human
  screen-recording task per `docs/launch-demo-storyboard.md` — out
  of scope here.

## Item 3 — Benchmark doc refresh

`benchmarks/token_efficiency.md` Assumptions table still says
"tailor-mcp 8.0.0 (this commit bumps to 9.0.0)"; the repo is at
9.1.0. Per the queued note in
`docs/reports/overnight-2026-06-10.md`: **re-run the script**
(`pip install tiktoken && python benchmarks/token_efficiency.py`)
rather than hand-editing, confirm every number in the md still
matches the output (the v9.0.2 fixture rename already moved
session-resume to 318.2× — verify no further drift), and update the
version row. If any number moved, update README's "The numbers"
table and `docs/launch-technical-piece.md` in the same commit — those
three surfaces must agree.

## Item 4 — Small doc-truth closures

- `docs/adr/0043-read-only-inspector-not-application.md` — Status
  reads **Proposed**; it shipped in tagged v9.1.0 (PR #148/#149).
  Flip to Accepted.
- `docs/launch-demo-storyboard.md` beat 4 — written as "If `tailor
  inspect` has shipped…"; it has. Make the inspector page the
  primary beat (keep the sqlite3 fallback text for the pre-render
  rehearsal note if useful).

## Acceptance criteria

1. `grep -rn "tailor fitting-room\|tailor tour\|tailor walkthrough"
   examples/ docs/guides/` returns only historical-ADR-quoted or
   changelog-style mentions — zero instructions to *run* removed
   verbs anywhere recipient-facing.
2. `rehearse.py` (cohort realistic AND business demo) exit 0 before
   and after.
3. cue-card-rehearsal-auditor returns all-PASS on the revised
   CUE_CARD.md.
4. Benchmark md / README numbers / technical piece agree with a
   fresh script run; version row current.
5. demo.tape records only commands that exist on the v9.1.0 surface;
   GIF rendered and embedded, or render-instructions fallback
   documented.
6. Full gates green (`ci-gate-runner` scope), commits signed off,
   `boss-report-auditor` pass on the final report before it goes to
   the boss.
