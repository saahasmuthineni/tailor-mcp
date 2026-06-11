# Handoff — launch-blocker cleanup (pre-launch doc-truth pass)

*Implementation brief, written 2026-06-11 to be dropped into a fresh
Claude Code session on this repo. Branch from current `main` (v9.1.0,
post-PR #149). Read CLAUDE.md first — all boss-architect protocols
and the specialist-gate culture apply. Every claim below was verified
against the tree at the commit this brief lands in. Amended
2026-06-11 after an independent verification review pass: all
original claims re-confirmed against the tree; item 1 gains the
wheel-shipped `RECIPIENT_README.md` (a missed occurrence of the same
failure class), the bundled-fixture snapshot mention gets an explicit
decision, and acceptance criterion 1's grep is widened repo-wide.*

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
  changes). Do not touch `pilot.py`, `__main__.py`, `wizard.py`, or
  the pyproject package-data *globs* — none of this work needs them.
- **`recipient-install-validator` file gate WILL fire** (item 1 now
  includes a one-line doc fix inside `_fixtures/**` — see the
  snapshot.md decision below). Flag it and skip per the v9.0.2
  precedent: a doc-text-only fixture change is not an install-path
  change. Name the flag-and-skip in the final report.

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
- **`src/tailor/RECIPIENT_README.md`** (added on review) — the worst
  instance of the class, missed by the original scope. This file
  ships **inside the wheel** via the `*.md` package-data glob,
  written specifically for an external Claude inspecting the wheel
  on a confused recipient's machine, and its TL;DR instructs
  `tailor fitting-room` as "the canonical recipient-onboarding
  command" (lines 13, 34, 43; the v7.1.x rename-history note at
  50–61 and line 85 also need a current-state rewrite). Rewrite it
  around the v8.0.0 recipient path: `tailor pilot` is the only CLI
  touch; fitting-room runs as the three MCP tools driven from chat.
  The historical rename note can stay as history but must end at the
  current truth (v8.0.0 hard-removed the verb). Editing this file
  does NOT trip the `recipient-install-validator` file gate — the
  gate names `pilot.py` / `__main__.py` / `wizard.py` /
  `fitting_room.py` / package-data globs / `_fixtures/**`, not this
  file.
- **`pyproject.toml` package-data comment** (added on review) — the
  comment above the `"*.md"` glob says the readme exists so an
  external Claude can "discover `tailor tour`". Comment-only fix;
  do not change the globs themselves.
- **`src/tailor/_fixtures/cohort_demo_realistic/vault/snapshot.md:15`**
  (added on review) — the bundled seed-vault snapshot says the demo
  vault was "scaffolded by `tailor fitting-room`". Descriptive, not
  instructional, but it lands verbatim in the recipient's vault and
  is now false (scaffolding happens via `tailor_fitting_room_scaffold`).
  **Decision: fix it** — one-line wording change — and accept that
  this touches `_fixtures/**`, firing the `recipient-install-validator`
  file gate; flag and skip per the v9.0.2 precedent (see ground
  rules). Leaving a known-false line in recipient-facing content to
  avoid a flag-and-skip would invert the doc-truth priority.

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
  it into a cue card. (Pre-verified on review: the scaffold tool
  takes `force: bool`, optional, default false —
  `framework/fitting_room/layer.py`.)
- The bare-`serve` recovery row points at `tailor_setup_help`. That
  tool still exists (`framework/setup_help/__init__.py`), so the row
  isn't wrong — but v8.0.0's `SetupLayer` tools
  (`tailor_setup_status` etc.) may now be the better-shaped recovery
  path. Reconsider which tool the rewritten row points at; the
  cue-card auditor validates what's written, not whether it's the
  best choice.
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

## Item 2 — Delete `docs/guides/demo.tape`; add a benchmark receipt SVG (boss-refined 2026-06-11, second pass)

**Problem:** the tape records `tailor walkthrough` (removed v8.0.0).
**Facts that shape the fix:** its output `docs/assets/demo.gif` does
not exist and nothing embeds it — the pipeline is broken *and*
unconsumed. And the format itself was inherited, not chosen: a
recording proves the thing ran *once, on the author's machine, at
render time* — it can go stale silently and a skeptical reader
trusts it less than text. The repo's brand is deterministic
receipts; the asset should be one.

**Decided direction (boss-ratified):**

1. **Delete `docs/guides/demo.tape`.** The falsehood and the format
   go together. Historical ADR mentions (0027, 0035) stay verbatim
   per the doc-truth convention.
