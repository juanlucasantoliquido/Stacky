"""Plan 131 — Resolutor de incidencias multimodal: bootstrap del agente + contexto.

F2: plantilla `.agent.md` del IncidentAnalyst (fuente de verdad única, viaja
dentro del bundle empaquetado — C10) y `ensure_incident_agent_file()`.
F3 agrega: manifest de adjuntos + catálogo de épicas + armado del prompt (§4.2).
"""
from __future__ import annotations

from pathlib import Path

from runtime_paths import stacky_agents_dir

_AGENT_FILENAME = "IncidentAnalyst.agent.md"

# C10 — fuente de verdad ÚNICA del contenido del .agent.md. En un deploy
# congelado (PyInstaller) el archivo del repo puede no existir; esta constante
# viaja siempre dentro del bundle. El archivo commiteado
# backend/agents/IncidentAnalyst.agent.md es un espejo byte-idéntico (test de
# sincronía F2.5).
_AGENT_TEMPLATE_MD = """---
name: IncidentAnalyst
description: "Analista de Incidencias unificado. Funde en UNA pasada las perspectivas de negocio, funcional y técnica para desglosar una incidencia multimodal (texto + capturas + logs) en un HTML dev-ready, con la épica relacionada del catálogo real. NO publica en el tracker (Stacky publica desde el backend tras la confirmación del operador)."
tools: ['codebase', 'search', 'usages', 'problems']
version: "1.0.0"
stacky_agent_type: incident
---

# IncidentAnalyst — Analista de Incidencias unificado

Sos el **Analista de Incidencias unificado**: fusionás en UNA pasada las perspectivas
del Agente de Negocio, el Analista Funcional y el Analista Técnico. Recibís una
incidencia reportada por el operador (texto libre + archivos adjuntos + catálogo de
épicas abiertas del tracker) y devolvés SOLO un desglose HTML dev-ready.

**PROHIBIDO narrar lo que vas a hacer** ("voy a analizar...", "leyendo el archivo...").
Tu respuesta ES el HTML del desglose y nada más.

---

## CÓMO LEER EL CONTEXTO RECIBIDO

### 1. Texto libre del operador

Viene primero en el prompt, verbatim. Es la fuente principal de contexto.

### 2. Bloque `<attachments-manifest>`

Lista los archivos adjuntos (imágenes, logs, texto) con su ruta absoluta, tamaño y
sha256. El contenido de los archivos de texto viene inline (truncado si es largo).

- **Si tu runtime puede leer imágenes del disco** (herramienta de lectura
  multimodal): abrí las rutas absolutas de las imágenes listadas y analizá su
  contenido visual.
- **Si tu runtime NO puede leer imágenes**: NO inventes ni alucines el contenido de
  la captura. Declaralo explícitamente en el desglose donde corresponda, con el
  formato exacto `[PENDIENTE: verificar captura <nombre>]`.
- El contenido de archivos de texto (logs, configs) ya viene inline: usalo como
  evidencia directa para el análisis técnico y los pasos de reproducción.

### 3. Bloque `<epic-catalog>`

Lista las épicas ABIERTAS reales del tracker (`id`, título, estado). Reglas
estrictas:

- Elegí **a lo sumo UNA** épica como relacionada, la que mejor explique el proceso
  de negocio afectado por la incidencia.
- **NUNCA inventes un id de épica** que no esté en el catálogo.
- Si el catálogo viene vacío, o ninguna épica calza, escribí exactamente
  `EPICA: ninguna` en la sección EPICA RELACIONADA.

---

## CONTRATO DE SALIDA (HTML, OBLIGATORIO Y LITERAL)

Devolvé SOLO este HTML, sin narración ni markdown alrededor (se tolera un fence
` ```html ` que Stacky limpia automáticamente). Los headings son LITERALES, sin
acentos, en este orden exacto:

```html
<h1>[INC] Título corto de la incidencia</h1>
<h2>RESUMEN EJECUTIVO</h2>            <p>2-4 frases: qué se rompe, a quién impacta, urgencia.</p>
<h2>CONTEXTO DE NEGOCIO</h2>          <p>Perspectiva de negocio: proceso de negocio afectado, actores, impacto.</p>
<h2>ANALISIS FUNCIONAL</h2>           <p>Perspectiva funcional: comportamiento esperado vs observado, casos borde, plan de pruebas mínimo.</p>
<h2>ANALISIS TECNICO</h2>             <p>Perspectiva técnica: hipótesis de causa raíz, componentes involucrados, approach sugerido de fix.</p>
<h2>PASOS DE REPRODUCCION</h2>        <ol><li>...</li></ol>
<h2>CRITERIOS DE ACEPTACION</h2>      <ul><li>binarios, verificables</li></ul>
<h2>ARCHIVOS Y MODULOS PROBABLES</h2> <ul><li>ruta/al/archivo.ext — por qué</li></ul>
<h2>EPICA RELACIONADA</h2>            <p>EPICA: 267 | CONFIANZA: 85 | RAZON: la incidencia afecta el proceso X de esa épica</p>
<h2>PRIORIDAD Y ESTIMACION</h2>       <p>Prioridad: alta|media|baja. Estimación: S|M|L. Justificación breve.</p>
```

Reglas del contrato:

- El `<h1>` es el título corto de la incidencia (se usa como título del Issue).
- Sos preciso, no inventás: todo lo no verificable va marcado como
  `[PENDIENTE: ...]` en vez de afirmado como cierto.
- La sección EPICA RELACIONADA sigue el formato EXACTO
  `EPICA: <id o ninguna> | CONFIANZA: <0-100> | RAZON: <texto>`.
- No agregues secciones extra, no cambies el orden, no uses Markdown.

---

## REGLA ANTI-NARRACIÓN

Tu respuesta completa es el bloque HTML de arriba. No agregues saludos, no expliques
qué vas a hacer, no resumas al final. Si tu runtime emite un mensaje de cierre
automático, ese texto NO forma parte del contrato y Stacky lo descarta — pero el
HTML del desglose debe estar completo igual, sin depender de ese mensaje.

---

_IncidentAnalyst v1.0.0 — Stacky Agents (Plan 131)._
"""


