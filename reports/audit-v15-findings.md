# ink-writerPro v15.0.0 问题清单与修复方案

> **审查日期**：2026-04-18
> **受审版本**：v15.0.0（HEAD=910add7）
> **审查深度**：读源码（Python + SKILL.md + agent 规格）+ grep 反向验证
> **配套产出**：[`reports/audit-v15-workflow.md`](audit-v15-workflow.md) — 工作流与优势

---

## 1. 审查摘要

### 1.1 严重度分布

```text
🔴 P0 阻断级（3 条）     ████ 14%
🟠 P1 高危   （9 条）   █████████████████████ 43%
🟡 P2 中等   （7 条）   █████████████████ 33%
🟢 P3 低     （2 条）   ████ 10%
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
共 21 条 F-XXX 问题
```

### 1.2 Top 5 最危险问题（一句话）

1. **F-001 (P0)**：`step3_runner` 的 5 个 Python gate 全部是 `_stub_checker` 占位符（score=1.0 恒通过），Step 3.45 实际上是"壳通了但芯是假的"——v14 FIX-04 Phase A 的 MVP 被误当作生产。
2. **F-002 (P0)**：SKILL.md 与代码**相互矛盾**：`skills/ink-auto/SKILL.md:40` 声称"实体写入受 SQLite WAL + ChapterLockManager 保护"，但 `pipeline_manager.py:10` 自己明确说"ChapterLockManager 尚未接入（原 docstring 声称接入为虚假陈述）"。
3. **F-003 (P0)**：PipelineManager 并发写仍裸奔——`parallel>1` 时多章 subprocess 共同写 `state.json`/`index.db`，仅靠 RuntimeWarning 劝退，真被用户无视就会 lost update（FIX-02 仅做了 Phase B 诚实降级，真接入仍待 FIX-04 Phase D）。
4. **F-005 (P1)**：FIX-11 双包合并**未彻底**：`ink-writer/scripts/ink-auto.sh:750` 仍 `from data_modules.checkpoint_utils import report_has_issues`，多处 CLI/test 仍 `sys.path.insert(0, 'ink-writer/scripts/data_modules')`，`skills/ink-resolve/SKILL.md:84-85` 注释改了但下一行立即又写了 `sys.path.insert`——**设计稿验收 §6.2/6.3 "零裸路径/零 data_modules"未达标**。
5. **F-007 (P1)**：创意生成（ink-init Quick Mode）**全部靠 LLM 自律**——陈词黑名单、金手指三重约束（GF-1/2/3）、敏感词 L0-L3 密度控制、书名禁词 combo 检测，**Python 层一个 validator 都没有**，只是 markdown + prompt 让 LLM "自觉遵守"。同一句 prompt 不同 session 输出漂移是确定会发生的事。

### 1.3 业主验收标准对照

| 业主期望 | 实际能力 | 结论 |
|---------|---------|------|
| 300 万字不崩 | SQL-first + 28 表 + progression + propagation 已到位，但端到端零压测 | 🟠 有基础设施但未验证（F-010） |
| 人物不崩 | FIX-18 progression + ooc-checker Layer K 真接线 | 🟢 架构到位 |
| 记忆不错乱 | SQL 单一事实源 + context-agent 4.5 注入 progression 已真实 | 🟢 架构到位 |
| 伏笔回收 | thread-lifecycle-tracker + propagation 双保险 | 🟢 架构到位 |
| 过起点审核 | editor_wisdom 364 条 RAG + anti_detection ZT 正则 | 🟢 **全球唯一且真执行** |
| 黄金三章铁律 | golden-three-checker + 阈值 0.92 + 4 类别强检 | 🟢 真执行 |
| 反俗套 | 数据层齐（1012 种子/170 书名/110 绰号）但 Python 层无 validator | 🟠 靠 LLM 自律（F-007） |
| 工程合理性 | v14/v15 改了很多，但 step3_runner stub、data_modules 残留、SKILL.md 矛盾均为硬伤 | 🟠 规格-代码仍有断层 |

---

## 2. D1-D8 维度问题清单

### D1：长期一致性（人物/记忆/伏笔/时间线）

---

#### F-001: step3_runner 的 5 个 Python gate 全部是 stub，实际不检查任何东西 🔴

| 字段 | 值 |
|---|---|
| 维度 | D1 + D6 |
| 严重度 | 🔴 P0 |
| 可重现性 | 总是 |
| 触发场景 | 任何 `/ink-write` 或 `/ink-auto` 触发的 Step 3.45 |

**证据**：
- `ink_writer/checker_pipeline/step3_runner.py:104-215` ——5 个 adapter（`_make_hook_adapter` / `_make_emotion_adapter` / `_make_anti_detection_adapter` / `_make_voice_adapter` / `_make_plotline_adapter`）内部全部定义 `_stub_checker` 返回 `{"score": 1.0, "passed": True}` 和 `_stub_polish` 返回原文
- 注释明确：`step3_runner.py:105-107` "v14 MVP：Phase A shadow 模式下不调用真 LLM checker；返回 benign pass 让 runner 基础设施先跑通"
- `ralph/prd.json:97`（US-006 notes）自述："Phase A MVP 使用 stub checker_fn/polish_fn，不调用真 LLM；Phase B 迭代时可换"
- `step3_runner.py:387-390` shadow 模式恒 `passed=True`；即使切 enforce 模式，5 个 gate 返回 score=1.0 也永远不会 hard fail
- SKILL.md 文案（`skills/ink-write/SKILL.md:1318-1357`）让用户以为"5 Python gate 真跑"，实际 gate 内 checker 返回固定通过值

**根因**：v14 FIX-04 分 Phase A/B/C 推进，PRD US-006 明确标注 "Phase A MVP = stub"，用意是"先跑通 orchestration 骨架"。但 v14 完结时 Phase B（接真 checker_fn）未做，直接跳到 Phase C（清理 SKILL.md），然后 v15 release note 宣称 "step3_runner 完整接入 5 Python gate 生产"——**用户侧看到的是"已完成"，实际上最关键的内芯是空壳**。

