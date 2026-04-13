"""
Biosensor-to-LLM Framework — Security Middleware
=================================================
Cross-cutting concerns owned by the parent router.
Domain-agnostic: these work identically regardless of data source.

Pipeline order (cheapest checks first):
1. ParamValidator  — reject bad input before any work
2. CircuitBreaker  — block if upstream is failing
3. ConsentGate     — per-domain biometric consent
4. CostGate        — pre-estimate tokens, gate if expensive
5. PHIScrubber     — institutional-policy scrubbing seam (default: no-op)
6. AuditLog        — log every call for reproducibility and IRB review
7. TokenLedger     — track cumulative session spend

Research framing
----------------
The audit log is the backbone of reproducibility and IRB review for
LLM-assisted analyses in this framework. Every tool call is persisted
with timestamp, domain, tool name, access tier, parameters, token
estimate, outcome, latency, and (optionally) a study ``subject_id``
pulled from the call parameters. That row is intended to be durable
evidence — of how an analyst accessed participant data, in what order,
with what scope, and with what result — suitable for appendices,
protocol amendments, or replication packages.

The PHIScrubber is the extension seam for institutional PHI
policies. It ships as a no-op; real scrubbing implementations are
added per data source and per institutional review.
"""

import logging
import re
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .interfaces import ValidationSchema

# ── JSON backend (orjson with stdlib fallback) ──

try:
    import orjson as _orjson

    def _dumps(obj, **kw) -> str:
        return _orjson.dumps(obj, default=str).decode()

    def _loads(s):
        return _orjson.loads(s)

    JSON_BACKEND = "orjson"
except ImportError:
    import json as _json

    def _dumps(obj, **kw) -> str:
        return _json.dumps(obj, default=str)

    def _loads(s):
        return _json.loads(s)

    JSON_BACKEND = "json (orjson not installed)"


log = logging.getLogger("biosensor-mcp")


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
# COST GATE
# ═══════════════════════════════════════════════════════════════

class CostGate:
    """
    Token cost gate. Fires when pre-estimated cost exceeds threshold.

    Uses the child's estimate_cost() — no wasted computation.
    Shows the user full vs. cheaper alternative costs before proceeding.
    Generates human-relatable context so raw token counts aren't presented alone.
    """

    # Baseline for "typical call" comparison (~800 tokens for a run report)
    TYPICAL_CALL_TOKENS = 800

    def __init__(self, threshold: int = 35_000):
        self.threshold = threshold

    def should_gate(self, estimated_tokens: int) -> bool:
        return estimated_tokens >= self.threshold

    def humanize(self, tokens: int, alternative_tokens: int = 0) -> dict:
        """
        Build a CostContext dict with human-relatable anchors.

        Returns a plain dict (not CostContext dataclass) for zero-import
        serialization in the router. Keeps the interface minimal.
        """
        multiple = round(tokens / self.TYPICAL_CALL_TOKENS)
        ctx: dict = {
            "tokens": tokens,
            "relative_to_typical": f"~{multiple}x a typical analysis call",
        }
        if alternative_tokens > 0:
            ratio = round(tokens / max(alternative_tokens, 1))
            ctx["relative_to_cheaper_pct"] = (
                f"~{ratio}x more than the downsampled alternative"
            )
        return ctx


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
    decision.

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

    def scrub(self, result: dict) -> dict:
        """
        Return ``result`` unchanged. Subclasses override this method
        to strip, hash, or transform fields before results leave the
        router. Implementations must be pure functions of the result
        dict — no I/O, no exceptions on well-formed input.
        """
        return result


# ═══════════════════════════════════════════════════════════════
# AUDIT LOG
# ═══════════════════════════════════════════════════════════════

