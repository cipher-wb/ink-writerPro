# M5 完整闭环上线 — Dashboard 治理 + Layer 4/5 + user_corpus + 文档 (Design Spec)

**Status**: ready-for-plan
**Date**: 2026-04-25
**Author**: cipher-wb（产品）+ brainstorming co-pilot
**Baseline**: v23.0.0 + M1 (`m1-foundation`) + M2 partial (`m2-data-assets-partial`) + M3 (`m3-p1-loop`) + M4 (`m4-p0-planning`)
**Target version**: v26.x（5 周 M1-M5 的最后一步，**完整闭环上线**）
**Quality target**: dashboard 实时显示 4 大指标 + Layer 4 复发追踪 / Layer 5 元规则浮现自动跑 + user_corpus 链路跑通 + 周报自动产出 + 作者/编辑双手册落档
**Origin spec**: `docs/superpowers/specs/2026-04-23-case-library-driven-quality-overhaul-design.md` §3 P3 + §7 5 层闭环 + §9 M5
**Brainstorm 记录**: `docs/superpowers/M5-PREPARATION-NOTES.md` Part C（13 题全采用 ⭐ 推荐）

---

## 1. 背景与问题陈述

### 1.1 M1-M4 已交付（前提）

- **M1** ✅：Case Library 基础设施 + Qdrant + Preflight + reference_corpus symlink 修复
- **M2** 🟡：cases 完整（403 cases，hard 236 / soft 147 / info 19）+ corpus_chunking 管线（实跑 deferred）
- **M3** ✅：writer-self-check + 阻断重写 + chapter `evidence_chain.json` 全链路
- **M4** ✅：ink-init/ink-plan 阶段 7 个策划期 checker + 2 个数据资产 + 7 个上游 seed cases + `planning_evidence_chain.json`

### 1.2 M5 要解决的问题

M1-M4 把"病例闭环 + 跨书共享 + 章节级阻断 + 策划期阻断" 4 个层全部建好（spec §7.2 Layer 1-3 + 章节/策划级 checker 全覆盖），**但还差 3 件事**：

| 缺口 | spec 索引 | M5 解决 |
|---|---|---|
| Layer 4 复发追踪：resolved 的 case 再次出现就该升级 severity | §7.2 Layer 4 | `regression_tracker` 模块 |
| Layer 5 元规则浮现：N 个相似 case 应自动归纳成产线 default | §7.2 Layer 5 | `meta_rule_emergence` 模块 |
| 整个产线没有可视化 — 用户/编辑看不到 4 大指标趋势 | §7.3 量化指标 + §9 M5 | dashboard 扩展 + 周报 CLI |

加上 **user_corpus** 接入（spec §3 P3 history-travel 样例，验证用户扩展接口）+ **A/B 通道**（spec §7.4 防过拟合护栏）+ **作者/编辑双手册**（spec §9 M5），构成 M5 完整范围。

### 1.3 与 M3/M4 的关系

- M3/M4 是"产线工业化"（建机制 + 阻断 + 评估）
- M5 是"产线运营化"（看仪表盘 + 自我学习 + 用户扩展）
- M5 ✅ 后 = 5 周 roadmap 100% 结构闭环；剩下的是 **真实质量验证**（跑 30 章测试书 + 投编辑评分）— 这是 M5 之外的事

### 1.4 设计原则

1. **复用 M1-M4 已建组件**（case_library / evidence_chain / planning_evidence_chain / LLMClient / thresholds_loader），不重建任何基础设施
2. **dashboard 改 v23 已建组件采"加新标签页不改前 N 个"模式**：与 M4 SKILL.md Step 99 同思路
3. **Layer 4/5 自动跑但要人审**：`meta_rules/` 升级 P0 必经用户审批门禁；`auto-case-from-failure` 每周限 5 个 + 审批兜底
4. **A/B 通道默认关闭**：用户主动开启（`--channel A|B`）才生效；不影响现有产线
5. **user_corpus 不强制**：history-travel 样例验证 ingest CLI 跑通，用户自己塞数据
6. **跨平台兼容**：周报 CLI 不依赖 cron / launchd（用户自接调度）
7. **向后兼容**：所有 case yaml 新字段（`recurrence_history` / `meta_rule_id` / `sovereign`）默认值兼容现有 410 个 case 不破坏

