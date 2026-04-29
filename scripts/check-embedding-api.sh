#!/bin/bash
# 验证 EMBED_API_KEY / RERANK_API_KEY 是否能真实调通 API。
# 用途：配完 ~/.claude/ink-writer/.env 之后跑一下，确认 key 没问题再回去跑 /ink-auto。
#
# 用法：
#   bash scripts/check-embedding-api.sh
#
# 检查内容：
#   1. ~/.claude/ink-writer/.env 是否存在
#   2. EMBED_API_KEY 是否有值（且不是模板占位符）
#   3. 实际调用一次 embed API，看返回的向量是否非空
#   4. RERANK_API_KEY 同样验证
#
# 任一项失败会打印具体修法。

# 不开 -u：本脚本里中文标点（如 `）`）紧贴 `$VAR` 时 bash 会把 UTF-8 字节误读为变量名
# 报 "unbound variable"。验证脚本不需要严格未定义变量保护。
set -o pipefail

CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude}"
ENV_FILE="${CLAUDE_HOME}/ink-writer/.env"

echo "═══════════════════════════════════════"
echo "  Ink Writer Embedding/Rerank API 检查"
echo "═══════════════════════════════════════"
echo ""

# 1. 检查 .env 是否存在
if [[ ! -f "$ENV_FILE" ]]; then
    echo "❌ .env 文件不存在: $ENV_FILE"
    echo ""
    echo "   修法："
    echo "   mkdir -p $(dirname \"$ENV_FILE\")"
    echo "   cp <ink-writer-repo>/templates/dotenv-template.env \"$ENV_FILE\""
    echo "   然后用编辑器打开填两个 key"
    exit 1
fi
echo "✅ .env 存在: $ENV_FILE"

# 2. 加载 .env 到当前 shell（不覆盖已有 env）
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

# 3. 检查 EMBED_API_KEY
EMBED_KEY="${EMBED_API_KEY:-}"
if [[ -z "$EMBED_KEY" ]] || [[ "$EMBED_KEY" == *"在此处粘贴"* ]] || [[ "$EMBED_KEY" == *"your_"* ]]; then
    echo "❌ EMBED_API_KEY 未配置或仍是模板占位符"
    echo "   去 https://modelscope.cn 注册 → 个人中心 → 访问令牌 → 创建 token"
    echo "   把 token 粘贴到 $ENV_FILE 的 EMBED_API_KEY 行"
    exit 1
fi
echo "✅ EMBED_API_KEY 已设置（${EMBED_KEY:0:6}...${EMBED_KEY: -4}，共 ${#EMBED_KEY} 字符）"

EMBED_URL="${EMBED_BASE_URL:-https://api-inference.modelscope.cn/v1}"
EMBED_MODEL_NAME="${EMBED_MODEL:-Qwen/Qwen3-Embedding-8B}"
echo "   URL=${EMBED_URL}"
echo "   Model=${EMBED_MODEL_NAME}"

# 4. 实际调 embed API
echo ""
echo "🔌 测试 Embedding API..."
EMBED_RESP=$(curl -sS -X POST "${EMBED_URL%/}/embeddings" \
    -H "Authorization: Bearer ${EMBED_KEY}" \
    -H "Content-Type: application/json" \
    -d "{\"model\":\"${EMBED_MODEL_NAME}\",\"input\":[\"测试文本：写小说的软件测试一下\"]}" \
    --max-time 30 2>&1)

if echo "$EMBED_RESP" | grep -q '"embedding"'; then
    DIM=$(echo "$EMBED_RESP" | python3 -c "import sys,json; print(len(json.load(sys.stdin)['data'][0]['embedding']))" 2>/dev/null || echo "?")
    echo "✅ Embedding API 调通（向量维度 = ${DIM}）"
else
    echo "❌ Embedding API 失败，返回内容："
    echo "$EMBED_RESP" | head -c 800
    echo ""
    echo ""
    echo "   常见原因："
    echo "   1) Token 写错或过期 → 去 https://modelscope.cn/my/myaccesstoken 重新生成"
    echo "   2) 模型名写错 → 默认 Qwen/Qwen3-Embedding-8B（注意大小写和斜杠）"
    echo "   3) 网络不通 → 检查是否需要代理"
    exit 1
