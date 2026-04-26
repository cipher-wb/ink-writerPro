# US-500 · Context Full-Text Carryover（前章正文全文注入）

> **状态**：Proposal / Pending Review
> **提出日期**：2026-04-19
> **影响模块**：`ink_writer/core/context` · `writer-agent` · `continuity-checker`
> **优先级**：High（解决线上实测问题）

---

## 1. 背景 · Observed Problem

### 1.1 实测 Bug

`/ink-auto 3` 跑完第 1-2 章后，人工阅读发现一处**台词承接冲突**：

- **第 1 章末**：萧珩推门进茶楼，对说书人（主角）说——「**我替你讲吧。**」（明确承诺：要接过讲书权）
- **第 2 章中**：萧珩却说——「**先生继续讲吧。**」「我陪你到打烊。」（完全颠覆了上章的承诺：从"替讲"变成"陪伴"）

这是读者一眼可见的 **承诺颠覆型连贯错误**，在"布局爽+文字质感"调性的作品中，会直接击碎读者对作者精密度的信任。

### 1.2 根因分析（三层叠加）

| # | 层级 | 根因 |
|---|---|---|
| 1 | **跨进程上下文传递** | `ink-auto` 每章启新 `claude -p` 进程、上下文清零；`context-agent` 从 `state.json + summaries + 最近章节摘要` 重建上下文，writer-agent 收到的是**抽象摘要**（"妹妹现身要替主角讲"），而非**原文台词**。语义粒度丢失。 |
| 2 | **大纲驱动 vs 正文连贯的张力** | 第 2 章大纲目标是"兄妹对视 + 承接锦衣卫线"，没写"如何处理『我替你讲』的原话"。writer-agent 在兑现大纲时**顺手修改**了萧珩的承诺语义，以配合自己"兄妹联盟"的章内基调。 |
| 3 | **审查 Agent 覆盖盲区** | `continuity-checker` 主查物理事实（时间/地点/道具/人物在场）；`reader-pull-checker` 查钩子兑现的**情感冲击**而非**台词承诺实现**。没有专门 checker 把关"台词级契约"的语义一致性。 |

### 1.3 问题本质

当前 context pipeline 在**近景信息粒度**上做了过度抽象：

```
原文（ch1 末 ~300 字原文）
  → data-agent 摘要化
  → summary.json "萧珩现身要替主角讲"
  → context-agent 重新打包
  → writer-agent 只看到语义标签，失去台词原文
```

**信息损耗发生在第一跳**：原文 → 摘要的压缩率过高（~10x），导致"台词级精度"无法保真恢复。

---

## 2. 提议方案 · Proposal

### 2.1 核心主张（来自用户实测建议）

> **写第 N 章时，直接把前 3 章全文作为 writer-agent 上下文。**
> 5000 字 ≈ 6-7k tokens，对 Claude Opus 4.7 / Sonnet 4.6（均 1M 上下文）占比 <1%，成本 ~$0.18/章。
> 全文注入彻底消除"摘要化损耗"，同时带来文字质感连续性的隐含红利。

### 2.2 分层注入策略（不只是前 3 章）

context-agent Step 1 打包逻辑改造为**四层上下文**，总预算 ~14k tokens：

| 层级 | 内容 | Token 预算 | 用途 |
|---|---|---|---|
| **L1 · 硬约束（顶层）** | 上章最后台词原文 + pending_utterance + 本章大纲 + 本章 ch1_cool_point_spec（仅第 1 章）| ~2k | 置于 prompt 开头，利用 attention 位置优势 |
| **L2 · 近景 · 原文** | 前 3 章全文（ch{N-3, N-2, N-1}）| ~7k | 台词级精度、文风连续性 |
| **L3 · 中景 · 摘要** | 第 N-10 到 N-4 章摘要（约 7 章）| ~2k | 中距回溯、伏笔铺垫回忆 |
| **L4 · 远景 · RAG** | 主伏笔埋设章 / 首次登场章 / 关键里程碑章的片段（按 `state.plot_threads.foreshadowing` 定位）| ~3k | 长距召回（第 50+ 章仍能"看见"第 1 章的关键设计）|

### 2.3 第 1-3 章的特殊处理

