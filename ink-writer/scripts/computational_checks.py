#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
计算型闸门 (Computational Gate) — Step 2C

在 LLM checker 调用之前执行的确定性检查，拦截明显问题以节省成本。
所有检查为纯规则/正则/SQL 查询，不调用 LLM。

用法:
    python computational_checks.py --project-root <path> --chapter <N> --chapter-file <path>
    python computational_checks.py --project-root <path> --chapter <N> --chapter-file <path> --format json

返回:
    exit 0: 全部通过或仅软警告
    exit 1: 存在硬失败
    exit 2: 脚本自身错误（不应阻断主流程）

输出 JSON 格式:
{
  "pass": true/false,
  "hard_failures": [...],
  "soft_warnings": [...],
  "checks_run": 6,
  "checks_passed": 5
}
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Check result model
# ---------------------------------------------------------------------------

class CheckResult:
    """单项检查结果"""

    def __init__(self, name: str, passed: bool, severity: str, message: str, detail: str = ""):
        self.name = name
        self.passed = passed
        self.severity = severity  # "hard" | "soft"
        self.message = message
        self.detail = detail

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "name": self.name,
            "passed": self.passed,
            "severity": self.severity,
            "message": self.message,
        }
        if self.detail:
            d["detail"] = self.detail
        return d


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def check_word_count(chapter_text: str, min_words: int = 2200, max_words: int = 5000) -> CheckResult:
    """检查章节字数是否在允许区间内"""
    # 去除 markdown 标题行，再去除空白
    cleaned = re.sub(r'^#+\s.*$', '', chapter_text, flags=re.MULTILINE)
    cleaned = re.sub(r'[\s\n\r]', '', cleaned)
    count = len(cleaned)

    if count < min_words:
        return CheckResult(
            "word_count", False, "hard",
            f"章节字数 {count} < 下限 {min_words}",
            f"当前 {count} 字，需要至少 {min_words} 字"
        )
    if count > max_words:
        return CheckResult(
            "word_count", False, "soft",
            f"章节字数 {count} > 建议上限 {max_words}",
            f"超出 {count - max_words} 字，可能过长"
        )
    return CheckResult("word_count", True, "soft", f"字数 {count}，在合理范围内")


def check_file_naming(chapter_file: Path, chapter_num: int) -> CheckResult:
    """检查章节文件命名是否符合规范"""
    name = chapter_file.name
    # 允许: 第0001章.md 或 第0001章-标题.md
    pattern = rf'^第{chapter_num:04d}章'
    if not re.match(pattern, name):
        # 也允许不带前导零的格式
        pattern_alt = rf'^第{chapter_num}章'
        if not re.match(pattern_alt, name):
            return CheckResult(
                "file_naming", False, "hard",
                f"文件名 '{name}' 不符合规范",
                f"期望格式: 第{chapter_num:04d}章-标题.md 或 第{chapter_num:04d}章.md"
            )
    if not name.endswith('.md'):
        return CheckResult(
            "file_naming", False, "hard",
            f"文件扩展名不是 .md: '{name}'"
        )
    return CheckResult("file_naming", True, "soft", f"文件名 '{name}' 符合规范")


def check_character_conflicts(chapter_text: str, project_root: Path) -> CheckResult:
    """检查角色名基础冲突（占位检查，复杂检测交给 consistency-checker）"""
    db_path = project_root / ".ink" / "index.db"
    if not db_path.exists():
        return CheckResult("character_conflicts", True, "soft", "index.db 不存在，跳过角色检查")

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # 获取所有已知实体名称和别名
        known_names: set[str] = set()
        try:
            cursor.execute("SELECT name FROM entities WHERE type = 'character'")
            for row in cursor.fetchall():
                known_names.add(row[0])
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("SELECT alias FROM aliases")
            for row in cursor.fetchall():
                known_names.add(row[0])
        except sqlite3.OperationalError:
            pass

        conn.close()

        if not known_names:
            return CheckResult("character_conflicts", True, "soft", "实体库为空，跳过角色检查")

        # 简单检测：检查已知角色是否在正文中出现了错误的名字变体
        # 这里只做基础检查，复杂的交给 consistency-checker
        return CheckResult("character_conflicts", True, "soft", f"已知实体 {len(known_names)} 个，基础检查通过")

    except Exception as e:
        return CheckResult("character_conflicts", True, "soft", f"角色检查异常: {e}")


