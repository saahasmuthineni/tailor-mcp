# ADR 0041: License — Apache-2.0 → AGPL-3.0-or-later, effective v9.0.0

- **Status:** Accepted
- **Date:** 2026-05-26
- **Related:**
  - [ADR 0011 (Promotion policy)](0011-promotion-policy.md) — structural-argument-plus-severity reasoning this ADR's choice-among-copyleft-options inherits
  - [ADR 0024 (Wheel-distributed tour and fixture bundling)](0024-wheel-distributed-tour-and-fixture-bundling.md) — recipient-by-construction distribution shape the license must not friction
  - [ADR 0029 (Token reduction as analytical quality)](0029-token-reduction-as-analytical-quality.md) — the "AI economics" umbrella claim a future "Tailor Cloud" extractive reuse would specifically capitalise on
  - [ADR 0030 (Public-mirror narrative and affordance depth)](0030-public-mirror-narrative-and-affordance-depth.md) — the public-rendering posture this ADR's license question presupposes
  - [ADR 0031 (Project rename to Tailor + Wardrobe)](0031-rename-to-tailor-and-wardrobe.md) — sister project-level commitment landed at a major bump; this ADR adopts the same major-bump shape for the license change
  - [ADR 0032 (Retire the public-mirror distribution path)](0032-retire-public-mirror-distribution.md) — closes the wheel-by-email distribution era; license question becomes load-bearing at the public-flip boundary
  - [`pyproject.toml`](../../pyproject.toml) — SPDX `license = "AGPL-3.0-or-later"` + `license-files = ["LICENSE"]` per PEP 639
  - [`LICENSE`](../../LICENSE) — the GNU AGPL v3 text shipped with v9.0.0

## Context

Tailor shipped under **Apache-2.0** from its first commit through the
end of the v8.x line. That choice was made early, before the project's
identity had stabilised, and was inherited by every subsequent release
without being explicitly re-decided. Apache-2.0 is a permissive
license: anyone may copy, modify, and redistribute the code, including
inside a closed-source product or a hosted service, with no obligation
to share modifications back. It was a reasonable default while the
project was private and the audience was the boss-architect plus a
handful of family-tester-by-construction recipients (per project
memory; the v6.11.x recipient-install-validator falsification ground
the install-population at empirically zero until 2026-05-12).

Two structural pressures forced the question on the public-flip
boundary:

1. **The public-flip is approaching.** v9.0.0 is shaped as
   public-flip-prep: identifier renames making the externally-visible
   vocabulary match the architectural commitment (subject_id →
   entity_id; PHIScrubber → DataScrubber; csv_cohort_summary →
   csv_group_summary), a benchmark artifact backing
   [ADR 0029](0029-token-reduction-as-analytical-quality.md)'s "AI
   economics" claim with reproducible numbers, and a README hero
   repositioned for problem-first framing. The three-condition trigger
   for the actual repo public-flip is named in the v7.0.13 banner
   (beachhead lab + launch-narrative artifacts + boss-decides-public-
   scrutiny). When that trigger fires, the license becomes a
   load-bearing decision about *what other parties may do with this
   project's work*. A license question that was acceptable as a
   placeholder under private-repo conditions stops being acceptable
   the moment the repo is visible to strangers and indexable by web
   search.

2. **The "AI economics" claim materially raises extraction risk.** The
   benchmark artifact shipping in v9.0.0 measures **657.6×–938.2× per-
   query token efficiency** and **318× session persistence efficiency**
   (`benchmarks/token_efficiency.md`). The numbers are reproducible
   under named scenarios with explicit assumptions and a quantitative
   prompt-caching counter-factual. Those numbers translate directly to
   dollar-cost reduction at hosted-LLM API pricing. A cloud provider
   reading those numbers has a sharper-than-usual incentive to fork
   Tailor, rebrand it as "Tailor Cloud" or equivalent, and offer it as
   a managed service capturing the cost-saving as margin — without
   contributing any modifications back. Under Apache-2.0 they are
   permitted to do exactly that, and the project's local-first /
   audit-trail / IRB-grade-reproducibility commitments would be
   trivially replaceable in any forked deployment by whatever the
   forking party decided to ship instead.