---

## 2. 整体架构

### 2.1 数据流

```
[现有] ink-write 产 chapter <chapter>.evidence.json (M3)
       ink-init/ink-plan 产 planning_evidence_chain.json (M4)
   │
   ▼
[NEW Layer 4] regression_tracker 周期/触发扫描
   │   检测 resolved case 是否再次出现
   │   写 case.recurrence_history + 升级 severity
   ▼
[NEW Layer 5] meta_rule_emergence 周期扫描
   │   N=5 + similarity > 0.80 → 提议合并
   │   写 data/case_library/meta_rules/MR-NNNN.yaml (status=pending)
   │   用户审批 → 升级 cases 关联 meta_rule_id
   ▼
[NEW] dashboard "M5 Case 治理" 标签页
   │   4 大指标 + dry-run counter + 切换推荐 + meta_rules pending 列表
   │
   ▼
[NEW] ink dashboard report --week N
   │   生成 reports/weekly/<date>.md 周报
   │
   ▼
[NEW] ink-learn --auto-case-from-failure
   │   读 evidence_chain.checkers blocked + cases_violated
   │   propose pending case (CASE-LEARN-NNNN)
   │
   ▼
[NEW] A/B 通道：ink-write --channel A|B 走老规则 vs 新元规则
   │   evidence_chain 加 channel 字段
   ▼
[NEW] user_corpus history-travel 样例 + ink corpus ingest
   │   走 M2 已建 corpus_chunking 管线 + 标 source_type=user
```

### 2.2 八大组件

| # | 组件 | 类型 |
|---|---|---|
| 1 | case schema 扩展（`recurrence_history` / `meta_rule_id` / `sovereign` 字段）| 改造 |
| 2 | `ink_writer/regression_tracker/`（Layer 4）| 新建 |
| 3 | `ink_writer/meta_rule_emergence/`（Layer 5）| 新建 |
| 4 | dashboard "M5 Case 治理" 标签页 + 4 大指标 + dry-run 切换推荐 | 改造 |
| 5 | `ink dashboard report --week N` CLI | 新建 |
| 6 | A/B 通道：`config/ab_channels.yaml` + `--channel` flag | 新建 |
| 7 | user_corpus history-travel 样例 + ingest 链路 | 新建（数据 + 验证） |
| 8 | `docs/USER_MANUAL.md` + `docs/EDITOR_FEEDBACK_GUIDE.md` | 新建（文档） |

### 2.3 与 M1-M4 资产复用

| 已有资产 | M5 中的角色 | 改不改 |
|---|---|---|
| `data/case_library/cases/CASE-2026-{NNNN,M4-NNNN}.yaml` | 加 3 字段（recurrence_history / meta_rule_id / sovereign）| 字段加值不动结构 |
| `ink_writer/case_library/{store, ingest, models}` | 加 `record_recurrence(case_id, evidence)` + `iter_resolved()` 方法 | 加方法不动现有 |
| `ink_writer/evidence_chain/{models, writer}` (M3) | 加 `channel: str \| None = None` 字段（A/B 通道）| 加字段向后兼容 |
| `ink_writer/evidence_chain/planning_writer.py` (M4) | 同上加 channel 字段 | 加字段 |
| `scripts/corpus_chunking/llm_client.LLMClient` | Layer 5 相似度比对 + 元规则归纳 prompt | 不动 |
| `ink-writer/skills/ink-dashboard/SKILL.md` | 加"M5 Case 治理"段 | 加段不改前 N 段 |
| `ink-writer/skills/ink-learn/SKILL.md` | 加 `--auto-case-from-failure` + `--promote` 段 | 加段 |
| `ink-writer/skills/ink-write/SKILL.md` | 加 `--channel` 参数说明 | 加段 |
| `data/.dry_run_counter`（M3）+ `.planning_dry_run_counter`（M4）| dashboard 读这两个文件显示 + 切换推荐算法基于 evidence_chain 通过率 | 不动 |
| `config/checker-thresholds.yaml`（M3+M4）| dashboard 显示当前阈值 | 不动 |

