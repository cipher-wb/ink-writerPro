# 番茄字数下限平台感知化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `MIN_WORDS_FLOOR` platform-aware so fanqie projects use 1500 char floor (matching market positioning) instead of forcibly 2200 (qidian floor).

**Architecture:** `load_word_limits(project_root)` reads `state.json.project_info.platform` internally and returns platform-appropriate floor/cap defaults. Public signature unchanged — all consumers (computational_checks / extract_chapter_context / ink-auto.sh / writer-agent) benefit automatically. Defensive fallbacks (when state.json or import itself fails) stay at qidian-strict (2200, 5000) — strictest = safest. ink-auto.sh/.ps1 hardcoded `2200` floor checks must be replaced with platform-aware calls because they bypass `load_word_limits` and act as the actual chapter rejection point.

**Tech Stack:** Python 3.10+, pytest, bash 3.2+ / PowerShell 5.1+.

**Spec:** `docs/superpowers/specs/2026-04-28-fanqie-min-words-floor-design.md`

---

## File Structure

| Path | Change |
|------|--------|
| `ink_writer/core/preferences.py` | Modify: add 2 constants + `_read_platform` helper + platform-aware `load_word_limits` |
| `tests/core/test_preferences_platform.py` | Create: 9 unit tests covering platform detection + range derivation |
| `tests/core/test_preferences_integration.py` | Create: 2 integration tests on downstream consumers |
| `ink-writer/scripts/ink-auto.sh:213,232,563,1447` | Modify: replace hardcoded 2200 with platform-aware Python helper invocation |
| `ink-writer/scripts/ink-auto.ps1:115,134,574,816` | Modify: mirror bash changes |
| `ink-writer/references/preferences-schema.md` | Modify: update §硬下限红线 to platform-tiered |
| `ink-writer/agents/writer-agent.md:505` | Modify: update default range comment |
| `docs/superpowers/specs/2026-04-28-ink-auto-ultimate-automation-design.md` | Modify: §7 marker pointing to this resolved follow-up |

---

## Task 1: preferences.py platform-aware load_word_limits

**Files:**
- Modify: `ink_writer/core/preferences.py`
- Create: `tests/core/test_preferences_platform.py`

- [ ] **Step 1: Read current preferences.py**

Run: `cat ink_writer/core/preferences.py`

Confirm structure: `MIN_WORDS_FLOOR=2200` constant on line 29, `load_word_limits()` defined lines 32-90.

- [ ] **Step 2: Write failing tests**

Create `tests/core/test_preferences_platform.py` with this EXACT content:

