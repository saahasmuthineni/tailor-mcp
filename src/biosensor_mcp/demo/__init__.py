"""
Demo mode — run the analytics pipeline against synthetic data.

No Strava account, OAuth tokens, or network access required.
"""

from .runner import run_demo

__all__ = ["run_demo"]
