"""
Biosensor-to-LLM Framework — Security pipeline components
==========================================================
Pre-execution gates owned by the parent router. Cheapest checks first
in the order defined by ``RouterMCP._dispatch()``:

1. ``ParamValidator``  — reject bad input before any work
2. ``CircuitBreaker``  — block if upstream is failing
3. ``ConsentGate``     — per-domain biometric consent
4. ``PHIScrubber``     — institutional-policy scrubbing seam (default: no-op)

The cost gate and audit log are separate concerns and live in
``framework.cost`` and ``framework.audit`` respectively.

Research framing
----------------
These components own the framework's governance surface for biosensor-
tier dispatch. The ``PHIScrubber`` in particular is a documented seam
(see ADR 0003) — institutions subclass it once they have an IRB-
approved policy. The default no-op surfaces itself loudly so a
misconfigured deployment is visible from the first call.
"""

import logging
import re
import time

from .interfaces import ValidationSchema

log = logging.getLogger("tailor")


# ═══════════════════════════════════════════════════════════════
# PARAM VALIDATION
# ═══════════════════════════════════════════════════════════════

class ParamValidator:
    """Validate and sanitize tool parameters against ValidationSchema."""

    @staticmethod
    def validate(schemas: dict[str, ValidationSchema], params: dict) -> tuple[bool, str, dict]:
        """
        Validate params against schemas.
        Returns (ok, error_msg, cleaned_params).
        """
        if not schemas:
            return True, "", params

        cleaned = {}
        for key, schema in schemas.items():
            value = params.get(key)

            # Required check
            if schema.required and value is None:
                return False, f"Missing required parameter: {key}", {}

            # Apply default
            if value is None:
                if schema.default is not None:
                    cleaned[key] = schema.default
                continue

            # Type-specific validation (schema.type stores a type object:
            # compare with `is` rather than ==, per PEP 8)
            if schema.type is int:
                try:
                    value = int(value)
                except (ValueError, TypeError):
                    return False, f"Parameter {key} must be an integer", {}
                if schema.min is not None and value < schema.min:
                    return False, f"Parameter {key} must be >= {schema.min}", {}
                if schema.max is not None and value > schema.max:
                    return False, f"Parameter {key} must be <= {schema.max}", {}

            elif schema.type is str:
                value = str(value)
                if schema.pattern and not re.match(schema.pattern, value):
                    return False, f"Parameter {key} format invalid (expected {schema.pattern})", {}

            elif schema.type is list:
                if not isinstance(value, list):
                    return False, f"Parameter {key} must be a list", {}
                if schema.min_len is not None and len(value) < schema.min_len:
                    return False, f"Parameter {key} must have at least {schema.min_len} items", {}
                if schema.max_len is not None and len(value) > schema.max_len:
                    return False, f"Parameter {key} must have at most {schema.max_len} items", {}
                if schema.allowed_values:
                    invalid = [v for v in value if v not in schema.allowed_values]
                    if invalid:
                        return False, (
                            f"Invalid values for {key}: {invalid}. "
                            f"Allowed: {schema.allowed_values}"
                        ), {}

            cleaned[key] = value

        # Pass through extra params not in schema
        for key, value in params.items():
            if key not in cleaned:
                cleaned[key] = value

        return True, "", cleaned


# ═══════════════════════════════════════════════════════════════
# CIRCUIT BREAKER
# ═══════════════════════════════════════════════════════════════

class CircuitBreaker:
    """
    Auto-block after N consecutive failures. Scoped per key (typically per child domain).

    Prevents cascading failures when an upstream API (Strava, CGM provider, etc.) is down.
    Resets automatically after a cooldown period.
    """

    def __init__(self, threshold: int = 3, reset_after: float = 300):
        self.threshold = threshold
        self.reset_after = reset_after
        self._failures: dict[str, list[float]] = {}
        self._tripped: dict[str, float] = {}

    def check(self, key: str) -> tuple[bool, str]:
        """Returns (ok, error_message). ok=False means circuit is open."""
        if key in self._tripped:
            elapsed = time.time() - self._tripped[key]
            if elapsed < self.reset_after:
                remaining = int(self.reset_after - elapsed)
                return False, f"Circuit open for {key} — {remaining}s until reset"
            del self._tripped[key]
            self._failures.pop(key, None)
        return True, ""

    def record_success(self, key: str):
        self._failures.pop(key, None)

    def record_failure(self, key: str):
        now = time.time()
        fails = self._failures.setdefault(key, [])
        fails.append(now)
        fails[:] = [f for f in fails if now - f < self.reset_after]
        if len(fails) >= self.threshold:
            self._tripped[key] = now
            log.warning(f"Circuit breaker TRIPPED for {key} after {self.threshold} failures")


# ═══════════════════════════════════════════════════════════════
# OPERATOR-ACTION-REQUIRED TAXONOMY (ADR 0003 § Amendment 2026-05-15)
# ═══════════════════════════════════════════════════════════════

