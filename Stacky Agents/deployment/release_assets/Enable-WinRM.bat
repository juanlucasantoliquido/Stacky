@echo off
REM Launcher para Enable-WinRM.ps1
REM Ejecuta el script PowerShell con politica de ejecucion permitida.

setlocal enabledelayedexpansion

REM Detectar si estamos siendo ejecutados desde el directorio correcto
set SCRIPT_DIR=%~dp0
set PS_SCRIPT=%SCRIPT_DIR%Enable-WinRM.ps1

if not exist "%PS_SCRIPT%" (
    echo [ERROR] No se encontro Enable-WinRM.ps1 en %SCRIPT_DIR%
    echo Asegurate de que ambos archivos (Enable-WinRM.bat y Enable-WinRM.ps1) estan en la misma carpeta.
    pause
    exit /b 1
)

REM Ejecutar PowerShell con bypass de politica (necesario para ejecutar scripts locales)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%"

exit /b %ERRORLEVEL%
