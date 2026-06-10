# ROADMAP v10 — reconciliation-first plan

Derived from the June 2026 full-corpus audit ([2026-06-fable-audit.md](2026-06-fable-audit.md)). Finding IDs (F-NN) reference that report's findings table.

**Sequencing principle:** v9 made the *public surface* trustworthy; v10's job is to make the *self-description* trustworthy and finish the domain-agnostic flip below the surface. The audit found no broken wire behavior on shipped surfaces — so v10 is ordered by leverage on credibility (a skeptical engineer or IRB reviewer cross-checking claims) rather than by code risk. Doc-truth fixes come first because they are cheap, currently falsifiable by any reader, and several gate the project's stated "rigor calibrated for a skeptical engineer" posture.

---

## Workstream 1 — Release-record and claim integrity (first; ~1 day; highest leverage)

The repo currently makes public claims a reviewer can falsify in minutes. Close every one:

1. **Back-fill CHANGELOG for v9.0.1 + v9.0.2** (F-01) and adopt the rule: anything published to PyPI gets a CHANGELOG entry, no "by intent" exceptions.
2. **Give `strong_motion` a release record** (F-02): CHANGELOG entry, ROADMAP § Shipped line, README + README_PYPI data-source rows. Also reconcile the held ROADMAP items it already satisfies: "Worked-example notebook v2 against a published analytical question" (the Northridge PGA notebook shipped, commit `153e11f`) and the "New ChildMCPs" candidate list that omits it.
3. **README accuracy pass** (F-12, F-22, F-40): fix the 938×-as-15-mile-run misattribution (×2), the 1,588 test count, the "~1000x" badge (use 938×), "implement five things" listing four, the unenforced "Coverage floor 80%" claim, README_PYPI's stale token counts and missing children; derive or drop the "85×" alt-text figure.
4. **Tool-count truth** (F-13): document `csv_synchronized_windows` (csv_dir is 8 tools), and add `force_csv` (9 tools) + `emg_csv` (8 tools) to CLAUDE.md File Structure and the child tables.
5. **CITATION.cff bump + add to release-shipper checklist** (F-26). Add the ADR-index row for 0042 (F-31).
6. **License-summary decision** (F-18): restore a short plain-English AGPL paragraph to README, or amend ADR 0041 + CHANGELOG to point at README_PYPI as the canonical summary. Pair with the AGPL hygiene decision on SPDX headers / asserted copyright (F-19) — recommend a one-line SPDX header sweep + filled copyright notice; it is mechanical and settles the posture permanently.

## Workstream 2 — Recipient-facing breakage from the v8 hard-removal (~1–2 days)

Everything here actively misleads a recipient or breaks a gate *today*:

1. **Regenerate the cue card** (F-04) against live v9 schemas (`csv_group_summary`, `entity_id`, MCP fitting-room flow) and run cue-card-rehearsal-auditor on it. Then amend the auditor's trigger so identifier renames in ToolDefinitions/params count as cue-card-affecting changes — the v9.0.0 "NOT TRIGGERED" miss is the gate failing its own remit.
2. **Rewrite recipient-install-validator** (F-05) Phase-1 steps against `tailor pilot` + WalkthroughLayer/FittingRoomLayer MCP tools, resolving the contradiction with CLAUDE.md's roster row. Drop the dead `tour.py` trigger glob in release-shipper (F-38).
3. **Fix runtime strings instructing removed commands** (F-15): `setup_help/__init__.py:166,168` and `demo/runner.py:468,529`.
4. **Guides sweep** (F-14): share-the-demo.md (also resolve the live mirror-URL question, F-27 — boss call on whether the legacy Pages URL staying up is acceptable post-name-scrub), claude-desktop-demo.md, demo.tape, structural-engineering-framing.md quickstart.
5. **docs/design current-tense API sweep** (F-16): `subject_id` → `entity_id`, `PHIScrubber` → `DataScrubber` in the four named files; run `scripts/rename_for_public_flip.py` over `examples/` to clear the beta/realistic residue (F-33).

