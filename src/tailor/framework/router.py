"""
Biosensor-to-LLM Framework — Parent Router MCP
================================================
The router sits between the LLM client (Claude Desktop, Claude API,
any MCP-speaking agent) and all registered child MCPs. It owns the
cross-cutting concerns that let a research group reason about what
an LLM analyst saw, when, with what scope, and under what gate —
without trusting the LLM to enforce those rules itself.

Architecture:
    LLM client → Router (validate → circuit break → consent → cost
                         → execute → PHI-scrub → audit)
                    ↓
               Child MCP (domain-specific execution)

Children register via register_child(). The router builds a unified
tool listing from all children and dispatches by tool name.

Every successful result that leaves the router carries a ``_meta``
block stamped with the package version, the tool name, and a UTC
timestamp. Combined with the audit log, this gives any downstream
consumer enough information to trace a result back to the exact code
version and moment that produced it — the minimum bar for an analysis
that might end up in a paper.
"""

import logging
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from mcp.server import Server
from mcp.types import TextContent, Tool

import tailor

from .audit import JSON_BACKEND, AuditLog, _dumps
from .cost import CostGate, TokenLedger, estimate_tokens
from .interfaces import ChildMCP, LLMInstruction, ToolDefinition
from .security import (
    CircuitBreaker,
    ConsentGate,
    OperatorActionRequired,
    ParamValidator,
    PHIScrubber,
)

log = logging.getLogger("tailor")


