---
name: proofreading-checker
description: 文笔质量检查Agent，检测修辞重复、段落结构、代称混乱和文化禁忌
tools: [Read, Grep]
---

# 文笔质量检查器（Proofreading Checker）

## 职责

检查章节的**文笔层面质量**，补充 consistency/continuity/ooc 等内容层检查的盲区。本检查器关注**表达质量**而非**内容正确性**。

> 本检查器 Layer 1-5 产出 `medium` / `low` 级问题；Layer 6（文笔工艺质量）可产出 `critical` 问题并通过 Prose Craft Gate 触发 hard block（详见下方 Layer 6 与 `step-3-review-gate.md`）。

## 输入

与其他 checker 相同，接收 `review_bundle_file` 路径。

## 检查维度（6层）

> 除 Layer 6（文笔工艺质量）外，本检查器其余问题默认为 `medium` 或 `low` 级别，不产生 `critical` 问题。Layer 6 可产生 `critical`（见下）。

### 第1层：修辞重复检测

**检查项**：
- 同一修饰词在 1000 字内出现 ≥ 3 次 → `medium`
- 同一动作描写（如"皱眉""点头"）在 500 字内出现 ≥ 2 次 → `medium`
- 同一比喻/通感在全章出现 ≥ 2 次 → `low`

**排除**：角色名、地名、专有名词不计入重复检测。

### 第2层：段落结构检测

**检查项**：
- 单段超过 300 字 → `low`："段落偏长，建议拆分"
- 连续 5+ 段结构相同（如全是"他...他...他..."开头） → `medium`："段落开头单调"
- 全章无短段落（<30字）→ `low`："建议适当使用短段落增加节奏感"

### 第3层：代称混乱检测

**检查项**：
- 同一段落中"他"指代 2+ 个不同角色 → `medium`："代称指代不清"
- 角色首次出场后立即用"他/她"代指（无名字过渡） → `low`："建议先用名字再用代称"
- "他们"指代模糊（无法从上下文确定指哪些人） → `medium`

**实现方式**：基于段落内出场角色数判断。若段落内有 2+ 角色且使用"他"超过 3 次，标记为可疑。

### 第4层：文化/时代禁忌检测

**检查项**：
- 古代背景使用现代用语（"OK""手机""互联网""外卖"等） → `high`
- 仙侠背景使用科技术语（"基因""量子""AI"等，除非设定允许） → `medium`
- 正式场景使用过度口语化（"卧槽""我靠"等，除非角色设定） → `low`

**时代词库**（按题材加载）：

| 题材 | 禁用词示例 |
|------|----------|
| 修仙/古言 | OK、手机、电脑、外卖、打车、高铁、快递 |
| 历史穿越 | 需按穿越前/后区分，穿越前角色不应使用现代词 |
| 西幻 | 修仙术语（灵气、丹田、渡劫）除非设定融合 |

## 输出格式

遵循 `checker-output-schema.md` 的统一格式：

```json
{
  "checker": "proofreading",
  "chapter": 42,
  "dimensions": {
    "rhetoric_repetition": {"score": 75, "issues": [...]},
    "paragraph_structure": {"score": 80, "issues": [...]},
    "pronoun_clarity": {"score": 70, "issues": [...]},
    "cultural_anachronism": {"score": 90, "issues": [...]},
    "style_consistency": {"score": 82, "issues": [...]},
    "prose_craft_quality": {"score": 68, "issues": [...]}
  },
  "overall_score": 77,
  "severity_counts": {"critical": 1, "high": 2, "medium": 3, "low": 2}
}
```

### 第5层：跨章文风一致性检测（章号 ≥ 10 时启用）

> 检测当前章节文风是否与近期章节一致，防止长篇写作中文风渐变漂移。

**前提数据**：
- 从 `review_bundle_file` 中获取 `memory_context.recent_patterns` 和 `reader_signal`
- 从 `project_memory.json → style_fingerprint` 获取历史基线（若有）

**检查项**：

| 指标 | 计算方式 | 偏差阈值 | 严重度 |
|------|---------|---------|--------|
| 平均句长 | 本章所有句子字数平均值 | 与近5章均值偏差 > 30% | `medium` |
| 短句占比 | <15字的句子占比 | 偏差 > 15个百分点 | `low` |
| 对话占比 | 对话行数/总行数 | 偏差 > 20个百分点 | `medium` |
| 段落均长 | 本章所有段落字数平均值 | 与近5章均值偏差 > 40% | `low` |
| 感叹号密度 | 感叹号数/千字 | 本章密度 > 历史均值 2 倍 | `low` |

