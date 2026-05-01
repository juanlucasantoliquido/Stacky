"""
prompt_builder.py — Construye prompts para los agentes PM-TLStack 1 PACIFICO y DevStack3.

Funciones disponibles:
  build_pm_prompt       — análisis inicial de un ticket
  build_dev_prompt      — implementación de un ticket
  build_tester_prompt   — verificación de un ticket
  build_retry_prompt    — reintento por timeout (incluye cuánto tiempo pasó)
  build_error_fix_prompt — corrección tras PM_ERROR/DEV_ERROR/TESTER_ERROR.flag
"""

import os

try:
    from code_context import build_code_context_section as _build_ctx
except ImportError:
    _build_ctx = None

# G-02: Pitfall Registry integration
try:
    from pitfall_registry import PitfallRegistry
    _pitfall_registry = PitfallRegistry()
except ImportError:
    _pitfall_registry = None

# Q-01: Semantic Anchor Injection
try:
    from semantic_anchor_injector import SemanticAnchorInjector
    _anchor_injector = SemanticAnchorInjector()
except ImportError:
    _anchor_injector = None

# Q-02: Pre-flight Handoff Score PM → DEV
try:
    from handoff_scorer import HandoffScorer, HandoffScore
    _handoff_scorer = HandoffScorer()
except ImportError:
    _handoff_scorer = None
    HandoffScore = None

# X-01: Self-Improving Prompt Engine
try:
    from self_improving_engine import get_engine as _get_self_improving_engine
except ImportError:
    _get_self_improving_engine = None

# Agent customization (strictness, extra instructions, allowed tests)
try:
    from agent_config import load_agent_config as _load_agent_config
    from agent_config import build_prompt_injection as _build_agent_injection
except ImportError:
    _load_agent_config = None
    _build_agent_injection = None


# A4: heartbeat block — se anexa a cada prompt para que el agente toque el
# archivo {STAGE}_HEARTBEAT.txt periódicamente. El zombie sweeper y el crash
# recovery del daemon usan el mtime de ese archivo (umbral: 5 min) como señal
# de vida más confiable que el PID del proceso invocador.
def heartbeat_tail(stage_upper: str) -> str:
    """Bloque heartbeat para anexar al final de cada prompt de agente.

    `stage_upper` debe ser PM/DEV/TESTER (un solo archivo por etapa padre,
    compartido por los 3 sub-agentes que la componen). El agente lo crea
    dentro de la carpeta del ticket que ya conoce por instrucciones previas.
    """
    return f"""

---
🫀 **Heartbeat obligatorio (control anti-zombie)**

Cada vez que ejecutes una tool call de larga duración (Bash, Edit, Write,
Grep masivo, lectura de archivos grandes), INMEDIATAMENTE DESPUÉS sobreescribí
el archivo `{stage_upper}_HEARTBEAT.txt` dentro de la carpeta del ticket con:
  - El timestamp ISO actual en la primera línea.
  - Una línea breve describiendo el paso que acabás de completar.

Ejemplo de contenido:
```
2026-04-19T14:32:10
analizando ANALISIS_TECNICO.md
```

Si este archivo no se actualiza durante más de **5 minutos**, el sweeper
del pipeline considerará al ticket como zombie y lo marcará en error. NO te
saltees esta instrucción incluso si la etapa es corta — la primera escritura
debe ocurrir antes de la primera tool call de carga.
"""


def _ticket_header(ticket_id: str, stage: str, titulo: str = "") -> str:
    """
    Cabecera estándar que aparece al principio de TODOS los prompts de agente.
    Incluye instrucción de renombrar la conversación para que sea fácil de
    identificar en el panel de chats.
    """
    stage_labels = {
        "pm":     "📋 PM — Análisis y planificación",
        "dev":    "⚙ Dev — Implementación",
        "tester": "🧪 QA — Pruebas",
    }
    label = stage_labels.get(stage, stage.upper())
    titulo_line = f" · {titulo}" if titulo else ""
    return (
        f"═══════════════════════════════════════════════════\n"
        f"🎫 TICKET #{ticket_id}{titulo_line}\n"
        f"   Etapa: {label}\n"
        f"═══════════════════════════════════════════════════\n\n"
        f"⚠️ **PRIMER PASO OBLIGATORIO:** Renombrá esta conversación a:\n"
        f"   `#{ticket_id} — {stage.upper()}`\n"
        f"   (en VS Code Copilot Chat: click en el título del chat → editá el nombre)\n\n"
    )


def _apply_agent_config(agent: str, prompt: str) -> str:
    """
    Apendea al prompt las instrucciones configuradas por el usuario para este
    agente del proyecto activo. No-op si el módulo agent_config no está
    disponible o si no hay config personalizada.
    """
    if _load_agent_config is None or _build_agent_injection is None:
        return prompt
    try:
        from project_manager import get_active_project
        project_name = get_active_project()
    except Exception:
        return prompt
    if not project_name:
        return prompt
    stacky_base = os.path.dirname(os.path.abspath(__file__))
    try:
        cfg = _load_agent_config(stacky_base, agent, project_name=project_name)
        injection = _build_agent_injection(agent, cfg)
    except Exception:
        return prompt
    if not injection:
        return prompt
    return prompt + injection


def _build_golden_examples_section(ticket_folder: str, stage: str,
                                    top_k: int = 2) -> str:
    """X-01: Inyecta ejemplos de tickets similares con QA APROBADO al primer intento."""
    if _get_self_improving_engine is None:
        return ""
    try:
        engine   = _get_self_improving_engine()
        examples = engine.get_similar_examples(ticket_folder, stage, top_k=top_k)
    except Exception:
        return ""
    if not examples:
        return ""
    body = "\n\n".join(examples)
    return (
        "## Ejemplos de tickets similares exitosos\n\n"
        + body
        + "\n\n---\n\n"
    )


def _build_handoff_score_section(ticket_folder: str) -> str:
    """Q-02: Prepend handoff score block to DEV prompt."""
    if _handoff_scorer is None:
        return ""
    try:
        result = _handoff_scorer.score_pm_to_dev(ticket_folder)
    except Exception:
        return ""
    missing = ", ".join(result.missing_signals) if result.missing_signals else "ninguna"
    lines = [
        f"## Handoff Score del análisis PM: {result.score}/100",
        f"**Señales faltantes:** {missing}",
    ]
    if result.score < 60:
        lines.append("⚠️ El análisis PM está incompleto — investigá más antes de codificar.")
    return "\n".join(lines) + "\n"


def _collect_anchor_files(ticket_folder: str, ticket_id: str,
                           workspace_root: str) -> list:
    """Q-01: Recolecta la lista de archivos relevantes para anclas semánticas."""
    rels: list = []
    seen: set = set()
    try:
        from code_context import (
            extract_files_from_architecture as _from_arch,
            find_relevant_files as _from_heuristic,
        )
        for f in _from_arch(ticket_folder, workspace_root):
            if f.get("exists") and f.get("rel_path") and f["rel_path"] not in seen:
                seen.add(f["rel_path"])
                rels.append(f["rel_path"])
        for f in _from_heuristic(ticket_folder, ticket_id, workspace_root):
            if f.get("rel_path") and f["rel_path"] not in seen:
                seen.add(f["rel_path"])
                rels.append(f["rel_path"])
    except Exception:
        pass
    return rels


def _build_semantic_anchors_section(ticket_folder: str, ticket_id: str,
                                     workspace_root: str) -> str:
    """Q-01: Genera la sección de anclas semánticas con código real, o '' si no hay."""
    if _anchor_injector is None:
        return ""
    try:
        file_list = _collect_anchor_files(ticket_folder, ticket_id, workspace_root)
        if not file_list:
            return ""
        anchors = _anchor_injector.build_anchors(file_list, workspace_root)
        if not anchors:
            return ""
        return "## Anclas semánticas (código real)\n\n" + anchors + "\n\n---\n\n"
    except Exception:
        return ""


def _inject_code_context(ticket_folder: str, ticket_id: str,
                          workspace_root: str) -> str:
    """
    Intenta generar la sección de contexto de código.
    Retorna '' si code_context no está disponible o no encuentra nada.
    """
    if _build_ctx is None:
        return ""
    return _build_ctx(ticket_folder, ticket_id, workspace_root)


def _inject_pitfall_warnings(ticket_folder: str) -> str:
    """G-02: Inyecta advertencias de pitfalls conocidos en el prompt DEV."""
    if _pitfall_registry is None:
        return ""
    import re
    files = []
    for md_name in ("ARQUITECTURA_SOLUCION.md", "TAREAS_DESARROLLO.md"):
        md_path = os.path.join(ticket_folder, md_name)
        if os.path.exists(md_path):
            with open(md_path, encoding="utf-8", errors="replace") as f:
                content = f.read()
            files.extend(re.findall(
                r'[\w/\\]+\.(?:cs|aspx|sql|vb|config)\b', content, re.IGNORECASE
            ))
    if not files:
        return ""
    warnings = _pitfall_registry.get_warnings_for_files(files)
    if not warnings:
        return ""
    section = "\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    section += "⚠️ PITFALLS CONOCIDOS (errores recurrentes)\n"
    section += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    for w in warnings[:5]:
        section += f"- {w}\n"
    return section


