#!/bin/bash
# start.sh — 启动 ink-writer Qdrant 单机实例（Mac/Linux）。
#
# 行为：
#   1. docker compose up -d 启动 qdrant/qdrant:v1.12.4（端口 6333 REST + 6334 gRPC）
#   2. 轮询 http://127.0.0.1:6333/readyz 最多 30 秒
#   3. ready 打印 "Qdrant is ready." 退 0；超时退 1
#
# 用法：
#   scripts/qdrant/start.sh
#
# 停止请用 scripts/qdrant/stop.sh。

set -euo pipefail

THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cd "$THIS_DIR"

docker compose up -d

READY_URL="http://127.0.0.1:6333/readyz"
TIMEOUT_SECONDS=30

elapsed=0
while [ "$elapsed" -lt "$TIMEOUT_SECONDS" ]; do
    if curl -fsS -o /dev/null "$READY_URL"; then
        echo "Qdrant is ready."
        exit 0
    fi
    sleep 1
    elapsed=$((elapsed + 1))
done

echo "Qdrant did not become ready within ${TIMEOUT_SECONDS}s (probed $READY_URL)." >&2
exit 1
