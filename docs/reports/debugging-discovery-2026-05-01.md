# Debugging-discovery report — overnight 2026-05-01

**What this is:** the open-ended, adversarial-eye findings from six discovery agents that read the codebase with no framing lens, plus the red-team-reviewer's objection on the framing-driven audits. Findings the night did NOT fix because they need your eyes, your call on math/science semantics, or your call on architectural scope.

**Read this if:** you want to know what is *actually wrong* in the codebase right now, beyond what the framing-driven audits surfaced. Some of these are real defects waiting for the right fix; some are second-reader questions; some are noise the report deliberately preserves so you can downgrade them.

**Read [overnight-2026-05-01.md](overnight-2026-05-01.md) instead if:** you want what shipped, what's queued for your decision, and what's in the PR.

---

## Top 10 ranked findings

Ranked by: real defect × researcher impact × ease-of-fix.

### 1. `time_to_50pct_drop_s` peak-tie systematic bias — **HIGH** (CSV cohort tool, scientific validity)

`children/csv_dir/processing.py:97-107` and `:187-195`. Both `aggregate_metric` (cohort) and `force_decline_summary` (per-file) use `values.index(peak)` — first occurrence — for the peak index. For real isometric force traces (typical: ramp → plateau → decline), this systematically underreports time-to-50% by the plateau duration. The bias is non-uniform across subjects (stronger participants hold longer plateaus), creating a comparison-of-groups confound that defeats the cohort tool's framing.

The weigher refused this as ADR-shaped (it's a bug, not a decision among credible alternatives). The fix shifts Tier-1 numbers — the HIP-Lab demo's expected outputs change. Recommend: read the synthetic data generator at `examples/hip_lab_demo/` first to confirm whether the demo's force traces are trapezoidal (bias bites) or triangular (bias doesn't bite). Fix candidate: define peak-onset as the *last* sample within ε of max, OR the first index where the next K samples are monotonically non-increasing. Add a regression test with a synthetic ramp-plateau-decline trace.

### 2. Hook name resolution always returns `"function"` or `"method"` — **MEDIUM** (vault writer diagnostics)

`framework/router.py:561`. `getattr(hook, "__class__", type(hook)).__name__` always reaches the `__class__` branch (every Python object has one), and for a plain `def vault_writer_hook(...)` registered as a hook, `hook.__class__.__name__` is the literal string `"function"`. So when v6.5.0's M1 fix surfaces hook failures via `_meta.hook_warnings`, the `hook` field reads `{"hook": "function", ...}` — useless for diagnosis, defeating the M1 fix's intent.

Fix: `getattr(hook, "__qualname__", None) or getattr(hook, "__name__", None) or type(hook).__name__`. Test: register a top-level `def vault_writer_hook(...)` that raises and assert the hook name is `"vault_writer_hook"`, not `"function"`.

### 3. Vault `vault_correct_evidence` propagation is no-op on same-timestamp re-correction — **MEDIUM** (correction integrity)

`framework/vault/writer.py:553-558`. The propagation idempotency key is `(theme_slug, evidence_timestamp)`. A researcher who corrects the same evidence block twice with *different* `correction` text gets the second call silently dropped on every referencing note — first callout stays, second one disappears.

Fix: include a hash of the correction text (or `correction_timestamp`) in `marker_token`, or check more than one timestamp at once.

### 4. `csv_force_decline` error envelope inconsistency — **MEDIUM** (LLM/audit-log disagreement)

`children/csv_dir/processing.py:157-158` `force_decline_summary` returns `{"error": "no values"}` on empty input; `_handle_force_decline` (`children/csv_dir/child.py:862-865`) doesn't check this — caller gets `{"error": "no values", "filename": "...", "column": "...", "_meta": {...}}`. The router stamps `_meta` (treats as success), but the response has an `error` key (LLM treats as failure). Two readers disagree.

Fix: `_handle_force_decline` should `if "error" in summary: return summary` before stamping filename/column. Add a regression test with an empty-column CSV.

