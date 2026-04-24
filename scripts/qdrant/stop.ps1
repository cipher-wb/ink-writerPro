# stop.ps1 — 停止 ink-writer Qdrant 单机实例（Windows PowerShell 5.1 兼容）。
#
# 行为：docker compose down（容器删除，.\storage volume 保留用于下次启动）。

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ThisDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Push-Location $ThisDir
try {
    docker compose down
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
