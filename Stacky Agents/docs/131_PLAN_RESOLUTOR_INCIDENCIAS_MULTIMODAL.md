# Plan 131 — Resolutor de Incidencias multimodal: intake (fotos + archivos + texto) → agente unificado → Issue en ADO linkeado a su Épica → nodo con aristas en el grafo documental

**Estado:** CRITICADO (v2, 2026-07-13) — RECHAZADO en v1 (C1/C2/C4 bloqueantes verificados en código); v2 corrige todos los hallazgos y queda lista para implementar

**v1 → v2 — CHANGELOG (crítica adversarial 2026-07-13):**

- **C1 BLOQUEANTE (fix §4.4 + F5.5):** `TrackerItem.fields={"System.Tags": ...}` hacía que `AdoClient.create_work_item` tomara la rama WS1 (`services/ado_client.py:600-628`) que **IGNORA los parámetros `title`/`description`** → el Issue nacía sin título en ADO (400 garantizado). v2 congela: `System.Title` y `System.Description` duplicados DENTRO de `fields` + test que lo asserta.
- **C2 BLOQUEANTE (fix F3):** el catálogo de épicas vía `provider.fetch_open_items` devuelve `[]` **SIEMPRE** en ADO: `AdoTrackerProvider.fetch_open_items` es un stub (`services/ado_provider.py:53-64`; `AdoClient` NO tiene `list_work_items`, verificado por grep). v2 agrega `fetch_epics()` duck-typed en el adapter ADO con WIQL dedicado (precedente de método extra-puerto: `mr_url`/`commit_url`, `gitlab_provider.py:179-195`).
- **C4 BLOQUEANTE (fix F4.5 + F5.4/F5.5b):** `create_epic_from_brief` NO usa el puerto tracker (publica ADO-directo vía `_publish_epic_to_ado`, `api/tickets.py:7031`) → "obtener provider con el mismo helper" apuntaba a un helper INEXISTENTE y "leer id+url como los lee create_epic_from_brief" a un dict que ese código nunca lee. v2 congela `get_tracker_provider(project)` (`services/tracker_provider.py:105`) y la extracción literal de id/url.
- **C3 IMPORTANTE (fix F4.3):** `ado_id=-2` COLISIONA con el discriminador de identidad del agente DevOps Plan 90 (`api/devops_agent.py:108` y `:350`). v2 usa `ado_id=-8` (mapa de sentinels ocupados incluido).
- **C5 IMPORTANTE (fix F0):** flag nueva sin entrada en `PLAIN_HELP` deja ROJO el centinela `tests/test_harness_flags_help.py` (exige cobertura 100% del registry). v2 agrega la entrada literal y suma esa suite a los criterios de F0 y F8.
- **C6 IMPORTANTE (fix F3):** el label de épica que Stacky crea en GitLab es `type::epic` (`_type_label`, `gitlab_provider.py:43-44`), no `epic` → el filtro por igualdad nunca matcheaba. v2 filtra por substring.
- **C7 IMPORTANTE (fix F5.5c):** quedaba indefinido qué responde publish si `create_item` falla por razón NO-parent (p.ej. `Bug` en proceso Basic de ADO, provider mal configurado, red caída). v2 congela: 502 `tracker_error` + incidente en `status="error"` re-publicable + test.
- **C8 MENOR (fix F5):** `GET /incident-preview` mutaba estado incondicionalmente; ahora la transición es condicional (`analizando`→`analizada`) e idempotente.
- **C9 MENOR (fix F1):** `app.py` NO define `MAX_CONTENT_LENGTH` (verificado) y el endpoint leía todo a RAM antes de validar → guard temprano por `Content-Length` (413) + lectura con cap por archivo.
- **C10 MENOR (fix F2):** el bootstrap del `.agent.md` dependía de un archivo del repo que puede NO existir en deploy frozen (gotcha PyInstaller) → la plantilla vive como constante en `incident_context.py`; el `.md` commiteado es espejo (test de sincronía).
- **C11 MENOR:** refs corregidas: el preview espejo es `epic_payload_preview` (`api/tickets.py:7061`, no `:6319`) con `_get_run_for_preview` (`:7055`); `confirm is not True` está en `:7020`; el modal en `TicketBoard.tsx:943-947`.
- **C12 MENOR (fix F3):** normalización del catálogo especificada también para el shape ADO raw (title/state viven en `fields["System.*"]`, no top-level).
- **C13 MENOR (fix F5.7):** dependencia invertida F5→F6 resuelta: import de `incident_docs` en try/except (módulo aún ausente ⇒ `doc_path=None`) → F5 queda verde sin F6.
- **C14 IMPORTANTE (fix F4.10):** el run de incidente es one-shot (nadie responde por consola; el modal solo pollea hasta terminal). En `claude_code_cli`, un pool ticket cuyo `ado_id` NO esté en `_ONE_SHOT_ADO_IDS` (`services/claude_code_cli_runner.py:216`) deja el proceso vivo esperando input → run colgado hasta el timeout de 1800s (bug ya sufrido por el Documentador `-7`). v2: agregar `-8` al frozenset + test.
- **[ADICIÓN ARQUITECTO] (F1b + F7):** reanudación de incidencias en curso: `GET /api/incidents` + `pickResumableIncident()` + banner "Retomar" al abrir el modal — cubre el riesgo zombie/cierre accidental SIN trabajo extra del operador.
- **[ADICIÓN ARQUITECTO] (§4.5):** trazabilidad run↔doc: `execution_id` en el frontmatter del doc del incidente.
**Dependencias:** ninguna dura. Reusa: pipeline brief→épica (Plan 38/41/42/45/52/55, `api/agents.py:564` + `api/tickets.py:6999`), puerto tracker-agnóstico (Plan 70, `services/tracker_provider.py`), grafo documental (Plan 109, `services/doc_graph.py` + `services/doc_indexer.py`), registro de flags del arnés (`services/harness_flags.py` + `services/harness_flags_help.py`), telemetría (`services/stacky_logger.py`).
**Ortogonal a:** Plan 110 (revisor de PRs), Plan 129 (paleta global), Plan 130 (gate de integridad). No comparte archivos nuevos con ninguno; comparte archivos EDITADOS (`api/tickets.py`, `api/agents.py`, `endpoints.ts`, `config.py`, `harness_flags.py`, `App`-adyacentes) → ver guardarraíl §3.9 de staging quirúrgico.

> Este documento está redactado para que un MODELO MENOR (Haiku, Codex CLI o GitHub
> Copilot Pro) lo implemente SIN inferir nada. Los contratos JSON/HTML, los nombres de
> símbolos, las rutas y los comandos son LITERALES: prohibido desviarse de los nombres
> exactos, prohibido "mejorar" el alcance. Todo lo ambiguo ya fue decidido acá.

---

## 1. Objetivo + KPI

Hoy, cuando el operador detecta una incidencia (un bug del producto del cliente, una
pantalla rota, un log con error), redactar el ticket dev-ready es artesanal: escribir el
contexto de negocio, el análisis funcional, el análisis técnico, los pasos de
reproducción, buscar la épica relacionada, subir las capturas a ADO y linkear todo a
mano. Son 30-60 minutos por incidencia y el resultado depende del ánimo del redactor.

Este plan agrega un **botón "🚑 Resolver incidencia"** en la pestaña Tickets que abre un
modal donde el operador **carga fotos, archivos y texto libre** describiendo la
incidencia. Con 2 clicks (Analizar → Publicar):

1. Un **agente NUEVO y unificado** (`IncidentAnalyst`) — que fusiona en UNA pasada las
   tres perspectivas de los agentes existentes `BusinessAgent` (negocio),
   `FunctionalAnalyst` (funcional) y `TechnicalAnalyst.v2` (técnico) — desglosa la
   incidencia en un documento HTML dev-ready: resumen, contexto de negocio, análisis
   funcional, análisis técnico, pasos de reproducción, criterios de aceptación, archivos
   probables y **la épica relacionada elegida desde el catálogo real del tracker, con
   confianza y razón**.
2. Stacky publica un **Issue en ADO** (o GitLab, con paridad) **linkeado como hijo de la
   épica relacionada**, con los archivos del operador subidos como **attachments
   nativos**.
3. Stacky escribe un **doc markdown del incidente** en el árbol que el grafo documental
   ya indexa, con wikilinks y referencias a código → el incidente **aparece como nodo
   con aristas** en la pestaña Grafo (Plan 109/111) sin tocar el contrato congelado de
   `GET /api/docs/graph`.

Una pasada de agente (no tres), publicación desde el backend (no desde el runner → 
paridad total de runtimes), y todo el contexto inyectado automáticamente (attachments,
catálogo de épicas, client-profile y RAG existentes).

**KPIs (binarios):**

- **KPI-1 (dev-ready en 2 clicks):** desde el modal, con texto + 1 imagen + 1 log, se
  obtiene un Issue publicado en el tracker con las 4 secciones obligatorias del contrato
  (§4.3) — verificado por los tests de F5 con provider fake.
- **KPI-2 (linkeo a épica):** si el agente propone una épica válida (o el operador la
  overridea en el preview), el Issue queda con parent link nativo; si el parent falla,
  fallback declarado a comentario en la épica; nunca falla la publicación por el link
  (test F5 caso 8-10).
- **KPI-3 (aristas en el grafo):** publicar una incidencia produce un `.md` bajo
  `docs/incidencias/` con al menos 1 wikilink (`[[INDICE_INCIDENCIAS]]`) y las rutas de
  código del desglose → `build_graph` lo devuelve como nodo con ≥1 arista saliente
  (test F6 caso 6, integra con `doc_graph` real sobre tmp_path).
- **KPI-4 (paridad 3 runtimes):** el análisis corre en `claude_code_cli`, `codex_cli` y
  `github_copilot`; la publicación es SIEMPRE backend (independiente del runtime). Las
  imágenes degradan explícitamente según runtime (§3.4). Test F4 caso 5 verifica que
  `run-incident` NO rechaza ningún runtime (a diferencia del autopublish de run-brief,
  `api/agents.py:599-608`).
- **KPI-5 (kill-switch limpio):** flag OFF → `GET /api/incidents/status` responde
  `{enabled:false}` (200), el resto de endpoints nuevos responden 404, el botón no se
  renderiza, y NINGÚN flujo existente cambia ni un byte (tests F0).

## 2. Por qué ahora / gap que cierra (evidencia verificada en HEAD)

