#!/bin/bash
# ink-auto: 跨会话无人值守智能批量写作
# 每章启动全新 CLI 进程，进程退出 = 上下文自然清零
# 内置分层检查点（v16 US-008 正式化 5 档）：
#   每 5 章   → ink-review Core + ink-fix
#   每 10 章  → + ink-audit quick + ink-fix
#   每 20 章  → + ink-audit standard + Tier2（浅）+ 消歧
#   每 50 章  → + Tier2（完整）+ propagation drift_detector
#   每 200 章 → + Tier3 跨卷分析
# 内置自动大纲生成 + 运行报告生成
#
# 用法:
#   ink-auto 5              # 写 5 章（串行）
#   ink-auto --parallel 4 20  # 写 20 章，4 章并发
#   ink-auto                # 默认 5 章
#
# 前提: 在小说项目目录下运行（含 .ink/state.json）
# 支持: claude / gemini / codex（自动检测）

set -euo pipefail

# ═══════════════════════════════════════════
# 参数解析：支持 --parallel N
# ═══════════════════════════════════════════

PARALLEL=0
POSITIONAL_ARGS=()

while [[ $# -gt 0 ]]; do
    case $1 in
        --parallel)
            PARALLEL="${2:-4}"
            shift 2
            ;;
        -p)
            PARALLEL="${2:-4}"
            shift 2
            ;;
        *)
            POSITIONAL_ARGS+=("$1")
            shift
            ;;
    esac
done

N=${POSITIONAL_ARGS[0]:-5}
COOLDOWN=${INK_AUTO_COOLDOWN:-10}
CHECKPOINT_COOLDOWN=${INK_AUTO_CHECKPOINT_COOLDOWN:-15}

# 统计计数器
REVIEW_COUNT=0
AUDIT_COUNT=0
MACRO_COUNT=0
PLAN_COUNT=0
FIX_COUNT=0
COMPRESS_NOTIFY_COUNT=0
PLANNED_VOLUMES=":"  # 追踪已尝试生成大纲的卷（字符串匹配，兼容 bash 3.2）
COMPLETED=0
START_TIME=$(date +%s)
START_TIME_STR=$(date "+%Y-%m-%d %H:%M:%S")
EXIT_REASON=""

# ═══════════════════════════════════════════
# 章节级进度条
# ═══════════════════════════════════════════

# 格式化秒数为人类可读时间
format_duration() {
    local secs="$1"
    if (( secs < 60 )); then
        echo "${secs}s"
    elif (( secs < 3600 )); then
        echo "$((secs / 60))m$((secs % 60))s"
    else
        echo "$((secs / 3600))h$(( (secs % 3600) / 60 ))m"
    fi
}

# 输出章节级进度条
# 参数：$1=已完成章数, $2=总章数
print_chapter_progress() {
    local done="$1"
    local total="$2"
    local now
    now=$(date +%s)
    local elapsed=$(( now - START_TIME ))
    local pct=0
    if (( total > 0 )); then
        pct=$(( done * 100 / total ))
    fi

    # 终端宽度检测
    local term_width
    term_width=$(tput cols 2>/dev/null || echo 80)

    if (( term_width < 60 )); then
        # 窄屏降级：纯文字
        local eta_str="计算中"
        if (( done > 0 )); then
            local remaining_secs=$(( elapsed * (total - done) / done ))
            eta_str=$(format_duration "$remaining_secs")
        fi
        echo "📖 ${done}/${total} 章 ${pct}% | ⏱️ $(format_duration "$elapsed") | 剩余 ${eta_str}"
        return
    fi

    # 进度条：宽度 20 字符
    local bar_width=20
    local filled=0
    if (( total > 0 )); then
        filled=$(( done * bar_width / total ))
    fi
    local empty=$(( bar_width - filled ))

    local bar=""
    local j
    for (( j=0; j<filled; j++ )); do bar+="█"; done
    for (( j=0; j<empty; j++ )); do bar+="░"; done

    # 时间估算
    local elapsed_str
    elapsed_str=$(format_duration "$elapsed")
    local eta_str="计算中"
    if (( done > 0 )); then
        local remaining_secs=$(( elapsed * (total - done) / done ))
        eta_str=$(format_duration "$remaining_secs")
    fi

    echo "═══ 📖 总进度 [${bar}] ${done}/${total} 章 (${pct}%) | ⏱️ 已耗时 ${elapsed_str} / 预计剩余 ${eta_str}"
}

# 检查点子步骤进度显示
# 参数：$1=检查点范围描述, $2=步骤状态字符串（如 "✅审查 ✅修复 ⏳审计 ☐审计修复"）
print_checkpoint_progress() {
    local scope="$1"
    local steps="$2"
    echo "🔍 检查点 [${scope}] ${steps}"
}

# ═══════════════════════════════════════════
# 路径检测
# ═══════════════════════════════════════════

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$PLUGIN_ROOT/.." && pwd)"
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
REPORT_DIR="${PROJECT_ROOT}/.ink/reports"
mkdir -p "$LOG_DIR" "$REPORT_DIR"

# 报告文件
REPORT_FILE="${REPORT_DIR}/auto-$(date +%Y%m%d-%H%M%S).md"

