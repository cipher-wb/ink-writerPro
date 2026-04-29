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

# v27: top-level defaults so trap-driven cleanup paths work even before
# init_project_paths runs (needed when user Ctrl+C during init bootstrap)
LOG_DIR=""
REPORT_FILE=""
BATCH_START=0
REPORT_EVENTS=""

# 暴露脚本自身 PID 给 watchdog，用于 SIGTERM 时清理孤儿 LLM CLI 子进程
INK_AUTO_PID=$$
export INK_AUTO_PID

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

# Python launcher 检测（Mac/Linux 定值 "python3"；Windows git-bash 探测 py -3/python3/python）
# 与 env-setup.sh:find_python_launcher_bash 和 env-setup.ps1:Find-PythonLauncher 语义对等。
find_python_launcher_bash() {
    case "${OSTYPE:-}" in
        msys*|cygwin*|win32*)
            local _cand _head
            for _cand in "py -3" "python3" "python"; do  # c8-ok: detector primitive
                _head="${_cand%% *}"
                if command -v "$_head" >/dev/null 2>&1; then
                    if $_cand --version >/dev/null 2>&1; then
                        PY_LAUNCHER="$_cand"
                        return 0
                    fi
                fi
            done
            PY_LAUNCHER="python"
            ;;
        *)
            PY_LAUNCHER="python3"  # c8-ok: detector primitive (Mac/Linux 定值)
            ;;
    esac
}

if [ -z "${PY_LAUNCHER:-}" ]; then
    find_python_launcher_bash
fi

find_project_root() {
    # 解析顺序（防止 Claude Code 子 shell cwd 不在小说目录时被误判为空项目）：
    #   1. INK_PROJECT_ROOT env var（用户/外层显式指定，最高优先级）
    #   2. PROJECT_ROOT env var（env-setup.sh 已计算并 export 的值）
    #   3. CLAUDE_PROJECT_DIR env var（Claude Code 主项目目录）
    #   4. 从 $PWD 向上递归找 .ink/state.json（旧行为，最后兜底）
    # 每个候选都要验证 .ink/state.json 真的存在；不存在就走下一个候选。
    local cand
    for cand in \
        "${INK_PROJECT_ROOT:-}" \
        "${PROJECT_ROOT:-}" \
        "${CLAUDE_PROJECT_DIR:-}"; do
        if [[ -n "$cand" ]] && [[ -f "$cand/.ink/state.json" ]]; then
            echo "$cand"
            return 0
        fi
    done

    # 兜底：PWD 上溯
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

# v27 ink-auto 终极自动化：允许 PROJECT_ROOT 暂时为空，后续状态分发处理
PROJECT_ROOT="$(find_project_root)" || PROJECT_ROOT=""

# ═══════════════════════════════════════════
# v27 路径相关变量初始化（PROJECT_ROOT 就绪后调用）
# ═══════════════════════════════════════════

init_project_paths() {
    LOG_DIR="${PROJECT_ROOT}/.ink/logs/auto"
    REPORT_DIR="${PROJECT_ROOT}/.ink/reports"
    mkdir -p "$LOG_DIR" "$REPORT_DIR"

    # 报告文件
    REPORT_FILE="${REPORT_DIR}/auto-$(date +%Y%m%d-%H%M%S).md"

    # ═══════════════════════════════════════════
    # 字数硬区间（v27 平台感知）：调用 load_word_limits 同时取 min + max
    # load_word_limits 读取 .ink/preferences.json 的 pacing.chapter_words，并推导 ±500 区间。
    # qidian: (2200, 5000) / fanqie: (1500, 2000) — 默认 qidian 兜底（state.json 损坏时安全)
    # MIN_WORDS_HARD: verify_chapter 下限阻断阈值
    # MAX_WORDS_HARD: verify_chapter 上限阻断阈值
    # ═══════════════════════════════════════════

    WORD_LIMITS=$(
        "${PY_LAUNCHER}" -X utf8 -c "
import sys
try:
    from ink_writer.core.preferences import load_word_limits
    min_w, max_w = load_word_limits(r'${PROJECT_ROOT}')
    print(f'{min_w} {max_w}')
except Exception:
    print('2200 5000')
" 2>/dev/null || echo "2200 5000"
    )
    MIN_WORDS_HARD=$(echo "$WORD_LIMITS" | awk '{print $1}')
    MAX_WORDS_HARD=$(echo "$WORD_LIMITS" | awk '{print $2}')

    # 防御：解析异常/非数字 → 兜底 qidian-strict (2200, 5000)
    if ! [[ "$MIN_WORDS_HARD" =~ ^[0-9]+$ ]]; then MIN_WORDS_HARD=2200; fi
    if ! [[ "$MAX_WORDS_HARD" =~ ^[0-9]+$ ]]; then MAX_WORDS_HARD=5000; fi
    if (( MAX_WORDS_HARD < MIN_WORDS_HARD )); then MAX_WORDS_HARD=$((MIN_WORDS_HARD + 500)); fi

    # 精简循环最大轮次（US-004：3 轮，与 SKILL.md 2A.5 对齐；下限补写循环保持 1 轮零回归）
    SHRINK_MAX_ROUNDS=3
}

# S1/S2/S3 路径：PROJECT_ROOT 已就绪，立即初始化路径变量
if [[ -n "$PROJECT_ROOT" ]]; then
    init_project_paths
fi

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
    [[ -n "$REPORT_FILE" ]] || return 0
    [[ -n "$LOG_DIR" ]] || return 0
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
    TRENDS_MD=$($PY_LAUNCHER -X utf8 "$SCRIPTS_DIR/ink.py" --project-root "$PROJECT_ROOT" \
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

# v27: PROJECT_ROOT 为空时跳过预检，状态分发块会在 run_cli_process 就绪后处理
if [[ -n "$PROJECT_ROOT" ]]; then
    if ! $PY_LAUNCHER -X utf8 "$SCRIPTS_DIR/ink.py" --project-root "$PROJECT_ROOT" preflight 2>/dev/null; then
        echo "❌ 预检失败，请检查项目状态"
        exit 1
    fi
fi

# ═══════════════════════════════════════════
# 读取当前章节号
# ═══════════════════════════════════════════

get_current_chapter() {
    $PY_LAUNCHER -X utf8 "$SCRIPTS_DIR/ink.py" \
        --project-root "$PROJECT_ROOT" state get-progress 2>/dev/null \
        | $PY_LAUNCHER -c "
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
    $PY_LAUNCHER -X utf8 -c "
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
    $PY_LAUNCHER -X utf8 -c "
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
    $PY_LAUNCHER -X utf8 -c "
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
    $PY_LAUNCHER -X utf8 -c "
import json
try:
    with open('${PROJECT_ROOT}/.ink/state.json') as f:
        state = json.load(f)
    print(len(state.get('project_info', {}).get('volumes', [])))
except Exception:
    print(0)
" 2>/dev/null
}

# NOTE: 完结检测 + 大纲预检逻辑已重构为 `_s1_outline_precheck_if_root` 函数，
# 在所有函数定义后统一调用（参见文件底部）。这样 auto_plan_volume / run_cli_process
# 等被引用的函数已就位，避免顶层内联代码引用未定义函数（旧 bug 表现：
# "auto_plan_volume: command not found"）。

# ═══════════════════════════════════════════
# 信号处理
# ═══════════════════════════════════════════

CHILD_PID=""
WATCHDOG_PID=""
INTERRUPTED=0

on_signal() {
    INTERRUPTED=1
    if [[ -n "$WATCHDOG_PID" ]]; then
        kill -TERM "$WATCHDOG_PID" 2>/dev/null || true
        wait "$WATCHDOG_PID" 2>/dev/null || true
        WATCHDOG_PID=""
    fi
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

# 把不完整草稿（中文字数 < MIN_WORDS_HARD）归档到 .ink/recovery_backups/
# 避免半成品留在 正文/ 下，让下次 /ink-auto 误判为已完成或拼接错乱。
# 调用时机：
#   - run_chapter 后 verify_chapter 失败
#   - retry 前（保留旧半成品作为参考，不直接覆盖）
#   - 最终失败 exit 前
_archive_partial_chapter() {
    local ch="$1"
    local padded
    padded=$(printf "%04d" "$ch")
    : "${MIN_WORDS_HARD:=2200}"

    local files=()
    while IFS= read -r f; do
        files+=("$f")
    done < <(ls "$PROJECT_ROOT/正文/第${padded}章"*.md 2>/dev/null || true)

    if (( ${#files[@]} == 0 )); then
        return 0  # 没文件就没事
    fi

    local archived=0
    local archive_dir="$PROJECT_ROOT/.ink/recovery_backups/partial_chapters"
    mkdir -p "$archive_dir"

    for f in "${files[@]}"; do
        [[ -f "$f" ]] || continue
        local cc
        cc=$(wc -m < "$f" 2>/dev/null | tr -d ' ')
        if [[ -n "$cc" ]] && (( cc < MIN_WORDS_HARD )); then
            local ts dst
            ts=$(date +%Y%m%d-%H%M%S)
            dst="$archive_dir/$(basename "$f" .md)-partial-${cc}字-${ts}.md"
            mv "$f" "$dst" 2>/dev/null && {
                echo "    🗄️  归档不完整草稿：$(basename "$f") (${cc}字 < ${MIN_WORDS_HARD}) → recovery_backups/partial_chapters/" >&2
                archived=$((archived + 1))
            }
        fi
    done

    return 0
}

verify_chapter() {
    local ch="$1"
    local padded
    padded=$(printf "%04d" "$ch")
    : "${MIN_WORDS_HARD:=2200}"
    : "${MAX_WORDS_HARD:=5000}"

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
    # 默认硬下限等价于旧规则: char_count < 2200
    if (( char_count < MIN_WORDS_HARD )); then
        return 1
    fi
    # US-004：字数硬上限对称阻断（MAX_WORDS_HARD 由 preferences.json 推导，默认 5000）
    if (( char_count > MAX_WORDS_HARD )); then
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

# step_id → 名称映射（覆盖 ink-init / ink-plan / ink-write 三个 skill）
# 同名 step（如 Step 1 在 init/plan/write 各有不同含义）由 SKILL.md 的进度规范明确归属，
# 这里给出"通用首选"名字（与各 SKILL.md 的进度输出规范保持一致）。
get_step_name() {
    local sid="$1"
    case "$sid" in
        # ── ink-init Quick Mode ───────────────────────
        "Step 0")    echo "预检/加载素材" ;;
        "Step 0.4")  echo "平台选择" ;;
        "Step 0.5")  echo "激进度档位选择" ;;
        "Step 0.7")  echo "金丝雀扫描" ;;
        "Step 0.8")  echo "设定校验" ;;
        "Step 1")    echo "上下文构建/方案生成" ;;
        "Step 1.5")  echo "金手指五重校验" ;;
        "Step 1.6")  echo "语言风格分配" ;;
        "Step 1.7")  echo "书名/人名校验" ;;
        # ── ink-plan ──────────────────────────────────
        "Step 2")    echo "设定基线补齐" ;;
        "Step 3")    echo "选卷/审查" ;;
        "Step 4")    echo "节拍表生成/润色" ;;
        "Step 4.5")  echo "时间线生成" ;;
        "Step 5")    echo "卷骨架/数据回写" ;;
        "Step 6")    echo "章纲生成/Git 备份" ;;
        "Step 7")    echo "设定集回写" ;;
        "Step 8")    echo "校验+落盘" ;;
        # ── ink-write 单章特有 ────────────────────────
        "Step 2A")   echo "正文起草" ;;
        "Step 2A.1") echo "自洽回扫" ;;
        "Step 2A.5") echo "字数校验" ;;
        "Step 2B")   echo "风格适配" ;;
        "Step 2C")   echo "计算型闸门" ;;
        "Step 4.5")  echo "改写安全校验" ;;
        "Step 5.5")  echo "前序章修复" ;;
        # ── 共用 ─────────────────────────────────────
        "Step 99")   echo "策划期审查" ;;
        "Step 99.5") echo "直播题材审查" ;;
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
# 进度心跳：在 LLM 子进程长时间跑期间，每 30s 主动观测产物 + log
# 让用户知道"软件还活着 + 当前在干嘛"，不再 1 小时黑屏
# ═══════════════════════════════════════════