**影响**：
- 业主期望的"追读力/情绪曲线/AI 味/语气指纹/明暗线 5 个维度硬阻断"，当前一条都不会真阻断；
- Step 3.45 每章空跑，写 review_metrics 永远是 passed=True；
- 下游 harness gate 读到"全是通过"，彻底失去门禁意义；
- 对外宣称"8 层反 AI 检测 + 硬门禁"在 step3_runner 层面是假的——真实的 anti_detection 硬门禁只在 SKILL.md Step 3.8 走 LLM 自律路径。

**修复方案**：
1. Phase B 实装：把 5 个 `_stub_checker` 换成调用实际 LLM 的 checker（通过 `ink_writer.core.infra.api_client` 或 claude-haiku-4-5 批量 checker）。
2. `_stub_polish` 接入真 `polish-agent`（subprocess 或 API 调用）。
3. 在 `step3_runner.py` 顶部加 E2E 集成测试：`tests/integration/test_step3_runner_real_gates.py`，mock 5 个 gate 的真 LLM checker 返回有违规的 case，验证 enforce 模式真阻断。
4. 删除所有 "Phase A MVP" 注释，改为 "Phase B production"。
5. SKILL.md 文案对齐：标明默认 `shadow` 模式下 step3_runner 是**影子统计**，不阻断；enforce 模式才真阻断，建议生产跑 enforce + 监控假阳性率。

**预期结果**：修复后，任一章节在 5 个维度违反阈值都会触发 hard fail → 退回 Step 2A 重写（enforce 模式）。review_metrics 的 overall_score 不再恒 100。

**预估工期**：3-4 天（每个 gate 约 0.5 天 + 集成测试 1 天）

**依赖**：无

---

#### F-004: thread-lifecycle-tracker 的生产调用尚未完全归一 🟡

| 字段 | 值 |
|---|---|
| 维度 | D1 |
| 严重度 | 🟡 P2 |
| 可重现性 | 查询时出现 |
| 触发场景 | `/ink-query` 查伏笔健康，同一实体可能从 `foreshadow/tracker.py` 和 `plotline/tracker.py` 各自查一次 |

**证据**：
- `ink_writer/foreshadow/tracker.py` 与 `ink_writer/plotline/tracker.py` 是 v12 以前的独立实现，虽然 agent 规格已合并到 `thread-lifecycle-tracker.md`，但 Python 层两个 tracker 模块仍独立存在
- `reports/architecture_audit.md:97,108-111` 列出 foreshadow + plotline 仍为独立 Python 包

**根因**：v13.0 只在 agent 规格层做了合并（规格别名），Python 实现未合并。

**影响**：轻微——数据库层面是同一张表（`plot_thread_registry`），不会数据不一致；主要是维护成本（两份相似代码）。

**修复方案**：新建 `ink_writer/thread_lifecycle/tracker.py` 作为统一入口，内部分别委托现有两个 tracker；2 轮以后删除旧 import 路径。

**预估工期**：1 天
**依赖**：无

---

### D2：网文商业性（过审/留存/连载节奏）

---

#### F-008: anti_detection 零容忍项只盖 2 条，不足以覆盖起点常见 AI 味 🟡

| 字段 | 值 |
|---|---|
| 维度 | D2 |
| 严重度 | 🟡 P2 |
| 可重现性 | 特定场景 |
| 触发场景 | 章节不以"第二天"开头、不含"与此同时"，但仍满屏 "不仅……而且……"、"尽管如此" |

**证据**：
- `config/anti-detection.yaml:44-62`（路径推断自用户 memory 与代码）ZT 项仅 `ZT_TIME_OPENING` + `ZT_MEANWHILE`
- 但 v13.7 加入的"镜头/感官/句式节奏"文笔硬约束是靠 3 个新 checker（prose-impact/sensory-immersion/flow-naturalness），它们在 step3_runner 覆盖之外
- `ink_writer/anti_detection/sentence_diversity.py` 真实 Python 执行但仅 7 类统计特征，未覆盖"套路化长连接词"

**根因**：ZT 正则扩展时机晚于 anti_detection_gate 的成型。

**影响**：过审拦截率不足；用户 memory 记录"起点编辑打回 AI 味"仍会复现。

**修复方案**：
1. 扩 ZT 正则到 8-10 条（加 "尽管如此/不仅……而且/与此同时"不同句式）；
2. sentence_diversity 增加"连接词密度"指标（配置 `conjunction_density_max`）；
3. 跑用户的 117 本起点标杆做 baseline，调试阈值。

**预期结果**：过审 AI 味拦截率显著提升，用户 Memory `feedback_writing_quality.md` 里的"第 xx 日时间标记开头"不再发生。

**预估工期**：2 天
**依赖**：F-001 先修完（否则 ZT 扩展无载体）

---

#### F-009: golden_three 阈值 0.92 可能导致前 3 章反复 blocked 🟡

| 字段 | 值 |
|---|---|
| 维度 | D2 + D3 |
| 严重度 | 🟡 P2 |
| 可重现性 | 前 3 章偶发 |
| 触发场景 | 黄金三章 editor_wisdom 召回命中 hard 规则较多时，3 次 retry 都触顶失败 |

**证据**：
- `config/editor-wisdom.yaml` 声明 `golden_three_threshold: 0.92`（US-017 从 0.85 升至 0.92）
- `editor_wisdom/checker.py:62-70` 扣分：1 条 hard = -0.3、soft = -0.1；召回 top_k=5 的话，只要命中 1 条 hard + 2 条 soft 即 0.5 < 0.92
- `review_gate.py:78-169` 3 次重试失败就 `blocked.md`，无降级路径

**根因**：阈值偏高 + 扣分模型线性 + retry 次数少，易误伤。

