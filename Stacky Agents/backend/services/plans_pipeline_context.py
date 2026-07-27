"""Plan 196 — bootstrap del agente ejecutor del pipeline de planes.

Espejo de services/incident_context.py (Plan 131 F2): plantilla `.agent.md` del
PlansPipeline (fuente de verdad unica, viaja dentro del bundle empaquetado) y
`ensure_plans_pipeline_agent_file()`.
"""
from __future__ import annotations

from pathlib import Path

from runtime_paths import stacky_agents_dir

_AGENT_FILENAME = "PlansPipeline.agent.md"

# Fuente de verdad UNICA del contenido del .agent.md. En un deploy congelado
# (PyInstaller) el archivo del repo puede no existir; esta constante viaja
# siempre dentro del bundle.
_AGENT_TEMPLATE_MD = """# PlansPipeline — Ejecutor del pipeline de planes de Stacky

Sos el ejecutor del pipeline de planes evolutivos de Stacky Agents.

## Única tarea
El mensaje inicial de la corrida es UNA línea con una skill del pipeline
(`/proponer-plan-stacky`, `/criticar-y-mejorar-plan <NN>`,
`/implementar-plan-stacky <NN>` o `/supervisar-implementaciones-planes <NN>`).
Ejecutá EXACTAMENTE esa skill con ese argumento, siguiendo sus pasos al pie de la letra.

## Reglas duras
- PROHIBIDO `git push` (incluido `git push --force`): el push es siempre manual del operador.
- PROHIBIDO `git stash`, `git reset`, `git rebase`, `git commit --amend`,
  `git checkout`/`git switch` (cambiar de rama) y el flag `--no-verify`:
  hay sesiones paralelas commiteando en este repo; amend/rebase pisan commits ajenos.
- Una corrida = una skill: no amplíes el alcance ni encadenes otras etapas.
- Tu último mensaje es el resumen que la skill pide (ruta del artefacto + resumen corto).

_PlansPipeline v1.0.0 — Stacky Agents (Plan 196)._
"""


def ensure_plans_pipeline_agent_file() -> Path:
    """Garantiza que `stacky_agents_dir()/PlansPipeline.agent.md` exista.

    - Si YA existe (el operador pudo editarlo): NO lo toca.
    - Si no existe: copia desde el archivo commiteado del repo
      (`backend/agents/PlansPipeline.agent.md`).
    - Si ese archivo tampoco existe (deploy congelado): escribe
      `_AGENT_TEMPLATE_MD` directo.
    """
    dest = stacky_agents_dir() / _AGENT_FILENAME
    if dest.exists():
        return dest

    dest.parent.mkdir(parents=True, exist_ok=True)
    repo_template = Path(__file__).resolve().parents[1] / "agents" / _AGENT_FILENAME
    try:
        content = repo_template.read_text(encoding="utf-8")
    except OSError:
        content = _AGENT_TEMPLATE_MD

    # newline="" evita la traduccion LF->CRLF de Windows: el archivo escrito
    # queda byte-identico al contenido en memoria.
    dest.write_text(content, encoding="utf-8", newline="")
    return dest
