"""
Tests for the local-LLM guardian layer (per ADR 0022).

Covers:
    * OracleResponse / NumericalClaim contract serialization.
    * NullBackend default-path behaviour (structured "not configured").
    * _flatten_claims handles flat and per-subject resolved-context shapes.
    * OllamaBackend HTTP wiring (mocked) — JSON parse, fallback path,
      numerical_claims always come from resolved_context.
    * LocalLLMLayer.execute returns OracleResponse.to_dict shape.
    * Router register_local_llm_layer + _dispatch_local_llm:
      tool registration, audit-log row, _meta provenance, error path.
    * Tool-name collision rejection between vault and local_llm layers.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from biosensor_mcp.framework.audit import AuditLog, _loads
from biosensor_mcp.framework.local_llm import (
    DEFAULT_TIER,
    LOCAL_LLM_TIERS,
    LocalLLMLayer,
    NullBackend,
    NumericalClaim,
    OllamaBackend,
    OracleMeta,
    OracleRequest,
    OracleResponse,
)
from biosensor_mcp.framework.local_llm.backends.null import _flatten_claims
from biosensor_mcp.framework.router import RouterMCP

# ─── Contract object tests ─────────────────────────────────────────


class TestOracleResponseContract:
    """The OracleResponse contract is the load-bearing fidelity guarantee."""

    def test_to_dict_shape(self):
        """Response serializes to documented shape."""
        meta = OracleMeta(
            model_id="llama3.1:8b",
            model_version_hash="abc123",
            tier="guardian",
            latency_ms=1234,
            prompt_hash="def456",
            called_at="2026-05-01T12:00:00Z",
            processing_calls=["csv_force_decline"],
            backend="ollama",
        )
        claim = NumericalClaim(
            metric="decline_pct_total", value=12.5,
            unit="%", processing_call="csv_force_decline",
        )
        response = OracleResponse(
            numerical_claims=[claim],
            narrative="P003 declined 12.5% over the trial.",
            ambiguity_axes=["operational definition of fatigue"],
            confidence=0.7,
            meta=meta,
        )
        d = response.to_dict()
        assert d["narrative"].startswith("P003")
        assert d["confidence"] == 0.7
        assert d["ambiguity_axes"] == ["operational definition of fatigue"]
        assert d["numerical_claims"][0]["metric"] == "decline_pct_total"
        assert d["numerical_claims"][0]["value"] == 12.5
        assert d["_meta"]["model_id"] == "llama3.1:8b"
        assert d["_meta"]["narrative_disclaimer"]  # non-empty disclaimer
        assert "non-citable" in d["_meta"]["narrative_disclaimer"]

    def test_tier_table_is_canonical(self):
        """The four tier codenames are stable across releases."""
        assert set(LOCAL_LLM_TIERS) == {
            "scout", "sentinel", "guardian", "titan",
        }
        assert DEFAULT_TIER == "guardian"
        # Each tier has model + ram_gb + floor_gb
        for tier_data in LOCAL_LLM_TIERS.values():
            assert "model" in tier_data
            assert "ram_gb" in tier_data
            assert "floor_gb" in tier_data


# ─── _flatten_claims tests ─────────────────────────────────────────


class TestFlattenClaims:
    """The fidelity guarantee: numerical claims always come from
    resolved_context, never from LLM prose. Both backends share this
    flattener so the property is enforced in one place."""

    def test_flat_shape(self):
        """{processing_call: {metric: value}} → claims with no subject_id."""
        ctx = {
            "csv_force_decline": {
                "peak": 100.0,
                "decline_pct_total": 12.5,
                "n_samples": 1500,
            },
        }
        claims = _flatten_claims(ctx)
        metrics = {c.metric: c.value for c in claims}
        assert metrics == {
            "peak": 100.0, "decline_pct_total": 12.5, "n_samples": 1500,
        }
        for c in claims:
            assert c.subject_id is None
            assert c.processing_call == "csv_force_decline"

    def test_per_subject_shape(self):
        """{processing_call: {subject_id: {metric: value}}} → keyed claims."""
        ctx = {
            "csv_cohort_summary": {
                "P003": {"decline_pct": 12.5, "peak": 100.0},
                "P004": {"decline_pct": 8.0, "peak": 95.0},
            },
        }
        claims = _flatten_claims(ctx)
        # 4 claims total: 2 metrics × 2 subjects
        assert len(claims) == 4
        by_subject = {(c.subject_id, c.metric): c.value for c in claims}
        assert by_subject[("P003", "decline_pct")] == 12.5
        assert by_subject[("P004", "peak")] == 95.0
        for c in claims:
            assert c.processing_call == "csv_cohort_summary"

    def test_booleans_are_skipped(self):
        """Booleans are int-subclass in Python; skip them so flag fields
        like {'has_data': True} don't surface as numerical claims."""
        ctx = {"csv_force_decline": {"has_decline": True, "peak": 100.0}}
        claims = _flatten_claims(ctx)
        metrics = {c.metric for c in claims}
        assert metrics == {"peak"}
        assert "has_decline" not in metrics

    def test_non_dict_results_are_skipped(self):
        """Defensive: if resolved_context value isn't a dict, skip."""
        ctx = {"csv_force_decline": "not a dict"}
        claims = _flatten_claims(ctx)
        assert claims == []

    def test_empty_context(self):
        """Empty resolved_context produces no claims."""
        assert _flatten_claims({}) == []


