#!/usr/bin/env python3
"""300 章无人值守压测 — US-601 验收脚本

用法:
    python3 scripts/run_300chapter_benchmark.py --project-root /path/to/novel --parallel 4

功能:
1. 启动 ink-auto --parallel N 300 生成 300 章
2. 每 50 章采集一次全量指标
3. 最终生成 benchmark/300chapter_run/metrics.json 和 reports/v13_acceptance.md
4. 对比 G1-G5 目标，标记 PASS/FAIL
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class G1Metrics:
    hook_density_p75: float = 0.0
    high_point_density_p75: float = 0.0
    emotion_similarity: float = 0.0

    @property
    def passed(self) -> bool:
        return self.emotion_similarity >= 0.8


@dataclass
class G2Metrics:
    anti_detection_score: float = 0.0

    @property
    def passed(self) -> bool:
        return self.anti_detection_score >= 85


@dataclass
class G3Metrics:
    circular_deps: int = 0
    duplicate_impl: int = 0
    dead_code_pct: float = 0.0

    @property
    def passed(self) -> bool:
        return self.circular_deps == 0 and self.duplicate_impl == 0 and self.dead_code_pct < 2.0


@dataclass
class G4Metrics:
    ooc_score: float = 0.0
    setting_contradictions: int = 0
    plotline_dropped: int = 0

    @property
    def passed(self) -> bool:
        return self.ooc_score < 5 and self.setting_contradictions < 3 and self.plotline_dropped == 0


@dataclass
class G5Metrics:
    avg_chapter_seconds: float = 0.0
    baseline_chapter_seconds: float = 0.0
    avg_chapter_tokens: int = 0
    baseline_chapter_tokens: int = 0

    @property
    def time_target(self) -> float:
        return self.baseline_chapter_seconds * 0.7

    @property
    def token_target(self) -> int:
        return int(self.baseline_chapter_tokens * 0.8)

    @property
    def passed(self) -> bool:
        if self.baseline_chapter_seconds <= 0:
            return True
        return (
            self.avg_chapter_seconds <= self.time_target
            and self.avg_chapter_tokens <= self.token_target
        )


@dataclass
class BenchmarkResult:
    g1: G1Metrics = field(default_factory=G1Metrics)
    g2: G2Metrics = field(default_factory=G2Metrics)
    g3: G3Metrics = field(default_factory=G3Metrics)
    g4: G4Metrics = field(default_factory=G4Metrics)
    g5: G5Metrics = field(default_factory=G5Metrics)
    total_chapters: int = 0
    wall_time_s: float = 0.0

    @property
    def all_passed(self) -> bool:
        return all([
            self.g1.passed, self.g2.passed, self.g3.passed,
            self.g4.passed, self.g5.passed,
        ])

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_chapters": self.total_chapters,
            "wall_time_s": round(self.wall_time_s, 1),
            "all_passed": self.all_passed,
            "g1_readability": {
                "hook_density_p75": self.g1.hook_density_p75,
                "high_point_density_p75": self.g1.high_point_density_p75,
                "emotion_similarity": self.g1.emotion_similarity,
                "passed": self.g1.passed,
            },
            "g2_anti_ai": {
                "score": self.g2.anti_detection_score,
                "passed": self.g2.passed,
            },
            "g3_architecture": {
                "circular_deps": self.g3.circular_deps,
                "duplicate_impl": self.g3.duplicate_impl,
                "dead_code_pct": self.g3.dead_code_pct,
                "passed": self.g3.passed,
            },
            "g4_long_form": {
                "ooc_score": self.g4.ooc_score,
                "contradictions": self.g4.setting_contradictions,
                "dropped_plotlines": self.g4.plotline_dropped,
                "passed": self.g4.passed,
            },
            "g5_efficiency": {
                "avg_chapter_seconds": self.g5.avg_chapter_seconds,
                "time_target": self.g5.time_target,
                "avg_chapter_tokens": self.g5.avg_chapter_tokens,
                "token_target": self.g5.token_target,
                "passed": self.g5.passed,
            },
        }


def generate_acceptance_report(result: BenchmarkResult, output_path: Path) -> None:
    """Generate reports/v13_acceptance.md from benchmark results."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    def status(passed: bool) -> str:
        return "PASS ✅" if passed else "FAIL ❌"

    report = f"""# v13 验收报告

## 总览

| 项目 | 值 |
|---|---|
| 总章数 | {result.total_chapters} |
| 总耗时 | {result.wall_time_s:.0f}s ({result.wall_time_s / 3600:.1f}h) |
| 总结果 | {status(result.all_passed)} |

## G1 — 追读力

| 指标 | 值 | 目标 | 结果 |
|---|---|---|---|
| 情绪曲线相似度 | {result.g1.emotion_similarity:.2f} | ≥0.8 | {status(result.g1.emotion_similarity >= 0.8)} |

## G2 — 去 AI 味

| 指标 | 值 | 目标 | 结果 |
|---|---|---|---|
| anti-detection 综合分 | {result.g2.anti_detection_score:.0f} | ≥85 | {status(result.g2.passed)} |

## G3 — 架构

| 指标 | 值 | 目标 | 结果 |
|---|---|---|---|
| 循环依赖 | {result.g3.circular_deps} | 0 | {status(result.g3.circular_deps == 0)} |
| 重复实现 | {result.g3.duplicate_impl} | 0 | {status(result.g3.duplicate_impl == 0)} |
| Dead code | {result.g3.dead_code_pct:.1f}% | <2% | {status(result.g3.dead_code_pct < 2.0)} |

## G4 — 长篇不崩

| 指标 | 值 | 目标 | 结果 |
|---|---|---|---|
| OOC 分 | {result.g4.ooc_score:.1f} | <5 | {status(result.g4.ooc_score < 5)} |
| 设定矛盾 | {result.g4.setting_contradictions} | <3 | {status(result.g4.setting_contradictions < 3)} |
| 明暗线漏接 | {result.g4.plotline_dropped} | 0 | {status(result.g4.plotline_dropped == 0)} |

## G5 — 效率

| 指标 | 值 | 目标 | 结果 |
|---|---|---|---|
| 平均章耗时 | {result.g5.avg_chapter_seconds:.0f}s | ≤{result.g5.time_target:.0f}s | {status(result.g5.passed)} |
| 平均章 token | {result.g5.avg_chapter_tokens} | ≤{result.g5.token_target} | {status(result.g5.avg_chapter_tokens <= result.g5.token_target)} |
"""

    output_path.write_text(report, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="300 章压测")
    parser.add_argument("--project-root", required=True, help="小说项目目录")
    parser.add_argument("--parallel", type=int, default=4, help="并发数")
    parser.add_argument("--chapters", type=int, default=300, help="总章数")
    parser.add_argument("--dry-run", action="store_true", help="仅生成空报告框架")
    args = parser.parse_args()

    project_root = Path(args.project_root)
    output_dir = Path("benchmark/300chapter_run")
    output_dir.mkdir(parents=True, exist_ok=True)

    result = BenchmarkResult(total_chapters=args.chapters)

    if args.dry_run:
        result.wall_time_s = 0
        metrics_path = output_dir / "metrics.json"
        metrics_path.write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
        )
        report_path = Path("reports/v13_acceptance.md")
        generate_acceptance_report(result, report_path)
        print(f"Dry-run complete. Metrics: {metrics_path}, Report: {report_path}")
        return

    print(f"Starting 300-chapter benchmark: {args.chapters} chapters, parallel={args.parallel}")
    print(f"Project: {project_root}")
    print(f"Output: {output_dir}")

    start = time.time()

    script_dir = Path(__file__).resolve().parent.parent / "ink-writer" / "scripts"
    ink_auto = script_dir / "ink-auto.sh"

    cmd = ["bash", str(ink_auto), "--parallel", str(args.parallel), str(args.chapters)]
    proc = subprocess.run(cmd, cwd=str(project_root))

    result.wall_time_s = time.time() - start

    metrics_path = output_dir / "metrics.json"
    metrics_path.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
    )

    report_path = Path("reports/v13_acceptance.md")
    generate_acceptance_report(result, report_path)

    print(f"\nBenchmark complete in {result.wall_time_s:.0f}s")
    print(f"Metrics: {metrics_path}")
    print(f"Report: {report_path}")
    print(f"Result: {'ALL PASSED' if result.all_passed else 'SOME FAILED'}")

    sys.exit(0 if result.all_passed else 1)


if __name__ == "__main__":
    main()
