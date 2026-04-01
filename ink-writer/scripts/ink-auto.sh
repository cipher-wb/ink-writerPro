#!/bin/bash
# ink-auto: 跨会话无人值守智能批量写作
# 每章启动全新 CLI 进程，进程退出 = 上下文自然清零
# 内置分层检查点：每5章审查+修复、每10章审计、每20章深度审查
# 内置自动大纲生成：写作前检测缺失大纲，自动启动 ink-plan
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
CHECKPOINT_COOLDOWN=${INK_AUTO_CHECKPOINT_COOLDOWN:-15}

# 统计计数器
REVIEW_COUNT=0
AUDIT_COUNT=0
MACRO_COUNT=0
PLAN_COUNT=0
FIX_COUNT=0
PLANNED_VOLUMES=":"  # 追踪已尝试生成大纲的卷（字符串匹配，兼容 bash 3.2）
COMPLETED=0

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
# 卷号检测（用于自动大纲生成）
# ═══════════════════════════════════════════

get_volume_for_chapter() {
    local ch="$1"
    python3 -X utf8 -c "
import json, re, sys
try:
    with open('${PROJECT_ROOT}/.ink/state.json') as f:
        state = json.load(f)
    volumes = state.get('project_info', {}).get('volumes', [])
    for v in volumes:
        r = v.get('chapter_range', '')
        m = re.match(r'(\d+)-(\d+)', r)
        if m and int(m.group(1)) <= $ch <= int(m.group(2)):
            vid = v.get('volume_id', v.get('id', ''))
            print(vid)
            sys.exit(0)
    print('')
except:
    print('')
" 2>/dev/null
}

# ═══════════════════════════════════════════
# 大纲覆盖预检（改为预报模式，不硬阻断）
# ═══════════════════════════════════════════

CURRENT_CH=$(get_current_chapter)
if [[ -z "$CURRENT_CH" || "$CURRENT_CH" == "0" ]]; then
    if ! python3 -X utf8 "$SCRIPTS_DIR/ink.py" --project-root "$PROJECT_ROOT" state get-progress 2>/dev/null | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
        echo "❌ 无法读取 state.json 进度信息，请检查项目状态"
        exit 1
    fi
    CURRENT_CH=${CURRENT_CH:-0}
fi

BATCH_START=$((CURRENT_CH + 1))
BATCH_END=$((CURRENT_CH + N))

echo "🔍 正在扫描第${BATCH_START}章到第${BATCH_END}章的大纲覆盖..."

if ! python3 -X utf8 "$SCRIPTS_DIR/ink.py" --project-root "$PROJECT_ROOT" \
    check-outline --chapter "$BATCH_START" --batch-end "$BATCH_END" 2>/dev/null; then
    echo ""
    echo "⚠️  部分章节大纲缺失，ink-auto 将在写作前自动生成"
    echo "    如需手动规划，请按 Ctrl+C 中止后执行 /ink-plan"
    echo ""
    sleep 5  # 给用户5秒决定是否中止
else
    echo "✅ 大纲覆盖完整"
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
        wait "$CHILD_PID" 2>/dev/null || true
    fi
    echo ""
    echo "🛑 已中止。已完成的章节不受影响。"
    # 输出已完成的统计
    print_summary
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
# CLI 进程启动通用函数
# ═══════════════════════════════════════════

run_cli_process() {
    local prompt="$1"
    local log_file="$2"
    local exit_code=0

    case $PLATFORM in
        claude)
            claude -p "$prompt" \
                --permission-mode bypassPermissions \
                --no-session-persistence \
                2>&1 | tee "$log_file" &
            CHILD_PID=$!
            wait $CHILD_PID 2>/dev/null && exit_code=0 || exit_code=$?
            CHILD_PID=""
            ;;
        gemini)
            echo "$prompt" | gemini --yolo \
                2>&1 | tee "$log_file" &
            CHILD_PID=$!
            wait $CHILD_PID 2>/dev/null && exit_code=0 || exit_code=$?
            CHILD_PID=""
            ;;
        codex)
            codex --approval-mode full-auto "$prompt" \
                2>&1 | tee "$log_file" &
            CHILD_PID=$!
            wait $CHILD_PID 2>/dev/null && exit_code=0 || exit_code=$?
            CHILD_PID=""
            ;;
    esac

    return $exit_code
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

    if ! run_cli_process "$prompt" "$log_file"; then
        echo "⚠️  CLI 进程异常退出"
        echo "    日志文件：$log_file"
        return 1
    fi
    return 0
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

    if ! run_cli_process "$prompt" "$log_file"; then
        echo "⚠️  重试进程异常退出"
        echo "    日志文件：$log_file"
        return 1
    fi
    return 0
}

# ═══════════════════════════════════════════
# 自动大纲生成
# ═══════════════════════════════════════════

