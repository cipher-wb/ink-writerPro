# Ink Writer Pro - 开发指南

## 编辑智慧模块

基于编辑星河 288 份写作建议构建的本地 RAG 知识库，作为硬约束融入写作全链路。

详细文档：[docs/editor-wisdom-integration.md](docs/editor-wisdom-integration.md)

### Top 3 注意事项

1. **retriever 加载慢**：首次 `import Retriever` 会加载 sentence-transformers 模型（~30s），在 CLI 和测试中应延迟导入或使用 module-scoped fixture
2. **分类/规则抽取需要 API Key**：步骤 03_classify 和 05_extract_rules 依赖 ANTHROPIC_API_KEY 环境变量，本机 `.zshrc` 默认 unset 了它
3. **agent 规格文件有两个目录**：原项目 agents 在 `ink-writer/agents/`，editor-wisdom 新增的 agent 在 `agents/ink-writer/`，修改时注意区分
