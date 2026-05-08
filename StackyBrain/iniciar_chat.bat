@echo off
title StackyBrain — Iniciando...
color 0A

echo.
echo  =======================================
echo   STACKYBRAIN CHAT — Inicio
echo  =======================================
echo.

:: ── 1. Verificar si Ollama ya esta corriendo ─────────────────────────────
tasklist /FI "IMAGENAME eq ollama.exe" 2>nul | find /I "ollama.exe" >nul
if %ERRORLEVEL%==0 (
    echo  [OK] Ollama ya esta corriendo
) else (
    echo  [..] Iniciando Ollama...
    set OLLAMA_ORIGINS=*
    set OLLAMA_MODELS=%~dp0
    set "OLLAMA_EXE=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
    if not exist "%OLLAMA_EXE%" (
        where ollama >nul 2>&1 && set "OLLAMA_EXE=ollama"
    )
    start "" /B "%OLLAMA_EXE%" serve
    timeout /t 3 /nobreak >nul
    echo  [OK] Ollama iniciado
)

:: ── 2. Verificar si el servidor HTTP ya esta en puerto 8888 ──────────────
netstat -ano | find ":8888 " | find "LISTEN" >nul 2>&1
if %ERRORLEVEL%==0 (
    echo  [OK] Servidor HTTP ya en puerto 8888
) else (
    echo  [..] Iniciando servidor HTTP en puerto 8888...
    start "" /B python -m http.server 8888 --directory "%~dp0"
    timeout /t 2 /nobreak >nul
    echo  [OK] Servidor HTTP iniciado
)

:: ── 3. Abrir browser ──────────────────────────────────────────────────────
echo  [..] Abriendo chat en el browser...
start "" "http://localhost:8888/chat.html"

echo.
echo  =======================================
echo   Chat disponible en:
echo   http://localhost:8888/chat.html
echo  =======================================
echo.
echo  Para cerrar: cerrar esta ventana
echo  (Ollama y el servidor HTTP seguiran corriendo en background)
echo.
pause
