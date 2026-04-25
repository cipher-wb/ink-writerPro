# 编辑反馈手册（EDITOR_FEEDBACK_GUIDE）

> 面向编辑 / 产品的反馈录入与 case 治理操作指南，覆盖评分录入 → case 提案审批 → 复发申诉 3 个阶段。
>
> 本手册仅给最小可执行流；详细字段语义、PowerShell sibling、提示词模板等请参阅
> `docs/USER_MANUAL.md` §4 与 `ink-writer/skills/<skill>/SKILL.md`。

---

## 1. 评分如何录入

### 1.1 文件位置与命名

每本书一份独立 yaml：

```
data/editor_reviews/<book>.yaml
```

`<book>` 与 `data/<book>/` 下的目录名严格一致；同一本书可多次追加 `reviews:` 条目，
不要按周拆多个文件——`aggregator.compute_editor_score_trend` 会按 `date` 字段自动聚合周环比。

### 1.2 yaml schema

```yaml
book: <book>                        # 必填，与目录名一致
reviews:
  - chapter: 12                     # 必填；策划期评分用 chapter: 0
    date: 2026-04-25                # 必填，YYYY-MM-DD
    score: 7.5                      # 必填，1-10 浮点，保留 1 位小数
    reviewer: editor_a              # 选填，多人评审时区分
    pros:                           # 选填，亮点摘要
      - "节奏紧凑"
      - "金手指代价可视化到位"
    cons:                           # 选填，缺陷摘要（驱动 case 提案）
      - "反派动机弱"
      - "第 3 段叙述视角混乱"
    suggestions:                    # 选填，具体修订建议（驱动 countermeasure 文案）
      - "把反派最近一次失败的具体后果在第 5 段补一句"
    severity_hint: P2               # 选填，编辑建议严重度（P0-P3，默认 P2）
```

### 1.3 录入流程

1. 编辑在 `data/editor_reviews/<book>.yaml` 追加一条 `reviews:` 条目。
2. 跑 `ink case ingest --from data/editor_reviews/<book>.yaml --book <book>` —— 每条 `cons`
   各自变成 1 条 `status=pending` 的 case 提案，写入 `data/case_library/cases/CASE-NNNN.yaml`，
   `severity` 取 `severity_hint`，`countermeasure.guideline` 取对应位置的 `suggestions`。
3. 录入完成后周报会自动消费：`aggregator.compute_editor_score_trend` 输出 `editor_score_trend`
   指标，`-0.5` 周环比即触发 dashboard 红线。

> 每章建议至少录 1 条评分；评分缺失会让该章在周报里显示为灰色（不计入 trend）。

---

## 2. case 提案审批

### 2.1 列出待审 case

```bash
ink case list --status pending
ink case list --status pending --book <book>
```

输出每行：`CASE-NNNN  P2  pending  :: <一句话描述>`。

### 2.2 审批单条 / 批量

```bash
# 单条
ink case approve CASE-0123
# 批量（逗号分隔）
ink case approve --batch CASE-0123,CASE-0124,CASE-0125
# 拒绝
ink case reject CASE-0124 --reason "编辑误判，已与编辑确认放弃"
```

`approve` 写 `status=active`；`reject` 写 `status=rejected` + `rejected_at`。
拒绝必须带 `--reason`，理由会落到 case yaml `notes` 字段以便后续审计。

### 2.3 自动学习 case（M5 P3）

ink 系统会自动产出两类 case 提案，**走相同的审批流**：

| 前缀 | 来源 | 触发条件 |
|---|---|---|
| `CASE-LEARN-NNNN` | `ink-learn --auto-case-from-failure` | 7 天内 blocked 章节 evidence_chain 中同一 `cases_violated` 组合出现 ≥ 2 次；每周限 5 条 |
| `CASE-PROMOTE-NNNN` | `ink-learn --promote` | 短期记忆 `.ink/<book>/project_memory.json` 中 `count ≥ 3` 的 success / failure pattern |

