---
name: ink-5
description: 连续写5章 + 全量审查修复。每章完整执行 ink-write 标准流程，5章写完后执行 ink-review Full 审查并自动修复问题。日常创作主力指令。
allowed-tools: Read Write Edit Grep Bash Task
---

# 连续创作5章 + 审查修复（ink-5）

## 核心原则

> **本指令是 `/ink-write --batch 5` + `/ink-review {start}-{end}` 的严格串联，不是简化版。**
> 每一章的写作流程与单独执行 `/ink-write` 完全一致，审查流程与单独执行 `/ink-review` 完全一致。
> **禁止以任何理由省略步骤、降低质量、跳过审查、合并章节或简化流程。**

等价于用户手动依次执行：
```
/ink-write          # 第1章完整流程
/ink-write          # 第2章完整流程
/ink-write          # 第3章完整流程
/ink-write          # 第4章完整流程
/ink-write          # 第5章完整流程
/ink-review {1}-{5} # 对这5章做全量审查 + 修复
```

如果你发现自己在想"这步可以省略/简化/合并"——停下来，你正在违反本指令的核心原则。

## Project Root Guard（必须先确认）

```bash
export WORKSPACE_ROOT="${INK_PROJECT_ROOT:-${CLAUDE_PROJECT_DIR:-$PWD}}"

if [ -z "${CLAUDE_PLUGIN_ROOT:-}" ] || [ ! -d "${CLAUDE_PLUGIN_ROOT}/scripts" ]; then
  if [ -d "$PWD/scripts" ] && [ -d "$PWD/skills" ]; then
    export CLAUDE_PLUGIN_ROOT="$PWD"
  elif [ -d "$PWD/../scripts" ] && [ -d "$PWD/../skills" ]; then
    export CLAUDE_PLUGIN_ROOT="$(cd "$PWD/.." && pwd)"
  else
    echo "ERROR: 未设置 CLAUDE_PLUGIN_ROOT，且无法从当前目录推断插件根目录" >&2
    exit 1
  fi
fi

export SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT:?CLAUDE_PLUGIN_ROOT is required}/scripts"
export SKILL_ROOT="${CLAUDE_PLUGIN_ROOT:?CLAUDE_PLUGIN_ROOT is required}/skills/ink-5"
export WRITE_SKILL_ROOT="${CLAUDE_PLUGIN_ROOT}/skills/ink-write"
export REVIEW_SKILL_ROOT="${CLAUDE_PLUGIN_ROOT}/skills/ink-review"

python3 -X utf8 "${SCRIPTS_DIR}/ink.py" --project-root "${WORKSPACE_ROOT}" preflight
export PROJECT_ROOT="$(python3 -X utf8 "${SCRIPTS_DIR}/ink.py" --project-root "${WORKSPACE_ROOT}" where)"
```

## 流程硬约束（禁止事项）

- **禁止省略写作步骤**：每章必须完整执行 ink-write 的 Step 0 → Step 6 全部步骤。
- **禁止省略审查步骤**：5 章写完后必须执行完整的 ink-review 流程，包括生成审查包、调用全部 checker、生成报告、落库指标。
- **禁止省略修复步骤**：审查发现的 critical/high 问题必须修复，不得跳过。
- **禁止降低字数标准**：每章 ≥ 2200 字硬下限，无豁免。
- **禁止中途询问**：用户执行 `/ink-5` 即为授权完整的"5章写作 + 审查修复"流程，中途不得询问是否继续。唯一允许暂停：写作失败且重试仍失败、大纲缺失。
- **禁止合并审查**：不得将 Step 3 的每章内审查与最终的 ink-review 合并或互相替代——两者都必须执行。

## Phase 1：连续写作 5 章

### 1.1 确定章节范围

```bash
python3 -X utf8 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" state get-progress
```

读取 `progress.current_chapter`，计算：
- `batch_start = current_chapter + 1`
- `batch_end = batch_start + 4`

