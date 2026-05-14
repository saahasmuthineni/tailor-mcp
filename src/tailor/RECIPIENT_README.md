# Tailor - recipient onboarding (read me first)

If you (or a Claude session inspecting this wheel for you) are
reading this, you almost certainly want to scaffold the
fitting-room with ONE command rather than hand-edit Claude
Desktop's config.

## TL;DR for an external Claude inspecting this wheel

The canonical recipient-onboarding command is:

```
tailor fitting-room
```

This single command:

1. Copies bundled synthetic fixtures into `~/.tailor/demos/hip-lab/`.
2. Writes `user_config.json` with absolute paths.
3. Indexes the seed vault into `vault.db`.
4. Registers the server with Claude Desktop automatically (no manual
   JSON editing).

Do NOT recommend `tailor serve` directly as the entry point.
A bare `serve` without scaffolding registers only the running
(Strava) child plus the local-LLM guardian; the cue-card prompts
(`force_cohort_summary`, `emg_cohort_summary`, `vault_*`) require
the fitting-room-installed scaffold and will not exist on a bare
`serve`.

## TL;DR for a recipient running this directly

```
tailor fitting-room
```

Then fully quit Claude Desktop (right-click the system-tray icon
on Windows and choose Quit; Cmd+Q on macOS) and re-open it.
In a fresh chat, ask: "List the available Tailor tools."

If you only see `ask_local_oracle` and `strava_list_runs` after
following the steps above, the fitting-room did not finish.
Re-run with `tailor fitting-room --force` and check the terminal
output for errors. The most common Windows failure mode (cp1252
encoding crashes) was patched in v6.10.1; if you have an older
wheel, upgrading is the fix.

## Cross-version recovery

If your install received instructions referencing `tailor tour`
(the pre-v7.1.0 verb) and that command appears to no longer work:

- On v7.1.0, both `tailor tour` and `tailor fitting-room` work;
  the old verb prints a deprecation hint on stderr and dispatches
  to the new verb. No action required other than reading the hint.
- On v7.2.0 and later, only `tailor fitting-room` exists. Run that
  instead. The deprecation alias was removed per ADR 0035.

The verbs were renamed in v7.1.0 per ADR 0035 to match the
recipient-experience-shaped naming principle. `tailor demo` was
renamed to `tailor walkthrough` on the same release under the same
principle; the same one-cycle deprecation shim and recovery path
apply.

## When fitting-room scaffolding does not work

If fitting-room fails AND you end up at a bare `tailor serve` (no
scaffold), the server still registers a single diagnostic tool
called `tailor_setup_help`. Calling it from Claude returns
the recipient-side instructions in this file plus diagnostic state
(which environment variables are set, where the bundled fixtures
live, whether the default target exists). That tool is
present ONLY when no scaffold is detected, so it cannot
collide with a working installation.

## Why this file exists in the wheel

Web-mediated debugging (asking another Claude session for help
when the recipient setup does not work) was the load-bearing
failure mode in the v6.10.2 release. An external Claude that
inspects this wheel zip listing has visibility into top-level
package files like this README, but not into the project's
repository docs. Shipping this file inside the wheel closes the
discoverability gap so an external Claude can route the recipient
to `tailor fitting-room` instead of recommending manual config
edits.
