# ink-writer Pro v9.0.0 项目级工程审查报告

**审查日期**：2026-04-03  
**审查范围**：仓库全量（架构、模块边界、配置、依赖、测试、发布链路）  
**审查方法**：静态分析 + 配置交叉验证 + 文件结构比对  

---

## 一、项目目标与成功标准

### 项目目标

ink-writer Pro 是一个**工业化长篇网文创作系统**，核心目标：

1. **自动化超长篇创作**：一条 `/ink-auto N` 命令批量生成章节（2200 字/章起步），支持百万字级连载
2. **质量不崩坏**：通过 14 个 AI Agent 组成的审查-修复闭环，解决 AI 写长篇时的记忆丢失、人设崩塌、AI 味过浓三大顽疾
3. **多平台分发**：作为 Claude Code Plugin / Gemini CLI Extension / Codex CLI Skill 三平台可用
4. **Harness-First 工程化**：v9.0 的核心哲学——不依赖模型能力提升，而是用确定性约束、状态机、计算型闸门把 Agent 变成可控系统

### 隐含成功标准

| 标准 | 判定依据 |
|------|---------|
| 新用户能在 10 分钟内从安装到出文 | README 安装流程 + `/ink-init` + `/ink-auto` 三步即达 |
| 写到 300 章不崩 | 25 张 SQLite 表 + 分层检查点（5/10/20 章） + 宏观审查 |
| 写出来不像 AI | anti-detection-checker + 200 词禁词表 + 6 层反检测 |
| 代码质量可维护 | 测试覆盖率 ≥90%，CI 自动验证 |

---

## 二、架构评估：是否支撑目标

### 架构概览

```
用户指令 → ink-auto（调度器）
           ├→ ink-plan（自动生成缺失大纲）
           └→ ink-write（单章 11 步流水线）
               ├→ context-agent（上下文构建）
               ├→ writer-agent（正文起草）
               ├→ 计算型闸门 Step 2C（确定性预检）
               ├→ 10 checker agents（并行审查）
               ├→ polish-agent（润色 + 追读力增强）
               └→ data-agent（实体提取 + 状态回写）
                   ├→ index.db（25 张 SQLite 表）
                   ├→ state.json（运行时状态）
                   └→ vectors.db（RAG 向量库）
```

### 架构判定：**基本合理，能支撑目标**

| 维度 | 评价 | 说明 |
|------|------|------|
| 写作流水线 | 优秀 | 11 步 DAG 设计成熟，有硬闸门（字数/安全/契约），能有效防崩 |
| Agent 编排 | 优秀 | 4 核心 + 10 审查分工清晰，checker 可并发 |
| 状态持久化 | 良好 | 三层存储（state.json / index.db / vectors.db）覆盖完整 |
| 多平台适配 | 有缺陷 | Gemini/Codex 适配文档未同步到 v9.0，版本漂移 |
| 测试与 CI | 有缺陷 | 测试代码完整但 CI 不跑测试，配置路径错位 |
| 发布链路 | 有缺陷 | 版本同步脚本遗漏 gemini-extension.json |

---

## 三、结构性问题清单

### 问题 1：CI 流水线不执行测试

**严重级别**：🔴 高

**证据**：
- `.github/workflows/plugin-version.yml`：仅运行 `sync_plugin_version.py --check`（版本一致性检查）
- `.github/workflows/plugin-release.yml`：仅运行版本校验 + 打 tag + 创建 Release
- 两条流水线均**不执行 `pytest`**
- 仓库有 23 个测试文件、7377 行测试代码、90% 覆盖率要求——全部靠本地手动执行

**影响**：
- PR 合并和版本发布没有自动化质量门禁
- 回归 bug 可能在不知不觉中进入主分支
- 90% 覆盖率要求形同虚设（无人强制执行）

**建议**：
新增一条 `ci-test.yml` workflow，在 push/PR 触发时执行 `pytest`。可复用现有 Python 3.11 环境，加一步 `pip install -r requirements.txt && pytest`。

---

### 问题 2：pytest / coverage 配置路径与仓库结构不一致

**严重级别**：🔴 高

**证据**：
- `pytest.ini` 第 2-3 行：
  ```ini
  testpaths = .claude/scripts/data_modules/tests
  pythonpath = .claude/scripts
  ```
- `.coveragerc` 第 2 行：
  ```ini
  source = .claude/scripts/data_modules
  ```
- `run_tests.ps1` 第 22 行：
  ```powershell
  $env:PYTHONPATH = ".claude/scripts"
  ```
