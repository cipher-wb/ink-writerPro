# Checker 共享前言 (Shared Preamble)

所有 checker agent 必须遵循以下共享规则。agent spec 中以 `{{SHARED_CHECKER_PREAMBLE}}` 标记引用此文件。

## 输入硬规则

1. **必须先读取 `review_bundle_file`**。
2. 若 `review_bundle_file` 缺失，直接返回 `pass=false`，说明 `REVIEW_BUNDLE_MISSING`；禁止自行扫描项目目录补救。
3. 默认只使用审查包内嵌的数据（正文、上下文、快照等）。
4. 仅当审查包明确缺字段时，才允许补充读取 `allowed_read_files` 中列出的**绝对路径**文件。
5. **禁止读取** `.db` 文件、目录路径、以及白名单外的相对路径。

## 输出硬规则

1. 必须遵循 `${CLAUDE_PLUGIN_ROOT}/references/checker-output-schema.md` 统一 JSON Schema。
2. 所有必填字段 (`agent`, `chapter`, `overall_score`, `pass`, `issues`, `metrics`, `summary`) 必须存在。
3. 扩展字段（`hard_violations`, `soft_suggestions`, `fix_prompt` 等）用于增强解释，不替代 `issues`。

## 评分通用规则

- 满分 100，最低 0。
- `pass` = `overall_score >= 60` 且无 `critical` severity 的 issue（除非 agent 有更严格的阈值）。
- `critical` issue → 润色步骤必须修复。
- `high` issue → 优先修复。
- `medium` / `low` issue → 建议修复 / 可选修复。
