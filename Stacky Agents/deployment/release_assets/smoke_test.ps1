#Requires -Version 5.1
<#
.SYNOPSIS
    Smoke test post-instalacion de Stacky Agents.
.DESCRIPTION
    Arranca el backend congelado en un puerto libre, valida /api/health,
    /api/projects y que la UI compilada se sirva desde /.
#>

[CmdletBinding()]
param(
    [int]$TimeoutSeconds = 45
)

$ErrorActionPreference = "Stop"
$STACKY_ROOT = $PSScriptRoot

function Write-Step { param([string]$Message) Write-Host "`n>> $Message" -ForegroundColor Cyan }
function Write-OK { param([string]$Message) Write-Host "   [OK] $Message" -ForegroundColor Green }

function Get-FreeTcpPort {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Parse("127.0.0.1"), 0)
    $listener.Start()
    try {
        return [int]$listener.LocalEndpoint.Port
    } finally {
        $listener.Stop()
    }
}

function Wait-ForHealth {
    param(
        [string]$BaseUrl,
        [System.Diagnostics.Process]$Process,
        [int]$TimeoutSeconds
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $lastError = $null
    while ((Get-Date) -lt $deadline) {
        if ($Process.HasExited) {
            throw "stacky-backend.exe termino antes de responder health. ExitCode=$($Process.ExitCode)"
        }
        try {
            $health = Invoke-RestMethod -Uri "$BaseUrl/api/health" -TimeoutSec 5
            if ($health.ok -eq $true) {
                return
            }
        } catch {
            $lastError = $_.Exception.Message
            Start-Sleep -Milliseconds 500
        }
    }
    throw "El backend no quedo healthy en $TimeoutSeconds segundos. Ultimo error: $lastError"
}

Write-Step "Smoke test del release instalado"

$backendExe = Join-Path $STACKY_ROOT "backend\stacky-backend.exe"
$frontendIndex = Join-Path $STACKY_ROOT "frontend\dist\index.html"
if (-not (Test-Path $backendExe)) {
    throw "No existe $backendExe"
}
if (-not (Test-Path $frontendIndex)) {
    throw "No existe $frontendIndex"
}

$port = Get-FreeTcpPort
$baseUrl = "http://127.0.0.1:$port"
$smokeData = Join-Path $STACKY_ROOT "data\smoke"
$smokeProjects = Join-Path $STACKY_ROOT "projects\smoke"
New-Item -ItemType Directory -Path $smokeData, $smokeProjects -Force | Out-Null

$savedEnv = @{
    PORT = $env:PORT
    DATABASE_URL = $env:DATABASE_URL
    LLM_BACKEND = $env:LLM_BACKEND
    STACKY_APP_ROOT = $env:STACKY_APP_ROOT
    STACKY_DATA_DIR = $env:STACKY_DATA_DIR
    STACKY_PROJECTS_DIR = $env:STACKY_PROJECTS_DIR
    STACKY_FRONTEND_DIST = $env:STACKY_FRONTEND_DIST
    STACKY_REAPER_ENABLED = $env:STACKY_REAPER_ENABLED
    STACKY_MANIFEST_WATCHER_ENABLED = $env:STACKY_MANIFEST_WATCHER_ENABLED
    STACKY_OUTPUT_WATCHER_ENABLED = $env:STACKY_OUTPUT_WATCHER_ENABLED
    STACKY_RECOVERY_ON_STARTUP = $env:STACKY_RECOVERY_ON_STARTUP
}

$process = $null
try {
    $env:PORT = [string]$port
    $dbPath = (Join-Path $smokeData "stacky_agents.db").Replace("\", "/")
    $env:DATABASE_URL = "sqlite:///$dbPath"
    $env:LLM_BACKEND = "mock"
    $env:STACKY_APP_ROOT = $STACKY_ROOT
    $env:STACKY_DATA_DIR = $smokeData
    $env:STACKY_PROJECTS_DIR = $smokeProjects
    $env:STACKY_FRONTEND_DIST = Join-Path $STACKY_ROOT "frontend\dist"
    $env:STACKY_REAPER_ENABLED = "false"
    $env:STACKY_MANIFEST_WATCHER_ENABLED = "false"
    $env:STACKY_OUTPUT_WATCHER_ENABLED = "false"
    $env:STACKY_RECOVERY_ON_STARTUP = "false"

    $process = Start-Process -FilePath $backendExe -WorkingDirectory $STACKY_ROOT -PassThru -WindowStyle Hidden
    Wait-ForHealth -BaseUrl $baseUrl -Process $process -TimeoutSeconds $TimeoutSeconds
    Write-OK "/api/health"

    $projects = Invoke-RestMethod -Uri "$baseUrl/api/projects" -TimeoutSec 5
    if ($projects.ok -ne $true -or $null -eq $projects.projects) {
        throw "/api/projects devolvio una respuesta inesperada"
    }
    Write-OK "/api/projects"

    $html = Invoke-WebRequest -Uri "$baseUrl/" -TimeoutSec 5 -UseBasicParsing
    if ($html.StatusCode -ne 200 -or $html.Content -notmatch 'id="root"' -or $html.Content -notmatch "Stacky Agents") {
        throw "La UI compilada no se sirvio correctamente desde /"
    }
    Write-OK "frontend compilado servido desde /"
} finally {
    if ($process -and -not $process.HasExited) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    }
    foreach ($key in $savedEnv.Keys) {
        if ($null -eq $savedEnv[$key]) {
            Remove-Item "Env:\$key" -ErrorAction SilentlyContinue
        } else {
            Set-Item "Env:\$key" $savedEnv[$key]
        }
    }
}

Write-Host ""
Write-Host "Smoke test OK." -ForegroundColor Green