def ensure_incident_agent_file() -> Path:
    """Garantiza que `stacky_agents_dir()/IncidentAnalyst.agent.md` exista.

    - Si YA existe (el operador pudo editarlo): NO lo toca.
    - Si no existe: copia desde el archivo commiteado del repo
      (`backend/agents/IncidentAnalyst.agent.md`).
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

    # newline="" evita la traducción LF->CRLF de Windows: el archivo escrito
    # queda byte-idéntico al contenido en memoria (test de sincronía C10).
    dest.write_text(content, encoding="utf-8", newline="")
    return dest


# ── F3 — Contexto: manifest de adjuntos + catálogo de épicas (§4.2) ───────────

_INLINE_MAX_PER_FILE = 8_000
_INLINE_MAX_TOTAL = 40_000

_KIND_LABEL = {"image": "imagen", "text": "texto", "binary": "binario"}


def _human_size(num_bytes: int) -> str:
    kb = num_bytes / 1024
    if kb < 1024:
        return f"{kb:.1f} KB"
    return f"{kb / 1024:.1f} MB"


def build_attachments_manifest(incident: dict) -> str:
    """Formato EXACTO §4.2. Rutas absolutas de todos los archivos; inline solo
    de los `kind == "text"` (con `errors='replace'`), con cap por archivo
    (_INLINE_MAX_PER_FILE) y cap total (_INLINE_MAX_TOTAL)."""
    from services.incident_store import incidents_root

    files = incident.get("files") or []
    incident_dir = incidents_root() / incident.get("id", "")

    lines: list[str] = [f"Archivos adjuntos ({len(files)}):"]
    for f in files:
        abs_path = incident_dir / f["stored_name"]
        kind_label = _KIND_LABEL.get(f.get("kind", ""), f.get("kind", ""))
        lines.append(
            f"- {f['stored_name']} | {kind_label} | {_human_size(f['bytes'])} | "
            f"sha256={f['sha256']} | ruta_absoluta={abs_path}"
        )
    lines.append(
        "Si tu runtime puede leer imágenes del disco, abrí las rutas absolutas de las imágenes."
    )
    lines.append(
        "Si NO puede, declaralo con [PENDIENTE: verificar captura <nombre>] donde corresponda."
    )

    text_files = [f for f in files if f.get("kind") == "text"]
    if text_files:
        lines.append("")
        lines.append("--- Contenido de archivos de texto (inline, truncado) ---")
        total_inline = 0
        for f in text_files:
            path = incident_dir / f["stored_name"]
            try:
                raw = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                raw = ""
            remaining_budget = max(0, _INLINE_MAX_TOTAL - total_inline)
            per_file_cap = min(_INLINE_MAX_PER_FILE, remaining_budget)
            shown = raw[:per_file_cap]
            total_inline += len(shown)
            lines.append(f"### {f['stored_name']}")
            lines.append(shown)
            leftover = len(raw) - len(shown)
            if leftover > 0:
                lines.append(f"[TRUNCADO: quedaron {leftover} bytes sin mostrar]")

    return "<attachments-manifest>\n" + "\n".join(lines) + "\n</attachments-manifest>"


def fetch_epic_catalog(provider, limit: int = 50) -> list[dict]:
    """Catálogo de épicas del tracker activo. TODO el cuerpo protegido por un
    único try/except (C2+C6+C12): cualquier excepción → [] (degradación
    declarada; el agente escribe 'EPICA: ninguna' y el operador puede
    overridear en el preview)."""
    try:
        fetch_epics_fn = getattr(provider, "fetch_epics", None)
        if callable(fetch_epics_fn):
            # Camino PRINCIPAL en ADO — ya viene normalizado del adapter;
            # fetch_open_items en ADO es un stub que devuelve [] siempre, así
            # que si el provider expone fetch_epics NUNCA se cae al fallback.
            return list(fetch_epics_fn(limit=limit) or [])

        from services.tracker_provider import TrackerQuery

        items = provider.fetch_open_items(TrackerQuery(state="open"))
        out: list[dict] = []
        for it in items:
            fields = it.get("fields")
            if fields:
                is_epic = fields.get("System.WorkItemType") == "Epic"
            else:
                labels = it.get("labels") or []
                # C6 — el label real que Stacky crea en GitLab es "type::epic"
                # (gitlab_provider._type_label), por eso substring y no igualdad.
                is_epic = any("epic" in str(lbl).lower() for lbl in labels)
            if not is_epic:
                continue
            item_id = it.get("iid") or it.get("id")
            title = it.get("title") or (it.get("fields") or {}).get("System.Title") or ""
            state = it.get("state") or (it.get("fields") or {}).get("System.State") or ""
            out.append({"id": item_id, "title": title, "state": state})
            if len(out) >= limit:
                break
        return out
    except Exception:  # noqa: BLE001 — degradación declarada, nunca 500
        return []


def build_epic_catalog_block(catalog: list[dict]) -> str:
    """Formato EXACTO §4.2."""
    lines = [
        "<epic-catalog>",
        "Épicas ABIERTAS del tracker (elegí a lo sumo UNA como relacionada):",
    ]
    if not catalog:
        lines.append('(catálogo vacío → escribí exactamente "EPICA: ninguna")')
    else:
        for item in catalog:
            lines.append(
                f"- id={item.get('id')} | {item.get('title', '')} | estado={item.get('state', '')}"
            )
    lines.append("</epic-catalog>")
    return "\n".join(lines)


def build_incident_prompt(incident: dict, catalog: list[dict]) -> str:
    """Concatena §4.2 en orden: header + texto verbatim + attachments-manifest
    + epic-catalog."""
    header = "INCIDENCIA REPORTADA POR EL OPERADOR\n====================================\n"
    text = incident.get("text", "")
    manifest = build_attachments_manifest(incident)
    catalog_block = build_epic_catalog_block(catalog)
    return f"{header}{text}\n\n{manifest}\n\n{catalog_block}"
