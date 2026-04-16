# PRD: ink-writer 深度 Review 与极致优化

## Introduction

ink-writer 当前 v12.0.0，已集成 editor-wisdom 编辑智慧 RAG（288 条规则）。本 PRD 目标是对项目进行**端到端深度审查 + 持续优化**，直到三大目标达成：

1. **架构完美**：无逻辑错误、无冗余、模块边界清晰、可维护可扩展
2. **作品质量爆款级**：去 AI 味、强钩子、密爽点、强情绪、连写 300w 字不崩
3. **效率最优**：生成速度、token 成本、并发度均在合理上限

执行方式：本 PRD + 配套实施计划交由 Ralph 自主执行，分阶段交付，每阶段有可量化的验收门禁。

## Goals

- **G1（追读力）**：在标准对照集（起点/番茄爆款 Top 50）上，钩子密度 ≥P75、爽点节奏 ≥P75、情绪曲线相似度 ≥0.8
- **G2（去 AI 味）**：anti-detection-checker 综合分 ≥85，盲测起点编辑识别率 <30%
- **G3（架构）**：模块循环依赖 = 0，重复实现 = 0，dead code <2%，所有 agent/skill 有自动化测试
- **G4（长篇不崩）**：连续生成 300 章（约 75w 字）后：人物 OOC 分 <5、设定矛盾 <3、明暗线漏接 = 0
- **G5（效率）**：单章端到端耗时 ≤当前 70%，单章 token 消耗 ≤当前 80%，支持 N 章并发

## User Stories

> 注：本项目无 UI（dashboard 为只读），故无需 dev-browser 验证。所有验收以 CLI 测试 + 量化指标为准。

---

### Phase 0 — 基线建立（必须先做）

#### US-001: 建立质量基线测量工具
**Description:** 作为优化执行者，我需要一套可重复运行的"质量测量脚本"，作为后续所有优化的对照基线。

**Acceptance Criteria:**
- [ ] `scripts/measure_baseline.py` 一键运行，输出 JSON 报告
- [ ] 指标覆盖：钩子密度、爽点密度、情绪方差、AI 味分、OOC 分、设定一致性、平均章耗时、平均章 token
- [ ] 在 `benchmark/baseline_v12.json` 落地当前基线
- [ ] 抓取/选定 ≥30 本起点番茄爆款样本，建立对照集 `benchmark/reference_corpus/`
- [ ] pytest 通过

#### US-002: 建立架构静态扫描
**Description:** 自动化扫描循环依赖、重复实现、dead code、token 浪费点。

**Acceptance Criteria:**
- [ ] `scripts/audit_architecture.py` 输出 `reports/architecture_audit.md`
- [ ] 检测项：import 循环、agent 间职责重叠、prompt 重复段、未被引用的模块
- [ ] 列出所有 agent/skill 的输入输出契约表
- [ ] pytest 通过

---

### Phase 1 — 追读力三件套（CABDE 中的 C，最高优先级）

#### US-101: 钩子引擎重构
**Description:** 现有钩子靠 prompt 和 reader-pull-checker 后置打分。重构为**前置约束 + 后置校验闭环**：每章生成前从"钩子库"取卡，生成后量化校验未达标自动重写。

**Acceptance Criteria:**
- [ ] 抽取爆款对照集中的钩子模式，建立 `data/hook_patterns.json`（≥200 条带分类）
- [ ] 章节大纲阶段强制声明本章钩子类型 + 兑现锚点
- [ ] reader-pull-checker 输出可执行 fix prompt（不只是评分）
- [ ] 钩子未达标触发 polish-agent 定向重写，最多 2 轮
- [ ] 在对照集上钩子密度从基线提升 ≥30%
- [ ] pytest 通过

#### US-102: 爽点节奏控制器
**Description:** 把 high-point-checker 升级为"主动调度器"：根据章节位置自动决定本章爽点类型/强度/兑现窗口。

**Acceptance Criteria:**
- [ ] 新增 `ink_writer/pacing/high_point_scheduler.py`
- [ ] 输入：当前章号、卷内位置、最近 5 章爽点历史；输出：本章爽点配方
- [ ] 接入 ink-write 写作链，作为大纲细化阶段强约束
- [ ] 连续 50 章测试：爽点密度方差 ≤0.2，无连续 3 章无爽点
- [ ] pytest 通过

