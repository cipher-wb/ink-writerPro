# v16.0.0 Release Audit（Milestone C 收口）

**发布日期**：2026-04-18
**分支**：`ralph/v16-audit-completion`
**Baseline**：`pytest --no-cov` = `2843 passed, 19 skipped`（v15.9.0 基线 2738 → +105 净增测试；含 tests/release 20 发版门禁）
**版本一致性**：`ink-writer/.claude-plugin/plugin.json` / `pyproject.toml` / `.claude-plugin/marketplace.json` = `16.0.0`
**守卫脚本**：`scripts/verify_docs.py` 0 drift、新增 `tests/release/test_v16_gates.py` 全绿。

---

## 1. 27 US 完成清单（PRD v16-audit-completion）

| ID | 标题 | 里程碑 | Commit |
|----|------|--------|--------|
| US-001 | SKILL.md ChapterLockManager 虚假声明清除 + verify_docs.py 守卫 | Milestone A | `830787e` |
| US-002 | ChapterLockManager 接入 PipelineManager（并发根治） | Milestone A | `1d6697c` |
| US-003 | step3_runner 5 Gate checker_fn 接真 LLM（Phase B 主干） | Milestone A | `587be7c` |
| US-004 | step3_runner polish_fn 接真 polish-agent | Milestone A | `4ee19dc` |
| US-005 | step3_runner enforce 模式 E2E 真阻断 + 默认切换 | Milestone A | `7aa0d27` |
| US-006 | FIX-11 残留清理 + CI 门禁 | Milestone A | `641e974` |
| US-007 | LLM 调用显式 timeout | Milestone A | `9d8bfde` |
| US-008 | ink-auto 分层检查点 5/10/20/50/200 正式化 | Milestone A | `f4b911e` |
| US-009 | creativity/name_validator.py（陈词 + 书名黑名单） | Milestone B | `244ffe4` |
| US-010 | creativity/gf_validator.py（金手指三重约束） | Milestone B | `57fff49` |
| US-011 | creativity/sensitive_lexicon_validator.py（L0-L3 密度） | Milestone B | `75c72a0` |
| US-012 | creativity 扰动引擎 + 5 次重抽降档循环 Python 实装 | Milestone B | `5a5d540` |
| US-013 | creativity Quick Mode SKILL.md 集成 | Milestone B | `07d43a3` |
| US-014 | anti_detection ZT 正则扩展 + 连接词密度 | Milestone B | `b34bc6b` |
| US-015 | 黄金三章阈值软化 + 整章重写逃生门 | Milestone B | `c5a1aa1` |
| US-016 | 文笔维度 merged_fix_suggestion | Milestone B | `e973e87` |
| US-017 | 300 章 Shadow 压测（G1-G5 性能指标，零 LLM 费用） | Milestone B | `5e60e9c` |
| US-018 | Q1-Q8 质量指标仪表盘（SQL 直查，零费） | Milestone B | `7aaca46` |
| US-019 | v15.9.0 发布（Milestone A+B 收口） | Milestone B | `7a25d9a` |
| US-020 | Skill 规范修复（ink-plan allowed-tools + CI agent frontmatter 审计） | Milestone C | `b28fde5` |
| US-021 | Agent SDK 优化（prompt_cache 观测 + 模型选型 + batch API） | Milestone C | `2c9f9d5` |
| US-022 | 长记忆范式升级（BM25 + 2 层压缩 + reflection agent） | Milestone C | `ae6777a` |
| US-023 | architecture_audit 扫描扩展 + 孤儿清理 | Milestone C | `7208085` |
| US-024 | 日志规范化 + JSON/DB 源头统一 | Milestone C | `952bc96` |
| US-025 | import cycle 解构 + foreshadow/plotline tracker Python 合并 | Milestone C | `f582b27` |
| US-026 | 前 3 章 checker 冲突仲裁 + 细节收尾（API Key 守卫 + CLAUDE.md 精简） | Milestone C | `053abf8` |
| US-027 | v16.0.0 发布（Milestone C 收口） | Milestone C | `4f8ce28` |

**总计**：27/27 passes，Milestone A (8) + Milestone B (11) + Milestone C (8)。

---

## 2. 本轮明确排除（已记录，不纳入 v16.0.0）

1. **AI 审读员（F-010b）** — LLM 审读会被 checker 自己的偏见污染，**没有替代手段**。替代策略：压测后人读 100 / 200 / 300 章各 10 分钟，关注伏笔记忆 / AI 味 / 爽点 / OOC（见 README "如何验证"）。如未来需要单独立项，请新开 PRD。
2. **真 LLM 300 章压测（FIX-16）** — 单次成本高（数十美元量级），v15.9.0 已交付 mock shadow 压测骨架（US-017），真 LLM 压测不纳入本轮发版门禁。后续单独 PRD 走费用预审批流程。

---

## 3. 已知 TODO（非阻塞，发版后跟进）

- Dashboard `/quality` 与 `/cache` 页面的浏览器人工验证（当前仅后端 SQL 链路有单测覆盖）。
- jieba `pkg_resources` DeprecationWarning（依赖上游，跟 setuptools 81+ 发布节奏）。
- `tests/editor_wisdom/test_retriever_category.py` 在全量 pytest 全局 teardown 时偶发 "httpx client closed"（隔离运行全绿，pre-existing flake，不影响发版门禁；issue tracker 记录）。

---

## 4. 关键指标对比（v15.9.0 → v16.0.0）

| 指标 | v15.9.0 | v16.0.0 | Δ |
|------|---------|---------|---|
| pytest `--no-cov` | 2738 passed | 2843 passed | +105 |
| Skill 规范合规 | 29/30 | 30/30 | +1 |
| Agent frontmatter 完整 | 未守卫 | CI 门禁 | 新增 |
| `data_modules` 导入残留 | 0（FIX-11 已收口） | 0 | 保持 |
| Import cycle (`state ↔ index`) | 1 环 | 0 环 | 清零 |
| 覆盖率（总） | ~82% | ~82% | 持平 |
| 覆盖率门禁 | 70% | 70% | 持平 |

---

## 5. 发版 Gate 清单（tests/release/test_v16_gates.py）

- plugin.json.version == pyproject.toml.version == 16.0.0
- 全维度 sanity：creativity / checker_pipeline / parallel / editor_wisdom 均 importable
- `scripts/verify_docs.py` exit 0（subprocess 断言）

---

## 6. 归档

本次发版后以下文件归档或保留：
- `tasks/prd-v16-audit-completion.md`（原始 PRD）
- `ralph/prd.json`（27/27 passes）
- `ralph/progress.txt`（每轮迭代日志）
- `reports/audit-prompt-v15.md` / `audit-v15-findings.md` / `audit-v15-workflow.md`（v15 审计原始产物）
- `reports/perf-300ch-shadow-v15.md` / `perf-parallel-v15.md` / `quality-300ch-v15.md`（v15 压测与质量报告）
