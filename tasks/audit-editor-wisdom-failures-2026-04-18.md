# Audit: tests/editor_wisdom 4 Failures（US-001 产物）

生成于 2026-04-18，作为 v14 US-001 的诊断产物。

## Scan Command

```bash
pytest tests/editor_wisdom --no-cov --tb=short
```

**实测结果**：4 failed, 223 passed, 3 warnings in 51.88s（原 v5 审计 "4 failed + 6 errors" 的 6 errors 已消失，疑似后续 US 修复副作用）。

## Failures 分类

所有 4 个 failure 均为 **DID NOT RAISE** 类型，根因一致：**Step 2 US-006 Retriever 单例化改动导致 mock 策略失效**。

### 共同根因

Step 2 US-006 改动：
- `ink_writer/editor_wisdom/context_injection.py:71` 原 `retriever = Retriever()` → `retriever = get_retriever()`
- `ink_writer/editor_wisdom/writer_injection.py:63` 同上

测试沿用旧 mock：
```python
with patch("ink_writer.editor_wisdom.context_injection.Retriever", side_effect=FileNotFoundError):
```

但代码走 `get_retriever()`（调用 module-level cache），**不经过被 patch 的 `Retriever` class**。故 mock 不命中，异常不抛，测试失败。

### 详细清单

| # | 测试文件:行号 | 现有 mock 对象 | 应改为 mock | 分类 |
|---|---|---|---|:---:|
| 1 | `tests/editor_wisdom/test_context_injection.py:253` `test_retriever_failure_raises_when_enabled` | `context_injection.Retriever` | `context_injection.get_retriever`（side_effect=FileNotFoundError）+ 先 `clear_retriever_cache()` | **mock-stale** |
| 2 | `tests/editor_wisdom/test_no_silent_fallback.py:31` `test_context_injection_propagates_when_enabled` | `context_injection.Retriever`（raises EditorWisdomIndexMissingError） | `context_injection.get_retriever` | **mock-stale** |
| 3 | `tests/editor_wisdom/test_no_silent_fallback.py:60` `test_writer_injection_propagates_when_enabled` | `writer_injection.Retriever` | `writer_injection.get_retriever` | **mock-stale** |
| 4 | `tests/editor_wisdom/test_writer_injection.py:200` `TestBuildWriterConstraints.test_retriever_failure_raises_when_enabled` | `writer_injection.Retriever` | `writer_injection.get_retriever` | **mock-stale** |

## 修复策略

**全部 4 个为 mock-stale（浅层），US-002 一次性修复**。

对每个 failing test：
1. 在 `with patch(...)` 替换 `Retriever` 为 `get_retriever`
2. 调用前先 `from ink_writer.editor_wisdom.retriever import clear_retriever_cache; clear_retriever_cache()`
3. 验证预期异常仍传播

## 无深层失败

US-003 深层修复无需执行（可直接跳过或做成空 US 标 skipped）。

## 结论

- **总失败数**：4（不是 v5 审计说的 4+6=10）
- **修复复杂度**：Low（均为 mock stale）
- **所需 US**：仅 US-002 足够，US-003 可提前释放
- **建议**：US-002 修完后跑 `pytest tests/editor_wisdom` 预期 0 fail；US-003 可直接 passes=true + notes 标"无深层失败，US-002 完成即可"