| 章号 | L2 近景原文范围 |
|---|---|
| 第 1 章 | 无（首章；改用 `golden_three_plan.json` 的 `ch1_cool_point_spec` + `cool_point_preview` 作为"虚拟前章"）|
| 第 2 章 | ch1 全文 |
| 第 3 章 | ch1 + ch2 全文 |
| 第 4 章及以后 | 前 3 章全文（滑动窗口）|

### 2.4 Prompt 排版规范（关键）

LLM 对 prompt 中段 attention 显著弱于首尾。**不能简单把 5000 字原文塞中间**。正确排版：

```
┌─────────────────────────────────────────┐
│ [TOP · 硬约束]                          │
│   - 本章大纲（目标/阻力/代价/压扬/...）│
│   - 上章未闭合问题: "萧珩玉牌为何..."   │
│   - pending_utterance: "我替你讲吧"     │ ← 必须响应
│   - must_handle: accept|refuse|transform│
│   - info_budget: max_new_concepts=3     │
├─────────────────────────────────────────┤
│ [MID · 参考资料，非硬约束]              │
│   近景原文（前 3 章全文）               │
│   中景摘要（N-10 至 N-4）               │
│   远景 RAG 片段                         │
├─────────────────────────────────────────┤
│ [BOTTOM · 执行指令]                     │
│   - 以承接第 N-1 章末状态为起点         │
│   - 按 L1 硬约束输出                    │
│   - 遵守 info_budget / 禁止引入新概念… │
└─────────────────────────────────────────┘
```

**关键原则**：
- L1（硬约束）和 Bottom（执行指令）占据 prompt 首尾，attention 最强
- L2-L4 作为"参考资料"放中段，writer 按需查阅而非必须消化
- 明确标注"参考但不复制前文措辞"——避免被文风过度锚定

---

## 3. 实现方案 · Implementation

### 3.1 数据契约变更

#### 新增字段 · `context_package.json`

```yaml
# 原有
recent_summaries:
  - ch: 1
    summary: "萧玄雪夜茶楼说书，妹妹现身..."

# 新增
recent_full_text:
  - ch: 1
    title: "雪下初子"
    text: |
      <full chapter text, ~2000 字>
    word_count: 2087
  - ch: 2
    ...

carryover_hooks:              # 硬约束层
  pending_utterances:
    - from_ch: 1
      speaker: "萧珩"
      utterance: "我替你讲吧"
      must_handle: "accept"   # accept|refuse|transform|defer
      handle_deadline_ch: 2   # 必须在第 2 章内响应

older_summaries:              # 中景
  - ch: 4
    summary: "..."

landmark_rag:                 # 远景
  - ch: 1
    trigger: "foreshadow_FS-001"
    excerpt: "观棋启动瞬间..."

token_budget_used: 6842       # 实际消耗统计
token_budget_cap: 14000
```

#### 新增字段 · `chapter.meta`（data-agent 产出）

```yaml
last_utterance:
  speaker: "萧珩"
  text: "我替你讲吧"
  context: "推门进茶楼后直接对说书人说"

last_action:
  actor: "萧珩"
  action: "掀开帷帽"
  state_after: "主角与妹妹对视，雪夜茶楼二楼"

pending_promises:             # 本章章末对下章的承诺清单
  - type: dialogue_handover
    promise: "要替主角讲下去"
    expected_response_in_ch: 2
```

### 3.2 代码改动点

| 文件 | 改动 |
|---|---|
| `ink_writer/core/context/context_agent.py` | `build_context_package()` 新增 `recent_full_text` / `carryover_hooks` / `landmark_rag` 三个打包函数；加入 token 预算控制 |
| `ink_writer/core/data/data_agent.py` | Step 5 归档时抽取 `last_utterance` / `last_action` / `pending_promises` 写入 `.ink/chapter_meta/ch{N}.json` |
| `ink_writer/core/write/writer_prompt.py` | Prompt 模板改为四段式排版（TOP / MID-参考 / BOTTOM-执行）|
| `ink_writer/agents/continuity_checker.py` | 新增检测规则：`pending_utterance` 是否被正确 handle（与 `must_handle` 语义一致）|
| `ink_writer/core/rag/landmark_retriever.py`（新增）| 按 `plot_threads.foreshadowing` + `chapter_meta` 中的关键标记，RAG 检索历史章节片段 |

