"""
mantis_scraper.py  v2.0

Mejoras:
  1. Deep scraping del detalle — descripción, pasos, info adicional, historial de notas
  2. Pipeline PM automático  — genera 6 archivos (INCIDENTE.md, ANALISIS_TECNICO.md, etc.)
                               en la misma carpeta del ticket
  3. Detección de cambios de estado — mueve la carpeta si el estado cambia en Mantis

Estructura de salida:
    tickets/{estado}/{ticket_id}/
        INC-{ticket_id}.md           ← descripción completa + historial
        INCIDENTE.md                 ← generado automáticamente (PM)
        ANALISIS_TECNICO.md          ← template listo para completar
        ARQUITECTURA_SOLUCION.md     ← template listo para completar
        TAREAS_DESARROLLO.md         ← template listo para DevStack2
        QUERIES_ANALISIS.sql         ← queries base
        NOTAS_IMPLEMENTACION.md      ← notas para el dev
        [adjuntos: imágenes, zips, docs...]

Requisitos:
    1. auth/auth.json (ejecutar capture_session.py una vez)
    2. VPN activa

Ejecutar:
    cd tools/mantis_scraper
    python mantis_scraper.py
"""

import hashlib
import json
import os
import re
import shutil
import sys
import threading
import time
from datetime import datetime
from urllib.parse import unquote, urlparse, parse_qs
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# Forzar stdout a UTF-8 para evitar UnicodeEncodeError en consola cp1252 de Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# ─────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────

def load_config(config_path: str = "config.json") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


# ─────────────────────────────────────────────
#  PRIORITY SCORE
# ─────────────────────────────────────────────

_GRAVEDAD_SCORES = {
    "bloqueante": 1,
    "blocker":    1,
    "urgente":    1,
    "urgent":     1,
    "crítica":    2,
    "critica":    2,
    "critical":   2,
    "mayor":      3,
    "major":      3,
    "menor":      4,
    "minor":      4,
    "feature":    5,
    "trivial":    5,
}


def _compute_priority_score(ticket: dict) -> int:
    """
    Mapea la gravedad del ticket a un score 1-5 (1 = más urgente).
    Retorna 5 si la gravedad no coincide con ningún valor conocido.
    """
    gravedad = ticket.get("gravedad", "").lower().strip()
    # Eliminar acentos básicos para comparación robusta
    gravedad = gravedad.replace("á", "a").replace("é", "e").replace("í", "i") \
                       .replace("ó", "o").replace("ú", "u")
    for key, score in _GRAVEDAD_SCORES.items():
        if key in gravedad:
            return score
    return 5


# ─────────────────────────────────────────────
#  STATE MANAGER
# ─────────────────────────────────────────────

