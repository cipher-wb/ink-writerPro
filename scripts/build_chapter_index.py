#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build (or rebuild) the FAISS vector index over chapter memory cards.

Usage:
    python scripts/build_chapter_index.py --project-root /path/to/novel

The index is stored under <project_root>/.ink/chapter_index/ and consumed by
SemanticChapterRetriever at context-extraction time.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SCRIPTS_DIR = Path(__file__).resolve().parent
INK_WRITER_SCRIPTS = SCRIPTS_DIR.parent / "ink-writer" / "scripts"
if str(INK_WRITER_SCRIPTS) not in sys.path:
    # [FIX-11] removed: sys.path.insert(0, str(INK_WRITER_SCRIPTS))


def build_index(project_root: Path, rebuild: bool = False) -> dict:
    from ink_writer.core.infra.config import DataModulesConfig
    from ink_writer.core.index.index_manager import IndexManager
    from ink_writer.semantic_recall.chapter_index import ChapterCard, ChapterVectorIndex
    from ink_writer.semantic_recall.config import SemanticRecallConfig

    config = DataModulesConfig.from_project_root(project_root)
    sr_config = SemanticRecallConfig.from_project_root(project_root)
    index_dir = project_root / ".ink" / "chapter_index"

    if not rebuild and (index_dir / "chapters.faiss").exists():
        logger.info("Index already exists at %s (use --rebuild to force)", index_dir)
        return {"status": "skipped", "reason": "already_exists"}

    idx_mgr = IndexManager(config)
    rows = idx_mgr.get_recent_chapter_memory_cards(limit=9999)
    if not rows:
        logger.warning("No chapter memory cards found in index.db")
        return {"status": "empty", "chapters": 0}

    cards = [ChapterCard.from_db_row(row) for row in rows]
    cards.sort(key=lambda c: c.chapter)
    logger.info("Building vector index for %d chapters...", len(cards))

    index = ChapterVectorIndex(index_dir=index_dir, model_name=sr_config.model_name)
    index.build(cards)
    index.save()

    logger.info("Index saved to %s (%d vectors)", index_dir, index.card_count)
    return {"status": "ok", "chapters": len(cards), "index_dir": str(index_dir)}


def main():
    parser = argparse.ArgumentParser(description="Build chapter vector index")
    parser.add_argument("--project-root", type=str, required=True)
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()

    result = build_index(Path(args.project_root), rebuild=args.rebuild)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
