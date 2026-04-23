"""Case library exceptions."""
from __future__ import annotations


class CaseLibraryError(Exception):
    """Base class for case library errors."""


class CaseValidationError(CaseLibraryError):
    """Raised when a case dict fails JSON Schema validation."""


class CaseNotFoundError(CaseLibraryError):
    """Raised when a case_id does not exist in the library."""


class DuplicateCaseError(CaseLibraryError):
    """Raised when ingesting raw_text whose hash matches an existing case."""
