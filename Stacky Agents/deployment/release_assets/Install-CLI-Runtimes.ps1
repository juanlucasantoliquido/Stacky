#Requires -Version 5.1
<#
.SYNOPSIS
    Instala los runtimes CLI que Stacky Agents necesita: claude y codex.
.DESCRIPTION
    1. Verifica si Node.js / npm estan disponibles; intenta instalarlos con winget si no.
    2. Instala @anthropic-ai/claude-code globalmente  -> comando "claude"
    3. Instala @openai/codex globalmente              -> comando "codex"
    4. Verifica que ambos respondan a --version.

    Se ejecuta normalmente via INSTALL-CLI-RUNTIMES.bat (doble clic).
#>

$ErrorActionPreference = "Stop"

function Write-Step { param([string]$Message) Write-Host "`n>> $Message" -ForegroundColor Cyan }
function Write-OK   { param([string]$Message) Write-Host "   [OK] $Message" -ForegroundColor Green }
function Write-Warn { param([string]$Message) Write-Host "   [WARN] $Message" -ForegroundColor Yellow }
function Write-Err  { param([string]$Message) Write-Host "   [ERROR] $Message" -ForegroundColor Red }

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " Stacky Agents - Instalar Runtimes CLI (claude + codex)" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# ---------------------------------------------------------------------------
# 1. Localizar npm
# ---------------------------------------------------------------------------
Write-Step "Verificando Node.js / npm"

function Resolve-Npm {
    $candidates = @(
        "npm",
        (Join-Path $env:ProgramFiles "nodejs\npm.cmd"),
        (Join-Path ${env:ProgramFiles(x86)} "nodejs\npm.cmd"),
        (Join-Path $env:APPDATA "npm\npm.cmd"),
        (Join-Path $env:LOCALAPPDATA "Programs\nodejs\npm.cmd")
    )
    foreach ($c in $candidates) {
        if (-not $c) { continue }
        try {
            $v = & $c --version 2>$null | Select-Object -First 1
            if ($v -match "^\d+\.\d+") { return $c }
        } catch {}
    }
    return $null
}

$npm = Resolve-Npm
if (-not $npm) {
    Write-Warn "npm no encontrado. Intentando instalar Node.js con winget..."
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        try {
            & winget install --id OpenJS.NodeJS.LTS -e --silent --accept-source-agreements --accept-package-agreements
        } catch {
            Write-Warn "winget devolvio un error, se reintenta la deteccion igualmente."
        }
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" +
                    [System.Environment]::GetEnvironmentVariable("Path","User")
        $npm = Resolve-Npm
    } else {
        Write-Warn "winget no esta disponible en esta maquina."
    }
}

if (-not $npm) {
    Write-Err "No se encontro npm. Instala Node.js LTS manualmente desde https://nodejs.org y volve a ejecutar este script."
    exit 1
}

$npmVersion = & $npm --version 2>$null | Select-Object -First 1
Write-OK "npm disponible ($npmVersion): $npm"

# ---------------------------------------------------------------------------
# 2. Instalar @anthropic-ai/claude-code  ->  claude
# ---------------------------------------------------------------------------
Write-Step "Instalando @anthropic-ai/claude-code (claude CLI)"

try {
    & $npm install -g "@anthropic-ai/claude-code"
    if ($LASTEXITCODE -ne 0) { throw "npm exito con codigo $LASTEXITCODE" }
    Write-OK "Paquete instalado"
} catch {
    Write-Err "Fallo la instalacion de @anthropic-ai/claude-code: $($_.Exception.Message)"
    exit 1
}

# ---------------------------------------------------------------------------
# 3. Instalar @openai/codex  ->  codex
# ---------------------------------------------------------------------------
Write-Step "Instalando @openai/codex (codex CLI)"

try {
    & $npm install -g "@openai/codex"
    if ($LASTEXITCODE -ne 0) { throw "npm exito con codigo $LASTEXITCODE" }
    Write-OK "Paquete instalado"
} catch {
    Write-Err "Fallo la instalacion de @openai/codex: $($_.Exception.Message)"
    exit 1
}

# Refrescar PATH para que los nuevos binarios sean visibles en este proceso
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" +
            [System.Environment]::GetEnvironmentVariable("Path","User")

# ---------------------------------------------------------------------------
# 4. Verificacion final
# ---------------------------------------------------------------------------
Write-Step "Verificando runtimes instalados"

$allOk = $true
foreach ($bin in @("claude", "codex")) {
    try {
        $v = & $bin --version 2>$null | Select-Object -First 1
        if ($v) {
            Write-OK "$bin $v"
        } else {
            Write-Warn "$bin no devolvio version. Puede ser necesario abrir una nueva terminal."
            $allOk = $false
        }
    } catch {
        Write-Warn "$bin no esta disponible en el PATH actual. Abri una nueva terminal y verifica con '$bin --version'."
        $allOk = $false
    }
}

Write-Host ""
if ($allOk) {
    Write-Host "Instalacion completa. Podes iniciar Stacky Agents con START.bat." -ForegroundColor Green
} else {
    Write-Host "Instalacion realizada. Abri una nueva terminal y ejecuta START.bat." -ForegroundColor Yellow
}
Write-Host ""
