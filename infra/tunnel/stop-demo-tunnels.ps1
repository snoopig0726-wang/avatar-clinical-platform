[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$runtimeDirectory = Join-Path $repositoryRoot '.local-data\tunnels'
$stateFile = Join-Path $runtimeDirectory 'state.json'

if (-not (Test-Path -LiteralPath $stateFile)) {
    Write-Host '没有检测到正在管理的演示隧道。'
    exit 0
}

$state = Get-Content -Raw -LiteralPath $stateFile -Encoding UTF8 | ConvertFrom-Json
foreach ($tunnel in $state.Processes) {
    $process = Get-Process -Id $tunnel.ProcessId -ErrorAction SilentlyContinue
    if ($process -and $process.ProcessName -eq 'cloudflared') {
        Stop-Process -Id $process.Id
        Write-Host "已停止 $($tunnel.Name) 隧道。"
    }
}

Remove-Item -LiteralPath $stateFile

Push-Location $repositoryRoot
try {
    & docker compose up -d backend worker scheduler
    if ($LASTEXITCODE -ne 0) {
        throw 'Docker Compose 未能恢复本地默认配置。'
    }
} finally {
    Pop-Location
}

Write-Host '本地 Docker 服务已恢复为 localhost 配置。'

