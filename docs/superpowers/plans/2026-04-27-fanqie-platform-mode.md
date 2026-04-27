# 番茄小说平台模式 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有起点模式基础上新增番茄小说平台模式，init 时选择平台 → 标记写入 state.json → plan/write/auto/checker/prose 全链路按平台区分行为。

**Architecture:** 平台枚举 `qidian`/`fanqie` 存储在 `state.json` → `project_info.platform`。共享工具模块 `ink_writer/platforms/resolver.py` 提供 `get_platform(project_root)` 和 `resolve_platform_config(raw_config, platform)`，所有 checker/config-loader 统一消费。配置文件采用内嵌 `platforms:` 块格式，YAML 层处理平台分支；Python 模块内阈值通过 `get_platform()` 运行时分支。

**Tech Stack:** Python 3.10+ / YAML / 现有 ink_writer 架构

---

### Task 1: Platform utility module

**Files:**
- Create: `ink_writer/platforms/__init__.py`
- Create: `ink_writer/platforms/resolver.py`
- Create: `tests/platforms/test_resolver.py`

- [ ] **Step 1: Create `ink_writer/platforms/__init__.py`**

```python
"""Platform mode resolution utilities."""
from ink_writer.platforms.resolver import (
    get_platform,
    resolve_platform_config,
    PLATFORM_QIDIAN,
    PLATFORM_FANQIE,
    PLATFORM_DEFAULTS,
)
```

- [ ] **Step 2: Write the failing tests for resolver**

Create `tests/platforms/test_resolver.py`:

```python
import json
import tempfile
from pathlib import Path
from ink_writer.platforms.resolver import (
    get_platform,
    resolve_platform_config,
    PLATFORM_QIDIAN,
    PLATFORM_FANQIE,
)


def test_get_platform_returns_qidian_when_state_has_platform():
    root = Path(tempfile.mkdtemp())
    ink_dir = root / ".ink"
    ink_dir.mkdir()
    state = {"project_info": {"platform": "qidian"}}
    (ink_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")
    assert get_platform(root) == PLATFORM_QIDIAN


def test_get_platform_returns_fanqie_when_state_has_platform():
    root = Path(tempfile.mkdtemp())
    ink_dir = root / ".ink"
    ink_dir.mkdir()
    state = {"project_info": {"platform": "fanqie"}}
    (ink_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")
    assert get_platform(root) == PLATFORM_FANQIE


def test_get_platform_defaults_to_qidian_when_platform_missing():
    root = Path(tempfile.mkdtemp())
    ink_dir = root / ".ink"
    ink_dir.mkdir()
    state = {"project_info": {}}
    (ink_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")
    assert get_platform(root) == PLATFORM_QIDIAN


def test_get_platform_defaults_to_qidian_when_state_missing():
    root = Path(tempfile.mkdtemp())
    assert get_platform(root) == PLATFORM_QIDIAN


def test_resolve_platform_config_extracts_platform_block():
    raw = {
        "platforms": {
            "qidian": {"block_threshold": 60},
            "fanqie": {"block_threshold": 85},
        },
        "warn_threshold": 75,
    }
    qidian = resolve_platform_config(raw, PLATFORM_QIDIAN)
    fanqie = resolve_platform_config(raw, PLATFORM_FANQIE)
    assert qidian["block_threshold"] == 60
    assert qidian["warn_threshold"] == 75
    assert fanqie["block_threshold"] == 85
    assert fanqie["warn_threshold"] == 75


def test_resolve_platform_config_no_platforms_block_returns_original():
    raw = {"block_threshold": 60, "warn_threshold": 75}
    result = resolve_platform_config(raw, PLATFORM_FANQIE)
    assert result["block_threshold"] == 60
    assert result["warn_threshold"] == 75


def test_resolve_platform_config_platform_key_missing_falls_back_to_top():
    raw = {
        "platforms": {"qidian": {"block_threshold": 60}},
        "block_threshold": 70,
    }
    result = resolve_platform_config(raw, PLATFORM_FANQIE)
    assert result["block_threshold"] == 70
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd /Users/cipher/AI/小说/ink/ink-writer && python -m pytest tests/platforms/test_resolver.py -v
```

Expected: FAIL with ModuleNotFoundError for `ink_writer.platforms.resolver`

- [ ] **Step 4: Implement `ink_writer/platforms/resolver.py`**

```python
"""Platform mode resolution.

Reads platform from state.json → project_info.platform.
Defaults to qidian when missing or state.json absent.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PLATFORM_QIDIAN = "qidian"
PLATFORM_FANQIE = "fanqie"

VALID_PLATFORMS = {PLATFORM_QIDIAN, PLATFORM_FANQIE}

PLATFORM_LABELS = {
    PLATFORM_QIDIAN: "起点中文网",
    PLATFORM_FANQIE: "番茄小说",
}

PLATFORM_DEFAULTS = {
    PLATFORM_QIDIAN: {
        "target_chapters": 600,
        "target_words": 2_000_000,
        "chapter_word_count": 3000,
        "target_reader": "25-35岁男性老白读者",
    },
    PLATFORM_FANQIE: {
        "target_chapters": 800,
        "target_words": 1_200_000,
        "chapter_word_count": 1500,
        "target_reader": "35-55岁下沉市场男性",
    },
}


def get_platform(project_root: str | Path) -> str:
    """Read platform from state.json. Defaults to qidian."""
    root = Path(project_root)
    state_path = root / ".ink" / "state.json"
    if not state_path.exists():
        return PLATFORM_QIDIAN
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return PLATFORM_QIDIAN
    platform = (state.get("project_info") or {}).get("platform")
    if platform in VALID_PLATFORMS:
        return platform
    # Migrate legacy values
    if platform in ("起点", "起点中文网"):
        return PLATFORM_QIDIAN
    return PLATFORM_QIDIAN


def resolve_platform_config(
    raw: dict[str, Any],
    platform: str,
) -> dict[str, Any]:
    """Extract platform-specific config from a dict with optional `platforms:` block.

    If `raw` has a `platforms` key, merge `platforms.<platform>` over
    the top-level keys (platform values win). If `platforms` key is
    absent, return `raw` unchanged.
    """
    platforms_block = raw.get("platforms")
    if not isinstance(platforms_block, dict):
        return raw
    platform_overrides = platforms_block.get(platform)
    if not isinstance(platform_overrides, dict):
        return raw
    merged = dict(raw)
    merged.update(platform_overrides)
    return merged
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd /Users/cipher/AI/小说/ink/ink-writer && python -m pytest tests/platforms/test_resolver.py -v
```