#### US-103: 情绪心电图引擎
**Description:** 每章生成"情绪曲线 JSON"（场景级 valence/arousal），与目标曲线对齐，偏差大时触发 polish。

**Acceptance Criteria:**
- [ ] data-agent 提取每章情绪曲线写入 `data/emotion_curves.jsonl`
- [ ] 新增 emotion-curve-checker agent
- [ ] 单章情绪方差 <阈值 → 标记"平淡"，触发 polish 加冲突
- [ ] 与对照集情绪曲线相似度 ≥0.8
- [ ] pytest 通过

---

### Phase 2 — 去 AI 味（CABDE 中的 A）

#### US-201: Style RAG 系统
**Description:** 当前 anti-detection-checker 只查不修。新增"风格库 RAG"，从爆款样本检索相似场景的人写句式作为 polish 参考。

**Acceptance Criteria:**
- [ ] 切片爆款对照集为场景级片段（场景类型 × 情绪 × 句式特征）
- [ ] 用 sentence-transformers 建索引（复用 editor-wisdom 的 retriever）
- [ ] polish-agent 调用：检索 Top-K 相似人写片段，作为 in-context 改写参考
- [ ] anti-detection 综合分基线 +10
- [ ] pytest 通过

#### US-202: 句式多样性硬门禁
**Description:** 把 anti-detection-checker 的统计特征（句长方差、句式重复、连接词频次）做成**写作链硬门禁**，不达标必须重写。

**Acceptance Criteria:**
- [ ] 在 ink-write 流程末尾加 hard gate
- [ ] 阈值可配置 `config/anti_ai_thresholds.yaml`
- [ ] 失败 → 自动 polish 1 轮 → 仍失败则报告并中断
- [ ] 禁用清单（如"第xx日"开头）作为零容忍项
- [ ] pytest 通过

#### US-203: 文化语料注入
**Description:** 建立"成语/俗语/方言/时代词"库，按题材自动注入，避免 AI 通用化表达。

**Acceptance Criteria:**
- [ ] `data/cultural_lexicon/{xianxia,urban,scifi,...}.json`
- [ ] context-agent 按题材附加到创作执行包
- [ ] 每章至少使用 N 个非通用词（按题材配置）
- [ ] pytest 通过

---

### Phase 3 — 长篇不崩（CABDE 中的 B）

#### US-301: 实体记忆图谱重构
**Description:** 当前 state.json + index.db 双存储易漂移。重构为**单一事实源 + 物化视图**架构。

**Acceptance Criteria:**
- [ ] 设计文档 `docs/memory_architecture_v13.md` 评审通过
- [ ] 实体存储统一为 SQLite（含人物/势力/物品/伏笔/设定/时间线）
- [ ] state.json 降级为视图缓存，可随时重建
- [ ] 提供 `ink-migrate` 平滑迁移半写项目
- [ ] 现有审计报告全部通过
- [ ] pytest 通过

#### US-302: 跨章语义检索（替代关键词匹配）
**Description:** 当前 context-agent 用关键词召回历史。升级为语义检索 + 重要性加权。

**Acceptance Criteria:**
- [ ] 章节摘要建向量索引
- [ ] 召回策略：语义 Top-K + 强相关实体强制召回 + 最近 N 章
- [ ] 创作执行包大小 ≤当前 80%（更精准 → 更短）
- [ ] 300 章测试：信息漏接事件 = 0
- [ ] pytest 通过

#### US-303: 伏笔生命周期管理器
**Description:** 伏笔从埋下→提示→兑现全程跟踪，超期未兑现自动告警。

**Acceptance Criteria:**
- [ ] 新增 foreshadow-tracker，每章扫描所有 open 伏笔
- [ ] 超期阈值（按伏笔权重）触发 ink-plan 强制安排兑现
- [ ] dashboard 可视化伏笔热力图
- [ ] 300 章测试：超期未兑现 = 0
- [ ] pytest 通过

#### US-304: 人物语气指纹
**Description:** 每个角色建立"语气指纹"（高频词、句长偏好、口头禅、价值观锚句），写作时强约束 + ooc-checker 增强。