### 2.4 边界（明确不做的事）

- ❌ 不补 M2 corpus_chunks（保持 deferred；US-013 可选）
- ❌ 不动 M3 5 个章节级 checker / M4 7 个策划期 checker（M5 只读它们的 evidence_chain）
- ❌ 不打包"自动周报 cron"（用户自接）
- ❌ 不做"在 dashboard 直接编辑 case yaml"（只读展示，编辑走 `ink case approve` CLI）
- ❌ 不做"实时 LLM 元规则推断"（Layer 5 是周期任务 / 用户触发，不实时）
- ❌ 不做"A/B 通道随机分流"（Q8 默认配置驱动，用户显式选 channel）
- ❌ 不做 dashboard "切换 dry-run 真阻断"按钮（仅推荐，用户手工改 yaml）
- ❌ 不做"复发申诉"工作流（编辑反馈手册简单说怎么标即可）
- ❌ user_corpus 不做"自动 propose case"（M2 chunks deferred + Q10 已 cover failure 模式）

---

## 3. case schema 扩展

### 3.1 新字段

`data/case_library/cases/CASE-NNNN.yaml` 加 3 个 optional 字段：

```yaml
# 现有字段保持不变...

recurrence_history:           # Layer 4 写入；list[dict]
  - resolved_at: '2026-04-20'
    regressed_at: '2026-04-25'
    book: 'demo-001'
    chapter: 'ch042'
    evidence_chain_path: 'data/demo-001/chapters/ch042.evidence.json'
    severity_before: hard
    severity_after: hard       # 已是顶级则递增 recurrence_count

meta_rule_id: null             # Layer 5 合并后填 MR-NNNN

sovereign: false               # 是否核心铁律（Layer 5 浮现时跳过）
```

### 3.2 向后兼容

- 现有 410 个 case yaml 不强制 backfill；loader 读到缺字段 fallback 为：
  - `recurrence_history` → `[]`
  - `meta_rule_id` → `None`
  - `sovereign` → `False`
- `ink case approve` / `ingest_case` 解析新字段时若缺则补默认值

### 3.3 schema 文件更新

- `schemas/case_schema.json` 加 3 个 optional 字段（不破坏现有 active cases 校验）
- 加单元测试覆盖：旧 case 文件无新字段仍能加载 ✅

---

## 4. Layer 4 — regression_tracker

### 4.1 职责

扫描所有 evidence_chain（chapter + planning），找出 status=resolved 的 case 是否再次被命中（`cases_violated` / `cases_hit` 含其 id），如有则：

1. 给 case 加一条 `recurrence_history` 记录
2. 升级 severity（hard 已顶则 `recurrence_count += 1`）
3. dashboard 展示该 case 为"复发"状态

### 4.2 模块结构

```
ink_writer/regression_tracker/
├── __init__.py
├── tracker.py             # scan_evidence_chains() + record_recurrence()
└── models.py              # RecurrenceRecord dataclass
```

### 4.3 核心 API

```python
def scan_evidence_chains(
    *,
    base_dir: Path = Path("data"),
    case_store: CaseStore,
    since: datetime | None = None,    # 只扫此时间之后产出的 evidence_chain
) -> list[RecurrenceRecord]:
    """
    返回新检测到的复发记录列表（不写盘，由调用方决定是否 commit）
    """

def apply_recurrence(
    *,
    case: Case,
    record: RecurrenceRecord,
    case_store: CaseStore,
) -> None:
    """
    持久化：写 case.yaml 的 recurrence_history + 可能升级 severity
    """
```

### 4.4 触发时机

- **手工**：`ink dashboard report --week N` 触发前自动跑一次（Q3 默认仅同 book 内复发）
- **CLI**：新增 `python -m ink_writer.regression_tracker --since YYYY-MM-DD` 单跑
- M5 不做 cron / watchdog 自动触发（用户自接）

### 4.5 单元测试

