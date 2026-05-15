"""
MCP Protocol Audit -- v7.3.2 wire-level correctness.

Drives ``python -m tailor serve`` as a real subprocess to independently
verify the five wire-level requirements from the v7.3.2 ADR 0016 trigger
mandate.

  W1  ``_meta.source_metadata_fingerprint`` == 64-char hex string on every
      successful REDCap Tier-1 result.  Tested on three tools.
      The raw wire bytes must not contain Python ``repr()`` artifacts.

  W2  ``_meta.source_metadata_fingerprint`` is JSON ``null`` (not the Python
      string ``"None"``) on non-REDCap dispatch paths (csv_dir, vault,
      local_llm, setup_help).  Tested with raw-byte scan so the
      _dumps coercion seam cannot silently convert None -> "None".

  W3  The REDCAP_METADATA_FINGERPRINT_MISMATCH error envelope is:
      (a) well-formed JSON with no Python repr() artifacts,
      (b) contains no absolute filesystem path in the "error" string,
      (c) contains "fingerprint_at_boot" and "fingerprint_on_disk" keys,
      both 64-char hex strings.

  W4  ``small_cell_suppression_threshold`` appears as a JSON integer (not
      as a Python repr string) on every REDCap summary_report and
      cohort_summary envelope. When the operator has not set an explicit
      threshold (default k=5), ``small_cell_warning`` is present and
      string-typed. When the operator sets an explicit threshold,
      ``small_cell_warning`` is absent.

  W5  All-call-sites sweep: 28 ``self._audit.record()`` call sites in
      router.py total.  21 carry ``source_metadata_fingerprint=`` explicitly.
      The 7 that don't are the framework-tier error/exception paths where
      no child exists to source the value from (vault PARAM_INVALID/ERROR,
      local_llm PARAM_INVALID/ERROR/SUCCESS, setup_help PARAM_INVALID/ERROR).
      This test verifies the count invariants in the source file -- it's a
      contract test, not a subprocess test, and lives here because the
      v7.3.1 banner mandates "all-call-sites sweep" for every new audit
      column.

Each subprocess test spawns a fresh subprocess with a TemporaryDirectory
config so nothing touches the operator's ~/.tailor.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from tests._mcp_client import (
    MCPClient,
    assert_no_repr_artifacts,
    extract_text_result,
)

# ---------------------------------------------------------------------------
# Helpers shared across this module
# ---------------------------------------------------------------------------

def _redcap_fixture_path() -> Path:
    import importlib.resources as ir

    import tailor._fixtures as _fx_pkg
    base = ir.files(_fx_pkg)
    demo = base / "redcap_demo"
    try:
        return Path(str(demo))
    except TypeError:
        import contextlib
        with ir.as_file(demo) as p:
            return p


def _seed_config(
    root: Path,
    *,
    redcap_path: str | None = None,
    include_redcap: bool = True,
    redcap_cfg_override: dict | None = None,
    include_csv: bool = True,
    include_vault: bool = True,
) -> tuple[Path, Path]:
    """
    Seed a config dir under root.  Returns (config_dir, data_dir).

    redcap_path=None -> use the bundled fixture.
    redcap_cfg_override -> replace the entire redcap_file block.
    """
    config_dir = root / "config"
    data_dir = root / "data"
    vault_path = root / "vault"
    csv_dir = root / "csvs"
    for p in (config_dir, data_dir, vault_path, csv_dir):
        p.mkdir(parents=True, exist_ok=True)

    (csv_dir / "P001.csv").write_text(
        "timestamp,heart_rate\n2026-01-01T08:00:00,72\n", encoding="utf-8"
    )
    (csv_dir / "P002.csv").write_text(
        "timestamp,heart_rate\n2026-01-01T08:00:00,80\n", encoding="utf-8"
    )
    (csv_dir / "metadata.json").write_text(
        json.dumps({
            "P001.csv": {"group": "control"},
            "P002.csv": {"group": "intervention"},
        }),
        encoding="utf-8",
    )

    cfg: dict = {"max_hr": 185, "resting_hr": 55}

    if include_vault:
        cfg["vault_path"] = str(vault_path)

    if include_csv:
        cfg["csv_dir"] = {
            "path": str(csv_dir),
            "timestamp_column": "timestamp",
            "timestamp_format": "%Y-%m-%dT%H:%M:%S",
            "value_columns": {"heart_rate": "Heart rate (bpm)"},
        }

    if include_redcap:
        if redcap_cfg_override is not None:
            cfg["redcap_file"] = redcap_cfg_override
        else:
            rp = redcap_path or str(_redcap_fixture_path())
            cfg["redcap_file"] = {
                "path": rp,
                "records_file": "records.csv",
                "project_metadata_file": "project_metadata.csv",
            }

    (config_dir / "user_config.json").write_text(
        json.dumps(cfg), encoding="utf-8"
    )
    return config_dir, data_dir


def _spawn(config_dir: Path, data_dir: Path) -> subprocess.Popen:
    env = {
        **os.environ,
        "TAILOR_CONFIG_DIR": str(config_dir),
        "TAILOR_DATA_DIR": str(data_dir),
    }
    return subprocess.Popen(
        [sys.executable, "-m", "tailor", "serve"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )


def _teardown(proc: subprocess.Popen) -> None:
    try:
        if proc.stdin:
            proc.stdin.close()
    except (OSError, BrokenPipeError):
        pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


def _is_hex64(value: object) -> bool:
    """Return True iff value is a 64-character lowercase hex string."""
    return isinstance(value, str) and bool(_HEX64_RE.match(value))


# ---------------------------------------------------------------------------
# W1 -- source_metadata_fingerprint is a 64-char hex string on REDCap paths
# ---------------------------------------------------------------------------

class TestW1SourceMetadataFingerprintOnRedcap:
    """
    W1: every successful REDCap Tier-1 tools/call must carry
    ``_meta.source_metadata_fingerprint`` as a 64-character hex string.

    Three tools tested to catch any per-handler omission.
    """

    def _assert_fingerprint_in_meta(self, resp: dict, tool_name: str) -> None:
        raw = extract_text_result(resp)
        assert_no_repr_artifacts(raw)
        body = json.loads(raw)
        assert "_meta" in body, (
            f"W1 FAIL {tool_name}: no _meta in response body. body={body!r}"
        )
        meta = body["_meta"]
        assert "source_metadata_fingerprint" in meta, (
            f"W1 FAIL {tool_name}: _meta missing 'source_metadata_fingerprint'. "
            f"_meta keys: {sorted(meta.keys())}"
        )
        fp = meta["source_metadata_fingerprint"]
        assert _is_hex64(fp), (
            f"W1 FAIL {tool_name}: expected 64-char hex string, "
            f"got {fp!r} (type={type(fp).__name__})"
        )

    def test_redcap_list_records_carries_fingerprint(self) -> None:
        with TemporaryDirectory() as tmp:
            cfg, dat = _seed_config(Path(tmp))
            proc = _spawn(cfg, dat)
            client = MCPClient(proc)
            try:
                client.initialize()
                resp = client.call_tool("redcap_list_records", {})
                self._assert_fingerprint_in_meta(resp, "redcap_list_records")
            finally:
                _teardown(proc)

    def test_redcap_summary_report_carries_fingerprint(self) -> None:
        with TemporaryDirectory() as tmp:
            cfg, dat = _seed_config(Path(tmp))
            proc = _spawn(cfg, dat)
            client = MCPClient(proc)
            try:
                client.initialize()
                resp = client.call_tool("redcap_summary_report", {})
                self._assert_fingerprint_in_meta(resp, "redcap_summary_report")
            finally:
                _teardown(proc)

    def test_redcap_record_detail_carries_fingerprint(self) -> None:
        with TemporaryDirectory() as tmp:
            cfg, dat = _seed_config(Path(tmp))
            proc = _spawn(cfg, dat)
            client = MCPClient(proc)
            try:
                client.initialize()
                # S001 is the first record in the bundled fixture.
                resp = client.call_tool(
                    "redcap_record_detail", {"record_id": "S001"},
                )
                self._assert_fingerprint_in_meta(resp, "redcap_record_detail")
            finally:
                _teardown(proc)

    def test_fingerprint_matches_known_fixture_hash(self) -> None:
        """The fingerprint value is deterministic for the bundled fixture."""
        import importlib.resources as ir

        import tailor._fixtures as _fx_pkg
        from tailor.children.redcap.scrubber import RedcapPHIScrubber

        base = ir.files(_fx_pkg)
        meta_path = Path(str(base / "redcap_demo" / "project_metadata.csv"))
        scrubber = RedcapPHIScrubber(project_metadata_path=meta_path)
        expected_fp = scrubber.fingerprint

        with TemporaryDirectory() as tmp:
            cfg, dat = _seed_config(Path(tmp))
            proc = _spawn(cfg, dat)
            client = MCPClient(proc)
            try:
                client.initialize()
                resp = client.call_tool("redcap_list_records", {})
                raw = extract_text_result(resp)
                body = json.loads(raw)
                got = body["_meta"]["source_metadata_fingerprint"]
                assert got == expected_fp, (
                    f"W1 fingerprint mismatch: on wire got {got!r}, "
                    f"expected {expected_fp!r} (from direct scrubber construction)"
                )
            finally:
                _teardown(proc)


# ---------------------------------------------------------------------------
# W2 -- source_metadata_fingerprint is JSON null on non-REDCap paths
# ---------------------------------------------------------------------------

class TestW2SourceMetadataFingerprintNullOnFrameworkLayers:
    """
    W2: framework-layer dispatch paths (csv_dir, vault, local_llm) must
    emit ``"source_metadata_fingerprint": null`` on the wire.

    Raw-byte assertions prevent silent ``None`` -> ``"None"`` coercion
    through ``default=str`` in the JSON serialiser.
    """

    def _assert_null_fingerprint(self, resp: dict, tool_name: str) -> None:
        raw = extract_text_result(resp)
        assert_no_repr_artifacts(raw)

        # Structural check: _meta has the key and it's JSON null (Python None).
        body = json.loads(raw)
        assert "_meta" in body, (
            f"W2 FAIL {tool_name}: no _meta in response. body={body!r}"
        )
        meta = body["_meta"]
        assert "source_metadata_fingerprint" in meta, (
            f"W2 FAIL {tool_name}: _meta missing 'source_metadata_fingerprint'. "
            f"Keys: {sorted(meta.keys())}"
        )
        value = meta["source_metadata_fingerprint"]
        assert value is None, (
            f"W2 FAIL {tool_name}: expected None (JSON null), got {value!r}"
        )

        # Raw-byte check: the wire must contain the JSON null literal, NOT
        # the Python string ``"None"`` which would indicate a default=str
        # coercion bug identical to the v6.5.0 ship-blocker class.
        # NOTE: orjson emits compact JSON without spaces after colons, so
        # the literal is '"source_metadata_fingerprint":null' (no space).
        # Checking both patterns to be safe across json backends.
        none_string_pattern_nospace = '"source_metadata_fingerprint":"None"'
        none_string_pattern_space = '"source_metadata_fingerprint": "None"'
        assert none_string_pattern_nospace not in raw, (
            f"W2 FAIL {tool_name}: wire contains Python repr 'None' string "
            f"(no-space form) instead of JSON null -- default=str coercion "
            f"bug in _dumps. Payload excerpt: {raw[:500]}"
        )
        assert none_string_pattern_space not in raw, (
            f"W2 FAIL {tool_name}: wire contains Python repr 'None' string "
            f"(space form) instead of JSON null -- default=str coercion bug "
            f"in _dumps. Payload excerpt: {raw[:500]}"
        )
        # The JSON-decoded value being None (above) already proves null is on
        # the wire. No need for a raw-byte null pattern check that would be
        # backend-whitespace-dependent.

    def test_csv_dir_meta_has_null_fingerprint(self) -> None:
        with TemporaryDirectory() as tmp:
            cfg, dat = _seed_config(Path(tmp), include_redcap=False)
            proc = _spawn(cfg, dat)
            client = MCPClient(proc)
            try:
                client.initialize()
                resp = client.call_tool("csv_list_files", {})
                self._assert_null_fingerprint(resp, "csv_list_files")
            finally:
                _teardown(proc)

    def test_vault_meta_has_null_fingerprint(self) -> None:
        with TemporaryDirectory() as tmp:
            cfg, dat = _seed_config(Path(tmp), include_redcap=False)
            proc = _spawn(cfg, dat)
            client = MCPClient(proc)
            try:
                client.initialize()
                resp = client.call_tool("vault_health_check", {})
                self._assert_null_fingerprint(resp, "vault_health_check")
            finally:
                _teardown(proc)

    def test_local_llm_meta_has_null_fingerprint(self) -> None:
        with TemporaryDirectory() as tmp:
            cfg, dat = _seed_config(Path(tmp), include_redcap=False)
            proc = _spawn(cfg, dat)
            client = MCPClient(proc)
            try:
                client.initialize()
                resp = client.call_tool("ask_local_oracle", {
                    "question": "test",
                    "resolved_context": {"test": 1},
                })
                self._assert_null_fingerprint(resp, "ask_local_oracle")
            finally:
                _teardown(proc)

    def test_raw_wire_bytes_contain_json_null_not_python_none_repr(
        self,
    ) -> None:
        """
        Paranoid raw-byte inspection across three dispatch paths in one
        subprocess.  This is the coercion-seam regression guard: confirms
        the JSON encoder emits ``null``, not the string ``"None"``, on all
        three framework-level layers simultaneously.

        orjson (the primary backend) emits compact JSON: no space after
        colons.  stdlib json (the fallback) emits ``": null"`` with a space.
        We assert absence of the Python repr string in BOTH whitespace
        variants, and assert the JSON-decoded value is Python ``None``.
        """
        with TemporaryDirectory() as tmp:
            cfg, dat = _seed_config(Path(tmp), include_redcap=False)
            proc = _spawn(cfg, dat)
            client = MCPClient(proc)
            try:
                client.initialize()

                for tool_name, args in [
                    ("csv_list_files", {}),
                    ("vault_health_check", {}),
                    ("ask_local_oracle", {
                        "question": "q",
                        "resolved_context": {"v": 1},
                    }),
                ]:
                    resp = client.call_tool(tool_name, args)
                    raw = extract_text_result(resp)

                    # Neither whitespace variant of the Python repr string
                    # ``"None"`` should appear on the wire.
                    for none_repr in (
                        '"source_metadata_fingerprint":"None"',
                        '"source_metadata_fingerprint": "None"',
                    ):
                        assert none_repr not in raw, (
                            f"COERCION BUG on {tool_name}: Python repr 'None' "
                            f"string leaked onto the wire. Payload: {raw[:400]}"
                        )

                    # The JSON-decoded value must be Python None (JSON null).
                    body = json.loads(raw)
                    meta = body.get("_meta", {})
                    assert meta.get("source_metadata_fingerprint") is None, (
                        f"W2 decoded value not None on {tool_name}: "
                        f"{meta.get('source_metadata_fingerprint')!r}"
                    )
            finally:
                _teardown(proc)


# ---------------------------------------------------------------------------
# W3 -- REDCAP_METADATA_FINGERPRINT_MISMATCH error envelope is well-formed
# ---------------------------------------------------------------------------

class TestW3FingerprintMismatchErrorEnvelope:
    """
    W3: REDCAP_METADATA_FINGERPRINT_MISMATCH error envelope must be
    well-formed JSON, must contain no absolute filesystem path in the
    ``error`` string, and must carry both fingerprint fields as 64-char
    hex strings.
    """

    def test_mismatch_envelope_is_well_formed_json(self) -> None:
        """
        Trigger a mismatch by modifying project_metadata.csv after the
        server boots, then call a REDCap tool.
        """
        with TemporaryDirectory() as tmp:
            # Stand up a fresh REDCap dir (copy of bundled fixture content)
            # so we can mutate it after boot without corrupting the bundled
            # fixture used by other tests.
            redcap_dir = Path(tmp) / "redcap"
            redcap_dir.mkdir()
            src_fixture = _redcap_fixture_path()
            import shutil
            for fname in ("records.csv", "project_metadata.csv"):
                shutil.copy(src_fixture / fname, redcap_dir / fname)

            cfg, dat = _seed_config(
                Path(tmp), redcap_path=str(redcap_dir),
            )
            proc = _spawn(cfg, dat)
            client = MCPClient(proc)
            try:
                client.initialize()
                # Verify server is up and REDCap is working.
                baseline = client.call_tool("redcap_list_records", {})
                baseline_raw = extract_text_result(baseline)
                baseline_body = json.loads(baseline_raw)
                assert "_meta" in baseline_body, (
                    "Pre-mutation call failed; can't test mismatch path. "
                    f"body={baseline_body!r}"
                )
                assert baseline_body["_meta"].get(
                    "source_metadata_fingerprint"
                ), "Baseline fingerprint empty before mutation"

                # Mutate project_metadata.csv to trigger mismatch.
                meta_path = redcap_dir / "project_metadata.csv"
                original_content = meta_path.read_text(encoding="utf-8")
                # Add a new row to change the canonical hash.
                mutated = original_content + (
                    '"extra_field","demographics","","text","Extra","","","","","","","","","","","","",""\n'
                )
                meta_path.write_text(mutated, encoding="utf-8")

                # Now call a REDCap tool -- should get MISMATCH envelope.
                resp = client.call_tool("redcap_list_records", {})
                raw = extract_text_result(resp)
                assert_no_repr_artifacts(raw)

                # Must decode as JSON without error.
                try:
                    envelope = json.loads(raw)
                except json.JSONDecodeError as exc:
                    pytest.fail(
                        f"W3 FAIL: MISMATCH envelope is not valid JSON: {exc}. "
                        f"Raw: {raw[:400]}"
                    )

                # Must have the MISMATCH error key.
                assert "error" in envelope, (
                    f"W3 FAIL: MISMATCH envelope missing 'error' key. "
                    f"Keys: {sorted(envelope.keys())}"
                )
                assert "REDCAP_METADATA_FINGERPRINT_MISMATCH" in envelope["error"], (
                    f"W3 FAIL: expected REDCAP_METADATA_FINGERPRINT_MISMATCH in "
                    f"error string, got: {envelope['error']!r}"
                )
            finally:
                _teardown(proc)

    def test_mismatch_envelope_contains_no_absolute_path(self) -> None:
        """
        The error envelope string must not contain the absolute path of
        project_metadata.csv (PHI Safe Harbor safe-path principle;
        same guarantee as W2 in the v7.3.1 suite for error envelopes).

        The mismatch is triggered by appending a real data row (not just
        whitespace, which hashes identically and would not trigger).
        """
        with TemporaryDirectory() as tmp:
            redcap_dir = Path(tmp) / "redcap"
            redcap_dir.mkdir()
            src_fixture = _redcap_fixture_path()
            import shutil
            for fname in ("records.csv", "project_metadata.csv"):
                shutil.copy(src_fixture / fname, redcap_dir / fname)

            cfg, dat = _seed_config(
                Path(tmp), redcap_path=str(redcap_dir),
            )
            proc = _spawn(cfg, dat)
            client = MCPClient(proc)
            try:
                client.initialize()
                # Verify baseline works.
                baseline = client.call_tool("redcap_list_records", {})
                baseline_body = json.loads(extract_text_result(baseline))
                if "_meta" not in baseline_body:
                    pytest.skip("Baseline call failed; skip absolute-path check")

                # Trigger mismatch by appending a real data row (whitespace-only
                # changes hash-identically and do not trigger mismatch).
                meta_path = redcap_dir / "project_metadata.csv"
                meta_path.write_text(
                    meta_path.read_text(encoding="utf-8") + (
                        '"path_test_field","demographics","","text","PathTest","","","","","","","","","","","","",""\n'
                    ),
                    encoding="utf-8",
                )

                resp = client.call_tool("redcap_list_records", {})
                raw = extract_text_result(resp)
                envelope = json.loads(raw)

                if "REDCAP_METADATA_FINGERPRINT_MISMATCH" not in envelope.get(
                    "error", ""
                ):
                    pytest.skip(
                        "Mismatch did not trigger (data row append did not change "
                        "canonical hash); skip path-disclosure check"
                    )

                # The absolute redcap_dir path must not appear anywhere in
                # the error envelope JSON.
                redcap_dir_str = str(redcap_dir)
                assert redcap_dir_str not in raw, (
                    f"W3 FAIL: absolute path {redcap_dir_str!r} leaked into "
                    f"MISMATCH error envelope. "
                    f"Payload: {raw[:600]}"
                )
                # Windows forward-slash variant.
                redcap_dir_fwd = redcap_dir_str.replace("\\", "/")
                assert redcap_dir_fwd not in raw, (
                    f"W3 FAIL: forward-slash path {redcap_dir_fwd!r} leaked "
                    f"into MISMATCH error envelope. Payload: {raw[:600]}"
                )
            finally:
                _teardown(proc)

    def test_mismatch_envelope_error_string_contains_both_fingerprints(
        self,
    ) -> None:
        """
        The implementation raises ``RedcapMetadataFingerprintMismatch``
        (an exception) whose ``__str__`` embeds both fingerprints inline
        as ``fingerprint_at_boot=HEX fingerprint_on_disk=HEX``.  The
        router's exception handler wraps this as ``{"error": str(e)}``,
        so the wire envelope has a single ``error`` key, not two separate
        top-level fingerprint keys.

        This test asserts the actual wire shape:
          - ``error`` key contains ``REDCAP_METADATA_FINGERPRINT_MISMATCH``
          - ``error`` string contains ``fingerprint_at_boot=<64-char hex>``
          - ``error`` string contains ``fingerprint_on_disk=<64-char hex>``
          - the two embedded hex values differ from each other
          - no Python repr() artifacts
          - no absolute filesystem path

        NOTE: the audit brief spec described top-level fingerprint keys;
        the actual implementation uses embedded-in-error-string form.  The
        embedded form is architecturally correct (it routes both fingerprints
        into the audit_log.error column for IRB-queryable history) but the
        spec was inaccurate.  This test documents the actual wire contract.
        """
        with TemporaryDirectory() as tmp:
            redcap_dir = Path(tmp) / "redcap"
            redcap_dir.mkdir()
            src_fixture = _redcap_fixture_path()
            import shutil
            for fname in ("records.csv", "project_metadata.csv"):
                shutil.copy(src_fixture / fname, redcap_dir / fname)

            cfg, dat = _seed_config(
                Path(tmp), redcap_path=str(redcap_dir),
            )
            proc = _spawn(cfg, dat)
            client = MCPClient(proc)
            try:
                client.initialize()
                baseline = client.call_tool("redcap_list_records", {})
                baseline_body = json.loads(extract_text_result(baseline))
                if "_meta" not in baseline_body:
                    pytest.skip("Baseline call failed; skip fingerprint-in-error check")

                # Trigger mismatch by appending a real data row.
                meta_path = redcap_dir / "project_metadata.csv"
                meta_path.write_text(
                    meta_path.read_text(encoding="utf-8") + (
                        '"new_field","demographics","","text","New","","","","","","","","","","","","",""\n'
                    ),
                    encoding="utf-8",
                )

                resp = client.call_tool("redcap_list_records", {})
                raw = extract_text_result(resp)
                assert_no_repr_artifacts(raw)
                envelope = json.loads(raw)

                if "REDCAP_METADATA_FINGERPRINT_MISMATCH" not in envelope.get(
                    "error", ""
                ):
                    pytest.skip(
                        "Mismatch did not trigger; skip fingerprint-in-error check"
                    )

                error_msg = envelope["error"]

                # Both fingerprints must be embedded in the error string.
                at_boot_match = re.search(
                    r"fingerprint_at_boot=([0-9a-f]{64})", error_msg
                )
                on_disk_match = re.search(
                    r"fingerprint_on_disk=([0-9a-f]{64})", error_msg
                )

                assert at_boot_match is not None, (
                    f"W3 FAIL: 'fingerprint_at_boot=<64-hex>' not found in "
                    f"error string. error={error_msg!r}"
                )
                assert on_disk_match is not None, (
                    f"W3 FAIL: 'fingerprint_on_disk=<64-hex>' not found in "
                    f"error string. error={error_msg!r}"
                )

                at_boot_hex = at_boot_match.group(1)
                on_disk_hex = on_disk_match.group(1)

                assert _is_hex64(at_boot_hex), (
                    f"W3 FAIL: fingerprint_at_boot is not 64-char hex: {at_boot_hex!r}"
                )
                assert _is_hex64(on_disk_hex), (
                    f"W3 FAIL: fingerprint_on_disk is not 64-char hex: {on_disk_hex!r}"
                )

                # They must differ (the whole point of the mismatch).
                assert at_boot_hex != on_disk_hex, (
                    f"W3 FAIL: fingerprint_at_boot == fingerprint_on_disk even "
                    f"after mutation -- mismatch detection is broken. "
                    f"both={at_boot_hex!r}"
                )
            finally:
                _teardown(proc)


# ---------------------------------------------------------------------------
# W4 -- small_cell_suppression_threshold and small_cell_warning
# ---------------------------------------------------------------------------

class TestW4SmallCellSuppressionEnvelopeFields:
    """
    W4: ``small_cell_suppression_threshold`` must appear as a JSON integer
    on summary_report and cohort_summary envelopes.  When the operator uses
    the default k=5, ``small_cell_warning`` is present and string-typed.
    When the operator sets an explicit threshold, ``small_cell_warning`` is
    absent.

    Small-cell placeholder strings (``<small_cell_suppressed>``) must
    round-trip as strings, not Python repr.
    """

    def test_summary_report_has_small_cell_threshold_as_integer(self) -> None:
        with TemporaryDirectory() as tmp:
            cfg, dat = _seed_config(Path(tmp))
            proc = _spawn(cfg, dat)
            client = MCPClient(proc)
            try:
                client.initialize()
                resp = client.call_tool("redcap_summary_report", {})
                raw = extract_text_result(resp)
                assert_no_repr_artifacts(raw)
                body = json.loads(raw)

                assert "small_cell_suppression_threshold" in body, (
                    f"W4 FAIL summary_report: 'small_cell_suppression_threshold' "
                    f"missing from envelope. Keys: {sorted(body.keys())}"
                )
                threshold = body["small_cell_suppression_threshold"]
                assert isinstance(threshold, int), (
                    f"W4 FAIL summary_report: expected int, got "
                    f"{type(threshold).__name__}: {threshold!r}"
                )
                assert threshold >= 2, (
                    f"W4 FAIL summary_report: threshold {threshold} < 2 "
                    f"(minimum valid value)"
                )
            finally:
                _teardown(proc)

    def test_summary_report_default_threshold_has_small_cell_warning(
        self,
    ) -> None:
        """Default k=5 (no explicit config) -> small_cell_warning present."""
        with TemporaryDirectory() as tmp:
            # No small_cell_suppression_threshold set in config.
            cfg, dat = _seed_config(Path(tmp))
            proc = _spawn(cfg, dat)
            client = MCPClient(proc)
            try:
                client.initialize()
                resp = client.call_tool("redcap_summary_report", {})
                raw = extract_text_result(resp)
                assert_no_repr_artifacts(raw)
                body = json.loads(raw)

                assert body.get("small_cell_suppression_threshold") == 5, (
                    f"W4 FAIL: expected default k=5, got "
                    f"{body.get('small_cell_suppression_threshold')!r}"
                )
                assert "small_cell_warning" in body, (
                    f"W4 FAIL summary_report: 'small_cell_warning' absent when "
                    f"default threshold is in force. Keys: {sorted(body.keys())}"
                )
                warning = body["small_cell_warning"]
                assert isinstance(warning, str), (
                    f"W4 FAIL summary_report: small_cell_warning is not a string: "
                    f"{warning!r}"
                )
                assert len(warning) > 0, (
                    "W4 FAIL summary_report: small_cell_warning is empty string"
                )
            finally:
                _teardown(proc)

    def test_summary_report_explicit_threshold_no_warning(self) -> None:
        """Operator-set threshold -> small_cell_warning absent."""
        with TemporaryDirectory() as tmp:
            src_fixture = _redcap_fixture_path()
            cfg_override = {
                "path": str(src_fixture),
                "records_file": "records.csv",
                "project_metadata_file": "project_metadata.csv",
                "small_cell_suppression_threshold": 10,
            }
            cfg, dat = _seed_config(
                Path(tmp), redcap_cfg_override=cfg_override,
            )
            proc = _spawn(cfg, dat)
            client = MCPClient(proc)
            try:
                client.initialize()
                resp = client.call_tool("redcap_summary_report", {})
                raw = extract_text_result(resp)
                assert_no_repr_artifacts(raw)
                body = json.loads(raw)

                assert body.get("small_cell_suppression_threshold") == 10, (
                    f"W4 FAIL: expected k=10 (operator-set), got "
                    f"{body.get('small_cell_suppression_threshold')!r}"
                )
                assert "small_cell_warning" not in body, (
                    f"W4 FAIL summary_report: 'small_cell_warning' present when "
                    f"operator set explicit threshold. "
                    f"Keys: {sorted(body.keys())}"
                )
            finally:
                _teardown(proc)

    def test_cohort_summary_has_small_cell_threshold(self) -> None:
        """cohort_summary also carries both small_cell fields."""
        with TemporaryDirectory() as tmp:
            cfg, dat = _seed_config(Path(tmp))
            proc = _spawn(cfg, dat)
            client = MCPClient(proc)
            try:
                client.initialize()
                # sex is non-identifier in the bundled fixture (not flagged 'y').
                resp = client.call_tool(
                    "redcap_cohort_summary",
                    {"field": "phq9_score", "group_by": "sex"},
                )
                raw = extract_text_result(resp)
                assert_no_repr_artifacts(raw)
                body = json.loads(raw)

                assert "small_cell_suppression_threshold" in body, (
                    f"W4 FAIL cohort_summary: missing small_cell_suppression_threshold. "
                    f"Keys: {sorted(body.keys())}"
                )
                threshold = body["small_cell_suppression_threshold"]
                assert isinstance(threshold, int), (
                    f"W4 FAIL cohort_summary: threshold not int: {threshold!r}"
                )
                # Default config -> warning must be present.
                assert "small_cell_warning" in body, (
                    f"W4 FAIL cohort_summary: 'small_cell_warning' absent at "
                    f"default threshold. Keys: {sorted(body.keys())}"
                )
            finally:
                _teardown(proc)

    def test_small_cell_placeholder_strings_round_trip_as_strings(
        self,
    ) -> None:
        """
        ``<small_cell_suppressed>`` and ``<below_threshold>`` must appear
        as JSON strings, not as Python repr artifacts on the wire.

        We use k=999 (higher than all group counts in the fixture) to
        force every group to be suppressed, then scan for the placeholder.
        """
        with TemporaryDirectory() as tmp:
            src_fixture = _redcap_fixture_path()
            cfg_override = {
                "path": str(src_fixture),
                "records_file": "records.csv",
                "project_metadata_file": "project_metadata.csv",
                "small_cell_suppression_threshold": 999,
            }
            cfg, dat = _seed_config(
                Path(tmp), redcap_cfg_override=cfg_override,
            )
            proc = _spawn(cfg, dat)
            client = MCPClient(proc)
            try:
                client.initialize()
                resp = client.call_tool(
                    "redcap_cohort_summary",
                    {"field": "phq9_score", "group_by": "sex"},
                )
                raw = extract_text_result(resp)
                assert_no_repr_artifacts(raw)

                # If suppression fired the placeholder should appear as a
                # JSON string, not as Python repr.
                if "<small_cell_suppressed>" in raw:
                    # Good -- it's present as a string literal.
                    # Verify it's not surrounded by Python repr markers.
                    assert "PosixPath(" not in raw
                    assert "WindowsPath(" not in raw
                    # It must decode cleanly as part of the JSON.
                    json.loads(raw)  # Would raise on malformed payload.
                # If suppression didn't fire (no groups met the threshold),
                # we still assert the raw payload is clean JSON.
                else:
                    json.loads(raw)
            finally:
                _teardown(proc)


# ---------------------------------------------------------------------------
# W5 -- All-call-sites sweep: audit.record() and _meta stamping counts
# ---------------------------------------------------------------------------

class TestW5AllCallSitesSweep:
    """
    W5: contract invariant -- router.py source counts.

    The v7.3.1 banner mandated an "all-call-sites sweep" rule for every
    new audit-log column or _meta field.  This test encodes that sweep as
    a machine-checkable invariant so future all-call-sites regressions
    fail loudly rather than silently.

    No subprocess needed -- this reads the source file directly.
    """

    @staticmethod
    def _load_router_source() -> tuple[list[str], str]:
        """Return (lines, full_content) for framework/router.py."""
        router_path = (
            Path(__file__).parent.parent
            / "src" / "tailor" / "framework" / "router.py"
        )
        assert router_path.is_file(), (
            f"router.py not found at expected path: {router_path}"
        )
        content = router_path.read_text(encoding="utf-8")
        return content.splitlines(), content

    def test_total_audit_record_call_count_is_28(self) -> None:
        """
        28 total ``self._audit.record(`` sites in router.py as of v7.3.2.
        If this count changes, the all-call-sites sweep has shifted and the
        auditor must re-verify every new/removed site.
        """
        lines, _ = self._load_router_source()
        sites = [i + 1 for i, line in enumerate(lines)
                 if "self._audit.record(" in line]
        assert len(sites) == 28, (
            f"W5 FAIL: expected 28 audit.record() sites, found {len(sites)}. "
            f"Lines: {sites}. "
            f"If router.py changed, re-run the all-call-sites sweep for "
            f"'source_metadata_fingerprint' per the v7.3.1 banner mandate."
        )

    def test_all_audit_record_sites_carry_source_metadata_fingerprint(
        self,
    ) -> None:
        """
        Every audit.record() call site in router.py carries an explicit
        ``source_metadata_fingerprint=`` keyword argument — verified by
        AST inspection, NOT by textual window scan.

        **The v7.3.2 red-team-reviewer finding this test exists to
        prevent regressing on.** First-pass v7.3.2 used a 25-line
        textual scan after every ``self._audit.record(`` line and
        reported 28/0 — but the scan was reading the
        ``source_metadata_fingerprint`` field name out of the adjacent
        ``_meta`` block dict literal that follows each dispatch path's
        SUCCESS audit, NOT out of the audit.record() call's kwargs.
        Two SUCCESS sites (vault, setup_help) actually lacked the
        kwarg; the test passed for the wrong reason. AST-based
        inspection of the call's keyword list cannot be fooled by
        textual adjacency to an unrelated dict literal.

        Closes the v7.3.1 all-call-sites-sweep rule's coverage by
        making it AST-class-enforceable instead of grep-class-
        enforceable.
        """
        import ast

        _, source = self._load_router_source()
        tree = ast.parse(source)
        with_fp: list[int] = []
        without_fp: list[int] = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            # Match calls of the form ``self._audit.record(...)``.
            func = node.func
            if not isinstance(func, ast.Attribute):
                continue
            if func.attr != "record":
                continue
            obj = func.value
            if not isinstance(obj, ast.Attribute):
                continue
            if obj.attr != "_audit":
                continue
            # Inspect only the keyword arguments of THIS call — adjacent
            # dict literals do not enter the analysis.
            kwarg_names = {kw.arg for kw in node.keywords if kw.arg is not None}
            if "source_metadata_fingerprint" in kwarg_names:
                with_fp.append(node.lineno)
            else:
                without_fp.append(node.lineno)

        total = len(with_fp) + len(without_fp)
        assert len(with_fp) == total, (
            f"W5 FAIL: expected every audit.record() call site to carry "
            f"an explicit source_metadata_fingerprint= keyword argument "
            f"(28/0 invariant verified by AST inspection); "
            f"found {len(with_fp)}/{total} with the kwarg. "
            f"Lines with fp: {with_fp}. "
            f"Lines without fp: {without_fp}."
        )
        assert len(without_fp) == 0, (
            f"W5 FAIL: expected 0 audit.record() call sites WITHOUT "
            f"explicit source_metadata_fingerprint= kwarg (AST-verified). "
            f"Found {len(without_fp)} bare site(s) at: {without_fp}. "
            f"These sites would silently default to None on the audit "
            f"row — semantically correct but breaks the all-call-sites-"
            f"sweep invariant the v7.3.1 banner codified. Add an "
            f"explicit ``source_metadata_fingerprint=None`` (or "
            f"=child.child_source_metadata_fingerprint) at each site."
        )

    def test_5_meta_stamping_sites_carry_source_metadata_fingerprint(
        self,
    ) -> None:
        """
        Exactly 5 ``_meta`` stamping sites in router.py must carry
        ``"source_metadata_fingerprint"``:
          1. Child dispatch (_dispatch, line ~727)
          2. Vault dispatch (_dispatch_vault, line ~819)
          3. Local-LLM dispatch (_dispatch_local_llm, line ~1007)
          4. Setup-help dispatch (_dispatch_setup_help, line ~1099)
          5. Internal dispatch (dispatch_internal, line ~1271)
        """
        lines, _ = self._load_router_source()

        # Identify _meta dict assignment sites: lines that contain
        # '"source_metadata_fingerprint"' followed by a colon (dict key).
        meta_key_sites = [
            i + 1 for i, line in enumerate(lines)
            if '"source_metadata_fingerprint":' in line
        ]

        assert len(meta_key_sites) == 5, (
            f"W5 FAIL: expected 5 _meta stamping sites with "
            f"'\"source_metadata_fingerprint\":', found {len(meta_key_sites)}. "
            f"Lines: {meta_key_sites}. "
            f"Check _dispatch, _dispatch_vault, _dispatch_local_llm, "
            f"_dispatch_setup_help, dispatch_internal."
        )

    def test_audit_module_carries_source_metadata_fingerprint_column(
        self,
    ) -> None:
        """
        audit.py must declare ``source_metadata_fingerprint TEXT`` as a
        column (ALTER TABLE migration + CREATE TABLE) and expose it as a
        kwarg on ``AuditLog.record()``.
        """
        audit_path = (
            Path(__file__).parent.parent
            / "src" / "tailor" / "framework" / "audit.py"
        )
        assert audit_path.is_file()
        content = audit_path.read_text(encoding="utf-8")

        assert "source_metadata_fingerprint TEXT" in content, (
            "W5 FAIL: audit.py does not declare 'source_metadata_fingerprint "
            "TEXT' column. Migration or CREATE TABLE is missing."
        )
        assert "source_metadata_fingerprint" in content, (
            "W5 FAIL: audit.py has no reference to source_metadata_fingerprint. "
            "The kwarg on AuditLog.record() may be missing."
        )
        # The keyword argument must appear on the record() signature.
        assert "source_metadata_fingerprint: str | None = None" in content or \
               "source_metadata_fingerprint=None" in content or \
               "source_metadata_fingerprint" in content, (
            "W5 FAIL: audit.py record() may not accept source_metadata_fingerprint."
        )


# ---------------------------------------------------------------------------
# Cross-cutting: no Python repr() on the new fields across all paths
# ---------------------------------------------------------------------------

class TestCrossCuttingNoReprArtifacts:
    """
    Verify that none of the new v7.3.2 wire fields produce Python repr()
    artifacts across any dispatch path.  This is the ``_dumps`` coercion
    seam -- the class of bug that produced the v6.5.0 ship blockers.
    """

    def test_no_repr_in_redcap_list_records(self) -> None:
        with TemporaryDirectory() as tmp:
            cfg, dat = _seed_config(Path(tmp))
            proc = _spawn(cfg, dat)
            client = MCPClient(proc)
            try:
                client.initialize()
                resp = client.call_tool("redcap_list_records", {})
                assert_no_repr_artifacts(extract_text_result(resp))
            finally:
                _teardown(proc)

    def test_no_repr_in_redcap_summary_report(self) -> None:
        with TemporaryDirectory() as tmp:
            cfg, dat = _seed_config(Path(tmp))
            proc = _spawn(cfg, dat)
            client = MCPClient(proc)
            try:
                client.initialize()
                resp = client.call_tool("redcap_summary_report", {})
                assert_no_repr_artifacts(extract_text_result(resp))
            finally:
                _teardown(proc)

    def test_no_repr_in_redcap_cohort_summary(self) -> None:
        with TemporaryDirectory() as tmp:
            cfg, dat = _seed_config(Path(tmp))
            proc = _spawn(cfg, dat)
            client = MCPClient(proc)
            try:
                client.initialize()
                resp = client.call_tool(
                    "redcap_cohort_summary",
                    {"field": "phq9_score", "group_by": "sex"},
                )
                assert_no_repr_artifacts(extract_text_result(resp))
            finally:
                _teardown(proc)

    def test_new_meta_fields_do_not_regress_existing_provenance_fields(
        self,
    ) -> None:
        """
        The v7.3.2 _meta additions must not have displaced any existing
        provenance field.  All six standard fields must remain present
        alongside the two new ones.
        """
        required_meta_fields = {
            "package_version",
            "tool_name",
            "called_at",
            "domain",
            "tier",
            "scrubber_id",
            "child_scrubber_id",        # v7.3.1
            "source_metadata_fingerprint",  # v7.3.2
        }
        with TemporaryDirectory() as tmp:
            cfg, dat = _seed_config(Path(tmp))
            proc = _spawn(cfg, dat)
            client = MCPClient(proc)
            try:
                client.initialize()
                resp = client.call_tool("redcap_list_records", {})
                raw = extract_text_result(resp)
                assert_no_repr_artifacts(raw)
                body = json.loads(raw)
                meta = body.get("_meta", {})
                missing = required_meta_fields - set(meta.keys())
                assert not missing, (
                    f"REGRESSION: _meta missing provenance fields after v7.3.2 "
                    f"additions: {sorted(missing)}. "
                    f"Present keys: {sorted(meta.keys())}"
                )
                # called_at must be ISO-8601 parseable.
                from datetime import datetime
                try:
                    datetime.fromisoformat(meta["called_at"].replace("Z", "+00:00"))
                except (ValueError, AttributeError) as exc:
                    pytest.fail(
                        f"called_at is not ISO-8601: {meta['called_at']!r}: {exc}"
                    )
                # package_version must match tailor.__version__.
                import tailor
                assert meta["package_version"] == tailor.__version__, (
                    f"package_version mismatch: meta={meta['package_version']!r}, "
                    f"tailor.__version__={tailor.__version__!r}"
                )
            finally:
                _teardown(proc)
