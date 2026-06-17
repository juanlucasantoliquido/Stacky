@echo off
setlocal
cd /d "%~dp0"

echo.
echo ============================================================
echo  PrepararPublicacionConProyectos - Stacky Agents
echo  Incluye proyectos configurados y empleados/agentes locales.
echo ============================================================
echo.
echo [ADVERTENCIA] Este deploy exporta configuracion local y credenciales,
echo             incluyendo PAT/tokens guardados para los proyectos.
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
    echo PrepararPublicacionConProyectos finalizo correctamente.
) else (
    echo PrepararPublicacionConProyectos finalizo con errores. Codigo: %EXITCODE%
)

if /I not "%STACKY_NO_PAUSE%"=="1" pause
exit /b %EXITCODE%
