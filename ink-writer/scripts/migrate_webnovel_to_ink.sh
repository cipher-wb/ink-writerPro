#!/bin/bash
# ============================================================
# webnovel-writer → ink-writer 项目迁移脚本
# 用法: bash migrate_webnovel_to_ink.sh /path/to/your/novel/project
# ============================================================

set -euo pipefail

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PROJECT_ROOT="${1:-}"

if [ -z "$PROJECT_ROOT" ]; then
    echo -e "${RED}错误：请指定项目路径${NC}"
    echo "用法: bash migrate_webnovel_to_ink.sh /path/to/your/novel/project"
    exit 1
fi

# 转为绝对路径
PROJECT_ROOT="$(cd "$PROJECT_ROOT" && pwd)"

echo "============================================================"
echo " webnovel-writer → ink-writer 迁移工具"
echo "============================================================"
echo ""
echo "项目路径: $PROJECT_ROOT"
echo ""

# ============================================================
# 预检
# ============================================================

# 检查是否是 webnovel 项目
if [ ! -d "$PROJECT_ROOT/.webnovel" ]; then
    echo -e "${RED}错误：$PROJECT_ROOT/.webnovel 不存在，这不是一个 webnovel-writer 项目${NC}"
    exit 1
fi

# 检查是否已经有 .ink 目录（避免覆盖）
if [ -d "$PROJECT_ROOT/.ink" ]; then
    echo -e "${RED}错误：$PROJECT_ROOT/.ink 已存在，项目可能已经迁移过${NC}"
    exit 1
fi

# 检查关键文件
echo "🔍 预检..."

if [ -f "$PROJECT_ROOT/.webnovel/state.json" ]; then
    echo -e "  ${GREEN}✅ state.json 存在${NC}"
else
    echo -e "  ${YELLOW}⚠️  state.json 不存在（新项目？）${NC}"
fi

if [ -f "$PROJECT_ROOT/.webnovel/index.db" ]; then
    echo -e "  ${GREEN}✅ index.db 存在${NC}"
else
    echo -e "  ${YELLOW}⚠️  index.db 不存在${NC}"
fi

if [ -d "$PROJECT_ROOT/大纲" ]; then
    echo -e "  ${GREEN}✅ 大纲/ 目录存在${NC}"
else
    echo -e "  ${YELLOW}⚠️  大纲/ 目录不存在${NC}"
fi

if [ -d "$PROJECT_ROOT/正文" ]; then
    echo -e "  ${GREEN}✅ 正文/ 目录存在${NC}"
else
    echo -e "  ${YELLOW}⚠️  正文/ 目录不存在${NC}"
fi

# 统计已写章节
chapter_count=0
if [ -d "$PROJECT_ROOT/正文" ]; then
    chapter_count=$(find "$PROJECT_ROOT/正文" -name "第*.md" -type f | wc -l | tr -d ' ')
fi
echo ""
echo "📊 项目统计:"
echo "   已写章节: ${chapter_count} 章"

# 统计卷目录
vol_dirs=0
if [ -d "$PROJECT_ROOT/正文" ]; then
    vol_dirs=$(find "$PROJECT_ROOT/正文" -maxdepth 1 -name "第*卷" -type d | wc -l | tr -d ' ')
fi
echo "   卷目录数: ${vol_dirs} 个"
echo ""

# ============================================================
# 确认
# ============================================================

echo "将执行以下操作:"
echo "  1. 重命名 .webnovel/ → .ink/"
if [ "$vol_dirs" -gt 0 ]; then
    echo "  2. 扁平化章节目录（将卷子目录中的章节移到 正文/ 根目录）"
fi
echo ""
read -p "确认迁移？(y/N) " confirm
if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
    echo "已取消"
    exit 0
fi

# ============================================================
# Step 1: 重命名隐藏目录
# ============================================================

echo ""
echo "📁 Step 1: 重命名 .webnovel/ → .ink/"
mv "$PROJECT_ROOT/.webnovel" "$PROJECT_ROOT/.ink"
echo -e "  ${GREEN}✅ 完成${NC}"

# ============================================================
# Step 2: 扁平化章节目录
# ============================================================