# log 异常关键词正则（API 限流 / 网络 / 服务故障 / token 超限）
# 命中任一即在心跳里高亮告警
_HEARTBEAT_ALERT_REGEX='(rate.?limit|429|503|502|504|timeout|overloaded|exceeded.?context|max.?tokens|connection.?refused|network.?error|api.?error|temporarily.?unavailable|too.?many.?requests)'

# $1: op (init / plan / write)
# $2: log_file（用来扫异常关键词）
# $3: 观测目标——init 时是 .ink/state.json；plan 时是 大纲/*.md 中最新的；write 时是当前章节文件
# $4: parent_pid（卡住检测用，超过 INK_AUTO_STALL_THRESHOLD 秒无产物增长 + step 不变 → SIGTERM 父进程的子 LLM）
_start_progress_heartbeat() {
    local op="$1"
    local log_file="$2"
    local watch_target="${3:-}"
    local parent_pid="${4:-}"
    local interval="${INK_AUTO_HEARTBEAT_INTERVAL:-30}"
    # 卡住阈值：连续 N 秒产物 + step 都没变化即视为卡住，默认 600s（10min）。设为 0 关闭。
    local stall_threshold="${INK_AUTO_STALL_THRESHOLD:-600}"

    (
        # 子 shell 退出时清理（防止心跳成为孤儿）
        trap 'exit 0' TERM INT

        local hb_start
        hb_start=$(date +%s)
        local last_size=0
        local last_alert_line=""
        local last_step=""
        local stall_since=0  # 字数 + step 都不变开始的时间戳；为 0 表示尚未开始停滞

        while true; do
            sleep "$interval"
            local now elapsed elapsed_str
            now=$(date +%s)
            elapsed=$((now - hb_start))
            elapsed_str=$(format_duration "$elapsed" 2>/dev/null || echo "${elapsed}s")

            # 1. 异常关键词扫描（最近 200 行 log）
            if [[ -f "$log_file" ]]; then
                local recent_alert
                recent_alert=$(tail -n 200 "$log_file" 2>/dev/null \
                    | grep -iE "$_HEARTBEAT_ALERT_REGEX" \
                    | tail -n 1 || true)
                if [[ -n "$recent_alert" ]] && [[ "$recent_alert" != "$last_alert_line" ]]; then
                    # 截断到 200 字符避免刷屏
                    local alert_short="${recent_alert:0:200}"
                    echo "    ⚠️  [心跳 ${elapsed_str}] 检测到 API 异常信号：${alert_short}" >&2
                    last_alert_line="$recent_alert"
                fi
            fi

            # 2. 产物观测：根据 op 类型看不同文件
            local observation=""
            case "$op" in
                init)
                    # init 看 4 个信号：
                    #   a) state.json 是否就位（最终标志）
                    #   b) .ink/ + 设定集/ + 大纲/ 三个目录的文件总数 + 字节
                    #   c) 最近创建/修改的文件名（让用户知道 LLM 当前在写什么）
                    #   d) init log 文件最后 1 行非空内容（LLM 进展）
                    if [[ -n "${PROJECT_ROOT:-}" ]]; then
                        local total_files=0 total_bytes=0 newest=""
                        local d
                        for d in ".ink" "设定集" "大纲"; do
                            local dpath="$PROJECT_ROOT/$d"
                            [[ -d "$dpath" ]] || continue
                            local n
                            n=$(find "$dpath" -type f 2>/dev/null | wc -l | tr -d ' ')
                            total_files=$((total_files + n))
                            local b
                            b=$(find "$dpath" -type f -exec wc -c {} + 2>/dev/null \
                                | awk 'END{print $1+0}')
                            total_bytes=$((total_bytes + ${b:-0}))
                        done
                        # 找全项目最新被修改的文件（不限子目录）
                        newest=$(find "$PROJECT_ROOT" -type f \
                            \( -name '*.md' -o -name '*.json' -o -name '*.yaml' \) \
                            -not -path '*/.git/*' -not -path '*/.ink-debug/*' \
                            -newer "$log_file" 2>/dev/null | head -1)
                        if [[ -z "$newest" ]]; then
                            # 回退到 LLM start 之后任何修改过的文件
                            newest=$(ls -t "$PROJECT_ROOT/.ink/"*.json 2>/dev/null | head -1)
                        fi

                        if [[ -f "$PROJECT_ROOT/.ink/state.json" ]]; then
                            observation="✓ state.json 已就位｜${total_files} 文件 ${total_bytes}B"
                        else
                            observation="${total_files} 文件 ${total_bytes}B"
                            [[ -n "$newest" ]] && observation="${observation}｜最新：$(basename "$newest")"
                        fi

                        # log 文件末行：取最新非空内容（截 100 字符）
                        # macOS 没 tac，用 awk 取最后一行非空（兼容 mac/linux）
                        if [[ -f "$log_file" ]]; then
                            local last_log_line
                            last_log_line=$(awk 'NF{last=$0} END{print last}' "$log_file" 2>/dev/null)
                            if [[ -n "$last_log_line" ]]; then
                                observation="${observation}｜log: ${last_log_line:0:100}"
                            fi
                        fi
                    else
                        observation="（init 进行中，PROJECT_ROOT 未确定）"
                    fi
                    ;;
                plan)
                    # plan 看 3 个信号：
                    #   a) 大纲/ 文件总数 + 总字节
                    #   b) 最新卷大纲文件 + 字节增长
                    #   c) 该文件里已生成的章节数（grep "^## 第N章" 数量）
                    if [[ -n "${PROJECT_ROOT:-}" ]]; then
                        local outline_count=0 outline_bytes=0
                        if [[ -d "$PROJECT_ROOT/大纲" ]]; then
                            outline_count=$(find "$PROJECT_ROOT/大纲" -type f -name '*.md' 2>/dev/null \
                                | wc -l | tr -d ' ')
                            outline_bytes=$(find "$PROJECT_ROOT/大纲" -type f -name '*.md' \
                                -exec wc -c {} + 2>/dev/null | awk 'END{print $1+0}')
                        fi
                        # 找最新卷大纲文件
                        local latest_outline=""
                        latest_outline=$(ls -t "$PROJECT_ROOT/大纲/"*.md 2>/dev/null | head -1)
                        if [[ -n "$latest_outline" ]]; then
                            local size growth=""
                            size=$(wc -c <"$latest_outline" 2>/dev/null | tr -d ' ' || echo 0)
                            if (( size > last_size )); then
                                local delta=$((size - last_size))
                                growth=" (+${delta}B)"
                            elif (( size == last_size && last_size > 0 )); then
                                growth=" (无增长)"
                            fi
                            # 数已生成章节
                            local ch_count
                            ch_count=$(grep -cE '^##\s*第\s*[0-9]+\s*章' "$latest_outline" 2>/dev/null \
                                || echo 0)
                            observation="$(basename "$latest_outline"): ${size}B${growth}｜${ch_count} 章已写"
                            last_size=$size
                        else
                            observation="${outline_count} 大纲文件 ${outline_bytes}B"
                        fi
                        # log 末行（mac/linux 兼容：用 awk 而非 tac）
                        if [[ -f "$log_file" ]]; then
                            local last_log_line
                            last_log_line=$(awk 'NF{last=$0} END{print last}' "$log_file" 2>/dev/null)
                            if [[ -n "$last_log_line" ]]; then
                                observation="${observation}｜log: ${last_log_line:0:80}"
                            fi
                        fi
                    fi
                    ;;
                write)
                    # write 看 4 个信号：
                    #   a) 章节文件字数（中文字符数）+ 增量
                    #   b) workflow_state.json 当前 step
                    #   c) workflow_state.json 已完成 step 数 / 总 step（13 步流程进度）
                    #   d) log 末行（LLM 最近输出 / Hard Block Rewrite 提示）
                    local size_changed=0
                    local cur_step=""
                    if [[ -n "$watch_target" ]] && [[ -f "$watch_target" ]]; then
                        local size char_count growth=""
                        size=$(wc -c <"$watch_target" 2>/dev/null | tr -d ' ' || echo 0)
                        char_count=$(wc -m <"$watch_target" 2>/dev/null | tr -d ' ' || echo 0)
                        if (( size > last_size )); then
                            local delta=$((size - last_size))
                            growth=" (+${delta}B)"
                            size_changed=1
                        elif (( size == last_size && last_size > 0 )); then
                            growth=" (无增长)"
                        fi
                        observation="$(basename "$watch_target"): ${char_count}字${growth}"
                        last_size=$size
                    fi
                    # 看 workflow_state.json 当前 step + 已完成 step 数
                    if [[ -n "${PROJECT_ROOT:-}" ]] && [[ -f "$PROJECT_ROOT/.ink/workflow_state.json" ]]; then
                        local step_info
                        step_info=$($PY_LAUNCHER -c "
import json, sys
try:
    d = json.load(open('$PROJECT_ROOT/.ink/workflow_state.json'))
    task = d.get('current_task') or {}
    cs = task.get('current_step') or {}
    sid = cs.get('id', '')
    sname = cs.get('name', '')
    completed = len(task.get('completed_steps', []) or [])
    parts = []
    if sid:
        parts.append(f'当前 {sid} {sname}'.strip())
    if completed > 0:
        parts.append(f'{completed}/13 已完成')
    print(' | '.join(parts))
except Exception:
    pass
" 2>/dev/null)
                        cur_step=$(echo "$step_info" | sed -n 's/^当前 \([^|]*\).*$/\1/p' | xargs 2>/dev/null)
                        if [[ -n "$step_info" ]]; then
                            observation="${observation}｜${step_info}"
                        fi
                    fi
                    # log 末行（LLM 最近输出，含 Hard Block Rewrite 提示等）
                    if [[ -f "$log_file" ]]; then
                        local last_log_line
                        last_log_line=$(awk 'NF{last=$0} END{print last}' "$log_file" 2>/dev/null)
                        if [[ -n "$last_log_line" ]]; then
                            observation="${observation}｜log: ${last_log_line:0:80}"
                        fi
                    fi

                    # 卡住检测：write 模式下，字数 + step 都没变化时累积停滞时长
                    if (( stall_threshold > 0 )); then
                        local step_changed=0
                        if [[ "$cur_step" != "$last_step" ]]; then
                            step_changed=1
                        fi
                        last_step="$cur_step"

                        if (( size_changed == 0 && step_changed == 0 )); then
                            if (( stall_since == 0 )); then
                                stall_since=$now
                            fi
                            local stall_dur=$((now - stall_since))
                            if (( stall_dur >= stall_threshold )) && [[ -n "$parent_pid" ]]; then
                                # 触发 SIGTERM：让 watchdog 接手清理 + 父流程进入 retry
                                echo "    🚨 [心跳 ${elapsed_str}] 检测到卡住：${stall_dur}s 内字数无增长且 step 未变化 → 终止子进程进入重试" >&2
                                kill -TERM "$parent_pid" 2>/dev/null || true
                                pkill -TERM -P "$parent_pid" 2>/dev/null || true
                                if [[ -n "${INK_AUTO_PID:-}" ]]; then
                                    pkill -TERM -P "$INK_AUTO_PID" -f "claude -p\|gemini --yolo\|codex --approval-mode" 2>/dev/null || true
                                fi
                                exit 0
                            elif (( stall_dur >= stall_threshold / 2 )); then
                                # 接近一半时提前预警，不立即终止
                                echo "    ⚠️  [心跳 ${elapsed_str}] 已停滞 ${stall_dur}s（阈值 ${stall_threshold}s）：再无进展将终止" >&2
                            fi
                        else
                            stall_since=0  # 任何变化重置计数
                        fi
                    fi
                    ;;
            esac

            local op_label
            case "$op" in
                init)  op_label="ink-init" ;;
                plan)  op_label="ink-plan" ;;
                write) op_label="ink-write" ;;
                *)     op_label="$op" ;;
            esac

            echo "    ⏱️  [心跳 ${elapsed_str}] ${op_label} 进行中｜${observation}" >&2
        done
    ) &
    HEARTBEAT_PID=$!
}

