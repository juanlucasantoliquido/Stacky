"""H3.1 — Texto canónico de reglas de ejecución de Stacky Agents.

Fuente única de verdad para las reglas que van en el system prompt de cada
runtime (claude_code_cli, codex_cli). Antes estaban duplicadas en:
  - services/claude_code_cli_runner.py  → _STACKY_RULES
  - services/codex_cli_runner.py        → texto embebido en _build_codex_prompt

Regla de diseño (plan H3.1):
  harness/ NO importa runners; los runners importan harness/.
"""
from __future__ import annotations

# ── Bloque de reglas file-drop (sin MCP) ─────────────────────────────────────
_RULES_FILEDROP = """\
## Reglas de ejecución (Stacky Agents)

- Trabajá en el workspace configurado para el proyecto.
- Mantené el comportamiento esperado por el agente que estás adoptando.
- Si editás archivos, limitá el cambio al alcance del ticket y dejá evidencia
  clara en tu respuesta final.
- Reportá comandos relevantes, archivos tocados y cualquier bloqueo real.
- Regla absoluta: no toques Azure DevOps. No publiques comentarios, no crees
  ni actualices work items, no cambies estados, no ejecutes APIs/CLI/scripts de
  ADO y no solicites credenciales ADO. Stacky Agents es el único autorizado a
  escribir en ADO.
- Si el resultado debe ser un comentario ADO, generá el archivo
  `Agentes/outputs/<ADO_ID>/comment.html` y opcionalmente `comment.meta.json`.
  Stacky lo validará y publicará.
- Si el resultado debe ser una Task hija para un Epic, generá
  `Agentes/outputs/epic-<ADO_ID>/<RF_SLUG>/pending-task.json` y los archivos
  referenciados, como `plan-de-pruebas.md`. Stacky creará la Task desde la UI y
  marcará el JSON como consumido.
- Importante: usá el ADO id real del work item (nunca el número ordinal 1, 2, 3…)
  tanto en el campo `epic_id` del JSON como en el nombre del directorio
  `epic-<ADO_ID>`. Confundir ordinal con ADO id real es la causa más común de
  que la Task no se cree.\
"""

# ── Bloque de reglas MCP (canal preferido: submit_*; file-drop como fallback) ─
_RULES_MCP = """\
## Reglas de ejecución (Stacky Agents — MCP activo)

- Trabajá en el workspace configurado para el proyecto.
- Mantené el comportamiento esperado por el agente que estás adoptando.
- Si editás archivos, limitá el cambio al alcance del ticket y dejá evidencia
  clara en tu respuesta final.
- Reportá comandos relevantes, archivos tocados y cualquier bloqueo real.
- Regla absoluta: no toques Azure DevOps directamente. No publiques comentarios,
  no crees ni actualices work items, no cambies estados, no ejecutes APIs/CLI/scripts
  de ADO y no solicites credenciales ADO. Stacky Agents es el único autorizado a
  escribir en ADO.
- Canal preferido: usá las tools MCP `stacky_submit_comment` y
  `stacky_submit_task` para entregar resultados. Stacky los validará y publicará
  en ADO de forma trazable.
- Fallback (solo si las tools MCP fallan): generá los archivos de salida como
  file-drop — `Agentes/outputs/<ADO_ID>/comment.html` para comentarios o
  `Agentes/outputs/epic-<ADO_ID>/<RF_SLUG>/pending-task.json` para Tasks.
- Importante: usá el ADO id real del work item (nunca el número ordinal 1, 2, 3…)
  tanto en los argumentos de submit_task como en los paths de file-drop.
  Confundir ordinal con ADO id real es la causa más común de que la Task no se cree.\
"""


def rules_text(*, runtime: str, mcp_enabled: bool) -> str:  # noqa: ARG001 — runtime reservado para extensión futura
    """Devuelve el texto canónico de reglas de ejecución para el runtime dado.

    Args:
        runtime:     "claude" | "codex" (actualmente ambos reciben el mismo texto;
                     el parámetro está disponible para divergencias futuras).
        mcp_enabled: Si True, el canal principal son las tools MCP (submit_*) y
                     file-drop es fallback. Si False, solo file-drop.

    Returns:
        String multilínea listo para embeber en un system prompt o prompt de usuario.
    """
    return _RULES_MCP if mcp_enabled else _RULES_FILEDROP
