#!/usr/bin/env python3
"""
Standalone Security Probe
=========================
Verifies the biosensor-to-LLM security pipeline WITHOUT network, MCP library,
or pytest. Runs as a standalone script -- no external dependencies beyond the
framework itself.

Tests gate bypass, adversarial inputs, multi-domain isolation, and audit
integrity:
  A. Middleware unit tests (CircuitBreaker, ConsentGate, CostGate, ParamValidator, TokenLedger)
  B. Router security pipeline (via MockChild, mocking the mcp module)
  C. Gate bypass attempts (adversarial tool names, domain injection)
  D. Consent UX fields (user_prompt + llm_instruction presence in gate responses)
  E. Edge cases (empty lists, None params, type coercion, SQL in params)
  F. Multi-domain isolation
  G. Audit log integrity

Exit code: 0 = all passed, 1 = failures detected.
"""

import asyncio
import sys
import tempfile
import time
import traceback

# -- Mock the MCP library so we can import router.py without installing it --
import types
from pathlib import Path


def _make_mcp_mock():
    mcp = types.ModuleType("mcp")
    mcp_server = types.ModuleType("mcp.server")
    mcp_types = types.ModuleType("mcp.types")
    mcp_server_stdio = types.ModuleType("mcp.server.stdio")

    class TextContent:
        def __init__(self, type, text): self.type = type; self.text = text
    class Tool:
        def __init__(self, name, description, inputSchema): self.name = name
    class Server:
        def __init__(self, name): self.name = name; self._ltools = None; self._ctool = None
        def list_tools(self): return lambda f: setattr(self, '_ltools', f) or f
        def call_tool(self): return lambda f: setattr(self, '_ctool', f) or f
        async def run(self, *a): pass

    mcp_types.TextContent = TextContent
    mcp_types.Tool = Tool
    mcp_server.Server = Server
    sys.modules["mcp"] = mcp
    sys.modules["mcp.server"] = mcp_server
    sys.modules["mcp.types"] = mcp_types
    sys.modules["mcp.server.stdio"] = mcp_server_stdio

_make_mcp_mock()

# -- Now import the real framework --
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tailor.framework.audit import _loads
from tailor.framework.cost import CostGate, TokenLedger, estimate_tokens
from tailor.framework.interfaces import (
    ChildMCP,
    CostEstimate,
    ToolDefinition,
    ValidationSchema,
)
from tailor.framework.router import RouterMCP
from tailor.framework.security import (
    CircuitBreaker,
    ConsentGate,
    ParamValidator,
)

# ===============================================================
# TEST INFRASTRUCTURE
# ===============================================================

passed = failed = 0

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        print(f"  PASS  {name}")
        passed += 1
    else:
        print(f"  FAIL  {name}" + (f"\n        -> {detail}" if detail else ""))
        failed += 1

def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

_loop = asyncio.new_event_loop()

def run(coro):
    return _loop.run_until_complete(coro)


# ===============================================================
# MOCK CHILD
# ===============================================================

class MockChild(ChildMCP):
    def __init__(self, domain_name="test", cost=100):
        self._domain = domain_name
        self._cost = cost
        self.execute_count = 0

    @property
    def domain(self): return self._domain
    @property
    def display_name(self): return f"Test ({self._domain})"
    @property
    def tool_definitions(self):
        return [
            ToolDefinition(f"{self._domain}_free",      1, "Free tool",      {"val": {"type":"integer","description":"v","required":True}}),
            ToolDefinition(f"{self._domain}_gated",     2, "Gated tool",     {"val": {"type":"integer","description":"v","required":True}}),
            ToolDefinition(f"{self._domain}_expensive", 3, "Expensive tool", {"val": {"type":"integer","description":"v","required":True}}),
        ]
    @property
    def param_schemas(self):
        base = {"val": ValidationSchema(type=int, min=1, required=True)}
        return {f"{self._domain}_{t}": base for t in ("free","gated","expensive")}

    async def execute(self, tool_name, params):
        self.execute_count += 1
        return {"result": "ok", "tool": tool_name, "params": params}

    async def estimate_cost(self, tool_name, params):
        return CostEstimate(
            tokens=self._cost,
            has_cheaper_alternative=self._cost > 10_000,
            alternative_tokens=self._cost // 10,
            alternative_description="Downsampled",
        )

    def purge_cache(self, *, force=False):
        return {"rows_purged": 0, "tables_touched": [], "preserved": []}


