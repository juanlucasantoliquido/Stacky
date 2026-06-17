@echo off
setlocal
cd /d "%~dp0"

echo.
echo ============================================================
echo  PrepararPublicacionExportConfig - Stacky Agents
echo  Incluye proyectos, agentes configurados y credenciales.
echo ============================================================
echo.
echo [ADVERTENCIA] Este deploy exporta credenciales configuradas, incluyendo PAT.
echo             Usalo solo para entregas controladas.
echo.

set "PS_NOPAUSE=-NoPause"
for %%A in (%*) do (
    if /I "%%~A"=="-NoPause" set "PS_NOPAUSE="
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0deployment\Prepare-Publication.ps1" %PS_NOPAUSE% -ExportConfig %*
set "EXITCODE=%ERRORLEVEL%"

echo.
if "%EXITCODE%"=="0" (
    echo PrepararPublicacionExportConfig finalizo correctamente.
) else (
    echo PrepararPublicacionExportConfig finalizo con errores. Codigo: %EXITCODE%
)

if /I not "%STACKY_NO_PAUSE%"=="1" pause
exit /b %EXITCODE%
