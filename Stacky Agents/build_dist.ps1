# build_dist.ps1
# Portado desde WS2 (2026-05-24) -- P3.1.
# Empaqueta Stacky Agents como distributable sin dependencias de Python ni Node.
#
# Requisitos previos (solo en la máquina de build):
#   - Node.js + npm instalados
#   - Python .venv en backend\.venv\ (ya existente)
#   - PyInstaller: se instala automáticamente si no está
#
# Resultado: C:\AIS\Stacky\
#   stacky.exe          ← doble clic para arrancar
#   ui\                 ← frontend React compilado
#   data\               ← base de datos y config
#   projects\           ← copiar aquí los proyectos
#   help\               ← ayuda Markdown
#   .env.example        ← renombrar a .env y configurar

$ErrorActionPreference = "Stop"
$ROOT      = Split-Path -Parent $MyInvocation.MyCommand.Path
$BACK      = Join-Path $ROOT "backend"
$FRONT     = Join-Path $ROOT "frontend"
$PYTHON    = Join-Path $BACK ".venv\Scripts\python.exe"
$PIP       = Join-Path $BACK ".venv\Scripts\pip.exe"
$DIST_BASE = "C:\AIS"          # carpeta padre de la distribución
$OUT       = "$DIST_BASE\Stacky"  # destino final

function Step($n, $msg) { Write-Host "`n[$n/5] $msg" -ForegroundColor Cyan }

# ── 1. Build frontend ────────────────────────────────────────────────────────
Step 1 "Building React frontend..."
Push-Location $FRONT
    if (-not (Test-Path "node_modules")) {
        Write-Host "  Installing npm dependencies..." -ForegroundColor Gray
        npm ci --silent
    }
    $env:VITE_API_BASE = "http://localhost:5050"
    npm run build
    if (-not (Test-Path "dist\index.html")) {
        throw "Frontend build failed: dist\index.html not found"
    }
    Write-Host "  Frontend built OK" -ForegroundColor Green
Pop-Location

# ── 2. Instalar PyInstaller en el venv ──────────────────────────────────────
Step 2 "Ensuring PyInstaller is installed..."
& $PIP install pyinstaller --quiet
Write-Host "  PyInstaller OK" -ForegroundColor Green

# ── 3. Ejecutar PyInstaller ──────────────────────────────────────────────────
Step 3 "Running PyInstaller (this may take a few minutes)..."

# Asegurarse de que C:\AIS existe
if (-not (Test-Path $DIST_BASE)) {
    New-Item -ItemType Directory -Path $DIST_BASE | Out-Null
    Write-Host "  Creado directorio $DIST_BASE" -ForegroundColor Gray
}

# Limpiar destino previo para evitar mezcla de versiones
if (Test-Path $OUT) {
    Write-Host "  Limpiando distribucion anterior en $OUT ..." -ForegroundColor Gray
    Remove-Item -Recurse -Force $OUT
}

Push-Location $BACK
    # --distpath pone la salida en C:\AIS\stacky\ (nombre viene del spec)
    & $PYTHON -m PyInstaller stacky.spec --clean --noconfirm --distpath $DIST_BASE
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }
    Write-Host "  PyInstaller OK" -ForegroundColor Green
Pop-Location

# ── 4. Renombrar stacky → Stacky ─────────────────────────────────────────────
Step 4 "Moving output to $OUT ..."
$pyiOut = Join-Path $DIST_BASE "stacky"
if (Test-Path $pyiOut) {
    Rename-Item -Path $pyiOut -NewName "Stacky"
    Write-Host "  Movido a $OUT" -ForegroundColor Green
} elseif (-not (Test-Path $OUT)) {
    throw "PyInstaller output not found at $pyiOut nor $OUT"
}

# ── 5. Post-proceso ──────────────────────────────────────────────────────────
Step 5 "Finalizing distribution package..."

# Copiar .env.example al dist si no fue incluido por el spec
$envExample = Join-Path $BACK ".env.example"
$envDest    = Join-Path $OUT  ".env.example"
if ((Test-Path $envExample) -and (-not (Test-Path $envDest))) {
    Copy-Item $envExample $envDest
}

# Copiar la extensión VS Code (.vsix) más reciente al dist
$vsixSrc = Get-ChildItem (Join-Path $ROOT "vscode_extension\*.vsix") |
           Sort-Object Name -Descending |
           Select-Object -First 1
if ($vsixSrc) {
    Copy-Item $vsixSrc.FullName (Join-Path $OUT $vsixSrc.Name)
    Write-Host "  Included $($vsixSrc.Name)" -ForegroundColor Gray
} else {
    Write-Host "  WARNING: No .vsix found in vscode_extension\" -ForegroundColor Yellow
}

# Copiar script de setup para el usuario final
Copy-Item (Join-Path $ROOT "Setup Stacky.ps1") (Join-Path $OUT "Setup Stacky.ps1")

# Crear launcher .bat para el usuario final
$launcher = @"
@echo off
title Stacky Agents
echo Iniciando Stacky Agents en http://localhost:5050 ...
stacky.exe
"@
Set-Content -Path (Join-Path $OUT "Iniciar Stacky.bat") -Value $launcher -Encoding UTF8

Write-Host ""
Write-Host "=================================================" -ForegroundColor Green
Write-Host "  Build completado!"                               -ForegroundColor Green
Write-Host "  Carpeta: $OUT"                                   -ForegroundColor Yellow
Write-Host "=================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Para distribuir:" -ForegroundColor White
Write-Host "  1. Comprimir C:\AIS\Stacky\ en un .zip" -ForegroundColor White
Write-Host "  2. Usuario ejecuta 'Setup Stacky.ps1' (instala .vsix + crea .env)" -ForegroundColor White
Write-Host "  3. Usuario edita .env con sus credenciales" -ForegroundColor White
Write-Host "  4. Usuario reinicia VS Code y ejecuta 'Iniciar Stacky.bat'" -ForegroundColor White