def load_state(state_path: str) -> dict:
    """
    Carga el estado desde seen_tickets.json.
    Migra automáticamente el formato antiguo (seen_ids) al nuevo (tickets por id).
    """
    if not os.path.exists(state_path):
        return {"tickets": {}, "last_run": None}

    with open(state_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Migración desde formato antiguo
    if "seen_ids" in data and "tickets" not in data:
        data["tickets"] = {
            tid: {"estado_normalizado": None, "titulo": "", "processed_at": None}
            for tid in data.pop("seen_ids")
        }

    return data


def save_state(state_path: str, state: dict) -> None:
    d = os.path.dirname(state_path)
    if d:
        os.makedirs(d, exist_ok=True)
    state["last_run"] = datetime.now().isoformat()
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


# ─────────────────────────────────────────────
#  NORMALIZACIÓN DE ESTADO
# ─────────────────────────────────────────────

_ACCENT_TABLE = str.maketrans("áéíóúÁÉÍÓÚñÑ", "aeiouAEIOUnN")

def normalize_estado(estado_raw: str) -> str:
    """'confirmada (Juan Luca Santolíquido)' → 'confirmada'"""
    estado = estado_raw.split("(")[0].strip().lower()
    estado = estado.translate(_ACCENT_TABLE).replace(" ", "_")
    return estado or "sin_estado"


# ─────────────────────────────────────────────
#  EXTRACCIÓN LISTA DE TICKETS
# ─────────────────────────────────────────────

def extract_tickets(page, config: dict) -> list:
    """
    Extrae TODOS los tickets del proyecto activo en una sola llamada JS.

    En lugar de iterar filas vía Playwright (N×M round-trips al browser),
    un único page.evaluate() recorre el DOM en el proceso del browser y
    retorna el array completo de una vez. Reduce el tiempo de scraping de
    ~5s a ~300ms en listas grandes.
    """
    mantis_base = config.get("mantis_url", "").rsplit("/view_all_bug_page.php", 1)[0]
    selectors   = config["selectors"]

    raw_tickets: list = page.evaluate(
        """([sel, base]) => {
            const rows = Array.from(document.querySelectorAll(sel.rows));
            return rows
                .filter(r => !r.className.includes('sticky-separator'))
                .map(r => {
                    const id_el  = r.querySelector(sel.id);
                    const st_el  = r.querySelector(sel.status);
                    if (!id_el || !st_el) return null;

                    const status_text = st_el.innerText.trim();
                    const m           = status_text.match(/\\((.+?)\\)/);
                    const asignado    = m ? m[1].trim() : '';
                    const estado_base = status_text.split('(')[0].trim();

                    const sum_el  = r.querySelector(sel.summary);
                    const titulo  = sum_el ? sum_el.innerText.trim() : '';
                    let url       = sum_el ? (sum_el.getAttribute('href') || '') : '';
                    if (url && !url.startsWith('http')) url = base + '/' + url.replace(/^\\//, '');

                    const cat_el  = r.querySelector(sel.category);
                    const sev_el  = r.querySelector(sel.severity);
                    const mod_el  = r.querySelector(sel.last_modified);

                    return {
                        ticket_id:         id_el.innerText.trim(),
                        titulo,
                        estado:            status_text,
                        estado_base,
                        asignado,
                        categoria:         cat_el ? cat_el.innerText.trim() : '',
                        gravedad:          sev_el ? sev_el.innerText.trim() : '',
                        fecha_actualizacion: mod_el ? mod_el.innerText.trim() : '',
                        url,
                    };
                })
                .filter(t => t !== null && t.ticket_id !== '');
        }""",
        [selectors, mantis_base],
    )

    # Agregar estado_normalizado (Python-side, una sola pasada)
    for t in raw_tickets:
        t["estado_normalizado"] = normalize_estado(t["estado"])

    return raw_tickets


# ─────────────────────────────────────────────
#  DESCARGA DE ADJUNTOS
# ─────────────────────────────────────────────

def _extract_filename(content_disposition: str, fallback_url: str) -> str:
    if content_disposition:
        match = re.search(r"filename\*=UTF-8''(.+)", content_disposition, re.IGNORECASE)
        if match:
            return re.sub(r'[<>:"/\\|?*]', '_', unquote(match.group(1)).strip())
        match = re.search(r'filename=["\']?([^"\';\r\n]+)', content_disposition, re.IGNORECASE)
        if match:
            return re.sub(r'[<>:"/\\|?*]', '_', unquote(match.group(1).strip().strip('"')))
    match = re.search(r'file_id=(\d+)', fallback_url)
    return f"adjunto_{match.group(1)}" if match else "adjunto_desconocido"


def _get_existing_file_hashes(ticket_folder: str) -> dict:
    """
    Retorna {sha256_hex: filename} para todos los archivos binarios existentes
    en la carpeta del ticket (excluye .md y .sql para no comparar texto).
    """
    hashes = {}
    for fname in os.listdir(ticket_folder):
        if fname.endswith((".md", ".sql")):
            continue
        fpath = os.path.join(ticket_folder, fname)
        if not os.path.isfile(fpath):
            continue
        try:
            with open(fpath, "rb") as f:
                h = hashlib.sha256(f.read()).hexdigest()
            hashes[h] = fname
        except Exception:
            pass
    return hashes


def _download_from_page(page, context, ticket_folder: str) -> list:
    """Descarga adjuntos desde una página ya abierta. Deduplica por URL y por hash."""
    downloaded = []
    links = page.locator("a[href*='file_download.php']").all()
    if not links:
        return downloaded

    seen_urls    = set()
    seen_hashes  = _get_existing_file_hashes(ticket_folder)

    for link in links:
        try:
            href = link.get_attribute("href") or ""
            if not href:
                continue
            if not href.startswith("http"):
                href = "https://soporte.ais-int.net/mantis/" + href.lstrip("/")

            key = re.sub(r'[&?]show_inline=\d+', '', href)
            if key in seen_urls:
                continue
            seen_urls.add(key)

            resp = context.request.get(href)
            if not resp.ok:
                print(f"       [WARN] HTTP {resp.status}: {href}")
                continue

            body     = resp.body()
            new_hash = hashlib.sha256(body).hexdigest()
            if new_hash in seen_hashes:
                print(f"       [SKIP] Duplicado de '{seen_hashes[new_hash]}' (mismo contenido)")
                continue

            filename = _extract_filename(resp.headers.get("content-disposition", ""), href)
            dest = os.path.join(ticket_folder, filename)
            if os.path.exists(dest):
                continue

            with open(dest, "wb") as f:
                f.write(body)

            seen_hashes[new_hash] = filename
            downloaded.append(filename)
            print(f"       [FILE] {filename}")

        except Exception as e:
            print(f"       [WARN] Error descargando adjunto: {e}")

    return downloaded


# ─────────────────────────────────────────────
#  DEEP SCRAPING DEL DETALLE  (NUEVO)
# ─────────────────────────────────────────────

def _text(page, *selectors) -> str:
    """Intenta cada selector y retorna el primero que tenga texto."""
    for sel in selectors:
        try:
            el = page.locator(sel)
            if el.count() > 0:
                t = el.first.inner_text().strip()
                if t:
                    return t
        except Exception:
            continue
    return ""


def scrape_ticket_detail(context, ticket: dict, ticket_folder: str) -> dict:
    """
    Navega al detalle del ticket y extrae:
      - Descripción completa
      - Pasos para reproducir
      - Información adicional
      - Historial de notas/comentarios
    También descarga adjuntos durante la misma visita.
    """
    detail = {
        "descripcion": "",
        "pasos_reproduccion": "",
        "informacion_adicional": "",
        "notas": [],
        "adjuntos": [],
    }

    url = ticket.get("url", "")
    if not url:
        return detail

    page = context.new_page()
    try:
        page.goto(url, timeout=25000)
        page.wait_for_load_state("domcontentloaded")

        # ── Descripción ──────────────────────────────────────────────────
        detail["descripcion"] = _text(
            page,
            "td.bug-description",
            ".bug-description",
            "td[class*='description']",
        )

        # ── Pasos para reproducir ─────────────────────────────────────────
        detail["pasos_reproduccion"] = _text(
            page,
            "td.bug-steps-to-reproduce",
            ".bug-steps-to-reproduce",
            "td[class*='steps']",
        )

        # ── Información adicional ─────────────────────────────────────────
        detail["informacion_adicional"] = _text(
            page,
            "td.bug-additional-information",
            ".bug-additional-information",
            "td[class*='additional']",
        )

        # ── Notas / comentarios ───────────────────────────────────────────
        note_texts     = page.locator("td.bugnote-note").all()
        note_reporters = page.locator("td.bugnote-reporter").all()
        note_dates     = page.locator("td.bugnote-date").all()

        for i, note_el in enumerate(note_texts):
            try:
                texto = note_el.inner_text().strip()
                if not texto:
                    continue
                reporter = note_reporters[i].inner_text().strip() if i < len(note_reporters) else ""
                fecha    = note_dates[i].inner_text().strip()     if i < len(note_dates)     else ""
                detail["notas"].append({"reporter": reporter, "fecha": fecha, "texto": texto})
            except Exception:
                continue

        # ── Adjuntos ──────────────────────────────────────────────────────
        detail["adjuntos"] = _download_from_page(page, context, ticket_folder)

    except Exception as e:
        print(f"  [WARN] Error en detalle del ticket: {e}")
    finally:
        page.close()

    return detail


# ─────────────────────────────────────────────
#  GENERACIÓN MARKDOWN MEJORADO
# ─────────────────────────────────────────────

def generate_ticket_md(ticket: dict, detail: dict, ticket_folder: str) -> str:
    """Genera INC-{id}.md con descripción completa, notas e índice de adjuntos."""
    os.makedirs(ticket_folder, exist_ok=True)
    filepath = os.path.join(ticket_folder, f"INC-{ticket['ticket_id']}.md")

    notas_md = ""
    if detail.get("notas"):
        notas_md = "\n---\n\n## Historial de comentarios\n\n"
        for n in detail["notas"]:
            notas_md += f"### {n['reporter']} — {n['fecha']}\n\n{n['texto']}\n\n"

    adjuntos_md = ""
    if detail.get("adjuntos"):
        adjuntos_md = "\n---\n\n## Adjuntos\n\n"
        for adj in detail["adjuntos"]:
            adjuntos_md += f"- [{adj}](./{adj})\n"

    content = f"""---
ticket_id: {ticket['ticket_id']}
titulo: "{ticket['titulo']}"
estado: "{ticket['estado']}"
categoria: "{ticket['categoria']}"
gravedad: "{ticket['gravedad']}"
fecha_actualizacion: "{ticket['fecha_actualizacion']}"
url: "{ticket['url']}"
---

# {ticket['titulo']}

## Descripción

{detail.get('descripcion') or '_Sin descripción registrada_'}
"""

    if detail.get("pasos_reproduccion"):
        content += f"\n## Pasos para reproducir\n\n{detail['pasos_reproduccion']}\n"

    if detail.get("informacion_adicional"):
        content += f"\n## Información adicional\n\n{detail['informacion_adicional']}\n"

    content += notas_md
    content += adjuntos_md

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    return filepath


# ─────────────────────────────────────────────
#  PIPELINE PM — 6 ARCHIVOS  (NUEVO)
# ─────────────────────────────────────────────

def generate_pm_files(ticket: dict, detail: dict, ticket_folder: str) -> None:
    """
    Genera los 6 archivos de análisis PM en la carpeta del ticket.
    No sobreescribe archivos existentes (puede tener trabajo del dev).
    """
    tid         = ticket["ticket_id"]
    titulo      = ticket["titulo"]
    categoria   = ticket["categoria"]
    gravedad    = ticket["gravedad"]
    estado      = ticket["estado"]
    url         = ticket["url"]
    fecha       = datetime.now().strftime("%Y-%m-%d")
    descripcion = detail.get("descripcion") or ticket["titulo"]
    pasos       = detail.get("pasos_reproduccion") or "_A completar por PM_"

    # ── INCIDENTE.md ──────────────────────────────────────────────────────
    incidente = f"""# {tid} — {titulo}

## Datos del Ticket

| Campo             | Valor |
|-------------------|-------|
| ID Mantis         | {tid} |
| Título            | {titulo} |
| Categoría         | {categoria} |
| Gravedad          | {gravedad} |
| Estado            | {estado} |
| Fecha análisis    | {fecha} |
| URL               | {url} |

---

## Descripción del Problema

{descripcion}

---

## Pasos para Reproducir

{pasos}

---

## Impacto Funcional

_A completar por PM_

---

## Sistema Afectado

- [ ] OnLine (ASP.NET WebForms)
- [ ] Batch (Windows Service)
- [ ] Ambos

---

## Prioridad

{gravedad.upper()}

---

## Fecha de reporte

{ticket.get('fecha_actualizacion', fecha)}
"""

    # ── ANALISIS_TECNICO.md ───────────────────────────────────────────────
    analisis = f"""# Análisis Técnico — {tid}

## Problema técnico

_A completar — describir qué está pasando en el código/BD_

## Flujo actual (cómo funciona HOY)

_A completar — describir el flujo completo de la funcionalidad afectada paso a paso_

## Causa probable

_A completar — hipótesis técnica de por qué falla_

## Componentes afectados

### Código OnLine

| Archivo | Clase/Método | Rol |
|---------|-------------|-----|
| `OnLine/AgendaWeb/...aspx.cs` | `MétodoX()` | A completar |

### Código Batch

| Archivo | Clase/Método | Rol |
|---------|-------------|-----|
| `Batch/RSXxx/...cs` | `MétodoY()` | A completar |

### Tablas Oracle

| Tabla | Campo relevante | Descripción |
|-------|----------------|-------------|
| ? | ? | A completar |

### Servicios/Procesos

_A completar_

---

**Generado desde Mantis #{tid} — {titulo}**
"""

    # ── ARQUITECTURA_SOLUCION.md ──────────────────────────────────────────
    arquitectura = f"""# Arquitectura de Solución — {tid}

## Estrategia general

_A completar por PM — explicar el enfoque de solución en 2-3 líneas_

## Cambios requeridos

### OnLine

| Archivo | Cambio |
|---------|--------|
| `ruta/Archivo.aspx.cs` | A completar |

### Batch

| Archivo | Cambio |
|---------|--------|
| `ruta/Archivo.cs` | A completar |

### Base de datos

| Tipo | Descripción |
|------|-------------|
| A completar | A completar |

### RIDIOMA — Mensajes nuevos (si aplica)

| ID | Español | Portugués |
|----|---------|-----------|
| XXXX | texto ES | texto PT |

## Impacto en módulos adyacentes

_A completar_

## Decisiones de diseño

_A completar_
"""

    # ── TAREAS_DESARROLLO.md ──────────────────────────────────────────────
    tareas = f"""# TAREAS DE DESARROLLO — {tid}

> Agente a usar: **DevStack2**
> Leer en orden: INCIDENTE → ANALISIS_TECNICO → ARQUITECTURA_SOLUCION → NOTAS → estas tareas

---

## T001 — [Describir tarea principal]

**Estado:** PENDIENTE
**Prioridad:** ALTA
**Sistema:** OnLine / Batch

### Objetivo

_A completar por PM_

### Archivos a modificar

- `ruta/relativa/Archivo.cs` — descripción del cambio

### Implementación esperada

_A completar por PM_

### Código de referencia (patrón a seguir)

```csharp
// A completar
```

### Query de verificación

```sql
-- A completar
```

### Criterios de aceptación

- [ ] A completar
- [ ] A completar

---

**Ticket origen:** Mantis #{tid} — {titulo}
"""

    # ── QUERIES_ANALISIS.sql ──────────────────────────────────────────────
    queries = f"""-- ============================================================
-- QUERIES DE ANÁLISIS — {tid}
-- {titulo}
-- ============================================================

-- 1. Estructura de tablas afectadas (completar con nombre de tabla)
/*
SELECT COLUMN_NAME, DATA_TYPE, NULLABLE, DATA_LENGTH
FROM ALL_TAB_COLUMNS
WHERE TABLE_NAME IN ('TABLA_A', 'TABLA_B')
ORDER BY TABLE_NAME, COLUMN_ID;
*/

-- 2. Datos relevantes para reproducir el problema
/*
SELECT *
FROM TABLA_X
WHERE <condicion_del_bug>
FETCH FIRST 10 ROWS ONLY;
*/

-- 3. Verificar estado antes del fix
/*
SELECT COUNT(*) AS REGISTROS_AFECTADOS
FROM TABLA_X
WHERE <condicion_del_problema>;
*/

-- 4. Query de validación post-implementación
-- (completar después de definir el fix)
"""

    # ── NOTAS_IMPLEMENTACION.md ───────────────────────────────────────────
    notas_impl = f"""# Notas para el Developer — {tid}

## Convenciones especiales para esta incidencia

_A completar por PM si hay particularidades_

## Mensajes RIDIOMA relevantes ya existentes

| IDTEXTO | Texto | Uso actual |
|---------|-------|-----------|
| XXXX | A completar | A completar |

## Precauciones

- _¿Qué NO hacer?_
- _¿Efectos secundarios conocidos?_
- _¿Dependencias con otros procesos?_

## Ambiente de pruebas

_A completar — cómo configurar / qué datos usar_

## Dependencias con otras incidencias

_Ninguna conocida al momento de la generación automática_

---

**Generado automáticamente desde Mantis #{tid}**
**Fecha:** {fecha}
"""

    files = {
        "INCIDENTE.md":              incidente,
        "ANALISIS_TECNICO.md":       analisis,
        "ARQUITECTURA_SOLUCION.md":  arquitectura,
        "TAREAS_DESARROLLO.md":      tareas,
        "QUERIES_ANALISIS.sql":      queries,
        "NOTAS_IMPLEMENTACION.md":   notas_impl,
    }

    for filename, content in files.items():
        filepath = os.path.join(ticket_folder, filename)
        if not os.path.exists(filepath):   # nunca sobreescribir trabajo ya hecho
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"       [PM]   {filename}")