def _read_file_safe(path: str, max_chars: int = 2000) -> str:
    """Lee un archivo y retorna su contenido truncado, o '' si no existe."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            content = fh.read(max_chars)
        if len(content) == max_chars:
            content += "\n… [truncado]"
        return content
    except Exception:
        return ""


def _to_workspace_relative(absolute_path: str, workspace_root: str) -> str:
    """Convierte ruta absoluta a relativa del workspace."""
    try:
        return os.path.relpath(absolute_path, workspace_root).replace("\\", "/")
    except ValueError:
        return absolute_path.replace("\\", "/")


def _find_project_docs(ticket_folder: str) -> str:
    """
    Busca PROJECT_DOCS.md subiendo desde la carpeta del ticket.
    Retorna ruta absoluta si existe, '' si no.
    """
    p = os.path.abspath(ticket_folder)
    for _ in range(8):  # máximo 8 niveles arriba
        candidate = os.path.join(p, "PROJECT_DOCS.md")
        if os.path.isfile(candidate):
            return candidate
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent
    return ""


# ── Y-02: PM Pre-Warming ──────────────────────────────────────────────────────

def _detect_project_name(ticket_folder: str) -> str:
    """Intenta detectar el nombre del proyecto desde la ruta del ticket."""
    try:
        p = os.path.abspath(ticket_folder)
        for _ in range(8):
            parent = os.path.dirname(p)
            if os.path.basename(parent).lower() == "projects":
                return os.path.basename(p)
            if parent == p:
                break
            p = parent
    except Exception:
        pass
    return ""


def build_pm_prewarming_section(ticket_folder: str, ticket_id: str,
                                workspace_root: str) -> str:
    """
    Y-02: Genera la sección de contexto pre-cargado para PM.
    Agrega al prompt de PM todo lo que Stacky ya sabe antes de que el agente
    empiece a analizar: memoria de agente, tickets similares, clasificación
    de subsistema, patrones aplicables.

    Retorna string listo para insertar al inicio del prompt PM.
    Si falla cualquier fuente, retorna "" (no bloquea el pipeline).
    """
    sections = []

    # ── Fuente 1: Subsystem Classifier (Y-03) ────────────────────────────────
    try:
        from subsystem_classifier import classify_ticket as _classify, format_for_prompt as _fmt_sub
        sub_result = _classify(ticket_folder, ticket_id)
        sub_line = _fmt_sub(sub_result)
        if sub_line:
            sections.append(sub_line.strip())
    except Exception:
        pass

    # ── Fuente 2: Agent Memory PM (G-06 si disponible) ───────────────────────
    try:
        from memory_manager import get_agent_memory
        import json as _json
        proj_name = _detect_project_name(ticket_folder)
        pm_mem = get_agent_memory(proj_name, "pm")
        if pm_mem:
            patterns = pm_mem.get("known_patterns", [])[:3]
            risky    = pm_mem.get("risky_areas", [])[:2]
            mem_lines = []
            if patterns:
                mem_lines.append("**Patrones conocidos del proyecto:**")
                for p in patterns:
                    desc = p.get("description", p.get("pattern", ""))
                    tickets_ref = p.get("seen_in_tickets", [])
                    ref_str = f" (tickets: {', '.join(['#'+t for t in tickets_ref[:3]])})" if tickets_ref else ""
                    mem_lines.append(f"- {desc}{ref_str}")
            if risky:
                mem_lines.append("**Áreas de riesgo conocidas:**")
                for r in risky:
                    mem_lines.append(f"- {r}")
            if mem_lines:
                sections.append("## Contexto pre-cargado — Memoria del agente PM\n" + "\n".join(mem_lines))
    except Exception:
        pass

    # ── Fuente 3: Tickets similares (E-01 Knowledge Base) ────────────────────
    try:
        from knowledge_base import find_similar_tickets
        inc_file = os.path.join(ticket_folder, f"INC-{ticket_id}.md")
        if os.path.exists(inc_file):
            query = open(inc_file, encoding="utf-8").read()[:500]
            similar = find_similar_tickets(query, top_k=3)
            if similar:
                sim_lines = ["**Tickets similares ya resueltos:**"]
                for s in similar:
                    sim_lines.append(
                        f"- #{s.get('ticket_id','')} (similitud {s.get('score',0):.0%}): "
                        f"{s.get('summary','')[:80]}"
                    )
                sections.append("\n".join(sim_lines))
    except Exception:
        pass

    if not sections:
        return ""

    return (
        "\n## Contexto pre-cargado — Stacky Pre-Warming\n\n"
        + "\n\n".join(sections)
        + "\n\n---\n\n"
    )


def build_pm_prompt(ticket_folder: str, ticket_id: str, workspace_root: str) -> str:
    rel_folder   = _to_workspace_relative(ticket_folder, workspace_root)

    # Y-03: Clasificar subsistema e inyectar al inicio del prompt
    _subsystem_line = ""
    try:
        from subsystem_classifier import classify_ticket as _classify, format_for_prompt as _fmt_sub
        _sub_result = _classify(ticket_folder, ticket_id)
        _subsystem_line = _fmt_sub(_sub_result)
    except Exception:
        pass

    # Referencia a PROJECT_DOCS.md si ya fue generado — reemplaza el code_context inline
    docs_path = _find_project_docs(ticket_folder)
    if docs_path:
        docs_rel  = _to_workspace_relative(docs_path, workspace_root)
        docs_note = (
            f"\n**Contexto del proyecto:** Leé `{docs_rel}` antes de investigar el código. "
            f"Contiene arquitectura, módulos, convenciones y tablas Oracle del proyecto.\n"
        )
    else:
        docs_note = (
            "\n**Nota:** No se encontró PROJECT_DOCS.md — investigá el código fuente directamente "
            "o usá el botón '📚 Generar Docs' del dashboard para crear el contexto del proyecto.\n"
        )

    # Incluir nota de contexto pre-pipeline si existe
    nota_pm_path = os.path.join(ticket_folder, "NOTA_PM.md")
    nota_pm_block = ""
    if os.path.exists(nota_pm_path):
        try:
            nota_content = open(nota_pm_path, encoding="utf-8").read().strip()
            if nota_content:
                nota_pm_block = f"\n\n## ⚠ Nota de contexto adicional (del usuario)\n\n{nota_content}\n"
        except Exception:
            pass

    # Y-02: Pre-warming — inyectar contexto ya disponible al inicio del prompt
    _prewarming = build_pm_prewarming_section(ticket_folder, ticket_id, workspace_root)

    # Q-01: Semantic Anchor Injection — inyectar fragmentos reales de código
    _semantic_anchors = _build_semantic_anchors_section(ticket_folder, ticket_id, workspace_root)

    # X-01: Golden Examples — ejemplos de tickets similares exitosos (primera pasada QA)
    _golden_examples = _build_golden_examples_section(ticket_folder, "pm", top_k=2)

    _pm_prompt = _ticket_header(ticket_id, "pm") + f"""Analizá y completá la incidencia del ticket #{ticket_id}.
{_semantic_anchors}{_golden_examples}{_prewarming}
{_subsystem_line}Carpeta del ticket: {rel_folder}/
{docs_note}{nota_pm_block}
Trabajá en 3 fases secuenciales. Completá cada fase antes de pasar a la siguiente.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FASE 1 — INVESTIGAR (sub-agente Investigador)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Objetivo: encontrar la CAUSA RAÍZ. NO diseñes soluciones todavía.

1. Leé INC-{ticket_id}.md para entender el síntoma exacto
2. Si existe PROJECT_DOCS.md, leélo primero para orientarte — ya tiene el mapa del proyecto
3. Buscá en el código fuente el componente exacto que falla (clase/método/SP/query)
4. Ejecutá queries Oracle para entender el estado de los datos involucrados
5. Escribí ANALISIS_TECNICO.md con:
   - **Síntoma**: qué reporta el usuario (verbatim del ticket)
   - **Causa raíz**: clase/método/SP específico + por qué falla exactamente
   - **Evidencia**: resultados de queries ejecutadas
   - **Archivos afectados**: rutas completas relativas al workspace
   - **Tablas BD involucradas**: columnas relevantes y datos de ejemplo
6. Escribí QUERIES_ANALISIS.sql con todas las queries ejecutadas

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FASE 2 — DISEÑAR (sub-agente Arquitecto)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Objetivo: diseñar la solución basada en lo que encontraste en la Fase 1.

1. Basándote en ANALISIS_TECNICO.md, diseñá el enfoque de solución
2. Escribí ARQUITECTURA_SOLUCION.md con:
   - Enfoque elegido y justificación (por qué esta solución y no otra)
   - Componentes a modificar con descripción del cambio esperado
   - Cambios de BD necesarios: DDL/DML si aplica
   - Impacto en otros módulos (blast radius)
   - Estrategia de rollback si hay riesgo
3. Escribí NOTAS_IMPLEMENTACION.md con:
   - Convenciones obligatorias (RIDIOMA para mensajes, Oracle DAL sin EF, Log.Error/Log.Info)
   - Gotchas y trampas del módulo afectado
   - Orden de ejecución recomendado (BD primero si hay cambios de schema)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FASE 3 — PLANIFICAR (sub-agente Planificador)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Objetivo: convertir la arquitectura en tareas ejecutables por DEV.

1. Escribí TAREAS_DESARROLLO.md con checklist de tareas directamente ejecutables:
   - Formato: `- [ ] <Tarea>` para cada item
   - Cada tarea indica: archivo exacto + cambio exacto + convención aplicable
   - Tareas de BD primero (RIDIOMA, DDL, DML) con el SQL exacto si es corto
   - Criterios de aceptación verificables que QA usará
   - Reemplazá TODOS los placeholders "_A completar por PM_"
2. Completá INCIDENTE.md si tiene placeholders

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FINALIZACIÓN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Cuando las 3 fases estén completas y TODOS los archivos guardados:
- Creá {rel_folder}/PM_COMPLETADO.flag con el texto 'ok'

Si encontrás un bloqueante insalvable en cualquier fase:
- Creá {rel_folder}/PM_ERROR.flag con la descripción del problema
- No crees PM_COMPLETADO.flag

No preguntes — ejecutá las 3 fases directamente."""
    return _apply_agent_config("pm", _pm_prompt)


def build_dev_prompt(ticket_folder: str, ticket_id: str, workspace_root: str) -> str:
    rel_folder   = _to_workspace_relative(ticket_folder, workspace_root)
    code_context = _inject_code_context(ticket_folder, ticket_id, workspace_root)

    # Q-02: Pre-flight Handoff Score — prepend score del análisis PM
    _handoff_block = _build_handoff_score_section(ticket_folder)

    # Q-01: Semantic Anchor Injection — inyectar fragmentos reales de código
    _semantic_anchors = _build_semantic_anchors_section(ticket_folder, ticket_id, workspace_root)

    # X-01: Golden Examples — ejemplos de tickets similares exitosos (primera pasada QA)
    _golden_examples = _build_golden_examples_section(ticket_folder, "dev", top_k=2)

    _dev_prompt = _ticket_header(ticket_id, "dev") + f"""{_handoff_block}Implementá la incidencia del ticket #{ticket_id}.
{_semantic_anchors}{_golden_examples}
Carpeta de trabajo: {rel_folder}/

