# ink-auto 终极自动化模式设计

**Status**: Draft
**Date**: 2026-04-28
**Owner**: cipher-wb
**Scope**: ink-auto 单命令一书到底（init + plan + write 全自动串接）

## 0. 目标

把 `/ink-auto N` 升级成"一命令到底"：在任意状态的工作目录下执行，自动完成"项目初始化 → 卷大纲生成 → 写 N 章 → 跨卷自动续 plan"全流程，零或极少人为干预。

**非目标**：

- 不重做 ink-write/ink-plan/ink-init 内部逻辑（仅在 init 加 1 个新参数）。
- 不改变 CLI 子进程隔离架构（保持现状的进程级上下文清零）。
- 不修复全系统 `MIN_WORDS_FLOOR=2200` 与番茄平台默认 1500 字的矛盾（独立 follow-up，见 §7）。

## 1. 状态机

`/ink-auto N` 启动时按 `detect_project_state(CWD)` 分发到 5 个分支：

| 状态 | 判定条件 | 处理 |
|------|---------|------|
| **S0a** 未初始化 + 找到蓝本 | 无 `.ink/state.json` + CWD 顶层有非黑名单 `.md` | 读最大 `.md` → Quick 模式 + 蓝本覆盖 → 落盘后转 S1 |
| **S0b** 未初始化 + 空目录 | 无 `.ink/state.json` + CWD 无符合的 `.md` | 前台 7 题问答落盘 `.ink-auto-blueprint.md` → 同 S0a 后续流程 |
| **S1** 仅初始化无大纲 | 有 `.ink/state.json` 但 `大纲/` 空或缺当前章所属卷 | 自动 plan 当前章所在卷 → 转 S2 |
| **S2** 写作进行中 | 有 state.json + 有可用大纲 + 未完结 | 主循环（现有逻辑零改动）；遇缺卷大纲触发 S1 子流程 |
| **S3** 已完结 | `progress.is_completed == true` | 现有完结分支（零改动） |

```
                        /ink-auto N
                              │
                       detect_state()
              ┌──────┬───────┼───────┬──────┐
              ▼      ▼       ▼       ▼      ▼
             S0a   S0b      S1      S2     S3
              │     │        │       │      │
              ▼     ▼        ▼       ▼      ▼
            scan  ask7      plan   loop   完结
              │     │        │       │
              └──┬──┘        │       │
                 ▼           │       │
              init  ─────────┴───────┘
                 │
                 ▼
              主循环（现有零改动）
```

## 2. 组件清单

### 2.1 新增组件

| 编号 | 组件 | 类型 | 路径 | 职责 |
|------|------|------|------|------|
| **C1** | `state_detector.py` | 新增 Python | `ink_writer/core/auto/state_detector.py` | 输入 CWD，输出 `{S0_UNINIT, S1_NO_OUTLINE, S2_WRITING, S3_COMPLETED}` |
| **C2** | `blueprint_scanner.py` | 新增 Python | `ink_writer/core/auto/blueprint_scanner.py` | 扫 **CWD（用户执行命令的当前目录）顶层** `.md`，**不递归子目录**；黑名单过滤 + size 选最大；返回路径或 `None` |
| **C3** | `blueprint_to_quick_draft.py` | 新增 Python | `ink_writer/core/auto/blueprint_to_quick_draft.py` | `.md` 蓝本 → Quick `draft.json`；缺失字段标 `__AUTO__` |
| **C5** | `interactive_bootstrap.sh` | 新增 shell | `ink-writer/scripts/interactive_bootstrap.sh` | 空目录 7 题问答落盘 `.ink-auto-blueprint.md`。**纯 bash `read` 实现**（不走 CLI 子进程），跨平台一致；同步提供 `.ps1` 走 PowerShell `Read-Host`。 |
| **C7** | `蓝本模板.md` | 新增模板 | `ink-writer/templates/blueprint-template.md` | 用户参考模板（在 ink-init `--help` 注明） |

### 2.2 改造组件