**影响**：用户反复被 blocked 体验差；真实场景 LLM 每次重写能解决的通常是 soft，hard 往往需要结构性改写超出 polish 能力。

**修复方案**：
1. 区分黄金三章的硬阈值（强制 ≥ 0.75）与软阈值（希望 ≥ 0.92 可 warn）；
2. retry 达限前增加一次"整章重写"逃生门（不是 polish 局部改，而是退 Step 2A）；
3. 把扣分模型从线性改为指数（多条 soft 比单 hard 更容易过），符合真实编辑判断。

**预期结果**：黄金三章 blocked 率显著下降，同时严格度不降（因为 hard 仍严）。

**预估工期**：1.5 天
**依赖**：无

---

### D3：结构铁律（黄金三章/钩子/卖点）

---

#### F-006: golden-three-checker 与章 1 的 4 项爽点硬阻断存在语义重叠但逻辑未互斥 🟡

| 字段 | 值 |
|---|---|
| 维度 | D3 |
| 严重度 | 🟡 P2 |
| 可重现性 | 前 3 章 |
| 触发场景 | 章 1 既被 golden-three-checker 专检也被 v13.7 的 4 项爽点硬阻断检，两套判决可能给出相反结论 |

**证据**：
- `ink_writer/editor_wisdom/golden_three.py:11` 检查 4 类别
- v13.7 新增 `prose-impact/sensory-immersion/flow-naturalness` 3 个 checker 对章 1 加严
- `docs/audit/03-checker-matrix.md:231-234` 指出"镜头/感官/句式节奏 4-5 重覆盖"

**根因**：v13.2 与 v13.7 两个阶段分别加门禁，未做交集收敛。

**影响**：polish-agent 收到冲突 fix_prompt，token 膨胀，修复方向可能抵消。

**修复方案**：建一张 "前 3 章所有 checker 冲突仲裁表"，polish-agent 消费 merged_fix_suggestion。

**预估工期**：2 天
**依赖**：无

---

### D4：反俗套 & 创意独特性

---

#### F-007: Creativity 生成完全靠 LLM 自律，Python 层零 validator 🟠

| 字段 | 值 |
|---|---|
| 维度 | D4 |
| 严重度 | 🟠 P1 |
| 可重现性 | 每次 /ink-init --quick |
| 触发场景 | 书名含后缀"神帝/至尊"、金手指是"修为暴涨无限金币"、敏感词超限——当前无 Python 拦截 |

**证据**：
- `data/naming/blacklist.json`（19 条书名后缀禁词 + 14 条前缀 + combo 笛卡儿积）——**无任何 Python 模块 import 或消费**（grep `blacklist` 无代码层命中）
- `ink-writer/skills/ink-init/references/creativity/golden-finger-rules.md`（GF-1/GF-2/GF-3 三重）仅 markdown，伪代码 `golden-finger-rules.md:88-100` 不存在 Python 实现
- `style-voice-levels.md:48-61` 敏感词 L0-L3 分级，密度矩阵全是文档，无 Python 检测
- `anti-trope-seeds.json` 1012 条仅 LLM 通过 prompt 消费
- `ralph/prd.json` 整个 v14/v15 PRD 里**没有修这个 Critical**（v14 US-006/v5 审计 Top #8 明示）

**根因**：v13.8 时这些都以"markdown + LLM 自律"方式实装；v14 审计发现后列为 Critical，但 v14/v15 的 30 US 聚焦在 checker/memory/propagation，创意 validator 被推迟。

**影响**：
- 同一 `/ink-init --quick` 不同 session 输出漂移——用户可能第一次出来就是"神帝战神斗罗大陆"类俗套；
- Quick Mode 的"5 次重抽 + 档位降档"流程完全靠 LLM 看心情执行；
- 敏感词 L2/L3 的 0.5%/1.5% 密度矩阵无算法保证；
- 与项目独特卖点"反俗套"承诺严重不符——数据备齐了但 validator 缺位。

**修复方案**：
1. 新建 `ink_writer/creativity/` 模块，对标 `editor_wisdom` 架构；
2. 实装 3 个 validator：
   - `name_validator.py`：读 `blacklist.json`，对书名/主角名做后缀+前缀+combo 检测；
   - `gf_validator.py`：对金手指方案做 GF-1 非战力维度枚举 + GF-2 代价可视化正则 + GF-3 一句话爆点长度/反直觉检测；
   - `sensitive_lexicon_validator.py`：读 L0-L3 词库，对生成文本做密度统计；
3. Quick Mode SKILL.md 在每次重抽后 bash 调用 `python -m ink_writer.creativity.validate`，失败即降档重抽。

**预期结果**：Quick Mode 输出稳定不漂移；同一档位下 100 次运行无一触碰黑名单。

**预估工期**：5-7 天
**依赖**：无（纯增量模块）

---

### D5：工程架构（模块边界/循环依赖/状态管理）

---

#### F-002: SKILL.md 文案与代码直接矛盾，ChapterLockManager 虚假声明未清除 🔴

| 字段 | 值 |
|---|---|
| 维度 | D5 + D7 |
| 严重度 | 🔴 P0 |
| 可重现性 | 总是 |
| 触发场景 | 用户阅读 `/ink-auto` SKILL.md，误以为并发写已接入保护 |

**证据**：
- `ink-writer/skills/ink-auto/SKILL.md:40`：**"实体写入受 SQLite WAL + ChapterLockManager 保护"**（虚假声明）
- `ink_writer/parallel/pipeline_manager.py:10-17`：**"ChapterLockManager 尚未接入（原 docstring 声称接入为虚假陈述），多个 CLI 子进程并发写 state.json / index.db 存在数据损坏风险"**（自认未接入）
- `README.md:166`：也明确警告"parallel>1 是实验特性，ChapterLockManager 集成尚未完成"