### 3.3 Token 预算守护

```python
def build_context_package(chapter_no: int, max_tokens: int = 14000) -> ContextPackage:
    budget = TokenBudget(cap=max_tokens)

    # L1 硬约束（置顶，不受预算压缩）
    hooks = load_carryover_hooks(chapter_no)
    budget.reserve(hooks, min_tokens=2000)

    # L2 近景原文（最高优先级消费预算）
    recent = load_recent_full_text(chapter_no, n=3)
    while budget.remaining() < recent.token_count and recent.chapters:
        # 预算不足时，从最远那一章开始降级为摘要
        oldest = recent.pop_oldest()
        recent.add_summary(oldest)

    # L3 中景摘要
    older = load_summaries(chapter_no, range=(N-10, N-4))
    budget.consume(older, max_tokens=2000)

    # L4 远景 RAG
    landmarks = rag_landmark_retriever(chapter_no, top_k=5)
    budget.consume(landmarks, max_tokens=3000)

    return ContextPackage(hooks, recent, older, landmarks, budget.used)
```

### 3.4 Checker 扩展

新增 `dialogue-continuity-checker`（或扩展 `continuity-checker`）：

```python
def check_pending_utterance_handled(
    prev_chapter_meta: ChapterMeta,
    current_chapter_text: str,
) -> CheckResult:
    """
    对每条 pending_utterance，用 LLM 判定当前章是否按 must_handle 响应。
    - accept: 当前章必须让该 speaker 兑现承诺
    - refuse: 当前章必须给出明确拒绝
    - transform: 允许转换但必须有合理过渡
    - defer: 允许推迟但需说明推迟到何时

    失败分级：
    - critical: 承诺被悄悄收回（本 bug 场景）
    - high: 响应方式与 must_handle 不一致
    - medium: 响应存在但过渡生硬
    """
```

---

## 4. 权衡与副作用 · Trade-offs

### 4.1 优点

1. **彻底解决台词承接问题**：原文直达，无损失
2. **文字质感自动延续**：意象反复、句式节奏、voice 一致性
3. **隐含的伏笔密度受益**：writer 看到前 3 章所有细节，自然避免重复铺设或遗漏回呼
4. **成本可控**：~$0.18/章 × 50 章/卷 ≈ $9/卷，相对质量提升可忽略
5. **人工作家工作流同构**：真实作家也翻前 3 章再动笔

### 4.2 副作用与缓解

| 副作用 | 风险等级 | 缓解措施 |
|---|---|---|
| **语言风格路径依赖** | 低 | 对"文字质感"项目反而是好事；通用项目可通过 `anti-detection-checker` 保留句式多样性 |
| **Attention 位置偏移**（L2 原文在 prompt 中段）| 中 | 通过四段式排版 + L1 硬约束置顶缓解 |
| **Token 成本增加** | 低 | Haiku 级小模型上可降级为"前 1 章全文 + 前 2 章摘要"，通过 `model_tier` 自适应 |
| **Writer 被过度锚定、缺乏创造力** | 低 | Prompt 明确"参考但不复制前文措辞" + L1 硬约束提供本章独立目标 |
| **上下文污染：前章的错误会延续** | 中 | 必须配合 continuity-checker 升级；错误修复后需重跑 data-agent 更新 chapter_meta |

### 4.3 兼容性

- 与现有 `state.json` schema（v9）兼容：新增字段落在 `.ink/chapter_meta/` 单独目录，不污染主 state
- 与 `/ink-write` 单章交互模式兼容：交互模式同样受益
- 与 `/ink-auto --parallel` 并发模式兼容：每个并发 writer 独立拉取 context_package

---

## 5. 验收标准 · Acceptance

### 5.1 功能验收
1. 新的 `context_package.json` 包含 `recent_full_text` / `carryover_hooks` / `landmark_rag` 三字段，且 token 预算 ≤ 14k
2. 第 N 章 writer-agent prompt 首段出现 `pending_utterances` 硬约束
3. `dialogue-continuity-checker` 在 Step 3 审查中作为标准 checker 运行

