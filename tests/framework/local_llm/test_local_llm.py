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


# ─── ADR 0023 — substrate-vision asymmetry ─────────────────────────


class _StubVaultStorage:
    """Minimal VaultStorage stand-in used by the substrate-scan tests.

    Implements only the two methods :class:`LocalLLMLayer` calls
    (``list_themes`` / ``list_notes``); ignores filter args except
    ``subject_id``, which it threads through so tests can assert it
    was passed.
    """

    def __init__(
        self,
        themes: dict[str | None, list[dict]] | None = None,
        notes: dict[str, dict[str | None, list[dict]]] | None = None,
        raise_on_call: Exception | None = None,
    ):
        self._themes = themes or {}
        self._notes = notes or {}
        self._raise = raise_on_call
        self.calls: list[tuple] = []

    def list_themes(self, subject_id=None, limit=50, **kw):
        self.calls.append(("list_themes", subject_id, limit))
        if self._raise is not None:
            raise self._raise
        return list(self._themes.get(subject_id, []))[:limit]

    def list_notes(self, note_type=None, subject_id=None, limit=50, **kw):
        self.calls.append(("list_notes", note_type, subject_id, limit))
        if self._raise is not None:
            raise self._raise
        return list(
            self._notes.get(note_type, {}).get(subject_id, [])
        )[:limit]


class TestRelatedSubstrateContract:
    """OracleResponse.related_substrate per ADR 0023."""

    def _build_response(self, related=None) -> OracleResponse:
        meta = OracleMeta(
            model_id="m", model_version_hash="v", tier="null",
            latency_ms=1, prompt_hash="p", called_at="2026-05-03T00:00:00Z",
            backend="null",
        )
        kwargs = dict(
            numerical_claims=[],
            narrative="",
            ambiguity_axes=[],
            confidence=0.0,
            meta=meta,
        )
        if related is not None:
            kwargs["related_substrate"] = related
        return OracleResponse(**kwargs)

    def test_default_is_empty_list(self):
        """Default constructor leaves related_substrate empty so legacy
        callers and tests are unaffected."""
        resp = self._build_response()
        assert resp.related_substrate == []
        assert resp.to_dict()["related_substrate"] == []

    def test_to_dict_top_level_not_under_meta(self):
        """ADR 0023 § Decision: related_substrate is a top-level
        response field; it is not provenance and does not nest into
        _meta."""
        resp = self._build_response(related=[{"kind": "theme", "slug": "x"}])
        d = resp.to_dict()
        assert d["related_substrate"] == [{"kind": "theme", "slug": "x"}]
        assert "related_substrate" not in d["_meta"]

    def test_substrate_scan_warning_default_absent(self):
        """Happy path: warning is None and not surfaced on the wire.
        Avoids noise on every successful oracle call."""
        resp = self._build_response()
        assert resp.substrate_scan_warning is None
        assert "substrate_scan_warning" not in resp.to_dict()

    def test_substrate_scan_warning_surfaces_when_set(self):
        """When a VaultStorage exception is swallowed by the layer's
        defensive scan, the reason surfaces at the response top
        level so a reviewer reading the wire payload can distinguish
        clean-empty from crash-empty (parallels ADR 0003
        scrubber_warning seam)."""
        resp = self._build_response()
        resp.substrate_scan_warning = "substrate scan failed: db locked"
        d = resp.to_dict()
        assert d["substrate_scan_warning"].startswith("substrate scan failed")
        # Top-level — not nested under _meta
        assert "substrate_scan_warning" not in d["_meta"]