**根因**：v13 US-023 FIX-02B 做了**诚实降级**（RuntimeWarning + README 更新 + pipeline_manager docstring 改写），但忘了同步 `skills/ink-auto/SKILL.md:40` 的文案。这是"修了代码忘了改文档"的经典 bug。

**影响**：
- AI agent 读 SKILL.md 误以为安全，可能直接建议 `parallel=4`；
- 用户若绕过 RuntimeWarning（设置 `warnings.simplefilter('ignore')`）会 silent data corruption；
- 文档-代码不一致是信任崩塌第一步，对 skill 类产品尤其致命。

**修复方案**：
1. 立即改 `skills/ink-auto/SKILL.md:40`："⚠️ 当前仅 parallel=1（串行）安全。parallel>1 未接 ChapterLockManager，存在写入竞争风险，会触发 RuntimeWarning。"
2. `scripts/verify_docs.py` 新增 check：grep 全仓"ChapterLockManager 保护|由 SQLite WAL .* ChapterLockManager"，若命中则 CI fail，强制与 pipeline_manager.py:10 同步。

**预期结果**：文档与代码一致；CI 持续守卫。

**预估工期**：0.3 天

**依赖**：无

---

#### F-003: PipelineManager 并发裸奔的根治仍未做 🔴

| 字段 | 值 |
|---|---|
| 维度 | D5 |
| 严重度 | 🔴 P0 |
| 可重现性 | `parallel>1` 时必然 |
| 触发场景 | 用户忽略 RuntimeWarning 强行设 parallel=N>1 |

**证据**：
- `ink_writer/parallel/pipeline_manager.py:149-159`：仅 `warnings.warn(..., RuntimeWarning)` 劝退
- 全文件 0 次 `from ink_writer.parallel.chapter_lock import ChapterLockManager`
- `ink_writer/parallel/chapter_lock.py:13` 的 `ChapterLockManager` 有完整实现 + 13 个 pytest，但**零生产调用者**
- `pipeline_manager.py:15` TODO 自己承认：**"TODO: 参考 tasks/design-fix-04-step3-gate-orchestrator.md Phase B/C"**

**根因**：FIX-02B 的方案 B 是"诚实降级到 parallel=1"（0.5 天工期），真接入方案（1.5 天）未做。v14 PRD 把 FIX-04 拆成 Phase A/B/C，Phase A 做 orchestration，Phase B/C/D 都未启动。

**影响**：
- 现在事实上无法用并发加速（用户 memory 中"每天 1-2 万字"依赖 parallel=1 慢串行）；
- ChapterLockManager 成沉没成本；
- 若用户强行并发，state.json + index.db lost update 会造成角色状态错乱、伏笔计数漂移。

**修复方案**：
1. `pipeline_manager.py` __init__ 实例化 `ChapterLockManager(state_dir, ttl=300)`；
2. Step 5 data-agent 写 SQL 前用 `lock.state_update_lock()` context 包裹；
3. 章节级任务启动前 `lock.chapter_lock(chapter_id)` 独占；
4. 把 `chapter_lock.py:49-54` 的 `threading.local()` 改为 `asyncio.Lock`（因 PipelineManager 用 asyncio）；
5. 把 parallel 警告改为"parallel>1 已接入 ChapterLockManager，但仍实验性；建议 ≤4"。

**预期结果**：`/ink-auto 10 --parallel 4` 真并发写入且无数据损坏；实测 4 章并发应比串行快 2.5-3x。

**预估工期**：2 天（含集成测试）

**依赖**：F-001 建议先修（否则 step3_runner stub 下观察不到真并发行为）

---

#### F-005: FIX-11 双包合并未达设计稿验收标准 🟠

| 字段 | 值 |
|---|---|
| 维度 | D5 |
| 严重度 | 🟠 P1 |
| 可重现性 | 总是 |
| 触发场景 | 新开发者运行 `/ink-auto`，或跑 `tests/` 时 |

**证据**（`tasks/design-fix-11-python-pkg-merge.md:186-188` 验收标准 §6.2/6.3："零裸路径"+"零 data_modules"）：
- `ink-writer/scripts/ink-auto.sh:750`：生产脚本仍 `from data_modules.checkpoint_utils import report_has_issues`——**未改**
- `ink-writer/scripts/ink-auto.sh:1099-1100`：`sys.path.insert(0, '$REPO_ROOT'); sys.path.insert(0, '${PLUGIN_ROOT}/scripts')`——**未清**
- `ink-writer/skills/ink-resolve/SKILL.md:84-85`：注释一行说 "FIX-11 sys.path.insert no longer required"，下一行紧跟着就 `sys.path.insert(0, str(Path('${CLAUDE_PLUGIN_ROOT}/..')))`——**注释与代码自相矛盾**
- `ink-writer/scripts/ink.py:26`、`scripts/migrate.py:213`、`scripts/extract_chapter_context.py:53`、`scripts/patch_outline_hook_contract.py:21`、`scripts/measure_baseline.py:22`、`scripts/build_chapter_index.py:26`（已注释）：生产 Python 仍有 sys.path.insert
- `ink_writer/core/cli/ink.py:573`：新包里 CLI 入口自己还在做 sys.path hack
- 仓库仍有 `ink_writer/core/tests_data_modules/` 目录，内含老测试

**根因**：v14 US-025/026 设计了迁移脚本（`scripts/migration/fix11_merge_packages.py`），但 ink-auto.sh（shell 脚本里的 embedded python）未被自动扫描；SKILL.md 里的 heredoc python 也遗漏。

**影响**：
- 设计稿明言"FIX-11 合并后不再需要 sys.path"，但生产 `/ink-auto` 依赖 sys.path 才能跑；
- 新开发者上手仍需理解"双包"心智模型；
- 未来 `pip install -e .` 行为与运行时路径不一致，PyPI 发包阻塞。