- El pipeline brief→épica existe y funciona (`api/agents.py:564` `run_brief`,
  `api/tickets.py:6998` `create_epic_from_brief`, modal `EpicFromBriefModal.tsx`), pero
  es **solo texto** (sin fotos ni archivos), produce **épicas de alcance nuevo** (no
  desgloses de incidencias sobre lo ya construido) y su autopublicación está atada a
  `claude_code_cli` (Plan 52 F0, `api/agents.py:599-608`).
- Los 3 agentes de análisis existen por separado (`backend/Stacky/agents/`:
  `BusinessAgent.agent.md`, `FunctionalAnalyst.agent.md`, `TechnicalAnalyst.v2.agent.md`)
  y corren en pasadas separadas del pipeline de tickets. Para una incidencia, tres
  pasadas son latencia y costo sin valor: el desglose cabe en UNA pasada con un prompt
  unificado. No existe hoy ningún agente tipo `incident` en `backend/agents/__init__.py:12-26`.
- El puerto tracker soporta CASI todo lo que la publicación necesita:
  `TrackerItem.parent_id` (`services/tracker_provider.py:38`), attachments nativos en
  ADO (`services/ado_provider.py:128-133`) y en GitLab (uploads + markdown,
  `services/gitlab_provider.py:311-343`), y parent link GitLab con fallback a
  issue-links "relates" (`services/gitlab_provider.py:102-125` + `:271-272`).
  **DOS excepciones verificadas en código (v2):** (a) `AdoTrackerProvider.fetch_open_items`
  es un stub que devuelve `[]` siempre (`ado_provider.py:53-64` — `AdoClient` no tiene
  `list_work_items`; lo real es `fetch_open_work_items(wiql=...)`, `ado_client.py:314`)
  → el catálogo de épicas ADO necesita el método NUEVO `fetch_epics()` de F3;
  (b) `AdoClient.create_work_item` con `fields` no-None toma la rama WS1
  (`ado_client.py:600-628`) que IGNORA `title`/`description` posicionales → §4.4 congela
  el workaround (title/description duplicados dentro de `fields`). Ninguna de las dos
  toca el Protocol del puerto (`PORT_METHODS` intacto).
- El grafo documental (Plan 109/111) indexa `STACKY_AGENTS_ROOT/docs/` recursivo
  (`services/doc_indexer.py:263-270`) y parsea wikilinks y referencias a código
  (`services/doc_graph.py:73-98`) con cache invalidable
  (`doc_graph.invalidate_graph_cache`, `services/doc_graph.py:116`). Escribir un `.md`
  de incidente ahí = nodo con aristas GRATIS, sin tocar el contrato congelado del
  endpoint.
- Precedente en el propio repo: las incidencias se documentaban a mano en
  `Stacky Agents/docs/` (`20_INCIDENTE_ADO_241_DETECCION_ARCHIVOS_2026-06-05.md`).
  Este plan lo vuelve automático y con grafo.
- No hay NADA llamado `incident` en el namespace backend (verificado por grep):
  cero riesgo de colisión de nombres.

## 3. Principios y guardarraíles (NO negociables)

1. **Human-in-the-loop innegociable:** el agente PROPONE (desglose + épica con
   confianza); el operador VE el preview y decide publicar con un click explícito
   (`confirm: true` duro en el backend, espejo de `create_epic_from_brief`,
   `api/tickets.py:7005`). El operador puede **override** de la épica relacionada en el
   preview. NO hay autopublicación desde el runner (deliberado: más estricto que
   épica-desde-brief y con paridad total de runtimes a cambio).
2. **Cero trabajo extra del operador:** feature 100% opt-in con flag default OFF. Con la
   flag ON, el flujo es: llenar el modal → click Analizar → click Publicar. Todo lo
   demás (contexto, attachments, doc, grafo, link a épica) es automático. Sin nueva
   carga de configuración: la flag se activa desde el panel de flags existente
   (`HarnessFlagsPanel`).
3. **Paridad 3 runtimes:** la GENERACIÓN corre en los 3 runtimes vía `run_agent` (igual
   que run-brief corre BusinessAgent). La PUBLICACIÓN la hace el backend de Stacky vía
   el puerto tracker (nunca el runner) → funciona idéntica con los 3. Sin la
   restricción `_AUTOPUBLISH_RUNTIME` de run-brief.
4. **Imágenes con degradación DECLARADA por runtime:** el bloque
   `attachments-manifest` (§4.2) siempre incluye rutas ABSOLUTAS de las imágenes +
   metadata + contenido inline de archivos de texto. `claude_code_cli` puede abrir las
   imágenes del disco (su tool Read es multimodal); `codex_cli` puede leer los archivos
   del workspace y si su build no soporta visión, usa la metadata + el texto del
   operador; `github_copilot` (bridge texto) usa SIEMPRE metadata + inline de texto.
   El prompt instruye explícitamente: "si tu runtime no puede ver imágenes, decláralo
   en el desglose como `[PENDIENTE: verificar captura <nombre>]`". Nada se rompe, nada
   se finge.
5. **Mono-operador, sin auth:** ningún endpoint nuevo valida usuario (patrón del resto
   de la API). Nada de RBAC.
6. **No degradar:** cero cambios de comportamiento con la flag OFF (tests F0). Los
   endpoints nuevos son aditivos; `api/tickets.py` y `api/agents.py` solo GANAN
   funciones/rutas nuevas; ningún símbolo existente cambia de firma.
7. **Flag default OFF (regla de la casa):** feature visible para el operador → opt-in.
   `FlagSpec` SIN parámetro `default=` (gotcha Plan 63: default explícito solo para
   flags curadas en `_CURATED_DEFAULTS_ON`, `tests/test_harness_flags.py:465`);
   `config.py` con `os.getenv(..., "false")` (espejo de `STACKY_ISSUE_FROM_BRIEF_ENABLED`,
   `config.py:828-830`). SIN `env_only`, SIN `requires`.
8. **Anti-narración:** guard `_looks_like_incident` en preview Y en publish (espejo de
   `_looks_like_epic`, `api/tickets.py:5983`): los CLI a veces devuelven narración
   ("voy a analizar...") en vez del HTML. Eso NUNCA se publica.
9. **Al implementar (WIP ajeno):** `api/tickets.py`, `api/agents.py`, `config.py`,
   `services/harness_flags.py`, `frontend/src/api/endpoints.ts` y archivos de tests
   suelen tener WIP de sesiones paralelas → staging quirúrgico por pathspec/hunk;
   PROHIBIDO `git stash`/`reset`/`checkout` de limpieza; `git status` al final.
10. **Colisión de numeración (riesgo VIVO):** hay un loop paralelo proponiendo planes
    (colisiones reales en 110, 118→119, 127→128 y 129). Quien implemente debe verificar
    que `131_PLAN_RESOLUTOR_INCIDENCIAS_MULTIMODAL.md` sigue siendo el único `131_*`.
11. **Seguridad de archivos:** allowlist de extensiones, límites de tamaño, sanitización
    de nombres, anti-traversal en el serving (§4.1). PROHIBIDO aceptar `.zip`/`.exe`/
    `.dll` (sin expansión de archivos, sin binarios ejecutables).

## 4. Contratos congelados

### 4.1 Intake: límites y almacenamiento (LITERALES)

```python
# services/incident_store.py
MAX_FILES = 10
MAX_FILE_BYTES = 10 * 1024 * 1024        # 10 MB por archivo
MAX_TOTAL_BYTES = 25 * 1024 * 1024       # 25 MB por incidencia
MAX_TEXT_LEN = 20_000                    # caracteres del texto libre
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
TEXT_EXTENSIONS = {".txt", ".log", ".md", ".json", ".csv", ".xml", ".yaml", ".yml",
                   ".sql", ".ps1", ".sh", ".py", ".cs", ".ts", ".tsx", ".js",
                   ".html", ".css", ".config"}
ALLOWED_EXTENSIONS = IMAGE_EXTENSIONS | TEXT_EXTENSIONS | {".pdf"}
```

- Almacenamiento: `data_dir()/incidents/<incident_id>/` (usar
  `runtime_paths.data_dir()`, ya usado por el resto del runtime data). Dentro:
  `intake.json` + los archivos con `stored_name` sanitizado.
- `incident_id` = `"inc_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid4().hex[:6]`.
- `sanitize_filename(name)`: tomar SOLO el basename (defensa contra `..\\`), reemplazar
  todo char fuera de `[A-Za-z0-9._ -]` por `_`, colapsar espacios, recortar a 120 chars,
  si queda vacío → `"archivo"`. Si dos archivos sanitizan igual, sufijar `_2`, `_3`, ...
- Ledger global `data_dir()/incidents/ledger.json` = lista de resúmenes
  `{id, created_at, status, title, tracker_id}`; TODA escritura bajo un
  `threading.Lock()` module-level `_LEDGER_LOCK` (patrón ledger Plan 120).
- `intake.json` (estado completo del incidente):

```json
{
  "id": "inc_20260713_153000_a1b2c3",
  "created_at": "2026-07-13T15:30:00+00:00",
  "text": "texto libre del operador",
  "files": [
    {"name": "pantalla rota.png", "stored_name": "pantalla_rota.png",
     "bytes": 123456, "ext": ".png", "kind": "image", "sha256": "..."}
  ],
  "status": "capturada",
  "execution_id": null,
  "tracker_id": null,
  "tracker_url": null,
  "epic_id": null,
  "doc_path": null,
  "error": null
}
```

- `kind` ∈ `image` (ext en IMAGE_EXTENSIONS) | `text` (ext en TEXT_EXTENSIONS) |
  `binary` (resto, o sea `.pdf`).
- `status` ∈ `capturada` → `analizando` → `analizada` → `publicada`, más `error`.
  Transiciones las hacen los endpoints; nunca el frontend directamente.

### 4.2 Bloques de contexto para el agente (formato EXACTO)

`build_incident_prompt(incident, catalog)` compone (en este orden) el string que
`run_incident` pasa al lanzamiento (por el MISMO parámetro por el que `run_brief` pasa
el brief — leer `api/agents.py:564-660` y espejar):