Trabajá en 3 fases secuenciales. Completá cada fase antes de pasar a la siguiente.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FASE 1 — LOCALIZAR (sub-agente Localizador)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Objetivo: encontrar exactamente QUÉ archivos y líneas tocar. NO escribas código todavía.

1. Leé en este orden: INCIDENTE.md → ANALISIS_TECNICO.md → ARQUITECTURA_SOLUCION.md → NOTAS_IMPLEMENTACION.md → TAREAS_DESARROLLO.md
2. Para cada tarea de TAREAS_DESARROLLO.md, navegá el código y ubicá:
   - Archivo exacto (ruta completa)
   - Número de línea o rango
   - Snippet del código actual (3 líneas de contexto)
3. Escribí BUG_LOCALIZATION.md con esa información por tarea, incluyendo el orden de ejecución recomendado

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FASE 2 — IMPLEMENTAR (sub-agente Implementador)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Objetivo: ejecutar todos los cambios de código.

1. Seguí el orden de BUG_LOCALIZATION.md
2. Modificá únicamente los archivos y líneas listados
3. Respetá siempre: RIDIOMA para mensajes al usuario, Oracle DAL sin Entity Framework, Log.Error en catch y Log.Info en operaciones importantes
4. Ejecutá los cambios de BD si los hay (RIDIOMA inserts, DDL)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FASE 3 — DOCUMENTAR (sub-agente Documentador)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Objetivo: documentar los cambios para QA.

1. Creá DEV_COMPLETADO.md en {rel_folder}/ con:
   ## Archivos modificados
   - <ruta relativa al workspace>
   ## Resumen de cambios por tarea
   ### Tarea N: <título>
   <qué se hizo exactamente>
   ## Cambios en BD
   <DDL/DML ejecutados, o "Ninguno">
   ## Observaciones
   <pendientes o riesgos; o "Sin observaciones">
2. Creá GIT_CHANGES.md con un resumen de cambios para el commit message

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FINALIZACIÓN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DEV_COMPLETADO.md es la señal del pipeline — crealo solo cuando las 3 fases estén completas.
Si encontrás un bloqueante: creá {rel_folder}/DEV_ERROR.flag con diagnóstico detallado.
No preguntes — ejecutá las 3 fases directamente.
{code_context}{_inject_pitfall_warnings(ticket_folder)}"""
    return _apply_agent_config("dev", _dev_prompt)


def build_tester_prompt(ticket_folder: str, ticket_id: str, workspace_root: str) -> str:
    rel_folder = _to_workspace_relative(ticket_folder, workspace_root)

    # ── Inyectar GIT_CHANGES.md / DEV_COMPLETADO.md ──────────────────────────
    git_changes_path = os.path.join(ticket_folder, "GIT_CHANGES.md")
    dev_completado_path = os.path.join(ticket_folder, "DEV_COMPLETADO.md")

    git_section = ""
    if os.path.exists(git_changes_path):
        git_content = _read_file_safe(git_changes_path, max_chars=4000)
        if git_content:
            git_section = f"\n\n---\n## Cambios declarados por DEV (GIT_CHANGES.md)\n\n{git_content}\n\n---\n"

    dev_completado_section = ""
    if os.path.exists(dev_completado_path):
        dev_content = _read_file_safe(dev_completado_path, max_chars=5000)
        if dev_content:
            dev_completado_section = f"\n\n---\n## DEV_COMPLETADO.md — archivos modificados y resumen\n\n{dev_content}\n\n---\n"

    # ── Extraer criterios de aceptación de TAREAS_DESARROLLO.md ──────────────
    acceptance_criteria_section = ""
    tareas_path = os.path.join(ticket_folder, "TAREAS_DESARROLLO.md")
    if os.path.exists(tareas_path):
        tareas_content = _read_file_safe(tareas_path, max_chars=6000)
        if tareas_content:
            acceptance_criteria_section = f"""

---

## Criterios de aceptación (de TAREAS_DESARROLLO.md)

Los siguientes criterios fueron definidos por PM. Tu tarea es verificar CADA uno con evidencia:

{tareas_content}

---
"""

    # ── Extraer archivos modificados de DEV_COMPLETADO.md para checklist ─────
    modified_files_hint = ""
    if os.path.exists(dev_completado_path):
        dev_content_raw = _read_file_safe(dev_completado_path, max_chars=3000)
        if dev_content_raw:
            import re as _re
            found = _re.findall(
                r'\b[\w/\\]+\.(?:cs|aspx|aspx\.cs|sql|vb|config)\b',
                dev_content_raw, _re.IGNORECASE
            )
            unique_files = list(dict.fromkeys(found))  # dedup preservando orden
            if unique_files:
                files_list = "\n".join(f"  - {f}" for f in unique_files[:20])
                modified_files_hint = f"""

## Archivos a auditar (extraídos de DEV_COMPLETADO.md)

Los siguientes archivos fueron modificados por DEV. Tu CODE_REVIEW.md **debe cubrir cada uno**:

{files_list}

Si alguno no existe en el workspace, reportalo como BLOQUEANTE.
"""

    git_section = ""
    if os.path.exists(git_changes_path):
        git_content = _read_file_safe(git_changes_path, max_chars=4000)
        if git_content:
            git_section = f"\n\n---\n## Cambios de código (GIT_CHANGES.md)\n\n{git_content}\n\n---\n"

    _tester_prompt = _ticket_header(ticket_id, "tester") + f"""Realizá pruebas exhaustivas de la implementación del ticket #{ticket_id}.

Carpeta de trabajo: {rel_folder}/

TU HIPÓTESIS DE PARTIDA: esta implementación tiene al menos un defecto. Tu trabajo es encontrarlo o refutarlo con evidencia concreta. Aprobás cuando los hechos te lo demuestran — no antes.

Para CADA verificación, pegá el fragmento de código o resultado de query como evidencia. Una verificación sin evidencia cuenta como FAIL.
{dev_completado_section}{git_section}{acceptance_criteria_section}{modified_files_hint}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FASE 1 — CODE REVIEW con evidencia obligatoria (sub-agente Revisor)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Objetivo: revisión estática del código. NO ejecutes pruebas funcionales todavía.

1. Para cada archivo modificado listado arriba, auditá las 10 reglas del proyecto (R1-R10).
2. Para cada regla, respondé con `[PASS]`, `[FAIL]` o `[N/A - motivo]` + pegá el fragmento de código auditado.
3. Buscá activamente las señales de alerta: catch vacíos, conversiones de input sin validación, SQL con concatenación de variables, acceso a Rows[0] sin verificar Count, ToString() sobre null potencial, UPDATE sin WHERE.

Escribí CODE_REVIEW.md con:
  - Resultado global: SIN ISSUES / CON ADVERTENCIAS / CON BLOQUEANTES
  - Por cada archivo auditado: tabla de reglas con [PASS]/[FAIL]/[N/A] + fragmento de evidencia
  - Lista de issues: # | Severidad | Archivo | Línea | Descripción exacta | Corrección requerida

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FASE 2 — PRUEBAS FUNCIONALES con evidencia (sub-agente Ejecutor)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Objetivo: verificar que CADA criterio de aceptación listado en TAREAS_DESARROLLO.md se cumple.

1. Para cada criterio de aceptación, diseñá el caso de prueba correspondiente.
2. Para cambios en Dalc/BD: ejecutá las queries de validación y pegá el resultado.
3. Probá siempre el escenario nulo/vacío y el escenario límite.

Escribí TEST_RESULTS.md con tabla:
| # | Criterio verificado | Input/Escenario | Resultado esperado | Evidencia real (código/query/output) | PASS/FAIL |

Para cambios DDL, la evidencia DEBE incluir el resultado de:
SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, NUMERIC_PRECISION, NUMERIC_SCALE, IS_NULLABLE
FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'TABLA' AND COLUMN_NAME IN ('campos nuevos')

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FASE 3 — VEREDICTO (sub-agente Árbitro)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Objetivo: consolidar CODE_REVIEW.md + TEST_RESULTS.md y emitir veredicto.

Criterios estrictos:
- APROBADO: cero BLOQUEANTES + TODOS los casos felices PASS + evidencia completa en cada check
- CON OBSERVACIONES: cero BLOQUEANTES + ADVERTENCIAS presentes + caso feliz PASS + evidencia completa
- RECHAZADO: ≥1 BLOQUEANTE, O ≥1 caso feliz FAIL, O evidencia faltante en check crítico

Creá TESTER_COMPLETADO.md con:
## Veredicto: [APROBADO / CON OBSERVACIONES / RECHAZADO]
## Resumen ejecutivo
(qué se probó, cuántos checks pasaron, cuántos fallaron)
## Issues bloqueantes
(lista numerada de BLOQUEANTES del CODE_REVIEW + casos FAIL de TEST_RESULTS; o "Ninguno")
## Observaciones no bloqueantes
(lista de ADVERTENCIAS; o "Ninguna")
## Criterios de aceptación verificados
(lista de los criterios de TAREAS_DESARROLLO.md con [VERIFICADO PASS] o [VERIFICADO FAIL])
## Recomendaciones para DEV (si RECHAZADO o CON OBSERVACIONES)
(qué exactamente debe corregir, con referencia a archivo y línea cuando sea posible)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FINALIZACIÓN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TESTER_COMPLETADO.md es la señal del pipeline — crealo solo cuando las 3 fases estén completas.
Si hay un error crítico que imposibilita el testing: creá {rel_folder}/TESTER_ERROR.flag con la descripción.
No preguntes — ejecutá las 3 fases directamente."""
    return _apply_agent_config("tester", _tester_prompt)


_STAGE_LABELS = {"pm": "Análisis PM", "dev": "Implementación Dev", "tester": "QA Testing", "doc": "Documentación"}
_STAGE_FLAG   = {"pm": "PM_COMPLETADO.flag", "dev": "DEV_COMPLETADO.md", "tester": "TESTER_COMPLETADO.md", "doc": "DOC_COMPLETADO.flag"}
_STAGE_ERROR  = {"pm": "PM_ERROR.flag", "dev": "DEV_ERROR.flag", "tester": "TESTER_ERROR.flag", "doc": "DOC_ERROR.flag"}


def build_doc_agent_prompt(ticket_folder: str, ticket_id: str, workspace_root: str,
                           kb_path: str) -> str:
    """
    Prompt para el agente DOC — corre después de TESTER y actualiza KNOWLEDGE_BASE.md.

    KNOWLEDGE_BASE.md es un único archivo indexado por categoría/módulo.
    Permite acceso inmediato al conocimiento acumulado sin recorrer carpetas de tickets.

    Estructura de KNOWLEDGE_BASE.md:
      - Encabezado con estadísticas (N tickets, última actualización)
      - Tabla de contenidos por categoría (links a anclas)
      - Secciones por categoría, cada una con entradas de tickets

    Categorías predefinidas (el agente elige la más adecuada o crea una nueva):
      UI / Formularios | Oracle / Queries | Procesos Batch | Seguridad / Accesos |
      Reportes | Integraciones | Rendimiento | Configuración | Otros
    """
    rel_folder = _to_workspace_relative(ticket_folder, workspace_root)
    try:
        kb_rel = os.path.relpath(kb_path, workspace_root).replace("\\", "/")
    except ValueError:
        kb_rel = kb_path.replace("\\", "/")

    kb_exists = os.path.exists(kb_path)
    kb_note = (
        f"> ⚠️ Ya existe KNOWLEDGE_BASE.md — **agregá** la nueva entrada, no sobrescribas las existentes.\n"
        if kb_exists else
        f"> ℹ️ No existe KNOWLEDGE_BASE.md — crealo desde cero con la estructura indicada.\n"
    )

    _doc_prompt = f"""Documentá el ticket #{ticket_id} en la base de conocimiento del proyecto.

