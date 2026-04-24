# start.ps1 — 启动 ink-writer Qdrant 单机实例（Windows PowerShell 5.1 兼容）。
#
# 行为：
#   1. docker compose up -d 启动 qdrant/qdrant:v1.12.4（端口 6333 REST + 6334 gRPC）
#   2. 轮询 http://127.0.0.1:6333/readyz 最多 30 秒
#   3. ready 打印 "Qdrant is ready." 退 0；超时退 1
#
# 用法：
#   .\scripts\qdrant\start.ps1
#
# 停止请用 .\scripts\qdrant\stop.ps1。

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ThisDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Push-Location $ThisDir
try {
    docker compose up -d
    if ($LASTEXITCODE -ne 0) {
        Write-Error "docker compose up 返回非 0，启动失败。"
        exit $LASTEXITCODE
    }

    $ReadyUrl = 'http://127.0.0.1:6333/readyz'
    $TimeoutSeconds = 30
    $elapsed = 0

    while ($elapsed -lt $TimeoutSeconds) {
        try {
            $resp = Invoke-WebRequest -Uri $ReadyUrl -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
            if ($resp.StatusCode -eq 200) {
                Write-Output 'Qdrant is ready.'
                exit 0
            }
        } catch {
            # 还没起来，继续轮询。
        }
        Start-Sleep -Seconds 1
        $elapsed = $elapsed + 1
    }

    Write-Error "Qdrant did not become ready within ${TimeoutSeconds}s (probed $ReadyUrl)."
    exit 1
} finally {
    Pop-Location
}
