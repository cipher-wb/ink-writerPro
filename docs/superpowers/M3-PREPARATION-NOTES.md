# M3 启动 Checklist & Brainstorm 准备

**Status**: 待 M2 收尾后启动
**M3 目标**: P1 下游闭环 — 写章合规率 + 阻断重写 + 2 个新 checker（**30 → 50 分质量拐点**）
**预计周期**: 1 周（≈ 13-15 user stories）
**Origin spec**: `docs/superpowers/specs/2026-04-23-case-library-driven-quality-overhaul-design.md` §5 + §9 M3

> ⚠️ **本文件用途**：M2 ingest 后台跑期间预先准备的 M3 brainstorm 输入，让 M3 启动时无需从零思考。**当 M2 全部 ✅ 之后**，按"M2 收尾仪式" → "M3 brainstorm 启动" 顺序执行。

---

## Part A — M2 收尾仪式（先做完才能开 M3）

### A.1 验收 6 条全过

```bash
# (1) 全量测试 + 覆盖率门禁
pytest -q
# 期望: ≥ 3700 passed / 0 failed / coverage ≥ 70

# (2) Qdrant 服务可用
curl -s http://127.0.0.1:6333/readyz
# 期望: HTTP 200

# (3) corpus_chunks 入库 ≥ 2500
curl -s http://127.0.0.1:6333/collections/corpus_chunks | jq .result.points_count
# 期望: >= 2500

# (4) case 总数 ≥ 400
ls data/case_library/cases/ | wc -l
# 期望: ≥ 400 (实际 403 = 402 业务 + zero-case)

# (5) active cases ≥ 200
python -m ink_writer.case_library.cli status active | wc -l
# 期望: ≈ 237 (236 hard + zero-case)

# (6) pending cases ≈ 166
python -m ink_writer.case_library.cli status pending | wc -l
# 期望: ≈ 166 (147 soft + 19 info)
```

### A.2 打 tag + 更新 ROADMAP + merge + push

```bash
git tag -a m2-data-assets -m "M2 complete: corpus chunking + cases conversion"
# 编辑 docs/superpowers/M-ROADMAP.md：M2 行 🟢 → ✅ + 完成日期
git checkout master
git merge --ff-only ralph/m2-data-assets
git push origin master --tags
```

---

## Part B — M2 实跑产出的关键事实（M3 必读）

### B.1 实际 LLM/Embedding 配置（与原 spec 偏差）

**spec §8 假设**：Qwen3-Embedding-8B (4096 维) + Anthropic Haiku 4.5
**M2 实际**：
- **Embedding**: ZhipuAI `embedding-3` (2048 维) via `https://open.bigmodel.cn/api/paas/v4`
- **LLM**: ZhipuAI `glm-4-flash`（降级链：glm-5.1 RPM 1302 死锁 → glm-4.6 单本 2.5h 太慢 → glm-4-flash 0.54s/call 终选）
- 配置在 `~/.claude/ink-writer/.env` 的 `LLM_BASE_URL/LLM_MODEL/LLM_API_KEY (复用 EMBED_API_KEY)/LLM_MIN_INTERVAL=0.2`
- `CORPUS_CHUNKS_SPEC.vector_size = 2048`（在 `ink_writer/qdrant/payload_schema.py`）

**M3 必须知道**：
- writer-self-check / polish-agent 等 LLM 调用要复用 `scripts/corpus_chunking/llm_client.LLMClient` wrapper（已 anthropic-shaped 接口）
- 如需更高质量：临时切回 glm-4.6（改 `~/.claude/ink-writer/.env` 的 `LLM_MODEL=glm-4.6` 即可，但要注意 RPM 限速）

### B.2 case 库实际状态

- 总数：**403** cases
- active：237 (236 hard + CASE-2026-0000)
- pending：166 (147 soft + 19 info)
- 全部 cases 的 `failure_pattern.observable` 是占位文本（`"待 M3 dry-run 后基于实际触发样本细化（rule_id: EW-XXXX）"`）—— **M3 dry-run 关键工作之一是基于实际触发日志反推 observable**

### B.3 corpus_chunks 实际状态

- 入库目标：≥ 2500（实际产出取决于 ingest 真跑情况；如果时间不够全 30 本，可能只覆盖部分书）
- chunk schema 已稳定：`scene_type / genre / tension_level / character_count / dialogue_ratio / hook_type / borrowable_aspects / quality_score / quality_breakdown`
- payload 索引字段已 freeze：`genre / scene_type / quality_score / source_type / source_book / case_ids`

