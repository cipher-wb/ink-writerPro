# Ink Writer Pro - 开发指南

## 编辑智慧模块

基于编辑星河 288 份写作建议构建的本地 RAG 知识库，作为硬约束融入写作全链路。

详细文档：[docs/editor-wisdom-integration.md](docs/editor-wisdom-integration.md)

### Top 3 注意事项

1. **retriever 加载慢**：首次 `import Retriever` 会加载 sentence-transformers 模型（~30s），在 CLI 和测试中应延迟导入或使用 module-scoped fixture
2. **分类/规则抽取需要 API Key**：步骤 03_classify 和 05_extract_rules 依赖 ANTHROPIC_API_KEY 环境变量，本机 `.zshrc` 默认 unset 了它
3. **agent 规格文件统一目录**：所有 agent 规格均在 `ink-writer/agents/`（US-402 已消除双目录）
4. **Python 包统一到 `ink_writer/`**：原 `ink-writer/scripts/data_modules/` 已于 FIX-11（US-026）合并至 `ink_writer/core/{state,index,context,cli,extract,infra}/`。导入统一用 `from ink_writer.core.<bucket>.<module> import X`，不要再引用 `data_modules`。
