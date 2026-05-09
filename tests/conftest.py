"""
Shared pytest fixtures and configuration for the tailor test suite.

What lives here:

- The ``probe`` marker registration. The standalone
  ``tests/security_probe.py`` script can also be invoked under pytest
  via the wrapper at ``tests/test_security_probe_pytest.py``; that
  wrapper is gated by ``@pytest.mark.probe`` so the probe surfaces
  visibly in CI output without polluting routine ``pytest -v`` runs
  with its synthetic console banners.

- ``tmp_data_dir`` and ``tmp_vault_dirs`` fixtures — boilerplate-
  reduction for the ``TemporaryDirectory`` + ``mkdir`` pattern that
  appears in every router/vault test. Existing tests that already
  use ``TemporaryDirectory()`` directly are not required to migrate.

Intentionally small: the goal is to give new tests a starting point,
not to refactor the existing suite. The MockChild definitions in
``tests/framework/test_router.py`` stay inline because they're used
exclusively from that file.
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers so ``-m`` and ``-W`` invocations work."""
    config.addinivalue_line(
        "markers",
        "probe: standalone security_probe.py wrapped under pytest. "
        "Run with `pytest -m probe`.",
    )


@pytest.fixture
def tmp_data_dir() -> Path:
    """Yield a fresh data dir under a TemporaryDirectory.

    Most router tests need a writable directory for ``audit.db`` and
    other SQLite files. This fixture replaces the recurring pattern:

        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "data"
            data_dir.mkdir()
            ...

    The TemporaryDirectory is scoped to the test and auto-cleaned.
    """
    with TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir) / "data"
        data_dir.mkdir()
        yield data_dir


@pytest.fixture
def tmp_vault_dirs() -> tuple[Path, Path]:
    """Yield ``(vault_path, data_dir)`` under a single TemporaryDirectory.

    Vault-layer tests need both a vault directory (markdown notes) and
    a data directory (SQLite index + audit log). They must share a
    parent so artifacts get cleaned up together.
    """
    with TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        vault_path = root / "vault"
        vault_path.mkdir()
        data_dir = root / "data"
        data_dir.mkdir()
        yield vault_path, data_dir
