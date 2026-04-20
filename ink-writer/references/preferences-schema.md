# preferences.json 设计

用于保存用户偏好与写作约束（可由 /ink-init 或用户手动编辑）。

## 示例

```json
{
  "tone": "热血",
  "pacing": {
    "chapter_words": 2500,
    "cliffhanger": true
  },
  "style": {
    "dialogue_ratio": 0.35,
    "narration_ratio": 0.65
  },
  "avoid": ["过度旁白", "重复台词"],
  "focus": ["主角成长", "战斗描写"]
}
```

## 字段说明
- tone: 全局情绪基调
- pacing: 节奏偏好
- style: 叙事/对话比例
- avoid: 禁忌清单
- focus: 必须强调的方向

## pacing.chapter_words 语义（v23 起）

`pacing.chapter_words` 是**目标章节字数（单值）**，流水线会据此推导章节字数的
硬区间 `[min_words, max_words_hard]`，在全链路统一消费（`check_word_count` / `ink-auto` /
`writer-agent` 起草阶段均受此约束）。

推导规则：

```
min_words      = max(2200, chapter_words - 500)
max_words_hard = chapter_words + 500
```

- **默认值（未配置或文件损坏）**：`(min=2200, max_hard=5000)`。
- **硬下限红线**：`min_words` 永不低于 2200，即便 `chapter_words` 配得很小（硬约束，
  写在 `ink_writer/core/preferences.py::MIN_WORDS_FLOOR`）。
- **硬上限对等硬下限**：超过 `max_words_hard` 由 `check_word_count` 返回
  `severity='hard'` 直接阻断；不存在按章节类型、节拍标签或大纲标签级的 LLM 自行
  豁免路径（这是 US-005 收紧的重点——历史版本按章型/百分比的放行条款全部删除）。
- 程序入口：`from ink_writer.core.preferences import load_word_limits`。
- **创作执行包传递（v23 US-003）**：`build_chapter_context_payload` 调用 `load_word_limits`
  后，会把结果写入 payload 顶层字段 `target_words_min` / `target_words_max`；
  `build_execution_pack_payload` 原样透出到创作执行包顶层，`writer-agent` 在 Step 2A
  起草时消费 `target_words_max` 作为硬约束上限，生成完成前必须自检 `实际字数 <= target_words_max`。

### 三组典型示例

| preferences.json | 推导结果 (min, max_hard) | 说明 |
| ---------------- | ------------------------ | ---- |
| 未配置 / 文件缺失 | `(2200, 5000)` | 全默认 |
| `pacing.chapter_words = 3000` | `(2500, 3500)` | 目标 3000 字，±500 区间 |
| `pacing.chapter_words = 2500` | `(2200, 3000)` | 目标 2500 字，min 被红线托到 2200 |
| `pacing.chapter_words = 4500` | `(4000, 5000)` | 目标 4500 字，适用节奏更慢的卷首 |

> **零回归承诺**：硬下限 2200 的所有现有阻断点在 v23 前后字节级一致；本机制仅硬化
> 上限方向，不允许任何弱化下限的逻辑路径。
