#!/bin/bash
# Ink Writer 垃圾文件清理工具（task #3 第 1 档）
#
# 清理目标：
#   1. macOS 自动产生的 .DS_Store（19 个）
#   2. .git/*.lock.bak.* 残留（sandbox 操作留下）
#   3. 旧 e2e/audit log（可重生成的）
#   4. v27 自动 init 临时产物（init 完成后无用）
#   5. __pycache__ / .pytest_cache（可重建）
#
# 默认 dry-run（只列出不删除）。加 --apply 才真正删。
# 用法：
#   bash scripts/cleanup-junk.sh             # dry-run
#   bash scripts/cleanup-junk.sh --apply     # 实际删

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APPLY=0
[[ "${1:-}" == "--apply" ]] && APPLY=1

echo "═══════════════════════════════════════"
echo "  Ink Writer 垃圾清理工具"
echo "═══════════════════════════════════════"
echo "  仓库根: $REPO_ROOT"
if (( APPLY )); then
    echo "  模式:   ❗ APPLY（实际删除）"
else
    echo "  模式:   📋 DRY-RUN（只列出，加 --apply 实删）"
fi
echo ""

TOTAL_FILES=0
TOTAL_BYTES=0

_count() {
    local path="$1"
    [[ -e "$path" ]] || return
    # -s 强制单行总和（目录里多文件时 du -k 会输出每个子项一行，导致算术报错）
    local sz
    sz=$(du -sk "$path" 2>/dev/null | head -1 | awk '{print $1}' | tr -dc '0-9')
    TOTAL_FILES=$((TOTAL_FILES + 1))
    TOTAL_BYTES=$((TOTAL_BYTES + ${sz:-0}))
}

_remove_or_list() {
    local path="$1"
    if (( APPLY )); then
        rm -rf "$path" 2>/dev/null && echo "  🗑️  删除: ${path#$REPO_ROOT/}"
    else
        echo "  📄 [DRY] ${path#$REPO_ROOT/}"
    fi
}

# ─────────────────────────────────────────
# 1. macOS .DS_Store
# ─────────────────────────────────────────
echo "▶ 1. .DS_Store 文件"
while IFS= read -r f; do
    _count "$f"
    _remove_or_list "$f"
done < <(find "$REPO_ROOT" -name '.DS_Store' -not -path '*/.git/*' 2>/dev/null)
echo ""

# ─────────────────────────────────────────
# 2. .git lock 残留
# ─────────────────────────────────────────
echo "▶ 2. .git lock 残留 (.lock.bak.*)"
while IFS= read -r f; do
    _count "$f"
    _remove_or_list "$f"
done < <(find "$REPO_ROOT/.git" -maxdepth 2 -name '*.lock.bak.*' 2>/dev/null)
echo ""

# ─────────────────────────────────────────
# 3. __pycache__ / .pytest_cache
# ─────────────────────────────────────────
echo "▶ 3. Python 缓存（可重建）"
while IFS= read -r d; do
    _count "$d"
    _remove_or_list "$d"
done < <(find "$REPO_ROOT" -type d \( -name '__pycache__' -o -name '.pytest_cache' \) -not -path '*/.git/*' 2>/dev/null)
echo ""

# ─────────────────────────────────────────
# 4. 旧 run log（reports/ 下手工生成的）
# ─────────────────────────────────────────
echo "▶ 4. 旧 run log（reports/ 下，可重生成）"
for f in \
    "$REPO_ROOT/reports/e2e-smoke-mac.log" \
    "$REPO_ROOT/scripts/live-review/m3_batch.log" \
    "$REPO_ROOT/scripts/ralph/ralph.run.log"
do
    if [[ -f "$f" ]]; then
        _count "$f"
        _remove_or_list "$f"
    fi
done
echo ""

# ─────────────────────────────────────────
# 5. v27 临时产物（小说项目里）
# ─────────────────────────────────────────
echo "▶ 5. 小说项目里的 v27 临时产物（init 完成后无用）"
echo "    需要你手动指定项目目录，例如："
echo "      cd /Users/cipher/ai/小说/农村养殖场"
echo "      bash $REPO_ROOT/scripts/cleanup-junk.sh --apply --project ."
echo ""
PROJECT_DIR=""
for ((i=1; i<=$#; i++)); do
    [[ "${!i}" == "--project" ]] && {
        next=$((i + 1))
        PROJECT_DIR="${!next}"
        break
    }
done
if [[ -n "$PROJECT_DIR" ]] && [[ -d "$PROJECT_DIR" ]]; then
    PROJECT_DIR="$(cd "$PROJECT_DIR" && pwd)"
    echo "    项目目录: $PROJECT_DIR"
    for pat in '.ink-auto-blueprint.md' '.ink-auto-quick-draft.json' '.ink-auto-init-*.log'; do
        for f in "$PROJECT_DIR"/$pat; do
            if [[ -e "$f" ]]; then
                _count "$f"
                _remove_or_list "$f"
            fi
        done
    done
fi
echo ""

# ─────────────────────────────────────────
# 6. .git/objects 里 sandbox 残留的 tmp_obj_*（罕见，但偶尔会留下）
# ─────────────────────────────────────────
echo "▶ 6. .git tmp 对象残留"
TMP_OBJ_COUNT=$(find "$REPO_ROOT/.git/objects" -name 'tmp_obj_*' 2>/dev/null | wc -l | tr -d ' ')
if (( TMP_OBJ_COUNT > 0 )); then
    echo "  发现 ${TMP_OBJ_COUNT} 个 tmp_obj_*（git gc 会自动清理，无害）"
    if (( APPLY )); then
        find "$REPO_ROOT/.git/objects" -name 'tmp_obj_*' -delete 2>/dev/null
        echo "  🗑️  已清理"
    fi
else
    echo "  ✓ 无残留"
fi
echo ""

# ─────────────────────────────────────────
# 总结
# ─────────────────────────────────────────
echo "═══════════════════════════════════════"
if (( APPLY )); then
    echo "  ✅ 清理完成：${TOTAL_FILES} 个文件/目录，约 $((TOTAL_BYTES / 1024)) MB"
else
    echo "  📋 DRY-RUN 总计：${TOTAL_FILES} 个文件/目录，约 $((TOTAL_BYTES / 1024)) MB"
    echo ""
    echo "  实际删除请加 --apply：bash scripts/cleanup-junk.sh --apply"
    echo "  小说项目临时文件请加 --project <path>"
fi
echo "═══════════════════════════════════════"