**修复方案**：
1. 把 `ink-auto.sh:750` 的 import 改为 `from ink_writer.core.cli.checkpoint_utils import report_has_issues`；
2. 删除 `ink-auto.sh:1099-1100` 的 sys.path 双插入，依赖 `PYTHONPATH` 环境变量（或 ink_writer 已安装）；
3. 修复 `skills/ink-resolve/SKILL.md:84-85` 的自我矛盾；
4. 扩迁移脚本扫描范围：加 `.sh` + SKILL.md 内 heredoc python 块；
5. 清 `ink_writer/core/tests_data_modules/`，把 tests 合进主 `tests/` 目录；
6. 在 `.pre-commit` / CI 加 `rg 'from data_modules|import data_modules'` fail 门禁。

**预期结果**：验收标准 §6.2/§6.3 真达标；`rg sys.path.insert` 仅剩 benchmark/ 下 3-5 条注释。

**预估工期**：1.5 天

**依赖**：无

---

#### F-011: 镜头/感官/句式节奏 3-5 重重复检测未收敛 🟡

| 字段 | 值 |
|---|---|
| 维度 | D5 |
| 严重度 | 🟡 P2 |
| 可重现性 | 总是 |
| 触发场景 | polish-agent 收到 SHOT_MONOTONY 的 fix_prompt 三份重复 |

**证据**：
- `reports/architecture_audit.md:190-231` 列出 50 条 repeated prompt fragments，其中大量是 `flow-naturalness-checker / prose-impact-checker / sensory-immersion-checker` 三重重叠
- `docs/engineering-review-report-v5.md:60` 指出 v13.7 polish-agent 对 SHOT_MONOTONY 显式写"对应规则码 SHOT_MONOTONY（writer-agent L10d / prose-impact-checker 镜头多样性 / proofreading 6B.1）"

**根因**：v13.7 新 checker 被叠加进来时未与 v13.6 及之前的 checker 做去重。

**影响**：prompt token 膨胀（估计 +15-25%）、polish-agent 收到冲突建议、测试时单维度 pass 但组合测试难。

**修复方案**：新建 `references/shared-checker-preamble.md` 的"冲突/互补维度矩阵"section，标注每个维度的**主 checker**，其他 checker 用 `@see` 引用；polish-agent 消费 merged_fix_suggestion。

**预估工期**：2-3 天
**依赖**：无

---

#### F-012: `chapter_paths` ↔ `chapter_outline_loader` import cycle 未解 🟡

| 字段 | 值 |
|---|---|
| 维度 | D5 |
| 严重度 | 🟡 P2 |
| 可重现性 | 总是（模块加载时） |
| 触发场景 | 冷启动 import |

**证据**：`reports/architecture_audit.md:15` 明确报告"Import cycles found: 1 — chapter_paths → chapter_outline_loader → chapter_paths"

**根因**：两模块职责未清晰分离，路径工具和章纲加载相互依赖。

**影响**：目前能跑是因为 Python 循环引用可以懒解析，但是加模块级代码或装饰器会 ImportError。

**修复方案**：抽 `chapter_path_types.py` 只含类型定义，两边都 import 它。

**预估工期**：0.5 天

---

### D6：Agent 工程范式（对标 Anthropic / Claude Code Skill / 主流框架）

---

#### F-013: Claude Code Skill 规范差距（3 条） 🟡

| 字段 | 值 |
|---|---|
| 维度 | D6 |
| 严重度 | 🟡 P2 |
| 可重现性 | 静态检查 |

**三向差距**：

**差距 1：`ink-plan/SKILL.md` 缺 `allowed-tools` frontmatter**
- 证据：其他 13 个 SKILL.md 都有 allowed-tools，仅 `skills/ink-plan/SKILL.md:1-4` 无；但 SKILL 内容里用 Read/Bash/AskUserQuestion
- 影响：主 agent 权限判定时可能给全权，违反最小权限
- 修复：补 `allowed-tools: Read Bash AskUserQuestion`

**差距 2：Skill description 里承诺与实际能力漂移**
- 证据：`skills/ink-write/SKILL.md` description 声称"runs context, drafting, review, polish, and data extraction"；但 Step 3.45 跑 step3_runner stub（F-001），Step 3.5 仍是 legacy LLM 自律（SKILL.md:1336）
- 修复：标明"Step 3 默认 shadow 模式，非 production enforce"，或与 F-001 一起根治

**差距 3：agent `allowed-tools` 分布整体健康但缺审计**
- context-agent / polish-agent / writer-agent / data-agent 都拿 Read+Write+Bash（正确）；checker 全 Read-only；这已是最小化的合格实现
- 但没有 CI 守卫"新 agent 默认 allowed-tools ≤ Read"
- 修复：`scripts/verify_docs.py` 新增 agent frontmatter 审计

**对标评分**（满分 30，基于 Skill Registry 四要素 + Extras 检查）：

| 指标 | ink-writer 得分 | 满分 |
|------|:---:|:---:|
| Skill 描述清晰度 | 4 | 5 |
| allowed-tools 最小化 | 4 | 5 |
| 避免滥用 skill（不拿 skill 当普通脚本） | 5 | 5 |
| 僵尸 agent 清理（v13 US-016 已删） | 5 | 5 |
| agent frontmatter 完整 | 5 | 5 |
| Skill frontmatter 完整 | 4 | 5 |
| **合计** | **27** | **30 (90%)** |

---

#### F-014: Anthropic Agent SDK 能力未最大化利用 🟡

| 字段 | 值 |
|---|---|
| 维度 | D6 |
| 严重度 | 🟡 P2 |
| 可重现性 | 静态检查 |

**三向差距**：

**差距 1：prompt_cache 机制可观测性空白**
- 证据：`ink_writer/prompt_cache/metrics.py` 存在但其 cache 命中率/过期率无任何 dashboard 暴露（架构审计把 `prompt_cache.metrics` 列为 unused module）
- 2026 Q1 Claude SDK 的 `prompt_caching` 提供 `usage.cache_creation_input_tokens` / `usage.cache_read_input_tokens`，需要采集进 `metrics.py`
- 修复：`api_client.py` 每次 response 后写 cache 命中到 SQLite `cache_metrics.db`；dashboard 显示每章 cache 命中率

