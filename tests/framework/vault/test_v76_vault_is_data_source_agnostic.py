"""
v7.6.0 AST-class invariant tests for VaultLayer data-source-agnostic
property per ADR 0038 § Amendment 2026-05-19.

Parallel to v7.5.0's
``test_user_config_json_write_sites_are_canonical`` (AST walking to
find write sites + verify canonical-seam rule). The tests here walk
``framework/vault/layer.py`` at the AST level — NOT grep-class —
because the v7.3.2 W5 textual-window lesson taught that grep-class
detection false-positives on adjacent comment text and dict-key
literals that look like the pattern but aren't actually parameter
keywords.

Invariants asserted:

1. Zero ``domain="running"`` keyword-argument literals outside an
   explicit allowlist of structurally-justified call sites.
2. Zero ``strava_*`` string-literal references outside lines that
   read from ``self._backfill_config`` (the wiring-site indirection
   that ADR 0038 § Decision sub-item 3 names).
3. The module no longer exports an ``_ALLOWED_KINDS`` tuple constant
   at module level; the canonical shape is the framework-tier base
   ``_FRAMEWORK_KIND_BASE`` plus instance-state ``_allowed_kinds``
   populated at ``register_vault_layer()`` time.
4. The module-level ``_domain_for_kind`` helper no longer exists at
   module level; it has migrated to ``VaultLayer._domain_for_kind``
   per the amendment.

See ADR 0038 § Amendment 2026-05-19 sub-section "Sub-item structural
backstop — AST-class invariant test" for the rationale.
"""

from __future__ import annotations

import ast
from pathlib import Path

LAYER_FILE = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "tailor"
    / "framework"
    / "vault"
    / "layer.py"
)


# ── Allowlist for domain="running" keyword-argument sites ──
#
# Each entry: a function or method name where the call is permitted
# because (a) the surrounding code path is structurally running-
# specific by its function-level contract (e.g. ``_find_run_note_by_
# activity_id`` looks up a running activity by ID), or (b) the call
# is gated on the running child being registered via
# ``"run_report" in self._kind_to_domain_map``.
#
# Maintenance contract: when a new running-specific helper lands or
# an existing one is renamed, update this set + cite ADR 0038 in the
# accompanying PR. The AST test fails loudly on any unsanctioned new
# site, preventing regression to v7.3.4-shape Strava-coupling drift.
DOMAIN_RUNNING_ALLOWLIST_FUNCTIONS: frozenset[str] = frozenset(
    {
        # ``_handle_fitness_summary`` counts ``domain="running"`` notes
        # to decide between the "running-deployment-empty" and
        # "non-running-deployment" remediation branches. The count is
        # how the function detects deployment shape; without it the
        # data-source-aware fallback v7.3.4 closed cannot exist.
        "_handle_fitness_summary",
        # ``_find_run_note_by_activity_id`` resolves a running-child
        # activity_id to its vault note filename. Only the running
        # child has activity_ids; the function is correctly running-
        # specific by contract. Returns None on non-running deployments.
        "_find_run_note_by_activity_id",
        # ``_build_snapshot_payload`` queries running notes for the
        # weekly summary section ONLY when "run_report" is registered
        # (the conditional landed in v7.6.0 per ADR 0038 § Amendment
        # 2026-05-19 sub-item 4 / auditor's I2 closure).
        "_build_snapshot_payload",
    }
)


