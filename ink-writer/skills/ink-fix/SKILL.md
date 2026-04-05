---
name: ink-fix
description: 自动修复审查/审计/宏观审查报告中发现的问题。支持正文修复和数据库修复。由 ink-auto 检查点自动调用，无人值守。
allowed-tools: Read Grep Write Edit Bash
---

# Ink-Fix：自动修复 Skill

## 设计原则

1. **最小修改**：只改报告标记的问题段落，不碰正常内容
2. **先数据后正文**：先修数据库一致性，再改章节文本（避免数据回写覆盖修复）
3. **修后验证**：每项修复后验证生效，失败不阻断后续修复
4. **安全边界**：不改剧情走向、不删大纲要求的事件、不改角色核心决策
5. **字数守护**：正文修复后字数必须 ≥ 2200 字

## Project Root Guard

```bash
export INK_SKILL_NAME="ink-fix"
source "${CLAUDE_PLUGIN_ROOT}/scripts/env-setup.sh"
```

## 输入参数

由 ink-auto.sh 传入：
- `report_path`：报告文件绝对路径
- `fix_type`：`review` | `audit` | `macro`
- `project_root`：项目根目录

## Step 0：解析报告

读取报告文件，提取所有需要修复的问题。

**分类提取规则**：
- `🔴` / `critical` / `严重` → 必须修复
- `🟠` / `high` / `较高` → 必须修复
- `🟡` / `medium` / `中等` → 尽量修复
- `🔵` / `low` / `较低` → 跳过（不值得冒引入新问题的风险）

提取每个问题的：
- 严重级别
- 所属章节号
- 问题类型（见下方分类）
- 问题描述和上下文
- 报告中的修复建议（如有）

## Step 1：按 fix_type 分流执行

---

### 1A. Review 修复（审查报告）

审查报告包含的可修复问题类型：

#### 1A.1 设定矛盾（consistency-checker 产出）

**修复策略**：
1. 读取报告中的矛盾描述（如"第12章说主角左手持剑，但第14章变成右手"）
2. 查询 `index.db` 确认正确设定：
   ```bash
   python3 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" \
     index query-entity --name "角色名" --field "属性名"
   ```
3. 读取出错章节文件，定位矛盾段落
4. 用 Edit 工具修正为正确设定，保持上下文通顺
5. 验证修复

#### 1A.2 逻辑断裂 / 连贯性问题（continuity-checker 产出）

**修复策略**：
1. 读取报告中的逻辑断裂描述
2. 读取相关章节的前后文
3. 用 Edit 补充缺失的过渡句或因果衔接
4. 修复类型：
   - 空间跳跃无交代 → 补一句位移说明
   - 时间线混乱 → 修正时间词
   - 物品凭空出现/消失 → 补一句来源/去向说明
   - 角色凭空到场 → 补一句出场交代

#### 1A.3 OOC（ooc-checker 产出）

**修复策略**：
1. 读取角色档案（从 `index.db` 或 `.ink/state.json`）
2. 读取 OOC 段落上下文
3. 调整角色的语气、用词、决策风格，使其符合角色设定
4. **安全边界**：只改表达方式，不改行为结果（行为结果是大纲决定的）

#### 1A.4 追读力不足（reader-pull-checker 产出）

**修复策略**：
1. 定位报告标记的低追读力段落
2. 可执行的修复：
   - 章末缺钩子 → 补一句悬念/期待/转折暗示
   - 微兑现缺失 → 在合适位置补入一个小回报/小进展
   - 信息落差不足 → 强化角色掌握信息与读者掌握信息的不对称

#### 1A.5 AI 味过重（anti-detection-checker 产出）

**修复策略**：
1. 定位 AI 味标记段落
2. 执行反 AI 替换：
   - 高风险词替换（宛如→像、仿佛→好像、不禁→忍不住）
   - 四字套语拆解
   - 过度对仗打破
   - 感叹句精简
3. 可调用 anti_ai_scanner.py 辅助：
   ```bash
   python3 "${SCRIPTS_DIR}/anti_ai_scanner.py" \
     --file "${chapter_file}" --json
   ```

#### 1A.6 文笔质量（proofreading-checker 产出）

**修复策略**：
- 修辞重复 → 替换为近义表达
- 代称混乱 → 统一为正确代称
- 段落结构失衡 → 拆分过长段落或合并碎片段落

---

### 1B. Audit 修复（审计报告）

审计报告包含的可修复问题类型：

#### 1B.1 state.json 与 index.db 不同步

```bash
python3 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" \
  state sync-from-db
```

#### 1B.2 过期伏笔未处理

```bash
python3 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" \
  index expire-foreshadowing --chapter ${current_chapter}
```

#### 1B.3 幽灵实体（index.db 中有记录但正文从未提及）

```bash
python3 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" \
  index remove-ghost-entities --dry-run
```
确认无误后去掉 `--dry-run` 执行。

#### 1B.4 chapter_meta 膨胀

```bash
python3 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" \
  state compact-chapter-meta
```

#### 1B.5 摘要文件缺失

若报告指出某章节缺少摘要文件 `.ink/summaries/ch{NNNN}.md`：
1. 读取对应章节正文
2. 生成摘要并写入：
   ```bash
   python3 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" \
     state regenerate-summary --chapter ${ch}
   ```
   若命令不存在，手动生成：读取章节 → 提炼 200 字摘要 → 写入 `.ink/summaries/ch{NNNN}.md`

---

### 1C. Macro 修复（宏观审查报告）

宏观审查的问题更具结构性。分为**可直接修复**和**约束注入**两类。

#### 1C.1 支线剧情停滞（dormant > 30 章）

