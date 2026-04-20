#!/usr/bin/env python3
"""One-shot helper: append simplicity rules (US-004) to data/editor-wisdom/rules.json.

Re-runnable: if any rule id already exists, that rule is skipped (no dup).
Not part of the regular pipeline — intentionally placed in scripts/ (not
scripts/editor-wisdom/) and not wired into SKILL.md. Future simplicity edits
should go through this script or direct rules.json edits.
"""

from __future__ import annotations

# Windows 兼容层：保证 stdout/stderr 以 UTF-8 输出（Mac/Linux no-op）。
import os as _os_win_stdio
import sys as _sys_win_stdio

_ink_scripts = _os_win_stdio.path.join(
    _os_win_stdio.path.dirname(_os_win_stdio.path.abspath(__file__)),
    "../ink-writer/scripts",
)
if _os_win_stdio.path.isdir(_ink_scripts) and _ink_scripts not in _sys_win_stdio.path:
    _sys_win_stdio.path.insert(0, _ink_scripts)
try:
    from runtime_compat import enable_windows_utf8_stdio as _enable_utf8_stdio  # noqa: E402

    _enable_utf8_stdio()
except Exception:
    pass

import json  # noqa: E402
from pathlib import Path  # noqa: E402

RULES_PATH = Path(__file__).resolve().parent.parent / "data" / "editor-wisdom" / "rules.json"

SOURCE_FILE = "prose-directness/simplicity-rules.md"

