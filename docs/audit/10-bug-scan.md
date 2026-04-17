# US-010 静态 Bug 扫描报告

**版本**：v13.8.0 深度健康审计
**执行日期**：2026-04-17
**执行类型**：静态分析（只读，不改源码）
**整体风险级别**：**MEDIUM-HIGH**（1 个 Blocker、2 个 Critical、若干 High）

---

## Executive Summary

本次扫描覆盖 `/Users/cipher/AI/ink/ink-writer` 的 Python 源码（主要是 `ink_writer/`、`scripts/editor-wisdom/`、`ink-writer/scripts/`）。未发现裸 `except:`、可变默认参数、SQL 注入（用户可控）等红线反模式；文件句柄全部通过 `with open(...)` 管理。

**关键发现**：
1. **Blocker — 并发 PipelineManager 缺少 ChapterLockManager 集成**：文档声称"实体写入由 SQLite WAL + ChapterLockManager 保护"，但 `pipeline_manager.py` 代码中完全未 import 或实例化 `ChapterLockManager`。N 章并发写作直接竞争 `state.json` / `index.db`，有数据损坏风险。
2. **Critical — `03_classify.py` / `05_extract_rules.py` 未在入口校验 API Key**：CLAUDE.md Top 3 风险 #2 未完全闭环。仅 `smoke_test.py` 有优雅 skip，主分类/抽取脚本缺失。
3. **Critical — editor_wisdom `Retriever` 无单例缓存**：`build_editor_wisdom_section` / `build_writer_constraints` 未传 retriever 时每次 new Retriever() → 重复加载 BAAI/bge-small-zh-v1.5（~20-30s）。`step3_harness_gate.py:135` 直接命中该反模式。

**CLAUDE.md Top 3 状态**：
- #1 retriever 延迟加载：**部分达标**（CLI 延迟 import、tests 使用 `scope=module` fixture；但生产代码路径 `build_*` 和 `step3_harness_gate` 每章重新实例化）
- #2 API Key 缺失检查：**未达标**（仅 smoke_test 有 skip，主脚本缺）
- #3 agent 双目录消除：**已达标**（`ink_writer/agents/` 不存在，仅 `ink-writer/agents/`）

---

## CLAUDE.md Top 3 风险当前状态

### 风险 #1：Retriever 延迟加载（30s 代价）—— 部分达标

**证据 — 正面（延迟加载已做到）**：

1. `ink_writer/editor_wisdom/cli.py:59`（lazy import）
   ```python
   def cmd_query(query_text: str, top_k: int = 5) -> int:
       try:
           from ink_writer.editor_wisdom.retriever import Retriever
   ```

2. `ink_writer/semantic_recall/chapter_index.py:101-105`（lazy model load）
   ```python
   def _get_model(self):
       if self._model is None:
           from sentence_transformers import SentenceTransformer
           self._model = SentenceTransformer(self._model_name)
   ```

3. tests 使用 `@pytest.fixture(scope="module")`：`tests/editor_wisdom/test_retriever.py:74,95`、`tests/style_rag/test_style_rag.py:203,210` 等。

**证据 — 负面（仍有反模式）**：

1. `ink_writer/editor_wisdom/retriever.py:11,46` — 模块顶层 `from sentence_transformers import SentenceTransformer` + `__init__` 里 `self._model = SentenceTransformer(MODEL_NAME)`。每个 `Retriever()` 调用就重新加载模型（30s+）。

2. `ink_writer/style_rag/retriever.py:12,62` — 同样问题。

3. `ink_writer/style_rag/__init__.py:8` 顶层 re-export `StyleRAGRetriever`，导致 `import ink_writer.style_rag` 即触发 `sentence_transformers` 导入（约 1.5s 实测）。

4. `ink-writer/scripts/step3_harness_gate.py:131-135` 每章写作流程里新建 retriever：
   ```python
   def checker_fn(text: str, ch_no: int) -> dict:
       from ink_writer.editor_wisdom.checker import check_chapter
       from ink_writer.editor_wisdom.retriever import Retriever
       retriever = Retriever()    # ← 每章重建，30s 冷启动
       rules = retriever.retrieve(text)
   ```
   若写一章触发一次 → 20 章 × 30s = 10 分钟纯模型加载时间。

