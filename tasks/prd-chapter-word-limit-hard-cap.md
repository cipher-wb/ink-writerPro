# PRD: 章节字数硬上限强制执行

## Introduction

ink-writer 当前字数约束体系**严重非对称**：硬下限 2200 字在多层（`computational_checks.py`、`ink-auto.sh`、`SKILL.md` 2A.5）强制阻断，但硬上限只是 prompt 里的文字建议，无任何代码层阻断，且豁免条款被 LLM 自行滥用。用户在 `preferences.json` 写入的字数偏好也**没有任何 caller 读取并注入**到字数校验。

实际事故：第 1 章写出 ~10000 字，审查仅产生 severity=`soft` 的警告，未阻断放行。

本 PRD 目标：让字数上限与下限**对等硬约束**，让用户 `preferences.json` 的 `pacing.chapter_words` 真正驱动写作目标与阻断，并收紧 LLM 自行豁免的路径。

## Goals

- `check_word_count` 默认产出硬上限阻断（hard severity），而非 soft 警告
- `preferences.json` 的 `pacing.chapter_words` 单值配置可直接推导出 [min, max] 区间并覆盖默认硬上限
- `ink-auto.sh` 在章节产出层对称检测上限超标并触发精简循环（最多 3 轮）
- 写前阶段：writer-agent 在生成时即受 `target_words_max` 硬约束，而非靠写后阻断兜底
- 彻底删除 LLM 自行判定"关键章"豁免的路径；不设任何大纲/白名单级豁免（选项 4D）

## User Stories

### US-001: `check_word_count` 支持硬/软双阈值上限
**Description:** 作为写作流水线，我需要 `check_word_count` 对超出硬上限的章节返回 `severity="hard"`，使 comp-gate 能真正阻断放行，而非仅打软警告。

**Acceptance Criteria:**
- [ ] `ink-writer/scripts/computational_checks.py:87` 的 `check_word_count` 函数签名新增 `max_words_hard: int = 5000` 和 `max_words_soft: Optional[int] = None` 参数
- [ ] 字数 > `max_words_hard` → 返回 `CheckResult(severity="hard", passed=False)`
- [ ] 若提供 `max_words_soft` 且 `max_words_hard < count <= max_words_soft` → 返回 `severity="soft"`（缓冲带）
- [ ] 保留原 `max_words` 参数作为 deprecated alias 映射到 `max_words_hard`，零回归
- [ ] 硬下限 `min_words=2200` 行为与返回 severity 不变
- [ ] 单元测试覆盖：低于下限 hard、位于 [min,max_hard] 通过、超 hard soft 缓冲带、超 soft 全部场景
- [ ] Typecheck 通过

### US-002: preferences.json 驱动字数阈值
**Description:** 作为用户，我在 `.ink/preferences.json` 写入 `pacing.chapter_words: N`，应能让流水线按 `[max(2200, N-500), N+500]` 作为实际 [min, max_hard] 区间执行，未配置时使用默认 5000。

**Acceptance Criteria:**
- [ ] 新增 `ink_writer/core/preferences.py`（或复用现有加载点）提供 `load_word_limits(project_root) -> (min_words, max_words_hard)` 函数
- [ ] 无 `pacing.chapter_words` 配置 → 返回 `(2200, 5000)`
- [ ] 有 `pacing.chapter_words: N` → 返回 `(max(2200, N-500), N+500)`；即硬下限永不低于 2200
- [ ] Step 2C comp-gate 调用 `check_word_count` 时传入该函数的返回值
- [ ] 更新 `ink-writer/references/preferences-schema.md` 文档，说明 `chapter_words` 推导 [min, max] 的语义
- [ ] 单元测试：无配置、有配置、配置极小值（< 2200）三种场景
- [ ] Typecheck 通过

### US-003: `ink-auto.sh` 增加上限硬阻断
**Description:** 作为自动化批量写作，我需要 `ink-auto.sh` 在检测章节文件时对称检测上限超标，触发精简循环（最多 3 轮），对齐现有补写循环的设计。

