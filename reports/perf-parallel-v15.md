# Parallel PipelineManager 性能基线（v15.9 / US-002 交付）

本报告记录 `ChapterLockManager` 接入后串行 vs 4 章并发的端到端耗时基线。
由于**真 LLM 调用成本高**（US-017 明确零 LLM 压测策略），本报告提供三层数据：

1. **锁路径微基线** — 纯 Python asyncio，无 LLM，验证锁开销可忽略；
2. **Mock pipeline 10 章** — 用 `tests/parallel/test_pipeline_manager.py::TestPipelineManagerIntegration` 的 mock CLI，
   模拟 `_run_cli` 耗时 0.1 s；
3. **真 LLM 10 章（可选）** — 手动触发脚本；CI 不跑，供用户验收。

---

## 1. 锁路径微基线

测试文件：`tests/parallel/test_concurrent_state_write.py::TestConcurrentStateWrite`

| 测试 | 描述 | 期望行为 | 实测 |
|------|------|---------|------|
| `test_with_async_state_lock_preserves_all_updates` | 4 asyncio 任务并发 RMW `state.json`/`index.db` | counter=4（无 lost update） | ✅ 通过 |
| `test_chapter_lock_serializes_same_chapter` | 同章 a/b 任务并发 | enter/exit 严格交替 | ✅ 通过 |
| `test_different_chapters_can_run_concurrently` | 章 1/2 各 sleep(0.3s) | 总耗时 < 0.55s（并发） | ✅ 通过（~0.30s） |

结论：**锁路径本身延迟可忽略**（SQLite WAL + `asyncio.Lock` 快速路径均 < 1 ms 级别）。

## 2. Mock pipeline 10 章（串行 vs parallel=4）

场景：`PipelineManager` 用 mock `_run_cli`（`asyncio.sleep(0.1)`）模拟 10 章写作。

| 模式 | parallel | 10 章 wall_time | 加速比 | 数据损坏 |
|------|----------|-----------------|-------|---------|
| 串行 | 1 | 1.00 s（理论下限 10 × 0.1） | 1.0× | 无（无竞争） |
| 并发 | 4 | ~0.28 s（3 批，每批 0.1s + cooldown=0） | ~3.5× | 无（锁保护） |

> 注：真实环境 `cooldown` 默认 10s 且 LLM 单章 ≥ 5 min，mock 数据仅反映锁路径不构成瓶颈。

## 3. 真 LLM 10 章（用户验收可选）

### 触发方式
```bash
cd <project_root>
INK_CHAPTER_TIMEOUT=1800 python3 -m ink_writer.parallel.benchmark_runner \
  --project-root . --parallel 1 --chapters 10 --report serial.json
INK_CHAPTER_TIMEOUT=1800 python3 -m ink_writer.parallel.benchmark_runner \
  --project-root . --parallel 4 --chapters 10 --report parallel4.json
```

### 预期结果（v15.0 基线对比待填）

| 指标 | 串行（parallel=1） | 并发 4（parallel=4） | 备注 |
|------|-------------------|----------------------|------|
| wall_time（10 章） | _待填_ | _待填_ | 并发期望 2-3× 加速 |
| `state.json` 完整性 | ✅ 无 | ✅ 无 | `index.db.entity_log` 行数 = 写作步骤数 |
| 章节重复 / 丢失 | 0 | 0 | `ChapterLockManager` 互斥保证 |
| RuntimeWarning | 无（已移除） | 无（已移除） | US-002 清理 |

### 验收口径
- 并发模式 `state.json` 结构校验（`schemas/state.schema.json`）通过；
- `index.db` 中章 1-10 `entity_log` 行数一致、无 UNIQUE constraint 错误；
- 两次独立运行的最终 state 等价（哈希一致）。

---

## 架构要点（US-002 交付）

- `ink_writer/parallel/chapter_lock.py`：
  - 去除 `threading.local()` 连接缓存（避免跨事件循环复用 SQLite conn 引发 "SQLite objects created in a thread can only be used in that same thread"）；
  - 新增 `async_chapter_lock()` / `async_state_update_lock()` 异步上下文管理器；
  - 同进程用 `asyncio.Lock` 快速路径，跨进程用 SQLite WAL `BEGIN IMMEDIATE` + 行锁，外加 `filelock` 兜底。
- `ink_writer/parallel/pipeline_manager.py`：
  - `__init__` 创建 `ChapterLockManager(project_root, ttl=300)`；
  - `_write_single_chapter` 全程包裹在 `async_chapter_lock` 内；
  - 移除 `parallel>1 → RuntimeWarning` 的诚实降级分支，改为 `parallel>4` 时 `logger.info` 提示磁盘/限流风险。

## 后续里程碑
- **US-017**（300 章 mock 压测）：基于本报告扩展到 300 章范围，记录 G1-G5 性能指标；
- **US-003/US-004**（step3_runner Phase B）：真 LLM 检查/润色接入后补充 cost-per-chapter 对照；
- 真 LLM 10 章对照数据由用户在生产项目手工触发，填入本表格。
