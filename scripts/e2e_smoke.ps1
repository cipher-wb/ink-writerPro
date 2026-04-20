# e2e_smoke.ps1 — Windows 端到端 smoke 入口（US-014）
#
# 驱动 scripts/e2e_smoke_harness.py 完成：
#   init (init_project) → write (合成 N 章) → verify (index.db + recent_full_texts)
#     → cleanup（默认清理 tmp 项目）
#
# 默认 3 章、日志写 reports/e2e-smoke-windows.log。环境无 LLM 调用——首版按 PRD
# 退化路径：writer 用 harness 合成中文正文替代，只验证数据流水线跨平台健康度。
#
# 用法:
#   .\scripts\e2e_smoke.ps1              # 3 章
#   .\scripts\e2e_smoke.ps1 5            # 5 章
#   .\scripts\e2e_smoke.ps1 5 --keep     # 5 章 + 保留 tmp 项目调试

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ThisDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ThisDir
$Harness = Join-Path $ThisDir 'e2e_smoke_harness.py'

function Find-PythonLauncher {
    $candidates = @('py -3', 'python3', 'python')  # c8-ok: detector primitive
    foreach ($cand in $candidates) {
        $exe = ($cand -split ' ')[0]
        if (Get-Command $exe -ErrorAction SilentlyContinue) {
            return $cand  # c8-ok: detector primitive
        }
    }
    return 'python'  # c8-ok: detector primitive
}

if (-not $env:PYTHON_LAUNCHER) {
    $env:PYTHON_LAUNCHER = Find-PythonLauncher
}

# 解析参数：第一个数字 → --chapters，其他透传
$PassThrough = @()
$ChaptersSet = $false
foreach ($arg in $args) {
    if (($arg -eq '-h') -or ($arg -eq '--help')) {
        $parts = $env:PYTHON_LAUNCHER -split ' '
        $exe = $parts[0]
        $preArgs = @()
        if ($parts.Length -gt 1) { $preArgs = $parts[1..($parts.Length - 1)] }
        & $exe @preArgs '-X' 'utf8' $Harness '--help'
        exit $LASTEXITCODE
    }
    if ((-not $ChaptersSet) -and ($arg -match '^[0-9]+$')) {
        $PassThrough += '--chapters'
        $PassThrough += $arg
        $ChaptersSet = $true
    } else {
        $PassThrough += $arg
    }
}

Push-Location $RepoRoot
try {
    $parts = $env:PYTHON_LAUNCHER -split ' '
    $exe = $parts[0]
    $preArgs = @()
    if ($parts.Length -gt 1) { $preArgs = $parts[1..($parts.Length - 1)] }
    & $exe @preArgs '-X' 'utf8' $Harness @PassThrough
    $code = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $code
