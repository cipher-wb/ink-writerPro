#!/bin/bash
# ink-auto: 跨会话无人值守批量写作
# 每章启动全新 CLI 进程，进程退出 = 上下文自然清零
#
# 用法:
#   ink-auto 5     # 写 5 章
#   ink-auto       # 默认 5 章
#
# 前提: 在小说项目目录下运行（含 .ink/state.json）
# 支持: claude / gemini / codex（自动检测）

set -euo pipefail

N=${1:-5}
COOLDOWN=${INK_AUTO_COOLDOWN:-10}

# ═══════════════════════════════════════════
# 路径检测
# ═══════════════════════════════════════════

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SCRIPTS_DIR="${PLUGIN_ROOT}/scripts"

find_project_root() {
    local dir="$PWD"
    while [[ "$dir" != "/" ]]; do
        if [[ -f "$dir/.ink/state.json" ]]; then
            echo "$dir"
            return 0
        fi
        dir="$(dirname "$dir")"
    done
    return 1
}

PROJECT_ROOT="$(find_project_root)" || {
    echo "❌ 未找到 .ink/state.json，请在小说项目目录下运行"
    exit 1
}

LOG_DIR="${PROJECT_ROOT}/.ink/logs/auto"
mkdir -p "$LOG_DIR"

# ═══════════════════════════════════════════
# 平台检测
# ═══════════════════════════════════════════

PLATFORM=""
if command -v claude &>/dev/null; then
    PLATFORM=claude
elif command -v gemini &>/dev/null; then
    PLATFORM=gemini
elif command -v codex &>/dev/null; then
    PLATFORM=codex
else
    echo "❌ 未找到 claude / gemini / codex，请先安装其中之一"
    exit 1
fi

# ═══════════════════════════════════════════
# 预检
# ═══════════════════════════════════════════

if ! python3 -X utf8 "$SCRIPTS_DIR/ink.py" --project-root "$PROJECT_ROOT" preflight 2>/dev/null; then
    echo "❌ 预检失败，请检查项目状态"
    exit 1
fi

# ═══════════════════════════════════════════
# 信号处理
# ═══════════════════════════════════════════

CHILD_PID=""
INTERRUPTED=0

on_signal() {
    INTERRUPTED=1
    if [[ -n "$CHILD_PID" ]]; then
        kill -INT "$CHILD_PID" 2>/dev/null || true
        # 等待子进程优雅退出
        wait "$CHILD_PID" 2>/dev/null || true
    fi
    echo ""
    echo "🛑 已中止。已完成的章节不受影响。"
    exit 130
}

trap on_signal INT TERM

# ═══════════════════════════════════════════
# 读取当前章节号
# ═══════════════════════════════════════════

get_current_chapter() {
    python3 -X utf8 "$SCRIPTS_DIR/ink.py" \
        --project-root "$PROJECT_ROOT" state get-progress 2>/dev/null \
        | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('data', {}).get('current_chapter', 0))
except:
    print(0)
" 2>/dev/null || echo 0
}

# ═══════════════════════════════════════════
# 验证章节产出
# ═══════════════════════════════════════════

verify_chapter() {
    local ch="$1"
    local padded
    padded=$(printf "%04d" "$ch")

    # 1. 章节文件存在且非空
    local file
    file=$(ls "$PROJECT_ROOT/正文/第${padded}章"*.md 2>/dev/null | head -1)
    if [[ -z "$file" || ! -s "$file" ]]; then
        return 1
    fi

    # 2. 字数 >= 2200
    local char_count
    char_count=$(wc -m < "$file" | tr -d ' ')
    if (( char_count < 2200 )); then
        return 1
    fi

    # 3. state.json 中 current_chapter >= 预期
    local cur
    cur=$(get_current_chapter)
    if (( cur < ch )); then
        return 1
    fi

    # 4. 摘要文件存在
    if [[ ! -f "$PROJECT_ROOT/.ink/summaries/ch${padded}.md" ]]; then
        return 1
    fi

    return 0
}

# ═══════════════════════════════════════════
# 获取章节字数
# ═══════════════════════════════════════════

get_chapter_wordcount() {
    local ch="$1"
    local padded
    padded=$(printf "%04d" "$ch")
    local file
    file=$(ls "$PROJECT_ROOT/正文/第${padded}章"*.md 2>/dev/null | head -1)
    if [[ -n "$file" && -s "$file" ]]; then
        wc -m < "$file" | tr -d ' '
    else
        echo 0
    fi
}

# ═══════════════════════════════════════════
# 单章执行
# ═══════════════════════════════════════════

