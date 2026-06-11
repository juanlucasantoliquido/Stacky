"""claude_cli_hooks.py — Hooks de Claude Code generados por Stacky (F1.4).

Genera por run un `settings.json` efímero en el run_dir, pasado al CLI vía
`--settings`. Contiene UN hook `PostToolUse` sobre `Write|Edit` que, cuando el
path escrito matchea `Agentes/outputs/**/pending-task.json` (o comment.html),
llama al endpoint local `POST /api/agents/validate-artifact` y, si el artifact
es inválido, devuelve el error al agente en el momento de la escritura
(exit code 2 + stderr → feedback inmediato al modelo).

Defensa en profundidad: hook (inmediato) + F1.3 (al cierre de turno) +
output_watcher/agent_completion (fallback). Cero config del operador: Stacky
genera y limpia los archivos.

IMPORTANTE (decisión §5.3 del plan): el settings.json SOLO define hooks.
No toca permisos — `--dangerously-skip-permissions` sigue mandando.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger("stacky.claude_cli_hooks")

SETTINGS_FILENAME = "stacky_hooks_settings.json"
HOOK_SCRIPT_PS1 = "stacky_validate_artifact_hook.ps1"
HOOK_SCRIPT_SH = "stacky_validate_artifact_hook.sh"

# Solo estos archivos disparan validación remota desde el hook.
_PATH_REGEX_PS = r"Agentes[\\/]+outputs[\\/].*(pending-task\.json|comment\.html)$"


def _ps1_script(port: int) -> str:
    return f"""# Generado por Stacky Agents (F1.4) — validación de artifacts en PostToolUse.
# Lee el payload JSON del hook por stdin, y si el archivo escrito es un
# artifact de Stacky (pending-task.json / comment.html) lo valida contra el
# backend local. exit 2 + stderr devuelve el error al agente.
$ErrorActionPreference = 'Stop'
try {{
    $raw = [Console]::In.ReadToEnd()
    $data = $raw | ConvertFrom-Json
}} catch {{ exit 0 }}
$filePath = $null
if ($data -and $data.tool_input -and $data.tool_input.file_path) {{
    $filePath = [string]$data.tool_input.file_path
}}
if (-not $filePath) {{ exit 0 }}
if ($filePath -notmatch '{_PATH_REGEX_PS}') {{ exit 0 }}
try {{
    $body = @{{ path = $filePath }} | ConvertTo-Json
    $resp = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:{port}/api/agents/validate-artifact' -ContentType 'application/json' -Body $body -TimeoutSec 30
}} catch {{ exit 0 }}  # backend caído/no accesible: no bloquear al agente
if ($resp -and ($resp.valid -eq $false)) {{
    $errors = ($resp.errors -join '; ')
    [Console]::Error.WriteLine("Stacky: el artifact que acabas de escribir es invalido y no podra procesarse: $errors. Corregilo y reescribilo.")
    exit 2
}}
exit 0
"""


def _sh_script(port: int) -> str:
    return f"""#!/bin/sh
# Generado por Stacky Agents (F1.4) — validación de artifacts en PostToolUse.
payload=$(cat)
file_path=$(printf '%s' "$payload" | sed -n 's/.*"file_path"[[:space:]]*:[[:space:]]*"\\([^"]*\\)".*/\\1/p' | head -1)
[ -n "$file_path" ] || exit 0
case "$file_path" in
  *Agentes/outputs/*pending-task.json|*Agentes/outputs/*comment.html) ;;
  *) exit 0 ;;
esac
resp=$(curl -s -m 30 -X POST -H 'Content-Type: application/json' \\
  -d "{{\\"path\\": \\"$file_path\\"}}" \\
  "http://127.0.0.1:{port}/api/agents/validate-artifact") || exit 0
case "$resp" in
  *'"valid": false'*|*'"valid":false'*)
    echo "Stacky: el artifact que acabas de escribir es invalido y no podra procesarse: $resp. Corregilo y reescribilo." >&2
    exit 2 ;;
esac
exit 0
"""


def write_run_settings(run_dir: Path, *, port: int) -> Path:
    """Genera el hook script + settings.json efímero del run.

    Retorna la ruta del settings.json para pasarla vía `--settings`.
    """
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    if os.name == "nt":
        script_path = run_dir / HOOK_SCRIPT_PS1
        script_path.write_text(_ps1_script(port), encoding="utf-8")
        command = (
            f'powershell -NoProfile -ExecutionPolicy Bypass -File "{script_path}"'
        )
    else:
        script_path = run_dir / HOOK_SCRIPT_SH
        script_path.write_text(_sh_script(port), encoding="utf-8")
        script_path.chmod(0o755)
        command = f'sh "{script_path}"'

    settings = {
        "hooks": {
            "PostToolUse": [
                {
                    "matcher": "Write|Edit",
                    "hooks": [
                        {"type": "command", "command": command, "timeout": 60}
                    ],
                }
            ]
        }
    }
    settings_path = run_dir / SETTINGS_FILENAME
    settings_path.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return settings_path


def cleanup_run_settings(run_dir: Path) -> None:
    """Borra los archivos efímeros del hook (best-effort, post-run)."""
    run_dir = Path(run_dir)
    for name in (SETTINGS_FILENAME, HOOK_SCRIPT_PS1, HOOK_SCRIPT_SH):
        try:
            (run_dir / name).unlink(missing_ok=True)
        except OSError:
            logger.debug("cleanup hook file failed: %s", run_dir / name, exc_info=True)
