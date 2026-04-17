# FIX-04 设计稿：Step 3 Gate Orchestrator 生产接线

**来源**：`docs/engineering-review-report-v5.md` Phase 2.P2.1
**定位**：v13 健康审计最关键的单点修复 — 把"规格齐全、生产未接入"的并发引擎 + 5 个 Python gate 真正串起来
**工作量**：3-4 天
**执行者**：Ralph 无法独立完成（涉及架构设计），需人工 + 有限 Ralph 子任务配合

---

## 1. 问题陈述

v5 审计确认：
- `ink_writer/checker_pipeline/runner.py`（249 行 asyncio 并发引擎 + cancel 语义 + 25 测试）**零生产调用者**
- Step 3.6-3.10 五个 Python gate（`run_hook_gate` / `run_emotion_gate` / `run_anti_detection_gate` / `run_voice_gate` / `scan_plotlines`）**零生产 import**
- `ink-writer/scripts/step3_harness_gate.py:22-40` 读死路径 `.ink/reports/review_ch*.json`，生产链路从不写此路径 → **100% 命中"无报告默认通过"静默 PASS 分支**
- 当前 `/ink-write` 的 Step 3 完全依赖 LLM 按 SKILL.md 文本自律执行 subagent

**结果**：用户跑 `/ink-auto` 全绿时，**一半质检是 LLM 在演**，Python 硬门禁形同虚设。

---

## 2. 当前架构（孤儿地图）

```
┌─────────────────────────────────────────────────────┐
│ /ink-write SKILL.md Step 3                          │
│   ↓ LLM 读文本 "call these checkers"                │
│   ↓                                                 │
│   [LLM 自律派发 subagent]                          │
│   ↓                                                 │
│   (无 Python 编排、无并发、无硬阻断)                │
│   ↓                                                 │
│   data-agent 最后兜底写 index.db.review_metrics     │
└─────────────────────────────────────────────────────┘

孤儿 1️⃣：ink_writer/checker_pipeline/runner.py
    ├── CheckerRunner (asyncio, first-fail-cancels)
    ├── GateSpec (gate_id, runner, is_hard, timeout)
    └── 249 行 + 25 测试，0 生产调用者

孤儿 2️⃣：5 个 Python Gate（都在 ink_writer/*/）
    ├── reader_pull/hook_retry_gate.py::run_hook_gate
    ├── emotion/emotion_gate.py::run_emotion_gate
    ├── anti_detection/anti_detection_gate.py::run_anti_detection_gate
    ├── voice_fingerprint/ooc_gate.py::run_voice_gate
    └── plotline/tracker.py::scan_plotlines

孤儿 3️⃣：step3_harness_gate.py
    └── 读死路径 → 永远 PASS
```

---

## 3. 目标架构

```
┌─────────────────────────────────────────────────────────────────┐
│ /ink-write SKILL.md Step 3                                      │
│   ↓ Bash: python3 -m ink_writer.checker_pipeline.step3_runner \ │
│            --chapter-id <id> --state-dir .ink/                  │
│   ↓                                                             │
│   step3_runner.py (新入口)                                      │
│   ├── Load chapter + review_bundle from state                   │
│   ├── CheckerRunner.run_gates([5 GateSpec], parallel=2)         │
│   │     ├── hook_retry_gate       (hard, timeout 60s)           │
│   │     ├── emotion_gate          (hard, timeout 60s)           │
│   │     ├── anti_detection_gate   (hard, timeout 120s)          │
│   │     ├── voice_gate            (soft, timeout 60s)           │
│   │     └── scan_plotlines        (hard, timeout 30s)           │
│   ├── 任何 hard FAIL → cancel 其余 → raise ChapterGateFailed    │
│   │     └── stderr 打印 gate_id + reason + fix_suggestion       │
│   │     └── exit code 1                                         │
│   └── 全 PASS 或仅 soft FAIL → 写 index.db.review_metrics       │
│                                                                 │
│ Step 3.5 Harness Gate（修复后）                                 │
│   ↓ step3_harness_gate.py 改读 index.db.review_metrics          │
│   ↓ 按严重度汇总判断是否进 polish                               │
│   ↓                                                             │
│ polish-agent（消费 gate_results）                               │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. 接口契约

### 4.1 Python API

```python
# ink_writer/checker_pipeline/step3_runner.py