if [ "$vol_dirs" -gt 0 ]; then
    echo ""
    echo "📁 Step 2: 扁平化章节目录"

    moved=0
    for vol_dir in "$PROJECT_ROOT/正文/第"*"卷"; do
        if [ -d "$vol_dir" ]; then
            vol_name=$(basename "$vol_dir")
            file_count=$(find "$vol_dir" -name "*.md" -type f | wc -l | tr -d ' ')

            if [ "$file_count" -gt 0 ]; then
                # 移动所有 md 文件到正文根目录
                for chapter_file in "$vol_dir"/*.md; do
                    if [ -f "$chapter_file" ]; then
                        filename=$(basename "$chapter_file")
                        # 检查目标是否已存在
                        if [ -f "$PROJECT_ROOT/正文/$filename" ]; then
                            echo -e "  ${YELLOW}⚠️  跳过 $filename（目标已存在）${NC}"
                        else
                            mv "$chapter_file" "$PROJECT_ROOT/正文/"
                            moved=$((moved + 1))
                        fi
                    fi
                done
                echo -e "  ${GREEN}✅ $vol_name: 移动 $file_count 个文件${NC}"
            fi

            # 尝试删除空卷目录
            rmdir "$vol_dir" 2>/dev/null && echo -e "  ${GREEN}✅ 删除空目录 $vol_name/${NC}" || echo -e "  ${YELLOW}⚠️  $vol_name/ 非空，保留${NC}"
        fi
    done

    echo "  共移动 $moved 个章节文件"
else
    echo ""
    echo "📁 Step 2: 无卷子目录，跳过扁平化"
fi

# ============================================================
# Step 3: 验证
# ============================================================

echo ""
echo "🔍 Step 3: 验证迁移结果"

# 检查 .ink 目录
if [ -d "$PROJECT_ROOT/.ink" ]; then
    echo -e "  ${GREEN}✅ .ink/ 目录存在${NC}"
else
    echo -e "  ${RED}❌ .ink/ 目录不存在${NC}"
fi

# 检查 state.json
if [ -f "$PROJECT_ROOT/.ink/state.json" ]; then
    echo -e "  ${GREEN}✅ .ink/state.json 存在${NC}"
else
    echo -e "  ${YELLOW}⚠️  .ink/state.json 不存在${NC}"
fi

# 检查 index.db
if [ -f "$PROJECT_ROOT/.ink/index.db" ]; then
    echo -e "  ${GREEN}✅ .ink/index.db 存在${NC}"
else
    echo -e "  ${YELLOW}⚠️  .ink/index.db 不存在${NC}"
fi

# 检查章节文件是否在正文根目录
flat_chapters=$(find "$PROJECT_ROOT/正文" -maxdepth 1 -name "第*.md" -type f | wc -l | tr -d ' ')
echo "  📄 正文/ 根目录章节数: $flat_chapters"

# 检查是否还有残留卷目录
remaining_vols=$(find "$PROJECT_ROOT/正文" -maxdepth 1 -name "第*卷" -type d 2>/dev/null | wc -l | tr -d ' ')
if [ "$remaining_vols" -gt 0 ]; then
    echo -e "  ${YELLOW}⚠️  仍有 $remaining_vols 个卷目录未清空（可能含非.md文件）${NC}"
else
    echo -e "  ${GREEN}✅ 无残留卷目录${NC}"
fi

# 检查 .webnovel 是否已删除
if [ -d "$PROJECT_ROOT/.webnovel" ]; then
    echo -e "  ${RED}❌ .webnovel/ 仍然存在${NC}"
else
    echo -e "  ${GREEN}✅ .webnovel/ 已移除${NC}"
fi

# ============================================================
# 完成
# ============================================================

echo ""
echo "============================================================"
echo -e " ${GREEN}迁移完成！${NC}"
echo "============================================================"
echo ""
echo "现在你可以使用 ink-writer 续写这个项目："
echo "  /ink-write              # 写一章"
echo "  /ink-write --batch 5    # 连续写5章"
echo "  /ink-review             # 审查"
echo ""
echo "首次使用前建议执行："
echo "  /ink-query              # 检查项目状态是否正常"
echo ""