class TestLocalLLMLayerSubstrateScan:
    """LocalLLMLayer._scan_related_substrate — ADR 0023 PR1."""

    def _layer_with(self, storage):
        return LocalLLMLayer(vault_storage=storage)

    def test_no_vault_returns_empty(self):
        """vault_storage=None → defensive empty; no exception, no log
        spam in production."""
        layer = LocalLLMLayer()  # default vault_storage=None
        result = asyncio.run(layer.execute(
            "ask_local_oracle",
            {
                "question": "?",
                "resolved_context": {"csv_force_decline": {"peak": 1.0}},
                "subject_id": "P003",
            },
        ))
        assert result["related_substrate"] == []

    def test_finds_themes_for_explicit_subject_id(self):
        """request.subject_id triggers a list_themes(subject_id=...) query
        and populates related_substrate."""
        storage = _StubVaultStorage(themes={
            "P003": [{
                "slug": "force-fatigue-mechanism",
                "status": "open",
                "last_updated": "2026-04-30T10:00:00Z",
                "subject_id": "P003",
            }],
        })
        layer = self._layer_with(storage)
        result = asyncio.run(layer.execute(
            "ask_local_oracle",
            {
                "question": "?",
                "resolved_context": {},
                "subject_id": "P003",
            },
        ))
        slugs = [e["slug"] for e in result["related_substrate"]]
        assert "force-fatigue-mechanism" in slugs
        # Verify the layer asked storage with subject_id (ADR 0009
        # IS-NULL-or-match filter semantics inherited from VaultStorage)
        assert ("list_themes", "P003", 10) in storage.calls

    def test_walks_per_subject_resolved_context(self):
        """Per-subject resolved_context shape (cohort summary):
        {processing_call: {subject_id: {metric: value}}} — scan walks
        each subject key."""
        storage = _StubVaultStorage(themes={
            "P003": [{
                "slug": "p003-theme",
                "status": "open",
                "last_updated": "2026-04-30T10:00:00Z",
                "subject_id": "P003",
            }],
            "P004": [{
                "slug": "p004-theme",
                "status": "open",
                "last_updated": "2026-04-29T10:00:00Z",
                "subject_id": "P004",
            }],
        })
        layer = self._layer_with(storage)
        result = asyncio.run(layer.execute(
            "ask_local_oracle",
            {
                "question": "?",
                "resolved_context": {
                    "csv_cohort_summary": {
                        "P003": {"decline_pct": 12.5},
                        "P004": {"decline_pct": 8.0},
                    },
                },
            },
        ))
        slugs = {e["slug"] for e in result["related_substrate"]}
        assert slugs == {"p003-theme", "p004-theme"}

    def test_caps_total_entries(self):
        """Substrate cap protects the tool description's token budget
        regardless of vault size — 100 themes returned by storage
        produce at most _SUBSTRATE_CAP entries on the wire."""
        many = [
            {
                "slug": f"theme-{i:03d}",
                "status": "open",
                "last_updated": f"2026-04-{(i % 28) + 1:02d}T10:00:00Z",
                "subject_id": "P003",
            }
            for i in range(100)
        ]
        storage = _StubVaultStorage(themes={"P003": many})
        layer = self._layer_with(storage)
        result = asyncio.run(layer.execute(
            "ask_local_oracle",
            {
                "question": "?",
                "resolved_context": {},
                "subject_id": "P003",
            },
        ))
        assert (
            len(result["related_substrate"]) <= LocalLLMLayer._SUBSTRATE_CAP
        )

    def test_swallows_storage_exception(self):
        """A vault-scan failure must never break the oracle call. The
        narrative + numerical_claims continue to surface; substrate
        is empty and the failure reason surfaces in
        ``substrate_scan_warning`` so a reviewer reading the wire
        payload can distinguish clean-empty from crash-empty
        (closes phi-irb-risk-reviewer Lens 3 + mcp-protocol-auditor
        BORDER NOTE; parallels ADR 0003 scrubber_warning seam)."""
        storage = _StubVaultStorage(raise_on_call=RuntimeError("db locked"))
        layer = self._layer_with(storage)
        result = asyncio.run(layer.execute(
            "ask_local_oracle",
            {
                "question": "?",
                "resolved_context": {"csv_force_decline": {"peak": 1.0}},
                "subject_id": "P003",
            },
        ))
        assert result["related_substrate"] == []
        assert "substrate_scan_warning" in result
        assert "db locked" in result["substrate_scan_warning"]
        # Numerical claim still surfaces — the rest of the response is
        # unaffected by the substrate-scan failure.
        metrics = {c["metric"] for c in result["numerical_claims"]}
        assert "peak" in metrics

    def test_happy_path_omits_substrate_scan_warning(self):
        """No warning on a clean scan — the field is only emitted on
        the wire when something actually went wrong."""
        storage = _StubVaultStorage(themes={
            "P003": [{
                "slug": "x",
                "status": "open",
                "last_updated": "2026-04-30T10:00:00Z",
                "subject_id": "P003",
            }],
        })
        layer = self._layer_with(storage)
        result = asyncio.run(layer.execute(
            "ask_local_oracle",
            {
                "question": "?",
                "resolved_context": {},
                "subject_id": "P003",
            },
        ))
        assert "substrate_scan_warning" not in result

    def test_non_dict_resolved_context_value_skipped(self):
        """coverage gate (line 276): a non-dict result in
        resolved_context is skipped by _collect_subjects rather than
        raising. The substrate scan still runs against
        request.subject_id; the malformed entry just contributes no
        per-subject keys."""
        storage = _StubVaultStorage(themes={
            "P003": [{
                "slug": "x",
                "status": "open",
                "last_updated": "2026-04-30T10:00:00Z",
                "subject_id": "P003",
            }],
        })
        layer = self._layer_with(storage)
        result = asyncio.run(layer.execute(
            "ask_local_oracle",
            {
                "question": "?",
                "resolved_context": {
                    "csv_summary_report": "string-not-a-dict",
                    "csv_force_decline": {"peak": 1.0},
                },
                "subject_id": "P003",
            },
        ))
        # Did not raise; substrate scan still ran on the explicit
        # subject_id; the malformed entry was tolerated.
        slugs = [e["slug"] for e in result["related_substrate"]]
        assert slugs == ["x"]

    def test_collect_subjects_skips_meta_shaped_sibling_keys(self):
        """red-team-reviewer OBJECTION on PR1 release pass: a tool
        returning `{call: {"_meta": {...}, "columns": {...},
        "P003": {...}}}` would (without the inner-scalar filter)
        yield `subjects=['_meta','columns','P003']` from
        _collect_subjects but only `P003` from _flatten_claims. The
        upstream auditor's CLEAN verdict was issued on a false
        equivalence between the two heuristics. After the fix, only
        keys whose inner dict has at least one numeric scalar
        survive — matching _flatten_claims's implicit filter at
        backends/null.py:108-115.
        """
        storage = _StubVaultStorage(themes={
            "P003": [{
                "slug": "p003-theme",
                "status": "open",
                "last_updated": "2026-04-30T10:00:00Z",
                "subject_id": "P003",
            }],
            # Bogus storage rows for the misclassified keys; if the
            # fix breaks, these will surface in related_substrate.
            "_meta": [{
                "slug": "would-not-exist",
                "status": "open",
                "last_updated": "2026-04-30T10:00:00Z",
                "subject_id": "_meta",
            }],
            "columns": [{
                "slug": "also-not-real",
                "status": "open",
                "last_updated": "2026-04-30T10:00:00Z",
                "subject_id": "columns",
            }],
        })
        layer = self._layer_with(storage)
        result = asyncio.run(layer.execute(
            "ask_local_oracle",
            {
                "question": "?",
                "resolved_context": {
                    "future_tool_with_meta": {
                        "_meta": {"version": "1.0", "schema": "v2"},
                        "columns": {"hr": "bpm", "ts": "iso"},
                        "P003": {"decline_pct": 12.5, "peak": 100.0},
                    },
                },
            },
        ))
        slugs = {e["slug"] for e in result["related_substrate"]}
        # Only P003 was a legitimate subject; the _meta/columns
        # sibling keys were correctly filtered by the inner-scalar
        # check before the storage query was even issued.
        assert slugs == {"p003-theme"}
        # Storage was NOT asked about the bogus subjects
        called_subjects = {
            args[1] for args in storage.calls if args[0] == "list_themes"
        }
        assert called_subjects == {"P003"}

    def test_cross_kind_slug_collision_both_surface(self):
        """coverage gate (line 233) + correctness edge case
        (coverage-criticality-mapper BORDER NOTE): a theme and a
        moment that happen to share a slug both surface — they are
        distinct artifacts in different vault namespaces. The dedup
        key is (kind, slug), not slug alone, so cross-kind
        collisions don't silently drop content."""
        shared = "force-decline-mechanism"
        storage = _StubVaultStorage(
            themes={
                "P003": [{
                    "slug": shared,
                    "status": "open",
                    "last_updated": "2026-04-30T10:00:00Z",
                    "subject_id": "P003",
                }],
            },
            notes={
                "moment": {
                    "P003": [{
                        "filename": f"{shared}.md",
                        "frontmatter": {"title": "Same name, different kind"},
                        "written_at": "2026-04-29T10:00:00Z",
                        "subject_id": "P003",
                    }],
                },
            },
        )
        layer = self._layer_with(storage)
        result = asyncio.run(layer.execute(
            "ask_local_oracle",
            {
                "question": "?",
                "resolved_context": {},
                "subject_id": "P003",
            },
        ))
        # Both surface — the (kind, slug) dedup key keeps them
        # distinct. A bug that reverted to slug-only dedup would
        # drop the moment.
        kinds = sorted(e["kind"] for e in result["related_substrate"])
        assert kinds == ["moment", "theme"]
        # And both reference the same slug name
        slugs = {e["slug"] for e in result["related_substrate"]}
        assert slugs == {shared}

    def test_no_subjects_in_scope_returns_empty(self):
        """When neither request.subject_id nor any per-subject key in
        resolved_context is present, the scan returns [] — substrate
        scan is purpose-built to find content about subjects of the
        question, not arbitrary recent vault content."""
        storage = _StubVaultStorage(themes={
            None: [{
                "slug": "cross-subject-theme",
                "status": "open",
                "last_updated": "2026-04-30T10:00:00Z",
                "subject_id": None,
            }],
        })
        layer = self._layer_with(storage)
        result = asyncio.run(layer.execute(
            "ask_local_oracle",
            {
                "question": "?",
                "resolved_context": {"csv_force_decline": {"peak": 1.0}},
            },
        ))
        assert result["related_substrate"] == []
        # Storage was NOT called — early return on empty subject list.
        assert storage.calls == []

    def test_collects_moments_and_failure_modes(self):
        """Substrate scan surfaces moment + failure_mode notes alongside
        themes — these are analyst-authored interpretation, the
        load-bearing content for grounding LLM composition."""
        storage = _StubVaultStorage(notes={
            "moment": {
                "P003": [{
                    "filename": "2026-04-30-p003-aha.md",
                    "frontmatter": {"title": "P003 plateau", "status": None},
                    "written_at": "2026-04-30T10:00:00Z",
                    "subject_id": "P003",
                }],
            },
            "failure_mode": {
                "P003": [{
                    "filename": "fm-electrode-drift.md",
                    "frontmatter": {
                        "title": "Electrode drift past minute 8",
                        "status": "active",
                    },
                    "written_at": "2026-04-29T10:00:00Z",
                    "subject_id": "P003",
                }],
            },
        })
        layer = self._layer_with(storage)
        result = asyncio.run(layer.execute(
            "ask_local_oracle",
            {
                "question": "?",
                "resolved_context": {},
                "subject_id": "P003",
            },
        ))
        kinds = {e["kind"] for e in result["related_substrate"]}
        assert kinds == {"moment", "failure_mode"}
        # Filename .md extension stripped to canonical slug shape
        slugs = {e["slug"] for e in result["related_substrate"]}
        assert "2026-04-30-p003-aha" in slugs
        assert "fm-electrode-drift" in slugs

    def test_sort_order_last_updated_desc(self):
        """Substrate is sorted by last_updated descending. This is a
        load-bearing contract claim from ADR 0023 — when the vault
        has more than _SUBSTRATE_CAP candidates, it determines which
        entries survive the cap. A future "improvement" sorting by
        status or alphabetically would silently break the recency
        bias the cap depends on."""
        storage = _StubVaultStorage(themes={
            "P003": [
                {
                    "slug": "oldest",
                    "status": "open",
                    "last_updated": "2026-01-01T00:00:00Z",
                    "subject_id": "P003",
                },
                {
                    "slug": "newest",
                    "status": "open",
                    "last_updated": "2026-04-30T00:00:00Z",
                    "subject_id": "P003",
                },
                {
                    "slug": "middle",
                    "status": "open",
                    "last_updated": "2026-03-15T00:00:00Z",
                    "subject_id": "P003",
                },
            ],
        })
        layer = self._layer_with(storage)
        result = asyncio.run(layer.execute(
            "ask_local_oracle",
            {
                "question": "?",
                "resolved_context": {},
                "subject_id": "P003",
            },
        ))
        slugs = [e["slug"] for e in result["related_substrate"]]
        assert slugs == ["newest", "middle", "oldest"]

    def test_dedupe_across_subjects(self):
        """If two subjects share a cross-subject theme (subject_id IS
        NULL — ADR 0009 IS-NULL-or-match), it appears once, not
        twice. The per-subject queries each return it; the layer
        dedupes by slug."""
        cross = {
            "slug": "cross-subject-hypothesis",
            "status": "open",
            "last_updated": "2026-04-30T10:00:00Z",
            "subject_id": None,
        }
        storage = _StubVaultStorage(themes={"P003": [cross], "P004": [cross]})
        layer = self._layer_with(storage)
        result = asyncio.run(layer.execute(
            "ask_local_oracle",
            {
                "question": "?",
                "resolved_context": {
                    "csv_cohort_summary": {
                        "P003": {"x": 1.0},
                        "P004": {"x": 2.0},
                    },
                },
            },
        ))
        slugs = [e["slug"] for e in result["related_substrate"]]
        assert slugs.count("cross-subject-hypothesis") == 1


