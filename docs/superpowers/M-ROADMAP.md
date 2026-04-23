# 病例库驱动的质量治理 — 5 周 Milestone Roadmap

**Status**: 持续跟踪（M1 进行中）
**Origin spec**: `docs/superpowers/specs/2026-04-23-case-library-driven-quality-overhaul-design.md`
**Goal**: 起点编辑评分 30 → 60-70（6 个月内验证）

---

## 为什么有这份文件

5 周 M1-M5 是一个**有顺序依赖、各自可独立交付**的子里程碑序列。每个里程碑独立写一份 PRD + plan，分批交给 ralph 执行。

> ⚠️ **重要提醒（给未来的 AI 会话）**：
> 这是一个跨多次会话的长期项目。每次新会话开始时，先 cat 这份 ROADMAP，确认当前所在阶段。**M1 完成后必须生成 M2 PRD + plan，否则项目会卡在 M1**。

---

## 进度跟踪

| Milestone | 状态 | PRD | Plan | ralph branch | 完成日期 |
|---|---|---|---|---|---|
| **M1** 基础设施 + Qdrant + symlink 修复 | 🟢 进行中 | `tasks/prd-m1-case-library-foundation.md` | `docs/superpowers/plans/2026-04-23-m1-foundation-and-qdrant-migration.md` | `ralph/m1-case-library-foundation` | — |
| **M2** 数据资产（切片 + 病例种子） | ⚪ 未开始 | TBD | TBD | TBD | — |
| **M3** P1 下游闭环（**质量拐点**）| ⚪ 未开始 | TBD | TBD | TBD | — |
| **M4** P0 上游策划层 | ⚪ 未开始 | TBD | TBD | TBD | — |
| **M5** Dashboard + 自进化 + 用户接口 | ⚪ 未开始 | TBD | TBD | TBD | — |

状态图例：⚪ 未开始 / 🟢 进行中 / ✅ 完成 / 🔴 卡住

---

## 各 Milestone 摘要

### M1：基础设施 + Qdrant 迁移 + symlink 修复（无依赖）
**独立交付价值**：病例库可创建 / 查询、preflight 健康检查可跑、Qdrant 在线、reference_corpus 不再悄悄退化  
**17 user stories**：见 `tasks/prd-m1-case-library-foundation.md`  
**详细 plan**：`docs/superpowers/plans/2026-04-23-m1-foundation-and-qdrant-migration.md`  
**验收**：`pytest -q` 全绿（覆盖率 ≥ 70）+ `python -m ink_writer.preflight.cli` `all_passed=True` + `git tag m1-foundation`

### M2：数据资产（依赖 M1）
**独立交付价值**：段落级范文召回可用、≥ 100 active cases  
**预期 user stories**（待 M1 完成后用 brainstorming + writing-plans 细化）：
- 场景级切片管线（scene_segmenter / chunk_tagger / chunk_indexer）
- 30 本范文切片入 Qdrant `corpus_chunks` collection（≈ 2700 chunks）
- `ink corpus ingest/watch/rebuild` CLI
- 288 条 editor-wisdom rules → 病例转换（`07_to_cases`）→ pending cases
- 批量审批合理 cases 置 active
- 起点 top 200 简介库爬取（季度刷新）
- FAISS → Qdrant 双写期结束 + FAISS 退役

**生成命令**（M1 完成后执行）：
```
1. 在新会话里说："基于 docs/superpowers/specs/2026-04-23-...md §9 M2，brainstorm M2 design 并写到 docs/superpowers/specs/<日期>-m2-data-assets-design.md"
2. 完成后说："基于 M2 spec 写一份 implementation plan 到 docs/superpowers/plans/<日期>-m2-data-assets.md"
3. 完成后说："/prd 把 plan 转成 PRD 到 tasks/prd-m2-data-assets.md"
4. 完成后说："/ralph 把 PRD 转 prd.json，branch ralph/m2-data-assets"
5. 启动后台 ralph
```

