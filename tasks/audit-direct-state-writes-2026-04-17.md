# Audit: Direct state.json Writes（US-025 产物）

生成于 2026-04-17，作为 v13 US-025 的审计产物，对 FIX-03A SQL-first 落地度做最终扫描。

## Scan Command

```bash
grep -rn 'atomic_write_json' ink-writer/scripts/ ink_writer/ | grep -v __pycache__ | grep -v test
```

## Findings

### ✅ 合法直写（保留）

| # | 位置 | 用途 | 判定理由 |
|---|------|------|---------|
| 1 | `state_manager.py:440` | StateManager.flush() 内的 view write | US-024 的核心路径，SQL-first 下 JSON 是视图 |
| 2 | `init_project.py:410` | 新项目初始化时创建 state.json | 项目尚无 .ink/index.db，StateManager 不可用 |
| 3 | `init_project.py:421` | 写入 preferences.json | 非 state.json |
| 4 | `init_project.py:440` | 写入 golden_three_plan.json | 非 state.json |
| 5 | `workflow_manager.py:916` | 写入 workflow_state.json | **非 state.json**，是 workflow 临时状态 |
| 6 | `project_locator.py:137` | 写入 project locator json | 非 state.json |
| 7 | `snapshot_manager.py:67` | 写入 snapshot 文件 | 非 state.json，是 snapshot 副本 |

### ⚠️ 需关注（已加 TODO）

| # | 位置 | 用途 | 问题 | 处置 |
|---|------|------|------|------|
| 1 | `archive_manager.py:123` | ArchiveManager.save_state 直写 state.json | 绕过 StateManager.flush()，归档流程完成时的 state 更新不走 SQL-first | 加 TODO 注释；后续 US 单独重构 |
| 2 | `update_state.py:215` | UpdateStateAgent 直写 state.json | 独立 CLI 工具，绕过 StateManager；用于脚本化修改 state | 加 TODO 注释（范围外，非主流程）；未来 US 重构 |

### ✅ 已完成迁移

| # | 位置 | 原状态 | 当前状态 |
|---|------|--------|---------|
| 1 | `ink-resolve/SKILL.md` | 直读+直写 state.json.disambiguation_pending | US-011 已迁移到 SQL 单接口 |
| 2 | `state_manager.py::flush()` 顺序 | JSON 先 SQL 后（反向） | US-024 改为 SQL 先 JSON 后（SQL-first） |

## Summary

- 合法直写 6 处（保留）
- 需重构 1 处：`archive_manager.py:114`
  - **加 TODO 注释指向本 US-025 和后续重构任务**
  - 影响面：归档流程（非主要写作链路），风险较低
  - 不在本轮 Ralph 自动修复范围（避免改动复杂 flow 的连锁影响）

## Grep 最终验证

除 StateManager 内部与合法直写外，真正"绕过 SQL"的直写 state.json 调用 ≤ 1（archive_manager）。
该 1 处已加 TODO，下一轮 PRD 统一清理。

## 未来工作（下一轮）

将 `archive_manager.py` 的 state 更新改为 StateManager 调用：

```python
# 当前（v13 US-025 已 TODO）：
atomic_write_json(self.state_file, state, use_lock=True, backup=True)

# 目标：
sm = StateManager(cfg)
# 用 StateManager API 应用归档后的状态变更，然后 sm.save_state()
```

注：需先把 archive_manager 的"state dict 修改逻辑"拆成对 StateManager 的高层调用（add_entity / update_entity 等），而非直接替换 dict。此重构工作量 M，放入下一轮 PRD。