### B.4 ralph 累积的 codebase patterns（M3 ralph 会自动继承）

`progress.txt` 顶部 Codebase Patterns 段共 ~16 条，含：
- Ruff lint gate 用法
- Audit 红线（cli_entries_utf8_stdio + safe_symlink）
- 跨目录 CLI 三段式 sys.path bootstrap
- M1 已建组件清单
- LLM client wrapper 模板
- Qdrant 单机 docker (OrbStack via daocloud mirror) 启停命令

---

## Part C — M3 brainstorm 关键问题（≈ 14 题）

### C.1 writer-self-check 时机与强度

**Q1**: writer-self-check 在哪个阶段调？
- a) 写完整章后（章末），合规率 < 阈值则**整章重写**（spec 默认）⭐
- b) 段落级流式（每段写完即 check），不合规则即时纠正
- c) 双轨：段落级 soft check + 章末 hard check

**Q2**: rule_compliance 阈值默认多少？
- a) 0.70（spec §5.1 默认；30% chunks 不达标会触发重写）⭐
- b) 0.80（更严格，可能频繁触发重写浪费 LLM 成本）
- c) 0.60（更宽松，质量可能不足）

### C.2 阻断重写的最大轮数与回退

**Q3**: 单章最多重写几次？
- a) **3 次**（spec §5.4 默认）⭐
- b) 2 次（更激进省成本）
- c) 5 次（高质量优先）

**Q4**: 3 次仍不通过怎么办？
- a) 标 `needs_human_review.jsonl`（spec §5.4 默认；不删稿，让作者决定）⭐
- b) 强制最佳一次提交（接受质量妥协）
- c) 抛错让 ink-write 退出，让用户立即看到

### C.3 evidence_chain.json schema 强制度

**Q5**: 没产 evidence_chain.json 算不算交付失败？
- a) **强制必须有**（spec §5 默认；缺则 ink-write 报错）⭐
- b) 缺则警告但不阻断（柔和过渡）
- c) 可选字段，dry-run 期间不强制

### C.4 conflict-skeleton-checker 触发条件

**Q6**: 何时跑 conflict-skeleton-checker？
- a) 每章必跑（spec §5.3 默认）⭐
- b) 仅章末必跑 + 高潮章节必跑
- c) 用户配置触发

**Q7**: 如何判定章节有"显式冲突"？
- a) LLM 主观判断：是否有人物立场对立 / 利益冲突 / 价值观碰撞 ⭐
- b) 客观规则：对话密度 + 情绪起伏 > 阈值
- c) 双轨

### C.5 protagonist-agency-checker（章节级）

**Q8**: 主角"主动决策点"如何判定？
- a) LLM 主观判断（每章必须 ≥ 1 个主角主动决策）⭐
- b) 客观规则：主角作为施动者的句子比例
- c) 双轨

### C.6 现有 checker 阈值升级范围

**Q9**: 哪些现有 checker 升级为"阻断"模式？
- a) **3 个**：reader-pull / sensory-immersion / high-point（spec §5.2 默认）⭐
- b) 5 个：再加 anti-detection / editor-wisdom-checker
- c) 全部 23 个 checker 都加 block_threshold

### C.7 dry-run 模式时长与切换

**Q10**: dry-run 模式跑多久后切真阻断？
- a) **跑 5 章观察**（spec §6.1 默认）⭐
- b) 跑 10 章观察（更稳）
- c) 跑 1 周观察

**Q11**: dry-run 期间产物如何保存？
- a) 每章产 evidence_chain.json + 标注"dry_run=true" ⭐
- b) 单独 logs 目录
- c) 只 stdout 不持久化

### C.8 polish-agent 改造

**Q12**: case_id 驱动重写时，polish-agent 同时处理几个 case？
- a) **一次一个 case**（隔离干扰，但慢） ⭐
- b) 一次 batch 多 cases（快但可能引入交互效应）

### C.9 配置热更新与回滚

**Q13**: `config/checker-thresholds.yaml` 如何应用变更？
- a) **每次 ink-write 启动时读**（修改后下次写章生效，最简）⭐
- b) 每章读一次（实时生效，但 IO 开销）
- c) 加 watch + reload

### C.10 GLM-4-flash 是否够用

**Q14**: writer-self-check / 2 个新 checker 用什么 model？
- a) **glm-4.6**（更高质量；这些 check 不像 ingest 那么大量调用，RPM 不会撞墙）⭐
- b) glm-4-flash（与 ingest 一致；可能质量不够）
- c) 用户充值升 glm-5.1 RPM 配额（需用户操作）

