# M2 启动 Checklist & Brainstorm 准备

**Status**: 待 M1 完成后启动
**M2 目标**: 数据资产 — 段落级范文召回可用 + ≥ 100 active cases
**预计周期**: 1 周（≈ 12-15 user stories）
**Origin spec**: `docs/superpowers/specs/2026-04-23-case-library-driven-quality-overhaul-design.md` §6 + §9 M2

> ⚠️ **本文件用途**：M1 在 ralph 后台跑期间预先准备的 brainstorm 输入材料，让 M2 启动时无需从零思考。**当 M1 全部 ✅ 之后**，按"M1 收尾仪式" → "M2 brainstorm 启动" 顺序执行。

---

## Part A — M1 收尾仪式（先做完这一段才能开 M2）

### A.1 验收 6 条全过

```bash
# (1) 全量测试 + 覆盖率门禁
pytest -q
# 期望：3700+ passed / 0 failed / coverage >= 70

# (2) Qdrant 服务可用
scripts/qdrant/start.sh
curl -s http://127.0.0.1:6333/readyz
# 期望：HTTP 200

# (3) reference_corpus 修复幂等（已在 US-001 跑过，复跑确认）
python scripts/maintenance/fix_reference_corpus_symlinks.py
# 期望：fixed=0 skipped=1487 missing_source=0

# (4) preflight 全过
python -m ink_writer.preflight.cli --no-require-embedding-key --no-require-rerank-key
# 期望：all_passed=True

# (5) zero-case 已在库
python scripts/case_library/init_zero_case.py
# 期望：already_exists（首次跑过后）

# (6) preflight 已写入 SKILL.md Step 0
grep -n "ink_writer.preflight.cli" ink-writer/skills/ink-write/SKILL.md
# 期望：>= 2 行（bash + ps1）
```

### A.2 打 tag + 更新 ROADMAP

```bash
git tag -a m1-foundation -m "M1 complete: case_library + qdrant + preflight + symlink fix"
git push --tags  # 仅在用户授权后

# 编辑 docs/superpowers/M-ROADMAP.md：
#   M1 行：🟢 进行中 → ✅ 完成
#   完成日期列：填入实际日期
```

### A.3 合并到 master（先确认）

> ralph 在分支 `ralph/m1-case-library-foundation` 上 commit；合 master 是用户决策，不是 AI 自动行为。**询问用户**：
> - a) 立即 fast-forward merge 到 master + push
> - b) 用 PR 流程
> - c) 暂不合并，留在分支上方便回滚

---

## Part B — M2 范围摘要（来自 spec §6 + §9 M2）

### B.1 spec §9 M2 任务清单

```
- [ ] scripts/corpus_chunking/ 切片管线
- [ ] 30 本范文切片产出（≈ 2700 chunks）入 Qdrant
- [ ] ink corpus ingest/watch/rebuild CLI
- [ ] 288 条 editor-wisdom rules → 病例转换（07_to_cases）→ pending cases
- [ ] 用户审批批量将合理 cases 置 active
- [ ] 起点 top 200 简介库（爬虫一次）

交付物：能召回到段落级范文；病例库有初始百量级 active cases。
```

### B.2 各模块的 spec §6 详细设计映射

| 模块 | spec 章节 | M1 已有依赖 |
|---|---|---|
| scene_segmenter (LLM 识别场景边界) | §6.1 | — |
| chunk_tagger (LLM 打标 + quality_score) | §6.1 | — |
| chunk_indexer (向量化入 Qdrant) | §6.1 | M1 US-012 `CORPUS_CHUNKS_SPEC` |
| chunk schema 落档 | §6.1 | — |
| ink corpus CLI | §6.4 | — |
| user_corpus 接口 | §6.4 | M1 US-007 `ingest_case`（自动产 pending case）|
| editor-wisdom rules → cases 转换器 | spec §3.7 / §9 M2 | M1 US-005 `CaseStore`、US-007 `ingest_case` |
| 起点 top 200 简介库 | spec §3.4 a) (genre-novelty 用) | — |

### B.3 M2 **不做**的事（明确边界）

- ❌ 不做召回路由改造（`ink_writer/retrieval/router.py` 加 case_aware/genre_filtered 等改造，留 M3）
- ❌ 不做病例反向召回的实际接线（`case_retriever.py` 留 M3）
- ❌ 不做 writer 侧注入修改（`writer_injection.py` 留 M3）
- ❌ 不做 P0 上游策划层（M4）
- ❌ 不做 dashboard / 自进化 Layer 4-5（M5）
- ❌ 不退役 FAISS（双写期保持，M3 dry-run 后再决定）

---

## Part C — M2 brainstorm 关键问题（≈ 12 题）

> 这些是我会在 brainstorm 阶段问用户的问题。预先想清楚答案能让 M2 启动当天就直接进入 plan 阶段。

### C.1 切片粒度策略

