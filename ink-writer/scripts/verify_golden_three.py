#!/usr/bin/env python3
"""Verify chapters 1-3 in 详细大纲.md align with .ink/golden_three_plan.json.

Hard rules (mirrors ink-plan SKILL.md line 614-625, 769, 887):
- 第 1 章大纲必须包含 "大卖点类型" 行，其值必须命中 ch1_cool_point_spec.payoff_form
  允许枚举：资源获取 / 敌人击退 / 他人认可 / 地位提升 / 信息解锁 / 危机解除
- 第 1 章必须有 "章末未闭合问题" 行（end_hook_requirement）
- 第 1-3 章每章必须存在 "倒计时状态" / "钩子" / "钩子契约" 行（end_hook gate）

Exit codes:
  0  全部通过
  1  发现违规（详情打到 stderr）
  2  数据缺失（golden_three_plan.json 不存在 / 大纲文件不存在 / parse 失败）

Used by ink-plan as a hard-gate after chapter outline generation.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ALLOWED_PAYOFF_FORMS = {
    "资源获取", "敌人击退", "他人认可", "地位提升", "信息解锁", "危机解除",
}

REQUIRED_FIELDS_PER_CHAPTER = (
    "倒计时状态",
    "大卖点类型",
    "钩子",
    "章末未闭合问题",
)


def _find_outline(project_root: Path) -> Path | None:
    candidates = [
        project_root / "大纲" / "第1卷-详细大纲.md",
        project_root / "大纲" / "第1卷详细大纲.md",
        project_root / "大纲" / "第一卷-详细大纲.md",
    ]
    for c in candidates:
        if c.exists():
            return c
    fallback = list((project_root / "大纲").glob("第1卷*详细大纲*.md")) if (project_root / "大纲").exists() else []
    return fallback[0] if fallback else None


def _split_chapters(text: str) -> dict[int, str]:
    chapters: dict[int, str] = {}
    pattern = re.compile(r"^###\s+第\s*(\d+)\s*章[:：]?(.*)$", re.MULTILINE)
    matches = list(pattern.finditer(text))
    for i, m in enumerate(matches):
        ch_no = int(m.group(1))
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chapters[ch_no] = text[start:end]
    return chapters


def _extract_field(body: str, field_name: str) -> str | None:
    pattern = re.compile(rf"^[\-\*•]?\s*{re.escape(field_name)}\s*[:：]\s*(.*)$", re.MULTILINE)
    m = pattern.search(body)
    return m.group(1).strip() if m else None


def verify(project_root: Path) -> tuple[int, list[str]]:
    violations: list[str] = []

    plan_path = project_root / ".ink" / "golden_three_plan.json"
    if not plan_path.exists():
        return 2, [f"DATA_MISSING: {plan_path} 不存在"]

    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return 2, [f"DATA_PARSE_ERROR: {plan_path}: {e}"]

    if not plan.get("enabled", True):
        return 0, ["INFO: golden_three gate disabled in plan, skipping"]

    outline_path = _find_outline(project_root)
    if outline_path is None:
        return 2, [f"DATA_MISSING: 未找到 第1卷-详细大纲.md（搜索路径: {project_root / '大纲'}）"]

    try:
        text = outline_path.read_text(encoding="utf-8")
    except OSError as e:
        return 2, [f"DATA_READ_ERROR: {outline_path}: {e}"]

    chapters = _split_chapters(text)

    plan_chapters = plan.get("chapters", {})
    for ch_no in (1, 2, 3):
        body = chapters.get(ch_no)
        if body is None:
            violations.append(f"第{ch_no}章: 大纲缺失整章节段")
            continue

        for field in REQUIRED_FIELDS_PER_CHAPTER:
            if _extract_field(body, field) is None:
                violations.append(f"第{ch_no}章: 缺少必填字段 '{field}'")

        if ch_no == 1:
            spec = plan_chapters.get("1", {}).get("ch1_cool_point_spec")
            if not spec:
                violations.append("第1章: golden_three_plan.json 缺少 chapters['1'].ch1_cool_point_spec")
            else:
                expected_form = spec.get("payoff_form", "").strip()
                if expected_form not in ALLOWED_PAYOFF_FORMS:
                    violations.append(
                        f"第1章: ch1_cool_point_spec.payoff_form='{expected_form}' "
                        f"不在允许枚举 {sorted(ALLOWED_PAYOFF_FORMS)}（本身已无效）"
                    )
                else:
                    actual = _extract_field(body, "大卖点类型") or ""
                    actual_head = actual.split("|")[0].strip()
                    if expected_form not in actual_head:
                        violations.append(
                            f"第1章: '大卖点类型: {actual_head}' 未对齐 "
                            f"ch1_cool_point_spec.payoff_form='{expected_form}'"
                        )

    return (1 if violations else 0), violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--project-root", required=True, help="Novel project root (containing .ink/ and 大纲/)")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of human-readable")
    args = parser.parse_args()

    rc, violations = verify(Path(args.project_root))

    if args.json:
        print(json.dumps({"exit_code": rc, "violations": violations}, ensure_ascii=False, indent=2))
    else:
        if rc == 0:
            print("✅ 黄金三章合规验证通过")
        elif rc == 1:
            print("❌ 黄金三章合规验证失败：", file=sys.stderr)
            for v in violations:
                print(f"   - {v}", file=sys.stderr)
        else:
            print(f"⚠️  数据缺失（exit_code={rc}）：", file=sys.stderr)
            for v in violations:
                print(f"   - {v}", file=sys.stderr)

    return rc


if __name__ == "__main__":
    try:
        import sys as _sys
        from pathlib import Path as _Path
        _sys.path.insert(0, str(_Path(__file__).resolve().parent))
        from runtime_compat import enable_windows_utf8_stdio
        enable_windows_utf8_stdio()
    except Exception:
        pass
    sys.exit(main())
