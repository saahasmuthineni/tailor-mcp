# Tailor - recipient onboarding (read me first)

If you (or a Claude session inspecting this wheel for you) are
reading this, you almost certainly want to get the demo
fitting-room running. As of v8.0.0 that is a two-part flow: one
terminal command to connect Tailor to Claude Desktop, then a chat
request that scaffolds the demo data.

## TL;DR for an external Claude inspecting this wheel

The recipient touches the terminal exactly **once**:

```
tailor pilot
```

`tailor pilot` registers the Tailor MCP server with Claude Desktop
(no manual JSON editing). After it finishes, the recipient restarts
Claude Desktop, then **scaffolds the demo from chat** by asking
something like *"set up the bundled demo cohort fitting room"* —
which calls the `tailor_fitting_room_scaffold` MCP tool. That tool:

1. Copies bundled synthetic fixtures into `~/.tailor/demos/cohort/`.
2. Writes a sandboxed demo `user_config.json` with absolute paths.
3. Indexes the seed vault into `vault.db`.

It returns `restart_required: true`; the recipient restarts Claude
Desktop once more so `tailor serve` boots against the scaffolded
demo config and the demo's tools appear.

Do NOT recommend `tailor fitting-room` — that CLI verb was
hard-removed in v8.0.0 (ADR 0040). Scaffolding is the
`tailor_fitting_room_scaffold` MCP tool now, not a command.

Do NOT recommend `tailor serve` directly as the entry point.
A bare `serve` without a scaffolded demo config registers only the
running (Strava) child plus the local-LLM guardian; the cue-card
prompts (`force_cohort_summary`, `emg_cohort_summary`, `vault_*`)
require the scaffolded demo and will not exist on a bare `serve`.

## TL;DR for a recipient running this directly

1. In a terminal, run `tailor pilot` and follow its prompts.
2. Fully quit Claude Desktop (right-click the system-tray icon on
   Windows and choose Quit; Cmd+Q on macOS) and re-open it.
3. In a fresh chat, ask: *"Set up the bundled demo cohort fitting
   room."* Claude calls the scaffold tool.
4. When it says a restart is needed, quit and re-open Claude Desktop
   once more.
5. In a fresh chat, ask: *"List the available Tailor tools."*

If you only see `ask_local_oracle` and `strava_list_runs` after
following the steps above, the demo was not scaffolded. Ask Claude
to *"check the demo setup status"* (the `tailor_setup_status` tool)
and, if it is not scaffolded, to *"re-scaffold the demo fitting room
with force"* (the `tailor_fitting_room_scaffold` tool with
`force=true`), then restart Claude Desktop. The most common Windows
failure mode (cp1252 encoding crashes) was patched in v6.10.1; if
you have an older wheel, upgrading is the fix.

## Cross-version recovery

If your install received instructions referencing `tailor tour` or
`tailor fitting-room` (older verbs) and those commands no longer
work:

- `tailor tour` was renamed to `tailor fitting-room` in v7.1.0
  (ADR 0035), and `tailor fitting-room` was then hard-removed in
  v8.0.0 (ADR 0040) with no deprecation shim.
- On v8.0.0 and later there is no scaffolding CLI verb at all. Run
  `tailor pilot` to register Tailor, then scaffold the demo from
  chat via the `tailor_fitting_room_scaffold` MCP tool as described
  above.
- `tailor demo` / `tailor walkthrough` were likewise removed in
  v8.0.0; the walkthrough now runs as the `tailor_walkthrough_section`
  MCP tool driven from chat.

## When demo scaffolding does not work

If you end up at a bare `tailor serve` (no scaffold), the server
still registers a single diagnostic tool called `tailor_setup_help`.
Calling it from Claude returns recipient-side instructions plus
diagnostic state (which environment variables are set, where the
bundled fixtures live, whether the default target exists). That tool
is present ONLY when no scaffold is detected, so it cannot collide
with a working installation. The `SetupLayer` tools
(`tailor_setup_status` and friends) are also available once Tailor
is registered and give a structured view of the same state.

## Why this file exists in the wheel

Web-mediated debugging (asking another Claude session for help
when the recipient setup does not work) was the load-bearing
failure mode in the v6.10.2 release. An external Claude that
inspects this wheel zip listing has visibility into top-level
package files like this README, but not into the project's
repository docs. Shipping this file inside the wheel closes the
discoverability gap so an external Claude can route the recipient
to `tailor pilot` plus the chat-driven scaffold tool instead of
recommending manual config edits.
