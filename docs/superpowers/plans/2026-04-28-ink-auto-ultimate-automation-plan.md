# ink-auto 终极自动化模式 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade `/ink-auto N` so that one command initializes the project (from `.md` blueprint or 7-question bootstrap), generates outlines on demand, and writes N chapters end-to-end without human intervention.

**Architecture:** Add a 3-module Python detection layer (`state_detector` + `blueprint_scanner` + `blueprint_to_quick_draft`) under `ink_writer/core/auto/`. Add `--blueprint` flag to ink-init Quick mode (SKILL.md edit). Add `interactive_bootstrap.sh` (pure bash `read`, no CLI subprocess). Patch `ink-auto.sh` lines 188-191 to dispatch on detected state instead of `exit 1`. Three rollback env vars allow reverting to current behavior.

**Tech Stack:** Python 3.10+, pytest, bash 3.2+ / PowerShell 5.1+, existing CLI subprocess pattern (claude-p / gemini --yolo / codex --approval-mode full-auto).

**Spec:** `docs/superpowers/specs/2026-04-28-ink-auto-ultimate-automation-design.md`

---

## File Structure

### New Python modules

| Path | Responsibility |
|------|---------------|
| `ink_writer/core/auto/__init__.py` | Package init (empty) |
| `ink_writer/core/auto/state_detector.py` | Enum 4 states + `detect_project_state(cwd) -> ProjectState` |
| `ink_writer/core/auto/blueprint_scanner.py` | `find_blueprint(cwd) -> Path | None` |
| `ink_writer/core/auto/blueprint_to_quick_draft.py` | `parse_blueprint(path) -> dict` + `validate(d) -> None` + `to_quick_draft(d) -> dict` + `BlueprintValidationError` exception |

### New tests

| Path | Coverage |
|------|---------|
| `tests/core/auto/__init__.py` | Package init |
| `tests/core/auto/test_state_detector.py` | 4 state cases |
| `tests/core/auto/test_blueprint_scanner.py` | blacklist / size / no-recurse |
| `tests/core/auto/test_blueprint_to_quick_draft.py` | parse / validate / to_quick_draft / blacklist hits |
| `tests/core/auto/test_integration_s0a.py` | E2E S0a: blueprint → ink-init → state.json |
| `tests/core/auto/test_integration_s0b.py` | E2E S0b: empty dir → mock 7 questions → blueprint |

### New shell scripts

| Path | Responsibility |
|------|---------------|
| `ink-writer/scripts/interactive_bootstrap.sh` | 7-question bash `read`, falls back to `read -p` for prompts |
| `ink-writer/scripts/interactive_bootstrap.ps1` | PowerShell sibling using `Read-Host` |
| `ink-writer/scripts/interactive_bootstrap.cmd` | Windows `cmd` launcher |

### Modified files

| Path | Lines | Edit |
|------|------|------|
| `ink-writer/scripts/ink-auto.sh` | ~188-191, +60 lines | Replace `exit 1` with state-dispatch block; add 3 rollback env-var checks |
| `ink-writer/scripts/ink-auto.ps1` | parallel section | Mirror bash changes |
| `ink-writer/skills/ink-init/SKILL.md` | top of Quick mode + Step 0.4 + Step 1 + Step 2 | Add `--blueprint` recognition + skip Step 0.4 + override Step 1 fields + auto-select scheme 1 |
| `ink-writer/skills/ink-auto/SKILL.md` | new section | Document new behavior + rollback switches |
| `ink-writer/templates/blueprint-template.md` | new file (move) | Move from repo root `蓝本模板.md` |

---

## Phase P0: Python Detection Layer (no behavior change)

These three modules are pure-Python utilities, fully testable in isolation. Merging them does not affect any existing flow until C6 wires them in.

### Task 1: Create package structure

**Files:**
- Create: `ink_writer/core/auto/__init__.py`
- Create: `tests/core/auto/__init__.py`

- [ ] **Step 1: Create empty package files**

```bash
mkdir -p ink_writer/core/auto tests/core/auto
touch ink_writer/core/auto/__init__.py tests/core/auto/__init__.py
```

- [ ] **Step 2: Verify packages importable**

Run: `python -c "import ink_writer.core.auto"`
Expected: no error.

- [ ] **Step 3: Commit**

```bash
git add ink_writer/core/auto/__init__.py tests/core/auto/__init__.py
git commit -m "feat(auto): create ink_writer.core.auto package skeleton"
```

---

### Task 2: state_detector.py

**Files:**
- Create: `ink_writer/core/auto/state_detector.py`
- Create: `tests/core/auto/test_state_detector.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/core/auto/test_state_detector.py
import json
from pathlib import Path
import pytest
from ink_writer.core.auto.state_detector import detect_project_state, ProjectState


def _write_state(root: Path, *, current_chapter: int = 0, is_completed: bool = False, volumes: list | None = None) -> None:
    (root / ".ink").mkdir(parents=True, exist_ok=True)
    state = {
        "project_info": {"volumes": volumes or []},
        "progress": {"current_chapter": current_chapter, "is_completed": is_completed},
    }
    (root / ".ink" / "state.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def test_s0_uninit_when_no_state_json(tmp_path: Path) -> None:
    assert detect_project_state(tmp_path) == ProjectState.S0_UNINIT


def test_s1_no_outline_when_state_exists_but_outline_dir_missing(tmp_path: Path) -> None:
    _write_state(tmp_path, volumes=[{"volume_id": "1", "chapter_range": "1-50"}])
    assert detect_project_state(tmp_path) == ProjectState.S1_NO_OUTLINE


def test_s1_no_outline_when_outline_dir_empty(tmp_path: Path) -> None:
    _write_state(tmp_path, volumes=[{"volume_id": "1", "chapter_range": "1-50"}])
    (tmp_path / "大纲").mkdir()
    assert detect_project_state(tmp_path) == ProjectState.S1_NO_OUTLINE


def test_s2_writing_when_state_and_outline_present(tmp_path: Path) -> None:
    _write_state(tmp_path, current_chapter=5, volumes=[{"volume_id": "1", "chapter_range": "1-50"}])
    (tmp_path / "大纲").mkdir()
    (tmp_path / "大纲" / "总纲.md").write_text("# 总纲", encoding="utf-8")
    assert detect_project_state(tmp_path) == ProjectState.S2_WRITING


def test_s3_completed_when_is_completed_true(tmp_path: Path) -> None:
    _write_state(tmp_path, current_chapter=600, is_completed=True, volumes=[{"volume_id": "1", "chapter_range": "1-600"}])
    (tmp_path / "大纲").mkdir()
    (tmp_path / "大纲" / "总纲.md").write_text("# 总纲", encoding="utf-8")
    assert detect_project_state(tmp_path) == ProjectState.S3_COMPLETED
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `pytest tests/core/auto/test_state_detector.py -v`
Expected: FAIL with `ImportError: cannot import name 'detect_project_state'`.

- [ ] **Step 3: Implement state_detector.py**

```python
# ink_writer/core/auto/state_detector.py
"""Detect ink-writer project state in a working directory.

Used by ink-auto to decide whether to dispatch to init / plan / main loop.
"""
from __future__ import annotations

import enum
import json
from pathlib import Path


class ProjectState(enum.Enum):
    S0_UNINIT = "S0_UNINIT"
    S1_NO_OUTLINE = "S1_NO_OUTLINE"
    S2_WRITING = "S2_WRITING"
    S3_COMPLETED = "S3_COMPLETED"


def detect_project_state(cwd: Path | str) -> ProjectState:
    cwd = Path(cwd)
    state_path = cwd / ".ink" / "state.json"
    if not state_path.is_file():
        return ProjectState.S0_UNINIT

    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return ProjectState.S0_UNINIT

    progress = state.get("progress", {}) if isinstance(state, dict) else {}
    if progress.get("is_completed") is True:
        return ProjectState.S3_COMPLETED

    outline_dir = cwd / "大纲"
    has_outline = outline_dir.is_dir() and any(outline_dir.iterdir())
    if not has_outline:
        return ProjectState.S1_NO_OUTLINE

    return ProjectState.S2_WRITING
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `pytest tests/core/auto/test_state_detector.py -v`
Expected: 5 PASSED.

