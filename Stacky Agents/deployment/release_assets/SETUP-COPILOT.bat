@echo off
setlocal
cd /d "%~dp0"

echo.
echo ============================================================
echo  Stacky Agents - Setup GitHub Copilot + Bridge VS Code
echo ============================================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Setup-Copilot.ps1"
set "RC=%ERRORLEVEL%"

echo.
if not "%RC%"=="0" (
    echo [ERROR] El setup termino con errores ^(codigo %RC%^). Revisa los mensajes de arriba.
) else (
    echo [OK] Setup finalizado correctamente.
)
echo.
pause
exit /b %RC%