```
INCIDENCIA REPORTADA POR EL OPERADOR
====================================
<texto libre, verbatim>

<attachments-manifest>
Archivos adjuntos (N):
- pantalla_rota.png | imagen | 120.6 KB | sha256=ab12... | ruta_absoluta=C:\...\incidents\inc_...\pantalla_rota.png
- error.log | texto | 4.2 KB | sha256=cd34... | ruta_absoluta=C:\...\error.log
Si tu runtime puede leer imágenes del disco, abrí las rutas absolutas de las imágenes.
Si NO puede, declaralo con [PENDIENTE: verificar captura <nombre>] donde corresponda.

--- Contenido de archivos de texto (inline, truncado) ---
### error.log
<primeros 8000 chars>
[TRUNCADO: quedaron X bytes sin mostrar]      ← solo si se truncó
</attachments-manifest>

<epic-catalog>
Épicas ABIERTAS del tracker (elegí a lo sumo UNA como relacionada):
- id=267 | Batch multibanco Mul2Bane | estado=open
- id=301 | Alta de clientes AgendaWeb | estado=open
(catálogo vacío → escribí exactamente "EPICA: ninguna")
</epic-catalog>
```

Límites del inline: `_INLINE_MAX_PER_FILE = 8_000` chars por archivo de texto,
`_INLINE_MAX_TOTAL = 40_000` chars sumados (constantes en
`services/incident_context.py`). PDF y binarios: solo la línea de metadata, nunca inline.

### 4.3 Contrato de salida del agente (HTML, headings LITERALES sin acentos)

El agente DEBE devolver SOLO este HTML (sin narración, sin markdown alrededor; se tolera
fence ```` ```html ```` que `_extract_epic_html_raw` ya limpia, `api/tickets.py:5873`):

```html
<h1>[INC] Título corto de la incidencia</h1>
<h2>RESUMEN EJECUTIVO</h2>            <p>2-4 frases: qué se rompe, a quién impacta, urgencia.</p>
<h2>CONTEXTO DE NEGOCIO</h2>          <p>Perspectiva BusinessAgent: proceso de negocio afectado, actores, impacto.</p>
<h2>ANALISIS FUNCIONAL</h2>           <p>Perspectiva FunctionalAnalyst: comportamiento esperado vs observado, casos borde, plan de pruebas mínimo.</p>
<h2>ANALISIS TECNICO</h2>             <p>Perspectiva TechnicalAnalyst: hipótesis de causa raíz, componentes involucrados, approach sugerido de fix.</p>
<h2>PASOS DE REPRODUCCION</h2>        <ol><li>...</li></ol>
<h2>CRITERIOS DE ACEPTACION</h2>      <ul><li>binarios, verificables</li></ul>
<h2>ARCHIVOS Y MODULOS PROBABLES</h2> <ul><li>ruta/al/archivo.ext — por qué</li></ul>
<h2>EPICA RELACIONADA</h2>            <p>EPICA: 267 | CONFIANZA: 85 | RAZON: la incidencia afecta el proceso X de esa épica</p>
<h2>PRIORIDAD Y ESTIMACION</h2>       <p>Prioridad: alta|media|baja. Estimación: S|M|L. Justificación breve.</p>
```

Reglas de parsing (backend):

- `_looks_like_incident(html)` → True si hay `<h1>` o `<h2>` Y aparecen (case-insensitive,
  literales SIN acentos) al menos 3 de: `ANALISIS FUNCIONAL`, `ANALISIS TECNICO`,
  `PASOS DE REPRODUCCION`, `CRITERIOS DE ACEPTACION`. Definir la tupla
  `_INCIDENT_REQUIRED_SECTIONS = ("ANALISIS FUNCIONAL", "ANALISIS TECNICO", "PASOS DE REPRODUCCION", "CRITERIOS DE ACEPTACION")`.
- `_parse_related_epic(html)` → `{"epic_id": int|None, "confidence": int|None, "reason": str|None}`
  con regex sobre el texto plano (tags removidos con `re.sub(r"<[^>]+>", " ", html)`):
  - `re.search(r"EPICA:\s*(ninguna|\d+)", plain, re.IGNORECASE)` → `ninguna` ⇒ None.
  - `re.search(r"CONFIANZA:\s*(\d{1,3})", plain, re.IGNORECASE)` → clamp 0..100.
  - `re.search(r"RAZON:\s*([^|<\n]{1,300})", plain, re.IGNORECASE)`.
  - Cualquier cosa no matcheada ⇒ None en ese campo. NUNCA lanzar excepción.
- El título del Issue = texto del `<h1>` (strip de tags); si falta `<h1>`, usar
  `"[INC] " + primeras 8 palabras del texto del operador`.

### 4.4 Endpoints nuevos (contratos request/response)

| Método y ruta | Gate | Request | Response OK | Errores |
|---|---|---|---|---|
| `GET /api/incidents/status` | ninguno (SIEMPRE 200) | — | `{enabled: bool, max_files: 10, max_file_mb: 10, allowed_extensions: [".png", ...]}` | — |
| `POST /api/incidents` | flag OFF → 404 `{ok:false,error:"feature_disabled"}` | multipart: campo `text` + files repetidos en campo `files` | 201 `{ok:true, incident:{...intake.json}}` | 400 `{ok:false,error:"validation_error",message}` (texto vacío Y sin archivos; ext no permitida; límites) |
| `GET /api/incidents/<id>` | flag OFF → 404 | — | `{ok:true, incident:{...}}` | 404 `{ok:false,error:"not_found"}` |
| `GET /api/incidents` [ADICIÓN ARQUITECTO] | flag OFF → 404 | — | `{ok:true, incidents:[...resúmenes del ledger, orden created_at desc]}` | — |
| `GET /api/incidents/<id>/files/<stored_name>` | flag OFF → 404 | — | el archivo (send_file) | 404 si no existe o si el path resuelto escapa de la carpeta del incidente (anti-traversal con `Path.resolve()` + `is_relative_to`) |
| `POST /api/agents/run-incident` | flag OFF → 404 | `{incident_id, runtime?, project?, model?, effort?}` | `{execution_id, status:"running"}` | 400 `{ok:false,error:"incident_not_found"}`; 400 si `status` no es `capturada`/`analizada`/`error` |
| `GET /api/tickets/incident-preview?execution_id=&incident_id=` | flag OFF → 404 | — | `{ok:true, title, html, related_epic:{epic_id,confidence,reason}, publishable:true}` | 200 `{ok:false, error:"incident_not_in_output", publishable:false}` si `_looks_like_incident` falla |
| `POST /api/tickets/incidents/publish` | flag OFF → 404 | `{incident_id, execution_id, confirm:true, override_epic_id?: int\|null, work_item_type?: "Issue"\|"Bug"}` | 201 `{ok:true, tracker_id, url, epic_id, epic_link_mode:"parent"\|"comment"\|"none", doc_path, warnings:[...]}` | 400 si `confirm is not True` (comparación exacta, espejo `api/tickets.py:7020`); 409 `{ok:false,error:"already_published", tracker_id}` si el incidente ya tiene `tracker_id`; 422 `{ok:false,error:"incident_not_in_output"}` si el guard falla server-side; **502 `{ok:false,error:"tracker_error",message}` si el tracker rechaza la creación por razón no-parent (C7, ver F5.5c)** |

- `override_epic_id`: `null` explícito = "publicar SIN épica" (ignora la del agente);
  ausente = usar la del agente; entero = usar ese id.
- `work_item_type` allowlist `("Issue","Bug")`, default `"Issue"` (Basic process de ADO:
  Epic > Issue; en proyectos Agile el operador puede elegir Bug). En GitLab ambos crean
  issue (el mapeo de tipo→label ya lo hace `gitlab_provider._type_label`).
- **Contrato del `TrackerItem` de publish (C1, CONGELADO — copiar tal cual):**

```python
item = TrackerItem(
    item_type=work_item_type,          # "Issue" | "Bug" (el adapter ADO mapea via _ADO_TYPE_MAP)
    title=title,
    description_html=html,
    labels=("incidencia",),            # GitLab los usa; ADO los ignora
    parent_id=str(epic_id) if epic_id is not None else None,
    fields={
        # OJO (verificado en HEAD): con fields no-None, AdoClient.create_work_item
        # toma la rama WS1 (services/ado_client.py:600-628) que IGNORA los parámetros
        # posicionales title/description → DEBEN duplicarse acá. GitLab ignora fields
        # por completo (gitlab_provider.create_item no los lee).
        "System.Title": title,
        "System.Description": html,
        "System.Tags": "incidencia; stacky-incident",
    },
)
```

  PROHIBIDO pasar `fields` sin `System.Title`/`System.Description`: en ADO crearía un
  work item sin título (400 del API). El test F5 caso 6 asserta que el provider fake
  recibió `fields["System.Title"] == title`.

### 4.5 Doc del incidente (plantilla LITERAL) y grafo

Destino: `STACKY_AGENTS_ROOT/docs/incidencias/INC-<tracker_id>_<slug>.md` — importar
`STACKY_AGENTS_ROOT` DESDE `services.doc_indexer` (mismo símbolo que usa el indexador,
`services/doc_indexer.py:265` indexa `STACKY_AGENTS_ROOT / "docs"` recursivo → el doc
entra al grafo garantizado). Si `STACKY_AGENTS_ROOT/docs` no existe (deploy frozen sin
docs): escribir en `data_dir()/incident_docs/` y agregar warning
`"doc fuera del grafo (deploy sin docs/)"` a la respuesta. `_slugify(title)`: lower,
solo `[a-z0-9-]`, espacios→`-`, colapsar `-`, cap 60 chars.

```markdown
---
tipo: incidencia
incident_id: inc_20260713_153000_a1b2c3
execution_id: 1234        # [ADICIÓN ARQUITECTO] trazabilidad run↔doc (tomar de incident["execution_id"]; si None, omitir la línea)
tracker_id: 341
work_item_type: Issue
epica: 267
estado: publicada
fecha: 2026-07-13
origen: stacky-incident-resolver
---

# INC-341 — Título corto de la incidencia

> Issue: <URL del tracker> · Épica relacionada: 267 (confianza 85%)

<h1>...todo el HTML del desglose, embebido verbatim...</h1>

## Relacionados

- [[INDICE_INCIDENCIAS]]
- Archivos probables (aristas a código): las rutas de la sección
  ARCHIVOS Y MODULOS PROBABLES, una por línea, texto plano.
```

- Las rutas de código en texto plano las detecta `parse_code_refs`
  (`services/doc_graph.py:85-98`: exige `dir/archivo.ext` o `archivo.ext:NNN`) → aristas
  doc→código automáticas. El wikilink `[[INDICE_INCIDENCIAS]]` da la arista doc→doc.
- `INDICE_INCIDENCIAS.md` (misma carpeta): crear si falta con
  `# Índice de Incidencias\n\n`; append idempotente (si ya hay una línea con
  `[[INC-<tracker_id>_<slug>]]`, no duplicar):
  `- [[INC-341_titulo-corto]] — Título corto — 2026-07-13 — tracker#341`.