| 用例 | 期望 |
|---|---|
| resolved case 再次出现 | 写 recurrence_history + severity 升级 |
| pending case 再次出现 | 不写（仅 resolved → regressed 才计） |
| 跨 book 复发 | 不计（Q3 默认仅同 book） |
| 同 book 多章重复复发 | 写多条 recurrence_history |
| 缺 evidence_chain.cases_violated 字段 | 优雅跳过（向后兼容） |

---

## 5. Layer 5 — meta_rule_emergence

### 5.1 职责

扫描所有 active cases（不含 sovereign），找出"N=5 个 + LLM 相似度 > 0.80"的相似 case 集合，提议合并到 `data/case_library/meta_rules/MR-NNNN.yaml`（status=pending），等用户审批 → 升级 cases.meta_rule_id。

### 5.2 相似度算法

LLM 主观判断（不用向量），调用 glm-4.6 prompt：

```
你是 case 库元规则归纳助手。给定 N 个 case 的 failure_pattern.description + tags，
判断它们是否描述同一类问题（即可合并为元规则）。

输入：
[
  {id: "CASE-2026-0042", title: "...", description: "...", tags: [...]},
  ...
]

严格 JSON：
{
  "similar": true/false,
  "similarity": 0.85,
  "merged_rule": "...",      # 合并后的元规则文本（一句话）
  "covered_cases": ["CASE-2026-0042", ...],
  "reason": "..."
}
```

### 5.3 模块结构

```
ink_writer/meta_rule_emergence/
├── __init__.py
├── emerger.py             # find_similar_clusters() + propose_meta_rule()
├── models.py              # MetaRuleProposal dataclass
└── prompts/emerge.txt
```

### 5.4 核心 API

```python
def find_similar_clusters(
    *,
    cases: list[Case],          # 必须 active + sovereign=False
    llm_client: LLMClient,
    min_cluster_size: int = 5,  # Q4 默认 N=5
    similarity_threshold: float = 0.80,
    model: str = "glm-4.6",
) -> list[MetaRuleProposal]:
    """
    返回提议列表（不写盘）。每个 proposal 包含覆盖的 case_ids + merged_rule 文本
    """

def write_meta_rule_proposal(
    *,
    proposal: MetaRuleProposal,
    base_dir: Path = Path("data/case_library/meta_rules"),
) -> Path:
    """
    写到 data/case_library/meta_rules/MR-NNNN.yaml (status=pending)
    """
```

### 5.5 用户审批流程（Q5）

```bash
# 列出 pending 元规则
ink meta-rule list --status pending

# 审批某条（升级关联 cases）
ink meta-rule approve MR-0001

# 拒绝（删除 pending yaml）
ink meta-rule reject MR-0001
```

approve 时给关联的 cases 写 `meta_rule_id: MR-0001` 字段。

### 5.6 主权保护（Q13）

`find_similar_clusters` 在筛选 cases 时强制：

```python
cases = [c for c in active_cases if not c.sovereign]
```

`sovereign=True` 的 case 不参与浮现归纳。

### 5.7 单元测试

| 用例 | 期望 |
|---|---|
| 5 个相似 case + sim > 0.80 | 产 1 个 proposal |
| 4 个相似 case | 不产（< N=5） |
| sovereign=True case 不参与 | 验证排除逻辑 |
| LLM 失败 | 返回空列表（不抛错） |
| 同一组 case 已有 meta_rule_id | 跳过（已合并过） |

---

## 6. Dashboard 扩展（"M5 Case 治理"标签页）

### 6.1 新增标签页内容

```
[M5 Case 治理]
├── ① 4 大指标卡片
│    ├── 病例复发率：X% (resolved → regressed) 趋势线
│    ├── 修复速度：平均 X 天（首次差评 → resolved）
│    ├── 编辑评分趋势：均分 X / 月
│    └── checker 准确率：X%（手工抽样命中 vs LLM 判定差异）
│
├── ② Dry-run 状态
│    ├── M3 chapter dry-run counter: X / 5（推荐切换：通过率 > 60% 才切真）
│    └── M4 planning dry-run counter: X / 5（同上）
│
├── ③ Pending 元规则列表
│    ├── MR-0001（覆盖 5 case）— 待审批
│    └── MR-0002（覆盖 7 case）— 待审批
│
├── ④ 复发 case 列表（最近 7 天）
│    └── CASE-2026-0042（demo-001 ch042 第 3 次复发）
│
└── ⑤ 周报快捷链接
     └── [生成本周周报] → ink dashboard report --week N
```

