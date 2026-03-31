# Review Bundle JSON 格式规范

> 本文档定义 `extract-context --format review-pack-json` 输出的 JSON 结构，是所有 checker 的唯一输入源。
>
> **单一事实源**：checker 不得自行扫描项目目录，只能消费本文件定义的字段。

## 生成方式

```bash
python3 -X utf8 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" \
  extract-context --chapter {chapter_num} --format review-pack-json \
  > "${PROJECT_ROOT}/.ink/tmp/review_bundle_ch${chapter_padded}.json"
```

## 顶层结构

```json
{
  "meta": { ... },
  "chapter_text": "...",
  "previous_summary": "...",
  "outline_excerpt": "...",
  "setting_snapshot": { ... },
  "character_snapshot": [ ... ],
  "memory_context": { ... },
  "reader_signal": { ... },
  "golden_three_contract": { ... },
  "writing_guidance": { ... },
  "allowed_read_files": [ ... ]
}
```

## 字段说明

### meta（必填）

| 字段 | 类型 | 说明 |
|------|------|------|
| `chapter` | int | 当前章节号 |
| `project_root` | string | 项目根目录绝对路径 |
| `genre` | string | 题材 ID（如 `shuangwen`、`xianxia`） |
| `volume_id` | int | 当前卷号 |
| `is_transition` | bool | 是否为过渡章 |
| `is_golden_three` | bool | 是否为黄金三章（ch1-3） |
| `generated_at` | string | ISO 8601 时间戳 |

### chapter_text（必填）

当前章节正文全文（string）。checker 从此字段读取待审查正文，不得从文件系统读取。

### previous_summary（必填，第1章可为空字符串）

上一章摘要（string）。来源：`.ink/summaries/ch{NNNN-1}.md`。

### outline_excerpt（必填）

当前章节的章纲摘录（string）。包含：目标/阻力/代价/时间锚点/Strand/反派层级/钩子/章末未闭合问题等字段。

### setting_snapshot（必填）

当前章节相关的设定快照（object）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `protagonist_state` | object | 主角当前状态（境界/位置/可用能力） |
| `power_system_rules` | string | 力量体系核心规则摘要 |
| `world_rules` | string | 世界规则红线摘要 |
| `active_factions` | array | 当前活跃势力列表 |
| `timeline_anchor` | object | 时间锚点（上章/本章/倒计时状态） |

### character_snapshot（必填）

本章出场角色列表（array of object）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 角色 ID |
| `name` | string | 角色名 |
| `role` | string | 主角/女主/配角/反派 |
| `personality` | string | 性格特征 |
| `speech_style` | string | 说话风格 |
| `current_state` | string | 当前状态（境界/情绪/位置） |
| `language_profile` | object/null | 语言档案（若有） |
| `red_lines` | array | 角色行为红线 |

### memory_context（必填）

章节记忆上下文（object）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `chapter_meta_prev` | object/null | 上章 chapter_meta（含 hook/ending） |
| `recent_patterns` | array | 最近 3-5 章的模式统计 |
| `active_foreshadowing` | array | 活跃伏笔列表（按紧急度排序） |
| `strand_tracker` | object | Strand 三线追踪器 |
| `debt_summary` | object | Override 债务摘要 |

### reader_signal（条件必填，reader-pull/high-point/pacing checker 使用）

追读力信号（object）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `recent_reading_power` | array | 最近 5 章追读力数据 |
| `hook_type_stats` | object | 钩子类型统计 |
| `pattern_usage_stats` | object | 模式使用统计 |
| `coolpoint_in_outline` | string/null | 大纲规划的爽点类型 |

### golden_three_contract（条件必填，仅 ch1-3）

黄金三章契约（object）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `golden_three_plan` | object | `.ink/golden_three_plan.json` 内容 |
| `preferences` | object | `.ink/preferences.json` 相关配置 |
| `role` | string | 本章职责（立触发/接钩升级/小闭环） |

### writing_guidance（必填）

写作指导信息（object）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `context_contract` | object | Context Contract 核心字段 |
| `style_guidance` | object | 风格指导 |
| `constraint_triggers` | array | 本章触发的约束（反套路/硬约束） |

### projected_strand（可选，pacing-checker 使用）

本章的预判 Strand 分类（object），用于解决 strand_tracker 在 Step 3 时尚未更新（Step 5 才写入）导致的滞后问题：

| 字段 | 类型 | 说明 |
|------|------|------|
| `dominant` | string | 预判的主导 Strand：quest / fire / constellation |
| `confidence` | string | 置信度：high / medium / low |
| `secondary` | string/null | 次要底色 Strand（可选） |

来源：由 review bundle 生成脚本根据章节正文内容预判。若生成脚本不支持此字段，可省略，pacing-checker 回退到使用 `memory_context.strand_tracker`（反映上一章数据）。

### narrative_commitments（可选，consistency-checker Layer 4 使用）

活跃叙事承诺列表（array of object）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 承诺 ID |
| `chapter` | int | 承诺发起章节 |
| `commitment_type` | string | 类型：oath / promise / prophecy / world_law / character_principle / prohibition |
| `entity_id` | string | 承诺关联角色 ID |
| `content` | string | 承诺内容描述 |
| `scope` | string | 作用范围 |

来源：`index.db.narrative_commitments WHERE resolved_chapter IS NULL`。若数据不可用，此字段可省略，checker 会跳过 Layer 4 检测。

### allowed_read_files（必填）

允许 checker 补充读取的文件绝对路径白名单（array of string）。仅当审查包缺字段时，checker 才可读取此列表中的文件。

## Checker 读取规则

1. **必须先读取 review_bundle_file**，从中获取所有审查所需数据
2. **默认只使用审查包内嵌数据**，不得自行扫描项目目录
3. **仅当审查包明确缺字段时**，才允许补充读取 `allowed_read_files` 中列出的文件
4. **禁止读取** `.db` 文件、目录路径、以及白名单外的文件

## 版本兼容

- 当前版本：v1
- 新增字段时保持向后兼容（新字段可选），不删除已有字段
- 若需要不兼容变更，在 `meta` 中增加 `schema_version` 字段
