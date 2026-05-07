# ADR 0026: Claude Desktop config-path resolution under UWP sandboxing — detect every parent that exists, dual-write to all of them

- **Status:** Accepted
- **Date:** 2026-05-06
- **Related:** [ADR 0024 (Wheel-distributed tour and fixture bundling)](0024-wheel-distributed-tour-and-fixture-bundling.md), [ADR 0014 (Coverage criticality is an invariant)](0014-coverage-criticality-invariant.md), [ADR 0010 (Adversarial pairing)](0010-adversarial-pairing.md), [CLAUDE.md § v6.10.2 banner](../../CLAUDE.md), [CLAUDE.md § v6.10.3 banner](../../CLAUDE.md)

## Context

Claude Desktop ships on Windows in two installation variants that the
framework's recipient-onboarding code did not previously distinguish:

1. **Classic** — the direct `.exe` installer downloaded from
   Anthropic. Reads `claude_desktop_config.json` from
   `%APPDATA%\Claude\` (i.e. `C:\Users\<user>\AppData\Roaming\Claude\`).
2. **Microsoft Store / UWP** — the packaged app installed via the
   Windows Store. Runs inside a UWP container that silently redirects
   `%APPDATA%\Claude\` reads to a per-package sandbox at
   `C:\Users\<user>\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\`.
   The redirection is transparent to code running *inside* the
   container; code running *outside* the container sees the unredirected
   paths.

The framework's pip-installed Python interpreter runs outside the UWP
container. `_claude_desktop_config_path()` at
[`src/biosensor_mcp/pilot.py:377-382`](../../src/biosensor_mcp/pilot.py)
returns `Path(os.environ.get("APPDATA", "")) / "Claude" /
"claude_desktop_config.json"` on Windows — the classic path only — and
`tour.py` imports the same helper per
[ADR 0024](0024-wheel-distributed-tour-and-fixture-bundling.md)
§2's deliberate inheritance. The same Windows branch is duplicated
verbatim at [`src/biosensor_mcp/__main__.py:407-408`](../../src/biosensor_mcp/__main__.py)
(in the `cmd_status` diagnostic) and at
[`src/biosensor_mcp/__main__.py:483-484`](../../src/biosensor_mcp/__main__.py)
(in `cmd_uninstall`).

A recipient with Store-installed Claude Desktop runs `biosensor-mcp
tour --force`, sees a `Tour scaffolded successfully` message naming
the classic config path, restarts Claude Desktop, and finds no
biosensor tools available. The Store-installed Claude Desktop reads
its own sandboxed `claude_desktop_config.json`, which the framework
never wrote to. The symptom — Claude Desktop comes up with no
biosensor tools after a successful registration message — is
symmetric with the v6.10.2 setup-help failure mode but unrelated in
cause; the v6.10.2 fix surfaced a diagnostic tool when the *config
file was found and degraded*, but here the config file the recipient's
Claude Desktop actually reads is never touched at all.

The boss reports hitting this failure mode "a million times since day
one" on his own machines. The recipient (dad) hit it on the v6.10.3
install path tested 2026-05-06 — the third recipient-onboarding
ship-blocker in the v6.10.x patch sequence after v6.10.1 (cp1252
glyphs), v6.10.2 (degraded-config diagnostics), and v6.10.3 (sibling
biosensor-* coexistence). Recipient-onboarding has been load-bearing
for three consecutive patches; this ADR completes the trilogy.

The structural question this ADR answers: *when "the recipient's
Claude Desktop" can mean either of two installations whose config
files live at different paths and whose existence is detectable
from outside both, what does the framework write to?*

## Decision

The framework detects every Claude Desktop config-file path whose
parent directory exists at registration / status / uninstall time,
and writes to (or cleans) all of them. Detect-and-pick is rejected
on the same severity grounds the v6.10.2 / v6.10.3 hardenings rest
on; dual-write is bulletproof against the case where both variants
are installed simultaneously, against package-family-name drift over
time, and against any future detection heuristic going stale.

Concrete mechanism:

- **`_claude_desktop_config_path() -> Path | None` is refactored to
  `_claude_desktop_config_paths() -> list[Path]`** at
  [`src/biosensor_mcp/pilot.py:377-382`](../../src/biosensor_mcp/pilot.py).
  The return is a list of every Claude Desktop config-file path the
  framework can confirm with positive evidence on this machine. On
  Windows the candidate set is computed as: the classic path under
  `%APPDATA%\Claude\claude_desktop_config.json` (always included; the
  classic install creates this directory on first registration), plus
  every glob match for
  `%LOCALAPPDATA%\Packages\Claude_*\LocalCache\Roaming\Claude\claude_desktop_config.json`
  (Store sandbox; one path per UWP package whose family-name prefix
  matches `Claude_`). On macOS the candidate set is one path
  (`~/Library/Application Support/Claude/`). On Linux the candidate
  set is empty (no Claude Desktop on Linux).
- **Detection by prefix-glob, not hardcoded family name.** The Store
  variant's full package family name is `Claude_pzs8sxrjxfjjc` as of
  this ADR, but the publisher-hash suffix is generated by Microsoft's
  signing toolchain and changes whenever Anthropic re-signs or
  re-publishes the package. Hardcoding the full name silently breaks
  Store-install detection on the next Anthropic-side change; the
  framework would not notice until a recipient hits the failure mode
  this ADR was supposed to close. Globbing `Claude_*` survives
  publisher-hash drift; the false-positive risk (an unrelated UWP app
  whose name starts with "Claude") is bounded by the rest of the path
  shape — `LocalCache\Roaming\Claude\claude_desktop_config.json` inside
  the sandbox is specifically Claude Desktop's structure, not a generic
  UWP app's. The two specialists who reviewed this ADR disagreed on
  this point per ADR 0010 (adversarial pairing); the path-shape
  narrowing is what made the dissent resolvable.
- **First-time-install fallback.** The classic path is always
  included on Windows even if `%APPDATA%\Claude\` does not yet exist.
  The Store glob may return zero matches on a fresh Store install
  whose UWP package directory has not yet been created (Store apps
  lazily create their `Packages\Claude_*\` sandbox on first launch).
  After first launch of the Store-installed Claude Desktop, the
  sandbox is materialised and a re-run of `biosensor-mcp tour --force`
  registers in both. The next-steps output from `tour` already
  instructs recipients to launch Claude Desktop after registration; a
  cue-card recovery row added in this PR names the re-run path for
  the Store-only-and-never-launched case.
- **Per-path atomic semantics.** `_register_with_claude_desktop` and
  `_clean_claude_desktop_biosensor_entries` iterate over every
  returned path. For each path P, the contract is: read P → clean
  every `biosensor-*` sibling in P → add the new entry to P → write P
  atomically via `os.replace`. The read / clean / add / write block
  is wrapped in try/except per path. A `PermissionError` (Claude
  Desktop has the file open because the user did not fully quit
  before running tour), `OSError` (disk full, antivirus quarantine),
  or any other exception on path P does **not** abort writes to the
  remaining paths — but does surface as a per-path error in the
  recipient-facing output naming P and a plain-language remediation
  ("quit Claude Desktop fully via the system tray and re-run").
  The success message is conditional: `Tour scaffolded successfully`
  prints only if every detected path was written; if any path
  failed, the output reports `Tour scaffolded with N of M Claude
  Desktop registrations succeeded` with the per-path errors listed
  beneath. The exit code is 0 if at least one path succeeded, 1 if
  all paths failed. The `.tmp` file from `_write_claude_config` is
  unlinked on partial failure to avoid clutter across debugging
  loops.
- **The duplicated Windows branches in `__main__.py` are folded into
  the new helper.** `cmd_status` at
  [`__main__.py:404-428`](../../src/biosensor_mcp/__main__.py) and
  `cmd_uninstall` at
  [`__main__.py:480-`](../../src/biosensor_mcp/__main__.py) both
  switch to `_claude_desktop_config_paths()` and iterate.
  `cmd_uninstall` cleans entries from every detected path, matching
  the v6.9.2 prefix-match cleanup pattern symmetrically across
  installs.
- **`cmd_status` framing as recovery instructions, not state report.**
  The diagnostic output reports per-path registration in
  recipient-actionable terms. *"Registered for both Claude Desktop
  variants"* on the bulletproof case; *"Registered for classic only —
  if you use the Microsoft Store version of Claude Desktop, run
  `biosensor-mcp tour --force` to register there too"* on the
  partial case. The recipient should not need to learn the UWP
  redirection mechanic to read the status output.
- **Invariant locked in writing.** After a successful `tour --force`,
  exactly one `biosensor-*` entry exists in **each detected** Claude
  Desktop config; the entry is identical across configs. The v6.10.3
  invariant ("exactly one biosensor-* entry exists in mcpServers")
  generalises per-path under this ADR. Regression tests assert it as
  a contract, not as an implementation accident.

The rule, plain English: the framework writes to every Claude Desktop
config the recipient's machine could plausibly be reading, on the
theory that writing to a config no Claude Desktop reads is harmless
and writing to none of the configs the running Claude Desktop reads
is the failure mode the v6.10.x trilogy keeps reproducing.

### Criticality classification per ADR 0014

Per [ADR 0014](0014-coverage-criticality-invariant.md), the refactored
helper inherits the HIGH criticality classification ADR 0024 §5
named for `tour.py`'s Claude Desktop integration. The new code paths
are:

| File | Criticality | Rationale |
|---|---|---|
| `src/biosensor_mcp/pilot.py:_claude_desktop_config_paths` | **HIGH** | Returns the set of paths that downstream registration / status / uninstall iterate over. A regression that drops the Store-sandbox path silently reproduces the v6.10.x failure mode this ADR closes. A regression that returns extra paths could write biosensor entries to unrelated `Claude\` directories. |
| `src/biosensor_mcp/pilot.py` Store-package-family-name constant | **HIGH** | A typo in the family name silently breaks Store-install detection and the failure is invisible until a recipient hits it. |
| `src/biosensor_mcp/pilot.py:_register_with_claude_desktop` (iteration loop) | **HIGH** | Per-path failure handling: a half-written registration where one path succeeds and the other fails is the worst-case state. The loop must surface per-path errors and must not abort a successful write to one path on a failure to another. |

Regression tests land in `tests/test_pilot_wizard.py` and
`tests/test_tour_subcommand.py` covering eight scenarios identified
by the proposal-mode audit: (i) Store-only environment, (ii)
classic-only environment, (iii) both-present-and-writable, (iv)
both-present-write-to-Store-fails-with-PermissionError (per-path
atomic recovery), (v) sibling-cleanup-fires-on-every-detected-path
(v6.10.3 invariant generalised per-path), (vi)
neither-present-on-fresh-install (classic-fallback contract), (vii)
Linux skips silently (existing behaviour preserved), (viii) the
v6.10.3 multi-entry-coexistence trap reproduced across both paths
simultaneously. The singular `_claude_desktop_config_path` helper is
deleted entirely; ~12 existing tests in `test_pilot_wizard.py` and
`test_tour_subcommand.py` are migrated mechanically to the list
shape (`monkeypatch.setattr(..., lambda: [path])`). A thin singular
shim is rejected explicitly: it would hide the dual-path behaviour
from every test that uses it, and the dual-path path is what this
ADR exists to harden.

## Consequences

### Positive

- **The Store-installed-Claude-Desktop recipient is reachable.** A
  recipient who installed Claude Desktop from the Microsoft Store —
  the path Microsoft promotes as default on Windows 11 — runs
  `biosensor-mcp tour` and gets a working biosensor tool surface
  on first try, without manual JSON editing or workaround docs.
- **The both-installed case is bulletproof.** A recipient who has
  both classic and Store installs simultaneously (someone who
  installed Store, then classic, or vice versa) gets the biosensor
  entry registered in both configs. Whichever Claude Desktop the
  recipient actually launches sees the entry.
- **The recipient-onboarding trilogy completes coherently.** v6.10.2
  fixed *what tools surface when the config is degraded*; v6.10.3
  fixed *which entries coexist in one config file*; this ADR fixes
  *which config files the framework knows to look at*. The three
  patches together close the recipient-onboarding failure surface
  the boss has reported hitting repeatedly since the project's
  earliest deployments.
- **The duplicated Windows branches in `__main__.py` are eliminated.**
  Three call sites (one in `pilot.py`, two in `__main__.py`) collapse
  to one helper. A future change to the path-detection logic — a new
  Claude Desktop installation variant, a package-family-name update —
  lands in one place.
- **`cmd_status` becomes more honest.** The diagnostic output names
  every path the framework knows about and reports per-path
  registration state. A recipient diagnosing why their Claude Desktop
  doesn't see biosensor tools sees immediately whether the entry is
  registered against the install they're actually running.

### Negative

- **The `Claude_*` prefix glob is brittle to publisher-prefix
  changes, not publisher-hash-suffix changes.** Globbing
  `%LOCALAPPDATA%\Packages\Claude_*\` survives Anthropic re-signing
  the package (the suffix changes; the prefix does not) but does not
  survive a deliberate rename — for example, if Anthropic publishes
  the Store version under a new publisher identity that produces a
  different prefix entirely. The drift would be invisible until a
  recipient hit it. The structural defense is that the v6.10.x
  trilogy has codified recipient-onboarding-failure as a load-bearing
  release-blocker; a future drift would be caught at the next
  recipient-onboarding pass and patched, the same way every prior
  drift in this surface has been.
- **Dual-write means dual-failure-surface.** A permission error on
  one config path no longer halts the operation; it surfaces as a
  per-path warning. A recipient whose Store-sandbox config is locked
  by a running Claude Desktop (the most common case) sees a clear
  per-path error message naming the path and instructing them to
  fully quit Claude Desktop via the system tray. Acceptable — the
  warning is the right surface; the alternative is silently failing
  on the path the recipient cares about, which is precisely the
  v6.10.x failure shape this ADR closes.
- **First-time-install on a Store-only machine that has never
  launched Claude Desktop misses the Store sandbox on the first
  `tour` run.** Store apps lazily create their `Packages\Claude_*\`
  directory on first launch; before launch, the glob returns no
  matches and `tour` writes only to the classic path. The recipient
  launches their Store-installed Claude Desktop, sees no biosensor
  tools, and must re-run `biosensor-mcp tour --force` to register
  in the now-existent sandbox. Mitigated in the recipient cue card
  (a new recovery row added in this PR for the symptom *"installed
  Store version, ran tour, no tools after first launch"*) and in the
  `tour` next-steps output. Not eliminable without paying the
  detection cost upfront on every machine — process-introspection or
  registry-scanning detection has its own failure modes per the
  Alternatives section below.
- **Mac App Store variant is not addressed.** Anthropic ships Claude
  Desktop on macOS as a direct `.dmg` install only as of this ADR;
  there is no Mac App Store variant whose sandbox would parallel the
  Windows UWP case. If Anthropic ever ships a Mac App Store version,
  the framework will reproduce the same recipient-onboarding failure
  on Mac and v6.10.4 will not protect against it — the macOS branch
  of `_claude_desktop_config_paths()` returns one path, not a glob.
  Named explicitly here so the gap does not drift to v6.11 silently;
  a future ADR would generalise the macOS branch the same way this
  one generalises Windows.

### Neutral

- **macOS and Linux are unchanged.** macOS has one canonical Claude
  Desktop config path
  (`~/Library/Application Support/Claude/claude_desktop_config.json`).
  Linux has no Claude Desktop. The list-returning helper is
  length-1 on macOS and length-0 on Linux; the iteration loop is
  trivially correct in both cases.
- **The v6.2.1 atomic-write + BOM round-trip + deep-merge hardenings
  inherited per ADR 0024 §2 propagate to every path written.** Each
  path is written through `_write_claude_config` independently;
  sibling MCP servers in either config are preserved per the v6.2.1
  contract.
- **The v6.9.2 prefix-match cleanup in `cmd_uninstall` and the
  v6.10.3 sibling-biosensor-* cleanup in `_register_with_claude_desktop`
  apply per-path.** A recipient whose classic config has a stale
  `biosensor-mcp` entry and whose Store config has a stale
  `biosensor-tour-hip-lab` entry gets both cleaned on the next
  registration. The cleanup contracts are unchanged in shape; only
  the surface they apply to widens.
- **The ADR 0024 §5 criticality classification of `tour.py` as HIGH
  is unchanged.** This ADR refines the helper at the addressing
  layer, not the registration logic that landed under ADR 0024.

## Alternatives considered

**Detect via process introspection — query running processes to
determine which Claude Desktop variant is installed and pick its
config path.** Rejected. Process introspection is a runtime-only
signal; the framework runs `biosensor-mcp tour` while Claude Desktop
is asked to be quit (so the recipient can edit the config file
without lock contention). At registration time there is by design
no Claude Desktop process to introspect. Even if there were, a
recipient with both variants installed but only one running at
registration time gets the registration written to one config and
not the other — same failure shape as detect-and-pick, in a more
fragile costume. Process introspection also requires platform-
specific APIs (Win32 `EnumProcesses` or PowerShell shell-out) that
add a meaningful dependency surface for a problem the parent-
directory-existence check already solves.

**Prompt the user during `tour` for which Claude Desktop install they
have.** Rejected on UX grounds. ADR 0024 §2 commits the recipient-
onboarding flow to "the recipient never types an env var by hand";
the v6.2.1 pilot wizard flow is "two terminal commands and three
prompts." Adding a fourth prompt — *"Which Claude Desktop did you
install? (1) the .exe from Anthropic (2) the Microsoft Store
version"* — pushes the recipient into a question they may not know
the answer to. The v6.10.x trilogy's structural lesson is precisely
that recipient-onboarding friction surfaces as silent failure two
weeks later; adding a disambiguation prompt is the same shape of
mistake in a different place. Detection is the framework's job.

**Document the Store-install workaround in `RECIPIENT_README.md` and
leave the code unchanged.** Rejected on severity grounds. The
v6.10.2 ADR-12-amendment bundled a `RECIPIENT_README.md` in the
wheel exactly so external Claude Desktops could discover `biosensor-mcp
tour` without source-code archaeology; a workaround doc inside that
file would document the failure mode rather than fix it. The boss-
architect protocol 4 (anti-sycophancy and mandatory conflict
pushback) names the pattern: documenting around a footgun the
framework can detect and handle is the framework refusing
responsibility for a problem it owns. The recipient-onboarding
trilogy's structural commitment is that the recipient runs `pip
install` plus `biosensor-mcp tour` and the framework handles the
rest; carving out an exception for this specific failure
contradicts the commitment.

**Hardcode the full Store package family name `Claude_pzs8sxrjxfjjc`
in a module-level constant rather than glob-matching `Claude_*`.**
Considered and rejected. The full family name's suffix is a
publisher-hash artifact generated by Microsoft's signing toolchain
and changes whenever Anthropic re-signs or re-publishes the package.
Hardcoding the full name silently regresses to "classic-only"
detection on the next Anthropic-side change; the framework would not
notice until a recipient hit the failure mode this ADR closes. The
ADR-drafter's original concern — that `Claude_*` would match
unrelated UWP apps starting with "Claude" — is bounded by the rest
of the path shape: the framework reads
`Claude_*\LocalCache\Roaming\Claude\claude_desktop_config.json`,
which is not a generic UWP app structure but specifically Claude
Desktop's. Two specialists disagreed on this point per
[ADR 0010](0010-adversarial-pairing.md) (adversarial pairing); the
path-shape narrowing is what made the dissent resolvable. Recorded
here to make the resolution durable rather than implicit.

**Always write to both Windows config paths unconditionally,
without any detection.** Considered and rejected. Writing to a UWP
sandbox path that the recipient's Microsoft Store has never
materialised would require pre-creating
`%LOCALAPPDATA%\Packages\Claude_<some-suffix>\LocalCache\Roaming\Claude\`
— but the framework has no basis for choosing the suffix without
detection in the first place, and pre-creating the directory could
collide with Microsoft's later Store install of the package. The
glob-matched detection is precise enough to avoid speculative
writes; speculative writes would be cheaper but at the cost of
filesystem-pollution and a structurally weaker contract.
