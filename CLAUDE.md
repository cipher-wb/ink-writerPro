# Ink Writer Pro - 开发指南

## 编辑智慧模块

基于编辑星河 288 份写作建议构建的本地 RAG 知识库，作为硬约束融入写作全链路。

详细文档：[docs/editor-wisdom-integration.md](docs/editor-wisdom-integration.md)

### Top 3 注意事项

1. **retriever 加载慢**：首次 `import Retriever` 会加载 sentence-transformers 模型（~30s），在 CLI 和测试中应延迟导入或使用 module-scoped fixture
2. **分类/规则抽取需要 API Key**：步骤 03_classify 和 05_extract_rules 依赖 ANTHROPIC_API_KEY 环境变量，本机 `.zshrc` 默认 unset 了它
3. **agent 规格文件统一目录**：所有 agent 规格均在 `ink-writer/agents/`（US-402 已消除双目录）

## Live-Review 模块（新增 v26.x）

基于 174 份起点编辑星河 B 站直播录像字幕稿构建的**作品病例 / 题材接受度信号 / 新原子规则候选**三类产物，分别接入 ink-writer 的 init / write / review 三阶段。与 `editor-wisdom` **并列共存不替换**：editor-wisdom 抽抽象规则，live-review 抽具体反例 + 含分数。

详细文档：[docs/live-review-integration.md](docs/live-review-integration.md)

### Top 3 注意事项

1. **首次接入需跑 §M-1..§M-9**：ralph 跑完 14 条 US 不会自动跑切分 / 聚合 / 索引，必须按 `docs/live-review-integration.md` §M-1..§M-9 顺序手动触发（§M-3 跑 174 份耗时 1-3 小时，§M-7 人工审核 1-2 小时）
2. **case_id prefix 是 `CASE-LR-2026-`**：底层复用 `case_library._id_alloc.allocate_case_id`，counter file 自动隔离 (`.id_alloc_case_lr_2026.cnt`)；不要新写 ID 分配器
3. **新规则永远走人工审核闸**：`extract_rule_candidates.py` 抽出的候选 `approved` 字段初始 `null`；只有 `review_rule_candidates.py` 标 `approved=true` 后 `promote_approved_rules.py` 才写入 `data/editor-wisdom/rules.json`（带 `source: live_review`）

## Prose Anti-AI 模块（新增 v26.x）

基于文笔反 AI 味 + 爆款白话化深层重构的七层改造：anti-detection 零容忍标点规则 / 装逼词黑名单 + 替换映射 / colloquial-checker 5 维白话度门禁 / directness-checker 全场景 7 维度 + 爆款档 / writer-agent L12 对话+动作驱动律 / 爆款示例 RAG few-shot / polish-agent Hard Block Rewrite Mode。

详细文档：[docs/prose-anti-ai-overhaul.md](docs/prose-anti-ai-overhaul.md)

### Top 3 注意事项

1. **D4 句长中位数 mid-is-better**：极短句（<8字）触发 red。写 prose 测试 fixture 时句子要在 13-17 字范围，否则 D4 会自动 red 破坏预期。
2. **三个独立回滚开关 + 总开关**：`config/anti-detection.yaml` 的 `prose_overhaul_enabled` 为总开关（false 时 3 个子开关全强制 false）；三个子开关可独立关闭（`colloquial.yaml` / `anti-detection.yaml` / `parallel-pipeline.yaml`）。回滚 SOP 见 `docs/prose-anti-ai-overhaul.md` 第五章。
3. **`check_zero_tolerance()` 返回 `str | None`**：命中规则→返回 rule ID 字符串，未命中→返回 None。调用方用 `is not None` 检查，不要用 `len()` 或 `bool()`（None 和空字符串 bool 值不一致）。

## Windows 兼容守则（feat/windows-compat 起生效）

面向 Claude Code 场景新增的 Windows 兼容层；Mac/Linux 行为与原先**字节级一致**（`.sh` 全部保留不动，所有 Windows 特化代码走 `if sys.platform == "win32":` 分支）。新代码提交前请自检：

1. **`open()` 必带 `encoding="utf-8"`**：Windows 默认 cp936/GBK，中文项目若省略参数会在某些路径炸出 `UnicodeDecodeError`。二进制模式（`"b"`）保持不变。同理 `Path.read_text()` / `write_text()`。
2. **Python 入口必调 `runtime_compat.enable_windows_utf8_stdio()`**：新增带 `if __name__ == "__main__":` 的脚本，在 main 函数开头调一次（Mac no-op）。
3. **面向用户的 CLI 必提供 PowerShell 对等入口**：新增 `.sh` 必须同时新增 `.ps1`（UTF-8 BOM 必需，PS 5.1 才能正确读中文）+ `.cmd` 双击包装；`ink-writer/skills/*/SKILL.md` 若引用 `.sh` 必须在同文件内附带 Windows PowerShell sibling 块（参考 `_patch_skills_win.py` 已做过的模式）。

规则参考：`ink-writer/scripts/runtime_compat.py` 提供 `set_windows_proactor_policy()` / `_has_symlink_privilege()` / `find_python_launcher()` / `enable_windows_utf8_stdio()` 共享原语，优先复用而非重写。
