# ============================================================
# webnovel-writer → ink-writer 项目迁移脚本（Windows PowerShell 对等版）
# 用法: pwsh -File migrate_webnovel_to_ink.ps1 C:\path\to\novel\project
# ============================================================

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string] $ProjectRoot
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if (-not $ProjectRoot) {
    Write-Host "错误：请指定项目路径" -ForegroundColor Red
    Write-Host "用法: pwsh -File migrate_webnovel_to_ink.ps1 C:\path\to\novel\project"
    exit 1
}

# 转为绝对路径
if (-not (Test-Path $ProjectRoot -PathType Container)) {
    Write-Host "错误：路径不存在: $ProjectRoot" -ForegroundColor Red
    exit 1
}
$ProjectRoot = (Resolve-Path $ProjectRoot).Path

Write-Host "============================================================"
Write-Host " webnovel-writer → ink-writer 迁移工具"
Write-Host "============================================================"
Write-Host ""
Write-Host "项目路径: $ProjectRoot"
Write-Host ""

# ============================================================
# 预检
# ============================================================

$webnovelDir = Join-Path $ProjectRoot '.webnovel'
$inkDir      = Join-Path $ProjectRoot '.ink'
$outlineDir  = Join-Path $ProjectRoot '大纲'
$bodyDir     = Join-Path $ProjectRoot '正文'

if (-not (Test-Path $webnovelDir -PathType Container)) {
    Write-Host "错误：$webnovelDir 不存在，这不是一个 webnovel-writer 项目" -ForegroundColor Red
    exit 1
}

if (Test-Path $inkDir -PathType Container) {
    Write-Host "错误：$inkDir 已存在，项目可能已经迁移过" -ForegroundColor Red
    exit 1
}

Write-Host "🔍 预检..."

if (Test-Path (Join-Path $webnovelDir 'state.json') -PathType Leaf) {
    Write-Host "  ✅ state.json 存在" -ForegroundColor Green
} else {
    Write-Host "  ⚠️  state.json 不存在（新项目？）" -ForegroundColor Yellow
}

if (Test-Path (Join-Path $webnovelDir 'index.db') -PathType Leaf) {
    Write-Host "  ✅ index.db 存在" -ForegroundColor Green
} else {
    Write-Host "  ⚠️  index.db 不存在" -ForegroundColor Yellow
}

if (Test-Path $outlineDir -PathType Container) {
    Write-Host "  ✅ 大纲/ 目录存在" -ForegroundColor Green
} else {
    Write-Host "  ⚠️  大纲/ 目录不存在" -ForegroundColor Yellow
}

if (Test-Path $bodyDir -PathType Container) {
    Write-Host "  ✅ 正文/ 目录存在" -ForegroundColor Green
} else {
    Write-Host "  ⚠️  正文/ 目录不存在" -ForegroundColor Yellow
}

# 统计已写章节
$chapterCount = 0
if (Test-Path $bodyDir -PathType Container) {
    $chapterCount = (Get-ChildItem -Path $bodyDir -Recurse -File -Filter '第*.md' -ErrorAction SilentlyContinue | Measure-Object).Count
}

Write-Host ""
Write-Host "📊 项目统计:"
Write-Host "   已写章节: $chapterCount 章"

# 统计卷目录
$volDirs = @()
if (Test-Path $bodyDir -PathType Container) {
    $volDirs = @(Get-ChildItem -Path $bodyDir -Directory -Filter '第*卷' -ErrorAction SilentlyContinue)
}
$volCount = $volDirs.Count
Write-Host "   卷目录数: $volCount 个"
Write-Host ""

# ============================================================
# 确认
# ============================================================

Write-Host "将执行以下操作:"
Write-Host "  1. 重命名 .webnovel/ → .ink/"
if ($volCount -gt 0) {
    Write-Host "  2. 扁平化章节目录（将卷子目录中的章节移到 正文/ 根目录）"
}
Write-Host ""

$confirm = Read-Host "确认迁移？(y/N)"
if ($confirm -ne 'y' -and $confirm -ne 'Y') {
    Write-Host "已取消"
    exit 0
}

# ============================================================
# Step 1: 重命名隐藏目录
# ============================================================

Write-Host ""
Write-Host "📁 Step 1: 重命名 .webnovel/ → .ink/"
Move-Item -Path $webnovelDir -Destination $inkDir
Write-Host "  ✅ 完成" -ForegroundColor Green

