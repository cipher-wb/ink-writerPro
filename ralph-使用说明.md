# Ralph 中文使用说明书

> Ralph 是一个自主 AI 编码循环器：把 PRD 拆成小任务，每次迭代开一个"全新上下文"的 AI 实例（Amp 或 Claude Code）完成一条 user story，跑完质量检查后自动 commit，直到所有任务 `passes: true`。
> 记忆不靠上下文，靠三样东西：**git 历史 + `progress.txt` + `prd.json`**。

---

## 1. 当前环境状态（已替你检查）

| 依赖 | 状态 | 备注 |
|---|---|---|
| `jq` | ✅ 已安装 | `/usr/bin/jq` |
| `claude` (Claude Code CLI) | ✅ 已安装 | `/Users/cipher/.local/bin/claude` |
| `amp` (Amp CLI) | ❌ 未安装 | 非必需，用 `--tool claude` 即可 |
| `~/.claude/skills/prd` | ✅ 已安装 | 与仓库版本一致 |
| `~/.claude/skills/ralph` | ✅ 已安装 | 与仓库版本一致 |
| 本地 clone | ✅ `./ralph/` | 位于 `ink-writer/ralph/` |

**结论**：你已经可以直接使用 `/prd` 和 `/ralph` 两个 slash command。不需要再安装。

---

## 2. Ralph 的核心思想（3 句话）

1. **每次迭代 = 全新 AI 实例**，没有上下文污染。
2. **任务必须足够小**（一个上下文窗口内能做完），否则会崩。
3. **反馈回路是生命线**：typecheck / lint / test 必须能跑，否则坏代码会累积。

---

## 3. 标准三步工作流

### Step 1 — 写 PRD（产品需求文档）

在 Claude Code 里说：

```
Load the prd skill and create a PRD for 我要实现 XXX 功能
```

或直接 `/prd`。Skill 会用苏格拉底式提问帮你澄清需求，产物保存到 `tasks/prd-[feature-name].md`。

### Step 2 — 把 PRD 转成 Ralph 用的 JSON

```
Load the ralph skill and convert tasks/prd-xxx.md to prd.json
```

或直接 `/ralph`。产物是 `prd.json`，含一组 `userStories`，每条带 `passes: false`。

`prd.json` 里的 `branchName` 字段决定 Ralph 会在哪个 git 分支上工作（没有会自动从 main 切出）。

### Step 3 — 启动 Ralph 循环

把 `ralph.sh` 拷到项目里（如果还没做）：

```bash
mkdir -p scripts/ralph
cp ralph/ralph.sh scripts/ralph/
cp ralph/CLAUDE.md scripts/ralph/CLAUDE.md   # Claude Code 的提示词模板
chmod +x scripts/ralph/ralph.sh
```

跑起来：

```bash
# 默认 10 轮，用 Claude Code
./scripts/ralph/ralph.sh --tool claude

# 指定 30 轮
./scripts/ralph/ralph.sh --tool claude 30
```

每轮 Ralph 会：
1. 切/建分支 → 2. 挑优先级最高且 `passes:false` 的 story → 3. 实现它 → 4. 跑质量检查 → 5. 通过则 commit → 6. 把该 story 标记 `passes:true` → 7. 往 `progress.txt` 追加学到的东西 → 8. 下一轮。

全部 story 完成时，Ralph 输出 `<promise>COMPLETE</promise>` 并退出。

---

## 4. 关键文件速查表

| 文件 | 作用 |
|---|---|
| `ralph.sh` | 外层 bash 循环，每轮 spawn 一个新 AI 实例 |
| `CLAUDE.md` | Claude Code 的提示词模板（告诉 AI 每轮该做啥） |
| `prompt.md` | Amp 的提示词模板 |
| `prd.json` | 任务清单（带 `passes` 状态） |
| `prd.json.example` | 格式参考 |
| `progress.txt` | **append-only** 的跨迭代记忆，顶部 `## Codebase Patterns` 段最关键 |

---

## 5. 调试 / 查看进度

```bash
# 看哪些故事做完了
cat prd.json | jq '.userStories[] | {id, title, passes}'

# 看历次迭代学到了什么
cat progress.txt

# 最近的 commit
git log --oneline -10
```

---

## 6. 使用建议与坑

- **story 要小**：能独立完成一列 DB 字段、一个 UI 组件、一个 API 字段，就是合适粒度。"做整个 dashboard"、"加认证"太大，必须拆。
- **`AGENTS.md` / `CLAUDE.md` 会被自动读**：在这两个文件里沉淀"这个 repo 的 X 惯例"、"改 W 时别忘了 Z"，后续迭代会自动受益。
- **UI 类 story** 最好在验收标准里写上 "Verify in browser using dev-browser skill"。
- **CI 必须绿**：一旦留坏代码，后续迭代会在坏代码上继续叠代，雪球式崩坏。
- **不要手动改 `progress.txt`** 的历史条目（只追加）；但可以整理顶部 `## Codebase Patterns` 段。
- **归档**：换新 `branchName` 时，Ralph 会自动把上一次运行归档到 `archive/YYYY-MM-DD-feature-name/`。

---

## 7. 和你当前项目（ink-writer）的关系

Ralph 本身是为"做软件工程任务"设计的（写代码 + 跑测试）。
你当前仓库 `ink-writer` 是小说工业化写作工具，已经有 `ink-auto` / `webnovel-write` 这类循环写作机制，逻辑更贴合"写小说"场景。
**Ralph 更适合用来**：给 ink-writer 自身迭代功能（如"新增一个 reader-simulator checker"、"加一个 dashboard 视图"），而不是用来写小说章节。

---

## 8. 参考

- 仓库：https://github.com/snarktank/ralph
- 原始设计思路（Geoffrey Huntley）：https://ghuntley.com/ralph/
- 作者深度文章：https://x.com/ryancarson/status/2008548371712135632
- 交互式流程图：https://snarktank.github.io/ralph/
