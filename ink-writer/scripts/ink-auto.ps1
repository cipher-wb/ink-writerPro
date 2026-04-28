# ============================================================
# ink-auto.ps1 — Windows PowerShell 对等版 ink-auto.sh
#
# 功能等价于 ink-auto.sh：
#   - 参数解析：-Parallel N 或 --parallel N；位置参数为章节数
#   - 分层检查点调度（5 章 review+fix / 10 章 audit quick / 20 章 audit
#     standard+Tier2 / 50 章 Tier2+drift / 200 章 Tier3，委托 Python
#     checkpoint-level 命令）
#   - 大纲缺失自动规划，失败优雅中止
#   - 全书完结检测
#   - 运行报告（与 .sh 报告字段一致）
#
# Windows 用户通过 ink-auto.cmd 或直接调用 PowerShell 运行：
#   pwsh -File ink-auto.ps1 5
#   pwsh -File ink-auto.ps1 -Parallel 4 20
# ============================================================

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [int] $N = 5,

    [int] $Parallel = 0,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $Remaining
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# 兼容 --parallel N 的 bash 风格，扫描 Remaining 做二次解析
if ($Remaining) {
    for ($i = 0; $i -lt $Remaining.Count; $i++) {
        $tok = $Remaining[$i]
        if ($tok -eq '--parallel' -or $tok -eq '-p') {
            if ($i + 1 -lt $Remaining.Count) {
                $Parallel = [int] $Remaining[$i + 1]
                $i++
            }
        } else {
            $parsed = 0
            if ([int]::TryParse($tok, [ref] $parsed)) {
                $N = $parsed
            }
        }
    }
}

if ($N -le 0) { $N = 5 }

$Cooldown           = if ($env:INK_AUTO_COOLDOWN)            { [int] $env:INK_AUTO_COOLDOWN }            else { 10 }
$CheckpointCooldown = if ($env:INK_AUTO_CHECKPOINT_COOLDOWN) { [int] $env:INK_AUTO_CHECKPOINT_COOLDOWN } else { 15 }

# 统计
$stats = [pscustomobject]@{
    ReviewCount          = 0
    AuditCount           = 0
    MacroCount           = 0
    PlanCount            = 0
    FixCount             = 0
    CompressNotifyCount  = 0
    PlannedVolumes       = ':'
    Completed            = 0
    ExitReason           = ''
}

$startTime     = Get-Date
$startEpoch    = [int][double]::Parse((Get-Date -UFormat %s))
$startTimeStr  = $startTime.ToString('yyyy-MM-dd HH:mm:ss')

# v27: top-level defaults for trap-driven cleanup paths (needed when user
# Ctrl+C during init bootstrap, before Initialize-ProjectPaths has run)
$script:LogDir       = ""
$script:ReportFile   = ""
$script:BatchStart   = 0
$script:ReportEvents = ""

# ============================================================
# 路径解析
# ============================================================

$ScriptDir  = Split-Path -Parent $PSCommandPath
$PluginRoot = Split-Path -Parent $ScriptDir
$RepoRoot   = Split-Path -Parent $PluginRoot
$ScriptsDir = Join-Path $PluginRoot 'scripts'

function Find-ProjectRoot {
    $dir = (Get-Location).Path
    while ($true) {
        if (Test-Path (Join-Path $dir '.ink/state.json') -PathType Leaf) {
            return $dir
        }
        $parent = Split-Path -Parent $dir
        if (-not $parent -or $parent -eq $dir) { return $null }
        $dir = $parent
    }
}

$ProjectRoot = Find-ProjectRoot
# v27 ink-auto 终极自动化：允许 PROJECT_ROOT 暂时为空，后续状态分发处理
if (-not $ProjectRoot) {
    $ProjectRoot = ""
}

function Initialize-ProjectPaths {
    $script:LogDir    = Join-Path $script:ProjectRoot '.ink/logs/auto'
    $script:ReportDir = Join-Path $script:ProjectRoot '.ink/reports'
    New-Item -ItemType Directory -Force -Path $script:LogDir, $script:ReportDir | Out-Null
    $script:ReportFile = Join-Path $script:ReportDir ("auto-{0}.md" -f $startTime.ToString('yyyyMMdd-HHmmss'))

    # ============================================================
    # 字数硬上限（US-004）：从 preferences.json 的 pacing.chapter_words 推导 +500
    # 读取失败/损坏/未配置 → 默认 5000（与 load_word_limits 默认一致）。
    # MaxWordsHard 是 Test-Chapter 上限阻断阈值；硬下限 2200 不可降（与 .sh 语义一致）。
    # ============================================================

    $script:MaxWordsHard = 5000
    try {
        $prefFile = Join-Path $script:ProjectRoot '.ink/preferences.json'
        if (Test-Path -LiteralPath $prefFile -PathType Leaf) {
            $prefData = Get-Content -LiteralPath $prefFile -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($prefData -and $prefData.pacing -and $prefData.pacing.chapter_words) {
                $cw = $prefData.pacing.chapter_words
                # 仅接受正整数；bool / 非数字 / 非正数 → 保持默认 5000
                if ($cw -is [int] -and $cw -gt 0) {
                    $script:MaxWordsHard = $cw + 500
                }
            }
        }
    } catch {
        $script:MaxWordsHard = 5000
    }
    if ($script:MaxWordsHard -lt 2200) { $script:MaxWordsHard = 5000 }

    # 精简循环最大轮次（US-004：3 轮，与 SKILL.md 2A.5 对齐；下限补写循环保持 1 轮零回归）
    $script:ShrinkMaxRounds = 3
}

