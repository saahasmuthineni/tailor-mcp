# Overnight 2026-05-01 — morning briefing

**Branch:** `claude/overnight-2026-05-01` (4 commits ahead of `main`, NOT merged)
**State of the tree:** 595/595 tests pass, 85% coverage, ruff clean, security probe clean, CLI smoke clean. Branch is shippable.
**What this report is for:** orient with coffee in three minutes; review the PR with the rest of breakfast.

---

## What the night did, in one paragraph

Fourteen specialist + discovery agents audited the v6.5.0 codebase in two waves. Wave 1 was 8 audit specialists + 6 open-ended discovery agents in parallel; wave 2 was the coverage-criticality mapper plus a red-team adversarial pass on the wave-1 verdicts. The framework's load-bearing invariants all hold (0 BROKEN reproducibility invariants, 0 IRB violations from the framing-driven audit). Fifteen low-risk fixes landed across four commits: documentation drift, three regression tests, three Proposed ADRs awaiting your review, and two small bug fixes (macOS iCloud cloud-sync detection + a vault `subject_id` set-once post-rejection invariant test). Nothing was merged. Three findings escalated past the audit framing — a cross-tier GPS leak the IRB auditor missed, a cost-gate Tier-2 wiring gap, and a recurring signature-drift class — and are filed as Proposed ADRs for your call.

---

## Decisions you own (in order of severity)

### 1. Cross-tier GPS precision asymmetry — **HIGH severity, IRB-relevant** ([ADR 0018](../adr/0018-cross-tier-gps-precision-asymmetry.md))

v6.3.1 hardened `strava_stop_analysis` (Tier 1) to coarsen GPS to 3 decimals (~111m) and bucket distance-from-home to 100m, citing HIPAA Safe Harbor §164.514(b)(2)(i)(B). But the same activity, escalated to Tier 2 via consent (`strava_downsampled_streams`) or Tier 3 (`strava_full_streams`), exposes residence-precision GPS at 5 decimals (~1.1m). The framework currently treats consent at Tier 2 as the shield against re-identification; v6.3.1's banner cites Safe Harbor as the shield at Tier 1. **The two readings are mutually exclusive and the project has not picked one.**

The discovery agent caught this; the IRB auditor did not (it spot-checked Tier 1 only); the red-team adversarial pass confirmed the gap.

**Pick one:**
- (A) **Uniform Safe Harbor across tiers** — Tier-2/3 also coarsen to 3 decimals; consent-gated streams trade some analytical fidelity for de-identification. Most defensive; matches the v6.3.1 framing.
- (B) **Consent-as-shield at Tier 2** — keep Tier-2/3 at 5-decimal residence precision; document that consent is the shield and update the consent text accordingly. Most flexible; preserves analytical fidelity.

The full Decision section in ADR 0018 walks both readings with the IRB-facing claim each commits the project to defending. After you pick: amend the ADR to single-reading Accepted, file the implementation issue, and `phi-irb-risk-reviewer` re-runs against the picked reading.

### 2. Cost gate Tier binding — **MEDIUM severity, ADR 0005 amendment** ([ADR 0019](../adr/0019-cost-gate-tier-binding.md))

`children/running/child.py:529-530` returns `tokens=0` for everything except `strava_full_streams`, so Tier-2 `strava_downsampled_streams` (whose ToolDefinition advertises 3,000-7,000 tokens) silently skips CostGate entirely. Same pattern in `children/csv_dir/child.py` and `children/template/child.py`. ADR 0005's "pre-estimation, not post-billing" claim is structurally incomplete on Tier 2.

**Pick one:**
- (A) **Wire Tier-2 estimators on every child** (rule: cost gate binds on every tier with a non-zero advertised token range)
- (B) **Amend ADR 0005 to Tier-3-only** — make the advertised token ranges explicitly advisory
- (C) **Per-tool flag on ToolDefinition** — `cost_estimator_required: bool`, default True for Tier ≥2

ADR 0019 walks all three. The rule, not the implementation, is the question for tonight.

### 3. Typed Protocols for cross-component seams — **MEDIUM severity, structural lesson from v6.5.0** ([ADR 0020](../adr/0020-typed-protocols-for-cross-component-seams.md))

