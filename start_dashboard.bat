@echo off
title Dashboard Pipeline RIPLEY
cd /d "%~dp0"

echo ============================================================
echo  Dashboard Pipeline RIPLEY
echo  http://localhost:5050
echo ============================================================
echo.

:: Verificar que Python este disponible
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python no encontrado en el PATH.
    echo         Asegurate de tener Python 3.11+ instalado.
    pause
    exit /b 1
)

:: Instalar dependencias si falta flask
python -c "import flask" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Instalando dependencias...
    pip install -r requirements.txt
    echo.
)

echo [INFO] Iniciando servidor en http://localhost:5050 ...
echo [INFO] Presiona Ctrl+C para detener.
echo.

set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1
python -u dashboard_server.py

echo.
echo [INFO] Servidor detenido.
pause
