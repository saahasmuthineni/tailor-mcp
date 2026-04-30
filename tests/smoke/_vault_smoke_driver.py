"""
Vault smoke driver — v6.1.0+
Exercises correction propagation idempotency, dashboard dual-output (ADR 0007),
dashboard freshness stamps, and kind-filter roundtrip.

Run:
    python tests/smoke/_vault_smoke_driver.py
"""
import asyncio
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from biosensor_mcp.framework.vault.layer import VaultLayer
from biosensor_mcp.framework.vault.writer import VaultWriter


def run(c):
    return asyncio.run(c)


failures: list[tuple[str, str]] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    status = "PASS" if cond else "FAIL"
    suffix = f"  -- {detail}" if (not cond and detail) else ""
    print(f"{status}  {label}{suffix}")
    if not cond:
        failures.append((label, detail))


vault_dir = Path(tempfile.mkdtemp(prefix="bio_vault_smoke_"))
data_dir = Path(tempfile.mkdtemp(prefix="bio_data_smoke_"))
print(f"vault: {vault_dir}")
print(f"data:  {data_dir}")
print()

writer = VaultWriter(vault_path=vault_dir, data_dir=data_dir, vaultable_tools=set())
layer = VaultLayer(vault_path=vault_dir, vault_writer=writer)