# ─────────────────────────────────────────────
#  DETECCIÓN DE CAMBIOS DE ESTADO  (NUEVO)
# ─────────────────────────────────────────────

def handle_state_change(ticket: dict, stored: dict, output_dir: str) -> str:
    """
    Si el estado cambió, mueve la carpeta al nuevo estado y actualiza
    el frontmatter del INC-{id}.md.
    Retorna la ruta de la carpeta final.
    """
    tid        = ticket["ticket_id"]
    old_est    = stored.get("estado_normalizado")
    new_est    = ticket["estado_normalizado"]
    old_folder = os.path.join(output_dir, old_est, tid) if old_est else None
    new_folder = os.path.join(output_dir, new_est, tid)

    if old_folder and old_folder != new_folder and os.path.exists(old_folder):
        os.makedirs(os.path.join(output_dir, new_est), exist_ok=True)
        shutil.move(old_folder, new_folder)
        print(f"[MOVE] {tid}: {old_est} -> {new_est}")

        # Actualizar frontmatter en INC-{id}.md
        md_path = os.path.join(new_folder, f"INC-{tid}.md")
        if os.path.exists(md_path):
            with open(md_path, "r", encoding="utf-8") as f:
                content = f.read()
            content = re.sub(
                r'^(estado: ").*(")',
                f'\\1{ticket["estado"]}\\2',
                content,
                flags=re.MULTILINE,
            )
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(content)

    return new_folder


