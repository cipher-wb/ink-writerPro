"""Cultural lexicon injection module for genre-specific vocabulary."""

from ink_writer.cultural_lexicon.config import CulturalLexiconConfig, load_config
from ink_writer.cultural_lexicon.context_injection import (
    CulturalLexiconSection,
    build_cultural_lexicon_section,
)
from ink_writer.cultural_lexicon.loader import LexiconEntry, load_lexicon

__all__ = [
    "CulturalLexiconConfig",
    "CulturalLexiconSection",
    "LexiconEntry",
    "build_cultural_lexicon_section",
    "load_config",
    "load_lexicon",
]