5. `ink_writer/editor_wisdom/writer_injection.py:63`、`context_injection.py:71`：
   ```python
   if retriever is None:
       try:
           retriever = Retriever()
   ```
   虽允许外部注入，但调用方若忘记传参就掉进反模式。目前这两个 build_* 函数未在生产代码路径被调用（仅 tests 中），风险潜伏。

### 风险 #2：API Key 缺失检查 / 优雅降级 —— 未达标

**证据 — 正面**：
- `scripts/editor-wisdom/smoke_test.py:22-24` 明确检查 `ANTHROPIC_API_KEY`，缺失时 exits 0 with status 'skipped'。
- `ink_writer/editor_wisdom/llm_backend.py:28` 有 key 时走 SDK，无 key 时 fallback 到 `claude -p` CLI（依赖 OAuth）。

**证据 — 负面**：
- `scripts/editor-wisdom/03_classify.py:188-197` `main()` 只检查 `clean_index.json`，不检查 API key。CLI fallback 隐式依赖 `claude` 命令在 PATH 中 — 若两者都无，直接在第一次 `call_llm` 抛异常。
  ```python
  def main() -> None:
      data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DATA_DIR
      if not (data_dir / "clean_index.json").exists():
          print("Error: clean_index.json not found. Run 02_clean.py first.", file=sys.stderr)
          sys.exit(1)
      stats = classify(data_dir)  # ← 直接进，每篇失败仅 continue，无整体失败 guard
  ```
- `scripts/editor-wisdom/05_extract_rules.py:224-233` 同样缺失入口 key 验证。
- `03_classify.py:130` / `05_extract_rules.py:157` 的 per-file `except Exception` 导致所有文章失败时用户仍看到"Classified: 288 (cached: 0, API calls: 0)"假成功提示。

### 风险 #3：agent 规格双目录 —— 已达标

**证据**：
- `ls /Users/cipher/AI/ink/ink-writer/ink_writer/agents/` → 不存在（目录不存在）。
- `ls /Users/cipher/AI/ink/ink-writer/ink-writer/agents/` → 存在，包含 24 个 `.md` agent 规格文件。
- US-402 consolidation 确实完成。

---

## 反模式发现（按类别）

### A. 裸/过宽 `except`

| 位置 | 片段 | 分级 | 说明 |
|---|---|---|---|
| `ink_writer/parallel/pipeline_manager.py:320,327,369,375,411,422` | `except Exception:` 吞掉所有异常（含 return None / 0） | High | `_get_final_chapter / _check_outline / _clear_workflow / _get_word_count / _run_checkpoint` 六处全部吞 exception 返回"默认值"，出错静默。工作流异常不会被感知。 |
| `ink_writer/parallel/chapter_lock.py:83,140` | `except Exception: conn.rollback(); raise` | Low | raise 了，但可改 `except sqlite3.Error`。 |
| `ink_writer/style_rag/polish_integration.py:175` | `except Exception:` + logger.warning | Medium | 已 log，可接受。 |
| `ink_writer/editor_wisdom/llm_backend.py:98` | `except Exception: pass`（metrics 记录） | Low | Best-effort metrics，可接受。 |
| `ink_writer/editor_wisdom/writer_injection.py:68`、`context_injection.py:76` | 含 **死代码**：`except Exception: if config.enabled: raise; return ...Section()` — 因为上文已通过 `config.enabled` gate，此处 `if config.enabled` 必然为 True，`return` 永远不可达 | Medium | 逻辑冗余但不致错。 |
| `ink_writer/checker_pipeline/runner.py:158,237` | `except Exception as e:` | Low | 明确捕获后记录，可接受。 |
| `scripts/editor-wisdom/03_classify.py:56,130` / `05_extract_rules.py:57,157` / `02_clean.py:53` / `04_build_kb.py:56` / `01_scan.py:36` | 多处 `except Exception` 用于文件读失败/LLM 失败 | Medium | 每文件容错，但见风险 #2：无整体 fail 门禁。 |