class FailingChild(MockChild):
    async def execute(self, tool_name, params):
        raise RuntimeError("Simulated upstream failure")


# ===============================================================
# A. MIDDLEWARE UNIT TESTS
# ===============================================================

section("A. Middleware -- CircuitBreaker")

cb = CircuitBreaker(threshold=3, reset_after=60)
ok, _ = cb.check("domain1")
check("starts closed", ok)

cb.record_failure("domain1"); cb.record_failure("domain1"); cb.record_failure("domain1")
ok, msg = cb.check("domain1")
check("trips after 3 failures", not ok and "Circuit open" in msg, msg)

ok2, _ = cb.check("domain2")
check("scoped per domain (domain2 still open)", ok2)

cb2 = CircuitBreaker(threshold=2, reset_after=0.05)
cb2.record_failure("x"); cb2.record_failure("x")
ok, _ = cb2.check("x"); check("tripped", not ok)
time.sleep(0.1)
ok, _ = cb2.check("x"); check("auto-resets after cooldown", ok)

cb3 = CircuitBreaker(threshold=3)
cb3.record_failure("y"); cb3.record_failure("y"); cb3.record_success("y"); cb3.record_failure("y")
ok, _ = cb3.check("y")
check("success resets failure window", ok)


section("B. Middleware -- ConsentGate")

gate = ConsentGate()
ok, err = gate.check("running")
check("default denied", not ok and "CONSENT_REQUIRED" in err)

gate.approve("running")
ok, _ = gate.check("running")
check("approve grants access", ok)

ok2, _ = gate.check("cgm")
check("per-domain scoping (cgm not approved)", not ok2)

gate.approve("sleep")
check("approved_domains list", set(gate.approved_domains) == {"running", "sleep"})


section("C. Middleware -- CostGate")

cg = CostGate(threshold=35_000)
check("below threshold passes", not cg.should_gate(34_999))
check("exactly at threshold gates", cg.should_gate(35_000))
check("above threshold gates", cg.should_gate(100_000))
check("custom threshold", CostGate(10_000).should_gate(9_999) is False and CostGate(10_000).should_gate(10_000) is True)


section("D. Middleware -- ParamValidator")

pv = ParamValidator

schema = {"n": ValidationSchema(type=int, min=1, max=100, required=True)}
ok, _, c = pv.validate(schema, {"n": 50}); check("valid int", ok and c["n"] == 50)
ok, err, _ = pv.validate(schema, {}); check("required missing", not ok and "required" in err.lower())
ok, err, _ = pv.validate(schema, {"n": 0}); check("int below min", not ok)
ok, err, _ = pv.validate(schema, {"n": 101}); check("int above max", not ok)
ok, _, c = pv.validate(schema, {"n": "42"}); check("string coerced to int", ok and c["n"] == 42)

ds = {"date": ValidationSchema(type=str, pattern=r"^\d{4}-\d{2}-\d{2}$")}
ok1, _, _ = pv.validate(ds, {"date": "2026-04-09"}); check("valid date pattern", ok1)
ok2, _, _ = pv.validate(ds, {"date": "not-a-date"}); check("invalid date pattern rejected", not ok2)

ls = {"ids": ValidationSchema(type=list, min_len=2, max_len=5, required=True)}
ok, _, _ = pv.validate(ls, {"ids": [1,2,3]}); check("valid list", ok)
ok, _, _ = pv.validate(ls, {"ids": [1]}); check("list too short rejected", not ok)
ok, _, _ = pv.validate(ls, {"ids": list(range(10))}); check("list too long rejected", not ok)

avs = {"streams": ValidationSchema(type=list, allowed_values=["hr","pace","gps"])}
ok, _, _ = pv.validate(avs, {"streams": ["hr","pace"]}); check("allowed values pass", ok)
ok, err, _ = pv.validate(avs, {"streams": ["hr","INVALID"]}); check("disallowed value rejected", not ok and "INVALID" in err)

# Extra params should pass through
ok, _, c = pv.validate(schema, {"n": 5, "extra": "whatever"})
check("extra params passed through", ok and c["extra"] == "whatever")