class TestRouterDispatchSubstrateCount:
    """Audit-log oracle_substrate_count column per ADR 0023."""

    def test_success_records_substrate_count_zero_with_no_vault(
        self, tmp_path: Path,
    ):
        """No vault wiring → substrate scan returns []; audit column
        records 0, not NULL. Distinguishes "successfully scanned and
        found nothing" from "pre-execute failure" (where the column
        is NULL)."""
        router = RouterMCP(name="test", data_dir=tmp_path)
        router.register_local_llm_layer(LocalLLMLayer())
        try:
            asyncio.run(router._dispatch(
                "ask_local_oracle",
                {
                    "question": "?",
                    "resolved_context": {"csv_force_decline": {"peak": 1.0}},
                    "subject_id": "P003",
                },
            ))
            audit = AuditLog(tmp_path / "audit.db")
            try:
                cursor = audit._conn.execute(
                    "SELECT oracle_substrate_count FROM audit_log "
                    "WHERE outcome = 'SUCCESS'"
                )
                rows = cursor.fetchall()
                assert len(rows) == 1
                assert rows[0][0] == 0
            finally:
                audit.close()
        finally:
            router._audit.close()

    def test_success_records_substrate_count_when_vault_wired(
        self, tmp_path: Path,
    ):
        """Layer with a wired vault_storage that returns substrate →
        audit column records the actual count."""
        storage = _StubVaultStorage(themes={
            "P003": [
                {
                    "slug": "t1", "status": "open",
                    "last_updated": "2026-04-30T10:00:00Z",
                    "subject_id": "P003",
                },
                {
                    "slug": "t2", "status": "open",
                    "last_updated": "2026-04-29T10:00:00Z",
                    "subject_id": "P003",
                },
            ],
        })
        router = RouterMCP(name="test", data_dir=tmp_path)
        router.register_local_llm_layer(
            LocalLLMLayer(vault_storage=storage)
        )
        try:
            asyncio.run(router._dispatch(
                "ask_local_oracle",
                {
                    "question": "?",
                    "resolved_context": {},
                    "subject_id": "P003",
                },
            ))
            audit = AuditLog(tmp_path / "audit.db")
            try:
                cursor = audit._conn.execute(
                    "SELECT oracle_substrate_count FROM audit_log "
                    "WHERE outcome = 'SUCCESS'"
                )
                rows = cursor.fetchall()
                assert len(rows) == 1
                assert rows[0][0] == 2
            finally:
                audit.close()
        finally:
            router._audit.close()

    def test_param_invalid_leaves_substrate_count_null(
        self, tmp_path: Path,
    ):
        """Pre-execute failure (PARAM_INVALID) records NULL for
        oracle_substrate_count — there was no response to read a
        substrate list from."""
        router = RouterMCP(name="test", data_dir=tmp_path)
        router.register_local_llm_layer(LocalLLMLayer())
        try:
            asyncio.run(router._dispatch(
                "ask_local_oracle",
                {"resolved_context": {}},  # missing 'question'
            ))
            audit = AuditLog(tmp_path / "audit.db")
            try:
                cursor = audit._conn.execute(
                    "SELECT oracle_substrate_count FROM audit_log "
                    "WHERE outcome = 'PARAM_INVALID'"
                )
                rows = cursor.fetchall()
                assert len(rows) == 1
                assert rows[0][0] is None
            finally:
                audit.close()
        finally:
            router._audit.close()


