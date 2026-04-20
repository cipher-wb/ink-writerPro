# ============================================================
# ralph.ps1 — Windows PowerShell 对等版 ralph.sh
# Long-running AI agent loop（仅支持 claude 工具，Windows 场景下无 amp）。
#
# 用法:
#   pwsh -File ralph.ps1 [-Tool claude] [-MaxIterations 10]
# ============================================================

[CmdletBinding()]
param(
    [ValidateSet('amp', 'claude')]
    [string] $Tool = 'claude',

    [int] $MaxIterations = 10,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $Remaining
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# 兼容 bash 风格的位置参数：数字视为 MaxIterations
if ($Remaining) {
    foreach ($tok in $Remaining) {
        $parsed = 0
        if ([int]::TryParse($tok, [ref] $parsed)) { $MaxIterations = $parsed }
    }
}

if ($Tool -ne 'amp' -and $Tool -ne 'claude') {
    Write-Host "Error: Invalid tool '$Tool'. Must be 'amp' or 'claude'."
    exit 1
}

$ScriptDir       = Split-Path -Parent $PSCommandPath
$PrdFile         = Join-Path $ScriptDir 'prd.json'
$ProgressFile    = Join-Path $ScriptDir 'progress.txt'
$ArchiveDir      = Join-Path $ScriptDir 'archive'
$LastBranchFile  = Join-Path $ScriptDir '.last-branch'
$PromptFile      = Join-Path $ScriptDir 'prompt.md'
$ClaudeMd        = Join-Path $ScriptDir 'CLAUDE.md'

function Read-BranchFromPrd {
    if (-not (Test-Path $PrdFile -PathType Leaf)) { return '' }
    try {
        $prd = Get-Content $PrdFile -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($prd.branchName) { return [string] $prd.branchName }
    } catch {}
    return ''
}

# Archive previous run if branch changed
if ((Test-Path $PrdFile -PathType Leaf) -and (Test-Path $LastBranchFile -PathType Leaf)) {
    $currentBranch = Read-BranchFromPrd
    $lastBranch = ''
    try { $lastBranch = (Get-Content $LastBranchFile -Raw -Encoding UTF8).Trim() } catch {}

    if ($currentBranch -and $lastBranch -and ($currentBranch -ne $lastBranch)) {
        $date = (Get-Date).ToString('yyyy-MM-dd')
        $folderName = $lastBranch -replace '^ralph/', ''
        $archiveFolder = Join-Path $ArchiveDir "$date-$folderName"

        Write-Host "Archiving previous run: $lastBranch"
        New-Item -ItemType Directory -Force -Path $archiveFolder | Out-Null
        if (Test-Path $PrdFile -PathType Leaf)      { Copy-Item $PrdFile      $archiveFolder }
        if (Test-Path $ProgressFile -PathType Leaf) { Copy-Item $ProgressFile $archiveFolder }
        Write-Host "   Archived to: $archiveFolder"

        # Reset progress file
        $header = @(
            '# Ralph Progress Log'
            "Started: $(Get-Date)"
            '---'
        )
        $header | Set-Content -Path $ProgressFile -Encoding UTF8
    }
}

# Track current branch
$branch = Read-BranchFromPrd
if ($branch) {
    $branch | Set-Content -Path $LastBranchFile -Encoding UTF8 -NoNewline
}

# Initialize progress file if missing
if (-not (Test-Path $ProgressFile -PathType Leaf)) {
    $header = @(
        '# Ralph Progress Log'
        "Started: $(Get-Date)"
        '---'
    )
    $header | Set-Content -Path $ProgressFile -Encoding UTF8
}

Write-Host "Starting Ralph - Tool: $Tool - Max iterations: $MaxIterations"

for ($i = 1; $i -le $MaxIterations; $i++) {
    Write-Host ''
    Write-Host '==============================================================='
    Write-Host "  Ralph Iteration $i of $MaxIterations ($Tool)"
    Write-Host '==============================================================='

    $output = ''
    try {
        if ($Tool -eq 'amp') {
            if (-not (Get-Command amp -ErrorAction SilentlyContinue)) {
                Write-Host 'Error: amp not found in PATH. Install amp or use --tool claude.'
                exit 1
            }
            $promptText = Get-Content $PromptFile -Raw -Encoding UTF8
            $output = $promptText | & amp --dangerously-allow-all 2>&1
        } else {
            if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
                Write-Host 'Error: claude CLI not found in PATH. Install Claude Code first.'
                exit 1
            }
            $claudeMdContent = Get-Content $ClaudeMd -Raw -Encoding UTF8
            $output = $claudeMdContent | & claude --dangerously-skip-permissions --print 2>&1
        }
    } catch {
        Write-Host "Iteration $i encountered an error: $_"
    }

    if ($output) { $output | Out-Host }

    # US-011: 与 ralph.sh 保持字节级语义一致的 COMPLETE 检测——
    #   1) 只看 OUTPUT 的最后 50 行（$tailText）避免早期 prompt 回显误触发；
    #   2) (?m) 多行模式 + ^...$ 行锚定：sentinel 必须独占一行。
    $outputText = if ($null -eq $output) { '' } else { ($output | Out-String) }
    $lines = $outputText -split "`r?`n"
    $tailLines = $lines | Select-Object -Last 50
    $tailText = $tailLines -join "`n"
    if ($tailText -match '(?m)^\s*<promise>COMPLETE</promise>\s*$') {
        Write-Host ''
        Write-Host 'Ralph completed all tasks!'
        Write-Host "Completed at iteration $i of $MaxIterations"
        exit 0
    }

    Write-Host "Iteration $i complete. Continuing..."
    Start-Sleep -Seconds 2
}

Write-Host ''
Write-Host "Ralph reached max iterations ($MaxIterations) without completing all tasks."
Write-Host "Check $ProgressFile for status."
exit 1
