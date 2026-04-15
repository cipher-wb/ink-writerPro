#!/usr/bin/env python3
"""De-duplicate and filter noise from raw_index.json."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "editor-wisdom"

NOISE_KEYWORDS = re.compile(r"登录|手机号|验证码")
MIN_BODY_CHARS = 50
MINHASH_THRESHOLD = 0.9
NUM_PERM = 128
NGRAM_SIZE = 3


def _char_ngrams(text: str, n: int = NGRAM_SIZE) -> list[str]:
    cleaned = re.sub(r"\s+", "", text)
    if len(cleaned) < n:
        return [cleaned]
    return [cleaned[i : i + n] for i in range(len(cleaned) - n + 1)]


def _minhash_signature(ngrams: list[str], num_perm: int = NUM_PERM) -> list[int]:
    if not ngrams:
        return [0] * num_perm
    sig = []
    for i in range(num_perm):
        min_val = min(
            int.from_bytes(
                hashlib.blake2b(f"{i}:{ng}".encode(), digest_size=4).digest(),
                "big",
            )
            for ng in ngrams
        )
        sig.append(min_val)
    return sig


def _jaccard_estimate(sig_a: list[int], sig_b: list[int]) -> float:
    if not sig_a:
        return 0.0
    return sum(a == b for a, b in zip(sig_a, sig_b)) / len(sig_a)


def _read_body(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except Exception:
        return ""


def clean(data_dir: Path) -> dict[str, int]:
    raw_path = data_dir / "raw_index.json"
    raw: list[dict] = json.loads(raw_path.read_text(encoding="utf-8"))

    kept: list[dict] = []
    dropped_short: list[str] = []
    dropped_noise: list[str] = []
    dropped_dup: list[str] = []

    kept_sigs: list[list[int]] = []

    for entry in raw:
        filename = entry["filename"]

        if NOISE_KEYWORDS.search(filename):
            dropped_noise.append(filename)
            continue

        body = _read_body(entry["path"])
        if len(body) < MIN_BODY_CHARS:
            dropped_short.append(filename)
            continue

        ngrams = _char_ngrams(body)
        sig = _minhash_signature(ngrams)

        is_dup = False
        for existing_sig in kept_sigs:
            if _jaccard_estimate(sig, existing_sig) > MINHASH_THRESHOLD:
                is_dup = True
                break

        if is_dup:
            dropped_dup.append(filename)
            continue

        kept.append(entry)
        kept_sigs.append(sig)

    data_dir.mkdir(parents=True, exist_ok=True)
    clean_path = data_dir / "clean_index.json"
    clean_path.write_text(json.dumps(kept, ensure_ascii=False, indent=2), encoding="utf-8")

    report_lines = [
        "# Cleanup Report\n",
        "## Summary\n",
        f"- Total input: {len(raw)}",
        f"- Kept: {len(kept)}",
        f"- Dropped (short <{MIN_BODY_CHARS} chars): {len(dropped_short)}",
        f"- Dropped (noise keywords): {len(dropped_noise)}",
        f"- Dropped (near-duplicate): {len(dropped_dup)}",
        "",
        "## Dropped Files\n",
        "### Short Content",
    ]
    for f in dropped_short[:20]:
        report_lines.append(f"- {f}")
    report_lines.append("")
    report_lines.append("### Noise Keywords")
    for f in dropped_noise[:20]:
        report_lines.append(f"- {f}")
    report_lines.append("")
    report_lines.append("### Near-Duplicates")
    for f in dropped_dup[:20]:
        report_lines.append(f"- {f}")

    report_path = data_dir / "cleanup_report.md"
    report_path.write_text("\n".join(report_lines), encoding="utf-8")

    return {
        "kept": len(kept),
        "dropped_short": len(dropped_short),
        "dropped_noise": len(dropped_noise),
        "dropped_dup": len(dropped_dup),
    }


def main() -> None:
    data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DATA_DIR

    if not (data_dir / "raw_index.json").exists():
        print("Error: raw_index.json not found. Run 01_scan.py first.", file=sys.stderr)
        sys.exit(1)

    stats = clean(data_dir)
    print(f"Kept: {stats['kept']}")
    print(f"Dropped — short: {stats['dropped_short']}, noise: {stats['dropped_noise']}, dup: {stats['dropped_dup']}")
    print(f"Output: {data_dir / 'clean_index.json'}")


if __name__ == "__main__":
    main()