_stop_progress_heartbeat() {
    if [[ -n "${HEARTBEAT_PID:-}" ]]; then
        kill -TERM "$HEARTBEAT_PID" 2>/dev/null || true
        wait "$HEARTBEAT_PID" 2>/dev/null || true
        HEARTBEAT_PID=""
    fi
}

# ═══════════════════════════════════════════
# CLI 进程启动通用函数
# ═══════════════════════════════════════════

_start_cli_watchdog() {
    # 启动后台 watchdog：超时后 kill CHILD_PID（pipeline 末端 parse_progress_output）
    # **同时**杀掉它的所有子进程（特别是 claude/gemini/codex 这种通过管道连进来的）。
    # 历史 bug：只 kill pipeline 末端，pipeline 头部的 LLM CLI 进程会变成孤儿继续跑，
    #          导致 watchdog "fire 了但脚本没真正释放资源"。
    local timeout_s="$1"
    local target_pid="$2"
    (
        sleep "$timeout_s"
        if kill -0 "$target_pid" 2>/dev/null; then
            echo "[ink-auto] watchdog: timeout ${timeout_s}s exceeded for PID $target_pid, sending SIGTERM" >&2
            # 先 SIGTERM 整个目标 + 它的所有子孙进程
            pkill -TERM -P "$target_pid" 2>/dev/null || true
            kill -TERM "$target_pid" 2>/dev/null || true
            # 同时找 ink-auto 父进程（INK_AUTO_PID）下的 LLM CLI 子代，避免孤儿 claude/gemini/codex
            if [[ -n "${INK_AUTO_PID:-}" ]]; then
                pkill -TERM -P "$INK_AUTO_PID" -f "claude -p\|gemini --yolo\|codex --approval-mode" 2>/dev/null || true
            fi
            sleep 8
            if kill -0 "$target_pid" 2>/dev/null; then
                echo "[ink-auto] watchdog: SIGTERM ignored, sending SIGKILL" >&2
                pkill -KILL -P "$target_pid" 2>/dev/null || true
                kill -KILL "$target_pid" 2>/dev/null || true
                if [[ -n "${INK_AUTO_PID:-}" ]]; then
                    pkill -KILL -P "$INK_AUTO_PID" -f "claude -p\|gemini --yolo\|codex --approval-mode" 2>/dev/null || true
                fi
            fi
        fi
    ) &
    WATCHDOG_PID=$!
}

