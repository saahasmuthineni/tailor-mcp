"""
Vault package — Obsidian integration for the biosensor-to-LLM framework.

The vault is the **reorientation tier**: durable analytical memory that
persists across sessions.  Markdown files in the Obsidian vault are the
canonical record; vault.db is a query-optimization index.

Exports:
    VaultWriter   Post-execute hook that archives analytics as markdown notes.
    VaultLayer    Framework-level read/annotate interface (not a ChildMCP).
"""

from .layer import VaultLayer
from .writer import VaultWriter

__all__ = ["VaultWriter", "VaultLayer"]