- Tras escribir: `from services.doc_graph import invalidate_graph_cache;
  invalidate_graph_cache()` (símbolo real en `services/doc_graph.py:116`).
- Escritura del doc SIEMPRE best-effort: cualquier excepción → `doc_path: null` +
  warning en la respuesta; JAMÁS revierte ni falla la publicación ya hecha.

---

## 5. Fases

### F0 — Flag + status endpoint (fundación verificable)

**Objetivo:** feature gateada de punta a punta con default OFF y botón invisible.
**Valor:** kill-switch limpio; cero riesgo para lo existente.

**Archivos:**
- `Stacky Agents/backend/config.py` — agregar (al final del bloque de flags de features,
  cerca de `STACKY_ISSUE_FROM_BRIEF_ENABLED`, `config.py:828`):

```python
# Plan 131 — Resolutor de incidencias multimodal (botón + intake + agente unificado
# + publish tracker + doc en grafo). Feature opt-in visible → default OFF.
STACKY_INCIDENT_RESOLVER_ENABLED: bool = os.getenv(
    "STACKY_INCIDENT_RESOLVER_ENABLED", "false"
).lower() in ("1", "true", "yes")
```

- `Stacky Agents/backend/services/harness_flags.py` — agregar `FlagSpec` (junto a las
  specs de features, patrón de `STACKY_DOCS_GRAPH_ENABLED` en `harness_flags.py:1475`
  pero SIN `default=`):

```python
FlagSpec(
    key="STACKY_INCIDENT_RESOLVER_ENABLED",
    type="bool",
    label="Resolutor de incidencias multimodal (Plan 131)",
    description=(
        "Plan 131 — Botón 'Resolver incidencia' en Tickets: el operador carga fotos, "
        "archivos y texto libre; el agente unificado IncidentAnalyst (negocio + "
        "funcional + técnico en una pasada) desglosa la incidencia dev-ready; Stacky "
        "publica el Issue en el tracker linkeado a su épica, sube los archivos como "
        "attachments y escribe el doc del incidente en el grafo documental. "
        "Publicación siempre con preview y confirmación del operador. Default OFF."
    ),
    group="global",
    env_only=False,
),
```

- NO tocar `_CURATED_DEFAULTS_ON` (default OFF). NO agregar a `harness_defaults.env`.
- `Stacky Agents/backend/services/harness_flags_help.py` — **OBLIGATORIO (C5):** el
  centinela `tests/test_harness_flags_help.py` exige que `PLAIN_HELP` cubra el 100% del
  registry (líneas 33-40: registry−help = vacío). Agregar la entrada LITERAL (4 campos
  `PlainHelp`: `what`/`on_effect`/`off_effect`/`example`, redacción sin jerga — leer la
  denylist del test antes):

```python
"STACKY_INCIDENT_RESOLVER_ENABLED": PlainHelp(
    what="Un botón en Tickets para reportar una incidencia con fotos, archivos y texto, y convertirla en un ticket listo para el desarrollador.",
    on_effect="Si la activás: aparece el botón 'Resolver incidencia'; el agente arma el análisis completo y, tras tu revisión y confirmación, Stacky publica el ticket con sus adjuntos y lo enlaza a su épica.",
    off_effect="Si la apagás: el botón desaparece y todo vuelve a como estaba; las incidencias se redactan a mano como siempre.",
    example="Ves una pantalla rota: sacás la captura, la arrastrás al modal con dos líneas de contexto, y en dos clicks tenés el ticket armado, adjuntado y enlazado en el tracker.",
),
```
- `Stacky Agents/backend/api/incidents.py` — NUEVO blueprint:

```python
"""Plan 131 — Resolutor de incidencias multimodal."""
from __future__ import annotations
from flask import Blueprint, jsonify, request

bp = Blueprint("incidents", __name__, url_prefix="/incidents")

@bp.get("/status")
def incidents_status():
    from config import config as _cfg
    from services.incident_store import ALLOWED_EXTENSIONS, MAX_FILES, MAX_FILE_BYTES
    return jsonify({
        "enabled": bool(_cfg.STACKY_INCIDENT_RESOLVER_ENABLED),
        "max_files": MAX_FILES,
        "max_file_mb": MAX_FILE_BYTES // (1024 * 1024),
        "allowed_extensions": sorted(ALLOWED_EXTENSIONS),
    })
```

- `Stacky Agents/backend/app.py` — registrar el blueprint EXACTAMENTE como los demás:
  buscar el bloque de `register_blueprint` (grep `from api.ui_sections import`) y
  agregar la línea espejo para `api.incidents` (mismo prefijo `/api`).

**Tests PRIMERO** — `Stacky Agents/backend/tests/test_plan131_incident_flag.py`
(espejar el estilo de `tests/test_plan109_flag.py`: fixture app/client):
1. `test_flag_default_off` — `config.STACKY_INCIDENT_RESOLVER_ENABLED is False` con env
   limpio (monkeypatch.delenv + reload del patrón que use test_plan109_flag).
2. `test_status_responds_200_with_enabled_false_when_off`.
3. `test_status_responds_enabled_true_when_on` (monkeypatch config attr True).
4. `test_flagspec_registered` — la key existe en el registro de
   `services.harness_flags` y su spec NO está en `_CURATED_DEFAULTS_ON`.
5. `test_plain_help_entry` — `PLAIN_HELP["STACKY_INCIDENT_RESOLVER_ENABLED"]` existe y
   sus 4 campos son no-vacíos (C5).

**Comando:** `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; & ".venv\Scripts\python.exe" -m pytest tests\test_plan131_incident_flag.py -q`
**Criterio binario:** 5/5 verdes + `tests\test_harness_flags.py` Y
`tests\test_harness_flags_help.py` siguen verdes
(`... -m pytest tests\test_harness_flags.py tests\test_harness_flags_help.py -q`).
**Flag:** `STACKY_INCIDENT_RESOLVER_ENABLED` default OFF.
**Runtimes:** N/A (no toca runtimes). **Operador:** ninguno (opt-in, default off).

### F1 — Intake: store + endpoints multipart

**Objetivo:** capturar texto + archivos con límites, sanitización y ledger.
**Valor:** la incidencia queda persistida y consultable aunque el análisis falle.

**Archivos:**
- `Stacky Agents/backend/services/incident_store.py` — NUEVO. Símbolos EXACTOS:
  constantes de §4.1 + `sanitize_filename(name: str) -> str`,
  `incidents_root() -> Path` (=`runtime_paths.data_dir() / "incidents"`),
  `create_incident(text: str, files: list[tuple[str, bytes]]) -> dict`,
  `get_incident(incident_id: str) -> dict | None`,
  `update_incident(incident_id: str, **patch) -> dict`,
  `list_incidents() -> list[dict]`, `_LEDGER_LOCK = threading.Lock()`,
  `_read_ledger() / _write_ledger(entries)`.
  - `create_incident` valida: `len(text) <= MAX_TEXT_LEN` (truncar, no fallar),
    `text.strip() or files` no vacío (si vacío → `ValueError("empty_intake")`),
    `len(files) <= MAX_FILES`, cada archivo `len(data) <= MAX_FILE_BYTES`, suma
    `<= MAX_TOTAL_BYTES`, ext (lower) en `ALLOWED_EXTENSIONS` — violación →
    `ValueError` con mensaje claro (`"ext_not_allowed:<ext>"`, `"file_too_big:<name>"`,
    `"too_many_files"`, `"total_too_big"`).
  - Escribe archivos + `intake.json` (§4.1) + entrada en ledger. `sha256` con `hashlib`.
- `Stacky Agents/backend/api/incidents.py` — agregar a F0 las rutas `POST ""`,
  `GET ""` (lista, [ADICIÓN ARQUITECTO]: devuelve `{ok:true, incidents: list_incidents()}`
  ordenado por `created_at` desc), `GET "/<incident_id>"`,
  `GET "/<incident_id>/files/<stored_name>"` según §4.4.
  Multipart con guards tempranos (C9 — `app.py` NO define `MAX_CONTENT_LENGTH`,
  verificado, así que el techo lo pone este endpoint):
  1. ANTES de leer nada: `if request.content_length and request.content_length >
     MAX_TOTAL_BYTES + 1_048_576: return jsonify({...error:"validation_error",
     message:"total_too_big"}), 413` (1 MB de margen para el overhead multipart).
  2. `text = request.form.get("text", "")`.
  3. Lectura con cap por archivo: `data = f.read(MAX_FILE_BYTES + 1)` — si
     `len(data) > MAX_FILE_BYTES` → 400 `validation_error` `"file_too_big:<name>"`
     SIN leer el resto del stream. `files = [(f.filename, data), ...]`.
  `ValueError` del store → 400 `{ok:false, error:"validation_error", message:str(exc)}`.
  Serving: `send_file` SOLO tras verificar
  `resolved.is_relative_to(incidents_root() / incident_id)` (si no → 404).
  Telemetría: `stacky_logger.info("incidents", "incident_created", incident_id=..., files=len(...))`
  (import y estilo de `api/ui_sections.py:19,58-63`).

**Tests PRIMERO** — `tests/test_plan131_incident_store.py`:
1. sanitización (`"..\\..\\x.png"` → basename sin path; chars raros → `_`; colisión → `_2`).
2. create feliz (texto+2 archivos) → intake.json correcto, sha256 correcto, ledger con 1 entrada.
3. ext prohibida (`.exe`) → ValueError `ext_not_allowed`.
4. archivo > 10MB → ValueError; total > 25MB → ValueError; > 10 archivos → ValueError.
5. intake vacío (sin texto ni archivos) → ValueError `empty_intake`.
6. `update_incident` patchea y persiste; `get_incident` inexistente → None.
7. (monkeypatch `runtime_paths.data_dir` → tmp_path en TODOS los tests.)

