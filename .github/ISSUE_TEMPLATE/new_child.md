---
name: New ChildMCP proposal
about: Propose a new data source (CSV, REDCap, Calendar, Notes, CGM, sleep, ECG, EDF, FHIR, ...)
title: "[child] "
labels: enhancement, new-child
---

<!--
ChildMCPs are the framework's extension point for new data sources.
One child = one data source — a vendor API, a file format, a
productivity-tool export, a clinical bundle, or anything else with
structured records. Before filing, skim CLAUDE.md § "Adding a New
ChildMCP" and ROADMAP.md § "New ChildMCPs" — your proposal may
already be on the roadmap, in which case link to it.
-->

## Data source

<!-- What are you wrapping? Be specific. -->

- Name:
- Kind: (vendor API / file format / productivity-tool export / clinical bundle / other)
- Public dataset or sample export to develop against (if any):
- Upstream docs / spec link:

## Domain

<!--
The `domain` string identifies this child in consent gates, audit
rows, and tool names. Must be lowercase, short, and not collide with
any existing child.
-->

- Proposed `domain` value:
- Proposed `display_name`:

## Consent scope

<!--
Who consents to this analysis — a research participant (IRB-governed
deployment), or the data owner themselves (quantified-self,
personal-knowledge, household / family contexts)? Both are
first-class deployment shapes as of v9.0.0. What exactly does the
consenting entity agree to when they approve this child? This
becomes the ConsentInfo.data_types list shown in the consent prompt.
-->

- Who consents: (research participant / data owner themselves / both supported)
- `data_types`:
- `purpose`:

## Tier mapping

<!--
Most analytical questions should be answerable at Tier 1 (server-
computed reports). Tier 2 is downsampled streams. Tier 3 is per-
timestamp / raw.
-->

- Tier 1 tools (server-side reports, no raw data leaves the machine):
  1.
  2.
  3.
- Tier 2 tools (downsampled streams):
  1.
- Tier 3 tools (raw / per-timestamp):
  1.

## Identifier / PHI considerations

<!--
Will this child's raw payload contain identifying fields? For
health-research deployments this means PHI (names, MRNs, dates
correlated with identifying metadata, etc.). For non-clinical
deployments (productivity tools, personal-knowledge bases, household
contexts) this can still mean identifiers worth scrubbing — email
addresses inside Notion pages, contact names in calendar invites,
home GPS inside fitness exports, etc. If yes, describe the policy
this child's DataScrubber subclass should enforce — or note that a
scrubber is out of scope for this first pass and will be tracked
separately. (See ADR 0003 § Amendment 2026-05-14 on framework-level
vs child-level scrubber seams.)
-->

## Implementation notes

<!-- Rate limits, auth model, cache strategy, storage file name. -->

- Auth: (none / API key / OAuth)
- Rate limit: (requests/min, if any)
- Local storage file: `<domain>.db`
- Template scaffolding: (will this start from `children/template/`, or
  does it need custom bootstrap?)

## Related

<!-- ROADMAP.md row, related issues, prior art. -->
