"""
Source package initialization
"""

import sys


def _force_utf8_console():
    """
    Make stdout/stderr tolerate the emoji used throughout this project.

    On Windows the console defaults to a legacy code page (cp1252), so a bare
    print("✅ ...") raises UnicodeEncodeError. That exception surfaced inside
    the RAG startup path and took the whole engine down with a misleading
    "'charmap' codec can't encode character" message. Re-encoding as UTF-8 with
    errors="replace" keeps logging cosmetic instead of fatal.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            # Stream already detached or replaced by a test harness — ignore
            pass


_force_utf8_console()

from .config import Config, SYSTEM_PROMPTS  # noqa: E402

__all__ = ["Config", "SYSTEM_PROMPTS"]