— `tests/test_plan131_incident_api.py`:
1. POST multipart feliz → 201 + incident en body.
2. POST con flag OFF → 404.
3. POST ext prohibida → 400 validation_error.
4. GET file → 200 con bytes exactos; GET con `stored_name` = `..%5C..%5Cintake.json`
   → 404 (anti-traversal).
5. GET incident inexistente → 404 not_found.
6. `GET /api/incidents` → 200 con los resúmenes del ledger (y 404 con flag OFF)
   [ADICIÓN ARQUITECTO].
7. POST con header `Content-Length` > 26 MB → 413 sin crear nada (C9).

**Comando:** `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; & ".venv\Scripts\python.exe" -m pytest tests\test_plan131_incident_store.py tests\test_plan131_incident_api.py -q`
**Criterio binario:** todos verdes.
**Flag:** gateado por `STACKY_INCIDENT_RESOLVER_ENABLED` (status exceptuado).
**Runtimes:** N/A (persistencia local pura, idéntica bajo los 3). **Operador:** ninguno.

### F2 — Agente unificado `IncidentAnalyst` (clase + prompt commiteado + bootstrap)

**Objetivo:** el agente NUEVO que fusiona negocio + funcional + técnico en una pasada.
**Valor:** 1 pasada en vez de 3 → menor latencia y costo, desglose consistente.

**Archivos:**
- `Stacky Agents/backend/agents/incident.py` — NUEVO:

```python
from .base import BaseAgent


class IncidentAgent(BaseAgent):
    type = "incident"
    name = "Incident Analyst"
    icon = "🚑"
    description = "Incidencia multimodal → desglose unificado negocio+funcional+técnico listo para dev"
    inputs_hint = ["texto libre de la incidencia", "capturas de pantalla", "logs y archivos adjuntos"]
    outputs_hint = [
        "HTML con RESUMEN EJECUTIVO / CONTEXTO DE NEGOCIO / ANALISIS FUNCIONAL / ANALISIS TECNICO",
        "PASOS DE REPRODUCCION y CRITERIOS DE ACEPTACION",
        "ARCHIVOS Y MODULOS PROBABLES",
        "EPICA RELACIONADA con confianza y razón",
    ]
    default_blocks = ["incident-intake", "attachments-manifest", "epic-catalog"]

    def system_prompt(self) -> str:
        return (
            "Sos el Analista de Incidencias unificado: fusionás en UNA pasada las "
            "perspectivas del Agente de Negocio, el Analista Funcional y el Analista "
            "Técnico. Recibís una incidencia (texto libre + archivos adjuntos + "
            "catálogo de épicas abiertas) y devolvés SOLO un desglose HTML dev-ready "
            "con las secciones EXACTAS: RESUMEN EJECUTIVO, CONTEXTO DE NEGOCIO, "
            "ANALISIS FUNCIONAL, ANALISIS TECNICO, PASOS DE REPRODUCCION, CRITERIOS "
            "DE ACEPTACION, ARCHIVOS Y MODULOS PROBABLES, EPICA RELACIONADA "
            "(formato: 'EPICA: <id o ninguna> | CONFIANZA: <0-100> | RAZON: ...'), "
            "PRIORIDAD Y ESTIMACION. Sos preciso, no inventás: lo no verificable va "
            "como [PENDIENTE: ...]. PROHIBIDO narrar lo que vas a hacer: tu respuesta "
            "es el HTML y nada más."
        )
```

- `Stacky Agents/backend/agents/__init__.py` — import + entrada en `registry`
  (`agents/__init__.py:12-26`): `from .incident import IncidentAgent` +
  `IncidentAgent(),  # Plan 131 — analista unificado de incidencias`.
- `Stacky Agents/backend/agents/IncidentAnalyst.agent.md` — NUEVO template commiteado
  (mismo lugar tracked que `backend/agents/Developer.agent.md`). Contenido: frontmatter
  `name: IncidentAnalyst` + descripción + el system prompt de arriba EXTENDIDO con:
  cómo leer `<attachments-manifest>` (abrir imágenes por ruta absoluta si el runtime
  puede; si no, `[PENDIENTE: verificar captura <nombre>]`), cómo usar `<epic-catalog>`
  (elegir a lo sumo UNA épica; catálogo vacío ⇒ `EPICA: ninguna`; NUNCA inventar ids),
  el contrato HTML de §4.3 copiado verbatim, y la regla anti-narración. Estructura
  espejo de `Developer.agent.md` (leerlo antes de escribir).
- `Stacky Agents/backend/services/incident_context.py` — NUEVO, incluye:
  - `_AGENT_TEMPLATE_MD: str` — constante module-level con el CONTENIDO COMPLETO del
    `.agent.md` (fuente de verdad única; C10: en deploy frozen/PyInstaller el archivo
    del repo puede NO existir, la constante viaja siempre dentro del bundle).
  - `ensure_incident_agent_file() -> Path`: si
    `stacky_agents_dir() / "IncidentAnalyst.agent.md"` YA existe → NO tocar (el
    operador pudo editarlo). Si NO existe → intentar copiar desde
    `Path(__file__).resolve().parents[1] / "agents" / "IncidentAnalyst.agent.md"`;
    si ese archivo tampoco existe (frozen) → escribir `_AGENT_TEMPLATE_MD`.
    Importar `stacky_agents_dir` del MISMO módulo del que lo importa `config.py:10`
    (verificar con `grep stacky_agents_dir backend/runtime_paths.py` antes de escribir
    el import).
  - El archivo commiteado `backend/agents/IncidentAnalyst.agent.md` se escribe con el
    MISMO contenido de `_AGENT_TEMPLATE_MD` (espejo; el test 5 fuerza la sincronía).

**Tests PRIMERO** — `tests/test_plan131_incident_agent.py`:
1. `agents.get("incident")` devuelve instancia con `type == "incident"` y
   `system_prompt()` conteniendo `"EPICA RELACIONADA"` y `"PASOS DE REPRODUCCION"`.
2. `agents.list_agents()` incluye el describe del nuevo (no rompe el shape existente).
3. `ensure_incident_agent_file` con dir vacío (monkeypatch stacky_agents_dir → tmp) →
   crea el archivo con el contenido del template.
4. `ensure_incident_agent_file` con archivo preexistente editado → NO lo sobreescribe
   (contenido intacto byte a byte).
5. Sincronía C10: el archivo commiteado `backend/agents/IncidentAnalyst.agent.md` es
   byte-idéntico a `incident_context._AGENT_TEMPLATE_MD`, Y contiene los 9 headings
   de §4.3.
6. Fallback frozen (C10): con el archivo del repo inaccesible (monkeypatch de la ruta
   template → tmp inexistente), `ensure_incident_agent_file` escribe
   `_AGENT_TEMPLATE_MD` igual.

**Comando:** `... -m pytest tests\test_plan131_incident_agent.py -q`
**Criterio binario:** 6/6 verdes.
**Flag:** el agente solo es alcanzable vía `run-incident` (F4, gateado); su presencia en
el registry con flag OFF es inerte (igual que DebugAgent).
**Runtimes:** el `.agent.md` lo consumen los runtimes CLI (patrón
`vscode_agent_filename`, `api/agents.py:570-571`); `github_copilot` usa
`system_prompt()` de la clase — paridad por diseño. **Operador:** ninguno.

### F3 — Contexto: manifest de adjuntos + catálogo de épicas

**Objetivo:** empaquetar TODO el contexto necesario en el prompt (§4.2).
**Valor:** el agente decide con datos reales (archivos + épicas del tracker), no a ciegas.

**Archivos:**
- `Stacky Agents/backend/services/ado_provider.py` — **NUEVO método duck-typed (C2;
  NO tocar el Protocol del puerto ni `PORT_METHODS` — precedente de método
  extra-puerto: `mr_url`/`commit_url` en `gitlab_provider.py:179-195`):**

```python
_EPICS_WIQL = (
    "SELECT [System.Id] FROM WorkItems "
    "WHERE [System.TeamProject] = @project "
    "AND [System.WorkItemType] = 'Epic' "
    "ORDER BY [System.ChangedDate] DESC"
)

def fetch_epics(self, limit: int = 50) -> list[dict]:
    """Plan 131 — catálogo de épicas vía WIQL dedicado (fetch_open_items es stub, :53-64).

    Devuelve [{"id": int, "title": str, "state": str}] ya normalizado, excluyendo
    estados terminales. Nunca lanza distinto de lo que lance el cliente HTTP.
    """
    rows = self._client.fetch_open_work_items(wiql=_EPICS_WIQL)
    out: list[dict] = []
    for r in rows:
        f = r.get("fields") or {}
        state = str(f.get("System.State") or "")
        if state.strip().lower() in ("closed", "done", "removed"):
            continue
        out.append({"id": r.get("id"), "title": str(f.get("System.Title") or ""), "state": state})
        if len(out) >= limit:
            break
    return out
```

  (El shape de `rows` es el raw de ADO `_batch_get`, `ado_client.py:325-349`: dicts con
  `id` top-level y `fields={"System.Title", "System.State", ...}` — C12.)
- `Stacky Agents/backend/services/incident_context.py` — agregar:
  - `_INLINE_MAX_PER_FILE = 8_000`, `_INLINE_MAX_TOTAL = 40_000`.
  - `build_attachments_manifest(incident: dict) -> str` — formato EXACTO §4.2; lee los
    archivos `kind=="text"` con `errors="replace"`; imágenes/binarios solo metadata;
    rutas absolutas con `incidents_root() / incident["id"] / stored_name`.
  - `fetch_epic_catalog(provider, limit: int = 50) -> list[dict]` — estrategia EXACTA
    (v2, C2+C6+C12; todo el cuerpo dentro de UN `try/except Exception: return []`):
    1. `fe = getattr(provider, "fetch_epics", None)`; si `callable(fe)` →
       `catalog = fe(limit=limit)`; si no-vacío → devolverlo (ya viene normalizado
       del adapter ADO; camino PRINCIPAL en ADO — `provider.fetch_open_items` allí es
       stub que devuelve `[]` siempre, `ado_provider.py:53-64`).
    2. Fallback (GitLab y providers sin `fetch_epics`):
       `items = provider.fetch_open_items(TrackerQuery(state="open"))`; filtrar en
       este orden: (a) si el dict tiene `fields` →
       `it["fields"].get("System.WorkItemType") == "Epic"`; (b) si no →
       `any("epic" in str(l).lower() for l in it.get("labels", []))` (C6: el label
       real que Stacky crea en GitLab es `type::epic` vía `_type_label`,
       `gitlab_provider.py:43-44` — por eso substring, NO igualdad).
    3. Normalizar cada item a `{"id": int|str, "title": str, "state": str}`:
       `id = it.get("iid") or it.get("id")`;
       `title = it.get("title") or (it.get("fields") or {}).get("System.Title") or ""`;
       `state = it.get("state") or (it.get("fields") or {}).get("System.State") or ""`
       (C12: en el shape ADO raw, title/state viven bajo `fields`). Cap `limit`.
    4. Resultado vacío o CUALQUIER excepción → `[]` (degradación declarada: el agente
       dirá `EPICA: ninguna` y el operador puede override en el preview).
  - `build_epic_catalog_block(catalog: list[dict]) -> str` — formato EXACTO §4.2.
  - `build_incident_prompt(incident: dict, catalog: list[dict]) -> str` — concatena
    §4.2 en orden.

