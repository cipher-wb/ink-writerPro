# ink-auto 内置自动化检查点（Auto Checkpoint Internals） — 索引页

> 来源：codemap §6-D。本文档**不是独立运行模式**，而是 `/ink-auto N` 命令内部的**分层检查点机制**。
> codemap §7 已声明："严格说不是独立运行模式，而是 `/ink-auto N` 命令内部的"分层检查点""。
> 本文是一份 cross-reference 索引，把 5/10/20/50/200 章触发点的全部分析锚点指向 quick-mode.md 的对应小节，避免重复内容。

---

## 触发点速查表（codemap §6-D 原文）

| 触发条件 | 动作 | 入口 |
|---|---|---|
| 每 5 章 | ink-review Core + ink-fix | ink-auto.sh:1098 `run_review_and_fix` |
| 每 10 章 | + ink-audit quick + ink-fix | ink-auto.sh:1130 `run_audit` |
| 每 20 章 | + ink-audit standard + Tier2（浅版）+ 消歧 | + ink-auto.sh:1160 `run_macro_review` + 1190 `check_disambiguation_backlog` |
| 每 50 章 | + Tier2（完整版）+ `propagation.drift_detector` | （同上）+ `ink_writer/propagation/drift_detector.py` |
| 每 200 章 | + Tier3 跨卷分析 | （同上） |

---

## 完整分析锚点（已写入 quick-mode.md）

| 关注点 | 文档位置 |
|---|---|
| **5 档判定的 Mermaid 流程图** | [quick-mode.md §B.4](./quick-mode.md#b4-子图检查点编排器每-510205020-章触发) |
| **`determine_checkpoint(chapter)` 函数源码逐行** | [quick-mode.md §C.3 #67](./quick-mode.md#c3-ink-auto-20-阶段ink-autosh--子进程约-30-个-bash-函数--python-调用) |
| **`run_checkpoint` 编排器源码逐行** | [quick-mode.md §C.3 #64](./quick-mode.md#c3-ink-auto-20-阶段ink-autosh--子进程约-30-个-bash-函数--python-调用) |
| **`run_review_and_fix` / `run_audit` / `run_macro_review` / `run_auto_fix` / `check_disambiguation_backlog`** | [quick-mode.md §C.3 #59-63](./quick-mode.md#c3-ink-auto-20-阶段ink-autosh--子进程约-30-个-bash-函数--python-调用) |
| **`cli_checkpoint_level` / `cli_report_check` / `cli_disambig_check` / `report_has_issues` / `count_issues_by_severity` / `get_disambiguation_backlog` / `disambiguation_urgency`** | [quick-mode.md §C.3 #66-74](./quick-mode.md#c3-ink-auto-20-阶段ink-autosh--子进程约-30-个-bash-函数--python-调用) |
| **5 档触发对照表（chapter % N → review/audit/macro/disambig）** | [quick-mode.md §E.4](./quick-mode.md#e4-checkpoint-level-分支5-档判定) |
| **检查点产出的 IO（review log / audit log / macro log / fix log / 审查报告 md / audit_*.md / 宏观审查 md）** | [quick-mode.md §D.1](./quick-mode.md#d1-项目内读写) |
| **检查点子进程的 watchdog 与平台分发** | [quick-mode.md §C.3 #54-55](./quick-mode.md#c3-ink-auto-20-阶段ink-autosh--子进程约-30-个-bash-函数--python-调用) |
| **检查点的 fail-soft 边界（任一子进程异常 ‖ true 包住，不阻断写作）** | [quick-mode.md §E.6](./quick-mode.md#e6-fail-soft-边界debug-永不打断主流程-业务-fail-soft) |
| **R10 风险：SKILL.md 中的 `auto_step_skipped` + `Alerter.batch_report` Python 调用代码在 ink-auto.sh 中 0 处实际调用** | [quick-mode.md §E.7 R10](./quick-mode.md#e7--已识别的-bug--风险) + [debug-mode.md §E.10 R1/R3](./debug-mode.md#e10-已识别的-bug--风险向-codemap-7-第-6-项补充) |

---

## 与 daily-workflow.md 的关系

`/ink-resume` + `/ink-resolve` **不是检查点**，但它们**消费检查点的产出**：
- `/ink-resume` 读 `.ink/workflow_state.json`，该文件由 `ink-write` 每 step 调 `workflow start-step / complete-step` 维护，与检查点本身无关
- `/ink-resolve` 读 `.ink/index.db` 的 `disambiguation_log` 表，该表的 `active` 计数被**每 20 章** `check_disambiguation_backlog` 检测后输出警告

完整分析见 [daily-workflow.md](./daily-workflow.md)。

---

## 为什么本文档不再单独成段

codemap §7 说明 6-D "严格说不是独立运行模式"。检查点的全部源码已在 quick-mode.md 中作为 ink-auto 主循环的子图（§B.4）+ 函数（§C.3）+ 分支（§E.4）+ IO（§D.1）+ 风险（§E.7）完整覆盖。强行拆出独立文档会重复 ~150 行内容。本文档作为 cross-reference 索引页，让按 codemap §6 顺序检索的读者能直接跳到 quick-mode.md 的精确位置。

---

## 7 个运行模式文档全览

| codemap § | 文档 | 说明 |
|---|---|---|
| 6-A.1 | [quick-mode.md](./quick-mode.md) | 主文档；详细写 ink-auto 全部细节 |
| 6-A.2 | [deep-mode.md](./deep-mode.md) | Deep init 部分新写；plan/auto 引用 quick-mode |
| 6-A.3 | [daily-workflow.md](./daily-workflow.md) | /ink-resume + /ink-resolve 新写；ink-auto 引用 quick-mode |
| **6-A.4** ⭐ | [v27-bootstrap-mode.md](./v27-bootstrap-mode.md) | **codemap §6 漏列的第 4 主模式**；空目录 + 蓝本 → /ink-auto N → 自动 init+plan+auto |
| 6-B.1 | [debug-mode.md](./debug-mode.md) | Debug Mode 完整独立分析（5 个子图 + 38 文件） |
| 6-B.2 | [cross-platform-mode.md](./cross-platform-mode.md) | runtime_compat + 双脚本对等 |
| 6-C | [external-environments-mode.md](./external-environments-mode.md) | 3 个 manifest + 平台探测 |
| 6-D | **本文档** | 索引页，全部锚点指向 quick-mode.md |