# ─── NullBackend tests ──────────────────────────────────────────────


class TestNullBackend:
    """NullBackend is the load-bearing default — surfaces deterministic
    claims with a 'not configured' narrative so existing deployments are
    behaviorally unchanged after this layer registers."""

    def test_compose_returns_structured_response(self):
        """NullBackend produces a complete OracleResponse, not None/error."""
        backend = NullBackend()
        request = OracleRequest(
            question="how did P003 do?",
            resolved_context={
                "csv_force_decline": {"peak": 100.0, "decline_pct_total": 8.0},
            },
        )
        response = asyncio.run(backend.compose(request))
        assert isinstance(response, OracleResponse)
        assert response.confidence == 0.0
        assert "not configured" in response.narrative.lower()
        # Numerical claims still surface — citable regardless of LLM state
        metrics = {c.metric for c in response.numerical_claims}
        assert metrics == {"peak", "decline_pct_total"}

    def test_meta_identifies_null_backend(self):
        """Audit log can distinguish null from real backends via _meta."""
        backend = NullBackend()
        request = OracleRequest(question="x", resolved_context={})
        response = asyncio.run(backend.compose(request))
        assert response.meta.backend == "null"
        assert response.meta.tier == "null"
        assert response.meta.model_id == "null"

    def test_backend_properties(self):
        backend = NullBackend()
        assert backend.backend_id == "null"
        assert backend.tier == "null"
        assert backend.model_id == "null"


# ─── OllamaBackend tests (HTTP mocked) ──────────────────────────────


