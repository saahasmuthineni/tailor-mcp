# ADR 0042: Docs and notebooks may instruct a fingerprint-pinned runtime download of public datasets

- **Status:** Proposed
- **Date:** 2026-05-28
- **Related:**
  - [ADR 0024 (Wheel-distributed tour and fixture bundling)](0024-wheel-distributed-tour-and-fixture-bundling.md) — the bundling boundary this ADR scopes against; § 4's synthetic-by-construction precondition is **not** amended (see § Decision and § Alternatives)
  - [ADR 0003 § Amendment 2026-05-15 (Trust-root attestation seam)](0003-phi-scrubber-seam.md) — the `source_metadata_fingerprint` canonical-form pin this ADR reuses on the docs surface
  - [ADR 0001 (Audit log is the backbone)](0001-audit-log-as-backbone.md) — the provenance-first commitment a pinned download demonstrates
  - [ADR 0008 (Deterministic-by-construction processing)](0008-deterministic-by-construction-processing.md) — a pinned dataset is the docs-surface analogue of the determinism invariant
  - [ADR 0017 (ADR-weigher and autonomous-session cap)](0017-adr-weigher-and-autonomous-session-cap.md) — this ADR was weighed PASS under the autonomous-ADR gate before drafting

> **Flip-to-Accepted trigger.** This ADR is Proposed because the
> governed behavior is not yet in the repo. It flips to Accepted when
> the issue-114 worked-example notebook lands with the pin-and-provenance
> mechanism implemented — the same Proposed→Accepted-on-ship pattern
> [ADR 0024 § 3.1](0024-wheel-distributed-tour-and-fixture-bundling.md)
> and [ADR 0038](0038-vault-layer-is-data-source-agnostic.md) use.

## Context

