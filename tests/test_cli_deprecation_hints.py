"""
Regression tests for the v7.1.0 / ADR 0035 CLI verb deprecation shims.

Per ADR 0035 § Decision item 1, ``tailor demo`` and ``tailor tour`` are
renamed to ``tailor walkthrough`` and ``tailor fitting-room`` in
v7.1.0. Both old verbs continue to work for one cycle (removed in
v7.2.0) and print a stderr deprecation hint that names the new verb
and the ADR.

These tests lock the hint shape:

- the substring ``[deprecation]`` appears in stderr
- the substring ``ADR 0035`` appears in stderr
- the new verb's name appears in stderr (so a recipient who sees
  the hint can act on it immediately)
- nothing leaks to stdout (stdout is the MCP wire and ``run_demo``
  consumes it; the hint goes to stderr by design)

The handler bodies forward to the new verb's handler, so we mock the
forward target out and exercise only the deprecation-hint emission.
"""

from __future__ import annotations

import pytest


class TestDemoDeprecationHint:
    """``tailor demo`` -> ``tailor walkthrough`` (ADR 0035 § Decision 1)."""

    def test_demo_prints_deprecation_hint_to_stderr(
        self, monkeypatch: pytest.MonkeyPatch, capsys,
    ) -> None:
        # Stub the forward target so we don't actually run the demo
        # in this unit test.
        called: list[bool] = []

        def _fake_walkthrough() -> None:
            called.append(True)

        monkeypatch.setattr("tailor.__main__.cmd_walkthrough", _fake_walkthrough)

        from tailor.__main__ import cmd_demo
        cmd_demo()

        captured = capsys.readouterr()
        # Hint went to stderr, not stdout.
        assert "[deprecation]" in captured.err
        assert "ADR 0035" in captured.err
        # Names the new verb explicitly.
        assert "walkthrough" in captured.err
        # Forwarded to the new handler.
        assert called == [True]

    def test_demo_hint_does_not_pollute_stdout(
        self, monkeypatch: pytest.MonkeyPatch, capsys,
    ) -> None:
        """stdout is the MCP wire; the deprecation hint MUST NOT leak
        there. A future refactor that prints the hint to sys.stdout
        (instead of sys.stderr) would break Claude Desktop's MCP
        handshake on a recipient using the deprecated verb."""

        monkeypatch.setattr("tailor.__main__.cmd_walkthrough", lambda: None)

        from tailor.__main__ import cmd_demo
        cmd_demo()
        captured = capsys.readouterr()
        assert "[deprecation]" not in captured.out
        assert "ADR 0035" not in captured.out


class TestTourDeprecationHint:
    """``tailor tour`` -> ``tailor fitting-room`` (ADR 0035 § Decision 1)."""

    def test_tour_prints_deprecation_hint_to_stderr(
        self, monkeypatch: pytest.MonkeyPatch, capsys,
    ) -> None:
        called: list[bool] = []

        def _fake_fitting_room() -> None:
            called.append(True)

        monkeypatch.setattr(
            "tailor.__main__.cmd_fitting_room", _fake_fitting_room,
        )

        from tailor.__main__ import cmd_tour
        cmd_tour()

        captured = capsys.readouterr()
        assert "[deprecation]" in captured.err
        assert "ADR 0035" in captured.err
        assert "fitting-room" in captured.err
        assert called == [True]

    def test_tour_hint_does_not_pollute_stdout(
        self, monkeypatch: pytest.MonkeyPatch, capsys,
    ) -> None:
        """Same MCP-wire integrity argument as the demo variant."""
        monkeypatch.setattr(
            "tailor.__main__.cmd_fitting_room", lambda: None,
        )

        from tailor.__main__ import cmd_tour
        cmd_tour()
        captured = capsys.readouterr()
        assert "[deprecation]" not in captured.out
        assert "ADR 0035" not in captured.out


class TestDispatchTableContainsBothNewAndDeprecatedVerbs:
    """The v7.1.0 dispatch table must accept both the new verbs
    (``walkthrough`` / ``fitting-room``) and the deprecated aliases
    (``demo`` / ``tour``). A future refactor that removes one of the
    new entries would break the rename; a future refactor that removes
    the deprecation alias before v7.2.0 would break the one-cycle
    deprecation commitment in ADR 0035 § Decision item 1."""

    def test_all_four_verbs_present_in_dispatch_table(self) -> None:
        # Inspect the dispatch table by reading the function source for
        # the `commands = {...}` dict in main(). This is cheap and
        # avoids actually invoking the CLI.
        import inspect

        from tailor import __main__ as main_mod

        source = inspect.getsource(main_mod.main)
        # New verbs.
        assert '"walkthrough"' in source
        assert '"fitting-room"' in source
        # Deprecated aliases — present through v7.1.0 per ADR 0035.
        assert '"demo"' in source
        assert '"tour"' in source
