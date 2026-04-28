#!/bin/bash
# interactive_bootstrap.sh — empty-dir 7-question fallback for /ink-auto
#
# Usage:  bash interactive_bootstrap.sh <output_path>
# Output: writes a blueprint .md to <output_path>
# Exit:   0 on success, 130 on Ctrl+C, 1 on error
set -euo pipefail

OUT="${1:-.ink-auto-blueprint.md}"

# Trap Ctrl+C — do NOT keep half-written file
cleanup_on_interrupt() {
    rm -f "$OUT"
    echo
    echo "❌ 用户中断，已删除半成品蓝本"
    exit 130
}
trap cleanup_on_interrupt INT

prompt_required() {
    local prompt="$1"
    local var=""
    while [[ -z "$var" ]]; do
        printf "%s\n> " "$prompt" >&2
        IFS= read -r var
        if [[ -z "$var" ]]; then
            echo "  ⚠️  必填，请重新输入" >&2
        fi
    done
    printf "%s" "$var"
}

prompt_with_default() {
    local prompt="$1"
    local default="$2"
    local var=""
    printf "%s（默认 %s）\n> " "$prompt" "$default" >&2
    IFS= read -r var
    if [[ -z "$var" ]]; then
        var="$default"
    fi
    printf "%s" "$var"
}

echo "============================================" >&2
echo "  ink-auto 空目录 7 题快速 bootstrap" >&2
echo "============================================" >&2

GENRE=$(prompt_required "1/7 题材方向（如：仙侠 / 都市悬疑 / 末世+异能）？")
PROTAGONIST=$(prompt_required "2/7 主角一句话人设（含欲望+缺陷）？")
GF_TYPE=$(prompt_required "3/7 金手指类型（信息/时间/情感/社交/认知/概率/感知/规则 8 选 1）？")
GF_LINE=$(prompt_required "4/7 金手指能力一句话（≤20 字，含具体动作/反直觉维度）？")
CONFLICT=$(prompt_required "5/7 核心冲突一句话？")
PLATFORM=$(prompt_with_default "6/7 平台 (qidian/fanqie)？" "qidian")
AGGRESSION=$(prompt_with_default "7/7 激进度档位 (1 保守 / 2 平衡 / 3 激进 / 4 疯批)？" "2")

cat > "$OUT" <<EOF
# ink-auto 自动 bootstrap 生成的蓝本（空目录场景）

## 一、项目元信息
### 平台
${PLATFORM}

### 激进度档位
${AGGRESSION}

## 二、故事核心
### 题材方向
${GENRE}

### 核心冲突
${CONFLICT}

## 三、主角设定
### 主角姓名
AUTO

### 主角人设
${PROTAGONIST}

## 四、金手指
### 金手指类型
${GF_TYPE}

### 能力一句话
${GF_LINE}

## 五、配角与情感线
### 女主姓名
AUTO
EOF

trap - INT
echo "✅ 蓝本已落盘：$OUT" >&2
exit 0
