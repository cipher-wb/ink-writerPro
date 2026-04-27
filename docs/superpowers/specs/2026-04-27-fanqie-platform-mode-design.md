# 番茄小说平台模式 — 全链路设计

> 状态：已确认 | 日期：2026-04-27 | 关联：ink-init / ink-plan / ink-write / ink-auto / all checkers

## 一、目标

在现有起点模式基础上新增「番茄小说」平台模式。用户在 `/ink-init` 时选择平台，标记写入 `state.json`，下游全链路（plan → write → auto → review → polish）按平台区分配置和行为。

## 二、平台枚举与存储

### 2.1 枚举

| key | label | 读者画像 | 商业模式 |
|-----|-------|----------|----------|
| `qidian` | 起点中文网 | 25-35岁男性老白读者 | 付费订阅 |
| `fanqie` | 番茄小说 | 35-55岁下沉市场男性 | 免费+广告分账 |

### 2.2 存储位置

`state.json` → `project_info`：

```json
{
  "platform": "qidian",
  "platform_label": "起点中文网"
}
```

### 2.3 读取方式

所有下游（plan/write/auto/checker/polish）通过 context-agent 读取 `.ink/state.json` 获取 `platform`。若 `platform` 缺失 → 阻断并提示"项目未标记平台，请重新运行 /ink-init"。

### 2.4 存量迁移

- `platform` 为空 → 默认 `qidian`，自动写入 `platform_migrated: true` + `migration_date`
- `platform` = "起点" / "起点中文网" → 自动映射 `qidian`
- 静默处理，不弹窗

## 三、init 流程改造

### 3.1 Deep Mode — Step 1 追加平台选择

在题材和目标规模收集完后，弹出 `AskUserQuestion`：

```
题干：目标发布平台？
选项：
- 起点中文网（长篇付费，3000-3500字/章，老白读者）
- 番茄小说（免费广告，1500-2000字/章，下沉市场）
```

### 3.2 平台默认值映射

用户选择后自动写入以下默认值（用户后续可覆盖）：

| 参数 | qidian | fanqie |
|------|--------|--------|
| `target_chapters` | 600 | 800 |
| `target_words` | 2,000,000 | 1,200,000 |
| `chapter_word_count` | 3000 | 1500 |
| `target_reader` | 25-35岁男性老白读者 | 35-55岁下沉市场男性 |

### 3.3 Quick Mode 改造

Quick Step 0.5 之前弹出平台选择。WebSearch 按平台分流：番茄项目只搜 `番茄小说 爆款 套路 2026` + `番茄免费小说 热门 新书`；起点项目只搜起点榜单。`market_avoid` 从对应平台数据中提取。

### 3.4 Step 99 策划期审查适配

`genre-novelty` checker 的 top200 对比池按平台切换：`fanqie` → 番茄 top200（一期复用起点数据 + 标记 `source=qidian_fallback`）。

## 四、plan 流程

### 4.1 chapter-planning.md 按平台分节

同一文件内部按平台组织，不创建独立平台文件：

```markdown
## 3. 章节字数控制

### 起点中文网
- 标准字数: 3000字/章
- 字数分配: 开头10% + 发展50% + 高潮33% + 结尾7%

### 番茄小说
- 标准字数: 1500字/章
- 字数分配: 开头15% + 冲突升级40% + 爽点爆发35% + 钩子10%
- 硬约束: 每500字至少1个小爽点
- 冲突模式: "看不起我→我亮身份→你跪下"循环
```

### 4.2 大纲粒度

- **起点**：精确到章内 4 段结构（开头→发展→高潮→结尾）
- **番茄**：粗粒度（本章冲突 + 爽点类型 + 章末钩子），因章节短节奏快，过细大纲限制 LLM 直白爆发力

### 4.3 钩子密度骨架检查

番茄模式下，`chapter-hook-density-checker` 的 `block_threshold` 从 0.70 提高到 0.85。

## 五、write 流程

### 5.1 创作执行包注入

context-agent 产出创作执行包时注入平台参数，writer-agent 本身不改：

| 注入字段 | qidian | fanqie |
|----------|--------|--------|
| `target_chapter_words` | 3000 | 1500 |
| `cool_point_interval` | 1000字/个 | 500字/个 |
| `conflict_style` | 多层次/有谋略 | 直白打脸循环 |
| `hook_requirement` | 章末强钩子 | 章末必须有悬念，否则阻断 |
| `dialogue_ratio` | ≥30% | ≥40% |
| `narration_style` | 可适度描写 | 少描写多动作 |

### 5.2 章末钩子硬阻断（番茄专属）

writer-agent 产出草稿后，polish 之前，规则检查章末 100 字是否包含钩子信号（悬念句 / 未闭合问题 / 反转预告 / 情绪高点）。不通过 → 退回 writer-agent 重写章末段落。起点不做此检查。

## 六、auto 流程

auto 本身不改。它是 plan → write → review → polish 的编排器，平台差异已下沉到各阶段。auto 仅在启动时从 `state.json` 读取 `platform` 并传递给每个子步骤。

## 七、Checker 全量适配

### 7.1 A 组 — 阈值不同（改 config 即可，7 个）