class AuditLog:
    """
    Every tool call logged to SQLite for reproducibility and IRB review.

    Captured per call: timestamp, domain, tool name, access tier,
    parameters, token estimate, outcome, latency, an optional error
    message, and an optional ``subject_id`` for studies that want to
    scope rows to a participant or cohort. ``subject_id`` is only
    populated when a caller supplies one — children are free to
    ignore it.

    Uses threading.local() so each thread gets its own SQLite connection —
    sqlite3 connections must not be shared across threads (check_same_thread
    defaults to True for good reason). The schema is created once on the
    first connection from any thread, and WAL mode allows concurrent readers.
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._local = threading.local()
        # Eagerly create the schema from the constructing thread
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                domain TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                tier INTEGER NOT NULL,
                params TEXT,
                token_estimate INTEGER,
                outcome TEXT NOT NULL,
                duration_ms INTEGER,
                error TEXT,
                subject_id TEXT
            )
        """)
        # Migrate pre-existing audit.db files that predate the subject_id
        # column. Mirrors VaultStorage._ensure_db()'s approach for
        # vault_notes.mtime_ns: detect via PRAGMA, ALTER TABLE if absent.
        cols = {
            row[1]
            for row in self._conn.execute("PRAGMA table_info(audit_log)").fetchall()
        }
        if "subject_id" not in cols:
            self._conn.execute("ALTER TABLE audit_log ADD COLUMN subject_id TEXT")
        self._conn.commit()

    @property
    def _conn(self) -> sqlite3.Connection:
        """Return (or lazily create) the per-thread SQLite connection."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(str(self.db_path))
            self._local.conn.execute("PRAGMA journal_mode=WAL")
        return self._local.conn

    def close(self):
        """Close the thread-local connection. Required on Windows to release file lock."""
        if hasattr(self._local, "conn") and self._local.conn is not None:
            self._local.conn.close()
            self._local.conn = None

    # A pathological caller can pass a multi-megabyte params dict and bloat
    # audit.db. Serialized params above this bound are truncated with a
    # marker — we still record *that* the call happened, but the params
    # column stays query-able. 50 KB is generous for structured args.
    _MAX_PARAMS_BYTES = 50_000

    def record(self, domain: str, tool_name: str, tier: int, params: dict,
               token_estimate: int, outcome: str, duration_ms: int,
               *, error: str | None = None,
               subject_id: str | None = None):
        params_json = _dumps(params)
        if isinstance(params_json, bytes):
            params_repr = params_json.decode("utf-8", errors="replace")
        else:
            params_repr = params_json
        if len(params_repr) > self._MAX_PARAMS_BYTES:
            params_repr = (
                params_repr[: self._MAX_PARAMS_BYTES]
                + f"...[truncated; original {len(params_repr)} bytes]"
            )
        self._conn.execute(
            "INSERT INTO audit_log"
            " (timestamp, domain, tool_name, tier, params, token_estimate,"
            "  outcome, duration_ms, error, subject_id)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (datetime.now(timezone.utc).isoformat(), domain, tool_name, tier,
             params_repr, token_estimate, outcome, duration_ms, error,
             subject_id),
        )
        self._conn.commit()
        log.info(
            f"AUDIT | {domain}.{tool_name} | tier={tier} "
            f"| tokens~{token_estimate} | {outcome} | {duration_ms}ms"
            + (f" | subject={subject_id}" if subject_id else "")
        )


# ═══════════════════════════════════════════════════════════════
# TOKEN LEDGER
# ═══════════════════════════════════════════════════════════════

class TokenLedger:
    """Track cumulative token spend per session, broken down by domain."""

    def __init__(self):
        self._entries: list[dict] = []
        self.session_start = datetime.now(timezone.utc)

    def add(self, domain: str, tool_name: str, tokens: int):
        self._entries.append({
            "domain": domain,
            "tool": tool_name,
            "tokens": tokens,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    @property
    def total(self) -> int:
        return sum(e["tokens"] for e in self._entries)

    def by_domain(self) -> dict[str, int]:
        domains: dict[str, int] = {}
        for e in self._entries:
            domains[e["domain"]] = domains.get(e["domain"], 0) + e["tokens"]
        return domains

    def summary(self) -> dict:
        return {
            "session_total_tokens": self.total,
            "call_count": len(self._entries),
            "by_domain": self.by_domain(),
        }


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
# UTILITY
# ═══════════════════════════════════════════════════════════════

def estimate_tokens(data: Any) -> int:
    """Rough token estimate: ~4 chars per token for JSON payloads."""
    text = _dumps(data) if not isinstance(data, str) else data
    return len(text) // 4
