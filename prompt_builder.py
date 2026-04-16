"""
prompt_builder.py — Construye prompts para los agentes PM-TLStack2 y DevStack2.

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


def _inject_code_context(ticket_folder: str, ticket_id: str,
                          workspace_root: str) -> str:
    """
    Intenta generar la sección de contexto de código.
    Retorna '' si code_context no está disponible o no encuentra nada.
    """
    if _build_ctx is None:
        return ""
    return _build_ctx(ticket_folder, ticket_id, workspace_root)


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

    return f"""Analizá y completá la incidencia del ticket #{ticket_id}.
{_prewarming}
{_subsystem_line}Carpeta del ticket: {rel_folder}/
{docs_note}{nota_pm_block}
El archivo con el contenido del ticket es: INC-{ticket_id}.md
Los archivos a completar con análisis técnico real son:
  - INCIDENTE.md
  - ANALISIS_TECNICO.md
  - ARQUITECTURA_SOLUCION.md
  - TAREAS_DESARROLLO.md
  - QUERIES_ANALISIS.sql
  - NOTAS_IMPLEMENTACION.md

Instrucciones:
1. Leé INC-{ticket_id}.md para entender el problema completamente
2. Si existe PROJECT_DOCS.md, leélo primero para orientarte — ya tiene el mapa del proyecto
3. Investigá el código fuente y la BD Oracle del proyecto para entender el impacto completo
4. Completá todos los archivos usando la herramienta editFiles para escribirlos en disco
5. Reemplazá TODOS los placeholders "_A completar por PM_" con análisis técnico real
6. No dejes ningún placeholder sin completar
7. Las tareas en TAREAS_DESARROLLO.md deben ser directamente ejecutables por DevStack3 sin preguntas adicionales
8. Guardá todos los archivos antes de terminar
9. IMPORTANTE — cuando hayas terminado de guardar todos los archivos, creá el archivo {rel_folder}/PM_COMPLETADO.flag con el texto 'ok'. Este archivo es la señal que usa el pipeline para saber que el análisis está completo y puede continuar al siguiente paso
10. Si encontrás un bloqueante que impide completar el análisis, creá {rel_folder}/PM_ERROR.flag con la descripción del problema"""


def build_dev_prompt(ticket_folder: str, ticket_id: str, workspace_root: str) -> str:
    rel_folder   = _to_workspace_relative(ticket_folder, workspace_root)
    code_context = _inject_code_context(ticket_folder, ticket_id, workspace_root)

    return f"""Implementá la incidencia del ticket #{ticket_id}.

Carpeta de trabajo: {rel_folder}/

Instrucciones:
1. Leé en este orden: INCIDENTE.md → ANALISIS_TECNICO.md → ARQUITECTURA_SOLUCION.md → NOTAS_IMPLEMENTACION.md → TAREAS_DESARROLLO.md
2. Los archivos de código a modificar están indicados en TAREAS_DESARROLLO.md y también en el contexto de código abajo
3. Ejecutá TODAS las tareas en estado PENDIENTE del archivo TAREAS_DESARROLLO.md
4. Implementá los cambios de código respetando las convenciones del proyecto RIPLEY (RIDIOMA, Oracle DAL, Logging)
5. Al finalizar TODA la implementación, creá el archivo DEV_COMPLETADO.md en {rel_folder}/ con:
   - Lista de archivos modificados (rutas relativas al workspace)
   - Resumen de cambios realizados por tarea
   - Observaciones o pendientes si los hay
6. Si encontrás un bloqueante que impide la implementación, creá {rel_folder}/DEV_ERROR.flag con la descripción
7. No preguntes — ejecutá basándote en los archivos de la carpeta
{code_context}"""


def build_tester_prompt(ticket_folder: str, ticket_id: str, workspace_root: str) -> str:
    rel_folder = _to_workspace_relative(ticket_folder, workspace_root)

    # Inyectar SVN_CHANGES.md si existe (generado por svn_reporter post-DEV)
    svn_changes_path = os.path.join(ticket_folder, "SVN_CHANGES.md")
    svn_section = ""
    if os.path.exists(svn_changes_path):
        svn_content = _read_file_safe(svn_changes_path, max_chars=4000)
        if svn_content:
            svn_section = f"""

---

## Cambios SVN realizados por DEV (auto-generado)

{svn_content}

---
"""

    return f"""Realizá pruebas exhaustivas de la implementación del ticket #{ticket_id}.

Carpeta de trabajo: {rel_folder}/

Instrucciones:
1. Leé TAREAS_DESARROLLO.md para entender qué se implementó y cuáles son los criterios de aceptación
2. Revisá DEV_COMPLETADO.md para ver qué archivos fueron modificados y qué cambios se realizaron
3. Revisá los archivos de código modificados por el DEV
4. Ejecutá las siguientes verificaciones:
   a) Comportamiento funcional: los cambios resuelven el problema descripto en INCIDENTE.md
   b) Casos edge y negativos: qué pasa con entradas inválidas, valores límite, casos vacíos
   c) Regresión: verificá que la funcionalidad existente no se rompió
   d) RIDIOMA: los mensajes al usuario usan constantes de RIDIOMA correctamente
   e) Logging: los logs de error e info están presentes donde corresponde
   f) Queries de validación: ejecutá las queries de QUERIES_ANALISIS.sql y verificá los datos
5. Emitir veredicto final: APROBADO / CON OBSERVACIONES / RECHAZADO
6. Al terminar, creá TESTER_COMPLETADO.md en {rel_folder}/ con el siguiente formato:
   ## Veredicto: [APROBADO / CON OBSERVACIONES / RECHAZADO]
   ## Resumen ejecutivo
   (2-3 líneas sobre qué se probó y el resultado)
   ## Casos de prueba
   | Caso | Tipo | Resultado | Evidencia |
   |------|------|-----------|----------|
   (tabla con todos los casos probados)
   ## Observaciones y riesgos
   (lista de hallazgos, riesgos o pendientes)
   ## Queries de validación ejecutadas
   (resultados de las queries relevantes)
7. Si encontrás un error crítico que imposibilita el testing, creá {rel_folder}/TESTER_ERROR.flag con la descripción
8. No preguntes — ejecutá directamente
{svn_section}"""


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

    return f"""Documentá el ticket #{ticket_id} en la base de conocimiento del proyecto.

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
    svn_changes = _read_file_safe(os.path.join(ticket_folder, "SVN_CHANGES.md"),
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

Archivos que modificaste (SVN):
{svn_changes or '(ver DEV_COMPLETADO.md)'}

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