Expected: all 6 tests PASS

- [ ] **Step 6: Commit**

```bash
git add ink_writer/platforms/ tests/platforms/
git commit -m "feat: add platform resolution utility module (qidian/fanqie)"
```

---

### Task 2: init_project.py — platform enum validation + defaults mapping

**Files:**
- Modify: `ink-writer/scripts/init_project.py:316-350` (state writing)
- Modify: `ink-writer/scripts/init_project.py:895` (argparse --platform)

- [ ] **Step 1: Add `--platform` choices to argparse**

In `init_project.py`, change line 895 from:
```python
parser.add_argument("--platform", default="", help="发布平台（深度模式）")
```
to:
```python
parser.add_argument(
    "--platform", default="qidian", choices=["qidian", "fanqie", "起点", "起点中文网", "番茄", "番茄小说"],
    help="发布平台: qidian | fanqie",
)
```

- [ ] **Step 2: Normalize platform value in `init_project()`**

After `init_project()` function signature (line 280), add normalization before the state-writing block. Insert after line 314 (`state = _ensure_state_schema(state)`):

```python
# Normalize platform to internal key
_platform_raw = (platform or "").strip()
_PLATFORM_ALIASES = {
    "起点": "qidian", "起点中文网": "qidian", "": "qidian",
    "番茄": "fanqie", "番茄小说": "fanqie",
}
platform_key = _PLATFORM_ALIASES.get(_platform_raw, _platform_raw)
if platform_key not in ("qidian", "fanqie"):
    platform_key = "qidian"
platform_label = PLATFORM_LABELS.get(platform_key, platform_key)

# Apply platform defaults for empty fields
if not target_reader:
    target_reader = PLATFORM_DEFAULTS[platform_key]["target_reader"]
if not target_chapters or target_chapters == 600:
    target_chapters = PLATFORM_DEFAULTS[platform_key]["target_chapters"]
if not target_words or target_words == 2_000_000:
    target_words = PLATFORM_DEFAULTS[platform_key]["target_words"]
```

And update the `from ink_writer.platforms.resolver import ...` import at the top of the file. Add after the existing imports (around line 34):

```python
from ink_writer.platforms.resolver import PLATFORM_DEFAULTS, PLATFORM_LABELS
```

- [ ] **Step 3: Write `platform_key` + `platform_label` to state.json**

In the `state["project_info"].update(...)` block (line 316), change:
```python
"platform": platform,
```
to:
```python
"platform": platform_key,
"platform_label": platform_label,
```

- [ ] **Step 4: Write failing test**

Create `tests/scripts/test_init_project_platform.py`:

```python
import json
import tempfile
from pathlib import Path
from ink_writer.scripts.init_project import init_project


def test_init_project_writes_qidian_platform():
    root = Path(tempfile.mkdtemp())
    init_project(str(root), "测试书名", "修仙", platform="qidian")
    state = json.loads((root / ".ink" / "state.json").read_text(encoding="utf-8"))
    assert state["project_info"]["platform"] == "qidian"
    assert state["project_info"]["platform_label"] == "起点中文网"


def test_init_project_writes_fanqie_platform():
    root = Path(tempfile.mkdtemp())
    init_project(str(root), "测试书名", "都市", platform="fanqie")
    state = json.loads((root / ".ink" / "state.json").read_text(encoding="utf-8"))
    assert state["project_info"]["platform"] == "fanqie"
    assert state["project_info"]["platform_label"] == "番茄小说"


def test_init_project_default_platform_is_qidian():
    root = Path(tempfile.mkdtemp())
    init_project(str(root), "测试书名", "修仙")
    state = json.loads((root / ".ink" / "state.json").read_text(encoding="utf-8"))
    assert state["project_info"]["platform"] == "qidian"


def test_init_project_fanqie_has_lower_word_targets():
    root = Path(tempfile.mkdtemp())
    init_project(str(root), "测试书名", "都市", platform="fanqie")
    state = json.loads((root / ".ink" / "state.json").read_text(encoding="utf-8"))
    assert state["project_info"]["target_chapters"] >= 800
    assert state["project_info"]["target_words"] <= 1_500_000
```

- [ ] **Step 5: Run tests**

```bash
cd /Users/cipher/AI/小说/ink/ink-writer && python -m pytest tests/scripts/test_init_project_platform.py -v
```

Expected: all 4 tests PASS

- [ ] **Step 6: Commit**

```bash
git add ink-writer/scripts/init_project.py tests/scripts/test_init_project_platform.py
git commit -m "feat: init_project platform enum validation + fanqie default word targets"
```

---

### Task 3: checker-thresholds.yaml — platform blocks for A-group checkers

**Files:**
- Modify: `config/checker-thresholds.yaml`

- [ ] **Step 1: Add `platforms` blocks to checker-thresholds.yaml**

After `writer_self_check:` block, add platform-specific overrides. Replace the flat thresholds for A-group checkers with platform-aware versions.

In `config/checker-thresholds.yaml`, change the `high_point:` block from:
```yaml
high_point:
  block_threshold: 70
  warn_threshold: 80
```
to:
```yaml
high_point:
  block_threshold: 70
  warn_threshold: 80
  platforms:
    qidian:
      block_threshold: 70
      warn_threshold: 80
    fanqie:
      block_threshold: 85
      warn_threshold: 90
```

