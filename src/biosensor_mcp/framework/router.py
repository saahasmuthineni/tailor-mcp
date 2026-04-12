"""
Biosensor-to-LLM Framework — Parent Router MCP
================================================
The router sits between Claude and all child MCPs.
It owns security, consent, cost gating, and audit.
Children register their tools; the router dispatches through
the security pipeline.

Architecture:
    Claude → Router (validate → circuit break → consent → cost → audit)
                ↓
           Child MCP (domain-specific execution)

Children register via register_child(). The router builds a unified
tool listing from all children and dispatches by tool name.
"""

import logging
import time
from pathlib import Path

from mcp.server import Server
from mcp.types import TextContent, Tool

from .interfaces import ChildMCP, CostEstimate, LLMInstruction, ToolDefinition
from .middleware import (
    JSON_BACKEND,
    AuditLog,
    CircuitBreaker,
    ConsentGate,
    CostGate,
    ParamValidator,
    TokenLedger,
    _dumps,
    estimate_tokens,
)

log = logging.getLogger("biosensor-mcp")


class RouterMCP:
    """
    Parent MCP that routes tool calls through security middleware to child MCPs.

    Usage:
        router = RouterMCP("my-server", data_dir=Path("~/.my-server/data"))
        router.register_child(RunningChild(config_dir, data_dir))
        router.register_child(CGMChild(config_dir, data_dir))  # future
        router.run()
    """

    def __init__(
        self,
        name: str,
        data_dir: Path,
        cost_threshold: int = 35_000,
        circuit_threshold: int = 3,
        circuit_reset: float = 300,
    ):
        self.name = name
        self.data_dir = data_dir
        data_dir.mkdir(parents=True, exist_ok=True)

        # Child registry
        self._children: dict[str, ChildMCP] = {}  # domain -> child
        self._tool_map: dict[str, tuple[ChildMCP, ToolDefinition]] = {}

        # Vault layer (framework-level reorientation tier; not a ChildMCP)
        # Tools go in _tool_map with child=None sentinel — dispatch redirects them.
        self._vault_layer = None

        # Middleware stack
        self._circuit = CircuitBreaker(
            threshold=circuit_threshold, reset_after=circuit_reset
        )
        self._consent = ConsentGate()
        self._cost_gate = CostGate(threshold=cost_threshold)
        self._audit = AuditLog(data_dir / "audit.db")
        self._ledger = TokenLedger()
        self._validator = ParamValidator()
        self._post_execute_hooks: list[callable] = []

        log.info(f"Router MCP '{name}' initialized (JSON backend: {JSON_BACKEND})")

    # ══════════════════════════════════════════════════════════
    # CHILD REGISTRATION
    # ══════════════════════════════════════════════════════════

    def register_child(self, child: ChildMCP):
        """
        Register a child MCP. Its tools become available to Claude.

        Raises ValueError if domain or tool names collide.
        """
        domain = child.domain
        if domain in self._children:
            raise ValueError(f"Domain '{domain}' already registered")

        self._children[domain] = child
        child._router = self

        for tool_def in child.tool_definitions:
            if tool_def.name in self._tool_map:
                existing = self._tool_map[tool_def.name][0].domain
                raise ValueError(
                    f"Tool '{tool_def.name}' already registered by domain '{existing}'"
                )
            self._tool_map[tool_def.name] = (child, tool_def)

        log.info(
            f"Registered child '{domain}' ({child.display_name}) "
            f"with {len(child.tool_definitions)} tools"
        )

    def register_post_execute_hook(self, hook: callable) -> None:
        """
        Register a callable that fires after every successful tool execution.

        Signature: hook(domain: str, tool_name: str, result: dict) -> None
        Errors are swallowed — a hook failure never breaks the MCP session.
        """
        self._post_execute_hooks.append(hook)

    def register_vault_layer(self, vault_layer) -> None:
        """
        Register the framework-level vault layer (reorientation tier).

        Vault tools are added to _tool_map with a None-child sentinel.
        Dispatch redirects them to _dispatch_vault() — a stripped-down
        pipeline (param validation + audit + execute) that skips consent,
        cost, and circuit breaker gates.  No consent approval tools are
        generated for the vault since it's not a biosensor domain.
        """
        if self._vault_layer is not None:
            raise ValueError("Vault layer already registered")

        self._vault_layer = vault_layer
        vault_layer._router = self  # Needed for backfill's dispatch_internal calls

        for tool_def in vault_layer.tool_definitions:
            if tool_def.name in self._tool_map:
                existing = self._tool_map[tool_def.name][0]
                existing_domain = existing.domain if existing is not None else "vault"
                raise ValueError(
                    f"Tool '{tool_def.name}' already registered by '{existing_domain}'"
                )
            # None sentinel marks this as a vault-layer tool
            self._tool_map[tool_def.name] = (None, tool_def)

        log.info(
            f"Registered vault layer with {len(vault_layer.tool_definitions)} tools"
        )

    @property
    def registered_domains(self) -> list[str]:
        return list(self._children.keys())

    @property
    def registered_tools(self) -> list[str]:
        return list(self._tool_map.keys())

    # ══════════════════════════════════════════════════════════
    # MCP SERVER
    # ══════════════════════════════════════════════════════════

    def create_server(self) -> Server:
        """Build the MCP Server with unified tool listing and dispatch."""
        app = Server(self.name)
        router = self  # capture for closures

        @app.list_tools()
        async def list_tools() -> list[Tool]:
            tools = []

            # Dynamic consent tools (approve + revoke, one pair per domain)
            for domain, child in router._children.items():
                tools.append(
                    Tool(
                        name=f"approve_consent_{domain}",
                        description=(
                            f"Approve biometric data access for {child.display_name} "
                            f"data in this session. Required before using gated tools "
                            f"in the '{domain}' domain."
                        ),
                        inputSchema={
                            "type": "object",
                            "properties": {},
                            "required": [],
                        },
                    )
                )
                tools.append(
                    Tool(
                        name=f"revoke_consent_{domain}",
                        description=(
                            f"Revoke biometric data access for {child.display_name} "
                            f"data. After revocation, gated tools in '{domain}' will "
                            f"require fresh consent."
                        ),
                        inputSchema={
                            "type": "object",
                            "properties": {},
                            "required": [],
                        },
                    )
                )

            # Tools from all children
            for tool_name, (_child, tool_def) in router._tool_map.items():
                schema: dict = {
                    "type": "object",
                    "properties": {},
                    "required": [],
                }
                for pname, pinfo in tool_def.params.items():
                    schema["properties"][pname] = {
                        "type": pinfo["type"],
                        "description": pinfo["description"],
                    }
                    if pinfo.get("required"):
                        schema["required"].append(pname)

                tools.append(
                    Tool(
                        name=tool_name,
                        description=tool_def.description,
                        inputSchema=schema,
                    )
                )

            return tools

        @app.call_tool()
        async def call_tool(name: str, arguments: dict) -> list[TextContent]:
            return await router._dispatch(name, arguments)

        return app

    # ══════════════════════════════════════════════════════════
    # DISPATCH PIPELINE
    # ══════════════════════════════════════════════════════════

    async def _dispatch(
        self, tool_name: str, arguments: dict
    ) -> list[TextContent]:
        start = time.time()

        # ── Consent tools (approve/revoke — special dynamic, no gates) ──
        if tool_name.startswith("approve_consent_"):
            return self._handle_consent_approval(tool_name)
        if tool_name.startswith("revoke_consent_"):
            return self._handle_consent_revocation(tool_name)

        # ── Resolve child ──
        if tool_name not in self._tool_map:
            return [
                TextContent(
                    type="text", text=_dumps({"error": f"Unknown tool: {tool_name}"})
                )
            ]

        child, tool_def = self._tool_map[tool_name]

        # ── Vault layer fast-path (framework-level; skip consent/cost/circuit) ──
        if child is None:
            return await self._dispatch_vault(tool_name, tool_def, arguments, start)

        domain = child.domain
        tier = tool_def.tier

        # ── LAYER 1: Param validation ──
        schemas = child.param_schemas.get(tool_name, {})
        ok, err, cleaned = self._validator.validate(schemas, arguments)
        if not ok:
            self._audit.record(
                domain, tool_name, tier, arguments, 0, "PARAM_INVALID", 0, err
            )
            return [TextContent(type="text", text=_dumps({"error": err}))]

        # ── LAYER 2: Circuit breaker (scoped per domain) ──
        cb_ok, cb_err = self._circuit.check(domain)
        if not cb_ok:
            self._audit.record(
                domain, tool_name, tier, cleaned, 0, "CIRCUIT_OPEN", 0, cb_err
            )
            return [TextContent(type="text", text=_dumps({"error": cb_err}))]

        # ── LAYER 3: Consent gate (per-domain, Tier 2+) ──
        if tier >= 2:
            consent_ok, _ = self._consent.check(domain)
            if not consent_ok:
                self._audit.record(
                    domain, tool_name, tier, cleaned, 0, "CONSENT_BLOCKED", 0
                )
                ci = child.consent_info
                scope = ci.scope

                # Dynamic scope: what THIS call needs vs. what the SESSION allows
                data_this_call = child.data_types_for_tool(tool_name, cleaned)
                data_session = ci.data_types

                this_call_list = ", ".join(data_this_call)
                session_list = ", ".join(data_session)

                # Build user_prompt with explicit scope separation
                if data_this_call == data_session:
                    user_prompt = (
                        f"This tool needs access to your {session_list} data "
                        f"for {ci.purpose}. Approval lasts {scope.duration_human}. "
                        f"Approve?"
                    )
                else:
                    user_prompt = (
                        f"This specific call needs: {this_call_list}. "
                        f"If you approve, the session will also allow future calls "
                        f"to access: {session_list} — {scope.duration_human}. "
                        f"Approve?"
                    )

                # Structured LLM instruction — each bullet individually checkable
                llm_instr = LLMInstruction(
                    must_do=[
                        "Present 'user_prompt' as the SOLE question in your next message",
                        f"State that approval lasts {scope.duration_human} in your own words before asking",
                        "If data_requested_this_call differs from data_categories_session, disclose the gap",
                    ],
                    must_not_do=[
                        "Auto-approve or assume consent from prior context",
                        "Bundle other questions, follow-up actions, or suggestions in the same turn",
                        "Paraphrase user_prompt in a way that hides scope or reversibility",
                        "Proceed on ambiguous replies — if unclear, re-ask before calling approve tool",
                    ],
                    on_ambiguous_reply=(
                        "Re-ask with a single yes/no question. Do not call "
                        f"approve_consent_{domain} until the user's intent is unambiguous."
                    ),
                )

                return [
                    TextContent(
                        type="text",
                        text=_dumps(
                            {
                                "gate": "consent_required",
                                "domain": domain,
                                "display_name": child.display_name,
                                "data_requested_this_call": data_this_call,
                                "data_categories_session": data_session,
                                "purpose": ci.purpose,
                                "scope": scope.to_dict(),
                                "user_prompt": user_prompt,
                                "llm_instruction": llm_instr.to_dict(),
                                "approve_tool": f"approve_consent_{domain}",
                                "revoke_tool": f"revoke_consent_{domain}",
                                "tool_requested": tool_name,
                                "tier": tier,
                            }
                        ),
                    )
                ]

        # ── LAYER 4: Cost pre-estimation + gate (Tier 3) ──
        if tier >= 3:
            try:
                cost_est = await child.estimate_cost(tool_name, cleaned)
            except Exception as e:
                cost_est = CostEstimate(tokens=0)
                log.warning(f"Cost estimation failed for {tool_name}: {e}")

            if self._cost_gate.should_gate(cost_est.tokens):
                duration_ms = int((time.time() - start) * 1000)
                self._audit.record(
                    domain,
                    tool_name,
                    tier,
                    cleaned,
                    cost_est.tokens,
                    "COST_GATE_TRIGGERED",
                    duration_ms,
                )

                # Human-relatable cost context
                cost_ctx = self._cost_gate.humanize(
                    cost_est.tokens, cost_est.alternative_tokens
                )

                options: dict = {
                    "full": {
                        "tokens": cost_est.tokens,
                        "description": "Full resolution with precision reduction",
                    },
                }
                if cost_est.has_cheaper_alternative:
                    options["downsampled"] = {
                        "tokens": cost_est.alternative_tokens,
                        "description": cost_est.alternative_description,
                    }
                    action = "Reply 'full' or 'downsampled' to proceed."
                    user_prompt = (
                        f"This request will use ~{cost_est.tokens:,} tokens — "
                        f"{cost_ctx['relative_to_typical']} "
                        f"(full) or ~{cost_est.alternative_tokens:,} tokens "
                        f"(downsampled, {cost_ctx.get('relative_to_cheaper_pct', 'cheaper')}). "
                        f"Which would you like?"
                    )
                else:
                    action = "Reply 'proceed' to continue."
                    user_prompt = (
                        f"This request will use ~{cost_est.tokens:,} tokens "
                        f"({cost_ctx['relative_to_typical']}). Proceed?"
                    )

                # Structured LLM instruction for cost gate
                cost_llm_instr = LLMInstruction(
                    must_do=[
                        "Present 'user_prompt' as the SOLE question in your next message",
                        "Include at least one human-relatable comparison from cost_context (not raw tokens alone)",
                        "Present all options from 'options' with their descriptions",
                    ],
                    must_not_do=[
                        "Auto-select an option",
                        "Present raw token count without a relatable anchor",
                        "Bundle other questions or suggestions in the same turn",
                    ],
                    on_ambiguous_reply=(
                        "Re-ask: 'Would you like full resolution or downsampled?' "
                        "Do not proceed until the user's choice is explicit."
                    ),
                )

                gate_response: dict = {
                    "gate": "cost_approval_required",
                    "domain": domain,
                    "tool_requested": tool_name,
                    "options": options,
                    "cost_context": cost_ctx,
                    "action": action,
                    "user_prompt": user_prompt,
                    "llm_instruction": cost_llm_instr.to_dict(),
                }

                return [TextContent(type="text", text=_dumps(gate_response))]

        # ── LAYER 5: Execute via child ──
        try:
            result = await child.execute(tool_name, cleaned)

            tokens = estimate_tokens(result)
            duration_ms = int((time.time() - start) * 1000)

            self._circuit.record_success(domain)
            self._ledger.add(domain, tool_name, tokens)
            self._audit.record(
                domain, tool_name, tier, cleaned, tokens, "SUCCESS", duration_ms
            )

            # ── Post-execute hooks (e.g. VaultWriter) ──
            for hook in self._post_execute_hooks:
                try:
                    hook(domain, tool_name, result)
                except Exception as _hook_exc:
                    log.warning(f"Post-execute hook failed silently: {_hook_exc}")

            # Attach metadata to response
            if isinstance(result, dict):
                result["_meta"] = {
                    "tokens_this_call": tokens,
                    "session_total_tokens": self._ledger.total,
                    "domain": domain,
                    "tier": tier,
                }

            return [TextContent(type="text", text=_dumps(result))]

        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            self._circuit.record_failure(domain)
            self._audit.record(
                domain, tool_name, tier, cleaned, 0, "ERROR", duration_ms, str(e)
            )
            log.error(f"Tool {tool_name} failed: {e}", exc_info=True)
            return [TextContent(type="text", text=_dumps({"error": str(e)}))]

    # ══════════════════════════════════════════════════════════
    # VAULT DISPATCH (framework-level, skips biosensor gates)
    # ══════════════════════════════════════════════════════════

    async def _dispatch_vault(
        self,
        tool_name: str,
        tool_def: ToolDefinition,
        arguments: dict,
        start: float,
    ) -> list[TextContent]:
        """
        Dispatch a vault-layer tool.  Stripped-down pipeline:

            param validation → execute → audit

        Skipped by design:
            - Circuit breaker (local SQLite + filesystem, not external API)
            - Consent gate (metadata, not biometric data)
            - Cost gate (always small, Tier 1)
            - Post-execute hooks (vault writes should not trigger recursive
              vault writes)
        """
        tier = tool_def.tier

        # ── LAYER 1: Param validation ──
        schemas = self._vault_layer.param_schemas.get(tool_name, {})
        ok, err, cleaned = self._validator.validate(schemas, arguments)
        if not ok:
            self._audit.record(
                "vault", tool_name, tier, arguments, 0, "PARAM_INVALID", 0, err
            )
            return [TextContent(type="text", text=_dumps({"error": err}))]

        # ── EXECUTE ──
        try:
            result = await self._vault_layer.execute(tool_name, cleaned)
            tokens = estimate_tokens(result)
            duration_ms = int((time.time() - start) * 1000)

            self._ledger.add("vault", tool_name, tokens)
            self._audit.record(
                "vault", tool_name, tier, cleaned, tokens, "SUCCESS", duration_ms
            )

            if isinstance(result, dict):
                result["_meta"] = {
                    "tokens_this_call": tokens,
                    "session_total_tokens": self._ledger.total,
                    "domain": "vault",
                    "tier": tier,
                }

            return [TextContent(type="text", text=_dumps(result))]

        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            self._audit.record(
                "vault", tool_name, tier, cleaned, 0, "ERROR", duration_ms, str(e)
            )
            log.error(f"Vault tool {tool_name} failed: {e}", exc_info=True)
            return [TextContent(type="text", text=_dumps({"error": str(e)}))]

    # ══════════════════════════════════════════════════════════
    # INTERNAL DISPATCH (cross-child queries)
    # ══════════════════════════════════════════════════════════

    async def dispatch_internal(
        self, tool_name: str, params: dict
    ) -> dict:
        """
        Internal cross-child dispatch.  Full security pipeline, returns dict.

        Used by framework components (e.g. VaultLayer backfill) to query
        children through the Router rather than holding direct references.

        Differences from _dispatch():
        - Returns dict (not TextContent) for programmatic consumption
        - Post-execute hooks are skipped (caller manages side effects)
        - Audit records source as "INTERNAL" for traceability
        """
        start = time.time()

        if tool_name not in self._tool_map:
            return {"error": f"Unknown tool: {tool_name}"}

        child, tool_def = self._tool_map[tool_name]

        # Vault tools are LLM-facing only; not valid for internal dispatch
        if child is None:
            return {"error": f"Vault tool '{tool_name}' cannot be called internally"}

        domain = child.domain
        tier = tool_def.tier

        # ── LAYER 1: Param validation ──
        schemas = child.param_schemas.get(tool_name, {})
        ok, err, cleaned = self._validator.validate(schemas, params)
        if not ok:
            self._audit.record(
                domain, tool_name, tier, params, 0, "PARAM_INVALID_INTERNAL", 0, err
            )
            return {"error": err}

        # ── LAYER 2: Circuit breaker ──
        cb_ok, cb_err = self._circuit.check(domain)
        if not cb_ok:
            self._audit.record(
                domain, tool_name, tier, cleaned, 0, "CIRCUIT_OPEN_INTERNAL", 0, cb_err
            )
            return {"error": cb_err}

        # ── LAYER 3: Consent gate (Tier 2+) ──
        if tier >= 2:
            consent_ok, _ = self._consent.check(domain)
            if not consent_ok:
                self._audit.record(
                    domain, tool_name, tier, cleaned, 0, "CONSENT_BLOCKED_INTERNAL", 0
                )
                return {"error": f"Consent not approved for domain '{domain}'"}

        # ── LAYER 4: Cost gate (Tier 3) ──
        if tier >= 3:
            try:
                cost_est = await child.estimate_cost(tool_name, cleaned)
            except Exception as exc:
                # Mirror the logging in the public dispatch path — silent
                # failure here could let a Tier-3 call slip past the cost
                # gate with a synthetic 0-token estimate.
                cost_est = CostEstimate(tokens=0)
                log.warning(
                    f"Internal dispatch: cost estimation failed for {tool_name}: {exc}"
                )
            if self._cost_gate.should_gate(cost_est.tokens):
                self._audit.record(
                    domain, tool_name, tier, cleaned, cost_est.tokens,
                    "COST_GATE_INTERNAL", 0
                )
                return {"error": f"Cost gate: {cost_est.tokens} tokens exceeds threshold"}

        # ── LAYER 5: Execute ──
        try:
            result = await child.execute(tool_name, cleaned)
            tokens = estimate_tokens(result)
            duration_ms = int((time.time() - start) * 1000)

            self._circuit.record_success(domain)
            self._ledger.add(domain, tool_name, tokens)
            self._audit.record(
                domain, tool_name, tier, cleaned, tokens, "SUCCESS_INTERNAL", duration_ms
            )
            # No post-execute hooks — caller manages side effects
            return result

        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            self._circuit.record_failure(domain)
            self._audit.record(
                domain, tool_name, tier, cleaned, 0, "ERROR_INTERNAL", duration_ms, str(e)
            )
            log.error(f"Internal dispatch {tool_name} failed: {e}", exc_info=True)
            return {"error": str(e)}

    # ── Consent Handler ──

    def _handle_consent_approval(self, tool_name: str) -> list[TextContent]:
        domain = tool_name[len("approve_consent_"):]
        if domain not in self._children:
            return [
                TextContent(
                    type="text",
                    text=_dumps({"error": f"Unknown domain: {domain}"}),
                )
            ]
        self._consent.approve(domain)
        child = self._children[domain]
        self._audit.record(domain, tool_name, 0, {}, 0, "SUCCESS", 0)
        return [
            TextContent(
                type="text",
                text=_dumps(
                    {
                        "approved": True,
                        "domain": domain,
                        "display_name": child.display_name,
                        "message": (
                            f"Biometric data access approved for "
                            f"{child.display_name} this session. "
                            f"Gated tools in '{domain}' are now available."
                        ),
                    }
                ),
            )
        ]

    # ── Consent Revocation Handler ──

    def _handle_consent_revocation(self, tool_name: str) -> list[TextContent]:
        domain = tool_name[len("revoke_consent_"):]
        if domain not in self._children:
            return [
                TextContent(
                    type="text",
                    text=_dumps({"error": f"Unknown domain: {domain}"}),
                )
            ]
        was_approved = self._consent.revoke(domain)
        child = self._children[domain]
        self._audit.record(domain, tool_name, 0, {}, 0, "SUCCESS", 0)
        if was_approved:
            return [
                TextContent(
                    type="text",
                    text=_dumps(
                        {
                            "revoked": True,
                            "domain": domain,
                            "display_name": child.display_name,
                            "message": (
                                f"Biometric data access revoked for "
                                f"{child.display_name}. Gated tools in "
                                f"'{domain}' will require fresh consent."
                            ),
                        }
                    ),
                )
            ]
        return [
            TextContent(
                type="text",
                text=_dumps(
                    {
                        "revoked": False,
                        "domain": domain,
                        "message": (
                            f"No active consent for '{domain}' to revoke."
                        ),
                    }
                ),
            )
        ]

    # ══════════════════════════════════════════════════════════
    # SERVER LIFECYCLE
    # ══════════════════════════════════════════════════════════

    def close(self):
        """Release resources (SQLite connections). Required on Windows to release file locks."""
        self._audit.close()
        if self._vault_layer is not None:
            self._vault_layer.close()

    def run(self):
        """Start the MCP server via stdio transport."""
        import asyncio

        from mcp.server.stdio import stdio_server

        server = self.create_server()

        async def main():
            async with stdio_server() as (read_stream, write_stream):
                await server.run(read_stream, write_stream)

        try:
            asyncio.run(main())
        finally:
            self.close()  # Release SQLite WAL locks (required on Windows)
