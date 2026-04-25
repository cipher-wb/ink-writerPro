# Ink Writer Pro 作者手册

> 面向作者的端到端使用指南，覆盖开新书 → 写章 → 看 dashboard → 录编辑反馈 → 应急绕过 5 个阶段。
>
> 本手册仅为索引与最小工作流；详细参数、PowerShell sibling、提示词模板等请参阅各 `ink-writer/skills/<skill>/SKILL.md`。

---

## 1. 开新书（ink-init）

### 1.1 quick 模式（5 分钟出 3 套方案，推荐首次试用）

`/ink-init --quick <档位>` 以最少交互生成 3 套差异化方案。`<档位>` 为 1-4：1=保守 / 2=平衡 / 3=激进 / 4=疯批；省略档位会弹 `AskUserQuestion` 询问。

```bash
# macOS / Linux
/ink-init --quick 2
```

```powershell
# Windows PowerShell sibling（PS 5.1 兼容；UTF-8 BOM 必需）
/ink-init --quick 2
```

quick 模式自带 **Quick Step 1.5 金手指三重校验**（GF-1 非战力维度 / GF-2 代价可视化 / GF-3 一句话爆点），失败 5 次自动降档。

### 1.2 detailed 模式（苏格拉底式深度提问）

不带 `--quick` 进入 Deep 模式：从题材 → 主角 → 金手指 → 反派 → 情绪曲线逐项交互；产物含完整 setting / outline / 元规则库 / 种子库 / 扰动引擎配置。适合作者已对题材有强偏好、希望最大化掌控权时使用。

### 1.3 Step 99：策划期审查（M4 P0 必跑）

ink-init / ink-plan 任一阶段产出 `setting.json` / `outline.json` 后，**必须**跑一次策划期合规审查：

```bash
python3 -m ink_writer.evidence_chain.planning_writer \
  --book <book> --setting data/<book>/setting.json
```

审查输出 `data/<book>/planning_evidence_chain.json`，含每个 stage 的 `outcome=passed|needs_human_review|blocked|skipped`。`blocked` 阻塞后续 ink-write，需人工修订或绕过。

### 1.4 紧急绕过：`--skip-planning-review`

仅在线上紧急情况（编辑临时改稿、平台抢首发）使用：

```bash
python3 -m ink_writer.evidence_chain.planning_writer \
  --book <book> --setting data/<book>/setting.json --skip-planning-review
```

此 flag 会写一条 `outcome=skipped` 的 stage 并打 `skip_reason='--skip-planning-review'`，留作可审计痕迹；恢复后请补跑一次正式审查并升级 case。

---

## 2. 写章（ink-write）

### 2.1 主流程

```bash
/ink-write --book <book> --chapter <N>
```

ink-write 分 6 个 Step：Step 0（读上下文）→ Step 1（任务书 + Context Contract）→ **Step 1.5（M3 写章合规循环）** → Step 2A（直写）→ Step 3（自检）→ Step 4-6（写盘 + 索引 + project_memory）。

### 2.2 Step 1.5：M3 写章合规循环（2026-04-25 起强制）

Step 1.5 在 Step 2A 起草后立刻运行 checker 链（pacing / OOC / continuity / consistency / high-point / reader-pull），命中 `cases_violated` 时：

- **dry-run 模式**（默认）：仍允许下笔，写 `outcome=needs_human_review` 的 evidence 供 dashboard 计数。
- **真阻断模式**（dashboard 推荐 `switch` 后切换）：`outcome=blocked` 时立即停止，禁止进入 Step 2C/3/4/5/6。

### 2.3 A/B 通道（M5 P3，默认 `enabled: false`）

`config/ab_channels.yaml` 定义两个通道：

```yaml
enabled: false
channels:
  A: { description: "对照组，跳过 meta_rule",  overrides: { use_meta_rule: false } }
  B: { description: "实验组，启用 meta_rule",  overrides: { use_meta_rule: true  } }
```

调用：

```bash
/ink-write --book <book> --chapter <N> --channel A
```

`--channel A|B` 透传到 `EvidenceChain.channel` 字段并落盘；`enabled: false` 时仅持久化字段、不切实际行为分支。切真前请先看 dashboard 周报 §Layer 4 的复发率与切换推荐。

### 2.4 紧急绕过：`--skip-compliance`

```bash
/ink-write --book <book> --chapter <N> --skip-compliance
```

跳过整个 Step 1.5；evidence 标 `skip_reason='--skip-compliance'`。仅紧急情况使用（首发倒计时、编辑要求强发）。恢复后由 ink-learn `--auto-case-from-failure` 自动从被跳过的章节里抽出失败模式补登 case。

---

## 3. 看 dashboard

### 3.1 启动

```bash
/ink-dashboard
# 然后浏览器开 http://127.0.0.1:8765
```

### 3.2 4 大指标解读（M5 Case 治理标签页）

