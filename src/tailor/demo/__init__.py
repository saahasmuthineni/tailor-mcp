"""
Demo mode — researcher first-look against bundled HIP Lab cohort
fixtures.

Per ADR 0027, ``tailor demo`` runs CSV cohort tools against
the bundled ``_fixtures/hip_lab_demo_realistic/force/`` subtree
(16 synthetic subjects + metadata.json sidecar) — the same fixtures
``tailor tour`` scaffolds. No Strava account, OAuth tokens,
or network access required.

The synthetic-Strava generator at ``demo.sample_data`` is preserved
per ADR 0008 § Alternatives and remains importable for the
worked-example notebook and the router smoke test, but is no longer
the demo's data source.
"""

from .runner import run_demo

__all__ = ["run_demo"]
