#!/bin/bash
# stop.sh — 停止 ink-writer Qdrant 单机实例（Mac/Linux）。
#
# 行为：docker compose down（容器删除，./storage volume 保留用于下次启动）。

set -euo pipefail

THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cd "$THIS_DIR"

docker compose down
