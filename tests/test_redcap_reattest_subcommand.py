"""
Tests for the `tailor redcap reattest` CLI subcommand.

Per ADR 0003 § Amendment 2026-05-15. The operator runs this command
after a legitimate edit to ``project_metadata.csv`` (e.g. adding a new
survey instrument mid-enrollment) to re-establish the cryptographic
attestation of the trust-root state. Mismatch failures at REDCap call
time point the operator here as the documented recovery path.

Tests cover:
- Successful re-attestation writes a REATTEST row to audit.db.
- Aborting at the confirmation prompt writes nothing.
- Same-fingerprint path exits 0 without prompting.
- Missing user_config.json / redcap_file block / project_metadata.csv
  fail with helpful errors and rc=1.
- The audit row carries the new fingerprint, the scrubber id, and the
  REDCap domain — IRB-grade provenance.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

from tailor.__main__ import cmd_redcap_reattest

SNAKE_CASE_HEADER = "field_name,form_name,field_type,identifier\n"
ORIGINAL_BODY = (
    SNAKE_CASE_HEADER
    + "record_id,demographics,text,\n"
    + "participant_name,demographics,text,y\n"
    + "sex,demographics,radio,\n"
)
FLIPPED_BODY = (
    SNAKE_CASE_HEADER
    + "record_id,demographics,text,\n"
    + "participant_name,demographics,text,\n"  # y → blank (the attack)
    + "sex,demographics,radio,\n"
)


def _stamp_prior_attestation(audit_db: Path, fingerprint: str) -> None:
    """Write a prior REDCap audit row carrying ``fingerprint``.

    Simulates the state after `tailor serve` has run REDCap calls with
    the original metadata file in place.
    """
    audit_db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(audit_db)) as conn:
        conn.execute("""
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
                entity_id TEXT,
                scrubber_id TEXT,
                child_scrubber_id TEXT,
                source_metadata_fingerprint TEXT
            )
        """)
        conn.execute(
            "INSERT INTO audit_log "
            "(timestamp, domain, tool_name, tier, params, token_estimate, "
            " outcome, duration_ms, source_metadata_fingerprint) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "2026-05-15T00:00:00+00:00",
                "redcap_file",
                "redcap_list_records",
                1,
                "{}",
                100,
                "SUCCESS",
                0,
                fingerprint,
            ),
        )
        conn.commit()


def _build_tailor_dirs(
    tmp_path: Path,
    metadata_body: str,
) -> tuple[Path, Path, Path]:
    """Set up config_dir / data_dir / redcap_dir for a reattest run.
    Returns (config_dir, data_dir, redcap_dir).
    """
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    redcap_dir = tmp_path / "redcap"
    for d in (config_dir, data_dir, redcap_dir):
        d.mkdir()
    (redcap_dir / "project_metadata.csv").write_text(
        metadata_body, encoding="utf-8",
    )
    (config_dir / "user_config.json").write_text(
        json.dumps({"redcap_file": {"path": str(redcap_dir)}}),
        encoding="utf-8",
    )
    return config_dir, data_dir, redcap_dir


def _patch_config_and_data_dir(
    monkeypatch: pytest.MonkeyPatch,
    config_dir: Path,
    data_dir: Path,
) -> None:
    """Re-point the cmd_redcap_reattest module-level CONFIG_DIR /
    DATA_DIR at the test's temp dirs. cmd_redcap_reattest reads from
    ``tailor.__main__.CONFIG_DIR``/``DATA_DIR`` which are loaded at
    import time; monkeypatching the module globals is the test seam."""
    import tailor.__main__ as main_mod
    monkeypatch.setattr(main_mod, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(main_mod, "DATA_DIR", data_dir)


class TestReattestSuccessPath:
    def test_writes_reattest_audit_row_on_confirm(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys,
    ):
        """After an identifier-flag flip, the operator runs reattest
        and types yes; a REATTEST row lands in audit.db with the new
        fingerprint, the REDCap domain, and the redcap_metadata_flags
        scrubber id."""
        config_dir, data_dir, redcap_dir = _build_tailor_dirs(
            tmp_path, ORIGINAL_BODY,
        )
        _patch_config_and_data_dir(monkeypatch, config_dir, data_dir)

        # Compute the original fingerprint and stamp a prior audit row.
        from tailor.children.redcap import RedcapPHIScrubber
        original = RedcapPHIScrubber(redcap_dir / "project_metadata.csv")
        original_fp = original.fingerprint
        _stamp_prior_attestation(data_dir / "audit.db", original_fp)

        # Now the attacker flips the flag.
        (redcap_dir / "project_metadata.csv").write_text(
            FLIPPED_BODY, encoding="utf-8",
        )

        # Operator types yes at the prompt.
        monkeypatch.setattr("builtins.input", lambda _: "yes")

        cmd_redcap_reattest()

        # Read back the audit log to verify a REATTEST row landed.
        with sqlite3.connect(str(data_dir / "audit.db")) as conn:
            cur = conn.execute(
                "SELECT domain, tool_name, outcome, scrubber_id, "
                "       child_scrubber_id, source_metadata_fingerprint "
                "FROM audit_log WHERE outcome = 'REATTEST' "
                "ORDER BY id DESC LIMIT 1"
            )
            row = cur.fetchone()
        assert row is not None, "REATTEST row not written"
        (
            domain, tool_name, outcome, scrubber_id, child_scrubber_id,
            fingerprint,
        ) = row
        assert domain == "redcap_file"
        assert tool_name == "redcap_reattest"
        assert outcome == "REATTEST"
        assert child_scrubber_id == "redcap_metadata_flags"
        # Closes phi-irb-risk-reviewer 2026-05-15 Lens 2 VIOLATION:
        # ADR 0003's load-bearing invariant — every audit row carries
        # the framework scrubber_id so "did we scrub?" is a fact on
        # disk. The first-pass hand-rolled INSERT left this NULL; the
        # AuditLog.record() rewrite populates it with "noop" (the
        # framework default when no institutional subclass is wired).
        assert scrubber_id is not None, (
            "scrubber_id is NULL on REATTEST row — ADR 0003 invariant "
            "broken; the operator-CLI path was bypassing AuditLog.record()"
        )
        assert scrubber_id == "noop"
        # The fingerprint stamped is the NEW one, not the cached one.
        flipped = RedcapPHIScrubber(redcap_dir / "project_metadata.csv")
        assert fingerprint == flipped.fingerprint
        assert fingerprint != original_fp

    def test_abort_does_not_write_audit_row(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ):
        """The operator inspects the listing and types 'no'; the
        framework does NOT write a REATTEST row."""
        config_dir, data_dir, redcap_dir = _build_tailor_dirs(
            tmp_path, ORIGINAL_BODY,
        )
        _patch_config_and_data_dir(monkeypatch, config_dir, data_dir)

        from tailor.children.redcap import RedcapPHIScrubber
        original = RedcapPHIScrubber(redcap_dir / "project_metadata.csv")
        _stamp_prior_attestation(data_dir / "audit.db", original.fingerprint)

        (redcap_dir / "project_metadata.csv").write_text(
            FLIPPED_BODY, encoding="utf-8",
        )

        monkeypatch.setattr("builtins.input", lambda _: "no")

        with pytest.raises(SystemExit) as exc:
            cmd_redcap_reattest()
        assert exc.value.code == 0

        with sqlite3.connect(str(data_dir / "audit.db")) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM audit_log WHERE outcome = 'REATTEST'"
            ).fetchone()[0]
        assert count == 0, "REATTEST row written despite operator aborting"

    def test_listing_shows_field_state_with_flags(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys,
    ):
        """The reattest output must show every field with its
        identifier flag — this is the trust-affording surface."""
        config_dir, data_dir, redcap_dir = _build_tailor_dirs(
            tmp_path, ORIGINAL_BODY,
        )
        _patch_config_and_data_dir(monkeypatch, config_dir, data_dir)

        from tailor.children.redcap import RedcapPHIScrubber
        original = RedcapPHIScrubber(redcap_dir / "project_metadata.csv")
        _stamp_prior_attestation(data_dir / "audit.db", original.fingerprint)

        (redcap_dir / "project_metadata.csv").write_text(
            FLIPPED_BODY, encoding="utf-8",
        )
        monkeypatch.setattr("builtins.input", lambda _: "no")

        with pytest.raises(SystemExit):
            cmd_redcap_reattest()
        out = capsys.readouterr().out
        # The listing must contain every field name and its flag word.
        assert "record_id" in out
        assert "participant_name" in out
        assert "sex" in out
        # In FLIPPED_BODY, participant_name is no longer flagged — it
        # should show as `ok`, not IDENTIFIER. This is the visible
        # surface of the tamper attempt.
        # The exact format is "  participant_name    ok" — we just
        # check the absence of "IDENTIFIER" on the same row by
        # asserting at least one ok line follows participant_name.
        idx = out.index("participant_name")
        line_end = out.index("\n", idx)
        line = out[idx:line_end]
        assert "ok" in line.lower() or "identifier" not in line.lower()

    def test_listing_shows_cached_and_new_fingerprints(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys,
    ):
        config_dir, data_dir, redcap_dir = _build_tailor_dirs(
            tmp_path, ORIGINAL_BODY,
        )
        _patch_config_and_data_dir(monkeypatch, config_dir, data_dir)

        from tailor.children.redcap import RedcapPHIScrubber
        original = RedcapPHIScrubber(redcap_dir / "project_metadata.csv")
        _stamp_prior_attestation(data_dir / "audit.db", original.fingerprint)

        (redcap_dir / "project_metadata.csv").write_text(
            FLIPPED_BODY, encoding="utf-8",
        )
        monkeypatch.setattr("builtins.input", lambda _: "no")

        with pytest.raises(SystemExit):
            cmd_redcap_reattest()
        out = capsys.readouterr().out

        # Both fingerprints must appear in the output.
        assert original.fingerprint in out
        flipped = RedcapPHIScrubber(redcap_dir / "project_metadata.csv")
        assert flipped.fingerprint in out

    def test_no_prior_attestation_shows_baseline_framing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys,
    ):
        """On a fresh install with no prior REDCap calls, audit.db has
        no source_metadata_fingerprint rows. The reattest output must
        say so explicitly rather than hiding the absence."""
        config_dir, data_dir, redcap_dir = _build_tailor_dirs(
            tmp_path, ORIGINAL_BODY,
        )
        _patch_config_and_data_dir(monkeypatch, config_dir, data_dir)
        # Do NOT stamp a prior audit row.
        monkeypatch.setattr("builtins.input", lambda _: "no")

        with pytest.raises(SystemExit):
            cmd_redcap_reattest()
        out = capsys.readouterr().out
        assert "no prior attestation" in out.lower()


class TestReattestSameFingerprintShortCircuit:
    def test_exits_zero_when_fingerprints_agree(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys,
    ):
        """If the cached fingerprint matches the current on-disk
        fingerprint, the reattest ritual is unnecessary and exits 0
        without prompting (no audit row written)."""
        config_dir, data_dir, redcap_dir = _build_tailor_dirs(
            tmp_path, ORIGINAL_BODY,
        )
        _patch_config_and_data_dir(monkeypatch, config_dir, data_dir)

        from tailor.children.redcap import RedcapPHIScrubber
        original = RedcapPHIScrubber(redcap_dir / "project_metadata.csv")
        _stamp_prior_attestation(data_dir / "audit.db", original.fingerprint)

        # No file change. Input not patched — if reattest prompts,
        # the test would hang.
        with pytest.raises(SystemExit) as exc:
            cmd_redcap_reattest()
        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "agree" in out.lower() or "no reattest" in out.lower()


class TestReattestErrorPaths:
    def test_missing_user_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys,
    ):
        config_dir = tmp_path / "config"
        data_dir = tmp_path / "data"
        config_dir.mkdir()
        data_dir.mkdir()
        # No user_config.json written.
        _patch_config_and_data_dir(monkeypatch, config_dir, data_dir)
        with pytest.raises(SystemExit) as exc:
            cmd_redcap_reattest()
        assert exc.value.code == 1
        err = capsys.readouterr().err
        assert "user_config.json" in err

    def test_no_redcap_file_block(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys,
    ):
        config_dir = tmp_path / "config"
        data_dir = tmp_path / "data"
        config_dir.mkdir()
        data_dir.mkdir()
        (config_dir / "user_config.json").write_text(
            json.dumps({"max_hr": 195}), encoding="utf-8",
        )
        _patch_config_and_data_dir(monkeypatch, config_dir, data_dir)
        with pytest.raises(SystemExit) as exc:
            cmd_redcap_reattest()
        assert exc.value.code == 1
        err = capsys.readouterr().err
        assert "redcap_file" in err

    def test_metadata_file_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys,
    ):
        config_dir = tmp_path / "config"
        data_dir = tmp_path / "data"
        redcap_dir = tmp_path / "redcap"
        for d in (config_dir, data_dir, redcap_dir):
            d.mkdir()
        (config_dir / "user_config.json").write_text(
            json.dumps({"redcap_file": {"path": str(redcap_dir)}}),
            encoding="utf-8",
        )
        _patch_config_and_data_dir(monkeypatch, config_dir, data_dir)
        with pytest.raises(SystemExit) as exc:
            cmd_redcap_reattest()
        assert exc.value.code == 1
        err = capsys.readouterr().err
        assert "project_metadata.csv not found" in err


class TestReattestDispatcher:
    def test_subcommand_dispatches_reattest(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ):
        """`tailor redcap reattest` → cmd_redcap_reattest()."""
        from tailor.__main__ import cmd_redcap

        config_dir, data_dir, redcap_dir = _build_tailor_dirs(
            tmp_path, ORIGINAL_BODY,
        )
        _patch_config_and_data_dir(monkeypatch, config_dir, data_dir)
        monkeypatch.setattr(sys, "argv", ["tailor", "redcap", "reattest"])
        # No prior attestation → output written, no prompt because
        # cached == new fingerprint? Actually no prior attestation
        # means cached is None, so they differ; we need to handle the
        # prompt.
        monkeypatch.setattr("builtins.input", lambda _: "no")
        with pytest.raises(SystemExit):
            cmd_redcap()

    def test_unknown_subcommand_exits_nonzero(
        self, monkeypatch: pytest.MonkeyPatch, capsys,
    ):
        from tailor.__main__ import cmd_redcap
        monkeypatch.setattr(sys, "argv", ["tailor", "redcap", "nonsense"])
        with pytest.raises(SystemExit) as exc:
            cmd_redcap()
        assert exc.value.code == 1
        out = capsys.readouterr().out
        assert "nonsense" in out
        assert "reattest" in out

    def test_no_subcommand_exits_nonzero(
        self, monkeypatch: pytest.MonkeyPatch, capsys,
    ):
        from tailor.__main__ import cmd_redcap
        monkeypatch.setattr(sys, "argv", ["tailor", "redcap"])
        with pytest.raises(SystemExit) as exc:
            cmd_redcap()
        assert exc.value.code == 1
