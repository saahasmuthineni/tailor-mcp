"""
Tests for TemplateProcessing — pure-function analytics.

These are the simplest tests in the template, by design. They
exist to teach contributors two things:

* the child/processing split is real (pure functions belong in
  ``processing.py``, not ``child.py``), and
* pure functions are independently testable with no fixtures.

When you fork the template, replace these with tests for your
own analytics. See ``tests/children/running/test_processing.py``
for a worked example.
"""

from __future__ import annotations

import pytest

from biosensor_mcp.children.template.processing import TemplateProcessing


class TestSummarize:
    def test_basic_stats(self):
        result = TemplateProcessing.summarize([1.0, 2.0, 3.0, 4.0, 5.0])
        assert result == {"count": 5, "mean": 3.0, "min": 1.0, "max": 5.0}

    def test_empty_series(self):
        result = TemplateProcessing.summarize([])
        assert result == {"count": 0, "mean": None, "min": None, "max": None}


class TestDownsample:
    def test_every_second_sample(self):
        assert TemplateProcessing.downsample([1, 2, 3, 4, 5, 6], 2) == [1, 3, 5]

    def test_interval_one_returns_original(self):
        assert TemplateProcessing.downsample([1, 2, 3], 1) == [1, 2, 3]

    def test_invalid_interval_raises(self):
        with pytest.raises(ValueError):
            TemplateProcessing.downsample([1, 2, 3], 0)