Change the `reader_pull:` block from:
```yaml
reader_pull:
  block_threshold: 60
  warn_threshold: 75
  bound_cases_tags:
    - reader_pull
    - hook_density
```
to:
```yaml
reader_pull:
  block_threshold: 60
  warn_threshold: 75
  bound_cases_tags:
    - reader_pull
    - hook_density
  platforms:
    fanqie:
      block_threshold: 75
      warn_threshold: 85
```

Change the `chapter_hook_density:` block from:
```yaml
chapter_hook_density:
  block_threshold: 0.70
  warn_threshold: 0.85
  case_ids:
    - CASE-2026-M4-0007
```
to:
```yaml
chapter_hook_density:
  block_threshold: 0.70
  warn_threshold: 0.85
  case_ids:
    - CASE-2026-M4-0007
  platforms:
    fanqie:
      block_threshold: 0.85
      warn_threshold: 0.90
```

Change the `colloquial:` block from:
```yaml
colloquial:
  enabled: true
  block_threshold: 70
  warn_threshold: 80
  case_ids:
    - CASE-2026-0403
```
to:
```yaml
colloquial:
  enabled: true
  block_threshold: 70
  warn_threshold: 80
  case_ids:
    - CASE-2026-0403
  platforms:
    fanqie:
      block_threshold: 80
      warn_threshold: 88
      force_aggressive: true
```

Add `golden_three:` block (new — was previously only referenced in golden_three.py constants):
```yaml
golden_three:
  block_threshold: 0.75
  platforms:
    qidian:
      opening_window_chars: 300
    fanqie:
      opening_window_chars: 200
```

Add `emotion_curve:` platform block:
```yaml
emotion_curve:
  block_threshold: 65
  warn_threshold: 75
  platforms:
    fanqie:
      block_threshold: 75
      warn_threshold: 85
      require_high_frequency_fluctuation: true
```

- [ ] **Step 2: Validate YAML syntax**

```bash
cd /Users/cipher/AI/小说/ink/ink-writer && python -c "import yaml; yaml.safe_load(open('config/checker-thresholds.yaml')); print('YAML valid')"
```

Expected: `YAML valid`

- [ ] **Step 3: Commit**

```bash
git add config/checker-thresholds.yaml
git commit -m "feat: add platform blocks to checker-thresholds.yaml for A-group checkers"
```

---

### Task 3b: Separate YAML configs — platform blocks (reader-pull, emotion-curve, high-point-scheduler)

**Files:**
- Modify: `config/reader-pull.yaml`
- Modify: `config/emotion-curve.yaml`
- Modify: `config/high-point-scheduler.yaml`

- [ ] **Step 1: Add platform blocks to reader-pull.yaml**

In `config/reader-pull.yaml`, append:

```yaml
platforms:
  fanqie:
    score_threshold: 80.0
    golden_three_threshold: 85.0
    max_retries: 3
```

- [ ] **Step 2: Add platform blocks to emotion-curve.yaml**

In `config/emotion-curve.yaml`, append:

```yaml
platforms:
  fanqie:
    variance_threshold: 0.10
    flat_segment_max: 1
    score_threshold: 70.0
```

- [ ] **Step 3: Add platform blocks to high-point-scheduler.yaml**

In `config/high-point-scheduler.yaml`, append:

```yaml
platforms:
  fanqie:
    max_consecutive_no_hp: 1
    combo_window: 3
    opening_boost_chapters: 1
```

- [ ] **Step 4: Validate all YAML files**

```bash
cd /Users/cipher/AI/小说/ink/ink-writer && python -c "
import yaml
for f in ['config/reader-pull.yaml', 'config/emotion-curve.yaml', 'config/high-point-scheduler.yaml']:
    yaml.safe_load(open(f)); print(f'{f}: OK')
"
```

- [ ] **Step 5: Commit**

```bash
git add config/reader-pull.yaml config/emotion-curve.yaml config/high-point-scheduler.yaml
git commit -m "feat: add platform blocks to reader-pull, emotion-curve, high-point-scheduler configs"
```

---

### Task 4: thresholds_loader.py — platform-aware loading

**Files:**
- Modify: `ink_writer/checker_pipeline/thresholds_loader.py`
- Create: `tests/checker_pipeline/test_thresholds_loader_platform.py`

- [ ] **Step 1: Add `load_thresholds_for_platform()` to thresholds_loader.py**

```python
"""M3 阈值加载器：读 config/checker-thresholds.yaml，支持平台解析。

ink-write 启动时调一次 load_thresholds_for_platform(platform)，把 dict 透传给 rewrite_loop / 各 checker。
M3 期间不做热更新；修改 yaml 后需重启 writer。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ink_writer.platforms.resolver import resolve_platform_config

DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "config"
    / "checker-thresholds.yaml"
)


class ThresholdsConfigError(RuntimeError):
    """阈值配置加载失败（缺文件 / yaml 解析失败）。"""


def load_thresholds(path: Path | str | None = None) -> dict[str, Any]:
    """加载 M3 阈值 yaml；缺文件或解析失败 raise ThresholdsConfigError。"""
    if path is None:
        path = DEFAULT_CONFIG_PATH
    path = Path(path)

    if not path.exists():
        raise ThresholdsConfigError(
            f"checker-thresholds.yaml not found: {path}"
        )

    try:
        with open(path, encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise ThresholdsConfigError(
            f"failed to parse checker-thresholds.yaml: {exc}"
        ) from exc

    if not isinstance(raw, dict):
        raise ThresholdsConfigError(
            f"checker-thresholds.yaml must be a mapping at top level, got {type(raw).__name__}"
        )

    return raw


def load_thresholds_for_platform(
    platform: str,
    path: Path | str | None = None,
) -> dict[str, Any]:
    """Load thresholds and resolve platform-specific overrides.

    For each top-level key that is a dict, if it has a `platforms`
    sub-key, merge `platforms.<platform>` into that dict before returning.
    """
    raw = load_thresholds(path)
    resolved: dict[str, Any] = {}
    for section_key, section_val in raw.items():
        if isinstance(section_val, dict):
            resolved[section_key] = resolve_platform_config(section_val, platform)
        else:
            resolved[section_key] = section_val
    return resolved
```

