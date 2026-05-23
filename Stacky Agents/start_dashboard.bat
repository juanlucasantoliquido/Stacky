@echo off
title Stacky Agents — Workbench
cd /d "%~dp0"

echo.
echo  ============================================================
echo   Stacky Agents — Agent Workbench
echo   App http://localhost:5050
echo  ============================================================
echo.

:: ── Verificar Python ─────────────────────────────────────────
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python no encontrado en el PATH.
    echo         Instala Python 3.11+ y vuelve a intentar.
    pause
    exit /b 1
)

:: ── Verificar Node / npm solo si falta el bundle ──────────────
if not exist "frontend\dist\index.html" (
    where npm >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] npm no encontrado en el PATH.
        echo         Instala Node.js 18+ o genera frontend\dist antes de iniciar.
        pause
        exit /b 1
    )
)

:: ── Instalar extensión VS Code si hay nueva versión ─────────
set "CODE_CMD=%LOCALAPPDATA%\Programs\Microsoft VS Code\bin\code.cmd"
if not exist "%CODE_CMD%" set "CODE_CMD=code"

set "LATEST_VSIX="
for /f "delims=" %%i in ('dir /b /o-d "vscode_extension\stacky-agents-*.vsix" 2^>nul') do (
    if not defined LATEST_VSIX set "LATEST_VSIX=vscode_extension\%%i"
)

if defined LATEST_VSIX (
    echo [INFO] Instalando/actualizando extension Stacky Agents en VS Code...
    start "" /b cmd /c ""%CODE_CMD%" --install-extension "%LATEST_VSIX%" --force >nul 2>&1"
    echo [OK]  Instalacion de extension lanzada en background.
)
echo.

:: ── Verificar gh CLI autenticado ────────────────────────────
set "GH_EXE="
for /f "delims=" %%G in ('where gh 2^>nul') do (
    if not defined GH_EXE set "GH_EXE=%%G"
)
if not defined GH_EXE (
    if exist "%LOCALAPPDATA%\Programs\GitHub CLI\gh.exe" set "GH_EXE=%LOCALAPPDATA%\Programs\GitHub CLI\gh.exe"
)
if not defined GH_EXE (
    if exist "%ProgramFiles%\GitHub CLI\gh.exe" set "GH_EXE=%ProgramFiles%\GitHub CLI\gh.exe"
)
if not defined GH_EXE (
    if exist "%ProgramFiles(x86)%\GitHub CLI\gh.exe" set "GH_EXE=%ProgramFiles(x86)%\GitHub CLI\gh.exe"
)
if defined GH_EXE (
    "%GH_EXE%" auth token >nul 2>&1
    if errorlevel 1 (
        echo [WARN] gh no esta autenticado. Ejecuta: gh auth login
        pause
    ) else (
        echo [OK]  gh autenticado.
    )
) else (
    echo [WARN] gh CLI no encontrado. Instala desde https://cli.github.com/
    pause
)
echo.

:: ── Crear .env si no existe ───────────────────────────────────
if not exist "backend\.env" (
    echo [INFO] Creando backend\.env desde .env.example...
    copy "backend\.env.example" "backend\.env" >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] No se pudo crear backend\.env desde backend\.env.example
        pause
        exit /b 1
    )
)

:: ── Virtualenv backend ───────────────────────────────────────
if not exist "backend\.venv\Scripts\python.exe" (
    echo [INFO] Creando virtualenv en backend\.venv ...
    python -m venv "backend\.venv"
    if errorlevel 1 (
        echo [ERROR] Fallo la creacion del virtualenv en backend\.venv
        pause
        exit /b 1
    )
    echo [OK]  Virtualenv creado.
    echo.
)

:: ── Instalar deps backend si falta flask ─────────────────────
"backend\.venv\Scripts\python.exe" -c "import flask" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Instalando dependencias del backend...
    "backend\.venv\Scripts\pip.exe" install -r "backend\requirements.txt" --quiet
    if errorlevel 1 (
        echo [ERROR] Fallo la instalacion de dependencias del backend.
        echo         Ejecuta manualmente: backend\.venv\Scripts\pip.exe install -r backend\requirements.txt
        pause
        exit /b 1
    )
    echo [OK]  Backend listo.
    echo.
)

:: ── Build frontend si falta dist ─────────────────────────────
if not exist "frontend\dist\index.html" (
    echo [INFO] Compilando frontend ^(puede tardar^)...
    cd frontend
    if not exist "node_modules" npm install --silent
    if errorlevel 1 (
        cd ..
        echo [ERROR] Fallo la instalacion de dependencias del frontend.
        echo         Ejecuta manualmente: cd frontend ^&^& npm install
        pause
        exit /b 1
    )
    npm run build
    if errorlevel 1 (
        cd ..
        echo [ERROR] Fallo la compilacion del frontend.
        echo         Ejecuta manualmente: cd frontend ^&^& npm run build
        pause
        exit /b 1
    )
    cd ..
    echo [OK]  Frontend compilado.
    echo.
)

:: ── Lanzar backend en ventana separada ─────────────────────
netstat -ano -p tcp 2>nul | findstr ":5050" | findstr "LISTENING" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Iniciando backend  (http://localhost:5050^) ...
    start "Stacky Agents — Backend" cmd /k "title Stacky Agents Backend && cd /d ""%~dp0backend"" && set PYTHONIOENCODING=utf-8 && set PYTHONUNBUFFERED=1 && .venv\Scripts\python.exe -u app.py"
    timeout /t 2 /nobreak >nul
) else (
    echo [OK]  Backend ya esta corriendo en http://localhost:5050
)

:: ── Abrir en el browser default ──────────────────────────────
echo [INFO] Abriendo http://localhost:5050 en el navegador...
start "" "http://localhost:5050"

echo.
echo  ============================================================
echo   Stacky Agents corriendo.
echo.
echo   App      -^> http://localhost:5050
echo   Health   -^> http://localhost:5050/api/health
echo.
echo   Para detener: cerra las ventanas Backend y Frontend.
echo  ============================================================
echo.
pause
