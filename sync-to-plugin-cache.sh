#!/bin/bash
# 把源码仓库的修改同步到 Claude Code plugin cache。
# 用途：在源码仓库改完 ink-auto.sh / 其他 plugin 文件后，让 /ink-writer:ink-auto 立即生效。
#
# 用法：
#   bash sync-to-plugin-cache.sh
#
# 安全性：只复制 ink-writer/ 子目录（plugin 内容），不动 Python 包（Python 走源码 editable
# install，本来就不需要同步）。
set -euo pipefail

SRC_REPO="$(cd "$(dirname "$0")" && pwd)"
SRC_PLUGIN="${SRC_REPO}/ink-writer"
CACHE_PLUGIN="${HOME}/.claude/plugins/cache/ink-writer-marketplace/ink-writer/26.3.0"

if [[ ! -d "$CACHE_PLUGIN" ]]; then
    echo "❌ 未找到 plugin cache: $CACHE_PLUGIN"
    echo "   请先在 Claude Code 里安装/更新一次 ink-writer plugin"
    exit 1
fi

if [[ ! -d "$SRC_PLUGIN" ]]; then
    echo "❌ 源码 plugin 目录缺失: $SRC_PLUGIN"
    exit 1
fi

echo "源码 → plugin cache："
echo "  src:   $SRC_PLUGIN"
echo "  dst:   $CACHE_PLUGIN"
echo ""

# rsync 增量同步：只覆盖更新的文件，删除 plugin cache 里源码已删除的文件
# 排除测试 / __pycache__ / .git 等本不该出现在 plugin 里的目录
rsync -av --delete \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='.DS_Store' \
    --exclude='*.log' \
    "${SRC_PLUGIN}/" "${CACHE_PLUGIN}/"

echo ""
echo "✅ 同步完成。现在在你的小说项目目录跑 /ink-writer:ink-auto 5 即可用上最新修复。"
