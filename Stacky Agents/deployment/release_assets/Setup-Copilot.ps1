#Requires -Version 5.1
<#
.SYNOPSIS
    Configura GitHub Copilot para Stacky Agents en la maquina del desarrollador.
.DESCRIPTION
    1. Instala GitHub CLI (gh) si no esta presente.
    2. Autentica gh con GitHub (login web/device).
    3. Guarda el token en backend\.copilot_token para que el backend congelado
       lo encuentre sin depender del PATH.
    4. Instala la extension VS Code (bridge) incluida en el paquete.
    5. Verifica el estado final.

    Se ejecuta normalmente via SETUP-COPILOT.bat (doble clic).
#>

$ErrorActionPreference = "Stop"
$STACKY_ROOT = Split-Path -Parent $PSScriptRoot
if (-not $STACKY_ROOT -or -not (Test-Path (Join-Path $STACKY_ROOT "backend"))) {
    # PSScriptRoot ya es la raiz del deploy cuando el script vive en la raiz
    $STACKY_ROOT = $PSScriptRoot
}

function Write-Step { param([string]$Message) Write-Host "`n>> $Message" -ForegroundColor Cyan }
function Write-OK   { param([string]$Message) Write-Host "   [OK] $Message" -ForegroundColor Green }
function Write-Warn { param([string]$Message) Write-Host "   [WARN] $Message" -ForegroundColor Yellow }
function Write-Err  { param([string]$Message) Write-Host "   [ERROR] $Message" -ForegroundColor Red }

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " Stacky Agents - Setup GitHub Copilot + Bridge VS Code" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# ---------------------------------------------------------------------------
# 1. Localizar / instalar GitHub CLI
# ---------------------------------------------------------------------------
function Resolve-Gh {
    $candidates = @(
        "gh",
        (Join-Path $env:ProgramFiles "GitHub CLI\gh.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "GitHub CLI\gh.exe"),
        (Join-Path $env:LOCALAPPDATA "GitHubCLI\gh.exe"),
        (Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Links\gh.exe")
    )
    foreach ($c in $candidates) {
        if (-not $c) { continue }
        try {
            $v = & $c --version 2>$null | Select-Object -First 1
            if ($v -match "gh version") { return $c }
        } catch {}
    }
    return $null
}

Write-Step "Verificando GitHub CLI (gh)"
$gh = Resolve-Gh
if (-not $gh) {
    Write-Warn "gh no encontrado. Intentando instalar con winget..."
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        try {
            & winget install --id GitHub.cli -e --silent --accept-source-agreements --accept-package-agreements
        } catch {
            Write-Warn "winget devolvio un error, se reintenta la deteccion igualmente."
        }
        # Refrescar PATH del proceso actual
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + `
                    [System.Environment]::GetEnvironmentVariable("Path","User")
        $gh = Resolve-Gh
    } else {
        Write-Warn "winget no esta disponible en esta maquina."
    }
}

if (-not $gh) {
    Write-Err "No se pudo instalar GitHub CLI automaticamente."
    Write-Host "        Instalalo manualmente desde: https://cli.github.com/ y volve a ejecutar este setup." -ForegroundColor Yellow
    exit 1
}
Write-OK "gh disponible: $gh"

# ---------------------------------------------------------------------------
# 2. Autenticar gh
# ---------------------------------------------------------------------------
Write-Step "Verificando autenticacion de GitHub"
$authed = $false
try {
    & $gh auth status 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { $authed = $true }
} catch {}

if ($authed) {
    Write-OK "Ya hay una sesion de GitHub activa."
} else {
    Write-Host "   Se abrira el login de GitHub. Segui las instrucciones en la consola/navegador." -ForegroundColor Yellow
    Write-Host "   (Se solicitara un codigo de dispositivo y se abrira https://github.com/login/device)" -ForegroundColor Yellow
    try {
        & $gh auth login --hostname github.com --git-protocol https --web
    } catch {
        Write-Err "El login de gh fallo o fue cancelado."
        exit 1
    }
    & $gh auth status 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Err "No quedo autenticado. Volve a ejecutar el setup."
        exit 1
    }
    Write-OK "Autenticacion completada."
}

# ---------------------------------------------------------------------------
# 3. Guardar token para el backend congelado
# ---------------------------------------------------------------------------
Write-Step "Guardando token para Stacky Agents"
$tokenFile = Join-Path $STACKY_ROOT "backend\.copilot_token"
try {
    $token = (& $gh auth token 2>$null | Select-Object -First 1)
    if ($token -and $token.Trim().Length -gt 0) {
        # Sin BOM para que el backend lo lea limpio
        [System.IO.File]::WriteAllText($tokenFile, $token.Trim(), (New-Object System.Text.UTF8Encoding($false)))
        Write-OK "Token guardado en backend\.copilot_token"
    } else {
        Write-Warn "No se pudo obtener el token via 'gh auth token'. El backend intentara usar gh en runtime."
    }
} catch {
    Write-Warn "No se pudo escribir el token: $($_.Exception.Message)"
}

# ---------------------------------------------------------------------------
# 4. Instalar extension VS Code (bridge)
# ---------------------------------------------------------------------------
Write-Step "Instalando extension VS Code (bridge)"
$codeCmd = $null
foreach ($candidate in @(
        "code",
        (Join-Path $env:LOCALAPPDATA "Programs\Microsoft VS Code\bin\code.cmd"),
        (Join-Path $env:ProgramFiles "Microsoft VS Code\bin\code.cmd"))) {
    try {
        $result = & $candidate --version 2>$null | Select-Object -First 1
        if ($result -match "\d+\.\d+\.\d+") { $codeCmd = $candidate; break }
    } catch {}
}

$vsixDir = Join-Path $STACKY_ROOT "vscode_extension"
$vsix = $null
if (Test-Path $vsixDir) {
    $vsix = Get-ChildItem -Path $vsixDir -Filter "stacky-agents-*.vsix" -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime, Name | Select-Object -Last 1
}

if ($codeCmd -and $vsix) {
    try {
        & $codeCmd --install-extension $vsix.FullName --force | Out-Null
        Write-OK "Extension instalada: $($vsix.Name)"
        Write-Host "   Recorda recargar VS Code: Ctrl+Shift+P -> Developer: Reload Window" -ForegroundColor Yellow
    } catch {
        Write-Warn "No se pudo instalar la extension automaticamente: $($_.Exception.Message)"
    }
} elseif (-not $codeCmd) {
    Write-Warn "VS Code no esta en el PATH. Abri VS Code una vez o instala 'code' en PATH y reintenta."
    if ($vsix) { Write-Host "   VSIX disponible en: $($vsix.FullName)" -ForegroundColor Yellow }
} else {
    Write-Warn "No se encontro ningun .vsix en $vsixDir"
}

# ---------------------------------------------------------------------------
# 5. Resumen
# ---------------------------------------------------------------------------
Write-Step "Verificacion final"
& $gh auth status 2>&1 | ForEach-Object { Write-Host "   $_" }
if (Test-Path $tokenFile) { Write-OK "backend\.copilot_token presente" } else { Write-Warn "backend\.copilot_token ausente" }

Write-Host ""
Write-Host "Setup de Copilot finalizado." -ForegroundColor Green
Write-Host "Siguiente paso: abri VS Code en tu proyecto, recargalo, y ejecuta START.bat." -ForegroundColor Green
Write-Host ""
