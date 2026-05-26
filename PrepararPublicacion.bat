@echo off
setlocal
call "%~dp0Stacky Agents\PrepararPublicacion.bat" %*
exit /b %ERRORLEVEL%