# ─────────────────────────────────────────────
#  INTERACTIVE PROJECT PICKER
# ─────────────────────────────────────────────

def pick_mantis_project_interactive(
    auth_path: str,
    mantis_url: str,
    timeout_sec: int = 120,
) -> dict:
    """
    Abre Chromium visible con Mantis cargado.
    El usuario elige el proyecto usando la interfaz normal de Mantis.
    La función intercepta el request a set_project.php, extrae project_id
    y el nombre de proyecto desde el título de la página resultante.

    Retorna: {"project_id": int|None, "project_name": str|None}
    """
    result = {"project_id": None, "project_name": None}
    detected_pid = [None]

    def _run_browser():
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=False,
                args=["--window-size=1280,850"],
            )
            try:
                ctx = browser.new_context(storage_state=auth_path)
                page = ctx.new_page()
                page.goto(mantis_url, timeout=30000)

                # Inyectar banner de instrucción visible
                page.evaluate("""() => {
                    const b = document.createElement('div');
                    b.id = '__picker_banner';
                    b.style.cssText = [
                        'position:fixed', 'top:0', 'left:0', 'right:0', 'z-index:2147483647',
                        'background:#1a1d2e', 'color:#7ee8a2',
                        'padding:14px 20px', 'font-size:15px', 'font-weight:bold',
                        'text-align:center', 'box-shadow:0 2px 10px rgba(0,0,0,.7)',
                        'font-family:monospace', 'letter-spacing:.5px'
                    ].join(';');
                    b.innerHTML = '🎯 &nbsp; Seleccioná el proyecto en el menú de Mantis &nbsp;→&nbsp; esta ventana se cerrará automáticamente';
                    document.body.style.marginTop = '52px';
                    document.body.prepend(b);
                }""")

                def _on_request(req):
                    if "set_project.php" in req.url:
                        # GET params
                        qs = parse_qs(urlparse(req.url).query)
                        pid = qs.get("project_id", [None])[0]
                        # POST body fallback
                        if not pid:
                            try:
                                post = req.post_data or ""
                                pid = parse_qs(post).get("project_id", [None])[0]
                            except Exception:
                                pass
                        if pid and int(pid) > 0:
                            detected_pid[0] = int(pid)

                page.on("request", _on_request)

                start = time.time()
                while detected_pid[0] is None and (time.time() - start) < timeout_sec:
                    try:
                        page.wait_for_timeout(400)
                    except Exception:
                        break

                if detected_pid[0]:
                    result["project_id"] = detected_pid[0]
                    # Esperar carga de la página del nuevo proyecto
                    try:
                        page.wait_for_load_state("domcontentloaded", timeout=8000)
                    except Exception:
                        pass
                    # Extraer nombre del proyecto (título de Mantis: "View Issues - NombreProyecto - Mantis")
                    try:
                        title = page.title()
                        parts = [p.strip() for p in title.split(" - ")]
                        if len(parts) >= 3:
                            result["project_name"] = parts[1]
                        elif len(parts) == 2:
                            result["project_name"] = parts[0]
                    except Exception:
                        pass
                    # Intentar también desde el selector de proyectos de Mantis
                    if not result["project_name"]:
                        try:
                            result["project_name"] = page.eval_on_selector(
                                "select[name='project_id'] option:checked, "
                                "select[name='f[project_id]'] option:checked",
                                "el => el.textContent.trim()"
                            )
                        except Exception:
                            pass

            finally:
                try:
                    browser.close()
                except Exception:
                    pass

    t = threading.Thread(target=_run_browser, daemon=True)
    t.start()
    t.join(timeout=timeout_sec + 10)
    return result