Carpeta del ticket: {rel_folder}/
Archivo de knowledge base: {kb_rel}
{kb_note}
## Tu tarea

Leé los artefactos del ticket y agregá una entrada concisa y navegable a `{kb_rel}`.

### Paso 1 — Leer el ticket

Leé estos archivos del ticket (los que existan):
- `{rel_folder}/INC-{ticket_id}.md` — descripción original del problema
- `{rel_folder}/INCIDENTE.md` — análisis del incidente
- `{rel_folder}/ANALISIS_TECNICO.md` — diagnóstico técnico del PM
- `{rel_folder}/DEV_COMPLETADO.md` — resumen de cambios del Dev
- `{rel_folder}/TESTER_COMPLETADO.md` — veredicto y hallazgos de QA

### Paso 2 — Clasificar el ticket

Elegí la categoría más adecuada (o creá una nueva si no encaja):
- **UI / Formularios** — pantallas, formularios Frm*, grillas, validaciones en UI
- **Oracle / Queries** — queries SQL, stored procedures, tablas, índices, datos
- **Procesos Batch** — jobs schedulados, procesos masivos, importaciones/exportaciones
- **Seguridad / Accesos** — permisos, roles, autenticación, auditoría
- **Reportes** — generación de reportes, exports, Crystal Reports, SSRS
- **Integraciones** — servicios externos, APIs, mensajería, SOAP/REST
- **Rendimiento** — timeouts, lentitud, memory leaks, optimizaciones
- **Configuración** — parámetros de sistema, archivos de config, instalación
- **Otros** — todo lo que no encaje arriba

### Paso 3 — Escribir la entrada

La entrada para este ticket debe tener este formato exacto:

```
#### [#{ticket_id}] <Título breve del problema — máx 80 chars>

| Campo | Detalle |
|-------|---------|
| **Problema** | Una línea: qué fallaba y en qué contexto |
| **Causa raíz** | Por qué ocurría (tabla/clase/query/config específica) |
| **Solución** | Qué se cambió — archivos/tablas/procedimientos concretos |
| **Veredicto QA** | APROBADO / CON OBSERVACIONES / RECHAZADO |
| **Archivos clave** | Lista de archivos/tablas principales que se tocaron |
| **Gotchas** | Trampas, efectos secundarios o cosas a tener en cuenta (puede ser vacío) |
```

### Paso 4 — Actualizar KNOWLEDGE_BASE.md

**Si el archivo NO existe** — crealo con esta estructura:

```markdown
# Knowledge Base — <nombre del proyecto>

> Tickets documentados: 1 | Última actualización: <fecha>

## Tabla de contenidos

- [UI / Formularios](#ui--formularios)
- [Oracle / Queries](#oracle--queries)
- ... (solo las categorías que tengan entradas)

---

## <Categoría elegida>

<entrada del ticket>
```

**Si el archivo YA EXISTE** — hacé solo esto:
1. Encontrá (o creá) la sección de la categoría elegida
2. Agregá la entrada del ticket al final de esa sección
3. Si la categoría es nueva, agregala en la Tabla de contenidos
4. Actualizá el contador de tickets y la fecha en el encabezado

### Paso 5 — Señalizar completado

Cuando hayas guardado `{kb_rel}` correctamente, creá el archivo:
`{rel_folder}/DOC_COMPLETADO.flag` con el texto `ok`

Si hay un bloqueante real que impide documentar, creá:
`{rel_folder}/DOC_ERROR.flag` con la descripción del problema

**Importante:** No preguntes — leé, clasificá, escribí y señalizá."""
    return _apply_agent_config("doc", _doc_prompt)


def build_retry_prompt(ticket_folder: str, ticket_id: str, workspace_root: str,
                       stage: str, retry_num: int = 1,
                       validation_result=None) -> str:
    """
    Prompt para cuando una etapa expiró por timeout o falló la validación.
    Inyecta:
      - Qué archivos ya existen y su tamaño
      - Qué issues específicos detectó el validador (si validation_result provisto)
      - Contenido parcial de los archivos incompletos para no partir de cero
    """
    rel_folder  = _to_workspace_relative(ticket_folder, workspace_root)
    stage_label = _STAGE_LABELS.get(stage, stage.upper())
    ok_flag     = _STAGE_FLAG.get(stage, f"{stage.upper()}_COMPLETADO")

    # Estado actual de la carpeta con tamaños
    existing = []
    try:
        for fname in sorted(os.listdir(ticket_folder)):
            if not fname.startswith("."):
                fpath = os.path.join(ticket_folder, fname)
                size  = os.path.getsize(fpath)
                existing.append(f"  - {fname} ({size:,} bytes)")
    except Exception:
        pass
    existing_str = "\n".join(existing) if existing else "  (carpeta vacía)"

    # Issues específicos del validador
    issues_section = ""
    if validation_result and hasattr(validation_result, "issues") and validation_result.issues:
        issues_lines = "\n".join(f"  • {i}" for i in validation_result.issues)
        issues_section = f"""
## Problemas detectados automáticamente que debés corregir

{issues_lines}

"""

    # Contenido parcial de archivos con issues para no reiniciar desde cero
    partial_content_section = ""
    if validation_result and hasattr(validation_result, "issues") and validation_result.issues:
        partial_parts = []
        # Extraer nombres de archivos mencionados en los issues
        import re
        file_mentions = re.findall(r'([\w_]+\.(?:md|sql|flag))', " ".join(validation_result.issues))
        for fname in dict.fromkeys(file_mentions):  # deduplica preservando orden
            fpath = os.path.join(ticket_folder, fname)
            if os.path.exists(fpath):
                content = _read_file_safe(fpath, max_chars=1500)
                if content:
                    partial_parts.append(f"### Contenido actual de {fname}\n```\n{content}\n```")
        if partial_parts:
            partial_content_section = (
                "\n## Contenido parcial ya generado (completar, no sobrescribir)\n\n"
                + "\n\n".join(partial_parts)
            )

    return f"""REINTENTO {retry_num} — {stage_label} del ticket #{ticket_id}

El pipeline detectó que la etapa de {stage_label} no completó correctamente.
Este es el reintento #{retry_num}.

Carpeta de trabajo: {rel_folder}/
{issues_section}
## Estado actual de la carpeta

{existing_str}
{partial_content_section}

## Instrucciones para el reintento

1. Revisá los PROBLEMAS DETECTADOS arriba — son los que impidieron que avance
2. NO sobreescribas trabajo ya realizado en otros archivos — completá solo lo que falta
3. Para los archivos marcados con problema: corregí exactamente lo que indica el error
4. Al terminar, creá {rel_folder}/{ok_flag} como señal de completado
5. Si hay un bloqueante real e insalvable, creá {rel_folder}/{_STAGE_ERROR.get(stage, stage.upper() + '_ERROR.flag')} con diagnóstico exacto
6. No preguntes — ejecutá directamente basándote en lo que ya está en la carpeta"""


def build_rework_prompt(ticket_folder: str, ticket_id: str, workspace_root: str,
                        qa_findings: list[str], rework_num: int = 1) -> str:
    """
    M-01: Prompt para DEV cuando QA reportó issues y se necesita rework.
    Inyecta los findings específicos de QA para que DEV corrija exactamente
    lo que falló, sin reiniciar el análisis desde cero.
    """
    rel_folder  = _to_workspace_relative(ticket_folder, workspace_root)
    code_context = _inject_code_context(ticket_folder, ticket_id, workspace_root)

    # Leer lo que DEV ya implementó
    dev_summary = _read_file_safe(os.path.join(ticket_folder, "DEV_COMPLETADO.md"),
                                  max_chars=2000)
    git_changes = _read_file_safe(os.path.join(ticket_folder, "GIT_CHANGES.md"),
                                  max_chars=1500)

    # Formatear findings de QA
    if qa_findings:
        findings_str = "\n".join(f"  {i+1}. {f}" for i, f in enumerate(qa_findings))
    else:
        # Leer TESTER_COMPLETADO.md completo si no hay findings extraídos
        tester_content = _read_file_safe(
            os.path.join(ticket_folder, "TESTER_COMPLETADO.md"), max_chars=2000
        )
        findings_str = tester_content or "Ver TESTER_COMPLETADO.md para el detalle"

    return f"""REWORK DEV — Correcciones solicitadas por QA — Ticket #{ticket_id}
Ciclo de rework: {rework_num}

QA revisó tu implementación y encontró los siguientes problemas que debés corregir:

{findings_str}

---

Carpeta de trabajo: {rel_folder}/

Tu implementación anterior:
{dev_summary}

Archivos que modificaste:
{git_changes or '(ver DEV_COMPLETADO.md)'}

---

Instrucciones para el rework:

