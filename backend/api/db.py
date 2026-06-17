"""Compatibility wrapper for legacy imports.

New backend code should import from ``core.db``.
"""

from core.db import *  # noqa: F401,F403
