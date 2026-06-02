"""
Walkthrough mode — researcher first-look against bundled demo
cohort fixtures.

Per ADRs 0027 and 0035, ``tailor walkthrough`` (renamed from
``tailor demo`` in v7.1.0) runs CSV cohort tools against the
bundled ``_fixtures/cohort_demo_realistic/force/`` subtree (16
synthetic subjects + metadata.json sidecar) — the same fixtures
``tailor fitting-room`` (renamed from ``tailor tour``) scaffolds.
No Strava account, OAuth tokens, or network access required.

The Python package directory name (``tailor.demo``) is unchanged at
v7.1.0; internal package structure is not recipient-facing and the
rename is deferred as known-debt per ADR 0035 § Decision item 7.

The synthetic-Strava generator at ``demo.sample_data`` is preserved
per ADR 0008 § Alternatives and remains importable for the
worked-example notebook and the router smoke test, but is no longer
the walkthrough's data source.
"""

from .runner import run_demo

__all__ = ["run_demo"]