## Workstream 3 — ADR corpus reconciliation (~1 day; mostly editing ADR files)

### Status flips (shipped but still Proposed) — F-10

Apply with one-line shipped-in-version notes:

- **ADR 0022 → Accepted.** *Stub:* "Status: Accepted (flipped 2026-06; the LocalLLMLayer shipped v6.6.0 and has been live architecture since — see CLAUDE.md § Architecture. Body identifiers updated for v9: `csv_cohort_summary` → `csv_group_summary`; the 'OracleBackend protocol' shipped as `LocalLLMBackend(ABC)` and 'contract.py' as `oracle.py` — accepted shape variances, not drift."
- **ADR 0023 → Accepted.** *Stub:* "Status: Accepted (flipped 2026-06; all three cooperation-loop fields, the layer-side deterministic scan, and the three oracle audit columns shipped — `oracle.py:147-176`, `layer.py:171-184`, `audit.py:219-232`)."
- **ADR 0038 → Accepted.** *Stub:* "Status: Accepted (v7.6.0 closure shipped the `vault_note_kinds` seam, `_kind_to_domain_map`, and the AST invariant tests this ADR's own terms named as the ratification condition; flip recorded 2026-06). The `vault_get_fitness_summary` removal trigger remains open and is re-checked per minor cycle."
- **ADR 0040 → Accepted.** *Stub:* "Status: Accepted (shipped as v8.0.0, 2026-05-19; all eight tools, the bounded-write allowlist triple defense, `SETUP_CONFIG_WRITE`, and `_redact_home` verified in the 2026-06 audit)."
- **ADR 0042 → Accepted.** *Stub:* "Status: Accepted — the named flip trigger fired when `docs/guides/worked-example.ipynb` landed with `fetch_pinned` (sha256 verify, provenance-before-analysis, license fields, labeled offline fallback)."
- **ADR 0025 → Accepted** (the gate is enforced at release-shipper and CLAUDE.md treats it as promoted), folded into the cue-card refresh of Workstream 2.

### Supersession markers and amendments

- **ADR 0021 → Superseded** (F-09). *Stub:* "Status: Superseded by ADR 0038 (vault decoupling concern) and the v9.0.0 public flip (project identity). The decision 'the framework must architecturally reflect the health-data-analysis domain' was reversed by events: v7.0.0 became the Tailor rename (ADR 0031), v8.0.0 became the recipient-experience offload (ADR 0040), and v9.0.0 made domain-agnosticism the externally-committed identity. The unfinished vault-decoupling work this ADR correctly identified (strava renderers and seed-dict defaults in framework core — `vault/writer.py:103-105`, `renderer.py:113-885`) transfers to the v10 Workstream 4 plan, not to this ADR."
- **ADR 0001/0004/0005 outcome-vocabulary amendment** (F-24). *Stub (one amendment, cross-referenced from all three):* "Amendment 2026-06: the outcome tokens these ADRs name (`OK`, `BLOCKED_*`, `CONSENT_REQUIRED`, `COST_APPROVAL_REQUIRED`) never matched the implementation. The canonical audit-outcome vocabulary is: `SUCCESS`, `ERROR`, `PARAM_INVALID`, `CIRCUIT_OPEN`, `CONSENT_BLOCKED`, `COST_ESTIMATE_ERROR`, `COST_GATE_TRIGGERED`, their `*_INTERNAL` twins, plus `SETUP_CONFIG_WRITE`, `ATTEST_INITIAL`, `REATTEST`, `PURGE_CACHE`, `PURGE_FAILED`. The wire-envelope `gate` field (`consent_required` / `cost_approval_required`) is where the ADRs' phrasing lives. IRB query recipes should use this list."
- **ADR 0012 amendment for the three v8 layers** (F-28). *Stub:* "Amendment 2026-06: SetupLayer, WalkthroughLayer, and FittingRoomLayer (ADR 0040) join the bypass roster. Invariants: SetupLayer's only write authority is the `SETUP_WRITE_KEY_ALLOWLIST` bounded write (its reversal condition lives in ADR 0040); Walkthrough and FittingRoom are read-only/scaffold-only surfaces whose reversal condition is any future tool on either layer that writes outside the demo sandbox — such a tool re-opens this ADR."
- **ADR 0026 v8 marker** (F-41) and **ADR 0030 CLI-host note** (F-42): one-line each, matching the markers their sibling ADRs received on 2026-05-19.
- **ADR 0014 amendment** (F-06, F-20): either (a) enforce — add `fail_under = 80` to `[tool.coverage.report]`, add a coverage step to CI, re-point coverage-criticality-mapper at the ADR as canonical; or (b) descope — amend the ADR to say the floor is agent-mediated, and delete the README claim. Recommend (a): the ADR's argument for the invariant is sound and the cost is one config line + one CI step.

