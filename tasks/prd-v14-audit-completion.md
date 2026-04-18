# PRD: v14 审计完结 + 架构借鉴（Step 3）

## 来源与定位

Step 2（tasks/prd-v13-step2-fixes.md）已 merge 到 master（commit 42c7203），
完成 25 US。本 PRD 是 **Step 3** — 清理 Step 2 排除的 6 项架构/借鉴工作。

**执行链条**：
```
本 PRD (tasks/prd-v14-audit-completion.md)
    ↓
ralph/prd.json (30 US, 机器可执行)
    ↓
./ralph/ralph.sh (自动执行)
```

---

## Goals

- **G1** 补齐 v5 审计 Critical 级缺口：tests/editor_wisdom 10 failures、FIX-04 完整 Phase A/B/C、US-025 收尾
- **G2** 兑现 US-012 三条借鉴设计：FIX-17 AutoNovel 反向传播、FIX-18 Novelcrafter Progressions 追踪
- **G3** 完成 v13 最大架构债：FIX-11 双 Python 包合并
- **G4** 将测试覆盖率门禁拉高：30 → 50 → 70 阶梯

---

## 🛑 核心约束

**零回归**（Step 2 沿用）：每个 US 执行前后跑 `pytest --no-cov` 对比 baseline。
Step 2 完成时 baseline = **2071 passed + 1 skipped**。

**FIX-11 人工决策点**：双包合并策略在 P6 首个 US 需输出设计决策稿，等用户批准后再开始迁移。Ralph 自动跑到此 US 会暂停。

---

## Phase 组织与 US 概览

### Phase 1（Critical）：tests/editor_wisdom 修复 — unblock CI

| US | 标题 | 复杂度 |
|---|------|:---:|
| US-001 | 诊断 tests/editor_wisdom 10 个 failures（分类报告） | S |
| US-002 | 修复 pytest.ini 加入 tests/editor_wisdom；修 transient 失败 | M |
| US-003 | 修 deep 失败（mock 契约不对齐等） | M |

### Phase 2（Critical）：FIX-04 Step3 Gate Orchestrator 完整实施

基于 `tasks/design-fix-04-step3-gate-orchestrator.md`（已批准）。

| US | 标题 | 复杂度 |
|---|------|:---:|
| US-004 | `index_manager` 新增 `write_review_metrics` / `read_review_metrics` API | S |
| US-005 | 新建 `ink_writer/checker_pipeline/step3_runner.py` 骨架 + CheckerRunner 实例化 | M |
| US-006 | 5 gate 接入 step3_runner（hook_retry / emotion / anti_detection / voice / plotline） | L |
| US-007 | step3_runner CLI 入口 + exit codes（0/1/2） | S |
| US-008 | `INK_STEP3_RUNNER_MODE` env 开关（off/shadow/enforce）+ shadow 模式实现 | M |
| US-009 | `ink-write` SKILL.md Step 3 集成 runner（调用 bash） | M |
| US-010 | Phase B：默认切 enforce + harness gate 改读 review_metrics | M |
| US-011 | Phase C：清理 SKILL.md Step 3 逐 checker 描述 + legacy JSON 路径 | S |

### Phase 3（Major）：US-025 收尾

| US | 标题 | 复杂度 |
|---|------|:---:|
| US-012 | 重构 `archive_manager.save_state` 走 StateManager API | M |
| US-013 | 重构 `update_state.py` 走 StateManager API | M |

### Phase 4（Major）：FIX-17 AutoNovel 反向传播

| US | 标题 | 复杂度 |
|---|------|:---:|
| US-014 | 设计 `propagation_debt.json` schema + `ink_writer/propagation/` 模块骨架 | M |
| US-015 | 实现 canon-drift-detector（扫描下游 review_metrics + chapter_meta 检测矛盾冒泡） | L |
| US-016 | 集成到 `ink-macro-review`：每 50 章触发 propagation 清算 | M |
| US-017 | `ink-plan` 消费 `propagation_debt.json`：规划下卷时优先消化历史债 | M |
| US-018 | 端到端集成测试（mock 30 章带人工矛盾，验证 propagation 能捕获） | M |

### Phase 5（Major）：FIX-18 Novelcrafter Progressions

