"""
Biosensor Child MCPs
====================
Children are the framework's extension point for new data sources.
Each child wraps exactly one origin of biometric data — a CSV
directory, an EDF file, a FHIR bundle, a REDCap export, a vendor
cloud API — and exposes it to the router as a uniform set of tiered
tools. The router owns validation, consent, cost gating, PHI
scrubbing, and audit identically for every registered child.

The running child (Strava) is one worked example of the pattern.
It is deliberately complete — OAuth, cached streams, tiered
analytics, downsampling, a cost gate at Tier 3 — so that someone
adding a new child for their own study has a concrete template to
copy from. It is NOT the canonical use case the framework was built
for.

Future children sketched in the roadmap include CGM traces
(OhioT1DM, Jaeb), sleep staging (PhysioNet Sleep-EDF), ECG
(MIT-BIH), a generic CSV directory child, an EDF file child, and a
FHIR bundle child. See docs/roadmap.md.
"""
