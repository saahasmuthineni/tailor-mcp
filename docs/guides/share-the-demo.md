# Share the demo with a friend (wheel-by-email)

> **Status: superseded as the primary channel (2026-06-11).** This
> guide's own § "When NOT to share" names the retirement condition:
> once PyPI publication lands and the repo is public, *"friends
> install via PyPI directly"* — both landed with v9.0.x
> (`uv tool install tailor-mcp`; public repo). Point friends at the
> README. The ritual below remains valid for the narrow case of
> sharing a pre-release build that isn't on PyPI yet. Command
> surfaces updated for v8.0.0+ (per
> [ADR 0040](../adr/0040-bounded-setup-time-conductor-surface.md), the
> `tailor walkthrough` CLI verb is removed; the walkthrough runs as
> `python -m tailor.demo` from a terminal, or as the
> `tailor_walkthrough_section` MCP tool from Claude Desktop chat).

**Audience:** the boss-architect, when they want to send Tailor's
walkthrough (formerly the `tailor walkthrough` / `tailor demo` CLI
verbs; renamed in v7.1.0 per
[ADR 0035](../adr/0035-cli-rename-walkthrough-and-fitting-room-and-recipient-experience-naming-principle.md),
removed as CLI verbs in v8.0.0 per ADR 0040)
to a technical friend (CS grad, researcher, RSE) for evaluation.

**Why this exists:** [ADR 0024 § 3](../adr/0024-wheel-distributed-tour-and-fixture-bundling.md)
defines wheel-by-email as the friend-shareable distribution channel
through Phase 1 of the project's lifecycle. The synthetic-by-construction
precondition (ADR 0024 § 4) is load-bearing — never reverse without
re-reading that section first.

> **Historical note (2026-05-09).** A public-mirror carve-out at
> `saahasmuthineni/biosensormcpdemo` ran from v6.11.1 through v6.13.0
> per ADR 0030 + ADR 0024 § 3.1 amendment. The mirror was retired in
> v7.0.6 per [ADR 0032](../adr/0032-retire-public-mirror-distribution.md)
> — wheel-by-email is sufficient through Phase 1 and the mirror's
> reason-for-being (Pages-from-private-repo workaround on a free GitHub
> plan) is structurally moot under ROADMAP § Phase 2's "make source repo
> public" commitment. The mirror repo is archived (not deleted) so prior
> friend-shares via the legacy URL continue to resolve. ADR 0030's
> zero-outbound-affordances rendering invariant is **retained** and
> governs wheel-handoff render output as described below.

---

## The four-step ritual (~5 minutes per release)

### 1. Build the wheel

From the source-repo working tree:

```
python -m build
```

This produces `dist/tailor_mcp-<version>-py3-none-any.whl`.

### 2. Render the shareable transcript

Always pass `--audience=public` (per [ADR 0030](../adr/0030-public-mirror-narrative-and-affordance-depth.md)
+ [ADR 0032](../adr/0032-retire-public-mirror-distribution.md)):

```
python -m tailor.demo --audience=public --save-shareable transcript.md
```

In `--audience=public` mode the saved markdown gets per-persona reading
panels (PI / analyst / IRB) spliced after each demo section, an
attribution-only footer (no outbound contact mechanisms — no mailto, no
Discord, no contact form per ADR 0030's zero-outbound-affordances
invariant), and a render-time URL-allowlist check that hard-fails if
any disallowed outbound URL appears.

If `python -m tailor.demo --audience=public --save-shareable` fails with
`ValueError: ...rendered output contains disallowed outbound URL...`,
that is the ADR 0030 render-time allowlist working as designed: a
contributor accidentally introduced a contact mechanism on the public
surface. Fix the offending link before sending; do not work around it
by passing `--audience=developer` (the developer-mode shape is wrong
for friend-share output).

### 3. Send the email

Attach two files to a personal email to the friend:

1. The wheel: `dist/tailor_mcp-<version>-py3-none-any.whl`
2. The transcript: `transcript.md`

Body: a one-paragraph note saying *"here's that thing I was telling you
about — install with `uv tool install ./tailor_mcp-<version>-py3-none-any.whl`,
then run `python -m tailor.demo`, transcript attached for context."*

The friend's machine prerequisites are the same as for any Tailor
recipient (per [README.md § Prerequisites](../../README.md)): `uv` (or
pipx) installed; Claude Desktop optional but recommended for the full
MCP integration.

### 4. Verify on a clean machine (optional)

If you want to confirm the wheel works for the friend before sending,
on a different account or VM:

```
uv tool install ./tailor_mcp-<version>-py3-none-any.whl
python -m tailor.demo
```

Should produce the same five-section demo output. The transcript file
is a frozen snapshot of that output rendered with `--audience=public`;
the friend can read it without running anything.

---

## When NOT to share

The carve-out preserves three invariants from ADR 0024 § 3.1; if any
of these is in question, do not send the wheel:

1. **Source repo must stay private through Phase 1.** If the project's
   privacy trajectory shifts (Phase 2 PyPI publication landed,
   public-collaborator onboarding, IRB-review-ready), the wheel-by-email
   path is no longer the right channel — friends install via PyPI
   directly. ADR 0024 Alternative 1 governs.
2. **Bundled bytes must be synthetic by construction.** If a release
   bundles real or de-identified-real participant data — even
   accidentally — the wheel becomes a covered-data egress event. Treat
   as a security incident; rotate any in-flight wheels, audit who
   received the wheel, escalate to whichever IRB / institutional channel
   has authority. ADR 0024 § 4 is the gating section.
3. **Recipient scale must remain handful-sized.** ~10+ public
   evaluators is the signal that PyPI publication is the right answer
   (ADR 0024 Alternative 1 + ROADMAP § Phase 2). Wheel-by-email is a
   friction-reducing intermediate, not a scaling step.

---

## Files this guide references

- [ADR 0024 § 3](../adr/0024-wheel-distributed-tour-and-fixture-bundling.md)
  — wheel-by-email distribution channel + carve-out invariants.
- [ADR 0030](../adr/0030-public-mirror-narrative-and-affordance-depth.md)
  — `--audience=public` rendering shape + zero-outbound-affordances
  invariant (retained under ADR 0032).
- [ADR 0032](../adr/0032-retire-public-mirror-distribution.md) — public
  mirror retirement; what was retired, what was retained, why.
- [ROADMAP.md § Phase 2](../../ROADMAP.md) — the *"Publish to PyPI as
  `tailor-mcp`"* + *"Make the GitHub repo public"* commitments that
  retire wheel-by-email naturally.
- `src/tailor/demo/runner.py` — the `--save-shareable` implementation.
- `src/tailor/demo/__main__.py` — the `python -m tailor.demo` flag
  wiring (the `cmd_walkthrough` CLI dispatch it replaces was
  hard-removed from `__main__.py` in v8.0.0 per ADR 0040).