**Acceptance Criteria:**
- [ ] 角色档案新增 `voice_fingerprint` 字段（首次出场后自动学习）
- [ ] 后续章节强制对齐，偏差 >阈值触发 polish
- [ ] 300 章测试：OOC 分 <5
- [ ] pytest 通过

#### US-305: 明暗线追踪器
**Description:** 显式声明每条线（main/sub/dark），每章标注推进了哪条线，长期不推进自动告警。

**Acceptance Criteria:**
- [ ] `state.json` 增加 plotlines schema
- [ ] ink-plan 阶段必须为每章打 plotline tag
- [ ] 单条线断更 >N 章告警
- [ ] 300 章测试：明暗线漏接 = 0
- [ ] pytest 通过

---

### Phase 4 — 架构清理（CABDE 中的 D）

#### US-401: Agent 职责重映射
**Description:** 基于 US-002 审计结果，合并/拆分 agent，消除职责重叠。

**Acceptance Criteria:**
- [ ] 输出 `docs/agent_topology_v13.md`
- [ ] 重叠 agent 合并（如多个 checker 合并为统一 checker pipeline）
- [ ] 每个 agent 单一职责，输入输出 schema 化
- [ ] 全量回归测试通过

#### US-402: 双目录消除
**Description:** `ink-writer/agents/` 和 `agents/ink-writer/` 双目录消除，统一规范。

**Acceptance Criteria:**
- [ ] 单一 agent 根目录
- [ ] CLAUDE.md 更新
- [ ] 所有引用更新
- [ ] pytest 通过

#### US-403: Skill 命令统一
**Description:** ink-writer 与 webnovel-writer 两套 skill 系统去重或明确边界。

**Acceptance Criteria:**
- [ ] 决策文档：合并 / 保留双系统（含理由）
- [ ] 若合并：迁移路径文档化
- [ ] 若保留：明确各自适用场景写入 README

#### US-404: Prompt 模板化与版本化
**Description:** 散落在各 agent 的 prompt 抽取到 `templates/`，版本化管理。

**Acceptance Criteria:**
- [ ] 所有 prompt 在 `templates/prompts/` 集中管理
- [ ] 支持 A/B 测试不同版本
- [ ] 重复 prompt 段落消除
- [ ] pytest 通过

---

### Phase 5 — 效率（CABDE 中的 E）

#### US-501: 章节级并发管线
**Description:** 当前 ink-auto 串行写章。重构为 N 章并发流水线（写章 / 审查 / 修复 / 数据提取异步）。

**Acceptance Criteria:**
- [ ] 支持 `--parallel N` 参数
- [ ] 实体写入加锁防竞争
- [ ] 端到端吞吐量 ≥串行 2.5x（N=4）
- [ ] pytest 通过

#### US-502: Prompt 缓存优化
**Description:** 利用 Anthropic prompt cache，把不变上下文（角色档案、世界观、风格指南）标记为可缓存。

**Acceptance Criteria:**
- [ ] 写作链 system prompt 拆分稳定段 + 易变段
- [ ] cache_control 标注稳定段
- [ ] 实测缓存命中率 ≥70%
- [ ] 单章 token 成本下降 ≥30%
- [ ] pytest 通过

#### US-503: 检查器并行化
**Description:** 当前 review 阶段多个 checker 串行。改为并行 + 早期失败终止。

**Acceptance Criteria:**
- [ ] checker 并发执行
- [ ] 任一硬门禁失败立即触发 polish，无需等其他
- [ ] review 阶段耗时 ≤当前 50%
- [ ] pytest 通过

#### US-504: 增量数据提取
**Description:** data-agent 当前每章全量重抽。改为增量 diff 模式。

**Acceptance Criteria:**
- [ ] 仅提取本章新增/变更
- [ ] 数据提取耗时 ≤当前 40%
- [ ] 全量与增量结果对比一致
- [ ] pytest 通过

---

### Phase 6 — 验证与回归

#### US-601: 300 章压测
**Description:** 用一个测试题材，连写 300 章（不开人工干预），全部指标采集。

**Acceptance Criteria:**
- [ ] `benchmark/300chapter_run/` 完整产物
- [ ] 报告对比 G1-G5 全部目标
- [ ] 任一指标未达标 → 回 Phase 1-5 对应模块迭代
- [ ] 通过后打 v13.0.0 tag