def _enclosing_function_name(tree: ast.AST, target_node: ast.AST) -> str | None:
    """Find the nearest enclosing FunctionDef/AsyncFunctionDef name."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(node):
                if child is target_node:
                    return node.name
    return None


def _iter_domain_running_call_sites(
    tree: ast.AST,
) -> list[tuple[int, str | None]]:
    """Find every call with a ``domain="running"`` keyword arg.

    Returns (lineno, enclosing_function_name) tuples.
    """
    sites: list[tuple[int, str | None]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if (
                kw.arg == "domain"
                and isinstance(kw.value, ast.Constant)
                and kw.value.value == "running"
            ):
                fn = _enclosing_function_name(tree, node)
                sites.append((node.lineno, fn))
    return sites


def _iter_strava_string_literals(tree: ast.AST) -> list[tuple[int, str]]:
    """Find every string literal that starts with 'strava_'."""
    sites: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value.startswith("strava_")
        ):
            sites.append((node.lineno, node.value))
    return sites


def _is_inside_backfill_config_subscript(
    tree: ast.AST, line: int
) -> bool:
    """Heuristic: scan ±2 lines around ``line`` for ``backfill_config``.

    A strava_* literal that appears within two lines of a
    ``backfill_config`` reference is treated as a wiring-site
    indirection (ADR 0038 sub-item 3 allows this). The heuristic is
    conservative — a false-positive here means a non-backfill_config
    strava literal sneaks through, but in practice the only callers
    of self._backfill_config.get(...) are the deprecation-hint
    derivation site.
    """
    source = LAYER_FILE.read_text(encoding="utf-8").splitlines()
    start = max(0, line - 3)
    end = min(len(source), line + 2)
    window = "\n".join(source[start:end])
    return "backfill_config" in window or "_backfill_config" in window


def _load_layer_ast() -> ast.AST:
    source = LAYER_FILE.read_text(encoding="utf-8")
    return ast.parse(source, filename=str(LAYER_FILE))


# ──────────────────────────────────────────────────────────────────
# INVARIANT 1 — domain="running" only inside allowlisted functions
# ──────────────────────────────────────────────────────────────────

def test_domain_running_kwarg_only_in_allowlisted_functions() -> None:
    """Every ``domain="running"`` call must sit inside an allowlisted
    function or method per ADR 0038 § Amendment 2026-05-19. New
    unsanctioned sites fail this test loudly — same shape as v7.5.0's
    ``test_user_config_json_write_sites_are_canonical``.
    """
    tree = _load_layer_ast()
    violations: list[tuple[int, str | None]] = []
    for lineno, fn_name in _iter_domain_running_call_sites(tree):
        if fn_name not in DOMAIN_RUNNING_ALLOWLIST_FUNCTIONS:
            violations.append((lineno, fn_name))

    assert not violations, (
        "framework/vault/layer.py contains domain=\"running\" "
        "keyword arguments outside the ADR 0038 allowlist:\n"
        + "\n".join(
            f"  line {ln} — inside function {fn!r}" for ln, fn in violations
        )
        + "\n\nIf this site is structurally running-specific by "
        "contract, add the enclosing function name to "
        "DOMAIN_RUNNING_ALLOWLIST_FUNCTIONS with a citation comment. "
        "Otherwise refactor to consult self._kind_to_domain_map "
        "instead of hardcoding a domain string."
    )


# ──────────────────────────────────────────────────────────────────
# INVARIANT 2 — strava_* literals only at backfill_config-derived sites
# ──────────────────────────────────────────────────────────────────

def test_strava_string_literals_only_at_backfill_config_sites() -> None:
    """Every ``strava_*`` string literal must sit within ±2 lines of
    a ``backfill_config`` reference — the wiring-site indirection ADR
    0038 § Decision sub-item 3 names. Module docstrings and the
    backfill-config docstring example are excluded by the windowed
    heuristic.
    """
    tree = _load_layer_ast()
    violations: list[tuple[int, str]] = []
    for lineno, value in _iter_strava_string_literals(tree):
        if not _is_inside_backfill_config_subscript(tree, lineno):
            violations.append((lineno, value))

    assert not violations, (
        "framework/vault/layer.py contains strava_* string literals "
        "outside backfill_config-derived sites:\n"
        + "\n".join(f"  line {ln} — literal {v!r}" for ln, v in violations)
        + "\n\nIf this is a wiring-site indirection, route the "
        "literal through self._backfill_config.get(...). If it's "
        "structurally Strava-specific by contract, document the "
        "exception and extend this test's allowlist."
    )


# ──────────────────────────────────────────────────────────────────
# INVARIANT 3 — _ALLOWED_KINDS module constant is gone
# ──────────────────────────────────────────────────────────────────

def test_allowed_kinds_module_constant_does_not_exist() -> None:
    """The pre-v7.6.0 module-level ``_ALLOWED_KINDS`` tuple constant
    is replaced by ``_FRAMEWORK_KIND_BASE`` (framework-tier only) plus
    instance-state ``_allowed_kinds`` populated at
    ``register_vault_layer()`` time. The old constant must not exist
    at module level — its presence would signal regression to the
    pre-amendment hardcoded shape.
    """
    tree = _load_layer_ast()
    module_assigns: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    module_assigns.append(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(
            node.target, ast.Name
        ):
            module_assigns.append(node.target.id)

    assert "_ALLOWED_KINDS" not in module_assigns, (
        "framework/vault/layer.py still defines _ALLOWED_KINDS at "
        "module level. ADR 0038 § Amendment 2026-05-19 replaced this "
        "with _FRAMEWORK_KIND_BASE (framework-tier only) plus "
        "VaultLayer._allowed_kinds populated at registration time. "
        "Remove the module constant and update call sites."
    )
    assert "_FRAMEWORK_KIND_BASE" in module_assigns, (
        "framework/vault/layer.py is missing the _FRAMEWORK_KIND_BASE "
        "constant introduced by ADR 0038 § Amendment 2026-05-19. "
        "Without it the framework-tier kind set has no canonical home."
    )


# ──────────────────────────────────────────────────────────────────
# INVARIANT 4 — module-level _domain_for_kind is gone
# ──────────────────────────────────────────────────────────────────

def test_domain_for_kind_module_function_does_not_exist() -> None:
    """The pre-v7.6.0 module-level ``_domain_for_kind`` helper has
    migrated to ``VaultLayer._domain_for_kind`` (instance method
    consulting ``self._kind_to_domain_map``). The module-level
    function must not exist — its presence would mean some call site
    is using the pre-amendment hardcoded mapping.
    """
    tree = _load_layer_ast()
    module_fns: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            module_fns.append(node.name)

    assert "_domain_for_kind" not in module_fns, (
        "framework/vault/layer.py still defines module-level "
        "_domain_for_kind. ADR 0038 § Amendment 2026-05-19 migrated "
        "this to VaultLayer._domain_for_kind which consults "
        "self._kind_to_domain_map. Remove the module function and "
        "update call sites to use the instance method."
    )
