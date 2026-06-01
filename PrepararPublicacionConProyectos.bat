@echo off
setlocal
call "%~dp0Stacky Agents\PrepararPublicacionConProyectos.bat" %*
exit /b %ERRORLEVEL%
