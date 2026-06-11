import asyncio
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tailor.framework.vault.layer import VaultLayer
from tailor.framework.vault.writer import VaultWriter


def run(c): return asyncio.run(c)

failures: list[tuple[str, str]] = []
def check(label: str, cond: bool, detail: str = ""):
    print(f"{'PASS' if cond else 'FAIL'}  {label}{('  -- ' + detail) if not cond else ''}")
    if not cond:
        failures.append((label, detail))

vault_dir = Path(tempfile.mkdtemp(prefix="bio_vault_smoke_"))
data_dir  = Path(tempfile.mkdtemp(prefix="bio_data_smoke_"))
print(f"vault: {vault_dir}\ndata:  {data_dir}\n")

writer = VaultWriter(vault_path=vault_dir, data_dir=data_dir, vaultable_tools=set())
layer  = VaultLayer(vault_path=vault_dir, vault_writer=writer)
try:
    # ---- Block A ----
    run(layer.execute("vault_upsert_theme", {
        "slug": "drift", "hypothesis": "H", "evidence": "E0",
    }))
    body = (vault_dir / "themes/drift.md").read_text(encoding="utf-8")
    ts = re.search(r"### Evidence -- (\S+)|### Evidence — (\S+)", body)
    ts = (ts.group(1) or ts.group(2)) if ts else None
    if not ts:
        check("A.2 evidence timestamp parsed", False, "regex did not match")
        sys.exit(1)
    for tag in ("a", "b", "c"):
        run(layer.execute("vault_capture_moment", {
            "title": f"M-{tag}",
            "body":  f"See [[drift]] tag={tag}.",
            "linked_themes": ["drift"],
            "date": "2026-04-29",
        }))
    res = run(layer.execute("vault_correct_evidence", {
        "theme_slug": "drift", "evidence_timestamp": ts,
        "correction": "Replace observation.", "propagate": True,
    }))
    check("A.5 propagated to 3 files",
          len(res["propagated_to"]) == 3,
          f"got {len(res['propagated_to'])}: {res['propagated_to']}")
    for p in res["propagated_to"]:
        c = (vault_dir / p).read_text(encoding="utf-8")
        check(f"A.6 {p} has Corrections section", "## Corrections" in c)
        check(f"A.6 {p} has [!warning]",          "> [!warning]" in c)
        n = c.count(f"[CORRECTED-EV {ts}]")
        check(f"A.6 {p} marker count == 1", n == 1, f"count={n}")
    run(layer.execute("vault_correct_evidence", {
        "theme_slug": "drift", "evidence_timestamp": ts,
        "correction": "Re-run.", "propagate": True,
    }))
    for p in res["propagated_to"]:
        c = (vault_dir / p).read_text(encoding="utf-8")
        n = c.count(f"[CORRECTED-EV {ts}]")
        check(f"A.7 {p} marker still 1 after re-run", n == 1, f"count={n}")

    # ---- Block B ----
    run(layer.execute("vault_log_failure_mode", {
        "slug": "fm-x", "symptom": "S", "diagnosis": "D", "mitigation": "M",
    }))
    run(layer.execute("vault_refresh_dashboards", {}))
    for n in ("open-themes", "active-failure-modes", "recent-moments"):
        c = (vault_dir / f"dashboards/{n}.md").read_text(encoding="utf-8")
        check(f"B.2 {n} has snapshot",  "## Snapshot" in c)
        check(f"B.2 {n} has dataview",  "```dataview" in c)
        m = re.search(r'last_updated:\s*"([^"]+)"', c)
        if m:
            ts_dash = datetime.fromisoformat(m.group(1).replace("Z", "+00:00"))
            age = datetime.now(timezone.utc) - ts_dash
            check(f"B.2 {n} fresh (<60s)", age < timedelta(seconds=60), f"age={age}")
        else:
            check(f"B.2 {n} has last_updated", False, "regex did not match")
    run(layer.execute("vault_refresh_dashboards", {"with_dataview_blocks": False}))
    for n in ("open-themes", "active-failure-modes", "recent-moments"):
        c = (vault_dir / f"dashboards/{n}.md").read_text(encoding="utf-8")
        check(f"B.4 {n} snapshot still present", "## Snapshot" in c)
        check(f"B.4 {n} dataview removed",       "```dataview" not in c)

    # ---- Block C ----
    fm  = run(layer.execute("vault_list_notes", {"kind": "failure_mode"}))
    dsh = run(layer.execute("vault_list_notes", {"kind": "dashboard"}))
    check("C failure_mode kind filter >=1", fm["count"] >= 1)
    check("C dashboard kind filter >=3",    dsh["count"] >= 3)

    # ---- Block D: Empty-vault fitness-summary remediation (fitting-room CLI removal) ----
    vault_dir_empty = Path(tempfile.mkdtemp(prefix="bio_vault_smoke_empty_"))
    data_dir_empty = Path(tempfile.mkdtemp(prefix="bio_data_smoke_empty_"))
    writer_empty = VaultWriter(vault_path=vault_dir_empty, data_dir=data_dir_empty, vaultable_tools=set())
    layer_empty = VaultLayer(vault_path=vault_dir_empty, vault_writer=writer_empty)
    try:
        res_empty = run(layer_empty.execute("vault_get_fitness_summary", {}))
        check("D.1 response has 'summary' key", "summary" in res_empty)
        check("D.2 response has 'note' key", "note" in res_empty)
        check("D.3 response has 'total_notes_in_vault' key", "total_notes_in_vault" in res_empty)
        check("D.4 response has 'weeks_back' key", "weeks_back" in res_empty)
        check("D.5 response has 'open_themes' key", "open_themes" in res_empty)
        check("D.6 response has 'recent_moments' key", "recent_moments" in res_empty)
        check("D.7 summary is 'Vault is empty.'", res_empty.get("summary") == "Vault is empty.")
        remediation = res_empty.get("note", "")
        check("D.8 remediation mentions tailor_fitting_room_scaffold",
              "tailor_fitting_room_scaffold" in remediation,
              f"remediation: {remediation[:80]}...")
        check("D.9 remediation does NOT mention 'tailor fitting-room'",
              "tailor fitting-room" not in remediation,
              f"remediation: {remediation[:80]}...")
    finally:
        layer_empty.close()
finally:
    layer.close()

print()
print(f"=== VAULT SMOKE -- failures: {len(failures)} ===")
if failures:
    print(f"vault: {vault_dir}\ndata:  {data_dir}")
    print("(temp dirs left in place for inspection)")
    for label, detail in failures:
        print(f"  - {label}  {detail}")
sys.exit(1 if failures else 0)
