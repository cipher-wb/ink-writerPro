$ErrorActionPreference = "Stop"
$root = if ($Env:INK_PROJECT_ROOT) { $Env:INK_PROJECT_ROOT } else { (Get-Location).Path }
function Find-PythonLauncher {
    $candidates = @('py -3', 'python3', 'python') # c8-ok: detector primitive
    foreach ($cand in $candidates) {
        $exe = ($cand -split ' ')[0]
        if (Get-Command $exe -ErrorAction SilentlyContinue) { return $cand }
    }
    return 'python'
}
$script:PythonLauncher = if ($Env:PYTHON_LAUNCHER) { $Env:PYTHON_LAUNCHER } else { Find-PythonLauncher }
function Invoke-Python {
    param([string[]]$PythonArgs)
    $parts = $script:PythonLauncher -split ' '
    $exe = $parts[0]
    $preArgs = @()
    if ($parts.Length -gt 1) { $preArgs = $parts[1..($parts.Length - 1)] }
    & $exe @preArgs @PythonArgs
}
Invoke-Python (@('-m', 'ink_writer.debug.cli', '--project-root', $root, 'report') + $args)
exit $LASTEXITCODE
