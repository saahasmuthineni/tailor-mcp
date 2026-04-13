---
name: New ChildMCP proposal
about: Propose a new biosensor data source (CGM, sleep, ECG, CSV, EDF, FHIR, ...)
title: "[child] "
labels: enhancement, new-child
---

<!--
ChildMCPs are the framework's extension point for new data sources.
One child = one data source (a vendor API, a file format, a clinical
bundle). Before filing, skim CLAUDE.md § "Adding a New ChildMCP" and
ROADMAP.md § "New ChildMCPs" — your proposal may already be on the
roadmap, in which case link to it.
-->

## Data source

<!-- What are you wrapping? Be specific. -->

- Name:
- Kind: (vendor API / file format / clinical bundle / other)
- Public dataset to develop against (if any):
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
What exactly does a participant (or analyst acting on their behalf)
consent to when they approve this child? This becomes the
ConsentInfo.data_types list shown in the consent prompt.
-->

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

## PHI considerations

<!--
Will this child's raw payload contain identifying fields (names,
MRNs, timestamps at day-resolution correlated with identifying
metadata, etc.)? If yes, describe the policy this child's PHIScrubber
subclass should enforce — or note that a PHIScrubber is out of scope
for this first pass and will be tracked separately.
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
