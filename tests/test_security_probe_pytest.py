"""
Pytest wrapper around the standalone security probe.

The probe at ``tests/security_probe.py`` is a deliberately self-
contained script: it can be run with ``python tests/security_probe.py``
on a machine without pytest installed.

This wrapper makes the same checks visible inside ``pytest`` runs, so a
failing security invariant fails CI regardless of which entry point the
suite was invoked through. It runs as part of the default ``pytest``
invocation CI uses (``pytest -v``); the ``@pytest.mark.probe`` marker
exists so the probe can ALSO be selected in isolation via
``pytest -m probe``, not to exclude it from the default run. The probe's
synthetic console banner is suppressed by capturing stdout below and is
surfaced only on failure.
"""

from __future__ import annotations

import io
import runpy
import sys
from pathlib import Path

import pytest

PROBE_PATH = Path(__file__).parent / "security_probe.py"


@pytest.mark.probe
def test_security_probe_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run the standalone probe under pytest and assert all invariants pass.

    The probe ends by calling ``sys.exit(0)`` on success and
    ``sys.exit(1)`` on failure. Capture both stdout (its progress log)
    and the exit code; convert non-zero into a pytest failure so the
    probe's output appears in the captured-stdout view.
    """
    captured = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured)
    try:
        runpy.run_path(str(PROBE_PATH), run_name="__main__")
    except SystemExit as exc:
        # Restore stdout before assertion so the captured output is visible.
        sys.stdout = sys.__stdout__
        if exc.code not in (0, None):
            pytest.fail(
                f"security_probe.py exited with code {exc.code}.\n\n"
                f"--- probe output ---\n{captured.getvalue()}"
            )
    finally:
        sys.stdout = sys.__stdout__