The launch worked-example notebook (issue #114) wants to show Tailor
producing a *real number from real public data* — strong-motion
acceleration from a CESMD station, a price prediction over the Ames
Housing dataset — not yet another synthetic fixture. Synthetic fixtures
prove the pipeline runs; they do not answer the question a skeptical
researcher actually asks, which is *"does this say something true about
data I recognize?"* A worked example that opens on `random.Random(...)`
output cannot answer that.

The bytes those notebooks need cannot ship in the wheel.
[ADR 0024 § 4](0024-wheel-distributed-tour-and-fixture-bundling.md)
governs what bytes ship *inside* the wheel: every byte in `_fixtures/`
must be synthetic by construction, because a wheel sent over email or
published to PyPI leaves the institution's data-governance perimeter and
cannot be recalled. That precondition is load-bearing and correct, and
nothing here changes it. But a notebook that downloads a public dataset
at runtime is not a bundling event. No byte enters `_fixtures/`; no byte
ships in the wheel. The notebook is *the user pointing Tailor at data
they fetched* — which is the product's central use case, not an
exception to it.

So ADR 0024 is the wrong frame for this question. Reaching for it would
either forbid the download (gutting the worked example) or force an
amendment that muddies a crisp bundling rule with a runtime-fetch rule
it was never written to carry. The docs/notebook surface needs its own
bright line.

A reviewer's instinct is to flag a runtime download as exactly the thing
this project exists to prevent: an uninstrumented data flow with no
provenance, no checksum, no record of where the bytes came from. That
instinct is right about the risk and points directly at the answer.
Provenance is what Tailor *is*. The question this ADR answers is: *under
what discipline may a doc or notebook instruct a runtime download, such
that the download becomes a demonstration of the product's own
provenance discipline rather than a hole in it?*

## Decision

Docs and notebooks **may** instruct a runtime download of an
openly-licensed public dataset, provided each download is
fingerprint-pinned and the pin is recorded as a provenance entry before
any byte of the data is analyzed.

- **The pin is four fields:** the source URL, the SHA-256 of the
  retrieved bytes, the dataset's license identifier, and the retrieval
  timestamp. The notebook records these as a provenance entry — printed,
  written to the notebook's own audit surface, or both — as its first
  action on the data, before the first analytical cell runs.
- **The checksum is verified, not just recorded.** The downloaded bytes
  are hashed and compared against the pinned SHA-256. On mismatch the
  notebook fails loud with a clear message naming the expected and
  actual digests, and falls back to a cached expected value rather than
  silently analyzing drifted upstream bytes. A launch notebook never
  opens on a red assertion cell caused by an upstream file moving under
  it.
- **The pin reuses an existing mechanism, not a new one.** This is the
  docs-surface analogue of
  [ADR 0003 § Amendment 2026-05-15](0003-phi-scrubber-seam.md)'s
  `source_metadata_fingerprint`: a canonical-form fingerprint
  (SHA-256 over the retrieved bytes) recorded so a reviewer can
  reconstruct *which state* of an external input a result was computed
  against. The trust-root pattern is identical; only the surface differs
  (a notebook cell rather than an audit-log column).
- **The license bright line is positive, not just a carve-out.**
  Permitted: data that is public-domain, OR carries an
  OSI-approved or Creative-Commons-style open license, AND is reachable
  by a plain anonymous GET — no click-through agreement, no credential,
  no registration gate. The two motivating datasets clear this bar:
  **CESMD strong-motion** records (US-government public-domain, no
  login) and the **Ames Housing** dataset (De Cock 2011, openly shared,
  no login).
- **Package and wheel contents are unchanged.** Everything that ships
  inside the wheel remains synthetic by construction per
  [ADR 0024 § 4](0024-wheel-distributed-tour-and-fixture-bundling.md).
  This ADR adds a rule for the docs/notebook surface; it does **not**
  amend ADR 0024, which continues to govern `_fixtures/` exactly as
  written.

Data that is PHI, governed by a data-use agreement, or
credential/registration-gated is **out of scope** and still requires a
superseding ADR before any doc or notebook may instruct its download.
Concretely, the following do **not** clear this ADR's bright line:
CC-BY-NC or other non-commercial-restricted datasets, "free with
registration" downloads, Kaggle-login-gated files, and any PHI or
DUA-covered data. The line is not "is it free" — it is "is it openly
licensed and reachable by an anonymous GET, with no possibility of
covered data passing through."

## Consequences

### Positive

- **Worked examples cite real numbers.** The launch notebook can show
  Tailor producing a recognizable result over a recognizable dataset,
  which is the evidence a skeptical researcher asks for and a synthetic
  fixture cannot supply.
- **Provenance-by-default on the most-scrutinized artifact.** The
  notebook's first action is to record where its data came from and
  verify the checksum before analysis. The risk a reviewer would flag —
  an uninstrumented data flow — is inverted into the opening
  demonstration of the product's own discipline. The flagged gap becomes
  the demo.
- **Supply-chain integrity.** Pinned bytes cannot silently drift. An
  upstream file that is re-versioned, corrupted, or swapped fails the
  checksum compare loudly instead of feeding changed numbers into a
  result a reader would trust.
- **Reproducibility on the docs surface.** A pinned dataset is the
  docs-surface analogue of
  [ADR 0008](0008-deterministic-by-construction-processing.md)'s
  determinism invariant: the same notebook over the same pinned bytes
  produces the same number on any machine, because the bytes are pinned
  by hash rather than fetched fresh each run.

### Negative

- **Contributors must pin every dataset.** Authoring a notebook that
  uses public data now carries a fixed cost: download once, record the
  URL, SHA-256, license, and timestamp, and wire the verify-and-fallback
  cell. This is mild friction on every new data-using notebook.
- **A moved or re-versioned upstream file requires re-pinning.** When an
  upstream maintainer replaces a file, the notebook's checksum compare
  fails and a contributor must re-fetch and re-pin. This is a real
  maintenance cost — but it fails loud, not silent, so it surfaces at
  authoring or CI time rather than corrupting a result.

### Neutral

- **This is a docs-surface rule.** It governs what a doc or notebook may
  instruct. It does not touch the router, the security pipeline, any
  child's `execute()` path, or the audit-log schema. The fingerprint
  pattern is borrowed from ADR 0003's trust-root seam, but no framework
  code changes to honor this ADR.
- **The synthetic-by-construction boundary is intact.** A reader of both
  ADRs sees two distinct bright lines: ADR 0024 governs wheel bytes
  (must be synthetic); this ADR governs notebook downloads (must be
  openly-licensed and pinned). Neither relaxes the other.

## Alternatives considered

**Amend ADR 0024 to permit bundling or downloading public data.**
Fold the runtime-download rule into ADR 0024's § 4 precondition, so one
ADR governs both wheel bytes and notebook fetches. Rejected — wrong
frame. ADR 0024 § 4 answers a single crisp question (*what bytes ship
inside the wheel?*) with a single crisp answer (*synthetic by
construction*). A runtime download puts no bytes in the wheel; bending
ADR 0024 to cover it would dilute a rule that earns its clarity from
being narrow. The two concerns are genuinely separate decisions and
belong in separate ADRs. Keeping ADR 0024 untouched preserves the
bright line that makes the wheel publicly shareable in the first place.

**No runtime downloads — notebooks stay synthetic-only or bundle data.**
Forbid runtime fetches entirely; every notebook either uses the bundled
synthetic fixtures or the contributor commits the data into the repo.
Rejected — this guts the reproduce-a-real-number worked example, which
is the whole point of issue #114. Synthetic-only notebooks cannot answer
*"does this say something true about data I recognize?"* And committing
public datasets into the repo re-creates the bundling-boundary problem
ADR 0024 exists to keep clean, while bloating the repo with bytes that
already live at a stable public URL. The pinned-download path gets the
real number without either cost.

## Reversal condition

The first contributor who needs a credential-gated or
restrictively-licensed dataset (CC-BY-NC, registration-gated, DUA-bound,
or PHI) in a doc or notebook triggers a superseding ADR. That ADR would
need to address — at minimum — how the credential is provisioned without
committing it, what the notebook's provenance entry records when the
source is access-controlled, and whether the resulting artifact may ship
or be shared publicly at all. Until then, the bright line holds:
openly-licensed, anonymous-GET, fingerprint-pinned.
