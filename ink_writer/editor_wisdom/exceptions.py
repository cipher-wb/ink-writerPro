"""Custom exceptions for the editor-wisdom module."""


class EditorWisdomIndexMissingError(RuntimeError):
    """Raised when config.enabled=true but required index files are missing."""


class EscapeHatchTriggered(RuntimeError):
    """US-015: raised when the review_gate's whole-chapter-rewrite escape hatch fires.

    Signals the orchestrator to re-run Step 2A (full rewrite) instead of another polish pass.
    Callers opt-in via `allow_escape_hatch=True`. The escape hatch fires at most once per
    chapter (enforced by caller tracking), preventing infinite rewrite loops.
    """

    def __init__(self, chapter_no: int, final_score: float, threshold: float, violations: list[dict]):
        self.chapter_no = chapter_no
        self.final_score = final_score
        self.threshold = threshold
        self.violations = violations
        super().__init__(
            f"Chapter {chapter_no} escape hatch triggered after 2 failed retries "
            f"(score={final_score}, threshold={threshold}). Re-run Step 2A."
        )