**Acceptance Criteria:**
- [ ] `ink-writer/scripts/ink-auto.sh:508` 附近在 `< 2200 return 1` 分支后增加 `> MAX_WORDS_HARD return 1` 分支
- [ ] `MAX_WORDS_HARD` 变量从 `.ink/preferences.json` 的 `pacing.chapter_words` 推导（`+500`），读不到则默认 5000
- [ ] 新增 PowerShell 对等入口改动：`ink-auto.ps1:409` 附近同步增加上限判定（按 CLAUDE.md Windows 兼容守则）
- [ ] 精简循环最多 3 轮（对齐 US-004 Step 2A.5 逻辑）；3 轮仍超限则阻断报错
- [ ] 精简后字数 ≥ 2200 校验保留（防精简过度）
- [ ] bash `.sh` 与 PowerShell `.ps1` 行为一致，Mac/Linux 下 `.sh` 字节级无其他改动
- [ ] 手动冒烟：构造 > 5000 字的章节文件，运行 ink-auto 应触发精简循环

### US-004: SKILL.md Step 2A.5 删除 LLM 自行豁免路径
**Description:** 作为指令规范维护者，我要收紧 `SKILL.md` 2A.5 的字数判定，删除"关键战斗章/高潮章/卷末章可放行"的豁免条款，使 LLM 无法自行判定豁免。

**Acceptance Criteria:**
- [ ] `ink-writer/skills/ink-write/SKILL.md:1028-1038` 的表格与豁免条款改写：
  - 删除"关键战斗章/高潮章/卷末章允许上浮 33%"表述
  - 删除"若大纲标注为关键战斗章/高潮章/卷末章，可放行"
  - 明确"硬上限由 `preferences.json` 的 `pacing.chapter_words+500` 决定，默认 5000，任何情况不得超限放行"
- [ ] 精简循环最大轮次更新为 3 轮（与 US-003 对齐）
- [ ] `ink-writer/agents/writer-agent.md:467`、`622`、`851`、`875` 等"硬上限 4000"表述更新为"由 preferences 驱动的硬上限，默认 5000"
- [ ] 保留"补写循环最多 2 轮"（下限方向的现有行为零回归）
- [ ] `ink-writer/skills/ink-fix/SKILL.md` 等下游文档中提及的"上限"字眼一并对齐
- [ ] 全仓 grep 确认无残留的"关键章可豁免"表述

### US-005: writer-agent 写前接收 `target_words_max` 硬约束
**Description:** 作为 writer-agent，我在 Step 2A 起草阶段即应收到明确的 `target_words_max` 上限字段，在生成时就受约束而非依赖写后阻断兜底。

**Acceptance Criteria:**
- [ ] `ink-writer/scripts/extract_chapter_context.py:674` 附近在创作执行包中新增 `target_words_min` 和 `target_words_max` 字段，值由 US-002 的 `load_word_limits` 提供
- [ ] `ink-writer/agents/writer-agent.md` 指令段落明确：必须读取创作包的 `target_words_max`，作为生成过程中的硬约束上限
- [ ] `writer-agent.md` 的"字数自检清单"新增：生成完成前自检 `当前字数 <= target_words_max`，超限必须自行精简再输出
- [ ] 现有 Step 2A 指令中所有涉及字数目标的硬编码数字（2200-3000 / 4000）改为引用 `target_words_min/max` 占位
- [ ] 执行包 schema 对应文档同步更新
- [ ] 现有创作执行包路径注入（preferences_file）保持不变，仅新增字段不改动既有字段

### US-006: 单元测试与回归验证
**Description:** 作为质量守门员，我需要自动化测试覆盖硬上限阻断、preferences 覆盖、精简循环三条关键路径，防止后续回归。

**Acceptance Criteria:**
- [ ] `tests/data_modules/test_computational_checks.py` 新增 `test_word_count_hard_upper_limit`：验证 > max_words_hard 时 passed=False, severity="hard"
- [ ] 新增 `test_word_count_soft_buffer`：验证 max_words_hard < count <= max_words_soft 时 passed=False, severity="soft"
- [ ] 新增 `test_word_count_backward_compat_max_words_alias`：验证老 `max_words=` 参数仍可用（deprecated 但不破坏）
- [ ] 新增 `tests/core/test_word_limits_preferences.py`：
  - 无 preferences → (2200, 5000)
  - `chapter_words=3000` → (2500, 3500)
  - `chapter_words=2000`（低于硬下限） → (2200, 2500)
  - `chapter_words=4500` → (4000, 5000)
- [ ] pytest 全量通过，无现有测试被破坏
- [ ] 现有 `check_word_count` 调用点（`computational_checks.py:646`）行为等价回归

