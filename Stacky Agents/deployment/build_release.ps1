#Requires -Version 5.1
<#
.SYNOPSIS
    Genera un release distribuible de Stacky Agents sin codigo fuente runtime.
.DESCRIPTION
    Compila el frontend, congela el backend con PyInstaller onedir y prepara una
    carpeta/zip portable. Si Inno Setup esta instalado, tambien genera un EXE.
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File ".\Stacky Agents\deployment\build_release.ps1"
#>

[CmdletBinding()]
param(
    [string]$OutputRoot = "",
    [string]$ReleaseName = "",
    [string]$Version = "",
    [string]$GitHubCopilotAgentsRepo = "",
    [string]$CertificateThumbprint = "",
    [string]$CertificatePath = "",
    [string]$CertificatePassword = "",
    [string]$TimestampServer = "http://timestamp.digicert.com",
    [string]$SignToolPath = "",
    [switch]$SkipZip,
    [switch]$SkipInstaller,
    [switch]$SkipSmokeTest,
    [switch]$ExportConfig,
    [switch]$RequireInstaller,
    [switch]$RequireSigning
)

$ErrorActionPreference = "Stop"

function Write-Step { param([string]$Message) Write-Host "`n>> $Message" -ForegroundColor Cyan }
function Write-OK { param([string]$Message) Write-Host "   [OK] $Message" -ForegroundColor Green }
function Write-Warn { param([string]$Message) Write-Host "   [WARN] $Message" -ForegroundColor Yellow }

function Require-Command {
    param(
        [Parameter(Mandatory = $true)][string]$Command,
        [Parameter(Mandatory = $true)][string]$Hint
    )

    if (-not (Get-Command $Command -ErrorAction SilentlyContinue)) {
        throw "$Command no esta disponible. $Hint"
    }
}

function Resolve-Python {
    $candidates = @(
        @{ Command = "python"; Args = @() },
        @{ Command = "py"; Args = @("-3.11") },
        @{ Command = "py"; Args = @("-3") }
    )

    foreach ($candidate in $candidates) {
        try {
            $cmd = $candidate["Command"]
            $argList = @($candidate["Args"]) + @("--version")
            $version = & $cmd @argList 2>&1
            if ($version -match "Python (\d+)\.(\d+)") {
                $major = [int]$Matches[1]
                $minor = [int]$Matches[2]
                if ($major -eq 3 -and $minor -ge 11) {
                    return $candidate
                }
            }
        } catch {
        }
    }

    throw "Python 3.11+ no esta disponible. Instala Python antes de generar el release."
}

function Invoke-BuildPython {
    param([string[]]$PythonArgs)
    $cmd = $script:Python["Command"]
    $argList = @($script:Python["Args"]) + $PythonArgs
    & $cmd @argList
}

function Resolve-SignTool {
    if ($SignToolPath -and (Test-Path $SignToolPath)) {
        return (Resolve-Path $SignToolPath).Path
    }

    $cmd = Get-Command "signtool.exe" -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    $kitRoots = @(
        "${env:ProgramFiles(x86)}\Windows Kits\10\bin",
        "${env:ProgramFiles}\Windows Kits\10\bin"
    )
    foreach ($root in $kitRoots) {
        if (-not (Test-Path $root)) {
            continue
        }
        $candidate = Get-ChildItem -Path $root -Filter "signtool.exe" -Recurse -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -match "\\x64\\signtool\.exe$" } |
            Sort-Object FullName -Descending |
            Select-Object -First 1
        if ($candidate) {
            return $candidate.FullName
        }
    }

    return ""
}

