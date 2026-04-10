# Step 2C: 计算型闸门 (Computational Gate)

## 目的

在昂贵的 LLM checker (Step 3) 之前，用确定性规则快速拦截明显问题。
**节省成本**：如果计算型检查发现硬失败，直接退回 Step 2A，不浪费 checker 调用。

## 调用方式

```bash
python3 "${SCRIPTS_DIR}/computational_checks.py" \
  --project-root "${PROJECT_ROOT}" \
  --chapter ${CHAPTER_NUM} \
  --chapter-file "${CHAPTER_FILE}" \
  --format json
```

或通过统一 CLI：

```bash
python3 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" \
  comp-gate --chapter ${CHAPTER_NUM} --chapter-file "${CHAPTER_FILE}" --format json
```

## 输出格式

```json
{
  "pass": true,
  "hard_failures": [],
  "soft_warnings": [
    {
      "name": "foreshadowing",
      "passed": false,
      "severity": "soft",
      "message": "2 条伏笔严重逾期（>20章）"
    }
  ],
  "checks_run": 6,
  "checks_passed": 5
}
```

## 检查项

| 检查项 | 类型 | 说明 |
|--------|------|------|
| `word_count` | 硬 | 字数 ∈ [2200, 5000]，低于下限为硬失败 |
| `file_naming` | 硬 | 文件名格式 `第NNNN章-标题.md` 或 `第NNNN章.md` |
| `character_conflicts` | 软 | 检查正文中出现但不在实体库中的角色名 |
| `foreshadowing` | 软 | 检查伏笔逾期 >20 章的情况 |
| `power_level` | 软 | 检查主角能力等级基础一致性 |
| `contract` | 软 | 检查前章 chapter_meta 关键字段完整性 |

## 判定逻辑

- **硬失败 (exit 1)** → 退回 Step 2A 重写。不进入 Step 3。
- **仅软警告 (exit 0)** → 将 `soft_warnings` 附加到 review_bundle，提供给 Step 3 checkers 参考。
- **全部通过 (exit 0)** → 正常进入 Step 3。
- **脚本错误 (exit 2)**：
  - 首次遇到：输出 WARNING 日志 `"⚠️ Step 2C 计算型闸门脚本异常，本次跳过。请检查 Python 环境。"`
  - 记录到 observability 日志（`tool_call_stats` 表，`tool_name='computational_checks'`, `success=false`）
  - 继续进入 Step 3（不阻断），但在 review_bundle 中附加 `comp_gate_skipped: true` 标记
  - 连续 3 次 exit 2 → 升级为 WARNING 并建议用户检查环境

## 容错

- 脚本不存在 → 跳过 Step 2C
- 脚本执行超时 → 跳过 Step 2C
- 脚本内部异常 → exit 2 + 按上述分级处理