# Empty schema -- anything passes
ok, _, c = pv.validate({}, {"anything": "value"})
check("empty schema passes anything", ok)


section("E. Middleware -- TokenLedger + estimate_tokens")

ledger = TokenLedger()
ledger.add("running", "report", 800)
ledger.add("cgm", "glucose", 400)
check("total tokens", ledger.total == 1200)
check("by_domain", ledger.by_domain() == {"running": 800, "cgm": 400})
s = ledger.summary()
check("summary call_count", s["call_count"] == 2)

check("estimate_tokens dict", estimate_tokens({"key": "value"}) > 0)
small = estimate_tokens({"a": 1})
large = estimate_tokens({"data": list(range(1000))})
check("larger data -> more tokens", large > small)


# ===============================================================
# F. ROUTER -- SECURITY PIPELINE
# ===============================================================

section("F. Router -- Basic Dispatch")

with tempfile.TemporaryDirectory() as tmpdir:
    router = RouterMCP("test", Path(tmpdir))
    router.register_child(MockChild("alpha"))

    # Unknown tool
    r = run(router._dispatch("nonexistent", {}))
    d = _loads(r[0].text)
    check("unknown tool returns error", "error" in d and "Unknown" in d["error"])

    # Tier 1 -- free tool executes
    r = run(router._dispatch("alpha_free", {"val": 5}))
    d = _loads(r[0].text)
    check("tier1 free tool executes", d.get("result") == "ok")
    check("tier1 meta attached", "_meta" in d and d["_meta"]["tier"] == 1)

    # Provenance stamps: every result carries enough metadata to be
    # traceable back to the code version that produced it. Minimum bar
    # for anything that might end up in a paper.
    _m = d.get("_meta", {})
    check("provenance: package_version stamped", "package_version" in _m,
          f"_meta keys: {list(_m.keys())}")
    check("provenance: tool_name stamped", _m.get("tool_name") == "alpha_free",
          f"got tool_name={_m.get('tool_name')}")
    check("provenance: called_at stamped", "called_at" in _m,
          f"_meta keys: {list(_m.keys())}")

    # Tier 1 -- bad param
    r = run(router._dispatch("alpha_free", {}))
    d = _loads(r[0].text)
    check("tier1 missing required param rejected", "error" in d)

    # Tier 1 -- param below min
    r = run(router._dispatch("alpha_free", {"val": 0}))
    d = _loads(r[0].text)
    check("tier1 param below min rejected", "error" in d)
    router.close()


section("G. Router -- Consent Gate (Tier 2)")

with tempfile.TemporaryDirectory() as tmpdir:
    router = RouterMCP("test", Path(tmpdir))
    router.register_child(MockChild("alpha"))

    # Tier 2 blocked without consent
    r = run(router._dispatch("alpha_gated", {"val": 1}))
    d = _loads(r[0].text)
    check("tier2 blocked without consent", d.get("gate") == "consent_required")
    check("gate includes domain", d.get("domain") == "alpha")
    check("gate includes display_name", "display_name" in d)
    check("gate includes tool_requested", d.get("tool_requested") == "alpha_gated")

    # Check for UX fields (user_prompt + llm_instruction)
    has_user_prompt = "user_prompt" in d
    has_llm_instr = "llm_instruction" in d
    check("gate includes user_prompt for LLM UX", has_user_prompt,
          "Missing 'user_prompt' -- LLM has no text to show user for consent")
    check("gate includes llm_instruction to prevent auto-approve", has_llm_instr,
          "Missing 'llm_instruction' -- LLM may auto-approve without asking user")
    if has_llm_instr:
        instr = d["llm_instruction"]
        if isinstance(instr, dict):
            check("llm_instruction is structured (must_do/must_not_do)",
                  "must_do" in instr and "must_not_do" in instr,
                  f"Got keys: {list(instr.keys())}")
            check("llm_instruction forbids bundling",
                  any("Bundle" in s for s in instr.get("must_not_do", [])),
                  f"must_not_do: {instr.get('must_not_do')}")
        else:
            check("llm_instruction says STOP", "STOP" in instr,
                  f"Got: {instr}")

    # Approve and retry
    run(router._dispatch("approve_consent_alpha", {}))
    r = run(router._dispatch("alpha_gated", {"val": 1}))
    d = _loads(r[0].text)
    check("tier2 passes after consent", d.get("result") == "ok")
    router.close()

