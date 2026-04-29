# check_plugin_version_consistency.ps1 — Windows release pre-flight 入口
#
# 校验 ink-writer/.claude-plugin/plugin.json 与 .claude-plugin/marketplace.json
# 的版本号一致；不一致返回非零退出码，便于挂入 pre-commit / CI。
#
# 用法:
#   .\scripts\maintenance\check_plugin_version_consistency.ps1
#   .\scripts\maintenance\check_plugin_version_consistency.ps1 --plugin-json other.json

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ThisDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent (Split-Path -Parent $ThisDir)
$Script = Join-Path $ThisDir 'check_plugin_version_consistency.py'

function Find-PythonLauncher {
    $candidates = @('py -3', 'python3', 'python') # c8-ok: detector primitive
    foreach ($cand in $candidates) {
        $exe = ($cand -split ' ')[0]
        if (Get-Command $exe -ErrorAction SilentlyContinue) {
            return $cand
        }
    }
    return 'python'
}

if (-not $env:PYTHON_LAUNCHER) {
    $env:PYTHON_LAUNCHER = Find-PythonLauncher
}

Push-Location $RepoRoot
try {
    $parts = $env:PYTHON_LAUNCHER -split ' '
    $exe = $parts[0]
    $preArgs = @()
    if ($parts.Length -gt 1) { $preArgs = $parts[1..($parts.Length - 1)] }
    & $exe @preArgs '-X' 'utf8' $Script @args
    $code = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $code
