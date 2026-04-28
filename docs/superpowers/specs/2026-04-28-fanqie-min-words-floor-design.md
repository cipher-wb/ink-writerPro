# 番茄字数下限平台感知化设计

**Status**: Draft
**Date**: 2026-04-28
**Owner**: cipher-wb
**Scope**: 修复 fanqie 项目实际写作字数被全系统 `MIN_WORDS_FLOOR=2200` 强制拉高，与"番茄 1500-2000 字/章下沉市场"定位不符的一致性 bug。

## 0. 目标

把 `MIN_WORDS_FLOOR` 从全系统硬常量改为平台感知：

- qidian → floor 2200（不变）
- fanqie → floor 1500（新增）

API 契约保持不变：`load_word_limits(project_root)` 内部读取 `state.json.project_info.platform` 自动选择，所有消费方零改动。

**非目标**：

- 不改 `WORD_LIMIT_SPREAD=500`（保持平台对称的 ±500 推导）
- 不改 `DEFAULT_MAX_WORDS_HARD=5000` 的全局含义（仅新增 fanqie 专用 fallback `2000`）
- 不引入回滚开关（这是修一致性 bug，非 feature）

**前置背景**：本 spec 来自 `2026-04-28-ink-auto-ultimate-automation-design.md` §7 标记的 follow-up。

## 1. 核心契约

### 1.1 平台感知配置表

| 平台 | 默认 chapter_words | floor | fallback max（chapter_words 缺失时） | spread |
|------|-------------------|-------|------------------------------------|--------|
| qidian | 3000 | **2200**（不变） | 5000（不变） | ±500 |
| fanqie | 1500 | **1500**（新增） | **2000**（新增） | ±500 |

### 1.2 推导示例

| 平台 | preferences.json `chapter_words` | 返回 `(min, max)` |
|------|-----------------------------------|-------------------|
| qidian | 3000 | `(2500, 3500)` |
| qidian | 缺失 | `(2200, 5000)` fallback |
| qidian | 2500 | `(2200, 3000)`（min 被 floor 抬升） |
| fanqie | 1500 | `(1500, 2000)` |
| fanqie | 缺失 | `(1500, 2000)` fallback |
| fanqie | 2000 | `(1500, 2500)` |
| fanqie | 1000 | `(1500, 1500)`（max < min 触发现有防御代码自动抬 max） |

### 1.3 新常量

`ink_writer/core/preferences.py` 增加：

```python
MIN_WORDS_FLOOR: int = 2200            # qidian (default, unchanged)
MIN_WORDS_FLOOR_FANQIE: int = 1500     # fanqie new
DEFAULT_MAX_WORDS_HARD: int = 5000     # qidian (unchanged)
DEFAULT_MAX_WORDS_HARD_FANQIE: int = 2000  # fanqie new
```

### 1.4 平台读取（mirror DataModulesConfig）

`load_word_limits` 函数内新增 state.json 读取逻辑，与 `ink_writer/core/infra/config.py:393-403` 已有模式一致：

```python
def _read_platform(project_root: Path) -> str:
    try:
        state_path = project_root / ".ink" / "state.json"
        if state_path.exists():
            data = json.loads(state_path.read_text(encoding="utf-8"))
            platform_val = data.get("project_info", {}).get("platform", "qidian")
            if platform_val in ("qidian", "fanqie"):
                return platform_val
    except Exception:
        pass
    return "qidian"
```

## 2. 改造点（7 处）

| # | 文件 | 改动 |
|---|------|------|
| **A** | `ink_writer/core/preferences.py` | 新增 2 常量（FANQIE 版本）+ `_read_platform` 辅助函数 + `load_word_limits` 内部按平台分支返回；签名不变 |
| **B** | `ink-writer/references/preferences-schema.md` | 更新"硬下限红线"段：从"永不低于 2200"改为"按平台分档：qidian 2200 / fanqie 1500"；补全 fanqie 推导示例 |
| **C** | `ink-writer/agents/writer-agent.md:505` | 更新"硬约束来源"段：明确"由 `load_word_limits` 按平台推导，default 范围 qidian `(2200, 5000)` / fanqie `(1500, 2000)`" |
| **D** | `ink-writer/scripts/computational_checks.py:89,687` | 第 89 行 `min_words: int = 2200` 默认值不动；第 687 行 fallback `(2200, 5000)` 不动（永远走最严格 = 最安全） |
| **E** | `ink-writer/scripts/extract_chapter_context.py:64` | fallback `(2200, 5000)` 不动（同 D 安全策略） |
| **F** | `ink-writer/scripts/ink-auto.sh:222,537` | line 222 `MAX_WORDS_HARD < 2200` 防御下限改为按平台读 state.json；line 537 `char_count < 2200` 替换为读 `load_word_limits` 返回的 min_words |
| **G** | `ink-writer/scripts/ink-auto.ps1` | 同 F 镜像 |

### 2.1 关键设计决定

1. **C/D/E（默认值/fallback）保留 2200/5000 不变**：当 `load_word_limits` 因 state.json 损坏 / 解析失败时退化到这些 fallback，最严格 = 最安全（fanqie 项目失败时被推到 2200 顶多写多几百字，比反过来强）。
2. **F/G（ink-auto.sh / .ps1）必改**：当前硬编码 2200 是 verify_chapter 的实际阻断点，不改的话 fanqie 项目永远写不出 1500 字章节。

## 3. 数据流

### 3.1 fanqie 正常路径