class OperatorActionRequired(Exception):
    """Marker exception class for child-raised conditions that require
    an operator action rather than back-off.

    The ``CircuitBreaker`` exists to back off external systems that are
    *flaky* (transient network, rate-limit, intermittent failure).
    Some legitimate runtime conditions are structurally different:
    the system is fine; the operator must take an out-of-band action
    (re-attest a trust root, rotate a credential, restart a process)
    before subsequent calls can succeed. Counting these toward the
    breaker is a taxonomy mismatch — it hides the recovery affordance
    behind a generic "Circuit open" envelope for the next 5 minutes,
    exactly the window the operator most needs guidance.

    Children that raise this class MUST provide a non-empty
    ``recovery_action`` describing the operator-facing remediation
    (e.g. ``"tailor redcap reattest"``). The router's exception
    handler exempts instances from ``CircuitBreaker.record_failure``;
    the recovery hint stays reachable on subsequent calls.

    Misuse guard: a child author who classifies an *upstream-flaky*
    exception as ``OperatorActionRequired`` would defeat the breaker
    for paths that legitimately need it. The required
    ``recovery_action`` attribute makes the contract self-documenting
    — if a child author cannot name a remediation command, the
    exception is not operator-action-required.

    See ADR 0003 § Amendment 2026-05-15 § Typed-exception taxonomy.
    """

    def __init__(self, *args, recovery_action: str):
        super().__init__(*args)
        if not isinstance(recovery_action, str) or not recovery_action.strip():
            raise TypeError(
                "OperatorActionRequired requires a non-empty `recovery_action` "
                "string naming the operator-facing remediation. See "
                "ADR 0003 § Amendment 2026-05-15."
            )
        self.recovery_action = recovery_action


# ═══════════════════════════════════════════════════════════════
# CONSENT GATE
# ═══════════════════════════════════════════════════════════════

class ConsentGate:
    """
    Per-domain biometric consent. Session-scoped, revocable.

    'I consent to share my running data' does NOT auto-approve
    CGM or sleep data. Each biosensor domain requires separate consent.
    Consent does not persist across sessions.

    Revocability closes the consent loop: "yes" is no longer functionally
    irreversible for the conversation. Users can revoke at any time.
    """

    def __init__(self):
        self._approved: dict[str, bool] = {}

    def check(self, domain: str) -> tuple[bool, str]:
        """Returns (ok, error_key). ok=False means consent needed."""
        if self._approved.get(domain, False):
            return True, ""
        return False, f"CONSENT_REQUIRED:{domain}"

    def approve(self, domain: str):
        self._approved[domain] = True
        log.info(f"Biometric consent GRANTED for domain: {domain}")

    def revoke(self, domain: str) -> bool:
        """
        Revoke consent for a domain. Returns True if was previously approved.

        After revocation, subsequent Tier 2+ calls to this domain will
        trigger the consent gate again. Does not affect Tier 1 (free) tools.
        """
        was_approved = self._approved.pop(domain, False)
        if was_approved:
            log.info(f"Biometric consent REVOKED for domain: {domain}")
        return was_approved

    def is_approved(self, domain: str) -> bool:
        return self._approved.get(domain, False)

    @property
    def approved_domains(self) -> list[str]:
        return [d for d, v in self._approved.items() if v]


# ═══════════════════════════════════════════════════════════════
# PHI SCRUBBER (extension seam)
# ═══════════════════════════════════════════════════════════════

class PHIScrubber:
    """
    Extension seam for institutional PHI scrubbing policies.

    The default implementation is a no-op: it returns the result
    unchanged. This is intentional. The running child in this
    repository ships with no institutional policy to enforce, and
    the framework never pretends to know what "PHI" means in a
    given study — that is an institutional, protocol-specific
    decision. See ADR 0003 for the full rationale.

    What this class IS:
        - A stable hook point between a child's ``execute()`` and the
          audit log / token accounting.
        - A single, documented place to plug in transforms that drop
          or hash identifying fields from tool results before those
          results leave the router.

    What this class is NOT:
        - A safe-harbor PHI de-identifier.
        - A replacement for institutional review.
        - A substitute for keeping raw streams local (which the
          tiered-access model already enforces).

    Subclass and override ``scrub()`` per data source. Wire a
    per-child instance in at router construction time once the
    subclass exists.
    """

    # Class-level flag so the no-op warning fires once per process,
    # not once per router instance (tests instantiate many routers).
    _noop_warning_emitted = False

    def __init__(self):
        # Only the base class is the no-op. Subclasses signal intent
        # by overriding scrub() — their __init__ doesn't trigger this.
        if type(self) is PHIScrubber and not PHIScrubber._noop_warning_emitted:
            log.warning(
                "PHIScrubber default is a no-op; subclass and wire a real "
                "scrubber in at router construction for production use."
            )
            PHIScrubber._noop_warning_emitted = True

    @property
    def scrubber_id(self) -> str:
        """Short identifier stamped into _meta for audit traceability."""
        return "noop" if type(self) is PHIScrubber else type(self).__name__

    @property
    def scrubber_warning(self) -> str | None:
        """
        Optional warning surfaced into every successful result's ``_meta``
        block when the no-op default scrubber is in use. Subclasses signal
        an active policy by inheriting the ``None`` return.

        Why surface here, not just stderr: stderr from a Claude-Desktop-
        spawned MCP server is invisible to the analyst. Stamping the
        warning into ``_meta`` makes the misconfiguration visible in the
        LLM transcript on every call, satisfying ADR 0003's intent that
        a no-op deployment surface "loudly" in any environment.
        """
        if type(self) is PHIScrubber:
            return (
                "PHIScrubber default is a no-op; production deployments "
                "must subclass PHIScrubber. See ADR 0003."
            )
        return None

    def scrub(self, result: dict) -> dict:
        """
        Return ``result`` unchanged. Subclasses override this method
        to strip, hash, or transform fields before results leave the
        router. Implementations must be pure functions of the result
        dict — no I/O, no exceptions on well-formed input.
        """
        return result
