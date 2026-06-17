#Requires -Version 5.1
<#
.SYNOPSIS
    Genera DeployStackyAgents versionado y listo para distribuir.
.DESCRIPTION
    Ejecuta el build de release, respalda el deploy anterior dentro de
    DeployStackyAgents\backups y crea un zip portable para entregar.
#>

[CmdletBinding()]
param(
    [string]$Version = "",
    [ValidateSet("major", "minor", "patch", "none")]
    [string]$Bump = "patch",
    [string]$DeployRoot = "",
    [string]$GitHubCopilotAgentsRepo = "",
    [switch]$SkipDependencyInstall,
    [switch]$SkipInstallerExe,
    [switch]$RequireInstallerExe,
    [switch]$SkipSmokeTest,
    [switch]$ExportConfig,
    [switch]$NoPause
)

$ErrorActionPreference = "Stop"

$deploymentDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$appRoot = Split-Path -Parent $deploymentDir
if (-not $DeployRoot) {
    $DeployRoot = Join-Path $appRoot "DeployStackyAgents"
}

$deployRootFull = [System.IO.Path]::GetFullPath($DeployRoot)
$backupsRoot = Join-Path $deployRootFull "backups"
$tempOut = Join-Path $deploymentDir ".prepare-out"
$zipStageRoot = Join-Path $deploymentDir ".zip-staging"
$buildRelease = Join-Path $deploymentDir "build_release.ps1"
$installDependencies = Join-Path $deploymentDir "Install-Dependencies.ps1"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host ">> $Message" -ForegroundColor Cyan
}

function Write-OK {
    param([string]$Message)
    Write-Host "   [OK] $Message" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host "   [WARN] $Message" -ForegroundColor Yellow
}

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

function Stop-DeployProcesses {
    if (-not (Test-Path $deployRootFull)) {
        return
    }

    $deployRootNormalized = [System.IO.Path]::GetFullPath($deployRootFull).TrimEnd('\')
    $processes = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.ExecutablePath -and
        [System.IO.Path]::GetFullPath($_.ExecutablePath).StartsWith($deployRootNormalized + "\", [StringComparison]::OrdinalIgnoreCase)
    })

    foreach ($process in $processes) {
        Write-Warn ("Cerrando proceso activo del deploy: {0} (PID {1})" -f $process.Name, $process.ProcessId)
        Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop
    }

    if ($processes.Count -gt 0) {
        Start-Sleep -Seconds 2
    }
}

function Parse-Version {
    param([string]$Text)
    if ($Text -match "^(\d+)\.(\d+)\.(\d+)$") {
        return [pscustomobject]@{
            Major = [int]$Matches[1]
            Minor = [int]$Matches[2]
            Patch = [int]$Matches[3]
            Text = $Text
        }
    }
    return $null
}

function Compare-VersionObject {
    param($A, $B)
    if ($A.Major -ne $B.Major) { return $A.Major.CompareTo($B.Major) }
    if ($A.Minor -ne $B.Minor) { return $A.Minor.CompareTo($B.Minor) }
    return $A.Patch.CompareTo($B.Patch)
}

function Get-CurrentDeployVersion {
    $candidates = @()

    $currentPayload = Get-DeployedPayloadVersion
    if ($currentPayload) {
        $candidates += $currentPayload.Text
    }

    if (Test-Path $backupsRoot) {
        Get-ChildItem -LiteralPath $backupsRoot -Directory -ErrorAction SilentlyContinue | ForEach-Object {
            if ($_.Name -match "(\d+\.\d+\.\d+)") {
                $candidates += $Matches[1]
            }
        }
    }

    $parsed = @($candidates | ForEach-Object { Parse-Version $_ } | Where-Object { $_ })
    if ($parsed.Count -eq 0) {
        return $null
    }

    return ($parsed | Sort-Object Major, Minor, Patch | Select-Object -Last 1)
}