1. Leé cada observación de QA arriba — son los únicos cambios requeridos
2. NO reescribas lo que ya funcionó — solo corregí los puntos específicos
3. Revisá los archivos que modificaste buscando exactamente el problema reportado
4. Implementá las correcciones respetando las convenciones del proyecto
5. Al finalizar las correcciones, REEMPLAZÁ DEV_COMPLETADO.md con un nuevo reporte que incluya:
   - Los cambios originales
   - Los cambios del rework (sección separada "## Rework {rework_num}")
   - Estado de cada observación de QA: RESUELTO / EN PROGRESO
6. Borrá el TESTER_COMPLETADO.md anterior para que QA re-valide desde cero
7. Creá {rel_folder}/DEV_COMPLETADO.md actualizado como señal de que el rework está listo
8. No creés DEV_ERROR.flag a menos que haya un bloqueante real e insalvable
9. No preguntes — ejecutá directamente
{code_context}"""


def build_pm_revision_prompt(ticket_folder: str, ticket_id: str, workspace_root: str,
                              accumulated_issues: list, cycle_num: int) -> str:
    """
    Y-01: Prompt para PM cuando el ciclo completo QA→DEV falló N veces.
    PM recibe el historial completo de todos los rechazos anteriores acumulados
    para que pueda replantear el enfoque sin repetir los mismos errores.
    """
    rel_folder   = _to_workspace_relative(ticket_folder, workspace_root)
    code_context = _inject_code_context(ticket_folder, ticket_id, workspace_root)

    # Formatear historial acumulado de issues
    if accumulated_issues:
        issues_str = "\n".join(f"  {i+1}. {issue}" for i, issue in enumerate(accumulated_issues))
    else:
        issues_str = "  (ver ciclos anteriores en CORRECTION_MEMORY.json)"

    # Detectar issues recurrentes (aparecen en más de un ciclo)
    from collections import Counter as _Counter
    issue_counts = _Counter(accumulated_issues)
    recurring = [issue for issue, count in issue_counts.items() if count > 1]
    recurring_str = ""
    if recurring:
        recurring_str = "\n\n**⚠️ ISSUES RECURRENTES (aparecieron en múltiples ciclos — prioridad máxima):**\n"
        recurring_str += "\n".join(f"  - {r}" for r in recurring[:5])

    return f"""REVISIÓN PM — Ciclo {cycle_num} — Ticket #{ticket_id}

El ciclo completo PM→DEV→QA falló {cycle_num - 1} veces. Es necesario replantear el enfoque.

## Historial acumulado de issues de QA (todos los ciclos):

{issues_str}
{recurring_str}

---

Carpeta de trabajo: {rel_folder}/

## Instrucciones para la revisión:

1. LEÉ el ANALISIS_TECNICO.md e ARQUITECTURA_SOLUCION.md existentes
2. Identificá qué estuvo MAL en el enfoque que causó los issues repetidos
3. NO reutilices la misma solución — proponé un enfoque diferente para los puntos problemáticos
4. Prestá especial atención a los issues que aparecen en múltiples ciclos (indicados arriba)
5. Actualizá ANALISIS_TECNICO.md y ARQUITECTURA_SOLUCION.md con el nuevo enfoque
6. Marcá explícitamente qué cambió respecto al ciclo anterior (sección "## Cambios de enfoque ciclo {cycle_num}")
7. Actualizá TAREAS_DESARROLLO.md con las tareas revisadas
8. Al terminar, creá {rel_folder}/PM_COMPLETADO.flag
9. NO preguntes — ejecutá directamente
{code_context}"""


def build_error_fix_prompt(ticket_folder: str, ticket_id: str, workspace_root: str,
                            stage: str, error_context: str) -> str:
    """
    Prompt especializado cuando el agente anterior dejó un error flag.
    Incluye el motivo del error y el estado actual de la carpeta para
    que el agente de corrección entienda exactamente qué falló.
    """
    rel_folder  = _to_workspace_relative(ticket_folder, workspace_root)
    stage_label = _STAGE_LABELS.get(stage, stage.upper())
    ok_flag     = _STAGE_FLAG.get(stage, f"{stage.upper()}_COMPLETADO")

    # Leer INC para dar contexto del problema original
    inc_summary = _read_file_safe(os.path.join(ticket_folder, f"INC-{ticket_id}.md"),
                                  max_chars=1500)

    # Leer el archivo más relevante para el stage (lo que ya hizo el agente anterior)
    relevant_files = {
        "pm":     ["ANALISIS_TECNICO.md", "INCIDENTE.md"],
        "dev":    ["TAREAS_DESARROLLO.md", "ANALISIS_TECNICO.md"],
        "tester": ["DEV_COMPLETADO.md", "TAREAS_DESARROLLO.md"],
    }
    context_parts = []
    for fname in relevant_files.get(stage, []):
        content = _read_file_safe(os.path.join(ticket_folder, fname), max_chars=800)
        if content:
            context_parts.append(f"### {fname}\n{content}")
    context_str = "\n\n".join(context_parts) if context_parts else "(sin contexto previo)"

    return f"""CORRECCIÓN DE ERROR — {stage_label} del ticket #{ticket_id}

El agente anterior reportó el siguiente error:

> {error_context}

Tu misión es diagnosticar por qué falló y completar la etapa de {stage_label}.

Carpeta de trabajo: {rel_folder}/

--- Contexto del ticket ---
{inc_summary}

--- Trabajo previo disponible ---
{context_str}

Instrucciones:
1. Leé el error reportado arriba y entendé por qué ocurrió
2. Buscá en el código fuente / BD lo que el agente anterior no pudo encontrar
3. Completá la etapa de {stage_label} superando el bloqueante
4. Al terminar exitosamente, creá {rel_folder}/{ok_flag}
5. Si el bloqueante persiste y es un impedimento real (no un error de búsqueda), creá
   {rel_folder}/{_STAGE_ERROR.get(stage, stage.upper() + '_ERROR.flag')} con diagnóstico detallado
6. No preguntes — investigá y resolvé directamente"""


def build_dba_prompt(ticket_folder: str, ticket_id: str, workspace_root: str) -> str:
    """
    Y-04: Prompt para el agente DBA Especialista.
    Genera DB_SOLUTION.sql con todos los cambios Oracle necesarios para el ticket.
    """
    rel_folder = _to_workspace_relative(ticket_folder, workspace_root)

    # Leer análisis PM para extraer requerimientos DB
    arch_content = _read_file_safe(
        os.path.join(ticket_folder, "ARQUITECTURA_SOLUCION.md"), max_chars=3000
    )
    tareas_content = _read_file_safe(
        os.path.join(ticket_folder, "TAREAS_DESARROLLO.md"), max_chars=2000
    )

    return f"""AGENTE DBA — Generación de Script Oracle — Ticket #{ticket_id}

Sos el DBA Especialista del pipeline Stacky. Tu tarea es analizar el ticket
y generar el script Oracle COMPLETO que DEV necesitará para implementar el fix.

## Análisis del PM (arquitectura):
{arch_content or '(ver carpeta del ticket)'}

## Tareas de desarrollo:
{tareas_content or '(ver TAREAS_DESARROLLO.md)'}

---

## Tu output debe ser el archivo `{rel_folder}/DB_SOLUTION.sql` que contenga:

1. **Comentario de encabezado** con: ticket, descripción, fecha, autor (DBA Agent)
2. **Verificaciones pre-ejecución** (SELECT que confirman que las tablas/columnas existen)
3. **Script DDL/DML** con todos los cambios necesarios:
   - ALTER TABLE / ADD COLUMN (con nullability y default correctos)
   - CREATE INDEX / SEQUENCE si aplica
   - INSERT INTO RIDIOMA para mensajes nuevos (idioma 1=Español, 2=Portugués)
   - INSERT INTO RCONTROLES para campos de grilla si aplica
   - Cualquier otra instrucción Oracle requerida
4. **Script de rollback** (sección comentada con el UNDO de cada instrucción)
5. **Verificaciones post-ejecución** (SELECT que confirman que el script se aplicó correctamente)

## Convenciones OBLIGATORIAS:

- NUNCA hardcodeés mensajes en el código — todo mensaje va a RIDIOMA
- Verificar NULLABLE con ALL_TAB_COLUMNS antes de asumir comportamiento
- Usar `SELECT MAX(IDTEXTO) FROM RIDIOMA` para obtener el próximo ID de mensaje
- Incluir COMMIT al final
- Si un cambio es riesgoso, agregar comentario de advertencia

## Al terminar:

1. Guardá el script como `{rel_folder}/DB_SOLUTION.sql`
2. Creá `{rel_folder}/DB_READY.flag` como señal de completado
3. Si hay un bloqueante, creá `{rel_folder}/DBA_ERROR.flag` con el diagnóstico
4. No preguntes — ejecutá directamente"""


def build_tl_prompt(ticket_folder: str, ticket_id: str, workspace_root: str) -> str:
    """Y-05: Prompt para el Tech Lead Reviewer."""
    rel_folder   = _to_workspace_relative(ticket_folder, workspace_root)
    arch_content = _read_file_safe(
        os.path.join(ticket_folder, "ARQUITECTURA_SOLUCION.md"), max_chars=4000
    )
    tareas = _read_file_safe(
        os.path.join(ticket_folder, "TAREAS_DESARROLLO.md"), max_chars=2000
    )
    analisis = _read_file_safe(
        os.path.join(ticket_folder, "ANALISIS_TECNICO.md"), max_chars=2000
    )

    return f"""TECH LEAD REVIEW — Ticket #{ticket_id}

Sos el Tech Lead Reviewer del pipeline Stacky. Revisá el análisis del PM
ANTES de que DEV empiece a implementar. Tu objetivo: detectar errores de
arquitectura temprano, evitando ciclos costosos PM→DEV→QA fallidos.

## Análisis técnico del PM:
{analisis or '(ver ANALISIS_TECNICO.md)'}

## Arquitectura propuesta:
{arch_content or '(ver ARQUITECTURA_SOLUCION.md)'}

## Tareas propuestas:
{tareas or '(ver TAREAS_DESARROLLO.md)'}

---

## Tu evaluación debe cubrir:

1. **Causa raíz:** ¿El PM identificó correctamente dónde está el bug?
2. **Arquitectura:** ¿El enfoque es correcto? ¿Hay riesgos de blast radius no considerados?
3. **Completitud:** ¿Las tareas cubren todos los casos incluyendo edge cases?
4. **Convenciones:** ¿Se respetan las reglas RIDIOMA, Oracle, WebForms del proyecto?
5. **Riesgos:** ¿Hay cambios que podrían romper otros módulos?