### Decide-or-retire (the aspirational trio)

- **ADR 0018 (GPS asymmetry)** — boss decision required (Reading A vs B). The audit found de facto Reading B without Reading B's consent wording or regression test (F-29). Put on the v10 agenda with a deadline; if no decision, codify the de facto state as Reading B *with* its safeguards (consent-prompt language + test) so behavior and paper trail match.
- **ADR 0019 (cost gate tier binding)** — implement or retire (F-08). Implementing requires a router change (the tier≥3 short-circuit at `router.py:768` makes child-side compliance dead code) plus estimator branches in 8 children. Retiring requires removing the ADR 0019 citation from `walkthrough/layer.py:186` and adding per-tool zero-cost docstrings. Recommend: retire-and-document unless a real deployment hits a tier-2 cost incident — the 35k threshold has never fired on tier 2 in practice, and the walkthrough citation is the only live surface treating it as law.
- **ADR 0020 (typed Protocols)** — recommend formal retirement. Zero Protocols exist after four version cycles; the one predicted seam shipped as an ABC and works; mypy is informational. *Stub:* "Status: Retired 2026-06 without implementation. The ABC pattern (`LocalLLMBackend`) plus the subprocess wire-test suite (ADR 0016) covered the signature-drift failure class this ADR targeted; no drift incident has occurred that Protocols would have caught and the wire tests did not. Reversal condition: a cross-component signature-drift bug that reaches a release despite the wire suite."

## Workstream 4 — Finish the domain-agnostic flip below the surface (the v10 headline; ~1 week)

v9 renamed identifiers; the core still *narrates* health (F-03, F-11, F-39). In leverage order:

1. **Core docstring sweep** (F-03): the seven "Biosensor-to-LLM Framework" module titles + the self-contradicting `framework/__init__.py` description. Pure text; zero behavior risk; removes the most embarrassing falsifiable claim ("the vocabulary matches the architectural commitment") first.
2. **Vault writer/renderer extraction** (F-11): empty the `strava_*` seed dict in `vault/writer.py:103-105` by registering those renderers from the running child via the existing `register_renderer` seam (`writer.py:134`); move the run/HR rendering suite (`renderer.py:113-885`) toward `children/running/` or a recipe module. This completes what ADR 0021 demanded and ADR 0038 started; it is the only workstream item with real code risk — gate it with vault-smoke-validator + mcp-protocol-auditor.
3. **Run-shaped vault tool names** (F-11): execute ADR 0038's `vault_get_fitness_summary` removal trigger check; decide rename-vs-alias for `vault_annotate_run` / `vault_list_anomalies` descriptions ("runs" → "source notes"). Tool renames are breaking — batch them so v10's major bump pays the break cost once, alongside any ADR 0019 outcome.
4. **Gate-language genericization** (F-39): ConsentGate "biometric consent" strings, `interfaces.py` defaults (`data_types=["biometric data"]`), router consent/revoke messaging, walkthrough section narration, setup_help strava assumptions, `~/biosensor-pilot` example path. Decide one vocabulary ("source-data consent") and sweep.
5. **`entity_id` coercion unification** (F-17): route all seven framework dispatchers through `_coerce_entity_id`. Small, but it is the ADR 0002/0009 scoping primitive and the divergence is live.
6. **pyproject identity nits** (F-25): drop/swap the `Medical Science Apps.` classifier; rewrite the package-data comments that present removed verbs as live rationale.

