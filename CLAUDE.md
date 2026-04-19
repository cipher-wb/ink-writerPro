# Ink Writer Pro - 开发指南

## 编辑智慧模块

基于编辑星河 288 份写作建议构建的本地 RAG 知识库，作为硬约束融入写作全链路。

详细文档：[docs/editor-wisdom-integration.md](docs/editor-wisdom-integration.md)

### Top 3 注意事项

1. **retriever 加载慢**：首次 `import Retriever` 会加载 sentence-transformers 模型（~30s），在 CLI 和测试中应延迟导入或使用 module-scoped fixture
2. **分类/规则抽取需要 API Key**：步骤 03_classify 和 05_extract_rules 依赖 ANTHROPIC_API_KEY 环境变量，本机 `.zshrc` 默认 unset 了它
3. **agent 规格文件统一目录**：所有 agent 规格均在 `ink-writer/agents/`（US-402 已消除双目录）

## Windows 兼容守则（feat/windows-compat 起生效）

面向 Claude Code 场景新增的 Windows 兼容层；Mac/Linux 行为与原先**字节级一致**（`.sh` 全部保留不动，所有 Windows 特化代码走 `if sys.platform == "win32":` 分支）。新代码提交前请自检：

1. **`open()` 必带 `encoding="utf-8"`**：Windows 默认 cp936/GBK，中文项目若省略参数会在某些路径炸出 `UnicodeDecodeError`。二进制模式（`"b"`）保持不变。同理 `Path.read_text()` / `write_text()`。
2. **Python 入口必调 `runtime_compat.enable_windows_utf8_stdio()`**：新增带 `if __name__ == "__main__":` 的脚本，在 main 函数开头调一次（Mac no-op）。
3. **面向用户的 CLI 必提供 PowerShell 对等入口**：新增 `.sh` 必须同时新增 `.ps1`（UTF-8 BOM 必需，PS 5.1 才能正确读中文）+ `.cmd` 双击包装；`ink-writer/skills/*/SKILL.md` 若引用 `.sh` 必须在同文件内附带 Windows PowerShell sibling 块（参考 `_patch_skills_win.py` 已做过的模式）。

规则参考：`ink-writer/scripts/runtime_compat.py` 提供 `set_windows_proactor_policy()` / `_has_symlink_privilege()` / `find_python_launcher()` / `enable_windows_utf8_stdio()` 共享原语，优先复用而非重写。