| 指标 | 算法 | 解读 |
|---|---|---|
| `recurrence_rate` | 复发 case / (resolved + regressed) | < 5% 健康；≥ 10% 触发回顾会议 |
| `repair_speed_days` | 平均从 pending → resolved 天数 | 越低越好；M5 占位 7.0，待 case 加 `resolved_at` 后真实计算 |
| `editor_score_trend` | 扫 `data/editor_reviews/*.yaml` 周平均 | 周环比 -0.5 即触发预警 |
| `checker_accuracy` | 抽样人审 / 总命中 | < 80% 表明 checker 误报偏高，应审 case 准入 |

### 3.3 切换推荐（dry-run → 真阻断）

`recommend_dry_run_switch` 算法：
- `counter < 5` → `continue`（样本不足，继续 dry-run）
- `pass_rate < 0.60` → `investigate`（通过率太低，先修 case，不可切真）
- 否则 → `switch`（切真阻断）

M3（章节级）与 M4（策划期）各自独立计数；切真要分模块逐个评估。

### 3.4 周报命令

```bash
# macOS / Linux
ink dashboard report --week 17 --year 2026
# 默认输出 reports/weekly/2026-W17.md
```

```powershell
# Windows PowerShell sibling
ink dashboard report --week 17 --year 2026
```

周报含 5 段 H2：4 大指标 / Layer 4 复发追踪 / Layer 5 元规则浮现 / Dry-run 状态 / 行动项。`pending 元规则 ≥ 1` 或推荐 `switch` 时自动加行动项。

---

## 4. 录编辑反馈

### 4.1 ink case ingest（从编辑差评直转 case 提案）

```bash
ink case ingest --from data/editor_reviews/<book>.yaml --book <book>
```

每条编辑评论 → 自动 propose 一个 `status=pending` 的 case 到 `data/case_library/cases/CASE-NNNN.yaml`，由编辑/产品审批后升 `active`。

### 4.2 评分录入 yaml schema

`data/editor_reviews/<book>.yaml`：

```yaml
book: <book>
reviews:
  - chapter: 12
    date: 2026-04-25
    score: 7.5            # 1-10
    pros: ["节奏紧凑", "金手指代价可视化到位"]
    cons: ["反派动机弱", "第 3 段叙述视角混乱"]
    suggestions:
      - "把反派最近一次失败的具体后果在第 5 段补一句"
```

录入后即可被 `aggregator.compute_editor_score_trend` 与 `ink case ingest` 同步消费。

### 4.3 ink case approve / reject

```bash
ink case list --status pending
ink case approve CASE-0123              # 单个
ink case approve --batch CASE-0123,CASE-0124,CASE-0125
ink case reject  CASE-0124 --reason "编辑误判，已与编辑确认放弃"
```

approve 写 `status=active`；reject 写 `status=rejected`。M5 还自动学习的 case（`CASE-LEARN-NNNN` / `CASE-PROMOTE-NNNN`）走相同审批流。

---

## 5. 应急绕过

> 5 项 `--skip` 共同契约：均会落盘 `outcome=skipped` 的可审计 stage / evidence；恢复后请由 `ink-learn --auto-case-from-failure` 或人工补跑正式审查。

### 5.1 `--skip-planning-review`（绕过 Step 99 策划期审查）

见 §1.4。

### 5.2 `--skip-compliance`（绕过 Step 1.5 写章合规循环）

见 §2.4。

### 5.3 `--skip-preflight`（绕过 ink-write 前置 preflight）

跳过基础设施健康检查（如 Qdrant 离线、case_library 索引未 rebuild）。仅在确认本机环境刚跑过 preflight 时使用。

### 5.4 `--dry-run`（M3/M4 切真前默认通道）

非阻断模式：仍允许产物落盘，但所有 evidence 写 `outcome=needs_human_review`；dashboard 计数器累计后供 `recommend_dry_run_switch` 评估切真时机。

### 5.5 `--channel A` / `--channel B`（A/B 通道字段持久化）

`config/ab_channels.yaml` `enabled: false` 时只落字段，不切行为；`enabled: true` 后 A 跳 meta_rule、B 启用 meta_rule（见 §2.3）。

### 5.6 Rollback：git checkout tag

线上灾难性回退：

```bash
git fetch --tags origin
git checkout m4-final          # 回到 M4 收官点（已知稳定）
# 或回 M3 收官
git checkout m3-final
```

回退后**必须**重跑 `ink case list` / `ink dashboard --m5` / `pytest -q --no-cov` 确认环境一致。回退期间禁止再发起 ink-write，避免 case_library 与 evidence_chain 状态错位。

---

## 附：跨手册导航

- 编辑/产品视角的 case 审批与复发申诉：见 `docs/EDITOR_FEEDBACK_GUIDE.md`
- 5 周质量治理 roadmap 与 milestone 状态：见 `docs/superpowers/M-ROADMAP.md`
- Windows 兼容守则与 PowerShell sibling 模板：见根目录 `CLAUDE.md` §Windows 兼容守则