- **实际仓库路径**为 `ink-writer/scripts/data_modules/tests/`，不是 `.claude/scripts/`
- `.claude/scripts/` 是 Claude Code **安装后**的运行时路径，仓库内不存在此目录

**影响**：
- 从仓库根目录执行 `pytest` 会因找不到测试目录而直接失败
- 新贡献者 clone 仓库后无法直接跑测试，必须理解「安装后路径映射」才能调试
- 如果 CI 要集成测试，必须先解决此路径问题

**建议**：
两套方案取其一：
1. **推荐**：在 pytest.ini 中使用仓库内实际路径 `ink-writer/scripts/data_modules/tests`，同步修改 `.coveragerc`
2. 在 CI 中通过软链接 `ln -s ink-writer .claude` 模拟安装后结构（不推荐，hack 味太重）

---

### 问题 3：版本同步脚本遗漏 gemini-extension.json

**严重级别**：🟡 中

**证据**：
- `gemini-extension.json` 第 4 行：`"version": "8.0.0"`
- `.claude-plugin/marketplace.json` 第 13 行：`"version": "9.0.0"`
- `ink-writer/.claude-plugin/plugin.json` 第 3 行：`"version": "9.0.0"`
- `sync_plugin_version.py` 第 12-13 行只定义了两个路径常量：
  ```python
  PLUGIN_JSON_PATH = ROOT / "ink-writer" / ".claude-plugin" / "plugin.json"
  MARKETPLACE_JSON_PATH = ROOT / ".claude-plugin" / "marketplace.json"
  ```
  **不包含 `gemini-extension.json`**
- CI workflow `plugin-version.yml` 的 `paths` 触发器也不包含 `gemini-extension.json`

**影响**：
- Gemini CLI 用户看到的版本号永远是 8.0.0，与实际功能不匹配
- 每次发版需要手动记住更新此文件，容易遗漏（已经遗漏了）

**建议**：
将 `gemini-extension.json` 加入 `sync_plugin_version.py` 的同步范围，并在 CI `paths` 触发器中加入此文件。

---

### 问题 4：多平台适配文档未同步到 v9.0

**严重级别**：🟡 中

**证据**：
- `GEMINI.md` 第 37 行仍将 `ink-5` 列为活跃 skill：
  ```
  | `ink-5` | 连续写 5 章 + 全量审查 | 日常批量创作 |
  ```
- `.codex/INSTALL.md` 第 69 行同样列出 `ink-5` 且无弃用标记
- 两份文档均**未提及 v9.0 新特性**：`ink-auto`、`ink-migrate`、计算型闸门、Reader Agent 升格
- GEMINI.md 第 63 行的限制说明仍针对旧架构：
  ```
  `ink-5` 的批量模式同样以串行方式运行每章的完整流程。
  ```

**影响**：
- Gemini/Codex 用户看到的是 v8.0 的使用指南，不知道 `ink-auto` 的存在
- 用户可能继续使用已弃用的 `ink-5`

**建议**：
统一更新 GEMINI.md 和 INSTALL.md：
1. 将 `ink-5` 标记为弃用，指向 `ink-auto 5`
2. 添加 `ink-auto`、`ink-migrate` 到命令列表
3. 补充 v9.0 新特性说明

---

### 问题 5：弃用 Skill（ink-5）仍保留在仓库中且无清理计划

**严重级别**：🟢 低

**证据**：
- `ink-writer/skills/ink-5/` 目录仍存在
- README.md 第 179 行标注了 `⚠️ 已由 ink-auto 5 取代`
- 但 GEMINI.md 和 INSTALL.md 中没有任何弃用标记
- 无移除时间表或 deprecation notice 文件

**影响**：
- 增加维护面积（skill 定义 + agent 调用矩阵中的额外条目）
- 新用户可能误用

**建议**：
- 在 ink-5 SKILL.md 顶部加一行硬重定向提示
- 定一个版本（如 v10.0）正式移除
- 统一在所有平台文档中标记弃用

---

### 问题 6：根目录堆积历史审查报告

**严重级别**：🟢 低

**证据**：
仓库根目录有 4 个旧的分析/审计报告文件：
```
ink-writer-全面分析报告.md          (30KB)
ink-writer-优化后分析报告.md        (23KB)
ink-writerPro-v7.0.6-全盘审计报告.md (12KB)
ink-writerPro-深度评审报告.md        (36KB)
ink-writerPro-优化路线图.md          (32KB)
```
合计 ~133KB，跨越 v7.0 到 v8.x 多个版本。

**影响**：
- 仓库根目录显得杂乱
- 新用户可能误以为是当前版本的有效文档
- 对仓库 clone 体积有轻微影响