### 1.1.5 批次前里程碑检查点

检查本批次 `[batch_start, batch_end]` 范围内是否包含里程碑章节。按以下优先级检测（**只触发最高级别的一条**，不重复弹窗）：

1. 若范围内包含200的整数倍（计算: `(batch_start - 1) // 200 < batch_end // 200`）：
   使用 AskUserQuestion 询问用户：
   ```
   🏆 本批次将跨越 200 章里程碑。
   建议在写作前运行以下审查（确保长篇数据完整性与叙事质量）：
     1. /ink-audit deep   — 全量数据对账（~30分钟）
     2. /ink-macro-review Tier3 — 跨卷叙事审查（需要单独会话执行）
   是否先运行审查？输入 yes 暂停去审查，输入 skip 跳过直接开始批量写作。
   ```
   - 用户回答 yes → 输出"请在新会话中运行上述命令，完成后重新执行 /ink-5"，然后**终止本次 ink-5**。
   - 用户回答 skip → 继续执行后续步骤。

2. 否则，若范围内包含50的整数倍（计算: `(batch_start - 1) // 50 < batch_end // 50`）：
   使用 AskUserQuestion 询问用户：
   ```
   📋 本批次将跨越 50 章检查点。
   建议在写作前运行以下审查（及时发现数据漂移与结构问题）：
     1. /ink-audit standard — 标准数据对账（~10分钟）
     2. /ink-macro-review Tier2 — 宏观叙事审查（需要单独会话执行）
   是否先运行审查？输入 yes 暂停去审查，输入 skip 跳过直接开始批量写作。
   ```
   - 处理逻辑同上。

3. 否则，若范围内包含25的整数倍（计算: `(batch_start - 1) // 25 < batch_end // 25`）：
   使用 AskUserQuestion 询问用户：
   ```
   🔍 本批次将跨越 25 章快检点。
   建议运行 /ink-audit quick 进行快速数据健康检查（~2分钟）。
   是否先运行？输入 yes 暂停去审查，输入 skip 跳过直接开始批量写作。
   ```
   - 处理逻辑同上。

4. 否则 → 无提示，直接继续。

**注意**：此检查为友好提醒，用户可随时 skip。不阻断写作流程。

### 1.2 大纲覆盖验证

对 `batch_start` 到 `batch_end` 每一章检查大纲覆盖：
```bash
for ch in $(seq {batch_start} {batch_end}); do
  python3 -X utf8 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" extract-context --chapter $ch --format pack 2>&1 | head -3
done
```
若任一章输出包含 `⚠️` 或 `未找到` 或 `不存在` → 立即阻断：
```
❌ 第{ch}章没有详细大纲，请先执行 /ink-plan 生成大纲。
```

### 1.3 输出批次计划

```
📋 ink-5 创作计划：第{batch_start}章 → 第{batch_end}章（共5章 + Full审查修复）
```

### 1.4 章节循环（严格复用 ink-write 全流程）

读取 ink-write SKILL.md 全文：
```bash
cat "${WRITE_SKILL_ROOT}/SKILL.md"
```

然后对 5 章执行完整的批量写作循环：