v6.5.0's demo-before-commit gate caught the `Server.run` SDK signature drift. The same gate-evasion class lives at `framework/router.py:554-565` (post-execute hook), audit row schema, `_meta` block, and `ChildMCPSurface`. A future fourth-arg add or kwarg-only signature change raises `TypeError` inside the silent try/except, vault writes silently stop, and pytest stays green because no test asserts empty `_meta.hook_warnings` on the canonical demo call.

**Pick one:**
- (A) **File ADR 0020 as drafted** — typed Protocols on four named seams; mypy/pyright in CI as the gate
- (B) **Amend [ADR 0016](../adr/0016-mcp-protocol-auditor.md)** — fold the structural lesson into the existing mcp-protocol-auditor ADR; one ADR covers both wire-side and internal-seam signature drift
- (C) **Defer** — runtime regression tests (the existing `mcp-protocol-auditor` shape) are sufficient

ADR 0020's Alternatives section frames (B) explicitly so you can pick at review time.

### 4. Framework concurrency model — **MEDIUM severity, deferred candidate** (no ADR yet)

The Strava OAuth refresh has a checked-then-acted race in `children/running/strava_api.py:104-126` — two concurrent `get()` calls under expired token both POST refresh; Strava rotates refresh_token on each, so the loser's refresh becomes invalid and the user must re-run `biosensor-mcp setup`. The fundamental question — *what concurrency model does the framework guarantee?* — was DEFER'd by the adr-weigher because the answer materially shapes the project's positioning against managed-agents (`docs/design/managed-agents-compat.md`) and you own that call.

**Pick one:**
- (A) Document single-process / single-event-loop assumption — cheapest, locks in an architecture invariant
- (B) Add a per-child file-lock around refresh — defends future multi-process deployments
- (C) Mark as known limitation in ROADMAP.md, deferred until the managed-agents path is explored

A future session files the chosen ADR.

---

## What the night actually shipped

Four commits on `claude/overnight-2026-05-01`:

| Commit | Cluster | Files changed |
|---|---|---|
| `1ebbc24` | Tier-1 doc drift | CLAUDE.md, README.md, ROADMAP.md, pyproject.toml |
| `dcf625e` | Tier-2 regression tests | tests/framework/test_security.py |
| `f6555b7` | ADR cluster (0017 Accepted + 0018/0019/0020 Proposed) | CLAUDE.md, .claude/agents/adr-weigher.md, 4 new ADR files |
| `1414457` | macOS iCloud detection + set-once invariant test | tests/, src/biosensor_mcp/pilot.py, src/biosensor_mcp/__main__.py |

**Doc drift fixed (4 P1 + 1 P2 from drift auditor):**
- README csv_dir tool count `5 → 7`
- README `_meta` examples `package_version 6.4.1 → 6.5.0` (two sites)
- CLAUDE.md File Structure block: csv_dir comment `5 tools → 7 tools`
- CLAUDE.md `_meta` field list: was incomplete, now names domain/tier/scrubber_id/token counts/scrubber_warning/hook_warnings to match `framework/router.py:571-587`
- ROADMAP.md "shipped" CSV directory section: `5 → 7` with ADR 0015 citation
- pyproject.toml `[project.urls]`: PyPI Homepage / Repository / Issues links were 404 (old repo name `biosensor-to-llm-middleware`); now point to `Biosensor-to-LLM-Connector`

**Regression tests added (4 new, all additive):**
- `test_int_coercion_typeerror_returns_explicit_failure` — pins `framework/security.py:65-69` int-coercion except branch (CRITICAL coverage gap per coverage-criticality-mapper)
- `test_noop_warning_emitted_at_most_once_per_process` — pins ADR 0003's once-per-process contract on PHIScrubber's no-op warning (had no test before)
- `test_subclass_construction_does_not_emit_noop_warning` — pairs with above; subclass policies must not trip the warning
- `test_reassignment_rejection_does_not_mutate_file_or_evidence` — pins ADR 0009's atomicity guarantee that the on-disk file is unchanged after a rejected `subject_id` reassignment

**Bug fixes (2):**
- macOS iCloud canonical paths (`~/Library/Mobile Documents/com~apple~CloudDocs/`) now trigger the cloud-sync warning the wizard already issues for OneDrive/Windows iCloudDrive
- (above-named regression test for ADR 0009 set-once)