审批前请重点核对 `failure_pattern.observable` 是否准确——自动学习会把 evidence 中的 `cases_violated`
列表直接塞进 `tags` 与 `observable`，可能含噪。`reject` 后该模式 7 天内不会再次提议（throttle 记忆）。

### 2.4 元规则提议审批

当 ≥ 5 条 active case 在 LLM 主观判断下相似度 > 0.80，系统会写一条
`data/case_library/meta_rules/MR-NNNN.yaml`（`status=pending`）：

```bash
ink meta-rule list --status pending
ink meta-rule approve MR-0001
ink meta-rule reject  MR-0002
```

`approve` 会给 `covered_cases` 各 case 写 `meta_rule_id=MR-NNNN`，并在 case yaml 中标记其归属
元规则；后续这些 case 在 dashboard 中显示为「已合并」状态，但仍独立计入 `recurrence_rate`。
`approve` 是幂等的：第二次 approve 同一 MR 直接返回 rc=1 + stderr 提示，不会重写下游 cases。

---

## 3. 复发申诉

### 3.1 什么是复发？

`status=resolved` 的 case 再次在 `evidence_chain` 中被命中（`cases_violated` 含其 id），
即触发 Layer 4 复发追踪：

- `severity` 自动升级一级（P3→P2→P1→P0；到 P0 则不再升）。
- `recurrence_history` 追加一条 `{book, chapter, evidence_chain_path, resolved_at, regressed_at}`。
- `status` 改回 `regressed`（区别于初次 `pending`，便于审计）。
- dashboard `recurrence_rate` 指标计入分子。

### 3.2 编辑申诉：sovereign 字段

部分 case 是「主权特例」——编辑明确认可的特定章节做法，不应升级 severity 也不应被合并到元规则。
此类 case 由编辑在 yaml 中显式标记：

```yaml
id: CASE-0089
sovereign: true
notes: "第 47 章战斗节奏与平台限流冲突，编辑保留为风格特例，不参与合规循环。"
```

`sovereign: true` 的 case：
- **不**进入 `regression_tracker` 升级流程（即使复发也仅记 history、不升 severity）。
- **不**被 `meta_rule_emergence` 当作候选（`_candidate_clusters_by_tags` 主动跳过）。
- 在 dashboard 的复发列表中以淡色显示，仅作信息展示。

### 3.3 已修复申诉：`ink case mark-resolved`

作者修复某个被命中的 case 后，编辑核对修订符合 countermeasure 即可标 resolved：

```bash
ink case mark-resolved CASE-0123 --book <book> --chapter 47 --note "第 47 章已补反派代价"
```

`mark-resolved` 写 `status=resolved` + `resolved_at`，dashboard `repair_speed_days` 指标据此计算。
若同一 case 在 mark-resolved 之后再次复发，会被 Layer 4 追踪为「真复发」并升级 severity。

### 3.4 元规则误合并申诉

若 `MR-NNNN` 已 approve 但编辑认为某条 covered case 不应被合并：

1. 在该 case yaml 中手动清空 `meta_rule_id: null` 并加 `sovereign: true`。
2. 跑 `ink meta-rule list --status approved` 复核归属是否仍合理；若整个元规则都需撤销：
3. 当前版本不支持 `ink meta-rule revoke`（M5 范围外）；直接编辑 `MR-NNNN.yaml` 改 `status=rejected`
   并加 `revoked_at` + `revoke_reason`，下游 dashboard 会按 `status` 重新过滤。

恢复后建议在 `docs/superpowers/M-ROADMAP.md` 反馈区登记，便于后续迭代加入 `revoke` 子命令。

---

## 附：跨手册导航

- 作者视角的开新书 / 写章 / 看 dashboard 全流程：见 `docs/USER_MANUAL.md`
- 5 周质量治理 roadmap 与 milestone 状态：见 `docs/superpowers/M-ROADMAP.md`
- Windows 兼容守则与 PowerShell sibling 模板：见根目录 `CLAUDE.md` §Windows 兼容守则