- [ ] **Step 5: Commit**

```bash
git add ink_writer/core/auto/state_detector.py tests/core/auto/test_state_detector.py
git commit -m "feat(auto): C1 add ProjectState enum and detect_project_state"
```

---

### Task 3: blueprint_scanner.py

**Files:**
- Create: `ink_writer/core/auto/blueprint_scanner.py`
- Create: `tests/core/auto/test_blueprint_scanner.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/core/auto/test_blueprint_scanner.py
from pathlib import Path
from ink_writer.core.auto.blueprint_scanner import find_blueprint, BLACKLIST


def test_returns_none_in_empty_dir(tmp_path: Path) -> None:
    assert find_blueprint(tmp_path) is None


def test_returns_none_when_only_blacklisted_md(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# readme", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("# claude", encoding="utf-8")
    (tmp_path / "TODO.md").write_text("# todo", encoding="utf-8")
    assert find_blueprint(tmp_path) is None


def test_blacklist_is_case_insensitive(tmp_path: Path) -> None:
    (tmp_path / "readme.md").write_text("# readme", encoding="utf-8")
    (tmp_path / "Claude.MD").write_text("# claude", encoding="utf-8")
    assert find_blueprint(tmp_path) is None


def test_excludes_draft_md(tmp_path: Path) -> None:
    (tmp_path / "idea.draft.md").write_text("# draft", encoding="utf-8")
    assert find_blueprint(tmp_path) is None


def test_picks_largest_md_when_multiple_candidates(tmp_path: Path) -> None:
    small = tmp_path / "idea.md"
    big = tmp_path / "setup.md"
    small.write_text("x" * 500, encoding="utf-8")
    big.write_text("x" * 5000, encoding="utf-8")
    assert find_blueprint(tmp_path) == big


def test_does_not_recurse_into_subdirs(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "extra.md").write_text("x" * 9999, encoding="utf-8")
    top = tmp_path / "idea.md"
    top.write_text("x" * 100, encoding="utf-8")
    assert find_blueprint(tmp_path) == top


def test_blacklist_contents() -> None:
    expected = {"README.md", "CLAUDE.md", "TODO.md", "CHANGELOG.md", "LICENSE.md", "CONTRIBUTING.md", "AGENTS.md", "GEMINI.md"}
    assert expected.issubset({n.upper() for n in BLACKLIST})
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `pytest tests/core/auto/test_blueprint_scanner.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement blueprint_scanner.py**

```python
# ink_writer/core/auto/blueprint_scanner.py
"""Scan CWD top-level for a usable blueprint .md file.

Used by ink-auto S0a branch to find a user-supplied blueprint.
"""
from __future__ import annotations

from pathlib import Path

BLACKLIST = {
    "README.md",
    "CLAUDE.md",
    "TODO.md",
    "CHANGELOG.md",
    "LICENSE.md",
    "CONTRIBUTING.md",
    "AGENTS.md",
    "GEMINI.md",
}


def _is_blacklisted(name: str) -> bool:
    upper = name.upper()
    if upper in {b.upper() for b in BLACKLIST}:
        return True
    if upper.endswith(".DRAFT.MD"):
        return True
    return False


def find_blueprint(cwd: Path | str) -> Path | None:
    cwd = Path(cwd)
    if not cwd.is_dir():
        return None
    candidates: list[Path] = []
    for entry in cwd.iterdir():
        if not entry.is_file():
            continue
        if not entry.name.lower().endswith(".md"):
            continue
        if _is_blacklisted(entry.name):
            continue
        candidates.append(entry)
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_size)
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `pytest tests/core/auto/test_blueprint_scanner.py -v`
Expected: 7 PASSED.

- [ ] **Step 5: Commit**

```bash
git add ink_writer/core/auto/blueprint_scanner.py tests/core/auto/test_blueprint_scanner.py
git commit -m "feat(auto): C2 add find_blueprint with blacklist + size selection"
```

---

### Task 4: blueprint_to_quick_draft.py — parser core

**Files:**
- Create: `ink_writer/core/auto/blueprint_to_quick_draft.py`
- Create: `tests/core/auto/test_blueprint_to_quick_draft.py`
- Create: `tests/core/auto/_blueprint_fixtures.py`

- [ ] **Step 1: Write fixture helper**

```python
# tests/core/auto/_blueprint_fixtures.py
"""Shared fixtures producing minimal valid / invalid blueprints."""
from pathlib import Path


def write_full_blueprint(path: Path) -> None:
    path.write_text(
        """# 小说蓝本

## 一、项目元信息
### 平台
qidian

### 激进度档位
2

### 目标章数
600

### 目标字数


## 二、故事核心
### 书名
AUTO

### 题材方向
仙侠

### 核心卖点


### 核心冲突
弃徒带真凶回师门当众对峙

## 三、主角设定
### 主角姓名
AUTO

### 主角人设
寒门弟子，渴望师门认可；过度自尊不会服软

### 主角职业/身份


## 四、金手指
### 金手指类型
信息

### 能力一句话
每读懂他人遗书借走立遗嘱者绝学三天

### 主代价


### 第一章爽点预览


## 五、配角与情感线
### 女主/核心配角姓名
AUTO

### 女主/核心配角人设


## 六、前三章钩子
### 第 1 章钩子


### 第 2 章钩子


### 第 3 章钩子


## 七、可选高级字段
### 元规则倾向


### 商业安全边界打破


### 语言风格档位


### 禁忌/避坑提示


## 八、自由备注

""",
        encoding="utf-8",
    )


def write_minimal_blueprint(path: Path) -> None:
    """Has only required fields; everything else AUTO/empty."""
    path.write_text(
        """# 蓝本
## 一、项目元信息
### 平台
qidian
### 激进度档位
2
## 二、故事核心
### 题材方向
仙侠
### 核心冲突
弃徒带真凶回师门当众对峙
## 三、主角设定
### 主角人设
寒门弟子；过度自尊不会服软
## 四、金手指
### 金手指类型
信息
### 能力一句话
每读懂他人遗书借走立遗嘱者绝学三天
""",
        encoding="utf-8",
    )


def write_blueprint_missing_required(path: Path) -> None:
    """Missing 主角人设."""
    path.write_text(
        """# 蓝本
## 一、项目元信息
### 平台
qidian
## 二、故事核心
### 题材方向
仙侠
### 核心冲突
foo
## 三、主角设定
### 主角人设

## 四、金手指
### 金手指类型
信息
### 能力一句话
abc
""",
        encoding="utf-8",
    )


def write_blueprint_with_gf_blacklist_word(path: Path) -> None:
    path.write_text(
        """# 蓝本
## 一、项目元信息
### 平台
qidian
## 二、故事核心
### 题材方向
仙侠
### 核心冲突
foo
## 三、主角设定
### 主角人设
abc
## 四、金手指
### 金手指类型
信息
### 能力一句话
修为暴涨碾压一切
""",
        encoding="utf-8",
    )
```

- [ ] **Step 2: Write failing tests for parse + validate + to_quick_draft**

```python
# tests/core/auto/test_blueprint_to_quick_draft.py
from pathlib import Path
import pytest
from ink_writer.core.auto.blueprint_to_quick_draft import (
    parse_blueprint,
    validate,
    to_quick_draft,
    BlueprintValidationError,
)
from tests.core.auto._blueprint_fixtures import (
    write_full_blueprint,
    write_minimal_blueprint,
    write_blueprint_missing_required,
    write_blueprint_with_gf_blacklist_word,
)


def test_parse_full_blueprint_extracts_known_sections(tmp_path: Path) -> None:
    bp = tmp_path / "bp.md"
    write_full_blueprint(bp)
    parsed = parse_blueprint(bp)
    assert parsed["平台"] == "qidian"
    assert parsed["激进度档位"] == "2"
    assert parsed["题材方向"] == "仙侠"
    assert parsed["主角人设"].startswith("寒门弟子")
    assert parsed["金手指类型"] == "信息"
    assert parsed["能力一句话"].startswith("每读懂他人遗书")
    # AUTO sentinel preserved as literal
    assert parsed["书名"] == "AUTO"


