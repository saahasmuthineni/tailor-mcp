"""
Tests for vault/rescan.py — bidirectional sync via filesystem mtime.
"""

import os
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from tailor.framework.vault.rescan import rescan_vault, revalidate_file
from tailor.framework.vault.storage import VaultStorage
from tailor.framework.vault.writer import VaultWriter


def _make_writer(vault: Path, data: Path) -> VaultWriter:
    return VaultWriter(
        vault_path=vault,
        data_dir=data,
        vaultable_tools=set(),
        max_hr=195,
    )


def _write_raw_theme(
    vault: Path,
    slug: str,
    status: str = "open",
    body_extra: str = "",
) -> Path:
    """Write a minimal theme .md directly to disk (no writer)."""
    path = vault / "themes" / f"{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (
        "---\n"
        "domain: vault\n"
        "note_type: theme\n"
        f"slug: \"{slug}\"\n"
        f"title: \"{slug.title()}\"\n"
        f"status: \"{status}\"\n"
        'opened: "2026-01-01"\n'
        'last_updated: "2026-01-01"\n'
        "linked_runs: []\n"
        "tags:\n  - theme\n"
        "---\n"
        f"# {slug.title()}\n\n"
        "## Hypothesis\n\n"
        "Some hypothesis.\n\n"
        f"{body_extra}"
    )
    path.write_text(content, encoding="utf-8")
    return path


class TestRevalidateFile:
    def test_new_file_added_to_index(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            vault = Path(v)
            writer = _make_writer(vault, Path(d))
            _write_raw_theme(vault, "new-theme")
            assert writer._storage.get_note("themes/new-theme.md") is None

            changed = revalidate_file("themes/new-theme.md", vault, writer._storage)
            assert changed is True
            assert writer._storage.get_note("themes/new-theme.md") is not None
            writer.close()

    def test_unchanged_file_skipped(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            vault = Path(v)
            writer = _make_writer(vault, Path(d))
            _write_raw_theme(vault, "x")
            revalidate_file("themes/x.md", vault, writer._storage)
            # Second call with no mtime change — must be a no-op
            changed = revalidate_file("themes/x.md", vault, writer._storage)
            assert changed is False
            writer.close()

    def test_modified_file_reindexed(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            vault = Path(v)
            writer = _make_writer(vault, Path(d))
            path = _write_raw_theme(vault, "drift")
            revalidate_file("themes/drift.md", vault, writer._storage)

            # Modify the file contents + bump mtime
            new_content = path.read_text(encoding="utf-8").replace(
                'status: "open"', 'status: "resolved"'
            )
            path.write_text(new_content, encoding="utf-8")
            future = time.time_ns() + 10_000_000_000  # 10 s in the future
            os.utime(path, ns=(future, future))

            changed = revalidate_file("themes/drift.md", vault, writer._storage)
            assert changed is True
            theme = writer._storage.get_theme("drift")
            assert theme is not None
            assert theme["status"] == "resolved"
            writer.close()

    def test_deleted_file_removed_from_index(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            vault = Path(v)
            writer = _make_writer(vault, Path(d))
            path = _write_raw_theme(vault, "gone")
            revalidate_file("themes/gone.md", vault, writer._storage)
            assert writer._storage.get_note("themes/gone.md") is not None

            path.unlink()
            changed = revalidate_file("themes/gone.md", vault, writer._storage)
            assert changed is True
            assert writer._storage.get_note("themes/gone.md") is None
            writer.close()

    def test_path_traversal_rejected(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            vault = Path(v)
            writer = _make_writer(vault, Path(d))
            assert revalidate_file("../../etc/passwd", vault, writer._storage) is False
            writer.close()


class TestRescanVault:
    def test_counts_added_files(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            vault = Path(v)
            writer = _make_writer(vault, Path(d))
            _write_raw_theme(vault, "a")
            _write_raw_theme(vault, "b")
            counts = rescan_vault(vault, writer._storage)
            assert counts["added"] == 2
            assert counts["modified"] == 0
            assert counts["deleted"] == 0
            writer.close()

    def test_counts_modified_files(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            vault = Path(v)
            writer = _make_writer(vault, Path(d))
            path = _write_raw_theme(vault, "a")
            rescan_vault(vault, writer._storage)

            path.write_text(path.read_text(encoding="utf-8") + "\n\nextra\n", encoding="utf-8")
            future = time.time_ns() + 10_000_000_000
            os.utime(path, ns=(future, future))

            counts = rescan_vault(vault, writer._storage)
            assert counts["modified"] == 1
            writer.close()

    def test_counts_deleted_files(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            vault = Path(v)
            writer = _make_writer(vault, Path(d))
            path = _write_raw_theme(vault, "x")
            rescan_vault(vault, writer._storage)
            path.unlink()

            counts = rescan_vault(vault, writer._storage)
            assert counts["deleted"] == 1
            writer.close()

    def test_unchanged_file_skipped(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            vault = Path(v)
            writer = _make_writer(vault, Path(d))
            _write_raw_theme(vault, "x")
            rescan_vault(vault, writer._storage)
            counts = rescan_vault(vault, writer._storage)
            assert counts["skipped"] == 1
            assert counts["modified"] == 0
            writer.close()

    def test_tmp_files_ignored(self):
        with TemporaryDirectory() as v, TemporaryDirectory() as d:
            vault = Path(v)
            writer = _make_writer(vault, Path(d))
            tmp = vault / "themes" / ".vault_tmp_ignore.md"
            tmp.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text("partial", encoding="utf-8")
            counts = rescan_vault(vault, writer._storage)
            assert counts["added"] == 0
            writer.close()
