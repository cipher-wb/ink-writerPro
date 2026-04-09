# RAG（检索增强生成）使用指南

## 什么是 RAG？

ink-writer 内置了完整的语义检索系统，在写作时自动召回与当前章节相关的历史片段。这不是一个需要手动操作的功能，而是一个"隐形的记忆增强层"。

## RAG 在写作流水线中的运用

### 写入（每章自动执行）
- **Step 5（Data Agent）的 Step G**：将每章的场景切片和摘要嵌入为向量，存储到 `.ink/vectors.db`
- 同时生成 BM25 倒排索引，支持关键词检索

### 读取（每章自动执行）
- **Step 1（Context Agent）**：在构建创作执行包时，自动检索与本章大纲最相关的历史章节片段
- 检索结果作为 `rag_assist` 注入到上下文包，帮助 writer-agent 保持记忆一致性

### 检索策略（自动选择）

| 策略 | 触发条件 | 精度 | 速度 |
|------|---------|------|------|
| 混合检索(Hybrid) | 有Embed API Key | 最高 | 中 |
| BM25关键词 | 无API Key（默认降级） | 中 | 快 |
| 图谱增强(Graph) | 手动开启 `graph_rag_enabled=True` | 最高(实体关联) | 慢 |

### 三层降级保障
1. 向量+BM25混合 → 2. 纯BM25 → 3. 内存卡+摘要检索
任何一层失败都会自动降级到下一层，写作流程不会中断。

## 配置方法

### 方式1：ModelScope（推荐，免费）
```bash
# 在 ~/.claude/ink-writer/.env 中添加：
EMBED_API_KEY=你的ModelScope密钥
# 默认使用 Qwen3-Embedding-8B 模型
```

### 方式2：OpenAI
```bash
EMBED_BASE_URL=https://api.openai.com/v1
EMBED_MODEL=text-embedding-3-small
EMBED_API_KEY=你的OpenAI密钥
```

### 方式3：本地部署（Ollama/vLLM）
```bash
EMBED_BASE_URL=http://localhost:11434/v1
EMBED_MODEL=nomic-embed-text
EMBED_API_KEY=placeholder
```

## 验证

```bash
# 查看RAG统计
python ink.py --project-root 你的项目 rag stats

# 测试检索
python ink.py --project-root 你的项目 rag search --query "主角的能力" --mode auto --top-k 5
```

## 高级配置

在项目 `.env` 中可调整：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `GRAPH_RAG_ENABLED` | false | 启用图谱增强检索 |
| `VECTOR_TOP_K` | 30 | 向量检索返回数 |
| `BM25_TOP_K` | 20 | BM25检索返回数 |
| `RERANK_TOP_N` | 10 | Rerank精排返回数 |
| `CONTEXT_RAG_ASSIST_TOP_K` | 4 | 注入执行包的结果数 |