| 编号 | 组件 | 路径 | 改造点 |
|------|------|------|--------|
| **C4** | ink-init `--blueprint <path>` 新参数 | `ink-writer/skills/ink-init/SKILL.md` | Quick 模式开头读蓝本 + 跳过 Quick Step 0.4 平台弹询问 + 用蓝本值覆盖 Quick Step 1 三方案对应字段 + 蓝本未提及字段照走 Quick 引擎 |
| **C6** | `ink-auto.sh` 状态分发 | `ink-writer/scripts/ink-auto.sh:188-191` | 把"未找到 .ink/state.json → exit 1"换成调用 C1，按状态分发 |

### 2.3 黑名单（C2 排除规则）

CWD 顶层 `.md` 命中以下任一规则即排除：

- 文件名（不区分大小写）：`README.md` / `CLAUDE.md` / `TODO.md` / `CHANGELOG.md` / `LICENSE.md` / `CONTRIBUTING.md` / `AGENTS.md` / `GEMINI.md`
- 文件名后缀：`*.draft.md`
- 路径含子目录（仅顶层扫描）

剩余候选取 `os.path.getsize` 最大者。

## 3. 数据流

### 3.1 场景 A（S0a）：找到蓝本

```
$ cd /book/我的修真          # 含「我的修真.md」
$ /ink-auto 100

[ink-auto.sh]
  ├─ C1: state=S0
  ├─ C2: scan → 我的修真.md (8.2KB)
  ├─ C3: parse → /tmp/blueprint_draft.json
  │           {platform:"qidian", aggression:2, 题材:"仙侠",
  │            主角:{...}, 金手指:{类型:"信息",...},
  │            __missing__:["女主","钩子1-3"]}
  ├─ 启动子进程: claude -p "ink-init --quick 2 \
  │              --platform qidian \
  │              --blueprint /tmp/blueprint_draft.json"
  │  └─[ink-init Quick]
  │     ├─ Step 0     WebSearch（起点榜单）
  │     ├─ Step 0.4   跳过平台弹询问（蓝本已锁）
  │     ├─ Step 1     生成 3 套方案（蓝本字段锁定，
  │     │                          __missing__ 走引擎）
  │     ├─ Step 1.5/6/7  金手指/语言档位/书名校验
  │     ├─ Step 2     自动选第 1 套（--blueprint 模式硬性）
  │     └─ Step 3     落盘 → INK_INIT_DONE
  ├─ 重读 state.json，状态升级 S0→S1
  ├─ 自动 plan 第 1 卷（现有逻辑）
  └─ 主循环 100 章（现有逻辑零改动）

产物: /book/我的修真/
       ├─ .ink/state.json
       ├─ 大纲/总纲.md, 卷1.md
       ├─ 设定集/...
       ├─ 正文/第001-100章.md
       ├─ 我的修真.md           （原蓝本，保留）
       └─ .ink-auto-blueprint.md（C3 派生副本）
```

### 3.2 场景 B（S0b）：空目录

```
$ cd /book/新书              # 空目录
$ /ink-auto 100

[ink-auto.sh]
  ├─ C1: state=S0
  ├─ C2: scan → None
  └─ C5 interactive_bootstrap
     ├─ 题1 题材方向？        ← 用户：仙侠
     ├─ 题2 主角人设？        ← 寒门弟子...
     ├─ 题3 金手指 8 选 1+一句话？← 信息：每读懂遗书...
     ├─ 题4 核心冲突？        ← 弃徒带真凶...
     ├─ 题5 平台？            ← qidian (默认)
     ├─ 题6 激进度？          ← 2 (默认)
     └─ 题7 目标章数？        ← 600 (默认)
  └─ 落盘 .ink-auto-blueprint.md → 同场景 A 后续流程
```

### 3.3 场景 C（S2 跨卷自动 plan）

**已被现有 ink-auto.sh 第 783-803 行覆盖，零改动。**

```
$ /ink-auto 10  (current=47, 卷1=1-50)
  ├─ i=1 第48章 → 大纲存在 → ✅
  ├─ i=2 第49章 → ✅
  ├─ i=3 第50章 → ✅
  ├─ i=4 第51章 → check-outline 失败
  │           → auto_plan_volume(2)（现有）
  │           → ✅ → 写第51章
  ├─ i=5..10 第52-57章 → ✅
```

