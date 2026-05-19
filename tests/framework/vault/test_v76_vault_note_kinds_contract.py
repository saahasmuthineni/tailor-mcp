"""
v7.6.0 behavioral tests for the ``ChildMCP.vault_note_kinds`` contract
+ ``VaultLayer._compute_kind_metadata()`` registration-time wiring +
``vault_get_fitness_summary`` deprecation hint per ADR 0038 §
Amendment 2026-05-19.

Sibling to ``test_v76_vault_is_data_source_agnostic.py`` (AST-class
invariants). This file covers the *behavioural* contract:

- Default ``ChildMCP.vault_note_kinds`` returns ``()``.
- ``RunningChild.vault_note_kinds`` returns the three canonical kinds.
- ``VaultLayer._compute_kind_metadata`` extends ``_allowed_kinds`` and
  ``_kind_to_domain_map`` from registered children.
- ``vault_list_notes`` param validation accepts a kind contributed by
  a registered child after registration time.
- The deprecation log on ``_handle_fitness_summary`` emits once per
  process (idempotent).
"""

from __future__ import annotations

import logging

from tailor.children.running.child import RunningChild
from tailor.framework.interfaces import ChildMCP


def test_childmcp_default_vault_note_kinds_is_empty_tuple() -> None:
    """The ABC's default ``vault_note_kinds`` property returns ``()``.

    Backward-compatibility-by-construction (ADR 0038 § Amendment
    2026-05-19 § "Why option (a) over the alternatives"). Existing
    children (csv_dir, matlab_file, redcap_file, force_csv, emg_csv,
    template) inherit this default and do not need to override it
    until they choose to participate in vault snapshot rendering.
    """

    # Construct a minimal ChildMCP subclass that satisfies the
    # abstract surface without overriding vault_note_kinds.
    class _MinimalChild(ChildMCP):  # noqa: D401 — test fixture
        @property
        def domain(self) -> str:
            return "test"

        @property
        def display_name(self) -> str:
            return "Test child"

        @property
        def tool_definitions(self):
            return []

        @property
        def param_schemas(self) -> dict:
            return {}

        async def execute(self, tool_name: str, params: dict) -> dict:
            return {}

        async def estimate_cost(self, tool_name: str, params: dict):
            from tailor.framework.interfaces import CostEstimate
            return CostEstimate(tokens=0)

        def purge_cache(self, *, force: bool = False) -> dict:
            return {
                "rows_purged": 0,
                "tables_touched": [],
                "preserved": [],
                "reason": "no cache",
            }

    child = _MinimalChild()
    assert child.vault_note_kinds == ()


def test_running_child_vault_note_kinds_returns_three_canonical_kinds(
    tmp_path,
) -> None:
    """``RunningChild`` overrides ``vault_note_kinds`` to declare the
    three frontmatter ``note_type`` values its vaultable tools emit:
    ``run_report``, ``trend_report``, ``compare_runs``. This is the
    worked example of declaring child-specific vault kinds per ADR
    0038 § Amendment 2026-05-19.
    """
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    config_dir.mkdir()
    data_dir.mkdir()

    child = RunningChild(config_dir=config_dir, data_dir=data_dir)
    try:
        assert child.vault_note_kinds == (
            "run_report",
            "trend_report",
            "compare_runs",
        )
    finally:
        child.close()


def test_vault_layer_compute_kind_metadata_extends_from_children(
    tmp_path,
) -> None:
    """``VaultLayer._compute_kind_metadata()`` reads each registered
    child's ``vault_note_kinds`` and extends ``self._allowed_kinds``
    + ``self._kind_to_domain_map``. Verified via a minimal in-process
    RouterMCP that registers a fake child + the vault layer.
    """
    from tailor.framework.router import RouterMCP
    from tailor.framework.vault import VaultLayer
    from tailor.framework.vault.writer import VaultWriter

    vault_path = tmp_path / "vault"
    vault_path.mkdir()
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    class _FakeRunningChild(ChildMCP):
        @property
        def domain(self) -> str:
            return "running"

        @property
        def display_name(self) -> str:
            return "Running (fake)"

        @property
        def vault_note_kinds(self) -> tuple[str, ...]:
            return ("run_report", "trend_report", "compare_runs")

        @property
        def tool_definitions(self):
            return []

        @property
        def param_schemas(self) -> dict:
            return {}

        async def execute(self, tool_name: str, params: dict) -> dict:
            return {}

        async def estimate_cost(self, tool_name: str, params: dict):
            from tailor.framework.interfaces import CostEstimate
            return CostEstimate(tokens=0)

        def purge_cache(self, *, force: bool = False) -> dict:
            return {
                "rows_purged": 0,
                "tables_touched": [],
                "preserved": [],
                "reason": "no cache",
            }

    router = RouterMCP(name="test-v76", data_dir=data_dir)
    try:
        router.register_child(_FakeRunningChild())

        writer = VaultWriter(
            vault_path=vault_path,
            data_dir=data_dir,
            vaultable_tools=set(),
            max_hr=195,
        )
        vault = VaultLayer(vault_path=vault_path, vault_writer=writer)
        router.register_vault_layer(vault)

        # Framework-tier base + child-declared kinds in union.
        assert "theme" in vault._allowed_kinds
        assert "moment" in vault._allowed_kinds
        assert "failure_mode" in vault._allowed_kinds
        assert "dashboard" in vault._allowed_kinds
        assert "snapshot" in vault._allowed_kinds
        assert "run_report" in vault._allowed_kinds
        assert "trend_report" in vault._allowed_kinds
        assert "compare_runs" in vault._allowed_kinds

        # Kind → domain mapping populated from child's domain.
        assert vault._kind_to_domain_map["run_report"] == "running"
        assert vault._kind_to_domain_map["trend_report"] == "running"
        assert vault._kind_to_domain_map["compare_runs"] == "running"
        # Framework-tier mapping preserved.
        assert vault._kind_to_domain_map["theme"] == "vault"
        assert vault._kind_to_domain_map["moment"] == "vault"

        # Instance _domain_for_kind consults the same map.
        assert vault._domain_for_kind("run_report") == "running"
        assert vault._domain_for_kind("theme") == "vault"
        assert vault._domain_for_kind("dashboard") is None
        assert vault._domain_for_kind(None) is None
        assert vault._domain_for_kind("never_registered") is None
    finally:
        router.close()