function Invoke-AuthenticodeSignature {
    param([Parameter(Mandatory = $true)][string]$Path)

    $hasCert = ($CertificateThumbprint -or $CertificatePath)
    if (-not $hasCert) {
        if ($RequireSigning) {
            throw "Firma Authenticode requerida pero no se configuro CertificateThumbprint ni CertificatePath."
        }
        Write-Warn "Firma omitida para ${Path}: no hay certificado configurado."
        return
    }

    $signtool = Resolve-SignTool
    if (-not $signtool) {
        if ($RequireSigning) {
            throw "Firma Authenticode requerida pero signtool.exe no esta disponible."
        }
        Write-Warn "Firma omitida para ${Path}: signtool.exe no encontrado."
        return
    }

    $args = @("sign", "/fd", "SHA256", "/tr", $TimestampServer, "/td", "SHA256")
    if ($CertificatePath) {
        if (-not (Test-Path $CertificatePath)) {
            throw "No existe el certificado PFX: $CertificatePath"
        }
        $args += @("/f", $CertificatePath)
        if ($CertificatePassword) {
            $args += @("/p", $CertificatePassword)
        }
    } else {
        $args += @("/sha1", $CertificateThumbprint)
    }
    $args += $Path

    & $signtool @args
    if ($LASTEXITCODE -ne 0) {
        throw "Fallo la firma Authenticode de $Path."
    }

    & $signtool verify /pa /v $Path
    if ($LASTEXITCODE -ne 0) {
        throw "Fallo la verificacion Authenticode de $Path."
    }
    Write-OK "Firmado: $Path"
}

function Assert-CleanReleasePayload {
    param([Parameter(Mandatory = $true)][string]$Root)

    $blockedNames = @(
        "ArreglosStackyAgents.md",
        "MejorasStackyAgent.md",
        "STACKY_AGENTS_COMPLETE.md",
        "README_PARA_AGENTES.md"
    )
    $blockedPatterns = @("Stacky Agents QA UAT roadmap *.md")
    $blocked = @()
    foreach ($name in $blockedNames) {
        $blocked += Get-ChildItem -Path $Root -Filter $name -Recurse -File -ErrorAction SilentlyContinue
    }
    foreach ($pattern in $blockedPatterns) {
        $blocked += Get-ChildItem -Path $Root -Filter $pattern -Recurse -File -ErrorAction SilentlyContinue
    }

    if ($blocked.Count -gt 0) {
        $list = ($blocked | Select-Object -ExpandProperty FullName) -join "`n"
        throw "El payload distribuible contiene documentacion interna bloqueada:`n$list"
    }
}

function Resolve-GitHubCopilotAgentsSource {
    if ($GitHubCopilotAgentsRepo) {
        return $GitHubCopilotAgentsRepo
    }

    if ($env:GITHUB_COPILOT_AGENTS_REPO) {
        return $env:GITHUB_COPILOT_AGENTS_REPO
    }

    if ($env:STACKY_GITHUB_COPILOT_AGENTS_REPO) {
        return $env:STACKY_GITHUB_COPILOT_AGENTS_REPO
    }

    if ($env:APPDATA) {
        $defaultPromptsDir = Join-Path $env:APPDATA "Code\User\prompts"
        if (Test-Path $defaultPromptsDir) {
            return $defaultPromptsDir
        }
    }

    return ""
}

function Copy-GitHubCopilotAgents {
    param(
        [Parameter(Mandatory = $true)][string]$SourceRoot,
        [Parameter(Mandatory = $true)][string]$DestinationRoot
    )

    if (-not $SourceRoot) {
        Write-Warn "No se configuro repo/carpeta de agentes GitHub Copilot. Se omite github_copilot_agents."
        return 0
    }

    if (-not (Test-Path $SourceRoot)) {
        Write-Warn "No existe la fuente de agentes GitHub Copilot: $SourceRoot"
        return 0
    }

    $sourceFull = [System.IO.Path]::GetFullPath($SourceRoot)
    $agentFiles = @(Get-ChildItem -LiteralPath $sourceFull -Filter "*.agent.md" -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -notmatch "\\(node_modules|\.git|outputs|__pycache__)($|\\)" } |
        Sort-Object FullName)

    if ($agentFiles.Count -eq 0) {
        Write-Warn "No se encontraron *.agent.md en: $sourceFull"
        return 0
    }

    New-Item -ItemType Directory -Path $DestinationRoot -Force | Out-Null
    $manifest = @()
    $usedNames = @{}

    foreach ($file in $agentFiles) {
        $targetName = $file.Name
        if ($usedNames.ContainsKey($targetName.ToLowerInvariant())) {
            $relativeParent = $file.DirectoryName.Substring($sourceFull.Length).TrimStart("\", "/")
            $prefix = ($relativeParent -replace "[\\/:*?`"<>| ]+", "_").Trim("_")
            if ($prefix) {
                $targetName = "$prefix-$($file.Name)"
            }
        }
        $usedNames[$targetName.ToLowerInvariant()] = $true

        $target = Join-Path $DestinationRoot $targetName
        Copy-Item -LiteralPath $file.FullName -Destination $target -Force
        $manifest += [ordered]@{
            filename = $targetName
            source_relative_path = $file.FullName.Substring($sourceFull.Length).TrimStart("\", "/")
            source_root = $sourceFull
        }
    }

    $manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $DestinationRoot "manifest.json") -Encoding UTF8
    return $agentFiles.Count
}

$deploymentDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$appRoot = Split-Path -Parent $deploymentDir
$frontendDir = Join-Path $appRoot "frontend"
$backendDir = Join-Path $appRoot "backend"
$vsixDir = Join-Path $appRoot "vscode_extension"
$buildRoot = Join-Path $deploymentDir ".build"
$exportConfigScript = Join-Path $deploymentDir "export_config_for_release.py"

if (-not $OutputRoot) {
    $OutputRoot = Join-Path $deploymentDir "out"
}

if (-not $Version) {
    try {
        $pkg = Get-Content -LiteralPath (Join-Path $frontendDir "package.json") -Raw | ConvertFrom-Json
        $Version = [string]$pkg.version
    } catch {
        $Version = "0.0.0"
    }
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
if (-not $ReleaseName) {
    $ReleaseName = "stacky-agents-$Version-$timestamp"
}

$releaseDir = Join-Path $OutputRoot $ReleaseName
$zipPath = Join-Path $OutputRoot "$ReleaseName.zip"
$installerPath = Join-Path $OutputRoot "StackyAgents-$Version-Setup.exe"

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " Stacky Agents - Generador de Release Distribuible" -ForegroundColor Cyan
Write-Host " App root : $appRoot" -ForegroundColor Gray
Write-Host " Version  : $Version" -ForegroundColor Gray
Write-Host " Salida   : $releaseDir" -ForegroundColor Gray
Write-Host "============================================================" -ForegroundColor Cyan

Require-Command -Command "npm" -Hint "Instala Node.js 18+ para compilar el frontend."
$script:Python = Resolve-Python

Write-Step "Compilando frontend"
Push-Location $frontendDir
try {
    if (-not (Test-Path (Join-Path $frontendDir "node_modules"))) {
        Write-Step "Instalando dependencias del frontend"
        npm install
    }

    npm run build
    if (-not (Test-Path (Join-Path $frontendDir "dist\index.html"))) {
        throw "La compilacion no genero frontend\dist\index.html."
    }
    Write-OK "Frontend compilado"
} finally {
    Pop-Location
}

Write-Step "Preparando entorno de build PyInstaller"
New-Item -ItemType Directory -Path $buildRoot -Force | Out-Null
$venvDir = Join-Path $buildRoot "pyinstaller-venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Invoke-BuildPython -PythonArgs @("-m", "venv", $venvDir)
}
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r (Join-Path $backendDir "requirements.txt") pyinstaller
Write-OK "Entorno PyInstaller listo"