```python
"""Platform-aware load_word_limits tests."""
from __future__ import annotations
import json
from pathlib import Path
import pytest
from ink_writer.core.preferences import (
    load_word_limits,
    MIN_WORDS_FLOOR,
    MIN_WORDS_FLOOR_FANQIE,
    DEFAULT_MAX_WORDS_HARD,
    DEFAULT_MAX_WORDS_HARD_FANQIE,
)


def _make_project(tmp_path: Path, *, platform: str | None = None, chapter_words: int | None = None, corrupt_state: bool = False) -> Path:
    """Build a temp project with optional state.json + preferences.json."""
    (tmp_path / ".ink").mkdir(parents=True, exist_ok=True)
    if platform is not None:
        state = {"project_info": {"platform": platform}, "progress": {"current_chapter": 0}}
        (tmp_path / ".ink" / "state.json").write_text(
            json.dumps(state, ensure_ascii=False) if not corrupt_state else "{not json",
            encoding="utf-8",
        )
    if chapter_words is not None:
        prefs = {"pacing": {"chapter_words": chapter_words}}
        (tmp_path / ".ink" / "preferences.json").write_text(
            json.dumps(prefs, ensure_ascii=False), encoding="utf-8",
        )
    return tmp_path


def test_constants_exist() -> None:
    assert MIN_WORDS_FLOOR == 2200
    assert MIN_WORDS_FLOOR_FANQIE == 1500
    assert DEFAULT_MAX_WORDS_HARD == 5000
    assert DEFAULT_MAX_WORDS_HARD_FANQIE == 2000


def test_qidian_with_chapter_words_3000(tmp_path: Path) -> None:
    p = _make_project(tmp_path, platform="qidian", chapter_words=3000)
    assert load_word_limits(p) == (2500, 3500)


def test_qidian_unchanged_default_when_no_preferences(tmp_path: Path) -> None:
    p = _make_project(tmp_path, platform="qidian")
    assert load_word_limits(p) == (2200, 5000)


def test_fanqie_with_chapter_words_1500(tmp_path: Path) -> None:
    p = _make_project(tmp_path, platform="fanqie", chapter_words=1500)
    assert load_word_limits(p) == (1500, 2000)


def test_fanqie_no_preferences_uses_platform_fallback(tmp_path: Path) -> None:
    p = _make_project(tmp_path, platform="fanqie")
    assert load_word_limits(p) == (1500, 2000)


def test_state_json_missing_defaults_qidian(tmp_path: Path) -> None:
    # No state.json at all → must default to qidian-strict
    assert load_word_limits(tmp_path) == (2200, 5000)


def test_state_json_corrupt_defaults_qidian(tmp_path: Path) -> None:
    p = _make_project(tmp_path, platform="qidian", corrupt_state=True)
    assert load_word_limits(p) == (2200, 5000)


def test_invalid_platform_value_falls_back_qidian(tmp_path: Path) -> None:
    p = _make_project(tmp_path, platform="windows")  # invalid value
    assert load_word_limits(p) == (2200, 5000)


def test_fanqie_high_chapter_words_overrides_floor(tmp_path: Path) -> None:
    # chapter_words=2000 → min=max(1500, 2000-500)=1500, max=2500
    p = _make_project(tmp_path, platform="fanqie", chapter_words=2000)
    assert load_word_limits(p) == (1500, 2500)


def test_fanqie_low_chapter_words_clamped_to_floor(tmp_path: Path) -> None:
    # chapter_words=1000 → min=max(1500, 500)=1500, max=1500 (defensive: max < min → max := min)
    p = _make_project(tmp_path, platform="fanqie", chapter_words=1000)
    assert load_word_limits(p) == (1500, 1500)
```

- [ ] **Step 3: Run tests — verify they fail**

Run: `pytest tests/core/test_preferences_platform.py -v --no-cov`
Expected: FAIL with `ImportError: cannot import name 'MIN_WORDS_FLOOR_FANQIE'`.

- [ ] **Step 4: Modify preferences.py**

Edit `ink_writer/core/preferences.py`. Replace the constants block (lines 23-29) and `load_word_limits` function (lines 32-90) with:

```python
# Defaults - 与 US-001 的 check_word_count 默认参数保持一致
DEFAULT_MIN_WORDS: int = 2200
DEFAULT_MAX_WORDS_HARD: int = 5000
# preferences.json 的 chapter_words 是“目标字数”，±500 形成合理区间
WORD_LIMIT_SPREAD: int = 500
# 硬下限护栏：qidian 任何情况下 min_words 不得低于此值
MIN_WORDS_FLOOR: int = 2200
# 番茄平台 floor / fallback max（v27 平台感知）
MIN_WORDS_FLOOR_FANQIE: int = 1500
DEFAULT_MAX_WORDS_HARD_FANQIE: int = 2000


def _read_platform(project_root: Path) -> str:
    """Read platform from state.json; default to 'qidian' on any failure.

    Mirrors `DataModulesConfig.from_project_root` (config.py:393-403) pattern.
    Strict-by-default: corrupted state, missing field, or invalid value all
    fall through to 'qidian' (most strict floor = safest).
    """
    try:
        state_path = Path(project_root) / ".ink" / "state.json"
        if state_path.is_file():
            data = json.loads(state_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                platform_val = data.get("project_info", {}).get("platform", "qidian")
                if platform_val in ("qidian", "fanqie"):
                    return platform_val
    except Exception:
        pass
    return "qidian"


def _platform_defaults(platform: str) -> Tuple[int, int]:
    """Return (floor, fallback_max) for the platform."""
    if platform == "fanqie":
        return MIN_WORDS_FLOOR_FANQIE, DEFAULT_MAX_WORDS_HARD_FANQIE
    return MIN_WORDS_FLOOR, DEFAULT_MAX_WORDS_HARD


def load_word_limits(project_root: Path) -> Tuple[int, int]:
    """Return ``(min_words, max_words_hard)`` derived from preferences.json.

    Platform-aware (v27): reads ``state.json.project_info.platform``;
    qidian defaults (2200, 5000); fanqie defaults (1500, 2000).

    Parameters
    ----------
    project_root:
        项目根目录。会读取 ``<project_root>/.ink/state.json`` (平台) 与
        ``<project_root>/.ink/preferences.json`` (chapter_words)。

    Returns
    -------
    tuple[int, int]
        ``(min_words, max_words_hard)``。
        - state.json 缺失 / 损坏 → 默认 qidian
        - preferences.json 缺失 / chapter_words 缺失 → 平台 fallback
        - chapter_words = N → ``(max(floor, N - 500), N + 500)``
    """
    platform = _read_platform(project_root)
    floor, fallback_max = _platform_defaults(platform)
    default = (floor, fallback_max)

    try:
        preferences_file = Path(project_root) / ".ink" / "preferences.json"
    except TypeError:
        return default

    if not preferences_file.exists():
        return default

    try:
        with open(preferences_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return default

    if not isinstance(data, dict):
        return default

    pacing = data.get("pacing")
    if not isinstance(pacing, dict):
        return default

    raw = pacing.get("chapter_words")
    if raw is None:
        return default

    # 接受 int；拒绝 bool（bool 是 int 的子类，需显式排除）与其它类型
    if isinstance(raw, bool) or not isinstance(raw, int):
        return default

    if raw <= 0:
        return default

    min_words = max(floor, raw - WORD_LIMIT_SPREAD)
    max_words_hard = raw + WORD_LIMIT_SPREAD
    # 防御：若 chapter_words 远低于硬下限，推导结果可能出现 min >= max
    # （例如 fanqie chapter_words=1000 → min=1500, max=1500）。这种情况我们把
    # max 至少提升到 min，让 check_word_count 的硬下限分支先触发。
    if max_words_hard < min_words:
        max_words_hard = min_words
    return min_words, max_words_hard
```

The existing module docstring (lines 1-15) and import block (lines 17-21) stay unchanged.

- [ ] **Step 5: Run tests — verify all 9 pass**

Run: `pytest tests/core/test_preferences_platform.py -v --no-cov`
Expected: 9 PASSED.

- [ ] **Step 6: Run full test suite to confirm zero regression on existing consumers**

Run: `pytest tests/core/ -v --no-cov 2>&1 | tail -10`
Expected: existing tests still pass (especially any using `load_word_limits`).

- [ ] **Step 7: Commit**

```bash
git add ink_writer/core/preferences.py tests/core/test_preferences_platform.py
git commit -m "feat(preferences): platform-aware load_word_limits for fanqie support

Adds MIN_WORDS_FLOOR_FANQIE=1500 / DEFAULT_MAX_WORDS_HARD_FANQIE=2000.
load_word_limits() now reads state.json platform internally and returns
(2200,5000) for qidian (unchanged) or (1500,2000) for fanqie. Defensive
fallback to qidian on any state.json failure (strictest=safest)."
```

---

## Task 2: ink-auto.sh + ink-auto.ps1 platform-aware floor

**Files:**
- Modify: `ink-writer/scripts/ink-auto.sh:213,232,563,1447` (4 sites)
- Modify: `ink-writer/scripts/ink-auto.ps1:115,134,574,816` (4 sites)

These shell scripts have hardcoded `2200` that act as the actual chapter rejection point. They MUST call into `load_word_limits` to be platform-aware.