def _coerce_subject_id(params: object) -> str | None:
    """
    Extract an optional ``subject_id`` from a params dict for audit-log
    scoping. Accepts str/int (common in research identifiers); anything
    else is treated as absent. Returning None means "no scope" — callers
    pass None through to ``AuditLog.record(subject_id=...)``.
    """
    if not isinstance(params, dict):
        return None
    raw = params.get("subject_id")
    if raw is None:
        return None
    if isinstance(raw, (str, int)):
        return str(raw)
    return None


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

        # Local-LLM layer (framework-level guardian; not a ChildMCP).
        # See ADR 0022. Tools also use the (None, tool_def) sentinel; the
        # _framework_layer_owner dict disambiguates vault vs local_llm so
        # _dispatch can route to the right stripped-down pipeline.
        self._local_llm_layer = None
        # Setup-help layer (framework-level recipient diagnostic; not a
        # ChildMCP). Registered conditionally by __main__.cmd_serve when
        # no demo scaffold is present in user_config.json. Same
        # (None, tool_def) sentinel + _framework_layer_owner pattern.
        self._setup_help_layer = None
        self._framework_layer_owner: dict[str, str] = {}

        # Middleware stack
        self._circuit = CircuitBreaker(
            threshold=circuit_threshold, reset_after=circuit_reset
        )
        self._consent = ConsentGate()
        self._cost_gate = CostGate(threshold=cost_threshold)
        # PHI scrubbing seam. Ships as a no-op; institutions swap in a
        # subclass that drops/hashes identifying fields on a per-child
        # basis once their policy is defined. See framework.security.PHIScrubber.
        self._phi_scrubber = PHIScrubber()
        self._audit = AuditLog(data_dir / "audit.db")
        self._ledger = TokenLedger()
        self._validator = ParamValidator()
        self._post_execute_hooks: list[Callable] = []

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

    def register_post_execute_hook(self, hook: Callable) -> None:
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
            self._framework_layer_owner[tool_def.name] = "vault"

        log.info(
            f"Registered vault layer with {len(vault_layer.tool_definitions)} tools"
        )

    def register_local_llm_layer(self, local_llm_layer) -> None:
        """
        Register the framework-level local-LLM guardian layer (per ADR 0022).

        Local-LLM tools are added to ``_tool_map`` with a None-child sentinel
        (same pattern as vault). Dispatch redirects them to
        ``_dispatch_local_llm()`` — a stripped-down pipeline (param
        validation + execute + audit) that skips consent, cost, circuit
        breaker, PHI scrub, and post-execute hooks.

        The ``_framework_layer_owner`` dict disambiguates vault vs local_llm
        in dispatch so each framework-tier layer gets its own
        purpose-specific pipeline.
        """
        if self._local_llm_layer is not None:
            raise ValueError("Local-LLM layer already registered")

        self._local_llm_layer = local_llm_layer
        local_llm_layer._router = self

        for tool_def in local_llm_layer.tool_definitions:
            if tool_def.name in self._tool_map:
                existing = self._tool_map[tool_def.name][0]
                if existing is not None:
                    existing_domain = existing.domain
                else:
                    existing_domain = self._framework_layer_owner.get(
                        tool_def.name, "framework"
                    )
                raise ValueError(
                    f"Tool '{tool_def.name}' already registered by '{existing_domain}'"
                )
            self._tool_map[tool_def.name] = (None, tool_def)
            self._framework_layer_owner[tool_def.name] = "local_llm"

        backend = local_llm_layer.backend
        log.info(
            f"Registered local-LLM layer "
            f"(backend={backend.backend_id}, tier={backend.tier}, "
            f"model={backend.model_id}) "
            f"with {len(local_llm_layer.tool_definitions)} tools"
        )

    def register_setup_help_layer(self, setup_help_layer) -> None:
        """
        Register the framework-level setup-help layer (recipient diagnostic).

        Tools use the same ``(None, tool_def)`` sentinel as vault and
        local_llm; ``_framework_layer_owner["tailor_setup_help"]`` is
        set to ``"setup_help"`` so ``_dispatch`` routes to
        ``_dispatch_setup_help()`` — a stripped-down pipeline (param
        validation + execute + audit) that skips consent, cost, circuit
        breaker, PHI scrub, and post-execute hooks.

        Conditionally registered: only when ``__main__.cmd_serve``
        detects no ``force_csv`` / ``emg_csv`` / ``csv_dir`` /
        ``vault_path`` blocks in ``user_config.json``. When the demo
        scaffold IS installed this layer is never constructed, so the
        tool does not appear on ``tools/list``.
        """
        if self._setup_help_layer is not None:
            raise ValueError("Setup-help layer already registered")

        self._setup_help_layer = setup_help_layer
        setup_help_layer._router = self

        for tool_def in setup_help_layer.tool_definitions:
            if tool_def.name in self._tool_map:
                existing = self._tool_map[tool_def.name][0]
                if existing is not None:
                    existing_domain = existing.domain
                else:
                    existing_domain = self._framework_layer_owner.get(
                        tool_def.name, "framework"
                    )
                raise ValueError(
                    f"Tool '{tool_def.name}' already registered by '{existing_domain}'"
                )
            self._tool_map[tool_def.name] = (None, tool_def)
            self._framework_layer_owner[tool_def.name] = "setup_help"

        log.info(
            f"Registered setup-help layer with "
            f"{len(setup_help_layer.tool_definitions)} tools"
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
                    # Defensive get on `description` so a future ToolDefinition
                    # that ships a param without a description does NOT take
                    # down the whole `tools/list` response with a KeyError.
                    # The MCP SDK tolerates an empty-string description; a
                    # silent param is a worse failure than an unhelpful one.
                    schema["properties"][pname] = {
                        "type": pinfo["type"],
                        "description": pinfo.get("description", ""),
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
            return self._handle_consent_revocation(tool_name, arguments)

        # ── Resolve child ──
        if tool_name not in self._tool_map:
            return [
                TextContent(
                    type="text", text=_dumps({"error": f"Unknown tool: {tool_name}"})
                )
            ]

        child, tool_def = self._tool_map[tool_name]

        # ── Framework-tier layers fast-path (skip consent/cost/circuit) ──
        # The owner dict disambiguates vault vs local_llm; both use the
        # (None, tool_def) sentinel in _tool_map but route to different
        # purpose-specific pipelines. A future third framework-tier
        # layer must register its owner explicitly; an unrecognized
        # owner fails loudly rather than silently routing to a wrong
        # pipeline (mcp-protocol-auditor BORDER NOTE on ADR 0022).
        if child is None:
            owner = self._framework_layer_owner.get(tool_name)
            if owner == "vault":
                return await self._dispatch_vault(
                    tool_name, tool_def, arguments, start,
                )
            if owner == "local_llm":
                return await self._dispatch_local_llm(
                    tool_name, tool_def, arguments, start,
                )
            if owner == "setup_help":
                return await self._dispatch_setup_help(
                    tool_name, tool_def, arguments, start,
                )
            log.error(
                f"Framework-tier tool '{tool_name}' has no registered "
                f"layer owner (got {owner!r}); refusing to silently "
                f"route. This is a registration bug — a new "
                f"framework-tier layer was added without populating "
                f"_framework_layer_owner."
            )
            return [TextContent(type="text", text=_dumps({
                "error": (
                    f"Framework-tier tool '{tool_name}' has no registered "
                    f"layer owner. This is a server configuration error."
                )
            }))]

        domain = child.domain
        tier = tool_def.tier

        # Extract optional study subject_id so every audit row along this
        # dispatch path can be scoped to a participant/cohort. Pre-validation
        # we read from raw arguments; post-validation from cleaned (which
        # ParamValidator preserves extra keys through).
        subject_id = _coerce_subject_id(arguments)

        # ── LAYER 1: Param validation ──
        schemas = child.param_schemas.get(tool_name, {})
        ok, err, cleaned = self._validator.validate(schemas, arguments)
        if not ok:
            self._audit.record(
                domain, tool_name, tier, arguments, 0, "PARAM_INVALID", 0,
                error=err, subject_id=subject_id,
                scrubber_id=self._phi_scrubber.scrubber_id,
                child_scrubber_id=child.child_scrubber_id,
                source_metadata_fingerprint=child.child_source_metadata_fingerprint,
            )
            return [TextContent(type="text", text=_dumps({"error": err}))]

        subject_id = _coerce_subject_id(cleaned)

        # ── LAYER 2: Circuit breaker (scoped per domain) ──
        cb_ok, cb_err = self._circuit.check(domain)
        if not cb_ok:
            self._audit.record(
                domain, tool_name, tier, cleaned, 0, "CIRCUIT_OPEN", 0,
                error=cb_err, subject_id=subject_id,
                scrubber_id=self._phi_scrubber.scrubber_id,
                child_scrubber_id=child.child_scrubber_id,
                source_metadata_fingerprint=child.child_source_metadata_fingerprint,
            )
            return [TextContent(type="text", text=_dumps({"error": cb_err}))]

        # ── LAYER 3: Consent gate (per-domain, Tier 2+) ──
        if tier >= 2:
            consent_ok, _ = self._consent.check(domain)
            if not consent_ok:
                self._audit.record(
                    domain, tool_name, tier, cleaned, 0, "CONSENT_BLOCKED", 0,
                    subject_id=subject_id,
                    scrubber_id=self._phi_scrubber.scrubber_id,
                    child_scrubber_id=child.child_scrubber_id,
                source_metadata_fingerprint=child.child_source_metadata_fingerprint,
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
                # Fail-closed: a broken estimator must not slip past the
                # cost gate with a synthetic 0-token estimate.
                duration_ms = int((time.time() - start) * 1000)
                self._audit.record(
                    domain, tool_name, tier, cleaned, 0,
                    "COST_ESTIMATE_ERROR", duration_ms,
                    error=str(e), subject_id=subject_id,
                    scrubber_id=self._phi_scrubber.scrubber_id,
                    child_scrubber_id=child.child_scrubber_id,
                source_metadata_fingerprint=child.child_source_metadata_fingerprint,
                )
                log.warning(f"Cost estimation failed for {tool_name}: {e}")
                return [
                    TextContent(
                        type="text",
                        text=_dumps({
                            "error": (
                                f"Could not estimate cost for {tool_name}; "
                                "refusing to execute Tier-3 call without a "
                                "verified token estimate."
                            )
                        }),
                    )
                ]

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
                    subject_id=subject_id,
                    scrubber_id=self._phi_scrubber.scrubber_id,
                    child_scrubber_id=child.child_scrubber_id,
                source_metadata_fingerprint=child.child_source_metadata_fingerprint,
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

            # ── PHI scrubbing seam (runs before tokens are counted or
            # the result is audited, so the scrubbed form is what every
            # downstream consumer sees). Default no-op; institutions
            # override by subclassing framework.security.PHIScrubber.
            if isinstance(result, dict):
                result = self._phi_scrubber.scrub(result)

            tokens = estimate_tokens(result)
            duration_ms = int((time.time() - start) * 1000)

            self._circuit.record_success(domain)
            self._ledger.add(domain, tool_name, tokens)
            self._audit.record(
                domain, tool_name, tier, cleaned, tokens, "SUCCESS", duration_ms,
                subject_id=subject_id,
                scrubber_id=self._phi_scrubber.scrubber_id,
                # Threaded on every audit row (matches existing
                # scrubber_id convention) to record what child-level
                # scrubber was configured at this call site, per
                # ADR 0003 § Amendment 2026-05-14 + ADR 0037.
                child_scrubber_id=child.child_scrubber_id,
                source_metadata_fingerprint=child.child_source_metadata_fingerprint,
            )

            # ── Post-execute hooks (e.g. VaultWriter) ──
            #
            # Hook failures cannot abort the tool call — the result is
            # already computed and audited — but they MUST surface to
            # the analyst. Pre-v6.5.0 the framework swallowed hook
            # failures into a stderr ``log.warning`` only, which is
            # invisible inside Claude Desktop (stderr is not surfaced
            # to the transcript). The mcp-protocol-auditor v6.5.0
            # release pass flagged this as M1: vault-write failures
            # during the demo were silently lost.
            #
            # Fix: failures are appended to ``_meta.hook_warnings`` so
            # they ride out in the same wire payload that carries the
            # result. The audit log keeps the full context (domain +
            # tool + exception class).
            hook_warnings: list[dict] = []
            for hook in self._post_execute_hooks:
                try:
                    hook(domain, tool_name, result)
                except Exception as _hook_exc:
                    log.warning(f"Post-execute hook failed: {_hook_exc}")
                    hook_warnings.append({
                        "hook": getattr(
                            hook, "__class__", type(hook),
                        ).__name__,
                        "error_type": type(_hook_exc).__name__,
                        "error": str(_hook_exc),
                    })

            # Attach metadata to response, including provenance stamps so
            # a downstream analyst can trace any result back to the exact
            # code version and moment that produced it.
            if isinstance(result, dict):
                result["_meta"] = {
                    "tokens_this_call": tokens,
                    "session_total_tokens": self._ledger.total,
                    "domain": domain,
                    "tier": tier,
                    "package_version": tailor.__version__,
                    "tool_name": tool_name,
                    "called_at": datetime.now(timezone.utc).isoformat(),
                    "scrubber_id": self._phi_scrubber.scrubber_id,
                    "child_scrubber_id": child.child_scrubber_id,
                    "source_metadata_fingerprint": child.child_source_metadata_fingerprint,
                }
                if self._phi_scrubber.scrubber_warning is not None:
                    result["_meta"]["scrubber_warning"] = self._phi_scrubber.scrubber_warning
                if hook_warnings:
                    # Surfaced into the wire so a vault-write failure
                    # during a Claude Desktop demo is visible in the
                    # transcript, not just the stderr log file.
                    result["_meta"]["hook_warnings"] = hook_warnings

            return [TextContent(type="text", text=_dumps(result))]

        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            # ADR 0003 § Amendment 2026-05-15 § Typed-exception taxonomy:
            # OperatorActionRequired signals "operator must act; system
            # is not flaky." Exempt from breaker accounting so the
            # recovery hint stays reachable on subsequent calls instead
            # of being hidden behind a generic "Circuit open" envelope.
            # Audit row still records outcome=ERROR with the same
            # provenance columns the W5 invariant covers. Logging level
            # also splits: programmer-error exceptions get the full
            # traceback at ERROR; operator-action conditions get the
            # message at INFO so a tight call loop does not flood
            # stderr (which on Windows fills the 4KB subprocess pipe
            # and stalls the server) for an expected condition.
            is_operator_action = isinstance(e, OperatorActionRequired)
            if not is_operator_action:
                self._circuit.record_failure(domain)
            self._audit.record(
                domain, tool_name, tier, cleaned, 0, "ERROR", duration_ms,
                error=str(e), subject_id=subject_id,
                scrubber_id=self._phi_scrubber.scrubber_id,
                child_scrubber_id=child.child_scrubber_id,
                source_metadata_fingerprint=child.child_source_metadata_fingerprint,
            )
            # OperatorActionRequired is structurally an expected
            # condition (operator must act to resolve); the audit row
            # and the wire envelope already carry the full event +
            # recovery hint. Emitting to the logger would write
            # ~500-byte lines to stderr; on a Windows MCP client that
            # does not drain stderr, the OS pipe buffer (4KB) fills
            # after ~8 events and the server stalls on its next write,
            # hiding the recovery affordance behind a different
            # failure mode — the exact class the v7.3.3 breaker
            # exemption was meant to close. The audit log is the
            # durable trace; live debugging goes through the audit DB,
            # not the stderr stream. Closes the v7.3.3 red-team-
            # reviewer OBJECTION (F-G).
            if not is_operator_action:
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
            - PHI-scrubber seam (per ADR 0012 — vault content is analyst
              notes or already-scrubbed downstream tool results, never
              raw biometric streams; the bypass is sound only while that
              invariant holds)
            - Post-execute hooks (vault writes should not trigger recursive
              vault writes)
        """
        tier = tool_def.tier
        subject_id = _coerce_subject_id(arguments)

        # ── LAYER 1: Param validation ──
        schemas = self._vault_layer.param_schemas.get(tool_name, {})
        ok, err, cleaned = self._validator.validate(schemas, arguments)
        if not ok:
            self._audit.record(
                "vault", tool_name, tier, arguments, 0, "PARAM_INVALID", 0,
                error=err, subject_id=subject_id,
                scrubber_id=self._phi_scrubber.scrubber_id,
                source_metadata_fingerprint=None,
            )
            return [TextContent(type="text", text=_dumps({"error": err}))]

        subject_id = _coerce_subject_id(cleaned)

        # ── EXECUTE ──
        try:
            result = await self._vault_layer.execute(tool_name, cleaned)
            tokens = estimate_tokens(result)
            duration_ms = int((time.time() - start) * 1000)

            self._ledger.add("vault", tool_name, tokens)
            self._audit.record(
                "vault", tool_name, tier, cleaned, tokens, "SUCCESS", duration_ms,
                subject_id=subject_id,
                scrubber_id=self._phi_scrubber.scrubber_id,
                source_metadata_fingerprint=None,
            )

            if isinstance(result, dict):
                result["_meta"] = {
                    "tokens_this_call": tokens,
                    "session_total_tokens": self._ledger.total,
                    "domain": "vault",
                    "tier": tier,
                    "package_version": tailor.__version__,
                    "tool_name": tool_name,
                    "called_at": datetime.now(timezone.utc).isoformat(),
                    "scrubber_id": self._phi_scrubber.scrubber_id,
                    "child_scrubber_id": None,
                    "source_metadata_fingerprint": None,
                    **(
                        {"scrubber_warning": self._phi_scrubber.scrubber_warning}
                        if self._phi_scrubber.scrubber_warning is not None
                        else {}
                    ),
                }

            return [TextContent(type="text", text=_dumps(result))]

        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            self._audit.record(
                "vault", tool_name, tier, cleaned, 0, "ERROR", duration_ms,
                error=str(e), subject_id=subject_id,
                scrubber_id=self._phi_scrubber.scrubber_id,
                source_metadata_fingerprint=None,
            )
            log.error(f"Vault tool {tool_name} failed: {e}", exc_info=True)
            return [TextContent(type="text", text=_dumps({"error": str(e)}))]

    async def _dispatch_local_llm(
        self,
        tool_name: str,
        tool_def: ToolDefinition,
        arguments: dict,
        start: float,
    ) -> list[TextContent]:
        """
        Dispatch a local-LLM-layer tool (per ADR 0022).

        Stripped-down pipeline:

            param validation → execute → audit

        Skipped by design:
            - Circuit breaker (no external API; the LLM runs on-device)
            - Consent gate (does not access biometric data directly;
              numerical_claims come from already-computed processing
              output, which already passed the appropriate gates on its
              originating Tier-1 calls)
            - Cost gate (local resource — wall-clock + CPU + RAM, not
              hosted-LLM tokens; ADR 0022 defers a local-resource gate
              to a future ADR)
            - PHI-scrubber seam (numerical claims came through processing.py
              and the scrubber on their original Tier-1 calls; the
              ``narrative`` field is LLM-generated prose explicitly
              labelled non-citable in _meta — operators with strict PHI
              policies should configure a backend that refuses to mention
              identifiers)
            - Post-execute hooks (oracle responses are non-citable
              narrative + already-cited numerical claims; they do not
              produce vaultable notes by design)

        The ``OracleResponse._meta`` provenance (model_id, model_version_hash,
        tier, latency_ms, prompt_hash, processing_calls, backend) is
        preserved by nesting it under ``result["_meta"]["oracle"]`` while
        the framework-level ``_meta`` keys (tokens, package_version, etc.)
        sit at the top level — same shape every other dispatch path uses.
        """
        tier = tool_def.tier
        subject_id = _coerce_subject_id(arguments)

        # ── LAYER 1: Param validation ──
        schemas = self._local_llm_layer.param_schemas.get(tool_name, {})
        ok, err, cleaned = self._validator.validate(schemas, arguments)
        if not ok:
            self._audit.record(
                "local_llm", tool_name, tier, arguments, 0, "PARAM_INVALID", 0,
                error=err, subject_id=subject_id,
                scrubber_id=self._phi_scrubber.scrubber_id,
                source_metadata_fingerprint=None,
            )
            return [TextContent(type="text", text=_dumps({"error": err}))]

        subject_id = _coerce_subject_id(cleaned)

        # ── EXECUTE ──
        try:
            result = await self._local_llm_layer.execute(tool_name, cleaned)
            tokens = estimate_tokens(result)
            duration_ms = int((time.time() - start) * 1000)

            # Pull oracle provenance from the response so the audit row
            # carries it as named columns (per ADR 0022 § "Architectural
            # placement"). The provenance also stays in the response's
            # _meta.oracle nested block for the LLM transcript — the
            # audit row makes it queryable from audit.db without parsing
            # the response payload.
            oracle_meta_for_audit = (
                result.get("_meta", {}) if isinstance(result, dict) else {}
            )
            oracle_confidence_raw = (
                result.get("confidence") if isinstance(result, dict) else None
            )
            try:
                oracle_confidence = (
                    float(oracle_confidence_raw)
                    if oracle_confidence_raw is not None
                    else None
                )
            except (TypeError, ValueError):
                oracle_confidence = None

            # The audit row's `oracle_latency_ms` is the backend's
            # compose() wall-clock alone — distinct from the row's
            # `duration_ms` which spans the full router pipeline
            # (validation + execute + audit-build). Querying audit.db
            # for "how long did the on-device inference take" wants
            # this column, not duration_ms.
            oracle_latency_raw = oracle_meta_for_audit.get("latency_ms")
            try:
                oracle_latency_ms = (
                    int(oracle_latency_raw)
                    if oracle_latency_raw is not None
                    else None
                )
            except (TypeError, ValueError):
                oracle_latency_ms = None

            # ADR 0023 — substrate count is recorded at the dispatch
            # layer (not by the layer.execute() return) so audit.db
            # answers "how much vault content did this oracle call
            # surface to the hosted LLM?" without parsing the response.
            substrate_raw = (
                result.get("related_substrate")
                if isinstance(result, dict)
                else None
            )
            oracle_substrate_count = (
                len(substrate_raw) if isinstance(substrate_raw, list) else 0
            )

            # ADR 0023 PR2 — gap-reasoning counts. Same dispatch-layer
            # extraction shape as oracle_substrate_count above so
            # audit.db answers "how many tool suggestions and analyst-
            # questions did the local LLM emit on this call?" without
            # parsing the response payload. The count is the audit-
            # completeness invariant; the content lives in the
            # response payload.
            next_best_raw = (
                result.get("next_best_calls")
                if isinstance(result, dict)
                else None
            )
            oracle_next_best_calls_count = (
                len(next_best_raw) if isinstance(next_best_raw, list) else 0
            )
            unresolved_raw = (
                result.get("unresolved_intent")
                if isinstance(result, dict)
                else None
            )
            oracle_unresolved_intent_count = (
                len(unresolved_raw) if isinstance(unresolved_raw, list) else 0
            )

            self._ledger.add("local_llm", tool_name, tokens)
            self._audit.record(
                "local_llm", tool_name, tier, cleaned, tokens, "SUCCESS",
                duration_ms,
                subject_id=subject_id,
                scrubber_id=self._phi_scrubber.scrubber_id,
                # Explicit None per the v7.3.1 all-call-sites-sweep
                # rule and mcp-protocol-auditor 2026-05-15 GAP finding —
                # local_llm has no child-level scrubber so the value is
                # None by construction; the explicit kwarg keeps every
                # SUCCESS audit row consistent under the sweep.
                source_metadata_fingerprint=None,
                oracle_model_id=oracle_meta_for_audit.get("model_id"),
                oracle_model_version_hash=oracle_meta_for_audit.get(
                    "model_version_hash"
                ),
                oracle_tier=oracle_meta_for_audit.get("tier"),
                oracle_confidence=oracle_confidence,
                oracle_prompt_hash=oracle_meta_for_audit.get("prompt_hash"),
                oracle_latency_ms=oracle_latency_ms,
                oracle_substrate_count=oracle_substrate_count,
                oracle_next_best_calls_count=oracle_next_best_calls_count,
                oracle_unresolved_intent_count=oracle_unresolved_intent_count,
            )

            if isinstance(result, dict):
                # Preserve OracleResponse._meta (model/tier/latency/prompt_hash)
                # by nesting it; overlay the framework's standard _meta keys.
                oracle_meta = result.pop("_meta", None)
                outer_meta: dict = {
                    "tokens_this_call": tokens,
                    "session_total_tokens": self._ledger.total,
                    "domain": "local_llm",
                    "tier": tier,
                    "package_version": tailor.__version__,
                    "tool_name": tool_name,
                    "called_at": datetime.now(timezone.utc).isoformat(),
                    "scrubber_id": self._phi_scrubber.scrubber_id,
                    "child_scrubber_id": None,
                    "source_metadata_fingerprint": None,
                }
                if self._phi_scrubber.scrubber_warning is not None:
                    outer_meta["scrubber_warning"] = (
                        self._phi_scrubber.scrubber_warning
                    )
                if isinstance(oracle_meta, dict):
                    outer_meta["oracle"] = oracle_meta
                result["_meta"] = outer_meta

            return [TextContent(type="text", text=_dumps(result))]

        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            self._audit.record(
                "local_llm", tool_name, tier, cleaned, 0, "ERROR", duration_ms,
                error=str(e), subject_id=subject_id,
                scrubber_id=self._phi_scrubber.scrubber_id,
                source_metadata_fingerprint=None,
            )
            log.error(
                f"Local-LLM tool {tool_name} failed: {e}", exc_info=True,
            )
            return [TextContent(type="text", text=_dumps({"error": str(e)}))]

    async def _dispatch_setup_help(
        self,
        tool_name: str,
        tool_def: ToolDefinition,
        arguments: dict,
        start: float,
    ) -> list[TextContent]:
        """
        Dispatch a setup-help-layer tool (recipient diagnostic).

        Stripped-down pipeline:

            param validation -> execute -> audit

        Skipped by design:
            - Circuit breaker (no external API; static instructions)
            - Consent gate (no biometric data accessed)
            - Cost gate (constant-size response, ~500 tokens)
            - PHI-scrubber seam (no biometric or subject data ever
              touched; bypass invariant + reversal condition codified
              in ADR 0012 § "Amendment — v6.10.2")
            - Post-execute hooks (no vaultable artifacts)

        Audit row uses domain="setup_help"; subject_id is always None
        because the tool is server-state, not per-subject. The standard
        framework ``_meta`` block is stamped onto the response so
        provenance (package_version, called_at, scrubber_id) is uniform
        with every other dispatch path.
        """
        tier = tool_def.tier

        # ── Param validation ──
        schemas = self._setup_help_layer.param_schemas.get(tool_name, {})
        ok, err, cleaned = self._validator.validate(schemas, arguments)
        if not ok:
            self._audit.record(
                "setup_help", tool_name, tier, arguments, 0,
                "PARAM_INVALID", 0,
                error=err, subject_id=None,
                scrubber_id=self._phi_scrubber.scrubber_id,
                source_metadata_fingerprint=None,
            )
            return [TextContent(type="text", text=_dumps({"error": err}))]

        # ── Execute ──
        try:
            result = await self._setup_help_layer.execute(tool_name, cleaned)
            tokens = estimate_tokens(result)
            duration_ms = int((time.time() - start) * 1000)

            self._ledger.add("setup_help", tool_name, tokens)
            self._audit.record(
                "setup_help", tool_name, tier, cleaned, tokens,
                "SUCCESS", duration_ms,
                subject_id=None,
                scrubber_id=self._phi_scrubber.scrubber_id,
                source_metadata_fingerprint=None,
            )

            if isinstance(result, dict):
                outer_meta: dict = {
                    "tokens_this_call": tokens,
                    "session_total_tokens": self._ledger.total,
                    "domain": "setup_help",
                    "tier": tier,
                    "package_version": tailor.__version__,
                    "tool_name": tool_name,
                    "called_at": datetime.now(timezone.utc).isoformat(),
                    "scrubber_id": self._phi_scrubber.scrubber_id,
                    "child_scrubber_id": None,
                    "source_metadata_fingerprint": None,
                }
                if self._phi_scrubber.scrubber_warning is not None:
                    outer_meta["scrubber_warning"] = (
                        self._phi_scrubber.scrubber_warning
                    )
                result["_meta"] = outer_meta

            return [TextContent(type="text", text=_dumps(result))]

        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            self._audit.record(
                "setup_help", tool_name, tier, cleaned, 0,
                "ERROR", duration_ms,
                error=str(e), subject_id=None,
                scrubber_id=self._phi_scrubber.scrubber_id,
                source_metadata_fingerprint=None,
            )
            log.error(
                f"Setup-help tool {tool_name} failed: {e}", exc_info=True,
            )
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
        subject_id = _coerce_subject_id(params)

        # ── LAYER 1: Param validation ──
        schemas = child.param_schemas.get(tool_name, {})
        ok, err, cleaned = self._validator.validate(schemas, params)
        if not ok:
            self._audit.record(
                domain, tool_name, tier, params, 0, "PARAM_INVALID_INTERNAL", 0,
                error=err, subject_id=subject_id,
                scrubber_id=self._phi_scrubber.scrubber_id,
                child_scrubber_id=child.child_scrubber_id,
                source_metadata_fingerprint=child.child_source_metadata_fingerprint,
            )
            return {"error": err}

        subject_id = _coerce_subject_id(cleaned)

        # ── LAYER 2: Circuit breaker ──
        cb_ok, cb_err = self._circuit.check(domain)
        if not cb_ok:
            self._audit.record(
                domain, tool_name, tier, cleaned, 0, "CIRCUIT_OPEN_INTERNAL", 0,
                error=cb_err, subject_id=subject_id,
                scrubber_id=self._phi_scrubber.scrubber_id,
                child_scrubber_id=child.child_scrubber_id,
                source_metadata_fingerprint=child.child_source_metadata_fingerprint,
            )
            return {"error": cb_err}

        # ── LAYER 3: Consent gate (Tier 2+) ──
        if tier >= 2:
            consent_ok, _ = self._consent.check(domain)
            if not consent_ok:
                self._audit.record(
                    domain, tool_name, tier, cleaned, 0, "CONSENT_BLOCKED_INTERNAL", 0,
                    subject_id=subject_id,
                    scrubber_id=self._phi_scrubber.scrubber_id,
                    child_scrubber_id=child.child_scrubber_id,
                source_metadata_fingerprint=child.child_source_metadata_fingerprint,
                )
                return {"error": f"Consent not approved for domain '{domain}'"}

        # ── LAYER 4: Cost gate (Tier 3) ──
        if tier >= 3:
            try:
                cost_est = await child.estimate_cost(tool_name, cleaned)
            except Exception as exc:
                # Fail-closed — same policy as the public path.
                duration_ms = int((time.time() - start) * 1000)
                self._audit.record(
                    domain, tool_name, tier, cleaned, 0,
                    "COST_ESTIMATE_ERROR_INTERNAL", duration_ms,
                    error=str(exc), subject_id=subject_id,
                    scrubber_id=self._phi_scrubber.scrubber_id,
                    child_scrubber_id=child.child_scrubber_id,
                source_metadata_fingerprint=child.child_source_metadata_fingerprint,
                )
                log.warning(
                    f"Internal dispatch: cost estimation failed for {tool_name}: {exc}"
                )
                return {
                    "error": (
                        f"Could not estimate cost for {tool_name}; "
                        "refusing internal Tier-3 dispatch without a "
                        "verified token estimate."
                    )
                }
            if self._cost_gate.should_gate(cost_est.tokens):
                duration_ms = int((time.time() - start) * 1000)
                self._audit.record(
                    domain, tool_name, tier, cleaned, cost_est.tokens,
                    "COST_GATE_INTERNAL", duration_ms,
                    subject_id=subject_id,
                    scrubber_id=self._phi_scrubber.scrubber_id,
                    child_scrubber_id=child.child_scrubber_id,
                source_metadata_fingerprint=child.child_source_metadata_fingerprint,
                )
                return {"error": f"Cost gate: {cost_est.tokens} tokens exceeds threshold"}

        # ── LAYER 5: Execute ──
        try:
            result = await child.execute(tool_name, cleaned)
            # Same PHI-scrubbing seam as the public dispatch path, so
            # internal cross-child calls (e.g. vault backfill) see the
            # same scrubbed view a Claude-facing call would see.
            if isinstance(result, dict):
                result = self._phi_scrubber.scrub(result)
            tokens = estimate_tokens(result)
            duration_ms = int((time.time() - start) * 1000)

            self._circuit.record_success(domain)
            self._ledger.add(domain, tool_name, tokens)
            self._audit.record(
                domain, tool_name, tier, cleaned, tokens, "SUCCESS_INTERNAL", duration_ms,
                subject_id=subject_id,
                scrubber_id=self._phi_scrubber.scrubber_id,
                # Threaded on every audit row (matches existing
                # scrubber_id convention) to record what child-level
                # scrubber was configured at this call site, per
                # ADR 0003 § Amendment 2026-05-14 + ADR 0037.
                child_scrubber_id=child.child_scrubber_id,
                source_metadata_fingerprint=child.child_source_metadata_fingerprint,
            )
            # No post-execute hooks — caller manages side effects.
            # Stamp _meta so internal dispatch results carry the same
            # provenance as Claude-facing ones; otherwise vault backfill
            # results would be untraceable.
            if isinstance(result, dict):
                result["_meta"] = {
                    "tokens_this_call": tokens,
                    "session_total_tokens": self._ledger.total,
                    "domain": domain,
                    "tier": tier,
                    "package_version": tailor.__version__,
                    "tool_name": tool_name,
                    "called_at": datetime.now(timezone.utc).isoformat(),
                    "scrubber_id": self._phi_scrubber.scrubber_id,
                    "child_scrubber_id": child.child_scrubber_id,
                    "source_metadata_fingerprint": child.child_source_metadata_fingerprint,
                    "source": "INTERNAL",
                }
                if self._phi_scrubber.scrubber_warning is not None:
                    result["_meta"]["scrubber_warning"] = self._phi_scrubber.scrubber_warning
            return result

        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            # ADR 0003 § Amendment 2026-05-15 § Typed-exception taxonomy:
            # parity with the public dispatch handler's breaker exemption.
            # A cross-child internal dispatch hitting an OperatorActionRequired
            # raise (e.g. an oracle tool grounding a claim against REDCap
            # while project_metadata.csv drift is in effect) must NOT trip
            # the breaker on the called child's domain — otherwise breaker
            # state diverges depending on which dispatch path triggered.
            # Symmetric log-level split with the public path.
            is_operator_action = isinstance(e, OperatorActionRequired)
            if not is_operator_action:
                self._circuit.record_failure(domain)
            self._audit.record(
                domain, tool_name, tier, cleaned, 0, "ERROR_INTERNAL", duration_ms,
                error=str(e), subject_id=subject_id,
                scrubber_id=self._phi_scrubber.scrubber_id,
                child_scrubber_id=child.child_scrubber_id,
                source_metadata_fingerprint=child.child_source_metadata_fingerprint,
            )
            # Symmetric silence on the internal dispatch path per
            # the F-G closure rationale above.
            if not is_operator_action:
                log.error(
                    f"Internal dispatch {tool_name} failed: {e}", exc_info=True
                )
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
        self._audit.record(
            domain, tool_name, 0, {}, 0, "SUCCESS", 0,
            scrubber_id=self._phi_scrubber.scrubber_id,
            child_scrubber_id=child.child_scrubber_id,
            source_metadata_fingerprint=child.child_source_metadata_fingerprint,
        )
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

    def _handle_consent_revocation(
        self, tool_name: str, arguments: dict
    ) -> list[TextContent]:
        """
        Revoke consent and purge the child's biometric cache atomically.

        Per ADR 0013, the order is purge → revoke (fail-closed):
        if the child's ``purge_cache()`` raises, consent stays
        approved and the caller sees the error. The IRB invariant is
        "revocation = no cache"; failing to revoke loudly is better
        than declaring revocation while PHI persists. Caller can
        pass ``force_revoke=True`` to swallow purge errors and
        revoke anyway — used for the rare locked-cache-file edge case.
        """
        domain = tool_name[len("revoke_consent_"):]
        if domain not in self._children:
            return [
                TextContent(
                    type="text",
                    text=_dumps({"error": f"Unknown domain: {domain}"}),
                )
            ]
        child = self._children[domain]
        force_revoke = bool(arguments.get("force_revoke", False)) if arguments else False
        scrubber_id = self._phi_scrubber.scrubber_id

        # If consent was never approved, there is nothing to purge —
        # short-circuit before touching the storage layer.
        if not self._consent.is_approved(domain):
            self._audit.record(
                domain, tool_name, 0, {}, 0, "SUCCESS", 0,
                scrubber_id=scrubber_id,
                child_scrubber_id=child.child_scrubber_id,
                source_metadata_fingerprint=child.child_source_metadata_fingerprint,
            )
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

        # ── Purge first (per ADR 0013 fail-closed ordering) ──
        try:
            purge_result = child.purge_cache(force=force_revoke)
        except Exception as exc:
            # Fail closed: consent stays approved, caller sees the error.
            self._audit.record(
                domain, tool_name, 0, {"force_revoke": force_revoke},
                0, "PURGE_FAILED", 0,
                error=str(exc), scrubber_id=scrubber_id,
                child_scrubber_id=child.child_scrubber_id,
                source_metadata_fingerprint=child.child_source_metadata_fingerprint,
            )
            log.error(
                f"purge_cache failed for {domain}; revocation aborted "
                f"(consent stays approved). Error: {exc}",
                exc_info=True,
            )
            return [
                TextContent(
                    type="text",
                    text=_dumps(
                        {
                            "revoked": False,
                            "domain": domain,
                            "error": (
                                f"Cache purge failed; consent NOT revoked "
                                f"to honour ADR 0013 fail-closed invariant. "
                                f"Underlying error: {exc}. Pass "
                                f"force_revoke=True to revoke anyway."
                            ),
                        }
                    ),
                )
            ]

        # Purge succeeded (or force=True swallowed any error). Flip
        # consent state and record the paired audit row. The purge
        # result (row counts, tables touched, preserved tables, any
        # partial-failure errors) lands in the PURGE_CACHE row's
        # params per ADR 0013 § "Paired audit rows" — the doc and
        # code claim a single source of truth, so both must agree.
        self._consent.revoke(domain)
        self._audit.record(
            domain, "purge_cache", 0,
            {"force_revoke": force_revoke, "purge_result": purge_result},
            0, "PURGE_CACHE", 0,
            scrubber_id=scrubber_id,
            child_scrubber_id=child.child_scrubber_id,
            source_metadata_fingerprint=child.child_source_metadata_fingerprint,
        )
        self._audit.record(
            domain, tool_name, 0, {"force_revoke": force_revoke},
            0, "SUCCESS", 0,
            scrubber_id=scrubber_id,
            child_scrubber_id=child.child_scrubber_id,
            source_metadata_fingerprint=child.child_source_metadata_fingerprint,
        )
        return [
            TextContent(
                type="text",
                text=_dumps(
                    {
                        "revoked": True,
                        "domain": domain,
                        "display_name": child.display_name,
                        "purge_result": purge_result,
                        "message": (
                            f"Biometric data access revoked for "
                            f"{child.display_name} and cache purged "
                            f"({purge_result.get('rows_purged', 0)} rows). "
                            f"Gated tools in '{domain}' will require "
                            f"fresh consent."
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
        for child in self._children.values():
            child.close()

    def run(self):
        """Start the MCP server via stdio transport."""
        import asyncio

        from mcp.server.stdio import stdio_server

        server = self.create_server()

        async def main():
            async with stdio_server() as (read_stream, write_stream):
                await server.run(
                    read_stream,
                    write_stream,
                    server.create_initialization_options(),
                )

        try:
            asyncio.run(main())
        finally:
            self.close()  # Release SQLite WAL locks (required on Windows)