fi

# 5. 检查 RERANK_API_KEY
echo ""
RERANK_KEY="${RERANK_API_KEY:-}"
if [[ -z "$RERANK_KEY" ]] || [[ "$RERANK_KEY" == *"在此处粘贴"* ]] || [[ "$RERANK_KEY" == *"your_"* ]]; then
    echo "❌ RERANK_API_KEY 未配置或仍是模板占位符"
    echo "   去 https://jina.ai 注册 → API Keys 页面 → 复制 key"
    echo "   把 key 粘贴到 $ENV_FILE 的 RERANK_API_KEY 行"
    exit 1
fi
echo "✅ RERANK_API_KEY 已设置（${RERANK_KEY:0:6}...${RERANK_KEY: -4}）"

RERANK_URL="${RERANK_BASE_URL:-https://api.jina.ai/v1}"
RERANK_MODEL_NAME="${RERANK_MODEL:-jina-reranker-v3}"
echo "   URL=${RERANK_URL}"
echo "   Model=${RERANK_MODEL_NAME}"

# 6. 实际调 rerank API（按 base_url 自动判断协议格式）
echo ""
echo "🔌 测试 Rerank API..."
if [[ "$RERANK_URL" == *"dashscope.aliyuncs.com"* ]]; then
    # 阿里 DashScope native 格式：input 嵌套 + parameters
    DASHSCOPE_RERANK_PATH="${RERANK_URL%/}"
    if [[ "$DASHSCOPE_RERANK_PATH" != *"/text-rerank" ]]; then
        DASHSCOPE_RERANK_PATH="${DASHSCOPE_RERANK_PATH%/}/services/rerank/text-rerank/text-rerank"
    fi
    RERANK_RESP=$(curl -sS -X POST "${DASHSCOPE_RERANK_PATH}" \
        -H "Authorization: Bearer ${RERANK_KEY}" \
        -H "Content-Type: application/json" \
        -d "{\"model\":\"${RERANK_MODEL_NAME}\",\"input\":{\"query\":\"农村养殖\",\"documents\":[\"养鸡场\",\"科幻小说\",\"种田文\"]},\"parameters\":{\"top_n\":3,\"return_documents\":false}}" \
        --max-time 30 2>&1)
    if echo "$RERANK_RESP" | grep -q '"relevance_score"'; then
        echo "✅ Rerank API 调通（DashScope native 协议）"
    else
        echo "❌ Rerank API 失败（DashScope 协议），返回内容："
        echo "$RERANK_RESP" | head -c 800
        echo ""
        echo "   常见原因："
        echo "   1) sk- 开头的千问 key 写错或过期"
        echo "   2) 模型名写错 → 应为 gte-rerank-v2"
        echo "   3) 千问账户没开通 rerank 服务（去 https://bailian.console.aliyun.com 开通）"
        exit 1
    fi
else
    # Jina / Cohere 兼容协议
    RERANK_RESP=$(curl -sS -X POST "${RERANK_URL%/}/rerank" \
        -H "Authorization: Bearer ${RERANK_KEY}" \
        -H "Content-Type: application/json" \
        -d "{\"model\":\"${RERANK_MODEL_NAME}\",\"query\":\"农村养殖\",\"documents\":[\"养鸡场\",\"科幻小说\",\"种田文\"],\"top_n\":3}" \
        --max-time 30 2>&1)
    if echo "$RERANK_RESP" | grep -q '"relevance_score"'; then
        echo "✅ Rerank API 调通（OpenAI/Jina 兼容协议）"
    else
        echo "❌ Rerank API 失败，返回内容："
        echo "$RERANK_RESP" | head -c 800
        echo ""
        echo "   常见原因："
        echo "   1) Jina key 写错 / 额度耗尽 → 去 https://jina.ai 检查"
        echo "   2) 模型名写错 → 默认 jina-reranker-v3"
        exit 1
    fi
fi

echo ""
echo "═══════════════════════════════════════"
echo "  ✅ 全部通过，可以放心跑 /ink-auto"
echo "═══════════════════════════════════════"