```
state.json.project_info.platform = "fanqie"
preferences.json: {pacing: {chapter_words: 1500}}
       │
       ▼
load_word_limits(project_root)
   ├─ _read_platform → "fanqie"
   ├─ 读 preferences.json → chapter_words = 1500
   ├─ floor = MIN_WORDS_FLOOR_FANQIE = 1500
   ├─ min_words = max(1500, 1500-500) = 1500
   └─ max_words_hard = 1500+500 = 2000
   → 返回 (1500, 2000)
       │
       ├─ writer-agent 写章节，目标 1500-2000 字
       ├─ check_word_count 验证 [1500, 2000]
       ├─ ink-auto.sh verify_chapter: char_count >= 1500 通过
       └─ shrink loop: char_count > 2000 触发精简
```

### 3.2 fanqie 缺 preferences.json 回退

```
load_word_limits → preferences.json 不存在
   ├─ _read_platform → "fanqie"
   └─ 返回 (MIN_WORDS_FLOOR_FANQIE, DEFAULT_MAX_WORDS_HARD_FANQIE) = (1500, 2000)
```

### 3.3 state.json 损坏极端情况

```
load_word_limits → state.json 解析失败
   ├─ _read_platform → "qidian"（默认）
   └─ 返回 (2200, 5000) 最严格 fallback
```

## 4. 错误处理

| 失败场景 | 行为 |
|---------|------|
| state.json 解析失败 / 缺 platform 字段 | 默认 qidian → 返回 (2200, 5000)。fanqie 项目可能误识别为 qidian 一次，下次 plan/write 会重新读取，自愈 |
| platform 值非 `qidian`/`fanqie`（脏数据） | 走默认 qidian 分支（与现有 `DataModulesConfig` 行为一致） |
| preferences.json 损坏但 state.json 正常 | 用平台 fallback：qidian → (2200, 5000)，fanqie → (1500, 2000) |
| ink-auto.sh `load_word_limits` 调用失败 | 现有 fallback 5000（max）+ 2200（min）继续生效，最严格行为，无新增风险 |

## 5. 测试方案

### 5.1 Unit（pytest）

新增 `tests/core/test_preferences_platform.py`：

| 测试 | 验证 |
|------|------|
| `test_fanqie_with_chapter_words_1500` | preferences chapter_words=1500 + state.platform=fanqie → (1500, 2000) |
| `test_fanqie_no_preferences` | preferences.json 不存在 + state.platform=fanqie → (1500, 2000) fallback |
| `test_qidian_unchanged_default` | qidian 现有默认行为零回归：(2200, 5000) |
| `test_qidian_with_chapter_words_3000` | (2500, 3500) 不变 |
| `test_state_json_missing_defaults_qidian` | 无 state.json → 默认 qidian → (2200, 5000) |
| `test_state_json_corrupt_defaults_qidian` | 损坏 state.json → 默认 qidian → (2200, 5000) |
| `test_invalid_platform_value_falls_back_qidian` | platform="windows" → 默认 qidian |
| `test_fanqie_high_chapter_words_overrides_floor` | fanqie chapter_words=2000 → (1500, 2500)，floor 仍 1500，max=2500 |
| `test_fanqie_low_chapter_words_clamped_to_floor` | fanqie chapter_words=1000 → min=1500，max=1500（触发 max < min 现有防御） |

### 5.2 Integration（pytest）

| 测试 | 验证 |
|------|------|
| `test_computational_checks_uses_fanqie_floor` | 创建 fanqie 项目目录 + 写一章 1600 字 → check_word_count 通过；写一章 1400 字 → 不通过 |
| `test_extract_chapter_context_passes_fanqie_limits_to_writer` | extract_chapter_context.py 调用结果 `target_words_min=1500` |

### 5.3 Smoke（ink-auto.sh）

```bash
# 创建 fanqie 项目，模拟一章 1600 字（落在 [1500, 2000] 内）→ verify_chapter 通过
# 模拟一章 1400 字 → verify_chapter 触发补写
```

## 6. 文档更新

| 文件 | 改动 |
|------|------|
| `ink-writer/references/preferences-schema.md` | "硬下限红线"段从单一 2200 改为"按平台分档：qidian 2200 / fanqie 1500"；新增推导示例表（§ 1.2） |
| `docs/superpowers/specs/2026-04-28-ink-auto-ultimate-automation-design.md` | §7 标记此 follow-up spec 为已解决，加链接 |
| 现有 fanqie SKILL.md / templates / 其他 | 不动（消费方零改动是契约 A 的全部价值） |

## 7. 兼容性

- **现有 qidian 项目**：零行为变化（platform 字段非 fanqie → 走原 2200 floor）
- **现有 fanqie 项目（如有）**：自动获得 (1500, 2000) range——这是修复，不是 breaking。已写章节不会被回溯校验
- **零回滚开关**：这是修一致性 bug，不是新增 feature。如有问题直接 git revert

## 8. 实现工作量估算

| 改造点 | 复杂度 | 行数估 |
|--------|--------|--------|
| A `preferences.py` | 中 | +30 |
| B `preferences-schema.md` | 低 | +20 文档 |
| C `writer-agent.md` | 低 | +5 文档 |
| D/E 防御 fallback 不动 | 零 | 0 |
| F `ink-auto.sh` line 222 + 537 | 中 | +20 |
| G `ink-auto.ps1` | 中 | +20 |
| Unit 测试 | 中 | ~150 |
| Integration 测试 | 低 | ~60 |
| **总计** | | **~305 行** |
