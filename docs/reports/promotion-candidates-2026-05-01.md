# Promotion-candidates memo — overnight 2026-05-01

**What this is:** the items the adr-weigher REJECTed as not-ADR-worthy that nevertheless deserve attention — bug-fix candidates, test-gap candidates, evidence re-investigation, and one specialist promotion candidate the night surfaced.

**Read this if:** you've already read the morning briefing and the discovery report and want the prioritized worklist for the v6.5.x → v6.6 cycle.

**Cap-status note:** [ADR 0017](../adr/0017-adr-weigher-and-autonomous-session-cap.md)'s autonomous-session ADR cap is six per session; the night used four. Any item below that you decide to elevate to ADR shape next session is well within budget — the cap was never the binding constraint, the weigher was.

---

## Bug-fix candidates (ADR-weigher REJECTed because they're bugs, not decisions)

### B1. `time_to_50pct_drop_s` peak-tie systematic bias — **HIGH severity, scientific validity**

`children/csv_dir/processing.py:97-107` and `:187-195`. See [debugging-discovery-2026-05-01.md § Top 10 finding 1](debugging-discovery-2026-05-01.md#1-time_to_50pct_drop_s-peak-tie-systematic-bias---high-csv-cohort-tool-scientific-validity) for the full description.

The fix is a 3-5 line change in two functions plus a regression test with a synthetic ramp-plateau-decline trace. The fix shifts Tier-1 numbers — the HIP-Lab demo's expected outputs change, and the v6.5.0 vault-smoke-validator seed-moment vault may need re-seeding.

**Recommended action:**
1. Read the synthetic data generator at `examples/hip_lab_demo/beta/generate.py` to confirm whether the demo's force traces are trapezoidal (bias bites) or triangular (bias doesn't bite). If triangular, the fix is post-mortem; the demo doesn't currently exhibit the bug.
2. Either way, apply the fix. The math is wrong for any real isometric data.
3. Add a regression test that asserts time_to_50% on a flat-top-trace = (time of first sample below 50% of plateau) − (time of plateau end), not (time of first sample below 50%) − (time of first sample at peak).
4. If the demo expected outputs shift, update the seed-moment vault and re-run vault-smoke-validator.

**Why this was REJECTed as ADR:** the decision-shape failed criterion 1 (no architectural alternatives among credible options); the math is wrong against the canonical "fatigue-onset = end of plateau" semantics. If the analyst contests the canonical semantics — e.g. proposes derivative-based onset detection or K-sample monotonic-decline thresholding — the *secondary* decision among those approaches becomes ADR-worthy. For tonight's fix, REJECTed; if a richer fatigue-onset definition emerges, file an ADR then.

### B2. `csv_force_decline` error envelope inconsistency — **MEDIUM severity, LLM/audit-log disagreement**

`children/csv_dir/child.py:862-865`. The handler doesn't check for `error` key in the processing result before stamping filename/column/`_meta`.

**Recommended action:** add `if "error" in summary: return summary` at the top of `_handle_force_decline` (after the validation step). Add a regression test in `tests/children/csv_dir/test_csv_dir_child.py` against an empty-column CSV that asserts the error envelope is consistent with the other handlers' shape.

**Why this was REJECTed as ADR:** mechanical fix, no alternatives lost. There is a *meta-question* that could become ADR-worthy if this same pattern recurs in 2+ other handlers — *"error envelopes do not carry `_meta` provenance"* would be an architecturally-codified convention. For tonight's batch with one cited instance, REJECTed and routed to local fix.

### B3. `cmd_serve()` silent CSV-child disable on user_config.json parse error — **HIGH severity, researcher-facing failure**

`src/biosensor_mcp/__main__.py:74-108`. On `JSONDecodeError`, the banner names "vault integration disabled" but the actual effect is "vault AND csv_dir disabled."

**Recommended action:** two acceptable fixes — (a) extend the banner to enumerate every disabled feature, OR (b) restructure to fail-loud and refuse to start the server on parse error. Option (b) is more defensible against future config-driven children but is a tier-3.5 production-code change that touches startup semantics. Add a regression test running `cmd_serve` against a corrupt user_config.json fixture that asserts both surfaces are named in the banner.

**Why this was REJECTed as ADR:** mechanical (extend the banner to mention both surfaces). The architectural pattern *"fail-loud is a project convention"* (already shipped in `scrubber_warning`, the v6.2.1 cloud-sync warning, etc.) could become ADR-worthy if a third instance surfaces in the next discovery wave. For tonight, REJECTed.