from dataclasses import dataclass

@dataclass
class GateFailure:
    gate_id: str
    severity: str        # 'hard' | 'soft'
    reason: str
    fix_suggestion: str | None
    raw_output: dict

@dataclass
class Step3Result:
    chapter_id: int
    passed: bool                     # all hard pass → True
    hard_fails: list[GateFailure]
    soft_fails: list[GateFailure]
    gate_results: dict               # gate_id → raw output（下游 polish 消费）
    duration_ms: int

async def run_step3(
    chapter_id: int,
    state_dir: Path,
    timeout_s: int = 300,
    parallel: int = 2,
    dry_run: bool = False,
) -> Step3Result:
    """主入口。cancel-on-first-hard-fail 语义。"""
    ...
```

### 4.2 CLI

```bash
python3 -m ink_writer.checker_pipeline.step3_runner \
    --chapter-id 5 \
    --state-dir .ink/ \
    [--timeout 300] \
    [--parallel 2] \
    [--dry-run]            # 跑但不写 index.db（Phase A 用）
```

**退出码**：
- `0` = 所有 hard gate 通过
- `1` = 有 hard gate 失败
- `2` = 内部错误（load state 失败 / timeout 本身失败）

### 4.3 数据库 schema

`index.db.review_metrics` 已存在（v5 审计确认），本设计**复用**，新增列（若缺）：

```sql
CREATE TABLE IF NOT EXISTS review_metrics (
    chapter_id INTEGER PRIMARY KEY,
    passed INTEGER NOT NULL,           -- 0/1
    hard_fail_count INTEGER NOT NULL,
    soft_fail_count INTEGER NOT NULL,
    gate_results_json TEXT NOT NULL,   -- 完整 dict 序列化
    duration_ms INTEGER NOT NULL,
    run_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    schema_version INTEGER DEFAULT 1
);
```

---

## 5. 文件变更清单

| # | 文件 | 操作 | 复杂度 |
|---|------|------|:---:|
| 1 | `ink_writer/checker_pipeline/step3_runner.py` | **新建**（~200 行） | M |
| 2 | `ink_writer/checker_pipeline/runner.py` | 复用，不改 | - |
| 3 | 5 个 gate 文件 | 仅被 import，不改 | - |
| 4 | `ink-writer/scripts/step3_harness_gate.py` | **重写**读取路径（改读 index.db）| S |
| 5 | `ink-writer/scripts/data_modules/index_manager.py` | 加 `write_review_metrics()` / `read_review_metrics()` | S |
| 6 | `ink-writer/skills/ink-write/SKILL.md` | Step 3 段落替换为调用 runner | S |
| 7 | `tests/checker_pipeline/test_step3_runner.py` | **新建**单元 + 集成测试 | M |
| 8 | `docs/architecture.md` + `docs/agent_topology_v13.md` | 更新 Step 3 描述 | S |

---

## 6. 迁移策略（三阶段）

### Phase A：影子运行（Day 1-2）

- 实现 `step3_runner.py` + `index_manager.write_review_metrics`
- 新增环境变量开关 `INK_STEP3_RUNNER_MODE`：
  - `off`（默认）= 不跑 runner，走原 LLM 自律
  - `shadow` = 跑 runner，写 `index.db.review_metrics`，但**不阻断**流程
  - `enforce` = 跑 runner，hard fail 真阻断
- `/ink-write` SKILL.md 里加一段："如果 `INK_STEP3_RUNNER_MODE=shadow|enforce`，先跑 runner 再决定是否走 LLM 流程"
- 自己跑 5 章（选不同题材），观察：
  - 5 个 gate 各自 FAIL 率是否合理（< 30% 为 baseline）
  - runner 耗时（预期 < 60s）
  - 与 LLM 自律结果的差异（diff）

### Phase B：强制启用（Day 3）

- 默认切 `INK_STEP3_RUNNER_MODE=enforce`
- `step3_harness_gate.py` 改读 `index.db.review_metrics`（fallback 旧路径，打 warning）
- SKILL.md 的 Step 3 文本删掉逐 checker 描述，改为"执行 `bash python3 -m ... step3_runner`"

### Phase C：清理（Day 4）

- 若 1 周内无 regression → 彻底删除 SKILL.md 里的逐 checker 描述
- 删除 `step3_harness_gate.py` 旧 JSON 路径读取
- 清理 `tests/` 中针对老路径的 fixture

---

## 7. 测试计划

### 7.1 单元测试（`test_step3_runner.py`）

- `test_all_pass`：5 gate 全 pass → Step3Result.passed=True
- `test_one_hard_fail_cancels`：第 1 个 gate FAIL → 其余被 cancel，passed=False
- `test_soft_fail_continues`：voice_gate FAIL (soft) → 流程继续，其余 gate 正常跑
- `test_timeout_per_gate`：某 gate > timeout → 该 gate 标 FAIL，不阻塞
- `test_db_write`：跑完后 index.db.review_metrics 有正确记录

### 7.2 集成测试

- `test_cli_exit_codes`：subprocess 跑 `python3 -m ... step3_runner --chapter-id 5`，验证 exit code
- `test_dry_run`：`--dry-run` 不写 DB
- `test_shadow_mode`：`INK_STEP3_RUNNER_MODE=shadow` 不抛异常（即使 hard fail）

### 7.3 回归

- 现有 `tests/` 2028 tests 无破坏
- `/ink-write` 手动连跑 3 章无回归

---

## 8. 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| 某 gate 假阳性率高，阻断合理章节 | 🟠 中 | Phase A 影子期收集数据；每 gate 可改 `is_hard=False` |
| `CheckerRunner` 并发引擎实际有 bug（249 行 untested in prod） | 🟠 中 | `parallel=1` 为保守默认；有 25 现存测试兜底 |
| LLM 原 Step 3 自律调用形成"默契"，切换后某些 corner case 行为异常 | 🟡 低 | Phase A 观察 1 周；保留 `off` 模式作为 kill-switch |
| `index.db.review_metrics` schema 与老数据冲突 | 🟡 低 | 新字段用 DEFAULT，老行兼容；schema_version 字段预留迁移 |

---

## 9. Ralph 可执行子任务

本设计稿主体需人工实现 + 测试，但以下子任务可由 Ralph 接力：

| Ralph US 候选（未来） | 对应本设计的 Phase |
|---------------------|----------------|
| 为 5 个 gate 各写一个 pytest fixture 和基线测试 | 配合 Phase A 观察 |
| `index_manager.py` 加 `write_review_metrics` / `read_review_metrics` 方法 + 测试 | Phase A 前置 |
| `step3_harness_gate.py` 改读 `index.db`（即当前 PRD 的 US-005） | Phase B |
| SKILL.md 里 Step 3 文本替换为 bash 调用（当 Phase B 完成后） | Phase B |

---

## 10. 验收标准（整体）

- [ ] `/ink-write` 默认跑时，`index.db.review_metrics` 每章有完整行记录
- [ ] 连续跑 10 章，runner 无 crash、无 timeout、无并发 bug
- [ ] 手动引入 1 个一定失败的 chapter，`exit code 1` 且 `polish-agent` 不被触发
- [ ] SKILL.md Step 3 文本 ≤10 行（从当前 ~100 行文本精简）
- [ ] Phase C 完成后，`CheckerRunner` 和 5 个 gate 从"规格孤儿"→"生产核心"
- [ ] 新增测试不少于 15 项，全 pass

---

**设计稿完。** 等待用户确认后启动 Phase A 实现。