### 6.2 数据源

- ① 4 大指标：聚合 `data/<book>/chapters/*.evidence.json` + `data/<book>/planning_evidence_chain.json` + case_library
- ② counter 文件：`data/.dry_run_counter` + `data/.planning_dry_run_counter`
- ③ pending：扫 `data/case_library/meta_rules/*.yaml` status=pending
- ④ 复发：扫 case.recurrence_history 字段
- ⑤ 链接：触发 `ink dashboard report --week N` CLI

### 6.3 dashboard 改造

`ink-writer/skills/ink-dashboard/SKILL.md` 末尾追加 `## M5 Case 治理（M5 P3 必跑）` 章节（与 M4 SKILL.md Step 99 同模式）：

```markdown
## M5 Case 治理（M5 P3）

加载新标签页 "M5 Case 治理"：

```bash
ink dashboard --m5
```

数据源： evidence_chain (M3 + M4) + case_library + dry_run counters。

### 周报生成

```bash
ink dashboard report --week 17
# 输出 reports/weekly/2026-W17.md
```
```

### 6.4 dashboard 后端

- 新增 `ink-writer/dashboard/m5_overview.py` Flask/FastAPI 路由 `/api/m5-overview`（与 v23 dashboard 同框架）
- 数据聚合放 `ink_writer/dashboard/aggregator.py`：
  - `compute_recurrence_rate(*, since=None) -> float`
  - `compute_repair_speed(*, since=None) -> float`
  - `compute_editor_score_trend(*, since=None) -> list[dict]`
  - `compute_checker_accuracy(*, sample_size=50) -> float`

### 6.5 切换推荐算法（Q12）

```python
def recommend_dry_run_switch(
    *,
    counter: int,
    pass_rate: float,
    threshold_runs: int = 5,
    threshold_pass_rate: float = 0.60,
) -> str:
    """
    返回 'switch' / 'continue' / 'investigate'
    """
    if counter < threshold_runs:
        return "continue"
    if pass_rate < threshold_pass_rate:
        return "investigate"  # 失败率高，先看原因
    return "switch"
```

---

## 7. 周报 CLI

### 7.1 命令

```bash
ink dashboard report --week N [--book BOOK_ID] [--out PATH]
# 默认输出到 reports/weekly/2026-W<N>.md
```

### 7.2 周报内容（markdown 模板）

```
# Weekly Report - 2026-W17 (2026-04-20 ~ 2026-04-26)

## 4 大指标
- 病例复发率：8.2%（上周 7.8%，+0.4%）
- 修复速度：3.5 天（上周 3.1，+0.4）
- 编辑评分：未录入
- checker 准确率：未抽样

## Layer 4 复发追踪
- 本周新增 3 条复发记录
- CASE-2026-0042（demo-001 ch042，第 3 次复发，已升 severity）

## Layer 5 元规则浮现
- 本周新提议 1 条：MR-0003（覆盖 5 个 naming-style case）
- 待审批：MR-0001 / MR-0002 / MR-0003

## Dry-run 状态
- M3 chapter: 4/5（通过率 80%，推荐切换）
- M4 planning: 2/5（继续观察）

## A/B 通道（如启用）
- channel A: 12 章
- channel B: 13 章
- A 通过率 75% / B 通过率 82%（B 显著优）

## 行动项
- [ ] 审批 3 条 pending 元规则
- [ ] 评估 M3 dry-run 切真（通过率达标）
```

### 7.3 模块

`ink_writer/dashboard/weekly_report.py`：
- `generate_weekly_report(*, week_num, book=None, out_path=None) -> Path`
- 调用 `aggregator.py` 的方法 + 模板字符串拼接
- 写盘 + 返回 Path

---

## 8. A/B 通道

### 8.1 配置

`config/ab_channels.yaml`：

