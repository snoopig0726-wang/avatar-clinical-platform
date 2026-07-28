[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^https://[a-zA-Z0-9.-]+(?::\d+)?$')]
    [string]$NetlifyOrigin
)

$ErrorActionPreference = 'Stop'

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$runtimeDirectory = Join-Path $repositoryRoot '.local-data\tunnels'
$stateFile = Join-Path $runtimeDirectory 'state.json'
$composeEnvironmentFile = Join-Path $runtimeDirectory 'compose.env'
$repositoryEnvironmentFile = Join-Path $repositoryRoot '.env'

if (Test-Path -LiteralPath $stateFile) {
    throw '检测到已有隧道状态。请先运行 infra\tunnel\stop-demo-tunnels.ps1。'
}

$cloudflaredCommand = Get-Command cloudflared -ErrorAction SilentlyContinue
$cloudflaredPath = if ($cloudflaredCommand) {
    $cloudflaredCommand.Source
} else {
    'C:\Program Files (x86)\cloudflared\cloudflared.exe'
}

if (-not (Test-Path -LiteralPath $cloudflaredPath)) {
    throw '未找到 cloudflared。请先安装：winget install --id Cloudflare.cloudflared --exact'
}

New-Item -ItemType Directory -Path $runtimeDirectory -Force | Out-Null

function Start-QuickTunnel {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$LocalUrl
    )

    $stdoutPath = Join-Path $runtimeDirectory "$Name.stdout.log"
    $stderrPath = Join-Path $runtimeDirectory "$Name.stderr.log"
    $process = Start-Process `
        -FilePath $cloudflaredPath `
        -ArgumentList @('tunnel', '--no-autoupdate', '--url', $LocalUrl) `
        -WindowStyle Hidden `
        -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath `
        -PassThru

    $deadline = (Get-Date).AddSeconds(40)
    $url = $null
    while ((Get-Date) -lt $deadline -and -not $process.HasExited) {
        Start-Sleep -Milliseconds 500
        $logText = @(
            if (Test-Path -LiteralPath $stdoutPath) {
                Get-Content -Raw -LiteralPath $stdoutPath -ErrorAction SilentlyContinue
            }
            if (Test-Path -LiteralPath $stderrPath) {
                Get-Content -Raw -LiteralPath $stderrPath -ErrorAction SilentlyContinue
            }
        ) -join "`n"
        $match = [regex]::Match(
            $logText,
            'https://(?!api\.)[a-z0-9]+(?:-[a-z0-9]+){2,}\.trycloudflare\.com',
            [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
        )
        if ($match.Success) {
            $url = $match.Value
            break
        }
    }

    if (-not $url) {
        if (-not $process.HasExited) {
            Stop-Process -Id $process.Id
        }
        throw "无法为 $Name 获取 Quick Tunnel 地址，请查看 $stderrPath。"
    }

    [pscustomobject]@{
        Name = $Name
        LocalUrl = $LocalUrl
        PublicUrl = $url
        ProcessId = $process.Id
    }
}

$startedTunnels = @()
try {
    $startedTunnels += Start-QuickTunnel -Name 'api' -LocalUrl 'http://localhost:8000'
    $startedTunnels += Start-QuickTunnel -Name 'storage' -LocalUrl 'http://localhost:9000'

    $apiTunnel = $startedTunnels | Where-Object Name -eq 'api'
    $storageTunnel = $startedTunnels | Where-Object Name -eq 'storage'
    $normalizedNetlifyOrigin = $NetlifyOrigin.TrimEnd('/')

    @(
        "FRONTEND_ORIGINS=http://localhost:5173,$normalizedNetlifyOrigin"
        "S3_PUBLIC_ENDPOINT=$($storageTunnel.PublicUrl)"
    ) | Set-Content -LiteralPath $composeEnvironmentFile -Encoding UTF8

    $state = [pscustomobject]@{
        StartedAt = (Get-Date).ToString('o')
        NetlifyOrigin = $normalizedNetlifyOrigin
        ApiUrl = $apiTunnel.PublicUrl
        StorageUrl = $storageTunnel.PublicUrl
        Processes = $startedTunnels
    }
    $state | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $stateFile -Encoding UTF8

    Push-Location $repositoryRoot
    try {
        $composeArguments = @('compose')
        if (Test-Path -LiteralPath $repositoryEnvironmentFile) {
            $composeArguments += @('--env-file', $repositoryEnvironmentFile)
        }
        $composeArguments += @(
            '--env-file',
            $composeEnvironmentFile,
            'up',
            '-d',
            'backend',
            'worker',
            'scheduler'
        )
        & docker @composeArguments
        if ($LASTEXITCODE -ne 0) {
            throw 'Docker Compose 未能应用隧道演示配置。'
        }
    } finally {
        Pop-Location
    }

    Write-Host ''
    Write-Host '免费演示隧道已启动。'
    Write-Host "Netlify 环境变量：VITE_API_BASE_URL=$($apiTunnel.PublicUrl)/api"
    Write-Host "API 健康检查：$($apiTunnel.PublicUrl)/api/health/ready"
    Write-Host "图片存储隧道：$($storageTunnel.PublicUrl)"
    Write-Host ''
    Write-Host '请在 Netlify 更新 VITE_API_BASE_URL 并触发一次重新部署。'
    Write-Host '演示结束后运行：.\infra\tunnel\stop-demo-tunnels.ps1'
} catch {
    foreach ($tunnel in $startedTunnels) {
        $process = Get-Process -Id $tunnel.ProcessId -ErrorAction SilentlyContinue
        if ($process -and $process.ProcessName -eq 'cloudflared') {
            Stop-Process -Id $process.Id
        }
    }
    throw
}