run_chapter() {
    local ch="$1"
    local padded
    padded=$(printf "%04d" "$ch")
    local log_file="$LOG_DIR/ch${padded}-$(date +%Y%m%d-%H%M%S).log"
    local prompt="使用 Skill 工具加载 \"ink-write\" 并完整执行所有步骤（Step 0 到 Step 6）。项目目录: ${PROJECT_ROOT}。禁止省略任何步骤，禁止提问，全程自主执行。完成后输出 INK_DONE。失败则输出 INK_FAILED。"

    case $PLATFORM in
        claude)
            claude -p "$prompt" \
                --permission-mode bypassPermissions \
                --no-session-persistence \
                2>&1 | tee "$log_file" &
            CHILD_PID=$!
            wait $CHILD_PID 2>/dev/null || true
            CHILD_PID=""
            ;;
        gemini)
            echo "$prompt" | gemini --yolo \
                2>&1 | tee "$log_file" &
            CHILD_PID=$!
            wait $CHILD_PID 2>/dev/null || true
            CHILD_PID=""
            ;;
        codex)
            codex --approval-mode full-auto "$prompt" \
                2>&1 | tee "$log_file" &
            CHILD_PID=$!
            wait $CHILD_PID 2>/dev/null || true
            CHILD_PID=""
            ;;
    esac
}

# ═══════════════════════════════════════════
# 重试（用 ink-resume）
# ═══════════════════════════════════════════

retry_chapter() {
    local ch="$1"
    local padded
    padded=$(printf "%04d" "$ch")
    local log_file="$LOG_DIR/ch${padded}-retry-$(date +%Y%m%d-%H%M%S).log"
    local prompt="使用 Skill 工具加载 \"ink-resume\"，恢复第${ch}章的写作并完成所有剩余步骤。项目目录: ${PROJECT_ROOT}。禁止提问，全程自主执行。完成后输出 INK_DONE。"

    case $PLATFORM in
        claude)
            claude -p "$prompt" \
                --permission-mode bypassPermissions \
                --no-session-persistence \
                2>&1 | tee "$log_file" &
            CHILD_PID=$!
            wait $CHILD_PID 2>/dev/null || true
            CHILD_PID=""
            ;;
        gemini)
            echo "$prompt" | gemini --yolo \
                2>&1 | tee "$log_file" &
            CHILD_PID=$!
            wait $CHILD_PID 2>/dev/null || true
            CHILD_PID=""
            ;;
        codex)
            codex --approval-mode full-auto "$prompt" \
                2>&1 | tee "$log_file" &
            CHILD_PID=$!
            wait $CHILD_PID 2>/dev/null || true
            CHILD_PID=""
            ;;
    esac
}

# ═══════════════════════════════════════════
# 主循环
# ═══════════════════════════════════════════

echo "═══════════════════════════════════════"
echo "  ink-auto | 写 $N 章 | $PLATFORM"
echo "  项目: $PROJECT_ROOT"
echo "  日志: $LOG_DIR"
echo "═══════════════════════════════════════"

COMPLETED=0

for i in $(seq 1 "$N"); do
    # 检查是否中断
    if (( INTERRUPTED )); then
        break
    fi

    # 读取下一章号
    CURRENT=$(get_current_chapter)
    NEXT_CH=$((CURRENT + 1))

    # 清理上一轮的 workflow 残留状态
    python3 -X utf8 "$SCRIPTS_DIR/ink.py" \
        --project-root "$PROJECT_ROOT" workflow clear 2>/dev/null || true

    echo ""
    echo "[$i/$N] 第${NEXT_CH}章 开始写作..."
    echo "───────────────────────────────────"

    # 执行写作
    run_chapter "$NEXT_CH"

    # 冷却：确保 git commit / index 更新等异步操作完成
    sleep "$COOLDOWN"

    # 验证
    if verify_chapter "$NEXT_CH"; then
        WC=$(get_chapter_wordcount "$NEXT_CH")
        echo "[$i/$N] 第${NEXT_CH}章完成 | ${WC}字"
        COMPLETED=$((COMPLETED + 1))
    else
        echo "[$i/$N] 验证失败，重试中..."

        retry_chapter "$NEXT_CH"
        sleep "$COOLDOWN"

        if verify_chapter "$NEXT_CH"; then
            WC=$(get_chapter_wordcount "$NEXT_CH")
            echo "[$i/$N] 第${NEXT_CH}章完成（重试成功）| ${WC}字"
            COMPLETED=$((COMPLETED + 1))
        else
            echo "[$i/$N] 第${NEXT_CH}章失败，中止批次"
            echo ""
            echo "已完成 $COMPLETED 章，失败章节可通过 /ink-resume 手动恢复"
            exit 1
        fi
    fi
done

echo ""
echo "═══════════════════════════════════════"
echo "  完成！共写 $COMPLETED 章"
echo "═══════════════════════════════════════"