## Workstream 5 — Pipeline correctness debt (~2–3 days)

1. **Cost-approval affordance** (F-07): the wire promises "Reply 'full' to proceed" with no executable path. Either implement a session-scoped `approve_cost_<domain>` tool (mirroring the auto-generated consent pair) or change the wire copy to name the real levers (tier-2 alternative; operator-side `cost_threshold`) and amend ADR 0005. Recommend implementing: the consent-gate twin already establishes the pattern, and "approve-to-proceed" is the documented design intent.
2. **Audit rows on probe paths** (F-23): `UNKNOWN_TOOL` / `UNKNOWN_DOMAIN` outcomes for unknown-tool dispatch, unknown-domain consent approve/revoke, unregistered-owner, and vault-via-internal refusals. Cheap, and consent-surface probing is exactly what ADR 0001's IRB reviewer wants reconstructable.
3. **Legacy-migration tests** (Needs-verification #1): add pytest coverage for the `subject_id` → `entity_id` ALTER TABLE path and the frontmatter alias — the v9 banner claims these were "verified" but nothing in tests/ exercises them.
4. **Demo bypass containment** (F-21): route `demo/runner.py` section 1 through `dispatch_internal` (or mark the ungated path explicitly); stop calling private `router._dispatch` from outside the router.
5. **Hook-failure comment fix** (F-35) and ADR 0007's missing snapshot-staleness field in `vault_health_check` (F-36): implement the small field or amend the ADR.

## Workstream 6 — Low-leverage debt (fold into touched-file work; no dedicated effort)

- Stale test names (`TestPHIScrubber*`, `test_csv_cohort_summary_*`) — rename when next editing those files (F-32).
- Dormant `resting_hr` config knob — wire into HR analysis or remove from docs/`tailor status` (F-34).
- Vestigial `child._router` attribute — remove or document (F-34).
- Same-named dual `_write_user_config` (pilot deep-merge vs fitting_room sandbox) — rename the sandbox one (F-34).
- One-shot rename scripts under `scripts/` — keep `rename_for_public_flip.py` (checked in by design), consider pruning the other two same-family migration artifacts.
- ADR 0024's "setup.py is removed" sentence vs the existing wrapper (F-38); ADR 0003's unfulfilled examples/-subclass sentence — land a ~20-line example `DataScrubber` subclass or strike (F-37).

---

## Suggested v10 release shape

| Order | Workstream | Risk | Gate |
|---|---|---|---|
| 1 | WS1 release-record + claims | none (docs) | boss-report-auditor on the claims diff |
| 2 | WS2 recipient breakage | low (strings, agent files, cue card) | cue-card-rehearsal-auditor |
| 3 | WS3 ADR reconciliation | none (ADR files) | adr-weigher on retirement decisions; boss sign-off on 0018/0019/0020 |
| 4 | WS5 pipeline debt | low-med | mcp-protocol-auditor (mandatory: touches router.py) + phi-irb-risk-reviewer (consent/audit paths) |
| 5 | WS4 domain-agnostic core | med (vault extraction; tool renames are breaking) | vault-smoke-validator + mcp-protocol-auditor + integration-auditor |
| 6 | WS6 opportunistic | none | — |

WS4 items 3 (tool renames) and the ADR 0019 outcome are the only breaking changes on the table — they justify the major-version bump and should land together, with WS1–WS3 shippable earlier as v9.0.x patches if desired. Total estimate: WS1–WS3 ≈ 3 days of focused work; WS4–WS5 ≈ 2 weeks including gate runs.

The boss-owned decisions in this plan: ADR 0018 Reading A/B; ADR 0019 implement-vs-retire; ADR 0020 retirement; the legacy mirror URL (F-27); coverage-floor enforce-vs-descope (F-06); cost-approval implement-vs-rewrite (F-07); restore-vs-relocate the README AGPL summary (F-18).