Write-Step "Congelando backend con PyInstaller"
$pyDist = Join-Path $buildRoot "pyinstaller-dist"
$pyWork = Join-Path $buildRoot "pyinstaller-work"
$pySpec = Join-Path $buildRoot "pyinstaller-spec"
Remove-Item -LiteralPath $pyDist, $pyWork, $pySpec -Recurse -Force -ErrorAction SilentlyContinue
Push-Location $backendDir
try {
    & $venvPython -m PyInstaller `
        --noconfirm `
        --clean `
        --onedir `
        --name stacky-backend `
        --distpath $pyDist `
        --workpath $pyWork `
        --specpath $pySpec `
        --collect-submodules api `
        --collect-submodules agents `
        --collect-submodules services `
        --collect-submodules packs `
        --collect-submodules sqlalchemy `
        --collect-submodules alembic `
        --collect-submodules win32crypt `
        --collect-submodules win32api `
        --collect-submodules pythonjsonlogger `
        app.py
} finally {
    Pop-Location
}

$frozenBackend = Join-Path $pyDist "stacky-backend"
if (-not (Test-Path (Join-Path $frozenBackend "stacky-backend.exe"))) {
    throw "PyInstaller no genero stacky-backend.exe."
}
Write-OK "Backend congelado"

Write-Step "Firmando backend congelado"
Invoke-AuthenticodeSignature -Path (Join-Path $frozenBackend "stacky-backend.exe")

Write-Step "Preparando carpeta release"
if (Test-Path $releaseDir) {
    Remove-Item -LiteralPath $releaseDir -Recurse -Force
}
New-Item -ItemType Directory -Path $releaseDir -Force | Out-Null

$releaseBackendDir = Join-Path $releaseDir "backend"
$releaseFrontendDir = Join-Path $releaseDir "frontend"
$releaseVsixDir = Join-Path $releaseDir "vscode_extension"
$releaseGitHubCopilotAgentsDir = Join-Path $releaseDir "github_copilot_agents"
$releaseDataDir = Join-Path $releaseDir "data"
$releaseProjectsDir = Join-Path $releaseDir "projects"

Write-Step "Copiando backend congelado"
New-Item -ItemType Directory -Path $releaseBackendDir -Force | Out-Null
Copy-Item -Path (Join-Path $frozenBackend "*") -Destination $releaseBackendDir -Recurse -Force
Copy-Item -LiteralPath (Join-Path $backendDir ".env.example") -Destination (Join-Path $releaseBackendDir ".env.example") -Force
New-Item -ItemType Directory -Path $releaseDataDir, $releaseProjectsDir -Force | Out-Null
Write-OK "Backend copiado sin fuentes del proyecto"

Write-Step "Copiando frontend compilado"
New-Item -ItemType Directory -Path $releaseFrontendDir -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $frontendDir "dist") -Destination (Join-Path $releaseFrontendDir "dist") -Recurse -Force
Write-OK "Frontend copiado"

Write-Step "Copiando extension VS Code"
New-Item -ItemType Directory -Path $releaseVsixDir -Force | Out-Null
$latestVsix = Get-ChildItem -Path $vsixDir -Filter "stacky-agents-*.vsix" -File -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime, Name |
    Select-Object -Last 1
if ($latestVsix) {
    Copy-Item -LiteralPath $latestVsix.FullName -Destination (Join-Path $releaseVsixDir $latestVsix.Name) -Force
    Write-OK "VSIX incluida: $($latestVsix.Name)"
} else {
    Write-Warn "No se encontro .vsix para incluir en el release."
}

Write-Step "Copiando agentes GitHub Copilot"
$githubCopilotAgentsSource = Resolve-GitHubCopilotAgentsSource
$githubCopilotAgentsCount = Copy-GitHubCopilotAgents -SourceRoot $githubCopilotAgentsSource -DestinationRoot $releaseGitHubCopilotAgentsDir
if ($githubCopilotAgentsCount -gt 0) {
    Write-OK "Agentes incluidos: $githubCopilotAgentsCount desde $githubCopilotAgentsSource"
}

if ($ExportConfig) {
    Write-Step "Exportando configuracion local de proyectos y credenciales"
    if (-not (Test-Path $exportConfigScript)) {
        throw "No se encontro export_config_for_release.py"
    }
    Invoke-BuildPython -PythonArgs @(
        $exportConfigScript,
        "--source-projects", (Join-Path $backendDir "projects"),
        "--source-data", (Join-Path $backendDir "data"),
        "--release-root", $releaseDir
    )
    if ($LASTEXITCODE -ne 0) {
        throw "Fallo la exportacion de configuracion local."
    }
    Write-OK "Configuracion local exportada al release"
}

Write-Step "Copiando scripts de release"
Copy-Item -LiteralPath (Join-Path $deploymentDir "release_assets\INSTALL.ps1") -Destination (Join-Path $releaseDir "INSTALL.ps1") -Force
Copy-Item -LiteralPath (Join-Path $deploymentDir "release_assets\START.bat") -Destination (Join-Path $releaseDir "START.bat") -Force
Copy-Item -LiteralPath (Join-Path $deploymentDir "release_assets\smoke_test.ps1") -Destination (Join-Path $releaseDir "smoke_test.ps1") -Force
Copy-Item -LiteralPath (Join-Path $deploymentDir "release_assets\INSTALLER.md") -Destination (Join-Path $releaseDir "INSTALLER.md") -Force
Copy-Item -LiteralPath (Join-Path $deploymentDir "release_assets\OPERATOR_GUIDE.md") -Destination (Join-Path $releaseDir "OPERATOR_GUIDE.md") -Force
Write-OK "Scripts copiados"

Write-Step "Generando metadata"
$gitSha = ""
try {
    $gitSha = (git -C $appRoot rev-parse --short HEAD).Trim()
} catch {
    $gitSha = ""
}

$manifest = [ordered]@{
    app = "Stacky Agents"
    generated_at = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    release_name = $ReleaseName
    version = $Version
    source_commit = $gitSha
    frontend_dist = "frontend/dist"
    backend_entrypoint = "backend/stacky-backend.exe"
    github_copilot_agents_dir = "github_copilot_agents"
    github_copilot_agents_count = $githubCopilotAgentsCount
    config_exported = [bool]$ExportConfig
    data_dir = "data"
    projects_dir = "projects"
    installer = "INSTALL.ps1"
    launcher = "START.bat"
    smoke_test = "smoke_test.ps1"
    operator_guide = "OPERATOR_GUIDE.md"
}

$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $releaseDir "release-manifest.json") -Encoding UTF8
Write-OK "Metadata generada"

Write-Step "Validando limpieza del payload"
Assert-CleanReleasePayload -Root $releaseDir
Write-OK "Payload sin documentacion interna"

if (-not $SkipSmokeTest) {
    Write-Step "Ejecutando smoke test del release"
    $previousReleaseRoot = $env:STACKY_RELEASE_ROOT
    $env:STACKY_RELEASE_ROOT = $releaseDir
    try {
        & $venvPython -m pytest (Join-Path $deploymentDir "tests\test_release_smoke.py") -q
        if ($LASTEXITCODE -ne 0) {
            throw "El smoke test del release fallo."
        }
    } finally {
        if ($null -eq $previousReleaseRoot) {
            Remove-Item Env:\STACKY_RELEASE_ROOT -ErrorAction SilentlyContinue
        } else {
            $env:STACKY_RELEASE_ROOT = $previousReleaseRoot
        }
    }
    Write-OK "Smoke test OK"
}

if (-not $SkipZip) {
    Write-Step "Generando zip"
    if (Test-Path $zipPath) {
        Remove-Item -LiteralPath $zipPath -Force
    }
    Compress-Archive -Path (Join-Path $releaseDir "*") -DestinationPath $zipPath
    Write-OK "ZIP generado: $zipPath"
}

if (-not $SkipInstaller) {
    Write-Step "Generando instalador EXE con Inno Setup"
    $iscc = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
    if (-not $iscc) {
        $defaultIscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
        if (Test-Path $defaultIscc) {
            $iscc = Get-Item $defaultIscc
        }
    }

    if ($iscc) {
        $isccPath = if ($iscc.Source) { $iscc.Source } else { $iscc.FullName }
        if (Test-Path $installerPath) {
            Remove-Item -LiteralPath $installerPath -Force
        }
        & $isccPath `
            (Join-Path $deploymentDir "stacky-agents.iss") `
            "/DSourceDir=$releaseDir" `
            "/DOutputDir=$OutputRoot" `
            "/DAppVersion=$Version" `
            "/DReleaseName=$ReleaseName"
        if ($LASTEXITCODE -ne 0) {
            throw "Inno Setup fallo con exit code $LASTEXITCODE."
        }
        if (-not (Test-Path $installerPath)) {
            throw "Inno Setup no genero el instalador esperado: $installerPath"
        }
        Write-OK "Instalador generado: $installerPath"
    } else {
        if ($RequireInstaller) {
            throw "Inno Setup no esta instalado y RequireInstaller esta activo."
        }
        Write-Warn "Inno Setup no esta instalado. Se deja listo el release portable/zip."
    }
}

if ((Test-Path $installerPath) -and (-not $SkipInstaller)) {
    Write-Step "Firmando instalador"
    Invoke-AuthenticodeSignature -Path $installerPath
}

Write-Host ""
Write-Host "Release generado correctamente." -ForegroundColor Green
Write-Host "Carpeta: $releaseDir" -ForegroundColor Green
if (-not $SkipZip) {
    Write-Host "ZIP    : $zipPath" -ForegroundColor Green
}
if ((Test-Path $installerPath) -and (-not $SkipInstaller)) {
    Write-Host "EXE    : $installerPath" -ForegroundColor Green
}
Write-Host ""