auto_generate_outline() {
    local ch="$1"
    local vol
    vol=$(get_volume_for_chapter "$ch")

    if [[ -z "$vol" ]]; then
        echo "    ❌ 无法确定第${ch}章所属卷号，中止"
        return 1
    fi

    # 同一卷只尝试一次（bash 3.2 兼容：字符串匹配）
    if [[ "$PLANNED_VOLUMES" == *":${vol}:"* ]]; then
        echo "    ❌ 第${vol}卷大纲已尝试生成但仍缺失，中止"
        return 1
    fi
    PLANNED_VOLUMES="${PLANNED_VOLUMES}${vol}:"

    echo "    📋 第${vol}卷大纲缺失，自动启动 ink-plan..."
    local log_file="$LOG_DIR/plan-vol${vol}-$(date +%Y%m%d-%H%M%S).log"
    local prompt="使用 Skill 工具加载 \"ink-plan\"。为第${vol}卷生成完整详细大纲（节拍表+时间线+章纲）。项目目录: ${PROJECT_ROOT}。禁止提问，自动选择第${vol}卷，全程自主执行。完成后输出 INK_PLAN_DONE。"

    run_cli_process "$prompt" "$log_file" || true

    PLAN_COUNT=$((PLAN_COUNT + 1))
    sleep "$CHECKPOINT_COOLDOWN"

    # 验证大纲是否生成成功
    if python3 -X utf8 "$SCRIPTS_DIR/ink.py" --project-root "$PROJECT_ROOT" \
        check-outline --chapter "$ch" >/dev/null 2>&1; then
        echo "    ✅ 第${vol}卷大纲生成成功"
        return 0
    else
        echo "    ❌ 第${vol}卷大纲生成失败，中止批量写作"
        echo "    日志文件：$log_file"
        return 1
    fi
}

# ═══════════════════════════════════════════
# 检查点：审查 + 自动修复
# ═══════════════════════════════════════════

run_review_and_fix() {
    local start="$1"
    local end="$2"
    local log_file="$LOG_DIR/review-ch${start}-${end}-$(date +%Y%m%d-%H%M%S).log"
    local prompt="使用 Skill 工具加载 \"ink-review\"。审查范围：第${start}章到第${end}章。审查深度：Core。项目目录: ${PROJECT_ROOT}。全程自主执行，禁止提问。发现 critical 或 high 问题时选择选项 A（立即修复），修复后自动重审验证。完成后输出 INK_REVIEW_DONE。"

    echo "    🔍 审查第${start}-${end}章 (Core)..."

    run_cli_process "$prompt" "$log_file" || true

    REVIEW_COUNT=$((REVIEW_COUNT + 1))
    sleep "$CHECKPOINT_COOLDOWN"

    # 检查审查报告
    local report_file="${PROJECT_ROOT}/审查报告/第${start}-${end}章审查报告.md"
    if [[ -f "$report_file" ]]; then
        if grep -q "critical" "$report_file" 2>/dev/null; then
            FIX_COUNT=$((FIX_COUNT + 1))
        fi
        echo "    ✅ 审查完成，报告: 审查报告/第${start}-${end}章审查报告.md"
    else
        echo "    ⚠️  审查进程完成，但未找到报告文件"
        echo "    日志文件：$log_file"
    fi
}

# ═══════════════════════════════════════════
# 检查点：数据审计
# ═══════════════════════════════════════════

run_audit() {
    local depth="$1"  # quick / standard / deep
    local log_file="$LOG_DIR/audit-${depth}-$(date +%Y%m%d-%H%M%S).log"
    local prompt="使用 Skill 工具加载 \"ink-audit\"。审计深度：${depth}。项目目录: ${PROJECT_ROOT}。全程自主执行，禁止提问。完成后输出 INK_AUDIT_DONE。"

    echo "    📊 数据审计 (${depth})..."

    run_cli_process "$prompt" "$log_file" || true

    AUDIT_COUNT=$((AUDIT_COUNT + 1))
    sleep "$CHECKPOINT_COOLDOWN"

    echo "    ✅ 审计完成"
}

# ═══════════════════════════════════════════
# 检查点：宏观审查
# ═══════════════════════════════════════════

run_macro_review() {
    local tier="$1"  # Tier2 / Tier3
    local log_file="$LOG_DIR/macro-${tier}-$(date +%Y%m%d-%H%M%S).log"
    local prompt="使用 Skill 工具加载 \"ink-macro-review\"。审查层级：${tier}。项目目录: ${PROJECT_ROOT}。全程自主执行，禁止提问。完成后输出 INK_MACRO_DONE。"

    echo "    🔭 宏观审查 (${tier})..."

    run_cli_process "$prompt" "$log_file" || true

    MACRO_COUNT=$((MACRO_COUNT + 1))
    sleep "$CHECKPOINT_COOLDOWN"

    echo "    ✅ 宏观审查完成"
}

# ═══════════════════════════════════════════
# 检查点：消歧积压检查
# ═══════════════════════════════════════════

