# ADR 0031: Project rename to Tailor + introduction of Wardrobe as the user-facing engine word, with a non-fashion counter-programming invariant

- **Status:** Superseded in part by [ADR 0033 (Complete the Tailor metaphor on the workshop side)](0033-complete-tailor-metaphor-workshop-side.md) — counter-programming invariant retired (replaced by positive metaphor identity + narrow-forbid list); naming decisions (Tailor / Wardrobe / `tailor-mcp` / `tailor` / `~/.tailor/`) retained. Further superseded in part by [ADR 0034 (Retire `tailor migrate` subcommand)](0034-retire-tailor-migrate-subcommand.md) — the migration mechanism (`tailor migrate` subcommand + the legacy-directory startup warning) retired in v7.0.9 once the v6 → v7 population was empirically confirmed zero; the rename itself (env vars, paths, package name, dual-prefix Claude Desktop cleanup) retained.
- **Date:** 2026-05-08
- **Related:**
  - [ADR 0024 (Wheel-distributed tour and fixture bundling)](0024-wheel-distributed-tour-and-fixture-bundling.md) — install path adopts the new CLI / package names; ADR 0024 amended with a v7.0.0 forward-cite
  - [ADR 0026 (Claude Desktop config-path resolution under UWP sandboxing)](0026-claude-desktop-config-dual-path.md) — registration cleanup logic widened from single-prefix to dual-prefix matching to handle the v6 → v7 upgrade; ADR 0026 amended with a v7.0.0 forward-cite
  - [ADR 0027 (Demo as researcher first-look)](0027-demo-as-researcher-first-look.md) — `tailor demo` carries the new naming
  - [ADR 0028 (Recipient-install validation as a release-time gate)](0028-recipient-install-validation-as-release-gate.md) — the recipient-install ritual updated for v7.0.0; the validator is skipped for this release per the v6.11.x silent-park falsification, with operator hand-validation until ADR 0028's v2 escalation lands
  - [CLAUDE.md § What This Project Is](../../CLAUDE.md#what-this-project-is) — the v7.0.0 framing reflecting the rename + Wardrobe definition

## Context

The project had been called *"Biosensor MCP"* (PyPI: `biosensor-mcp`; Python import: `biosensor_mcp`; CLI: `biosensor-mcp`) since its first commit. The name accurately described what the framework's first deployment recipe handles — biosensor data from health-research workflows — but it confined the platform's perceived identity to a single domain. Two structural pressures forced the question on 2026-05-08:

1. **The architecture is data-agnostic; the name was not.** The framework's load-bearing primitives — router, ChildMCP plurality, vault, audit log, consent / cost / circuit-breaker gates, local-LLM guardian, deterministic processing, MCP transport — none of these are biosensor-specific. They compose around any sufficiently structured personal data. The biosensor framing was the first deployment recipe shipped end-to-end, not the platform's identity. A name that confined the platform to "biosensor" closed the door on every other recipe before any of them had a chance.

2. **The boss-architect's articulated vision is broader than the name implied.** In a strategic conversation on 2026-05-08, the boss-architect's vision crystallised as *"plug-and-play infrastructure that lets ANY individual turn ANY MCP-speaking LLM into something orders of magnitude more useful by giving it their own data — aspiration on the order of Python, Blender, or MCP itself."* That target is structurally incompatible with a domain-specific name. The first deployment recipe (HIP Lab researcher first-look) stays health-research-shaped; the platform's identity needs to be substrate-shaped.

The boss-architect supplied two narrowings to keep scope tractable: *"the next Obsidian"* (a beloved single-author tool with a plugin ecosystem) AND *"AI-optimized computer"* (a turnkey deployment-recipe shape). These narrowings shaped the rename criteria but not the name itself.

A separate question landed alongside the rename: the working term *"substrate"* used in design conversations was inadequate as a user-facing word. Substrate captures only the *foundation* property; the engine actually has three load-bearing properties — **persistence** (durable record), **navigability** (traversal / retrieval / reasoning across the record), and **stewardship** (audit, consent, scrubbing, reversibility, deterministic results). A user-facing word needs to gesture at all three.

## Decision

Rename the project to **Tailor**, with **Wardrobe** as the user-facing engine word. Both names land together in v7.0.0 because they're complementary halves of a single naming commitment, and shipping them separately would produce a half-named transitional state that confused users twice.

### Naming decisions, fully resolved

| Surface | New value | Was | Rationale |
|---|---|---|---|
| Display name | **Tailor** | "Biosensor MCP" | Character-shape; warm; suggests bespoke fitting; domain-neutral |
| PyPI distribution name | **`tailor-mcp`** | `biosensor-mcp` | The bare `tailor` is taken on PyPI; `tailor-mcp` matches the historical `biosensor-mcp` pattern and is available |
| Python import name | **`tailor`** | `biosensor_mcp` | Short, clean; PyPI normalisation does not require parity with distribution name (e.g. `pip install python-decouple` → `from decouple import config`) |
| CLI command | **`tailor`** | `biosensor-mcp` | Short, distinctive, English-natural; same name as the import keeps the surface coherent |
| Default config dir | **`~/.tailor/`** | `~/.biosensor-mcp/` | Mirrors the new project identity; migration was originally handled via `tailor migrate` (retired in v7.0.9 — see [ADR 0034](0034-retire-tailor-migrate-subcommand.md)) |
| Default data dir | **`~/.tailor/data/`** | `~/.biosensor-mcp/data/` | Same story |
| Env var prefix | **`TAILOR_*`** | `BIOSENSOR_*` | Three vars renamed: `TAILOR_CONFIG_DIR`, `TAILOR_DATA_DIR`, `TAILOR_DEMO_INSTALL_URL_BASE` |
| Claude Desktop key (main) | **`tailor`** | `biosensor-mcp` | Bare key; matches CLI command |
| Claude Desktop key (tour) | **`tailor-tour-<variant>`** | `biosensor-tour-<variant>` | Prefix shape preserved; just the prefix value changed |
| Diagnostic tool name | **`tailor_setup_help`** | `biosensor_setup_help` | User-visible to AIs via tools/list; v7 renaming applies |
| User-facing engine word | **Wardrobe** | (no prior word; "substrate" was internal-only) | New |

### Wardrobe — what the word names and what it does NOT name

A **Wardrobe** in Tailor is *what your AI knows about you*: the structured collection of your data and prior analytical work that lives entirely on your machine. The Wardrobe accumulates:

- **Themes** — persistent questions / hypotheses you keep returning to (research questions for a PI; recurring threads for a writer; case formulations for a clinician)
- **Moments** — observations worth remembering across sessions (an aha; a captured mid-analysis insight; a clinical impression)
- **Evidence** — data that grounds a theme (a specific time-window, a specific cohort comparison, a specific trace)
- **Failure modes** — documented dead-ends so the AI doesn't suggest them again
- **Audit history** — every action your AI took on your behalf, with timestamps, parameters, outcomes
- **Source data** — the biometric streams, CSVs, vault notes the AI reasons over

The word is a **user-facing aggregate term** for what the framework holds collectively on the user's behalf. Internally the framework retains its existing component names: `vault/` for the markdown storage layer (themes / moments / evidence / failure modes), `framework/` for the security pipeline, `audit.db` for the SQLite audit log, child SQLite caches for source data. Tailor *curates* the Wardrobe — adds to it, retrieves from it, governs how the AI reaches into it.

### Counter-programming invariant (load-bearing)

The Tailor + Wardrobe pairing has internal coherence (a tailor *does* manage wardrobes — that's a real-world thematic match) AND a real branding risk: a stranger encountering the project cold may read it as fashion-adjacent. The boss-architect's directive on 2026-05-08, after explicit consideration of less-thematic alternatives (Trove, Cabinet, Den, Keep), was *"commit + counter-program"* — accept the tight pairing's strength while actively redirecting the literal-clothing read.

The counter-programming invariant has three commitments, codified here so future contributors who drift from them are in measurable conflict with this ADR:

1. **Visual language stays non-fashion.** No fabric textures, no garment iconography, no haute-couture aesthetic anywhere in branding, README, demo, install ritual, web mirror, or future UI. The project's visual identity is workshop-shaped or infrastructure-shaped, never boutique.
2. **Onboarding copy actively redirects the literal-clothing read.** The first prose a stranger encounters that uses the word *Wardrobe* must define it explicitly — *"your personally curated collection of what matters to you, not clothes, your stuff."* The README, CLAUDE.md, and all future onboarding surfaces must treat this redirection as load-bearing copy, not optional polish.
3. **Content shown in any "your Wardrobe" view is visibly diverse from first impression.** A user (or AI) inspecting what's *in* a Wardrobe sees themes / moments / evidence / audit rows / data — not a single content type. This is the most powerful counter-programming move: showing rather than telling that *Wardrobe* doesn't mean clothes.

A pull request that adds fashion-domain language, fashion-domain imagery, or a single-content-type Wardrobe view is in conflict with this ADR. The reviewer should ask the contributor to revise OR explicitly override this ADR via a superseding ADR.

### Migration story (v6 → v7)

A v6 user upgrading to v7 has four pieces of state that need to migrate cleanly:

1. **Filesystem**: `~/.biosensor-mcp/` (configs, tokens, audit logs, vault, child caches) → `~/.tailor/`. Handled by the new `tailor migrate` subcommand. Non-destructive by default (copies; `--move` to remove the legacy directory after copying). Refuses to overwrite a non-empty destination.
2. **Environment variables**: `BIOSENSOR_CONFIG_DIR` / `BIOSENSOR_DATA_DIR` set in shell rc files, Claude Desktop config env blocks, or CI workflows → `TAILOR_CONFIG_DIR` / `TAILOR_DATA_DIR`. The user updates these by hand (the framework cannot reach into shell rc files); a startup warning fires when the legacy filesystem is present, pointing the user at `tailor migrate` and serving as the breadcrumb that env vars also need updating.
3. **Claude Desktop registration**: the v6.x cleanup function matched only `biosensor-*` prefixed keys. v7 widens the match to BOTH legacy `biosensor-*` AND current `tailor` / `tailor-*` (via the new `_is_orphan_entry_key` helper). Running `tailor tour` or `tailor uninstall` on an upgrade machine cleans every legacy `biosensor-*` entry alongside the new `tailor` entries. The cleanup function is renamed `_clean_claude_desktop_orphan_entries` to reflect that it handles both prefixes.
4. **PyPI install command**: `uv tool install git+https://github.com/saahasmuthineni/tailor-mcp.git` and `pip install tailor-mcp` (when published) replace the v6 install commands in docs. (Updated 2026-05-10 alongside the GitHub repo rename — see § Negative consequences known-debt closeout. GitHub's auto-redirect from the old `Biosensor-to-LLM-Connector` URL keeps any prior install command working for v7.0.0–v7.0.4 recipients who already ran it; new docs cite the new URL.)

A startup warning fires on every `tailor` invocation when `~/.biosensor-mcp/` exists and `~/.tailor/` is absent or empty:

```
[tailor v7.0] Legacy directory ~/.biosensor-mcp detected. Run `tailor migrate` to copy configs/data to ~/.tailor.
```

The warning is a single stderr line, non-blocking, no prompt — auto-prompts during `tailor serve` (which runs as a subprocess of Claude Desktop with stdin = JSON-RPC) would silently park, the same failure shape the v6.11.x recipient-install-validator hardenings were empirically falsified against. Code, not prompts, is the only enforcement that survives.

> **Retired 2026-05-12 in v7.0.9** — see [ADR 0034 (Retire `tailor migrate` subcommand)](0034-retire-tailor-migrate-subcommand.md). The `tailor migrate` subcommand AND the legacy-directory startup warning are both retired. The v6 → v7 population this migration mechanism was built for turned out to be empirically zero: no successful external v6 install ever happened, and the smoking-gun evidence is a 2026-05-12 hand-patch on the project author's own machine for a path-rewrite gap that would have produced broken Claude Desktop starts on any real v6 user's machine (because `cmd_migrate` never rewrote embedded absolute paths inside Claude Desktop config or `user_config.json`). Reversal: a real v6 install in the wild reverses this; restoring `cmd_migrate` is a code-revert but a safe restoration additionally requires fixing the path-rewrite gap. The rest of the rename (env vars, paths, package name, dual-prefix Claude Desktop cleanup) remains intact.

### Historical preservation

Three categories of files retain the old `biosensor-mcp` / `Biosensor MCP` references by design:

1. **`CHANGELOG.md`** — release notes describe what shipped under each name. Rewriting them would falsify the historical record.
2. **`docs/reports/*-2026-05-01.md`** — dated session reports. Snapshots of past state.
3. **`examples/hip_lab_demo/beta/vault/moments/2026-05-05-biosensor-mcp-6-9-0-...md`** — a captured vault moment from 2026-05-05. Vault moments are immutable historical artifacts; the filename's `biosensor-mcp` substring documents the project's name at the moment of capture.

Future release notes (this banner, ADR 0031, future changelog entries) use the new name. Future vault moments use the new name. Old artifacts stay as they were.

## Consequences

### Positive

- The name no longer confines the platform's perceived identity to biosensor data, opening the door to additional deployment recipes (knowledge work, clinical, household, creative) without a second rename.
- **Wardrobe** gives the user a single word for *what their AI knows*, which the framework previously had no concise word for — the architecture had `vault/`, `audit.db`, child caches as separate components, and prose had to describe them as "the framework's persistent state" or worse.
- The Tailor + Wardrobe pairing is **place-shape + character-shape** — Tailor names what curates, Wardrobe names what's curated. Each word does its own conceptual work; neither competes with the other for the same slot. The pairing is loose enough to survive metaphor stress (a future user encountering Tailor without first encountering Wardrobe still gets a coherent read).
- The dual-prefix Claude Desktop cleanup logic (matching both `biosensor-*` and `tailor*`) is broader than the migration story — it's a *generalisation* of the v6.9.2 prefix-match contract that handles future prefix changes without further refactor. If a future ADR introduces a third prefix, the matcher's contract is the only thing that needs to widen.
- The `tailor migrate` subcommand is a recipient-friendly upgrade path that the v6.10.x patch quartet's failure modes argued for: *"upgrades that silently abandon user data are a class of recipient bug we want closed at the framework level, not via docs."* **(Retired 2026-05-12 in v7.0.9 — see [ADR 0034](0034-retire-tailor-migrate-subcommand.md); the v6 → v7 population this bullet argued for turned out to be empirically zero.)**
- The release becomes a v7.0.0 — the first major version bump in the project's history. Every prior bump has been a minor or patch despite some ADRs (ADR 0013 added an abstract method; ADR 0009 changed vault subject-keying invariants) that were technically breaking. v7.0.0 sets a precedent that breaking changes get major bumps, which makes future versioning honest.

### Negative

- **A 1,400+ string occurrence rename across ~120 files is the largest single content change the project has ever shipped.** The risk surface is broad: dangling references, broken doc anchors, stale cached artifacts, untested shell rc updates. The phased commit structure (Phases 1–6 each a separate commit with gates between them) is the structural patch; the residual risk is the work between the developer's environment and a stranger's machine, which the recipient-install-validator would normally catch but which is empirically unreliable per the v6.11.x falsification documented in project memory. Operator hand-validation is the backstop for v7.0.0.
- **The counter-programming invariant has an ongoing maintenance cost** that simpler naming choices (Trove, Den, Keep) would have avoided. Every README revision, every demo redesign, every onboarding-copy edit, every visual asset has to actively redirect the literal-clothing read indefinitely. This is the cost of choosing a thematically-tight pair (Tailor + Wardrobe) over a thematically-loose one (Tailor + Keep). The invariant is the structural commitment that makes the pair survive its own marketing pressure.
- **"Tailor" is more brand-collision-prone than the prior name.** Several existing tech products use *Tailor* (Tailor.tech, Tailor Brands, various startups). The PyPI fallback to `tailor-mcp` is the structural mitigation; for casual context the name is just *Tailor*. This is a real cost; it was accepted because the alternatives (longer compound names, less-distinctive words) were structurally worse.
- **Existing v6 installs do not auto-migrate.** The user must explicitly run `tailor migrate` after upgrading the wheel. The startup warning makes the migration step visible, but a recipient running `tailor serve` for the first time on an upgraded machine will see the warning on stderr (which Claude Desktop swallows) without the user noticing. This is a small but real gap; the framework cannot auto-migrate on `serve` because that command's stdin is JSON-RPC, not a human, and any prompt would silently park.
  - **Closed 2026-05-12 in v7.0.9** — see [ADR 0034 (Retire `tailor migrate` subcommand)](0034-retire-tailor-migrate-subcommand.md). The v6 → v7 population this bullet was warning about turned out to be empirically zero: no successful external v6 install ever happened across the v6.10.x patch quartet, the v6.11.x falsified recipient-install-validator, the 2026-05-09 self-driven Windows install, or the 2026-05-12 first true outside-recipient macOS install (which was a fresh install with no v6 state). The `tailor migrate` subcommand and the legacy-directory startup warning are both retired. A future v6 install discovered in the wild reverses this and additionally requires fixing the path-rewrite gap (`cmd_migrate` never rewrote embedded absolute paths inside Claude Desktop config or `user_config.json`).
- **The GitHub repo (`saahasmuthineni/Biosensor-to-LLM-Connector`) is not renamed in this PR.** The repo rename is a separate operation (requires GitHub admin access and breaks every existing clone URL). GitHub's auto-redirect from old repo URLs makes the lag tolerable, but the URL referenced in `pyproject.toml`, README badges, and ADR cross-links still says `Biosensor-to-LLM-Connector`. This is documented as known debt; the repo rename can land separately.
  - **Closed 2026-05-10.** The GitHub repo was renamed `Biosensor-to-LLM-Connector` → `tailor-mcp` (matching the PyPI distribution name) as part of a Phase 1 doc-truth pass. `pyproject.toml`, README badges, install commands across `README.md` / `CLAUDE.md` / `docs/guides/multi-subject-pilot.md` / `docs/diagnosis/phase-0-diagnosis-kit.md` / `docs/external-review.md` / `examples/hip_lab_demo/beta/README.md`, and `ROADMAP.md`'s Phase 1 row all updated to the new URL. Historical artifacts (`CHANGELOG.md`, dated `docs/reports/*-2026-05-01.md`, dated vault daily notes, captured vault moments) preserved per § Historical preservation. GitHub's automatic redirect from the old URL preserves any existing clones, in-flight `uv tool install` commands, and external links indefinitely. The local working-copy directory at `c:\Users\saaha\Biosensor-to-LLM-Connector\` was not renamed (out of scope for the GitHub-rename operation).

### Neutral

- **Internal architectural identifiers are NOT renamed.** `framework/`, `vault/`, `local_llm/`, `children/`, `RouterMCP`, `VaultLayer`, `ChildMCP`, `RunningChild`, `audit.db`, `vault.db` — these stay. They describe the architecture, not the project's identity, and renaming them would introduce churn without clarifying anything.
- **Domain-term language is NOT renamed.** *"Biosensor children"*, *"biosensor-tier gates"*, *"biosensor data"* describe the kind of data those components handle (biological sensor data), not the project name. The framework continues to handle biosensor data; that domain terminology is still accurate.
- **The first deployment recipe (HIP Lab researcher first-look) is unchanged.** The bundled fixtures, the `tailor tour` command, the `tailor demo` command, the demo runner output — all carry the new naming, but the recipe's content (force / EMG / 31P-MRS cohort analysis on 16 synthetic subjects) is what it was. Future deployment recipes compose on the same engine without disturbing this one.

## Alternatives considered

### Alternative 1: Stay on v6 with the old name

The architecturally cleanest "do nothing" option. The project would continue to ship under *Biosensor MCP*, the engine word would remain conversational-only ("substrate"), and future deployment recipes would either inherit a confusing name or be released as separate projects.

**Rejected because**: the boss-architect's articulated vision is structurally incompatible with the old name, and the cost of a rename grows with every future deployment recipe. Doing the rename at v7.0.0 (when the platform has one shipped recipe and limited adoption) is dramatically cheaper than doing it later.

### Alternative 2: Rename the project but skip the engine word ("Tailor + no Wardrobe")

Use *Tailor* for the project, leave *substrate* as the conversational working term, don't introduce a user-facing engine word at all.

**Rejected because**: the architecture has a real "thing the AI knows" that previously had no concise user-facing name. Without *Wardrobe* (or a chosen equivalent), every piece of onboarding copy has to describe the same aggregate concept ad-hoc, and the user has no shared vocabulary with the AI. The engine word is more load-bearing than its absence in v6.x suggested.

### Alternative 3: Different engine words considered

The boss-architect and main session iterated through five engine-word candidates before landing on Wardrobe:

- **Memory** — eliminated because it captured only the *storage* property, not navigability or stewardship. The user pushed back: *"isn't it more than the memory though as it also handles things like navigating and governing that memory."*
- **Keep** — survived the three-property criterion best (place-shape, durable, governance-forward) and pairs cleanly with Tailor (loose pairing). Was the leading candidate before *Wardrobe* surfaced.
- **Hold** — verby, neutral, captured all three properties evenly but lightly. Less distinctive than Keep.
- **Trust** — relational + fiduciary stewardship metaphor. Heavier connotation; collides with *trust models / zero trust* in tech vocabulary.
- **Hearth** — warm, intimate, but weaker on the audit / consent / governance shape than place-shaped alternatives.
- **Wardrobe** — the boss-architect's suggestion. Captured *intimate-curated-accumulation* warmth that Keep / Hold / Trust did not. The clothing-domain risk was the cost; *commit + counter-program* was the chosen mitigation.

The consideration of these alternatives is preserved here so a future ADR proposing a different engine word can argue against the specific reasoning that landed on *Wardrobe* rather than against an unstated prior.

### Alternative 4: Alternative project names considered

The boss-architect surfaced *Tailor* unprompted. The main session evaluated it under the three-criterion frame established for the engine word and found it strongest for the project name (where character-shape is appropriate) but inadequate for the engine word (where place-shape is needed). The Tailor + Wardrobe split — product / engine — is the resolution of that tension.

Other project names briefly considered and rejected:

- **Substrate** — too jargon-y for a product; an engineering word, not a brand
- **Anchor** — grounded but lacked the personalisation aesthetic Tailor carries
- **Atelier** — tightly thematic with Tailor (a tailor's workshop) but pretentious as a standalone product name; consigned to "synthesis word" status during the engine-word iteration
- **Mneme / Memory / Recall** — character-shape candidates eliminated for the same reasons as the engine word (too narrow on storage, too generic, trademark-heavy)

### Alternative 5: Don't ship the counter-programming invariant — accept the fashion read

Pick *Tailor + Wardrobe* and let strangers read the project as fashion-adjacent. Fix it later if it becomes a real adoption barrier.

**Rejected because**: the cost of fixing a brand misperception *after* it sets is dramatically higher than the cost of redirecting it from day one. Plex's "library" successfully expanded beyond books because Plex's earliest content explicitly was movies / TV / music, never books. A *Wardrobe* whose earliest content is themes / moments / audit rows / biometric data has the same structural opportunity to expand beyond clothes — but only if the redirect is consistent from first impression. Letting the fashion read set first means fighting it for years.

### Alternative 6: Phased rename across multiple releases

Rename the package and CLI in v7.0.0; defer the prose / README rewrite to v7.1.0; defer the engine word to v7.2.0.

**Rejected because**: a half-renamed project produces incoherent docs (CLI says `tailor` but README says *Biosensor MCP*; pyproject.toml says `tailor-mcp` but the framework banner reads *Biosensor MCP — Status Check*) that confuse users twice — once at the partial rename, once at the completion. The rename's atomicity is the only state that's actually coherent; phased delivery is structurally worse than a single bigger PR.

## Reversal conditions

This ADR can be revisited (or superseded) under any of the following conditions:

1. **The counter-programming invariant proves untenable in practice.** If the project consistently fails to keep fashion-domain language out of branding / docs / UI despite genuine effort, the *Wardrobe* engine word should be replaced with one of the runner-up alternatives (Trove or Cabinet are the closest; Keep is the safest). The replacement is a major version bump unless the engine word never appeared on a stable surface.
2. **A trademark conflict materialises around *Tailor* or *Wardrobe*.** Specifically: if a credible cease-and-desist arrives, or if a trademark search before any commercial offering surfaces a conflict that legal counsel deems material. The fallback name candidates are documented in Alternatives § 4 of this ADR.
3. **The architecture diverges from the substrate framing.** If a future major architectural shift (e.g. moving the framework from local-first to a hybrid local-cloud topology) would make the *Wardrobe* metaphor structurally inaccurate, the engine word is revisited as part of that shift.
4. **Adoption signals reveal a different audience.** If the project's actual user base concentrates around a tribe whose culture clashes with the *Tailor* aesthetic (e.g. if academic IRB committees consistently object to the bespoke-craft framing as inappropriate for medical-data infrastructure), the project's voice is revisited via a follow-up ADR.

The reversal conditions are deliberately *not* "the rename feels imperfect" or "a contributor disagrees with the chosen names." Names are always partly arbitrary; once chosen and shipped at v7.0.0, the project's identity stabilises around them. Reversing them again carries a cost (the v6 → v7 migration cost) that is only worth paying for one of the structural conditions above.