class TestOllamaBackend:
    """OllamaBackend HTTP wiring — uses mocked requests so tests don't
    require a running Ollama daemon."""

    def test_init_validates_tier(self):
        """Unknown tier raises immediately, not on first call."""
        with pytest.raises(ValueError, match="Unknown tier"):
            OllamaBackend(tier="not-a-tier")

    def test_init_uses_tier_default_model(self):
        """Tier without explicit model picks the recommended model."""
        backend = OllamaBackend(tier="guardian")
        assert backend.model_id == "llama3.1:8b"

    def test_init_explicit_model_override(self):
        backend = OllamaBackend(tier="guardian", model="custom:model")
        assert backend.model_id == "custom:model"

    def test_compose_happy_path(self):
        """Successful Ollama call → OracleResponse with parsed narrative."""
        backend = OllamaBackend(tier="scout")
        ctx = {"csv_force_decline": {"peak": 100.0, "decline_pct_total": 12.5}}
        request = OracleRequest(question="how did P003 do?", resolved_context=ctx)

        ollama_response = json.dumps({
            "narrative": "P003 declined 12.5% from a peak of 100.",
            "ambiguity_axes": [],
            "confidence": 0.8,
        })
        with patch.object(backend, "_call_ollama", return_value=ollama_response):
            response = asyncio.run(backend.compose(request))

        assert response.narrative.startswith("P003 declined")
        assert response.confidence == 0.8
        # Numerical claims came from resolved_context, not the LLM.
        metrics = {c.metric for c in response.numerical_claims}
        assert metrics == {"peak", "decline_pct_total"}

    def test_compose_invents_no_numbers(self):
        """LOAD-BEARING FIDELITY GUARANTEE per ADR 0022:
        even if the LLM returns prose claiming numbers not in
        resolved_context, the response's numerical_claims come ONLY
        from resolved_context."""
        backend = OllamaBackend(tier="scout")
        ctx = {"csv_force_decline": {"peak": 100.0}}
        request = OracleRequest(question="?", resolved_context=ctx)

        # LLM tries to invent a "decline_pct_total: 50%" not in resolved_context
        bad_response = json.dumps({
            "narrative": "Hallucinated narrative claiming decline 50%.",
            "ambiguity_axes": [],
            "confidence": 0.9,
            "numerical_claims": [
                {"metric": "decline_pct_total", "value": 50.0},
            ],
        })
        with patch.object(backend, "_call_ollama", return_value=bad_response):
            response = asyncio.run(backend.compose(request))

        # The hallucinated claim must NOT appear in the response
        metrics = {c.metric for c in response.numerical_claims}
        assert metrics == {"peak"}
        assert "decline_pct_total" not in metrics

    def test_compose_with_empty_resolved_context_yields_no_claims(self):
        """Stronger fidelity property (per red-team-reviewer dissent):
        the previous test would pass on any implementation that doesn't
        mutate resolved_context. This test exercises the structural
        guarantee directly — when resolved_context is empty AND the LLM
        fabricates a numerical_claims field, the response contains
        ZERO claims. A future implementation that accidentally added
        an LLM-claim parser would break this test."""
        backend = OllamaBackend(tier="scout")
        request = OracleRequest(question="?", resolved_context={})

        fabricated = json.dumps({
            "narrative": "Entirely fabricated claim about a number.",
            "ambiguity_axes": [],
            "confidence": 0.99,
            "numerical_claims": [
                {"metric": "fabricated_metric", "value": 42.0},
                {"metric": "another_fake", "value": 100.0},
            ],
        })
        with patch.object(backend, "_call_ollama", return_value=fabricated):
            response = asyncio.run(backend.compose(request))

        # ZERO numerical claims — there's nothing in resolved_context
        # for _flatten_claims to derive from. Any non-empty result here
        # would mean the LLM-supplied claims got through.
        assert response.numerical_claims == []

    def test_compose_fallback_on_invalid_json(self):
        """Two-strike retry fails → fallback response with no narrative
        but deterministic claims still surface."""
        backend = OllamaBackend(tier="scout")
        ctx = {"csv_force_decline": {"peak": 100.0}}
        request = OracleRequest(question="?", resolved_context=ctx)

        # Both calls return non-JSON
        with patch.object(backend, "_call_ollama", return_value="not json at all"):
            response = asyncio.run(backend.compose(request))

        assert response.confidence == 0.0
        assert "unavailable" in response.narrative.lower()
        # Numerical claims still surface
        metrics = {c.metric for c in response.numerical_claims}
        assert metrics == {"peak"}
        assert response.meta.backend == "ollama-fallback"

    def test_compose_clamps_confidence(self):
        """LLM returning confidence > 1.0 or < 0.0 is clamped to [0,1]."""
        backend = OllamaBackend(tier="scout")
        for raw_conf, expected in [(2.5, 1.0), (-0.3, 0.0), (0.5, 0.5)]:
            llm_resp = json.dumps({
                "narrative": "x", "ambiguity_axes": [],
                "confidence": raw_conf,
            })
            request = OracleRequest(question="?", resolved_context={})
            with patch.object(backend, "_call_ollama", return_value=llm_resp):
                response = asyncio.run(backend.compose(request))
            assert response.confidence == expected


