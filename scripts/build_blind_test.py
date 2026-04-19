#!/usr/bin/env python3
"""盲测工具 — US-602 验收脚本

用法:
    python3 scripts/build_blind_test.py --project-root /path/to/novel --samples 20

功能:
1. 从生成章节中抽样 N 章
2. 从 benchmark/reference_corpus/ 中抽样 N 章
3. 打乱混合，生成 benchmark/blind_test/ 目录
4. 输出评分表模板 benchmark/blind_test/rating_sheet.md
5. 汇总评分并生成 reports/blind_test_v13.md
"""

from __future__ import annotations

# US-010: ensure Windows stdio is UTF-8 wrapped when launched directly.
import os as _os_win_stdio
import sys as _sys_win_stdio
_ink_scripts = _os_win_stdio.path.join(
    _os_win_stdio.path.dirname(_os_win_stdio.path.abspath(__file__)),
    '../ink-writer/scripts',
)
if _os_win_stdio.path.isdir(_ink_scripts) and _ink_scripts not in _sys_win_stdio.path:
    _sys_win_stdio.path.insert(0, _ink_scripts)
try:
    from runtime_compat import enable_windows_utf8_stdio as _enable_utf8_stdio
    _enable_utf8_stdio()
except Exception:
    pass
import argparse
import json
import random
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


RATING_DIMENSIONS = [
    "吸引力 (1-10)",
    "AI 味 (1-10, 10=完全人写)",
    "人物塑造 (1-10)",
    "节奏 (1-10)",
    "情绪感染力 (1-10)",
]


@dataclass
class BlindTestConfig:
    samples_per_source: int = 10
    seed: int = 42
    min_readers: int = 5


@dataclass
class BlindSample:
    sample_id: str
    source: str  # "generated" or "reference"
    original_path: str
    blind_path: str


@dataclass
class BlindTestSet:
    samples: list[BlindSample] = field(default_factory=list)
    config: BlindTestConfig = field(default_factory=BlindTestConfig)

    def to_manifest(self) -> dict[str, Any]:
        return {
            "total_samples": len(self.samples),
            "generated_count": sum(
                1 for s in self.samples if s.source == "generated"
            ),
            "reference_count": sum(
                1 for s in self.samples if s.source == "reference"
            ),
            "dimensions": RATING_DIMENSIONS,
            "min_readers": self.config.min_readers,
            "samples": [
                {
                    "sample_id": s.sample_id,
                    "blind_path": s.blind_path,
                }
                for s in self.samples
            ],
        }

    def to_answer_key(self) -> dict[str, str]:
        return {s.sample_id: s.source for s in self.samples}


