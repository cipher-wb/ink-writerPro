"""Custom exceptions for the editor-wisdom module."""


class EditorWisdomIndexMissingError(RuntimeError):
    """Raised when config.enabled=true but required index files are missing."""