# ─── LocalLLMLayer tests ────────────────────────────────────────────


class TestLocalLLMLayer:
    def test_default_backend_is_null(self):
        layer = LocalLLMLayer()
        assert isinstance(layer.backend, NullBackend)

    def test_explicit_backend_used(self):
        backend = OllamaBackend(tier="guardian")
        layer = LocalLLMLayer(backend=backend)
        assert layer.backend is backend

    def test_tool_definitions_include_ask_local_oracle(self):
        layer = LocalLLMLayer()
        names = [t.name for t in layer.tool_definitions]
        assert names == ["ask_local_oracle"]

    def test_tool_definition_includes_subject_id_param(self):
        layer = LocalLLMLayer()
        tool = layer.tool_definitions[0]
        assert "subject_id" in tool.params

    def test_execute_unknown_tool_returns_error(self):
        layer = LocalLLMLayer()
        result = asyncio.run(layer.execute("not_a_tool", {}))
        assert "error" in result

    def test_execute_returns_oracle_response_shape(self):
        layer = LocalLLMLayer()
        result = asyncio.run(layer.execute(
            "ask_local_oracle",
            {
                "question": "how did P003 do?",
                "resolved_context": {
                    "csv_force_decline": {"peak": 100.0},
                },
            },
        ))
        assert "numerical_claims" in result
        assert "narrative" in result
        assert "ambiguity_axes" in result
        assert "confidence" in result
        assert "_meta" in result


# ─── Router integration tests ──────────────────────────────────────