- [ ] **Step 2: Write test**

Create `tests/checker_pipeline/test_thresholds_loader_platform.py`:

```python
import tempfile
from pathlib import Path
import yaml
from ink_writer.checker_pipeline.thresholds_loader import (
    load_thresholds_for_platform,
)


def test_load_thresholds_for_platform_resolves_fanqie():
    raw = {
        "high_point": {
            "block_threshold": 70,
            "warn_threshold": 80,
            "platforms": {
                "fanqie": {"block_threshold": 85},
            },
        },
        "logic_gap": 2,
    }
    tmp = Path(tempfile.mktemp(suffix=".yaml"))
    tmp.write_text(yaml.dump(raw), encoding="utf-8")
    result = load_thresholds_for_platform("fanqie", path=tmp)
    assert result["high_point"]["block_threshold"] == 85
    assert result["high_point"]["warn_threshold"] == 80
    assert result["logic_gap"] == 2


def test_load_thresholds_for_platform_qidian_uses_defaults():
    raw = {
        "high_point": {
            "block_threshold": 70,
            "platforms": {"fanqie": {"block_threshold": 85}},
        },
    }
    tmp = Path(tempfile.mktemp(suffix=".yaml"))
    tmp.write_text(yaml.dump(raw), encoding="utf-8")
    result = load_thresholds_for_platform("qidian", path=tmp)
    assert result["high_point"]["block_threshold"] == 70
```

- [ ] **Step 3: Run tests**

```bash
cd /Users/cipher/AI/小说/ink/ink-writer && python -m pytest tests/checker_pipeline/test_thresholds_loader_platform.py -v
```

Expected: 2 tests PASS

- [ ] **Step 4: Commit**

```bash
git add ink_writer/checker_pipeline/thresholds_loader.py tests/checker_pipeline/test_thresholds_loader_platform.py
git commit -m "feat: add platform-aware threshold loading to thresholds_loader"
```

---

### Task 5: DataModulesConfig — pacing/strand platform awareness

**Files:**
- Modify: `ink_writer/core/infra/config.py:334-349`

- [ ] **Step 1: Add platform-aware properties to DataModulesConfig**

After the existing pacing/strand config properties (around line 349), add:

```python
    # ================= 平台感知 pacing/strand =================
    _platform: str = "qidian"

    @property
    def platform(self) -> str:
        return self._platform

    @platform.setter
    def platform(self, value: str) -> None:
        if value in ("qidian", "fanqie"):
            self._platform = value

    @property
    def pacing_words_per_point_block(self) -> int:
        """爽点间隔字数门禁（平台感知）。"""
        if self._platform == "fanqie":
            return 500
        return self.pacing_words_per_point_acceptable

    @property
    def strand_quest_max_consecutive_platform(self) -> int:
        """Quest strand 最大连续章数（番茄更短）。"""
        if self._platform == "fanqie":
            return 3
        return self.strand_quest_max_consecutive
```

- [ ] **Step 2: Write test**

Create `tests/core/infra/test_config_platform.py`:

```python
from ink_writer.core.infra.config import DataModulesConfig


def test_pacing_platform_fanqie_tighter():
    cfg = DataModulesConfig()
    cfg.platform = "fanqie"
    assert cfg.pacing_words_per_point_block == 500


def test_pacing_platform_qidian_default():
    cfg = DataModulesConfig()
    cfg.platform = "qidian"
    assert cfg.pacing_words_per_point_block == cfg.pacing_words_per_point_acceptable


def test_strand_platform_fanqie_shorter():
    cfg = DataModulesConfig()
    cfg.platform = "fanqie"
    assert cfg.strand_quest_max_consecutive_platform == 3
```

- [ ] **Step 3: Run tests**

```bash
cd /Users/cipher/AI/小说/ink/ink-writer && python -m pytest tests/core/infra/test_config_platform.py -v
```

Expected: 3 tests PASS

- [ ] **Step 4: Commit**

```bash
git add ink_writer/core/infra/config.py tests/core/infra/test_config_platform.py
git commit -m "feat: add platform-aware pacing/strand properties to DataModulesConfig"
```

---

### Task 6: ink-init SKILL.md — platform selection

**Files:**
- Modify: `ink-writer/skills/ink-init/SKILL.md`

- [ ] **Step 1: Add platform selection to Deep Mode Step 1**

In `ink-writer/skills/ink-init/SKILL.md`, after Step 1 的题材集合（around line 626）and before Step 2, add:

```markdown
### Step 1.5：目标平台选择（必收）

在题材和规模确认后，追加平台选择：

调用 `AskUserQuestion`：

```
题干：目标发布平台？
选项：
- 起点中文网（长篇付费，3000-3500字/章，深度世界观，老白读者）
- 番茄小说（免费广告，1500-2000字/章，快节奏，下沉市场）
```

选择后：
- `fanqie` → 自动设置 `target_chapters=800`、`target_words=1,200,000`、`chapter_word_count=1500`、`target_reader=35-55岁下沉市场男性`
- `qidian` → 保持现有默认值（600章 / 200万字 / 3000字/章）

写入内部数据模型 `project.platform`。
```

- [ ] **Step 2: Add platform selection to Quick Mode**

In Quick Mode section, before Quick Step 0.5 (激进度档位选择), add:

