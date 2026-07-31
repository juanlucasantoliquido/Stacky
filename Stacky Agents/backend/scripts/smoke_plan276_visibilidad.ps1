# smoke_plan276_visibilidad.ps1 — Plan 276 F12.
# Wrapper SIN LÓGICA a propósito: toda la verificación vive en el .py, así los 3
# runtimes (Codex CLI, Claude Code CLI, GitHub Copilot Pro) ejecutan exactamente el
# mismo código y no hay nada que pueda divergir. Motivo medido en este repo: los dos
# ratchets duplican la misma responsabilidad en dos sintaxis y YA divergieron en 64
# entradas. La paridad acá es ESTRUCTURAL, no declarada.
$PY = "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\.venv\Scripts\python.exe"
& $PY "$PSScriptRoot\smoke_plan276_visibilidad.py" @args
exit $LASTEXITCODE