## 4. 平台感知链路（已有 v26.2 全链路覆盖）

| 阶段 | 平台来源 | 影响 |
|------|---------|------|
| init Quick Step 0.4 / WebSearch | 蓝本 `平台` 字段或 7 题问答第 5 题 → `--platform` flag | 榜单源 + 默认参数（章数/字数/读者画像）|
| init 落盘 | 上一步 → `state.json.project_info.platform` | 持久化 |
| plan / write / review | 读 `state.json` | 章节字数/钩子密度/检查阈值按平台档 |

### 4.1 本 spec 新增的两条契约

**契约 ① C3**：
- 蓝本 `平台` 字段 → `draft.json.platform`
- `目标章数` / `目标字数` 留空时按平台默认填值（**不**让 Quick 引擎随机）：
  - qidian → 章数 600 / 字数 1,800,000 / 章长 3000
  - fanqie → 章数 800 / 字数 1,200,000 / 章长 1500

  默认值权威来源：`ink-writer/skills/ink-init/SKILL.md` Quick Step 0.4（v26.2 line 91-104）。任何变更须同步 ink-init SKILL.md 与本 spec C3 实现。

**契约 ② C4**：
- `--blueprint` 提供时强制跳过 Quick Step 0.4 弹询问
- 蓝本 `平台` 字段为空 → 默认 qidian（不弹询问，避免阻塞无人值守）

## 5. 错误处理矩阵

| 失败场景 | 行为 |
|---------|------|
| 蓝本 `.md` 解析失败（YAML/字段格式错） | 中止，输出具体行号；**不**回退到 7 题问答 |
| 蓝本必填字段缺失（题材/主角人设/金手指类型/金手指能力） | 提示哪几项缺；**不**回退到 7 题问答（用户既已写蓝本就是有意图） |
| 蓝本字段命中黑名单（金手指禁词、书名禁词） | 中止，输出命中规则；让用户改蓝本 |
| init 子进程失败（Quick 降档失败 / API 超时） | 中止，保留 `.ink-auto-blueprint.md`，输出 init 日志路径 |
| 7 题问答中用户 Ctrl+C | 中止，**不**保留半成品蓝本 |
| auto-plan 失败（已有逻辑） | 中止批量写作（保持） |
| 章节写作失败（已有逻辑） | 重试 1 次 → 仍失败中止（保持） |

## 6. 回滚开关

| 环境变量 | 默认 | 关闭后行为 |
|---------|------|-----------|
| `INK_AUTO_INIT_ENABLED` | `1` | `0` → 退化到现状（state.json 缺失 → exit 1） |
| `INK_AUTO_BLUEPRINT_ENABLED` | `1` | `0` → 跳过蓝本扫描，蓝本 `.md` 也走 7 题 |
| `INK_AUTO_INTERACTIVE_BOOTSTRAP_ENABLED` | `1` | `0` → 空目录直接报错，强制要求蓝本 `.md` |

最严格组合：`BLUEPRINT_ENABLED=0 + INTERACTIVE_BOOTSTRAP_ENABLED=0` ≡ 现状。

## 7. 已知未解决问题（非本 spec 范围）

### 7.1 番茄字数下限矛盾

**现象**：`ink-init` Quick Step 0.4 声明 fanqie 默认 `chapter_word_count=1500`，但全系统 `MIN_WORDS_FLOOR=2200` 硬红线（落在 6 处）会把 fanqie 项目的实际章节字数拉到 2200+，与"番茄 1500 字/章下沉市场"定位不符。

**牵涉文件**：

- `ink_writer/core/preferences.py::MIN_WORDS_FLOOR`
- `references/preferences-schema.md` §硬下限红线
- `agents/writer-agent.md:505`
- `scripts/computational_checks.py:89,687`
- `scripts/extract_chapter_context.py:64`
- `scripts/ink-auto.sh:222,537`

**为何不在本 spec 解决**：

1. 范围错配：本 spec 主题是"无人值守串流水线"，番茄字数下限是"平台分档定义"，混合会让评审失焦。
2. 风险等级：本 spec 改新增组件 + 1 处分发逻辑，回归面小；番茄字数下限改全系统硬红线，需独立回归。
3. 决策点：是否完全废弃系统级硬下限改成平台档位驱动？是否引入新红线 1500？这些应在独立 spec 决策。

