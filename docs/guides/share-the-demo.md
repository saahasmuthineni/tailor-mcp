# Share the demo with a friend (one URL)

**Audience:** the boss-architect, when they want to send `biosensor-mcp
demo` to a technical friend (CS grad, researcher, RSE) for evaluation.
This guide walks through the one-time public-mirror setup and the
per-release ritual that produces the shareable URL.

**Why this exists:** [ADR 0024 § 3.1](../adr/0024-wheel-distributed-tour-and-fixture-bundling.md)
codifies a public release-only mirror as a carve-out alongside the
existing Drive/email distribution channel. The carve-out is for the
specific use case *"send a friend the demo via one URL; let them
evaluate without account, clone, or env-setup ritual."* Source repo
stays private; only the release artifact + transcript page are
public. Synthetic-by-construction precondition (ADR 0024 § 4) is
load-bearing — never reverse without re-reading that section first.

---

## One-time setup (~10 minutes)

Steps you do once. Skip after the first release if already done.

### 1. Create the public mirror repo

On GitHub:
- Click **+ → New repository**
- Owner: your account
- Repository name: `biosensormcpdemo`
- Description: *"Public release distribution + demo transcript for
  Biosensor MCP. Source repo is private — see project author for
  details."*
- Visibility: **Public**
- Initialize with a README ✓
- Click **Create repository**

### 2. Replace the auto-generated README

The mirror's home page is what the friend lands on. Replace the
default README with this minimal page (the per-release ritual below
will overwrite this with the transcript-rendered version on each
release; the initial content is just a placeholder).

```markdown
# Biosensor MCP — public release distribution

Local-first infrastructure for LLM-assisted analysis of biometric
data. The source repo is private (ask the author for access if
interested in the design). This repo exists only to host:

- Release wheels as GitHub release assets
- A rendered transcript of `biosensor-mcp demo` (regenerated on
  each release)

A friend evaluating the framework should run:

```
uvx --from <wheel-url-from-latest-release> biosensor-mcp demo
```

The latest release page has the wheel URL.
```

Commit directly to `main`.

### 3. Configure GitHub Pages

On the new repo:
- Go to **Settings → Pages**
- Source: **Deploy from a branch**
- Branch: `main`, Folder: `/(root)`
- Click **Save**

GitHub Pages will publish at
`https://<your-username>.github.io/biosensormcpdemo/` within ~30
seconds. That's the URL you'll send to friends.

### 4. Create a Personal Access Token for `release-shipper`

`release-shipper` (when extended in a future release) needs write
access to the public mirror to push wheels + update the transcript.
Until that extension lands, the per-release ritual below is manual.

For when the automation is wired:
- GitHub **Settings → Developer settings → Personal access tokens →
  Tokens (classic)**
- Click **Generate new token (classic)**
- Note: `biosensormcpdemo release publish`
- Expiration: 90 days (rotate per cycle)
- Scope: `public_repo` (the only one needed)
- Click **Generate token**, copy it
- In a PowerShell session, set the env var (persists per terminal):
  ```
  $env:GITHUB_TOKEN_DEMO_REPO = "ghp_..."
  ```
- Or persist machine-wide via **System → Environment Variables**.

---

## Per-release ritual (until release-shipper extension lands)

Steps to run after each `release-shipper` invocation that ships a new
version. Manual until the extension lands; the extension folds these
into the existing ship-it flow.

### 1. Build the wheel

```
python -m build
```

This produces `dist/biosensor_mcp-<version>-py3-none-any.whl`.

### 2. Generate the shareable transcript

```
biosensor-mcp demo --save-shareable
```

By default this writes to
`~/.biosensor-mcp/shareable-demo-v<version>.md`. The output path is
printed at the end of the demo. You can also pass an explicit path:

```
biosensor-mcp demo --save-shareable demo-share.md
```

### 3. Push to the public mirror

In your local clone of `biosensormcpdemo` (the public repo):

1. Copy the shareable markdown into the repo as `README.md` (renaming
   from the default `shareable-demo-v<version>.md`):
   ```
   cp ~/.biosensor-mcp/shareable-demo-v<version>.md ./README.md
   ```
   GitHub Pages will render this as the home page.

2. Commit and push:
   ```
   git add README.md
   git commit -m "Update transcript for v<version>"
   git push
   ```

3. Create a GitHub release with the wheel attached:
   ```
   gh release create v<version> dist/biosensor_mcp-<version>-py3-none-any.whl --title "v<version>" --notes "Demo for v<version>. See https://<your-username>.github.io/biosensormcpdemo/ for the rendered transcript."
   ```

### 4. Verify

- Open `https://<your-username>.github.io/biosensormcpdemo/` in a
  browser. Confirm:
  - The transcript is the latest version (check the version-stamp at
    the top).
  - The `uvx --from <wheel-url> biosensor-mcp demo` command in the
    page points at a valid release URL.
- Click the wheel-URL itself; confirm GitHub serves the wheel file.
- (Optional, on a clean machine) run the `uvx` command yourself to
  confirm end-to-end installation works against the public URL.

### 5. Send the URL

Copy `https://<your-username>.github.io/biosensormcpdemo/` and
paste it into any channel. The friend opens, reads the transcript,
and optionally runs the one-line install command on their own
machine.

---

## When NOT to share publicly

The carve-out preserves three invariants from ADR 0024 § 3.1; if any
of these is in question, do not push to the public mirror:

1. **Source repo must stay private.** If the project's privacy
   trajectory has shifted (IRB-review-ready, public-collaborator
   onboarding, PyPI publication considered), revisit § 3.1 and
   ADR 0024 Alternative 1 before extending the public footprint.
2. **Bundled bytes must be synthetic by construction.** If a release
   bundles real or de-identified-real participant data — even
   accidentally — the public wheel becomes a covered-data egress
   event. Treat as a security incident; rotate the public mirror to
   private, audit who downloaded the wheel, escalate to whichever
   IRB / institutional channel has authority. ADR 0024 § 4 is the
   gating section.
3. **Recipient scale must remain handful-sized.** ~10+ public
   evaluators is the signal that PyPI publication is the right
   answer (ADR 0024 Alternative 1). The mirror is a friction-
   reducing intermediate, not a scaling step.

If any of these trip, retire the public mirror (`gh repo delete
saahasmuthineni/biosensormcpdemo`) and revert to ADR 0024 § 3's
Drive/email-only path. The mirror is purely additive; deletion is
reversible.

---

## Files this guide references

- [ADR 0024 § 3.1](../adr/0024-wheel-distributed-tour-and-fixture-bundling.md)
  — the carve-out's invariants and reversal conditions.
- [ADR 0029](../adr/0029-token-reduction-as-analytical-quality.md) —
  the demo reshape that makes the demo worth sharing publicly.
- `src/biosensor_mcp/demo/runner.py` — the
  `--save-shareable` implementation.
- `src/biosensor_mcp/__main__.py:cmd_demo` — the CLI flag wiring.