with tempfile.TemporaryDirectory() as tmpdir:
    router = RouterMCP("test", Path(tmpdir))
    router.register_child(MockChild("alpha"))
    router.register_child(MockChild("beta"))
    run(router._dispatch("approve_consent_alpha", {}))
    r1 = run(router._dispatch("alpha_gated", {"val": 1}))
    r2 = run(router._dispatch("beta_gated", {"val": 1}))
    check("consent alpha -> alpha passes", _loads(r1[0].text).get("result") == "ok")
    check("consent alpha -> beta still blocked", _loads(r2[0].text).get("gate") == "consent_required")

    # Approve unknown domain
    r = run(router._dispatch("approve_consent_UNKNOWN", {}))
    d = _loads(r[0].text)
    check("approve unknown domain returns error", "error" in d)
    router.close()


section("H. Router -- Cost Gate (Tier 3)")

with tempfile.TemporaryDirectory() as tmpdir:
    router = RouterMCP("test", Path(tmpdir), cost_threshold=35_000)
    router.register_child(MockChild("alpha", cost=1_000))
    run(router._dispatch("approve_consent_alpha", {}))

    # Cheap passes through
    r = run(router._dispatch("alpha_expensive", {"val": 1}))
    d = _loads(r[0].text)
    check("cheap tier3 passes cost gate", d.get("result") == "ok")
    router.close()

with tempfile.TemporaryDirectory() as tmpdir:
    router = RouterMCP("test", Path(tmpdir), cost_threshold=35_000)
    router.register_child(MockChild("alpha", cost=50_000))
    run(router._dispatch("approve_consent_alpha", {}))

    r = run(router._dispatch("alpha_expensive", {"val": 1}))
    d = _loads(r[0].text)
    check("expensive tier3 triggers cost gate", d.get("gate") == "cost_approval_required")
    check("cost gate shows full token count", d.get("options", {}).get("full", {}).get("tokens") == 50_000)
    check("cost gate offers downsampled alternative", "downsampled" in d.get("options", {}))

    # Check for UX fields
    has_user_prompt = "user_prompt" in d
    has_llm_instr = "llm_instruction" in d
    check("cost gate includes user_prompt", has_user_prompt,
          "Missing 'user_prompt' -- LLM has no text to show user for cost approval")
    check("cost gate includes llm_instruction", has_llm_instr,
          "Missing 'llm_instruction' -- LLM may auto-proceed without asking user")
    router.close()


section("I. Router -- Circuit Breaker Integration")

with tempfile.TemporaryDirectory() as tmpdir:
    router = RouterMCP("test", Path(tmpdir), circuit_threshold=2, circuit_reset=60)
    router.register_child(FailingChild("alpha"))

    run(router._dispatch("alpha_free", {"val": 1}))  # fail 1
    run(router._dispatch("alpha_free", {"val": 1}))  # fail 2 -> trips
    r = run(router._dispatch("alpha_free", {"val": 1}))  # should be blocked
    d = _loads(r[0].text)
    check("circuit trips after failures", "Circuit open" in d.get("error", ""), d.get("error"))
    router.close()


section("J. SECURITY -- Gate Bypass Attempts")