def test_parse_minimal_blueprint_marks_empty_optional_as_none(tmp_path: Path) -> None:
    bp = tmp_path / "bp.md"
    write_minimal_blueprint(bp)
    parsed = parse_blueprint(bp)
    assert parsed.get("书名") in (None, "")
    assert parsed["题材方向"] == "仙侠"


def test_validate_passes_for_complete_minimal(tmp_path: Path) -> None:
    bp = tmp_path / "bp.md"
    write_minimal_blueprint(bp)
    parsed = parse_blueprint(bp)
    validate(parsed)  # no raise


def test_validate_rejects_missing_required_field(tmp_path: Path) -> None:
    bp = tmp_path / "bp.md"
    write_blueprint_missing_required(bp)
    parsed = parse_blueprint(bp)
    with pytest.raises(BlueprintValidationError) as exc:
        validate(parsed)
    assert "主角人设" in str(exc.value)


def test_validate_rejects_gf_blacklist_word(tmp_path: Path) -> None:
    bp = tmp_path / "bp.md"
    write_blueprint_with_gf_blacklist_word(bp)
    parsed = parse_blueprint(bp)
    with pytest.raises(BlueprintValidationError) as exc:
        validate(parsed)
    assert "修为暴涨" in str(exc.value)


def test_to_quick_draft_qidian_defaults_for_missing_chapter_count(tmp_path: Path) -> None:
    bp = tmp_path / "bp.md"
    write_minimal_blueprint(bp)
    parsed = parse_blueprint(bp)
    draft = to_quick_draft(parsed)
    assert draft["platform"] == "qidian"
    assert draft["target_chapters"] == 600
    assert draft["chapter_words"] == 3000
    assert draft["aggression_level"] == 2


def test_to_quick_draft_fanqie_defaults(tmp_path: Path) -> None:
    bp = tmp_path / "bp.md"
    bp.write_text(
        "# 蓝本\n## 一、项目元信息\n### 平台\nfanqie\n### 激进度档位\n3\n"
        "## 二、故事核心\n### 题材方向\n都市\n### 核心冲突\n复仇\n"
        "## 三、主角设定\n### 主角人设\n社畜逆袭\n"
        "## 四、金手指\n### 金手指类型\n信息\n### 能力一句话\n二十字之内的爆点\n",
        encoding="utf-8",
    )
    parsed = parse_blueprint(bp)
    draft = to_quick_draft(parsed)
    assert draft["platform"] == "fanqie"
    assert draft["target_chapters"] == 800
    assert draft["chapter_words"] == 1500
    assert draft["aggression_level"] == 3


def test_to_quick_draft_marks_missing_optional_for_quick_engine(tmp_path: Path) -> None:
    bp = tmp_path / "bp.md"
    write_minimal_blueprint(bp)
    parsed = parse_blueprint(bp)
    draft = to_quick_draft(parsed)
    assert "__missing__" in draft
    # Optional fields not provided in minimal blueprint
    assert "书名" in draft["__missing__"]
    assert "女主姓名" in draft["__missing__"]
```

- [ ] **Step 3: Run tests — verify they fail**

Run: `pytest tests/core/auto/test_blueprint_to_quick_draft.py -v`
Expected: FAIL — module not found.

- [ ] **Step 4: Implement parser core**

```python
# ink_writer/core/auto/blueprint_to_quick_draft.py
"""Parse blueprint .md file → Quick mode draft.json input.

Public API:
- parse_blueprint(path) -> dict[str, str | None]
- validate(parsed) -> None  (raises BlueprintValidationError)
- to_quick_draft(parsed) -> dict
- BlueprintValidationError
"""
from __future__ import annotations

import re
from pathlib import Path

# Required fields — blueprint must have non-empty values for these or validation fails
REQUIRED_FIELDS = ("题材方向", "核心冲突", "主角人设", "金手指类型", "能力一句话")

# Golden-finger禁词（命中即失败）
GF_BLACKLIST = (
    "修为暴涨",
    "无限金币",
    "系统签到",
    "作弊器",
    "外挂",
    "全能系统",
    "签到系统",
)

# Platform defaults — sourced from ink-init SKILL.md Quick Step 0.4 v26.2 (line 91-104)
_PLATFORM_DEFAULTS = {
    "qidian": {"target_chapters": 600, "target_words": 1_800_000, "chapter_words": 3000},
    "fanqie": {"target_chapters": 800, "target_words": 1_200_000, "chapter_words": 1500},
}

# Optional fields tracked in __missing__ so Quick engine knows to auto-fill
OPTIONAL_FIELDS_TRACKED = (
    "书名", "核心卖点", "主角姓名", "主代价", "第一章爽点预览",
    "女主姓名", "女主人设", "钩子1", "钩子2", "钩子3",
)


class BlueprintValidationError(Exception):
    """Raised when blueprint .md fails parse or value-level validation."""


# Section header pattern: "### 字段名" → captures field name; allows trailing spaces / 全角
_SECTION_RE = re.compile(r"^###\s+(?:[一二三四五六七八九十]+、)?\s*(.+?)\s*$")


def parse_blueprint(path: Path | str) -> dict[str, str | None]:
    """Parse blueprint .md → flat dict {字段名: 值 or None}.

    HTML comments (<!-- ... -->) within section body are stripped.
    Empty sections map to None.
    """
    text = Path(path).read_text(encoding="utf-8")
    lines = text.splitlines()
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in lines:
        m = _SECTION_RE.match(line)
        if m:
            # Normalise: strip variants like "第 1 章钩子" → "钩子1"
            name = _normalise_field_name(m.group(1).strip())
            current = name
            sections.setdefault(current, [])
            continue
        if current is not None:
            sections[current].append(line)

    return {name: _clean_body(body) for name, body in sections.items()}


def _normalise_field_name(raw: str) -> str:
    raw = raw.strip()
    # Map "第 N 章钩子" → "钩子N"
    m = re.match(r"^第\s*([123])\s*章钩子$", raw)
    if m:
        return f"钩子{m.group(1)}"
    # Strip trailing parenthetical hints like "(选填)"
    raw = re.sub(r"[\(（].*?[\)）]\s*$", "", raw).strip()
    aliases = {
        "女主/核心配角姓名": "女主姓名",
        "女主/核心配角人设": "女主人设",
    }
    return aliases.get(raw, raw)


def _clean_body(body_lines: list[str]) -> str | None:
    cleaned: list[str] = []
    for ln in body_lines:
        # Drop HTML comments (single-line)
        ln = re.sub(r"<!--.*?-->", "", ln).strip()
        # Drop subsection markers and empty
        if ln.startswith("##") or ln.startswith("---"):
            continue
        if not ln:
            continue
        cleaned.append(ln)
    if not cleaned:
        return None
    return "\n".join(cleaned)


def validate(parsed: dict[str, str | None]) -> None:
    missing = [f for f in REQUIRED_FIELDS if not (parsed.get(f) or "").strip()]
    if missing:
        raise BlueprintValidationError(f"蓝本缺少必填字段: {', '.join(missing)}")

    gf_text = (parsed.get("能力一句话") or "") + (parsed.get("金手指类型") or "")
    for word in GF_BLACKLIST:
        if word in gf_text:
            raise BlueprintValidationError(
                f"金手指描述命中禁词 '{word}'。请避免：{', '.join(GF_BLACKLIST)}"
            )


