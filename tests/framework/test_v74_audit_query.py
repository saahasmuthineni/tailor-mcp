"""
v7.4.0 — audit_query layer Phase-A tests.

Phase A locks the load-bearing invariants:

    1. `since` parser accepts relative + ISO; rejects negative,
       future, malformed, and >90-day lookback.
    2. `AuditLog.query()` enforces the B1 column allowlist — never
       returns raw `params`, never returns raw `error` strings.
    3. `AuditQueryLayer.execute()` returns the structured envelope
       with rows / row_count / scope_statement and surfaces parser
       errors as a structured error envelope (not a raised exception).
    4. IS-NULL-or-match subject filter per ADR 0009.
    5. `include_self=true` default so audit-query usage is visible
       in the audit trail (IMPORTANT-1 from the v7.4.0 proposal audit).

Phase B (deferred to a follow-up commit) adds wire tests in
`tests/test_serve_v740_wire_audit.py`, AST-class W5 contract
extension, and red-team-reviewer adversarial pairing.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tailor.framework.audit import AuditLog
from tailor.framework.audit_query import (
    MAX_LOOKBACK_DAYS,
    AuditQueryLayer,
    SinceParseError,
    parse_since,
)

# ══════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════


@pytest.fixture()
def audit_log(tmp_path: Path) -> AuditLog:
    """Fresh AuditLog backed by a tempdir SQLite file."""
    log = AuditLog(tmp_path / "audit.db")
    yield log
    log.close()


@pytest.fixture()
def seeded_audit_log(audit_log: AuditLog) -> AuditLog:
    """AuditLog with a handful of representative rows across paths."""
    audit_log.record(
        "csv_dir", "csv_group_summary", 1, {"value_column": "force"},
        500, "SUCCESS", 12, entity_id="S001",
        scrubber_id="noop",
    )
    audit_log.record(
        "redcap_file", "redcap_record_detail", 1,
        {"record_id": "MRN-12345"},  # Tests must verify this never egresses
        420, "SUCCESS", 18, entity_id="S004",
        scrubber_id="noop", child_scrubber_id="redcap_metadata_flags",
        source_metadata_fingerprint="a1b2c3d4",
    )
    audit_log.record(
        "running", "strava_run_report", 3, {"activity_id": 42},
        45_000, "COST_BLOCKED", 8, entity_id=None,
        scrubber_id="noop",
        # Raw on-disk path simulating a pre-v7.3.1 row
        error="ERROR at /home/saahas/secret/path: cost exceeded",
    )
    audit_log.record(
        "audit_query", "audit_query", 1, {"since": "1h"},
        2_400, "SUCCESS", 5, entity_id=None,
        scrubber_id="noop",
    )
    audit_log.record(
        "vault", "vault_upsert_theme", 1, {"slug": "fatigue-decline"},
        1_200, "SUCCESS", 22, entity_id="S004",
        scrubber_id="noop",
    )
    return audit_log


# ══════════════════════════════════════════════════════════════
# 1. parse_since
# ══════════════════════════════════════════════════════════════


class TestParseSince:

    def test_relative_hours(self):
        now = datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc)
        result = parse_since("1h", now=now)
        assert result == "2026-05-16T11:00:00+00:00"

    def test_relative_days(self):
        now = datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc)
        result = parse_since("7d", now=now)
        assert result == "2026-05-09T12:00:00+00:00"

    def test_relative_weeks(self):
        now = datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc)
        result = parse_since("1w", now=now)
        assert result == "2026-05-09T12:00:00+00:00"

    def test_relative_case_insensitive(self):
        now = datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc)
        assert parse_since("1H", now=now) == parse_since("1h", now=now)

    def test_iso_with_z(self):
        now = datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc)
        result = parse_since("2026-05-15T10:00:00Z", now=now)
        assert result.startswith("2026-05-15T10:00:00")

    def test_iso_with_explicit_offset(self):
        now = datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc)
        result = parse_since("2026-05-15T10:00:00+00:00", now=now)
        assert result.startswith("2026-05-15T10:00:00")

    def test_iso_naive_coerces_utc(self):
        """Naive ISO timestamps must be coerced to UTC, not silently
        assumed to be local. Closes the v7.4.0 audit IMPORTANT-3."""
        now = datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc)
        result = parse_since("2026-05-15T10:00:00", now=now)
        assert result.endswith("+00:00")

    def test_negative_relative_rejected(self):
        """The v7.4.0 audit named this explicitly: `-1h` must be
        PARAM_INVALID, not silently `now + 1h`."""
        with pytest.raises(SinceParseError):
            parse_since("-1h")

    def test_zero_relative_rejected(self):
        with pytest.raises(SinceParseError):
            parse_since("0h")

    def test_garbage_rejected(self):
        with pytest.raises(SinceParseError):
            parse_since("garbage")

    def test_empty_rejected(self):
        with pytest.raises(SinceParseError):
            parse_since("")

    def test_non_string_rejected(self):
        with pytest.raises(SinceParseError):
            parse_since(None)  # type: ignore[arg-type]

    def test_future_iso_rejected(self):
        """Future timestamps deserve a clear error rather than
        silently returning zero rows."""
        now = datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc)
        with pytest.raises(SinceParseError, match="future"):
            parse_since("2026-05-17T00:00:00Z", now=now)

    def test_beyond_cap_rejected_relative(self):
        with pytest.raises(SinceParseError, match=f"{MAX_LOOKBACK_DAYS}"):
            parse_since(f"{MAX_LOOKBACK_DAYS + 1}d")

    def test_beyond_cap_rejected_iso(self):
        now = datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc)
        too_old = (now - timedelta(days=MAX_LOOKBACK_DAYS + 1)).isoformat()
        with pytest.raises(SinceParseError, match=f"{MAX_LOOKBACK_DAYS}"):
            parse_since(too_old, now=now)

    def test_parse_error_carries_original(self):
        try:
            parse_since("-1h")
        except SinceParseError as exc:
            assert exc.original == "-1h"


# ══════════════════════════════════════════════════════════════
# 2. AuditLog.query() column allowlist
# ══════════════════════════════════════════════════════════════


class TestAuditLogQueryAllowlist:
    """The IRB-stakes invariant: raw params and raw error never egress."""

    def test_returns_structured_columns_only(self, seeded_audit_log):
        rows = seeded_audit_log.query(since="2020-01-01T00:00:00+00:00")
        assert rows, "expected at least one row"
        row = rows[0]
        expected_keys = {
            "id", "timestamp", "domain", "tool_name", "tier",
            "token_estimate", "outcome", "duration_ms",
            "entity_id", "scrubber_id", "child_scrubber_id",
            "source_metadata_fingerprint", "has_error",
        }
        assert set(row.keys()) == expected_keys

    def test_never_returns_params_content(self, seeded_audit_log):
        """The REDCap `record_id="MRN-12345"` in the seeded row must
        never appear in the query response. This is the load-bearing
        v7.4.0 BLOCKING-1 invariant."""
        rows = seeded_audit_log.query(since="2020-01-01T00:00:00+00:00")
        for row in rows:
            for value in row.values():
                if isinstance(value, str):
                    assert "MRN-12345" not in value, (
                        f"row leaked params content: {row}"
                    )

    def test_never_returns_raw_error_string(self, seeded_audit_log):
        """The pre-v7.3.1-shape error with `/home/saahas/secret/path`
        in the seeded row must never appear in the response. This is
        the v7.4.0 BLOCKING-2 invariant — legacy rows from before the
        path-redaction hardening cannot be re-promoted to the LLM
        transcript."""
        rows = seeded_audit_log.query(since="2020-01-01T00:00:00+00:00")
        for row in rows:
            for value in row.values():
                if isinstance(value, str):
                    assert "secret" not in value, (
                        f"row leaked raw error content: {row}"
                    )
                    assert "/home/" not in value

    def test_has_error_bool_set_correctly(self, seeded_audit_log):
        """has_error is True iff the underlying error column is non-NULL."""
        rows = seeded_audit_log.query(since="2020-01-01T00:00:00+00:00")
        cost_blocked = [r for r in rows if r["outcome"] == "COST_BLOCKED"]
        assert cost_blocked and cost_blocked[0]["has_error"] is True
        success_rows = [r for r in rows if r["outcome"] == "SUCCESS"]
        assert success_rows and all(r["has_error"] is False for r in success_rows)

    def test_entity_id_is_null_or_match_filter(self, seeded_audit_log):
        """ADR 0009 IS-NULL-or-match: a entity_id filter must surface
        framework-tier rows (NULL entity_id) alongside the requested
        subject's rows. From the v7.4.0 audit NICE-TO-HAVE-1."""
        rows = seeded_audit_log.query(
            since="2020-01-01T00:00:00+00:00", entity_id="S004",
        )
        sids = {row["entity_id"] for row in rows}
        # Both the explicit S004 rows AND the NULL-subject rows surface
        assert "S004" in sids
        assert None in sids
        # The S001 row (different subject) does NOT surface
        assert "S001" not in sids

    def test_entity_id_none_returns_all(self, seeded_audit_log):
        rows = seeded_audit_log.query(since="2020-01-01T00:00:00+00:00")
        sids = {row["entity_id"] for row in rows}
        # All seeded subjects + NULL
        assert sids == {"S001", "S004", None}

    def test_include_self_true_default_surfaces_audit_query_rows(
        self, seeded_audit_log,
    ):
        """IMPORTANT-1 from the v7.4.0 audit: default surfaces audit-query
        usage to the IRB reviewer rather than silently hiding it."""
        rows = seeded_audit_log.query(since="2020-01-01T00:00:00+00:00")
        tools = {row["tool_name"] for row in rows}
        assert "audit_query" in tools

    def test_include_self_false_excludes_audit_query_rows(
        self, seeded_audit_log,
    ):
        rows = seeded_audit_log.query(
            since="2020-01-01T00:00:00+00:00", include_self=False,
        )
        tools = {row["tool_name"] for row in rows}
        assert "audit_query" not in tools

    def test_limit_clamped_to_hard_cap(self, audit_log):
        for i in range(120):
            audit_log.record(
                "csv_dir", f"tool_{i}", 1, {}, 100, "SUCCESS", 1,
                scrubber_id="noop",
            )
        rows = audit_log.query(since="2020-01-01T00:00:00+00:00", limit=500)
        assert len(rows) <= AuditLog._MAX_QUERY_LIMIT