**Tests PRIMERO** — `tests/test_plan131_incident_context.py` (todo con tmp_path +
providers fake, CERO red):
1. manifest con 1 imagen + 1 log → contiene ruta absoluta de la imagen, inline del log,
   y la instrucción de degradación de imágenes.
2. log de 20k chars → truncado a 8k + línea `[TRUNCADO...]`; 6 archivos de texto de 8k
   → inline total ≤ 40k.
3. `fetch_epic_catalog` con provider fake que EXPONE `fetch_epics` → usa ese camino y
   NO llama `fetch_open_items` (espía); con provider fake SIN `fetch_epics` estilo
   GitLab (`labels=["type::epic"]`) → lo incluye (C6 substring); con provider que
   lanza → `[]`; con todo vacío → `[]`.
4. `build_epic_catalog_block([])` → contiene `EPICA: ninguna`.
5. `build_incident_prompt` → contiene el texto del operador verbatim + ambos bloques en
   orden.
6. `AdoTrackerProvider.fetch_epics` (C2): con
   `monkeypatch.setattr("services.ado_provider.build_ado_client", lambda project_name=None: FakeAdoClient())`
   donde el fake devuelve rows raw ADO (`{"id": 267, "fields": {"System.Title": "X",
   "System.State": "Doing", "System.WorkItemType": "Epic"}}` + uno en "Done") →
   normaliza a `{"id","title","state"}`, excluye el "Done" y respeta `limit`.

**Comando:** `... -m pytest tests\test_plan131_incident_context.py -q`
**Criterio binario:** 6/6 verdes + `tests\test_plan70_tracker_item_adapter.py` y
`tests\test_tracker_provider_conformance.py` siguen verdes (el método nuevo es aditivo;
si alguna tenía fallas preexistentes, re-demostrarlas idénticas).
**Flag:** módulo puro, solo invocado desde flujo gateado.
**Runtimes:** el manifest ES el mecanismo de paridad multimodal (§3.4). **Operador:** ninguno.

### F4 — Lanzamiento: `POST /api/agents/run-incident`

**Objetivo:** correr `IncidentAnalyst` sobre la incidencia en CUALQUIER runtime.
**Valor:** análisis con 1 click, reusando el harness completo (pool ticket, polling,
consola, telemetría, selector adaptativo).

**Archivos:**
- `Stacky Agents/backend/api/agents.py` — NUEVA ruta `@bp.post("/run-incident")`
  `def run_incident():` ESPEJO LÍNEA A LÍNEA de `run_brief` (`api/agents.py:564-660`)
  con estas diferencias EXACTAS y ninguna otra:
  1. Gate: `config.STACKY_INCIDENT_RESOLVER_ENABLED` OFF → 404 `feature_disabled`.
  2. Input: `incident_id` (requerido) en vez de `brief`;
     `incident = incident_store.get_incident(incident_id)` → None ⇒ 400
     `incident_not_found`; `incident["status"]` no en
     `("capturada", "analizada", "error")` ⇒ 400 `invalid_status`.
  3. Pool ticket: `ado_id=-8`, título `"Incident Pool Ticket"` (espejo del Brief Pool
     `ado_id=-1`, `api/agents.py:568`, get-or-create en `:708-718`). **PROHIBIDO otro
     sentinel (C3): el mapa de negativos OCUPADOS es** `-1` brief pool, `-2` agente
     DevOps (discriminador de identidad, `api/devops_agent.py:108,350`), `-3` doctor
     secciones, `-4` consola remota, `-5` análisis LLM local, `-6` PR review
     (`api/pr_review.py:36`), `-7` documenter. `-8` verificado LIBRE en HEAD
     (re-verificar con `grep -rn "= -8" backend --include=*.py` antes de implementar).
  4. `agent_type="incident"`; `vscode_agent_filename` auto = `"IncidentAnalyst.agent.md"`
     (espejo de `api/agents.py:570-571`), tras llamar
     `incident_context.ensure_incident_agent_file()`.
  5. El contenido que run_brief pasa como brief → acá
     `build_incident_prompt(incident, catalog)`. **Provider (C4 — `create_epic_from_brief`
     NO usa el puerto, publica ADO-directo vía `_publish_epic_to_ado`; NO hay helper que
     espejar ahí):** obtenerlo con la fábrica real
     `from services.tracker_provider import get_tracker_provider` →
     `provider = get_tracker_provider(project_name)` (`services/tracker_provider.py:105`),
     TODO dentro de try/except: cualquier excepción (TrackerConfigError, provider no
     configurado, etc.) → `catalog = []`, NUNCA 500; si el provider se obtuvo →
     `catalog = fetch_epic_catalog(provider)`.
  6. SIN validación de `work_item_type`, SIN preflight de intención, y SIN el bloque
     `_AUTOPUBLISH_RUNTIME` (`api/agents.py:595-608`): los 3 runtimes son válidos
     porque acá NADIE autopublica.
  7. `model`/`effort`/`runtime`/`project`: passthrough idéntico a run_brief.
  8. Al lanzar OK: `update_incident(incident_id, status="analizando", execution_id=<id>)`.
  9. Telemetría: `stacky_logger.info("incidents", "incident_analysis_started", ...)`.
  10. **(C14)** `Stacky Agents/backend/services/claude_code_cli_runner.py` — cambiar
      `_ONE_SHOT_ADO_IDS = frozenset({-1, -7})` (`:216`) a
      `frozenset({-1, -7, -8})` con comentario
      `# -8 = incident pool (Plan 131): análisis one-shot, nadie responde por consola`.
      Sin esto, en `claude_code_cli` el proceso queda esperando input y el run cuelga
      hasta el timeout (1800s) — mismo bug que tuvo el Documentador (`-7`, ver
      comentario `:207-215`).

**Tests PRIMERO** — `tests/test_plan131_run_incident.py` (monkeypatch del
lanzador/run_agent interno con fake que captura kwargs, patrón de los tests existentes
de run-brief — buscar `run-brief` en `tests/` y espejar el que exista):
1. flag OFF → 404.
2. incident inexistente → 400 `incident_not_found`.
3. feliz → 200 con execution_id; el prompt capturado contiene texto del operador +
   `<attachments-manifest>` + `<epic-catalog>`; agent_type `"incident"`;
   vscode_agent_filename `"IncidentAnalyst.agent.md"`.
4. status pasa a `analizando` con execution_id persistido.
5. runtime `codex_cli` y `github_copilot` → NO son rechazados (ausencia del guard
   autopublish).
6. provider roto (fake que lanza al pedir catálogo) → 200 igual (catálogo vacío).
7. (C14) `-8 in claude_code_cli_runner._ONE_SHOT_ADO_IDS` y `-1`/`-7` siguen adentro
   (espejo de `tests/test_documenter_autonomy.py:37-41`).

**Comando:** `... -m pytest tests\test_plan131_run_incident.py -q`
**Criterio binario:** 7/7 verdes + `tests\test_documenter_autonomy.py` sigue verde.
**Flag:** `STACKY_INCIDENT_RESOLVER_ENABLED`.
**Runtimes:** los 3 lanzan; imágenes según §3.4. **Operador:** 1 click (Analizar).

### F5 — Preview + Publish (Issue + parent + attachments)

**Objetivo:** extraer/validar el desglose, mostrarlo, y al confirmar publicar TODO.
**Valor:** el Issue queda dev-ready en el tracker, linkeado y con evidencia adjunta.