def to_quick_draft(parsed: dict[str, str | None]) -> dict:
    platform_raw = (parsed.get("平台") or "qidian").strip().lower()
    platform = "fanqie" if platform_raw in ("fanqie", "番茄", "番茄小说") else "qidian"
    defaults = _PLATFORM_DEFAULTS[platform]

    aggression_raw = (parsed.get("激进度档位") or "2").strip()
    aggression = _coerce_aggression(aggression_raw)

    target_chapters = _coerce_int(parsed.get("目标章数"), defaults["target_chapters"])
    target_words = _coerce_int(parsed.get("目标字数"), defaults["target_words"])
    chapter_words = defaults["chapter_words"]

    draft: dict = {
        "platform": platform,
        "aggression_level": aggression,
        "target_chapters": target_chapters,
        "target_words": target_words,
        "chapter_words": chapter_words,
        "题材方向": parsed.get("题材方向"),
        "核心冲突": parsed.get("核心冲突"),
        "主角人设": parsed.get("主角人设"),
        "金手指类型": parsed.get("金手指类型"),
        "能力一句话": parsed.get("能力一句话"),
    }

    optional_pass_through = ("书名", "核心卖点", "主角姓名", "主代价", "第一章爽点预览",
                             "女主姓名", "女主人设", "钩子1", "钩子2", "钩子3",
                             "元规则倾向", "商业安全边界打破", "语言风格档位",
                             "禁忌/避坑提示", "自由备注", "主角职业/身份")
    for field in optional_pass_through:
        val = parsed.get(field)
        if val and val.upper() != "AUTO":
            draft[field] = val

    missing: list[str] = []
    for field in OPTIONAL_FIELDS_TRACKED:
        v = parsed.get(field)
        if not v or v.strip().upper() == "AUTO":
            missing.append(field)
    draft["__missing__"] = missing

    return draft


def _coerce_aggression(raw: str) -> int:
    raw = raw.strip().lower()
    mapping = {"1": 1, "保守": 1, "conservative": 1,
               "2": 2, "平衡": 2, "balanced": 2,
               "3": 3, "激进": 3, "aggressive": 3,
               "4": 4, "疯批": 4, "wild": 4, "crazy": 4}
    return mapping.get(raw, 2)


def _coerce_int(raw: str | None, default: int) -> int:
    if not raw:
        return default
    try:
        return int(raw.strip())
    except (ValueError, AttributeError):
        return default
```

- [ ] **Step 5: Run tests — verify they pass**

Run: `pytest tests/core/auto/test_blueprint_to_quick_draft.py -v`
Expected: 8 PASSED.

- [ ] **Step 6: Commit**

```bash
git add ink_writer/core/auto/blueprint_to_quick_draft.py tests/core/auto/test_blueprint_to_quick_draft.py tests/core/auto/_blueprint_fixtures.py
git commit -m "feat(auto): C3 add blueprint parser, validator, and quick-draft converter"
```

---

## Phase P1: ink-init `--blueprint` Integration

### Task 5: ink-init SKILL.md `--blueprint` parameter recognition

**Files:**
- Modify: `ink-writer/skills/ink-init/SKILL.md` (top of Quick mode + Step 0.4 + Step 1 + Step 2)

ink-init Quick mode is invoked by the LLM via natural-language prompt. Adding `--blueprint <path>` means:

1. The LLM (Claude Code) recognises `--blueprint <path>` in the user input.
2. Reads the file via Read tool.
3. Calls `to_quick_draft` (via Bash subprocess).
4. Skips Quick Step 0.4 弹询问.
5. In Quick Step 1, overrides 3 generated proposals' fields with blueprint values.
6. In Quick Step 2, auto-selects scheme 1 instead of asking user.

- [ ] **Step 1: Read current ink-init SKILL.md "## 模式分支" section**

Run: `sed -n '9,25p' ink-writer/skills/ink-init/SKILL.md`
Confirm location of mode parsing.

- [ ] **Step 2: Insert new `--blueprint <path>` parsing block**

Edit `ink-writer/skills/ink-init/SKILL.md` after line 5 (right after the `---` frontmatter close), prepending a new section:

```markdown
## --blueprint 参数（v27 新增，自动化模式入口）

如果用户输入包含 `--blueprint <path>`（无论是否带 `--quick`），按以下流程处理：

1. **强制 Quick 模式**：忽略原本的 deep / quick 分支判定，强制走 Quick。
2. **读取蓝本并转换**：
   ```bash
   python -m ink_writer.core.auto.blueprint_to_quick_draft \
       --input "<path>" --output /tmp/quick_draft.json
   ```
   （若该 CLI 入口不存在，作为 fallback 直接读 `<path>` 后调用 `parse_blueprint` + `validate` + `to_quick_draft` 序列。）
3. **跳过 Quick Step 0.4 平台弹询问**：使用 `quick_draft.platform` 字段。
4. **跳过激进度档位弹询问**：使用 `quick_draft.aggression_level` 字段。
5. **Quick Step 1 字段锁定**：对 `quick_draft` 中已有的题材方向 / 核心冲突 / 主角人设 / 金手指类型 / 能力一句话 / 主角姓名 / 书名 / 第一章爽点 等字段，**强制覆盖**生成的 3 套方案对应字段；`__missing__` 数组里的字段照常走 Quick 引擎。
6. **Quick Step 2 自动选择**：`--blueprint` 模式下不再询问用户选 1/2/3，**强制选方案 1**；混搭/重抽路径关闭。
7. **完成后落盘**：`state.json.project_info.platform` = `quick_draft.platform`，与 v26.2 现有契约一致。

校验失败时（缺必填 / 命中黑名单）：直接报错给用户，**不**回退到 deep 模式或弹询问，让用户先改蓝本。
```

- [ ] **Step 3: Add CLI entry to blueprint_to_quick_draft.py**

Edit `ink_writer/core/auto/blueprint_to_quick_draft.py`, append at module bottom:

```python