class TestRouterDispatchGapReasoningCounts:
    """Audit-log oracle_next_best_calls_count and
    oracle_unresolved_intent_count columns per ADR 0023 PR2.

    Mirrors TestRouterDispatchSubstrateCount above — the same audit-
    completeness invariant ADR 0023 § "Audit-log column" justified
    for substrate applies to gap-reasoning by symmetry: an IRB
    reviewer should be able to query "how much did the local LLM
    suggest and ask?" from audit.db without parsing the response
    payload."""

    def _build_layer_with_canned_response(
        self, next_best_calls: list[str], unresolved_intent: list[str],
    ) -> LocalLLMLayer:
        """A LocalLLMLayer whose backend returns the supplied lists.
        Bypasses Ollama HTTP entirely — we want to test the dispatch-
        layer extraction, not the backend."""
        from biosensor_mcp.framework.local_llm.backends import (
            LocalLLMBackend,
        )

        class _CannedBackend(LocalLLMBackend):
            @property
            def backend_id(self) -> str: return "canned"
            @property
            def tier(self) -> str: return "canned"
            @property
            def model_id(self) -> str: return "canned"

            async def compose(self, request):
                return OracleResponse(
                    numerical_claims=[], narrative="canned",
                    ambiguity_axes=[], confidence=0.5,
                    next_best_calls=list(next_best_calls),
                    unresolved_intent=list(unresolved_intent),
                    meta=OracleMeta(
                        model_id="m", model_version_hash="h",
                        tier="canned", latency_ms=1, prompt_hash="p",
                        called_at="2026-05-03T00:00:00Z",
                        processing_calls=[], backend="canned",
                    ),
                )

        return LocalLLMLayer(backend=_CannedBackend())

    def test_success_records_zero_when_lists_empty(self, tmp_path: Path):
        """NullBackend (or any backend) returning empty lists →
        audit columns record 0, not NULL. Distinguishes "successfully
        composed and emitted no gap reasoning" from "pre-execute
        failure" (where both columns are NULL)."""
        router = RouterMCP(name="test", data_dir=tmp_path)
        router.register_local_llm_layer(LocalLLMLayer())  # NullBackend
        try:
            asyncio.run(router._dispatch(
                "ask_local_oracle",
                {"question": "?", "resolved_context": {}},
            ))
            audit = AuditLog(tmp_path / "audit.db")
            try:
                cursor = audit._conn.execute(
                    "SELECT oracle_next_best_calls_count, "
                    "oracle_unresolved_intent_count FROM audit_log "
                    "WHERE outcome = 'SUCCESS'"
                )
                rows = cursor.fetchall()
                assert len(rows) == 1
                assert rows[0] == (0, 0)
            finally:
                audit.close()
        finally:
            router._audit.close()

    def test_success_records_actual_counts_when_populated(
        self, tmp_path: Path,
    ):
        """Backend returning non-empty lists → audit columns record
        the actual lengths. Counts are independent (one populated,
        other empty round-trips correctly)."""
        layer = self._build_layer_with_canned_response(
            next_best_calls=["csv_force_decline", "csv_summary_report"],
            unresolved_intent=[
                "which group is P003 in?", "stratify by sex?", "n=?",
            ],
        )
        router = RouterMCP(name="test", data_dir=tmp_path)
        router.register_local_llm_layer(layer)
        try:
            asyncio.run(router._dispatch(
                "ask_local_oracle",
                {"question": "?", "resolved_context": {}},
            ))
            audit = AuditLog(tmp_path / "audit.db")
            try:
                cursor = audit._conn.execute(
                    "SELECT oracle_next_best_calls_count, "
                    "oracle_unresolved_intent_count FROM audit_log "
                    "WHERE outcome = 'SUCCESS'"
                )
                rows = cursor.fetchall()
                assert len(rows) == 1
                assert rows[0] == (2, 3)
            finally:
                audit.close()
        finally:
            router._audit.close()

    def test_param_invalid_leaves_both_counts_null(self, tmp_path: Path):
        """Pre-execute failure (PARAM_INVALID) records NULL for both
        new columns — the response never existed to extract counts
        from. Same invariant as oracle_substrate_count's NULL-on-
        failure shape."""
        router = RouterMCP(name="test", data_dir=tmp_path)
        router.register_local_llm_layer(LocalLLMLayer())
        try:
            asyncio.run(router._dispatch(
                "ask_local_oracle",
                {"resolved_context": {}},  # missing 'question'
            ))
            audit = AuditLog(tmp_path / "audit.db")
            try:
                cursor = audit._conn.execute(
                    "SELECT oracle_next_best_calls_count, "
                    "oracle_unresolved_intent_count FROM audit_log "
                    "WHERE outcome = 'PARAM_INVALID'"
                )
                rows = cursor.fetchall()
                assert len(rows) == 1
                assert rows[0] == (None, None)
            finally:
                audit.close()
        finally:
            router._audit.close()