try:
    # ════════════════════════════════════════════════════════════
    # BLOCK A — Correction propagation idempotency
    # ════════════════════════════════════════════════════════════
    print("--- Block A: Correction propagation idempotency ---")

    # A.1  Create theme 'drift'
    res = run(layer.execute("vault_upsert_theme", {
        "slug": "drift",
        "hypothesis": "H — cardiac drift as a marker of fatigue accumulation",
        "evidence": "E0 — initial observation from session 1.",
    }))
    check("A.1 theme created", res.get("created") is True, str(res))

    # A.2  Parse the evidence timestamp from the written file
    theme_body = (vault_dir / "themes/drift.md").read_text(encoding="utf-8")
    ts_match = re.search(r"### Evidence\s*[—\-]+\s*(\S+)", theme_body)
    check("A.2 evidence timestamp found", ts_match is not None,
          "regex did not match '### Evidence — <ts>' in theme body")
    if not ts_match:
        sys.exit(1)
    ev_ts = ts_match.group(1)
    print(f"     evidence_timestamp = {ev_ts}")

    # A.3  Capture three moments that wikilink to [[drift]]
    for tag in ("a", "b", "c"):
        mres = run(layer.execute("vault_capture_moment", {
            "title": f"M-{tag}",
            "body": f"See [[drift]] tag={tag}.",
            "linked_themes": ["drift"],
            "date": "2026-04-29",
        }))
        check(f"A.3 moment M-{tag} captured", mres.get("captured") is True, str(mres))

    # A.4  First correction with propagate=True
    corr1 = run(layer.execute("vault_correct_evidence", {
        "theme_slug": "drift",
        "evidence_timestamp": ev_ts,
        "correction": "Replace observation with corrected value.",
        "propagate": True,
    }))
    check("A.4 correction call succeeded", corr1.get("corrected") is True, str(corr1))

    # A.5  Exactly 3 files received the propagated callout
    propagated = corr1.get("propagated_to", [])
    check("A.5 propagated to 3 files",
          len(propagated) == 3,
          f"got {len(propagated)}: {propagated}")

    # A.6  For each propagated note: Corrections section, [!warning], marker once
    marker_token = f"[CORRECTED-EV {ev_ts}]"
    for p in propagated:
        content = (vault_dir / p).read_text(encoding="utf-8")
        check(f"A.6 {p} has '## Corrections'",
              "## Corrections" in content)
        check(f"A.6 {p} has '> [!warning]'",
              "> [!warning]" in content)
        n_markers = content.count(marker_token)
        check(f"A.6 {p} marker count == 1 (first run)",
              n_markers == 1, f"count={n_markers}")

    # A.7  Re-run identical correction — idempotency: marker count stays at 1
    corr2 = run(layer.execute("vault_correct_evidence", {
        "theme_slug": "drift",
        "evidence_timestamp": ev_ts,
        "correction": "Re-run with same args.",
        "propagate": True,
    }))
    check("A.7 second correction call succeeded", corr2.get("corrected") is True, str(corr2))
    for p in propagated:
        content = (vault_dir / p).read_text(encoding="utf-8")
        n_markers = content.count(marker_token)
        check(f"A.7 {p} marker count == 1 (idempotent)",
              n_markers == 1, f"count={n_markers}")

    # ════════════════════════════════════════════════════════════
    # BLOCK B — Dashboards dual-output (ADR 0007)
    # ════════════════════════════════════════════════════════════
    print()
    print("--- Block B: Dashboards dual-output (ADR 0007) ---")

    # B.1  Seed a failure-mode so active-failure-modes dashboard has ≥1 row
    fm_res = run(layer.execute("vault_log_failure_mode", {
        "slug": "fm-x",
        "symptom": "Abnormal HR spike during rest",
        "diagnosis": "Sensor noise from device movement",
        "mitigation": "Apply 5-second rolling median filter",
    }))
    check("B.1 failure-mode created", fm_res.get("created") is True, str(fm_res))

    # B.2  vault_refresh_dashboards (with_dataview_blocks=True, the default)
    dash_res = run(layer.execute("vault_refresh_dashboards", {}))
    check("B.2 refresh call succeeded", dash_res.get("refreshed") is True, str(dash_res))

    # Verify each dashboard file
    before_utc = datetime.now(timezone.utc)
    dashboard_names = ("open-themes", "active-failure-modes", "recent-moments")
    for dname in dashboard_names:
        dash_path = vault_dir / "dashboards" / f"{dname}.md"
        check(f"B.2 {dname}.md exists", dash_path.exists())
        if not dash_path.exists():
            continue
        c = dash_path.read_text(encoding="utf-8")

        check(f"B.2 {dname} has '## Snapshot'", "## Snapshot" in c)
        check(f"B.2 {dname} has dataview fence", "```dataview" in c)

        # Snapshot table: header + separator + (≥1 data row OR placeholder)
        has_table_header = bool(re.search(r"^\|.+\|$", c, re.MULTILINE))
        has_separator = bool(re.search(r"^\|[-|]+\|$", c, re.MULTILINE))
        has_data_or_placeholder = (
            bool(re.search(r"^\|(?!\s*[-]+\s*\|).*\|$", c, re.MULTILINE))
            or "*(No rows.)*" in c
        )
        check(f"B.2 {dname} snapshot table header present", has_table_header)
        check(f"B.2 {dname} snapshot table separator present", has_separator)
        check(f"B.2 {dname} snapshot has data or placeholder",
              has_data_or_placeholder)

        # Freshness: last_updated within 60s of now
        lu_match = re.search(r'last_updated:\s*"([^"]+)"', c)
        check(f"B.2 {dname} has last_updated frontmatter", lu_match is not None,
              "last_updated key not found in frontmatter")
        if lu_match:
            ts_str = lu_match.group(1).replace("Z", "+00:00")
            ts_dash = datetime.fromisoformat(ts_str)
            age = before_utc - ts_dash
            check(f"B.2 {dname} freshness (<60s)", abs(age) < timedelta(seconds=60),
                  f"age={age}")

    # B.3  vault_refresh_dashboards with_dataview_blocks=False
    dash_no_dv = run(layer.execute("vault_refresh_dashboards", {"with_dataview_blocks": False}))
    check("B.3 refresh(no_dv) succeeded", dash_no_dv.get("refreshed") is True, str(dash_no_dv))
    check("B.3 with_dataview_blocks=False echoed", dash_no_dv.get("with_dataview_blocks") is False,
          str(dash_no_dv.get("with_dataview_blocks")))

    for dname in dashboard_names:
        dash_path = vault_dir / "dashboards" / f"{dname}.md"
        if not dash_path.exists():
            check(f"B.4 {dname} still exists after no-dv refresh", False, "file missing")
            continue
        c = dash_path.read_text(encoding="utf-8")
        check(f"B.4 {dname} snapshot still present", "## Snapshot" in c)
        check(f"B.4 {dname} dataview fence removed", "```dataview" not in c,
              "```dataview block still present")

    # ════════════════════════════════════════════════════════════
    # BLOCK C — Kind-filter roundtrip
    # ════════════════════════════════════════════════════════════
    print()
    print("--- Block C: Kind-filter roundtrip ---")

    fm_list = run(layer.execute("vault_list_notes", {"kind": "failure_mode"}))
    check("C vault_list_notes(failure_mode) count >= 1",
          fm_list.get("count", 0) >= 1,
          f"count={fm_list.get('count')}")
    if fm_list.get("notes"):
        kinds = [n.get("note_type") for n in fm_list["notes"]]
        all_match = all(k == "failure_mode" for k in kinds)
        check("C all returned notes have note_type=failure_mode",
              all_match, f"note_types found: {set(kinds)}")

    dsh_list = run(layer.execute("vault_list_notes", {"kind": "dashboard"}))
    check("C vault_list_notes(dashboard) count >= 3",
          dsh_list.get("count", 0) >= 3,
          f"count={dsh_list.get('count')}")
    if dsh_list.get("notes"):
        kinds = [n.get("note_type") for n in dsh_list["notes"]]
        all_match = all(k == "dashboard" for k in kinds)
        check("C all returned notes have note_type=dashboard",
              all_match, f"note_types found: {set(kinds)}")

    # ════════════════════════════════════════════════════════════
    # BLOCK D — Vault subject-keying (ADR 0009)
    # ════════════════════════════════════════════════════════════
    print()
    print("--- Block D: Vault subject-keying (ADR 0009) ---")

    # D.1  Create P004-scoped theme; subject in frontmatter + evidence block
    res = run(layer.execute("vault_upsert_theme", {
        "slug": "p004-drift",
        "hypothesis": "P004 shows late-run HR drift",
        "evidence": "Mile-15 split shows +6 bpm",
        "subject_id": "P004",
    }))
    check("D.1 P004 theme created", res.get("created") is True, str(res))
    p004_body = (vault_dir / "themes/p004-drift.md").read_text(encoding="utf-8")
    check("D.1 P004 frontmatter carries subject_id",
          'subject_id: "P004"' in p004_body)
    check("D.1 P004 evidence block carries Subject blockquote",
          "> Subject: P004" in p004_body)

    # D.2  Set-once invariant — reassignment to P007 must fail
    reassign = run(layer.execute("vault_upsert_theme", {
        "slug": "p004-drift",
        "evidence": "Trying to retarget to P007",
        "subject_id": "P007",
    }))
    check("D.2 reassignment rejected with set-once error",
          "error" in reassign and "set-once" in reassign["error"],
          str(reassign))

    # D.3  Cross-subject theme (no subject_id) — frontmatter has no field
    run(layer.execute("vault_upsert_theme", {
        "slug": "cohort-hypothesis",
        "hypothesis": "Cohort-level claim",
        "evidence": "Cohort observation",
    }))
    cohort_body = (vault_dir / "themes/cohort-hypothesis.md").read_text(encoding="utf-8")
    check("D.3 cohort theme omits subject_id frontmatter",
          "subject_id:" not in cohort_body)

    # D.4  Subject-filtered list_themes returns matching + NULL (cohort), not P007's
    run(layer.execute("vault_upsert_theme", {
        "slug": "p007-only",
        "hypothesis": "P007-specific",
        "evidence": "P007 evidence",
        "subject_id": "P007",
    }))
    filtered = run(layer.execute("vault_list_themes", {"subject_id": "P004"}))
    slugs = {t["slug"] for t in filtered.get("themes", [])}
    check("D.4 list_themes(P004) includes P004's theme",
          "p004-drift" in slugs, f"slugs={slugs}")
    check("D.4 list_themes(P004) includes cohort theme (IS NULL branch)",
          "cohort-hypothesis" in slugs, f"slugs={slugs}")
    check("D.4 list_themes(P004) excludes P007's theme",
          "p007-only" not in slugs, f"slugs={slugs}")

    # D.5  Promotion: cross-subject -> subject-scoped is allowed
    promo = run(layer.execute("vault_upsert_theme", {
        "slug": "cohort-hypothesis",
        "evidence": "Subject-specific follow-up",
        "subject_id": "P004",
    }))
    check("D.5 promotion succeeded (no error)",
          "error" not in promo, str(promo))
    promoted_body = (vault_dir / "themes/cohort-hypothesis.md").read_text(encoding="utf-8")
    check("D.5 promoted theme now carries subject_id",
          'subject_id: "P004"' in promoted_body)

finally:
    layer.close()

# ════════════════════════════════════════════════════════════
# REPORT
# ════════════════════════════════════════════════════════════
print()
print(f"=== VAULT SMOKE — failures: {len(failures)} ===")
if failures:
    print(f"vault: {vault_dir}")
    print(f"data:  {data_dir}")
    print("(temp dirs left in place for inspection)")
    for label, detail in failures:
        detail_str = f"  -- {detail}" if detail else ""
        print(f"  - {label}{detail_str}")
    sys.exit(1)
else:
    print("ALL PASS")
    print(f"vault: {vault_dir}")
    print(f"data:  {data_dir}")
    sys.exit(0)
