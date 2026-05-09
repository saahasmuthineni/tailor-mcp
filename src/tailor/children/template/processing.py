"""
Template Processing — Stateless Analytics Stubs
================================================
Pure-function analytics helpers for the template child.

The child/processing split is a deliberate architectural pattern:
``child.py`` owns I/O, caching, and dispatch; ``processing.py``
owns transformations that are *only* a function of their inputs.
This makes the analytics independently testable with no fixtures,
no temp dirs, no mocks — see ``tests/children/template/
test_template_processing.py`` for the shape of those tests.

For a worked example with real analytics (HR zones, drift, GAP,
decoupling, efficiency factor), see
``src/tailor/children/running/processing.py``.
"""

from __future__ import annotations

from statistics import fmean


class TemplateProcessing:
    """
    Stateless analytics for the template domain.

    Each method is a ``@staticmethod`` so tests can call them
    without constructing a ``TemplateProcessing`` instance. Keep
    them that way in your own child unless you genuinely need
    instance state (running-child doesn't).
    """

    @staticmethod
    def summarize(values: list[float]) -> dict:
        """
        Compute a trivial summary over a series of numeric values.

        Returned shape is the kind of thing a Tier-1 server-computed
        report hands back to the LLM: a handful of scalars, ~50
        tokens, no raw data leaked. Replace this with the summary
        statistics that actually matter for your domain (time-in-
        range, efficiency, drift, anomaly count, etc.).
        """
        if not values:
            return {"count": 0, "mean": None, "min": None, "max": None}
        return {
            "count": len(values),
            "mean": round(fmean(values), 3),
            "min": min(values),
            "max": max(values),
        }

    @staticmethod
    def downsample(series: list[float], interval: int) -> list[float]:
        """
        Return every Nth element of ``series``.

        Tier-2 analytics in a real child are usually richer than
        this — anti-aliasing, averaging within the interval,
        handling irregular timestamps — but a decimation stub is
        enough to illustrate the pattern.
        """
        if interval < 1:
            raise ValueError("interval must be >= 1")
        return series[::interval]