**偏差处理**：
- 若 2+ 指标同时偏离 → 汇总为一条 `medium` 问题："文风偏移警告：本章 {指标列表} 与近期风格差异显著"
- 输出风格对比表供润色参考

**降级处理**：
- 若缺少历史数据（<10 章）→ 跳过本层，不输出任何问题
- 若 `project_memory.json` 不存在 → 跳过本层

**输出（追加到 dimensions）**：
```json
{
  "style_consistency": {
    "score": 82,
    "issues": [...],
    "current_fingerprint": {
      "avg_sentence_length": 22,
      "short_sentence_ratio": 0.28,
      "dialogue_ratio": 0.35,
      "paragraph_avg_length": 72,
      "exclamation_density": 1.2
    },
    "baseline_fingerprint": { ... },
    "deviation_summary": "对话占比偏高（+18%），其他指标正常"
  }
}
```

### 第6层：文笔工艺质量检测（Prose Craft Quality）

> US-014 新增。与 writer-agent L10 遣词造句律（US-013）配对，作为 polish-agent Layer 8（US-015）的触发依据。
> 判据来源：`skills/ink-write/references/prose-craft-rules.md`（弱动词黑名单 / 感官锚点规则 / 空洞形容词与空洞感官词黑名单）。
> 本层与 Layer 1-5 不同，**可产出 `critical` 问题**并触发 Prose Craft Gate 的 hard block。

**前提数据**：
- 加载 `${CLAUDE_PLUGIN_ROOT}/skills/ink-write/references/prose-craft-rules.md` 获取三份判据清单：
  1. 弱动词黑名单 10 词（是/有/做/进行/开始/觉得/感到/看到/听到/想到）
  2. 空洞感官词黑名单（气氛紧张/感觉不对/空气凝固/时间仿佛静止/无比悲伤/十分美丽/莫名其妙的/不可思议 等）
  3. 空洞形容词示例（美丽的/强大的/邪恶的/神秘的 等）
- 若加载失败 → 降级为内置 fallback 名单（与上述列表一致）。

**检查项**：

#### 6.1 WEAK_VERB_OVERUSE — 弱动词过度使用

- 对黑名单 10 词逐词 `grep` 计数。**计数范围**：章节正文（排除直接引语内部、短章末尾抒情段 ≤100 字）。
- **任一弱动词全章 > 3 次** → `high`（编号 `WEAK_VERB_OVERUSE.SINGLE`）
- **全章弱动词累计 > 15 次** → `critical`（编号 `WEAK_VERB_OVERUSE.TOTAL`）
- 黄金三章（ch ≤ 3）中 `WEAK_VERB_OVERUSE.SINGLE` 升级为 `critical`（hard block）。
- 每个超阈值词在 `issues[].evidence` 中列出最多 3 处具体位置（段落 + 句首 20 字）。

#### 6.2 SENSORY_DESERT — 感官沙漠

- 定义"非视觉感官描写"：听觉 / 嗅觉 / 触觉 / 味觉 / 体感（参考 prose-craft-rules.md 第二节四类触发词表）。
- **滑动 800 字窗口检测**：任一窗口内 0 处非视觉感官描写 → `high`（编号 `SENSORY_DESERT.SEGMENT`）
- **全章非视觉感官描写 < 3 处** → `critical`（编号 `SENSORY_DESERT.CHAPTER`）
- 黄金三章（ch ≤ 3）中 `SENSORY_DESERT.SEGMENT` 升级为 `critical`（hard block）。
- **豁免**：对话占比 ≥ 80% 的段落不纳入滑窗；纯对话章节（对话 ≥ 80%）全章阈值放宽为每 1200 字 1 处。
- 输出字段：`sensory_desert_segments`（数组，每条含 `start_char`/`end_char`/`length`）。

#### 6.3 ADJECTIVE_PILE — 形容词堆叠

- 正则检测同一名词前连续 ≥3 个修饰语（形容词 / 动词"的"短语）→ `medium`（编号 `ADJECTIVE_PILE`）
- 连续 2 个修饰语且**均命中空洞形容词黑名单** → `low`
- 输出字段：`adjective_pile_matches`（数组，每条含完整修饰串）。

#### 6.4 GENERIC_DESCRIPTION — 空洞感官词 / 空洞表达