class TestRouterDispatch:
    """The router's _dispatch_local_llm path: registration, dispatch,
    audit-log row, _meta merging."""

    def test_register_local_llm_layer_adds_tools(self, tmp_path: Path):
        router = RouterMCP(name="test", data_dir=tmp_path)
        layer = LocalLLMLayer()
        router.register_local_llm_layer(layer)
        try:
            assert "ask_local_oracle" in router.registered_tools
        finally:
            router._audit.close()

    def test_register_local_llm_layer_twice_rejected(self, tmp_path: Path):
        router = RouterMCP(name="test", data_dir=tmp_path)
        router.register_local_llm_layer(LocalLLMLayer())
        try:
            with pytest.raises(ValueError, match="already registered"):
                router.register_local_llm_layer(LocalLLMLayer())
        finally:
            router._audit.close()

    def test_dispatch_local_llm_writes_audit_row(self, tmp_path: Path):
        """Successful oracle call records SUCCESS row with domain=local_llm."""
        router = RouterMCP(name="test", data_dir=tmp_path)
        router.register_local_llm_layer(LocalLLMLayer())
        try:
            result = asyncio.run(router._dispatch(
                "ask_local_oracle",
                {
                    "question": "how did P003 do?",
                    "resolved_context": {
                        "csv_force_decline": {"peak": 100.0},
                    },
                    "subject_id": "P003",
                },
            ))
            # Result is a list of TextContent objects
            assert len(result) == 1
            payload = _loads(result[0].text)
            assert "narrative" in payload
            assert payload["_meta"]["domain"] == "local_llm"
            assert payload["_meta"]["tool_name"] == "ask_local_oracle"
            # Inner OracleResponse._meta is preserved under _meta.oracle
            assert "oracle" in payload["_meta"]
            assert payload["_meta"]["oracle"]["backend"] == "null"

            # Audit log carries the call
            audit = AuditLog(tmp_path / "audit.db")
            try:
                cursor = audit._conn.execute(
                    "SELECT domain, tool_name, outcome, subject_id "
                    "FROM audit_log WHERE tool_name = 'ask_local_oracle'"
                )
                rows = cursor.fetchall()
                assert len(rows) == 1
                domain, tool, outcome, subject_id = rows[0]
                assert domain == "local_llm"
                assert outcome == "SUCCESS"
                assert subject_id == "P003"
            finally:
                audit.close()
        finally:
            router._audit.close()

    def test_dispatch_local_llm_invalid_params_returns_error(
        self, tmp_path: Path,
    ):
        """Missing required 'question' param → PARAM_INVALID audit row."""
        router = RouterMCP(name="test", data_dir=tmp_path)
        router.register_local_llm_layer(LocalLLMLayer())
        try:
            result = asyncio.run(router._dispatch(
                "ask_local_oracle",
                {"resolved_context": {}},  # missing 'question'
            ))
            payload = _loads(result[0].text)
            assert "error" in payload
        finally:
            router._audit.close()

    def test_local_llm_tool_owner_is_local_llm(self, tmp_path: Path):
        """Owner dict disambiguates from vault layer."""
        router = RouterMCP(name="test", data_dir=tmp_path)
        router.register_local_llm_layer(LocalLLMLayer())
        try:
            assert router._framework_layer_owner["ask_local_oracle"] == "local_llm"
        finally:
            router._audit.close()

    def test_dispatch_local_llm_populates_oracle_audit_columns(
        self, tmp_path: Path,
    ):
        """ADR 0022 commits to audit-log columns capturing oracle
        provenance: model_id, model_version_hash, tier (codename),
        confidence, prompt_hash, and latency_ms (6 columns total —
        docstring previously said 5; oracle_latency_ms was added in
        the same migration block as the other 5, audit.py:192-199).
        The ``researcher-utility-reviewer`` flagged ADR-vs-code drift
        on this commitment pre-commit; this test pins the contract so
        it cannot silently regress."""
        router = RouterMCP(name="test", data_dir=tmp_path)
        router.register_local_llm_layer(LocalLLMLayer())
        try:
            asyncio.run(router._dispatch(
                "ask_local_oracle",
                {
                    "question": "how did P003 do?",
                    "resolved_context": {
                        "csv_force_decline": {"peak": 100.0},
                    },
                    "subject_id": "P003",
                },
            ))
            audit = AuditLog(tmp_path / "audit.db")
            try:
                cursor = audit._conn.execute(
                    "SELECT oracle_model_id, oracle_model_version_hash, "
                    "oracle_tier, oracle_confidence, oracle_prompt_hash, "
                    "oracle_latency_ms "
                    "FROM audit_log WHERE tool_name = 'ask_local_oracle' "
                    "AND outcome = 'SUCCESS'"
                )
                rows = cursor.fetchall()
                assert len(rows) == 1
                (model_id, version_hash, tier, confidence,
                 prompt_hash, latency_ms) = rows[0]
                # NullBackend identifies itself in every column
                assert model_id == "null"
                assert version_hash == "null"
                assert tier == "null"
                assert confidence == 0.0
                assert prompt_hash is not None and len(prompt_hash) == 16
                # latency_ms is queryable from SQL — distinct from the
                # row's duration_ms which spans the full router pipeline
                assert latency_ms is not None and latency_ms >= 0
            finally:
                audit.close()
        finally:
            router._audit.close()

    def test_non_oracle_dispatch_leaves_oracle_columns_null(
        self, tmp_path: Path,
    ):
        """Non-oracle calls (PARAM_INVALID on ask_local_oracle itself
        with bad params) record NULL for the oracle_* columns — the
        new columns are oracle-specific, not biosensor-tier audit data."""
        router = RouterMCP(name="test", data_dir=tmp_path)
        router.register_local_llm_layer(LocalLLMLayer())
        try:
            asyncio.run(router._dispatch(
                "ask_local_oracle",
                {"resolved_context": {}},  # missing 'question' → PARAM_INVALID
            ))
            audit = AuditLog(tmp_path / "audit.db")
            try:
                cursor = audit._conn.execute(
                    "SELECT oracle_model_id, oracle_model_version_hash, "
                    "oracle_tier, oracle_confidence, oracle_prompt_hash, "
                    "oracle_latency_ms "
                    "FROM audit_log WHERE outcome = 'PARAM_INVALID'"
                )
                rows = cursor.fetchall()
                assert len(rows) == 1
                # All six oracle columns NULL on a pre-execute failure —
                # we don't have a response to read provenance from.
                assert all(v is None for v in rows[0])
            finally:
                audit.close()
        finally:
            router._audit.close()
