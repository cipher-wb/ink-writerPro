#!/bin/bash
# e2e_smoke.sh — Mac/Linux 端到端 smoke 入口（US-014）
#
# 驱动 scripts/e2e_smoke_harness.py 完成：
#   init (init_project) → write (合成 N 章) → verify (index.db + recent_full_texts)
#     → cleanup（默认清理 tmp 项目）
#
# 默认 3 章、日志写 reports/e2e-smoke-mac.log。环境无 LLM 调用——首版按 PRD
# 退化路径：writer 用 harness 合成中文正文替代，只验证数据流水线跨平台健康度。
#
# 用法:
#   scripts/e2e_smoke.sh                # 3 章（默认）
#   scripts/e2e_smoke.sh 5              # 5 章
#   scripts/e2e_smoke.sh 5 --keep       # 5 章 + 保留 tmp 项目调试

set -euo pipefail

THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$THIS_DIR/.." && pwd)"
HARNESS="$THIS_DIR/e2e_smoke_harness.py"

# 复用 US-009 的 Python launcher 探测（Mac/Linux → python3；Windows git-bash → py -3 / python3 / python）
find_python_launcher_bash() {
    case "${OSTYPE:-}" in
        msys*|cygwin*|win32*)
            local candidates=("py -3" "python3" "python")  # c8-ok: detector primitive
            for _cand in "${candidates[@]}"; do
                if command -v ${_cand%% *} >/dev/null 2>&1; then
                    PYTHON_LAUNCHER="$_cand"  # c8-ok: detector primitive
                    return 0
                fi
            done
            PYTHON_LAUNCHER="python"  # c8-ok: detector primitive
            ;;
        *)
            PYTHON_LAUNCHER="python3"  # c8-ok: detector primitive (Mac/Linux 定值)
            ;;
    esac
}

if [ -z "${PYTHON_LAUNCHER:-}" ]; then
    find_python_launcher_bash
fi

ARGS=()
CHAPTERS_SET=0
for arg in "$@"; do
    case "$arg" in
        -h|--help)
            exec $PYTHON_LAUNCHER -X utf8 "$HARNESS" --help
            ;;
        --)
            ;;
        --*)
            ARGS+=("$arg")
            ;;
        *)
            if [ "$CHAPTERS_SET" = "0" ] && [[ "$arg" =~ ^[0-9]+$ ]]; then
                ARGS+=("--chapters" "$arg")
                CHAPTERS_SET=1
            else
                ARGS+=("$arg")
            fi
            ;;
    esac
done

cd "$REPO_ROOT"
exec $PYTHON_LAUNCHER -X utf8 "$HARNESS" "${ARGS[@]}"
