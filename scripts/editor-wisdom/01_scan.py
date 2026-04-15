#!/usr/bin/env python3
"""Scan 编辑星河 data source and produce raw_index.json."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

DEFAULT_SOURCE = Path("/Users/cipher/Desktop/星河编辑")
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "editor-wisdom"

PLATFORM_MAP = {
    "编辑星河": "xhs",
    "编辑星河_抖音": "douyin",
}


def file_hash(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def scan(source_dir: Path, output_dir: Path) -> dict[str, int]:
    output_dir.mkdir(parents=True, exist_ok=True)
    index: list[dict] = []
    skipped: list[str] = []

    for md_file in sorted(source_dir.rglob("*.md")):
        rel = md_file.relative_to(source_dir)
        parts = rel.parts
        platform = PLATFORM_MAP.get(parts[0], "unknown") if parts else "unknown"

        try:
            text = md_file.read_text(encoding="utf-8")
        except Exception as e:
            skipped.append(f"{md_file}\t{e}")
            continue

        title = ""
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                title = stripped.lstrip("#").strip()
                break

        index.append({
            "path": str(md_file),
            "filename": md_file.name,
            "title": title,
            "platform": platform,
            "word_count": len(text),
            "file_hash": file_hash(md_file),
        })

    index_path = output_dir / "raw_index.json"
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")

    skip_path = output_dir / "skipped.log"
    skip_path.write_text("\n".join(skipped) if skipped else "", encoding="utf-8")

    return {"indexed": len(index), "skipped": len(skipped)}


def main() -> None:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SOURCE
    output = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUTPUT_DIR

    if not source.is_dir():
        print(f"Error: source directory not found: {source}", file=sys.stderr)
        sys.exit(1)

    stats = scan(source, output)
    print(f"Indexed: {stats['indexed']}, Skipped: {stats['skipped']}")
    print(f"Output: {output / 'raw_index.json'}")


if __name__ == "__main__":
    main()