# ─── ADR 0023 PR2 — LLM-driven gap-reasoning contract ──────────────


class TestCooperationLoopContract:
    """OracleResponse-level contract for next_best_calls and
    unresolved_intent — the LLM-generated gap-reasoning fields per
    ADR 0023 PR2. Wire-shape stability: empty lists by default, always
    emitted (even when empty), defensive list-coercion downstream of
    backends."""

    def _meta(self) -> OracleMeta:
        return OracleMeta(
            model_id="m", model_version_hash="h", tier="guardian",
            latency_ms=1, prompt_hash="p",
            called_at="2026-05-03T00:00:00Z",
            processing_calls=[], backend="x",
        )

    def test_defaults_are_empty_lists(self):
        """A response constructed without naming the new fields gets
        empty lists — the wire contract holds for any caller that
        existed before PR2."""
        resp = OracleResponse(
            numerical_claims=[], narrative="", ambiguity_axes=[],
            confidence=0.0, meta=self._meta(),
        )
        assert resp.next_best_calls == []
        assert resp.unresolved_intent == []

    def test_to_dict_always_emits_both_fields(self):
        """Even when empty, both fields appear in the wire payload —
        so hosted Claude can rely on `response.next_best_calls`
        existing without a defensive get(). Mirrors related_substrate
        from PR1."""
        resp = OracleResponse(
            numerical_claims=[], narrative="", ambiguity_axes=[],
            confidence=0.0, meta=self._meta(),
        )
        d = resp.to_dict()
        assert "next_best_calls" in d
        assert "unresolved_intent" in d
        assert d["next_best_calls"] == []
        assert d["unresolved_intent"] == []

    def test_to_dict_round_trips_populated_lists(self):
        resp = OracleResponse(
            numerical_claims=[], narrative="", ambiguity_axes=[],
            confidence=0.0, meta=self._meta(),
            next_best_calls=["csv_force_decline"],
            unresolved_intent=["which subjects belong to group A?"],
        )
        d = resp.to_dict()
        assert d["next_best_calls"] == ["csv_force_decline"]
        assert d["unresolved_intent"] == [
            "which subjects belong to group A?",
        ]

    def test_dataclass_default_factory_is_independent_per_instance(self):
        """Regression guard for the classic mutable-default trap:
        two instances must not share the same default list. If a
        future refactor swapped field(default_factory=list) for `=[]`,
        this test would catch the silent bug where mutating one
        response's list mutates another's."""
        a = OracleResponse(
            numerical_claims=[], narrative="", ambiguity_axes=[],
            confidence=0.0, meta=self._meta(),
        )
        b = OracleResponse(
            numerical_claims=[], narrative="", ambiguity_axes=[],
            confidence=0.0, meta=self._meta(),
        )
        a.next_best_calls.append("csv_force_decline")
        a.unresolved_intent.append("clarify cohort")
        assert b.next_best_calls == []
        assert b.unresolved_intent == []


