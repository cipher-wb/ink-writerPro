$ErrorActionPreference = "Stop"
$root = if ($Env:INK_PROJECT_ROOT) { $Env:INK_PROJECT_ROOT } else { (Get-Location).Path }
& python3 -m ink_writer.debug.cli --project-root $root status @args
exit $LASTEXITCODE