# ══════════════════════════════════════════════════════════════
# 3. AuditQueryLayer.execute()
# ══════════════════════════════════════════════════════════════


class TestAuditQueryLayerExecute:

    def test_happy_path_returns_envelope(self, seeded_audit_log):
        layer = AuditQueryLayer(audit_log=seeded_audit_log)
        result = asyncio.run(
            layer.execute("audit_query", {"since": "30d"}),
        )
        assert "rows" in result
        assert "row_count" in result
        assert "scope_statement" in result
        assert result["row_count"] == len(result["rows"])

    def test_malformed_since_returns_structured_error(self, audit_log):
        layer = AuditQueryLayer(audit_log=audit_log)
        result = asyncio.run(
            layer.execute("audit_query", {"since": "garbage"}),
        )
        assert "error" in result
        assert "original_since" in result
        assert result["original_since"] == "garbage"

    def test_negative_since_returns_structured_error(self, audit_log):
        layer = AuditQueryLayer(audit_log=audit_log)
        result = asyncio.run(
            layer.execute("audit_query", {"since": "-1h"}),
        )
        assert "error" in result

    def test_unknown_tool_returns_error(self, audit_log):
        layer = AuditQueryLayer(audit_log=audit_log)
        result = asyncio.run(
            layer.execute("nope_query", {"since": "1h"}),
        )
        assert "error" in result

    def test_scope_statement_includes_filters(self, seeded_audit_log):
        layer = AuditQueryLayer(audit_log=seeded_audit_log)
        result = asyncio.run(
            layer.execute(
                "audit_query",
                {
                    "since": "1h",
                    "entity_id": "S004",
                    "domain": "redcap_file",
                    "limit": 10,
                },
            ),
        )
        scope = result["scope_statement"]
        assert "since=" in scope
        assert "entity_id=S004" in scope
        assert "domain=redcap_file" in scope
        assert "limit=10" in scope

    def test_tool_definitions_shape(self, audit_log):
        layer = AuditQueryLayer(audit_log=audit_log)
        defs = layer.tool_definitions
        assert len(defs) == 1
        td = defs[0]
        assert td.name == "audit_query"
        assert td.tier == 1
        assert "since" in td.params
        assert td.params["since"]["required"] is True
        assert "entity_id" in td.params
        assert "domain" in td.params

    def test_param_schemas_covers_all_declared_params(self, audit_log):
        layer = AuditQueryLayer(audit_log=audit_log)
        schemas = layer.param_schemas["audit_query"]
        for key in (
            "since", "entity_id", "domain", "tool", "outcome",
            "limit", "include_self",
        ):
            assert key in schemas