---

## What the night chose not to do

The autonomous-session ADR cap is six per session ([ADR 0017](../adr/0017-adr-weigher-and-autonomous-session-cap.md), filed tonight as `Accepted`). The adr-weigher returned 4 PASS verdicts (used 3 ADR slots — 0018, 0019, 0020 — plus the 0017 governance ADR; 2 PASS slots remained unused). Five candidates were `REJECT-NOT-ADR-WORTHY` and one was `DEFER-NEEDS-BOSS-INPUT` (the concurrency-model question above).

The full discovery findings (15 DEFINITELY, 27 LIKELY, 24+ WORTH-A-LOOK across the 6 module surfaces) are in [`docs/reports/debugging-discovery-2026-05-01.md`](debugging-discovery-2026-05-01.md). The REJECTed-but-still-worth-fixing items (5 bug-shaped findings + 1 evidence-not-reproducible re-investigation) are in [`docs/reports/promotion-candidates-2026-05-01.md`](promotion-candidates-2026-05-01.md).

The hardest candidate the weigher refused: **C3, the `time_to_50pct_drop_s` peak-tie systematic bias** in `children/csv_dir/processing.py:97-107`. For real isometric force traces (ramp → plateau → decline), `values.index(peak)` returns the *first* index at peak, not the start of decline — so time-to-50% is systematically underreported by the plateau duration, with bias scaling non-uniformly across subjects. This invalidates the cohort tool's comparison-of-groups framing for the HIP-Lab demo. The weigher refused `PASS` because the decision-shape failed criterion 1 (it's a math bug, not a decision among credible alternatives) and instead routed it to the bug-fix list. **This is the one finding the night did not fix; it requires your math/science-shape review before the fix changes Tier-1 numbers and shifts the demo's expected outputs.** Full detail in the discovery report.

---

## Things you should look at in the PR

1. **ADR 0018 Decision section** — both readings are presented at full detail with the IRB-facing claim each commits the project to. The structurally unusual shape (two readings in Decision, not Alternatives) is documented as Proposed-status convention; on acceptance the un-chosen reading collapses to one paragraph in Alternatives.

2. **The adr-weigher specialist** at `.claude/agents/adr-weigher.md` and ADR 0017. The cap is six PASS verdicts per autonomous session; the weigher is the binding constraint, not the count. Anti-sycophancy section explicitly forbids returning PASS-justifications for all candidates the main session stages.

3. **The doc-drift fixes are mostly mechanical** — fast skim is sufficient. The one with mild semantic content is the CLAUDE.md `_meta` field list expansion at line 544; the previous text was an honest under-spec.

4. **The regression tests** are pure additive coverage; no production code paths changed.

---

## Numbers

- 4 commits ahead of `main`
- 14 agents in wave 1; 2 in wave 2; 3 adr-drafter calls; 1 adr-weigher call; 1 ci-gate-runner final = 21 specialist invocations
- 595 tests pass (was 591); 85% coverage (was 85%)
- 4 PASS / 5 REJECT / 1 DEFER from adr-weigher on 10 candidates
- 1 MEDIUM red-team objection raised (and confirmed)
- 0 changes to `framework/security.py` / `framework/router.py` / `framework/audit.py` / `framework/vault/` (the hard limits I held)
- 0 production-code changes that altered Tier-1 numbers or behavior the boss has not approved

---

## What's next

The PR is open against `main`, NOT merged. With coffee:

1. Skim the four commits in order; the morning-readable summary is each commit message.
2. Read ADR 0018; pick A or B. (HIGH severity, IRB-facing.)
3. Read ADR 0019; pick A / B / C. (MEDIUM severity.)
4. Read ADR 0020; pick A / B / C. (MEDIUM severity, may amend 0016 instead.)
5. Read [`debugging-discovery-2026-05-01.md`](debugging-discovery-2026-05-01.md) for C3 (peak-tie bias) and decide whether it's a fix-this-week or fix-next-cycle.
6. Read [`promotion-candidates-2026-05-01.md`](promotion-candidates-2026-05-01.md) for the REJECTed bug list.
7. Either merge the PR (`gh pr merge --admin --merge <PR#>`) or leave it open and we land Accepted-ADR amendments before merge.
