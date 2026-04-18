# FIX-11 设计稿：双包合并（`ink_writer/` vs `scripts/data_modules/`）

**Status**: 🛑 AWAITING USER DECISION
**Author**: Ralph (US-024)
**Date**: 2026-04-18
**Scope**: XL 重构，预计工期 1–2 个 session

---

## 1. 现状

仓库当前存在两个并行的 Python 包，职责彼此咬合但边界模糊：

### 1.1 `ink_writer/`（根级，新包，17 子包）

| 子包 | 职责 |
| --- | --- |
| `anti_detection` | AI 味检测、去 AI 味规则 |
| `checker_pipeline` | 章节检查流水线调度 |
| `cultural_lexicon` | 文化词汇库 |
| `editor_wisdom` | 编辑智慧 RAG（288 条规则）|
| `emotion` | 情绪曲线 / 心电图 |
| `foreshadow` | 伏笔生命周期 |
| `incremental_extract` | 增量实体抽取 |
| `pacing` | Strand Weave 节奏 |
| `parallel` | 并发调度 |
| `plotline` | 明暗线追踪 |
| `progression` | 人物成长进度（FIX-18） |
| `prompt_cache` | Prompt 缓存 |
| `propagation` | 反向传播（FIX-17） |
| `reader_pull` | 追读力 |
| `semantic_recall` | 语义召回 |
| `style_rag` | 文风 RAG |
| `voice_fingerprint` | Voice 一致性 |

- 特征：**域驱动**（by-feature）目录结构，每个子包自带 `tests/`、`schemas.py`、`README` 倾向
- 导入计数：`from ink_writer. … `  ≈ **90 处**
- 安装姿态：根目录即 import root，无需 `sys.path` 注入
- 新功能（FIX-17/18、检查器管线、RAG）几乎都落在此包

### 1.2 `ink-writer/scripts/data_modules/`（老包，37 模块）

| 模块类别 | 代表文件 |
| --- | --- |
| **状态/索引核心** | `state_manager.py`, `sql_state_manager.py`, `index_manager.py`, `index_*_mixin.py`（6 个）, `index_types.py`, `migrate_state_to_sqlite.py`, `snapshot_manager.py`, `schemas.py`, `state_validator.py` |
| **上下文装配** | `context_manager.py`, `context_ranker.py`, `context_weights.py`, `memory_compressor.py`, `query_router.py`, `writing_guidance_builder.py`, `rag_adapter.py` |
| **CLI/运维** | `ink.py`, `cli_args.py`, `cli_output.py`, `checkpoint_utils.py`, `observability.py`, `config.py` |
| **抽取/风格** | `entity_linker.py`, `genre_aliases.py`, `genre_profile_builder.py`, `style_anchor.py`, `style_sampler.py`, `golden_three.py`, `anti_ai_lint.py` |
| **基建** | `api_client.py` |
| **测试** | `tests/`（54 文件）|

- 特征：**扁平**模块集合 + `tests/` 同包；按"数据链"组织
- 导入计数：`from data_modules. … `  ≈ **32 处**（其中约一半来自 `scripts/` CLI entry，另一半来自 `data_modules/tests/`）
- 安装姿态：依赖调用方把 `ink-writer/scripts/` 注入 `sys.path`（`ink.py`、`migrate.py`、`extract_chapter_context.py` 都做此注入）
- `__init__.py` 刻意使用 **lazy import** 规避 `python -m data_modules.xxx` 的 RuntimeWarning——说明包路径设计本身即是痛点

### 1.3 关键摩擦点

1. **路径魔法**：所有 CLI 必须先 `# [FIX-11] sys.path.insert no longer required — ink_writer is importable`，否则 `import data_modules` 失败
2. **双 schemas.py**：`ink_writer/*/schemas.py`（域内） vs `data_modules/schemas.py`（全局）存在重叠风险
3. **测试路径**：`data_modules/tests/` 与 `ink_writer/*/tests/` 需要两套 pytest 配置
4. **历史债**：`data_modules/ink.py` 是主 CLI 入口，但新 agents 都指向 `ink_writer.*`
5. **CLAUDE.md US-402 已声明**："agent 规格文件统一目录" — 说明"去重双目录"是既定方向

---

## 2. 合并方向：二选一