```yaml
# M5 A/B 通道（spec §7.4 防过拟合护栏）
# default: 不启用（用户显式 --channel A|B 才生效）
enabled: false
channels:
  A:
    description: 老规则（M4 baseline，无元规则升级）
    overrides: {}      # 阈值不改
  B:
    description: 新规则（含 Layer 5 元规则升级）
    overrides:
      meta_rule_active: true
```

### 8.2 ink-write 集成

`ink-write` CLI 加 `--channel A|B|both`：
- A：跳过 meta_rule_emergence 升级，evidence_chain 写 `channel: "A"`
- B：使用 meta_rule，evidence_chain 写 `channel: "B"`
- both：默认（不启用 A/B），不写 channel 字段（向后兼容）

### 8.3 evidence_chain 加字段

```python
@dataclass
class EvidenceChain:
    # ... 现有字段 ...
    channel: str | None = None    # 'A' | 'B' | None
```

### 8.4 dashboard 分通道展示

`compute_*` 方法加 `channel: str | None = None` 参数，分通道聚合 4 大指标。

---

## 9. user_corpus history-travel 样例

### 9.1 目录结构

```
data/case_library/user_corpus/
├── history-travel/
│   ├── 明朝那些事儿_节选_第一章.txt   (公开节选 ≤ 2000 字)
│   ├── 明朝那些事儿_节选_第二章.txt
│   └── _meta.yaml
└── user_genres.yaml
```

### 9.2 _meta.yaml 内容

```yaml
genre: history-travel
description: 历史穿越类作品节选样例（公开 fair_use_excerpt）
license: fair_use_excerpt
files:
  - path: 明朝那些事儿_节选_第一章.txt
    source: 当年明月《明朝那些事儿》
    note: 公开节选不超过 2000 字，用于 ingest 链路验证
created_at: '2026-04-25'
```

### 9.3 ingest 链路

```bash
ink corpus ingest --dir data/case_library/user_corpus/history-travel/
```

走 M2 已建 `corpus_chunking` 管线 + 自动给每个 chunk 标 `source_type: user`（原 source_type 为 reference）。

### 9.4 单元测试

- `test_user_corpus_meta_yaml_valid`：_meta.yaml schema 校验
- `test_ingest_marks_source_type_user`：mock M2 管线，验证 chunks 标记
- 不真跑 M2 切片（M2 deferred），仅验证管线参数传递

### 9.5 边界

- M2 corpus_chunks 实跑仍 deferred；US 内不跑实际切片
- 仅 1 个题材样例（history-travel）；其他题材让用户自己塞

---

## 10. ink-learn 改造

### 10.1 新增 flag

`ink-writer/skills/ink-learn/SKILL.md` 加 2 段：

#### `--auto-case-from-failure`

读取 `data/<book>/chapters/*.evidence.json` 找出 blocked 章节 + cases_violated 集合，分析新失败模式（pattern_failure 类型）：

- 把同一 cases_violated 组合连续出现 ≥ 2 次的视为 "新模式"
- 不在现有 cases 列表中 → 自动 propose `data/case_library/cases/CASE-LEARN-NNNN.yaml`（status=pending）
- 每周最多 propose 5 个（`config/ink_learn_throttle.yaml` 控制）

#### `--promote`

读 `.ink/project_memory.json` 短期记忆 → 把"重复出现 ≥ N 次"的 success/failure 模式回灌到 case_library（成功 → pattern_success，失败 → pending case）。

### 10.2 模块

`ink_writer/learn/`：
- `auto_case.py`：`propose_cases_from_failures(*, evidence_dir, case_store, max_per_week=5) -> list[Case]`
- `promote.py`：`promote_short_term_to_long_term(*, project_memory_path, case_store, min_occurrences=3) -> list[Case]`

### 10.3 单元测试

- `test_auto_case_proposes_new_pattern`
- `test_auto_case_skips_existing_cases`
- `test_auto_case_throttled_at_max_per_week`
- `test_promote_aggregates_repeated_patterns`

---

## 11. 文档（作者手册 + 编辑反馈手册）

