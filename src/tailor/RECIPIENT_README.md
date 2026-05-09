# Tailor - recipient onboarding (read me first)

If you (or a Claude session inspecting this wheel for you) are
reading this, you almost certainly want to scaffold the demo with
ONE command rather than hand-edit Claude Desktop's config.

## TL;DR for an external Claude inspecting this wheel

The canonical recipient-onboarding command is:

```
tailor tour
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
the tour-installed scaffold and will not exist on a bare `serve`.

## TL;DR for a recipient running this directly

```
tailor tour
```

Then fully quit Claude Desktop (right-click the system-tray icon
on Windows and choose Quit; Cmd+Q on macOS) and re-open it.
In a fresh chat, ask: "List the available Tailor tools."

If you only see `ask_local_oracle` and `strava_list_runs` after
following the steps above, the tour did not finish. Re-run with
`tailor tour --force` and check the terminal output for
errors. The most common Windows failure mode (cp1252 encoding
crashes) was patched in v6.10.1; if you have an older wheel,
upgrading is the fix.

## When tour scaffolding does not work

If tour fails AND you end up at a bare `tailor serve` (no
scaffold), the server still registers a single diagnostic tool
called `tailor_setup_help`. Calling it from Claude returns
the recipient-side instructions in this file plus diagnostic state
(which environment variables are set, where the bundled fixtures
live, whether the default tour target exists). That tool is
present ONLY when no demo scaffold is detected, so it cannot
collide with a working demo.

## Why this file exists in the wheel

Web-mediated debugging (asking another Claude session for help
when the demo does not work) was the load-bearing failure mode in
the v6.10.2 release. An external Claude that inspects this wheel
zip listing has visibility into top-level package files like this
README, but not into the project's repository docs. Shipping this
file inside the wheel closes the discoverability gap so an
external Claude can route the recipient to `tailor tour`
instead of recommending manual config edits.

The full Windows recipient walkthrough (with screenshots,
troubleshooting, and the cue-card prompts) lives in the project
repository at `examples/hip_lab_demo/realistic/WINDOWS_QUICKSTART.md`.