def _load_project_overrides(project_name: str) -> dict:
    """Carga el config.json del proyecto e infiere overrides para el scraper.
    Siempre usa rutas relativas a la carpeta del proyecto para tickets y state,
    garantizando aislamiento multi-proyecto.
    """
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "projects", project_name)
    cfg_path = os.path.join(base, "config.json")
    if not os.path.exists(cfg_path):
        print(f"[WARN] Proyecto '{project_name}' no encontrado en projects/")
        return {}
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    # Siempre usar rutas dentro de la carpeta del proyecto — nunca paths del config.json heredados
    overrides = {
        "output_dir": os.path.join(base, "tickets"),
        "state_path": os.path.join(base, "pipeline", "state.json"),
    }

    if cfg.get("mantis_project_id"):
        overrides["mantis_project_id"] = cfg["mantis_project_id"]

    print(f"[INFO] Proyecto activo: {cfg.get('display_name', project_name)}")
    print(f"[INFO] tickets -> {overrides['output_dir']}")
    print(f"[INFO] state   -> {overrides['state_path']}")
    if overrides.get("mantis_project_id"):
        print(f"[INFO] Mantis project_id: {overrides['mantis_project_id']}")
    return overrides


# ─────────────────────────────────────────────
#  ORQUESTADOR PRINCIPAL
# ─────────────────────────────────────────────