## Decisión:

**APROBAR** → Creá `{rel_folder}/TL_APPROVED.flag`
**RECHAZAR** → Creá `{rel_folder}/TL_REJECTED.md` con:
  - Problema específico encontrado
  - Instrucción concreta de qué replantear
  - NO rechaces sin proporcionar dirección de corrección

No preguntes — ejecutá directamente."""


def build_ui_tester_prompt(ticket_folder: str, ticket_id: str, workspace_root: str,
                            app_url: str = "", extra_notes: str = "") -> str:
    """
    Construye el prompt para el agente UI Tester que simula al usuario final
    usando Playwright para interactuar con la interfaz de la aplicación.
    """
    rel_folder = _to_workspace_relative(ticket_folder, workspace_root)

    url_section = ""
    if app_url:
        url_section = f"\n**URL de la aplicación:** {app_url}\n"
    else:
        url_section = "\n**URL de la aplicación:** Determinar desde la configuración del proyecto o INC-{ticket_id}.md\n".replace("{ticket_id}", ticket_id)

    notes_section = ""
    if extra_notes:
        notes_section = f"\n## Instrucciones adicionales del usuario\n\n{extra_notes}\n"

    # Leer resumen del ticket
    inc_summary = _read_file_safe(os.path.join(ticket_folder, f"INC-{ticket_id}.md"), max_chars=600)
    dev_summary = _read_file_safe(os.path.join(ticket_folder, "DEV_COMPLETADO.md"), max_chars=800)

    return f"""Actuá como UI Tester — simulá al usuario final interactuando con la interfaz de la aplicación para verificar el ticket #{ticket_id}.

Carpeta de trabajo: {rel_folder}/
{url_section}
## Contexto del ticket
{inc_summary or "Ver INC-" + ticket_id + ".md en la carpeta de trabajo"}

## Qué implementó el Developer
{dev_summary or "Ver DEV_COMPLETADO.md en la carpeta de trabajo"}
{notes_section}
## Tu misión

Usá **Playwright** (o la herramienta de automatización disponible) para:

1. **Leer el contexto** del ticket:
   - `{rel_folder}/INC-{ticket_id}.md` — caso de uso del usuario
   - `{rel_folder}/TAREAS_DESARROLLO.md` — criterios de aceptación
   - `{rel_folder}/DEV_COMPLETADO.md` — qué se implementó y cómo probar

2. **Instalar Playwright si es necesario:**
   ```
   pip install playwright
   playwright install chromium
   ```

3. **Escribir y ejecutar un script de prueba** que:
   - Navegue a la URL de la aplicación
   - Realice el flujo del caso de uso descrito en el ticket
   - Verifique que el comportamiento reportado en el bug ya no ocurre
   - Verifique los criterios de aceptación de TAREAS_DESARROLLO.md
   - Tome capturas de pantalla de los pasos clave
   - Reporte cualquier error de consola o excepción que aparezca

4. **Guardar el script** como `{rel_folder}/UI_TEST_{ticket_id}.py`

5. **Crear `{rel_folder}/UI_TESTER_COMPLETADO.md`** con:
   - Resultado: ✅ APROBADO / ⚠ CON OBSERVACIONES / ❌ RECHAZADO
   - Flujo probado (pasos realizados)
   - Capturas de pantalla generadas (paths)
   - Errores encontrados (si los hay)
   - Comportamiento esperado vs real
   - Tiempo total de prueba

## Reglas
- Probá SIEMPRE el camino feliz (golden path) primero
- Si el elemento UI no existe o la URL da error, reportalo como bloqueante
- No modifiques código fuente — solo ejecutás pruebas
- Si Playwright no puede usarse (entorno headless no disponible), indicá los pasos manuales detallados que el QA debe ejecutar"""


# ── Sub-agentes especializados por etapa ──────────────────────────────────────
# PM:  Investigador → Arquitecto → Planificador
# DEV: Localizador  → Implementador → Documentador
# QA:  Revisor      → Ejecutor      → Árbitro
# ─────────────────────────────────────────────────────────────────────────────


def build_pm_inv_prompt(ticket_folder: str, ticket_id: str, workspace_root: str) -> str:
    """Sub-agente PM-Investigador: busca la causa raíz, no diseña soluciones."""
    rel_folder   = _to_workspace_relative(ticket_folder, workspace_root)
    code_context = _inject_code_context(ticket_folder, ticket_id, workspace_root)

    docs_path = _find_project_docs(ticket_folder)
    docs_note = (
        f"\n**Contexto del proyecto:** Leé `{_to_workspace_relative(docs_path, workspace_root)}` "
        f"antes de investigar el código.\n"
        if docs_path else
        "\n**Nota:** No hay PROJECT_DOCS.md — investigá el código directamente.\n"
    )

    return f"""PM-Investigador — Ticket #{ticket_id}

Tu ÚNICA tarea: INVESTIGAR la causa raíz. NO diseñes soluciones ni escribas tareas.

Carpeta del ticket: {rel_folder}/
{docs_note}
1. Leé INC-{ticket_id}.md para entender el síntoma exacto
2. Buscá en el código fuente el componente que falla (clase/método/SP)
3. Ejecutá queries Oracle para entender el estado de los datos
4. Documentá QUÉ está mal, EN QUÉ archivo/línea y POR QUÉ

**Tu output obligatorio:**

`ANALISIS_TECNICO.md` con secciones:
- **Síntoma**: qué reporta el usuario (verbatim del ticket)
- **Causa raíz**: clase/método/SP específico + por qué falla
- **Evidencia**: queries ejecutadas y sus resultados relevantes
- **Archivos afectados**: rutas completas relativas al workspace
- **Tablas BD involucradas**: con columnas relevantes y datos de ejemplo

`QUERIES_ANALISIS.sql` con todas las queries que ejecutaste para llegar a la causa raíz.

**Al terminar:** creá `{rel_folder}/INV_COMPLETADO.flag` con el texto `ok`.
**Si hay un bloqueante real:** creá `{rel_folder}/PM_ERROR.flag` con el diagnóstico.

No diseñes la solución — solo investigá y documentá evidencia.
{code_context}"""


def build_pm_arq_prompt(ticket_folder: str, ticket_id: str, workspace_root: str) -> str:
    """Sub-agente PM-Arquitecto: diseña la solución basada en el análisis del Investigador."""
    rel_folder  = _to_workspace_relative(ticket_folder, workspace_root)
    analisis    = _read_file_safe(os.path.join(ticket_folder, "ANALISIS_TECNICO.md"), max_chars=3500)
    queries_sql = _read_file_safe(os.path.join(ticket_folder, "QUERIES_ANALISIS.sql"), max_chars=1500)

    return f"""PM-Arquitecto — Ticket #{ticket_id}

El Investigador ya identificó la causa raíz. Tu tarea: DISEÑAR LA SOLUCIÓN.

Carpeta del ticket: {rel_folder}/

## Análisis del Investigador:
{analisis or "(leer ANALISIS_TECNICO.md)"}

## Queries de evidencia:
{queries_sql or "(leer QUERIES_ANALISIS.sql)"}

---

Diseñá la solución y escribí:

**ARQUITECTURA_SOLUCION.md** con:
- Enfoque elegido y justificación (por qué esta solución y no otra)
- Componentes a modificar con descripción del cambio esperado
- Cambios de BD necesarios: DDL/DML con orden de ejecución
- Impacto en otros módulos (blast radius): qué puede romperse
- Estrategia de rollback si la solución tiene riesgo

**NOTAS_IMPLEMENTACION.md** con:
- Convenciones obligatorias a respetar (RIDIOMA, Oracle DAL sin EF, Logging)
- Gotchas y trampas conocidas del módulo afectado
- Orden de ejecución recomendado para DEV (BD primero, luego código)
- Dependencias entre tareas (si A depende de B)

NO escribas tareas granulares con checklist — eso lo hace el Planificador.

**Al terminar:** creá `{rel_folder}/ARQ_COMPLETADO.flag` con el texto `ok`.
**Si la arquitectura es inviable:** creá `{rel_folder}/PM_ERROR.flag` con el diagnóstico."""


def build_pm_plan_prompt(ticket_folder: str, ticket_id: str, workspace_root: str) -> str:
    """Sub-agente PM-Planificador: convierte la arquitectura en tareas ejecutables por DEV."""
    rel_folder = _to_workspace_relative(ticket_folder, workspace_root)
    arq        = _read_file_safe(os.path.join(ticket_folder, "ARQUITECTURA_SOLUCION.md"), max_chars=3500)
    notas      = _read_file_safe(os.path.join(ticket_folder, "NOTAS_IMPLEMENTACION.md"), max_chars=2000)
    inc_file   = _read_file_safe(os.path.join(ticket_folder, f"INC-{ticket_id}.md"), max_chars=1500)

    return f"""PM-Planificador — Ticket #{ticket_id}

La arquitectura ya está definida. Tu tarea: escribir TAREAS EJECUTABLES para DEV y completar INCIDENTE.md.

Carpeta del ticket: {rel_folder}/

## Arquitectura del Arquitecto:
{arq or "(leer ARQUITECTURA_SOLUCION.md)"}

## Notas de implementación:
{notas or "(leer NOTAS_IMPLEMENTACION.md)"}

---

**TAREAS_DESARROLLO.md** — cada tarea debe ser directamente ejecutable por DEV sin preguntas:
- Formato checklist: `- [ ] <Tarea>`
- Para cada tarea: qué archivo modificar + qué cambio exacto + referencia a convención aplicable
- Incluir las tareas de BD primero (RIDIOMA, DDL, DML) con el SQL exacto si es corto
- Incluir criterios de aceptación verificables que QA usará para aprobar/rechazar

**INCIDENTE.md** (completar si tiene placeholders):
- Descripción breve del incidente (para el lector técnico)
- Impacto en el negocio / usuarios afectados
- Módulos involucrados

## Ticket original (para contexto):
{inc_file or "(leer INC-" + ticket_id + ".md)"}