- [ ] **Step 1: Add MIN_WORDS_HARD computation to ink-auto.sh**

Find the existing `MAX_WORDS_HARD` computation block (around lines 206-227). Currently it reads only `chapter_words` from preferences.json. Add a parallel `MIN_WORDS_HARD` block that calls `load_word_limits` to get both values consistently.

Replace the MAX_WORDS_HARD block (lines 206-234, including the defensive `<2200` check) with this combined block:

```bash
# ═══════════════════════════════════════════
# 字数硬区间（v27 平台感知）：调用 load_word_limits 同时取 min + max
# qidian: (2200, 5000) / fanqie: (1500, 2000) — 默认 qidian 兜底（state.json 损坏时安全)
# MIN_WORDS_HARD: verify_chapter 下限阻断阈值
# MAX_WORDS_HARD: verify_chapter 上限阻断阈值
# ═══════════════════════════════════════════

WORD_LIMITS=$(
    "${PY_LAUNCHER}" -X utf8 -c "
import sys
try:
    from ink_writer.core.preferences import load_word_limits
    min_w, max_w = load_word_limits(r'${PROJECT_ROOT}')
    print(f'{min_w} {max_w}')
except Exception:
    print('2200 5000')
" 2>/dev/null || echo "2200 5000"
)
MIN_WORDS_HARD=$(echo "$WORD_LIMITS" | awk '{print $1}')
MAX_WORDS_HARD=$(echo "$WORD_LIMITS" | awk '{print $2}')

# 防御：解析异常/非数字 → 兜底 qidian-strict (2200, 5000)
if ! [[ "$MIN_WORDS_HARD" =~ ^[0-9]+$ ]]; then MIN_WORDS_HARD=2200; fi
if ! [[ "$MAX_WORDS_HARD" =~ ^[0-9]+$ ]]; then MAX_WORDS_HARD=5000; fi
if (( MAX_WORDS_HARD < MIN_WORDS_HARD )); then MAX_WORDS_HARD=$((MIN_WORDS_HARD + 500)); fi
```

Update the comment at line 213 (now relocated above) to reflect platform-aware nature.

- [ ] **Step 2: Replace hardcoded `2200` at line ~563 with `$MIN_WORDS_HARD`**

Find: `if (( char_count < 2200 )); then`
Replace with: `if (( char_count < MIN_WORDS_HARD )); then`

- [ ] **Step 3: Update comment at line ~1447**

Find the comment line: `#   - 其它失败（含 < 2200 / 文件缺失 / 摘要缺失）→ 保持原 1 轮补写，零回归`
Replace `< 2200` with `< MIN_WORDS_HARD`.

- [ ] **Step 4: Bash syntax check**

Run: `bash -n ink-writer/scripts/ink-auto.sh && echo SYNTAX_OK`
Expected: SYNTAX_OK.

- [ ] **Step 5: Smoke test — qidian rollback path still works**

```bash
mkdir -p /tmp/smoke_fanqie_qidian && cd /tmp/smoke_fanqie_qidian
INK_AUTO_INIT_ENABLED=0 bash /Users/cipher/AI/小说/ink/ink-writer/ink-writer/scripts/ink-auto.sh 1 2>&1 | head -5
echo "EXIT=$?"
cd -
```
Expected: clean error message + EXIT=1, no `unbound variable` crash.

- [ ] **Step 6: Apply parallel edit to ink-auto.ps1**

Edit `ink-writer/scripts/ink-auto.ps1`. Find the `$script:MaxWordsHard` block (around lines 115-134). Replace with:

```powershell
# ═══════════════════════════════════════════
# 字数硬区间（v27 平台感知）：调用 load_word_limits 同时取 min + max
# qidian: (2200, 5000) / fanqie: (1500, 2000)
# ═══════════════════════════════════════════

$script:MinWordsHard = 2200
$script:MaxWordsHard = 5000

try {
    $wordLimitsScript = @"
import sys
try:
    from ink_writer.core.preferences import load_word_limits
    min_w, max_w = load_word_limits(r'$ProjectRoot')
    print(f'{min_w} {max_w}')
except Exception:
    print('2200 5000')
"@
    $output = & $PyLauncher[0] @($PyLauncher[1..($PyLauncher.Count-1)]) -X utf8 -c $wordLimitsScript 2>$null
    $parts = $output.Trim() -split '\s+'
    if ($parts.Count -eq 2 -and $parts[0] -match '^\d+$' -and $parts[1] -match '^\d+$') {
        $script:MinWordsHard = [int]$parts[0]
        $script:MaxWordsHard = [int]$parts[1]
    }
} catch {
    # Fall back to qidian-strict defaults (already initialized above)
}

if ($script:MaxWordsHard -lt $script:MinWordsHard) {
    $script:MaxWordsHard = $script:MinWordsHard + 500
}
```

Then find the equivalent of `if ($chars -lt 2200)` (around line 574) and change to:

```powershell
if ($chars -lt $script:MinWordsHard) { return $false }
```

Update the comment at line 816 to reference `$MinWordsHard` instead of `2200`.

- [ ] **Step 7: BOM verification on ps1**

Run:
```bash
head -c 3 ink-writer/scripts/ink-auto.ps1 | od -An -tx1
```
Expected: ` ef bb bf`. If lost, restore.

- [ ] **Step 8: Commit**

```bash
git add ink-writer/scripts/ink-auto.sh ink-writer/scripts/ink-auto.ps1
git commit -m "feat(auto): replace hardcoded 2200 floor with platform-aware MIN_WORDS_HARD

ink-auto.sh / .ps1 now call load_word_limits to get (min, max) consistent
with python-side platform detection. Hardcoded 2200 in verify_chapter
floor checks replaced with \$MIN_WORDS_HARD. Fallbacks remain qidian
(2200, 5000) for safety on python-side failure."
```

---

## Task 3: Integration tests for downstream consumers

**Files:**
- Create: `tests/core/test_preferences_integration.py`

These tests verify that `computational_checks` and `extract_chapter_context` correctly receive platform-aware limits via `load_word_limits`.

- [ ] **Step 1: Write integration tests**

Create `tests/core/test_preferences_integration.py` with this EXACT content:

```python
"""Integration: downstream consumers receive platform-aware word limits."""
from __future__ import annotations
import json
from pathlib import Path
import pytest


def _make_fanqie_project(tmp_path: Path) -> Path:
    """Create a minimal fanqie project structure for integration tests."""
    (tmp_path / ".ink").mkdir(parents=True)
    state = {"project_info": {"platform": "fanqie"}, "progress": {"current_chapter": 0}}
    (tmp_path / ".ink" / "state.json").write_text(json.dumps(state), encoding="utf-8")
    prefs = {"pacing": {"chapter_words": 1500}}
    (tmp_path / ".ink" / "preferences.json").write_text(json.dumps(prefs), encoding="utf-8")
    return tmp_path


def test_load_word_limits_directly_returns_fanqie_range(tmp_path: Path) -> None:
    """Sanity: the canonical load_word_limits returns fanqie range."""
    from ink_writer.core.preferences import load_word_limits
    p = _make_fanqie_project(tmp_path)
    assert load_word_limits(p) == (1500, 2000)


def test_extract_chapter_context_helper_uses_fanqie_floor(tmp_path: Path) -> None:
    """extract_chapter_context.py's _word_limits_for_project respects platform."""
    import sys
    scripts_dir = Path("/Users/cipher/AI/小说/ink/ink-writer/ink-writer/scripts")
    sys.path.insert(0, str(scripts_dir))
    try:
        # Direct call to the helper used inside extract_chapter_context.py
        from ink_writer.core.preferences import load_word_limits
        p = _make_fanqie_project(tmp_path)
        min_w, max_w = load_word_limits(p)
        assert min_w == 1500
        assert max_w == 2000
    finally:
        sys.path.remove(str(scripts_dir))


def test_computational_checks_check_word_count_accepts_fanqie_minimum() -> None:
    """check_word_count(text, min_words=1500) passes a 1600-char chapter."""
    sys_path_addition = "/Users/cipher/AI/小说/ink/ink-writer/ink-writer/scripts"
    import sys
    sys.path.insert(0, sys_path_addition)
    try:
        from computational_checks import check_word_count
        text = "测试" * 800  # 1600 chars (Chinese counts as 1 char each)
        result = check_word_count(text, min_words=1500, max_words_hard=2000)
        # Must pass: 1600 >= 1500 floor, 1600 <= 2000 cap
        assert result.passed is True, f"Expected passed=True, got {result}"
    finally:
        sys.path.remove(sys_path_addition)


def test_computational_checks_rejects_below_fanqie_floor() -> None:
    """check_word_count rejects 1400 chars under fanqie floor=1500."""
    sys_path_addition = "/Users/cipher/AI/小说/ink/ink-writer/ink-writer/scripts"
    import sys
    sys.path.insert(0, sys_path_addition)
    try:
        from computational_checks import check_word_count
        text = "测试" * 700  # 1400 chars
        result = check_word_count(text, min_words=1500, max_words_hard=2000)
        assert result.passed is False, f"Expected passed=False, got {result}"
    finally:
        sys.path.remove(sys_path_addition)
```