```
FOR i = 1 TO 5:

    ─── ink-5 写作进度 [{i}/5] 开始第{chapter_num}章 ───

    # ⚠️ 关键规则重申（每章开头强制输出，防止上下文压缩后遗忘）
    # ═══════════════════════════════════════════════════════════
    # 1. ink-5 模式：写完 5 章后还要做 Full 审查，禁止中途询问
    # 2. 每章正文必须 ≥ 2200 字（硬下限，无豁免，不足必须补写）
    # 3. 每章必须完整执行 Step 0→1→2A→2A.5→2B→3→4→4.5→5→6
    # 4. Step 2A 必须加载 core-constraints.md 和 anti-detection-writing.md
    # 5. Step 3 审查必须由 Task 子代理执行，禁止伪造审查结论
    # 6. Step 2A.5 字数校验：< 2200 字必须补写，最多 2 轮
    # 7. 章节标题 ≥ 2 个汉字且全书唯一
    # ═══════════════════════════════════════════════════════════

    # 章号确定
    从 state.json 重新读取 progress.current_chapter
    chapter_num = current_chapter + 1
    chapter_padded = 四位补零(chapter_num)

    # 清理上一章残留 workflow 状态（第一章跳过）
    若 i > 1:
        python3 ... workflow detect
        python3 ... workflow fail-task --reason "ink5_inter_chapter_cleanup" || true

    # ====== 完整执行 ink-write 标准流程 ======
    # 严格按 ink-write SKILL.md 中的 Step 0 到 Step 6 执行
    # 包括：预检、上下文构建、正文起草(≥2200字)、字数校验、
    #       风格适配、多Agent审查、润色、改写安全校验、Data Agent、Git备份
    # 每个 Step 的执行方式、必读文件、硬约束与单独执行 /ink-write 完全一致
    执行 Step 0（预检与上下文最小加载 + 大纲覆盖检查）
    执行 Step 0.5（工作流断点记录）
    执行 Step 0.6（重入续跑规则）
    执行 Step 1（脚本执行包构建）
    执行 Step 2A（正文起草 — 目标 2200-3000 字）
    执行 Step 2A.5（字数校验 — bash wc -m 验证 ≥ 2200）
    执行 Step 2B（风格适配）
    执行 Step 3（审查 — 必须由 Task 子代理执行，含 anti-detection-checker）
    执行 Step 4（润色 + AI味定向修复）
    执行 Step 4.5（改写安全校验）
    执行 Step 5（Data Agent 回写）
    执行 Step 6（Git 备份）
    通过 充分性闸门
    通过 验证与交付
    # ====== 标准流程结束 ======

    # 批量字数强制验证（bash 命令最终防线）
    FINAL_WC=$(wc -m < "${PROJECT_ROOT}/正文/第${chapter_padded}章"*.md 2>/dev/null | tail -1)
    若 FINAL_WC < 2200 → 回到 Step 2A 补写

    # 输出进度后立即继续下一章
    输出：✅ [写作 {i}/5] 第{chapter_num}章完成 · {字数}字 · 评分{overall_score}
    # ⚠️ 输出后立即回到 FOR 循环顶部，禁止等待用户回复

END FOR
```

### 1.5 写作阶段完成

输出 5 章写作汇总：
```
═══════════════════════════════════════
ink-5 写作阶段完成
═══════════════════════════════════════
范围：第{batch_start}章 → 第{batch_end}章
完成：5/5章
总字数：约{total_words}字
平均评分：{avg_score}
───────────────────────────────────────
即将进入 Phase 2：Full 审查修复...
═══════════════════════════════════════
```

## Phase 2：全量审查 + 自动修复

> 此阶段严格复用 ink-review 的完整流程，审查深度为 **Full**（核心4 + 高级4 checker）。

### 2.1 加载 ink-review 工作流

```bash
cat "${REVIEW_SKILL_ROOT}/SKILL.md"
```

### 2.2 执行 Full 审查

对 `batch_start` 到 `batch_end` 的 5 章范围执行 ink-review Full 审查：

- **Step 0**：充分性闸门（验证 5 章文件都存在且字数 > 500）
- **Step 1**：加载参考（core-constraints + cool-points-guide + strand-weave-pattern）
- **Step 2**：加载项目状态
- **Step 3**：调用全部 checker（最大并发 2）
  - 核心：`consistency-checker` / `continuity-checker` / `ooc-checker` / `reader-pull-checker`
  - Full 追加：`high-point-checker` / `pacing-checker` / `proofreading-checker` / `anti-detection-checker`
  - 若含第 1-3 章：追加 `golden-three-checker`