**差距 2：模型选型未做分层（杀鸡用牛刀 or 反之）**
- 证据：`core/infra/api_client.py` 按用户 memory 建议 Opus 4.7 / Sonnet 4.6 / Haiku 4.5，但 grep 未见不同 task 的差异化选型；writer-agent/polish-agent 这种高创意任务应默认 Opus 4.7；simple classify / extract 应 Haiku 4.5
- 修复：建 task→model 映射表 `config/model_selection.yaml`

**差距 3：没有利用 batch API 做多章并发审查**
- 证据：22 个 checker 并发时，若用 Anthropic Messages Batch API 可 50% 折扣 + 24h SLA
- 修复：ink-review 批量 >10 章时自动走 batch API

---

#### F-015: 小说 AI 长记忆范式差距（3 条） 🟡

| 字段 | 值 |
|---|---|
| 维度 | D6 |
| 严重度 | 🟡 P2 |

**差距 1：相关性检索混合策略未实装**
- NovelCrafter Codex 用 embedding + 关键词混合检索；ink-writer semantic_recall 只有 FAISS 或 SQLite quality_score DESC（`semantic_recall/retriever.py:180-223`）
- 修复：加 BM25 并与 FAISS 做 reciprocal rank fusion

**差距 2：记忆压缩与长程召回只有单层**
- MemGPT 范式有 main_context / external_context 两层，动态压缩
- ink-writer `memory_compressor.py` 只做"卷级 mega-summary"单层（`memory_compressor.py` Reader 仅卷间），章节内信息没压缩
- 修复：加章级 L1 压缩（8→3 bullet）与卷级 L2 压缩（40→10 bullet）

**差距 3：缺少 Generative Agents 风格的 reflection**
- Generative Agents 每 N 轮让 agent 自己反思"最近经历对角色的影响"
- ink-writer progression_events 只捕获 from/to 具体变化，没有 "对整体世界观/人物关系的二级推论"
- 修复：在 /ink-macro-review 加一个 reflection agent：输入最近 50 章摘要 + progressions → 输出 3-5 条"涌现现象"写入 `.ink/reflections.json`

---

### D7：测试与可观测性

---

#### F-010: 300 万字端到端压测零证据，性能承诺悬空 🟠

| 字段 | 值 |
|---|---|
| 维度 | D7 |
| 严重度 | 🟠 P1 |
| 可重现性 | 总是 |
| 触发场景 | 用户真写到 300 章才会知道会不会崩 |

**证据**：
- `README.md:158-160` FAQ：**"100 章总检查点开销约 7 小时"**——凭空数字
- v14 PRD `ralph/prd.json:4` 明确 exclude FIX-16 "100 章真实压测"
- `benchmark/300chapter_run/metrics.json` 曾被 v5 审计发现 wall_time=8.1s / G1-G5 全 0
- v14/v15 全部 30 US 中无一条做真实压测

**根因**：压测成本高（token 费用 + wall time），v14 集中修 Checker/Memory/Creative 优先级更高。

**影响**：
- 业主最大期望"300 万字不崩"**完全依赖推断**，无数据支撑；
- 一旦真用户写到第 250 章发现 state.json 膨胀到 50MB 性能断崖，届时迁移成本极高；
- 存在潜伏 bug（比如 progression 累积 1000+ 行/角色时 IndexManager 内存/查询性能未知）。

**修复方案**：
1. 写 `benchmark/e2e_300_chapter_mock.py`：用 LLM 生成每章 1-2KB 的短 mock 章节，真跑 300 次 `/ink-write`（或 shadow 模式省 LLM 费用）；
2. 收集 G1-G5：`G1=wall_time_per_chapter`, `G2=state.json_size_at_milestones`, `G3=index.db_size`, `G4=context-agent pack_size`, `G5=retriever_latency`；
3. 产出 `reports/perf-300chapter-v15.md`，修正 README 数字。

**预期结果**：README 数字真实；长度上限可实证（比如"在当前架构下，1000 章时 state.json ≈ 32MB，context pack ≈ 12K tokens，性能稳定"）。

**预估工期**：3-4 天（含 token 费用）

**依赖**：F-001 应先修（否则压测得到的是 stub 结果）

---

#### F-016: architecture_audit 报 123 unused candidates，误报多但有真问题 🟡

| 字段 | 值 |
|---|---|
| 维度 | D7 |
| 严重度 | 🟡 P2 |

**证据**：
- `reports/architecture_audit.md:19`："Unused module candidates: 123"
- 其中大量是 `core.*` / `progression.*` / `propagation.*`（实际被 SKILL.md 里的 python 脚本块调用，AST 扫不到）
- 但 `incremental_extract/differ.py` 确实零 import（v5 审计已标孤儿）

**根因**：`scripts/audit_architecture.py` 只扫 .py 文件的静态 import，不解析 SKILL.md 里的 embedded python。

**修复方案**：
1. 扩 `audit_architecture.py` 扫 SKILL.md 的 `python3 -c "from ink_writer..."` / `python -m ink_writer...`；
2. 真孤儿 `incremental_extract/differ.py` 要么接入 data-agent、要么归档；
3. `ink_writer/core/tests_data_modules/` 合并到 tests/ 统一管理。

**预估工期**：1 天

---

#### F-017: 审查报告文件体系与 DB metrics 双写但消费端仍混乱 🟡

| 字段 | 值 |
|---|---|
| 维度 | D7 |
| 严重度 | 🟡 P2 |

**证据**：
- `review_metrics` 表已是主数据源（v14 US-010 修复 harness_gate 走 DB）
- 但 `/ink-review` 仍生成 `.ink/reports/review_*.json` 文件
- 有些 checker 报告在 JSON 文件里更详细，有些维度只在 DB