**Al terminar:** creá `{rel_folder}/PM_COMPLETADO.flag` con el texto `ok`.
Este flag es la señal del pipeline completo de PM — no lo crees hasta haber guardado todos los archivos.
**Si hay un bloqueante:** creá `{rel_folder}/PM_ERROR.flag`."""


def build_dev_loc_prompt(ticket_folder: str, ticket_id: str, workspace_root: str) -> str:
    """Sub-agente DEV-Localizador: encuentra exactamente qué archivos y líneas tocar."""
    rel_folder = _to_workspace_relative(ticket_folder, workspace_root)
    tareas     = _read_file_safe(os.path.join(ticket_folder, "TAREAS_DESARROLLO.md"), max_chars=3000)
    analisis   = _read_file_safe(os.path.join(ticket_folder, "ANALISIS_TECNICO.md"), max_chars=2000)
    arq        = _read_file_safe(os.path.join(ticket_folder, "ARQUITECTURA_SOLUCION.md"), max_chars=2000)

    return f"""DEV-Localizador — Ticket #{ticket_id}

Tu ÚNICA tarea: LOCALIZAR exactamente qué archivos y líneas hay que tocar. No escribas código todavía.

Carpeta del ticket: {rel_folder}/

## Tareas a implementar:
{tareas or "(leer TAREAS_DESARROLLO.md)"}

## Análisis técnico del PM:
{analisis or "(leer ANALISIS_TECNICO.md)"}

## Arquitectura propuesta:
{arq or "(leer ARQUITECTURA_SOLUCION.md)"}

---

Navegá el código fuente y producí **BUG_LOCALIZATION.md** con exactamente:

### Por cada tarea de TAREAS_DESARROLLO.md:

```
## Tarea N: <título de la tarea>
- **Archivo**: <ruta completa relativa al workspace>
- **Línea(s)**: <número de línea o rango>
- **Código actual** (snippet con 3 líneas de contexto arriba y abajo):
  ````
  <código actual>
  ````
- **Cambio requerido**: <descripción precisa del cambio>
- **Dependencias**: <si esta tarea debe ir después de otra, indicar cuál>
```

Al final de BUG_LOCALIZATION.md, agregá:
```
## Orden de ejecución recomendado
1. <tarea> — motivo
2. ...
```

**Al terminar:** creá `{rel_folder}/LOC_COMPLETADO.flag` con el texto `ok`.
Si un archivo no existe o el análisis PM está equivocado, documentalo con `[ERROR]` en BUG_LOCALIZATION.md y terminá igual (el Implementador necesita saberlo).
NO modifiques código todavía."""


def build_dev_impl_prompt(ticket_folder: str, ticket_id: str, workspace_root: str) -> str:
    """Sub-agente DEV-Implementador: ejecuta cambios con localización exacta."""
    rel_folder   = _to_workspace_relative(ticket_folder, workspace_root)
    tareas       = _read_file_safe(os.path.join(ticket_folder, "TAREAS_DESARROLLO.md"), max_chars=2500)
    localizacion = _read_file_safe(os.path.join(ticket_folder, "BUG_LOCALIZATION.md"), max_chars=5000)
    notas        = _read_file_safe(os.path.join(ticket_folder, "NOTAS_IMPLEMENTACION.md"), max_chars=1500)

    return f"""DEV-Implementador — Ticket #{ticket_id}

El Localizador ya identificó exactamente qué tocar. Tu tarea: IMPLEMENTAR LOS CAMBIOS.

Carpeta del ticket: {rel_folder}/

## Localización exacta de los cambios:
{localizacion or "(leer BUG_LOCALIZATION.md — OBLIGATORIO antes de tocar código)"}

## Tareas:
{tareas or "(leer TAREAS_DESARROLLO.md)"}

## Convenciones obligatorias:
{notas or "(leer NOTAS_IMPLEMENTACION.md)"}

---

Instrucciones estrictas:
1. Seguí el **orden de ejecución** indicado en BUG_LOCALIZATION.md
2. Modificá ÚNICAMENTE los archivos y líneas listados — no refactorices lo que no corresponde
3. Respetar siempre: RIDIOMA para mensajes, Oracle DAL sin EF, Log.Error/Log.Info donde aplica
4. Si un item de BUG_LOCALIZATION.md tiene `[ERROR]`, documentalo en IMPL_BLOCKERS.md y continuá con el resto

**Al terminar TODOS los cambios:** creá `{rel_folder}/IMPL_COMPLETADO.flag` con el texto `ok`.
**Si hay un bloqueante crítico** que impide la implementación: creá `{rel_folder}/DEV_ERROR.flag` con diagnóstico detallado.
No preguntes — ejecutá."""


def build_dev_doc_prompt(ticket_folder: str, ticket_id: str, workspace_root: str) -> str:
    """Sub-agente DEV-Documentador: documenta los cambios para QA."""
    rel_folder   = _to_workspace_relative(ticket_folder, workspace_root)
    localizacion = _read_file_safe(os.path.join(ticket_folder, "BUG_LOCALIZATION.md"), max_chars=3000)
    tareas       = _read_file_safe(os.path.join(ticket_folder, "TAREAS_DESARROLLO.md"), max_chars=2000)
    blockers     = _read_file_safe(os.path.join(ticket_folder, "IMPL_BLOCKERS.md"), max_chars=1000)

    blockers_section = f"\n## Bloqueantes durante implementación:\n{blockers}\n" if blockers else ""

    return f"""DEV-Documentador — Ticket #{ticket_id}

La implementación está completa. Tu tarea: DOCUMENTAR los cambios para que QA pueda verificarlos.

Carpeta del ticket: {rel_folder}/

## Localización usada:
{localizacion or "(leer BUG_LOCALIZATION.md)"}

## Tareas ejecutadas:
{tareas or "(leer TAREAS_DESARROLLO.md)"}
{blockers_section}

---

Revisá los archivos que BUG_LOCALIZATION.md indica como modificados y creá:

**DEV_COMPLETADO.md** con:
```markdown
## Archivos modificados
- <ruta relativa al workspace>
- ...

## Resumen de cambios por tarea
### Tarea 1: <título>
<qué se hizo exactamente>
...

## Cambios en BD
<DDL/DML ejecutados, o "Ninguno" si no aplica>

## Observaciones
<pendientes, riesgos identificados, o "Sin observaciones">
```

**GIT_CHANGES.md** con un resumen de qué líneas cambiaron y por qué (para el commit message).

DEV_COMPLETADO.md es el **flag de completado del pipeline DEV** — el watcher lo detecta al crearse.
Guardá los dos archivos y terminás."""


def build_qa_rev_prompt(ticket_folder: str, ticket_id: str, workspace_root: str) -> str:
    """Sub-agente QA-Revisor: code review estático sin pruebas funcionales."""
    rel_folder     = _to_workspace_relative(ticket_folder, workspace_root)
    dev_completado = _read_file_safe(os.path.join(ticket_folder, "DEV_COMPLETADO.md"), max_chars=3000)
    tareas         = _read_file_safe(os.path.join(ticket_folder, "TAREAS_DESARROLLO.md"), max_chars=2000)
    notas          = _read_file_safe(os.path.join(ticket_folder, "NOTAS_IMPLEMENTACION.md"), max_chars=1500)

    return f"""QA-Revisor — Ticket #{ticket_id}

El DEV terminó la implementación. Tu tarea: CODE REVIEW ESTÁTICO. NO ejecutes pruebas funcionales todavía.

Carpeta del ticket: {rel_folder}/

## Lo que hizo DEV:
{dev_completado or "(leer DEV_COMPLETADO.md)"}

## Criterios de aceptación:
{tareas or "(leer TAREAS_DESARROLLO.md)"}

## Convenciones del proyecto:
{notas or "(leer NOTAS_IMPLEMENTACION.md)"}

---

Revisá cada archivo listado en DEV_COMPLETADO.md y auditá:

1. **RIDIOMA**: ¿todos los mensajes visibles al usuario usan constantes de RIDIOMA (no texto hardcodeado)?
2. **Logging**: ¿hay `Log.Error` en los catch y `Log.Info` en operaciones importantes?
3. **Null safety**: ¿hay potenciales NullReferenceException sin guard?
4. **Oracle DAL**: ¿se usa el patrón correcto (sin Entity Framework, SQL directo vía DAL)?
5. **Blast radius**: ¿los cambios pueden romper funcionalidad fuera del scope del ticket?
6. **Criterios PM**: ¿las tareas de TAREAS_DESARROLLO.md están todas implementadas?

Producí **CODE_REVIEW.md** con:
```markdown
## Resultado: [SIN ISSUES / CON ADVERTENCIAS / CON BLOQUEANTES]

## Issues encontrados
| # | Severidad | Archivo | Línea | Descripción | Corrección sugerida |
|---|-----------|---------|-------|-------------|---------------------|
| 1 | BLOQUEANTE / ADVERTENCIA / SUGERENCIA | ... | ... | ... | ... |

## Checklist de convenciones
- [x/o] RIDIOMA: ...
- [x/o] Logging: ...
- [x/o] Null safety: ...
- [x/o] Oracle DAL: ...
- [x/o] Criterios PM cubiertos: ...
```

Si no hay issues: escribí "Sin observaciones — code review OK" en la sección de issues.

**Al terminar:** creá `{rel_folder}/REVIEW_COMPLETADO.flag` con el texto `ok`.
Solo reportás — no modificás código."""


def build_qa_exec_prompt(ticket_folder: str, ticket_id: str, workspace_root: str) -> str:
    """Sub-agente QA-Ejecutor: corre casos de prueba funcionales."""
    rel_folder   = _to_workspace_relative(ticket_folder, workspace_root)
    tareas       = _read_file_safe(os.path.join(ticket_folder, "TAREAS_DESARROLLO.md"), max_chars=2500)
    code_review  = _read_file_safe(os.path.join(ticket_folder, "CODE_REVIEW.md"), max_chars=2000)
    queries      = _read_file_safe(os.path.join(ticket_folder, "QUERIES_ANALISIS.sql"), max_chars=2000)
    incidente    = _read_file_safe(os.path.join(ticket_folder, "INCIDENTE.md"), max_chars=1000)

    queries_section = f"\n## Queries de validación:\n```sql\n{queries}\n```\n" if queries else ""

    return f"""QA-Ejecutor — Ticket #{ticket_id}

El code review estático está listo. Tu tarea: EJECUTAR PRUEBAS FUNCIONALES.

Carpeta del ticket: {rel_folder}/

## Problema original:
{incidente or "(leer INCIDENTE.md)"}

