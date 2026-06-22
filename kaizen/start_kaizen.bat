@echo off
REM ============================================================
REM  Kaizen - automejora AI-driven: dashboard + loop constante
REM  Doble clic para arrancar. El motor (claude) sale de
REM  config/kaizen.config.yaml (mode: aotl, adapter: claude).
REM  Ctrl+C en ESTA ventana frena el loop; el dashboard sigue.
REM ============================================================
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo ERROR: 'python' no esta en el PATH. Instala Python 3 o agregalo al PATH.
  pause
  exit /b 1
)

echo Iniciando dashboard en una ventana nueva...
start "Kaizen Dashboard" cmd /k python kaizen.py dashboard

REM Espera breve a que levante el servidor y abre el navegador.
timeout /t 2 /nobreak >nul
start "" http://127.0.0.1:8765

echo.
echo   Dashboard: http://127.0.0.1:8765
echo   Loop de automejora AI-driven (constante). Ctrl+C para frenar.
echo.
python kaizen.py loop --forever

echo.
echo Loop detenido. El dashboard sigue abierto en su ventana (cerrala cuando quieras).
pause
endlocal
