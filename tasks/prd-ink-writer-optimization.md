# PRD: Ink Writer 效率优化与项目瘦身

## Introduction

对 Ink Writer Pro 进行四项优化：(1) 用快速随机生成模式替换 ink-init 的苏格拉底式提问流程，一次生成 3 套完整小说方案供用户选择，大幅提升项目初始化效率；(2) 构建防重复、有艺术感的角色命名系统，解决 AI 生成小说角色名高度雷同的问题（如反复出现"林默""苏婉清"）；(3) 清理项目中积累的旧版审查报告和日志等非运行必需文件；(4) 面向用户重写 README。

## Goals

- 新增 `--quick` 快速模式，将 ink-init 项目初始化从 10+ 轮对话缩减至 1-2 轮（选择方案 + 确认），同时保留原有深度提问模式
- 消除角色命名重复问题，通过丰富的命名库和随机性确保角色名有艺术感且不千篇一律
- 删除项目及 marketplace 目录中的旧版审查报告、日志等非必需文件
- README 面向小说作者重写，突出功能介绍和快速上手

## User Stories

### US-001: 新增快速随机生成模式（与苏格拉底模式共存）

**Description:** 作为小说作者，我希望 ink-init 支持两种模式：默认仍为苏格拉底式深度提问；当我传入 `--quick` 参数时，直接生成 3 套完整方案供选择，不满意可重新随机，让我能根据需要选择效率优先或深度优先。

**Acceptance Criteria:**
- [ ] `/ink-init` 不带参数时，保留原有苏格拉底式提问流程不变
- [ ] `/ink-init --quick` 进入快速随机模式，直接生成 3 套完整方案
- [ ] 每套方案包含：书名、题材方向、核心卖点、主角姓名+设定、女主/核心配角姓名+设定、核心冲突、金手指概要、前三章钩子概念
- [ ] 用户通过选择编号（1/2/3）确定方案，选择后直接进入大纲生成流程
- [ ] 支持混搭模式：用户可指定"1的书名 + 2的主角 + 3的冲突"等自由组合，系统自动合并为最终方案
- [ ] 用户全部不满意时，输入"重新随机"或编号 0，系统重新生成 3 套全新方案（不限重随次数）
- [ ] 3 套方案之间在题材方向、角色设定、冲突模式上有明显差异化
- [ ] 方案生成时自动调用防重复命名系统（US-002），确保角色名不落俗套
- [ ] 用户选择/混搭方案后，系统基于最终方案自动填充 state.json、preferences.json 等初始化文件
- [ ] 保留 genre anti-trope 参考文件的加载能力（L2 层），供方案生成时使用

### US-002: 防重复角色命名系统

**Description:** 作为小说作者，我希望每次创建新小说时角色名字都独特且有艺术感，不再反复出现"林默""苏婉清"等 AI 偏好的高频名字。

**Acceptance Criteria:**
- [ ] 创建命名黑名单文件 `data/naming/blacklist.json`，预置 AI 高频重复名字（林默、苏婉清、陆辰、沈清月、叶辰、萧寒、顾念、林羽等至少 50 个）
- [ ] 创建多维度姓氏库 `data/naming/surnames.json`，按稀有度分层：常见姓（20%概率）、中频姓（40%概率）、稀有姓（30%概率）、复姓（10%概率），总量不少于 200 个
- [ ] 创建名字素材库 `data/naming/given_names.json`，按风格分类：古风典雅、现代简约、江湖豪放、书卷气质、冷峻凌厉等至少 5 种风格，每种风格不少于 100 个字/词素
- [ ] 命名时根据角色性别、性格标签、题材风格自动匹配合适的姓氏+名字组合
- [ ] 生成的名字需通过黑名单校验 — 与黑名单中任何名字的姓或名完全相同则重新生成
- [ ] 同一本书内角色名字的姓氏不重复（除非有剧情需要的亲属关系）
- [ ] 名字需符合中文命名逻辑：姓+名 2-3 字为主，避免生僻到无法阅读的字

### US-003: 项目文件清理

**Description:** 作为开发者，我希望删除项目中积累的旧版审查报告、日志和非必需文件，保持项目目录整洁。

