$ErrorActionPreference = "Stop"
$shimDir = Join-Path (Split-Path -Parent $PSScriptRoot) "_pyshim"
$root = if ($Env:INK_PROJECT_ROOT) { $Env:INK_PROJECT_ROOT } else { (Get-Location).Path }
$probe = & python3 -c "import ink_writer.debug.cli" 2>$null
if ($LASTEXITCODE -eq 0) {
    & python3 -m ink_writer.debug.cli --project-root $root status @args
} else {
    $env:PYTHONPATH = "$shimDir;$env:PYTHONPATH"
    & python3 -m ink_writer.debug.cli --project-root $root status @args
}
exit $LASTEXITCODE