### 5. `cmd_serve()` silent CSV-child disable on user_config.json parse error — **HIGH** (researcher-facing failure)

`src/biosensor_mcp/__main__.py:74-108`. The `JSONDecodeError` branch prints the loud "vault integration disabled" banner, then falls through to line 104 where `csv_dir_config = _ucfg.get("csv_dir")` returns `None` because `_ucfg` was reset to `{}`. The CSV directory child silently un-registers — for a v6.2 / v6.5 multi-subject pilot user (the primary persona), this is a worse failure than vault disable, and there's no breadcrumb pointing at the parse error.

Fix: extend the banner to mention every disabled feature, OR fail-loud and refuse to start the server on parse error. Both options are tier-3 production-code changes; held for boss review.

### 6. `aggregate_metric` for `time_to_50pct_drop_s` silently drops cohort rows on length mismatch — **MEDIUM** (silent under-counts)

`children/csv_dir/child.py:803-804`, `_handle_cohort_summary`. `_numeric_values` skips rows where the column doesn't parse as float; `_extract_timestamps` returns one timestamp per row, or `None` for the whole list if any single row fails to parse. Result: on a CSV with even one non-numeric cell in the target column, `len(timestamps) != len(values)` and `aggregate_metric` silently returns `None` for `time_to_50pct_drop_s`. The cohort row drops into `n_missing` with no surfaced reason.

The same defect for `force_decline_summary` silently drops the entire timestamped branch (`peak_time_s`, `duration_s`, `decline_rate_per_min`, `time_to_50pct_drop_s` all absent on length mismatch). User probably won't notice for a while.

Fix: align extraction passes — zip rows and skip both timestamp+value when either is missing, and surface `n_dropped_rows` in the result.

### 7. Cross-tier GPS precision asymmetry — **HIGH, IRB-relevant** (already filed as ADR 0018)

See [ADR 0018](../adr/0018-cross-tier-gps-precision-asymmetry.md) and the morning briefing.

### 8. orjson stdlib fallback test does not exercise non-string-key dicts on the stdlib path — **MEDIUM** (latent regression risk)

The v6.4.1 banner cites a regression test for the stdlib JSON fallback, but the test (`tests/test_serve_mcp_protocol.py:500-519`) only round-trips a datetime. The orjson backend uses `OPT_NON_STR_KEYS`; the stdlib backend silently coerces int keys to strings via Python's default `JSONEncoder`. Both round-trip int keys correctly *today*, but no test asserts behavioral parity — a future stdlib-path divergence (e.g. on `frozenset` keys, on `dataclass` instances) would silently regress.

The existing `TestJSONBackendCoercion` tests int-keyed dicts but only against whichever backend is loaded. A second test forcing the stdlib path via `importlib.reload` and asserting the same int-key behavior would close the gap.

### 9. `metadata.json` filename-key validation — **MEDIUM** (cohort silent under-counts)

`children/csv_dir/child.py:705-734` `_load_metadata_sidecar`. Schema check confirms each *value* is a dict, but the *keys* are trusted as filenames. A typo (`p001.csv` vs `P001.csv` on a case-sensitive filesystem; or `P001.CSV`; or stale entries for files since deleted) silently drops the file into `missing_metadata`. There is *no* audit signal saying "your metadata sidecar references P001.csv but no such file exists in the directory" — a hostile or careless metadata.json can quietly drop subjects from the cohort.

Fix: compute `metadata_filenames - actual_files` once and surface as `unknown_metadata_files` on the result. Cheap, no behavior change, makes the failure mode visible.

### 10. OAuth refresh race in `strava_api.py` — **MEDIUM, deferred to boss**

See morning briefing § 4. The boss owns the framework concurrency-model decision.

---

## Per-module findings (full)

### Router (D1)

`framework/router.py` — read all 1025 lines. The file is in better shape than its size suggests; v6.4.x / v6.5.0 audit churn has clearly hardened it. Genuine findings are few.