| Checker | qidian | fanqie | 原因 |
|---------|--------|--------|------|
| high-point-checker | 密度 0.6 | 密度 0.85 | 番茄爽点密度翻倍 |
| reader-pull-checker | 标准钩子 | 钩子强制+每章评估 | 番茄不钩就划走 |
| golden-three-checker | 300字触发窗口 | 200字触发窗口 | 番茄章短触发更快 |
| directness-checker | 7维标准 | 白话度门槛更高 | 下沉用户 |
| colloquial-checker | 5维标准 | 白话度门禁更严 | 广场舞大妈能懂 |
| emotion-curve-checker | 标准曲线 | 高频小波动 | 每500字需情绪点 |
| pacing-checker | 标准节奏 | 快节奏权重更高 | 碎片化阅读 |

### 7.2 B 组 — 逻辑不同（需改 checker 逻辑，3 个）

| Checker | 差异 |
|----------|------|
| prose-impact-checker | fanqie 降低"镜头多样性"权重，提高"动词锐度"权重（少描写多动作） |
| anti-detection-checker | fanqie 追加检测"过于文艺的句子"（下沉用户看不懂的表达 = AI味） |
| editor-wisdom-checker | fanqie 注入不同规则集（家庭伦理冲突 / 打脸循环 / 身份掉马） |

### 7.3 C 组 — 平台无关不改

logic-checker、consistency-checker、continuity-checker、ooc-checker、proofreading-checker、sensory-immersion-checker、thread-lifecycle-tracker、outline-compliance-checker、protagonist-agency-checker、conflict-skeleton-checker、flow-naturalness-checker、chapter-hook-density-checker、genre-novelty-checker、golden-finger-spec-checker、golden-finger-timing-checker、naming-style-checker、protagonist-motive-checker、protagonist-agency-skeleton-checker、live-review-checker。

## 八、Prose Anti-AI 适配

### 8.1 colloquial 最低档位

番茄模式下 `colloquial` 自动锁定为"激进"档，不可下调。

### 8.2 anti-detection 追加规则

番茄模式下 `zero_tolerance_rules` 追加一条：**禁用超过 25 字的复合修饰句**（起点不限制）。

### 8.3 开关控制

三个子开关（`colloquial.yaml` / `anti-detection.yaml` / `parallel-pipeline.yaml`）在番茄模式下各自独立，不受平台影响。但 `colloquial` 的档位选择在番茄模式下只读。

## 九、配置文件平台维度格式

### 9.1 Schema

需要平台区分的 YAML 配置统一使用内嵌结构：

```yaml
# 平台相关参数
platforms:
  qidian:
    high_point_density: 0.6
    cool_point_interval: 1000
  fanqie:
    high_point_density: 0.85
    cool_point_interval: 500

# 平台无关参数留在顶层
logic_gap_tolerance: 2
```

### 9.2 读取逻辑

`load_config(platform)` 从 `platforms.<platform>` 取值，fallback 到顶层默认值。平台无关的 checker 不改动。

### 9.3 需要改造的配置文件清单

| 文件 | 改造类型 |
|------|----------|
| `checker-thresholds.yaml` | A 组 — 加 `platforms` 块 |
| `reader-pull.yaml` | A 组 — 加 `platforms` 块 |
| `emotion-curve.yaml` | A 组 — 加 `platforms` 块 |
| `colloquial.yaml` | A 组 + 番茄锁定激进档 |
| `anti-detection.yaml` | B 组 — 追加番茄规则 |
| `editor-wisdom.yaml` | B 组 — 追加番茄规则集 |
| `high-point-scheduler.yaml` | A 组 — 加 `platforms` 块 |
| `ink_writer/prose/directness_threshold_gates.py` | A 组 — 模块内阈值按平台分支 |
| `ink_writer/prose/colloquial_checker.py` | A 组 — 白话度门禁按平台调参 |
| pacing-checker / strand-weave（Python 模块内阈值） | A 组 — 快节奏权重按平台调参 |

## 十、SKILL.md 修改清单

| 文件 | 改动 |
|------|------|
| `ink-init/SKILL.md` | Deep Step 1 追加平台选择；Quick Mode 追加平台选择 + WebSearch 分流 |
| `ink-plan/SKILL.md` | 所有硬编码"3000字"替换为"按平台读取"；引用 `chapter-planning.md` 的平台分节 |
| `ink-plan/references/outlining/chapter-planning.md` | 第 3 节按平台分节；所有模板字数标注平台差异 |
| `ink-plan/references/outlining/outline-structure.md` | 字数检查改为平台感知 |
| `ink-write/SKILL.md` | 创作执行包字段按平台注入 |
| `ink-auto/SKILL.md` | 启动时读取 platform 传递给子步骤 |
| `ink-init/references/creativity/market-positioning.md` | 番茄读者画像更新为 35-55 岁下沉市场 |

## 十一、实施顺序

1. **config 层**：所有配置文件的 `platforms` 块
2. **state.json 读写**：`init_project.py` 平台枚举 + 存量迁移
3. **init 流程**：SKILL.md + 平台选择交互
4. **plan 流程**：reference 文件按平台分节
5. **write 流程**：context-agent 注入 + 章末钩子硬阻断
6. **checker 适配**：A 组 config → B 组逻辑 → C 组确认不改
7. **Prose Anti-AI**：colloquial 锁定 + anti-detection 追加规则
8. **auto 流程**：platform 传递
9. **存量迁移**：自动静默迁移逻辑
10. **集成测试**：两条平台链路端到端验证

## 十二、回滚策略

- `state.json` 的 `platform` 字段可手动改为 `qidian` 恢复起点行为
- 各配置文件的 `platforms` 块不影响存量项目（`platform=qidian` 读取的值与当前一致）
- 番茄专属的逻辑分支（章末钩子阻断、colloquial 锁定）在 `platform=qidian` 时完全不触发
