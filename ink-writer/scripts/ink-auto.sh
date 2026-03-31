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
# 读取当前章节号（提前定义，供预检使用）
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
# 大纲覆盖预检（批量启动前检查所有章节）
# ═══════════════════════════════════════════

CURRENT_CH=$(get_current_chapter)
if [[ -z "$CURRENT_CH" || "$CURRENT_CH" == "0" ]]; then
    # current_chapter=0 表示尚未开始写作，属正常；但若读取失败则需检查
    if ! python3 -X utf8 "$SCRIPTS_DIR/ink.py" --project-root "$PROJECT_ROOT" state get-progress 2>/dev/null | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
        echo "❌ 无法读取 state.json 进度信息，请检查项目状态"
        exit 1
    fi
    CURRENT_CH=${CURRENT_CH:-0}
fi

BATCH_START=$((CURRENT_CH + 1))
BATCH_END=$((CURRENT_CH + N))

echo "🔍 正在检查第${BATCH_START}章到第${BATCH_END}章的大纲覆盖..."

if ! python3 -X utf8 "$SCRIPTS_DIR/ink.py" --project-root "$PROJECT_ROOT" \
    check-outline --chapter "$BATCH_START" --batch-end "$BATCH_END"; then
    echo ""
    echo "═══════════════════════════════════════"
    echo "  ❌ 大纲预检失败 — 批量写作已中止"
    echo "  请先执行 /ink-plan 生成缺失的大纲"
    echo "═══════════════════════════════════════"
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
# 验证章节产出
# ═══════════════════════════════════════════

verify_chapter() {
    local ch="$1"
    local padded
    padded=$(printf "%04d" "$ch")

    # 1. 章节文件存在且非空（支持平铺和卷目录两种布局）
    local file
    file=$(ls "$PROJECT_ROOT/正文/第${padded}章"*.md 2>/dev/null | head -1)
    if [[ -z "$file" || ! -s "$file" ]]; then
        # 尝试卷目录布局: 正文/第N卷/第XXX章*.md
        file=$(find "$PROJECT_ROOT/正文" -name "第${padded}章*.md" -o -name "第$((ch))章*.md" 2>/dev/null | head -1)
    fi
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
    local exit_code=0

    case $PLATFORM in
        claude)
            claude -p "$prompt" \
                --permission-mode bypassPermissions \
                --no-session-persistence \
                2>&1 | tee "$log_file" &
            CHILD_PID=$!
            wait $CHILD_PID 2>/dev/null
            exit_code=$?
            CHILD_PID=""
            ;;
        gemini)
            echo "$prompt" | gemini --yolo \
                2>&1 | tee "$log_file" &
            CHILD_PID=$!
            wait $CHILD_PID 2>/dev/null
            exit_code=$?
            CHILD_PID=""
            ;;
        codex)
            codex --approval-mode full-auto "$prompt" \
                2>&1 | tee "$log_file" &
            CHILD_PID=$!
            wait $CHILD_PID 2>/dev/null
            exit_code=$?
            CHILD_PID=""
            ;;
    esac

    # 检查进程退出码（非零可能是网络错误、超时、崩溃等）
    if (( exit_code != 0 )); then
        echo "⚠️  CLI 进程异常退出 (exit code: $exit_code)"
        echo "    可能原因：网络中断、API 超时、进程崩溃"
        echo "    日志文件：$log_file"
    fi
    return $exit_code
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
    local exit_code=0

    case $PLATFORM in
        claude)
            claude -p "$prompt" \
                --permission-mode bypassPermissions \
                --no-session-persistence \
                2>&1 | tee "$log_file" &
            CHILD_PID=$!
            wait $CHILD_PID 2>/dev/null
            exit_code=$?
            CHILD_PID=""
            ;;
        gemini)
            echo "$prompt" | gemini --yolo \
                2>&1 | tee "$log_file" &
            CHILD_PID=$!
            wait $CHILD_PID 2>/dev/null
            exit_code=$?
            CHILD_PID=""
            ;;
        codex)
            codex --approval-mode full-auto "$prompt" \
                2>&1 | tee "$log_file" &
            CHILD_PID=$!
            wait $CHILD_PID 2>/dev/null
            exit_code=$?
            CHILD_PID=""
            ;;
    esac

    if (( exit_code != 0 )); then
        echo "⚠️  重试进程异常退出 (exit code: $exit_code)"
        echo "    日志文件：$log_file"
    fi
    return $exit_code
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

    # 逐章大纲二次检查（防御性：防止批次预检后大纲被删除等极端情况）
    if ! python3 -X utf8 "$SCRIPTS_DIR/ink.py" --project-root "$PROJECT_ROOT" \
        check-outline --chapter "$NEXT_CH" >/dev/null 2>&1; then
        echo ""
        echo "[$i/$N] ❌ 第${NEXT_CH}章大纲缺失，中止批量写作"
        echo "    请先执行 /ink-plan 生成大纲后再重试"
        echo ""
        echo "已完成 $COMPLETED 章，未写章节不受影响"
        exit 1
    fi

    # 清理上一轮的 workflow 残留状态
    python3 -X utf8 "$SCRIPTS_DIR/ink.py" \
        --project-root "$PROJECT_ROOT" workflow clear 2>/dev/null || true

    echo ""
    echo "[$i/$N] 第${NEXT_CH}章 开始写作..."
    echo "───────────────────────────────────"

    # 执行写作
    if ! run_chapter "$NEXT_CH"; then
        echo "[$i/$N] ⚠️  第${NEXT_CH}章 CLI 进程异常，尝试验证产出..."
    fi

    # 冷却：确保 git commit / index 更新等异步操作完成
    sleep "$COOLDOWN"

    # 验证
    if verify_chapter "$NEXT_CH"; then
        WC=$(get_chapter_wordcount "$NEXT_CH")
        echo "[$i/$N] ✅ 第${NEXT_CH}章完成 | ${WC}字"
        COMPLETED=$((COMPLETED + 1))
    else
        echo "[$i/$N] ⚠️  验证失败，重试中..."

        if ! retry_chapter "$NEXT_CH"; then
            echo "[$i/$N] ⚠️  重试进程也异常退出"
        fi
        sleep "$COOLDOWN"

        if verify_chapter "$NEXT_CH"; then
            WC=$(get_chapter_wordcount "$NEXT_CH")
            echo "[$i/$N] ✅ 第${NEXT_CH}章完成（重试成功）| ${WC}字"
            COMPLETED=$((COMPLETED + 1))
        else
            echo ""
            echo "═══════════════════════════════════════"
            echo "  ❌ 第${NEXT_CH}章写作失败，批量写作中止"
            echo "═══════════════════════════════════════"
            echo "  已完成：$COMPLETED 章"
            echo "  失败章节：第${NEXT_CH}章"
            echo "  可能原因：网络中断、API 限流、上下文溢出"
            echo "  日志目录：$LOG_DIR"
            echo "  恢复方式：/ink-resume 或重新执行 /ink-auto"
            echo "═══════════════════════════════════════"
            exit 1
        fi
    fi
done

echo ""
echo "═══════════════════════════════════════"
echo "  完成！共写 $COMPLETED 章"
echo "═══════════════════════════════════════"