**Archivos:**
- `Stacky Agents/backend/api/tickets.py` — agregar (cerca de `_looks_like_epic`,
  `api/tickets.py:5983`):
  - `_INCIDENT_REQUIRED_SECTIONS` + `def _looks_like_incident(html: str | None) -> bool`
    + `def _parse_related_epic(html: str) -> dict` (reglas EXACTAS §4.3).
  - `@bp.get("/incident-preview")` — query `execution_id` + `incident_id`; obtener el
    output crudo de la ejecución EXACTAMENTE como lo hace `epic_payload_preview`
    (endpoint `GET /epic-preview`, `api/tickets.py:7061` — C11): con `session_scope()`,
    `run = _get_run_for_preview(execution_id, db=db)` (`api/tickets.py:7055`) →
    `output = run.output`; reusar `_extract_epic_html_raw` (`api/tickets.py:5873`);
    aplicar `_looks_like_incident`; OK ⇒ transición CONDICIONAL e idempotente (C8:
    es un GET — SOLO `if incident["status"] == "analizando":
    update_incident(incident_id, status="analizada")`; cualquier otro status se deja
    intacto) y devolver §4.4.
  - `@bp.post("/incidents/publish")` — flujo EXACTO:
    1. Gate flag → 404. `confirm is not True` → 400. Incidente con `tracker_id` → 409.
    2. Re-extraer html + re-validar `_looks_like_incident` (server-side, nunca confiar
       en el front) → si falla, 422.
    3. Resolver épica: `override_epic_id` presente (incluido null) manda; si ausente,
       `_parse_related_epic(html)["epic_id"]`.
    4. Provider del tracker activo (C4): `from services.tracker_provider import
       get_tracker_provider, TrackerItem, TrackerApiError, TrackerError` →
       `provider = get_tracker_provider(project_name)`. Si ESTO lanza → 502
       `tracker_error` (paso 5c). NO existe helper de provider en
       `create_epic_from_brief` (publica ADO-directo vía `_publish_epic_to_ado`) —
       NO intentar espejarlo.
    5. Construir `item` EXACTAMENTE con el contrato congelado de §4.4 (C1:
       `fields` DEBE incluir `System.Title` y `System.Description` duplicados —
       la rama WS1 de `AdoClient.create_work_item` ignora los posicionales) →
       `created = provider.create_item(item)`; si lanza `TrackerApiError` Y había
       parent_id → reintentar UNA vez sin parent (`epic_link_mode="none"` provisional)
       y luego best-effort `provider.post_comment(str(epic_id), <html con link al issue
       nuevo>)` → si el comment sale, `epic_link_mode="comment"`; si el create con
       parent salió a la primera → `"parent"`; sin épica → `"none"`.
    5b. Extracción de id/url del `created` (LITERAL — cubre ambos providers: ADO
       devuelve el raw del work item con `id` top-level; GitLab devuelve
       `_normalize_issue` con `id`/`iid`/`web_url`, `gitlab_provider.py:62-80`;
       para GitLab el id operable en la API es el `iid`):
       `tracker_id = str((created or {}).get("iid") or (created or {}).get("id") or "")`;
       si `tracker_id == ""` → tratar como fallo del paso 5c.
       `url = ""`; `try: url = provider.item_url(tracker_id) or "" except Exception: pass`;
       si `url == ""` → `url = (created or {}).get("web_url") or (created or {}).get("url") or ""`.
    5c. **Contrato de error terminal (C7):** si el create (o el retry sin parent)
       falla — `TrackerApiError` no-parent (p.ej. `work_item_type="Bug"` en proceso
       Basic de ADO, que no tiene Bug), `TrackerError`, `TrackerConfigError` o
       cualquier excepción — entonces: `update_incident(incident_id, status="error",
       error=str(exc))` SIN tracker_id (el incidente queda re-publicable), telemetría
       `incident_publish_failed`, y response 502
       `{ok:false, error:"tracker_error", message:str(exc)}`. PROHIBIDO escribir el
       doc F6 o marcar `publicada` en este camino.
    6. Attachments: por CADA archivo del incidente, `att = provider.upload_attachment(
       str(ruta_absoluta), stored_name)` + `provider.link_attachment(str(tracker_id),
       att)` dentro de try/except POR ARCHIVO; fallo → append a `warnings`
       (`"attachment_failed:<name>"`), NUNCA abortar.
    7. F6 (C13 — `incident_docs` se crea en la fase SIGUIENTE; este import va
       protegido para que F5 quede verde sin F6):
       `try: from services import incident_docs; doc_path =
       incident_docs.write_incident_doc(incident, title, html, related)
       except Exception: doc_path = None` (best-effort, §4.5).
    8. `update_incident(incident_id, status="publicada", tracker_id=..., tracker_url=...,
       epic_id=..., doc_path=...)` + telemetría `incident_published`.
    9. Response 201 §4.4.

**Tests PRIMERO** — `tests/test_plan131_incident_preview_publish.py` (FakeProvider
en-memoria que graba llamadas; CERO red):
1. `_looks_like_incident` True con el HTML completo §4.3; False con narración
   ("Voy a analizar la incidencia..."); False con solo 2 secciones.
2. `_parse_related_epic`: caso completo (267/85/razón), caso `ninguna`, caso sin
   sección (todos None), confianza 150 → clamp 100.
3. preview con output narrativo → `{ok:false, error:"incident_not_in_output"}`.
4. preview feliz → title del h1 + related_epic parseada + status `analizada`.
5. publish sin confirm → 400; con confirm string "true" → 400 (exactitud booleana).
6. publish feliz con épica → FakeProvider recibió TrackerItem con parent_id="267",
   labels incidencia, y `fields` conteniendo `System.Tags` **Y
   `System.Title == title` Y `System.Description == html` (guard C1 de la rama WS1)**;
   response `epic_link_mode=="parent"`.
7. publish con FakeProvider que lanza TrackerApiError en create con parent → segundo
   create sin parent + post_comment a la épica → `epic_link_mode=="comment"`.
8. `override_epic_id=null` → item sin parent, `epic_link_mode=="none"`.
9. attachments: 2 archivos, el 2º falla el upload → 1 linked + warning
   `attachment_failed:...`, publish igual 201.
10. re-publish del mismo incidente → 409 `already_published`.
11. flag OFF → 404 en ambos endpoints.
12. (C7) FakeProvider cuyo `create_item` lanza `TrackerApiError` SIEMPRE (con y sin
    parent) → response 502 `tracker_error`, incidente en `status=="error"` con
    `tracker_id is None` (re-publicable), y NO se escribió ningún doc.
13. (C8) preview por GET dos veces seguidas → misma respuesta; un incidente ya
    `publicada` NO retrocede a `analizada` por llamar al preview.

**Comando:** `... -m pytest tests\test_plan131_incident_preview_publish.py -q`
**Criterio binario:** 13/13 verdes.
**Flag:** `STACKY_INCIDENT_RESOLVER_ENABLED`.
**Runtimes:** publish es backend-puro → idéntico bajo los 3 (KPI-4).
**Operador:** 1 click (Publicar) + override opcional de épica.

### F6 — Doc del incidente + aristas en el grafo

**Objetivo:** materializar el incidente como nodo del grafo documental con aristas.
**Valor:** memoria institucional navegable; el grafo muestra incidencias ↔ código ↔ docs.

**Archivos:**
- `Stacky Agents/backend/services/incident_docs.py` — NUEVO. Símbolos EXACTOS:
  `INCIDENTS_DOC_DIRNAME = "incidencias"`, `INDEX_NAME = "INDICE_INCIDENCIAS.md"`,
  `_slugify(title: str) -> str`,
  `resolve_docs_root() -> Path | None` (§4.5: `STACKY_AGENTS_ROOT/docs` si existe, si
  no `data_dir()/incident_docs` con flag interno de "fuera del grafo"),
  `write_incident_doc(incident: dict, title: str, html: str, related: dict) -> str | None`
  (plantilla LITERAL §4.5; extrae las rutas de la sección ARCHIVOS Y MODULOS PROBABLES
  con `re.findall` sobre el texto plano de esa sección y las emite una por línea; append
  idempotente al índice; `invalidate_graph_cache()`; devuelve ruta absoluta como str;
  cualquier excepción → `None`).

**Tests PRIMERO** — `tests/test_plan131_incident_docs.py` (tmp_path, monkeypatch
`STACKY_AGENTS_ROOT`-fuente según cómo lo exponga `doc_indexer` — leerlo primero):
1. write feliz → archivo `INC-341_<slug>.md` con frontmatter completo + `[[INDICE_INCIDENCIAS]]`.
2. índice creado si falta; segunda escritura del MISMO incidente NO duplica la línea.
3. slug: título con acentos/símbolos → `[a-z0-9-]` cap 60.
4. sin docs root (dir inexistente) → escribe en fallback y la función devuelve la ruta.
5. `invalidate_graph_cache` invocada (monkeypatch espía).
6. INTEGRACIÓN grafo: armar tmp docs root con 1 doc dummy + escribir el doc del
   incidente → llamar `doc_graph.build_graph` (con los parámetros que sus tests
   existentes usan — leer `tests/test_plan109_*` y espejar el harness) → el nodo
   `INC-341...` existe y tiene ≥1 arista saliente (wikilink al índice) y ≥1 arista a
   código si el HTML tenía `backend/services/foo.py`.

**Comando:** `... -m pytest tests\test_plan131_incident_docs.py -q`
**Criterio binario:** 6/6 verdes (el caso 6 es el KPI-3).
**Flag:** solo se invoca desde publish (gateado).
**Runtimes:** N/A (filesystem local). **Operador:** ninguno.

### F7 — Frontend: botón + modal + cliente API

**Objetivo:** la superficie visible: cargar, analizar, revisar, publicar.
**Valor:** los 2 clicks del KPI-1.

**Archivos:**
- `Stacky Agents/frontend/src/incidents/incidentModel.ts` — NUEVO (lógica PURA
  testeable): tipos `IncidentDTO`, `IncidentPreviewDTO`, `IncidentStatusDTO`;
  `validateFiles(files: {name: string; size: number}[], status: IncidentStatusDTO)
  -> {ok: boolean; errors: string[]}` (espejo cliente de los límites §4.1, usando
  `status.allowed_extensions`/`max_files`/`max_file_mb`);
  `canAnalyze(text: string, files: unknown[]) -> boolean` (texto no vacío O ≥1 archivo);
  `summarizeRelatedEpic(preview: IncidentPreviewDTO) -> string` (ej.
  `"Épica 267 — confianza 85% — <razón>"` o `"Sin épica relacionada"`);
  **[ADICIÓN ARQUITECTO]** `pickResumableIncident(list: IncidentDTO[]) ->
  IncidentDTO | null` — la MÁS RECIENTE (por `created_at`) con
  `status ∈ ("analizando", "analizada")` y `execution_id` no-null y sin `tracker_id`;
  si no hay, `null`.
- `Stacky Agents/frontend/src/api/endpoints.ts` — agregar export `Incidents`:
  `status()`, `create(text: string, files: File[])` — LITERAL (verificado: el cliente
  `api.post` de `client.ts:85-86` fija `Content-Type: application/json`, NO sirve para
  multipart; `client.ts:65` exporta `apiBase`):
  `import { apiBase } from "./client";` →
  `fetch(`${apiBase}/api/incidents`, { method: "POST", body: formData })` SIN header
  `Content-Type` (el browser pone el boundary) —
  `list()` (GET `/api/incidents`, [ADICIÓN ARQUITECTO], con `api.get`),
  `get(id)`, `runAnalysis(payload: {incident_id, runtime?, model?, effort?, project?})`
  → POST `/api/agents/run-incident`, `preview(executionId, incidentId)`,
  `publish(payload: {incident_id, execution_id, confirm: true, override_epic_id?,
  work_item_type?})`.
