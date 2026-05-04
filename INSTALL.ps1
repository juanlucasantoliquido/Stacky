#Requires -Version 5.1
<#
.SYNOPSIS
    Stacky Agents — Instalador portable
.DESCRIPTION
    Instala todas las dependencias necesarias para ejecutar Stacky Agents
    en cualquier máquina Windows. Solo requiere PowerShell 5.1+.
    Re-ejecutable (idempotente): no sobreescribe lo que ya está instalado.
.EXAMPLE
    # Desde PowerShell (con permiso de ejecución):
    .\INSTALL.ps1
    # Si hay restricción de ejecución:
    powershell -ExecutionPolicy Bypass -File .\INSTALL.ps1
#>

$ErrorActionPreference = "Stop"
$STACKY_ROOT = $PSScriptRoot

# ── Helpers de output ──────────────────────────────────────────────────────
function Write-Step { param($msg) Write-Host "`n  >> $msg" -ForegroundColor Cyan }
function Write-OK   { param($msg) Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Warn { param($msg) Write-Host "  [!!] $msg" -ForegroundColor Yellow }
function Write-Err  { param($msg) Write-Host "  [ERR] $msg" -ForegroundColor Red; $script:hasErrors = $true }
function Write-Info { param($msg) Write-Host "       $msg" -ForegroundColor Gray }

$script:hasErrors = $false

Write-Host ""
Write-Host "  ================================================================" -ForegroundColor Cyan
Write-Host "   Stacky Agents — Instalador Portable" -ForegroundColor Cyan
Write-Host "   Directorio: $STACKY_ROOT" -ForegroundColor Gray
Write-Host "  ================================================================" -ForegroundColor Cyan

# ── 1. Verificar / Instalar Python 3.11+ ──────────────────────────────────
Write-Step "Python 3.11+"
$pythonCmd = $null
foreach ($cmd in @("python", "python3", "py -3")) {
    try {
        $ver = Invoke-Expression "$cmd --version 2>&1"
        if ($ver -match "Python (\d+)\.(\d+)") {
            $major = [int]$Matches[1]; $minor = [int]$Matches[2]
            if ($major -eq 3 -and $minor -ge 11) {
                $pythonCmd = $cmd.Split(" ")[0]
                Write-OK "Python $major.$minor encontrado ($cmd)"
                break
            } else {
                Write-Warn "Python $major.$minor encontrado pero se requiere 3.11+"
            }
        }
    } catch {}
}
if (-not $pythonCmd) {
    Write-Warn "Python 3.11+ no encontrado. Instalando con winget..."
    try {
        winget install --id Python.Python.3.11 --silent --accept-package-agreements --accept-source-agreements
        # Refrescar PATH
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
        $pythonCmd = "python"
        Write-OK "Python instalado via winget."
        Write-Warn "Si el PATH no se actualizó, cierra y reabre PowerShell y vuelve a ejecutar INSTALL.ps1"
    } catch {
        Write-Err "No se pudo instalar Python automáticamente."
        Write-Info "Instala Python 3.11+ desde: https://www.python.org/downloads/"
        Write-Info "Marca 'Add Python to PATH' durante la instalación."
        Read-Host "`n  Presiona Enter para salir"
        exit 1
    }
}

# ── 2. Verificar / Instalar Node.js 18+ ───────────────────────────────────
Write-Step "Node.js 18+ y npm"
$nodeOK = $false
try {
    $nodeVer = node --version 2>&1
    if ($nodeVer -match "v(\d+)") {
        $nodeMajor = [int]$Matches[1]
        if ($nodeMajor -ge 18) {
            $nodeOK = $true
            $npmVer = npm --version 2>&1
            Write-OK "Node.js $nodeVer  /  npm $npmVer"
        } else {
            Write-Warn "Node.js $nodeVer encontrado pero se requiere v18+"
        }
    }
} catch {}
if (-not $nodeOK) {
    Write-Warn "Node.js 18+ no encontrado. Instalando con winget..."
    try {
        winget install --id OpenJS.NodeJS.LTS --silent --accept-package-agreements --accept-source-agreements
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
        Write-OK "Node.js instalado via winget."
        Write-Warn "Si el PATH no se actualizó, cierra y reabre PowerShell y vuelve a ejecutar INSTALL.ps1"
    } catch {
        Write-Err "No se pudo instalar Node.js automáticamente."
        Write-Info "Instala Node.js 18 LTS desde: https://nodejs.org/"
        Read-Host "`n  Presiona Enter para salir"
        exit 1
    }
}

# ── 3. Verificar / Instalar Git ───────────────────────────────────────────
Write-Step "Git"
$gitOK = $false
try {
    $gitVer = git --version 2>&1
    if ($gitVer -match "git version") {
        $gitOK = $true
        Write-OK "$gitVer"
    }
} catch {}
if (-not $gitOK) {
    Write-Warn "Git no encontrado. Instalando con winget..."
    try {
        winget install --id Git.Git --silent --accept-package-agreements --accept-source-agreements
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
        Write-OK "Git instalado via winget."
    } catch {
        Write-Warn "No se pudo instalar Git. Algunas funciones de SCM no estarán disponibles."
    }
}

# ── 4. Verificar / Instalar gh CLI (opcional) ─────────────────────────────
Write-Step "GitHub CLI (gh)  [opcional]"
$ghOK = $false
try {
    $ghVer = gh --version 2>&1
    if ($ghVer -match "gh version") {
        $ghOK = $true
        Write-OK ($ghVer | Select-Object -First 1)
    }
} catch {}
if (-not $ghOK) {
    Write-Warn "gh CLI no encontrado. Intentando instalar con winget..."
    try {
        winget install --id GitHub.cli --silent --accept-package-agreements --accept-source-agreements
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
        Write-OK "gh CLI instalado via winget."
        Write-Info "Ejecuta 'gh auth login' para autenticar GitHub."
        $ghOK = $true
    } catch {
        Write-Warn "gh CLI no se pudo instalar. Las funciones de GitHub requerirán autenticación manual."
        Write-Info "Instala manualmente desde: https://cli.github.com/"
    }
}

# ── 5. Verificar / Instalar VS Code (opcional) ────────────────────────────
Write-Step "VS Code  [opcional — requerido para integración Copilot]"
$codeCmd = $null
foreach ($candidate in @("code", "$env:LOCALAPPDATA\Programs\Microsoft VS Code\bin\code.cmd")) {
    try {
        $v = Invoke-Expression "`"$candidate`" --version 2>&1" | Select-Object -First 1
        if ($v -match "\d+\.\d+\.\d+") {
            $codeCmd = $candidate
            Write-OK "VS Code $v"
            break
        }
    } catch {}
}
if (-not $codeCmd) {
    Write-Warn "VS Code no encontrado."
    Write-Info "Si usas integración con GitHub Copilot, instala VS Code desde: https://code.visualstudio.com/"
}

# ── 6. Crear virtualenv del backend ──────────────────────────────────────
$backendDir   = Join-Path $STACKY_ROOT "Stacky Agents\backend"
$venvDir      = Join-Path $backendDir ".venv"
$venvPython   = Join-Path $venvDir "Scripts\python.exe"
$venvPip      = Join-Path $venvDir "Scripts\pip.exe"

Write-Step "Virtualenv del backend"
if (-not (Test-Path $venvPython)) {
    Write-Info "Creando virtualenv en '$venvDir'..."
    & $pythonCmd -m venv $venvDir
    if (-not (Test-Path $venvPython)) {
        Write-Err "Falló la creación del virtualenv."
        Read-Host "`n  Presiona Enter para salir"
        exit 1
    }
    Write-OK "Virtualenv creado"
} else {
    Write-OK "Virtualenv ya existe"
}

# ── 7. Instalar dependencias del backend ──────────────────────────────────
Write-Step "Dependencias del backend (Flask, SQLAlchemy, etc.)"
$backendReq = Join-Path $backendDir "requirements.txt"
Write-Info "pip install -r requirements.txt ..."
& $venvPip install -r $backendReq --quiet --upgrade 2>&1 | Out-Null
Write-OK "Backend deps instaladas"

# ── 8. Instalar dependencias del pipeline / Playwright ────────────────────
$pipelineReq = Join-Path $STACKY_ROOT "Stacky pipeline\requirements.txt"
if (Test-Path $pipelineReq) {
    Write-Step "Dependencias del pipeline (Playwright, pytest, etc.)"
    Write-Info "pip install -r pipeline/requirements.txt ..."
    & $venvPip install -r $pipelineReq --quiet 2>&1 | Out-Null
    $playwrightExe = Join-Path $venvDir "Scripts\playwright.exe"
    if (Test-Path $playwrightExe) {
        Write-Info "Instalando navegador Chromium para Playwright..."
        & $playwrightExe install chromium 2>&1 | Out-Null
        Write-OK "Playwright + Chromium instalados"
    }
}

# ── 9. Instalar dependencias QA UAT Agent ────────────────────────────────
$qaReq = Join-Path $STACKY_ROOT "Stacky tools\QA UAT Agent\requirements.txt"
if (Test-Path $qaReq) {
    Write-Step "Dependencias QA UAT Agent"
    & $venvPip install -r $qaReq --quiet 2>&1 | Out-Null
    Write-OK "QA UAT Agent deps instaladas"
}

# ── 10. Dependencias del frontend ─────────────────────────────────────────
$frontendDir = Join-Path $STACKY_ROOT "Stacky Agents\frontend"
Write-Step "Dependencias del frontend (React, Vite, TypeScript)"
if (-not (Test-Path (Join-Path $frontendDir "node_modules"))) {
    Write-Info "npm install (puede tardar unos minutos)..."
    Push-Location $frontendDir
    try {
        npm install --silent
        Write-OK "Frontend deps instaladas"
    } catch {
        Write-Err "Falló npm install en el frontend."
        Write-Info "Intenta manualmente: cd `"$frontendDir`" && npm install"
    } finally {
        Pop-Location
    }
} else {
    Write-OK "Frontend deps ya instaladas"
}

# ── 11. Instalar extensión VS Code (si existe y VS Code disponible) ────────
if ($codeCmd) {
    $vsixPath = Join-Path $STACKY_ROOT "Stacky Agents\vscode_extension"
    $vsix = Get-ChildItem -Path $vsixPath -Filter "*.vsix" -ErrorAction SilentlyContinue | Select-Object -Last 1
    if ($vsix) {
        Write-Step "Extensión VS Code Stacky Agents"
        Write-Info "Instalando $($vsix.Name)..."
        try {
            & $codeCmd --install-extension $vsix.FullName --force 2>&1 | Out-Null
            Write-OK "Extensión VS Code instalada: $($vsix.Name)"
        } catch {
            Write-Warn "No se pudo instalar la extensión VS Code automáticamente."
        }
    }
}

# ── 12. Crear .env si no existe, con setup interactivo ───────────────────
$envFile    = Join-Path $backendDir ".env"
$envExample = Join-Path $backendDir ".env.example"
Write-Step "Configuración del backend (.env)"
if (-not (Test-Path $envFile)) {
    if (Test-Path $envExample) {
        Copy-Item $envExample $envFile
        Write-OK ".env creado desde .env.example"
    } else {
        Write-Warn ".env.example no encontrado — creando .env mínimo"
        @"
ADO_ORG=
ADO_PROJECT=
ADO_PAT=
DATABASE_URL=sqlite:///./data/stacky_agents.db
LLM_BACKEND=mock
LLM_MODEL=claude-sonnet-4-6
LOG_LEVEL=INFO
ALLOWED_ORIGINS=http://localhost:5173
PORT=5050
"@ | Out-File -FilePath $envFile -Encoding utf8
    }

    Write-Host ""
    Write-Host "  ── Configuración Azure DevOps ──────────────────────────" -ForegroundColor Cyan
    Write-Host "  Puedes configurar ADO ahora o editar el archivo después:" -ForegroundColor Gray
    Write-Info $envFile
    $doConfig = Read-Host "`n  ¿Configurar Azure DevOps ahora? (s/N)"
    if ($doConfig -ieq "s") {
        $adoOrg     = Read-Host "  ADO Organización (ej: MiOrg)"
        $adoProject = Read-Host "  ADO Proyecto     (ej: MiProyecto)"
        $adoPat     = Read-Host "  ADO PAT          (Personal Access Token)"

        $content = Get-Content $envFile -Raw
        $content = $content -replace "(?m)^ADO_ORG=.*",     "ADO_ORG=$adoOrg"
        $content = $content -replace "(?m)^ADO_PROJECT=.*", "ADO_PROJECT=$adoProject"
        $content = $content -replace "(?m)^ADO_PAT=.*",     "ADO_PAT=$adoPat"
        [System.IO.File]::WriteAllText($envFile, $content, [System.Text.Encoding]::UTF8)
        Write-OK "ADO configurado en .env"
    }
} else {
    Write-OK ".env ya existe — no sobreescrito"
    Write-Info "Para reconfigurar, edita: $envFile"
}

# ── 13. Crear directorio data/ si no existe ───────────────────────────────
$dataDir = Join-Path $backendDir "data"
if (-not (Test-Path $dataDir)) {
    New-Item -ItemType Directory -Path $dataDir | Out-Null
    Write-OK "Directorio data/ creado"
}

# ── 14. Validar instalación ───────────────────────────────────────────────
Write-Step "Validando instalación"

try {
    $v = & $venvPython --version 2>&1
    Write-OK "venv Python: $v"
} catch {
    Write-Err "venv Python no responde"
}

try {
    $flaskVer = & $venvPython -c "import flask; print(flask.__version__)" 2>&1
    Write-OK "Flask $flaskVer"
} catch {
    Write-Err "Flask no importa — revisa el log de instalación"
}

try {
    $npmVer = npm --version 2>&1
    Write-OK "npm $npmVer"
} catch {
    Write-Err "npm no disponible en PATH"
}

$nodeModules = Join-Path $frontendDir "node_modules"
if (Test-Path $nodeModules) {
    Write-OK "frontend/node_modules presente"
} else {
    Write-Err "frontend/node_modules ausente — npm install falló"
}

# ── 15. Resumen final ─────────────────────────────────────────────────────
Write-Host ""
if (-not $script:hasErrors) {
    Write-Host "  ================================================================" -ForegroundColor Green
    Write-Host "   Instalacion completada con exito." -ForegroundColor Green
    Write-Host ""
    Write-Host "   Para iniciar Stacky Agents:" -ForegroundColor White
    Write-Host "     START.bat                              (raiz del proyecto)" -ForegroundColor Yellow
    Write-Host "     Stacky Agents\start_dashboard.bat     (equivalente)" -ForegroundColor Yellow
    Write-Host "  ================================================================" -ForegroundColor Green
} else {
    Write-Host "  ================================================================" -ForegroundColor Yellow
    Write-Host "   Instalacion completada con advertencias." -ForegroundColor Yellow
    Write-Host "   Revisa los errores [ERR] antes de continuar." -ForegroundColor Yellow
    Write-Host "  ================================================================" -ForegroundColor Yellow
}
Write-Host ""

$launch = Read-Host "  Iniciar Stacky Agents ahora? (s/N)"
if ($launch -ieq "s") {
    $startBat = Join-Path $STACKY_ROOT "Stacky Agents\start_dashboard.bat"
    Start-Process "cmd.exe" -ArgumentList "/c `"$startBat`""
}
