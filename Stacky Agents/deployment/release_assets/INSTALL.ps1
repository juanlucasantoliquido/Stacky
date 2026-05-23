#Requires -Version 5.1
<#
.SYNOPSIS
    Post-instalador local de Stacky Agents.
.DESCRIPTION
    Prepara carpetas persistentes, crea accesos directos e instala la extension
    VS Code mas reciente incluida en el paquete.
#>

$ErrorActionPreference = "Stop"
$STACKY_ROOT = $PSScriptRoot

function Write-Step { param([string]$Message) Write-Host "`n>> $Message" -ForegroundColor Cyan }
function Write-OK { param([string]$Message) Write-Host "   [OK] $Message" -ForegroundColor Green }
function Write-Warn { param([string]$Message) Write-Host "   [WARN] $Message" -ForegroundColor Yellow }

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " Stacky Agents - Instalador Local" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

Write-Step "Validando artefactos"
if (-not (Test-Path (Join-Path $STACKY_ROOT "backend\stacky-backend.exe"))) {
    throw "No se encontro backend\stacky-backend.exe. El paquete no es un release congelado."
}
if (-not (Test-Path (Join-Path $STACKY_ROOT "frontend\dist\index.html"))) {
    throw "No se encontro frontend\dist\index.html. El paquete no incluye el frontend compilado."
}
Write-OK "Artefactos presentes"

Write-Step "Preparando carpetas persistentes"
foreach ($dir in @("data", "projects")) {
    $path = Join-Path $STACKY_ROOT $dir
    if (-not (Test-Path $path)) {
        New-Item -ItemType Directory -Path $path -Force | Out-Null
        Write-OK "$dir creado"
    } else {
        Write-OK "$dir preservado"
    }
}

$envFile = Join-Path $STACKY_ROOT "backend\.env"
$envExample = Join-Path $STACKY_ROOT "backend\.env.example"
if (-not (Test-Path $envFile) -and (Test-Path $envExample)) {
    Copy-Item -LiteralPath $envExample -Destination $envFile -Force
    Write-OK ".env creado desde .env.example"
}

Write-Step "Instalando extension VS Code (opcional)"
$codeCmd = $null
foreach ($candidate in @("code", "$env:LOCALAPPDATA\Programs\Microsoft VS Code\bin\code.cmd")) {
    try {
        $result = & $candidate --version 2>&1 | Select-Object -First 1
        if ($result -match "\d+\.\d+\.\d+") {
            $codeCmd = $candidate
            break
        }
    } catch {
    }
}

$vsix = Get-ChildItem -Path (Join-Path $STACKY_ROOT "vscode_extension") -Filter "stacky-agents-*.vsix" -File -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime, Name |
    Select-Object -Last 1

if ($codeCmd -and $vsix) {
    try {
        & $codeCmd --install-extension $vsix.FullName --force | Out-Null
        Write-OK "Extension instalada: $($vsix.Name)"
    } catch {
        Write-Warn "No se pudo instalar la extension automaticamente."
    }
} else {
    Write-Warn "VS Code o VSIX no disponible. Se omite la instalacion de la extension."
}

Write-Step "Creando accesos directos"
try {
    $shell = New-Object -ComObject WScript.Shell
    $targets = @(
        Join-Path ([Environment]::GetFolderPath("Desktop")) "Stacky Agents.lnk",
        Join-Path ([Environment]::GetFolderPath("Programs")) "Stacky Agents.lnk"
    )
    foreach ($shortcutPath in $targets) {
        $shortcut = $shell.CreateShortcut($shortcutPath)
        $shortcut.TargetPath = Join-Path $STACKY_ROOT "START.bat"
        $shortcut.WorkingDirectory = $STACKY_ROOT
        $shortcut.IconLocation = Join-Path $STACKY_ROOT "backend\stacky-backend.exe"
        $shortcut.Save()
    }
    Write-OK "Accesos directos listos"
} catch {
    Write-Warn "No se pudieron crear los accesos directos."
}

Write-Step "Smoke test post-instalacion"
$smokeTest = Join-Path $STACKY_ROOT "smoke_test.ps1"
if (-not (Test-Path $smokeTest)) {
    throw "No se encontro smoke_test.ps1. El paquete no puede validarse."
}
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $smokeTest
if ($LASTEXITCODE -ne 0) {
    throw "Smoke test post-instalacion fallido."
}
Write-OK "Smoke test post-instalacion OK"

Write-Host ""
Write-Host "Instalacion finalizada." -ForegroundColor Green
Write-Host "Siguiente paso: ejecutar START.bat" -ForegroundColor Green
Write-Host ""
