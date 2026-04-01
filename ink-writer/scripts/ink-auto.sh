#!/bin/bash
# ink-auto: 跨会话无人值守智能批量写作
# 每章启动全新 CLI 进程，进程退出 = 上下文自然清零
# 内置分层检查点：每5章审查+修复、每10章审计+修复、每20章深度审查+修复
# 内置自动大纲生成 + 运行报告生成
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
START_TIME=$(date +%s)
START_TIME_STR=$(date "+%Y-%m-%d %H:%M:%S")
EXIT_REASON=""

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
except:
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
except:
    print('')
" 2>/dev/null
}

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

    # 检查报告中是否有需要修复的问题
    if ! grep -qiE "critical|high|严重|错误|不一致|漂移|失衡|逾期" "$report_path" 2>/dev/null; then
        echo "    ✅ 报告无需修复的问题"
        report_event "✅" "${fix_type}修复" "${scope} — 无需修复"
        return 0
    fi

    echo "    🔧 发现问题，启动自动修复..."
    report_event "🔧" "${fix_type}修复启动" "${scope}"

    local log_file="$LOG_DIR/fix-${fix_type}-$(date +%Y%m%d-%H%M%S).log"
    local prompt=""

    case $fix_type in
        review)
            prompt="项目目录: ${PROJECT_ROOT}。请读取审查报告文件 ${report_path}，对其中所有 critical 和 high 级别问题执行修复。对每个问题：1) 定位对应章节文件（在 正文/ 目录下），2) 用 Edit 工具做最小修复，3) 验证修复后字数仍 >= 2200字。修复完成后执行 git add 正文/ .ink/ && git commit -m 'ink-auto: 自动修复审查问题'。禁止提问，全程自主执行。完成后输出 INK_FIX_DONE。"
            ;;
        audit)
            prompt="项目目录: ${PROJECT_ROOT}。请读取审计报告文件 ${report_path}，对其中发现的数据不一致问题执行修复。可能的问题包括：state.json与index.db状态不同步、过期伏笔未处理、chapter_meta膨胀、实体幽灵记录。使用 python3 ${SCRIPTS_DIR}/ink.py --project-root ${PROJECT_ROOT} 的相关子命令修复数据问题。修复完成后执行 git add .ink/ && git commit -m 'ink-auto: 自动修复审计问题'。禁止提问，全程自主执行。完成后输出 INK_FIX_DONE。"
            ;;
        macro)
            prompt="项目目录: ${PROJECT_ROOT}。请读取宏观审查报告文件 ${report_path}，对其中发现的结构性问题执行修复。可能的问题包括：支线剧情停滞、角色弧光断裂、冲突模式重复、叙事承诺未兑现、风格漂移。对于可直接修复的问题（如过期伏笔标记、承诺追踪更新），使用 python3 ${SCRIPTS_DIR}/ink.py --project-root ${PROJECT_ROOT} 的相关子命令执行修复。对于需要修改章节内容的问题，用 Edit 工具做最小修复。修复完成后执行 git add 正文/ .ink/ && git commit -m 'ink-auto: 自动修复宏观审查问题'。禁止提问，全程自主执行。完成后输出 INK_FIX_DONE。"
            ;;
    esac

    run_cli_process "$prompt" "$log_file" || true

    FIX_COUNT=$((FIX_COUNT + 1))
    sleep "$CHECKPOINT_COOLDOWN"

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
        report_event "⚠️" "消歧积压" "${count}条 — 建议手动处理"
    elif (( count > 20 )); then
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

    # 不是5的倍数，跳过
    if (( ch % 5 != 0 )); then
        return 0
    fi

    echo ""
    echo "───────── 📋 检查点：第${ch}章 ─────────"
    report_event "📋" "检查点触发" "第${ch}章"

    # 从高到低执行审计（高层级先行，结果可被后续审查利用）
    if (( ch % 20 == 0 )); then
        run_audit "standard"
        run_macro_review "Tier2"
        check_disambiguation_backlog
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
# 完成摘要（终端输出）
# ═══════════════════════════════════════════

print_summary() {
    echo ""
    echo "═══════════════════════════════════════"
    echo "  ink-auto 完成报告"
    echo "═══════════════════════════════════════"
    echo "  📝 写作：$COMPLETED 章"
    if (( REVIEW_COUNT > 0 )); then
        echo "  🔍 审查：${REVIEW_COUNT} 次"
    fi
    if (( FIX_COUNT > 0 )); then
        echo "  🔧 自动修复：${FIX_COUNT} 次"
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
echo "  检查点: 每5章审查+修复 | 每10章审计+修复 | 每20章深度审查+修复"
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
        echo "[$i/$N] ✅ 第${NEXT_CH}章完成 | ${WC}字"
        COMPLETED=$((COMPLETED + 1))
        report_event "✅" "写作完成" "第${NEXT_CH}章 ${WC}字"

        run_checkpoint "$NEXT_CH"
    else
        echo "[$i/$N] ⚠️  验证失败，重试中..."
        report_event "⚠️" "写作验证失败" "第${NEXT_CH}章，启动重试"

        if ! retry_chapter "$NEXT_CH"; then
            echo "[$i/$N] ⚠️  重试进程也异常退出"
        fi
        sleep "$COOLDOWN"

        if verify_chapter "$NEXT_CH"; then
            WC=$(get_chapter_wordcount "$NEXT_CH")
            echo "[$i/$N] ✅ 第${NEXT_CH}章完成（重试成功）| ${WC}字"
            COMPLETED=$((COMPLETED + 1))
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