**Acceptance Criteria:**
- [ ] 删除主项目根目录下所有 `工程审查报告_v*.md` 文件（v9.7.0 ~ v9.16.0，共 8 个）
- [ ] 删除 `data/editor-wisdom/` 下的日志和报告文件：`errors.log`、`skipped.log`、`classify_report.md`、`cleanup_report.md`
- [ ] 保留 `reports/` 目录下最新版报告（如 v13_acceptance.md），删除过时的审计报告
- [ ] 保留 `archive/` 目录（适度清理策略）
- [ ] 清理 marketplace 目录 `/Users/cipher/.claude/plugins/marketplaces/ink-writer-marketplace/`：
  - 删除根目录下所有 `工程审查报告_v*.md`
  - 删除 `reports/` 下的审查报告（`ralph-editor-wisdom-review.md`、`architecture_audit.md`）
  - 删除 `docs/archive/` 下所有旧版工程审计报告（`ENGINEERING_AUDIT_*.md` 等历史分析报告）
  - 保留 symlink `ink-writer/` 和核心配置文件
- [ ] 清理后项目仍可正常运行（`python -c "import ink_writer"` 成功）
- [ ] 清理后所有 skill 仍可正常加载

### US-004: README 面向用户重写

**Description:** 作为小说作者（用户），我希望 README 清晰告诉我这个工具能做什么、怎么安装、怎么用，而不是堆砌技术架构细节。

**Acceptance Criteria:**
- [ ] README 以用户视角重写，核心结构：一句话介绍 > 功能亮点 > 安装方法 > 快速上手（5 分钟写出第一章）> 核心命令速查表 > FAQ
- [ ] 功能亮点部分用具体场景说明，而非罗列技术组件（如"一条命令自动写 10 章并审查修复"而非"14 个 AI Agent"）
- [ ] 安装方法覆盖 Claude Code（推荐）、Gemini CLI、Codex CLI 三种方式
- [ ] 快速上手部分提供从 ink-init 到 ink-write 的完整示例流程
- [ ] 核心命令速查表列出所有 /ink-* 命令及一句话说明
- [ ] 版本号更新为当前最新版本
- [ ] 总长度控制在 200 行以内，简洁有力

## Functional Requirements

- FR-1: ink-init SKILL.md 新增 `--quick` 参数分支：带参数走"生成 3 套方案 → 选择/混搭/重随 → 自动初始化"流程，不带参数走原有苏格拉底提问流程
- FR-2: 方案生成 prompt 需引用 genre anti-trope 参考文件，确保方案有创意且不落俗套
- FR-3: 每套方案输出格式统一为结构化 markdown，包含书名、题材、主角、配角、冲突、金手指、前三章钩子共 7 个维度
- FR-3.1: 支持混搭选择 — 用户可从不同方案中挑选各维度自由组合，系统合并后进入初始化
- FR-4: 命名系统作为独立数据模块存放在 `data/naming/` 目录，包含 blacklist.json、surnames.json、given_names.json 三个文件
- FR-5: 命名系统在 ink-init 方案生成和 ink-write 新角色创建时均被调用
- FR-6: 黑名单支持用户手动追加（JSON 数组格式，无需代码修改）
- FR-7: 文件清理通过一次性脚本或手动删除完成，不需要持久化的清理机制
- FR-8: README 使用 v13.x 版本号，反映快速随机生成等新特性

## Non-Goals

- 不实现 Web UI 或可视化方案选择界面
- 不实现角色名自动翻译或多语言支持
- 不重构 ink-write、ink-plan 等其他 skill 的流程
- 不迁移 marketplace 目录结构或改变 symlink 方式
- 不添加自动化定期清理机制（一次性清理即可）
- 不实现基于 AI 的名字语义分析（仅用规则+库匹配）

## Technical Considerations

- ink-init SKILL.md 是纯 markdown 格式的 skill 定义文件，修改时需保持 frontmatter 和工具声明格式
- 命名数据文件使用 JSON 格式，便于 skill prompt 中直接 Read 加载
- 姓氏和名字素材库需考虑文件大小 — JSON 格式下 200 姓 + 500 名字素材约 20KB，在 prompt context 中可接受
- marketplace 的 `ink-writer/` 是 symlink，清理时不能误删 symlink 指向的源文件
- 命名系统的核心目标是随机性而非跨项目去重 — 通过足够大的命名库+随机抽取+黑名单过滤实现多样性

## Success Metrics

- ink-init 全流程从启动到大纲生成完成，对话轮次 <= 3 轮
- 连续初始化 5 个项目，主角名字零重复
- 项目根目录文件数减少 8+ 个（删除旧审查报告）
- README 行数 <= 200 行，新用户阅读后 5 分钟内可启动第一次写作

## Open Questions

- 命名黑名单是否需要区分男名/女名分别维护？
