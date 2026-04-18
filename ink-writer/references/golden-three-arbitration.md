# 前 3 章 Checker 冲突仲裁矩阵

> US-026 产出。当章 1-3 同时触发 `golden-three-checker` 硬阻断、4 项爽点硬阻断、以及 `editor_wisdom` 软规则时，
> polish-agent 按本优先级表采纳建议，避免重复或自相矛盾的 `fix_prompt`。

## 1. 适用范围

- 章节编号 ∈ {1, 2, 3}（黄金前三章）
- 同一章节的 review bundle 中同时存在 ≥2 个 checker 产出冲突 issue

## 2. 优先级总表（由高到低）

| 优先级 | 来源                         | Severity | 是否阻断发布 | 冲突时采纳 |
| ------ | ---------------------------- | -------- | ------------ | ---------- |
| P0     | `golden-three-checker`       | hard     | 是           | 必采纳     |
| P1     | 4 项爽点硬阻断 (highpoint-x4)| hard     | 是           | 必采纳     |
| P2     | `editor_wisdom` (severity=hard) | hard  | 是           | 采纳除非 P0/P1 已覆盖 |
| P3     | `editor_wisdom` (severity=soft) | soft  | 否           | 采纳除非与 P0/P1/P2 文本冲突 |
| P4     | `editor_wisdom` (severity=info) | info  | 否           | 仅作为提示注入 context |

## 3. 冲突类型与解析

### 3.1 同向冲突（两个 checker 指向同一症状，措辞不同）

例：`golden-three-checker` 说"开篇钩子不足"，`editor_wisdom` soft 规则说"前 500 字需挂出高爽点"。

仲裁规则：
1. 保留 P0 的 `fix_prompt` 原文。
2. P1/P2/P3 的 fix_prompt 合并进同一个 issue 的 `context_addendum`（附加上下文），不产生独立条目。

### 3.2 反向冲突（建议互斥）

例：`golden-three-checker` 要求"主角立即使用金手指"，`editor_wisdom` soft 规则要求"金手指延后 3 章揭示"。

仲裁规则：
1. 采纳高优先级条目（P0 胜出）。
2. 低优先级条目降级为 `info` 写入日志（`polish-agent` 不据此改稿）。
3. 日志格式：`[arbitration] DROPPED ew_rule=<id> reason=conflict_with_golden_three`。

### 3.3 重复冲突（同 severity 同方向，多 checker 都命中）

例：4 项爽点硬阻断中的 2 项 + editor_wisdom hard 1 条都指向"第 1 章缺爽点"。

仲裁规则：
1. 合并为单一 `fix_prompt`（取 P1 原文为基础）。
2. `sources` 字段列出全部 checker id，供调试追溯。

## 4. 输出数据结构（供 polish-agent 消费）

polish-agent 收到的仲裁结果形如：

```json
{
  "arbitration": {
    "chapter_id": 1,
    "merged_fixes": [
      {
        "issue_id": "ARB-001",
        "priority": "P0",
        "fix_prompt": "...合并后单一指令...",
        "sources": ["golden-three-checker#H-12", "highpoint-checker-x4#H-03"],
        "context_addendum": "editor_wisdom soft EW-0087: ..."
      }
    ],
    "dropped": [
      {"source": "editor_wisdom#EW-0091", "reason": "conflict_with_P0"}
    ]
  }
}
```

## 5. 与既有 pipeline 的衔接

- `checker-merge-matrix.md` 定义 checker 之间的通用 merge 逻辑；本文件是其在**黄金前三章**场景的特化。
- 章节 ≥ 4 时本仲裁关闭，走 `checker-merge-matrix.md` 的通用合并路径。
- 仲裁执行点：`review` 阶段产出 review_bundle 之后、`polish` 阶段读取之前，由 review-gate 调用。

## 6. 回归保护

- `tests/integration/test_chapter1_arbitration.py` 覆盖 §3.1 §3.2 §3.3 全部三种冲突类型。
- 任何修改本文件优先级表的 PR 必须同步更新该测试的断言。
