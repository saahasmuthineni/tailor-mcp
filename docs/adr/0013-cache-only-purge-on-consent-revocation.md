# ADR 0013: Cache-only purge on consent revocation — mandatory, synchronous, fail-closed

- **Status:** Accepted
- **Date:** 2026-04-30
- **Related:** [ADR 0001 (Audit log is the backbone)](0001-audit-log-as-backbone.md), [ADR 0003 (PHI scrubber seam)](0003-phi-scrubber-seam.md), [ADR 0009 (Vault subject-keying)](0009-vault-subject-keying.md), [ADR 0012 (Vault PHI-scrubber bypass)](0012-vault-phi-scrubber-bypass.md), [ROADMAP.md § Real PHI-scrubbing implementations](../../ROADMAP.md#real-phi-scrubbing-implementations-behind-the-phiscrubber-slot)

## Context

`ConsentGate.revoke()` flipped an in-memory dict and returned. That
was the entire revocation path through v6.3. A participant withdrawing
consent — or an analyst calling `revoke_consent_running` after the
end of a session — saw consent state change to "revoked" while every
cached row of their biometric data sat untouched in `activities.db`
under `~/.tailor/data/`. The Strava stream cache continued to
hold the per-second HR, pace, and GPS rows that originated from the
participant's wearable; the CSV-directory child held no derivative
cache, but the framework had no contract that distinguished one case
from the other.

The Lens 6 retention WATCH from the v6.3.0 hygiene pass surfaced this
explicitly. The IRB-committee lens reads the asymmetry as: *consent
is the gate that authorises a child to read participant data; the
cache is the on-disk evidence that the data was read; revocation
that touches only the gate but not the evidence is a governance
fiction*. `STRAVA_STREAM_CACHE_TTL_DAYS=7` mitigates the window but
does not close it — a participant who withdraws on day 1 still has
cached PHI on disk through day 7, with no signal in the audit log
that the data was supposed to be gone on day 1.

The framework had three options at this seam: leave revocation as
a state flip and document the cache lifecycle as the deployer's
problem; build a framework-owned cache-and-vault purge that
guarantees revocation removes every derivative artifact; or build a
narrower cache-only purge that handles the biometric-cache case the
framework owns and explicitly defers vault to its own ADR-governed
persistence tier. The first re-creates the governance fiction the
WATCH named. The second couples revocation to the vault's append-only
invariants ([ADR 0009](0009-vault-subject-keying.md)) in a way that
would force the framework to take a position on whether analyst-
authored notes survive the participant they describe — a question
that belongs to the IRB protocol, not the framework.

The question this ADR answers: *what is the smallest contract on
`ChildMCP` that turns consent revocation into a real on-disk
guarantee for the biometric cache, without overcommitting to vault
purge semantics that depend on study-specific IRB language?*

## Decision

Consent revocation purges the biometric cache before flipping
consent state. The purge is mandatory on every child, runs
synchronously inside the revocation handler, produces a paired
audit row, and fails closed by default with a `force_revoke=True`
escape hatch for locked-cache edge cases.

The IRB invariant this ADR codifies: *consent revocation for a
domain leaves no cached participant biometric data on disk for that
domain.* The ordering invariant: *purge first, then flip consent —
if purge fails, consent stays approved.*

- **Mandatory abstract method.** `ChildMCP` declares
  `purge_cache(*, force: bool = False) -> dict` as
  [`abstractmethod`](../../src/tailor/framework/interfaces.py).
  Every child must implement it. There is no default no-op.
  ADR 0003's PHI-scrubber pattern (default no-op + warning) is
  deliberately *not* reused here: the asymmetry is that PHI
  scrubbing's policy depends on the IRB and cannot be defaulted
  honestly, while cache identification is a structural property of
  the child — the child knows which tables hold biometric rows
  because the child wrote them. A default no-op would re-create the
  exact failure mode the WATCH surfaced, with the framework signing
  off on it.
- **Synchronous execution.** The router calls
  `child.purge_cache(force=force_revoke)` inside
  `_handle_consent_revocation` at
  [`router.py:889-891`](../../src/tailor/framework/router.py),
  not on a background thread. An asynchronous purge would open a
  window in which `consent.is_approved(domain)` returns `False`
  while the cache still holds rows from the just-revoked subject —
  the audit log would record revocation before the disk caught up.
  Synchronous purge collapses that window to zero.
- **Fail-closed ordering.** The handler runs purge first. If
  `purge_cache` raises and `force_revoke=False`, the router writes
  a `PURGE_FAILED` audit row, leaves consent approved, and returns
  an error to the caller naming ADR 0013. If purge succeeds (or
  `force_revoke=True` swallows the error into the return dict's
  `errors` list), the router calls `self._consent.revoke(domain)`
  and writes the paired audit rows.
- **Paired audit rows per revocation.** A successful revocation
  produces two rows in `audit.db` (per [ADR 0001](0001-audit-log-as-backbone.md)):
  one with `tool_name = "purge_cache"` and `outcome = "PURGE_CACHE"`
  carrying `force_revoke` and (via the child's return dict) the
  rows-purged count, and one with `tool_name = "revoke_consent_<domain>"`
  and `outcome = "SUCCESS"`. Both rows carry `scrubber_id` from the
  active `PHIScrubber` so a reviewer can correlate the revocation
  with the scrubber configuration in effect. A failed revocation
  produces one `PURGE_FAILED` row and no `SUCCESS` row — absence
  of the SUCCESS row is itself the signal.
- **`force_revoke=True` escape hatch.** The handler accepts an
  optional `force_revoke` parameter. When true, `purge_cache` is
  called with `force=True`, the child swallows I/O errors into the
  returned dict, and revocation proceeds even if the cache file
  was (e.g.) locked by an external process. The escape hatch is
  recorded in the audit row's params (`force_revoke=True`) so a
  reviewer can distinguish a clean revocation from a forced one.
- **Cache-only scope, not vault purge.** `purge_cache` deletes
  rows from biometric tables only. `RunningChild.purge_cache`
  removes rows from `activities` and `streams`, preserves
  `stop_labels` (analyst-authored). Vault notes are not touched
  here; vault is a separate persistence tier governed by
  [ADR 0009](0009-vault-subject-keying.md) and
  [ADR 0012](0012-vault-phi-scrubber-bypass.md), and its retention
  story depends on whether analyst-authored notes survive the
  participant they describe — a study-specific question this ADR
  refuses to answer on the IRB's behalf.
- **Children with no framework-owned cache.** The CSV-directory
  child returns
  `{"rows_purged": 0, "tables_touched": [], "preserved": [], "reason": "csv_dir reads institutional CSV files at csv_dir.path; the framework owns no derivative cache to purge. Source-file retention is the deployer's responsibility per ADR 0013."}`.
  The template child returns the same shape with author-facing
  guidance. The contract is satisfied by an honest empty purge with
  a citable reason, not by silence.
- **Reversal condition.** This ADR moves toward vault purging if
  the IRB profile codified in
  [docs/design/research-framing.md § Consent withdrawal under
  this profile](../design/research-framing.md#consent-withdrawal-under-this-profile)
  evolves to require it. The current profile reads withdrawal as
  *"cessation of further data collection plus removal of cached
  participant biometric data on the analyst's machine"* — not full
  erasure of derivative analytical artifacts. A study whose IRB
  language reads *"withdrawal removes all derivative records"*
  instead — for instance a clinical-grade or GDPR-strict study —
  would extend the purge contract to the vault tier, supersede
  ADR 0009's append-only invariant for revoked subjects, and
  require a new ADR resolving the conflict between append-only
  analytical memory and full-erasure compliance. The reversal is
  *not* triggered by adding a new biometric child — those are
  handled inside the existing contract.

## Consequences

**Positive.**

- The IRB invariant *consent revocation = no cached participant
  biometric data on disk* is now enforced by code, not by the
  deployer's memory of when caches expire. A reviewer reading
  `audit.db` can confirm cleanup completed on the same row that
  records the revocation request.
- The paired audit rows give a forensic anchor for compliance
  review. A reviewer asking "did revocation actually purge the
  cache?" reads two rows side by side, both stamped with
  `scrubber_id` and `force_revoke`, and gets a deterministic
  answer.
- The fail-closed default closes the silent-revocation failure
  mode: a locked database file or filesystem error cannot result
  in "consent revoked, cache intact" — it results in "revocation
  refused, caller informed, audit row recorded."
- The mandatory-abstract decision pushes the cache-identification
  question into the right place. A new child author cannot ship
  without answering "what tables of this child hold biometric
  data?" — a question that has to be answered correctly anyway for
  the cache to be sound.
- The cache-only scope keeps revocation cheap. A 10-participant
  pilot where one withdraws does not force a cohort-wide vault
  rewrite or break append-only invariants downstream analysts
  depend on.

**Negative.**

- Every new `ChildMCP` implementation adds a method. The cost is
  one method per child (3 currently shipped: running, csv_dir,
  template), and the template's implementation is itself a
  worked example with author guidance. The friction is the point
  — a new child without a purge story is a child whose retention
  posture is unknown.
- The framework's retention guarantee stops at the cache boundary.
  An IRB reviewer reading this ADR may reasonably ask why vault
  notes are not also purged on revocation. The defence is in the
  Reversal condition: the framework refuses to pre-empt a study-
  specific IRB question, but documents the seam at which the
  answer would land.
- `force_revoke=True` exists as an escape hatch and could be
  abused by a deployer who wants the revocation to "succeed"
  regardless of cache state. Mitigated by the audit-row record:
  every `PURGE_CACHE` row carries the `force_revoke` flag, and a
  reviewer can grep for forced revocations across a deployment.
  The escape hatch is loud, not silent.
- **Single-account-per-domain assumption.** The contract takes no
  `subject_id` argument: a child purges its entire cache, not the
  cache slice belonging to one participant. This is correct for the
  running child today — one Strava OAuth token corresponds to one
  participant — but a future child whose data source shares one
  account across multiple participants (e.g. a CGM child wrapping a
  shared Dexcom Clarity account, a wearable group-portal export)
  would, by faithfully copying the running pattern, blow away
  cohort-wide cache when one of N participants withdraws. The
  abstract contract pre-empts the more conservative implementation
  because the signature does not pass `subject_id` through. This
  ADR records the assumption explicitly so the first child author
  who needs subject-scoped purge knows to widen the contract via a
  superseding ADR rather than work around it. The fix path is well-
  defined: extend `purge_cache(*, force, subject_id=None)` and
  thread `subject_id` from the consent-revoke handler when the
  domain's child opts in. Deferred until a multi-participant child
  actually ships — speculative widening adds API surface today
  without buying compliance value.

**Neutral.**

- The audit-row contract is uniform across success and failure.
  Both `PURGE_CACHE` and `PURGE_FAILED` rows carry `scrubber_id`,
  `force_revoke`, and the child's return dict. A reviewer building
  a retention-compliance report runs one query.
- This ADR does not change the consent gate's session-scoped
  semantics ([ADR 0003 § Security pipeline](../../CLAUDE.md#security-pipeline-cheapest-first))
  — consent is still per-domain, in-memory, and revocable. It
  changes only what `revoke()` is paired with on disk.
- ADR 0012's vault PHI-scrubber bypass is unaffected. The vault
  dispatch path does not invoke `purge_cache` and does not need
  to: the vault is out of scope by the cache-only-not-vault-purge
  decision.
- The `_meta` provenance contract on tool results is unchanged.
  `purge_cache` is invoked by the router on the revocation path,
  not as a tool the LLM can call directly, so it does not produce
  an LLM-visible result that would carry `_meta`.

## Alternatives considered

**Default no-op `purge_cache` on `ChildMCP`, with a one-time warning
on first construction (the ADR 0003 PHI-scrubber pattern).**
Rejected. The asymmetry is structural, not stylistic: PHI scrubbing's
policy is genuinely IRB-dependent and the framework cannot define it
honestly, so a default no-op with a warning is the right compromise.
Cache identification is *not* IRB-dependent — the child wrote the
rows and knows which tables hold biometric data. A default no-op
here would let a child author silently inherit the failure mode the
v6.3.0 WATCH named, with the framework's signature on it. The
abstract-method choice pays a one-method-per-child cost in exchange
for closing a governance gap rather than papering over it.

**Asynchronous purge — schedule the cache cleanup on a background
thread and return revocation immediately.** Rejected. The window
between "consent state says revoked" and "cache is empty" is
exactly the window an IRB reviewer would fail the deployment for.
Synchronous purge inside the revocation handler collapses the
window to zero. The cost is that a slow purge holds the request
open; the alternative is a fast lie.

**Framework-owned cache-and-vault purge — revocation also rewrites
or deletes vault notes referencing the subject.** Rejected, with a
named reversal condition. The vault tier ([ADR 0009](0009-vault-subject-keying.md))
holds analyst-authored content whose retention semantics depend on
the study's IRB language. Some IRBs treat analyst notes as
derivative records subject to withdrawal; some treat them as
analytical work product the analyst owns; the framework cannot pick
one default without overcommitting. The Reversal condition above
names the exact circumstance under which this answer changes — a
new ADR superseding ADR 0009's append-only invariant for revoked
subjects — and the conflict that ADR would have to resolve.

**Fail-open by default — purge errors logged but revocation
proceeds, with `strict_revoke=True` as the opt-in for fail-closed.**
Rejected. The default value of a fail-policy flag determines what
the median deployment ships with. Fail-open by default means the
median deployment honours revocation as a state flip the moment a
storage error occurs, which is the failure mode the WATCH named.
Fail-closed by default with a named escape hatch (`force_revoke=True`)
inverts the burden: the deployer who wants the lossy behaviour has
to ask for it explicitly, and every audit row records whether they
did.

**Defer the contract to a future ADR and ship v6.4.0 with cache
TTL as the only retention story.** Rejected. The TTL is a
seven-day cleanup, not a revocation guarantee — a participant who
withdraws on day 1 has cached PHI through day 7 with no audit
signal that the data was supposed to be gone on day 1. The hygiene-
pass WATCH is not closeable by tuning the TTL; it is closeable only
by making revocation produce a paired on-disk effect. Deferring
re-creates the governance gap on a different timeline, which is the
same anti-pattern ADR 0012 rejected for the vault PHI-scrubber
bypass.