```markdown
### Quick Step 0.4：平台选择

Quick Step 0 完成后，弹出平台选择（与激进度档位独立）：

调用 `AskUserQuestion`：
- 题干：目标发布平台？
- 选项：
  - 起点中文网（长篇付费，老白读者）
  - 番茄小说（免费广告，下沉市场）

选择后写入会话上下文 `platform ∈ {qidian, fanqie}`，影响：
- Quick Step 0 WebSearch 源分流（fanqie 只搜番茄榜单，qidian 只搜起点榜单）
- Quick Step 3 初始化时 `--platform` 参数
```

- [ ] **Step 3: Update WebSearch section for platform-specific search**

In Quick Step 0 WebSearch section, update the search queries to note platform routing:

Change the fixed 4 search queries description from "不可配置" to add platform routing:

```markdown
**平台路由**（v26.2 新增）：
- `platform=qidian` → 只执行起点 2 条检索（1, 2），跳过番茄检索
- `platform=fanqie` → 只执行番茄 2 条检索（3, 4），跳过起点检索
- `platform` 未确定时仍执行全部 4 条（兼容存量）
```

- [ ] **Step 4: Update `--platform` in init command template**

In the init command (around line 879), update the `--platform` argument:

Change:
```
--platform "{platform}" --opening-hook "{opening_hook}"
```
to:
```
--platform "{platform_key}" --opening-hook "{opening_hook}"
```

And add a note:
```markdown
`platform_key` 传 `qidian` 或 `fanqie`（内部枚举 key，不是中文标签）。
```

- [ ] **Step 5: Commit**

```bash
git add ink-writer/skills/ink-init/SKILL.md
git commit -m "feat: add platform selection step to ink-init (Deep + Quick mode)"
```

---

### Task 7: ink-plan reference files — platform-specific sections

**Files:**
- Modify: `ink-writer/skills/ink-plan/references/outlining/chapter-planning.md:87-104`
- Modify: `ink-writer/skills/ink-plan/references/outlining/outline-structure.md:199`
- Modify: `ink-writer/skills/ink-plan/SKILL.md`

- [ ] **Step 1: Rewrite chapter-planning.md §3 with platform sections**

Replace lines 87-104 of `chapter-planning.md` (the entire §3 "章节字数控制"):

```markdown
## 3. 章节字数控制（平台感知）

> 实际字数目标从 `.ink/state.json` → `project_info.platform` 读取，
> 以下为各平台默认值。

### 起点中文网（qidian）

- **标准字数**: 3000字/章
- **字数分配黄金比例**:
  - 开头钩子: 10%（300字）
  - 剧情发展: 50%（1500字）
  - 高潮爽点: 33%（1000字）
  - 结尾钩子: 7%（200字）
- **爽点密度**: 每 1000 字至少 1 个小爽点

### 番茄小说（fanqie）

- **标准字数**: 1500字/章
- **字数分配**:
  - 开头钩子: 15%（225字）
  - 冲突升级: 40%（600字）
  - 爽点爆发: 35%（525字）
  - 结尾钩子: 10%（150字）
- **爽点密度**: 每 500 字至少 1 个小爽点
- **冲突模式**: "看不起我→我亮身份→你跪下" 直白循环，禁止阴谋诡计
- **章末钩子**: 强制，不留悬念直接阻断

### 特殊情况（两平台通用）

- **大高潮章节**: 起点可写到 5000-6000 字；番茄可写到 2500-3000 字
- **过渡章节**: 起点可压缩到 2500 字；番茄可压缩到 1000 字
```

Also update the template word counts in §7 (lines 207-250): change hardcoded `**字数**: 3000` to platform-aware annotation:
```markdown
**字数**: 3000（起点）/ 1500（番茄）
```

And update line 255 self-check:
```markdown
- [ ] **字数**: 起点 2000-4000 字区间？番茄 1000-2000 字区间？
```

- [ ] **Step 2: Update outline-structure.md platform check**

In `outline-structure.md`, line 199, change:
```markdown
- [ ] **字数**: 预估总字数是否符合平台要求？（起点至少100万字）
```
to:
```markdown
- [ ] **字数**: 预估总字数是否符合平台要求？（起点至少100万字，番茄至少60万字）
```

- [ ] **Step 3: Update ink-plan SKILL.md**

Add a note in the SKILL.md preamble section that the plan step reads platform from state.json and routes to the correct reference section:

After the opening sections, add:
```markdown
## 平台感知（v26.2）

ink-plan 从 `.ink/state.json` → `project_info.platform` 读取平台（`qidian` | `fanqie`），
所有章节参数（字数/爽点密度/冲突风格）按平台取值。详见 `references/outlining/chapter-planning.md` §3。
```

- [ ] **Step 4: Commit**

```bash
git add ink-writer/skills/ink-plan/
git commit -m "feat: add platform-specific chapter word count and structure sections to ink-plan refs"
```

---

### Task 8: ink-write SKILL.md — platform injection into creation exec package

**Files:**
- Modify: `ink-writer/skills/ink-write/SKILL.md`

- [ ] **Step 1: Add platform injection section to ink-write SKILL.md**

In `ink-writer/skills/ink-write/SKILL.md`, add after the preamble:

```markdown
## 平台感知（v26.2）

Step 1（context-agent）读取 `.ink/state.json` → `project_info.platform`，
在创作执行包中注入以下平台参数：

| 字段 | qidian | fanqie |
|------|--------|--------|
| `target_chapter_words` | 3000 | 1500 |
| `cool_point_interval` | 1000 | 500 |
| `conflict_style` | 多层次/有谋略 | 直白打脸循环 |
| `hook_requirement` | 章末强钩子 | 章末必须有悬念，否则阻断 |
| `dialogue_ratio` | ≥30% | ≥40% |
| `narration_style` | 可适度描写 | 少描写多动作 |

writer-agent 消费这些字段调整正文输出。
```

- [ ] **Step 2: Add fanqie chapter-end hook hard block step**

After the writer-agent produces the draft and before polish, add a check for fanqie platform:

