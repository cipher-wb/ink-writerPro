"""chapter_outline_loader 章纲提取回归（针对 2026-04-29 真实用户 bug）

历史 bug 描述：
  ink-plan 生成第 N 卷大纲时章节标题用 `## 第 1 章：xxx`（二级标题），
  但 _extract_outline_section 的正则只识别 `### 第 1 章：xxx`（三级标题）。
  导致：
    - check-outline 报"第 N 章没有详细大纲，禁止写作"
    - ink-auto.sh 误判为 ink-plan 失败 → exit 1
    - 用户实际看到 128KB 详细大纲已落盘，但软件不认

修复：让 _extract_outline_section 同时识别 `##` 和 `###` 两种章节标题。

本测试守护：
  1. ## 二级标题能被正确提取
  2. ### 三级标题不被破坏（向后兼容）
  3. 多章共存时段落边界正确（不会把第 1 章和第 2 章粘成一段）
  4. 章节标题包含空格、英文冒号、中文冒号都能识别
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# 让 import 能找到 ink-writer/scripts
REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "ink-writer" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from chapter_outline_loader import _extract_outline_section  # noqa: E402


def test_extracts_ink_plan_h2_title():
    """ink-plan 当前产出的 `## 第N章：xxx` 必须能被识别。"""
    content = """# 第1卷 详细大纲

## 第 1 章：重生回到小山村
- 钩子：男主重生到 1990 年的小山村
- 主线推进：决定靠养殖场翻身
- 字数目标：3000

## 第 2 章：第一只鸡
- 钩子：在山里捡到一只野鸡
- ...
"""
    section = _extract_outline_section(content, 1)
    assert section is not None, "## 二级标题的章节大纲应被识别"
    assert "重生回到小山村" in section
    assert "决定靠养殖场翻身" in section
    # 边界正确：不应吃到第 2 章的内容
    assert "第一只鸡" not in section, "不应把第 2 章的标题误吃进第 1 章"


def test_extracts_ink_plan_h2_no_space():
    """`## 第1章：xxx` (无空格) 也要识别。"""
    content = """## 第1章：重生
- 钩子：男主重生

## 第2章：第一只鸡
- 钩子：捡野鸡
"""
    section = _extract_outline_section(content, 1)
    assert section is not None
    assert "重生" in section
    assert "第一只鸡" not in section


def test_extracts_legacy_h3_title_still_works():
    """旧模板的 `### 第N章：xxx`（三级标题）必须保留兼容。"""
    content = """## 第 1 卷概述

### 第 1 章：序章
- 钩子：开篇

### 第 2 章：相遇
- 钩子：邂逅
"""
    section = _extract_outline_section(content, 1)
    assert section is not None
    assert "序章" in section
    assert "邂逅" not in section, "h3 模式下也不应跨段污染"


def test_h2_chapter_boundary_does_not_eat_next_chapter():
    """关键：第 N 章段落不能蔓延到第 N+1 章及之后。

    历史风险：之前的正则用 `$` 边界，遇到多章 `##` 共存时可能整文读完。
    """
    content = """## 第 1 章：开局
- 钩子 A
- 主线 A

## 第 2 章：进展
- 钩子 B
- 主线 B

## 第 3 章：高潮
- 钩子 C
"""
    sec1 = _extract_outline_section(content, 1)
    sec2 = _extract_outline_section(content, 2)
    sec3 = _extract_outline_section(content, 3)

    assert sec1 and "钩子 A" in sec1 and "钩子 B" not in sec1 and "钩子 C" not in sec1
    assert sec2 and "钩子 B" in sec2 and "钩子 A" not in sec2 and "钩子 C" not in sec2
    assert sec3 and "钩子 C" in sec3
    # 第 3 章是最后一章，应吃到文末
    assert "钩子 C" in sec3


def test_english_colon_works():
    """章节标题用英文冒号 `:` 也要识别。"""
    content = """## 第 1 章: 开局
- 钩子
"""
    section = _extract_outline_section(content, 1)
    assert section is not None
    assert "开局" in section


def test_missing_chapter_returns_none():
    content = """## 第 1 章：开局
## 第 2 章：进展
"""
    assert _extract_outline_section(content, 99) is None


def test_h1_in_content_does_not_break_h2_chapter_boundary():
    """章节正文里出现 ## 不应被误判为章节边界（用 ^## 行首锚定保护）。

    实际上 ink-plan 产出里章节正文不会有独立 ##，但加 re.MULTILINE 增强稳健性。
    """
    # 反例：第 1 章描述里有"## 不要紧"（不在行首是普通文本）
    content = """## 第 1 章：开局
- 钩子：男主重生
- 描述里出现 ## 这种字符串无所谓
- 字数 3000

## 第 2 章：进展
- 钩子 B
"""
    section = _extract_outline_section(content, 1)
    assert section is not None
    # 关键：吃完第 1 章所有内容（描述行里的 ## 不应当成边界）
    assert "字数 3000" in section
    assert "进展" not in section


def test_real_world_ink_plan_output_format():
    """模拟 ink-plan 真实生成的 128KB 大纲片段，确保 50 章都能被提取。"""
    chapters = []
    for i in range(1, 51):
        chapters.append(f"""## 第 {i} 章：第{i}章标题

### 钩子设计
- 开篇钩子 {i}A
- 主线钩子 {i}B

### 主线推进
- 推进点 {i}-1
- 推进点 {i}-2

### 字数目标
3000 字
""")
    content = "# 第 1 卷 详细大纲\n\n" + "\n".join(chapters)

    for i in (1, 25, 50):  # 抽 3 个代表测
        section = _extract_outline_section(content, i)
        assert section is not None, f"第 {i} 章应被识别"
        assert f"第{i}章标题" in section
        assert f"开篇钩子 {i}A" in section
        # 第 i 章不应吃到第 i+1 章
        if i < 50:
            assert f"第{i+1}章标题" not in section, (
                f"第 {i} 章不应吃到第 {i+1} 章"
            )