### B4. `csv_force_decline` heterogeneous CSV column rejection — **MEDIUM severity, multi-subject pilot UX**

`children/csv_dir/child.py:399-403`. `column` parameter validated against `self._column_names`, computed at init from the *first CSV's* auto-detect. If P001 has `force_n` and P003 has `force_kg`, the validator rejects `force_kg` even though the per-file handler would otherwise read happily. Same issue at `_handle_cohort_summary.column` (line 379-383).

**Recommended action:** drop the `allowed_values` constraint on `column` and let the per-file `if column not in headers: load_errors.append(...)` branch surface it. This branch already exists at `:796-801` and matches the existing `missing_metadata` / `missing_group_field` design.

**Why this was REJECTed as ADR:** the existing per-file fail-closed pattern already covers this; the validator is over-constraining without architectural reason.

### B5. `_handle_cohort_summary` length-mismatch silent row drop — **MEDIUM severity, silent under-counts**

`children/csv_dir/child.py:803-804`. `_numeric_values` and `_extract_timestamps` return mismatched-length lists when one row has a non-numeric value; `aggregate_metric` for `time_to_50pct_drop_s` silently returns `None` and the cohort row drops into `n_missing`.

**Recommended action:** align extraction passes — zip rows and skip both timestamp + value when either is missing, and surface `n_dropped_rows` in the result.

**Why this was REJECTed as ADR:** mechanical alignment fix; the *visibility* design (surfacing dropped-row counts) is the same pattern v6.5.0 already established with `missing_metadata` / `missing_group_field`. If the analyst-visibility convention itself is contested, that *is* ADR-worthy; for tonight, mechanical.

### B6. Hook name resolution at `framework/router.py:561` — **MEDIUM severity, defeats v6.5.0 M1 fix's intent**