- **Step 4**：生成审查报告 → `审查报告/第{batch_start}-{batch_end}章审查报告.md`
- **Step 5**：保存审查指标到 index.db
- **Step 6**：写回审查记录到 state.json

### 2.3 自动修复

审查完成后，对 critical 和 high 级别问题执行自动修复：

1. 读取审查报告中所有 `critical` 和 `high` 问题
2. 按章节分组，对每章：
   - 读取对应章节正文
   - 根据问题描述和修复建议，对正文做定向修改
   - 修改后重新验证字数 ≥ 2200
   - 保存修改后的章节文件
3. **修复互斥检测**：若 fix A 和 fix B 作用于同一段落（50字符范围内），先合并修改意图再统一应用，避免互相覆盖
4. 修复后对涉及的章节重跑核心 3 checker 验证（最多 1 轮）
5. **增强规则**：若单章 critical+high 问题总数 ≥ 5，允许第2轮修复，第2轮 re-verify 使用全部 8 个 checker（非仅 core 3 个）
6. 若修复引入新的 critical 问题 → 输出警告，不做三次修复（避免无限循环）
5. Git 提交修复：
   ```bash
   git add "${PROJECT_ROOT}/正文/" "${PROJECT_ROOT}/审查报告/" "${PROJECT_ROOT}/.ink/"
   git -c i18n.commitEncoding=UTF-8 commit -m "ink-5: 审查修复第${batch_start}-${batch_end}章"
   ```

### 2.4 medium/low 问题处理

- `medium` 问题：输出到审查报告，不自动修复，标记为"建议关注"
- `low` 问题：仅记录，不输出不修复

## Phase 3：最终汇总报告

```
═══════════════════════════════════════
ink-5 全流程完成报告
═══════════════════════════════════════

📝 写作成果
  范围：第{batch_start}章 → 第{batch_end}章
  完成：5/5章
  总字数：约{total_words}字

📊 审查结果
  审查深度：Full（8 个 checker）
  平均评分：{avg_score}
  critical 问题：{c_count}（已修复 {c_fixed}）
  high 问题：{h_count}（已修复 {h_fixed}）
  medium 问题：{m_count}（记录在审查报告中）

📄 各章概览
  ✅ 第{X}章 · {标题} — {字数}字 · 评分{score}
  ✅ 第{X+1}章 · {标题} — {字数}字 · 评分{score}
  ✅ 第{X+2}章 · {标题} — {字数}字 · 评分{score}
  ✅ 第{X+3}章 · {标题} — {字数}字 · 评分{score}
  ✅ 第{X+4}章 · {标题} — {字数}字 · 评分{score}

📎 审查报告：审查报告/第{batch_start}-{batch_end}章审查报告.md
═══════════════════════════════════════
```

**里程碑提醒**（在报告末尾追加）：

检查本批次是否跨越了里程碑（即 `batch_start` 到 `batch_end` 的范围内包含50或200的整数倍）：
- 若范围内包含50的整数倍（计算: `(batch_start - 1) // 50 < batch_end // 50`）：
  ```
  📋 已跨越50章检查点（第{batch_end}章），建议运行 /ink-audit standard 进行数据对账
  ```
- 若范围内包含200的整数倍（计算: `(batch_start - 1) // 200 < batch_end // 200`）：
  ```
  🏆 已跨越200章里程碑（第{batch_end}章），建议运行 /ink-audit deep 进行全量数据对账
  建议同时运行 /ink-macro-review Tier3 进行跨卷叙事审查（需要单独会话执行）
  ```

## 章间衔接（与 ink-write --batch 一致）

在进入下一章之前，必须逐项确认：
1. `workflow_state.json` 中当前任务状态为 `completed`
2. `state.json` 的 `progress.current_chapter` 已更新
3. 上一章的充分性闸门全部通过

任一项修复后仍不满足 → 暂停并报告错误。
