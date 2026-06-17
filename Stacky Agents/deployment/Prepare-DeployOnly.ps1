#Requires -Version 5.1
<#
.SYNOPSIS
    Re-empaqueta un DeployStackyAgents ya existente sin instalar nada.
.DESCRIPTION
    Este script no ejecuta npm, pip, winget ni recompila nada. Solo toma el
    contenido actual de DeployStackyAgents, opcionalmente hace backup, y genera
    un zip portable nuevo.
#>

[CmdletBinding()]
param(
    [string]$DeployRoot = "",
    [string]$Version = "",
    [switch]$NoBackup,
    [switch]$NoPause
)

$ErrorActionPreference = "Stop"

$deploymentDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$appRoot = Split-Path -Parent $deploymentDir
if (-not $DeployRoot) {
    $DeployRoot = Join-Path $appRoot "DeployStackyAgents"
}

$deployRootFull = [System.IO.Path]::GetFullPath($DeployRoot)
$zipStageRoot = Join-Path $deploymentDir ".zip-staging"

function Write-Step { param([string]$Message) Write-Host "`n>> $Message" -ForegroundColor Cyan }
function Write-OK { param([string]$Message) Write-Host "   [OK] $Message" -ForegroundColor Green }
function Write-Warn { param([string]$Message) Write-Host "   [WARN] $Message" -ForegroundColor Yellow }
function Assert-ChildPath {
    param(
        [Parameter(Mandatory = $true)][string]$Base,
        [Parameter(Mandatory = $true)][string]$Path
    )

    $baseFull = [System.IO.Path]::GetFullPath($Base).TrimEnd('\')
    $pathFull = [System.IO.Path]::GetFullPath($Path).TrimEnd('\')
    if ($pathFull -ne $baseFull -and -not $pathFull.StartsWith($baseFull + "\", [StringComparison]::OrdinalIgnoreCase)) {
        throw "Ruta fuera del destino esperado: $pathFull"
    }
}
function Remove-SafeDirectory {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$AllowedParent
    )

    if (-not (Test-Path $Path)) {
        return
    }
    Assert-ChildPath -Base $AllowedParent -Path $Path
    Remove-Item -LiteralPath $Path -Recurse -Force
}

function Get-DeployVersion {
    $candidates = @()
    $manifestPath = Join-Path $deployRootFull "release-manifest.json"
    if (Test-Path $manifestPath) {
        try {
            $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
            if ($manifest.version) { $candidates += [string]$manifest.version }
        } catch {}
    }
    $versionPath = Join-Path $deployRootFull "VERSION.txt"
    if (Test-Path $versionPath) {
        try { $candidates += (Get-Content -LiteralPath $versionPath -Raw).Trim() } catch {}
    }
    if ($Version) { return $Version }
    return ($candidates | Select-Object -First 1)
}

if (-not (Test-Path $deployRootFull)) {
    throw "No existe DeployStackyAgents en: $deployRootFull"
}

$releaseVersion = Get-DeployVersion
if (-not $releaseVersion) {
    $releaseVersion = "sin-version"
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$zipName = "DeployStackyAgents-{0}.zip" -f $releaseVersion
$zipPath = Join-Path $deployRootFull $zipName

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " Prepare-DeployOnly - Stacky Agents" -ForegroundColor Cyan
Write-Host " Deploy   : $deployRootFull" -ForegroundColor Gray
Write-Host " Version  : $releaseVersion" -ForegroundColor Gray
Write-Host "============================================================" -ForegroundColor Cyan

if (-not $NoBackup) {
    Write-Step "Respaldando deploy actual"
    $backupsRoot = Join-Path $deployRootFull "backups"
    New-Item -ItemType Directory -Path $backupsRoot -Force | Out-Null
    $backupDir = Join-Path $backupsRoot ("DeployStackyAgents-{0}-{1}" -f $releaseVersion, $timestamp)
    New-Item -ItemType Directory -Path $backupDir -Force | Out-Null

    foreach ($item in Get-ChildItem -LiteralPath $deployRootFull -Force) {
        if ($item.Name -eq "backups" -or $item.Name -eq $zipName) {
            continue
        }
        Copy-Item -LiteralPath $item.FullName -Destination (Join-Path $backupDir $item.Name) -Recurse -Force
    }
    Write-OK "Backup creado: $backupDir"
}

Write-Step "Generando zip portable"
Remove-SafeDirectory -Path $zipStageRoot -AllowedParent $deploymentDir
New-Item -ItemType Directory -Path $zipStageRoot -Force | Out-Null
$stageDeploy = Join-Path $zipStageRoot "DeployStackyAgents"
New-Item -ItemType Directory -Path $stageDeploy -Force | Out-Null

foreach ($item in Get-ChildItem -LiteralPath $deployRootFull -Force) {
    if ($item.Name -eq "backups" -or $item.Name -like "DeployStackyAgents-*.zip") {
        continue
    }
    Copy-Item -LiteralPath $item.FullName -Destination (Join-Path $stageDeploy $item.Name) -Recurse -Force
}

if (Test-Path $zipPath) {
    Assert-ChildPath -Base $deployRootFull -Path $zipPath
    Remove-Item -LiteralPath $zipPath -Force
}

Compress-Archive -Path $stageDeploy -DestinationPath $zipPath -CompressionLevel Optimal
Remove-SafeDirectory -Path $zipStageRoot -AllowedParent $deploymentDir

Write-OK "ZIP generado: $zipPath"
Write-Host ""
Write-Host "Deploy-only listo." -ForegroundColor Green
Write-Host "ZIP: $zipPath" -ForegroundColor Green
Write-Host ""

if (-not $NoPause) {
    Write-Host "Pulsa Enter para cerrar..."
    [void][Console]::ReadLine()
}