The local-first deployment recipe (the framework's primary use case
per `CLAUDE.md` § "What This Project Is") is structurally indifferent
to permissive vs copyleft licensing under normal use: a PI installing
Tailor on a lab workstation, an RSE supporting a study, an academic
medical center running it against participant biometric data — none
of these parties expose Tailor to the public over a network in a way
that would trigger the AGPL § 13 network-interaction clause. The
license-choice question is therefore not *"what does this license
require of the framework's actual users?"* but *"what does this
license require of the parties who would convert the framework's work
into extractive cloud margin without contributing back?"*

## Decision

Switch the license to **GNU Affero General Public License version 3
or any later version** (SPDX identifier: `AGPL-3.0-or-later`), effective
v9.0.0. Forward-only: tagged releases through v8.0.0 remain
Apache-2.0 in perpetuity for any recipient who already received them;
v9.0.0 onward is AGPL-3.0-or-later.

`pyproject.toml` declares the new license via PEP 639 SPDX syntax
(`license = "AGPL-3.0-or-later"` + `license-files = ["LICENSE"]`). The
`LICENSE` file at the repo root is the GNU AGPL v3 verbatim text. The
prior `License :: OSI Approved :: Apache Software License` classifier
is retired (PEP 639 replaces classifier-based licensing); no
`License :: OSI Approved :: GNU Affero General Public License v3`
classifier is added under PEP 639, which prefers the SPDX field.

The README license section is expanded from the prior single line
(`Apache-2.0.`) to a ~35-line plain-English summary covering what the
license requires, what it protects, and the network-trigger clause's
practical scope for local-first deployments.

### Why AGPL specifically — the network-trigger as the load-bearing clause

GPL family licenses are copyleft: a party who distributes modified
versions of the code must publish their modifications under the same
license. This handles the *distribution* case (a fork compiled into a
binary and given to users) but has a gap on the *hosted service* case
(a fork run as a backend behind a network API, never distributed to
end-users in binary form). The hosted-service gap is the structural
lever a cloud provider would use to wrap Tailor's work into proprietary
margin: GPLv3 alone would let them do it without sharing modifications,
because users of the service never receive a copy of the modified
binary.

AGPL § 13 closes that gap. Quoted in plain language: *"if you modify
the program and run that modified version on a server that users
interact with over a network, you must make the corresponding source
code of that modified version available to those users under the same
AGPL terms."* A future "Tailor Cloud" provider must publish their
modifications under AGPL — which means individuals, institutions, and
the project itself can fold those modifications back into the
community-maintained codebase. The provider can still run a hosted
service; what they cannot do is keep their improvements private.

The network-trigger clause is asymmetric in exactly the way the
project needs:

