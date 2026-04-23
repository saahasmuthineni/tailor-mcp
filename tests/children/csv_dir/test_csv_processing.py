"""
Pure-function tests for CSVProcessing — no fixtures, no I/O.

Mirrors ``tests/children/template/test_template_processing.py``.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from biosensor_mcp.children.csv_dir.processing import CSVProcessing

# ═══════════════════════════════════════════════════════════════
# summarize_column
# ═══════════════════════════════════════════════════════════════


class TestSummarizeColumn:
    def test_basic_stats(self):
        result = CSVProcessing.summarize_column([1.0, 2.0, 3.0, 4.0, 5.0])
        assert result["count"] == 5
        assert result["mean"] == 3.0
        assert result["min"] == 1.0
        assert result["max"] == 5.0
        assert result["std"] > 0

    def test_empty_list_returns_nulls(self):
        result = CSVProcessing.summarize_column([])
        assert result == {"count": 0, "mean": None, "min": None, "max": None, "std": None}

    def test_single_element(self):
        result = CSVProcessing.summarize_column([42.0])
        assert result["count"] == 1
        assert result["mean"] == 42.0
        assert result["min"] == 42.0
        assert result["max"] == 42.0
        assert result["std"] == 0.0


# ═══════════════════════════════════════════════════════════════
# downsample_rows
# ═══════════════════════════════════════════════════════════════


class TestDownsampleRows:
    def test_every_2nd_row(self):
        rows = [{"a": i} for i in range(10)]
        result = CSVProcessing.downsample_rows(rows, 2)
        assert len(result) == 5
        assert result[0]["a"] == 0
        assert result[1]["a"] == 2

    def test_interval_1_returns_original(self):
        rows = [{"a": i} for i in range(5)]
        result = CSVProcessing.downsample_rows(rows, 1)
        assert result == rows

    def test_interval_less_than_1_raises(self):
        with pytest.raises(ValueError, match="interval must be >= 1"):
            CSVProcessing.downsample_rows([], 0)

    def test_empty_list(self):
        result = CSVProcessing.downsample_rows([], 5)
        assert result == []


# ═══════════════════════════════════════════════════════════════
# detect_timestamp_column
# ═══════════════════════════════════════════════════════════════


class TestDetectTimestampColumn:
    def test_finds_timestamp(self):
        assert CSVProcessing.detect_timestamp_column(["id", "timestamp", "value"]) == "timestamp"

    def test_finds_time(self):
        assert CSVProcessing.detect_timestamp_column(["id", "time", "value"]) == "time"

    def test_finds_datetime(self):
        assert CSVProcessing.detect_timestamp_column(["datetime", "val"]) == "datetime"

    def test_case_insensitive(self):
        assert CSVProcessing.detect_timestamp_column(["ID", "Timestamp", "Value"]) == "Timestamp"

    def test_finds_ts(self):
        assert CSVProcessing.detect_timestamp_column(["id", "ts", "value"]) == "ts"

    def test_finds_event_time(self):
        assert CSVProcessing.detect_timestamp_column(["id", "event_time", "value"]) == "event_time"

    def test_finds_reading_time(self):
        assert CSVProcessing.detect_timestamp_column(["reading_time", "val"]) == "reading_time"

    def test_finds_substring_match(self):
        assert CSVProcessing.detect_timestamp_column(["id", "sample_timestamp", "val"]) == "sample_timestamp"

    def test_returns_none_when_no_match(self):
        assert CSVProcessing.detect_timestamp_column(["id", "value", "measurement"]) is None


# ═══════════════════════════════════════════════════════════════
# parse_timestamp
# ═══════════════════════════════════════════════════════════════


class TestParseTimestamp:
    def test_iso_8601(self):
        result = CSVProcessing.parse_timestamp("2026-01-15T10:30:00")
        assert isinstance(result, datetime)
        assert result.year == 2026
        assert result.hour == 10

    def test_iso_8601_with_timezone(self):
        result = CSVProcessing.parse_timestamp("2026-01-15T10:30:00+00:00")
        assert isinstance(result, datetime)

    def test_custom_format(self):
        result = CSVProcessing.parse_timestamp(
            "01/15/2026 10:30", fmt="%m/%d/%Y %H:%M",
        )
        assert isinstance(result, datetime)
        assert result.month == 1
        assert result.day == 15

    def test_invalid_returns_none(self):
        assert CSVProcessing.parse_timestamp("not-a-date") is None

    def test_empty_string_returns_none(self):
        assert CSVProcessing.parse_timestamp("") is None


# ═══════════════════════════════════════════════════════════════
# estimate_row_tokens
# ═══════════════════════════════════════════════════════════════


class TestEstimateRowTokens:
    def test_known_values(self):
        assert CSVProcessing.estimate_row_tokens(100, 5) == 1000

    def test_zero_rows(self):
        assert CSVProcessing.estimate_row_tokens(0, 10) == 0

    def test_zero_cols(self):
        assert CSVProcessing.estimate_row_tokens(100, 0) == 0


# ═══════════════════════════════════════════════════════════════
# reduce_precision
# ═══════════════════════════════════════════════════════════════


class TestReducePrecision:
    def test_rounds_to_2_decimals(self):
        assert CSVProcessing.reduce_precision(3.14159) == 3.14

    def test_rounds_to_custom_decimals(self):
        assert CSVProcessing.reduce_precision(3.14159, decimals=3) == 3.142

    def test_integer_input(self):
        assert CSVProcessing.reduce_precision(42.0) == 42.0
