# ============================================================
# ink-writer PowerShell 共享环境初始化脚本（Windows 对等版 env-setup.sh）
#
# 输入环境变量（可选）：
#   INK_SKILL_NAME   — 设置后自动导出 SKILL_ROOT
#   INK_PREFLIGHT=1  — 设置后自动运行 preflight 校验
#   INK_DASHBOARD=1  — 设置后校验并导出 DASHBOARD_DIR
#
# 输出环境变量（写入当前进程 $env:）：
#   WORKSPACE_ROOT, CLAUDE_PLUGIN_ROOT, SCRIPTS_DIR, PROJECT_ROOT,
#   PYTHON_LAUNCHER
#   SKILL_ROOT    （如果设置了 INK_SKILL_NAME）
#   DASHBOARD_DIR （如果设置了 INK_DASHBOARD=1）
#
# 典型用法（从另一脚本 dot-source）：
#   . "$PSScriptRoot\env-setup.ps1"
# ============================================================

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# Step 1: Workspace root
if ($env:INK_PROJECT_ROOT) {
    $env:WORKSPACE_ROOT = $env:INK_PROJECT_ROOT
} elseif ($env:CLAUDE_PROJECT_DIR) {
    $env:WORKSPACE_ROOT = $env:CLAUDE_PROJECT_DIR
} else {
    $env:WORKSPACE_ROOT = (Get-Location).Path
}

# Step 2: Resolve CLAUDE_PLUGIN_ROOT
function Test-PluginRoot {
    param([string]$Dir)
    if (-not $Dir) { return $false }
    return (Test-Path (Join-Path $Dir 'scripts') -PathType Container) -and
           (Test-Path (Join-Path $Dir 'skills') -PathType Container)
}

if (-not (Test-PluginRoot $env:CLAUDE_PLUGIN_ROOT)) {
    $cwd = (Get-Location).Path
    if (Test-PluginRoot $cwd) {
        $env:CLAUDE_PLUGIN_ROOT = $cwd
    } elseif (Test-PluginRoot (Split-Path $cwd -Parent)) {
        $env:CLAUDE_PLUGIN_ROOT = (Resolve-Path (Join-Path $cwd '..')).Path
    } else {
        # Fallback: 从本脚本自身路径反推插件根目录 (scripts/ 的父目录)
        $envSetupDir = Split-Path -Parent $PSCommandPath
        $candidate = Split-Path -Parent $envSetupDir
        if (Test-PluginRoot $candidate) {
            $env:CLAUDE_PLUGIN_ROOT = (Resolve-Path $candidate).Path
        } else {
            Write-Error "未设置 CLAUDE_PLUGIN_ROOT，且无法从当前目录推断插件根目录"
            exit 1
        }
    }
}

# Step 3: Core paths
$env:SCRIPTS_DIR = Join-Path $env:CLAUDE_PLUGIN_ROOT 'scripts'

if (-not (Test-Path $env:SCRIPTS_DIR -PathType Container)) {
    Write-Error "脚本目录不存在: $($env:SCRIPTS_DIR)"
    exit 1
}

# Step 3.5: Python launcher detection (py -3 > python3 > python)
function Find-PythonLauncher {
    $candidates = @(
        @{ Cmd = 'py';      Args = @('-3', '--version') },
        @{ Cmd = 'python3'; Args = @('--version')       },  # c8-ok: detector primitive
        @{ Cmd = 'python';  Args = @('--version')       }
    )
    foreach ($c in $candidates) {
        if (-not (Get-Command $c.Cmd -ErrorAction SilentlyContinue)) { continue }
        try {
            $null = & $c.Cmd @($c.Args) 2>&1
            if ($LASTEXITCODE -eq 0) {
                if ($c.Cmd -eq 'py') { return 'py -3' }  # c8-ok: detector primitive
                return $c.Cmd
            }
        } catch {
            continue
        }
    }
    return 'python'
}

if (-not $env:PYTHON_LAUNCHER) {
    $env:PYTHON_LAUNCHER = Find-PythonLauncher
}

# 辅助：用检测到的启动器调 Python，统一带 -X utf8
function Invoke-InkPython {
    param([Parameter(ValueFromRemainingArguments = $true)] [string[]] $Args)
    $parts = $env:PYTHON_LAUNCHER -split ' '
    $exe = $parts[0]
    $preArgs = @()
    if ($parts.Count -gt 1) { $preArgs = $parts[1..($parts.Count - 1)] }
    & $exe @preArgs '-X' 'utf8' @Args
}

# Step 4: SKILL_ROOT (optional)
if ($env:INK_SKILL_NAME) {
    $env:SKILL_ROOT = Join-Path (Join-Path $env:CLAUDE_PLUGIN_ROOT 'skills') $env:INK_SKILL_NAME
}

# Step 5: Dashboard mode (optional)
if ($env:INK_DASHBOARD -eq '1') {
    $dashDir = Join-Path $env:CLAUDE_PLUGIN_ROOT 'dashboard'
    if (-not (Test-Path $dashDir -PathType Container)) {
        Write-Error "未找到 dashboard 模块: $dashDir"
        exit 1
    }
    $env:DASHBOARD_DIR = $dashDir
}

# Step 6: Preflight check (optional)
if ($env:INK_PREFLIGHT -eq '1') {
    Invoke-InkPython (Join-Path $env:SCRIPTS_DIR 'ink.py') '--project-root' $env:WORKSPACE_ROOT 'preflight'
}

# Step 7: Resolve PROJECT_ROOT via ink.py
$projectRoot = Invoke-InkPython (Join-Path $env:SCRIPTS_DIR 'ink.py') '--project-root' $env:WORKSPACE_ROOT 'where'
if ($projectRoot) {
    $env:PROJECT_ROOT = ($projectRoot | Select-Object -First 1).Trim()
}