**裸 `except:`（无 Exception）**：未发现（grep `except\s*:` 在 `ink_writer/` 和 `scripts/` 均 0 命中）。

### B. 可变默认参数

Grep `def.*=\s*\[\]|def.*=\s*\{\}`：**0 命中**。整个项目使用 dataclass + `field(default_factory=list)` 规范，非常好。

### C. 未关闭文件句柄

全部 `open(` 都用 `with`（`ink_writer/` 目录 grep `open\(` 10 处，均含 `with`）。

### D. SQL 注入（字符串拼接/f-string）

- **ink_writer/** 主包：0 命中（全部参数化查询）。
- `ink-writer/scripts/data_modules/style_sampler.py:99,103` 和 `index_manager.py:1019,1027` 使用 f-string 拼 `PRAGMA table_info({table_name})` 和 `ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}`：
  - 参数来源：**内部硬编码**（非用户输入），注入风险低
  - 但属于技术债，若未来接入用户可控 schema 名则爆。标记 **Low**。
- `benchmark/style_rag_builder.py:382` f-string execute：仅 benchmark 脚本，**Low**。

### E. `ink_writer/parallel/` race condition

| 位置 | 问题 | 分级 |
|---|---|---|
| `ink_writer/parallel/pipeline_manager.py:5`（docstring）vs `ink_writer/parallel/pipeline_manager.py` 全文件 | docstring 声称"实体写入由 SQLite WAL + ChapterLockManager 保护"，但 `pipeline_manager.py` 里没有任何 `from ink_writer.parallel.chapter_lock import ChapterLockManager` 或其实例化 | **Blocker** |
| `pipeline_manager.py:296-297` | `proc.stdin.write(prompt.encode()); proc.stdin.close()` — 缺 `await proc.stdin.drain()` 和 `await proc.stdin.wait_closed()`；大 prompt（中文 100KB+）可能写入缓冲区溢出或未完成 flush 就被 close | High |
| `pipeline_manager.py:177-181` | 多章 subprocess 并发，写同一 `state.json` / `.ink/index.db`。即使 SQLite WAL 允许多读一写，多个 CLI 进程内的 write 事务仍会竞争：如两章同时 commit entity 更新，fingerprint、plotline 状态可能被后来者覆盖 | **Blocker**（与 #1 关联） |
| `pipeline_manager.py:14,15` | `import os, import shutil` 均未使用 | Trivial |
| `pipeline_manager.py:354,381,404` | `import re`、`import glob` 内联在函数内（对 2 处已是热路径） | Low（风格问题） |
| `ink_writer/parallel/chapter_lock.py:127` | `_cleanup_expired` DELETE 每次 acquire 都执行，写放大；BEGIN IMMEDIATE 保护下竞争可能形成长尾 | Low |
| `ink_writer/parallel/chapter_lock.py:49-54` | `threading.local()` 缓存 connection，但 `ChapterLockManager` 在 `pipeline_manager` 中用的是 asyncio 不是 threading — 若外部代码跨 event loop 调 `state_update_lock`，同一 connection 跨 task 使用会冲突 | Medium（当前未用到，潜伏） |

### F. `ink_writer/prompt_cache/` stale cache

- `prompt_cache/segmenter.py` 只构造 `cache_control: ephemeral`（Anthropic 5 分钟 TTL），不做本地持久化缓存。**不存在 stale cache 问题**。
- `prompt_cache/metrics.py` 写 SQLite 事件日志，不涉及内容缓存。
- **但**：`segmenter.py:47-49` 文档"base system prompt is stable across calls" 依赖调用方传的 `system_text` 本身不含动态信息。若有调用方误将 `chapter_outline` 拼到 `system_text` 里，缓存命中率将归零且不会告警。需要对齐文档/运行时护栏（US-013 监控议题）。
- `editor-wisdom` 的 `classify_cache.json` / `rules_cache.json`（`scripts/editor-wisdom/03_classify.py:61`、`05_extract_rules.py:62`）使用 `file_hash` 作 key，天然抗 staleness。**OK**。

### G. Python 常见 bug 扫描

| 类型 | 发现 | 位置 |
|---|---|---|
| None dereference | `pipeline_manager.py:296` `proc.stdin.write(...)` — `create_subprocess_exec` 保证了 `stdin=PIPE` 时 `proc.stdin` 非 None，可接受 | — |
| None dereference | `pipeline_manager.py:307` `proc.returncode or 0` — 进程未结束时 `returncode is None`，这里 `await proc.wait()` 之后返回，所以非 None。OK | — |
| Infinite loop | `chapter_lock.py:124-147` `while True:` — 有 deadline + TimeoutError 出口，安全。OK | — |
| 缺少 return | 未发现 | — |
| 变量作用域错误 | 未发现 | — |
| 捕获后静默 | `pipeline_manager.py:320-423` 六处 `except Exception: return ...` 值得警惕（见 A 类） | High |
| `json.loads` 无 schema validation | `pipeline_manager.py:419` `cp = json.loads(result)` + 随后 `.get` — 如果 `result` 为 `[...]`（list）则 `.get` 抛 AttributeError | Medium |
| 路径未检查存在 | `pipeline_manager.py:386` `if not filepath.exists() or filepath.stat().st_size == 0` — 正确 | — |
| race 于共享字典 | 未发现（PipelineReport 只在主协程追加） | — |

### H. ANTHROPIC_API_KEY 相关护栏完整性

- `llm_backend.py:28` 分支：有 key → SDK；无 key → `claude -p`。若两者都失效：
  - SDK 分支：`anthropic.Anthropic()` 初始化就会抛
  - CLI 分支：`subprocess.run(cmd, ..., check=True)` 会抛 `FileNotFoundError` / `CalledProcessError`
- 下游 `03_classify.py:128-132` / `05_extract_rules.py:154-159` 用 `except Exception` 逐文件兜住，**但没有入口时的快速失败**。于是典型症状：跑 288 个文件 × 每个失败 + `except` → 288 个 errors.log 条目 + 假成功输出，浪费时间+误导。

---

## Top 10 最高风险点

### 🔴 1. Blocker — ChapterLockManager 未集成到 PipelineManager

- **文件**：`ink_writer/parallel/pipeline_manager.py:5,177-181`（docstring vs 实现），全文件无 ChapterLockManager 引用
- **证据**：
  ```python
  # 第 5 行 docstring
  # - 实体写入由 SQLite WAL + ChapterLockManager 保护
  # 第 177-181 行（实际代码）
  tasks = [
      self._write_single_chapter(ch, batch_idx, i + 1, len(batch))
      for i, ch in enumerate(batch)
  ]
  results = await asyncio.gather(*tasks, return_exceptions=True)
  ```
- **风险**：N 章并发 CLI 子进程同时写 `state.json` 和 `.ink/index.db`。SQLite WAL 允许并发读+单写，但跨进程的"读-改-写" state.json（非事务 JSON 文件）会发生 lost update。角色 fingerprint / plotline 状态可能静默丢失。
- **触发路径**：任何使用 `PipelineConfig.parallel > 1` 的场景。
- **建议**：要么真接入 ChapterLockManager，要么文档修正为"仅串行安全"。

### 🔴 2. Critical — editor-wisdom 分类/抽取脚本缺入口 API Key 校验

- **文件**：`scripts/editor-wisdom/03_classify.py:188-197`、`scripts/editor-wisdom/05_extract_rules.py:224-233`
- **证据**：`main()` 检查 clean_index.json 存在，但不检查 `ANTHROPIC_API_KEY` 或 `claude` CLI 可用性。
- **风险**：无 key 且 CLI 不可用时，跑完全量 288 文件所有 API 调用都失败（per-file `except` 静默），输出"Classified: 288 (API calls: 0)"假成功。用户无法快速感知原因。
- **对比**：`smoke_test.py:22-24` 有正确的 skip 逻辑，需复用到这两个脚本。

### 🔴 3. Critical — Retriever 无全局单例，每次 new 花 30s

- **文件**：`ink-writer/scripts/step3_harness_gate.py:131-135`、`ink_writer/editor_wisdom/writer_injection.py:63`、`ink_writer/editor_wisdom/context_injection.py:71`
- **证据**（harness_gate 最严重）：
  ```python
  def checker_fn(text: str, ch_no: int) -> dict:
      from ink_writer.editor_wisdom.checker import check_chapter
      from ink_writer.editor_wisdom.retriever import Retriever
      retriever = Retriever()            # 每章新建
      rules = retriever.retrieve(text)
  ```
- **风险**：单章写作触发 1 次 `Retriever()` → 20 章批次 = 20 × 30s ≈ 10 min 纯模型加载开销。
- **建议**：在 `step3_harness_gate` 模块级 cache 或 `functools.lru_cache` 包装 `Retriever` 工厂。

### 🟠 4. High — PipelineManager 六处 `except Exception` 静默吞

- **文件**：`ink_writer/parallel/pipeline_manager.py:320,327,369,375,411,422`
- **证据**：
  ```python
  async def _check_outline(self, chapter: int) -> bool:
      try:
          await self._ink_py("check-outline", "--chapter", str(chapter))
          return True
      except Exception:   # line 327
          return False    # 任何错误都被当"大纲不存在"
  ```
- **风险**：真实故障（权限、路径、python 崩溃）被误判为"需要生成大纲"，触发冤枉的 `_auto_generate_outline`；或 `_get_word_count` 返回 0 导致误判"写作失败"。排查成本高。
- **建议**：区分 FileNotFoundError（业务预期） vs 其他（重抛或至少 logger.warning）。

### 🟠 5. High — pipeline_manager stdin.write 无 drain

- **文件**：`ink_writer/parallel/pipeline_manager.py:296-297`
- **证据**：
  ```python
  proc.stdin.write(prompt.encode())
  proc.stdin.close()
  ```
- **风险**：asyncio stdin 有 buffer，大 prompt (gemini 平台的中文 prompt 可能 >64KB) 可能未 flush 就被 close；缺 `await proc.stdin.drain()` / `await proc.stdin.wait_closed()`。症状：gemini 子进程读到截断 prompt，写出不完整章节。
- **建议**：改为
  ```python
  proc.stdin.write(prompt.encode())
  await proc.stdin.drain()
  proc.stdin.close()
  await proc.stdin.wait_closed()
  ```

### 🟠 6. High — 03_classify/05_extract_rules per-file except 吞 + 无总体 fail gate

- **文件**：`scripts/editor-wisdom/03_classify.py:128-132`、`05_extract_rules.py:154-160`
- **证据**：
  ```python
  try:
      result = _classify_one(body, entry["title"])
  except Exception as exc:
      _append_error(data_dir, file_hash, entry.get("filename", ""), exc)
      continue
  ```
- **风险**：若所有文件 LLM 调用失败（API outage），`continue` 288 次，最终输出"Classified: 288 (API calls: 0)"假成功。cache 被写空，下次 rebuild 继承坏结果。
- **建议**：添加"连续 N 次失败则整体 abort"门禁。

### 🟠 7. High — 死代码导致维护误解

- **文件**：`ink_writer/editor_wisdom/writer_injection.py:65-71`、`ink_writer/editor_wisdom/context_injection.py:72-79`
- **证据**：
  ```python
  if retriever is None:
      try:
          retriever = Retriever()
      except EditorWisdomIndexMissingError:
          if config.enabled:
              raise
          return WriterConstraintsSection(chapter_no=chapter_no)  # 不可达
      except Exception:
          if config.enabled:
              raise
          return WriterConstraintsSection(chapter_no=chapter_no)  # 不可达
  ```
  上文 line 58-59 已有 `if not config.enabled: return ...`，因此此处 `config.enabled` 必为 True，`return` 分支死代码。
- **风险**：阅读者误以为存在"禁用时的 graceful fallback"。未来修改 config gate 逻辑时可能依赖此假设。
- **建议**：简化为 `except (EditorWisdomIndexMissingError, Exception): raise`。

### 🟡 8. Medium — pipeline_manager json.loads + dict.get 链无类型保护

- **文件**：`ink_writer/parallel/pipeline_manager.py:418-423`
- **证据**：
  ```python
  try:
      result = await self._ink_py("checkpoint-level", ...)
      cp = json.loads(result)
      if not cp.get("review"):
          return
  except Exception:
      return
  ```
- **风险**：若 `ink.py` 输出格式变化（如返回 list），`.get` 抛 AttributeError 被 `except Exception` 兜住 → 检查点静默跳过。症状：写了 20 章都没触发审查。
- **建议**：`if not isinstance(cp, dict): logger.error("malformed checkpoint output"); return`。

### 🟡 9. Medium — chapter_lock 跨 event-loop connection 共享风险（潜伏）

- **文件**：`ink_writer/parallel/chapter_lock.py:48-54`
- **证据**：`_local = threading.local()`，在 asyncio 下 `threading.local` 仅区分 OS thread，不区分 asyncio task。如果多个 asyncio task 共用同一 thread（单 loop 场景下必然），那么多个 task 并发调 `state_update_lock` 会竞争同一个 `sqlite3.Connection`，而 SQLite connection 非线程/协程安全。
- **风险**：当前 `PipelineManager` 未引用 `ChapterLockManager`（见风险 #1），问题潜伏；一旦修复 #1 接入，这个坑立即暴露。
- **建议**：改为 per-call 短连接（每次 `try_acquire` 自己开 connection），或用 `asyncio.Lock` 序列化同 loop 内调用。

### 🟡 10. Medium — 未使用 import / 小代码异味

- `ink_writer/parallel/pipeline_manager.py:14,15` `import os`、`import shutil` 未使用。
- `ink_writer/parallel/pipeline_manager.py:354,381,404` 函数内 `import re`、`import glob` 反复执行。
- `ink-writer/scripts/data_modules/style_sampler.py:99,103` 和 `index_manager.py:1019,1027` f-string 拼 DDL。
- **影响**：单独看每项都轻微，累积是"代码质量退化信号"。US-011 重构议题可批处理。

---

## 附录：扫描结论

| 类别 | 发现数 | 备注 |
|---|---|---|
| 裸 `except:` | 0 | |
| 过宽 `except Exception:` | 18 处 | 其中 6 处为静默吞风险点 |
| 可变默认参数 | 0 | dataclass + field(default_factory) 规范 |
| 未关闭文件句柄 | 0 | 全部 `with open` |
| SQL 字符串拼接（用户可控） | 0 | |
| SQL f-string（内部 DDL） | 7 处 | 低风险技术债 |
| 死代码 | 4 处 | writer_injection/context_injection |
| 未使用 import | 2 处 | pipeline_manager |
| 并发 race（真实触发） | 2 处 | pipeline_manager 未接 ChapterLockManager + stdin 未 drain |
| None deref（真实触发） | 0 | |
| 无限循环（真实触发） | 0 | |

**整体风险级别**：**MEDIUM-HIGH**

理由：代码基础卫生（except、文件句柄、可变默认）很好，但并发模块（US-401 对应）存在名不副实的 Blocker，且 editor-wisdom（CLAUDE.md Top 3 #1/#2）的护栏落实不完整。一旦有人打开 `PipelineConfig.parallel > 1` 就可能产生数据损坏，而两个 API Key 校验缺口又影响 rebuild 体验。

---

**报告路径**：`/Users/cipher/AI/ink/ink-writer/docs/audit/10-bug-scan.md`
**Top 3 风险**：
1. **Blocker** — `pipeline_manager.py` 并发写未接入 `ChapterLockManager`（文档/实现不一致，数据损坏潜在）
2. **Critical** — `03_classify.py` / `05_extract_rules.py` 缺入口 API Key 校验
3. **Critical** — `step3_harness_gate.py:135` 等路径每章新建 `Retriever()`，~30s/次冷启动累积成分钟级开销