### 方向 A：全部合到 `ink_writer/`（新包主导，推荐）

```
ink_writer/
  anti_detection/       # 原有 17 个域子包保持不动
  ...
  core/                 # ← NEW: 容纳 data_modules 内容
    state/              # state_manager, sql_state_manager, snapshot_manager,
                        #   state_validator, migrate_state_to_sqlite, schemas
    index/              # index_manager + 6 mixins + index_types
    context/            # context_manager, context_ranker, context_weights,
                        #   memory_compressor, query_router, writing_guidance_builder,
                        #   rag_adapter
    cli/                # ink.py (main entry), cli_args, cli_output, checkpoint_utils
    extract/            # entity_linker, genre_aliases, genre_profile_builder,
                        #   style_anchor, style_sampler, golden_three, anti_ai_lint
    infra/              # api_client, observability, config
  tests/                # 汇总 data_modules/tests/ 迁入（按上述子包分文件夹）
```

#### Pro
- ✅ 与 CLAUDE.md 既定方向一致（"新架构主导"）
- ✅ 已有 90 处 import 不变；仅需改 32 处 `data_modules.*` → `ink_writer.core.*`
- ✅ 消除 `sys.path` 注入——`ink_writer` 在仓库根，`pip install -e .` 即可
- ✅ 域目录结构统一（by-feature），消除 "扁平 vs 分层" 风格割裂
- ✅ 新增的 FIX-17/18 所在位置即未来主干

#### Con
- ⚠️ `scripts/data_modules/tests/` 54 个测试文件需要迁移 + 重写 import
- ⚠️ `ink-writer/scripts/ink.py` 薄壳需更新 forward 目标
- ⚠️ 短期 PR 体积大（一次性改 ~86 个文件 import）

#### 迁移步骤
1. **Step 1** 建空骨架：`ink_writer/core/{state,index,context,cli,extract,infra}/__init__.py`
2. **Step 2** Script-based 移动：`git mv` 每个 `.py`（保留历史）
3. **Step 3** 自动改 import：`scripts/fix11_rewrite_imports.py` 用 `libcst` 或 `ast` 替换 `data_modules.X` → `ink_writer.core.<bucket>.X`
4. **Step 4** 迁测试：`data_modules/tests/` → `ink_writer/core/tests/`（按 bucket 分）
5. **Step 5** 修薄壳：`scripts/ink.py`、`scripts/migrate.py` 去掉 `sys.path` 注入，改为 `from ink_writer.core.cli.ink import main`
6. **Step 6** 删 `data_modules/__init__.py` 及其 lazy-import 机制
7. **Step 7** `pytest --no-cov` 全量通过 + `ruff` / `mypy` 通过

#### 风险
- 🔴 （高）34 个 `index_*_mixin` 之间 circular import 风险，需在 bucket 化时保留 mixin 同一目录
- 🟡 （中）agent 规格文件（`.claude/agents/*.md`）里若硬编码 `data_modules.*` 路径，需同步搜改
- 🟢 （低）历史 `.pyc` 缓存需清理

---

### 方向 B：全部合到 `data_modules/`（老包主导，不推荐）

把 `ink_writer/` 17 个子包迁进 `ink-writer/scripts/data_modules/`，改为：
```
ink-writer/scripts/data_modules/
  core/                 # 原有 37 个模块
  features/
    anti_detection/
    checker_pipeline/
    ...（17 个）
```

#### Pro
- ✅ `scripts/` CLI 零变动
- ✅ data_modules 的 lazy-import 习惯可复用

#### Con
- ❌ 与 CLAUDE.md "新架构主导" 方向相反
- ❌ 要改 **90 处** `from ink_writer.*`，比方向 A 多 2.8×
- ❌ `sys.path` 注入病继续存在——新开发者上手成本高
- ❌ 把设计良好的域包塞进 `scripts/` 子目录，**层级更深**（4 级），IDE 自动补全体验差
- ❌ 包名带连字符的父目录（`ink-writer/`）对 Python 打包不友好

#### 迁移步骤
（略，与 A 对称但工作量翻倍）

#### 风险
- 🔴 （高）90 处 import 改动更容易漏
- 🔴 （高）未来 `pip install` 发包时包名字段混乱

---

## 3. 推荐方向

### ✅ 方向 A（合到 `ink_writer/`）