function Get-DeployedPayloadVersion {
    $candidates = @()

    $manifestPath = Join-Path $deployRootFull "release-manifest.json"
    if (Test-Path $manifestPath) {
        try {
            $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
            if ($manifest.version) {
                $candidates += [string]$manifest.version
            }
        } catch {
        }
    }

    $versionPath = Join-Path $deployRootFull "VERSION.txt"
    if (Test-Path $versionPath) {
        try {
            $candidates += (Get-Content -LiteralPath $versionPath -Raw).Trim()
        } catch {
        }
    }

    $parsed = @($candidates | ForEach-Object { Parse-Version $_ } | Where-Object { $_ })
    if ($parsed.Count -eq 0) {
        return $null
    }

    return ($parsed | Sort-Object Major, Minor, Patch | Select-Object -Last 1)
}

function Get-NextVersion {
    param(
        $Current,
        [string]$BumpKind
    )

    if (-not $Current) {
        return "1.0.0"
    }

    if ($BumpKind -eq "none") {
        return $Current.Text
    }
    if ($BumpKind -eq "major") {
        return "{0}.0.0" -f ($Current.Major + 1)
    }
    if ($BumpKind -eq "minor") {
        return "{0}.{1}.0" -f $Current.Major, ($Current.Minor + 1)
    }
    return "{0}.{1}.{2}" -f $Current.Major, $Current.Minor, ($Current.Patch + 1)
}

function Test-CurrentDeployPayload {
    if (-not (Test-Path $deployRootFull)) {
        return $false
    }
    return (
        (Test-Path (Join-Path $deployRootFull "backend\stacky-backend.exe")) -or
        (Test-Path (Join-Path $deployRootFull "release-manifest.json")) -or
        (Test-Path (Join-Path $deployRootFull "START.bat"))
    )
}

function Backup-CurrentDeploy {
    param([string]$PreviousVersion)

    if (-not (Test-CurrentDeployPayload)) {
        return $null
    }

    Write-Step "Respaldando deploy anterior"
    Stop-DeployProcesses
    New-Item -ItemType Directory -Path $backupsRoot -Force | Out-Null

    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $safeVersion = if ($PreviousVersion) { $PreviousVersion } else { "sin-version" }
    $backupDir = Join-Path $backupsRoot ("DeployStackyAgents-{0}-{1}" -f $safeVersion, $timestamp)
    New-Item -ItemType Directory -Path $backupDir -Force | Out-Null

    $items = Get-ChildItem -LiteralPath $deployRootFull -Force | Where-Object { $_.Name -ne "backups" }
    foreach ($item in $items) {
        Assert-ChildPath -Base $deployRootFull -Path $item.FullName
        $destination = Join-Path $backupDir $item.Name
        Assert-ChildPath -Base $backupDir -Path $destination
        try {
            Move-Item -LiteralPath $item.FullName -Destination $destination -Force
        } catch {
            Write-Warn ("No se pudo mover '{0}' al backup. Se copiara y se actualizara en sitio. Detalle: {1}" -f $item.FullName, $_.Exception.Message)
            Copy-Item -LiteralPath $item.FullName -Destination $destination -Recurse -Force
            try {
                Remove-Item -LiteralPath $item.FullName -Recurse -Force
            } catch {
                Write-Warn ("No se pudo limpiar '{0}' despues del backup. Se sobrescribira con el nuevo release. Detalle: {1}" -f $item.FullName, $_.Exception.Message)
            }
        }
    }

    Write-OK "Backup creado: $backupDir"
    return $backupDir
}

function Invoke-PowerShellScript {
    param(
        [Parameter(Mandatory = $true)][string]$ScriptPath,
        [string[]]$Arguments = @()
    )

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $ScriptPath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Fallo $ScriptPath con exit code $LASTEXITCODE"
    }
}