class TestOllamaBackendCooperationLoop:
    """OllamaBackend behaviour for the new gap-reasoning fields. Uses
    mocked HTTP throughout so tests don't require a running Ollama."""

    def test_prompt_includes_both_new_fields_and_split_rule(self):
        """The prompt schema must teach the model to emit both fields,
        and the prompt body must teach the load-bearing split:
        fetch-this-data vs ask-the-analyst. Without the split, the
        model conflates the two and the cooperation loop degrades to
        a single-list ambiguity_axes."""
        backend = OllamaBackend(tier="scout")
        request = OracleRequest(question="?", resolved_context={})
        prompt = backend._build_prompt(request)
        assert "next_best_calls" in prompt
        assert "unresolved_intent" in prompt
        # Split rule — exact wording is not load-bearing, but the two
        # role labels must both appear so a model reading the prompt
        # can distinguish them.
        assert "fetch" in prompt.lower()
        assert "analyst" in prompt.lower()

    def test_compose_parses_both_fields(self):
        """Happy path: well-formed JSON with both lists populated
        round-trips through the parser into the OracleResponse."""
        backend = OllamaBackend(tier="scout")
        request = OracleRequest(question="?", resolved_context={})
        llm_resp = json.dumps({
            "narrative": "n",
            "ambiguity_axes": [],
            "confidence": 0.5,
            "next_best_calls": ["csv_force_decline", "csv_summary_report"],
            "unresolved_intent": ["which group is P003 in?"],
        })
        with patch.object(backend, "_call_ollama", return_value=llm_resp):
            response = asyncio.run(backend.compose(request))
        assert response.next_best_calls == [
            "csv_force_decline", "csv_summary_report",
        ]
        assert response.unresolved_intent == ["which group is P003 in?"]

    def test_compose_defensive_coercion_when_not_lists(self):
        """LLM emits a string instead of a list (a common JSON-mode
        failure shape) — parser falls back to []. Mirrors the
        ambiguity_axes coercion at ollama.py:174-175 — without this
        the wire payload would carry a malformed type."""
        backend = OllamaBackend(tier="scout")
        request = OracleRequest(question="?", resolved_context={})
        llm_resp = json.dumps({
            "narrative": "n",
            "ambiguity_axes": [],
            "confidence": 0.5,
            "next_best_calls": "csv_force_decline",       # string, not list
            "unresolved_intent": {"q": "who is P003?"},   # dict, not list
        })
        with patch.object(backend, "_call_ollama", return_value=llm_resp):
            response = asyncio.run(backend.compose(request))
        assert response.next_best_calls == []
        assert response.unresolved_intent == []

    def test_compose_coerces_non_string_entries_to_str(self):
        """LLM emits valid lists with non-string entries (numbers,
        booleans, dicts) — each entry is str()'d so the wire shape
        list[str] holds. Mirrors the [str(x) for x in ambiguity]
        coercion."""
        backend = OllamaBackend(tier="scout")
        request = OracleRequest(question="?", resolved_context={})
        llm_resp = json.dumps({
            "narrative": "n",
            "ambiguity_axes": [],
            "confidence": 0.5,
            "next_best_calls": [42, True, {"tool": "csv_force_decline"}],
            "unresolved_intent": [None, 1.5],
        })
        with patch.object(backend, "_call_ollama", return_value=llm_resp):
            response = asyncio.run(backend.compose(request))
        assert all(isinstance(x, str) for x in response.next_best_calls)
        assert all(isinstance(x, str) for x in response.unresolved_intent)
        assert "42" in response.next_best_calls
        assert "True" in response.next_best_calls

    def test_compose_missing_fields_default_to_empty(self):
        """LLM emits valid JSON with no next_best_calls or
        unresolved_intent keys — parser defaults both to []. Models
        that don't follow the schema strictly should not crash the
        layer."""
        backend = OllamaBackend(tier="scout")
        request = OracleRequest(question="?", resolved_context={})
        llm_resp = json.dumps({
            "narrative": "n",
            "ambiguity_axes": [],
            "confidence": 0.5,
            # both new fields absent
        })
        with patch.object(backend, "_call_ollama", return_value=llm_resp):
            response = asyncio.run(backend.compose(request))
        assert response.next_best_calls == []
        assert response.unresolved_intent == []

    def test_fallback_response_emits_empty_gap_reasoning(self):
        """When Ollama is unavailable the fallback path has no LLM in
        the loop — both gap-reasoning fields must be empty. Emitting
        anything else here would be a fabrication: the fallback is
        the structural signal that no LLM ran."""
        backend = OllamaBackend(tier="scout")
        ctx = {"csv_force_decline": {"peak": 100.0}}
        request = OracleRequest(question="?", resolved_context=ctx)
        # Both calls fail (non-JSON twice → fallback)
        with patch.object(backend, "_call_ollama", return_value="not json"):
            response = asyncio.run(backend.compose(request))
        assert response.meta.backend == "ollama-fallback"
        assert response.next_best_calls == []
        assert response.unresolved_intent == []