**LIKELY:**
- (#2 above) hook name resolution always returns `"function"`
- `:961-971` purge-success vs failure audit-row asymmetry — on success, both `PURGE_CACHE` and `revoke_consent_<domain>` `SUCCESS` rows are written; on `PURGE_FAILED`, only the failure row exists, no `revoke_consent_<domain>` row. ADR 0013 specifies "paired audit rows" but the pairing exists only on the success path.

**WORTH A LOOK:**
- `:631, 643` and `:311, 324` — `subject_id` recomputed from `cleaned`; if a child's `param_schemas` doesn't declare `subject_id`, the post-validation read may zero the audit scoping the pre-validation read had captured (incremental ADR 0009 wiring → silent un-scoped audit rows on legacy children)
- `:285-288` consent prefix-match accepts any future tool named `approve_consent_foo`; namespace collision guard exists on `_tool_map` but not on dispatch
- `:298, 707, 710` `_tool_map` has no architectural guard against in-flight mutation
- `:530-531` `record_success` and `ledger.add` happen *before* `_audit.record` — drift between observable state and durable record on audit failure
- `:896` `arguments.get("force_revoke", False)` accepts any truthy value (LLM may pass `"yes"` or `1` and bypass the ADR 0013 fail-closed default)
- `:599, 684, 833` `log.error(..., exc_info=True)` writes traceback to stderr (invisible on Claude Desktop per CLAUDE.md)
- `:823` `dispatch_internal` returns dict directly; callers can't distinguish a child returning `{"error": ...}` as a valid result from a router-level error

### Security / Audit / Cost (D2)

**DEFINITELY:**
- (#8 above) orjson stdlib fallback test does not exercise non-string-key contract
- `security.py:231-241` PHIScrubber `_noop_warning_emitted` once-only contract has no test (**fixed tonight** via `test_noop_warning_emitted_at_most_once_per_process`)

**LIKELY:**
- `security.py:54-61` `ValidationSchema.default` not run through type-coercion / range checks before insertion; `default=0` with `min=10, max=20` accepts the default without flagging
- `security.py:65-93` `ValidationSchema.type` only handles `int / str / list`; `float`, `bool`, `dict` silently fall through with no validation
- `security.py:80-94` `list` validation order-of-check (min_len vs allowed_values) is undocumented
- `audit.py:131-166` schema migration `ALTER TABLE` runs outside transaction guard
- `audit.py:168-180` `close()` only closes current thread's connection; worker-thread connections leak on Windows shutdown
- `cost.py:46-63` `humanize` divides by `TYPICAL_CALL_TOKENS` (800) without zero-guard
- `cost.py:107-110` `estimate_tokens` falls through to `_dumps`, which raises `TypeError` for unsupported types — pre-v6.5.0 was silent (`default=str`); breaking change

**WORTH A LOOK:**
- `security.py:137-144` CircuitBreaker `record_success` clears `_failures` but not `_tripped`
- `security.py:166-189` `ConsentGate` has no lock around mutation
- `audit.py:55-77` `_wire_default` for `bytes` decodes utf-8 with `errors="replace"` — silently corrupts binary payloads
- `audit.py:188-218` `record()` uses positional `?` placeholders — column rename in future would silently swap fields
- `cost.py:73-83` `TokenLedger._entries` unbounded list growth across long sessions

### Vault layer (D3)

**DEFINITELY:**
- (#3 above) correction propagation no-op on same-timestamp re-correction
- `writer.py` read-modify-write race in `_merge_theme_frontmatter` — discovery agent's cited file:line was unreproducible (the function name doesn't appear in `writer.py`); the adr-weigher REJECTed C5 with "evidence-not-reproducible." **Re-investigation needed: D3 may have intended `framework/vault/layer.py` rather than `writer.py`.**
- `parser.py:48-52` frontmatter parser strips leading `\n` from body; a body starting with a literal `---` markdown rule on its own line corrupts parsing (closing-fence search at `parser.split_frontmatter:44` grabs the first `---` after frontmatter)
- `layer.py:1225-1264` `vault_search_notes` cross-domain leakage — when called with no `kind`, lazy revalidate path issues N stats + N reads with no early-out; on slow filesystem (network share, iCloud Drive) this is multi-second wall time, and `revalidate_file` swallows IOErrors silently so partial outage looks like "no matches"

**LIKELY:**
- `storage.py:466-477` + `layer.py:2230` "stale theme" definition flags any theme with no activity in 30 days regardless of confidence — high-confidence resolved-pending themes get noisy false positives on health-check
- `writer.py:538-577` correction propagation has no concurrency guard while `vault_rescan` may be re-indexing
- `writer.py:1060-1069` `_safe_path` defended via `is_relative_to`; symlink hazard is real on Linux/macOS but the explicit check holds. Same pattern in `_handle_read_note` (`layer.py:1206`) — only `_is_relative_to`, not full resolve
- `writer.py:743-750` `_replace_yaml_tags` regex doesn't escape `:` in tags — a tag containing colon corrupts YAML
- `layer.py:2745-2780` `vault_traverse_links` records edges before checking visited set — depth-1 results may contain edges to nodes never expanded

**WORTH A LOOK:** see full D3 findings excerpted in adr-weigher logs; 7 worth-a-look items including code-block-aware evidence counting, propagation idempotency window width, inbox-drain index drift, renderer YAML scalar escape gaps, capture-session subject_id propagation, dashboard timestamp duplication risk, top-level-file unknown note-type classification.

### csv_dir child (D4)

**DEFINITELY:**
- (#1 above) `time_to_50pct_drop_s` peak-tie systematic bias
- (#4 above) `csv_force_decline` error envelope inconsistency

**LIKELY:**
- (#6 above) `aggregate_metric` silent row-drop on length mismatch
- `child.py:399-403` `csv_force_decline` `column` parameter validated against `self._column_names`, computed at init from the *first CSV's* auto-detect — heterogeneous CSVs (P001 has `force_n`, P003 has `force_kg`) get rejected at the gate even though the per-file handler would otherwise read happily
- (#9 above) `metadata.json` filename-key validation

**WORTH A LOOK:**
- `child.py:752-754` malformed-sidecar wrapping is sound — checked, OK
- `child.py:763-770` `MAX_COHORT_FILES = 64` cap fires before metadata filtering — confusing UX when 100 CSVs exist but cohort metadata only declares 30

### running child (D5)

**DEFINITELY:**
- (#7 above) cross-tier GPS precision asymmetry — filed as ADR 0018
- (#10 above) OAuth refresh race — DEFERed for boss
- `child.py:529-530` cost gate not wired for Tier-2 — filed as ADR 0019

**LIKELY:**
- `processing.py:152-161` HR-zone boundary off-by-one when `hr/max_hr` is exactly 0.6/0.7/0.8/0.9; the boundary goes to the lower zone (`pct <= upper`); seconds-per-zone misallocation for runners whose data lands exactly on boundaries
- `strava_api.py:91-97, 175-176` rate-limiter persistence is non-atomic `write_text`; concurrent `get()` calls partial-overwrite or corrupt JSON
- `child.py:106-128` stream cache TTL measured against `fetched_at` not `activity.start_date` — re-sync after 8-day vacation re-fetches every immutable stream; wastes Strava API quota
- `child.py:603-622` `_handle_sync` pagination has no upper bound; `days_back=365` for a serious athlete (300+ runs) hits 6+ pages with no resume marker on rate-limit failure
- `processing.py:297-302` `compute_decoupling` divides by velocity without low-velocity floor guard; stop-heavy run can produce thousands-of-percent decoupling

**WORTH A LOOK:**
- `child.py:725` `_handle_stop_analysis` re-reads user_config inside handler (cached at `__init__` for max_hr); inconsistency yields different `distance_from_home_m` across sessions if config edited mid-session
- `processing.py:182` `compute_hr_drift` doesn't guard `first_half == 0`
- `processing.py:467-483` spike detection 30-second cooldown can fire on the *first* iteration since `last_spike_second = -30`
- `child.py:868-870` `strava_compare_runs` swallows API errors silently; LLM gets a row with `name=""` and `distance_miles=0`
- `child.py:190` docstring claims "Exposes: 13 tools" but `tool_definitions` returns 12

### CLI / pilot / wizard (D6)

**DEFINITELY:**
- C9 — macOS iCloud canonical paths missed (**fixed tonight** in pilot.py + __main__.py)
- (#5 above) `cmd_serve()` silent CSV-child disable on parse error

**LIKELY:**
- `wizard.py:30, 116-117` OAuth callback server has no port-collision handling; binds before printing the URL; `server.timeout = 120` set but never honored by the busy-wait loop on `auth_code[0] is None`
- `pilot.py:482-494` `_smoke_check` instantiates `CSVDirectoryChild(data_dir=CONFIG_DIR / "data")` instead of using the env-var-honoring `DATA_DIR` from `config.py` — env-var-set deployments get two databases, one materialized by the smoke check and a different empty one used at serve time
- `pilot.py:348-353` and `wizard.py:170` — atomic-write is `os.replace` on POSIX but Windows raises `PermissionError` if the destination is open; wizard.py's `tokens.json` write is plain `write_text`, not atomic-replace, so SIGINT mid-write leaves a zero-byte file
- `__main__.py:200-219` `cmd_status` prints `tokens.get('client_id')` in plaintext and surfaces `JSONDecodeError` body verbatim (which can include malformed-token-file content)

**WORTH A LOOK:**
- `config.py:78-80` `CONFIG_DIR = config_dir()` runs at import time; tests using `BIOSENSOR_CONFIG_DIR` env-var override after module import see the stale constant

---

## Red-team adversarial findings

[`red-team-reviewer`](../../.claude/agents/red-team-reviewer.md) pressure-tested wave-1's confident verdicts. Result: **1 OBJECTION RAISED, 3 VERDICTS UPHELD, 1 NO OBJECTION FOUND**.

The objection — **MEDIUM severity — confirms the cross-tier GPS leak**. The phi-irb-risk-reviewer's "0 VIOLATIONS, 2 WATCH" verdict scoped its check to Tier-1 surfaces hardened in v6.3.1 and missed the Tier-2/3 5-decimal residence-precision GPS in `processing.py:45`. Filed as [ADR 0018](../adr/0018-cross-tier-gps-precision-asymmetry.md).

Lower-severity OBJECTION on reproducibility-provenance-auditor's "13 HOLDS" verdict: the auditor's framing implicitly extended to Tier-1 *handler* paths, but `children/running/child.py:606` (`_handle_sync`, a Tier-1 handler) reads `datetime.now(timezone.utc)` to compute the Strava API window from `days_back`. The ADR 0008 invariant ("every method on `*Processing` is `@staticmethod` pure") literally holds — `*Processing` is clean — but the reader is left to assume Tier-1 calls reproduce, which is false for `strava_sync`. The invariant scope is processing-method-only, not Tier-1-call-only. Worth a one-line clarification in ADR 0008's scope language; deferred for a separate session.

---

## What this report does NOT do

- **Does not fix** any of the findings above except the four named on the morning briefing (3 ADRs + the 2 small fixes that landed). Production-code changes to `framework/` and most of `children/` are out of scope for the autonomous session.
- **Does not propose** comprehensive specialist additions; the [promotion-candidates memo](promotion-candidates-2026-05-01.md) covers that.
- **Does not retro-update** the ADR-weigher's REJECTs as "PASS later"; the boss owns the call to elevate any of these to ADR shape.

The cheapest immediate next moves, in order of researcher-impact-per-hour:

1. Pick a reading on ADR 0018 (HIGH, IRB-facing).
2. Apply the C3 peak-tie fix after confirming the demo's force-trace shape (HIGH, scientific validity).
3. Fix the hook name resolution at `framework/router.py:561` (MEDIUM, restores M1's diagnostic value).
4. Apply the C5 vault read-modify-write re-investigation (D3 cited an unreproducible file:line; re-dispatch with corrected target).
5. The remaining MEDIUM/LIKELY items can land on the next coverage-hardening release in the v6.5.x line.