def test_vault_list_notes_param_schema_accepts_child_contributed_kind(
    tmp_path,
) -> None:
    """After ``register_vault_layer()`` populates ``_allowed_kinds``,
    the ``vault_list_notes`` param schema's ``allowed_values`` includes
    every child-contributed kind alongside the framework-tier base.
    Verified by reading the param_schemas property dict directly.
    """
    from tailor.framework.interfaces import CostEstimate
    from tailor.framework.router import RouterMCP
    from tailor.framework.vault import VaultLayer
    from tailor.framework.vault.writer import VaultWriter

    vault_path = tmp_path / "vault"
    vault_path.mkdir()
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    class _FakeChild(ChildMCP):
        @property
        def domain(self) -> str:
            return "fake_domain"

        @property
        def display_name(self) -> str:
            return "Fake"

        @property
        def vault_note_kinds(self) -> tuple[str, ...]:
            return ("fake_report",)

        @property
        def tool_definitions(self):
            return []

        @property
        def param_schemas(self) -> dict:
            return {}

        async def execute(self, tool_name: str, params: dict) -> dict:
            return {}

        async def estimate_cost(self, tool_name: str, params: dict):
            return CostEstimate(tokens=0)

        def purge_cache(self, *, force: bool = False) -> dict:
            return {
                "rows_purged": 0,
                "tables_touched": [],
                "preserved": [],
                "reason": "no cache",
            }

    router = RouterMCP(name="test-v76", data_dir=data_dir)
    try:
        router.register_child(_FakeChild())
        writer = VaultWriter(
            vault_path=vault_path,
            data_dir=data_dir,
            vaultable_tools=set(),
            max_hr=195,
        )
        vault = VaultLayer(vault_path=vault_path, vault_writer=writer)
        router.register_vault_layer(vault)

        schemas = vault.param_schemas
        kind_schema = schemas["vault_list_notes"]["kind"]
        assert "fake_report" in kind_schema.allowed_values, (
            "vault_list_notes kind schema should accept "
            "child-contributed kinds after registration. Got: "
            f"{kind_schema.allowed_values}"
        )
        assert "theme" in kind_schema.allowed_values
        assert "snapshot" in kind_schema.allowed_values
    finally:
        router.close()


def test_fitness_summary_deprecation_hint_emits_once_per_layer(
    tmp_path, caplog
) -> None:
    """``_handle_fitness_summary`` emits a deprecation WARNING on
    first call per VaultLayer instance, idempotent on subsequent
    calls. The audit row is unaffected — this is a stderr-only
    deprecation hint per ADR 0038 § Amendment 2026-05-19 sub-item 7.
    """
    import asyncio

    from tailor.framework.router import RouterMCP
    from tailor.framework.vault import VaultLayer
    from tailor.framework.vault.writer import VaultWriter

    vault_path = tmp_path / "vault"
    vault_path.mkdir()
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    router = RouterMCP(name="test-v76", data_dir=data_dir)
    try:
        writer = VaultWriter(
            vault_path=vault_path,
            data_dir=data_dir,
            vaultable_tools=set(),
            max_hr=195,
        )
        vault = VaultLayer(vault_path=vault_path, vault_writer=writer)
        router.register_vault_layer(vault)

        with caplog.at_level(logging.WARNING, logger="tailor.vault"):
            asyncio.run(vault._handle_fitness_summary({}))
            asyncio.run(vault._handle_fitness_summary({}))
            asyncio.run(vault._handle_fitness_summary({}))

        deprecation_warnings = [
            r for r in caplog.records
            if "DEPRECATED in v7.6.0" in r.getMessage()
        ]
        assert len(deprecation_warnings) == 1, (
            "Deprecation hint should emit exactly once per VaultLayer "
            "instance (idempotent on subsequent calls). Got: "
            f"{len(deprecation_warnings)} emissions"
        )
    finally:
        router.close()
