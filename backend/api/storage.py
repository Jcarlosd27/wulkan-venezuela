"""Compatibility wrapper for legacy imports.

New backend code should import from ``core.storage``.
"""

from core.storage import *  # noqa: F401,F403