**直接修复**（对最近 3 章中最合适的 1 章操作）：
1. 从报告中提取停滞支线名称和上次出现章节
2. 读取最近 3 章正文，找到最自然的插入点
3. 用 Edit 插入 1-2 句对该支线的提及/回忆/暗示（不超过 50 字）
4. 示例：角色内心独白中提及未解决的事、某个物件触发回忆、路人闲聊提到相关信息

**约束注入**（对后续章节的写作施加约束）：
```bash
python3 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" \
  state add-writing-constraint "支线'{subplot_name}'已停滞{N}章，近5章内必须推进"
```

#### 1C.2 角色弧光停滞

**直接修复**（对最近 3 章中有该角色出场的 1 章操作）：
1. 读取角色当前状态和演化记录
2. 在角色对话或心理活动中补入一处微小的态度/认知变化（不超过 30 字）
3. 变化方向须符合角色设定中的成长轨迹

**约束注入**：
```bash
python3 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" \
  state add-writing-constraint "角色'{char_name}'弧光停滞，下次出场需展现态度/能力变化"
```

#### 1C.3 冲突模式重复（同类型冲突出现 ≥ 3 次）

**不直接修改旧章节**（修改冲突需要重写场景，风险过高）。

**约束注入**：
```bash
python3 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" \
  state add-writing-constraint "近50章'{conflict_pattern}'冲突模式出现{N}次，后续禁止复用，改用其他冲突类型"
```

#### 1C.4 叙事承诺未兑现（overdue > 50 章）

**直接修复**（对最近 3 章中最合适的 1 章操作）：
1. 从报告中提取未兑现的承诺内容
2. 在最近章节中补入一处微小推进（角色提及、线索浮现、伏笔回响），不超过 50 字
3. 更新承诺的追踪状态：
   ```bash
   python3 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" \
     index update-commitment --id ${commitment_id} --status "partially_addressed" \
     --note "ch${ch} 补入微推进"
   ```

#### 1C.5 风格漂移

**直接修复**（对漂移最严重的章节执行）：
1. 从报告中提取漂移指标（如四字套语密度偏高、对话标签过少）
2. 读取漂移章节
3. 针对具体漂移指标做定向修复：
   - 四字套语密度过高 → 拆解部分四字套语
   - 短句占比过低 → 拆分部分长句
   - 感官描写缺失 → 补入 1-2 句感官细节
4. 调用 `anti_ai_scanner.py` 验证修复效果

#### 1C.6 主题呈现缺席

**约束注入**：
```bash
python3 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" \
  state add-writing-constraint "主题'{theme}'已缺席{N}章，近3章内需自然呈现"
```

---

## Step 2：正文修复执行（通用流程）

对每个需要修改章节正文的问题：

1. **读取章节**：`Read` 工具读取章节文件
2. **定位问题段落**：根据报告描述匹配具体段落
3. **执行修复**：`Edit` 工具做最小替换
4. **编码校验**：
   ```bash
   python3 "${SCRIPTS_DIR}/encoding_validator.py" \
     --file "${chapter_file}"
   ```
5. **字数验证**：
   ```bash
   WORD_COUNT=$(wc -m < "${chapter_file}")
   # 必须 ≥ 2200
   ```
6. **记录修复**：记录修复了什么、在哪个文件、修复前后的差异摘要

## Step 3：修复验证

所有修复完成后：

1. **数据一致性验证**（若执行了数据库修复）：
   ```bash
   python3 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" \
     audit quick --silent
   ```
2. **正文完整性验证**（若执行了正文修复）：
   - 确认所有修改的章节文件存在且字数 ≥ 2200
   - 运行编码校验确认无乱码

## Step 4：Git 提交

```bash
cd "${PROJECT_ROOT}"
git add 正文/ .ink/
git diff --cached --quiet || git commit -m "ink-auto: 自动修复${fix_type}问题 ($(date +%Y%m%d-%H%M%S))"
```

## Step 5：输出修复报告

输出结构化修复摘要（直接打印到 stdout，供 ink-auto 日志捕获）：

```
=== INK-FIX 修复报告 ===
类型: {fix_type}
报告: {report_path}
修复项: {N} 项
  - [critical] 第{ch}章: {问题描述} → 已修复
  - [high] 第{ch}章: {问题描述} → 已修复
  - [high] 数据库: {问题描述} → 已修复
跳过项: {M} 项
  - [medium] 第{ch}章: {问题描述} → 风险过高，跳过
约束注入: {K} 项
  - 支线'{name}'停滞 → 约束已写入
Git: committed {hash}
INK_FIX_DONE
```

## 安全红线（不可逾越）

1. **不改剧情走向**：角色行为结果、因果链、大纲要求的事件不可修改
2. **不删内容**：修复只做替换和追加，不删除大段正文（除非删除的是明确的重复段落）
3. **不改角色核心决策**：角色选择 A 而非 B 是大纲决定的，修复只改表达不改选择
4. **字数下限 2200**：修复后任何章节不得低于此数
5. **单章修改上限**：对同一章节的修复不超过 5 处，超出则跳过并记录
6. **不跨章创建新内容**：修复只在现有段落基础上调整，不新增完整段落（微量插入除外，≤ 50 字）

## 与 ink-auto 的集成

ink-auto.sh 通过 `run_auto_fix()` 函数调用本 skill：
```bash
prompt="使用 Skill 工具加载 'ink-fix'。修复类型: ${fix_type}。报告路径: ${report_path}。项目目录: ${PROJECT_ROOT}。全程自主执行，禁止提问。完成后输出 INK_FIX_DONE。"
```

本 skill 接收 prompt 后：
1. 解析 fix_type 和 report_path
2. 读取报告 → 提取问题 → 分流执行修复
3. 验证 → Git 提交 → 输出报告 → 输出 `INK_FIX_DONE`
