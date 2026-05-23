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

netstat -ano -p tcp 2>nul | findstr ":%STACKY_PORT%" | findstr "LISTENING" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Iniciando Stacky Agents...
    start "Stacky Agents" cmd /k "title Stacky Agents && cd /d ""%~dp0"" && set STACKY_APP_ROOT=%~dp0 && set STACKY_DATA_DIR=%~dp0data && set STACKY_PROJECTS_DIR=%~dp0projects && set STACKY_FRONTEND_DIST=%~dp0frontend\dist && set PYTHONIOENCODING=utf-8 && set PYTHONUNBUFFERED=1 && backend\stacky-backend.exe"
) else (
    echo [OK] Stacky Agents ya esta corriendo en el puerto %STACKY_PORT%.
)

timeout /t 3 /nobreak >nul
start "" "http://localhost:%STACKY_PORT%"

echo.
echo Stacky Agents esta listo.
echo Cierra la ventana Stacky Agents para detenerlo.
echo.
pause