**建议跟进**：在 `2026-04-27-fanqie-platform-mode-design.md` 后续版本或新独立 spec 中处理。

## 8. 测试方案

### 8.1 Unit（pytest）

| 测试目标 | fixture |
|---------|---------|
| C1 4 种状态枚举 | tmp_path × 4 |
| C2 黑名单过滤 + size 最大 | README + idea(2KB) + setup(8KB) → setup |
| C2 子目录排除 | 顶层 idea.md + `docs/extra.md` → 仅 idea |
| C3 完整字段映射 | 完整蓝本 → 全字段填充 |
| C3 缺失字段标记 | 半空蓝本 → `__missing__` 数组 |
| C3 黑名单命中 | 金手指写"修为暴涨" → `BlueprintValidationError` |

### 8.2 Integration

| 场景 | 验证 |
|------|------|
| 端到端 S0a：放置蓝本 → `/ink-auto 1` → 写完第 1 章 | `.ink/state.json` 存在 + 第001章字数 ≥ 2200 |
| 端到端 S0b：空目录 + mock 7 题 → `/ink-auto 1` | 同上 + `.ink-auto-blueprint.md` 落盘 |
| 跨卷自动 plan：S2 写满第 1 卷 → 触发 plan vol 2 | 现有测试套已覆盖，新增 trace 验证 |
| 回归：原有 S2 启动路径不退化 | 现有测试套全过 |

### 8.3 手动验收

- 真实跑 S0a：放蓝本 → `/ink-auto 5` → 检查产物
- 真实跑 S0b：空目录 → `/ink-auto 3` → 检查 7 题问答 + 产物
- 真实跑 S0a fanqie：蓝本里 platform=fanqie → 检查 state.json.platform 落地正确（**字数下限矛盾按 §7 已知问题处理，不阻塞 spec**）

## 9. 实现工作量估算

| 组件 | 复杂度 | 行数估 |
|------|--------|--------|
| C1 state_detector | 低 | ~80 |
| C2 blueprint_scanner | 低 | ~60 |
| C3 blueprint_to_quick_draft | 中 | ~250（YAML 解析 + 字段映射 + 黑名单校验） |
| C4 ink-init `--blueprint` 接入 | 中 | SKILL.md +50 行 + Quick 流程 patch |
| C5 interactive_bootstrap.sh | 低 | ~100（含 PowerShell sibling） |
| C6 ink-auto.sh 状态分发 | 低 | +~80 |
| C7 模板归档 | 极低 | 复制即用 |
| Unit 测试 | 中 | ~400 |
| Integration 测试 | 中 | ~200 |
| **总计** | | **~1200 行** |

## 10. 兼容性

- **Mac/Linux**：所有 `.sh` 保持字节级兼容；新增 `interactive_bootstrap.sh` 同步出 `.ps1` + `.cmd`（Windows 守则）。
- **跨 CLI**：claude / gemini / codex 三平台均支持。C5 走纯 bash `read`，与 CLI 平台无关（与现有 `ink-auto.sh` 风格一致）。init 子进程根据现有 `PLATFORM` 检测分别调用 `claude -p` / `gemini --yolo` / `codex --approval-mode full-auto`。
- **现有项目**：S2 路径零改动，已写到一半的项目升级后行为完全一致。

## 11. 推出节奏

| 阶段 | 内容 |
|------|------|
| **P0** | C1+C2+C3 + Unit 测试（不改 ink-auto.sh，可独立验证） |
| **P1** | C4（ink-init `--blueprint` 参数）+ Integration 测试 S0a |
| **P2** | C5（interactive_bootstrap）+ Integration 测试 S0b |
| **P3** | C6（ink-auto.sh 状态分发）+ 端到端手动验收 |
| **P4** | 文档（C7 + ink-init 帮助 + ink-auto SKILL.md 更新） |

每阶段独立可合并；P0-P2 通过回滚开关可临时关闭，不影响 S2 现有路径。
