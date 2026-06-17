@echo off
setlocal
cd /d "%~dp0"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0deployment\Prepare-DeployOnly.ps1" -NoPause %*
set "EXITCODE=%ERRORLEVEL%"

echo.
if "%EXITCODE%"=="0" (
    echo PrepararDeploySolo finalizo correctamente.
) else (
    echo PrepararDeploySolo finalizo con errores. Codigo: %EXITCODE%
)

if /I not "%STACKY_NO_PAUSE%"=="1" pause
exit /b %EXITCODE%
