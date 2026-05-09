# ADR 0024: Wheel-distributed tour and fixture bundling — generated artifacts ship, generators stay out

- **Status:** Accepted
- **Date:** 2026-05-04
- **Amended:** 2026-05-07 — § 3.1 added (public release-only mirror as a friend-shareable carve-out alongside the existing Drive/email distribution); see § 3.1 for the carve-out's invariants and reversal conditions. Cites [ADR 0029 (Token reduction is analytical quality)](0029-token-reduction-as-analytical-quality.md).
- **Related:** [ADR 0008 (Deterministic by construction)](0008-deterministic-by-construction-processing.md), [ADR 0014 (Coverage criticality is an invariant)](0014-coverage-criticality-invariant.md), [ADR 0015 (Tier-1 cohort surface + metadata sidecar)](0015-tier-1-cohort-surface-and-metadata-sidecar.md), [ADR 0029 (Token reduction is analytical quality)](0029-token-reduction-as-analytical-quality.md), [CLAUDE.md § Workflow: manager mode](../../CLAUDE.md#workflow-manager-mode), [CLAUDE.md § Boss-architect protocols (Tier 1)](../../CLAUDE.md#boss-architect-protocols-tier-1--main-session-discipline)

## Context

The HIP Lab realistic demo (`examples/hip_lab_demo/realistic/`) ships
in v6.5.0 as a 48-CSV multimodal fixture plus a guided walkthrough
designed for live recipients — Dr. Senefeld at the next HIP Lab
meeting, the boss-architect's family member as a non-technical first
audience, future PIs evaluating the framework. The demo is the
project's primary live-audience surface; everything before it
(`tailor demo`, the synthetic-running-data analytics dump) is
operator self-verification, not an audience walkthrough.

Until v6.9.0 the demo could only be run from a source clone of the
repo. The recipient had to:

1. Clone or download the GitHub repository.
2. Install Python and the package in editable mode.
3. Run `python examples/hip_lab_demo/realistic/setup.py` to scaffold
   the demo.
4. Hand-edit `claude_desktop_config.json` to add a server entry with
   the right `TAILOR_CONFIG_DIR` env var pointing at the cloned
   repo's `examples/` subdirectory.
5. Restart Claude Desktop.

This works for in-repo developers but collapses for the demo's actual
target audience. The repo is private (and will stay private — see
§ Alternatives). Non-technical recipients do not have GitHub access,
do not write JSON by hand, and will not type
`TAILOR_CONFIG_DIR=/long/absolute/path tailor serve` in a
PowerShell window. Each step in the prior flow is a place where the
recipient can silently fail with no breadcrumb back to the cause.

The structural question this ADR answers is: *what artifacts ship
inside the wheel, and what stays in `examples/`?* The convention
since v6.2.1 (when the multi-subject pilot's three CSV fixtures
moved into `src/tailor/_fixtures/multi_subject_pilot/csv/`)
has been *"the wheel ships only enough fixtures to make `pilot`'s
end-to-end smoke check work; everything else lives in `examples/`
for in-repo dev only."* That convention is too narrow now: the demo
is a primary audience-facing surface, and the audience can't reach
`examples/`.

[ADR 0008](0008-deterministic-by-construction-processing.md) places
fixture generators (`examples/**/generate.py`) on a permit-list — a
deliberate exception to the no-PRNG / no-clock invariant that
processing code obeys, justified because generators sit *off* the
analytical path. The generators do not ship in the wheel. The
question of whether their *generated outputs* ship has been resolved
inconsistently — `multi_subject_pilot/csv/` outputs ship; the
hip_lab_demo realistic outputs did not, until this ADR.

## Decision

Wheel-distribute the HIP Lab realistic demo via a single CLI
subcommand, governed by four sub-decisions:

### 1. Generated fixtures ship in the wheel; generators do not

The 48 force/EMG/MRS CSVs, three `metadata.json` sidecars, and the
S004 cross-session-memory seed vault moment migrate from
`examples/hip_lab_demo/realistic/{force,emg,mrs,vault}/` to
`src/tailor/_fixtures/hip_lab_demo_realistic/{force,emg,mrs,vault}/`.
`pyproject.toml` `[tool.setuptools.package-data]` extends to glob
`_fixtures/**/*.csv`, `_fixtures/**/*.json`, and `_fixtures/**/*.md`
so the entire bundled tree ships in the wheel.

`examples/hip_lab_demo/realistic/generate.py` keeps the seeded PRNG
that produced those fixtures, stays out of the wheel by way of the
`[tool.setuptools.packages.find] where = ["src"]` rule, and writes
its outputs *into the bundled tree* — `generate.py`'s output path
becomes `src/tailor/_fixtures/hip_lab_demo_realistic/`, not
the in-repo example dir. Re-running `generate.py` is the way to
refresh the bundled fixtures; the next wheel build picks up the new
bytes automatically.

This sharpens the ADR 0008 permit-list semantics rather than
weakening them. The invariant is *"no PRNG and no clock reads on the
analytical path"*; generators are off-path by definition. The
permit-list grants the generator file the right to exist; it does
not bind the disposition of what the generator produces. Generated
artifacts ship under the same logic as a tested fixture file — the
fact that some upstream code generated them is irrelevant once the
bytes are committed.

### 2. The `tour` CLI subcommand is the live-audience surface

`tailor tour` lands as a new public CLI subcommand at
[`src/tailor/tour.py`](../../src/tailor/tour.py).
Default invocation (`tailor tour`) scaffolds the hip-lab
realistic variant into `~/.tailor/demos/hip-lab/`, copies
bundled fixtures via `importlib.resources`, writes `user_config.json`
with absolute paths resolved against the target dir, indexes the
seed vault moment into `data/vault.db`, and writes (or merges with)
the recipient's Claude Desktop config to register an
`mcpServers["biosensor-tour-hip-lab"]` entry whose `env` block
**bakes in `TAILOR_CONFIG_DIR` and `TAILOR_DATA_DIR` pointing
at the scaffolded target dir**. The recipient never types an env
var by hand; Claude Desktop spawns the server with the right
environment automatically.

Flags: `--variant=<name>` (currently only `hip-lab`; future variants
plug into the `_VARIANT_FIXTURES` table), `--target=<dir>` (override
default scaffold location), `--no-claude-desktop` (skip the Claude
Desktop merge for headless / CI use), `--force` (overwrite a
non-tour target dir).

The Claude Desktop merge code is **explicitly inherited** from
[`src/tailor/pilot.py`](../../src/tailor/pilot.py)'s
v6.2.1 hardenings — atomic write via `os.replace`, BOM round-trip,
deep-merge into existing `mcpServers` so sibling MCP servers
survive. `tour.py` imports the path-resolution helper plus
`_write_registration_to_path` from `pilot.py` rather than
reimplementing them. (Naming context: at the time of this ADR's
landing in v6.9.0 the helper was singular,
`_claude_desktop_config_path() -> Path | None`; v6.10.4 generalised
it to `_claude_desktop_config_paths() -> list[Path]` per
[ADR 0026](0026-claude-desktop-config-dual-path.md) so the dual-write
under UWP sandboxing on Windows extends through the same inheritance
seam.) Pilot and tour are siblings — both
scaffold a working configuration for a non-technical recipient —
but they are *not* unified: pilot is for "ingest your own CSV
directory and connect it"; tour is for "run a canned demo against
bundled fixtures." Tour is read-only against the package; pilot is
write-through against the user's data. Different jobs; different
subcommands.

Naming: `tour` was selected over `hip-lab` (recipient-name
lock-in), `hip-lab-demo` (collides with the existing operator
self-verification `demo` subcommand), and folding into `demo
--variant=hip-lab` (would breaking-change the existing `demo`
subcommand's behaviour). The legacy `demo` subcommand will rename
to `verify` in a future release — bookmarked in
[ROADMAP.md § "CLI UX: rename legacy demo → verify"](../../ROADMAP.md#cli-ux-rename-legacy-demo--verify).

### 3. Distribution model: pre-built wheel, not PyPI

Wheels are built locally (`python -m build`) and sent to recipients
via Drive or email. No PyPI publish. The repo stays private; the
project's metadata stays off `pypi.org` until the boss-architect
judges the IRB-review-readiness threshold met. Recipients install
via `pip install <path-to-wheel>`. Updates re-send the wheel file;
recipients re-run `pip install --force-reinstall` (or `pip install
--upgrade <new-wheel>`).

This shape works because the immediate recipient set is small (one
family member, one PI). For 10+ recipients, PyPI becomes the right
answer; the work converts trivially (one `twine upload` invocation
once `python -m build` is in dev extras). See § Alternatives.

### 3.1. Public release-only mirror for friend-shareable demo (amended 2026-05-07)

The 2026-05-04 decision in § 3 above named a single distribution
channel (Drive/email). The 2026-05-07 amendment adds a parallel
channel — **a public release-only GitHub mirror repo at
`saahasmuthineni/biosensormcpdemo`** — for the specific use case of
*"send the demo to a CS-grad-shaped friend who wants to evaluate the
framework with one click."* The motivating boss-architect intent
(2026-05-07): *"my only requirement is I can easily send this demo
and my friend can try it easily as well."* That requirement is not
met by the Drive/email path — the boss has to attach a wheel, the
friend has to know how to install it locally, and there's no
copyable URL for messengers.

The carve-out's mechanism: the boss creates one public GitHub repo
(no source code, no docs) whose only purpose is hosting (a) a
GitHub Pages-rendered shareable demo transcript and (b) versioned
wheel files as release assets. Each `release-shipper` run uploads
the new wheel to this mirror and regenerates `index.md` from the
output of `tailor demo --save-shareable`. The boss then has
a permanent URL (e.g.
`https://saahasmuthineni.github.io/biosensormcpdemo/`) to share
through any channel; the friend's one-line `uvx --from <wheel-url>
tailor demo` runs the same demo on their machine without any
account, clone, or env-setup ritual.

**Invariants the carve-out preserves:**

1. **Source repo stays private.** The mirror is release-artifact-only.
   No source code, no ADRs, no design docs, no CLAUDE.md propagate to
   the public mirror. The mirror's `README` says only *"this is the
   release distribution channel for the (private) Biosensor MCP
   project; the demo URL is …"* with a contact-the-author breadcrumb.
2. **Synthetic-by-construction precondition holds.** § 4 below is
   load-bearing for this carve-out — the wheel is shareable publicly
   only because every byte it contains is synthetic by construction
   (HIP Lab fixtures from `random.Random(20260504)`, fictitious
   subject IDs, no possibility of real participant data passing
   through). A future bundle of real or de-identified-real data
   under § 4's reversal conditions immediately disqualifies this
   carve-out — public distribution becomes a covered-data egress
   event with no audit trail. The carve-out reverses if § 4 reverses.
3. **Recipient set scale is unchanged.** The carve-out is for a
   handful of evaluator-friends, not for general public adoption. At
   ~10+ public consumers, PyPI publication (Alternative 1 below)
   becomes the right answer for the same reasons named in § 3 — the
   carve-out is a friction-reducing intermediate, not a scaling step.

**Reversal condition:** if recipient feedback shows the public-URL
shape damages first-impression formation, or if the synthetic-by-
construction precondition reverses (per § 4), or if the project's
private-to-IRB-review-readiness trajectory shifts, retire the
public mirror and revert to § 3's Drive/email-only path. The mirror
is purely additive; deletion is reversible.

**Boss-side setup (one-time, ~10 minutes):** create a public repo
named `biosensormcpdemo`, configure GitHub Pages from `main` /
`(root)`, and provide `release-shipper` with a Personal Access Token
(scope: `public_repo`) so the publish step is automatic per release.
Setup checklist lives at `docs/guides/share-the-demo.md` (added in
the same patch).

**Companion to ADR 0029.** The carve-out only matters because the
demo *itself* now demonstrates the framework's load-bearing
architectural claims (per ADR 0029); a friend running the prior-
v6.10.5 router-bypassed cohort-only demo would have had less to
evaluate. ADR 0029 makes the demo worth sharing publicly; this
amendment makes the sharing path itself frictionless.

### 4. Synthetic-by-construction precondition

**Bundling fixtures inside the wheel under this pattern is permitted
only when the bundled bytes are synthetic by construction.** "Synthetic
by construction" means: the bytes are produced by a seeded generator
(`examples/**/generate.py`) acting on fictitious subject IDs and
fictitious clinical interpretations, with no possibility of real
participant data passing through the generator's input. The HIP Lab
realistic fixtures meet this bar by inspection — `generate.py` takes
no inputs from outside its own constants, and the seed
(`random.Random(20260504)`) plus integer subject IDs (`S001`–`S016`)
are fictitious by construction.

This precondition is load-bearing under HIPAA Safe Harbor and any
IRB equivalent: a wheel sent over Drive or email leaves the
institution's data-governance perimeter and cannot be recalled. If
the bundled bytes are real or de-identified-real (HIPAA Safe Harbor
§164.514(b) Limited Dataset, or worse), the distribution model in §3
becomes a covered-data egress event with no audit trail. The seam
that ADR 0024 is *not* the right home for that case is precisely
that the wheel transfer is uninstrumented — the recipient pulls the
file, no audit row exists, no consent gate fires.

**A future variant (sleep, CGM, EHR, etc.) that wants to bundle real
or de-identified-real cohort data under this pattern requires a
superseding ADR.** That ADR would need to address (at minimum): a
data-use-agreement attestation in the recipient onboarding, a
manifest of what bytes ship with each wheel, an audit-log entry on
wheel-build, an IRB-side review of the recipient set, and likely a
shift away from email/Drive transfer toward a per-recipient
provisioned channel (signed URL, institutional file-share, etc.).
Bundling real data under v6.9.0's pattern without that work would be
a Safe Harbor violation.

The synthetic-by-construction guardrail is enforced by review at PR
time on every new entry to `_VARIANT_FIXTURES`. The
`phi-irb-risk-reviewer` agent's Lens 1 (HIPAA Safe Harbor) closes the
loop: any future bundled-fixtures variant goes through that lens
before promotion.

### 5. Criticality classification per ADR 0014

Per [ADR 0014](0014-coverage-criticality-invariant.md), every new
public surface declares its criticality class so
`coverage-criticality-mapper` can hold the line on future regressions.

| File | Criticality | Rationale |
|---|---|---|
| `src/tailor/tour.py` | **HIGH** | CLI public surface that writes the recipient's Claude Desktop config and scaffolds runtime SQLite state. A regression in `_register_with_claude_desktop` could clobber sibling MCP servers (the v6.2.1 hardening this ADR inherits); a regression in `_write_user_config` could write paths that point at the operator's real config dir instead of the scaffold. Both failure modes are silent and recipient-visible. |
| `src/tailor/_fixtures/hip_lab_demo_realistic/**` | LOW | Bundled data; coverage doesn't apply to non-code artifacts. |
| `examples/hip_lab_demo/realistic/generate.py` | LOW | Deterministic generator off the analytical path; output is verified by `rehearse.py` end-to-end (which is itself in the dev tree). |
| `examples/hip_lab_demo/realistic/rehearse.py` | MEDIUM | Pre-meeting smoke check; failure is loud and pre-ship, but a regression that flatten the S004 amplitude bridge silently undermines the demo's wow moment if `rehearse.py` itself drifts in lockstep. Step 4b's cohort-relativity assertion is the structural backstop. |

`tests/test_tour_subcommand.py` lands with 19 tests covering the
HIGH region — bundled fixtures present, scaffold populates the
target dir, `user_config.json` shape, vault index has seed moment,
idempotency, `--target` / `--force` / `--no-claude-desktop`
behaviour, the load-bearing Claude Desktop env-var bake-in, and
sibling-MCP-server preservation on merge.

## Consequences

### Positive

- **Recipient install collapses from 5 manual steps to 2:** receive
  the `.whl`, `pip install <path>` + `tailor tour`. The
  Claude Desktop wiring is automatic. No GitHub, no env vars, no
  JSON edits.
- **The wheel is a self-contained demo carrier.** A reviewer who
  receives the wheel can install it, run the tour, and reach the
  S004 cross-session-memory wow moment without seeing any source
  code.
- **`generate.py`'s output path is the canonical fixture
  location.** The dev workflow is "edit `generate.py` → re-run →
  fixtures are now in `_fixtures/`" — no separate copy step, no
  drift between in-repo and in-wheel fixtures.
- **`rehearse.py` exercises the recipient code path.** The new
  rehearsal scaffolds a real tour into a temp dir and runs against
  it, rather than reading from a back-channel in-repo location.
  Drift in the tour scaffolder is caught by rehearse before the
  demo is run live.
- **`pilot` and `tour` share the Claude Desktop merge code.** The
  v6.2.1 atomic-write + BOM + deep-merge hardenings cover both
  surfaces; future fixes to either land in `pilot.py` and propagate
  to `tour.py` for free.

### Negative

- **Wheel size grows by ~3 MB.** The 48 CSVs at 100 Hz × 60 s ≈
  6,000 rows × 48 = 288k rows × ~30 bytes/row CSV ≈ 8.6 MB
  uncompressed; ~2–3 MB after wheel zip. The pre-v6.9.0 wheel is
  under 1 MB; v6.9.0 lands at ~3.5 MB. Well under Gmail's 25 MB
  attachment limit and Drive's effective limit; not a constraint
  on adding a second variant (sleep, CGM, etc.) without revisiting
  the budget. **A wheel-size budget of 10 MB is named here** so a
  future contributor adding a third or fourth variant has a number
  to hit; crossing 10 MB triggers a re-evaluation of whether the
  variants should split into separate distribution artifacts.
- **`examples/hip_lab_demo/realistic/setup.py` is removed.** Any
  external doc, slack message, or memory referencing the prior
  `python setup.py` invocation is now stale. The replacement
  command is `tailor tour`; the doc churn is contained to
  the realistic directory's own README, CUE_CARD, and
  WINDOWS_QUICKSTART, all updated in this PR.
- **`generate.py`'s output path is now coupled to the package
  layout.** Moving `_fixtures/` would require updating
  `generate.py`'s `PACKAGE_FIXTURES` constant. The coupling is
  documented inline.
- **The default scaffold target dir
  `~/.tailor/demos/hip-lab/` lives under the operator's
  tailor config root.** A future user running both a real
  pilot and the tour will see them as siblings under
  `~/.tailor/`; an `rm -rf ~/.tailor/` would nuke
  both. Mitigation: the `demos/` subdir scope makes a more
  targeted cleanup easy (`rm -rf ~/.tailor/demos/`); for
  single-recipient deployments (mom, Senefeld) there is no real
  pilot config to collide with.
- **`pip install <path-to-wheel>` does not pull dependencies from
  PyPI for offline recipients.** A recipient on a fully air-gapped
  laptop would need the dependency wheels too. Out of scope for
  v6.9.0; recipients with internet access are fine.

### Neutral

- **The `examples/` directory still exists and is still useful.**
  Generators, the rehearse harness, and the live-walkthrough
  documentation (CUE_CARD, README, WINDOWS_QUICKSTART) all live
  in-repo. Only the *generated artifacts* relocated.
- **`pilot` is unchanged.** Existing v6.2.1 behaviour holds.
- **The `demo` subcommand is unchanged in v6.9.0.** Operator
  self-verification still runs `python -m tailor.demo` via
  the same dispatch entry as of this ADR's landing. Subsequently
  reframed in v6.10.5 per [ADR 0027](0027-demo-as-researcher-first-look.md):
  the `demo` subcommand is now a researcher first-look that runs
  the CSV cohort tools against the bundled fixtures from this ADR,
  and the deferred `demo` → `verify` rename is killed (a researcher-
  first-look surface should not be called `verify`). The dispatch
  entry is unchanged; the implementation and framing are.
- **Cross-platform behaviour:** Windows + macOS get the full
  Claude Desktop registration flow; Linux gets the scaffold but
  silently skips the Claude Desktop merge (no Claude Desktop on
  Linux). `_claude_desktop_config_paths()` returns `[]` on Linux
  (singular `_claude_desktop_config_path()` returning `None` was
  the v6.9.0–v6.10.3 shape; v6.10.4 generalised the helper per
  [ADR 0026](0026-claude-desktop-config-dual-path.md)); the tour
  reports `"skipped (Linux, or APPDATA missing)"`.

## Alternatives

### Alternative 1 — Publish to PyPI

Push the package to PyPI under the same name. `pip install
tailor` + `tailor tour` works for any Python user
with internet access; no manual wheel transfer.

**Why rejected today, retained as future option.** The repo is
private and the boss-architect's stated reason is that PyPI
publishing makes project metadata (name, description, license,
dependency list, author) publicly discoverable on `pypi.org` *even
though source code stays private*. The project's stated trajectory
is "private until IRB-review-ready"; PyPI presence is a softer
form of public exposure but still public. The cost of waiting (one
extra step per recipient: receive a wheel file vs. running `pip
install`) is small for two known recipients today. When the
recipient set crosses ~10 PyPI becomes the right answer; conversion
is one `twine upload` invocation. Not bound by this ADR.

### Alternative 2 — Make the GitHub repo public

Open the repo. Recipients clone or download a ZIP. No new
infrastructure.

**Rejected.** Same trajectory concern as Alternative 1, more
strongly: opening the repo exposes all source code, all ADRs, all
audit-log behaviour, all in-progress detours. The IRB-review-ready
threshold the project is targeting includes review-time docs that
do not exist yet. Premature.

### Alternative 3 — Send the demo as a .zip of the repo

`git archive` the repo, send the zip, recipient extracts and runs
`python examples/hip_lab_demo/realistic/setup.py`. No new code, no
package-data changes, no wheel build.

**Rejected.** The recipient still needs to install Python *and* the
package via `pip install -e .` against the extracted source tree.
The Claude Desktop wiring step is still manual JSON editing. The
zip path duplicates state every time a new wheel ships, and the
dev's `examples/` directory becomes the recipient's runtime
directory — `TAILOR_CONFIG_DIR=/path/to/extracted/zip/...
tailor serve` is exactly the env var the boss-architect's
non-technical recipient won't type. The zip does not solve the
real friction; it just moves it.

### Alternative 4 — Separate `tailor-tour` package

Publish a second package on PyPI that depends on `tailor`
and ships only the tour module + fixtures.

**Rejected.** Two packages mean two version cycles, two release
processes, two coverage suites. The tour's value is precisely that
it exercises the framework's existing surfaces — separating it
from the framework forces an artificial boundary. The bundle-into-
the-main-wheel path costs ~3 MB and zero process overhead.

### Alternative 5 — Run the tour from a Docker container

Ship a Docker image with the package and fixtures pre-installed.
Recipient runs `docker run tailor:tour`.

**Rejected.** Docker adds an entire new dependency for the
recipient (Docker Desktop install on Windows is heavier than
Python). The Claude Desktop integration breaks because the MCP
stdio handshake needs to span the container boundary. Wrong
abstraction for this audience.