---

## Part D — M3 预期 user story 草拟（≈ 14 个）

| US | 标题 | 关键依赖 |
|---|---|---|
| US-001 | `config/checker-thresholds.yaml` schema + 加载器 | M2 |
| US-002 | `evidence_chain.json` schema + 写入工具 | M1 case_library |
| US-003 | `writer-self-check` agent (rule_compliance 计算) | M1 + M2 |
| US-004 | `conflict-skeleton-checker` agent | M1 cases |
| US-005 | `protagonist-agency-checker` agent (章节级) | M1 cases |
| US-006 | `polish-agent` 改造接收 case_id 驱动重写 | M1 ingest_case |
| US-007 | reader-pull/sensory-immersion/high-point 加 block_threshold | 现有 checker 改造 |
| US-008 | ink-write 流程加"合规→阻断→重写"循环（最多 3 轮）| US-003~007 |
| US-009 | dry-run 模式标志 + evidence_chain `dry_run=true` 字段 | US-002 |
| US-010 | dry-run 跑 5 章观察 + 决策切换报告 | US-008+009 |
| US-011 | `needs_human_review.jsonl` 兜底机制（3 次仍不通过）| US-008 |
| US-012 | reader-pull / sensory / high-point 切真阻断 | US-010 通过后 |
| US-013 | M3 e2e 集成测试（5-7 用例）| 全部 |
| US-014 | M3 验收 + tag `m3-p1-loop` + 更新 M-ROADMAP | US-013 |

**预估**：14 US × ~22 分钟（参考 M1/M2 节奏）≈ **5 小时**

---

## Part E — M3 风险与护栏

| # | 风险 | 缓解 |
|---|---|---|
| 1 | dry-run 5 章不足以暴露所有阻断模式 | 必须用真实 v23 项目跑 dry-run，不是空项目 |
| 2 | rule_compliance 计算依赖 LLM 主观判断（不稳） | 多次 sample 取均值；evidence_chain 留 raw scores 供反查 |
| 3 | 重写 3 轮成本翻倍（章 cost ×4）| 监控总 token 消耗；超预算自动降级到 dry-run |
| 4 | 236 active cases 同时阻断会让重写率 > 80% | dry-run 阶段统计每个 case 的 hit rate；命中率 > 50% 的 case 自动降为 pending |
| 5 | conflict-skeleton-checker 误判（场景型章节如序章被误判无冲突）| 加 scope.chapter 例外（如 prologue 不查冲突）|
| 6 | protagonist-agency-checker 在群像章节误判（多 POV 章节）| 加 scope.character_focus 字段 |
| 7 | evidence_chain.json 占用大量磁盘（每章 ~5KB × 数百章 = MB 级）| 1 年后归档 + 压缩 |

---

## Part F — M3 启动命令清单（M2 完成后照执行）

```
# 步骤 1：在新会话或本会话里说：
"M2 跑完了，按 docs/superpowers/M3-PREPARATION-NOTES.md 推进 M3"

# 我会自动：
1. cat docs/superpowers/M-ROADMAP.md 确认 M2 ✅
2. 跑 Part A 的 6 条验收命令
3. 标记 M-ROADMAP M2 ✅ + 打 tag + merge + push
4. 进入 brainstorming skill，逐题问 Part C 的 14 个问题
5. 写 docs/superpowers/specs/<日期>-m3-p1-loop-design.md
6. 写 docs/superpowers/plans/<日期>-m3-p1-loop.md
7. /prd → tasks/prd-m3-p1-loop.md
8. /ralph → prd.json + branch ralph/m3-p1-loop
9. bash scripts/ralph/ralph.sh --tool claude 14（后台启动）
```

---

## Part G — 故意不预设的事

1. writer-self-check prompt 模板（要 brainstorm 共同设计）
2. conflict-skeleton-checker / protagonist-agency-checker 的 prompt 设计
3. 是否在 M3 中添加性能监控（LLM token 消耗 / 重写率 dashboard）
4. evidence_chain.json 的具体字段（spec §5.5 已有草案但需细化）
5. dry-run 报告的格式（CLI 表格 / HTML / Markdown）

---

## 备注

本文件创建于 M2 ingest 后台运行期间（2026-04-25 凌晨）。
M2 完成后人类决定：
- 把本文件 commit 到 master 作为永久 brainstorm 准备物（推荐）
- 或在 M3 brainstorm 开始时把内容并入正式 spec 后删除本文件