**Q1**：scene_segmenter 用什么模型？
- a) Haiku 4.5（便宜，~$0.25/1M tokens 输入，估全量 < $10）⭐
- b) Sonnet 4.6（更准但贵 5×）
- c) 混合：先 Haiku 切，质量 < 0.7 时 Sonnet 复切

**Q2**：每 chunk 的字数范围？
- a) 200-800 字（spec 默认）⭐
- b) 100-500 字（更细，chunks 数量翻倍 ≈ 5400）
- c) 300-1500 字（更粗，避免割裂感）

### C.2 切片处理顺序

**Q3**：30 本范文一次切完，还是分批？
- a) 一次全切（节省切换成本，1-2 小时）⭐
- b) 先切 5-10 本（玄幻/都市优先，验证质量后再扩）
- c) 按题材分批（一个题材一批）

### C.3 chunk_tagger 标签 schema

**Q4**：scene_type 取值集合用 spec 默认还是扩展？
- a) spec §6.1 默认 8 种：开篇/打脸/装逼/情感升华/反转/战斗/危机/钩子结尾 ⭐
- b) 扩展到 12-15 种（加：重逢/告别/初遇/突破/失败/转折/世界观展示等）
- c) 让 LLM 自由生成，事后归并

**Q5**：quality_score 怎么打？
- a) LLM 主观 0-1（Sonnet 给）
- b) 多维度加权：tension（0.3）+ originality（0.3）+ language_density（0.2）+ readability（0.2）⭐
- c) 双轨：LLM 主观 + 客观维度，取均值

### C.4 题材标签建模

**Q6**：30 本范文的 genre 标签怎么定？
- a) 人工先标一份 ground truth（半天工作），LLM 校对 ⭐
- b) 全 LLM 自动推断（可能跨题材误判）
- c) 看 `benchmark/reference_corpus/<book>/manifest.json` 现有 genre 字段直接复用

> 提示：之前看 manifest 已有 `genre` 字段（如诡秘之主标"异世大陆"），可以直接复用，但要补 ink-writer/genres/ 的 10 个标准题材映射

### C.5 editor-wisdom → cases 转换策略

**Q7**：288 条规则一对一转 case，还是合并？
- a) 一对一（288 个 pending case，量大但忠实）⭐
- b) 按主题域合并（10 个主题 → ~50-80 case，更聚焦）
- c) 只转高频规则（rule.confidence > 0.8 的，估 ~150）

**Q8**：转换后默认状态？
- a) 全 pending 等用户审批 ⭐（保守，但需要人工 review 288 条）
- b) 全 active 直接生效（激进）
- c) 高 severity (P0/P1) → active；P2/P3 → pending

**Q9**：rule 的 applies_to → case scope.chapter 怎么映射？
- a) opening_only / golden_three / combat / climax / high_point / all_chapters → 同名映射 ⭐
- b) 全部映射成 ["all"]（M3 dry-run 时再细化）
- c) 让用户在 brainstorm 时给规则

### C.6 起点 top 200 简介库

**Q10**：怎么获取？
- a) 自己写爬虫（合规风险低，简介本是公开数据，但要写 1 天）
- b) 用 7zip 现成的起点公开数据集（如有）
- c) 跳过本期，等 M4 用到 genre-novelty 时再做 ⭐（M2 是数据资产，M4 才用）

> 推荐 c：起点 top 200 简介是 M4 `genre-novelty-checker` 的依赖，M2 不真用到。本期把这个 task 移到 M4 一起做更聚焦。

### C.7 API 成本与时长预算

**Q11**：单次切片成本可接受范围？
- a) < $30（spec 估值，用 Haiku）⭐
- b) < $80（混合 Haiku + Sonnet 高质 chunk）
- c) 不设限（全 Sonnet，估 ~$200）

### C.8 M1 → M2 的衔接验证

**Q12**：开 M2 前是否需要补一份 M1 → M2 联调测试？
- a) 不补，M1 接口已稳，M2 直接调即可 ⭐
- b) 补一份 `tests/integration/test_m1_to_m2_handoff.py`：跑 ingest_case → list → load 端到端
- c) 跑一份手动 smoke：`ink case create --domain writing_quality --layer downstream ...` + `ink case list` 看是否符合预期

> 推荐 a：M1 端到端测试 (US-017 `test_m1_e2e.py`) 已经验过 case CRUD 链路；M2 直接信任。

---

## Part D — M2 预期 user story 草稿（≈ 13 个）

> 这只是草拟，brainstorm 后会精修。每个 US 应符合 ralph 单 iteration 可完成的尺寸（< 1 个上下文）。