**影响**：用户 / 审查 AI 看不同数据源得到不同结论。

**修复方案**：明确"DB 是源，JSON 是可读视图"；JSON 标记 `generated_from: index.db` 并自动同步。

**预估工期**：1 天

---

### D8：安全与健壮性

---

#### F-018: API Key 泄露风险（低）+ 日志仍混 print/logging 🟡

| 字段 | 值 |
|---|---|
| 维度 | D8 |
| 严重度 | 🟡 P2 |

**证据**：
- v5 审计的"`api_client.py` 8 处 retry print 污染 stdout"在 v14 PRD 里没有专门修复（未列入 30 US）
- `ink-writer/scripts/` 下 print vs logging 比例未改善（需复查）

**修复方案**：一次性把 `ink_writer/core/infra/api_client.py` 的 retry print 换 `logger.warning`；同时给 LLM 调用加显式 timeout。

**预估工期**：1 天

---

#### F-019: LLM 调用无显式 timeout（潜在会话卡死） 🟡

| 字段 | 值 |
|---|---|
| 维度 | D8 |
| 严重度 | 🟡 P2 |

**证据**：v5 审计 Finding #17，v14 PRD 未修。

**修复方案**：`editor_wisdom/llm_backend.py` + `core/infra/api_client.py` 在 `client.messages.create()` 显式传 `timeout=120`。

**预估工期**：0.5 天

---

#### F-020: 03_classify / 05_extract_rules 入口仍需 API Key 校验 🟢

| 字段 | 值 |
|---|---|
| 维度 | D8 |
| 严重度 | 🟢 P3 |

**证据**：v5 审计 Finding #14，v14 PRD 未明确修。但 v14 Step 2 曾声称做 "API Key 入口护栏"。

**修复方案**：最小化 —— 已部分修复，增加单测覆盖。

**预估工期**：0.3 天

---

#### F-021: CLAUDE.md Top 3 注意事项已过时 🟢

| 字段 | 值 |
|---|---|
| 维度 | D7 |
| 严重度 | 🟢 P3 |

**证据**：
- `CLAUDE.md:9-14` Top 3 现在写了 4 条（第 4 条是 FIX-11 说明）
- 第 2 条仍说"分类/规则抽取需要 API Key，本机 `.zshrc` 默认 unset 了它"—— 是事实但提示位置不对

**修复方案**：清理到 3 条，或改名"Top 5"；第 4 条关于 FIX-11 的警告可能已不需要（如果 F-005 修完）。

**预估工期**：0.1 天

---

## 3. 关键架构建议（系统级，5 条）

### 建议 1：把 step3_runner 从 Phase A MVP 升级到 Phase B Production

**做**：F-001 方案，把 5 个 stub 替换为真 LLM checker + polish，集成测试覆盖 hard fail 真阻断。
**不做的代价**：所有"5 Python gate 硬门禁"承诺都是假的，`/ink-auto` 每章空跑 step3_runner 徒增 wall time 无收益；用户对"过审保障"失去实际凭据。
**做的代价**：3-4 天 + 每章增加约 5-10 秒 wall time（5 个 gate × 2s LLM call）。

### 建议 2：建立"文档-代码同步 CI 门禁"（verify_docs.py 扩展）

**做**：`scripts/verify_docs.py` 增加 10+ 条规则：
- SKILL.md 里出现"ChapterLockManager 保护|parallel>1 安全"必须与 pipeline_manager.py 一致
- SKILL.md 里的 python 脚本块必须能 import 成功
- Agent frontmatter `allowed-tools` 必须存在
- 版本号一致性（plugin.json / pyproject.toml / README shield）
- `rg 'from data_modules'` 必须 0 命中

**不做的代价**：F-002 类文档-代码矛盾会持续产生；每个 release 都有"修了代码忘了改 README"的隐患。
**做的代价**：2 天实装 + 每次改动略增摩擦。

### 建议 3：把创意生成 markdown 伪代码产品化为 `ink_writer/creativity/` Python 模块

**做**：F-007 方案，对标 `editor_wisdom` 架构建 validator 子系统。
**不做的代价**：项目独特卖点"反俗套"是半成品；Quick Mode 不稳定；不同 session 输出漂移。
**做的代价**：5-7 天。

### 建议 4：压测与性能实证（300 章 mock）

**做**：F-010 方案，真跑 300 章收集 G1-G5。
**不做的代价**：最核心卖点"300 万字不崩"纸面承诺；万一是真的就能用作推广弹药，万一有问题趁早暴露。
**做的代价**：3-4 天 + token 费用估 $50-200（取决于是 shadow mock 还是真 LLM）。

### 建议 5：收敛文笔维度重复检测（polish-agent merged_fix_suggestion）

**做**：F-011 方案，polish-agent 消费统一的 merged_fix_suggestion，而非 3-5 份重叠 checker report。
**不做的代价**：polish token 膨胀、修复方向冲突。
**做的代价**：2-3 天。

---

## 4. 修复路线图（3 个 milestone）

### Milestone A：止血（1-2 周）

| ID | 标题 | 工期 | 阻断 |
|---|---|:---:|:---:|
| F-002 | SKILL.md 文案与代码对齐 + verify_docs.py 守卫 | 0.3d | - |
| F-003 | ChapterLockManager 真接入 pipeline_manager | 2d | - |
| F-001 | step3_runner Phase B：5 stub → 真 checker/polish | 3-4d | - |
| F-005 | FIX-11 残留清理（ink-auto.sh + SKILL.md） | 1.5d | - |
| F-019 | LLM 调用加 timeout | 0.5d | - |
| **小计** | | **7-8 天** | |

### Milestone B：补能力（2-4 周）