## Criterios de aceptación:
{tareas or "(leer TAREAS_DESARROLLO.md)"}

## Hallazgos del code review (tener en cuenta):
{code_review or "(leer CODE_REVIEW.md)"}
{queries_section}

---

Ejecutá estas pruebas y documentá cada una:

1. **Caso feliz**: el escenario principal del ticket ahora funciona correctamente
2. **Casos edge**: entrada vacía, valores límite, datos nulos, usuario sin permisos
3. **Regresión directa**: funcionalidad en el mismo módulo que NO estás cambiando sigue igual
4. **Validación de BD**: ejecutá las queries de QUERIES_ANALISIS.sql y verificá que los datos son correctos

Producí **TEST_RESULTS.md** con tabla de resultados:
```markdown
## Resumen: N casos / N pasaron / N fallaron

| # | Caso | Tipo | Pasos | Esperado | Real | Estado |
|---|------|------|-------|----------|------|--------|
| 1 | ... | Feliz/Edge/Regresión/BD | ... | ... | ... | PASS/FAIL |
```

**Al terminar:** creá `{rel_folder}/TEST_COMPLETADO.flag` con el texto `ok`.
Solo ejecutás pruebas — NO modificás código."""


def build_qa_arb_prompt(ticket_folder: str, ticket_id: str, workspace_root: str) -> str:
    """Sub-agente QA-Árbitro: emite el veredicto final consolidando review + tests."""
    rel_folder   = _to_workspace_relative(ticket_folder, workspace_root)
    code_review  = _read_file_safe(os.path.join(ticket_folder, "CODE_REVIEW.md"), max_chars=2500)
    test_results = _read_file_safe(os.path.join(ticket_folder, "TEST_RESULTS.md"), max_chars=2500)
    incidente    = _read_file_safe(os.path.join(ticket_folder, "INCIDENTE.md"), max_chars=800)

    return f"""QA-Árbitro — Ticket #{ticket_id}

Tenés tanto el code review como los resultados de pruebas. Tu tarea: EMITIR EL VEREDICTO FINAL.

Carpeta del ticket: {rel_folder}/

## Code Review:
{code_review or "(leer CODE_REVIEW.md)"}

## Resultados de pruebas:
{test_results or "(leer TEST_RESULTS.md)"}

## Problema original:
{incidente or "(leer INCIDENTE.md)"}

---

Criterios de veredicto:
- **APROBADO**: sin issues BLOQUEANTES + todos los casos felices PASS
- **CON OBSERVACIONES**: hay ADVERTENCIAS pero el caso feliz pasa — se puede deployar con nota
- **RECHAZADO**: hay issues BLOQUEANTES O casos felices FAIL

Creá **TESTER_COMPLETADO.md** con:
```markdown
## Veredicto: [APROBADO / CON OBSERVACIONES / RECHAZADO]

## Resumen ejecutivo
<2-3 líneas: qué se probó, resultado general, confianza>

## Issues bloqueantes
<items BLOQUEANTE del code review + casos FAIL de tests; o "Ninguno">

## Observaciones no bloqueantes
<advertencias y sugerencias; o "Ninguna">

## Recomendaciones para el próximo ciclo
<si fue RECHAZADO: qué exactamente debe corregir DEV; o "N/A">
```

**TESTER_COMPLETADO.md es el flag de completado del pipeline QA** — el watcher lo detecta al crearse.
No modifiques código — solo emitís el veredicto."""


def build_unstuck_prompt(ticket_folder: str, ticket_id: str, workspace_root: str,
                          current_state: str, reason: str = "") -> str:
    """
    Prompt del agente DESATASCADOR.

    Se invoca cuando el pipeline quedó frenado y el usuario apretó "🚑 Desatascar"
    en el dashboard. El agente tiene autoridad plena para:
      - Crear los flags de completado faltantes ({PM|DEV|TESTER|DOC}_COMPLETADO.*)
      - Borrar/renombrar flags de error o en-curso obsoletos
      - Completar archivos incompletos o vacíos que debieron dejar las etapas previas
      - Decidir la siguiente etapa válida del pipeline

    Recibe el estado actual, el listado de archivos de la carpeta y el motivo del
    atasco (si se pudo inferir), y responde con acciones concretas que destraben
    el flujo.
    """
    rel_folder = _to_workspace_relative(ticket_folder, workspace_root)

    # Inventario de archivos del ticket — el agente decide qué falta / está incompleto
    file_inventory = []
    try:
        for fname in sorted(os.listdir(ticket_folder)):
            fpath = os.path.join(ticket_folder, fname)
            if os.path.isfile(fpath):
                size = os.path.getsize(fpath)
                marker = " (vacío)" if size == 0 else f" ({size} bytes)"
                file_inventory.append(f"  - {fname}{marker}")
    except Exception:
        file_inventory.append("  (no se pudo listar la carpeta)")
    inventory_str = "\n".join(file_inventory) if file_inventory else "  (carpeta vacía)"

    reason_block = f"\n## Motivo reportado del atasco:\n{reason}\n" if reason else ""

    return f"""AGENTE DESATASCADOR — Ticket #{ticket_id}

El pipeline Stacky quedó frenado en el estado `{current_state}`. Tu trabajo es
**dejar el pipeline avanzando solo**, sin pedir nada al usuario. Si la solución
pasa por que trabaje otro agente (DEV, PM, QA), tenés que poner el ticket en el
estado que dispara a ese agente — no explicar el problema y cortar.

Tenés autoridad plena dentro de {rel_folder}/ para:
  1. CREAR flags de completado faltantes
  2. BORRAR o renombrar flags de error / en-curso obsoletos (*.flag.prev está OK)
  3. COMPLETAR archivos vacíos o con placeholders que alguna etapa dejó a medias
  4. CAMBIAR el estado del ticket en state.json para re-lanzar la etapa correcta
     (vía el flag correspondiente — NO edites state.json directamente)
{reason_block}
## Estado actual en state.json
- estado: `{current_state}`
- carpeta: {rel_folder}/

## Inventario actual de la carpeta
{inventory_str}

## Convenciones del pipeline (flags que el watcher mira)

| Etapa  | Flag de OK              | Flag de error        | Siguiente etapa |
|--------|-------------------------|----------------------|-----------------|
| pm     | PM_COMPLETADO.flag      | PM_ERROR.flag        | dev             |
| dev    | DEV_COMPLETADO.md       | DEV_ERROR.flag       | tester          |
| tester | TESTER_COMPLETADO.md    | TESTER_ERROR.flag    | doc (o rework)  |
| doc    | DOC_COMPLETADO.flag     | DOC_ERROR.flag       | completado      |
| dba    | DB_READY.flag           | —                    | dev             |
| tl     | TL_APPROVED.flag        | TL_REJECTED.md       | dev / pm        |

El watcher también reconoce el sufijo `_en_proceso` en el estado — si ve por ejemplo
`dev_en_proceso` pero no hay ningún thread vivo esperándolo, re-registra el watcher.
Por eso alcanza con dejar el flag correcto para que el pipeline avance.

## Protocolo de decisión (seguilo en orden)

1. **Mirá el inventario de archivos.** ¿Qué flag de OK debería existir dado el
   estado `{current_state}` y no está?
2. **Abrí los archivos que sí existen** y verificá que no estén vacíos ni con
   placeholders estilo `<TODO>`, `TBD`, `pendiente`. Si están incompletos y no
   hay un COMPLETADO flag, terminá de completarlos ANTES de crear el flag.
3. **Si hay un flag de ERROR** (*.flag sin contrapartida OK), evaluá si el
   error ya está resuelto en el contenido de los archivos. Si sí, renombralo a
   `*.flag.resolved` para que el watcher no lo vuelva a leer, y creá el flag OK.
4. **Si hay un `*_AGENTE_EN_CURSO.flag` huérfano** (sin proceso vivo invocando),
   borralo — bloquea re-invocaciones.
5. **Si el estado es `completado` pero `TESTER_COMPLETADO.md` dice RECHAZADO o
   CON OBSERVACIONES** → el ticket NO está realmente terminado. Renombrá
   `TESTER_COMPLETADO.md` a `.prev`, borrá `DEV_COMPLETADO.md` si aplica y creá
   `DEV_ERROR.flag` con el detalle de los FAIL de QA para que el daemon lance
   un rework automáticamente. NO aceptes `completado` con FAIL.
6. **Si el ticket está en `stagnation_detected` o `error_*`**, relanzá la etapa
   que corresponde creando/renombrando el flag adecuado. El daemon va a volver
   a invocar al agente al próximo ciclo.
7. **Escribí `DESATASCO_COMPLETADO.md` al final** describiendo:
   - Qué encontraste (archivos faltantes, incompletos, flags inconsistentes)
   - Qué acciones tomaste (crear flag X, borrar Y, completar Z)
   - Cuál es la próxima etapa esperada y qué agente la va a tomar
   - Si NO pudiste desatascar, por qué — pero solo si literalmente es imposible
     (ej: archivo binario .docx que requiere abrir Word). En ese caso tenés que
     además crear `BLOQUEO_HUMANO.flag` con el texto exacto del bloqueo y
     **aun así** dejar el pipeline en un estado coherente (no `completado` si
     QA rechazó).

## Reglas duras

- NO le pidas al usuario que haga nada. El usuario pidió destrabar; si hay
  trabajo técnico que puede hacer otro agente, dispará ese agente mediante el
  flag correspondiente — no describas lo que debería hacerse, hacelo o dispará
  al agente que lo va a hacer.
- NO cierres con "requiere intervención humana" salvo bloqueo físico real
  (archivo binario, credencial humana, acceso manual a app externa). En ese
  caso creá `BLOQUEO_HUMANO.flag` — no alcanza con explicarlo en el md.
- NO modifiques código de la aplicación fuera de {rel_folder}/
- NO borres archivos que tengan contenido real (solo flags / sentinels)
- NO toques state.json directamente — el watcher lo actualiza al ver el flag
- NO inventes evidencia de QA — si DEV no terminó, no crees TESTER_COMPLETADO.md

Ejecutá las acciones directamente, sin preguntar. El flag de tu propio trabajo es
`DESATASCO_COMPLETADO.md`. Si dejaste el pipeline disparando otra etapa,
indicalo explícitamente en el md — el dashboard va a relanzar automáticamente.
"""