2. **Add `benchmarks/render_receipt.py`** — a small, deterministic,
   stdlib-only generator that takes the benchmark script's JSON
   output and renders a terminal-styled SVG panel of the final
   output (the three scenarios, token counts, ratios) to
   `docs/assets/benchmark-receipt.svg`. Match the visual language of
   the existing hand-built SVGs (`footprint.svg`,
   `vault-insights.svg`) — dark panel, same accent palette. Static;
   no animation in v1.
3. **Add a pytest freshness guard** (e.g.
   `tests/test_benchmark_receipt.py`): re-run the benchmark
   measurement, parse the numbers out of the checked-in SVG, assert
   they match. The image must not be able to drift from the script —
   if a fixture change moves a ratio, CI fails until the receipt is
   re-rendered. This is the load-bearing difference from any
   recording format. **For the guard to actually run in CI, add
   `tiktoken` to the `[dev]` extras in `pyproject.toml`** (the SVG's
   numbers are tiktoken numbers; a skip-when-absent guard would
   silently never execute in the CI matrix, voiding the property).
   Keep the runtime sane — the cohort measurement is the slow one;
   target < 30s or mark it appropriately.
4. **Embed in README** next to "The numbers" table, with the
   three-command reproduce block adjacent: the image is the
   invitation, the reproduction is the proof. Alt text carries the
   three ratios for accessibility.

Notes: the same SVG is reusable as the repo social-preview card and
launch-post image — keep the aspect ratio sane for that (roughly
2:1). The motion job (watching the product work) belongs to the
human screen recording in `docs/launch-demo-storyboard.md`, not this
asset; do not add a GIF.

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
- `docs/launch-demo-storyboard.md` — two edits: (a) beat 4 is
  written as "If `tailor inspect` has shipped…"; it has — make the
  inspector page the primary beat (keep the sqlite3 fallback text
  for the pre-render rehearsal note if useful). (b) The blocker
  callout at the top links to `docs/guides/demo.tape`, which item 2
  deletes — rewrite it as resolved (tape deleted; terminal proof is
  now the CI-verified receipt SVG; the storyboard covers only the
  chat-beats human recording).

## Acceptance criteria

1. Across **recipient-facing documentation** — `examples/**`, the
   wheel-shipped `src/tailor/RECIPIENT_README.md`, and the bundled
   `_fixtures/**` vault prose — `grep -rn "tailor fitting-room\|tailor
   tour\|tailor walkthrough"` returns only historical mentions
   (those that say *renamed / hard-removed / no longer / legacy*).
   Zero instructions to *run* a removed verb. Named historical
   exclusion zones where stale verbs are expected and left verbatim:
   `docs/adr/`, `CHANGELOG.md`, `docs/reports/`, `docs/diagnosis/`,
   and ROADMAP "Shipped" sections.

   **Out of this brief's scope (flag as follow-on, do NOT fix here —
   they touch `framework/` / `src/` / `scripts/` / tests, fenced off
   by the ground rules):** the `tailor_setup_help` framework tool
   still emits `recipient_steps` that say "Run: tailor fitting-room"
   (`framework/setup_help/__init__.py`) — the most serious instance,
   since it instructs the removed verb to exactly the stuck-recipient
   audience, and it is regression-locked by `test_setup_help_layer.py`
   so fixing it is a framework + test change; `src/tailor/fitting_room.py`
   argparse/usage still advertises `tailor fitting-room` (preserved
   library module, CLI dispatch already removed); `demo/runner.py`
   + `docs/guides/share-the-demo.md` document the removed
   `tailor walkthrough --save-shareable` export, which has no shipped
   MCP equivalent (a rewrite-or-delete decision, not a verb swap —
   needs boss input); `scripts/build_demo_install_pdf.py` and
   `__main__.py` status strings. These are real doc-truth defects but
   a separate, larger pass.
2. `rehearse.py` (cohort realistic AND business demo) exit 0 before
   and after.
3. cue-card-rehearsal-auditor returns all-PASS on the revised
   CUE_CARD.md.
4. Benchmark md / README numbers / technical piece agree with a
   fresh script run; version row current.
5. `demo.tape` deleted; `docs/assets/benchmark-receipt.svg` exists,
   is embedded in README, and the freshness test fails if the SVG's
   numbers are edited away from the benchmark output (prove it once
   by mutating a digit locally, watching the test fail, reverting).
6. Full gates green (`ci-gate-runner` scope), commits signed off,
   `boss-report-auditor` pass on the final report before it goes to
   the boss.