_stop_cli_watchdog() {
    if [[ -n "${WATCHDOG_PID:-}" ]]; then
        kill -TERM "$WATCHDOG_PID" 2>/dev/null || true
        wait "$WATCHDOG_PID" 2>/dev/null || true
        WATCHDOG_PID=""
    fi
}

run_cli_process() {
    # $1 prompt
    # $2 log_file
    # $3 (可选) timeout_s，覆盖默认值
    # $4 (可选) op：init / plan / write —— 用于心跳监测产物文件
    # $5 (可选) watch_target：write 模式下的章节文件路径
    #
    # 默认超时按操作类型分档（由调用方通过 $3 传入；不传则取 INK_AUTO_CHAPTER_TIMEOUT）：
    #   - ink-write 单章：3600s（60min）—— 含 5 个 checker + Hard Block Rewrite 最坏 5 轮
    #   - ink-plan 整卷：3600s（60min）—— 30+ 章纲一次生成
    #   - ink-init：     1800s（30min）—— 一次性初始化
    # 1800s 在用户实测 2026-04-29 cipher 第 2 章触发 watchdog；提到 3600s 给极端情况留余量。
    local prompt="$1"
    local log_file="$2"
    local timeout_s="${3:-${INK_AUTO_CHAPTER_TIMEOUT:-3600}}"
    local op="${4:-}"
    local watch_target="${5:-}"
    local exit_code=0

    # 启动进度心跳（每 30s 报一次产物状态 + 异常关键词 + 卡住检测）
    # 注意：parent_pid 需要 CHILD_PID 就绪后再传，所以心跳启动放到 pipeline 启动之后

    case $PLATFORM in
        claude)
            claude -p "$prompt" \
                --permission-mode bypassPermissions \
                --no-session-persistence \
                2>&1 | parse_progress_output "$log_file" &
            CHILD_PID=$!
            (( timeout_s > 0 )) && _start_cli_watchdog "$timeout_s" "$CHILD_PID"
            [[ -n "$op" ]] && _start_progress_heartbeat "$op" "$log_file" "$watch_target" "$CHILD_PID"
            wait $CHILD_PID 2>/dev/null && exit_code=0 || exit_code=$?
            _stop_cli_watchdog
            CHILD_PID=""
            ;;
        gemini)
            echo "$prompt" | gemini --yolo \
                2>&1 | parse_progress_output "$log_file" &
            CHILD_PID=$!
            (( timeout_s > 0 )) && _start_cli_watchdog "$timeout_s" "$CHILD_PID"
            [[ -n "$op" ]] && _start_progress_heartbeat "$op" "$log_file" "$watch_target" "$CHILD_PID"
            wait $CHILD_PID 2>/dev/null && exit_code=0 || exit_code=$?
            _stop_cli_watchdog
            CHILD_PID=""
            ;;
        codex)
            codex --approval-mode full-auto "$prompt" \
                2>&1 | parse_progress_output "$log_file" &
            CHILD_PID=$!
            (( timeout_s > 0 )) && _start_cli_watchdog "$timeout_s" "$CHILD_PID"
            [[ -n "$op" ]] && _start_progress_heartbeat "$op" "$log_file" "$watch_target" "$CHILD_PID"
            wait $CHILD_PID 2>/dev/null && exit_code=0 || exit_code=$?
            _stop_cli_watchdog
            CHILD_PID=""
            ;;
    esac

    # 停止心跳（成功/失败都要停，避免后台残留）
    _stop_progress_heartbeat

    # US-012 defensive 日志：CLI 子进程非零退出时显式打到 stderr（机器可读 marker，被回归测试守护）
    # 同时打一行中文人类可读说明 + 透出 log 中的具体异常信号，避免"只看到 exit 1 不知道为啥"。
    if (( exit_code == 124 || exit_code == 137 || exit_code == 143 )); then
        echo "[ink-auto] llm_exit=$exit_code timeout=${timeout_s}s tool=$PLATFORM log=$log_file" >&2
        echo "[ink-auto] ❌ LLM 子进程超时（${timeout_s}s 内未完成，被 watchdog 强制结束）" >&2
    elif (( exit_code != 0 )); then
        echo "[ink-auto] llm_exit=$exit_code tool=$PLATFORM log=$log_file" >&2
        echo "[ink-auto] ❌ LLM 子进程非零退出 (code=$exit_code)" >&2
    fi
    # 失败时不论退出码，扫一遍 log 提取最具体的异常信号给用户
    if (( exit_code != 0 )) && [[ -f "$log_file" ]]; then
        local alert_regex="${_HEARTBEAT_ALERT_REGEX:-rate.?limit|429|503|502|504|timeout|overloaded|connection.?refused|api.?error}"
        local last_alert
        last_alert=$(tail -n 200 "$log_file" 2>/dev/null \
            | grep -iE "$alert_regex" \
            | tail -n 3 || true)
        if [[ -n "$last_alert" ]]; then
            echo "[ink-auto] 🔍 log 中检测到的 API/网络异常信号（最近 3 条）：" >&2
            echo "$last_alert" | sed 's/^/    | /' >&2
        fi
        local last_lines
        last_lines=$(tail -n 5 "$log_file" 2>/dev/null || true)
        if [[ -n "$last_lines" ]]; then
            echo "[ink-auto] 📜 log 末尾 5 行（用于诊断）：" >&2
            echo "$last_lines" | sed 's/^/    | /' >&2
        fi
    fi

    return $exit_code
}