**建议**：
移入 `docs/archive/` 子目录，或在下个大版本中移除。

---

### 问题 7：Dashboard 前端构建产物（dist/）提交到 Git

**严重级别**：🟢 低

**证据**：
- `.gitignore` 第 24-26 行**刻意豁免**了 dist 目录：
  ```
  dist/
  !ink-writer/dashboard/frontend/dist/
  !ink-writer/dashboard/frontend/dist/**
  ```
- Git 跟踪了 3 个构建产物文件：
  ```
  ink-writer/dashboard/frontend/dist/assets/index-D6050mjS.js
  ink-writer/dashboard/frontend/dist/assets/index-qVwzETG1.css
  ink-writer/dashboard/frontend/dist/index.html
  ```

**影响**：
- 这是**有意为之**（插件分发时用户不需要 `npm install && npm run build`），从用户体验角度合理
- 但如果前端有更新，需要手动 rebuild 后提交，容易遗漏源码改了但 dist 没更新的情况

**建议**：
当前做法对于插件分发是合理的。如果担心源码与 dist 不同步，可在 CI 中加一步 `npm run build && git diff --exit-code dist/` 检测漂移。

---

### 问题 8：无 conftest.py，测试缺少共享 fixture

**严重级别**：🟢 低

**证据**：
- `ink-writer/scripts/data_modules/tests/conftest.py` 不存在
- 23 个测试文件各自独立设置测试环境

**影响**：
- 测试间可能存在重复的 setup/teardown 逻辑
- 临时目录、mock state、测试数据库的创建可能不统一

**建议**：
提取公共 fixture（如临时项目目录、mock state.json、测试用 index.db）到 conftest.py。优先级低，在测试文件增多或出现重复问题时再做。

---

## 四、总体评价

### **部分合理**

架构设计成熟（11 步 DAG、14 Agent 编排、三层状态存储），核心写作流水线经过多版本迭代已经稳固。Harness-First 理念正确，计算型闸门和 Reader Agent 升格体现了工程化思维。

但**工程基础设施存在两个断层**：
1. **CI 不跑测试** — 有完整的测试代码和覆盖率要求，却没有自动化执行，质量门禁是空的
2. **测试配置路径错位** — 导致 CI 即使想跑测试也跑不起来，形成了鸡生蛋的死循环

这两个问题叠加意味着：**当前仓库的回归保护完全依赖开发者手动跑测试的自律性**。

---

## 五、最关键的 3 个问题

| 排名 | 问题 | 严重级别 | 核心风险 |
|:----:|------|:--------:|---------|
| 1 | CI 不执行测试 | 🔴 高 | 90% 覆盖率要求形同虚设，回归 bug 无门禁 |
| 2 | pytest/coverage 配置路径与仓库结构不一致 | 🔴 高 | 从仓库根目录无法直接跑测试，阻塞 CI 集成 |
| 3 | 版本同步脚本遗漏 gemini-extension.json | 🟡 中 | 已造成实际版本漂移（8.0.0 vs 9.0.0） |

---

## 六、最值得做的 3 个优化

| 排名 | 优化项 | 预期收益 | 工作量 |
|:----:|--------|---------|:------:|
| 1 | **新增 CI 测试 workflow + 修复 pytest 路径** | 一举解决 Top 1 和 Top 2 问题，打通自动化质量门禁 | 小（约 30 行配置） |
| 2 | **gemini-extension.json 加入版本同步** | 消除版本漂移，三平台版本永远一致 | 小（改 sync_plugin_version.py ~20 行） |
| 3 | **统一更新 GEMINI.md / INSTALL.md 到 v9.0** | Gemini/Codex 用户获得正确的使用指南 | 小（文档更新） |

---

## 七、先别乱动的地方

| 区域 | 原因 |
|------|------|
| **ink-write 的 11 步 DAG 流水线** | 核心写作管线，经过多版本打磨，闸门设计合理，改动风险大收益小 |
| **14 个 Agent 的 prompt 定义**（`agents/*.md`） | 经过大量实际写作验证和调优，微调可能引发不可预期的质量波动 |
| **index_manager.py 的 25 张表 schema** | 已有大量线上项目依赖此 schema，改动需要配套迁移工具 |
| **Dashboard 的 dist/ 提交策略** | 刻意为之的设计决策（免去用户 npm build），不是疏忽 |
| **scripts/ 的双重 import 兼容模式**（try/except ImportError） | 适配多运行上下文（插件模式 vs 直接运行），看着丑但有用 |

---

*审查完毕。以上所有结论均基于仓库当前状态的静态分析，未做任何代码修改。*
