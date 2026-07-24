@echo off
REM Wrapper minimo: delega en migrar_mantis_gitlab.ps1 (mismo patron que el
REM resto de wrappers .bat/.ps1 de deployment/). Pasa todos los argumentos
REM tal cual (subcomando + flags del CLI del migrador Mantis -> GitLab, Plan 217).
setlocal
set SCRIPT_DIR=%~dp0
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%migrar_mantis_gitlab.ps1" %*
exit /b %ERRORLEVEL%