def _validate_selectors(page, config: dict) -> list:
    """
    Verifica que los selectores críticos retornen al menos un resultado.
    Retorna lista de selectores que fallaron (vacía = todo OK).
    Emite alerta [SELECTOR_DRIFT] si alguno falla.
    """
    failed = []
    for name, selector in config.get("selectors", {}).items():
        try:
            count = page.locator(selector).count()
            if count == 0:
                failed.append(name)
                print(f"[SELECTOR_DRIFT] '{name}' → '{selector}' no encontró elementos")
        except Exception as e:
            failed.append(name)
            print(f"[SELECTOR_DRIFT] '{name}' → error: {e}")
    if failed:
        print(f"[SELECTOR_DRIFT] {len(failed)} selector(es) fallaron. "
              f"MantisBT puede haber cambiado su HTML.")
    return failed


def _detail_hash(detail: dict) -> str:
    """Hash SHA256 del contenido de un detalle para detectar cambios."""
    key = (
        (detail.get("descripcion") or "")
        + (detail.get("pasos_reproduccion") or "")
        + (detail.get("informacion_adicional") or "")
        + "".join(n.get("texto", "") for n in detail.get("notas", []))
    )
    return hashlib.sha256(key.encode("utf-8", errors="replace")).hexdigest()[:16]


def _build_incremental_url(base_url: str, last_run_iso: str | None) -> str:
    """
    Agrega filtro de fecha al URL de Mantis para traer solo tickets
    modificados desde el último run. Si last_run_iso es None o muy antiguo,
    retorna el URL sin filtro (scraping completo).
    """
    if not last_run_iso:
        return base_url
    try:
        from datetime import timedelta
        last_run = datetime.fromisoformat(last_run_iso)
        # Si el último run fue hace más de 7 días, desactivar filtro incremental
        if (datetime.now() - last_run).days > 7:
            return base_url
        # Formato de fecha para Mantis: YYYY-MM-DD
        date_str = last_run.strftime("%Y-%m-%d")
        sep = "&" if "?" in base_url else "?"
        return f"{base_url}{sep}filter[last_updated_from]={date_str}"
    except Exception:
        return base_url


# ── Instancia global de Playwright para reutilización entre ciclos ────────────
_playwright_ctx = {"pw": None, "browser": None, "auth_mtime": 0.0}
_playwright_lock = threading.RLock()  # RLock: re-entrante — evita deadlock en _get_or_create_browser → _close_browser


def _get_or_create_browser(auth_path: str):
    """
    Retorna (playwright, browser) reutilizando la instancia existente si está viva.
    Crea una nueva si no existe o si auth.json cambió (re-login).
    """
    try:
        auth_mtime = os.path.getmtime(auth_path)
    except OSError:
        auth_mtime = 0.0

    with _playwright_lock:
        # Re-usar si el browser ya existe y auth.json no cambió
        if (_playwright_ctx["browser"] is not None
                and _playwright_ctx["auth_mtime"] == auth_mtime):
            try:
                # Verificar que el browser sigue vivo con un ping ligero
                _ = _playwright_ctx["browser"].is_connected()
                return _playwright_ctx["pw"], _playwright_ctx["browser"]
            except Exception:
                pass  # Browser muerto — recrear

        # Cerrar el viejo si existe
        _close_browser()

        pw      = sync_playwright().start()
        browser = pw.chromium.launch(headless=True)
        _playwright_ctx["pw"]          = pw
        _playwright_ctx["browser"]     = browser
        _playwright_ctx["auth_mtime"]  = auth_mtime
        return pw, browser


def _close_browser() -> None:
    """Cierra el browser Playwright si está abierto."""
    with _playwright_lock:
        try:
            if _playwright_ctx["browser"]:
                _playwright_ctx["browser"].close()
        except Exception:
            pass
        try:
            if _playwright_ctx["pw"]:
                _playwright_ctx["pw"].stop()
        except Exception:
            pass
        _playwright_ctx["browser"] = None
        _playwright_ctx["pw"]      = None
        _playwright_ctx["auth_mtime"] = 0.0


