"""
Running Child MCP — Strava Integration (Worked Example)
========================================================
Implements ChildMCP for running data sourced from Strava.

This child is retained as a worked example of the ChildMCP pattern
for research-software engineers wiring up new data sources. It is
deliberately complete: three access tiers, OAuth token management,
stream caching, server-side analytics, downsampling, and a cost
gate on the raw-stream tool.

It is NOT the canonical use case the framework was built for, and
the analytics in ``processing.py`` are not intended to generalize
beyond running. Treat this package as a template to copy rather
than a dependency to import.
"""

from .child import RunningChild

__all__ = ["RunningChild"]