### 11.1 `docs/USER_MANUAL.md`（5 节）

```
# Ink Writer Pro 作者手册

## 1. 开新书（ink-init quick / detailed）
   - quick 模式：5 分钟生成 3 套方案
   - detailed：自定义题材 / 主角 / 金手指
   - Step 99 策划期审查（M4）

## 2. 写章（ink-write）
   - Step 1.5 写完合规循环（M3）
   - dry-run 模式 vs 真阻断
   - --skip-planning-review / --skip-compliance 紧急绕过

## 3. 看 dashboard
   - ink dashboard --m5
   - 4 大指标解读
   - 切换推荐怎么读

## 4. 录编辑反馈
   - ink case ingest --from <file>
   - 评分录入：data/editor_reviews/<book>.yaml

## 5. 应急绕过
   - 各种 --skip flag 用法
   - 出问题怎么 rollback
```

### 11.2 `docs/EDITOR_FEEDBACK_GUIDE.md`（3 节）

```
# 编辑反馈录入手册

## 1. 评分如何录入
   - data/editor_reviews/<book>.yaml schema
   - 评分 / 优点 / 问题点 / 建议

## 2. case 提案审批
   - 编辑差评 → ink case ingest 自动 propose
   - 编辑或产品审 status=pending → active

## 3. 复发申诉
   - case 被升 severity 时怎么标记"误判"
   - sovereign 字段含义
```

### 11.3 范围控制

- 不写"教程"或"上手教程"（这是 README 的事）
- 不重复 SKILL.md 内容（手册引用 SKILL.md 即可）
- 每节 ~200-400 字

---

## 12. user story 列表（13 US，全部 ralph 顺序执行）

| US | 标题 | 估时 | 依赖 |
|---|---|---|---|
| US-001 | case schema 扩展（recurrence_history / meta_rule_id / sovereign 字段 + 向后兼容 + schema.json 更新）| 10 min | M1 case_library |
| US-002 | Layer 4 `regression_tracker` 模块 + CLI + 4 单元测试 | 20 min | M3 evidence_chain + M4 planning_writer |
| US-003 | Layer 5 `meta_rule_emergence` 模块 + LLM prompt + 5 单元测试 | 25 min | M2 LLMClient |
| US-004 | `ink meta-rule {list,approve,reject}` CLI + 关联 case 字段写入 | 15 min | US-001 + US-003 |
| US-005 | dashboard "M5 Case 治理" 标签页 + 4 大指标 aggregator + 切换推荐算法 + 6 单元测试 | 30 min | v23 ink-dashboard |
| US-006 | `ink dashboard report --week N` CLI 周报 markdown 生成 + 3 单元测试 | 20 min | US-005 |
| US-007 | A/B 通道 `config/ab_channels.yaml` + `--channel` flag + evidence_chain 加 channel 字段 + 4 单元测试 | 20 min | M3 evidence_chain |
| US-008 | user_corpus history-travel 样例 + _meta.yaml + ingest 链路 + 3 单元测试 | 15 min | M2 corpus_chunking |
| US-009 | ink-learn `--auto-case-from-failure` + throttle config + 4 单元测试 | 20 min | M3 evidence_chain |
| US-010 | ink-learn `--promote` + 4 单元测试 | 15 min | project_memory.json |
| US-011 | `docs/USER_MANUAL.md` 5 节 | 15 min | 全部 |
| US-012 | `docs/EDITOR_FEEDBACK_GUIDE.md` 3 节 | 10 min | 全部 |
| US-013 | M5 e2e 集成测试（6 用例：recurrence / meta_rule / dashboard / weekly_report / ab_channel / ink_learn）+ M5 验收 + tag `m5-final` + ROADMAP/handoff "5 周完成"标记 + push | 30 min | 全部 |

**总估时**：约 4 小时（M5 涉及更多模块改造 + 文档，节奏比 M4 略慢）

---

## 13. 验收

### 13.1 M5 验收清单

