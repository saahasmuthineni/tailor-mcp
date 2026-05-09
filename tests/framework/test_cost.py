"""
Tests for ``framework.cost`` — cost gating and token accounting.

CostGate (pre-execution gate), TokenLedger (per-session
accumulator), ``estimate_tokens`` (the rough char-count fallback).
"""

from tailor.framework.cost import CostGate, TokenLedger, estimate_tokens


class TestCostGate:
    def test_below_threshold(self):
        gate = CostGate(threshold=35_000)
        assert gate.should_gate(20_000) is False

    def test_at_threshold(self):
        gate = CostGate(threshold=35_000)
        assert gate.should_gate(35_000) is True

    def test_above_threshold(self):
        gate = CostGate(threshold=35_000)
        assert gate.should_gate(50_000) is True

    def test_custom_threshold(self):
        gate = CostGate(threshold=10_000)
        assert gate.should_gate(10_000) is True
        assert gate.should_gate(9_999) is False


class TestTokenLedger:
    def test_tracks_totals(self):
        ledger = TokenLedger()
        ledger.add("running", "strava_run_report", 800)
        ledger.add("running", "strava_hr_analysis", 400)
        assert ledger.total == 1200

    def test_tracks_by_domain(self):
        ledger = TokenLedger()
        ledger.add("running", "report", 800)
        ledger.add("cgm", "glucose_report", 500)
        by_domain = ledger.by_domain()
        assert by_domain["running"] == 800
        assert by_domain["cgm"] == 500

    def test_summary(self):
        ledger = TokenLedger()
        ledger.add("running", "report", 800)
        s = ledger.summary()
        assert s["session_total_tokens"] == 800
        assert s["call_count"] == 1


class TestTokenEstimation:
    def test_estimates_from_dict(self):
        data = {"key": "value", "number": 42}
        tokens = estimate_tokens(data)
        assert tokens > 0

    def test_larger_data_more_tokens(self):
        small = {"a": 1}
        large = {"data": list(range(1000))}
        assert estimate_tokens(large) > estimate_tokens(small)