- `Stacky Agents/frontend/src/components/IncidentResolverModal.tsx` + `.module.css` —
  NUEVO. Espejar la mecánica de `EpicFromBriefModal.tsx` (steps, polling
  `POLL_INTERVAL_MS = 2500` / `POLL_TIMEOUT_MS = 5*60*1000`, selector de runtime
  `AgentRuntimeSelector`, selector modelo/effort para claude, botón Stop):
  - Steps: `"intake" | "running" | "preview" | "publishing" | "done" | "error"`.
  - **[ADICIÓN ARQUITECTO] Reanudación:** al montar, `Incidents.list()` (best-effort,
    error ⇒ ignorar) + `pickResumableIncident(...)`; si devuelve una incidencia, banner
    no-modal arriba del intake: `"Tenés una incidencia en curso (<title || id>)"` con
    botón `Retomar` → setea `incidentId`/`executionId` desde la incidencia y salta a
    `running` (status `analizando`, re-engancha el polling existente) o directo a
    `preview` (status `analizada`, llama `Incidents.preview`). Cubre cierre accidental
    del modal y runs zombie sin trabajo extra del operador.
  - Intake: textarea (texto libre) + input file múltiple + drag&drop (`onDrop` en el
    contenedor) + thumbnails de imágenes (`URL.createObjectURL`) + lista de archivos
    con tamaño + validación `validateFiles` en vivo (errores en rojo, botón Analizar
    deshabilitado si `!canAnalyze(...)` o `!validateFiles(...).ok`).
  - Analizar: `Incidents.create` → `Incidents.runAnalysis` → poll
    `Executions.get(executionId)` hasta terminal (mismo criterio que
    EpicFromBriefModal) → `Incidents.preview`.
  - Preview: render del HTML (mismo mecanismo de render que use EpicFromBriefModal
    para su preview), card "Épica relacionada" con `summarizeRelatedEpic` + input
    numérico "Override épica (id)" + checkbox "Publicar sin épica"; checkbox de
    aprobación + botón "Publicar en el tracker" (deshabilitado sin checkbox).
  - Done: links clickeables a `tracker_url` y `doc_path` + `epic_link_mode` legible +
    warnings visibles si los hay.
- `Stacky Agents/frontend/src/pages/TicketBoard.tsx` — junto al botón/estado que abre
  `EpicFromBriefModal` (`TicketBoard.tsx:937-941` y su botón asociado): estado
  `incidentModalOpen` + botón `🚑 Resolver incidencia` renderizado SOLO si
  `Incidents.status().enabled` (fetch al montar, mismo patrón que cualquier fetch del
  board) + `{incidentModalOpen && <IncidentResolverModal onClose={...} />}`.

**Tests PRIMERO** — `Stacky Agents/frontend/src/incidents/incidentModel.test.ts`
(vitest puro, patrón de `src/docs/docGraphModel.test.ts`):
1. `validateFiles`: feliz; ext prohibida; >max_files; archivo >max_file_mb.
2. `canAnalyze`: solo texto OK; solo archivos OK; nada → false.
3. `summarizeRelatedEpic`: con épica, sin épica, sin confianza.
4. `pickResumableIncident`: lista vacía → null; elige la más reciente `analizando`;
   ignora `publicada`/con `tracker_id`/sin `execution_id` [ADICIÓN ARQUITECTO].

**Comandos:**
`cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"; npx vitest run src/incidents/incidentModel.test.ts`
`cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"; npx tsc --noEmit`
**Criterio binario:** vitest verde + `tsc --noEmit` con 0 errores.
**Flag:** botón invisible con flag OFF (status.enabled=false).
**Runtimes:** el selector de runtime del modal expone los 3 (mismo componente que
brief→épica). **Operador:** 2 clicks.

### F8 — No-regresión + cierre

**Objetivo:** demostrar que nada existente cambió.
**Comandos (todos deben quedar como estaban o verdes):**
1. `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; & ".venv\Scripts\python.exe" -m pytest tests\test_plan131_incident_flag.py tests\test_plan131_incident_store.py tests\test_plan131_incident_api.py tests\test_plan131_incident_agent.py tests\test_plan131_incident_context.py tests\test_plan131_run_incident.py tests\test_plan131_incident_preview_publish.py tests\test_plan131_incident_docs.py -q`
2. Suites vecinas de los archivos tocados (por archivo, regla de la casa):
   `... -m pytest tests\test_harness_flags.py tests\test_harness_flags_help.py tests\test_plan70_tracker_item_adapter.py tests\test_tracker_provider_conformance.py tests\test_epic_autopublish_backend.py -q`
   (incluye la suite de help por C5 y la de conformance por el método nuevo de F3;
   si alguna tenía fallas PREEXISTENTES, re-demostrarlas idénticas y declararlas).
3. `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"; npx tsc --noEmit` → 0 errores.
4. `git status` final: SOLO los archivos del plan staged; WIP ajeno intacto.

**Criterio binario:** 1-4 cumplidos. **Operador:** ninguno.

---

## 6. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| El agente devuelve narración en vez del HTML (patrón conocido del BusinessAgent) | Guard `_looks_like_incident` en preview Y publish + regla anti-narración en el prompt + mensaje de reintento en el modal (espejo `EPIC_NOT_IN_OUTPUT_MSG`, `EpicFromBriefModal.tsx:81-84`) |
| El agente inventa un id de épica que no existe | El catálogo inyectado es la ÚNICA fuente válida (prompt lo prohíbe); en publish, si ADO rechaza el parent → retry sin parent + comment fallback (`epic_link_mode`) — la publicación nunca falla POR EL LINK; fallos no-parent → 502 `tracker_error` con incidente re-publicable (C7) |
| ADO crea el work item sin título (rama WS1 de `create_work_item` ignora title/description con `fields` no-None) | Contrato §4.4 congelado: `System.Title`/`System.Description` duplicados dentro de `fields` + test F5.6 que lo asserta (C1) |
| Runtime sin visión "alucina" el contenido de una imagen | Instrucción explícita de declarar `[PENDIENTE: verificar captura <nombre>]` + el operador VE el preview antes de publicar (HITL) |
| Archivos maliciosos/gigantes | Allowlist §4.1 + límites duros + sanitización + anti-traversal en serving; sin zip/exe |
| Catálogo de épicas vacío (en ADO `fetch_open_items` es stub `[]` SIEMPRE — C2; GitLab free sin epics nativos) | Camino principal ADO = `fetch_epics()` WIQL dedicado (F3); GitLab = labels `type::epic` por substring (C6); si igual queda vacío → `[]` declarado + override manual del operador en el preview |
| Doc del incidente rompe la publicación | Escritura best-effort: excepción → `doc_path:null` + warning; el Issue ya está creado |
| Deploy frozen sin `docs/` | Fallback a `data_dir()/incident_docs` con warning "fuera del grafo" (declarado) |
| WIP ajeno en `tickets.py`/`agents.py`/`endpoints.ts` | Guardarraíl §3.9: staging por hunk, prohibido stash/reset, `git status` final |
| Run de incidente colgado 1800s en `claude_code_cli` (proceso esperando input que nunca llega) | C14: `-8` agregado a `_ONE_SHOT_ADO_IDS` (`claude_code_cli_runner.py:216`) + test F4.7 — precedente: bug real del Documenter `-7` |
| Colisión de numeración con el loop paralelo | Guardarraíl §3.10: verificar unicidad de `131_*` antes de implementar |

## 7. Fuera de scope (deliberado)

- **Modo directo sin preview** (autopublicar al terminar el análisis): posible fase
  futura tras validar calidad del desglose en uso real; hoy el guardarraíl HITL manda.
- Resolución AUTOMÁTICA de la incidencia (que el Developer agent la implemente solo):
  el desglose es PARA el dev; encadenar el fix es otro plan.
- OCR local de imágenes para runtimes sin visión (posible con Plan 106/127 IA local).
- Detección de incidencias duplicadas (similarity contra incidencias previas).
- Edición del HTML en el preview (v1: se publica lo generado o se re-analiza).
- Épicas de GitLab Premium como catálogo first-class (hoy: labels heurística + override).
- Webhook/inbox externo de incidencias (email → incidencia).

## 8. Glosario (para el modelo menor)

- **Runtime:** motor que ejecuta agentes: `claude_code_cli` (CLI de Claude), `codex_cli`
  (CLI de Codex), `github_copilot` (bridge HTTP texto). Registrados en
  `harness/capabilities.py:21-46`.
- **Provider / puerto tracker:** abstracción ADO/GitLab (`services/tracker_provider.py`);
  `TrackerItem` es el dataclass de creación; ADO = `services/ado_provider.py`, GitLab =
  `services/gitlab_provider.py`.
- **Épica (Epic):** work item padre en ADO (Basic: Epic > Issue); en GitLab, issue con
  label épica o Epic premium.
- **Pool ticket:** Ticket local sintético (ado_id negativo) que ancla ejecuciones sin
  ticket real (patrón run-brief, `api/agents.py:568`).
- **Grafo documental:** nodos = notas markdown indexadas por `doc_indexer`; aristas =
  links md, wikilinks `[[nombre]]` y referencias a código (`doc_graph.py:18-51`).
- **Wikilink:** `[[NOMBRE_DE_NOTA]]` — arista doc→doc resuelta por nombre de archivo.
- **HITL:** human-in-the-loop; acá = preview + confirm obligatorios.
- **Flag del arnés:** toggle en `services/harness_flags.py` + espejo en `config.py`,
  editable por UI (`HarnessFlagsPanel`).
- **Intake:** captura persistida de la incidencia (texto + archivos) previa al análisis.
- **data_dir:** carpeta de datos runtime (`runtime_paths.data_dir()`), fuera del repo.

## 9. Orden de implementación + DoD

**Orden:** F0 → F1 → F2 → F3 → F4 → F5 → F6 → F7 → F8 (cada fase deja verde la
anterior; F5 depende de F2-F4; F6 se integra dentro de F5 pero se testea aislada; F7 al
final porque consume todos los contratos).

**Definición de Hecho (DoD) global:**
1. Los 8 archivos de test nuevos (7 backend + 1 frontend) verdes con los comandos
   literales de cada fase.
2. `tsc --noEmit` 0 errores; suites vecinas sin regresión (o fallas preexistentes
   re-demostradas idénticas y declaradas).
3. Con flag OFF: cero cambio observable (status 200 enabled:false; resto 404; sin botón).
4. Con flag ON, flujo manual E2E: modal → texto + 1 png + 1 log → Analizar (cualquier
   runtime) → preview con secciones y épica → Publicar → Issue en tracker con parent o
   comment + 2 attachments + doc `INC-*.md` visible como nodo con aristas en la pestaña
   Grafo.
5. `git status` final limpio de WIP ajeno; commits con staging quirúrgico; sin push
   (manual del operador).
6. Actualizar el encabezado **Estado:** de este doc a IMPLEMENTADO al cerrar.