def build_blind_test(
    project_root: Path,
    reference_corpus: Path,
    output_dir: Path,
    config: Optional[BlindTestConfig] = None,
) -> BlindTestSet:
    """Build a blind test set by mixing generated and reference chapters."""
    if config is None:
        config = BlindTestConfig()

    output_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(config.seed)

    generated_dir = project_root / "正文"
    generated_files = sorted(generated_dir.glob("*.md")) if generated_dir.exists() else []
    reference_files = _collect_reference_samples(reference_corpus)

    gen_sample = rng.sample(
        generated_files, min(config.samples_per_source, len(generated_files))
    ) if generated_files else []
    ref_sample = rng.sample(
        reference_files, min(config.samples_per_source, len(reference_files))
    ) if reference_files else []

    samples: list[BlindSample] = []
    for i, f in enumerate(gen_sample):
        samples.append(BlindSample(
            sample_id="", source="generated",
            original_path=str(f), blind_path="",
        ))
    for i, f in enumerate(ref_sample):
        samples.append(BlindSample(
            sample_id="", source="reference",
            original_path=str(f), blind_path="",
        ))

    rng.shuffle(samples)

    for i, s in enumerate(samples):
        s.sample_id = f"S{i + 1:03d}"
        blind_filename = f"{s.sample_id}.md"
        s.blind_path = blind_filename
        src = Path(s.original_path)
        if src.exists():
            shutil.copy2(src, output_dir / blind_filename)

    test_set = BlindTestSet(samples=samples, config=config)

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(test_set.to_manifest(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    answer_key_path = output_dir / "answer_key.json"
    answer_key_path.write_text(
        json.dumps(test_set.to_answer_key(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    rating_sheet = _generate_rating_sheet(test_set)
    (output_dir / "rating_sheet.md").write_text(rating_sheet, encoding="utf-8")

    return test_set


def _collect_reference_samples(corpus_dir: Path) -> list[Path]:
    """Collect sample chapter files from the reference corpus."""
    files: list[Path] = []
    if not corpus_dir.exists():
        return files
    for book_dir in sorted(corpus_dir.iterdir()):
        if not book_dir.is_dir():
            continue
        for f in sorted(book_dir.glob("*.md")):
            files.append(f)
        for f in sorted(book_dir.glob("*.txt")):
            files.append(f)
    return files


def _generate_rating_sheet(test_set: BlindTestSet) -> str:
    lines = ["# 盲测评分表\n"]
    lines.append(f"评分维度：{', '.join(RATING_DIMENSIONS)}\n")
    lines.append(f"最低评审人数：{test_set.config.min_readers}\n")
    lines.append("---\n")

    for sample in test_set.samples:
        lines.append(f"## {sample.sample_id}\n")
        lines.append(f"文件：{sample.blind_path}\n")
        for dim in RATING_DIMENSIONS:
            lines.append(f"- {dim}: ___\n")
        lines.append("")

    return "\n".join(lines)


def generate_blind_test_report(
    ratings: dict[str, list[dict[str, float]]],
    answer_key: dict[str, str],
    output_path: Path,
) -> dict[str, Any]:
    """Aggregate ratings and compare generated vs reference scores."""
    gen_scores: dict[str, list[float]] = {d: [] for d in RATING_DIMENSIONS}
    ref_scores: dict[str, list[float]] = {d: [] for d in RATING_DIMENSIONS}

    for sample_id, reader_ratings in ratings.items():
        source = answer_key.get(sample_id, "unknown")
        target = gen_scores if source == "generated" else ref_scores
        for reader_rating in reader_ratings:
            for dim in RATING_DIMENSIONS:
                score = reader_rating.get(dim, 0)
                target[dim].append(score)

    result: dict[str, Any] = {"dimensions": {}}
    all_ratios: list[float] = []
    for dim in RATING_DIMENSIONS:
        gen_avg = sum(gen_scores[dim]) / len(gen_scores[dim]) if gen_scores[dim] else 0
        ref_avg = sum(ref_scores[dim]) / len(ref_scores[dim]) if ref_scores[dim] else 0
        ratio = gen_avg / ref_avg if ref_avg > 0 else 0
        all_ratios.append(ratio)
        result["dimensions"][dim] = {
            "generated_avg": round(gen_avg, 2),
            "reference_avg": round(ref_avg, 2),
            "ratio": round(ratio, 4),
            "passed": ratio >= 0.95,
        }

    result["overall_ratio"] = round(
        sum(all_ratios) / len(all_ratios), 4
    ) if all_ratios else 0
    result["passed"] = all(
        d["passed"] for d in result["dimensions"].values()
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    report = f"# 盲测报告 v13\n\n"
    report += f"总结果: {'PASS' if result['passed'] else 'FAIL'}\n\n"
    report += "| 维度 | 生成 | 对照 | 比值 | 结果 |\n|---|---|---|---|---|\n"
    for dim, data in result["dimensions"].items():
        status = "✅" if data["passed"] else "❌"
        report += f"| {dim} | {data['generated_avg']} | {data['reference_avg']} | {data['ratio']} | {status} |\n"

    output_path.write_text(report, encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description="盲测工具")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--samples", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    config = BlindTestConfig(samples_per_source=args.samples, seed=args.seed)
    project_root = Path(args.project_root)
    reference_corpus = Path("benchmark/reference_corpus")
    output_dir = Path("benchmark/blind_test")

    test_set = build_blind_test(project_root, reference_corpus, output_dir, config)
    print(f"Blind test set created: {len(test_set.samples)} samples")
    print(f"  Generated: {sum(1 for s in test_set.samples if s.source == 'generated')}")
    print(f"  Reference: {sum(1 for s in test_set.samples if s.source == 'reference')}")
    print(f"  Output: {output_dir}")
    print(f"  Rating sheet: {output_dir / 'rating_sheet.md'}")
    print(f"\nDistribute rating_sheet.md to ≥{config.min_readers} readers.")
    print("After collecting ratings, run with --aggregate to generate report.")


if __name__ == "__main__":
    main()