```markdown
### Step 2A.6：番茄章末钩子硬阻断（仅 fanqie）

若 `platform=fanqie`，对 writer-agent 产出的草稿执行章末钩子检查：

检查章末 100 字是否包含钩子信号：
- 悬念句（以 `？` 或 `...` 结尾的问句/省略句）
- 未闭合问题（含 `突然` / `就在这时` / `然而` / `但是` / `没想到` 等转折词）
- 反转预告（含 `冷笑` / `震惊` / `跪下` / `颤抖` / `哑然` 等情绪爆发词）
- 情绪高点（含 `竟然` / `不可能` / `怎么` / `难道` 等惊叹词）

规则检查（Python regex fallback）：
```python
import re
HOOK_PATTERNS = [
    r"[？?]",                          # 悬念问句
    r"\.{3,}",                          # 省略号
    r"突然|就在这时|然而|但是|没想到",   # 转折
    r"冷笑|震惊|跪下|颤抖|哑然",         # 情绪爆发
    r"竟然|不可能|怎么|难道",            # 惊叹词
]
def check_chapter_end_hook(text: str) -> bool:
    tail = text[-100:]
    return any(re.search(p, tail) for p in HOOK_PATTERNS)
```

不通过 → 退回 writer-agent 重写章末 200 字，附反馈：「章末 100 字未检测到钩子信号（悬念/转折/情绪爆发），请追加钩子」。

最多重试 2 次。2 次仍失败 → 标记 `needs_human_review` 并在 polish 阶段由 polish-agent 追加钩子句。
```

- [ ] **Step 3: Commit**

```bash
git add ink-writer/skills/ink-write/SKILL.md
git commit -m "feat: add platform injection + fanqie chapter-end hook hard block to ink-write"
```

---

### Task 9: ink-auto SKILL.md — platform passthrough

**Files:**
- Modify: `ink-writer/skills/ink-auto/SKILL.md`

- [ ] **Step 1: Add platform passthrough note**

At the top of `ink-writer/skills/ink-auto/SKILL.md`, add:

```markdown
## 平台感知（v26.2）

auto 是 plan → write → review → polish 的编排器，平台差异已下沉到各阶段。
auto 在启动时从 `.ink/state.json` → `project_info.platform` 读取平台，
并将 `platform` 参数透传给每个子步骤（ink-plan / ink-write / ink-review）。

auto 本身不做平台特定逻辑。
```

- [ ] **Step 2: Commit**

```bash
git add ink-writer/skills/ink-auto/SKILL.md
git commit -m "feat: add platform passthrough note to ink-auto SKILL.md"
```

---

### Task 10: A-group checker — consume platform-resolved config

**Files:**
- Modify: `ink_writer/checker_pipeline/` — each checker's entry point where it reads thresholds
- (Actual files depend on how each checker reads config; the pattern is the same)

- [ ] **Step 1: Update checker config loading pattern**

For each A-group checker (high-point, reader-pull, golden-three, emotion-curve, colloquial, directness, pacing), change config loading from:

```python
thresholds = load_thresholds()
high_point_threshold = thresholds["high_point"]["block_threshold"]
```

to:

```python
from ink_writer.platforms.resolver import get_platform
from ink_writer.checker_pipeline.thresholds_loader import load_thresholds_for_platform

platform = get_platform(project_root)
thresholds = load_thresholds_for_platform(platform)
high_point_threshold = thresholds["high_point"]["block_threshold"]
```

The key change: replace `load_thresholds()` with `load_thresholds_for_platform(platform)` in all checker entry points.

Checkers affected and their config keys:
- `high_point_checker` → `thresholds["high_point"]`
- `reader_pull_checker` → `thresholds["reader_pull"]`
- `golden_three_checker` → `thresholds["golden_three"]`
- `emotion_curve_checker` → `thresholds["emotion_curve"]`
- `colloquial_checker` → `thresholds["colloquial"]`
- `pacing_checker` → `DataModulesConfig.platform` (set before reading pacing props)

- [ ] **Step 2: Verify each checker loads platform-aware config**

For each checker file, grep for `load_thresholds` to confirm it uses the right loader:

```bash
cd /Users/cipher/AI/小说/ink/ink-writer && grep -rn "load_thresholds" ink_writer/ --include="*.py" | grep -v __pycache__ | grep -v test_
```

Expected: each checker that reads thresholds should use `load_thresholds_for_platform`

- [ ] **Step 3: Commit**

```bash
git add ink_writer/checker_pipeline/ ink_writer/high_point/ ink_writer/reader_pull/ ink_writer/emotion/ ink_writer/golden_three/ ink_writer/prose/
git commit -m "feat: wire platform-aware config loading into A-group checkers"
```

---

### Task 11: B-group checker — logic adaptations

**Files:**
- Modify: `ink_writer/prose/prose_impact_checker.py` (if exists) or the prose-impact checker agent
- Modify: `ink_writer/anti_detection/` — add fanqie rule
- Modify: `ink_writer/editor_wisdom/` — add fanqie rule set

- [ ] **Step 1: prose-impact-checker — adjust weights for fanqie**

In the prose-impact checker (locate the actual file with `find`):

```bash
find /Users/cipher/AI/小说/ink/ink-writer -name "*prose*impact*" -o -name "*impact*checker*" | grep -v __pycache__
```

If the checker is an agent (SKILL.md-based), add platform-aware weighting to its spec. If it's a Python module, add:

```python
def get_prose_impact_weights(platform: str) -> dict[str, float]:
    if platform == "fanqie":
        return {
            "lens_diversity": 0.10,     # 镜头多样性 — 降低（少描写）
            "sensory_richness": 0.15,
            "sentence_rhythm": 0.20,     # 句式节奏 — 提高
            "verb_sharpness": 0.25,      # 动词锐度 — 提高（多动作）
            "env_emotion_resonance": 0.10,
            "closeup_absence": 0.20,     # 特写缺失 — 提高
        }
    return {
        "lens_diversity": 0.20,
        "sensory_richness": 0.20,
        "sentence_rhythm": 0.15,
        "verb_sharpness": 0.15,
        "env_emotion_resonance": 0.15,
        "closeup_absence": 0.15,
    }
```