| ID | 标题 | 工期 | 阻断 |
|---|---|:---:|:---:|
| F-007 | Creativity validator 实装 | 5-7d | - |
| F-010 | 300 章 E2E 压测 | 3-4d | F-001 |
| F-008 | ZT 正则扩展 + 连接词密度指标 | 2d | F-001 |
| F-011 | 文笔维度 merged_fix_suggestion | 2-3d | - |
| F-009 | 黄金三章阈值软化 | 1.5d | - |
| **小计** | | **14-18 天** | |

### Milestone C：工程卫生（1-3 周）

| ID | 标题 | 工期 | 阻断 |
|---|---|:---:|:---:|
| F-013/014/015 | Skill/SDK/NovelCrafter 对标差距修复 | 8d | - |
| F-016 | architecture_audit 扩展扫描 + 孤儿清理 | 1d | - |
| F-017 | JSON report / DB metrics 源头统一 | 1d | - |
| F-018 | print → logging + api_client 日志 | 1d | - |
| F-012 | import cycle 解构 | 0.5d | - |
| F-004 | foreshadow/plotline tracker 合并 Python | 1d | - |
| F-006 | 前 3 章 checker 冲突仲裁 | 2d | F-011 |
| F-020/F-021 | 细节收尾 | 0.5d | - |
| **小计** | | **15 天** | |

**总计**：36-41 天（Milestone A+B+C），单人全职大约 2 个月。

---

## 5. 修复后预期指标

假设 Milestone A + B 全部完成（约 3-4 周）：

| 指标 | 当前（v15.0.0） | 修复后（v15.x） | 验证方式 |
|------|:---:|:---:|------|
| step3_runner 有效硬门禁数 | 0/5（全 stub） | 5/5 | tests/integration/test_step3_enforce_real_fail.py |
| SKILL.md ↔ 代码一致率 | ~85%（F-002 + F-005 明伤） | 100% | verify_docs.py CI |
| `/ink-auto 10 --parallel 4` 数据安全 | 🔴 裸奔 | 🟢 ChapterLockManager 保护 | tests/parallel/test_concurrent_state_write.py |
| Quick Mode 书名黑名单触碰率 | 未知（无检测） | <1% | tests/creativity/test_name_validator.py |
| 300 章 mock wall_time | 无数据 | 实测 G1-G5 | reports/perf-300chapter-v15.md |
| AI 味过审拦截率 | ~65%（估计） | ~85% | tests/anti_detection/test_zt_expansion.py |
| Skill 规范评分 | 27/30 | 30/30 | scripts/verify_docs.py |

---

## 6. 对业主的 Top 3 直白建议（大白话）

### 建议 1：别被"已完成"骗了——Step 3.45 目前是"装了个壳，里头空的"

你以为 v15 新加的"5 层 Python 硬门禁"（追读力/情绪/AI 味/语气/明暗线）在帮你挡劣质章节？**其实没有**。我看了代码，这 5 层每一层的"检查函数"都被代码里一个名叫 `_stub_checker` 的占位符顶着，它返回"所有章节都通过"。这不是 bug，是上一轮工作只做了一半——做了"壳"，没做"芯"。

**你要做的事**：下次开新 PRD 时，把"补齐 step3_runner 的 5 个真 checker/polish 接线"列为最高优先级 P0。没有它，所谓"质检硬阻断"都是纸面承诺。修完后你应该能看到：写一章故意让它出 AI 味，`review_metrics` 里会真的记录为 `passed: false`，章节会退回 Step 2A 重写。这才叫生效。

### 建议 2："300 万字不崩"目前只是推断，没人真跑过

这个项目所有"记忆不错乱"的能力，都建立在一个没被验证的假设上——"SQL 表设计对，就能撑到 1000 章"。**但从来没人真的跑到 300 章过**。你 README 说"100 章约 7 小时"也是估算不是实测。

这不是说架构不行，相反我觉得架构很扎实。但**没验证过**就是没验证过。建议你找个不太忙的周末，或者让我们把它放进下一轮 PRD——用 shadow 模式（不调用 LLM，只跑流水线本身）模拟 300 章，测 3 个数字：
1. state.json 膨胀到多大（担心 >30MB 会慢）
2. 每章 context pack 多大（担心 >15K tokens）
3. IndexManager 查询延迟（担心 >500ms 会卡）

跑完你心里就有底了，写到 500 章也不慌。

### 建议 3："反俗套"目前是"词库齐、发力没"——这是项目最不对称的地方

你自豪的反俗套机制：陈词黑名单（19 条书名后缀禁词）、金手指三重约束（GF-1/2/3）、敏感词分级 L0-L3 密度矩阵、书名模板库 170 条、绰号库 110 条、反俗套种子库 1012 条——**数据层准备得非常好**，这是竞争对手没有的资产。

**但是**，代码里一个 Python 函数都没消费这些数据。Quick Mode 跑出来"三套方案"时，所有"不要重复、不要俗套、密度要对"的规则全靠 LLM 看到 prompt 里的 markdown 自己遵守。同一句提示词，跑两次，结果可能一个挺好一个烂。

这件事不紧急（不会让你当下崩），但是**它是你卖点和现实差最大的地方**。编辑智慧（288 条规则）那边你做得很好——有 Retriever、有硬门禁、有 retry 3 次失败阻断——那是"Python 真在跑"。把那套做法复制到反俗套这边（建 `ink_writer/creativity/` 模块，写 3 个 validator），一周时间，你的"反俗套"就从"PPT 级"升到"真能跑"。到时候别人抄你的词库，还是抄不走你的 validator。

---

**报告结束。**

21 条 F-XXX 问题（P0×3 / P1×9 / P2×7 / P3×2），建议按 Milestone A → B → C 推进，总工期约 36-41 人日。

v15 相较 v5 审计基线进步巨大（FIX-11/17/18 落地，SQL-first 到位，覆盖率 82%），但 step3_runner Phase A 被误作终点是最大的认知失准——建议下一轮 PRD 优先处理。
