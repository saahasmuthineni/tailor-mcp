"""
Bundled-fixture honesty check.

Verifies the bundled HIP Lab fixtures and the vault-layer code they depend
on still satisfy the v7.3.4-shipped commitments (snapshot.md indexed as
note_type=snapshot, S004 moment reachable from "subject four" prose,
renderer.py weekly-summary conditional, etc.). Standalone runnable — exits
0 on PASS / 1 on FAIL. Not auto-collected by pytest (underscore prefix).

If a future release changes the bundled fixtures or the vault-layer code
this check inspects, update the assertions here so it stays honest.
"""
import re
import sys
from pathlib import Path


def check(label: str, cond: bool, detail: str = ""):
    print(f"{'PASS' if cond else 'FAIL'}  {label}{('  -- ' + detail) if not cond else ''}")
    if not cond:
        return False
    return True

all_pass = True
repo_root = Path(__file__).parent.parent.parent

# ---- Verify fixture files exist ----
snapshot_file = repo_root / "src/tailor/_fixtures/cohort_demo_realistic/vault/snapshot.md"
moment_file = repo_root / "src/tailor/_fixtures/cohort_demo_realistic/vault/moments/2026-04-20-s004-emg-force-decoupling-suspected.md"

all_pass &= check("Fixture snapshot.md exists", snapshot_file.exists())
all_pass &= check("Fixture moment file exists", moment_file.exists())

# ---- Verify snapshot.md content ----
if snapshot_file.exists():
    snapshot_content = snapshot_file.read_text(encoding="utf-8")
    all_pass &= check("snapshot.md mentions 'subject four'", "subject four" in snapshot_content)
    all_pass &= check("snapshot.md cites ADR 0024", "ADR 0024" in snapshot_content)
    all_pass &= check("snapshot.md is note_type: snapshot", "note_type: snapshot" in snapshot_content)
    all_pass &= check("snapshot.md has Vault Snapshot heading", "# Vault Snapshot" in snapshot_content)

# ---- Verify moment file content ----
if moment_file.exists():
    moment_content = moment_file.read_text(encoding="utf-8")
    all_pass &= check("moment file mentions 'subject four'", "subject four" in moment_content)
    all_pass &= check("moment file entity_id is S004", 'entity_id: "S004"' in moment_content)
    all_pass &= check("moment file has S004 title", "S004" in moment_content)
    all_pass &= check("moment file references J Physiol 2024", "J Physiol" in moment_content and "2024" in moment_content)

# ---- Verify vault layer code changes ----
rescan_file = repo_root / "src/tailor/framework/vault/rescan.py"
layer_file = repo_root / "src/tailor/framework/vault/layer.py"
renderer_file = repo_root / "src/tailor/framework/vault/renderer.py"

# Check _infer_note_type snapshot special case
if rescan_file.exists():
    rescan_content = rescan_file.read_text(encoding="utf-8")
    all_pass &= check(
        "rescan.py _infer_note_type has snapshot special case",
        'if filename == "snapshot.md":\n        return "snapshot"' in rescan_content
    )

# Check layer.py _handle_fitness_summary non-running remediation
if layer_file.exists():
    layer_content = layer_file.read_text(encoding="utf-8")
    all_pass &= check(
        "layer.py has non-running remediation path",
        "No biosensor run data is registered in this deployment" in layer_content
    )
    all_pass &= check(
        "layer.py suggests fitting-room on empty vault",
        "tailor fitting-room" in layer_content
    )

# Check renderer.py conditional weekly summary
if renderer_file.exists():
    renderer_content = renderer_file.read_text(encoding="utf-8")
    all_pass &= check(
        "renderer.py weekly_summary is conditional",
        "if weekly:" in renderer_content and "v7.3.4" in renderer_content
    )

print()
print(f"=== Bundled fixture honesty check -- {'PASS' if all_pass else 'FAIL'} ===")
sys.exit(0 if all_pass else 1)