function Copy-ReleaseToDeploy {
    param(
        [Parameter(Mandatory = $true)][string]$ReleaseDir,
        [Parameter(Mandatory = $true)][string]$ReleaseVersion,
        [string]$InstallerPath
    )

    Write-Step "Copiando release a DeployStackyAgents"
    New-Item -ItemType Directory -Path $deployRootFull -Force | Out-Null
    New-Item -ItemType Directory -Path $backupsRoot -Force | Out-Null

    foreach ($item in Get-ChildItem -LiteralPath $ReleaseDir -Force) {
        $destination = Join-Path $deployRootFull $item.Name
        Copy-Item -LiteralPath $item.FullName -Destination $destination -Recurse -Force
    }

    if ($InstallerPath -and (Test-Path $InstallerPath)) {
        Copy-Item -LiteralPath $InstallerPath -Destination (Join-Path $deployRootFull (Split-Path -Leaf $InstallerPath)) -Force
        Write-OK "Instalador EXE incluido"
    } elseif (-not $SkipInstallerExe) {
        Write-Warn "No se genero instalador EXE. Se entrega release portable y zip."
    }

    Set-Content -LiteralPath (Join-Path $deployRootFull "VERSION.txt") -Value $ReleaseVersion -Encoding UTF8

    $deployInfo = [ordered]@{
        app = "Stacky Agents"
        version = $ReleaseVersion
        generated_at = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
        deploy_root = $deployRootFull
        portable_launcher = "START.bat"
        post_install = "INSTALL.ps1"
        zip = "DeployStackyAgents-$ReleaseVersion.zip"
    }
    $deployInfo | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $deployRootFull "DEPLOY_INFO.json") -Encoding UTF8

    $readme = @"
Stacky Agents - Deploy $ReleaseVersion

Entrega:
1. Descomprimir DeployStackyAgents-$ReleaseVersion.zip en la maquina destino.
2. Ejecutar INSTALL.ps1 una vez.
3. Ejecutar START.bat para abrir http://localhost:5050.

Notas:
- backend\stacky-backend.exe ya incluye las dependencias Python.
- frontend\dist ya esta compilado.
- Stacky\agents contiene los .agent.md incluidos en el deploy.
- data y projects se preservan entre actualizaciones.
- Si existe StackyAgents-$ReleaseVersion-Setup.exe, tambien puede usarse como instalador.
"@
    Set-Content -LiteralPath (Join-Path $deployRootFull "LEEME_DEPLOY.txt") -Value $readme -Encoding UTF8
    Write-OK "Deploy actualizado: $deployRootFull"
}

function New-DeployZip {
    param([Parameter(Mandatory = $true)][string]$ReleaseVersion)

    Write-Step "Generando zip final"
    Remove-SafeDirectory -Path $zipStageRoot -AllowedParent $deploymentDir
    New-Item -ItemType Directory -Path $zipStageRoot -Force | Out-Null
    $stageDeploy = Join-Path $zipStageRoot "DeployStackyAgents"
    New-Item -ItemType Directory -Path $stageDeploy -Force | Out-Null

    $excludedNames = @("backups")
    foreach ($item in Get-ChildItem -LiteralPath $deployRootFull -Force) {
        if ($excludedNames -contains $item.Name) {
            continue
        }
        if ($item.Name -like "DeployStackyAgents-*.zip") {
            continue
        }
        Copy-Item -LiteralPath $item.FullName -Destination (Join-Path $stageDeploy $item.Name) -Recurse -Force
    }

    $zipPath = Join-Path $deployRootFull ("DeployStackyAgents-{0}.zip" -f $ReleaseVersion)
    if (Test-Path $zipPath) {
        Assert-ChildPath -Base $deployRootFull -Path $zipPath
        Remove-Item -LiteralPath $zipPath -Force
    }

    Compress-Archive -Path $stageDeploy -DestinationPath $zipPath -CompressionLevel Optimal
    Write-OK "ZIP generado: $zipPath"
    return $zipPath
}