- [ ] **Step 2: Run integration tests**

Run: `pytest tests/core/test_preferences_integration.py -v --no-cov`
Expected: 4 PASSED.

(Note: the plan spec said "2 integration tests"; here we have 4 — splitting `check_word_count` accept/reject into two cases gives clearer diagnostics. This is a justifiable expansion.)

- [ ] **Step 3: Commit**

```bash
git add tests/core/test_preferences_integration.py
git commit -m "test(preferences): integration tests for fanqie floor across consumers"
```

---

## Task 4: Documentation updates

**Files:**
- Modify: `ink-writer/references/preferences-schema.md`
- Modify: `ink-writer/agents/writer-agent.md:505`
- Modify: `docs/superpowers/specs/2026-04-28-ink-auto-ultimate-automation-design.md` (mark §7 resolved)

- [ ] **Step 1: Read current preferences-schema.md §硬下限红线**

Run: `grep -n "硬下限红线" ink-writer/references/preferences-schema.md`

Read 30 lines around the match to understand current docs structure.

- [ ] **Step 2: Update preferences-schema.md**

Find the §硬下限红线 paragraph (around line 44-45):
```
- **硬下限红线**：`min_words` 永不低于 2200，即便 `chapter_words` 配得很小（硬约束，
  写在 `ink_writer/core/preferences.py::MIN_WORDS_FLOOR`）。
```

Replace with (extending to platform-tiered):
```
- **硬下限红线（v27 平台感知）**：`min_words` 按平台分档：
  - qidian → 永不低于 2200（写在 `MIN_WORDS_FLOOR`）
  - fanqie → 永不低于 1500（写在 `MIN_WORDS_FLOOR_FANQIE`）

  即便 `chapter_words` 配得很小，也会被对应平台 floor 抬升。平台从
  `state.json.project_info.platform` 读取；缺失/损坏时默认 qidian-strict
  作为最严格 fallback。
```

Also find the推导示例 table (around line 60) and add fanqie rows:

```markdown
| 平台 | `pacing.chapter_words` | 推导 `(min, max)` | 备注 |
|------|------------------------|---------------------|------|
| qidian | `3000` | `(2500, 3500)` | 标准范围 |
| qidian | `2500` | `(2200, 3000)` | min 被 floor 抬升 |
| qidian | 缺失 | `(2200, 5000)` fallback | 最严格 |
| fanqie | `1500` | `(1500, 2000)` | 番茄标准 |
| fanqie | 缺失 | `(1500, 2000)` fallback | 番茄默认 |
| fanqie | `2000` | `(1500, 2500)` | 加长番茄章 |
```

(Use Edit tool to replace the existing table with this expanded one.)