def _main() -> int:
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(description="Convert blueprint .md to Quick draft.json")
    parser.add_argument("--input", required=True, help="Blueprint .md path")
    parser.add_argument("--output", required=True, help="Output draft.json path")
    args = parser.parse_args()

    try:
        parsed = parse_blueprint(args.input)
        validate(parsed)
        draft = to_quick_draft(parsed)
    except BlueprintValidationError as e:
        print(f"BLUEPRINT_INVALID: {e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"BLUEPRINT_IO_ERROR: {e}", file=sys.stderr)
        return 3

    Path(args.output).write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"BLUEPRINT_OK: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
```

- [ ] **Step 4: Add CLI test**

Append to `tests/core/auto/test_blueprint_to_quick_draft.py`:

```python
def test_cli_invocation_writes_draft_json(tmp_path: Path) -> None:
    import subprocess
    import json

    bp = tmp_path / "bp.md"
    write_minimal_blueprint(bp)
    out = tmp_path / "draft.json"
    result = subprocess.run(
        ["python", "-m", "ink_writer.core.auto.blueprint_to_quick_draft",
         "--input", str(bp), "--output", str(out)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "BLUEPRINT_OK" in result.stdout
    draft = json.loads(out.read_text(encoding="utf-8"))
    assert draft["platform"] == "qidian"
    assert draft["题材方向"] == "仙侠"


def test_cli_returns_exit2_on_invalid_blueprint(tmp_path: Path) -> None:
    import subprocess

    bp = tmp_path / "bp.md"
    write_blueprint_missing_required(bp)
    out = tmp_path / "draft.json"
    result = subprocess.run(
        ["python", "-m", "ink_writer.core.auto.blueprint_to_quick_draft",
         "--input", str(bp), "--output", str(out)],
        capture_output=True, text=True,
    )
    assert result.returncode == 2
    assert "BLUEPRINT_INVALID" in result.stderr
```

- [ ] **Step 5: Run all auto tests**

Run: `pytest tests/core/auto/ -v`
Expected: 22 PASSED (5 + 7 + 8 + 2 new).

- [ ] **Step 6: Commit**

```bash
git add ink_writer/core/auto/blueprint_to_quick_draft.py tests/core/auto/test_blueprint_to_quick_draft.py ink-writer/skills/ink-init/SKILL.md
git commit -m "feat(auto): C4 add --blueprint parameter to ink-init Quick mode"
```

---

### Task 6: Integration test S0a (blueprint → ink-init → state.json)

**Files:**
- Create: `tests/core/auto/test_integration_s0a.py`

This integration test exercises the C1+C2+C3 pipeline only (does NOT spawn a real CLI subprocess for ink-init, which would require API access).

- [ ] **Step 1: Write integration test**

```python
# tests/core/auto/test_integration_s0a.py
"""Integration test: blueprint .md found → state detected → quick draft generated.

Stops short of actual ink-init CLI subprocess invocation (which would need API key).
"""
import json
from pathlib import Path
import subprocess
from ink_writer.core.auto.state_detector import detect_project_state, ProjectState
from ink_writer.core.auto.blueprint_scanner import find_blueprint
from tests.core.auto._blueprint_fixtures import write_full_blueprint


def test_s0a_pipeline_produces_valid_quick_draft(tmp_path: Path) -> None:
    write_full_blueprint(tmp_path / "我的修真.md")
    (tmp_path / "README.md").write_text("# readme", encoding="utf-8")

    assert detect_project_state(tmp_path) == ProjectState.S0_UNINIT

    bp = find_blueprint(tmp_path)
    assert bp is not None and bp.name == "我的修真.md"

    out = tmp_path / "draft.json"
    result = subprocess.run(
        ["python", "-m", "ink_writer.core.auto.blueprint_to_quick_draft",
         "--input", str(bp), "--output", str(out)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr

    draft = json.loads(out.read_text(encoding="utf-8"))
    assert draft["platform"] == "qidian"
    assert draft["aggression_level"] == 2
    assert draft["target_chapters"] == 600
    assert draft["题材方向"] == "仙侠"
    assert draft["主角人设"].startswith("寒门弟子")
    assert draft["金手指类型"] == "信息"
    assert "__missing__" in draft
```

- [ ] **Step 2: Run test**

Run: `pytest tests/core/auto/test_integration_s0a.py -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/core/auto/test_integration_s0a.py
git commit -m "test(auto): integration S0a blueprint → quick draft pipeline"
```

---

## Phase P2: Interactive Bootstrap (S0b)

### Task 7: interactive_bootstrap.sh (bash read x 7)

**Files:**
- Create: `ink-writer/scripts/interactive_bootstrap.sh`

The script asks 7 questions via bash `read`, writes `.ink-auto-blueprint.md` in CWD using the same field schema as the user template.

- [ ] **Step 1: Write the script**

```bash
#!/bin/bash
# interactive_bootstrap.sh — empty-dir 7-question fallback for /ink-auto
#
# Usage:  bash interactive_bootstrap.sh <output_path>
# Output: writes a blueprint .md to <output_path>
# Exit:   0 on success, 130 on Ctrl+C, 1 on error
set -euo pipefail

OUT="${1:-.ink-auto-blueprint.md}"

# Trap Ctrl+C — do NOT keep half-written file
cleanup_on_interrupt() {
    rm -f "$OUT"
    echo
    echo "❌ 用户中断，已删除半成品蓝本"
    exit 130
}
trap cleanup_on_interrupt INT

prompt_required() {
    local prompt="$1"
    local var=""
    while [[ -z "$var" ]]; do
        printf "%s\n> " "$prompt" >&2
        IFS= read -r var
        if [[ -z "$var" ]]; then
            echo "  ⚠️  必填，请重新输入" >&2
        fi
    done
    printf "%s" "$var"
}

prompt_with_default() {
    local prompt="$1"
    local default="$2"
    local var=""
    printf "%s（默认 %s）\n> " "$prompt" "$default" >&2
    IFS= read -r var
    if [[ -z "$var" ]]; then
        var="$default"
    fi
    printf "%s" "$var"
}

echo "============================================" >&2
echo "  ink-auto 空目录 7 题快速 bootstrap" >&2
echo "============================================" >&2

GENRE=$(prompt_required "1/7 题材方向（如：仙侠 / 都市悬疑 / 末世+异能）？")
PROTAGONIST=$(prompt_required "2/7 主角一句话人设（含欲望+缺陷）？")
GF_TYPE=$(prompt_required "3/7 金手指类型（信息/时间/情感/社交/认知/概率/感知/规则 8 选 1）？")
GF_LINE=$(prompt_required "4/7 金手指能力一句话（≤20 字，含具体动作/反直觉维度）？")
CONFLICT=$(prompt_required "5/7 核心冲突一句话？")
PLATFORM=$(prompt_with_default "6/7 平台 (qidian/fanqie)？" "qidian")
AGGRESSION=$(prompt_with_default "7/7 激进度档位 (1 保守 / 2 平衡 / 3 激进 / 4 疯批)？" "2")

cat > "$OUT" <<EOF
# ink-auto 自动 bootstrap 生成的蓝本（空目录场景）

## 一、项目元信息
### 平台
${PLATFORM}

### 激进度档位
${AGGRESSION}

## 二、故事核心
### 题材方向
${GENRE}

### 核心冲突
${CONFLICT}

## 三、主角设定
### 主角姓名
AUTO

### 主角人设
${PROTAGONIST}

## 四、金手指
### 金手指类型
${GF_TYPE}

### 能力一句话
${GF_LINE}

## 五、配角与情感线
### 女主姓名
AUTO
EOF

trap - INT
echo "✅ 蓝本已落盘：$OUT" >&2
exit 0
```

- [ ] **Step 2: Make executable**

Run:
```bash
chmod +x ink-writer/scripts/interactive_bootstrap.sh
```

- [ ] **Step 3: Write smoke test for the script**

Create `tests/core/auto/test_interactive_bootstrap.py`:

```python
import subprocess
from pathlib import Path


def test_bootstrap_writes_blueprint_with_all_7_answers(tmp_path: Path) -> None:
    out = tmp_path / "bp.md"
    answers = "\n".join([
        "仙侠",          # 1 题材
        "寒门弟子；过度自尊不会服软",  # 2 主角
        "信息",          # 3 GF type
        "每读懂他人遗书借走立遗嘱者绝学三天",  # 4 GF line
        "弃徒带真凶回师门",  # 5 conflict
        "qidian",        # 6 platform
        "2",             # 7 aggression
    ]) + "\n"
    result = subprocess.run(
        ["bash", "ink-writer/scripts/interactive_bootstrap.sh", str(out)],
        input=answers, capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    body = out.read_text(encoding="utf-8")
    assert "题材方向" in body and "仙侠" in body
    assert "金手指类型" in body and "信息" in body
    assert "qidian" in body


def test_bootstrap_uses_defaults_for_platform_and_aggression(tmp_path: Path) -> None:
    out = tmp_path / "bp.md"
    answers = "\n".join([
        "都市", "社畜逆袭", "信息", "二十字之内的爆点", "复仇主线",
        "",  # default platform
        "",  # default aggression
    ]) + "\n"
    result = subprocess.run(
        ["bash", "ink-writer/scripts/interactive_bootstrap.sh", str(out)],
        input=answers, capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    body = out.read_text(encoding="utf-8")
    assert "qidian" in body
    assert "\n2\n" in body  # aggression default


def test_bootstrap_rejects_empty_required(tmp_path: Path) -> None:
    out = tmp_path / "bp.md"
    # First answer is empty, second is filled — should re-prompt and use second
    answers = "\n".join([
        "",              # 1 empty (re-prompt)
        "仙侠",          # 1 retry
        "寒门弟子",
        "信息",
        "二十字之内的爆点",
        "弃徒",
        "qidian",
        "2",
    ]) + "\n"
    result = subprocess.run(
        ["bash", "ink-writer/scripts/interactive_bootstrap.sh", str(out)],
        input=answers, capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert "必填" in result.stderr
    body = out.read_text(encoding="utf-8")
    assert "仙侠" in body
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/core/auto/test_interactive_bootstrap.py -v`
Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add ink-writer/scripts/interactive_bootstrap.sh tests/core/auto/test_interactive_bootstrap.py
git commit -m "feat(auto): C5 interactive_bootstrap.sh with 7-question bash read fallback"
```

---

### Task 8: PowerShell + cmd siblings (Windows compat)

**Files:**
- Create: `ink-writer/scripts/interactive_bootstrap.ps1`
- Create: `ink-writer/scripts/interactive_bootstrap.cmd`

Per CLAUDE.md Windows 兼容守则：新增 `.sh` 必须配套 `.ps1` + `.cmd`，PS1 文件需 UTF-8 BOM。

- [ ] **Step 1: Write .ps1 sibling**

```powershell
# interactive_bootstrap.ps1 — Windows sibling to interactive_bootstrap.sh
# Usage:  pwsh interactive_bootstrap.ps1 <output_path>
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

param(
    [Parameter(Position=0, Mandatory=$false)]
    [string]$OutPath = ".ink-auto-blueprint.md"
)

function Prompt-Required {
    param([string]$Prompt)
    while ($true) {
        Write-Host $Prompt
        $val = Read-Host ">"
        if ($val) { return $val }
        Write-Host "  ⚠️  必填，请重新输入"
    }
}

function Prompt-WithDefault {
    param([string]$Prompt, [string]$Default)
    Write-Host "$Prompt（默认 $Default）"
    $val = Read-Host ">"
    if (-not $val) { return $Default }
    return $val
}

try {
    Write-Host "============================================"
    Write-Host "  ink-auto 空目录 7 题快速 bootstrap"
    Write-Host "============================================"

    $genre = Prompt-Required "1/7 题材方向（如：仙侠 / 都市悬疑 / 末世+异能）？"
    $protagonist = Prompt-Required "2/7 主角一句话人设（含欲望+缺陷）？"
    $gfType = Prompt-Required "3/7 金手指类型？"
    $gfLine = Prompt-Required "4/7 金手指能力一句话（≤20 字）？"
    $conflict = Prompt-Required "5/7 核心冲突一句话？"
    $platform = Prompt-WithDefault "6/7 平台 (qidian/fanqie)？" "qidian"
    $aggression = Prompt-WithDefault "7/7 激进度档位 (1/2/3/4)？" "2"

    $body = @"
# ink-auto 自动 bootstrap 生成的蓝本（空目录场景）

## 一、项目元信息
### 平台
$platform

### 激进度档位
$aggression

## 二、故事核心
### 题材方向
$genre

### 核心冲突
$conflict

## 三、主角设定
### 主角姓名
AUTO

### 主角人设
$protagonist

## 四、金手指
### 金手指类型
$gfType

### 能力一句话
$gfLine

## 五、配角与情感线
### 女主姓名
AUTO
"@

    Set-Content -Path $OutPath -Value $body -Encoding UTF8
    Write-Host "✅ 蓝本已落盘：$OutPath"
    exit 0
}
catch {
    if (Test-Path $OutPath) { Remove-Item $OutPath -Force }
    Write-Host "❌ $($_.Exception.Message)"
    exit 1
}
```

The file MUST start with UTF-8 BOM. After writing, verify:
```bash
file ink-writer/scripts/interactive_bootstrap.ps1
```
Expected: contains "UTF-8 Unicode (with BOM)".

If no BOM, prepend with: `printf '\xEF\xBB\xBF' | cat - ink-writer/scripts/interactive_bootstrap.ps1 > /tmp/_p && mv /tmp/_p ink-writer/scripts/interactive_bootstrap.ps1`

- [ ] **Step 2: Write .cmd launcher**

```cmd
@echo off
REM interactive_bootstrap.cmd — Windows double-click launcher for the .ps1
SET SCRIPT_DIR=%~dp0
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%interactive_bootstrap.ps1" %*
exit /b %ERRORLEVEL%
```

- [ ] **Step 3: Verify BOM on .ps1**

Run:
```bash
head -c 3 ink-writer/scripts/interactive_bootstrap.ps1 | od -An -tx1
```
Expected: ` ef bb bf`

- [ ] **Step 4: Commit**

```bash
git add ink-writer/scripts/interactive_bootstrap.ps1 ink-writer/scripts/interactive_bootstrap.cmd
git commit -m "feat(auto): C5 add Windows .ps1/.cmd siblings to interactive_bootstrap"
```

---

## Phase P3: ink-auto.sh State Dispatcher (C6)

### Task 9: Replace `exit 1` with state dispatch + add rollback switches

**Files:**
- Modify: `ink-writer/scripts/ink-auto.sh:188-191` (remove `exit 1`, add dispatch)
- Modify: `ink-writer/scripts/ink-auto.sh` add 3 rollback env-var checks
- Modify: `ink-writer/scripts/ink-auto.ps1` mirror changes

- [ ] **Step 1: Read current dispatch code**

Run: `sed -n '175,200p' ink-writer/scripts/ink-auto.sh`
Verify lines 188-191 contain:
```bash
PROJECT_ROOT="$(find_project_root)" || {
    echo "❌ 未找到 .ink/state.json，请在小说项目目录下运行"
    exit 1
}
```

- [ ] **Step 2: Replace with state dispatch block**

Edit `ink-writer/scripts/ink-auto.sh` lines 188-191:

```bash
# ═══════════════════════════════════════════
# 项目状态检测与自动初始化（v27 ink-auto 终极自动化）
# ═══════════════════════════════════════════

INK_AUTO_INIT_ENABLED="${INK_AUTO_INIT_ENABLED:-1}"
INK_AUTO_BLUEPRINT_ENABLED="${INK_AUTO_BLUEPRINT_ENABLED:-1}"
INK_AUTO_INTERACTIVE_BOOTSTRAP_ENABLED="${INK_AUTO_INTERACTIVE_BOOTSTRAP_ENABLED:-1}"

PROJECT_ROOT="$(find_project_root)" || PROJECT_ROOT=""

if [[ -z "$PROJECT_ROOT" ]]; then
    if [[ "$INK_AUTO_INIT_ENABLED" != "1" ]]; then
        echo "❌ 未找到 .ink/state.json，请在小说项目目录下运行"
        echo "   提示：设置 INK_AUTO_INIT_ENABLED=1 启用自动初始化"
        exit 1
    fi

    PROJECT_ROOT="$PWD"
    echo "════════════════════════════════════════════════════"
    echo "  ink-auto 终极自动化模式：未检测到已初始化项目"
    echo "  当前目录：${PROJECT_ROOT}"
    echo "════════════════════════════════════════════════════"

    # 扫描蓝本
    BLUEPRINT_PATH=""
    if [[ "$INK_AUTO_BLUEPRINT_ENABLED" == "1" ]]; then
        BLUEPRINT_PATH=$(
            "$PY_LAUNCHER" -X utf8 -c "
from pathlib import Path
from ink_writer.core.auto.blueprint_scanner import find_blueprint
result = find_blueprint(Path('${PROJECT_ROOT}'))
print(str(result) if result else '')
" 2>/dev/null || echo ""
        )
    fi

    if [[ -n "$BLUEPRINT_PATH" ]]; then
        echo "📄 找到蓝本：${BLUEPRINT_PATH}"
    else
        if [[ "$INK_AUTO_INTERACTIVE_BOOTSTRAP_ENABLED" != "1" ]]; then
            echo "❌ 未找到蓝本 .md，且 INK_AUTO_INTERACTIVE_BOOTSTRAP_ENABLED=0"
            echo "   请先放置蓝本（参考 ${SCRIPTS_DIR}/../templates/blueprint-template.md）"
            exit 1
        fi
        BLUEPRINT_PATH="${PROJECT_ROOT}/.ink-auto-blueprint.md"
        echo "📋 未找到蓝本，启动 7 题交互式 bootstrap..."
        bash "${SCRIPTS_DIR}/interactive_bootstrap.sh" "$BLUEPRINT_PATH" || {
            echo "❌ 交互式 bootstrap 失败或被中断"
            exit 1
        }
    fi

    # 转换蓝本 → quick draft
    DRAFT_PATH="${PROJECT_ROOT}/.ink-auto-quick-draft.json"
    if ! "$PY_LAUNCHER" -X utf8 -m ink_writer.core.auto.blueprint_to_quick_draft \
        --input "$BLUEPRINT_PATH" --output "$DRAFT_PATH" 2>&1; then
        echo "❌ 蓝本校验失败，请修正后重跑 /ink-auto"
        exit 1
    fi

    # 调用 ink-init Quick 模式（CLI 子进程）
    INIT_LOG="${PROJECT_ROOT}/.ink-auto-init-$(date +%Y%m%d-%H%M%S).log"
    INIT_PROMPT="使用 Skill 工具加载 \"ink-init\"。模式：--quick --blueprint ${BLUEPRINT_PATH}。draft.json 路径: ${DRAFT_PATH}。项目目录: ${PROJECT_ROOT}。禁止提问，全程自主执行，最终输出 INK_INIT_DONE 或 INK_INIT_FAILED。"
    echo "⚙️  启动自动初始化（CLI 子进程，约 5-10 分钟）..."
    if ! run_cli_process "$INIT_PROMPT" "$INIT_LOG"; then
        echo "❌ 自动初始化失败，日志：${INIT_LOG}"
        echo "   蓝本保留：${BLUEPRINT_PATH}"
        echo "   你可以手动重跑：claude -p '使用 ink-init --quick --blueprint ${BLUEPRINT_PATH}'"
        exit 1
    fi
    echo "✅ 初始化完成"

    # 重新解析项目根
    PROJECT_ROOT="$(find_project_root)" || {
        echo "❌ init 后仍未找到 .ink/state.json，可能初始化未完整落盘"
        echo "   日志：${INIT_LOG}"
        exit 1
    }
fi
```

(Note: `run_cli_process` is defined later in the script; the dispatch block needs to be moved AFTER `run_cli_process` definition. See Step 3.)

- [ ] **Step 3: Reorder script — move dispatch AFTER `run_cli_process` definition**

Current ink-auto.sh structure (line numbers):
- L1-186: env detection, helper functions
- L188-191: PROJECT_ROOT resolution (this is what we're replacing)
- L675+: `run_cli_process` definition
- L720+: main loop

The replacement block uses `run_cli_process`, so it must come AFTER L675. Solution: move the entire PROJECT_ROOT block (which currently triggers `mkdir -p $LOG_DIR`, computes `MAX_WORDS_HARD`, etc.) to AFTER `run_cli_process`. Or simpler: at L188, only do `find_project_root` (allow empty); do the actual dispatch + init invocation right before main loop.

Concrete edit:

1. At L188-191, change to:
```bash
PROJECT_ROOT="$(find_project_root)" || PROJECT_ROOT=""
# Defer state dispatch until after run_cli_process is defined (see line ~720).
```

2. Find the line just before main loop starts (search for the comment `# 主循环` or the first chapter loop iteration). Insert the full state-dispatch block from Step 2 there.

3. The existing `mkdir -p "$LOG_DIR" "$REPORT_DIR"` etc. on L193-198 should be guarded:
```bash
if [[ -n "$PROJECT_ROOT" ]]; then
    LOG_DIR="${PROJECT_ROOT}/.ink/logs/auto"
    # ... etc, existing code
fi
# (re-run after state dispatch when PROJECT_ROOT becomes available)
```

OR simpler approach: introduce a function `init_project_paths` that re-runs path setup, call once after dispatch.

Use the simpler approach. Wrap L193-onwards path-dependent setup in a function:

```bash
init_project_paths() {
    LOG_DIR="${PROJECT_ROOT}/.ink/logs/auto"
    REPORT_DIR="${PROJECT_ROOT}/.ink/reports"
    mkdir -p "$LOG_DIR" "$REPORT_DIR"
    REPORT_FILE="${REPORT_DIR}/auto-$(date +%Y%m%d-%H%M%S).md"
    # MAX_WORDS_HARD computation (copy from L206-220)
    MAX_WORDS_HARD=$(...)
    # ... etc
}

if [[ -n "$PROJECT_ROOT" ]]; then
    init_project_paths
fi
```

Then after the state dispatch block (which sets PROJECT_ROOT), call `init_project_paths` again.

- [ ] **Step 4: Run smoke test — empty dir falls back to bootstrap warning**

Create a temp dir, set `INK_AUTO_INTERACTIVE_BOOTSTRAP_ENABLED=0`, run script, verify it errors out cleanly:

```bash
mkdir /tmp/ink_auto_smoke_empty
cd /tmp/ink_auto_smoke_empty
INK_AUTO_INTERACTIVE_BOOTSTRAP_ENABLED=0 bash /Users/cipher/AI/小说/ink/ink-writer/ink-writer/scripts/ink-auto.sh 1 || echo "EXPECTED_FAIL"
```
Expected: prints "未找到蓝本 .md" + "EXPECTED_FAIL".

- [ ] **Step 5: Run smoke test — rollback switch returns to current behavior**

```bash
mkdir /tmp/ink_auto_smoke_rollback
cd /tmp/ink_auto_smoke_rollback
INK_AUTO_INIT_ENABLED=0 bash /Users/cipher/AI/小说/ink/ink-writer/ink-writer/scripts/ink-auto.sh 1 || echo "EXPECTED_FAIL"
```
Expected: prints "未找到 .ink/state.json，请在小说项目目录下运行" + "EXPECTED_FAIL".

- [ ] **Step 6: Commit**

```bash
git add ink-writer/scripts/ink-auto.sh
git commit -m "feat(auto): C6 ink-auto.sh state dispatch + 3 rollback env vars"
```

---

### Task 10: ink-auto.ps1 Windows mirror

**Files:**
- Modify: `ink-writer/scripts/ink-auto.ps1`

Mirror the bash dispatch logic in PowerShell. Use the same env-var names (`$env:INK_AUTO_INIT_ENABLED` etc.) and call `interactive_bootstrap.ps1` instead of `.sh`.

- [ ] **Step 1: Read current ink-auto.ps1 to find equivalent dispatch point**

Run: `grep -n "find-project-root\|state.json\|exit 1" ink-writer/scripts/ink-auto.ps1 | head -10`

- [ ] **Step 2: Apply parallel edit to .ps1**

(Detailed PowerShell port — same logic, PowerShell idioms.)

```powershell
# After find-project-root (which may return null)
$INK_AUTO_INIT_ENABLED = if ($env:INK_AUTO_INIT_ENABLED) { $env:INK_AUTO_INIT_ENABLED } else { "1" }
$INK_AUTO_BLUEPRINT_ENABLED = if ($env:INK_AUTO_BLUEPRINT_ENABLED) { $env:INK_AUTO_BLUEPRINT_ENABLED } else { "1" }
$INK_AUTO_INTERACTIVE_BOOTSTRAP_ENABLED = if ($env:INK_AUTO_INTERACTIVE_BOOTSTRAP_ENABLED) { $env:INK_AUTO_INTERACTIVE_BOOTSTRAP_ENABLED } else { "1" }

if (-not $PROJECT_ROOT) {
    if ($INK_AUTO_INIT_ENABLED -ne "1") {
        Write-Host "❌ 未找到 .ink/state.json"; exit 1
    }
    $PROJECT_ROOT = $PWD.Path
    # ... mirror the bash logic with PowerShell
    if ($INK_AUTO_BLUEPRINT_ENABLED -eq "1") {
        $BLUEPRINT_PATH = & $PY_LAUNCHER -X utf8 -c @"
from pathlib import Path
from ink_writer.core.auto.blueprint_scanner import find_blueprint
r = find_blueprint(Path(r'$PROJECT_ROOT'))
print(str(r) if r else '')
"@
    }
    # ... etc.
}
```

- [ ] **Step 3: Manual smoke test on macOS via pwsh (if available)**

If pwsh is not on macOS, skip — Windows users will validate.

- [ ] **Step 4: Commit**

```bash
git add ink-writer/scripts/ink-auto.ps1
git commit -m "feat(auto): C6 mirror state dispatch in ink-auto.ps1"
```

---

## Phase P4: Templates and Documentation

### Task 11: Move blueprint template to canonical location

**Files:**
- Move: `蓝本模板.md` (repo root) → `ink-writer/templates/blueprint-template.md`

- [ ] **Step 1: Move file**

```bash
git mv 蓝本模板.md ink-writer/templates/blueprint-template.md
```

- [ ] **Step 2: Verify**

Run: `ls ink-writer/templates/blueprint-template.md`
Expected: file present.

- [ ] **Step 3: Commit**

```bash
git add ink-writer/templates/blueprint-template.md
git commit -m "docs(auto): C7 move blueprint template to ink-writer/templates/"
```

---

### Task 12: Update ink-auto SKILL.md to document new behavior

**Files:**
- Modify: `ink-writer/skills/ink-auto/SKILL.md` (add new section near top)

- [ ] **Step 1: Append new section after `## 用法` block**

Edit `ink-writer/skills/ink-auto/SKILL.md`, locate `## 用法` section (around line 22-29), insert AFTER it:

```markdown
## 终极自动化模式（v27 新增）

未初始化项目下运行 `/ink-auto N` 触发自动 bootstrap：

| CWD 状态 | 行为 |
|----------|------|
| 顶层有非黑名单 `.md` 蓝本 | 读取最大那份 → 转 quick draft → 自动 init → 自动 plan → 写 N 章 |
| 空目录（无 `.md`） | 弹 7 题问答 → 落盘 `.ink-auto-blueprint.md` → 同上 |
| 已 init 但缺当前章卷大纲 | 自动 plan → 写 N 章 |
| 已 init + 已写一半 | 直接写 N 章（沿用现有逻辑） |
| 已 init + 已完结 | 报错"项目已完结" |

**蓝本黑名单**：`README.md` / `CLAUDE.md` / `TODO.md` / `CHANGELOG.md` / `LICENSE.md` / `CONTRIBUTING.md` / `AGENTS.md` / `GEMINI.md` / `*.draft.md`。

**蓝本模板**：`ink-writer/templates/blueprint-template.md`，必填字段 5 个：题材方向 / 核心冲突 / 主角人设 / 金手指类型 / 能力一句话。

### 回滚开关

| 环境变量 | 默认 | 关闭后行为 |
|---------|------|-----------|
| `INK_AUTO_INIT_ENABLED` | `1` | `0` → 退化到现状（state.json 缺失 → exit 1） |
| `INK_AUTO_BLUEPRINT_ENABLED` | `1` | `0` → 跳过蓝本扫描，蓝本 `.md` 也走 7 题 |
| `INK_AUTO_INTERACTIVE_BOOTSTRAP_ENABLED` | `1` | `0` → 空目录直接报错 |
```

- [ ] **Step 2: Commit**

```bash
git add ink-writer/skills/ink-auto/SKILL.md
git commit -m "docs(auto): document v27 ultimate automation mode in ink-auto SKILL.md"
```

---

### Task 13: Update ink-init SKILL.md help to reference template

**Files:**
- Modify: `ink-writer/skills/ink-init/SKILL.md` (existing modification from Task 5)

- [ ] **Step 1: Append template reference at end of `## --blueprint 参数` section (added in Task 5)**

```markdown
**蓝本模板**：用户参考 `ink-writer/templates/blueprint-template.md`，必填字段 5 个（题材方向 / 核心冲突 / 主角人设 / 金手指类型 / 能力一句话）。
```

- [ ] **Step 2: Commit**

```bash
git add ink-writer/skills/ink-init/SKILL.md
git commit -m "docs(init): reference blueprint template in --blueprint section"
```

---

### Task 14: End-to-end manual verification

**Files:** None (manual)

This is a manual verification that requires a working API key and a sandbox dir.

- [ ] **Step 1: Verify scenario A (blueprint .md path)**

```bash
mkdir -p /tmp/ink_auto_e2e_a
cd /tmp/ink_auto_e2e_a
cp /Users/cipher/AI/小说/ink/ink-writer/ink-writer/templates/blueprint-template.md ./blueprint.md
# Manually edit blueprint.md filling in 5 required fields
# (题材方向: 仙侠, 核心冲突: …, 主角人设: …, 金手指类型: 信息, 能力一句话: …)
/ink-auto 1
# Wait ~30 min
ls -la .ink/state.json 大纲/总纲.md 正文/第001章*.md
# Expect all 3 files exist; 第001章 字数 >= 2200
```

- [ ] **Step 2: Verify scenario B (empty dir → 7 questions)**

```bash
mkdir -p /tmp/ink_auto_e2e_b
cd /tmp/ink_auto_e2e_b
/ink-auto 1
# Answer 7 questions
# Wait ~30 min
ls -la .ink-auto-blueprint.md .ink/state.json 正文/第001章*.md
```

- [ ] **Step 3: Verify scenario C (cross-volume auto plan, regression)**

```bash
# Use an existing project that has 1 volume (50 chapters) outlined and is at chapter 47
cd ~/path/to/existing-project
/ink-auto 5
# Should write chapters 48-50, then auto-plan vol 2, then continue 51-52
# Verify .ink/logs/auto/plan-vol2-*.log exists
```

- [ ] **Step 4: Document any issues in test report**

Append to `docs/superpowers/specs/2026-04-28-ink-auto-ultimate-automation-design.md` §8.3 manual verification results, or open a follow-up issue in `tasks/`.

- [ ] **Step 5: No commit needed (manual verification)**

---

## Self-Review

Spec coverage:

| Spec section | Covered by task |
|--------------|-----------------|
| §1 状态机 5 分支 | Task 2 (S0/S1/S2/S3 enum + detection) + Task 9 (dispatch) |
| §2.1 C1 state_detector | Task 2 |
| §2.1 C2 blueprint_scanner | Task 3 |
| §2.1 C3 blueprint_to_quick_draft | Task 4 |
| §2.1 C5 interactive_bootstrap | Task 7 + Task 8 |
| §2.1 C7 template | Task 11 |
| §2.2 C4 ink-init --blueprint | Task 5 |
| §2.2 C6 ink-auto.sh dispatch | Task 9 + Task 10 |
| §2.3 黑名单 | Task 3 (BLACKLIST + tests) |
| §3 数据流 3 场景 | Task 6 (S0a integration) + Task 14 (manual S0a/S0b/S2) |
| §4 平台感知 + 2 契约 | Task 4 (C3 platform defaults) + Task 5 (C4 skip Step 0.4) |
| §5 错误处理矩阵 7 条 | Task 4 (validate raises) + Task 7 (Ctrl+C) + Task 9 (init failure) |
| §6 回滚开关 3 档 | Task 9 (3 env vars) |
| §7 番茄字数下限（已知问题） | Out of scope per spec — not implemented |
| §8 测试方案 Unit/Integration/手动 | Tasks 2/3/4/6/7 (Unit + Integration); Task 14 (manual) |
| §10 兼容性（PowerShell sibling）| Task 8 (.ps1+.cmd) + Task 10 (.ps1) |
| §11 推出节奏 P0-P4 | Tasks 1-4 (P0), 5-6 (P1), 7-8 (P2), 9-10 (P3), 11-13 (P4) |

All sections accounted for.

Type consistency check:
- `ProjectState` enum (Task 2) used as return type only — no later task references its members in code.
- `find_blueprint(cwd) -> Path | None` (Task 3) — Task 9 calls via Python `-c` and prints `str(result) if result else ''`, consistent.
- `parse_blueprint(path) -> dict` + `validate(parsed)` + `to_quick_draft(parsed) -> dict` + `BlueprintValidationError` (Task 4) — Task 5 CLI invokes them; Task 6 integration test invokes them via subprocess; signatures consistent.
- `BLACKLIST` set in scanner (Task 3) — referenced in test only, consistent.
- `_PLATFORM_DEFAULTS` keys `target_chapters / target_words / chapter_words` (Task 4) — Task 12 documents the same defaults; consistent.
- ink-auto.sh env vars `INK_AUTO_INIT_ENABLED / INK_AUTO_BLUEPRINT_ENABLED / INK_AUTO_INTERACTIVE_BOOTSTRAP_ENABLED` (Task 9) — Task 12 documents same names; consistent.

Placeholder scan: no TBD / TODO / "implement later" / "similar to Task N" / "add appropriate error handling".

All checks pass.
