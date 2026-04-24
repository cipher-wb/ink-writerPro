"""Preflight-specific exceptions."""
from __future__ import annotations


class PreflightError(Exception):
    """Raised when preflight is configured to abort on failure.

    Carries the list of failing check names so callers can surface them
    without re-parsing the message.
    """

    def __init__(self, failed_check_names: list[str], message: str) -> None:
        super().__init__(message)
        self.failed_check_names = list(failed_check_names)
        self.message = message