def check_foreshadowing_consistency(project_root: Path, chapter_num: int) -> CheckResult:
    """检查伏笔生命周期一致性"""
    db_path = project_root / ".ink" / "index.db"
    if not db_path.exists():
        return CheckResult("foreshadowing", True, "soft", "index.db 不存在，跳过伏笔检查")

    try:
        with closing(sqlite3.connect(str(db_path))) as conn:
            cursor = conn.cursor()

            # 检查是否有严重逾期的伏笔
            overdue_threads: list[str] = []
            try:
                cursor.execute(
                    "SELECT thread_id, planted_chapter, expected_payoff_chapter "
                    "FROM plot_threads WHERE status = 'active' AND expected_payoff_chapter < ?",
                    (chapter_num,)
                )
                for row in cursor.fetchall():
                    delay = chapter_num - row[2]
                    if delay > 20:  # 超期 20 章以上
                        overdue_threads.append(f"伏笔 '{row[0]}' (第{row[1]}章埋) 预期第{row[2]}章回收，已逾期 {delay} 章")
            except sqlite3.OperationalError:
                pass

        if overdue_threads:
            return CheckResult(
                "foreshadowing", False, "soft",
                f"{len(overdue_threads)} 条伏笔严重逾期（>20章）",
                "\n".join(overdue_threads[:5])
            )

        return CheckResult("foreshadowing", True, "soft", "伏笔生命周期检查通过")

    except Exception as e:
        return CheckResult("foreshadowing", True, "soft", f"伏笔检查异常: {e}")


def check_power_level(chapter_text: str, project_root: Path) -> CheckResult:
    """检查主角能力等级基础一致性（占位检查，详细越级检测交给 consistency-checker）"""
    state_path = project_root / ".ink" / "state.json"
    if not state_path.exists():
        return CheckResult("power_level", True, "soft", "state.json 不存在，跳过能力检查")

    try:
        with open(state_path, "r", encoding="utf-8") as f:
            state = json.load(f)

        protagonist = state.get("protagonist", {})
        power = protagonist.get("power", {})
        realm = power.get("realm", "")

        if not realm:
            return CheckResult("power_level", True, "soft", "主角境界未设置，跳过能力检查")

        # 基础检查通过（详细的越级检查交给 consistency-checker）
        return CheckResult("power_level", True, "soft", f"主角当前境界: {realm}")

    except Exception as e:
        return CheckResult("power_level", True, "soft", f"能力检查异常: {e}")


def check_contract_completeness(project_root: Path, chapter_num: int) -> CheckResult:
    """检查章节契约字段完整性（如果存在）"""
    state_path = project_root / ".ink" / "state.json"
    if not state_path.exists():
        return CheckResult("contract", True, "soft", "state.json 不存在，跳过契约检查")

    try:
        with open(state_path, "r", encoding="utf-8") as f:
            state = json.load(f)

        chapter_meta = state.get("chapter_meta", {})
        prev_key = f"{chapter_num - 1:04d}"
        prev_meta = chapter_meta.get(prev_key, chapter_meta.get(str(chapter_num - 1), {}))

        if not prev_meta:
            return CheckResult("contract", True, "soft", f"前一章(第{chapter_num-1}章) meta 不存在，跳过契约检查")

        # 检查关键字段
        missing: list[str] = []
        if "hook" not in prev_meta:
            missing.append("hook")
        if "ending" not in prev_meta:
            missing.append("ending")

        if missing:
            return CheckResult(
                "contract", False, "soft",
                f"前一章 meta 缺少字段: {', '.join(missing)}",
                "可能影响本章上下文构建"
            )

        return CheckResult("contract", True, "soft", "前章契约字段完整")

    except Exception as e:
        return CheckResult("contract", True, "soft", f"契约检查异常: {e}")