class TestNullBackendCooperationLoop:
    """NullBackend — no LLM in the loop, so gap-reasoning fields stay
    empty. Documents the parallel with PR1's substrate scan: the
    deterministic vault scan happens at the layer (NullBackend
    inherits substrate vision), but gap-reasoning is LLM-only and
    NullBackend correctly emits []."""

    def test_null_backend_emits_empty_gap_reasoning(self):
        backend = NullBackend()
        request = OracleRequest(question="?", resolved_context={})
        response = asyncio.run(backend.compose(request))
        assert response.next_best_calls == []
        assert response.unresolved_intent == []


class TestAskLocalOracleToolDescription:
    """The tool description on ask_local_oracle teaches hosted Claude
    the cooperation-loop pattern. PR2 expanded it; this test pins the
    contract so a future drift removes the loop teaching only when
    the ADR is amended."""

    def test_description_mentions_all_three_cooperation_fields(self):
        layer = LocalLLMLayer()
        defs = layer.tool_definitions
        assert len(defs) == 1
        desc = defs[0].description
        # All three cooperation-loop fields surfaced in the tool
        # description so hosted Claude can reason about each.
        assert "related_substrate" in desc
        assert "next_best_calls" in desc
        assert "unresolved_intent" in desc
        # The split rule: fetch-this-data vs ask-the-analyst.
        assert "analyst" in desc.lower()
        # The iteration framing — without this, hosted Claude reads
        # the response as a one-shot terminal answer.
        assert "iterate" in desc.lower() or "re-invoke" in desc.lower()
