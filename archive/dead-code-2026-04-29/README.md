# Dead Code 归档（2026-04-29）

来自 task #3 第 2 档瘦身。基于 `docs/analysis/02-dead-code.md` 的静态扫描 + 二次 grep 验证（2026-04-29 重核）。

## 归档清单（6 个文件 + 2 个测试）

| 原路径 | 归档名 | 归档原因 |
|---|---|---|
| `ink_writer/foreshadow/fix_prompt_builder.py` | `foreshadow-fix_prompt_builder.py` | 仅 `tests/foreshadow/test_foreshadow_fix_prompt.py` 引用；主流程 `ink-write` SKILL.md 未接入。设计文档承诺的"伏笔生命周期违规自动修复提示词"未落地 |
| `ink_writer/plotline/fix_prompt_builder.py` | `plotline-fix_prompt_builder.py` | 同上，`ink-write` SKILL.md:1766 提及 `plotline_fix_prompt` 但 line 1773 实际只列了 `tracker.scan_plotlines`，未导入 fix builder |
| `scripts/migration/fix11_merge_packages.py` | `fix11_merge_packages.py` | FIX-11 一次性 Python 包合并迁移脚本。FIX-11 已彻底完成（master 当前为合并后状态），脚本无需保留在主干 |
| `ink-writer/scripts/sync_plugin_version.py` | `sync_plugin_version.py` | 手工发布前同步 plugin.json / manifest 版本的工具，无外部调用，未接入任何发布流程 |
| `tests/foreshadow/test_foreshadow_fix_prompt.py` | `test_foreshadow_fix_prompt.py` | 配套测试，与归档代码一起搬走 |
| `tests/plotline/test_plotline_fix_prompt.py` | `test_plotline_fix_prompt.py` | 同上 |

## 直接删除（不归档，索引已 `D`）

| 原路径 | 删除原因 |
|---|---|
| `ink_writer/chapter_paths_types.py` | 0 引用，类型重复定义。`scripts/chapter_paths_types.py` 是真正在用的版本 |
| `config/incremental-extract.yaml` | `ink_writer/incremental_extract/` 模块已删除，留下的孤儿配置 |

## 没动的"候选"

二次 grep 后发现以下文件**仍在被引用**，**不归档**：

| 文件 | 引用方 |
|---|---|
| `ink_writer/pacing/high_point_scheduler.py` + `config/high-point-scheduler.yaml` | `ink-writer/skills/ink-plan/SKILL.md:521` 在用 |
| `config/ab_channels.yaml` | `ink-writer/skills/ink-write/SKILL.md` 多处 + `docs/USER_MANUAL.md` 文档化 |

如果未来确认这些"实际未生效"（比如 LLM 看 SKILL.md 但不会真去 `import`），可以做下一轮归档。

## 复活方法

如果以后发现某个归档代码其实有用：

```bash
git mv archive/dead-code-2026-04-29/<file> <原路径>
git commit -m "revive: <file> 实际有用，搬回主干"
```

git history 完整保留（用 `git mv` 而非 `cp + rm`）。