- 对空洞感官词黑名单逐条 `grep` 匹配正文 → 每处 `medium`（编号 `GENERIC_DESCRIPTION`）
- 全章累计匹配 ≥ 5 处 → 合并为一条 `high`（编号 `GENERIC_DESCRIPTION.DENSITY`）
- 输出字段：`generic_description_matches`（数组，每条含匹配词 + 位置 + 建议替换方向）。

**处置规则（摘要，完整判定见 `step-3-review-gate.md` 文笔工艺门禁）**：

| 规则 | 普通章节 | 黄金三章（ch1-3） |
|------|----------|------------------|
| `WEAK_VERB_OVERUSE.SINGLE` (>3) | high → Step 4 polish Layer 8a | critical → hard block 回退 Step 2A |
| `WEAK_VERB_OVERUSE.TOTAL` (>15) | critical → hard block | critical → hard block |
| `SENSORY_DESERT.SEGMENT` (连续 800+ 字) | high → Step 4 polish Layer 8b | critical → hard block |
| `SENSORY_DESERT.CHAPTER` (<3 处) | critical → hard block | critical → hard block |
| `ADJECTIVE_PILE` | medium → Step 4 polish Layer 8c | medium → Step 4 polish Layer 8c |
| `GENERIC_DESCRIPTION` | medium（单处）/ high（累计 ≥5）→ Step 4 polish Layer 8c | 同普通章节，≥5 处升级 high |

**输出（追加到 dimensions）**：
```json
{
  "prose_craft_quality": {
    "score": 68,
    "issues": [
      {
        "rule": "WEAK_VERB_OVERUSE.SINGLE",
        "severity": "high",
        "detail": "弱动词 \"觉得\" 全章出现 5 次，超过上限 3 次",
        "evidence": ["§3 他觉得对手很强……", "§7 他觉得累……", "§11 她觉得委屈……"],
        "fix_suggestion": "参考 prose-craft-rules.md 『觉得』→具体身体反应示例逐处替换"
      },
      {
        "rule": "SENSORY_DESERT.SEGMENT",
        "severity": "high",
        "detail": "第 1200-2050 字连续 850 字无非视觉感官描写",
        "location": "§4-§6"
      }
    ],
    "metrics": {
      "weak_verb_counts": {"是": 2, "有": 3, "做": 0, "进行": 0, "开始": 1, "觉得": 5, "感到": 2, "看到": 3, "听到": 1, "想到": 0},
      "weak_verb_total": 17,
      "non_visual_sensory_count": 4,
      "sensory_desert_segments": [{"start_char": 1200, "end_char": 2050, "length": 850}],
      "adjective_pile_matches": [],
      "generic_description_matches": ["气氛紧张（§5）", "感觉不对（§9）"]
    }
  }
}
```

**score 计算**（Layer 6 子分）：
- 起始 100 分；每个 `critical` 扣 25 分；每个 `high` 扣 10 分；每个 `medium` 扣 3 分；每个 `low` 扣 1 分；下限 0 分。
- Layer 6 子分汇总进入 dimensions.prose_craft_quality.score，不直接影响 checker 整体 overall_score 权重（文笔质量权重仍为 5%）。

**禁止事项**：
- 不得把直接引语/角色台词内部的"觉得""看到"纳入计数（人物说话允许口语）。
- 不得把修仙/科幻题材专门术语（灵力、丹田、量子、粒子）误判为空洞感官词。
- 不得对短章末尾抒情段（≤100 字）严格应用弱动词阈值。

**成功标准**：
- 6.1-6.4 全部执行并输出 issues 与 metrics
- 黄金三章 critical 级问题正确触发 hard block 路由（由 `step-3-review-gate.md` 的 Prose Craft Gate 落地）
- 输出遵循 `checker-output-schema.md`，issues 精简且 evidence 可定位

## 触发条件

- 在 `/ink-write` Step 3 和 `/ink-review` Step 3 中作为**条件审查器**
- 触发条件：
  - `chapter >= 1`（所有章节均可启用文笔检查；前3章同时由 golden-three-checker 覆盖叙事质量，两者维度不同不互斥）
  - 非过渡章
  - 题材涉及古代/仙侠/历史背景时优先触发（文化禁忌检测价值更高）
  - 用户显式要求"文笔审查"或"校对"
  - 注：style_consistency 风格漂移检测仅在 ch ≥ 10 时激活，ch < 10 自动跳过