See [debugging-discovery-2026-05-01.md § Top 10 finding 2](debugging-discovery-2026-05-01.md#2-hook-name-resolution-always-returns-function-or-method---medium-vault-writer-diagnostics).

**Recommended action:** change `getattr(hook, "__class__", type(hook)).__name__` to `getattr(hook, "__qualname__", None) or getattr(hook, "__name__", None) or type(hook).__name__`. Test: register a top-level `def vault_writer_hook(...)` that raises and assert `_meta.hook_warnings[0]["hook"] == "vault_writer_hook"`.

**Why this was on no candidate list initially:** discovery agent D1 flagged it; the night's batch focused on the larger architectural gaps. Promote to fix-list for the next coverage-hardening release.

### B7. `vault_correct_evidence` propagation no-op on same-timestamp re-correction — **MEDIUM severity, correction integrity**

`framework/vault/writer.py:553-558`. See [debugging-discovery-2026-05-01.md § Top 10 finding 3](debugging-discovery-2026-05-01.md#3-vault-vault_correct_evidence-propagation-is-no-op-on-same-timestamp-re-correction---medium-correction-integrity).

**Recommended action:** include hash of correction text (or `correction_timestamp`) in `marker_token`. Add a regression test: correct evidence at timestamp T with text A, then again at timestamp T with text B; assert both callouts appear in referencing notes.

---

## Test gaps (ADR-weigher REJECTed because adding a test is not a new decision)

### T1. `subject_id` post-rejection invariant — **FIXED tonight**

Already landed in commit `1414457`: `test_reassignment_rejection_does_not_mutate_file_or_evidence` in `tests/framework/vault/test_subject_keying.py`. Pins ADR 0009's atomicity guarantee.

### T2. orjson stdlib fallback non-string-key behavioral parity

`tests/test_serve_mcp_protocol.py:500-519` only round-trips a datetime on the stdlib path. Add a second test forcing `importlib.reload` after `monkeypatch.setitem(sys.modules, "orjson", None)`, then round-trip an int-keyed dict (`{1: "a", 2: "b"}`) and assert behavioral parity with the orjson backend. Closes the future-stdlib-divergence regression risk discovery agent D2 flagged.

### T3. Coverage-criticality-mapper's CRITICAL/HIGH targets not yet pinned

The mapper named four high-leverage tonight-eligible test gaps; tonight pinned two of them (T1 above + the int-coercion TypeError branch in `framework/security.py:65-69`). The remaining two — `framework/audit.py:195` (50KB params truncation path) and `framework/router.py:199-273` (`create_server()` schema construction) — are still uncovered. Both are tier-2 additive tests, no production-code change required. The truncation test can be a single parametrize row; the create_server test needs a mock `ChildMCP` registration.

---

## Re-investigation candidates

### R1. C5 — vault read-modify-write race (evidence-not-reproducible)

Discovery agent D3 cited `framework/vault/writer.py:1871` and `_merge_theme_frontmatter` as the read-modify-write race location. The function name does not appear in `writer.py`; line 1871 does not exist (file is 1085 lines). The adr-weigher REJECTed this with verdict "evidence-not-reproducible."

**Recommended action:** re-dispatch D3 (or `triage-debugger`) against the corrected target. The most likely intended file is `framework/vault/layer.py` (which is 2000+ lines, plausible for an 1871 reference). The actual race may be real; the cited evidence was wrong.

**Why on this list, not the bug list:** until the evidence reproduces, neither bug nor ADR is appropriate.

---

## Specialist promotion candidates

### S1. `vault-smoke-validator` to fire on every coverage-hardening release

`vault-smoke-validator` already exists. The promotion candidate is a *fire-cadence* expansion: it currently fires "after any change to `framework/vault/`," but the v6.5.0 demo seed-moment vault is the load-bearing artifact for the HIP-Lab demo, and any fix that shifts Tier-1 numbers (e.g. B1 above) must re-seed the demo and re-run the smoke validator. Promote the trigger from "any change to `framework/vault/`" to also include "any change to `children/csv_dir/processing.py` Tier-1 math."

**Maintenance estimate:** zero. The agent already exists; only the CLAUDE.md trigger row changes.

### S2. None other rise to the ADR 0011 promotion bar

The night did not surface any specialist promotion candidate that clears ADR 0011's structural-argument + severity grounding bar that the existing 14-agent roster does not already defend. The four research-utility / compliance backstops added in v6.3.0 plus the `mcp-protocol-auditor` from v6.5.0 plus tonight's `adr-weigher` (15 specialists total) cover the threat surface the night exercised.

If a third instance of "fail-loud convention" violations surfaces (B3 currently has one cited instance; if we count the `_meta.hook_warnings` "useless `function` field" as a fail-loud regression at B6, that's two), a `convention-discipline-auditor` specialist could be motivated. For tonight, premature.

---

## Summary action list (prioritized)

| # | Item | Severity | Effort | Where filed |
|---|---|---|---|---|
| 1 | Pick a reading on ADR 0018 (cross-tier GPS) | HIGH (IRB-facing) | 1h boss-decision | [ADR 0018](../adr/0018-cross-tier-gps-precision-asymmetry.md) |
| 2 | Apply B1 (peak-tie bias fix) after demo-shape check | HIGH (scientific validity) | 1-2h fix + test | This memo § B1 |
| 3 | Pick a reading on ADR 0019 (cost gate Tier binding) | MEDIUM | 30min boss-decision | [ADR 0019](../adr/0019-cost-gate-tier-binding.md) |
| 4 | Pick a reading on ADR 0020 (typed Protocols) | MEDIUM | 30min boss-decision | [ADR 0020](../adr/0020-typed-protocols-for-cross-component-seams.md) |
| 5 | Apply B6 (hook name resolution fix) | MEDIUM | 15min fix + test | This memo § B6 |
| 6 | Apply B5 (length-mismatch row drop) | MEDIUM | 30min fix + test | This memo § B5 |
| 7 | Decide framework concurrency model (deferred ADR) | MEDIUM | 30min boss-decision | Morning briefing § 4 |
| 8 | R1 (re-dispatch D3 on vault layer.py) | MEDIUM | 15min agent dispatch | This memo § R1 |
| 9 | T2 (orjson stdlib non-string-key parity test) | LOW | 15min test | This memo § T2 |
| 10 | Apply B2 (force_decline error envelope) | MEDIUM | 15min fix + test | This memo § B2 |
| 11 | Apply B3 (silent CSV disable) | HIGH (UX) | 30min fix + test | This memo § B3 |
| 12 | Apply B4 (heterogeneous column rejection) | MEDIUM | 15min fix | This memo § B4 |
| 13 | Apply B7 (correction propagation idempotency) | MEDIUM | 30min fix + test | This memo § B7 |
| 14 | T3 (audit truncation + create_server tests) | LOW | 1h tests | This memo § T3 |

Total estimated effort for items 1-14: ~10 hours of focused work, distributable across two coverage-hardening sub-releases (v6.5.1 + v6.5.2). The boss-decisions (#1, #3, #4, #7) are the gate; the rest of the list parallelizes once those land.