def run_scraper(project_name: str = None, incremental: bool = True, _retried: bool = False):
    """
    Orquestador principal del scraping.

    incremental=True: filtra por last_modified desde el último run
                      (mucho más rápido en proyectos con muchos tickets).
    incremental=False: scraping completo (útil para la primera ejecución).
    """
    from session_manager import SessionManager, SessionExpiredError

    config = load_config()

    # Aplicar overrides del proyecto activo
    if project_name:
        overrides = _load_project_overrides(project_name)
        config.update(overrides)

    auth_path = config["auth_path"]
    sm = SessionManager(auth_path, config["mantis_url"], config.get("timeout_ms", 30000))

    if not os.path.exists(auth_path):
        print("[SESSION] No existe auth.json — abriendo browser para capturar sesión SSO...")
        if not sm.prompt_renewal(timeout_seconds=300):
            print("[ERROR] No se capturó la sesión. Ejecutar manualmente: python capture_session.py")
            sys.exit(1)
        print("[SESSION] Sesión capturada. Continuando...")

    # Verificar sesión antes de lanzar Playwright
    elif sm.needs_renewal():
        renewed = sm.renew_session_headless()
        if not renewed:
            print("[SESSION] Sesión expirada — abriendo browser para renovar sesión SSO...")
            renewed = sm.prompt_renewal(timeout_seconds=300)
            if not renewed:
                raise SessionExpiredError(
                    "La sesión SSO de Mantis expiró y no se pudo renovar. "
                    "Ejecutar manualmente: python capture_session.py"
                )
            print("[SESSION] Sesión renovada exitosamente. Continuando...")

    state         = load_state(config["state_path"])
    tickets_state = state.setdefault("tickets", {})

    # URL incremental: solo traer tickets modificados desde el último run
    mantis_url = config["mantis_url"]
    if incremental and state.get("last_run"):
        mantis_url = _build_incremental_url(mantis_url, state["last_run"])
        if mantis_url != config["mantis_url"]:
            print(f"[INFO] Scraping incremental desde: {state['last_run'][:10]}")

    stats = {"new": 0, "moved": 0, "skip": 0, "updated": 0}

    # Reusar el browser Playwright entre ciclos del daemon
    _, browser = _get_or_create_browser(auth_path)
    try:
        context = browser.new_context(storage_state=auth_path)

        # ── Paso 0: cambiar al proyecto correcto en Mantis ────────────────
        mantis_project_id = config.get("mantis_project_id")
        if mantis_project_id:
            base_url   = config["mantis_url"].rsplit("/", 1)[0]
            switch_url = (
                f"{base_url}/set_project.php"
                f"?project_id={mantis_project_id}&ref=view_all_bug_page.php"
            )
            print(f"[INFO] Cambiando proyecto Mantis -> project_id={mantis_project_id}")
            sw_page = context.new_page()
            sw_page.goto(switch_url, timeout=config["timeout_ms"])
            sw_page.close()

        # ── Paso 1: cargar lista de tickets ───────────────────────────────
        list_page = context.new_page()
        print(f"[INFO] Navegando a: {mantis_url}")
        list_page.goto(mantis_url)

        try:
            list_page.wait_for_selector(
                config["selectors"]["table"],
                timeout=config["timeout_ms"],
            )
        except PlaywrightTimeout:
            # Intentar primero con URL completa (sin filtro incremental) por si
            # el filtro GET no es soportado y devuelve una página sin #buglist.
            if incremental and mantis_url != config["mantis_url"]:
                print("[WARN] #buglist no cargó con URL incremental — reintentando sin filtro de fecha.")
                context.close()
                return run_scraper(project_name=project_name, incremental=False, _retried=_retried)

            print("[ERROR] No se cargó #buglist. VPN caída o sesión expirada.")
            context.close()
            _close_browser()

            if _retried:
                raise SessionExpiredError(
                    "No se cargó #buglist tras renovar sesión — VPN caída o sesión inválida. "
                    "Ejecutar manualmente: python capture_session.py"
                )

            print("[SESSION] Abriendo browser para renovar sesión SSO...")
            if sm.prompt_renewal(timeout_seconds=300):
                print("[SESSION] Sesión renovada — reintentando scraper...")
                return run_scraper(project_name=project_name, incremental=incremental, _retried=True)
            raise SessionExpiredError(
                "No se cargó #buglist — VPN caída o sesión expirada. "
                "Ejecutar manualmente: python capture_session.py"
            )

        # Validar selectores (detecta drift silencioso en el HTML de Mantis)
        _validate_selectors(list_page, config)

        tickets = extract_tickets(list_page, config)
        list_page.close()

        print(f"[INFO] Tickets encontrados: {len(tickets)}\n")

        # ── Paso 2: procesar cada ticket ──────────────────────────────────
        for ticket in tickets:
            tid    = ticket["ticket_id"]
            stored = tickets_state.get(tid)

            if stored is not None:
                # Verificar que la carpeta del ticket realmente existe en disco.
                # Si fue borrada manualmente, tratarlo como ticket nuevo.
                _expected_folder = os.path.join(
                    config["output_dir"], ticket["estado_normalizado"], tid
                )
                _alt_folder = _find_ticket_folder(config["output_dir"], ticket["estado_normalizado"], tid)
                if not os.path.isdir(_expected_folder) and not _alt_folder:
                    print(f"[RECOVER] {tid}: carpeta borrada — re-scrapeando como ticket nuevo")
                    del tickets_state[tid]
                    stored = None

            if stored is not None:
                # Ticket conocido — verificar cambio de estado
                estado_cambio = (
                    stored.get("estado_normalizado") and
                    stored["estado_normalizado"] != ticket["estado_normalizado"]
                )
                if estado_cambio:
                    handle_state_change(ticket, stored, config["output_dir"])
                    tickets_state[tid]["estado_normalizado"] = ticket["estado_normalizado"]
                    stats["moved"] += 1
                else:
                    # ── Detección de cambios en el contenido del ticket ───
                    # Si fecha_actualizacion cambió, re-scrapeamos el detalle
                    # y comparamos hash para detectar nueva información.
                    if (ticket.get("fecha_actualizacion") and
                            ticket["fecha_actualizacion"] != stored.get("fecha_actualizacion")):
                        ticket_folder = _find_ticket_folder(
                            config["output_dir"], ticket["estado_normalizado"], tid
                        )
                        if ticket_folder:
                            new_detail = scrape_ticket_detail(context, ticket, ticket_folder)
                            new_hash   = _detail_hash(new_detail)
                            old_hash   = stored.get("detail_hash", "")
                            if new_hash != old_hash:
                                print(f"[UPDATE] {tid}: contenido actualizado — re-generando INC")
                                generate_ticket_md(ticket, new_detail, ticket_folder)
                                tickets_state[tid]["detail_hash"]         = new_hash
                                tickets_state[tid]["fecha_actualizacion"] = ticket["fecha_actualizacion"]
                                tickets_state[tid]["content_updated_at"]  = datetime.now().isoformat()
                                stats["updated"] += 1
                            else:
                                tickets_state[tid]["fecha_actualizacion"] = ticket["fecha_actualizacion"]
                    else:
                        print(f"[SKIP] {tid}  ({ticket['estado_normalizado']})")
                        stats["skip"] += 1

                # Actualizar campos dinámicos siempre
                tickets_state[tid]["estado_base"] = ticket.get("estado_base", "")
                tickets_state[tid]["asignado"]    = ticket.get("asignado", "")
                continue

            # ── Ticket nuevo ──────────────────────────────────────────────
            ticket_folder = os.path.join(
                config["output_dir"],
                ticket["estado_normalizado"],
                tid,
            )
            os.makedirs(ticket_folder, exist_ok=True)

            print(f"[NEW]  {ticket['estado_normalizado']}/{tid}/")
            print(f"       Titulo: {ticket['titulo'].encode('cp1252', errors='replace').decode('cp1252')}")

            # Deep scraping del detalle + descarga de adjuntos
            detail = scrape_ticket_detail(context, ticket, ticket_folder)

            if not detail["adjuntos"]:
                print(f"       [INFO] Sin adjuntos")
            if not detail["descripcion"]:
                print(f"       [INFO] Descripción no capturada (selector no encontrado)")
            if detail.get("notas"):
                print(f"       [INFO] {len(detail['notas'])} nota(s) en historial")

            # Generar INC-{id}.md completo
            generate_ticket_md(ticket, detail, ticket_folder)
            print(f"       [MD]   INC-{tid}.md")

            # Generar 6 archivos PM
            generate_pm_files(ticket, detail, ticket_folder)

            # Registrar en estado
            tickets_state[tid] = {
                "estado_normalizado":  ticket["estado_normalizado"],
                "estado_base":         ticket.get("estado_base", ""),
                "asignado":            ticket.get("asignado", ""),
                "titulo":              ticket["titulo"],
                "fecha_actualizacion": ticket.get("fecha_actualizacion", ""),
                "detail_hash":         _detail_hash(detail),
                "processed_at":        datetime.now().isoformat(),
                "auto_priority":       _compute_priority_score(ticket),
            }
            stats["new"] += 1
            print()

        context.close()

    except Exception:
        # Si algo falla, cerrar el browser para forzar recreación en el próximo ciclo
        _close_browser()
        raise

    save_state(config["state_path"], state)

    print(f"{'-' * 55}")
    print(f"[RESUMEN] Nuevos: {stats['new']} | Actualizados: {stats['updated']} | "
          f"Movidos: {stats['moved']} | Skip: {stats['skip']}")
    print(f"[RESUMEN] Total tickets conocidos: {len(tickets_state)}")
    if stats["new"] > 0:
        print(f"[RESUMEN] Carpeta de salida: {config['output_dir']}/")
        today = datetime.now().strftime("%Y-%m-%d")
        for tid in [t["ticket_id"] for t in tickets
                    if tickets_state.get(t["ticket_id"], {}).get("processed_at", "").startswith(today)]:
            t = tickets_state.get(tid, {})
            print(f"         -> {tid}: {t.get('titulo', '')[:60]}")
        print(f"[INFO] Podes analizar los nuevos con el agente PMTL-Stack2")
    print(f"{'-' * 55}")