- [ ] **Step 2: anti-detection-checker — add fanqie compound-sentence rule**

In `ink_writer/anti_detection/` or the anti-detection checker agent:

Add fanqie-specific zero-tolerance rule:
```python
FANQIE_EXTRA_RULES = {
    "FQ-001": {
        "id": "FQ-001",
        "pattern": r"[^。！？\n]{25,}",
        "description": "番茄模式：超过 25 字的复合修饰句，下沉用户看不懂",
        "severity": "high",
    },
}
```

When `platform == "fanqie"`, merge `FANQIE_EXTRA_RULES` into `zero_tolerance_rules` before checking.

- [ ] **Step 3: editor-wisdom-checker — fanqie rule set**

In the editor-wisdom checker, when `platform == "fanqie"`, inject additional rule categories:
- 家庭伦理冲突
- 打脸循环（看不起→亮身份→跪下）
- 身份掉马

The rule injection uses the existing `editor_wisdom/context_injection.py` mechanism — add a `platform` filter parameter.

- [ ] **Step 4: Commit**

```bash
git add ink_writer/prose/ ink_writer/anti_detection/ ink_writer/editor_wisdom/
git commit -m "feat: B-group checker logic adaptations for fanqie platform"
```

---

### Task 12: Prose Anti-AI — colloquial lock + anti-detection fanqie rules

**Files:**
- Modify: `ink_writer/prose/colloquial_checker.py`
- Modify: `config/anti-detection.yaml`
- Modify: `config/colloquial.yaml`

- [ ] **Step 1: Lock colloquial to aggressive mode for fanqie**

In `colloquial_checker.py`, at the point where the colloquial aggressiveness level is read:

```python
from ink_writer.platforms.resolver import get_platform

def get_colloquial_level(project_root, config: dict) -> str:
    platform = get_platform(project_root)
    if platform == "fanqie":
        return "aggressive"  # 番茄强制激进档，不可下调
    return config.get("level", "balanced")
```

- [ ] **Step 2: Add fanqie zero-tolerance rule to anti-detection.yaml**

In `config/anti-detection.yaml`, add under `zero_tolerance_rules`:

```yaml
zero_tolerance_rules:
  # ... existing rules ...

  # === 番茄专属规则 ===
  FQ-001:
    id: FQ-001
    description: "禁止超过25字的复合修饰句（下沉用户看不懂）"
    pattern: "[^。！？\\n]{25,}"
    severity: high
    platforms:
      - fanqie
```

- [ ] **Step 3: Add fanqie force-aggressive flag to colloquial.yaml**

In `config/colloquial.yaml`, add:

```yaml
platforms:
  fanqie:
    force_aggressive: true
    min_level: aggressive
```

- [ ] **Step 4: Commit**

```bash
git add ink_writer/prose/colloquial_checker.py config/anti-detection.yaml config/colloquial.yaml
git commit -m "feat: lock colloquial to aggressive + add fanqie anti-detection rule"
```

---

### Task 13: market-positioning.md — update fanqie reader profile

**Files:**
- Modify: `ink-writer/skills/ink-init/references/creativity/market-positioning.md:38-61`

- [ ] **Step 1: Update fanqie section with accurate reader profile**

Replace lines 38-61 (the §1.2 番茄小说 section):

```markdown
### 1.2 番茄小说

**读者画像**：
- **核心年龄**：35-55岁男性为主，三四线城市
- **职业**：外卖员/快递员/工厂工人/出租车司机/个体户
- **付费习惯**：免费阅读+广告分账，作者收入靠广告曝光量
- **阅读偏好**：小人物逆袭、被低估后扬眉吐气、家庭伦理冲突
- **阅读场景**：短时间碎片化阅读（等单、午休、睡前）
- **阅读习惯**：每章必须有爽点，不爽就划走

**题材优势**：
- ✅ 赘婿逆袭（爽文经典）
- ✅ 战神归来（身份掉马）
- ✅ 乡村题材（贴近生活）
- ✅ 家庭伦理（情感共鸣）
- ✅ 都市脑洞（快节奏反转）

**平台特色**：
- 免费模式+广告分账（读者数量 > 读者质量）
- 算法推荐驱动（完读率=生命线）
- 短章节友好（1500-2000字/章）
- 要求"广场舞大妈也能看懂"的白话程度

**爆款底层逻辑**：
- 每 500 字必须有一个小爽点
- 冲突直白："看不起我→我亮身份→你跪下"循环
- 禁止阴谋诡计、权谋暗算
- 章末必须留悬念，不留悬念读者直接关页面
```

- [ ] **Step 2: Commit**

```bash
git add ink-writer/skills/ink-init/references/creativity/market-positioning.md
git commit -m "docs: update fanqie reader profile in market-positioning.md"
```

---

### Task 14: Integration test — end-to-end platform mode

**Files:**
- Create: `tests/integration/test_platform_mode_e2e.py`

- [ ] **Step 1: Write end-to-end test**