### M3：P1 下游闭环（依赖 M1 + M2）
**独立交付价值**：每章新产出附 evidence_chain.json 含合规率，违规阻断重写  
**这是 30 → 50 分的关键节点**  
**预期 user stories**：
- `writer-self-check` agent（写完比对，强制环节）
- `conflict-skeleton-checker` agent（章节级）
- `protagonist-agency-checker` agent（章节级）
- `polish-agent` 改造（接收 case_id 驱动重写）
- `config/checker-thresholds.yaml` 集中管理 + 热更新
- reader-pull / sensory-immersion / high-point 阈值阻断升级
- dry-run 模式跑 5 章观察后切真阻断
- evidence_chain.json schema 落档

### M4：P0 上游策划层（依赖 M1 + M2）
**独立交付价值**：开新书强制走策划期审查（题材 / 金手指 / 起名 / 主角主动性）  
**预期 user stories**：
- 4 个 ink-init checker（genre-novelty / golden-finger-spec / naming-style / protagonist-motive）
- 3 个 ink-plan checker（golden-finger-timing / protagonist-agency-skeleton / chapter-hook-density）
- LLM 高频起名词典（≈ 300 条种子）
- `planning_evidence_chain.json` schema
- ink-init / ink-plan SKILL.md 增加 Step 99
- 上游 cases 批量编写

### M5：Dashboard + 自进化 + 用户接口（依赖前 4）
**独立交付价值**：完整闭环 + 周报自动产出 + history-travel 用户案例  
**预期 user stories**：
- `ink dashboard` 扩展（病例复发率 / 修复速度 / 编辑分趋势 / checker 准确率）
- Layer 4 复发追踪（resolved → regressed 升级 severity）
- Layer 5 元规则浮现（5 个相似 case 自动建议合并）
- `data/case_library/user_corpus/` + history-travel 样例
- A/B 通道（可选 50% 章节生效）
- 文档：作者使用手册 + 编辑反馈录入手册

---

## 标准的 milestone 推进流程（每次推进新 M 都执行一遍）

```
1. cat docs/superpowers/M-ROADMAP.md     ← 当前会话第一件事
2. 找到下一个未开始（⚪）的 M
3. brainstorm M 的设计 → 写 spec 到 docs/superpowers/specs/
4. writing-plans 写实现 plan → docs/superpowers/plans/
5. /prd 把 plan 转 markdown PRD → tasks/prd-m<N>-<feature>.md
6. /ralph 把 PRD 转 prd.json，branch ralph/m<N>-<feature>
7. 启动后台 ralph：bash scripts/ralph/ralph.sh --tool claude
8. ralph 全部 passes:true 后：
   - git tag m<N>-<feature>
   - 更新本文件：⚪ → ✅，填完成日期
   - 推进到下一个 M
```

---

## 失败模式与护栏

- **失败模式 1**：M1 完成后会话结束，新会话不知道有 M2-M5
  - **护栏**：本文件 + 项目 memory + progress.txt 末尾 "Next milestone" 提示三重保险
- **失败模式 2**：某个 M 期间发现需求变化，不再适合原 spec
  - **护栏**：可以局部修订 spec（commit 到 git），更新本文件 status，但不能跳过 M2 直接做 M3（依赖关系硬）
- **失败模式 3**：ralph 卡在某个 US 反复失败
  - **护栏**：手动 review 该 US 的 acceptanceCriteria 是否过细、过严或矛盾；调整后继续
- **失败模式 4**：M3 dry-run 结果显示阈值需要调整
  - **护栏**：spec §6.1 已声明 M3 必须强制 dry-run 1 周再切真阻断；如需大改则插入 "M3.5 阈值调优" milestone

---

## 关键人物 / 关键事实（给未来的 AI 会话）

- **作者**：cipher-wb（insectwb@gmail.com）
- **当前项目**：ink-writer 长篇网文写作工具（v23.0.0 baseline）
- **核心痛点**：编辑评分 30/100，参考库已有但"靠感觉判断生不生效"
- **方案哲学**：病例（case）为产线唯一真相源；编辑差评 → case → checker → 阻断重写 → 通过 → 复发监测
- **跨平台**：必须支持 macOS + Windows 11；遵守 `CLAUDE.md` Windows 兼容守则
- **现有 ralph 系统**：每个 user story 跑一个 fresh AI 实例（context 隔离），靠 git + progress.txt + prd.json 三件持久记忆