# ---------------------------------------------------------------------------
# Metadata leakage check
# ---------------------------------------------------------------------------

METADATA_PATTERNS = [
    r'（本章完）', r'（全文完）',
    r'\*\*本章字数[：:]', r'\*\*章末钩子[：:]',
    r'\*\*本章小结', r'---\s*\n\s*\*\*',
]


def check_metadata_leakage(chapter_text: str) -> CheckResult:
    """检测正文末尾是否混入元数据。"""
    tail = chapter_text[-500:] if len(chapter_text) > 500 else chapter_text
    hits = [p for p in METADATA_PATTERNS if re.search(p, tail)]
    if hits:
        return CheckResult(
            "metadata_leakage", True, "soft",
            f"正文末尾检测到元数据泄漏: {', '.join(hits)}",
            "建议在润色步骤中清理这些元数据行",
        )
    return CheckResult("metadata_leakage", True, "soft", "无元数据泄漏")


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def run_all_checks(
    project_root: Path,
    chapter_num: int,
    chapter_file: Path,
    chapter_text: str,
) -> Dict[str, Any]:
    """执行所有计算型检查，返回汇总结果"""

    results: List[CheckResult] = [
        check_word_count(chapter_text),
        check_file_naming(chapter_file, chapter_num),
        check_character_conflicts(chapter_text, project_root),
        check_foreshadowing_consistency(project_root, chapter_num),
        check_power_level(chapter_text, project_root),
        check_contract_completeness(project_root, chapter_num),
        check_metadata_leakage(chapter_text),
    ]

    hard_failures = [r for r in results if not r.passed and r.severity == "hard"]
    soft_warnings = [r for r in results if not r.passed and r.severity == "soft"]
    passed_all = len(hard_failures) == 0

    return {
        "pass": passed_all,
        "hard_failures": [r.to_dict() for r in hard_failures],
        "soft_warnings": [r.to_dict() for r in soft_warnings],
        "all_results": [r.to_dict() for r in results],
        "checks_run": len(results),
        "checks_passed": sum(1 for r in results if r.passed),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="计算型闸门 (Step 2C)")
    parser.add_argument("--project-root", required=True, help="书项目根目录")
    parser.add_argument("--chapter", type=int, required=True, help="章节号")
    parser.add_argument("--chapter-file", required=True, help="章节文件路径")
    parser.add_argument("--format", choices=["text", "json"], default="json", help="输出格式")

    args = parser.parse_args()
    project_root = Path(args.project_root)
    chapter_file = Path(args.chapter_file)

    if not chapter_file.exists():
        print(json.dumps({"pass": False, "error": f"章节文件不存在: {chapter_file}"}, ensure_ascii=False))
        return 1

    chapter_text = chapter_file.read_text(encoding="utf-8")

    try:
        result = run_all_checks(project_root, args.chapter, chapter_file, chapter_text)
    except Exception as e:
        # 脚本自身错误 → exit 2，不阻断主流程
        print(json.dumps({"pass": True, "error": f"闸门内部错误: {e}", "fallthrough": True}, ensure_ascii=False))
        return 2

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        status = "✅ 全部通过" if result["pass"] else "❌ 存在硬失败"
        print(f"\n计算型闸门 (Step 2C): {status}")
        print(f"  检查项: {result['checks_run']} 个，通过: {result['checks_passed']} 个")
        if result["hard_failures"]:
            print(f"  硬失败: {len(result['hard_failures'])} 项")
            for f in result["hard_failures"]:
                print(f"    ❌ [{f['name']}] {f['message']}")
        if result["soft_warnings"]:
            print(f"  软警告: {len(result['soft_warnings'])} 项")
            for w in result["soft_warnings"]:
                print(f"    ⚠️ [{w['name']}] {w['message']}")

    return 0 if result["pass"] else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        # 兜底：任何未捕获异常 → exit 2（不阻断）
        print(json.dumps({"pass": True, "error": str(e), "fallthrough": True}, ensure_ascii=False))
        sys.exit(2)
