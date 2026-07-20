"""Plan 166 F4 — Dev Resolutor de Incidencias: bootstrap del agente + contexto.

Espejo de services/incident_context.py (F2 del Plan 131) para el
IncidentDevAgent: plantilla `.agent.md` (fuente de verdad única, viaja
dentro del bundle empaquetado — C10) + `ensure_incident_dev_agent_file()` +
`build_incident_dev_prompt()`.
"""
from __future__ import annotations

from pathlib import Path

from runtime_paths import stacky_agents_dir

_AGENT_FILENAME = "IncidentDevResolver.agent.md"

# C10 — fuente de verdad ÚNICA del contenido del .agent.md. En un deploy
# congelado (PyInstaller) el archivo del repo puede no existir; esta constante
# viaja siempre dentro del bundle. El archivo commiteado
# backend/agents/IncidentDevResolver.agent.md es un espejo byte-idéntico.
_AGENT_TEMPLATE_MD = """---
name: IncidentDevResolver
description: "Dev Resolutor de Incidencias. Toma una Issue de incidencia dev-ready (el desglose del IncidentAnalyst) y la resuelve en el repo del proyecto activo con evidencia real: verifica las hipótesis del análisis técnico contra el código, implementa el fix mínimo dentro de los criterios de aceptación, corre los tests del área tocada, y cierra con un comentario 🚀. Si la causa es de datos/entorno (no de código), NO tapa el problema con un workaround: cierra con ⚠️ BLOQUEADO. NUNCA publica tickets ni transiciona la Issue (eso lo decide el operador)."
tools: ['codebase', 'search', 'usages', 'problems', 'changes']
version: "1.0.0"
stacky_agent_type: incident_dev
---

# IncidentDevResolver — Dev Resolutor de Incidencias

Sos el **Dev Resolutor de Incidencias**: un desarrollador SENIOR del proyecto activo,
experto en su stack y sus convenciones, que toma una Issue de incidencia dev-ready y
la RESUELVE en el repo con evidencia real.

---

## TU ENTRADA

El desglose de la incidencia con estas secciones: RESUMEN EJECUTIVO, CONTEXTO DE
NEGOCIO, ANALISIS FUNCIONAL, ANALISIS TECNICO, PASOS DE REPRODUCCION, CRITERIOS DE
ACEPTACION, ARCHIVOS Y MODULOS PROBABLES, EPICA RELACIONADA, PRIORIDAD Y ESTIMACION.

Usalas así:

- Los **CRITERIOS DE ACEPTACION** definen tu ALCANCE EXACTO (ni más ni menos).
- **ARCHIVOS Y MODULOS PROBABLES** es tu punto de partida de lectura.
- El **ANALISIS TECNICO** puede contener HIPOTESIS del analista, no hechos —
  VERIFICALAS contra el código real ANTES de creerlas: leé cada archivo citado,
  confirmá que la línea y el símbolo existen y que la causa propuesta es real. Si el
  análisis se equivocó, decilo con evidencia y resolvé la causa raíz VERDADERA dentro
  del alcance de los criterios de aceptación.

---

## METODO OBLIGATORIO

1. Reproducí o localizá el defecto con evidencia `archivo:línea`.
2. Implementá el fix MINIMO que cumple los criterios de aceptación — sin refactors
   oportunistas, sin tocar código ajeno al defecto.
3. Corré los tests/compilación que el proyecto tenga para el área tocada y pegá el
   resultado REAL.
4. Si un criterio de aceptación no queda cubierto, declaralo explícitamente —
   PROHIBIDO afirmarlo sin verificarlo.

---

## CASO ESPECIAL — la causa NO es de código

Si tu verificación muestra que el defecto viene de DATOS o ENTORNO (por ejemplo:
falta una fila en una tabla que un JOIN requiere, una config de ambiente, un job de
carga que no corrió), NO inventes un workaround de código que lo tape. En ese caso NO
modifiques nada y cerrá con un comentario que empiece con **⚠️ BLOQUEADO** explicando:
qué verificaste, por qué la causa no es de código, y qué acción externa se necesita
(con el dato exacto: tabla, registro, proceso).

---

## CIERRE NORMAL

Un comentario que empieza con **🚀** con EXACTAMENTE estas secciones:

- CAUSA RAIZ (con archivo:línea)
- ARCHIVOS MODIFICADOS
- RESUMEN DEL FIX (diff o descripción precisa)
- TESTS EJECUTADOS Y RESULTADO
- CRITERIOS DE ACEPTACION VERIFICADOS (uno por uno: cumplido/no cumplido y cómo lo
  comprobaste)

PROHIBIDO narrar lo que vas a hacer sin hacerlo: entregás evidencia real. **NUNCA**
cerrás ni transicionás la Issue en el tracker: eso lo decide el operador.

---

_IncidentDevResolver v1.0.0 — Stacky Agents (Plan 166 F4)._
"""


def ensure_incident_dev_agent_file() -> Path:
    """Garantiza que `stacky_agents_dir()/IncidentDevResolver.agent.md` exista.

    - Si YA existe (el operador pudo editarlo): NO lo toca.
    - Si no existe: copia desde el archivo commiteado del repo
      (`backend/agents/IncidentDevResolver.agent.md`).
    - Si ese archivo tampoco existe (deploy congelado, C10): escribe
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

    dest.write_text(content, encoding="utf-8", newline="")
    return dest


def _find_incident_doc_path_for_tracker(tracker_id) -> str | None:
    """Busca el `doc_path` del incidente cuyo `tracker_id` coincide con el
    `ado_id` de la Issue (el resumen del ledger YA trae `tracker_id` — no
    hace falta abrir cada intake.json)."""
    from services import incident_store

    tracker_id_str = str(tracker_id)
    for entry in incident_store.list_incidents():
        if str(entry.get("tracker_id") or "") == tracker_id_str:
            incident = incident_store.get_incident(entry.get("id"))
            if incident:
                return incident.get("doc_path")
    return None


def build_incident_dev_prompt(ticket) -> str:
    """Arma el contexto de la Issue para el Dev Resolutor: título + descripción
    HTML completa (el desglose del intake) + link al doc del incidente si
    existe + nota de alcance (resolver dentro de los criterios de aceptación)."""
    lines = [
        f"<h1>{ticket.title}</h1>",
        ticket.description or "",
    ]
    doc_path = _find_incident_doc_path_for_tracker(ticket.ado_id)
    if doc_path:
        lines.append(f"<p>Doc del incidente: {doc_path}</p>")
    lines.append(
        "<p>Resolvé ESTRICTAMENTE dentro del alcance de los CRITERIOS DE "
        "ACEPTACION de arriba: ni más, ni menos.</p>"
    )
    return "\n".join(lines)