if ($ProjectRoot) {
    Initialize-ProjectPaths
}

# Python launcher
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
                if ($c.Cmd -eq 'py') { return @('py', '-3') }
                return @($c.Cmd)
            }
        } catch { continue }
    }
    return @('python')
}

$PyLauncher = Find-PythonLauncher

function Invoke-InkPy {
    [CmdletBinding()]
    param([Parameter(ValueFromRemainingArguments = $true)] [string[]] $PyArgs)
    & $PyLauncher[0] @($PyLauncher[1..($PyLauncher.Count - 1)]) '-X' 'utf8' @PyArgs
}

function Invoke-InkCli {
    [CmdletBinding()]
    param([Parameter(ValueFromRemainingArguments = $true)] [string[]] $Rest)
    $inkPy = Join-Path $ScriptsDir 'ink.py'
    Invoke-InkPy $inkPy '--project-root' $ProjectRoot @Rest
}

# ============================================================
# 平台检测（Windows 上默认只检查 claude）
# ============================================================

$Platform = ''
foreach ($p in @('claude', 'gemini', 'codex')) {
    if (Get-Command $p -ErrorAction SilentlyContinue) { $Platform = $p; break }
}
if (-not $Platform) {
    Write-Host '❌ 未找到 claude / gemini / codex，请先安装 Claude Code'
    exit 1
}

# ============================================================
# 事件日志 + 报告
# ============================================================

$reportEvents = New-Object System.Collections.Generic.List[string]

function Report-Event {
    param([string] $Status, [string] $Event, [string] $Detail = '')
    $ts = (Get-Date).ToString('HH:mm:ss')
    $reportEvents.Add("| $ts | $Status | $Event | $Detail |")
}

function Format-Duration {
    param([int] $Seconds)
    if ($Seconds -lt 60) { return "${Seconds}s" }
    if ($Seconds -lt 3600) { return ("{0}m{1}s" -f [int]($Seconds / 60), $Seconds % 60) }
    return ("{0}h{1}m" -f [int]($Seconds / 3600), [int](($Seconds % 3600) / 60))
}

function Write-Report {
    # v27: guard against early-exit before Initialize-ProjectPaths has run
    if (-not $script:ReportFile) { return }
    $endTimeStr = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $endEpoch   = [int][double]::Parse((Get-Date -UFormat %s))
    $duration   = $endEpoch - $startEpoch
    $hours      = [int]($duration / 3600)
    $minutes    = [int](($duration % 3600) / 60)
    $events     = ($reportEvents -join "`n")
    $batchStart = $script:BatchStart

    $content = @"
# ink-auto 运行报告

## 基本信息

| 项目 | 值 |
|------|-----|
| 开始时间 | $startTimeStr |
| 结束时间 | $endTimeStr |
| 总耗时 | ${hours}小时${minutes}分钟 |
| 平台 | $Platform |
| 计划章数 | $N |
| 完成章数 | $($stats.Completed) |
| 起始章节 | 第${batchStart}章 |
| 终止原因 | $(if ($stats.ExitReason) { $stats.ExitReason } else { '正常完成' }) |

## 统计摘要

| 操作 | 次数 |
|------|------|
| 写作 | $($stats.Completed) 章 |
| 质量审查 | $($stats.ReviewCount) 次 |
| 自动修复 | $($stats.FixCount) 次 |
| 数据审计 | $($stats.AuditCount) 次 |
| 宏观审查 | $($stats.MacroCount) 次 |
| 记忆压缩提示 | $($stats.CompressNotifyCount) 次 |
| 自动规划 | $($stats.PlanCount) 卷 |

## 执行时间线

| 时间 | 状态 | 事件 | 详情 |
|------|------|------|------|
$events

## 日志目录

``$($script:LogDir)``

## 报告与产出

- 审查报告: ``审查报告/`` 目录
- 审计报告: ``.ink/audit_reports/`` 目录
- 宏观审查: ``审查报告/`` 目录
- 章节文件: ``正文/`` 目录
"@

    $content | Set-Content -Path $script:ReportFile -Encoding UTF8
    Write-Host "📄 运行报告: $script:ReportFile"
}