**理由三句话：**
1. **少数派服从多数派**：`from ink_writer.*` 有 90 处，`from data_modules.*` 只有 32 处，改动量 A 方案只有 B 的 1/3。
2. **架构方向一致**：CLAUDE.md US-402 已声明消除双目录，新功能（FIX-17/18、editor_wisdom、checker_pipeline）全在 `ink_writer/`，老包 `data_modules/` 增长停滞。
3. **消除路径魔法**：`ink_writer/` 在仓库根是标准 Python 包；`data_modules` 依赖 `sys.path` 注入是技术债的根源。

---

## 4. 实施阶段（方向 A）

| 阶段 | 任务 | 可回滚性 | 预估 |
| --- | --- | --- | --- |
| **P0** 准备 | 建 `ink_writer/core/{state,index,context,cli,extract,infra}/` 空骨架 + `__init__.py` | 纯新增，随时弃用 | 0.2h |
| **P1** 迁移 | 写 `scripts/fix11_migrate.py`：`git mv` + 改 import（`libcst` 语法树替换）| 脚本幂等；失败可 `git reset --hard` | 1.5h |
| **P2** 入口 | 改 `scripts/ink.py`、`scripts/migrate.py` 为薄壳：`from ink_writer.core.cli.ink import main` | 局部改动 | 0.3h |
| **P3** 测试 | 迁 `data_modules/tests/` → `ink_writer/core/tests/`；跑 `pytest --no-cov` | 若断测单独修 | 0.5h |
| **P4** 清理 | 删 `data_modules/__init__.py`、`data_modules/` 空目录；搜删所有 `# [FIX-11] sys.path.insert no longer required — ink_writer is importable` | commit 粒度细，可 revert | 0.3h |
| **P5** 文档 | 更新 CLAUDE.md、agents/*.md、docs/*.md 中旧路径 | 文本改动 | 0.2h |
| **P6** PYTHONPATH | 在 `pyproject.toml` / `setup.cfg` 加 `packages = ["ink_writer"]`，`pip install -e .` | 新增配置 | 0.2h |

**总计：约 3.2 小时**（单 session 可完成）

---

## 5. 回退预案

- 每个阶段独立 commit，commit message 前缀 `fix11-pA-N:`；任一阶段失败执行 `git reset --hard HEAD~1`
- 迁移脚本 `scripts/fix11_migrate.py` 支持 `--dry-run`，先出 diff 再真动
- 保留 `data_modules/__init__.py` 一个版本作为 transitional shim（内部 `from ink_writer.core.state import *`），灰度 1 个 session 后再删

---

## 6. 验收标准

1. **零回归**：`pytest --no-cov` 全量通过（基线：当前主干的 pass 数）
2. **零裸路径**：全仓库 `rg "sys.path.insert"` 结果为 0 或仅留 1 条注释过的兼容入口
3. **零 data_modules**：`rg "from data_modules|import data_modules"` 结果为 0
4. **导入健康**：`python -c "import ink_writer; import ink_writer.core.state.state_manager"` 无警告
5. **CLI 可跑**：`python -m ink_writer.core.cli.ink --help` 输出完整子命令
6. **文档同步**：CLAUDE.md 顶部 "Top 3 注意事项" 已移除双目录告警，agents/*.md 中无 `data_modules` 字样
7. **打包可行**：`pip install -e .` 成功，`ink-write --help`（若有 console_scripts）可用

---

## 7. 决策请求（✅ APPROVED）

- [x] **APPROVED: 方向 A**（合到 `ink_writer/core/`）
- [ ] ~~APPROVED: 方向 B~~
- [ ] ~~REVISE~~

---

## APPROVED BY USER: 方向 A

- **批准时间**：2026-04-18
- **批准人**：cipher-wb (insectwb@gmail.com)
- **批准范围**：按本文档第 2.A 节目标结构 + 第 4 节 P0–P6 阶段实施
- **后续动作**：
  1. US-025 按此方向实施 Migration Script（`scripts/fix11_migrate.py` with `libcst` + `--dry-run`）
  2. 每阶段独立 commit，前缀 `fix11-pA-N:`
  3. 任一阶段失败执行 `git reset --hard HEAD~1`
  4. 保留 `data_modules/__init__.py` transitional shim 一个 session 后再删
