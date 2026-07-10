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
    [string]$DeployRoot = "",
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
function Write-Utf8NoBom {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Value
    )

    $encoding = [System.Text.UTF8Encoding]::new($false)
    [System.IO.File]::WriteAllText($Path, $Value, $encoding)
}

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

function Resolve-StackyAgentsSource {
    if ($PSScriptRoot) {
        $repoAppRoot = Split-Path -Parent $PSScriptRoot

        # Fuente AUTORIZADA: los .agent.md editables viven en backend/Stacky/agents.
        # No se aceptan fuentes GitHub Copilot/VS Code ni bundles legacy:
        # Stacky/agents es el origen único del release.
        $authoredSource = Join-Path $repoAppRoot "backend\Stacky\agents"
        if (Test-Path $authoredSource) {
            return $authoredSource
        }
    }

    return ""
}

function Get-AgentName {
    param([Parameter(Mandatory = $true)][string]$Filename)
    if ($Filename -match "^(.*)\.agent\.md$") {
        return $Matches[1]
    }
    if ($Filename -match "^(.*)\.prompt\.md$") {
        return $Matches[1]
    }
    if ($Filename -match "^(.*)\.md$") {
        return $Matches[1]
    }
    return $Filename
}

function Get-AgentDescription {
    param([Parameter(Mandatory = $true)][string]$Path)
    try {
        $content = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
    } catch {
        return ""
    }
    if (-not $content) { return "" }
    # frontmatter YAML mínimo: ---\n description: ... \n---
    if ($content -match "(?s)^---\s*\r?\n(.*?)\r?\n---") {
        $front = $Matches[1]
        foreach ($line in ($front -split "\r?\n")) {
            if ($line -match "^\s*description\s*:\s*(.+)$") {
                return ($Matches[1].Trim().Trim('"').Trim("'"))
            }
        }
    }
    foreach ($line in ($content -split "\r?\n")) {
        $stripped = $line.Trim()
        if ($stripped -and -not $stripped.StartsWith("#")) {
            if ($stripped.Length -gt 240) {
                return $stripped.Substring(0, 240)
            }
            return $stripped
        }
    }
    return ""
}

