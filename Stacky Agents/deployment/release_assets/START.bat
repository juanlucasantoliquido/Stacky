@echo off
setlocal
cd /d "%~dp0"

for /f "delims=" %%P in ('powershell -NoProfile -ExecutionPolicy Bypass -Command "$p=5050; $f='data\runtime_config.json'; if(Test-Path $f){ try { $j=Get-Content $f -Raw | ConvertFrom-Json; if($j.port){ $p=[int]$j.port } } catch {} }; $p"') do set "STACKY_PORT=%%P"
if not defined STACKY_PORT set "STACKY_PORT=5050"

echo.
echo ============================================================
echo  Stacky Agents
echo  App http://localhost:%STACKY_PORT%
echo ============================================================
echo.

if not exist "backend\stacky-backend.exe" (
    echo [ERROR] No existe backend\stacky-backend.exe
    echo         El release esta incompleto o corrupto.
    pause
    exit /b 1
)

if not exist "frontend\dist\index.html" (
    echo [ERROR] No existe frontend\dist\index.html
    echo         El release esta incompleto o corrupto.
    pause
    exit /b 1
)

if not exist "data" mkdir "data"
if not exist "projects" mkdir "projects"

if not exist "backend\.env" (
    if exist "backend\.env.example" (
        copy "backend\.env.example" "backend\.env" >nul
    )
)

:: Enrich PATH with npm global prefix so claude/codex are visible to the backend.
:: %APPDATA%\npm is where `npm install -g` puts binaries on Windows (user install).
if exist "%APPDATA%\npm" set "PATH=%APPDATA%\npm;%PATH%"
:: Also ask npm for its configured prefix in case it was customised.
for /f "usebackq delims=" %%N in (`npm config get prefix 2^>nul`) do (
    if exist "%%N" set "PATH=%%N;%PATH%"
)

:: Si algo ya esta escuchando en el puerto, puede ser un backend VIEJO que quedo
:: colgado de un deploy anterior (no fue matado por Prepare-Publication porque
:: corria desde otra ruta, o el cmd nunca se cerro). Reusarlo serviria assets
:: viejos aunque el disco ya tenga el release fresco. Por eso SIEMPRE lo matamos
:: y arrancamos el backend de ESTE release, nunca lo dejamos "como esta".
for /f "tokens=5" %%A in ('netstat -ano -p tcp 2^>nul ^| findstr ":%STACKY_PORT%" ^| findstr "LISTENING"') do (
    echo [INFO] Liberando puerto %STACKY_PORT% ^(PID %%A ya escuchando^)...
    taskkill /PID %%A /F >nul 2>&1
)

echo [INFO] Iniciando Stacky Agents...
start "Stacky Agents" cmd /k "title Stacky Agents && cd /d ""%~dp0"" && set STACKY_APP_ROOT=%~dp0 && set STACKY_DATA_DIR=%~dp0data && set STACKY_PROJECTS_DIR=%~dp0projects && set STACKY_FRONTEND_DIST=%~dp0frontend\dist && set PYTHONIOENCODING=utf-8 && set PYTHONUNBUFFERED=1 && backend\stacky-backend.exe"

timeout /t 3 /nobreak >nul
start "" "http://localhost:%STACKY_PORT%"

echo.
echo Stacky Agents esta listo.
echo Cierra la ventana Stacky Agents para detenerlo.
echo.
pause