- **Local-first deployments** (the framework's primary use case): a PI
  on a lab workstation, an RSE in a study, an academic medical center,
  a household installing for personal use. None of these expose Tailor
  to public-internet users over a network; § 13 does not fire; AGPL
  imposes essentially zero additional friction over Apache-2.0 for
  these users. They modify the code locally as they always could; they
  do not redistribute their internal modifications because internal
  modifications are not being given to anyone outside the institution.
- **Hosted-service repackaging** (the failure mode this ADR defends
  against): a cloud provider runs Tailor (modified) as a backend that
  end-users interact with over the public internet. § 13 fires; the
  provider must publish their modifications. The project gets the
  improvements back, or the provider doesn't make modifications worth
  hiding.

The asymmetry is what makes AGPL the right structural tool here.
Permissive licensing (MIT, Apache-2.0) treats both deployment shapes
identically and lets the hosted-service shape extract without
contributing. Symmetric copyleft (GPLv3 without § 13) closes the
distribution side but leaves the hosted-service side open. Source-
available non-OSI licenses (BSL, Elastic, SSPL) close both but at a
cost in researcher and institutional friction the project is not
willing to pay (see § Alternatives 4–5).

### Choosing the *-or-later* shape, not version-locked

The SPDX identifier is `AGPL-3.0-or-later`, not `AGPL-3.0-only`.
Quoted from the license: *"or, at your option, any later version
published by the Free Software Foundation."* This is the load-bearing
choice that affects how the project survives long-form license
evolution.

If the FSF publishes AGPL v4 (or a successor numbered differently) at
any future point — to close a new extraction loophole, address an
emerging deployment shape, or clarify a clause whose practical scope
has shifted — recipients of Tailor under `AGPL-3.0-or-later` may
choose to apply the v4 terms. This is the same shape the Linux
kernel, GCC, and most other long-form copyleft projects rely on: a
single explicit license update is not required when the FSF revises
the license, because the *-or-later* clause already authorised the
upgrade at the original distribution moment.

`AGPL-3.0-only` (version-locked) would require an explicit license
update in this repo every time the FSF revised the license, with the
attendant ADR ritual and recipient-side migration friction. The
upgrade-on-choice shape preferred by *-or-later* respects the project's
limited maintainer bandwidth without giving up project control: the
recipient chooses whether to apply the new version; the project is
not obligated to.

## Consequences

### Positive

- **The "Tailor Cloud" extraction failure mode is closed structurally.**
  A future cloud provider must publish their modifications under AGPL.
  The project gets improvements back, or the provider doesn't make
  improvements worth hiding. This is the single load-bearing reason
  for the license switch; the other consequences are second-order.
- **The license aligns with the project's actual community shape.**
  Tailor is built for researchers, RSEs, and institutional users who
  benefit from a thriving local-first commons; AGPL is the standard
  license for projects that want extraction to flow back to the
  commons rather than into proprietary margin. The signal a license
  sends to the community is part of what the license does; AGPL
  signals *"contributions and modifications belong in the commons"*
  the way Apache-2.0 signals *"do what you want, no obligations."*
- **For the primary use case (local-first), the change is
  behaviourally invisible.** A PI installing Tailor, an RSE supporting
  a study, an academic medical center running it on internal
  infrastructure — none of these parties experience any practical
  difference. AGPL § 13 only fires when modified versions are exposed
  to network users; internal use, derivative works used only by the
  institution that produced them, and personal use are all unchanged
  by the switch.
- **The benchmark artifact and the license reinforce each other.** The
  v9.0.0 benchmark (`benchmarks/token_efficiency.md`) measures and
  publishes the cost-reduction claim that would otherwise make Tailor
  an attractive extraction target. The AGPL is the structural response
  that closes the extraction path the benchmark advertises. Shipping
  the two together makes the project's posture coherent: *"here is
  how much money this saves; here is why you cannot take that saving
  and resell it as your closed-source product."*
- **Forward-only adoption preserves recipient trust.** Tagged releases
  through v8.0.0 remain Apache-2.0 for any recipient who already
  received them; no relicensing of prior versions, no retroactive
  obligations on prior recipients. The promise made to a v8.0.0
  recipient (*"you received this under Apache-2.0; the terms of that
  receipt do not change"*) is honored in perpetuity.

### Negative

- **Wider adoption surface is narrower than under Apache-2.0.** Some
  institutional users are unwilling to deploy AGPL-licensed software
  because of legal-team uncertainty about the § 13 scope, even when
  the deployment shape would not actually trigger § 13. This is a real
  cost, paid at the institution-adoption boundary. The mitigation is
  the README license section's plain-English summary of what AGPL
  actually requires in a local-first deployment (essentially nothing),
  which a legal team can read in five minutes rather than reading the
  raw 26-page AGPL text.
- **The hosted-service-by-third-party path is structurally closed at
  the proprietary-margin level.** A cloud provider who wanted to offer
  "Tailor Cloud" can still do it — but they must publish their
  modifications under AGPL. Some providers will pass on this on legal
  / competitive grounds rather than contribute back. This is the
  intended consequence, named here so future contributors do not
  misread it as collateral damage: closing the proprietary-margin
  cloud path is the point of the license switch, not a side effect.
- **License compatibility with permissively-licensed downstream
  consumers narrows.** A downstream Apache-2.0 or MIT project cannot
  link Tailor's code into its own codebase without itself adopting
  AGPL terms for the combined work. For local-first individual
  installations of Tailor this never arises (Tailor is the application,
  not a library being linked into something else). For an institutional
  deployment that wanted to import Tailor as a library into a larger
  Apache-2.0 internal codebase, the institution must either
  (a) treat the larger codebase as AGPL-licensed when distributed or
  served, or (b) interact with Tailor across a process boundary (e.g.
  subprocess + JSON-RPC, which is in fact Tailor's primary integration
  pattern via MCP) where the licensing question is shaped by how the
  two programs communicate rather than how they link.
- **A future relicensing of the project itself requires either
  agreement from every contributor or a clean-room rewrite.** AGPL is
  inherited by contribution under the inbound-equals-outbound
  convention (every contributor's PR is implicitly accepted under the
  license the project ships under at the time of contribution). To
  relicense Tailor away from AGPL in the future, the project would
  need either an explicit Contributor License Agreement (CLA) signed
  by every past contributor authorising the relicensing, or a
  rewrite of every contributor's work by a contributor authorised to
  ship the new license. This is a real cost paid by accepting AGPL;
  Apache-2.0 has the same property in the same direction (Apache-2.0
  → permissive-public-domain is impossible without similar consent).
  The cost is named here so a future contributor who proposes a
  relicensing is grounded in what the proposal actually requires.

### Neutral

- **The license switch does not change what Tailor does, what it
  ships, or how it works.** The router, ChildMCP plurality, vault,
  audit log, consent / cost / circuit-breaker gates, local-LLM
  guardian, deterministic processing, MCP transport — all unchanged
  by the license. The license names the legal contract between the
  project and its recipients; it does not name the technical
  behaviour the project performs.
- **The license switch does not affect the audit-log backbone or any
  IRB-facing claim.** The audit log lives at `audit.db` and is
  produced by code Tailor runs locally on the operator's machine; the
  legal status of that code's source distribution is orthogonal to
  the integrity of the rows the code writes. An IRB reviewer reading
  the audit log under v9.0.0 sees exactly what they would have seen
  under v8.0.0, with the same provenance guarantees.
- **The license switch does not affect the existing PyPI listing
  beyond the metadata fields.** `tailor-mcp` at version 9.0.0 ships
  with the new license in `pyproject.toml`; prior versions on PyPI
  (7.x and 8.x) remain available under their original Apache-2.0
  license. PyPI does not retroactively relicense prior releases when
  a project changes its license metadata — the change applies only to
  new uploads.
- **Compatibility with MCP itself is unchanged.** Tailor is an MCP
  server, not a fork or derivative of the MCP protocol or SDK. The
  MCP SDK (`mcp` on PyPI) is MIT-licensed. Tailor imports it as a
  dependency; this is not a derivative-work relationship under any
  reasonable reading of either license. The choice of license for
  Tailor does not propagate to the MCP SDK and is not constrained by
  the MCP SDK's license.

## Alternatives considered

### Alternative 1: Stay on Apache-2.0

The status-quo option. Keep the permissive license that shipped with
the project from day one. The cost of changing licenses is zero;
existing institutional users who already cleared Apache-2.0 with
their legal teams don't have to clear AGPL.

**Rejected because**: under Apache-2.0 the "Tailor Cloud" extractive
fork is fully permitted with no obligation to contribute back. The
benchmark artifact shipping in v9.0.0 publishes the cost-reduction
claim that makes the extraction attractive. Closing the extraction
path is the load-bearing reason for the license switch; staying on
Apache-2.0 is a decision to leave that path open. The cost-of-change
this alternative would avoid is small (a major-bump banner entry, an
ADR, a LICENSE swap, a few doc edits); the cost-of-not-changing it
would lock in is large (the proprietary-margin extraction path is
permanently open to any future cloud provider).

### Alternative 2: Switch to MIT

The most permissive of the well-known OSI-approved licenses. Slightly
shorter and easier to read than Apache-2.0; otherwise equivalent in
permissions.

**Rejected because**: this is a strict regression on the
extraction-prevention dimension. MIT, like Apache-2.0, permits closed-
source forks and hosted-service repackaging with no contribution-back
obligation. The reasons Apache-2.0 was rejected (Alternative 1) apply
identically to MIT, with the additional cost that MIT loses
Apache-2.0's explicit patent grant. There is no scenario in which MIT
is preferable to Apache-2.0 for this project, and Apache-2.0 is
already rejected above.

### Alternative 3: GPLv3 (without § 13)

Symmetric copyleft. Closes the distribution side: a forked binary
distributed to users must publish source under GPL. Does not close
the hosted-service side: a forked Tailor run as a network backend
without binary distribution to end-users does not require source
publication.

**Rejected because**: the hosted-service shape is exactly the
extraction path this ADR defends against. GPLv3 closes the
less-likely path (binary distribution of a forked Tailor) while
leaving the more-likely path (cloud-hosted "Tailor Cloud") open. The
benchmark artifact published in v9.0.0 specifically targets cloud-cost
optimisation; the proprietary-margin scenario is overwhelmingly more
likely to take the cloud-hosted shape than the binary-distribution
shape. AGPL closes both; GPLv3 closes only one; the cost difference
between GPLv3 and AGPL is essentially zero for local-first users
(neither fires § 13 in normal use); the benefit difference is
meaningful. AGPL dominates GPLv3 for this project's structural
position.

### Alternative 4: Business Source License (BSL)

A source-available license used by HashiCorp (since 2023), MariaDB,
CockroachDB, Sentry, and others. Code is published openly; specific
production uses (typically "managed service offering of the licensed
work" for a fixed period) are prohibited; the license converts to a
permissive OSI license (Apache-2.0 or MPL-2.0) after a "change date"
(typically 3–4 years). BSL is explicitly designed to defend against
the hosted-service extraction shape.

**Rejected because**: BSL is not an OSI-approved license, which has
two structural consequences this project cannot accept. First, many
academic institutions, research labs, and IRB-governed deployments
have policies that restrict software adoption to OSI-approved
licenses; adopting BSL would close adoption paths for exactly the
researchers and institutions the project's first deployment recipe
targets. Second, BSL's "you may not offer this as a managed service"
restriction is structurally fuzzy on edge cases that matter for
research: a hospital running Tailor on infrastructure shared across
multiple research groups, a university IT department running Tailor
on a shared lab server, an academic core facility offering Tailor-
backed analysis as a service to PIs in the same institution. AGPL's
§ 13 trigger handles all of these cleanly (internal-to-institution
use does not trigger § 13; only public-network exposure does). BSL's
"managed service" restriction requires case-by-case interpretation
that researcher institutions cannot consistently make in advance.
AGPL has the same defensive effect against the extractive-cloud-
provider shape (which is the actual concern) without the OSI-non-
approval and institutional-edge-case costs.

### Alternative 5: Server Side Public License (SSPL) or Elastic License v2

Other source-available licenses adopted by MongoDB (SSPL) and
Elasticsearch (Elastic License v2). SSPL extends GPLv3-shape copyleft
to the entire stack a hosted service runs (the OS, load balancers,
monitoring infrastructure — anything needed to make the service
available). Elastic License v2 restricts hosted-service offerings and
removal of license/attribution notices.

**Rejected because**: neither is OSI-approved (the same institutional-
adoption barrier as BSL applies). SSPL's scope is generally
considered overreach by the OSI and the broader free-software
community — it has been formally rejected by OSI review — and would
flag Tailor as a project whose license is widely regarded as user-
hostile despite its open-source-adjacent posture. Elastic License v2
has narrower scope but the same OSI-non-approval problem. Both
licenses' actual extractive-cloud defenses are no stronger than
AGPL's § 13 for the cloud-provider scenario, but their adoption-side
costs are higher. AGPL again dominates on the cost/benefit shape.

### Alternative 6: AGPL-3.0-only (version-locked)

Same license, version-locked to v3 specifically. Forbids recipients
from applying any future AGPL version (v4 if it is ever published) to
the same codebase without an explicit project-side license update.

**Rejected because**: the project does not have the maintainer
bandwidth to commit to issuing an explicit license update every time
the FSF revises the AGPL. Version-locking would force exactly that
commitment: a future AGPL v4 closing a new extraction loophole would
not protect Tailor under AGPL-3.0-only until the project explicitly
shipped a license update (with the attendant ADR ritual, recipient-
side migration, and forward-only / backward-compatibility handling).
*-or-later* puts the version-upgrade choice in the recipient's hands
where it can be made when needed without the project being on the
critical path. The downside of *-or-later* (a hypothetical future
AGPL v4 introduces terms the project would not have agreed to in
advance) is governed by the recipient's choice not to apply v4, not
by the project being permanently bound to v4. This is the standard
shape long-form copyleft projects (Linux kernel, GCC, GNU coreutils)
have settled on, for the same reasons.

### Alternative 7: Dual-license (AGPL for community + commercial license for cloud providers)

Common pattern for projects that want extractive-cloud defenses
without losing the option to monetise via commercial licensing.
Project ships under AGPL for the general community; cloud providers
who want to offer a hosted service can buy a commercial license that
exempts them from § 13. Examples: MongoDB historically, MySQL under
Oracle, Qt.

**Rejected because**: the dual-license pattern requires either a CLA
(every contributor signs over the right for the project owner to
relicense their contributions under a different license) or
single-author authorship in perpetuity. Tailor has had a single author
to date, but the project's stated future shape includes contributions
from the broader community once the public-flip lands. Adopting dual-
licensing would either commit the project to a CLA — which is a
significant ergonomic and political cost on contributors — or
constrain it to permanent single-author authorship, which is at
direct cross-purposes with the open-source-collaborator-attracting
function the public-flip is partly meant to serve. The defensive
posture this ADR adopts (AGPL alone, no commercial-license track) is
sufficient for the project's stated concerns; the dual-license
machinery exists to enable commercial-license revenue, which is not a
goal this project has named.

### Alternative 8: Defer the license question to the public-flip moment

Ship v9.0.0 still under Apache-2.0; revisit the license question
when the three-condition trigger for the actual public-flip (per the
v7.0.13 banner: beachhead lab + launch-narrative artifacts + boss-
decides-public-scrutiny) fires.

**Rejected because**: v9.0.0 ships the benchmark artifact that
materially raises extraction risk and the README hero repositioned for
problem-first framing aimed at a broader audience. The conditions
under which the license question is load-bearing are already present
in v9.0.0; deferring the answer to a later release would leave a
window in which the project's most public-facing framing is
permissively-licensed and therefore extractable. The reasonable
shipping order is to ship the framing and the license together,
because they protect each other (the license closes the extraction
path the framing advertises). Adopting the license at v9.0.0 also
respects the major-bump shape codified by
[ADR 0031](0031-rename-to-tailor-and-wardrobe.md) for project-level
commitments: the rename and the license switch are both project-
identity changes that warrant a major version, and bundling them
preserves the precedent that breaking-shape changes land in major
releases.

## Backward compatibility with prior Apache-2.0 versions

Forward-only adoption. Tagged releases through v8.0.0 remain
Apache-2.0 in perpetuity; v9.0.0 onward is AGPL-3.0-or-later. No
relicensing of prior versions, no retroactive obligations on prior
recipients. The structural commitments:

1. **PyPI history is not rewritten.** `tailor-mcp` versions through
   8.x remain on PyPI under their original Apache-2.0 metadata. A
   recipient who installed v8.0.0 last week continues to hold it
   under Apache-2.0; a recipient who installs v8.0.0 next year
   continues to hold *that* under Apache-2.0. PyPI does not propagate
   the v9.0.0 license metadata backward to prior releases.
2. **Git history is not rewritten.** Commits through the v8.0.0 tag
   were made under Apache-2.0 and remain under Apache-2.0 in the git
   log. A reviewer reading the v8.0.0-tagged source tree on GitHub
   (or in a cloned repo at the v8.0.0 commit) sees Apache-2.0 in
   `pyproject.toml` and `LICENSE` as those files existed at that
   moment.
3. **The change-of-license is named in a single commit on the
   `feature/v9-public-flip-prep` branch.** The LICENSE file swap, the
   `pyproject.toml` SPDX field change, the README license-section
   expansion, and this ADR all land in commits identified by their
   commit messages as part of the v9.0.0 public-flip-prep work. A
   future contributor or reviewer auditing the license history can
   identify the exact commit where the project's license shifted, and
   the prior history is unambiguously Apache-2.0.
4. **Recipients who upgrade across the boundary upgrade explicitly.**
   A v8.0.0 user who runs `uv tool install --upgrade tailor-mcp` and
   receives v9.0.0 receives the new version under AGPL-3.0-or-later
   from that install moment forward. The license terms attached to
   the v8.0.0 install they previously held are unchanged; the
   upgraded install is governed by the v9.0.0 license. This is the
   standard semantics across both Apache-2.0 and AGPL: each
   distributed copy carries the license under which it was
   distributed.
5. **No contributor-side relicensing is required.** Every commit
   merged through v8.0.0 was contributed under Apache-2.0's inbound-
   equals-outbound convention. Apache-2.0 is compatible with AGPLv3
   in the project-relicense-going-forward direction (Apache-2.0 ⇒
   AGPL is permitted because Apache-2.0's permissive terms allow the
   licensee — including the project itself — to relicense modified
   versions under more restrictive terms when doing so does not
   violate any Apache-2.0 obligation). The license-switch operation
   is therefore not blocked by any prior contributor's lack of
   explicit consent; future contributions (post-v9.0.0) come in
   under AGPL.

## Reversal conditions

This ADR can be revisited (or superseded) under any of the following
conditions:

1. **An academic-institution adoption barrier proves load-bearing in
   practice.** If a credible beachhead lab or institutional adopter
   reports that their legal team blocks AGPL adoption for the
   project's stated use case (a local-first install on lab
   infrastructure), and the README license section's plain-English
   summary cannot resolve the block, the license is revisited. The
   most likely fallback is a dual-license shape (AGPL for community
   + a no-cost academic-institutional license that explicitly grants
   AGPL-equivalent rights without requiring AGPL adoption by the
   institution's downstream-derived works). This reversal is shaped
   such that it preserves the extractive-cloud defense while opening
   the institution-adoption path; it would not be a return to
   Apache-2.0.
2. **A "Tailor Cloud" or equivalent extractive fork demonstrates that
   AGPL's § 13 trigger is not enforceable against the deployment
   shape that materialises.** If a cloud provider successfully argues
   in court that § 13 does not apply to their particular hosted-
   service configuration of Tailor (e.g., by exposing only a thin
   proxy API rather than direct Tailor interaction), the license is
   revisited with the specific evasion path informing the
   replacement. Most likely candidates: SSPL or BSL with the
   institutional-adoption costs accepted as the price of closing the
   newly-discovered loophole.
3. **The benchmark artifact's "AI economics" claim retires.** If a
   future architectural shift (frontier-model context-window
   expansion to the point that raw-stream-to-LLM is structurally
   competitive with Tailor's tier-1 surface, or a pricing model
   shift that closes the cost-per-question gap) retires the
   extractive-cloud incentive structurally, the license question
   loses its load-bearing motivation. The license could revert to a
   permissive option in that scenario without harm. This reversal is
   symmetric with [ADR 0029 § Amendment 2026-05-12](0029-token-
   reduction-as-analytical-quality.md)'s own reversal condition (two
   independent published benchmarks showing frontier-model parity at
   sub-10k-token loads).
4. **The project's stated goals shift to commercial licensing
   revenue.** A future project decision to adopt a commercial-
   license-track business model (dual-licensing AGPL + commercial)
   requires CLA infrastructure (see Alternative 7) that is incompatible
   with the current zero-CLA contribution shape. Adopting that shape
   is a project-identity decision warranting its own ADR and superseding
   this one.

The reversal conditions are deliberately *not* "the license feels
imperfect" or "a recipient prefers Apache-2.0." The license is the
structural answer to the extraction question; reversing it requires
either the extraction risk to have retired structurally (condition 3)
or a load-bearing adoption / enforcement / business-shape constraint
to materialise (conditions 1, 2, 4). Once chosen and shipped at
v9.0.0, the project's license posture stabilises around AGPL-3.0-or-
later; reversing it again carries a cost (a second major-bump license
change, a second ADR, recipient communication) that is only worth
paying for one of the structural conditions above.
