# PRD: ink-writer v13 健康审计修复（Step 2）

## 来源与定位

Step 1 深度健康审计已完成。总报告：[docs/engineering-review-report-v5.md](../docs/engineering-review-report-v5.md)

本 PRD 是 Step 2 修复的**人类可读主文档**，定义目标、约束、边界、验收。机器可执行版本在 [`ralph/prd.json`](../ralph/prd.json)（25 User Story）。

**执行链条**：
```
本 PRD (tasks/prd-v13-step2-fixes.md)
    ↓
ralph/prd.json (25 US, 机器可执行)
    ↓
./ralph/ralph.sh (自动执行)
```

---

## Goals

- **G1** 修复 3 个 Blocker：依赖声明缺失（US-001~003）、PipelineManager 并发声明虚假（US-023）、Memory v13 方向与代码不一致（US-024+025）
- **G2** 兑现 v13 "规格-代码 gap" 的关键缺失：Step 3.5 Harness Gate 改读真源（US-005）、Retriever 单例化（US-006）、API Key 护栏（US-007）、Style RAG 开箱即用（US-008）、创意指纹入库（US-009+010）、ink-resolve 走 SQL（US-011）
- **G3** 工程基线拉齐：pytest 覆盖率门禁现实化（US-004）、LLM/章级 timeout（US-012+013）、日志迁 logger（US-018）
- **G4** 清理技术债：删除 archive/ 旧 PRD 快照（US-014）、docs/archive/ 历史审查（US-015）、僵尸 agent 规格（US-016）、脏文件（US-017）、孤儿数据表（US-019）
- **G5** 文档一致性：README 数字对齐（US-020）、agent_topology 补齐（US-021）、新增 CI 校验脚本（US-022）

---

## 🛑 核心约束（Hard Constraint）

**零回归**：用户明确硬需求 — 所有修复不得破坏原有写作能力，只能正向优化。

- 每个 US 执行前跑 `pytest --no-cov` 记录 baseline
- 修改后再跑对比，无新增失败才算 passes=true
- 若某测试因预期行为变更而调整，必须在 `ralph/prd.json` 的 notes 字段明示
- 涉及写作主链路（context/writer/review/polish）必须手动跑一次 `/ink-write` 验证不崩

详见 [progress.txt](../progress.txt)。

---

## User Stories 概览

| 优先级 | 来源 | US | 标题 | 复杂度 |
|:---:|:---:|:---|------|:---:|
| 1-3 | FIX-01 | US-001/002/003 | 依赖声明 + pyproject + CI 冒烟 | S+S+S |
| 4 | FIX-10 | US-004 | pytest cov-fail-under 降到 30 | S |
| 5 | FIX-04 前置 | US-005 | Step 3.5 Harness Gate 改读 index.db | S |
| 6 | FIX-08 | US-006 | Retriever 3 文件单例化 | S |
| 7 | FIX-09 | US-007 | API Key 护栏（2 脚本） | S |
| 8 | FIX-05 | US-008 | Style RAG 自动构建 + SQLite fallback | M |
| 9-10 | FIX-06 | US-009/010 | 创意指纹 schema + init 消费 | S+M |
| 11 | FIX-07 | US-011 | ink-resolve SQL 单接口 | M |
| 12-13 | FIX-14 | US-012/013 | LLM + 章级 timeout | S+S |
| 14-17 | FIX-12 | US-014~017 | archive/ + docs/archive/ + 僵尸 agent + 脏文件 | S×4 |
| 18 | FIX-13 | US-018 | api_client print → logger | S |
| 19 | FIX-12 | US-019 | 孤儿表 protagonist_knowledge | M |
| 20-22 | FIX-15 | US-020/021/022 | README 对齐 + topology 补齐 + verify_docs.py | S+M+M |
| **23** | **FIX-02B** | **US-023** | **PipelineManager 诚实降级** | **S** |
| **24** | **FIX-03A** | **US-024** | **StateManager flush 改 SQL-first** | **M** |
| **25** | **FIX-03A** | **US-025** | **扫描所有直写 state.json 旁门** | **M** |

**合计**：25 US，预计总工期 ~14-18 天（Ralph 并不是线性时间，很多 US 是小时级）。

详细 acceptance criteria 见 [`ralph/prd.json`](../ralph/prd.json)。

---

## Non-Goals（本轮不做）

- **FIX-11 双 Python 包合并**：XL 重构 5-10d，需架构决策，单独立项
- **FIX-16 真实 100 章压测**：需显著 token 预算，单独立项
- **FIX-17 AutoNovel 反向传播**：XL 新模块，下轮处理（见 memory project_ink_writer_pending_fixes.md）
- **FIX-18 Novelcrafter Progressions 追踪**：L 新模块，下轮处理
- **FIX-04 完整 Phase A/B/C 实施**：本 PRD 仅含前置 US-005（改 Harness 读源）；runner 主体在下轮按 [设计稿](design-fix-04-step3-gate-orchestrator.md) 分阶段做
- **API 限流 / 成本监控**：未在 v5 审计范围
- **新功能开发**：本轮纯修复 + 优化，不新增用户可见功能（除 FIX-02B 的警告）

---

## Technical Considerations

- **FIX-03A 的风险面**：`state_manager.py:413-421` 的顺序反转是数据层的根本变更。US-024 必须先于 US-025；若 US-024 fails 则停下来人工介入，不要继续 US-025 扩散风险
- **US-023 是文字/警告改动**：不影响运行时行为，仅对用户透明化风险
- **US-014~017 的清理**：执行前 git status 确认无未 commit 脏文件；rm 后 pytest 再跑验证无代码引用
- **US-009/010 schema 升级**：schema_version 从 9 → 10；已有项目需能平滑迁移（pytest 测试覆盖）

---

## Success Metrics

- **M1** 25 US 全部 passes=true；Ralph 进度 log 有每个 US 的量化 notes
- **M2** 最终 `pytest --no-cov` 无新增失败（对比本 PRD 开始前 baseline）
- **M3** `/ink-write` 手动跑一次不崩、产出章节字数达标
- **M4** `ls archive/ docs/archive/` 只剩本次归档（清理生效）
- **M5** `python3 -c 'import ink_writer.editor_wisdom, ink_writer.style_rag, ...'` 在干净 venv 成功（依赖声明生效）
- **M6** 健康度总评从 54 回升到 ≥ 70（按 v5 报告各维度复评）

---

## Execution

```bash
cd /Users/cipher/AI/ink/ink-writer
./ralph/ralph.sh
```

Ralph 会按 priority 顺序逐 US 执行。每 US 完成后在 `progress.txt` 追加执行记录 + 量化 notes。

---

## Open Questions

本 PRD 执行前所有 Open Questions 已 Closed：

| # | Question | Decision |
|---|----------|----------|
| 1 | FIX-02 并发方案 | ✅ 方案 B 诚实降级（US-023） |
| 2 | FIX-03 Memory v13 方向 | ✅ 方案 A SQL-first（US-024+025） |
| 3 | FIX-04 设计稿审批 | ✅ 已批准，Phase A 在本 PRD 仅含前置 US-005 |
| 4 | FIX-17/18 何时做 | ✅ 下轮 PRD（已记入 memory） |
| 5 | 零回归原则 | ✅ 每个 US AC 包含全量回归；progress.txt 顶部写明 |
| 6 | 工作流 | ✅ 严格 /prd → /ralph → 执行（已记入 memory） |

---

**批准后直接启动 Ralph**。
