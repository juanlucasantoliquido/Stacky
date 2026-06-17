@echo off
setlocal
cd /d "%~dp0"

set "PS_NOPAUSE=-NoPause"
for %%A in (%*) do (
    if /I "%%~A"=="-NoPause" set "PS_NOPAUSE="
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0deployment\Prepare-Publication.ps1" %PS_NOPAUSE% %*
set "EXITCODE=%ERRORLEVEL%"

echo.
if "%EXITCODE%"=="0" (
    echo PrepararPublicacion finalizo correctamente.
) else (
    echo PrepararPublicacion finalizo con errores. Codigo: %EXITCODE%
)

if /I not "%STACKY_NO_PAUSE%"=="1" pause
exit /b %EXITCODE%