# ============================================================
# state 查询辅助
# ============================================================

function Get-CurrentChapter {
    try {
        $raw = Invoke-InkCli state get-progress 2>$null
        if (-not $raw) { return 0 }
        $d = $raw | ConvertFrom-Json
        return [int] $d.data.current_chapter
    } catch { return 0 }
}

function Get-VolumeForChapter {
    param([int] $Ch)
    try {
        $state = Get-Content (Join-Path $ProjectRoot '.ink/state.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        foreach ($v in @($state.project_info.volumes)) {
            $r = $v.chapter_range
            if ($r -match '^(\d+)-(\d+)$') {
                $lo = [int] $Matches[1]
                $hi = [int] $Matches[2]
                if ($Ch -ge $lo -and $Ch -le $hi) {
                    if ($v.PSObject.Properties.Match('volume_id').Count) { return $v.volume_id }
                    return $v.id
                }
            }
        }
    } catch {}
    return ''
}

function Get-FinalChapter {
    try {
        $state = Get-Content (Join-Path $ProjectRoot '.ink/state.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        $vols = @($state.project_info.volumes)
        if ($vols.Count -eq 0) { return 0 }
        $r = $vols[-1].chapter_range
        if ($r -match '^(\d+)-(\d+)$') { return [int] $Matches[2] }
    } catch {}
    return 0
}

function Get-TotalVolumes {
    try {
        $state = Get-Content (Join-Path $ProjectRoot '.ink/state.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        return @($state.project_info.volumes).Count
    } catch { return 0 }
}

function Test-ProjectCompleted {
    try {
        $state = Get-Content (Join-Path $ProjectRoot '.ink/state.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($state.progress.is_completed) { return 'completed' }
        $final = Get-FinalChapter
        if ($final -gt 0 -and [int] $state.progress.current_chapter -ge $final) { return 'completed' }
        return 'in_progress'
    } catch { return 'unknown' }
}

# ============================================================
# Preflight（v27: PROJECT_ROOT 为空时跳过，状态分发块会在 Invoke-CliProcess 就绪后处理）
# ============================================================

if ($ProjectRoot) {
    try {
        Invoke-InkCli preflight *>$null
        if ($LASTEXITCODE -ne 0) { throw '' }
    } catch {
        Write-Host '❌ 预检失败，请检查项目状态'
        exit 1
    }

    $ProjectStatus = Test-ProjectCompleted
    if ($ProjectStatus -eq 'completed') {
        Write-Host '🎉 本书已完结！所有卷章均已写完。'
        Write-Host '   如需继续创作，请手动修改 .ink/state.json 中的 is_completed 字段。'
        exit 0
    }

    $CurrentCh = Get-CurrentChapter
    $script:BatchStart = $CurrentCh + 1
    $BatchEnd = $CurrentCh + $N

    Report-Event '🚀' '批量写作启动' "计划${N}章，从第${script:BatchStart}章到第${BatchEnd}章"
    Write-Host "🔍 正在扫描第${script:BatchStart}章到第${BatchEnd}章的大纲覆盖..."

    try {
        Invoke-InkCli check-outline --chapter $script:BatchStart --batch-end $BatchEnd *>$null
        if ($LASTEXITCODE -ne 0) { throw '' }
        Write-Host '✅ 大纲覆盖完整'
        Report-Event '✅' '大纲预检' '全部覆盖'
    } catch {
        Write-Host ''
        Write-Host '⚠️  部分章节大纲缺失，ink-auto 将在写作前自动生成'
        Write-Host '    如需手动规划，请按 Ctrl+C 中止后执行 /ink-plan'
        Write-Host ''
        Report-Event '⚠️' '大纲预检' '部分章节大纲缺失，将按需自动生成'
        Start-Sleep -Seconds 5
    }
}  # end: if ($ProjectRoot) (v27 preflight/完结/大纲预检守卫)

# ============================================================
# CLI 进程执行（Windows 平台探测命令的具体参数对齐 .sh）
# ============================================================

$script:Interrupted = $false

function Invoke-CliProcess {
    param([string] $Prompt, [string] $LogFile)

    $exitCode = 0
    try {
        switch ($Platform) {
            'claude' {
                $output = & claude -p $Prompt `
                    --permission-mode bypassPermissions `
                    --no-session-persistence 2>&1
                $exitCode = $LASTEXITCODE
            }
            'gemini' {
                $output = $Prompt | & gemini --yolo 2>&1
                $exitCode = $LASTEXITCODE
            }
            'codex' {
                $output = & codex --approval-mode full-auto $Prompt 2>&1
                $exitCode = $LASTEXITCODE
            }
        }
        $output | ForEach-Object { $_ } | Tee-Object -FilePath $LogFile -Append | Out-Host
    } catch {
        Write-Host "CLI 异常：$_"
        $exitCode = 1
    }

    # US-012 defensive 日志：CLI 子进程非零退出时显式打到 stderr
    # （与 ink-auto.sh:run_cli_process 的 LLM_EXIT 模式对等；成功时静默）
    if ($exitCode -ne 0) {
        [Console]::Error.WriteLine("[ink-auto] llm_exit=$exitCode tool=$Platform log=$LogFile")
    }

    return $exitCode
}

# ═══════════════════════════════════════════
# v27 状态分发：未初始化项目时自动 init
# ═══════════════════════════════════════════

$INK_AUTO_INIT_ENABLED                    = if ($env:INK_AUTO_INIT_ENABLED)                    { $env:INK_AUTO_INIT_ENABLED }                    else { "1" }
$INK_AUTO_BLUEPRINT_ENABLED               = if ($env:INK_AUTO_BLUEPRINT_ENABLED)               { $env:INK_AUTO_BLUEPRINT_ENABLED }               else { "1" }
$INK_AUTO_INTERACTIVE_BOOTSTRAP_ENABLED   = if ($env:INK_AUTO_INTERACTIVE_BOOTSTRAP_ENABLED)   { $env:INK_AUTO_INTERACTIVE_BOOTSTRAP_ENABLED }   else { "1" }

if (-not $ProjectRoot) {
    if ($INK_AUTO_INIT_ENABLED -ne "1") {
        Write-Host "❌ 未找到 .ink/state.json，请在小说项目目录下运行"
        Write-Host "   提示：当前目录无已初始化项目（自动初始化已被 INK_AUTO_INIT_ENABLED=0 禁用）"
        Write-Host "   解决：移除 INK_AUTO_INIT_ENABLED=0 重新运行，或切换到已初始化的项目目录"
        exit 1
    }

    $ProjectRoot = $PWD.Path
    Write-Host "════════════════════════════════════════════════════"
    Write-Host "  ink-auto 终极自动化模式：未检测到已初始化项目"
    Write-Host "  当前目录：$ProjectRoot"
    Write-Host "════════════════════════════════════════════════════"

    # 扫描蓝本
    $BlueprintPath = ""
    if ($INK_AUTO_BLUEPRINT_ENABLED -eq "1") {
        $scanScript = @"
from pathlib import Path
from ink_writer.core.auto.blueprint_scanner import find_blueprint
result = find_blueprint(Path(r'$ProjectRoot'))
print(str(result) if result else '')
"@
        $BlueprintPath = & $PyLauncher[0] @($PyLauncher[1..($PyLauncher.Count - 1)]) -X utf8 -c $scanScript 2>$null
        if (-not $BlueprintPath) { $BlueprintPath = "" }
    }

    if ($BlueprintPath) {
        Write-Host "📄 找到蓝本：$BlueprintPath"
    } else {
        if ($INK_AUTO_INTERACTIVE_BOOTSTRAP_ENABLED -ne "1") {
            Write-Host "❌ 未找到蓝本 .md，且 INK_AUTO_INTERACTIVE_BOOTSTRAP_ENABLED=0"
            Write-Host "   请先放置蓝本（参考 $ScriptDir/../templates/blueprint-template.md）"
            exit 1
        }
        $BlueprintPath = Join-Path $ProjectRoot ".ink-auto-blueprint.md"
        Write-Host "📋 未找到蓝本，启动 7 题交互式 bootstrap..."
        $psExecutable = (Get-Process -Id $PID).Path
        & $psExecutable -NoProfile -ExecutionPolicy Bypass -File "$ScriptDir/interactive_bootstrap.ps1" $BlueprintPath
        if ($LASTEXITCODE -ne 0) {
            Write-Host "❌ 交互式 bootstrap 失败或被中断"
            exit 1
        }
    }

    # 转换蓝本 → quick draft
    $DraftPath = Join-Path $ProjectRoot ".ink-auto-quick-draft.json"
    & $PyLauncher[0] @($PyLauncher[1..($PyLauncher.Count - 1)]) -X utf8 -m ink_writer.core.auto.blueprint_to_quick_draft --input $BlueprintPath --output $DraftPath
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ 蓝本校验失败（$BlueprintPath），请修正后重跑 /ink-auto"
        exit 1
    }

    # 调用 ink-init Quick 模式（CLI 子进程）
    $InitLog = Join-Path $ProjectRoot ("ink-auto-init-{0}.log" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
    $q = [char] 0x22
    $InitPrompt = "使用 Skill 工具加载 ${q}ink-init${q}。模式：--quick --blueprint $BlueprintPath。draft.json 路径: $DraftPath。项目目录: $ProjectRoot（**强制在该目录原地初始化，不要根据书名生成子目录**；最终 .ink/state.json 必须落在 $ProjectRoot/.ink/state.json）。禁止提问，全程自主执行，最终输出 INK_INIT_DONE 或 INK_INIT_FAILED。"
    Write-Host "⚙️  启动自动初始化（CLI 子进程，约 5-10 分钟）..."
    $initRc = Invoke-CliProcess -Prompt $InitPrompt -LogFile $InitLog
    if ($initRc -ne 0) {
        Write-Host "❌ 自动初始化失败，日志：$InitLog"
        Write-Host "   蓝本保留：$BlueprintPath"
        exit 1
    }
    Write-Host "✅ 初始化完成"

    # 重新解析项目根
    $ProjectRoot = Find-ProjectRoot
    if (-not $ProjectRoot) {
        Write-Host "❌ init 后仍未找到 .ink/state.json，可能初始化未完整落盘"
        Write-Host "   日志：$InitLog"
        exit 1
    }

    # 此时 PROJECT_ROOT 已就绪，初始化路径相关变量
    Initialize-ProjectPaths

    # 重新执行预检 / 完结检测 / 大纲预检（之前因 ProjectRoot 为空已跳过）
    try {
        Invoke-InkCli preflight *>$null
        if ($LASTEXITCODE -ne 0) { throw '' }
    } catch {
        Write-Host '❌ 预检失败，请检查项目状态'
        exit 1
    }

    $ProjectStatus2 = Test-ProjectCompleted
    if ($ProjectStatus2 -eq 'completed') {
        Write-Host '🎉 本书已完结！所有卷章均已写完。'
        exit 0
    }

    $CurrentCh2 = Get-CurrentChapter
    $script:BatchStart = $CurrentCh2 + 1
    $BatchEnd = $CurrentCh2 + $N

    Report-Event '🚀' '批量写作启动（自动初始化后）' "计划${N}章，从第${script:BatchStart}章到第${BatchEnd}章"
    Write-Host "🔍 正在扫描第${script:BatchStart}章到第${BatchEnd}章的大纲覆盖..."

    try {
        Invoke-InkCli check-outline --chapter $script:BatchStart --batch-end $BatchEnd *>$null
        if ($LASTEXITCODE -ne 0) { throw '' }
        Write-Host '✅ 大纲覆盖完整'
        Report-Event '✅' '大纲预检' '全部覆盖'
    } catch {
        Write-Host ''
        Write-Host '⚠️  部分章节大纲缺失，ink-auto 将在写作前自动生成'
        Write-Host ''
        Report-Event '⚠️' '大纲预检' '部分章节大纲缺失，将按需自动生成'
        Start-Sleep -Seconds 5
    }
}

function Invoke-Chapter {
    param([int] $Ch)
    $padded = '{0:D4}' -f $Ch
    $logFile = Join-Path $script:LogDir ("ch${padded}-{0}.log" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
    $q = [char] 0x22
    $prompt = "使用 Skill 工具加载 ${q}ink-write${q} 并完整执行所有步骤（Step 0 到 Step 6）。项目目录: ${ProjectRoot}。禁止省略任何步骤，禁止提问，全程自主执行。完成后输出 INK_DONE。失败则输出 INK_FAILED。"
    $rc = Invoke-CliProcess $prompt $logFile
    if ($rc -ne 0) {
        Write-Host '⚠️  CLI 进程异常退出'
        Write-Host "    日志文件：$logFile"
        return $false
    }
    return $true
}

function Invoke-ResumeChapter {
    param([int] $Ch)
    $padded = '{0:D4}' -f $Ch
    $logFile = Join-Path $script:LogDir ("ch${padded}-retry-{0}.log" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
    $q = [char] 0x22
    $prompt = "使用 Skill 工具加载 ${q}ink-resume${q}，恢复第${Ch}章的写作并完成所有剩余步骤。项目目录: ${ProjectRoot}。禁止提问，全程自主执行。完成后输出 INK_DONE。"
    $rc = Invoke-CliProcess $prompt $logFile
    if ($rc -ne 0) {
        Write-Host '⚠️  重试进程异常退出'
        Write-Host "    日志文件：$logFile"
        return $false
    }
    return $true
}

function Test-Chapter {
    param([int] $Ch)
    $padded = '{0:D4}' -f $Ch
    $glob = Join-Path $ProjectRoot "正文/第${padded}章*.md"
    $file = Get-ChildItem -Path $glob -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $file -or $file.Length -eq 0) { return $false }
    $chars = (Get-Content $file.FullName -Raw -Encoding UTF8).Length
    if ($chars -lt 2200) { return $false }
    # US-004：字数硬上限对称阻断（MaxWordsHard 由 preferences.json 推导，默认 5000）
    if ($chars -gt $script:MaxWordsHard) { return $false }
    $cur = Get-CurrentChapter
    if ($cur -lt $Ch) { return $false }
    $summary = Join-Path $ProjectRoot ".ink/summaries/ch${padded}.md"
    if (-not (Test-Path $summary -PathType Leaf)) { return $false }
    return $true
}

function Get-ChapterWordcount {
    param([int] $Ch)
    $padded = '{0:D4}' -f $Ch
    $glob = Join-Path $ProjectRoot "正文/第${padded}章*.md"
    $file = Get-ChildItem -Path $glob -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $file) { return 0 }
    return (Get-Content $file.FullName -Raw -Encoding UTF8).Length
}

# ============================================================
# 自动大纲生成
# ============================================================

function Invoke-AutoGenerateOutline {
    param([int] $Ch)
    $vol = Get-VolumeForChapter -Ch $Ch
    if (-not $vol) {
        $totalVols = Get-TotalVolumes
        if ($totalVols -gt 0) {
            Write-Host "    🎉 第${Ch}章已超出总纲定义的${totalVols}卷范围，全书完结"
            Report-Event '🎉' '全书完结' "无需为第${Ch}章生成大纲"
            return $false
        }
        Write-Host "    ❌ 无法确定第${Ch}章所属卷号，中止"
        return $false
    }
    if ($stats.PlannedVolumes -like "*:${vol}:*") {
        Write-Host "    ❌ 第${vol}卷大纲已尝试生成但仍缺失，中止"
        return $false
    }
    $stats.PlannedVolumes = "$($stats.PlannedVolumes)${vol}:"

    Write-Host "    📋 第${vol}卷大纲缺失，自动启动 ink-plan..."
    Report-Event '📋' '自动大纲启动' "第${vol}卷（因第${Ch}章需要）"
    $logFile = Join-Path $script:LogDir ("plan-vol${vol}-{0}.log" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
    $q = [char] 0x22
    $prompt = "使用 Skill 工具加载 ${q}ink-plan${q}。为第${vol}卷生成完整详细大纲（节拍表+时间线+章纲）。项目目录: ${ProjectRoot}。禁止提问，自动选择第${vol}卷，全程自主执行。完成后输出 INK_PLAN_DONE。"
    Invoke-CliProcess $prompt $logFile | Out-Null
    $stats.PlanCount++
    Start-Sleep -Seconds $CheckpointCooldown

    try {
        Invoke-InkCli check-outline --chapter $Ch *>$null
        if ($LASTEXITCODE -ne 0) { throw '' }
        Write-Host "    ✅ 第${vol}卷大纲生成成功"
        Report-Event '✅' '自动大纲完成' "第${vol}卷"
        return $true
    } catch {
        Write-Host "    ❌ 第${vol}卷大纲生成失败，中止批量写作"
        Report-Event '❌' '自动大纲失败' "第${vol}卷"
        return $false
    }
}

# ============================================================
# 并发模式：委托 Python asyncio 编排器
# ============================================================

if ($Parallel -gt 1) {
    Write-Host '═══════════════════════════════════════'
    Write-Host "  ink-auto | 写 $N 章 | 并发 $Parallel | $Platform"
    Write-Host "  项目: $ProjectRoot"
    Write-Host '  检查点: 每批次完成后统一运行'
    Write-Host "  日志: $script:LogDir"
    Write-Host '═══════════════════════════════════════'

    $pythonPathPrefix = "$RepoRoot;$ScriptsDir"
    if ($env:PYTHONPATH) {
        $env:PYTHONPATH = "$pythonPathPrefix;$($env:PYTHONPATH)"
    } else {
        $env:PYTHONPATH = $pythonPathPrefix
    }

    $pyTemplate = @'
import asyncio, json, sys, time
from pathlib import Path
from ink_writer.parallel.pipeline_manager import PipelineManager, PipelineConfig
config = PipelineConfig(
    project_root=Path(r'__PROJECT_ROOT__'),
    plugin_root=Path(r'__PLUGIN_ROOT__'),
    parallel=__PARALLEL__,
    cooldown=__COOLDOWN__,
    checkpoint_cooldown=__CHECKPOINT_COOLDOWN__,
    platform='__PLATFORM__',
)
mgr = PipelineManager(config)
report = asyncio.run(mgr.run(total_chapters=__N__))
result = report.to_dict()
print()
print('=' * 39)
print('  ink-auto 并发完成报告')
print('=' * 39)
print(f'  并发度: {result["parallel"]}')
print(f'  完成: {result["completed"]} 章 | 失败: {result["failed"]} 章')
print(f'  墙钟时间: {result["wall_time_s"]}s | 串行等效: {result["serial_total_s"]}s')
print(f'  加速比: {result["speedup"]}x')
print('=' * 39)
report_path = Path(r'__REPORT_DIR__') / f'auto-parallel-{time.strftime("%Y%m%d-%H%M%S")}.json'
report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(f'  报告: {report_path}')
sys.exit(1 if result['failed'] > 0 else 0)
'@
    $pyScript = $pyTemplate `
        -replace '__PROJECT_ROOT__', $ProjectRoot `
        -replace '__PLUGIN_ROOT__', $PluginRoot `
        -replace '__REPORT_DIR__', $script:ReportDir `
        -replace '__PARALLEL__', $Parallel `
        -replace '__COOLDOWN__', $Cooldown `
        -replace '__CHECKPOINT_COOLDOWN__', $CheckpointCooldown `
        -replace '__PLATFORM__', $Platform `
        -replace '__N__', $N
    Invoke-InkPy '-c' $pyScript
    exit $LASTEXITCODE
}

# ============================================================
# 串行主循环
# ============================================================

Write-Host '═══════════════════════════════════════'
Write-Host "  ink-auto | 写 $N 章 | $Platform"
Write-Host "  项目: $ProjectRoot"
Write-Host '  检查点: 5章 review+fix / 10章 audit quick / 20章 audit standard+Tier2 / 50章 Tier2+drift / 200章 Tier3'
Write-Host "  日志: $script:LogDir"
Write-Host "  报告: $script:ReportFile"
Write-Host '═══════════════════════════════════════'

function Invoke-Checkpoint {
    param([int] $Ch)
    try {
        $cpJson = Invoke-InkCli checkpoint-level --chapter $Ch 2>$null
        if (-not $cpJson) { return }
        $cp = $cpJson | ConvertFrom-Json
        if (-not $cp.review) { return }
    } catch { return }

    Write-Host ''
    Write-Host "───────── 📋 检查点：第${Ch}章 ─────────"
    Report-Event '📋' '检查点触发' "第${Ch}章"

    $reviewStart = $cp.review_range[0]
    $reviewEnd   = $cp.review_range[1]

    $q = [char] 0x22
    if ($cp.audit) {
        $logFile = Join-Path $script:LogDir ("audit-$($cp.audit)-{0}.log" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
        $prompt = "使用 Skill 工具加载 ${q}ink-audit${q}。审计深度：$($cp.audit)。项目目录: ${ProjectRoot}。全程自主执行，禁止提问。完成后输出 INK_AUDIT_DONE。"
        Invoke-CliProcess $prompt $logFile | Out-Null
        $stats.AuditCount++
        Start-Sleep -Seconds $CheckpointCooldown
    }

    if ($cp.macro) {
        $logFile = Join-Path $script:LogDir ("macro-$($cp.macro)-{0}.log" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
        $prompt = "使用 Skill 工具加载 ${q}ink-macro-review${q}。审查层级：$($cp.macro)。项目目录: ${ProjectRoot}。全程自主执行，禁止提问。完成后输出 INK_MACRO_DONE。"
        Invoke-CliProcess $prompt $logFile | Out-Null
        $stats.MacroCount++
        Start-Sleep -Seconds $CheckpointCooldown
    }

    # 审查 + 修复（始终执行）
    $logFile = Join-Path $script:LogDir ("review-ch${reviewStart}-${reviewEnd}-{0}.log" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
    $prompt = "使用 Skill 工具加载 ${q}ink-review${q}。审查范围：第${reviewStart}章到第${reviewEnd}章。审查深度：Core。项目目录: ${ProjectRoot}。全程自主执行，禁止提问。发现 critical 或 high 问题时选择选项 A（立即修复），修复后自动重审验证。完成后输出 INK_REVIEW_DONE。"
    Invoke-CliProcess $prompt $logFile | Out-Null
    $stats.ReviewCount++
    Start-Sleep -Seconds $CheckpointCooldown

    Write-Host '───────── 检查点完成 ─────────'
    Write-Host ''
}

for ($i = 1; $i -le $N; $i++) {
    if ($script:Interrupted) { break }

    $current = Get-CurrentChapter
    $nextCh  = $current + 1

    # 大纲检查
    try {
        Invoke-InkCli check-outline --chapter $nextCh *>$null
        if ($LASTEXITCODE -ne 0) { throw '' }
    } catch {
        Write-Host "[$i/$N] 📋 第${nextCh}章大纲缺失，尝试自动生成..."
        if (-not (Invoke-AutoGenerateOutline -Ch $nextCh)) {
            Write-Host ''
            Write-Host '═══════════════════════════════════════'
            Write-Host '  ❌ 大纲生成失败，批量写作中止'
            Write-Host '═══════════════════════════════════════'
            $stats.ExitReason = "第${nextCh}章大纲生成失败"
            Report-Event '❌' '批量写作中止' "大纲生成失败"
            Write-Report
            exit 1
        }
    }

    # 清理 workflow
    try { Invoke-InkCli workflow clear *>$null } catch {}

    Write-Host ''
    Write-Host "[$i/$N] 第${nextCh}章 开始写作..."
    Write-Host '───────────────────────────────────'
    Report-Event '📝' '写作启动' "第${nextCh}章 [$i/$N]"

    $ok = Invoke-Chapter -Ch $nextCh
    Start-Sleep -Seconds $Cooldown

    if (-not $ok) {
        Write-Host "[$i/$N] ⚠️  第${nextCh}章 CLI 进程异常，尝试验证产出..."
    }

    if (Test-Chapter -Ch $nextCh) {
        $wc = Get-ChapterWordcount -Ch $nextCh
        $stats.Completed++
        Write-Host "[$i/$N] ✅ 第${nextCh}章完成 | ${wc}字"
        Report-Event '✅' '写作完成' "第${nextCh}章 ${wc}字"

        Invoke-Checkpoint -Ch $nextCh

        $finalCh = Get-FinalChapter
        if ($finalCh -gt 0 -and $nextCh -ge $finalCh) {
            Write-Host ''
            Write-Host '═══════════════════════════════════════'
            Write-Host "  🎉 全书完结！第${nextCh}章是最终章。"
            Write-Host '═══════════════════════════════════════'
            try { Invoke-InkCli update-state --mark-completed *>$null } catch {}
            $stats.ExitReason = '全书完结'
            Report-Event '🎉' '全书完结' "第${nextCh}章为最终章"
            Write-Report
            exit 0
        }
    } else {
        # US-004：根据失败原因分流
        #   - 字数超限 (> MaxWordsHard) → 精简循环最多 ShrinkMaxRounds（3 轮）
        #   - 其它失败（< 2200 / 文件缺失 / 摘要缺失）→ 保持原 1 轮补写，零回归
        $wcFail = Get-ChapterWordcount -Ch $nextCh
        if ($wcFail -gt $script:MaxWordsHard) {
            $maxRetries = $script:ShrinkMaxRounds
            $failReason = "字数超限(${wcFail}>${script:MaxWordsHard})"
        } else {
            $maxRetries = 1
            $failReason = '验证失败'
        }
        Write-Host "[$i/$N] ⚠️  ${failReason}，启动重试（最多 ${maxRetries} 轮）..."
        Report-Event '⚠️' '写作验证失败' "第${nextCh}章 ${failReason}，最多 ${maxRetries} 轮"

        $retryRound = 0
        $retryVerified = $false
        while ($retryRound -lt $maxRetries) {
            $retryRound++
            Write-Host "[$i/$N] 🔄 第${retryRound}/${maxRetries}轮重试..."
            $retryOk = Invoke-ResumeChapter -Ch $nextCh
            Start-Sleep -Seconds $Cooldown
            if ($retryOk -and (Test-Chapter -Ch $nextCh)) {
                $retryVerified = $true
                break
            }
        }

        if ($retryVerified) {
            $wc = Get-ChapterWordcount -Ch $nextCh
            $stats.Completed++
            Write-Host "[$i/$N] ✅ 第${nextCh}章完成（重试成功）| ${wc}字"
            Report-Event '✅' '重试成功' "第${nextCh}章 ${wc}字（${retryRound}轮）"
            Invoke-Checkpoint -Ch $nextCh
        } else {
            Write-Host ''
            Write-Host '═══════════════════════════════════════'
            Write-Host "  ❌ 第${nextCh}章写作失败，批量写作中止"
            Write-Host '═══════════════════════════════════════'
            $stats.ExitReason = "第${nextCh}章写作失败（${failReason}，${maxRetries}轮重试仍未通过）"
            Report-Event '❌' '批量写作中止' "第${nextCh}章 ${failReason}"
            Write-Report
            exit 1
        }
    }
}

Report-Event '🎉' '批量写作完成' "共$($stats.Completed)章"
Write-Host ''
Write-Host '═══════════════════════════════════════'
Write-Host '  ink-auto 完成报告'
Write-Host '═══════════════════════════════════════'
Write-Host "  生成章节：第${script:BatchStart}-$(Get-CurrentChapter)章（$($stats.Completed)/$N 成功）"
Write-Host "  📂 日志：$script:LogDir"
Write-Host '═══════════════════════════════════════'
Write-Report
