---
name: ink-migrate
description: 将旧版项目（v8.x）迁移到 v9.0 架构。三阶段：资产发现→Schema迁移→迁移审计。保障半写项目无损升级。
allowed-tools: Read Write Bash AskUserQuestion
---

# 项目迁移工具 (ink-migrate)

## 目的

将使用 v8.x 架构的旧项目迁移到 v9.0 Harness-First 架构。
保证已写长篇能够延续，而不是被架构升级废弃。

## 前提

- 项目根目录必须包含 `.ink/state.json`
- 项目必须有至少 1 个章节文件

## 环境设置

```bash
source "${CLAUDE_PLUGIN_ROOT}/scripts/env-setup.sh"
```

## 三阶段执行流程

### Phase 1：资产发现（只读扫描）

```bash
python3 "${SCRIPTS_DIR}/migration_auditor.py" --project-root "${PROJECT_ROOT}" discover
```

扫描并报告：
- 章节文件数量、目录位置、命名格式
- `.ink/state.json` 存在性和 schema 版本
- `.ink/index.db` 存在性和表结构
- `.ink/summaries/` 覆盖率（有摘要的章节 / 总章节）
- 大纲文件覆盖率
- `审查报告/` 历史覆盖率
- `vectors.db` 存在性

输出资产清单到终端和 `.ink/migration/asset_inventory.json`。

**判定**：
- 如果 state.json schema_version 已经 ≥ 7 → 提示"已是 v9.0 架构，无需迁移"，终止
- 如果 state.json 不存在 → 提示"请先运行 /ink-init"，终止

### Phase 2：Schema 迁移 + 数据补全

**执行前自动备份**：
```bash
python3 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" backup --reason "pre-migration-v9"
```

备份整个 `.ink/` 目录到 `.ink/backups/pre-migration-v9-{timestamp}/`。

**2.1 state.json 迁移**（v6 → v7）：
```bash
python3 "${SCRIPTS_DIR}/migrate.py" --project-root "${PROJECT_ROOT}"
```

新增字段：
```json
{
  "schema_version": 7,
  "harness_config": {
    "computational_gate_enabled": true,
    "reader_verdict_mode": "core",
    "reader_verdict_thresholds": {
      "pass": 32,
      "enhance": 25,
      "rewrite_min": 0
    }
  }
}
```

**2.2 index.db 新表创建**：
```bash
python3 "${SCRIPTS_DIR}/migration_auditor.py" --project-root "${PROJECT_ROOT}" create-tables
```

新建：
- `harness_evaluations` 表（存放 reader_verdict 历史）
- `computational_gate_log` 表（存放 Step 2C 结果）

**2.3 数据补全**（可选，需用户确认）：

对于缺少 entity extraction 的历史章节，**询问用户**是否批量补录：
- 是 → 列出需要补录的章节清单，提供预估耗时
- 否 → 跳过，标记为 `legacy_unextracted`

对于缺少 review_metrics 的历史章节，标记为 `legacy_unreviewed`（不补录）。

### Phase 3：迁移审计

```bash
python3 "${SCRIPTS_DIR}/migration_auditor.py" --project-root "${PROJECT_ROOT}" audit
```

生成迁移审计报告到 `.ink/migration/audit_report.md`。

报告内容：
- 迁移结果总览（成功/失败）
- 各项迁移的通过状态
- 置信度分级（高/中/低）
- 需要人工确认的项目列表
- 推荐的后续操作

**置信度分级标准**：
- **高置信**：schema 迁移、新表创建、已有完整数据的章节
- **中置信**：有部分数据的章节（如有摘要但无实体提取）
- **低置信**：伏笔归属不确定、角色关系变化疑似逆转 vs 短期冲突、时间线跳跃 >30 天无过渡

## 完成输出

```
═══════════════════════════════════════
  ink-migrate 完成
═══════════════════════════════════════
  Schema 版本：v6 → v7 ✅
  章节文件：120/120 完整 ✅
  摘要覆盖：118/120 ⚠️ 缺失2章
  新表创建：2/2 ✅
  备份位置：.ink/backups/pre-migration-v9-20260403/
  审计报告：.ink/migration/audit_report.md

  推荐下一步：
  1. 阅读审计报告中的低置信项
  2. 运行 /ink-resolve 处理待确认项
  3. 运行 /ink-auto 1 验证新流程
═══════════════════════════════════════
```

## 回滚

如果迁移后发现问题：
```bash
python3 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" backup restore \
  --backup-file ".ink/backups/pre-migration-v9-{timestamp}/index.db.bak"
```

state.json 可通过 `.ink/state.json.bak.6` 恢复。

## 安全保证

- 执行前自动备份整个 `.ink/` 目录
- 不修改章节正文文件
- 不修改大纲文件
- 不删除任何历史数据
- 任何 Phase 失败都可回滚到备份