| US | 标题 | 复杂度 |
|---|------|:---:|
| US-019 | 新增 `character_progressions` 表 + IndexManager 读写方法 | S |
| US-020 | data-agent 产出 `progression_events`（进展切片 JSON） | M |
| US-021 | context-agent 3-layer pack 注入"本章之前的角色演进摘要" | M |
| US-022 | OOC checker 消费 progression：跨章立场变化审计 | M |
| US-023 | 端到端测试（mock 80 章配角，验证立场渐变可追溯） | M |

### Phase 6（Major, **人工决策点**）：FIX-11 双 Python 包合并

| US | 标题 | 复杂度 |
|---|------|:---:|
| US-024 | **设计决策稿** `tasks/design-fix-11-python-pkg-merge.md`（合并策略：方向/顺序/回退预案）→ **等用户批准** | L |
| US-025 | 按批准方案执行 Migration script（批量 imports 调整 + pythonpath 更新） | L |
| US-026 | 批量迁移 17 个 `ink_writer/` 模块到统一位置（或 data_modules 的反向） | XL |
| US-027 | 清理旧目录 + CLAUDE.md 更新 + 全量回归 | M |

### Phase 7（Minor）：覆盖率阶梯

| US | 标题 | 复杂度 |
|---|------|:---:|
| US-028 | pytest.ini `--cov-fail-under=30 → 50`（补 state_manager / extract_chapter_context / step3_runner 集成测试） | L |
| US-029 | pytest.ini `--cov-fail-under=50 → 70`（补剩余低覆盖模块） | L |

---

## Non-Goals

- **FIX-16 100 章真实压测** — 需要换模型（大 token 预算），由用户在另一会话处理
- **UI Dashboard 增强** — 非本轮范围
- **新题材 template 扩充** — 非本轮范围
- **国际化 / 多语言** — 非本轮范围

---

## Technical Considerations

- **P2 FIX-04 依赖**：P1 tests/editor_wisdom 先修复才能跑集成测试
- **P4 FIX-17 依赖**：需要 P2 review_metrics 表稳定（检测依据）
- **P5 FIX-18 依赖**：可与 P4 并行（互不干扰），但数据层 schema 变更需错开 US-019
- **P6 FIX-11 风险**：XL 重构影响 37+ 模块 + 多处 sys.path。**必须人工批准设计稿**后才执行
- **P7 阶梯**：必须最后做（依赖所有前置模块完成补测试）

---

## Success Metrics

- **M1** 30 US 全部 passes=true
- **M2** 最终 `pytest --no-cov` 无新增失败（baseline 2071 → 目标 ≥2100）
- **M3** tests/editor_wisdom 纳入 testpaths，0 failures / 0 errors
- **M4** `/ink-write` 手动跑一次：step3_runner 在 enforce 模式下正常跑完 + review_metrics 表有完整记录
- **M5** `ink_writer/propagation/` + `ink_writer/progression/` 两新模块有完整测试
- **M6** 双包统一后：`import ink_writer.X` 与 `import data_modules.X` 无歧义
- **M7** 覆盖率门禁 70% 维持 CI 稳定

---

## Execution

```bash
cd /Users/cipher/AI/ink/ink-writer
./ralph/ralph.sh
```

Ralph 按 priority 1→29 顺序执行。US-024（FIX-11 设计稿）完成时会暂停等待用户批准。

---

## Open Questions（待执行前确认）

1. **FIX-11 合并方向默认假设**：合并到 `ink_writer/`（新包），逐步弃用 `ink-writer/scripts/data_modules/`。若用户倾向另一方向（如合到 `data_modules/`），请在 US-024 批准时说明。
2. **tests/editor_wisdom 具体 failure 类型**：诊断产物（US-001）会决定后续修复工作量；若 >20 failures 则拆出 P0'独立 PRD。
3. **FIX-17 propagation 触发频率**：默认每 50 章触发清算，可配置（env `INK_PROPAGATION_INTERVAL`）。
4. **FIX-18 Progressions 存储粒度**：默认每章每维度一条记录，可能产生大量行；下一轮可按需切分归档。
5. **Phase 6/7 是否可拆出单独 Ralph round**：如用户中途想停，可在 P5 完成后切分。

---

## Checklist（PRD 生成后自检）

- [x] 7 个候选全部纳入（Q1 except E）
- [x] 按 v5 严重度组织（Q3-D）：Critical → Major → Minor
- [x] tests/editor_wisdom 纳入（Q4-A）
- [x] FIX-16 明确排除（用户会换模型单独做）
- [x] 人工决策点（US-024 FIX-11）明示
- [x] 零回归约束保留
- [x] 30 个 US 可执行