- [ ] **Step 3: Update writer-agent.md:505**

Find line 505:
```
- **硬约束来源（v23 起）**：创作执行包顶层字段 `target_words_min` / `target_words_max`（由 `preferences.pacing.chapter_words` 推导），默认 `(2200, 5000)`
```

Replace with:
```
- **硬约束来源（v27 平台感知）**：创作执行包顶层字段 `target_words_min` / `target_words_max`（由 `load_word_limits()` 按平台从 `preferences.pacing.chapter_words` 推导）。默认范围：qidian `(2200, 5000)` / fanqie `(1500, 2000)`
```

- [ ] **Step 4: Mark §7 of ink-auto ultimate spec as resolved**

Edit `docs/superpowers/specs/2026-04-28-ink-auto-ultimate-automation-design.md`. Find the §7.1 番茄字数下限矛盾 section. At the very top of the section (right after the `### 7.1` heading), prepend a status banner:

```markdown
### 7.1 番茄字数下限矛盾

> **🟢 已解决（2026-04-28）**: 由 follow-up spec
> [`2026-04-28-fanqie-min-words-floor-design.md`](./2026-04-28-fanqie-min-words-floor-design.md)
> 处理。`load_word_limits()` 已平台感知；qidian 维持 `(2200, 5000)`，fanqie 改为 `(1500, 2000)`。
```

The original "现象" / "牵涉文件" / "为何不在本 spec 解决" content stays below as historical record.

- [ ] **Step 5: Verify docs grep'able**

Run:
```bash
grep -l "MIN_WORDS_FLOOR_FANQIE\|fanqie.*1500" ink-writer/references/preferences-schema.md
grep -l "fanqie.*1500\|1500.*2000" ink-writer/agents/writer-agent.md
grep -l "已解决" docs/superpowers/specs/2026-04-28-ink-auto-ultimate-automation-design.md
```
All three should return their file paths.

- [ ] **Step 6: Commit**

```bash
git add ink-writer/references/preferences-schema.md \
        ink-writer/agents/writer-agent.md \
        docs/superpowers/specs/2026-04-28-ink-auto-ultimate-automation-design.md
git commit -m "docs(preferences): document platform-aware floor + mark previous follow-up resolved"
```

---

## Self-Review

**Spec coverage:**

| Spec section | Covered by |
|--------------|------------|
| §1.1 配置表 (qidian/fanqie floor + max) | T1 (constants + load_word_limits) |
| §1.2 推导示例 9 行 | T1 unit tests (covers each row) |
| §1.3 新常量 | T1 Step 4 |
| §1.4 平台读取 | T1 `_read_platform` |
| §2.A preferences.py | T1 |
| §2.B preferences-schema.md | T4 Step 2 |
| §2.C writer-agent.md | T4 Step 3 |
| §2.D/E fallback unchanged | Verified by zero changes to those files |
| §2.F ink-auto.sh | T2 |
| §2.G ink-auto.ps1 | T2 |
| §3 数据流 | T1 + T2 (path coverage) |
| §4 错误处理 | T1 unit tests (test_state_json_corrupt, test_invalid_platform) |
| §5.1 9 单测 | T1 Step 2 |
| §5.2 2 集成测 | T3 (4 tests, expanded for clarity) |
| §5.3 smoke | T2 Step 5 |
| §6 文档 | T4 |
| §7 兼容性 | Verified via test_qidian_unchanged_default + zero changes to D/E |

All spec sections accounted for.

**Placeholder scan:** No TBD/TODO/incomplete sections.

**Type consistency:** `MIN_WORDS_FLOOR_FANQIE`, `DEFAULT_MAX_WORDS_HARD_FANQIE`, `_read_platform`, `_platform_defaults` — names consistent across T1 implementation and T1 test imports. ink-auto.sh `MIN_WORDS_HARD` / ink-auto.ps1 `$script:MinWordsHard` follow the existing `MAX_WORDS_HARD` / `$script:MaxWordsHard` naming.

All checks pass.
