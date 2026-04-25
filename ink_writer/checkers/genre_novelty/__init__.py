"""genre-novelty-checker — M4 ink-init 策划期题材新颖度检查（spec §3.1）。"""

from ink_writer.checkers.genre_novelty.checker import check_genre_novelty
from ink_writer.checkers.genre_novelty.models import GenreNoveltyReport

__all__ = ["GenreNoveltyReport", "check_genre_novelty"]