# v22 US-004 — 14 条 simplicity 规则，覆盖 PRD 要求的 5 类 applies_to 组合。
# severity 按 PRD 示例（"每句必须服务剧情"等 4 条核心硬原则）标 hard；
# 其余按"建议遵守"标 soft（与现存 category=prose_* 的 hard/soft 比例一致）。
SIMPLICITY_RULES: list[dict] = [
    {
        "id": "EW-0389",
        "category": "simplicity",
        "rule": "每句话必须服务剧情推进、角色心理或冲突升级三选一；无功能句立即删除",
        "why": "PRD US-006 硬原则：直白模式下'故事 > 文字'——读者付费买推进感，凡不服务三者之一的句子都在浪费阅读预算",
        "severity": "hard",
        "applies_to": ["golden_three", "combat", "climax", "high_point"],
        "source_files": [SOURCE_FILE],
    },
    {
        "id": "EW-0390",
        "category": "simplicity",
        "rule": "同句禁用两个及以上抽象形容词堆叠（如'莫名而无尽的恐惧'），必须用具体动作或场景替代",
        "why": "PRD US-006 硬原则：抽象形容词堆叠=AI 味 + 信息密度塌陷；改写为'她的指甲在掌心掐出月牙'直接给画面",
        "severity": "hard",
        "applies_to": ["golden_three", "combat", "climax", "high_point"],
        "source_files": [SOURCE_FILE],
    },
    {
        "id": "EW-0391",
        "category": "simplicity",
        "rule": "禁止出现连续超过 3 句的纯环境/物件描写段，每 3 句内必须插入角色动作、对话或心理",
        "why": "PRD US-006 硬原则：空境描写让爽点断气；战斗场景的 4 句环境 = 节奏死亡。即使是铺垫也要让人物嵌在环境里",
        "severity": "hard",
        "applies_to": ["golden_three", "combat", "climax", "high_point"],
        "source_files": [SOURCE_FILE],
    },
    {
        "id": "EW-0392",
        "category": "simplicity",
        "rule": "比喻/拟人的本体不得为抽象概念（时间/情绪/意识/命运）；抽象概念只允许用具体动作或物件喻依",
        "why": "PRD US-006 硬原则：'时间如流水'类套喻是 AI 味重灾区，编辑直接打回；要么换成具体动作（他数着自己的呼吸），要么删除",
        "severity": "hard",
        "applies_to": ["golden_three", "combat", "climax", "high_point"],
        "source_files": [SOURCE_FILE],
    },
    {
        "id": "EW-0393",
        "category": "simplicity",
        "rule": "优先使用强动词 + 具体名词；能用动词表达的禁止用'形容词 + 的 + 名词'结构",
        "why": "编辑星河反复强调：强动词带画面，'缓慢而沉重地走过去'不如'拖着步子'；直白化的核心就是动词密度",
        "severity": "hard",
        "applies_to": ["golden_three", "combat", "climax", "high_point"],
        "source_files": [SOURCE_FILE],
    },
    {
        "id": "EW-0394",
        "category": "simplicity",
        "rule": "战斗/高潮场景单句字数控制在 20 字以内，必要时主动拆为两短句以营造短促感",
        "why": "benchmark 起点爆款战斗段句长中位数 13~18 字；长句稀释爆发力，短句才有打击感",
        "severity": "hard",
        "applies_to": ["combat", "climax", "high_point"],
        "source_files": [SOURCE_FILE],
    },
    {
        "id": "EW-0395",
        "category": "simplicity",
        "rule": "禁用空心形容词：莫名、无尽、难以言喻、仿佛、似乎、恍惚、浩渺、深邃、蓦然、豁然（引用 prose-blacklist.yaml）",
        "why": "US-003 黑名单最毒 10 词——这些词把具体情绪/动作糊成一团，读者收不到信号；直接删或替换为具体动词",
        "severity": "hard",
        "applies_to": ["all_chapters", "golden_three", "combat", "climax", "high_point"],
        "source_files": [SOURCE_FILE, "assets/prose-blacklist.yaml"],
    },
    {
        "id": "EW-0396",
        "category": "simplicity",
        "rule": "禁用空洞套话：此情此景、不知为何、时间仿佛静止、心里五味杂陈、眼里闪过一丝（引用 prose-blacklist.yaml）",
        "why": "US-003 黑名单套话组——全是 telling 不是 showing，AI 生成最喜欢的填充料，编辑一眼识破",
        "severity": "hard",
        "applies_to": ["all_chapters", "golden_three", "combat", "climax", "high_point"],
        "source_files": [SOURCE_FILE, "assets/prose-blacklist.yaml"],
    },
    {
        "id": "EW-0397",
        "category": "simplicity",
        "rule": "每章形容词-动词比不得超过 0.6；超过即用动词 + 具体细节替代形容词",
        "why": "benchmark 起点基线 golden_three D2 p50≈0.45，> 0.6 即显华丽；directness-checker D2 维度直接按此计分",
        "severity": "soft",
        "applies_to": ["golden_three", "combat", "climax", "high_point"],
        "source_files": [SOURCE_FILE, "reports/seed_thresholds.yaml"],
    },
    {
        "id": "EW-0398",
        "category": "simplicity",
        "rule": "高潮/爽点段落抒情与心理描写总字数占比不得超过 20%，其余交给动作与对白",
        "why": "爽点的核心是'发生了什么'而非'我感觉到什么'；心理描写超 20% 就会稀释爆点，读者追文会划走",
        "severity": "hard",
        "applies_to": ["climax", "high_point"],
        "source_files": [SOURCE_FILE],
    },
    {
        "id": "EW-0399",
        "category": "simplicity",
        "rule": "连续两句以上修辞（比喻/拟人/排比）必须删到只剩一句；排比句限单段一次",
        "why": "修辞堆砌 = 炫技 = AI 味；benchmark 起点 D1 修辞密度 p75 ≈ 0.025，即每 40 句才允许一次修辞，连续两句立即触发 red",
        "severity": "hard",
        "applies_to": ["golden_three", "combat", "climax", "high_point"],
        "source_files": [SOURCE_FILE, "reports/seed_thresholds.yaml"],
    },
    {
        "id": "EW-0400",
        "category": "simplicity",
        "rule": "黄金三章每 100 字必须推进一个主线事件（人物登场、冲突升级、信息披露或决策转折）",
        "why": "PRD 数据：起点黄金三章段落事件密度高于后续章；100 字无推进 = 读者弃文概率骤升，编辑 A/B 测试验证",
        "severity": "hard",
        "applies_to": ["golden_three"],
        "source_files": [SOURCE_FILE],
    },
    {
        "id": "EW-0401",
        "category": "simplicity",
        "rule": "对话前后的心理/动作夹叙不超过 2 句；对话密度高的场景允许裸对白 + 极简动作标签",
        "why": "战斗与爽点段对白是信息爆点，夹叙超过 2 句就打断节奏；裸对白 + '他挑眉'这类单句标签已够塑造人物",
        "severity": "soft",
        "applies_to": ["combat", "climax", "high_point"],
        "source_files": [SOURCE_FILE],
    },
    {
        "id": "EW-0402",
        "category": "simplicity",
        "rule": "严禁'X 得 Y'补语堆叠（笑得灿烂/跑得飞快），改为具体动作细节（如'露出整排牙'/'鞋底擦出火星'）",
        "why": "补语结构是 telling 的最后堡垒，读者脑海里画不出画面；强制拆为动作 + 细节立刻 showing",
        "severity": "soft",
        "applies_to": ["all_chapters", "golden_three", "combat", "climax", "high_point"],
        "source_files": [SOURCE_FILE],
    },
]


def main() -> None:
    rules = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    existing_ids = {r["id"] for r in rules}
    added = 0
    for new_rule in SIMPLICITY_RULES:
        if new_rule["id"] in existing_ids:
            continue
        rules.append(new_rule)
        existing_ids.add(new_rule["id"])
        added += 1
    RULES_PATH.write_text(
        json.dumps(rules, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    total = sum(1 for r in rules if r["category"] == "simplicity")
    print(f"Appended {added} new simplicity rules; total simplicity={total}; rules.json size={len(rules)}")


if __name__ == "__main__":
    main()
