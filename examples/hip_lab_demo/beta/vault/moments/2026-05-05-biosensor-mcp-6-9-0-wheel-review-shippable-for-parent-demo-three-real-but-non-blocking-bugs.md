---
domain: vault
note_type: moment
kind: moment
title: "biosensor-mcp 6.9.0 wheel review — shippable for parent demo, three real but non-blocking bugs"
slug: "biosensor-mcp-6-9-0-wheel-review-shippable-for-parent-demo-three-real-but-non-blocking-bugs"
date: "2026-05-05"
linked_runs: []
linked_themes: []
divergence: "Goal was to verify the wheel works for a recipient on another system. Drifted into a full bug hunt at user request, then a focused review of the MCP registration path. Outcome stronger than scope: shippable verdict + prioritized fix list, not just a yes/no on functionality."
generated_at: "2026-05-05T05:01:11Z"
tags:
  - moment
  - meta
  - code-review
  - release-readiness
  - windows-quickstart
  - session-summary
---
# biosensor-mcp 6.9.0 wheel review — shippable for parent demo, three real but non-blocking bugs

Sandbox-verified the 6.9.0 wheel end-to-end before sending the Windows quickstart PDF to my parent. Net: wheel is shippable as-is.

**What ran cleanly** (Linux venv, Python 3.10): `pip install`, `--help`, `status`, `demo`, `tour` (gracefully prints `register with Claude Desktop … skipped (Linux, or APPDATA missing)`), `serve` (router boots, all four children register, vault layer + 25 tools, local-LLM layer).

**Three verified bugs that don't block the parent demo:**

1. **Uninstall orphans the Claude Desktop entry.** `tour.py:273` registers under `biosensor-tour-{variant}`, but `__main__.py:438-439` only deletes `mcpServers['biosensor-mcp']`. After `pip uninstall biosensor-mcp` (which the PDF lists as cleanup), Claude Desktop keeps a `biosensor-tour-hip-lab` entry pointing at a missing binary → red MCP indicator. Fix: delete any key prefixed `biosensor-`.

2. **CSV readers don't strip UTF-8 BOM.** Every `open(...)` in `force_csv/child.py:761,780`, `emg_csv/child.py:673,691`, `csv_dir/child.py:157,532,555` uses `encoding='utf-8'` not `'utf-8-sig'`. Bundled fixtures don't have a BOM so the demo works fine, but any user-provided CSV that's been Excel-touched or PowerShell-redirected has its first column header silently become `﻿t_s`.

3. **`tour --force` doesn't wipe stale state.** `_copy_resource_tree` (tour.py:73-86) is `shutil.copy2` file-by-file, never removes anything. The PDF's troubleshooting tip relies on `--force` recovering from a broken scaffold; stale files survive. Fix: `shutil.rmtree(target_dir, ignore_errors=True)` at scaffold entry when `--force`.

**MCP registration is well-designed.** Two correct decisions: (a) `command: sys.executable, args: ['-m', 'biosensor_mcp', 'serve']` instead of bare `biosensor-mcp` — sidesteps the Windows PATH-not-inherited gotcha; (b) proper merge into existing config via `_read_claude_config` → `setdefault('mcpServers', {})` → `_write_claude_config`, with BOM preservation and atomic `os.replace`. Parent's existing MCP servers survive; missing parent dir gets created.

**Two non-blocking hardening tweaks if revisited:** print resolved `command`+`args` after `(4/4)` so the operator can eyeball; pre-write `.bak` of existing config since `_read_claude_config` returns `{}` on JSONDecodeError and silently overwrites.

Unverified findings from the broader sweep (passed through with appropriate hedging): `cohort_stats` over-counts when per-file scalar is None; `StravaAPI` rate-limit file write is non-atomic and the in-memory list lacks a lock; `VaultWriter.__call__` swallows exceptions to `_meta.hook_warnings` only; `_extract_timestamps` returns None on any bad row instead of dropping; `cmd_status` doesn't guard the activities-table SELECT.

## Divergence

Goal was to verify the wheel works for a recipient on another system. Drifted into a full bug hunt at user request, then a focused review of the MCP registration path. Outcome stronger than scope: shippable verdict + prioritized fix list, not just a yes/no on functionality.
