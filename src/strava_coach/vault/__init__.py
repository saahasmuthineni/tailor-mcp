"""
Vault package — Obsidian integration for the biosensor-to-LLM framework.

Exports:
    VaultWriter   Post-execute hook that archives analytics as markdown notes.
    VaultChild    ChildMCP with 7 tools for reading, searching, and annotating.
"""

from .writer import VaultWriter
from .child import VaultChild

__all__ = ["VaultWriter", "VaultChild"]