## Functional Requirements

- FR-1: `check_word_count(chapter_text, min_words=2200, max_words_hard=5000, max_words_soft=None, max_words=None)` — `max_words` 为 deprecated alias
- FR-2: 超 `max_words_hard` 返回 `severity="hard"`, `passed=False`
- FR-3: 设 `max_words_soft` 时，`max_words_hard < count <= max_words_soft` 返回 `severity="soft"`, `passed=False`（缓冲带警告）
- FR-4: `load_word_limits(project_root)` 读 `.ink/preferences.json` 的 `pacing.chapter_words`，返回 `(max(2200, N-500), N+500)`；缺省返回 `(2200, 5000)`
- FR-5: Step 2C comp-gate 调用 `check_word_count` 时必须传入 `load_word_limits` 结果
- FR-6: `ink-auto.sh` 与 `ink-auto.ps1` 检测章节字数超 `MAX_WORDS_HARD` 时触发精简回退（最多 3 轮），对齐现有补写回退路径
- FR-7: 创作执行包（`extract_chapter_context.py` 产出）必须包含 `target_words_min` 与 `target_words_max` 字段
- FR-8: writer-agent 指令必须读取并遵循 `target_words_max`；不得自行豁免
- FR-9: SKILL.md Step 2A.5 删除所有"关键章可豁免"表述
- FR-10: 硬下限 2200 行为在所有层级完全保留（零回归）

## Non-Goals

- 不新增配置文件（仍复用 `.ink/preferences.json`）
- 不改 `preferences.json` 其他字段（tone/style/avoid/focus）语义
- 不改 dashboard / review 报告的字段或展示格式
- 不支持章节级 `word_target` 覆盖（选项 4D：彻底不设豁免）
- 不改 polish-agent 的 70% 字数下限保护逻辑
- 不改 `reports/` 目录的任何历史产物
- 不向 `preferences.json` 新增字段（仅复用 `pacing.chapter_words`）

## Technical Considerations

### 零回归红线（硬约束，优先于代码整洁）
- 硬下限 2200 字所有现有阻断路径（`computational_checks.py`、`ink-auto.sh:508`、`SKILL.md` 2A.5、`polish-agent.md`）字节级不得弱化
- 现有"补写循环最多 2 轮"不变
- 仅向上游增加能力，不得删除任何现有校验
- Mac/Linux `.sh` 脚本除新增上限分支外字节级一致（CLAUDE.md Windows 兼容守则）
- Deprecated `max_words=` 参数映射到 `max_words_hard=`，已有 caller 零改动通过

### 推导规则（US-002）
- `pacing.chapter_words: N` → `(min=max(2200, N-500), max_hard=N+500)`
- 缺省 → `(min=2200, max_hard=5000)`
- 硬下限永不低于 2200（即使用户配置极小值）

### Windows 兼容（US-003）
- 修改 `ink-auto.sh` 必须同步修改 `ink-auto.ps1`（UTF-8 BOM 保留）
- 复用 `ink-writer/scripts/runtime_compat.py` 已有原语
- 所有 Python 新增入口调用 `enable_windows_utf8_stdio()`

### 依赖分析
- `extract_chapter_context.py` 已注入 `preferences_file` 路径，本次只增加新字段不改既有
- `check_word_count` 被 `computational_checks.py:646` 和可能的 Step 2C gate 调用；均需更新

## Success Metrics

- 给定 `pacing.chapter_words: 3000` 的项目，写出 > 3500 字章节 100% 被阻断
- 写出 > 5000 字章节 100% 被阻断（无 preferences 配置兜底）
- 写出 < 2200 字行为与现状完全一致（零回归）
- `pytest tests/` 全绿
- 全仓 grep 无残留"关键章可豁免"表述
- writer-agent 生成阶段日志可见 `target_words_max` 已注入

## Open Questions

- `max_words_soft` 缓冲带默认值是否需要（例如 `max_words_hard + 500`）？本 PRD 默认不设，US-001 保留能力但默认 `None`
- `preferences-schema.md` 示例的 `chapter_words: 2500` 是否要改为更合理的默认值（如 2800）？建议保留 2500 不改，避免示例改动引发现有项目解读差异
- 是否需要在 `/ink-init` 交互中提示用户设置 `pacing.chapter_words`？本 PRD 不涉及，可在后续迭代补充
