@echo off
REM ============================================================
REM  Kaizen - automejora AI-driven.
REM  Abre el DASHBOARD y el navegador. Desde la pagina arrancas
REM  y frenas el loop con los botones START / STOP (sin terminal).
REM  El motor sale de config/kaizen.config.yaml (mode: aotl).
REM ============================================================
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo ERROR: 'python' no esta en el PATH. Instala Python 3 o agregalo al PATH.
  pause
  exit /b 1
)

echo Iniciando el dashboard de Kaizen en una ventana nueva...
start "Kaizen Dashboard" cmd /k python kaizen.py dashboard

REM Espera breve a que levante el servidor y abre el navegador.
timeout /t 2 /nobreak >nul
start "" http://127.0.0.1:8765

echo.
echo   Dashboard abierto: http://127.0.0.1:8765
echo   En la pagina:  [ START ] arranca el loop AI-driven,  [ STOP ] lo frena.
echo   El log en vivo (y cualquier error) se ve en la misma pagina.
echo.
echo   Esta ventana ya se puede cerrar. El dashboard sigue en su propia ventana.
timeout /t 8 /nobreak >nul
endlocal
