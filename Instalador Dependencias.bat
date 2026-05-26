@echo off
setlocal
call "%~dp0Stacky Agents\Instalador Dependencias.bat" %*
exit /b %ERRORLEVEL%