def _find_ticket_folder(output_dir: str, estado_normalizado: str, tid: str) -> str | None:
    """Encuentra la carpeta de un ticket (puede no estar en el estado esperado)."""
    # Primero buscar en el estado esperado
    expected = os.path.join(output_dir, estado_normalizado, tid)
    if os.path.isdir(expected):
        return expected
    # Buscar en todos los estados
    try:
        with os.scandir(output_dir) as dirs:
            for d in dirs:
                if not d.is_dir():
                    continue
                candidate = os.path.join(d.path, tid)
                if os.path.isdir(candidate):
                    return candidate
    except Exception:
        pass
    return None


if __name__ == "__main__":
    import argparse
    from session_manager import SessionExpiredError
    parser = argparse.ArgumentParser(description="Mantis Scraper")
    parser.add_argument("--project", default=None, help="Nombre del proyecto (carpeta en projects/)")
    args = parser.parse_args()
    try:
        run_scraper(project_name=args.project)
    except SessionExpiredError as e:
        print(f"[ERROR] {e}")
        print("[SESSION] Intentando abrir browser para renovar sesión...")
        try:
            from session_manager import SessionManager
            _cfg = load_config()
            if args.project:
                _cfg.update(_load_project_overrides(args.project))
            _sm = SessionManager(_cfg["auth_path"], _cfg["mantis_url"])
            if _sm.prompt_renewal(timeout_seconds=300):
                print("[SESSION] Sesión renovada — reintentando scraper...")
                run_scraper(project_name=args.project)
            else:
                print("[ERROR] No se renovó la sesión. Ejecutar manualmente: python capture_session.py")
                sys.exit(1)
        except Exception as _inner:
            print(f"[ERROR] No se pudo renovar la sesión: {_inner}")
            sys.exit(1)