| US | 标题 | 关键依赖 |
|---|---|---|
| US-001 | scripts/corpus_chunking/ 包骨架 + scene 边界识别原语 | M1 |
| US-002 | scene_segmenter（LLM 识别 + 落 chunks_raw.jsonl） | US-001 |
| US-003 | chunk_tagger（LLM 打标 + quality_score） | US-002 |
| US-004 | chunk_indexer（向量化 + 入 Qdrant CORPUS_CHUNKS_SPEC） | US-003 + M1 US-012 |
| US-005 | `ink corpus ingest --dir <path>` 单次摄入 | US-001~004 |
| US-006 | `ink corpus rebuild` 全量重建 | US-005 |
| US-007 | `ink corpus watch --dir <path>` 监听增量 | US-005 |
| US-008 | 30 本范文切片实跑 + 入库验证（≈ 2700 chunks） | US-001~006 |
| US-009 | editor-wisdom rules.json → cases 转换器（07_to_cases） | M1 US-007 |
| US-010 | 288 条 rules 实跑转换 → ≥ 100 pending cases | US-009 |
| US-011 | `ink case approve --batch <file>` 批量审批工具 | M1 US-008 |
| US-012 | user_corpus 目录结构 + `_meta.yaml` schema | US-005 |
| US-013 | M2 端到端集成测试 + tag `m2-data-assets` | 全部 |

**预估**：13 US × ~22 分钟（参考 M1 节奏）≈ 5 小时

---

## Part E — M2 风险与护栏

| # | 风险 | 缓解 |
|---|---|---|
| 1 | LLM 切片误切（场景边界判断错） | quality_score < 0.6 进人工复审队列；US-008 实跑后抽样 50 chunks 人工核对 |
| 2 | 30 本切片成本超预算 | Q11 选 a 全 Haiku；US-002 先单本试切估真实成本再 scale |
| 3 | chunk 重复率高（同一情节多本反复） | spec §6.6 护栏 3：相似度 > 0.95 合并；US-004 入库前去重 |
| 4 | 288 条 rules → cases 转换质量差（机翻味浓） | Q8 选 a 全 pending，让用户审批保留质控 |
| 5 | Qdrant collection 字段类型与 chunk_tagger 输出不匹配 | M1 US-012 已冻结字段 schema；M2 chunk_tagger 必须输出对齐 |
| 6 | user_corpus 用户喂垃圾数据污染索引 | spec §6.6 护栏 5：source_type=user 权重略低；本期实现，下期 M3 调权 |
| 7 | M2 切片期间 Qdrant 卡死 / 容量不够 | Qdrant 4096 维 × 5000 chunks ≈ 80 MB，单机 docker 远够；提前监控 `du -sh scripts/qdrant/storage/` |

---

## Part F — M2 启动命令清单（M1 完成后照执行）

```
# 步骤 1：在新会话或本会话里，跟我说：
"M1 跑完了，按 docs/superpowers/M2-PREPARATION-NOTES.md 推进 M2"

# 我会自动：
1. cat docs/superpowers/M-ROADMAP.md 确认进度
2. 跑 Part A 的 6 条验收命令
3. 询问 Part A.3 的合并策略
4. 标记 M-ROADMAP M1 ✅ + 打 tag
5. 进入 brainstorm skill，逐题问 Part C 的 12 个问题
6. 写 docs/superpowers/specs/<日期>-m2-data-assets-design.md（细化 §6 + §9 M2）
7. 写 docs/superpowers/plans/<日期>-m2-data-assets.md（13 US TDD 计划）
8. /prd → tasks/prd-m2-data-assets.md
9. /ralph → prd.json + branch ralph/m2-data-assets
10. bash scripts/ralph/ralph.sh --tool claude 13（后台启动）
```

---

## Part G — 不能在 brainstorm 之前预设的事

**故意不在本文件预设、留给 brainstorm 决策**：

1. **chunk_tagger 用什么 prompt 模板**：留给 brainstorm 与用户共同设计；不同模板对 quality_score 影响巨大
2. **批量审批 UI（US-011）的具体形态**：CLI 交互式（`ink case approve --interactive`）vs 一次性 yaml 文件 review vs Web UI；这是用户偏好，不预设
3. **30 本范文中是否包含某些应排除的**：例如政治敏感、版权敏感的；用户决定
4. **chunk 是否做"角色识别"**：spec §6.1 的 `character_count` 字段需要 NER 或 LLM 估算，工程量不小；Q4/Q5 之外的隐藏决策
5. **是否同步把现有 `data/style_rag/` 的 chunks 也迁到 Qdrant `corpus_chunks` 里**（避免双索引）—— 取决于 style_rag 当前内容质量，brainstorm 时单独问

---

## 备注：本文件不入 git？

> 本文件创建时 ralph 还在跑 M1（在 `ralph/m1-case-library-foundation` 分支），所以**本文件以 untracked 形态留在工作区**。
>
> M1 完成、合并到 master 后，**人类决策**：
> - 把本文件 commit 到 master 作为永久 brainstorm 准备物（推荐）
> - 或在 M2 brainstorm 开始时把内容并入正式 spec 后删除本文件

现在（M1 进行中）暂不 commit；待用户在 M2 启动当天指示。
