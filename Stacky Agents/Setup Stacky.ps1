# Setup Stacky.ps1
# Ejecutar UNA VEZ en la maquina del usuario para preparar el entorno.
# Requisitos: VS Code instalado con GitHub Copilot activo.

$ErrorActionPreference = "Stop"
$HERE = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host ""
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host "   STACKY AGENTS - Setup inicial"                  -ForegroundColor Cyan
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host ""

# -- 1. Instalar extension VS Code -------------------------------------------
$vsix = Get-ChildItem (Join-Path $HERE "stacky-agents-*.vsix") |
        Sort-Object Name -Descending |
        Select-Object -First 1

if (-not $vsix) {
    Write-Host "[!] No se encontro el archivo .vsix en esta carpeta." -ForegroundColor Red
    Write-Host "    Instalalo manualmente: VS Code > Extensions > ... > Install from VSIX" -ForegroundColor Yellow
} else {
    Write-Host "[1/3] Instalando extension VS Code: $($vsix.Name)..." -ForegroundColor Cyan
    try {
        & code --install-extension $vsix.FullName --force
        Write-Host "      OK - Extension instalada" -ForegroundColor Green
    } catch {
        Write-Host "      ERROR: No se pudo ejecutar 'code'." -ForegroundColor Red
        Write-Host "      Asegurate de que VS Code este instalado y 'code' en el PATH." -ForegroundColor Yellow
        Write-Host "      O instalala manualmente: VS Code > Extensions > ... > Install from VSIX" -ForegroundColor Yellow
    }
}

# -- 2. Crear .env ------------------------------------------------------------
$envFile = Join-Path $HERE ".env"
if (Test-Path $envFile) {
    Write-Host "[2/3] .env ya existe - no se sobreescribe." -ForegroundColor Gray
} else {
    $envExample = Join-Path $HERE ".env.example"
    if (Test-Path $envExample) {
        Copy-Item $envExample $envFile
        Write-Host "[2/3] Creado .env desde .env.example" -ForegroundColor Green
        Write-Host "      *** IMPORTANTE: Edita .env y configura ADO_PAT y los datos de tu proyecto ***" -ForegroundColor Yellow
    } else {
        Write-Host "[2/3] No se encontro .env.example - crea el .env manualmente." -ForegroundColor Yellow
    }
}

# -- 3. Instrucciones finales -------------------------------------------------
Write-Host ""
Write-Host "[3/3] Pasos finales:" -ForegroundColor Cyan
Write-Host "      1. Edita el archivo .env con tus credenciales (ADO_PAT, proyecto, etc.)" -ForegroundColor White
Write-Host "      2. Reinicia VS Code para activar la extension Stacky" -ForegroundColor White
Write-Host "      3. En VS Code, abre un workspace con tu proyecto" -ForegroundColor White
Write-Host "      4. Ejecuta 'Iniciar Stacky.bat' para arrancar la aplicacion" -ForegroundColor White
Write-Host "      5. La app se abrira en http://localhost:5050" -ForegroundColor White
Write-Host ""
Write-Host "Para mas informacion consulta README.md" -ForegroundColor Gray
Write-Host ""
Read-Host "Pulsa Enter para cerrar"