# ═══════════════════════════════════════════
# 报告系统
# ═══════════════════════════════════════════

# 事件日志（内存中积累，最后写入报告）
REPORT_EVENTS=""

report_event() {
    local status="$1"   # ✅ ⚠️ ❌ 🔍 📋 📊 🔭 🔧
    local event="$2"
    local detail="${3:-}"
    local ts
    ts=$(date "+%H:%M:%S")
    REPORT_EVENTS="${REPORT_EVENTS}| ${ts} | ${status} | ${event} | ${detail} |
"
}

write_report() {
    local end_time_str
    end_time_str=$(date "+%Y-%m-%d %H:%M:%S")
    local end_time
    end_time=$(date +%s)
    local duration=$(( end_time - START_TIME ))
    local hours=$(( duration / 3600 ))
    local minutes=$(( (duration % 3600) / 60 ))

    cat > "$REPORT_FILE" << REPORT_EOF
# ink-auto 运行报告

## 基本信息

| 项目 | 值 |
|------|-----|
| 开始时间 | ${START_TIME_STR} |
| 结束时间 | ${end_time_str} |
| 总耗时 | ${hours}小时${minutes}分钟 |
| 平台 | ${PLATFORM} |
| 计划章数 | ${N} |
| 完成章数 | ${COMPLETED} |
| 起始章节 | 第${BATCH_START}章 |
| 终止原因 | ${EXIT_REASON:-正常完成} |

## 统计摘要

| 操作 | 次数 |
|------|------|
| 写作 | ${COMPLETED} 章 |
| 质量审查 | ${REVIEW_COUNT} 次 |
| 自动修复 | ${FIX_COUNT} 次 |
| 数据审计 | ${AUDIT_COUNT} 次 |
| 宏观审查 | ${MACRO_COUNT} 次 |
| 记忆压缩提示 | ${COMPRESS_NOTIFY_COUNT} 次 |
| 自动规划 | ${PLAN_COUNT} 卷 |

## 执行时间线

| 时间 | 状态 | 事件 | 详情 |
|------|------|------|------|
${REPORT_EVENTS}
## 日志目录

\`${LOG_DIR}\`

## 报告与产出

- 审查报告: \`审查报告/\` 目录
- 审计报告: \`.ink/audit_reports/\` 目录
- 宏观审查: \`审查报告/\` 目录
- 章节文件: \`正文/\` 目录
REPORT_EOF

    # v9.0 增强：追加质量趋势和追读力信号到报告
    local CURRENT_END
    CURRENT_END=$(get_current_chapter 2>/dev/null || echo "?")
    local TRENDS_MD
    TRENDS_MD=$(python3 -X utf8 "$SCRIPTS_DIR/ink.py" --project-root "$PROJECT_ROOT" \
        index get-review-trends --start "${BATCH_START}" --end "${CURRENT_END}" --format markdown 2>/dev/null) || true
    if [ -n "$TRENDS_MD" ]; then
        cat >> "$REPORT_FILE" << TRENDS_EOF

## 质量趋势（v9.0 增强）

${TRENDS_MD}
TRENDS_EOF
    fi

    echo "📄 运行报告: ${REPORT_FILE}"
}

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
except Exception:
    print(0)
" 2>/dev/null || echo 0
}

# ═══════════════════════════════════════════
# 卷号检测
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
except Exception:
    print('')
" 2>/dev/null
}

# ═══════════════════════════════════════════
# 完结检测（v10.5）
# ═══════════════════════════════════════════

is_project_completed() {
    python3 -X utf8 -c "
import json, re, sys
try:
    with open('${PROJECT_ROOT}/.ink/state.json') as f:
        state = json.load(f)
    # 检查显式完结标记
    if state.get('progress', {}).get('is_completed', False):
        print('completed')
        sys.exit(0)
    # 检查是否已写到最后一卷最后一章
    volumes = state.get('project_info', {}).get('volumes', [])
    if not volumes:
        print('unknown')
        sys.exit(0)
    last_vol = volumes[-1]
    r = last_vol.get('chapter_range', '')
    m = re.match(r'(\d+)-(\d+)', r)
    if m:
        final_chapter = int(m.group(2))
        current = state.get('progress', {}).get('current_chapter', 0)
        if current >= final_chapter:
            print('completed')
            sys.exit(0)
    print('in_progress')
except Exception:
    print('unknown')
" 2>/dev/null
}

get_final_chapter() {
    python3 -X utf8 -c "
import json, re
try:
    with open('${PROJECT_ROOT}/.ink/state.json') as f:
        state = json.load(f)
    volumes = state.get('project_info', {}).get('volumes', [])
    if volumes:
        r = volumes[-1].get('chapter_range', '')
        m = re.match(r'(\d+)-(\d+)', r)
        if m:
            print(m.group(2))
        else:
            print(0)
    else:
        print(0)
except Exception:
    print(0)
" 2>/dev/null
}

get_total_volumes() {
    python3 -X utf8 -c "
import json
try:
    with open('${PROJECT_ROOT}/.ink/state.json') as f:
        state = json.load(f)
    print(len(state.get('project_info', {}).get('volumes', [])))
except Exception:
    print(0)
" 2>/dev/null
}

# 完结检测 preflight
PROJECT_STATUS=$(is_project_completed)
if [[ "$PROJECT_STATUS" == "completed" ]]; then
    echo "🎉 本书已完结！所有卷章均已写完。"
    echo "   如需继续创作，请手动修改 .ink/state.json 中的 is_completed 字段。"
    exit 0
fi

# ═══════════════════════════════════════════
# 大纲覆盖预检（预报模式）
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

report_event "🚀" "批量写作启动" "计划${N}章，从第${BATCH_START}章到第${BATCH_END}章"

echo "🔍 正在扫描第${BATCH_START}章到第${BATCH_END}章的大纲覆盖..."

if ! python3 -X utf8 "$SCRIPTS_DIR/ink.py" --project-root "$PROJECT_ROOT" \
    check-outline --chapter "$BATCH_START" --batch-end "$BATCH_END" 2>/dev/null; then
    echo ""
    echo "⚠️  部分章节大纲缺失，ink-auto 将在写作前自动生成"
    echo "    如需手动规划，请按 Ctrl+C 中止后执行 /ink-plan"
    echo ""
    report_event "⚠️" "大纲预检" "部分章节大纲缺失，将按需自动生成"
    sleep 5
else
    echo "✅ 大纲覆盖完整"
    report_event "✅" "大纲预检" "全部覆盖"
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
    EXIT_REASON="用户中断 (Ctrl+C)"
    report_event "🛑" "用户中断" "已完成${COMPLETED}章"
    print_summary
    write_report
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

    local file
    file=$(ls "$PROJECT_ROOT/正文/第${padded}章"*.md 2>/dev/null | head -1)
    if [[ -z "$file" || ! -s "$file" ]]; then
        file=$(find "$PROJECT_ROOT/正文" -name "第${padded}章*.md" -o -name "第$((ch))章*.md" 2>/dev/null | head -1)
    fi
    if [[ -z "$file" || ! -s "$file" ]]; then
        return 1
    fi

    local char_count
    char_count=$(wc -m < "$file" | tr -d ' ')
    if (( char_count < 2200 )); then
        return 1
    fi

    local cur
    cur=$(get_current_chapter)
    if (( cur < ch )); then
        return 1
    fi

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
# 内层进度事件解析
# ═══════════════════════════════════════════

# step_id → 名称映射
get_step_name() {
    local sid="$1"
    case "$sid" in
        "Step 0")    echo "预检" ;;
        "Step 0.7")  echo "金丝雀扫描" ;;
        "Step 0.8")  echo "设定校验" ;;
        "Step 1")    echo "上下文构建" ;;
        "Step 2A")   echo "正文起草" ;;
        "Step 2A.5") echo "字数校验" ;;
        "Step 2B")   echo "风格适配" ;;
        "Step 2C")   echo "计算型闸门" ;;
        "Step 3")    echo "审查" ;;
        "Step 4")    echo "润色" ;;
        "Step 5")    echo "数据回写" ;;
        "Step 6")    echo "Git 备份" ;;
        *)           echo "" ;;
    esac
}

# 解析子进程输出：[INK-PROGRESS] 行格式化展示，其余透传
# 参数：$1=日志文件路径
# stdin: 子进程的合并输出流
parse_progress_output() {
    local log_file="$1"
    local line event_rest event_type step_id step_name seconds
    local ch_num ch_wc ch_score ch_secs

    while IFS= read -r line; do
        # 所有原始输出写入日志文件
        printf '%s\n' "$line" >> "$log_file"

        # 检测 [INK-PROGRESS] 前缀
        case "$line" in
            *"[INK-PROGRESS] "*)
                # 提取 [INK-PROGRESS] 后面的内容
                event_rest="${line#*\[INK-PROGRESS\] }"
                # 提取事件类型（第一个空格前的部分）
                event_type="${event_rest%% *}"

                case "$event_type" in
                    step_started)
                        # 格式: step_started {step_id}
                        step_id="${event_rest#step_started }"
                        step_name=$(get_step_name "$step_id")
                        echo "    ⏳ ${step_id} ${step_name} ← 执行中..."
                        ;;
                    step_completed)
                        # 格式: step_completed {step_id} {elapsed_seconds}
                        # step_id 含空格，elapsed_seconds 是最后一个字段
                        local args="${event_rest#step_completed }"
                        seconds="${args##* }"
                        step_id="${args% *}"
                        step_name=$(get_step_name "$step_id")
                        echo "    ✅ ${step_id} ${step_name} (${seconds}s)"
                        ;;
                    step_skipped)
                        # 格式: step_skipped {step_id}
                        step_id="${event_rest#step_skipped }"
                        step_name=$(get_step_name "$step_id")
                        echo "    ⏭  ${step_id} ${step_name} (跳过)"
                        ;;
                    step_retry)
                        # 格式: step_retry {from_step} {to_step}
                        local retry_args="${event_rest#step_retry }"
                        echo "    🔄 回退重写: ${retry_args}"
                        ;;
                    chapter_completed)
                        # 格式: chapter_completed {ch} {wc} {score} {secs}
                        local ch_args="${event_rest#chapter_completed }"
                        ch_num="${ch_args%% *}"; ch_args="${ch_args#* }"
                        ch_wc="${ch_args%% *}"; ch_args="${ch_args#* }"
                        ch_score="${ch_args%% *}"; ch_args="${ch_args#* }"
                        ch_secs="${ch_args}"
                        local ch_dur
                        ch_dur=$(format_duration "$ch_secs" 2>/dev/null || echo "${ch_secs}s")
                        echo ""
                        echo "    ✅ 第${ch_num}章完成 | ${ch_wc}字 | 总耗时 ${ch_dur} | 审查分 ${ch_score}"
                        ;;
                    *)
                        # 未知事件类型，静默忽略（不影响流程）
                        ;;
                esac
                ;;
            *)
                # 非 [INK-PROGRESS] 行：正常透传到终端
                printf '%s\n' "$line"
                ;;
        esac
    done
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
                2>&1 | parse_progress_output "$log_file" &
            CHILD_PID=$!
            wait $CHILD_PID 2>/dev/null && exit_code=0 || exit_code=$?
            CHILD_PID=""
            ;;
        gemini)
            echo "$prompt" | gemini --yolo \
                2>&1 | parse_progress_output "$log_file" &
            CHILD_PID=$!
            wait $CHILD_PID 2>/dev/null && exit_code=0 || exit_code=$?
            CHILD_PID=""
            ;;
        codex)
            codex --approval-mode full-auto "$prompt" \
                2>&1 | parse_progress_output "$log_file" &
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
        # v10.5: 检查是否超出总纲定义的卷数（全书完结）
        local total_volumes
        total_volumes=$(get_total_volumes)
        if [[ "$total_volumes" != "0" ]] && (( total_volumes > 0 )); then
            echo "    🎉 第${ch}章已超出总纲定义的${total_volumes}卷范围，全书完结"
            report_event "🎉" "全书完结" "无需为第${ch}章生成大纲，已超出总纲卷数"
            return 1
        fi
        echo "    ❌ 无法确定第${ch}章所属卷号，中止"
        report_event "❌" "自动大纲" "无法确定第${ch}章所属卷号"
        return 1
    fi

    if [[ "$PLANNED_VOLUMES" == *":${vol}:"* ]]; then
        echo "    ❌ 第${vol}卷大纲已尝试生成但仍缺失，中止"
        report_event "❌" "自动大纲" "第${vol}卷重复失败"
        return 1
    fi
    PLANNED_VOLUMES="${PLANNED_VOLUMES}${vol}:"

    echo "    📋 第${vol}卷大纲缺失，自动启动 ink-plan..."
    report_event "📋" "自动大纲启动" "第${vol}卷（因第${ch}章需要）"

    local log_file="$LOG_DIR/plan-vol${vol}-$(date +%Y%m%d-%H%M%S).log"
    local prompt="使用 Skill 工具加载 \"ink-plan\"。为第${vol}卷生成完整详细大纲（节拍表+时间线+章纲）。项目目录: ${PROJECT_ROOT}。禁止提问，自动选择第${vol}卷，全程自主执行。完成后输出 INK_PLAN_DONE。"

    run_cli_process "$prompt" "$log_file" || true

    PLAN_COUNT=$((PLAN_COUNT + 1))
    sleep "$CHECKPOINT_COOLDOWN"

    if python3 -X utf8 "$SCRIPTS_DIR/ink.py" --project-root "$PROJECT_ROOT" \
        check-outline --chapter "$ch" >/dev/null 2>&1; then
        echo "    ✅ 第${vol}卷大纲生成成功"
        report_event "✅" "自动大纲完成" "第${vol}卷"
        return 0
    else
        echo "    ❌ 第${vol}卷大纲生成失败，中止批量写作"
        report_event "❌" "自动大纲失败" "第${vol}卷，日志: $log_file"
        return 1
    fi
}

# ═══════════════════════════════════════════
# 通用自动修复（读取报告文件，修复问题）
# ═══════════════════════════════════════════

run_auto_fix() {
    local report_path="$1"
    local fix_type="$2"   # review / audit / macro
    local scope="$3"      # 人类可读描述，如 "第11-15章" "standard审计"

    if [[ ! -f "$report_path" ]]; then
        echo "    ⚠️  未找到报告文件，跳过修复: $report_path"
        return 0
    fi

    # 检查报告中是否有需要修复的问题（委托 Python 模块，比 Bash 正则更可靠）
    # v16 US-006：从 data_modules.checkpoint_utils 迁移到 ink_writer.core.cli.checkpoint_utils。
    if ! PYTHONPATH="$REPO_ROOT:${PYTHONPATH:-}" python3 -X utf8 -c "from ink_writer.core.cli.checkpoint_utils import report_has_issues; import sys; sys.exit(0 if report_has_issues('$report_path') else 1)" 2>/dev/null; then
        echo "    ✅ 报告无需修复的问题"
        report_event "✅" "${fix_type}修复" "${scope} — 无需修复"
        return 0
    fi

    echo "    🔧 发现问题，启动自动修复..."
    report_event "🔧" "${fix_type}修复启动" "${scope}"

    local log_file="$LOG_DIR/fix-${fix_type}-$(date +%Y%m%d-%H%M%S).log"
    local prompt=""

    prompt="使用 Skill 工具加载 \"ink-fix\"。修复类型: ${fix_type}。报告路径: ${report_path}。项目目录: ${PROJECT_ROOT}。全程自主执行，禁止提问。完成后输出 INK_FIX_DONE。"

    run_cli_process "$prompt" "$log_file" || true

    FIX_COUNT=$((FIX_COUNT + 1))
    sleep "$CHECKPOINT_COOLDOWN"

    # 检查修复后是否仍有 critical 问题
    if [ "$fix_type" = "audit" ]; then
        STILL_HAS_CRITICAL=$(python3 -X utf8 -c "
import json, sys
try:
    with open('$report_path', 'r') as f:
        data = json.load(f)
    issues = data.get('issues', [])
    critical = [i for i in issues if i.get('severity') == 'critical']
    print('True' if critical else 'False')
except:
    print('False')
" 2>/dev/null || echo "False")
        if [ "$STILL_HAS_CRITICAL" = "True" ]; then
            echo "    ⚠️  WARNING: audit critical 问题修复后仍存在，继续写作可能在错误状态上累积"
            report_event "⚠️" "修复不完全" "audit critical 问题仍存在"
        fi
    fi

    echo "    ✅ 自动修复完成"
    report_event "✅" "${fix_type}修复完成" "${scope}，日志: $(basename "$log_file")"
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
    report_event "🔍" "审查启动" "第${start}-${end}章 Core"

    run_cli_process "$prompt" "$log_file" || true

    REVIEW_COUNT=$((REVIEW_COUNT + 1))
    sleep "$CHECKPOINT_COOLDOWN"

    # 检查审查报告并决定是否需要额外修复
    local report_file="${PROJECT_ROOT}/审查报告/第${start}-${end}章审查报告.md"
    if [[ -f "$report_file" ]]; then
        echo "    ✅ 审查完成，报告: 审查报告/第${start}-${end}章审查报告.md"
        report_event "✅" "审查完成" "第${start}-${end}章"

        # ink-review 内置修复可能不够彻底，追加一轮独立修复
        run_auto_fix "$report_file" "review" "第${start}-${end}章"
    else
        echo "    ⚠️  审查进程完成，但未找到报告文件"
        report_event "⚠️" "审查异常" "第${start}-${end}章 — 未生成报告"
    fi
}

# ═══════════════════════════════════════════
# 检查点：数据审计 + 自动修复
# ═══════════════════════════════════════════

run_audit() {
    local depth="$1"  # quick / standard / deep
    local log_file="$LOG_DIR/audit-${depth}-$(date +%Y%m%d-%H%M%S).log"
    local prompt="使用 Skill 工具加载 \"ink-audit\"。审计深度：${depth}。项目目录: ${PROJECT_ROOT}。全程自主执行，禁止提问。完成后输出 INK_AUDIT_DONE。"

    echo "    📊 数据审计 (${depth})..."
    report_event "📊" "审计启动" "${depth}深度"

    run_cli_process "$prompt" "$log_file" || true

    AUDIT_COUNT=$((AUDIT_COUNT + 1))
    sleep "$CHECKPOINT_COOLDOWN"

    # 查找最新的审计报告并自动修复
    local latest_audit
    latest_audit=$(ls -t "${PROJECT_ROOT}/.ink/audit_reports/audit_"*.md 2>/dev/null | head -1)
    if [[ -n "$latest_audit" ]]; then
        echo "    ✅ 审计完成，报告: $(basename "$latest_audit")"
        report_event "✅" "审计完成" "${depth}深度"
        run_auto_fix "$latest_audit" "audit" "${depth}审计"
    else
        echo "    ⚠️  审计进程完成，但未找到报告文件"
        report_event "⚠️" "审计异常" "${depth}深度 — 未生成报告"
    fi
}

# ═══════════════════════════════════════════
# 检查点：宏观审查 + 自动修复
# ═══════════════════════════════════════════

run_macro_review() {
    local tier="$1"  # Tier2 / Tier3
    local log_file="$LOG_DIR/macro-${tier}-$(date +%Y%m%d-%H%M%S).log"
    local prompt="使用 Skill 工具加载 \"ink-macro-review\"。审查层级：${tier}。项目目录: ${PROJECT_ROOT}。全程自主执行，禁止提问。完成后输出 INK_MACRO_DONE。"

    echo "    🔭 宏观审查 (${tier})..."
    report_event "🔭" "宏观审查启动" "${tier}"

    run_cli_process "$prompt" "$log_file" || true

    MACRO_COUNT=$((MACRO_COUNT + 1))
    sleep "$CHECKPOINT_COOLDOWN"

    # 查找最新的宏观审查报告并自动修复
    local latest_macro
    latest_macro=$(ls -t "${PROJECT_ROOT}/审查报告/宏观审查"*.md "${PROJECT_ROOT}/审查报告/里程碑审查"*.md 2>/dev/null | head -1)
    if [[ -n "$latest_macro" ]]; then
        echo "    ✅ 宏观审查完成，报告: $(basename "$latest_macro")"
        report_event "✅" "宏观审查完成" "${tier}"
        run_auto_fix "$latest_macro" "macro" "${tier}宏观审查"
    else
        echo "    ⚠️  宏观审查进程完成，但未找到报告文件"
        report_event "⚠️" "宏观审查异常" "${tier} — 未生成报告"
    fi
}

# ═══════════════════════════════════════════
# 检查点：消歧积压检查
# ═══════════════════════════════════════════

check_disambiguation_backlog() {
    local dj
    dj=$(python3 -X utf8 "$SCRIPTS_DIR/ink.py" \
        --project-root "$PROJECT_ROOT" disambig-check 2>/dev/null) || { echo "    ✅ 消歧检查跳过"; return 0; }

    local count urgency
    count=$(echo "$dj" | python3 -c "import sys,json; print(json.load(sys.stdin).get('count',0))" 2>/dev/null || echo 0)
    urgency=$(echo "$dj" | python3 -c "import sys,json; print(json.load(sys.stdin).get('urgency','normal'))" 2>/dev/null || echo "normal")

    if [[ "$urgency" == "critical" ]]; then
        echo "    ⚠️⚠️ 消歧积压 ${count} 条！强烈建议暂停批量写作，手动执行 /ink-resolve"
        report_event "⚠️" "消歧积压" "${count}条 — 建议手动处理"
    elif [[ "$urgency" == "warning" ]]; then
        echo "    ⚠️  消歧积压 ${count} 条，建议择机执行 /ink-resolve"
        report_event "⚠️" "消歧积压" "${count}条"
    else
        echo "    ✅ 消歧积压 ${count} 条（正常）"
        report_event "✅" "消歧检查" "${count}条（正常）"
    fi
}

# ═══════════════════════════════════════════
# 检查点编排器
# ═══════════════════════════════════════════

run_checkpoint() {
    local ch="$1"

    # 使用统一 CLI 判断检查点级别（可测试、无内联 Python）
    local cp_json
    cp_json=$(python3 -X utf8 "$SCRIPTS_DIR/ink.py" \
        --project-root "$PROJECT_ROOT" checkpoint-level --chapter "$ch" 2>/dev/null) || return 0

    local do_review audit_depth macro_tier do_disambig review_start review_end
    do_review=$(echo "$cp_json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['review'])" 2>/dev/null)
    if [[ "$do_review" != "True" && "$do_review" != "true" ]]; then
        return 0
    fi

    echo ""
    echo "───────── 📋 检查点：第${ch}章 ─────────"
    report_event "📋" "检查点触发" "第${ch}章"

    audit_depth=$(echo "$cp_json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['audit'] or '')")
    macro_tier=$(echo "$cp_json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['macro'] or '')")
    do_disambig=$(echo "$cp_json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['disambig'])")
    review_start=$(echo "$cp_json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['review_range'][0])")
    review_end=$(echo "$cp_json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['review_range'][1])")

    # 构建检查点子步骤列表并动态展示进度
    local cp_scope="第${review_start}-${review_end}章"
    local cp_steps=()
    cp_steps+=("审查" "修复")
    if [[ -n "$audit_depth" ]]; then
        cp_steps+=("审计" "审计修复")
    fi
    if [[ -n "$macro_tier" ]]; then
        cp_steps+=("宏观审查" "宏观修复")
    fi
    if [[ "$do_disambig" == "True" ]]; then
        cp_steps+=("消歧检查")
    fi

    # 初始化步骤状态数组（所有☐）
    local cp_status=()
    local si
    for si in "${!cp_steps[@]}"; do
        cp_status[$si]="☐"
    done

    # Helper: 渲染当前检查点进度
    _render_cp_progress() {
        local parts=""
        local si
        for si in "${!cp_steps[@]}"; do
            parts+="${cp_status[$si]}${cp_steps[$si]} "
        done
        print_checkpoint_progress "$cp_scope" "$parts"
    }

    # Helper: 标记步骤开始(⏳)并渲染
    _cp_step_start() {
        local idx="$1"
        cp_status[$idx]="⏳"
        _render_cp_progress
    }

    # Helper: 标记步骤完成(✅)并渲染
    _cp_step_done() {
        local idx="$1"
        cp_status[$idx]="✅"
        _render_cp_progress
    }

    local step_idx=0  # 当前步骤索引追踪

    # 审查（步骤0）+ 修复（步骤1）始终在最后执行，先执行高层级操作
    # 重排：审计→宏观→消歧→审查→修复
    step_idx=2  # 跳过审查(0)和修复(1)，从审计开始

    # 从高到低执行审计（高层级先行，结果可被后续审查利用）
    if [[ -n "$audit_depth" ]]; then
        _cp_step_start "$step_idx"
        run_audit "$audit_depth"
        _cp_step_done "$step_idx"
        step_idx=$((step_idx + 1))

        _cp_step_start "$step_idx"
        # audit修复已在 run_audit 内部的 run_auto_fix 中完成
        _cp_step_done "$step_idx"
        step_idx=$((step_idx + 1))
    fi
    if [[ -n "$macro_tier" ]]; then
        _cp_step_start "$step_idx"
        run_macro_review "$macro_tier"
        _cp_step_done "$step_idx"
        step_idx=$((step_idx + 1))

        _cp_step_start "$step_idx"
        # macro修复已在 run_macro_review 内部的 run_auto_fix 中完成
        _cp_step_done "$step_idx"
        step_idx=$((step_idx + 1))
    fi
    if [[ "$do_disambig" == "True" ]]; then
        _cp_step_start "$step_idx"
        check_disambiguation_backlog
        _cp_step_done "$step_idx"
    fi

    # 审查最近5章 + 自动修复（始终执行）
    _cp_step_start 0
    run_review_and_fix "$review_start" "$review_end"
    _cp_step_done 0

    _cp_step_start 1
    # 修复已在 run_review_and_fix 内部的 run_auto_fix 中完成
    _cp_step_done 1

    echo "───────── 检查点完成 ─────────"
    echo ""
}

# ═══════════════════════════════════════════
# 完成摘要（终端输出）
# ═══════════════════════════════════════════

print_summary() {
    local CURRENT_END
    CURRENT_END=$(get_current_chapter 2>/dev/null || echo "?")

    echo ""
    echo "═══════════════════════════════════════"
    echo "  ink-auto 完成报告"
    echo "═══════════════════════════════════════"
    echo "  生成章节：第${BATCH_START}-${CURRENT_END}章（${COMPLETED}/${N} 成功）"

    local END_TIME_NOW
    END_TIME_NOW=$(date +%s)
    local ELAPSED=$(( END_TIME_NOW - START_TIME ))
    local H=$(( ELAPSED / 3600 ))
    local M=$(( (ELAPSED % 3600) / 60 ))
    echo "  总耗时：${H}小时${M}分钟"
    echo ""

    # 质量概览
    echo "  质量概览："
    if (( REVIEW_COUNT > 0 )); then
        echo "  ├─ 审查：${REVIEW_COUNT} 次"
    fi
    if (( FIX_COUNT > 0 )); then
        echo "  ├─ 自动修复：${FIX_COUNT} 次"
    fi
    if (( AUDIT_COUNT > 0 )); then
        echo "  ├─ 数据审计：${AUDIT_COUNT} 次"
    fi
    if (( MACRO_COUNT > 0 )); then
        echo "  ├─ 宏观审查：${MACRO_COUNT} 次"
    fi
    if (( PLAN_COUNT > 0 )); then
        echo "  ├─ 自动规划：${PLAN_COUNT} 卷"
    fi

    # v9.0 增强：追读力和伏笔信号（查询 index.db，失败时静默跳过）
    local TRENDS
    TRENDS=$(python3 -X utf8 "$SCRIPTS_DIR/ink.py" --project-root "$PROJECT_ROOT" \
        index get-review-trends --start "${BATCH_START}" --end "${CURRENT_END}" --format text 2>/dev/null) || true
    if [ -n "$TRENDS" ]; then
        echo ""
        echo "$TRENDS"
    fi

    echo ""
    echo "  📂 日志：$LOG_DIR"
    echo "  推荐下一步：ink-auto ${N}"
    echo "═══════════════════════════════════════"
}

# ═══════════════════════════════════════════
# 并发模式：委托给 Python asyncio 编排器
# ═══════════════════════════════════════════

if (( PARALLEL > 1 )); then
    echo "═══════════════════════════════════════"
    echo "  ink-auto | 写 $N 章 | 并发 $PARALLEL | $PLATFORM"
    echo "  项目: $PROJECT_ROOT"
    echo "  检查点: 每批次完成后统一运行"
    echo "  日志: $LOG_DIR"
    echo "═══════════════════════════════════════"

    # v16 US-006：去掉 sys.path.insert hack，改用 PYTHONPATH env var（设计稿 §6.2 零裸路径）。
    PYTHONPATH="$REPO_ROOT:${PLUGIN_ROOT}/scripts:${PYTHONPATH:-}" python3 -X utf8 -c "
import asyncio, json
from pathlib import Path
from ink_writer.parallel.pipeline_manager import PipelineManager, PipelineConfig

config = PipelineConfig(
    project_root=Path('$PROJECT_ROOT'),
    plugin_root=Path('$PLUGIN_ROOT'),
    parallel=$PARALLEL,
    cooldown=$COOLDOWN,
    checkpoint_cooldown=$CHECKPOINT_COOLDOWN,
    platform='$PLATFORM',
)
mgr = PipelineManager(config)
report = asyncio.run(mgr.run(total_chapters=$N))
result = report.to_dict()

print()
print('═══════════════════════════════════════')
print(f'  ink-auto 并发完成报告')
print('═══════════════════════════════════════')
print(f'  并发度: {result[\"parallel\"]}')
print(f'  完成: {result[\"completed\"]} 章 | 失败: {result[\"failed\"]} 章')
print(f'  墙钟时间: {result[\"wall_time_s\"]}s | 串行等效: {result[\"serial_total_s\"]}s')
print(f'  加速比: {result[\"speedup\"]}x')
print('═══════════════════════════════════════')

# 输出 JSON 报告
report_path = Path('$REPORT_DIR') / f'auto-parallel-{__import__(\"time\").strftime(\"%Y%m%d-%H%M%S\")}.json'
report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
print(f'  报告: {report_path}')

sys.exit(1 if result['failed'] > 0 else 0)
"
    exit $?
fi

# ═══════════════════════════════════════════
# 主循环（串行模式）
# ═══════════════════════════════════════════

echo "═══════════════════════════════════════"
echo "  ink-auto | 写 $N 章 | $PLATFORM"
echo "  项目: $PROJECT_ROOT"
echo "  检查点: 5章 review+fix / 10章 audit quick / 20章 audit standard+Tier2 / 50章 Tier2+drift / 200章 Tier3"
echo "  日志: $LOG_DIR"
echo "  报告: $REPORT_FILE"
echo "═══════════════════════════════════════"

for i in $(seq 1 "$N"); do
    if (( INTERRUPTED )); then
        break
    fi

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
            EXIT_REASON="第${NEXT_CH}章大纲生成失败"
            report_event "❌" "批量写作中止" "大纲生成失败，已完成${COMPLETED}章"
            print_summary
            write_report
            exit 1
        fi
    fi

    # 清理上一轮的 workflow 残留状态
    python3 -X utf8 "$SCRIPTS_DIR/ink.py" \
        --project-root "$PROJECT_ROOT" workflow clear 2>/dev/null || true

    # 跨卷记忆压缩检查（在新卷首章自动提示）
    COMPRESS_JSON=$(python3 -X utf8 "$SCRIPTS_DIR/ink.py" \
        --project-root "$PROJECT_ROOT" memory auto-compress --chapter "$NEXT_CH" --format json 2>/dev/null) || true
    if [ -n "$COMPRESS_JSON" ]; then
        COMPRESS_NEEDED=$(echo "$COMPRESS_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('needed', False))" 2>/dev/null || echo "False")
        if [[ "$COMPRESS_NEEDED" == "True" ]]; then
            COMPRESS_VOL=$(echo "$COMPRESS_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('volume_to_compress', '?'))" 2>/dev/null || echo "?")
            COMPRESS_REASON=$(echo "$COMPRESS_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('reason', ''))" 2>/dev/null || echo "")
            echo "    📦 记忆压缩提示: 第${COMPRESS_VOL}卷需要mega-summary压缩"
            echo "       ${COMPRESS_REASON}"
            echo "       将由 ink-write Step 0 自动执行"
            report_event "📦" "记忆压缩提示" "第${COMPRESS_VOL}卷待压缩"
            COMPRESS_NOTIFY_COUNT=$((COMPRESS_NOTIFY_COUNT + 1))
        fi
    fi

    echo ""
    print_chapter_progress "$COMPLETED" "$N"
    echo ""
    echo "[$i/$N] 第${NEXT_CH}章 开始写作..."
    echo "───────────────────────────────────"
    report_event "📝" "写作启动" "第${NEXT_CH}章 [$i/$N]"

    if ! run_chapter "$NEXT_CH"; then
        echo "[$i/$N] ⚠️  第${NEXT_CH}章 CLI 进程异常，尝试验证产出..."
    fi

    sleep "$COOLDOWN"

    if verify_chapter "$NEXT_CH"; then
        WC=$(get_chapter_wordcount "$NEXT_CH")
        COMPLETED=$((COMPLETED + 1))
        echo "[$i/$N] ✅ 第${NEXT_CH}章完成 | ${WC}字"
        print_chapter_progress "$COMPLETED" "$N"
        report_event "✅" "写作完成" "第${NEXT_CH}章 ${WC}字"

        run_checkpoint "$NEXT_CH"

        # v10.5: 完结检测——检查是否达到最终章
        FINAL_CH=$(get_final_chapter)
        if [[ "$FINAL_CH" != "0" ]] && (( NEXT_CH >= FINAL_CH )); then
            echo ""
            echo "═══════════════════════════════════════"
            echo "  🎉 全书完结！第${NEXT_CH}章是最终章。"
            echo "═══════════════════════════════════════"
            python3 -X utf8 "$SCRIPTS_DIR/ink.py" --project-root "$PROJECT_ROOT" \
                update-state --mark-completed 2>/dev/null || true
            EXIT_REASON="全书完结"
            report_event "🎉" "全书完结" "第${NEXT_CH}章为最终章"
            print_summary
            write_report
            exit 0
        fi
    else
        echo "[$i/$N] ⚠️  验证失败，重试中..."
        report_event "⚠️" "写作验证失败" "第${NEXT_CH}章，启动重试"

        if ! retry_chapter "$NEXT_CH"; then
            echo "[$i/$N] ⚠️  重试进程也异常退出"
        fi
        sleep "$COOLDOWN"

        if verify_chapter "$NEXT_CH"; then
            WC=$(get_chapter_wordcount "$NEXT_CH")
            COMPLETED=$((COMPLETED + 1))
            echo "[$i/$N] ✅ 第${NEXT_CH}章完成（重试成功）| ${WC}字"
            print_chapter_progress "$COMPLETED" "$N"
            report_event "✅" "重试成功" "第${NEXT_CH}章 ${WC}字"

            run_checkpoint "$NEXT_CH"
        else
            echo ""
            echo "═══════════════════════════════════════"
            echo "  ❌ 第${NEXT_CH}章写作失败，批量写作中止"
            echo "═══════════════════════════════════════"
            EXIT_REASON="第${NEXT_CH}章写作失败（重试后仍未通过验证）"
            report_event "❌" "批量写作中止" "第${NEXT_CH}章写作失败，已完成${COMPLETED}章"
            print_summary
            write_report
            exit 1
        fi
    fi
done

EXIT_REASON=""
report_event "🎉" "批量写作完成" "共${COMPLETED}章"
print_summary
write_report