```bash
# (1) 全量 pytest 全绿 + 覆盖率 ≥ 82%
pytest -q

# (2) M5 全部模块导入成功
python3 -c "from ink_writer.regression_tracker import scan_evidence_chains; \
            from ink_writer.meta_rule_emergence import find_similar_clusters; \
            from ink_writer.dashboard.aggregator import compute_recurrence_rate; \
            from ink_writer.dashboard.weekly_report import generate_weekly_report; \
            from ink_writer.learn.auto_case import propose_cases_from_failures; \
            from ink_writer.learn.promote import promote_short_term_to_long_term; \
            print('M5 OK')"

# (3) case schema 加 3 字段成功 + 现有 410 case 加载兼容
python3 -c "from ink_writer.case_library.store import CaseStore; \
            s = CaseStore(); active = list(s.iter_active()); \
            assert all(hasattr(c, 'sovereign') for c in active); \
            print(f'410+ cases 加载成功，sovereign 字段 OK')"

# (4) regression_tracker 跑通
python3 -m ink_writer.regression_tracker --since 2026-04-25

# (5) meta_rule_emergence 提议产出
python3 -m ink_writer.meta_rule_emergence --propose
ls data/case_library/meta_rules/MR-*.yaml 2>/dev/null

# (6) dashboard 加载 M5 标签
ink dashboard --m5 &
curl http://127.0.0.1:8765/api/m5-overview     # 200 OK + JSON
kill %1

# (7) 周报生成
ink dashboard report --week 17
ls reports/weekly/2026-W17.md

# (8) A/B 通道 evidence_chain 加 channel 字段
python3 -c "from ink_writer.evidence_chain.models import EvidenceChain; \
            e = EvidenceChain(channel='A', ...); \
            assert e.to_dict()['channel'] == 'A'; print('OK')"

# (9) user_corpus ingest 链路（不真跑 M2，仅验证参数）
ink corpus ingest --dir data/case_library/user_corpus/history-travel/ --dry-run

# (10) ink-learn --auto-case-from-failure
python3 -c "from ink_writer.learn.auto_case import propose_cases_from_failures; \
            from ink_writer.case_library.store import CaseStore; \
            s = CaseStore(); proposals = propose_cases_from_failures(evidence_dir='data', case_store=s); \
            print(f'propose count: {len(proposals)}')"

# (11) 文档存在
test -f docs/USER_MANUAL.md && wc -l docs/USER_MANUAL.md
test -f docs/EDITOR_FEEDBACK_GUIDE.md && wc -l docs/EDITOR_FEEDBACK_GUIDE.md

# (12) git tag m5-final + push
git tag -l | grep m5-final
git ls-remote --tags origin | grep m5-final
```

### 13.2 ROADMAP / handoff 更新

- 更新 `docs/superpowers/M-ROADMAP.md` 进度跟踪表 M5 行 ⚪ → ✅ + Status 行加 "5 周 roadmap 100% 完成"
- 更新 `docs/superpowers/M-SESSION-HANDOFF.md` §2 进度快照（80% → 100%，4/5 + 1 partial → 5/5 + 1 partial）+ §3 重写为 M5 实际产出 + §7 改为"M5 ✅ 已完成；下一步真实质量验证"段
- 更新 memory `project_quality_overhaul_roadmap.md` 标记 100% 完成

---

## 14. 故意延后的事（M5 之外的 follow-up）

1. **真实测试书 30 章**（核心质量验证）：M5 之后用户跑 ink-init quick → ink-plan → ink-write 30 章 → 投编辑评分 → dashboard 看趋势是否真的从 30 → 60+
2. **M2 corpus_chunks 实跑**（spec §6 P2 完整）：`docs/superpowers/M2-FOLLOWUP-NOTES.md` A 选项；M5 ✅ 后再做
3. **元规则浮现的 cron 自动化**：M5 仅手工触发；如需自动化需用户接 cron / launchd
4. **dashboard 写权限**（直接审批 meta_rule）：M5 仅只读展示
5. **跨 book 复发追踪**（Q3 默认仅同 book）：M5 之后如发现需要可加
6. **A/B 通道随机分流**（Q8 默认配置驱动）：M5 之后如需要 50% 强制随机可加
7. **更多 user_corpus 题材**（M5 仅 history-travel 1 题材）：用户自塞