```python
"""End-to-end test: init project with fanqie platform, verify all artifacts."""
import json
import tempfile
from pathlib import Path
from ink_writer.scripts.init_project import init_project
from ink_writer.platforms.resolver import get_platform
from ink_writer.checker_pipeline.thresholds_loader import (
    load_thresholds_for_platform,
)


def test_fanqie_init_produces_correct_state():
    root = Path(tempfile.mkdtemp())
    init_project(str(root), "测试番茄书", "都市+重生", platform="fanqie")

    # Verify state.json
    state = json.loads((root / ".ink" / "state.json").read_text(encoding="utf-8"))
    assert state["project_info"]["platform"] == "fanqie"
    assert state["project_info"]["platform_label"] == "番茄小说"
    assert state["project_info"]["target_chapters"] >= 800
    assert state["project_info"]["target_words"] <= 1_500_000

    # Verify platform resolution
    assert get_platform(root) == "fanqie"


def test_qidian_init_produces_correct_state():
    root = Path(tempfile.mkdtemp())
    init_project(str(root), "测试起点书", "修仙", platform="qidian")

    state = json.loads((root / ".ink" / "state.json").read_text(encoding="utf-8"))
    assert state["project_info"]["platform"] == "qidian"
    assert state["project_info"]["target_chapters"] == 600
    assert state["project_info"]["target_words"] == 2_000_000


def test_thresholds_fanqie_differs_from_qidian():
    thresholds_qidian = load_thresholds_for_platform("qidian")
    thresholds_fanqie = load_thresholds_for_platform("fanqie")

    # fanqie should have different high_point threshold
    assert (
        thresholds_fanqie["high_point"]["block_threshold"]
        != thresholds_qidian["high_point"]["block_threshold"]
    )

    # fanqie colloquial should have force_aggressive flag
    assert thresholds_fanqie["colloquial"].get("force_aggressive") is True
    assert thresholds_qidian["colloquial"].get("force_aggressive") is not True


def test_unknown_platform_defaults_to_qidian():
    root = Path(tempfile.mkdtemp())
    init_project(str(root), "测试", "修仙", platform="")
    assert get_platform(root) == "qidian"
```

- [ ] **Step 2: Run integration tests**

```bash
cd /Users/cipher/AI/小说/ink/ink-writer && python -m pytest tests/integration/test_platform_mode_e2e.py -v
```

Expected: 4 tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_platform_mode_e2e.py
git commit -m "test: add end-to-end integration tests for platform mode"
```

---

### Task 15: Legacy project migration — silent auto-migrate

**Files:**
- Modify: `ink_writer/platforms/resolver.py` — migration logic already in `get_platform()`

- [ ] **Step 1: Add migration writing to `get_platform()`**

Update `get_platform()` in `resolver.py` to write back migrated platform value:

```python
def get_platform(project_root: str | Path, *, migrate: bool = True) -> str:
    """Read platform from state.json. Defaults to qidian.

    If migrate=True and the state.json has a legacy or missing platform,
    write back the resolved value.
    """
    root = Path(project_root)
    state_path = root / ".ink" / "state.json"
    if not state_path.exists():
        return PLATFORM_QIDIAN
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return PLATFORM_QIDIAN

    project_info = state.get("project_info") or {}
    platform = project_info.get("platform")

    needs_migration = False
    if platform in VALID_PLATFORMS:
        return platform
    if platform in ("起点", "起点中文网"):
        resolved = PLATFORM_QIDIAN
        needs_migration = True
    else:
        resolved = PLATFORM_QIDIAN
        needs_migration = True

    if migrate and needs_migration:
        from datetime import datetime
        project_info["platform"] = resolved
        project_info["platform_migrated"] = True
        project_info["migration_date"] = datetime.now().strftime("%Y-%m-%d")
        state["project_info"] = project_info
        try:
            state_path.write_text(
                json.dumps(state, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass  # best-effort

    return resolved
```

- [ ] **Step 2: Write migration test**

In `tests/platforms/test_resolver.py`, add:

```python
def test_get_platform_migrates_empty_to_qidian():
    root = Path(tempfile.mkdtemp())
    ink_dir = root / ".ink"
    ink_dir.mkdir()
    state = {"project_info": {"title": "test"}}  # no platform
    (ink_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")
    result = get_platform(root)
    assert result == "qidian"
    # Verify migration wrote back
    updated = json.loads((ink_dir / "state.json").read_text(encoding="utf-8"))
    assert updated["project_info"]["platform"] == "qidian"
    assert updated["project_info"]["platform_migrated"] is True


def test_get_platform_migrates_legacy_chinese_label():
    root = Path(tempfile.mkdtemp())
    ink_dir = root / ".ink"
    ink_dir.mkdir()
    state = {"project_info": {"platform": "起点"}}
    (ink_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")
    result = get_platform(root)
    assert result == "qidian"
```

- [ ] **Step 3: Run tests**

```bash
cd /Users/cipher/AI/小说/ink/ink-writer && python -m pytest tests/platforms/test_resolver.py -v
```

Expected: all tests PASS (6 original + 2 new = 8)

- [ ] **Step 4: Commit**

```bash
git add ink_writer/platforms/resolver.py tests/platforms/test_resolver.py
git commit -m "feat: add silent auto-migration for legacy platform values in state.json"
```

---

### Task 16: Final validation — run all tests

- [ ] **Step 1: Run full test suite**

```bash
cd /Users/cipher/AI/小说/ink/ink-writer && python -m pytest tests/platforms/ tests/checker_pipeline/test_thresholds_loader_platform.py tests/core/infra/test_config_platform.py tests/scripts/test_init_project_platform.py tests/integration/test_platform_mode_e2e.py -v
```

Expected: all tests PASS

- [ ] **Step 2: Verify import chain**

```bash
cd /Users/cipher/AI/小说/ink/ink-writer && python -c "
from ink_writer.platforms.resolver import get_platform, resolve_platform_config, PLATFORM_QIDIAN, PLATFORM_FANQIE
from ink_writer.checker_pipeline.thresholds_loader import load_thresholds_for_platform
print('All imports OK')
print('Qidian thresholds:', list(load_thresholds_for_platform('qidian').keys())[:5])
print('Fanqie thresholds:', list(load_thresholds_for_platform('fanqie').keys())[:5])
"
```

Expected: imports succeed, both platform configs load

- [ ] **Step 3: Commit final checkpoint**

```bash
git add -A
git diff --staged --stat
git commit -m "chore: final validation — all platform mode tests pass"
```