### 5.2 回归测试
- 对当前项目 `北魏-雪中问青` 第 1-2 章 bug 场景做回归：
  - **重写第 2 章**，验证萧珩的「我替你讲」是否被正确 handle（accept/transform）
  - 重跑审查，`dialogue-continuity-checker` 必须能在**未升级前的**第 2 章正文上检出该 critical

### 5.3 Token 预算验证
- 50 章卷全量跑一遍，`token_budget_used` 平均 < 14k、p95 < 16k、无溢出

---

## 6. Rollout 计划

### Phase 1（MVP，1-2 周）
- data-agent 新增 `chapter_meta` 抽取（`last_utterance` / `pending_promises`）
- context-agent 新增 `recent_full_text` 打包（默认前 3 章全文）
- writer-agent prompt 模板四段式改造
- 对现有项目做 backfill：扫描全部已写章节生成 `chapter_meta/ch{N}.json`

### Phase 2（Checker 升级，1 周）
- `dialogue-continuity-checker` 新建
- `continuity-checker` 扩展 `pending_utterance` 检测规则
- Step 3 审查 agent 清单纳入该 checker

### Phase 3（远景 RAG，2 周）
- `landmark_retriever` 实现
- 对 `plot_threads.foreshadowing` / `chapter_meta.last_utterance` 建立专用索引
- Token 预算自适应算法

### Phase 4（观测与调优，持续）
- `.ink/reports/auto-*.md` 增加 token 预算使用统计
- 多项目对比：全文 carryover 前后的 `overall_score` / `reader_verdict` / bug 率变化

---

## 7. Open Questions

1. **是否需要为第 2 章特殊处理？**（因为它只有 ch1 一章可回溯，不满 3 章窗口）
   建议：滑动窗口，不强制 3 章；第 2 章只注入 ch1 全文即可
2. **是否前 3 章都注入全文会让 writer 产生"学舌现象"？**
   需要通过 Phase 1 MVP 上线后观察 `prose-impact-checker` 的文风一致性指标
3. **与 `/ink-5` / `/ink-auto -p 4` 的交互？**
   并发模式下每个章节独立 context，不共享；但若相邻章节并发，可能出现 A 写 ch10 时 ch9 尚未归档的问题——需要在 `ChapterLockManager` 中加入"前章归档完成"等待信号
4. **是否考虑将 L2 的 3 章窗口配置化？**（小体量作品 5 章 / 长篇巨制 3 章甚至 2 章）
   建议配置项：`context.recent_full_text_window`（默认 3，范围 1-5）

---

## 附录 A · 实测 Bug 复现记录

**项目**：`/Users/cipher/ai/北魏-雪中问青`
**命令**：`/ink-writer:ink-auto 3`
**时间**：2026-04-19 20:51 - 22:22

### 第 1 章末（`正文/第0001章-雪下初子.md` 末段）
```
…… 她抖了抖身上的雪。帷帽那圈素白的纱被风吹起半寸。
"——我替你讲吧。"
```

### 第 2 章中（`正文/第0002章-毒酒的味道.md`）
```
萧珩的睫毛上还沾着一点雪。雪融得慢。她没接这一声。
她只往前一步……
"先生继续讲吧。"她嗓音压得低，"我陪你到打烊。"
```

**承诺偏移**：`"我替你讲吧"` （夺讲书权）→ `"先生继续讲吧 / 我陪你到打烊"`（退让为陪伴）

当前架构下，**所有 Step 3 checker 均未检出此偏移**（overall_score=90, reader_verdict=44/50 pass）。

---

## 附录 B · 设计参考

- **Anthropic Prompt Engineering · Long Context**：长上下文下 attention 首尾优势
- **ink-writer US-005（info_budget）**：已有的"信息释放配额"机制，与 carryover 形成配对（前者管"本章写多少新"，后者管"从前章带多少来"）
- **ink-writer US-004（爽点闭环）**：第 1 章硬约束机制为 carryover 机制提供了"章末承诺原文"的数据源（`cool_point_preview`）

---

**草拟人**：用户 @cipher（实测建议）+ Claude（架构化整理）
**下一步**：请 ink-writer 维护者 Review 本提案 → 决策 Phase 1 排期 → 分配实现人