#### US-602: 盲测人工评估
**Description:** 抽取生成章节与起点爆款混合，请 ≥5 名读者盲测打分。

**Acceptance Criteria:**
- [ ] 评分维度：吸引力、AI 味、人物、节奏、情绪
- [ ] 生成章节平均分 ≥对照集 0.95×
- [ ] 报告归档 `reports/blind_test_v13.md`

---

## Functional Requirements

- **FR-1**: 所有优化必须有自动化测试，pytest 全绿才算完成
- **FR-2**: 每个 Phase 结束必须重跑 `scripts/measure_baseline.py`，与上一基线对比，指标退化立即回滚
- **FR-3**: 任何架构改动必须提供 `ink-migrate` 路径，保证已有项目数据不丢
- **FR-4**: 所有新增模块遵循现有 agent/skill 规范，输入输出 schema 化
- **FR-5**: editor-wisdom 288 条规则作为所有写作链的硬门禁，不可绕过
- **FR-6**: 所有 prompt 改动必须 A/B 测试，效果不退化才合并
- **FR-7**: Phase 间允许并行，但 Phase 0 必须最先完成

## Non-Goals

- **不做** Web/移动端 UI（dashboard 维持只读）
- **不做** 多语言（仅中文）
- **不做** 替换底层 LLM 的抽象层（继续 Claude 为主）
- **不做** 商业化分发功能（账号、订阅、付费墙）
- **不做** 对 ralph 框架本身的改造
- **不做** 历史版本（<v12.0.0）兼容

## Technical Considerations

- **依赖**：editor-wisdom retriever、sentence-transformers、SQLite、Anthropic SDK（开启 prompt cache）
- **迁移**：所有 schema 变更走 `ink-migrate`，半写项目零损失
- **并发**：SQLite 写锁需评估，必要时切换 WAL 或换 DuckDB
- **token 成本**：所有 LLM 调用必须经过 prompt cache 评估
- **测试集**：对照集需合规获取（公开样章 / 自爬带标识，避免侵权）

## Success Metrics

| 指标 | 基线（v12） | 目标（v13） |
|---|---|---|
| 钩子密度（每千字） | 待测 | ≥对照集 P75 |
| 爽点密度（每章） | 待测 | ≥对照集 P75 |
| AI 味分（anti-detection） | 待测 | ≥85 |
| OOC 分（300 章后） | 待测 | <5 |
| 设定矛盾（300 章后） | 待测 | <3 |
| 明暗线漏接 | 待测 | 0 |
| 单章端到端耗时 | 待测 | ≤基线 70% |
| 单章 token 成本 | 待测 | ≤基线 80% |
| 4 章并发吞吐 | N/A | ≥串行 2.5x |
| 盲测吸引力分 | N/A | ≥对照集 0.95× |

## Open Questions

- **OQ-1**：对照集爬取的合规边界？建议只用公开样章 + 自购章节，避免全本。
- **OQ-2**：是否引入 DuckDB 替代 SQLite 以支持并发？需在 US-301 评估。
- **OQ-3**：Style RAG 是否需要按作者风格分子库？还是统一池？建议先统一，效果不够再分。
- **OQ-4**：盲测样本招募渠道？是否复用现有起点编辑朋友圈？
- **OQ-5**：US-403（双 skill 系统）保留还是合并？需用户决策。

---

## 实施建议（给 Ralph）

**推荐执行顺序**：

```
Phase 0 (US-001, US-002)   ← 必须最先，建立基线
   ↓
Phase 1 (追读力, P0)
   ↓
Phase 2 (去 AI 味, P1)
   ↓
Phase 3 (长篇不崩, P2)
   ↓
Phase 4 (架构清理, P3) ← 可与 Phase 5 并行
   ↓
Phase 5 (效率, P4)
   ↓
Phase 6 (300 章压测验收)
```

**每个 US 完成判定**：
1. 代码合并 + pytest 全绿
2. 重跑 baseline 对应指标，无退化
3. 在 `progress.txt` 标记完成

**回滚机制**：任一阶段 baseline 退化超 5%，git revert 该 US 全部 commit，重新设计。