try {
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host " PrepararPublicacion - Stacky Agents" -ForegroundColor Cyan
    Write-Host " App root : $appRoot" -ForegroundColor Gray
    Write-Host " Deploy   : $deployRootFull" -ForegroundColor Gray
    Write-Host "============================================================" -ForegroundColor Cyan

    if (-not (Test-Path $buildRelease)) {
        throw "No se encontro build_release.ps1 en deployment."
    }

    if ($SkipInstallerExe -and $RequireInstallerExe) {
        throw "No se puede usar SkipInstallerExe y RequireInstallerExe al mismo tiempo."
    }

    $deployedPayloadVersion = Get-DeployedPayloadVersion
    $currentVersion = Get-CurrentDeployVersion
    if ($Version) {
        if (-not (Parse-Version $Version)) {
            throw "Version invalida: $Version. Usar formato X.Y.Z"
        }
        $releaseVersion = $Version
    } else {
        $releaseVersion = Get-NextVersion -Current $currentVersion -BumpKind $Bump
    }

    Write-OK "Version a generar: $releaseVersion"

    if (-not $SkipDependencyInstall) {
        Write-Step "Preparando dependencias de build"
        $depArgs = @("-NoPause")
        if (-not $SkipInstallerExe) {
            $depArgs += "-InstallInnoSetup"
        }
        Invoke-PowerShellScript -ScriptPath $installDependencies -Arguments $depArgs
        Write-OK "Dependencias verificadas"
    }

    Write-Step "Generando release base"
    Remove-SafeDirectory -Path $tempOut -AllowedParent $deploymentDir
    New-Item -ItemType Directory -Path $tempOut -Force | Out-Null

    $releaseName = "stacky-agents-$releaseVersion"
    # -DeployRoot: build_release snapshotea el arnes vivo (harness_defaults.env)
    # ANTES de Backup-CurrentDeploy, mientras $deployRootFull todavia tiene la
    # config actual del operador, y lo hornea en el backend\.env del release.
    $buildArgs = @(
        "-OutputRoot", $tempOut,
        "-ReleaseName", $releaseName,
        "-Version", $releaseVersion,
        "-DeployRoot", $deployRootFull
    )
    if ($GitHubCopilotAgentsRepo) {
        Write-Warn "-GitHubCopilotAgentsRepo está obsoleto y se ignora. La fuente de agentes es backend\Stacky\agents."
    }
    if ($SkipInstallerExe) {
        $buildArgs += "-SkipInstaller"
    }
    if ($RequireInstallerExe) {
        $buildArgs += "-RequireInstaller"
    }
    if ($SkipSmokeTest) {
        $buildArgs += "-SkipSmokeTest"
    }
    if ($ExportConfig) {
        $buildArgs += "-ExportConfig"
    }

    Invoke-PowerShellScript -ScriptPath $buildRelease -Arguments $buildArgs

    $releaseDir = Join-Path $tempOut $releaseName
    if (-not (Test-Path $releaseDir)) {
        $releaseDir = (Get-ChildItem -LiteralPath $tempOut -Directory | Sort-Object LastWriteTime | Select-Object -Last 1).FullName
    }
    if (-not $releaseDir -or -not (Test-Path (Join-Path $releaseDir "backend\stacky-backend.exe"))) {
        throw "El release no contiene backend\stacky-backend.exe"
    }

    $previousVersion = if ($deployedPayloadVersion) { $deployedPayloadVersion.Text } else { "" }
    $backupDir = Backup-CurrentDeploy -PreviousVersion $previousVersion

    $installerPath = Join-Path $tempOut ("StackyAgents-{0}-Setup.exe" -f $releaseVersion)
    Copy-ReleaseToDeploy -ReleaseDir $releaseDir -ReleaseVersion $releaseVersion -InstallerPath $installerPath
    $zipPath = New-DeployZip -ReleaseVersion $releaseVersion

    Remove-SafeDirectory -Path $zipStageRoot -AllowedParent $deploymentDir

    Write-Host ""
    Write-Host "Publicacion lista." -ForegroundColor Green
    Write-Host "Carpeta : $deployRootFull" -ForegroundColor Green
    Write-Host "ZIP     : $zipPath" -ForegroundColor Green
    if ($backupDir) {
        Write-Host "Backup  : $backupDir" -ForegroundColor Green
    }
    Write-Host ""
} catch {
    Write-Host ""
    Write-Host "[ERROR] $($_.Exception.Message)" -ForegroundColor Red
    Write-Host ""
    exit 1
}

if (-not $NoPause) {
    Write-Host "Pulsa Enter para cerrar..."
    [void][Console]::ReadLine()
}