function Get-FileSha256 {
    param([Parameter(Mandatory = $true)][string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Copy-StackyAgents {
    <#
    .SYNOPSIS
        Materializa los .agent.md dentro de <release>/Stacky/agents y genera
        manifest.json con el formato del plan plan-agentes-bundled-en-stacky.
    #>
    param(
        [Parameter(Mandatory = $true)][string]$SourceRoot,
        [Parameter(Mandatory = $true)][string]$StackyHomeDir
    )

    $stackyAgentsDir = Join-Path $StackyHomeDir "agents"
    New-Item -ItemType Directory -Path $stackyAgentsDir -Force | Out-Null

    if (-not $SourceRoot -or -not (Test-Path $SourceRoot)) {
        Write-Warn "Sin fuente canonical para Stacky/agents: backend/Stacky/agents no existe."
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

    $manifestAgents = @()
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

        $target = Join-Path $stackyAgentsDir $targetName
        Copy-Item -LiteralPath $file.FullName -Destination $target -Force

        $name = Get-AgentName -Filename $targetName
        $description = Get-AgentDescription -Path $target
        $checksum = Get-FileSha256 -Path $target

        $relativePath = "agents/{0}" -f $targetName
        $absolutePath = ($target -replace "\\", "/")

        $manifestAgents += [ordered]@{
            name = $name
            mention = "@$name"
            filename = $targetName
            path = $absolutePath
            relative_path = $relativePath
            description = $description
            checksum_sha256 = $checksum
            source = "bundled"
        }
    }

    $stackyHomeForward = ($StackyHomeDir -replace "\\", "/")
    $stackyAgentsForward = ($stackyAgentsDir -replace "\\", "/")
    $manifest = [ordered]@{
        schema_version = 1
        generated_at = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
        stacky_home = $stackyHomeForward
        agents_dir = $stackyAgentsForward
        agents = $manifestAgents
    }

    Write-Utf8NoBom -Path (Join-Path $stackyAgentsDir "manifest.json") -Value ($manifest | ConvertTo-Json -Depth 6)
    return $agentFiles.Count
}

$deploymentDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$appRoot = Split-Path -Parent $deploymentDir
$frontendDir = Join-Path $appRoot "frontend"
$backendDir = Join-Path $appRoot "backend"
$vsixDir = Join-Path $appRoot "vscode_extension"
$buildRoot = Join-Path $deploymentDir ".build"
$exportConfigScript = Join-Path $deploymentDir "export_config_for_release.py"
$exportHarnessScript = Join-Path $deploymentDir "export_harness_defaults.py"
$harnessDefaultsFile = Join-Path $backendDir "harness_defaults.env"

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

if ($GitHubCopilotAgentsRepo) {
    Write-Warn "-GitHubCopilotAgentsRepo está obsoleto y se ignora. La fuente de agentes es backend\Stacky\agents."
}

Require-Command -Command "npm" -Hint "Instala Node.js 18+ para compilar el frontend."
$script:Python = Resolve-Python

# Snapshot del arnés vivo → harness_defaults.env (versionado). Se hornea más abajo
# en backend\.env. Corre ANTES del backup del deploy en Prepare-Publication, así que
# $DeployRoot todavía apunta al deploy con la config actual del operador. Si no hay
# deploy vivo (build standalone / otra máquina) se conserva el harness_defaults.env
# versionado existente.
if ($DeployRoot -and (Test-Path $DeployRoot)) {
    Write-Step "Sincronizando harness_defaults.env con el arnes vivo del deploy"
    if (Test-Path $exportHarnessScript) {
        Invoke-BuildPython -PythonArgs @(
            $exportHarnessScript,
            "--deploy-root", $DeployRoot,
            "--out", $harnessDefaultsFile
        )
        if ($LASTEXITCODE -ne 0) {
            Write-Warn "No se pudo refrescar harness_defaults.env; se usara el versionado existente."
        } else {
            Write-OK "harness_defaults.env sincronizado con el arnes vivo"
        }
    } else {
        Write-Warn "export_harness_defaults.py no encontrado; se usara harness_defaults.env versionado."
    }
}

Write-Step "Compilando frontend"
Push-Location $frontendDir
try {
    # Matar procesos node/npm activos en el frontend para evitar bloqueos EBUSY en node_modules
    # (típicamente `npm run dev` que mantiene archivos .node abiertos durante npm install)
    $frontendDirFull = [System.IO.Path]::GetFullPath($frontendDir)
    $nodeProcs = @(Get-CimInstance Win32_Process -Filter "Name LIKE '%node.exe%' OR Name LIKE '%npm%'" -ErrorAction SilentlyContinue | 
        Where-Object { 
            $_.ExecutablePath -and
            $_.CommandLine -and
            $_.CommandLine -match [regex]::Escape($frontendDirFull)
        })
    if ($nodeProcs.Count -gt 0) {
        Write-Warn "Deteniendo $($nodeProcs.Count) procesos node/npm en el frontend para liberar node_modules."
        foreach ($proc in $nodeProcs) {
            try {
                Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
            } catch {
                Write-Warn "No se pudo detener el proceso $($proc.Name) (PID $($proc.ProcessId)): $_"
            }
        }
        Start-Sleep -Seconds 3
    }

    if (-not (Test-Path (Join-Path $frontendDir "node_modules"))) {
        Write-Step "Instalando dependencias del frontend"
        npm install
        if ($LASTEXITCODE -ne 0) {
            throw "npm install fallo con exit code $LASTEXITCODE."
        }
    }

    # Rebuild SIEMPRE fresco: borrar el dist previo antes de compilar. Vite vacia
    # outDir por default, pero esto blinda el deploy contra cualquier cambio futuro
    # de config (outDir fuera de root o emptyOutDir:false) que dejaria assets
    # huerfanos del build anterior viajando al release (el dolor "build FROZEN":
    # los fixes del fuente no llegan). node_modules se reutiliza a proposito (no
    # afecta la frescura del bundle; Vite recompila el fuente actual).
    $frontendDist = Join-Path $frontendDir "dist"
    if (Test-Path $frontendDist) {
        Write-Step "Limpiando frontend\dist previo (rebuild fresco)"
        Remove-Item -LiteralPath $frontendDist -Recurse -Force -ErrorAction SilentlyContinue
    }

    npm run build
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "npm run build fallo. Limpiando node_modules y reintentando."

        # Reintentar matar procesos antes de limpiar
        $nodeProcs = @(Get-CimInstance Win32_Process -Filter "Name LIKE '%node.exe%' OR Name LIKE '%npm%'" -ErrorAction SilentlyContinue | 
            Where-Object { 
                $_.ExecutablePath -and
                $_.CommandLine -and
                $_.CommandLine -match [regex]::Escape($frontendDirFull)
            })
        if ($nodeProcs.Count -gt 0) {
            Write-Warn "Deteniendo $($nodeProcs.Count) procesos node/npm en el frontend para liberar node_modules antes de limpiar."
            foreach ($proc in $nodeProcs) {
                try {
                    Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
                } catch {
                    Write-Warn "No se pudo detener el proceso $($proc.Name) (PID $($proc.ProcessId)): $_"
                }
            }
            Start-Sleep -Seconds 3
        }

        # Limpiar node_modules completamente y reinstalar
        $nodeModules = Join-Path $frontendDir "node_modules"
        if (Test-Path $nodeModules) {
            Write-Warn "Eliminando node_modules para asegurar limpieza completa."
            Remove-Item -LiteralPath $nodeModules -Recurse -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 2
        }

        npm install
        if ($LASTEXITCODE -ne 0) {
            throw "npm install fallo durante reintento con exit code $LASTEXITCODE."
        }

        npm run build
        if ($LASTEXITCODE -ne 0) {
            throw "npm run build fallo con exit code $LASTEXITCODE."
        }
    }

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
    # --collect-data services: empaqueta los archivos de DATOS dentro del paquete
    # `services` (p. ej. `client_profile_defaults/*.json`). `--collect-submodules`
    # solo trae los `.py`; sin esto los JSON no llegaban al deploy congelado y
    # get_default_client_profile() devolvía un template vacío (perfiles sembrados
    # incompletos + "client-profile no inyectado"). El fallback embebido en
    # services/client_profile_default_templates.py cubre el caso aunque esto falle.
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
        --collect-data services `
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
$releaseStackyHomeDir = Join-Path $releaseDir "Stacky"
$releaseStackyAgentsDir = Join-Path $releaseStackyHomeDir "agents"
$releaseDataDir = Join-Path $releaseDir "data"
$releaseProjectsDir = Join-Path $releaseDir "projects"

Write-Step "Copiando backend congelado"
New-Item -ItemType Directory -Path $releaseBackendDir -Force | Out-Null
Copy-Item -Path (Join-Path $frozenBackend "*") -Destination $releaseBackendDir -Recurse -Force
Copy-Item -LiteralPath (Join-Path $backendDir ".env.example") -Destination (Join-Path $releaseBackendDir ".env.example") -Force

# Hornear backend\.env con el arnes por defecto, en TODO deploy (con o sin
# -ExportConfig): .env.example (base sin secretos) + harness_defaults.env (flags
# del arnes). Es el .env que config.py carga al arrancar (backend_root()\.env),
# asi que el deploy nuevo arranca con el arnes configurado sin tocar nada.
# harness_defaults.env SOLO contiene flags de FLAG_REGISTRY: nunca credenciales.
$releaseEnvFile = Join-Path $releaseBackendDir ".env"
$envExampleText = Get-Content -LiteralPath (Join-Path $backendDir ".env.example") -Raw
if (Test-Path $harnessDefaultsFile) {
    $harnessText = Get-Content -LiteralPath $harnessDefaultsFile -Raw
    $bakedEnv = $envExampleText.TrimEnd("`r", "`n") + "`r`n`r`n" +
        "# == Arnes por defecto horneado en el deploy (fuente: harness_defaults.env) ==`r`n" +
        $harnessText
    Write-Utf8NoBom -Path $releaseEnvFile -Value $bakedEnv
    Write-OK "backend\.env horneado con el arnes por defecto (.env.example + harness_defaults.env)"
} else {
    Write-Utf8NoBom -Path $releaseEnvFile -Value $envExampleText
    Write-Warn "harness_defaults.env ausente; backend\.env horneado solo desde .env.example."
}

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

Write-Step "Materializando Stacky/agents desde backend/Stacky/agents"
$stackyAgentsSource = Resolve-StackyAgentsSource
$stackyAgentsCount = Copy-StackyAgents -SourceRoot $stackyAgentsSource -StackyHomeDir $releaseStackyHomeDir
if ($stackyAgentsCount -gt 0) {
    Write-OK "Stacky/agents incluidos: $stackyAgentsCount agentes desde $stackyAgentsSource (con manifest.json + checksum)"

    Write-Step "Validando Stacky/agents (check_deploy_agents.py)"
    $checkScript = Join-Path $deploymentDir "check_deploy_agents.py"
    if (Test-Path $checkScript) {
        Invoke-BuildPython -PythonArgs @($checkScript, "--stacky-home", $releaseStackyHomeDir)
        if ($LASTEXITCODE -ne 0) {
            throw "check_deploy_agents.py reportó problemas en Stacky/agents. Cancelo el release."
        }
        Write-OK "Stacky/agents validado (manifest + checksums)"
    } else {
        Write-Warn "check_deploy_agents.py no encontrado; omitiendo validación canonical."
    }
} else {
    if ($RequireInstaller) {
        throw "Stacky/agents está vacío y RequireInstaller=true. Cancelo el release."
    }
    Write-Warn "Stacky/agents quedó vacío. El backend no importará fuentes legacy en runtime."
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
Copy-Item -LiteralPath (Join-Path $deploymentDir "release_assets\Setup-Copilot.ps1") -Destination (Join-Path $releaseDir "Setup-Copilot.ps1") -Force
Copy-Item -LiteralPath (Join-Path $deploymentDir "release_assets\SETUP-COPILOT.bat") -Destination (Join-Path $releaseDir "SETUP-COPILOT.bat") -Force
Copy-Item -LiteralPath (Join-Path $deploymentDir "release_assets\Install-CLI-Runtimes.ps1") -Destination (Join-Path $releaseDir "Install-CLI-Runtimes.ps1") -Force
Copy-Item -LiteralPath (Join-Path $deploymentDir "release_assets\INSTALL-CLI-RUNTIMES.bat") -Destination (Join-Path $releaseDir "INSTALL-CLI-RUNTIMES.bat") -Force
Copy-Item -LiteralPath (Join-Path $deploymentDir "release_assets\Enable-WinRM.ps1") -Destination (Join-Path $releaseDir "Enable-WinRM.ps1") -Force
Copy-Item -LiteralPath (Join-Path $deploymentDir "release_assets\Enable-WinRM.bat") -Destination (Join-Path $releaseDir "Enable-WinRM.bat") -Force
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
    stacky_home_dir = "Stacky"
    stacky_agents_dir = "Stacky/agents"
    stacky_agents_count = $stackyAgentsCount
    config_exported = [bool]$ExportConfig
    data_dir = "data"
    projects_dir = "projects"
    installer = "INSTALL.ps1"
    launcher = "START.bat"
    smoke_test = "smoke_test.ps1"
    operator_guide = "OPERATOR_GUIDE.md"
}

Write-Utf8NoBom -Path (Join-Path $releaseDir "release-manifest.json") -Value ($manifest | ConvertTo-Json -Depth 5)
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
