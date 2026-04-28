# interactive_bootstrap.ps1 — Windows sibling to interactive_bootstrap.sh
# Usage:  pwsh interactive_bootstrap.ps1 <output_path>
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

param(
    [Parameter(Position=0, Mandatory=$false)]
    [string]$OutPath = ".ink-auto-blueprint.md"
)

function Prompt-Required {
    param([string]$Prompt)
    while ($true) {
        Write-Host $Prompt
        $val = Read-Host ">"
        if ($val) { return $val }
        Write-Host "  ⚠️  必填，请重新输入"
    }
}

function Prompt-WithDefault {
    param([string]$Prompt, [string]$Default)
    Write-Host "$Prompt（默认 $Default）"
    $val = Read-Host ">"
    if (-not $val) { return $Default }
    return $val
}

try {
    Write-Host "============================================"
    Write-Host "  ink-auto 空目录 7 题快速 bootstrap"
    Write-Host "============================================"

    $genre = Prompt-Required "1/7 题材方向（如：仙侠 / 都市悬疑 / 末世+异能）？"
    $protagonist = Prompt-Required "2/7 主角一句话人设（含欲望+缺陷）？"
    $gfType = Prompt-Required "3/7 金手指类型（信息/时间/情感/社交/认知/概率/感知/规则 8 选 1）？"
    $gfLine = Prompt-Required "4/7 金手指能力一句话（≤20 字，含具体动作/反直觉维度）？"
    $conflict = Prompt-Required "5/7 核心冲突一句话？"
    $platform = Prompt-WithDefault "6/7 平台 (qidian/fanqie)？" "qidian"
    $aggression = Prompt-WithDefault "7/7 激进度档位 (1 保守 / 2 平衡 / 3 激进 / 4 疯批)？" "2"

    $body = @"
# ink-auto 自动 bootstrap 生成的蓝本（空目录场景）

## 一、项目元信息
### 平台
$platform

### 激进度档位
$aggression

## 二、故事核心
### 题材方向
$genre

### 核心冲突
$conflict

## 三、主角设定
### 主角姓名
AUTO

### 主角人设
$protagonist

## 四、金手指
### 金手指类型
$gfType

### 能力一句话
$gfLine

## 五、配角与情感线
### 女主姓名
AUTO
"@

    Set-Content -Path $OutPath -Value $body -Encoding UTF8
    Write-Host "✅ 蓝本已落盘：$OutPath"
    exit 0
}
catch {
    if (Test-Path $OutPath) { Remove-Item $OutPath -Force }
    Write-Host "❌ $($_.Exception.Message)"
    exit 1
}