# ============================================================
# Step 2: 扁平化章节目录
# ============================================================

if ($volCount -gt 0) {
    Write-Host ""
    Write-Host "📁 Step 2: 扁平化章节目录"

    $moved = 0
    foreach ($volDir in $volDirs) {
        $volName = $volDir.Name
        $mdFiles = @(Get-ChildItem -Path $volDir.FullName -File -Filter '*.md' -ErrorAction SilentlyContinue)
        $fileCount = $mdFiles.Count

        if ($fileCount -gt 0) {
            foreach ($chapterFile in $mdFiles) {
                $target = Join-Path $bodyDir $chapterFile.Name
                if (Test-Path $target -PathType Leaf) {
                    Write-Host "  ⚠️  跳过 $($chapterFile.Name)（目标已存在）" -ForegroundColor Yellow
                } else {
                    Move-Item -Path $chapterFile.FullName -Destination $target
                    $moved++
                }
            }
            Write-Host "  ✅ ${volName}: 移动 $fileCount 个文件" -ForegroundColor Green
        }

        # 尝试删除空卷目录（只删真正为空的）
        $remaining = @(Get-ChildItem -Path $volDir.FullName -Force -ErrorAction SilentlyContinue)
        if ($remaining.Count -eq 0) {
            Remove-Item -Path $volDir.FullName -Force
            Write-Host "  ✅ 删除空目录 $volName/" -ForegroundColor Green
        } else {
            Write-Host "  ⚠️  $volName/ 非空，保留" -ForegroundColor Yellow
        }
    }

    Write-Host "  共移动 $moved 个章节文件"
} else {
    Write-Host ""
    Write-Host "📁 Step 2: 无卷子目录，跳过扁平化"
}

# ============================================================
# Step 3: 验证
# ============================================================

Write-Host ""
Write-Host "🔍 Step 3: 验证迁移结果"

if (Test-Path $inkDir -PathType Container) {
    Write-Host "  ✅ .ink/ 目录存在" -ForegroundColor Green
} else {
    Write-Host "  ❌ .ink/ 目录不存在" -ForegroundColor Red
}

if (Test-Path (Join-Path $inkDir 'state.json') -PathType Leaf) {
    Write-Host "  ✅ .ink/state.json 存在" -ForegroundColor Green
} else {
    Write-Host "  ⚠️  .ink/state.json 不存在" -ForegroundColor Yellow
}

if (Test-Path (Join-Path $inkDir 'index.db') -PathType Leaf) {
    Write-Host "  ✅ .ink/index.db 存在" -ForegroundColor Green
} else {
    Write-Host "  ⚠️  .ink/index.db 不存在" -ForegroundColor Yellow
}

$flatChapters = 0
if (Test-Path $bodyDir -PathType Container) {
    $flatChapters = (Get-ChildItem -Path $bodyDir -File -Filter '第*.md' -ErrorAction SilentlyContinue | Measure-Object).Count
}
Write-Host "  📄 正文/ 根目录章节数: $flatChapters"

$remainingVols = 0
if (Test-Path $bodyDir -PathType Container) {
    $remainingVols = (Get-ChildItem -Path $bodyDir -Directory -Filter '第*卷' -ErrorAction SilentlyContinue | Measure-Object).Count
}
if ($remainingVols -gt 0) {
    Write-Host "  ⚠️  仍有 $remainingVols 个卷目录未清空（可能含非.md文件）" -ForegroundColor Yellow
} else {
    Write-Host "  ✅ 无残留卷目录" -ForegroundColor Green
}

if (Test-Path $webnovelDir -PathType Container) {
    Write-Host "  ❌ .webnovel/ 仍然存在" -ForegroundColor Red
} else {
    Write-Host "  ✅ .webnovel/ 已移除" -ForegroundColor Green
}

# ============================================================
# 完成
# ============================================================

Write-Host ""
Write-Host "============================================================"
Write-Host " 迁移完成！" -ForegroundColor Green
Write-Host "============================================================"
Write-Host ""
Write-Host "现在你可以使用 ink-writer 续写这个项目："
Write-Host "  /ink-write              # 写一章"
Write-Host "  /ink-write --batch 5    # 连续写5章"
Write-Host "  /ink-review             # 审查"
Write-Host ""
Write-Host "首次使用前建议执行："
Write-Host "  /ink-query              # 检查项目状态是否正常"
Write-Host ""