check_disambiguation_backlog() {
    local count
    count=$(python3 -X utf8 -c "
import json
try:
    with open('${PROJECT_ROOT}/.ink/state.json') as f:
        s = json.load(f)
    print(len(s.get('disambiguation_pending', [])))
except:
    print(0)
" 2>/dev/null || echo 0)

    if (( count > 100 )); then
        echo "    ⚠️⚠️ 消歧积压 ${count} 条！强烈建议暂停批量写作，手动执行 /ink-resolve"
    elif (( count > 20 )); then
        echo "    ⚠️  消歧积压 ${count} 条，建议择机执行 /ink-resolve"
    else
        echo "    ✅ 消歧积压 ${count} 条（正常）"
    fi
}

# ═══════════════════════════════════════════
# 检查点编排器
# ═══════════════════════════════════════════

run_checkpoint() {
    local ch="$1"

    # 不是5的倍数，跳过
    if (( ch % 5 != 0 )); then
        return 0
    fi

    echo ""
    echo "───────── 📋 检查点：第${ch}章 ─────────"

    # 从高到低执行审计（高层级先行，结果可被后续审查利用）
    # 每20章：深度审计 + 宏观审查 + 消歧检查
    if (( ch % 20 == 0 )); then
        run_audit "standard"
        run_macro_review "Tier2"
        check_disambiguation_backlog
    # 每10章（非20倍数）：快速审计
    elif (( ch % 10 == 0 )); then
        run_audit "quick"
    fi

    # 每5章：审查最近5章 + 自动修复（始终执行）
    local review_start=$((ch - 4))
    if (( review_start < 1 )); then review_start=1; fi
    run_review_and_fix "$review_start" "$ch"

    echo "───────── 检查点完成 ─────────"
    echo ""
}

# ═══════════════════════════════════════════
# 完成摘要
# ═══════════════════════════════════════════

print_summary() {
    echo ""
    echo "═══════════════════════════════════════"
    echo "  ink-auto 完成报告"
    echo "═══════════════════════════════════════"
    echo "  📝 写作：$COMPLETED 章"
    if (( REVIEW_COUNT > 0 )); then
        echo "  🔍 审查：${REVIEW_COUNT} 次（含自动修复 ${FIX_COUNT} 次）"
    fi
    if (( AUDIT_COUNT > 0 )); then
        echo "  📊 审计：${AUDIT_COUNT} 次"
    fi
    if (( MACRO_COUNT > 0 )); then
        echo "  🔭 宏观审查：${MACRO_COUNT} 次"
    fi
    if (( PLAN_COUNT > 0 )); then
        echo "  📋 自动规划：${PLAN_COUNT} 卷"
    fi
    echo "  📂 日志：$LOG_DIR"
    echo "═══════════════════════════════════════"
}

# ═══════════════════════════════════════════
# 主循环
# ═══════════════════════════════════════════

echo "═══════════════════════════════════════"
echo "  ink-auto | 写 $N 章 | $PLATFORM"
echo "  项目: $PROJECT_ROOT"
echo "  检查点: 每5章审查 | 每10章审计 | 每20章深度审查"
echo "  日志: $LOG_DIR"
echo "═══════════════════════════════════════"

for i in $(seq 1 "$N"); do
    # 检查是否中断
    if (( INTERRUPTED )); then
        break
    fi

    # 读取下一章号
    CURRENT=$(get_current_chapter)
    NEXT_CH=$((CURRENT + 1))

    # 逐章大纲检查 + 自动生成
    if ! python3 -X utf8 "$SCRIPTS_DIR/ink.py" --project-root "$PROJECT_ROOT" \
        check-outline --chapter "$NEXT_CH" >/dev/null 2>&1; then
        echo "[$i/$N] 📋 第${NEXT_CH}章大纲缺失，尝试自动生成..."
        if ! auto_generate_outline "$NEXT_CH"; then
            echo ""
            echo "═══════════════════════════════════════"
            echo "  ❌ 大纲生成失败，批量写作中止"
            echo "═══════════════════════════════════════"
            echo "  已完成：$COMPLETED 章"
            echo "  缺失章节：第${NEXT_CH}章"
            echo "  请手动执行 /ink-plan 生成大纲后重试"
            echo "═══════════════════════════════════════"
            print_summary
            exit 1
        fi
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

        # 检查点评估（写作验证通过后执行）
        run_checkpoint "$NEXT_CH"
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

            # 重试成功后也执行检查点
            run_checkpoint "$NEXT_CH"
        else
            echo ""
            echo "═══════════════════════════════════════"
            echo "  ❌ 第${NEXT_CH}章写作失败，批量写作中止"
            echo "═══════════════════════════════════════"
            echo "  已完成：$COMPLETED 章"
            echo "  失败章节：第${NEXT_CH}章"
            echo "  可能原因：网络中断、API 限流、上下文溢出"
            echo "  恢复方式：/ink-resume 或重新执行 /ink-auto"
            echo "═══════════════════════════════════════"
            print_summary
            exit 1
        fi
    fi
done

print_summary