with tempfile.TemporaryDirectory() as tmpdir:
    router = RouterMCP("test", Path(tmpdir))
    router.register_child(MockChild("alpha"))

    # Attempt 1: tool name that looks like an approval
    r = run(router._dispatch("approve_consent_alpha_gated", {}))
    d = _loads(r[0].text)
    # Should fail (domain 'alpha_gated' doesn't exist)
    check("fake approve_consent_ rejected (unknown domain)", "error" in d,
          f"Got: {d}")

    # Attempt 2: empty tool name
    r = run(router._dispatch("", {}))
    d = _loads(r[0].text)
    check("empty tool name rejected", "error" in d or "Unknown" in str(d))

    # Attempt 3: SQL injection in string param
    # ParamValidator should pass it through (no DB query at validation layer)
    # but it should NOT break the validator
    inj_schema = {"label": ValidationSchema(type=str)}
    ok, err, c = ParamValidator.validate(inj_schema, {"label": "'; DROP TABLE audit_log; --"})
    check("SQL injection in string param doesn't crash validator", ok)
    check("SQL injection string preserved as-is (parameterized later)", "DROP TABLE" in c.get("label",""))

    # Attempt 4: extremely large int
    schema_big = {"val": ValidationSchema(type=int, min=1, required=True)}
    ok, _, c = ParamValidator.validate(schema_big, {"val": 10**100})
    check("very large integer handled without crash", ok)  # just checks no exception

    # Attempt 5: negative int as activity_id
    schema_neg = {"activity_id": ValidationSchema(type=int, min=1, required=True)}
    ok, err, _ = ParamValidator.validate(schema_neg, {"activity_id": -1})
    check("negative activity_id rejected", not ok)

    # Attempt 6: None value for required param
    ok, err, _ = ParamValidator.validate(schema_neg, {"activity_id": None})
    check("None for required param rejected", not ok)

    # Attempt 7: list injection -- try to pass a non-list for list param
    ls_schema = {"ids": ValidationSchema(type=list, required=True, min_len=1)}
    ok, err, _ = ParamValidator.validate(ls_schema, {"ids": "not-a-list"})
    check("string where list expected rejected", not ok)

    router.close()

with tempfile.TemporaryDirectory() as tmpdir:
    router = RouterMCP("bypass_test", Path(tmpdir))
    router.register_child(MockChild("alpha"))
    router.register_child(MockChild("beta"))
    # Approve beta, then try to call alpha_gated
    run(router._dispatch("approve_consent_beta", {}))
    r = run(router._dispatch("alpha_gated", {"val": 1}))
    d = _loads(r[0].text)
    check("approving beta does NOT unlock alpha (domain isolation)", d.get("gate") == "consent_required",
          f"Got: {d}")
    router.close()


section("K. Router -- Child Registration Safety")

with tempfile.TemporaryDirectory() as tmpdir:
    router = RouterMCP("test", Path(tmpdir))
    router.register_child(MockChild("alpha"))
    check("alpha registered", "alpha" in router.registered_domains)
    check("alpha tools registered", "alpha_free" in router.registered_tools)

    try:
        router.register_child(MockChild("alpha"))
        check("duplicate domain rejected", False, "Expected ValueError, got none")
    except ValueError:
        check("duplicate domain rejected", True)
    router.close()


section("L. Audit Log -- Writes on Every Call")

with tempfile.TemporaryDirectory() as tmpdir:
    import sqlite3
    router = RouterMCP("test", Path(tmpdir))
    router.register_child(MockChild("alpha"))
    run(router._dispatch("alpha_free", {"val": 5}))
    run(router._dispatch("alpha_gated", {"val": 5}))  # blocked by consent gate
    # A call with a study subject_id so we can verify scoping works.
    run(router._dispatch("alpha_free", {"val": 9, "subject_id": "P042"}))

    conn = sqlite3.connect(str(Path(tmpdir) / "audit.db"))
    rows = conn.execute(
        "SELECT tool_name, outcome, subject_id FROM audit_log ORDER BY id"
    ).fetchall()
    conn.close()

    check("tier1 success audited",
          any(r[0] == "alpha_free" and r[1] == "SUCCESS" for r in rows),
          f"rows: {rows}")
    check("consent block audited",
          any(r[0] == "alpha_gated" and r[1] == "CONSENT_BLOCKED" for r in rows),
          f"rows: {rows}")
    # Research-framing: subject_id threads through to the audit row, so
    # a study's analytical trace can be scoped to a participant/cohort.
    check("subject_id recorded on audit row",
          any(r[0] == "alpha_free" and r[2] == "P042" for r in rows),
          f"rows: {rows}")
    check("subject_id absent stays NULL",
          any(r[0] == "alpha_gated" and r[2] is None for r in rows),
          f"rows: {rows}")
    router.close()


# ===============================================================
# SUMMARY
# ===============================================================

total = passed + failed
print(f"\n{'='*60}")
print(f"  RESULTS: {passed}/{total} passed", end="")
if failed:
    print(f"  ({failed} FAILED)")
else:
    print("  -- ALL CLEAR")
print(f"{'='*60}\n")

sys.exit(0 if failed == 0 else 1)