# NOTE: v27 状态分发 + 自动 init 逻辑已重构为 `_v27_init_if_needed` 函数，
# 在所有函数定义后统一调用（参见文件底部）。这样 run_cli_process / auto_plan_volume
# 等被引用的函数已就位（旧 bug 表现："auto_plan_volume: command not found"）。
INK_AUTO_INIT_ENABLED="${INK_AUTO_INIT_ENABLED:-1}"
INK_AUTO_BLUEPRINT_ENABLED="${INK_AUTO_BLUEPRINT_ENABLED:-1}"
INK_AUTO_INTERACTIVE_BOOTSTRAP_ENABLED="${INK_AUTO_INTERACTIVE_BOOTSTRAP_ENABLED:-1}"

# ═══════════════════════════════════════════
# 单章执行
# ═══════════════════════════════════════════

run_chapter() {
    local ch="$1"
    local padded
    padded=$(printf "%04d" "$ch")
    local log_file="$LOG_DIR/ch${padded}-$(date +%Y%m%d-%H%M%S).log"
    local prompt="使用 Skill 工具加载 \"ink-write\" 并完整执行所有步骤（Step 0 到 Step 6）。项目目录: ${PROJECT_ROOT}。禁止省略任何步骤，禁止提问，全程自主执行。完成后输出 INK_DONE。失败则输出 INK_FAILED。"

    # write 心跳：观测当前章节文件的字数增长 + workflow_state.json 当前 step
    local watch_file="${PROJECT_ROOT}/正文/第${padded}章.md"
    if ! run_cli_process "$prompt" "$log_file" "${INK_AUTO_CHAPTER_TIMEOUT:-3600}" "write" "$watch_file"; then
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

    local watch_file="${PROJECT_ROOT}/正文/第${padded}章.md"
    if ! run_cli_process "$prompt" "$log_file" "${INK_AUTO_CHAPTER_TIMEOUT:-3600}" "write" "$watch_file"; then
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

    # ink-plan 整卷大纲耗时最长（30+ 章纲），用 INK_AUTO_PLAN_TIMEOUT（默认 3600s）+ plan 心跳
    run_cli_process "$prompt" "$log_file" "${INK_AUTO_PLAN_TIMEOUT:-3600}" "plan" || true

    PLAN_COUNT=$((PLAN_COUNT + 1))
    sleep "$CHECKPOINT_COOLDOWN"

    if $PY_LAUNCHER -X utf8 "$SCRIPTS_DIR/ink.py" --project-root "$PROJECT_ROOT" \
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

# 按显式卷号触发 ink-plan 生成完整卷大纲；ch_hint 用于 check-outline 校验。
# 与 auto_generate_outline 的差别：调用方已确定卷号（如 v27 init 后或 S1 状态批跨多卷），
# 不再由 chapter→volume 反查，因此可在循环内对多个卷依次调用。
# 调用点：ink-auto.sh:535 (S1 路径) + ink-auto.sh:933 (v27 自动 init 后)。
auto_plan_volume() {
    local vol="$1"
    local ch_hint="${2:-}"

    if [[ -z "$vol" ]]; then
        echo "    ❌ auto_plan_volume: 缺少卷号参数" >&2
        report_event "❌" "自动大纲" "auto_plan_volume 缺少卷号参数"
        return 1
    fi

    # 防重复尝试（同一批次内对同卷多次失败要中止，避免死循环）
    if [[ "$PLANNED_VOLUMES" == *":${vol}:"* ]]; then
        echo "    ❌ 第${vol}卷大纲已尝试生成但仍缺失，中止"
        report_event "❌" "自动大纲" "第${vol}卷重复失败"
        return 1
    fi
    PLANNED_VOLUMES="${PLANNED_VOLUMES}${vol}:"

    echo "    📋 自动启动 ink-plan 生成第${vol}卷..."
    report_event "📋" "自动大纲启动" "第${vol}卷"

    local log_file="$LOG_DIR/plan-vol${vol}-$(date +%Y%m%d-%H%M%S).log"
    local prompt="使用 Skill 工具加载 \"ink-plan\"。为第${vol}卷生成完整详细大纲（节拍表+时间线+章纲）。项目目录: ${PROJECT_ROOT}。禁止提问，自动选择第${vol}卷，全程自主执行。完成后输出 INK_PLAN_DONE。"

    # ink-plan 整卷大纲耗时最长，用 INK_AUTO_PLAN_TIMEOUT（默认 3600s）+ plan 心跳
    run_cli_process "$prompt" "$log_file" "${INK_AUTO_PLAN_TIMEOUT:-3600}" "plan" || true

    PLAN_COUNT=$((PLAN_COUNT + 1))
    sleep "$CHECKPOINT_COOLDOWN"

    # 校验：优先用 ch_hint 做 check-outline；缺失则用卷首章兜底（让 ink.py 自己解析）
    local check_args=("--project-root" "$PROJECT_ROOT" "check-outline")
    if [[ -n "$ch_hint" ]]; then
        check_args+=("--chapter" "$ch_hint")
    fi

    if $PY_LAUNCHER -X utf8 "$SCRIPTS_DIR/ink.py" "${check_args[@]}" >/dev/null 2>&1; then
        echo "    ✅ 第${vol}卷大纲生成成功"
        report_event "✅" "自动大纲完成" "第${vol}卷"
        return 0
    else
        echo "    ❌ 第${vol}卷大纲生成失败，日志: $log_file"
        report_event "❌" "自动大纲失败" "第${vol}卷，日志: $log_file"
        return 1
    fi
}

# ═══════════════════════════════════════════
# v27 状态分发：未初始化项目时自动 init + 首卷 plan
# 必须在所有函数（auto_plan_volume / run_cli_process / find_project_root 等）
# 定义之后由主流程统一调用；以前是顶层内联，引用未定义函数导致 R1 bug。
# ═══════════════════════════════════════════

_v27_init_if_needed() {
    if [[ -n "$PROJECT_ROOT" ]]; then
        return 0  # 已初始化，无须 v27
    fi

    if [[ "$INK_AUTO_INIT_ENABLED" != "1" ]]; then
        echo "❌ 未找到 .ink/state.json，请在小说项目目录下运行"
        echo "   提示：当前目录无已初始化项目（自动初始化已被 INK_AUTO_INIT_ENABLED=0 禁用）"
        echo "   解决：移除 INK_AUTO_INIT_ENABLED=0 重新运行，或切换到已初始化的项目目录"
        exit 1
    fi

    PROJECT_ROOT="$PWD"
    echo "════════════════════════════════════════════════════"
    echo "  ink-auto 终极自动化模式：未检测到已初始化项目"
    echo "  当前目录：${PROJECT_ROOT}"
    echo "════════════════════════════════════════════════════"

    local blueprint_path=""
    if [[ "$INK_AUTO_BLUEPRINT_ENABLED" == "1" ]]; then
        blueprint_path=$(
            "$PY_LAUNCHER" -X utf8 "${SCRIPTS_DIR}/blueprint_scanner.py" \
                --cwd "${PROJECT_ROOT}" 2>/dev/null || echo ""
        )
    fi

    if [[ -n "$blueprint_path" ]]; then
        echo "📄 找到蓝本：${blueprint_path}"
    else
        if [[ "$INK_AUTO_INTERACTIVE_BOOTSTRAP_ENABLED" != "1" ]]; then
            echo "❌ 未找到蓝本 .md，且 INK_AUTO_INTERACTIVE_BOOTSTRAP_ENABLED=0"
            echo "   请先放置蓝本（参考 ${SCRIPTS_DIR}/../templates/blueprint-template.md）"
            exit 1
        fi
        blueprint_path="${PROJECT_ROOT}/.ink-auto-blueprint.md"
        echo "📋 未找到蓝本，启动 7 题交互式 bootstrap..."
        bash "${SCRIPTS_DIR}/interactive_bootstrap.sh" "$blueprint_path" || {
            echo "❌ 交互式 bootstrap 失败或被中断"
            exit 1
        }
    fi

    local draft_path="${PROJECT_ROOT}/.ink-auto-quick-draft.json"
    if ! "$PY_LAUNCHER" -X utf8 "${SCRIPTS_DIR}/blueprint_to_quick_draft.py" \
        --input "$blueprint_path" --output "$draft_path" 2>&1; then
        echo "❌ 蓝本校验失败，请修正后重跑 /ink-auto"
        exit 1
    fi

    local init_log="${PROJECT_ROOT}/.ink-auto-init-$(date +%Y%m%d-%H%M%S).log"
    local init_prompt="使用 Skill 工具加载 \"ink-init\"。模式：--quick --blueprint ${blueprint_path}。draft.json 路径: ${draft_path}。项目目录: ${PROJECT_ROOT}（**强制在该目录原地初始化，不要根据书名生成子目录**；最终 .ink/state.json 必须落在 ${PROJECT_ROOT}/.ink/state.json）。禁止提问，全程自主执行，最终输出 INK_INIT_DONE 或 INK_INIT_FAILED。"
    echo "⚙️  启动自动初始化（CLI 子进程，约 5-15 分钟）..."
    # ink-init 一次性初始化，用 INK_AUTO_INIT_TIMEOUT（默认 1800s）+ init 心跳
    if ! run_cli_process "$init_prompt" "$init_log" "${INK_AUTO_INIT_TIMEOUT:-1800}" "init"; then
        echo "❌ 自动初始化失败，日志：${init_log}"
        echo "   蓝本保留：${blueprint_path}"
        echo "   你可以手动重跑：claude -p '使用 ink-init --quick --blueprint ${blueprint_path}'"
        exit 1
    fi
    echo "✅ 初始化完成"

    PROJECT_ROOT="$(find_project_root)" || {
        echo "❌ init 后仍未找到 .ink/state.json，可能初始化未完整落盘"
        echo "   日志：${init_log}"
        exit 1
    }

    init_project_paths

    if ! $PY_LAUNCHER -X utf8 "$SCRIPTS_DIR/ink.py" --project-root "$PROJECT_ROOT" preflight 2>/dev/null; then
        echo "❌ 预检失败，请检查项目状态"
        exit 1
    fi

    PROJECT_STATUS=$(is_project_completed)
    if [[ "$PROJECT_STATUS" == "completed" ]]; then
        echo "🎉 本书已完结！所有卷章均已写完。"
        exit 0
    fi

    CURRENT_CH=$(get_current_chapter)
    CURRENT_CH=${CURRENT_CH:-0}
    BATCH_START=$((CURRENT_CH + 1))
    BATCH_END=$((CURRENT_CH + N))

    report_event "🚀" "批量写作启动（自动初始化后）" "计划${N}章，从第${BATCH_START}章到第${BATCH_END}章"

    echo "🔍 正在扫描第${BATCH_START}章到第${BATCH_END}章的大纲覆盖..."
    if ! $PY_LAUNCHER -X utf8 "$SCRIPTS_DIR/ink.py" --project-root "$PROJECT_ROOT" \
        check-outline --chapter "$BATCH_START" --batch-end "$BATCH_END" 2>/dev/null; then
        echo ""
        echo "⚠️  大纲缺失，init 后自动启动 ink-plan 生成完整卷大纲..."
        echo ""
        report_event "📋" "init后自动plan" "第${BATCH_START}章起，大纲缺失，触发完整卷大纲生成"

        local _vol
        _vol=$(get_volume_for_chapter "$BATCH_START")
        if [[ -n "$_vol" ]] && auto_plan_volume "$_vol" "$BATCH_START"; then
            echo "✅ 第${_vol}卷完整大纲生成成功"
            report_event "✅" "init后自动plan完成" "第${_vol}卷"
        else
            echo "❌ 第${_vol}卷大纲生成失败，中止批量写作"
            report_event "❌" "init后自动plan失败" "第${_vol}卷"
            exit 1
        fi
    else
        echo "✅ 大纲覆盖完整"
        report_event "✅" "大纲预检" "全部覆盖"
    fi
}

# ═══════════════════════════════════════════
# S1 状态：已初始化但缺大纲——做完结检测 + 大纲预检 + 按需 plan
# ═══════════════════════════════════════════

_s1_outline_precheck_if_root() {
    if [[ -z "$PROJECT_ROOT" ]]; then
        return 0  # 还没初始化，跳过
    fi

    PROJECT_STATUS=$(is_project_completed)
    if [[ "$PROJECT_STATUS" == "completed" ]]; then
        echo "🎉 本书已完结！所有卷章均已写完。"
        echo "   如需继续创作，请手动修改 .ink/state.json 中的 is_completed 字段。"
        exit 0
    fi

    CURRENT_CH=$(get_current_chapter)
    if [[ -z "$CURRENT_CH" || "$CURRENT_CH" == "0" ]]; then
        if ! $PY_LAUNCHER -X utf8 "$SCRIPTS_DIR/ink.py" --project-root "$PROJECT_ROOT" state get-progress 2>/dev/null | $PY_LAUNCHER -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
            echo "❌ 无法读取 state.json 进度信息，请检查项目状态"
            exit 1
        fi
        CURRENT_CH=${CURRENT_CH:-0}
    fi

    BATCH_START=$((CURRENT_CH + 1))
    BATCH_END=$((CURRENT_CH + N))

    report_event "🚀" "批量写作启动" "计划${N}章，从第${BATCH_START}章到第${BATCH_END}章"

    PROJECT_STATE=$(
        "$PY_LAUNCHER" -X utf8 -c "
from pathlib import Path
from ink_writer.core.auto.state_detector import detect_project_state
print(detect_project_state(Path('${PROJECT_ROOT}')).value)
" 2>/dev/null || echo "S2_WRITING"
    )

    echo "🔍 正在扫描第${BATCH_START}章到第${BATCH_END}章的大纲覆盖...（项目状态: ${PROJECT_STATE}）"

    if $PY_LAUNCHER -X utf8 "$SCRIPTS_DIR/ink.py" --project-root "$PROJECT_ROOT" \
        check-outline --chapter "$BATCH_START" --batch-end "$BATCH_END" 2>/dev/null; then
        echo "✅ 大纲覆盖完整"
        report_event "✅" "大纲预检" "全部覆盖"
        return 0
    fi

    echo ""
    if [[ "$PROJECT_STATE" != "S1_NO_OUTLINE" ]]; then
        echo "⚠️  部分章节大纲缺失，ink-auto 将在写作前自动生成"
        echo "    如需手动规划，请按 Ctrl+C 中止后执行 /ink-plan"
        report_event "⚠️" "大纲预检" "部分章节大纲缺失，将按需自动生成"
        sleep 5
        echo ""
        return 0
    fi

    echo "📋 项目缺大纲（S1），自动启动 ink-plan 生成完整卷大纲..."
    report_event "📋" "S1自动plan启动" "大纲缺失，生成完整卷大纲"

    # 确定需要规划的卷范围：从 BATCH_START 到 BATCH_END 覆盖的所有卷
    local _plan_vol _plan_vols _last_plan_vol _pc
    _plan_vols=""
    _last_plan_vol=""
    for ((_pc=BATCH_START; _pc<=BATCH_END; _pc++)); do
        _plan_vol=$(get_volume_for_chapter "$_pc")
        if [[ -n "$_plan_vol" ]] && [[ "$_plan_vol" != "$_last_plan_vol" ]]; then
            _plan_vols="${_plan_vols} ${_plan_vol}"
            _last_plan_vol="$_plan_vol"
        fi
    done

    for _plan_vol in $_plan_vols; do
        echo "    📋 正在生成第${_plan_vol}卷完整大纲..."
        if auto_plan_volume "$_plan_vol" "$BATCH_START"; then
            echo "    ✅ 第${_plan_vol}卷大纲生成成功"
            report_event "✅" "S1自动plan完成" "第${_plan_vol}卷"
        else
            echo "    ❌ 第${_plan_vol}卷大纲生成失败，中止批量写作"
            report_event "❌" "S1自动plan失败" "第${_plan_vol}卷"
            exit 1
        fi
    done
    echo ""
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
    # US-012：stderr 不再吞到 /dev/null，改为附加到 debug 日志
    # （Windows 下 Python 崩溃/import 错误/编码问题可追踪，不再静默）
    if ! PYTHONPATH="$REPO_ROOT:${PYTHONPATH:-}" $PY_LAUNCHER -X utf8 -c "from ink_writer.core.cli.checkpoint_utils import report_has_issues; import sys; sys.exit(0 if report_has_issues('$report_path') else 1)" 2>>"$LOG_DIR/checkpoint-utils-debug.log"; then
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
        STILL_HAS_CRITICAL=$($PY_LAUNCHER -X utf8 -c "
import json, sys
try:
    with open('$report_path', 'r', encoding='utf-8') as f:
        data = json.load(f)
    issues = data.get('issues', [])
    critical = [i for i in issues if i.get('severity') == 'critical']
    print('True' if critical else 'False')
except:
    print('False')
" 2>>"$LOG_DIR/checkpoint-utils-debug.log" || echo "False")
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
    dj=$($PY_LAUNCHER -X utf8 "$SCRIPTS_DIR/ink.py" \
        --project-root "$PROJECT_ROOT" disambig-check 2>/dev/null) || { echo "    ✅ 消歧检查跳过"; return 0; }

    local count urgency
    count=$(echo "$dj" | $PY_LAUNCHER -c "import sys,json; print(json.load(sys.stdin).get('count',0))" 2>/dev/null || echo 0)
    urgency=$(echo "$dj" | $PY_LAUNCHER -c "import sys,json; print(json.load(sys.stdin).get('urgency','normal'))" 2>/dev/null || echo "normal")

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
    cp_json=$($PY_LAUNCHER -X utf8 "$SCRIPTS_DIR/ink.py" \
        --project-root "$PROJECT_ROOT" checkpoint-level --chapter "$ch" 2>/dev/null) || return 0

    local do_review audit_depth macro_tier do_disambig review_start review_end
    do_review=$(echo "$cp_json" | $PY_LAUNCHER -c "import sys,json; d=json.load(sys.stdin); print(d['review'])" 2>/dev/null)
    if [[ "$do_review" != "True" && "$do_review" != "true" ]]; then
        return 0
    fi

    echo ""
    echo "───────── 📋 检查点：第${ch}章 ─────────"
    report_event "📋" "检查点触发" "第${ch}章"

    audit_depth=$(echo "$cp_json" | $PY_LAUNCHER -c "import sys,json; d=json.load(sys.stdin); print(d['audit'] or '')")
    macro_tier=$(echo "$cp_json" | $PY_LAUNCHER -c "import sys,json; d=json.load(sys.stdin); print(d['macro'] or '')")
    do_disambig=$(echo "$cp_json" | $PY_LAUNCHER -c "import sys,json; d=json.load(sys.stdin); print(d['disambig'])")
    review_start=$(echo "$cp_json" | $PY_LAUNCHER -c "import sys,json; d=json.load(sys.stdin); print(d['review_range'][0])")
    review_end=$(echo "$cp_json" | $PY_LAUNCHER -c "import sys,json; d=json.load(sys.stdin); print(d['review_range'][1])")

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
    [[ -n "$LOG_DIR" ]] || return 0
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
    TRENDS=$($PY_LAUNCHER -X utf8 "$SCRIPTS_DIR/ink.py" --project-root "$PROJECT_ROOT" \
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
# 主流程启动：状态分发 + 大纲预检（必须在所有函数定义后调用）
# ═══════════════════════════════════════════

# v27 路径：PROJECT_ROOT 为空则自动 init + 首卷 plan，落盘后 PROJECT_ROOT 就绪
_v27_init_if_needed

# 已初始化路径：完结检测 + 大纲覆盖预检（可能再触发 S1 自动 plan）
_s1_outline_precheck_if_root

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
    PYTHONPATH="$REPO_ROOT:${PLUGIN_ROOT}/scripts:${PYTHONPATH:-}" $PY_LAUNCHER -X utf8 -c "
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
    if ! $PY_LAUNCHER -X utf8 "$SCRIPTS_DIR/ink.py" --project-root "$PROJECT_ROOT" \
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
    $PY_LAUNCHER -X utf8 "$SCRIPTS_DIR/ink.py" \
        --project-root "$PROJECT_ROOT" workflow clear 2>/dev/null || true

    # 跨卷记忆压缩检查（在新卷首章自动提示）
    COMPRESS_JSON=$($PY_LAUNCHER -X utf8 "$SCRIPTS_DIR/ink.py" \
        --project-root "$PROJECT_ROOT" memory auto-compress --chapter "$NEXT_CH" --format json 2>/dev/null) || true
    if [ -n "$COMPRESS_JSON" ]; then
        COMPRESS_NEEDED=$(echo "$COMPRESS_JSON" | $PY_LAUNCHER -c "import sys,json; print(json.load(sys.stdin).get('needed', False))" 2>/dev/null || echo "False")
        if [[ "$COMPRESS_NEEDED" == "True" ]]; then
            COMPRESS_VOL=$(echo "$COMPRESS_JSON" | $PY_LAUNCHER -c "import sys,json; print(json.load(sys.stdin).get('volume_to_compress', '?'))" 2>/dev/null || echo "?")
            COMPRESS_REASON=$(echo "$COMPRESS_JSON" | $PY_LAUNCHER -c "import sys,json; print(json.load(sys.stdin).get('reason', ''))" 2>/dev/null || echo "")
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
            $PY_LAUNCHER -X utf8 "$SCRIPTS_DIR/ink.py" --project-root "$PROJECT_ROOT" \
                update-state --mark-completed 2>/dev/null || true
            EXIT_REASON="全书完结"
            report_event "🎉" "全书完结" "第${NEXT_CH}章为最终章"
            print_summary
            write_report
            exit 0
        fi
    else
        # US-004：根据失败原因分流
        #   - 字数超限 (> MAX_WORDS_HARD) → 精简循环最多 SHRINK_MAX_ROUNDS（3 轮）
        #   - 其它失败（含 < MIN_WORDS_HARD / 文件缺失 / 摘要缺失）→ 保持原 1 轮补写，零回归
        WC_FAIL=$(get_chapter_wordcount "$NEXT_CH")
        if (( WC_FAIL > MAX_WORDS_HARD )); then
            MAX_RETRIES=$SHRINK_MAX_ROUNDS
            FAIL_REASON="字数超限(${WC_FAIL}>${MAX_WORDS_HARD})"
        else
            MAX_RETRIES=1
            FAIL_REASON="验证失败"
        fi
        echo "[$i/$N] ⚠️  ${FAIL_REASON}，启动重试（最多 ${MAX_RETRIES} 轮）..."
        report_event "⚠️" "写作验证失败" "第${NEXT_CH}章 ${FAIL_REASON}，最多 ${MAX_RETRIES} 轮"

        # 重试前归档当前不完整草稿，避免 retry_chapter 误判为已存在
        _archive_partial_chapter "$NEXT_CH"

        RETRY_ROUND=0
        RETRY_VERIFIED=0
        while (( RETRY_ROUND < MAX_RETRIES )); do
            RETRY_ROUND=$((RETRY_ROUND + 1))
            echo "[$i/$N] 🔄 第${RETRY_ROUND}/${MAX_RETRIES}轮重试..."
            if ! retry_chapter "$NEXT_CH"; then
                echo "[$i/$N] ⚠️  重试进程也异常退出"
            fi
            sleep "$COOLDOWN"

            if verify_chapter "$NEXT_CH"; then
                RETRY_VERIFIED=1
                break
            fi
            # 本轮失败：归档半成品再进入下一轮
            _archive_partial_chapter "$NEXT_CH"
        done

        if (( RETRY_VERIFIED == 1 )); then
            WC=$(get_chapter_wordcount "$NEXT_CH")
            COMPLETED=$((COMPLETED + 1))
            echo "[$i/$N] ✅ 第${NEXT_CH}章完成（重试成功）| ${WC}字"
            print_chapter_progress "$COMPLETED" "$N"
            report_event "✅" "重试成功" "第${NEXT_CH}章 ${WC}字（${RETRY_ROUND}轮）"

            run_checkpoint "$NEXT_CH"
        else
            # 最终失败：归档残留半成品，避免下次 ink-auto 误判
            _archive_partial_chapter "$NEXT_CH"
            echo ""
            echo "═══════════════════════════════════════"
            echo "  ❌ 第${NEXT_CH}章写作失败，批量写作中止"
            echo "═══════════════════════════════════════"
            echo "  💡 提示：再次运行 /ink-auto ${N} 会从第${NEXT_CH}章重新开始"
            echo "      不完整草稿（如有）已自动归档到 .ink/recovery_backups/partial_chapters/"
            echo "═══════════════════════════════════════"
            EXIT_REASON="第${NEXT_CH}章写作失败（${FAIL_REASON}，${MAX_RETRIES}轮重试仍未通过）"
            report_event "❌" "批量写作中止" "第${NEXT_CH}章 ${FAIL_REASON}，已完成${COMPLETED}章"
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
