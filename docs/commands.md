# 命令详解

## 命令分级（v9.0）

v9.0 将命令分为两层：**主入口**（日常使用）和**高级命令**（调试/精细控制）。

### 主入口（4 个）

| 命令 | 用途 | 使用频率 |
|------|------|---------|
| `/ink-init` | 创建项目 | 一次 |
| `/ink-auto N` | 全自动写 N 章 | 每天 |
| `/ink-resume` | 中断恢复 | 偶尔 |
| `/ink-migrate` | 旧项目升级到 v9.0 | 一次 |

### 高级命令

日常不需要。`ink-auto` 内部会自动调用这些。

---

## `/ink-init`

**级别**：主入口

用途：交互式初始化小说项目（书名、题材、角色、世界观、力量体系）。

产出：

- `.ink/state.json`
- `.ink/index.db`
- `设定集/`
- `大纲/总纲.md`

```bash
/ink-init
```

## `/ink-auto [N]`

**级别**：主入口

用途：全自动写 N 章（默认 5），内置智能检查点、自动审查修复、自动大纲生成。

```bash
/ink-auto        # 默认写 5 章
/ink-auto 10     # 写 10 章
/ink-auto 100    # 写 100 章（通宵服务）
```

### 内置检查点

| 触发 | 操作 |
|------|------|
| 每 5 章 | 核心审查（5 个 checker）+ 自动修复 |
| 每 10 章 | + 数据审计 |
| 每 20 章 | + 宏观审查 + 深度修复 |

### v9.0 增强

- **计算型闸门**（Step 2C）：每章正文完成后自动检查字数、命名、伏笔逾期等
- **Reader Verdict**：每章输出 7 维追读力评分，分数不够自动增强
- **增强报告**：完成后输出质量趋势、追读力信号、伏笔债务

### 环境变量

| 变量 | 说明 | 默认 |
|------|------|------|
| `INK_AUTO_COOLDOWN` | 章节间冷却秒数 | 10 |
| `INK_AUTO_CHECKPOINT_COOLDOWN` | 检查点间冷却秒数 | 15 |

## `/ink-resume`

**级别**：主入口

用途：任务中断后自动识别断点并恢复。

```bash
/ink-resume
```

## `/ink-migrate`

**级别**：主入口（v9.0 新增）

用途：将 v8.x 项目迁移到 v9.0 Harness-First 架构。

```bash
/ink-migrate
```

三阶段自动执行：
1. **资产发现**：只读扫描章节、摘要、大纲、审查报告
2. **Schema 迁移**：自动备份 → state.json v6→v7 → index.db 建新表
3. **迁移审计**：生成审计报告，列出需要人工确认的项

详见 [v9.0 升级指南](v9-upgrade-guide.md)。

---

## 高级命令

### `/ink-write`

用途：执行单章完整创作流程（11 步流水线）。

```bash
/ink-write       # 写下一章
```

### `/ink-plan [卷号]`

用途：生成卷级规划与章节大纲。

```bash
/ink-plan 1      # 生成第 1 卷大纲
/ink-plan 2-3    # 生成第 2-3 卷
```

### `/ink-review [范围]`

用途：对章节做多维质量审查。

```bash
/ink-review 1-5  # 审查第 1-5 章
/ink-review 45   # 审查第 45 章
```

审查深度：
- **Core**：consistency + continuity + OOC + reader-pull + reader-simulator（快速）
- **Full**：Core + high-point + pacing + proofreading + golden-three
- **Full+**：Full + reader-simulator（完整）+ anti-detection

### `/ink-audit`

用途：检查 state.json 与 index.db 数据一致性。

```bash
/ink-audit           # 标准审计
/ink-audit quick     # 快速审计
```

### `/ink-macro-review`

用途：宏观结构审查（支线健康、角色弧光、承诺审计、风格漂移）。

```bash
/ink-macro-review
```

### `/ink-query [关键词]`

用途：查询角色、伏笔、节奏、状态等运行时信息。

```bash
/ink-query 萧炎
/ink-query 伏笔
/ink-query 紧急
```

### `/ink-resolve`

用途：处理 AI 无法确定的实体消歧（唯一需要人工操作的命令）。

```bash
/ink-resolve
```

### `/ink-learn`

用途：从当前会话提取可复用写作模式，写入项目记忆。

```bash
/ink-learn
```

### `/ink-dashboard`

用途：启动只读可视化面板。

```bash
/ink-dashboard
```

### `/ink-5`（已弃用）

> **已由 `/ink-auto 5` 取代。** `/ink-auto` 更智能、更持久、更省心。
