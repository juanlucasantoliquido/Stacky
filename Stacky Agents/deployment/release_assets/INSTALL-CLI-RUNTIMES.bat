@echo off
setlocal
cd /d "%~dp0"

echo.
echo ============================================================
echo  Stacky Agents - Instalar Runtimes CLI (claude + codex)
echo ============================================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-CLI-Runtimes.ps1"
set "RC=%ERRORLEVEL%"

echo.
if not "%RC%"=="0" (
    echo [ERROR] La instalacion termino con errores ^(codigo %RC%^). Revisa los mensajes de arriba.
) else (
    echo [OK] Runtimes CLI instalados correctamente.
)
echo.
pause
exit /b %RC%
