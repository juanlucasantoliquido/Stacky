# Plan 166 — Ciclo completo de Incidencias: Issues visibles en Tickets, Agente Dev Resolutor, Visión de capturas y creación directa en lote

**Estado:** CRITICADO (v2) — 2026-07-17 · APROBADO-CON-CAMBIOS por `criticar-y-mejorar-plan`

## Versión: v1 -> v2 (crítica adversarial aplicada)

**CHANGELOG v1 -> v2:**
- **C1 (IMPORTANTE, resuelto):** F0 omitía el registro en `_CATEGORY_KEYS`
  (`harness_flags.py:325` lo exige literalmente o `test_every_registry_flag_is_categorized`
  rompe) y proponía un `group="global"` inventado. v2: los 6 keys van a la MISMA tupla
  de `_CATEGORY_KEYS` que ya contiene `STACKY_INCIDENT_RESOLVER_ENABLED`, y todos los
  `FlagSpec` usan `group="global"` (espejo verificado del flag hermano,
  `harness_flags.py:3308`).
- **C2 (IMPORTANTE, resuelto):** `_do_publish_incident` estaba subespecificado: el rango a
  mover está lleno de `return jsonify(...), NNN` y `jsonify` REQUIERE app context — el
  post-hook corre en el thread del runner SIN contexto y crashearía. v2 fija el contrato
  literal `(payload: dict, status: int)`, prohíbe `jsonify` dentro del núcleo y especifica
  la adaptación de `_incident_publish_terminal_error`.
- **C3 (IMPORTANTE, resuelto):** fallo de autopublish MUDO en modo lote (excepción no-tracker
  → solo `logger.warning` → la cola mostraba "analizando" para siempre, violando el plan
  135). v2: el `except` del hook marca `status="error"` en el store (best-effort) y la cola
  mapea también `analizada` y `capturada`; +1 caso de test.
- **C4 (IMPORTANTE, resuelto):** contrato del endpoint de visión ambiguo. Verificado:
  `LOCAL_LLM_ENDPOINT` es la URL COMPLETA de chat-completions
  (`copilot_bridge.py:257-261`, "ej. http://localhost:11434/v1/chat/completions").
  v2 declara el mismo contrato para `STACKY_INCIDENT_VISION_ENDPOINT` (FlagSpec + docstring)
  y reusa `LOCAL_LLM_TIMEOUT_SEC` como timeout default.
- **C5 (IMPORTANTE, resuelto):** F2 sin presupuesto (N imágenes × 120 s síncronos dentro del
  request de `run_incident`). v2: cap de tamaño por imagen (reusa `MAX_FILE_BYTES` del
  intake), máx 6 imágenes por incidente, presupuesto TOTAL 240 s; +1 caso de test.
- **C6 (IMPORTANTE, resuelto — directiva del operador):** los 2 agentes del ciclo quedaron
  "muy expertos": nueva sección §3bis con la ficha completa de cada uno (rol, entradas/
  salidas exactas, herramientas, modelo/runtime con paridad, criterios binarios), prompt
  experto LARGO del `IncidentDevAgent` (incluye el contrato ⚠️ BLOQUEADO para causas de
  datos/entorno — exactamente la hipótesis principal del insumo real
  `docs/incidencias/INC-_inc-prestamos-...md`: gap de datos en RPRES que ningún fix de
  código resuelve) y refuerzo ADITIVO del prompt del `IncidentAgent` para explotar el OCR
  (F2b).
- **C7 (MENOR, resuelto → elevado a [ADICIÓN ARQUITECTO]):** bug real verificado en el
  cierre del ciclo documental: `write_incident_doc` se llama con el `incident` VIEJO
  (`api/tickets.py:7538`) ANTES del update de `tracker_id` (`:7544`) → el doc y el índice
  quedan con `tracker_id:` vacío aun tras publicar (visible en el insumo real). v2 reordena
  en `_do_publish_incident` y agrega test.
- **C8 (MENOR, resuelto):** la cola del modal ya no usa un `setInterval` sin acotar
  (coherencia con el plan 156, latido único): 3000 ms, SOLO con modal abierto y ≥1 ítem no
  terminal, `clearInterval` en cleanup.
- **C9 (MENOR, resuelto):** vaguedades podadas: "grupo incidents o global" (decidido por C1),
  "junto a otros registros de hooks" ahora tiene ancla literal, `incidents_status` es `:14`,
  `_find_incident_by_execution` con dos alternativas → decidido `incident_store.find_by_execution`.
- **C10 (MENOR, resuelto):** los tests de endpoint de F3 ahora instruyen espejar los helpers
  existentes de `test_plan131_incident_preview_publish.py` (`_make_app`/`_patch_run`/mocks
  de provider) en vez de dejar el setup a inferencia.
- **[ADICIÓN ARQUITECTO] Cierre del ciclo documental:** ver C7 — tras publicar, el doc del
  incidente y `INDICE_INCIDENCIAS.md` quedan con el `tracker_id` real y `estado: publicada`
  (frontmatter refrescado), cerrando el ciclo captura→publicación→doc con trazabilidad.
  Cero trabajo del operador, agnóstico de runtime, backward-compatible.
- **Directivas del operador incorporadas:** (1) mínima fricción — F3 crea directo y en lote
  sin diálogos; (2) DOS ACTORES — el ciclo es cargador → resolutor, sin terceros roles ni
  triage (verificado: el plan no introduce ninguno); (3) agentes MUY expertos — §3bis.

> Este documento está redactado para que un **MODELO MENOR** (Haiku, Codex CLI o
> GitHub Copilot Pro) lo implemente **SIN inferir nada**. Los nombres de símbolos,
> rutas, literales de mensajes y comandos son **LITERALES**: prohibido desviarse de
> los nombres exactos, prohibido "mejorar" el alcance. Todo lo ambiguo ya fue decidido
> acá. Cada afirmación sobre código existente está anclada a `archivo:línea` **verificada**.
> Los comandos con `&&` se ejecutan en **Git Bash** (en PowerShell 5.1 `&&` es error de parser).

**Dependencias:** ninguna dura. Reusa: el Resolutor de Incidencias (Plan 131,
`STACKY_INCIDENT_RESOLVER_ENABLED`, `services/incident_store.py`,
`services/incident_context.py`, `api/incidents.py`, `api/tickets.py::publish_incident`,
`components/IncidentResolverModal.tsx`); el patrón de persistencia local de Épicas
(`api/tickets.py::_persist_epic_ticket` `:6391`) e Issues (`publish_issue_from_run` `:7013`);
el hook agnóstico de runtime `services/ticket_status.py::register_post_hook` `:307`; el
registro de agentes `agents/__init__.py::registry` `:13`; el patrón `DeveloperAgent`
(`agents/developer.py`); el cliente LLM local OpenAI-compatible
(`copilot_bridge.py::invoke_local_llm` `:241`); los flags del arnés (patrón triple).

**Ortogonal a:** Plan 160 (repair HTML + pegado de imágenes al modal — el pegado YA
existe: `IncidentResolverModal.tsx::handlePaste` `:127`; lo que ESTE plan agrega es
**procesar** esas imágenes). Plan 159 (catálogo de modelos) — no se toca.

---

## 1. Objetivo + KPI

El operador reporta cuatro fallas reales del ciclo de incidencias, hoy incompleto:

1. **La Issue publicada NO aparece en Tickets para resolverla.** El operador publicó su
   primera Issue vía el Resolutor, pero no la ve en el board. Causa raíz verificada:
   `api/tickets.py::publish_incident` (`:7396`) crea el work item en ADO y actualiza el
   `incident_store` (`:7544`) **pero nunca persiste un `Ticket` local** — a diferencia de
   las Épicas (`_persist_epic_ticket` `:6391`) y del path de Issues-desde-brief
   (`publish_issue_from_run` `:7013`). La Issue sólo aparecería tras el próximo sync
   completo de ADO, y aun así como huérfana fácil de pasar por alto.

2. **No existe un agente que resuelva la Issue.** El `IncidentAgent` (`agents/incident.py`)
   sólo **analiza** (produce el desglose HTML); no hay ningún agente que **tome esa Issue
   y la resuelva** en el repo. El operador pide un agente NUEVO "dev resolvedor de
   incidencias".

3. **Las capturas pegadas no se procesan.** Hoy el manifiesto
   (`incident_context.py::build_attachments_manifest` `:157`) lista las imágenes como
   rutas absolutas y sólo mete inline el contenido de archivos `kind == "text"`
   (`:181-200`); las imágenes quedan libradas a que el runtime las lea del disco
   (`:174-176`), lo que falla en runtimes sin visión (Codex/Copilot) y para rutas fuera
   del workspace del runtime. Resultado: la captura no aporta texto a la Issue.

4. **La creación pide confirmación y no permite lote.** `publish_incident` exige
   `confirm == True` (`:7408`) y el modal fuerza un paso preview + checkbox "Revisé el
   desglose y confirmo" (`IncidentResolverModal.tsx:430-433`). El operador quiere que la
   Issue **se cree directo, sin confirmación**, y **crear varias seguidas sin permisos**.

**KPI / impacto esperado:**
- **K1 — Visibilidad:** una Issue publicada por el Resolutor aparece en el board de Tickets
  en **≤ 1 s** (sin esperar sync de ADO), con badge ámbar "Issue" y botón de resolución.
  Medible: test `test_persist_incident_ticket.py` (la fila `Ticket` existe post-publish).
- **K2 — Resolución:** desde la Issue, un click lanza el **Dev Resolutor** que produce un
  comentario 🚀 con diffs/evidencia. Medible: `run-incident-dev` devuelve `execution_id`
  y el run corre en los 3 runtimes.
- **K3 — Visión:** una captura con texto legible aporta ese texto al desglose (sección
  inline `texto extraído de la captura`). Medible: `test_incident_vision.py` (mock del
  endpoint) inyecta el OCR en el manifiesto.
- **K4 — Cero fricción:** con auto-publish ON, capturar N incidencias seguidas produce N
  Issues publicadas **sin un solo diálogo de confirmación**. Medible: `publish_incident`
  publica sin `confirm` cuando el flag está ON; el modal no muestra el paso preview.

---

## 2. Por qué ahora / gap que cierra

El Plan 131 entregó intake + análisis + publish **con** gate humano; el Plan 160 sumó
repair de HTML y pegado de imágenes al modal. Pero el **ciclo de vida completo** de una
incidencia —*capturar → (ver la captura procesada) → publicar Issue → verla en Tickets →
resolverla con un agente*— tiene cuatro eslabones rotos, todos verificados arriba. Este
plan los cierra sin agregar carga al operador (salvo la excepción dura citada en F3) y
respetando los 3 runtimes.

---

## 3. Principios y guardarraíles (no negociables)

- **3 runtimes con paridad:** Codex CLI, Claude Code CLI, GitHub Copilot Pro. Cada ítem
  funciona en los 3 o degrada de forma **explícita** con fallback declarado. Nada atado a
  un runtime. (F2 desacopla la visión del runtime justamente para esto; F4 corre vía
  `agent_runner.run_agent`, agnóstico; F3 usa `register_post_hook`, agnóstico.)
- **Cero trabajo extra al operador:** todo invisible/automático u opt-in **default ON**,
  salvo **F3**, que dispara la **EXCEPCIÓN DURA #1 (bypass de revisión humana)**. Esa
  excepción se cita explícitamente y se acepta por **directiva explícita del operador
  (2026-07-17)**, con el mismo precedente ya aceptado *épica-desde-brief* (auto-publicación
  autónoma del backend). Kill-switch por UI en todos los flags.
- **Human-in-the-loop:** el operador se amplifica. F3 es la única autonomía nueva y es
  pedida por él; el resto NO agrega autonomía proactiva (el Dev Resolutor F4/F5 sólo actúa
  cuando el operador hace click).
- **Mono-operador sin auth real:** nada de RBAC/multiusuario.
- **No degradar** performance/seguridad/estabilidad/DX. Backward-compatible: con todos los
  flags nuevos OFF, el comportamiento es **byte-idéntico** al de hoy.

### Gotchas del repo que el implementador DEBE respetar (verificadas)

- **G1 — `config.config` vs módulo `config`:** en `api/tickets.py` y `api/incidents.py` el
  módulo importado suele ser `config`; la **instancia** de flags es `config.config`
  (`api/tickets.py:7401` usa `config.config.STACKY_INCIDENT_RESOLVER_ENABLED`). En
  `api/agents.py` en cambio se usa `config.STACKY_...` (ver `:888`). **Copiá el patrón del
  archivo que estás editando**, no mezcles.
- **G2 — Ratchet de tests:** todo `test_*.py` nuevo DEBE agregarse a `HARNESS_TEST_FILES`
  en **ambos** `backend/scripts/run_harness_tests.sh` (`:20`) y
  `backend/scripts/run_harness_tests.ps1` (`:394-401` es el bloque Plan 131) o un meta-test
  se pone rojo.
- **G3 — Aristas `requires=`:** cada flag con `requires=` DEBE tener su arista registrada
  en `backend/tests/test_harness_flags_requires.py` (mapa `:186`).
- **G4 — `_CURATED_DEFAULTS_ON`:** cada flag con `default=True` DEBE aparecer en el set
  `_CURATED_DEFAULTS_ON` de `backend/tests/test_harness_flags.py` (`:467`) o el meta-test
  `test_default_known_only_for_curated` (`:744`) se pone rojo.
- **G5 — venv y tests por archivo:** correr con `Stacky Agents/backend/.venv`, **por
  archivo** (nunca la suite completa; hay contaminación cross-run conocida). Frontend:
  vitest **por archivo**.
- **G6 — Ratchet UI cero inline-style:** los `.tsx` nuevos tienen alcance 0 en
  `uiDebtRatchet`; usá clases del `.module.css`, no `style={{}}`.
- **G7 (C1) — `_CATEGORY_KEYS` obligatorio:** toda flag nueva DEBE agregarse también al
  dict `_CATEGORY_KEYS` de `services/harness_flags.py` (nota literal en `:325`: "toda flag
  nueva debe agregarse también a _CATEGORY_KEYS (arriba) o el test
  `test_every_registry_flag_is_categorized` rompe CI a propósito"). Ancla: la tupla que ya
  contiene el literal `STACKY_INCIDENT_RESOLVER_ENABLED` (`:312`).
- **G8 (C2) — `jsonify` requiere app context:** el post-hook de F3 corre en el thread del
  agent runner SIN request/app context. PROHIBIDO `jsonify` (y todo acceso a `request`)
  dentro de `_do_publish_incident`; solo dicts y tuplas `(dict, int)`.

---

## 3bis. Los 2 agentes expertos del ciclo (directiva del operador 2026-07-17)

En una incidencia intervienen **DOS ACTORES**: el que la **CARGA** y el que la **RESUELVE**.
No hay terceros roles, triage ni aprobadores intermedios. El human-in-the-loop del lado
del resolutor se mantiene: el operador lanza al Dev Resolutor con un click y supervisa su
salida (el agente comenta con evidencia; NUNCA transiciona ni cierra la Issue solo).
Cada actor tiene UN agente experto a su servicio:

### 3bis.1 — Agente de INTAKE: `IncidentAgent` (existente, Plan 131 — este plan lo potencia)

| Dimensión | Especificación |
|---|---|
| Rol | Analista de Incidencias unificado (negocio + funcional + técnico en una pasada). Ya existe: `agents/incident.py:7` (`type="incident"`, `name="Incident Analyst"`). |
| Entradas exactas | Bloques `incident-intake` (texto libre del cargador), `attachments-manifest` (manifiesto con texto inline de adjuntos `kind=="text"` + **desde F2** el texto OCR de cada captura), `epic-catalog` (catálogo de épicas del proyecto). Ver `default_blocks` en `agents/incident.py:19`. |
| Salidas exactas | HTML puro con las secciones RESUMEN EJECUTIVO, CONTEXTO DE NEGOCIO, ANALISIS FUNCIONAL, ANALISIS TECNICO, PASOS DE REPRODUCCION, CRITERIOS DE ACEPTACION, ARCHIVOS Y MODULOS PROBABLES, EPICA RELACIONADA, PRIORIDAD Y ESTIMACION — el formato REAL ya en producción (ver insumo `docs/incidencias/INC-_inc-prestamos-...md`). Gate de forma: `_looks_like_incident` (`api/tickets.py:6142`); reintento automático: Plan 160 F0. |
| Herramientas | Lectura del repo del proyecto activo (runtime CLI) para anclar ARCHIVOS Y MODULOS PROBABLES a `archivo:línea` reales; PROHIBIDO modificar código. |
| Modelo/runtime | Los 3 runtimes con paridad (corre vía `agent_runner.run_agent`); la visión NO depende del runtime porque el OCR de F2 entra inline en el prompt (fallback declarado en F2). |
| Criterios binarios | (a) `_looks_like_incident(html) == True`; (b) si una imagen tiene `ocr_text`, el prompt contiene la sección `"Texto extraído de las capturas (visión)"` (test F2 caso 6); (c) NO le pide nada extra al cargador: normaliza con lo que hay y marca `[PENDIENTE]` solo lo estrictamente ilegible. |

**F2b — refuerzo experto ADITIVO del prompt (editar `agents/incident.py::system_prompt`):**
al final del string retornado, CONCATENAR (aditivo, sin tocar el texto existente — los
tests del Plan 131 validan el HTML de salida, no el prompt, pero no se reescribe nada):

```python
            " Si el contexto incluye la sección 'Texto extraído de las capturas (visión)', "
            "tratá ese texto como EVIDENCIA PRIMARIA de la incidencia: extraé de ahí "
            "mensajes de error, códigos, valores de pantalla y nombres de campos, citalos "
            "textualmente en ANALISIS FUNCIONAL/TECNICO y usalos para los PASOS DE "
            "REPRODUCCION. Nunca le pidas información adicional al cargador: normalizá con "
            "lo disponible, distinguí HECHOS (lo que se ve/lee) de HIPOTESIS (lo que "
            "inferís) marcando las hipótesis como tales, y dejá la incidencia lista para "
            "que un dev la resuelva sin volver a preguntar."
```

### 3bis.2 — Agente DEV RESOLUTOR: `IncidentDevAgent` (NUEVO — F4)

| Dimensión | Especificación |
|---|---|
| Rol | Dev senior del proyecto activo que TOMA una Issue de incidencia dev-ready y la RESUELVE en el repo, con supervisión del operador (lanzado on-click, F5). |
| Entradas exactas | El `Ticket` local de la Issue (`work_item_type` ∈ {"Issue","Bug"}): título + descripción HTML (el desglose completo del intake) + doc del incidente si existe (`incident.doc_path`) — vía `build_incident_dev_prompt` (F4). |
| Salidas exactas | Cambios de código en el repo + comentario final que empieza con `🚀` (contrato de secciones en el prompt de abajo) O, si la causa NO es de código, comentario que empieza con `⚠️ BLOQUEADO` (sin tocar código). NUNCA publica tickets ni transiciona la Issue. |
| Herramientas | Las del `DeveloperAgent` espejo: `['codebase','search','usages','problems','changes']` (frontmatter del `.agent.md`, F4). |
| Modelo/runtime | Los 3 runtimes con paridad vía `agent_runner.run_agent` (mismo camino que Developer); passthrough de `model_override`/`effort_override` idéntico a `run_incident`. |
| Criterios binarios | (a) `"incident_dev" in registry`; (b) endpoint `run-incident-dev` responde 202 con `execution_id`; (c) el system_prompt contiene los literales `"🚀"`, `"⚠️ BLOQUEADO"` y `"criterios de aceptación"` (tests F4). |

El prompt experto literal de este agente está en F4 (§4.4) — es NORMATIVO: se copia
carácter por carácter.

---

## 4. Fases

Orden por dependencia: **F0 → F1 → F2 → F3 → F4 → F5 → F6**.

---

### F0 — Flags del arnés (patrón triple) + config de visión

**Objetivo (1 frase):** registrar los 4 flags nuevos + 2 valores de config de visión con
el patrón triple, para que todas las fases queden protegidas y configurables por UI.

**Valor:** cada fase se puede apagar sin tocar código; el operador ve y controla todo desde
el panel del Arnés.

**Archivos a editar:**
- `Stacky Agents/backend/config.py`
- `Stacky Agents/backend/services/harness_flags.py`
- `Stacky Agents/backend/tests/test_harness_flags.py` (set `_CURATED_DEFAULTS_ON`)
- `Stacky Agents/backend/tests/test_harness_flags_requires.py` (aristas `requires`)

**Flags (nombres EXACTOS) y defaults:**

| Flag | Default | `requires=` | Excepción dura |
|---|---|---|---|
| `STACKY_INCIDENT_TICKET_PERSIST_ENABLED` | **ON** | `STACKY_INCIDENT_RESOLVER_ENABLED` | ninguna (sólo persiste espejo local) |
| `STACKY_INCIDENT_VISION_OCR_ENABLED` | **ON** | `STACKY_INCIDENT_RESOLVER_ENABLED` | ninguna (degrada exacto a hoy sin endpoint) |
| `STACKY_INCIDENT_AUTO_PUBLISH_ENABLED` | **ON** | `STACKY_INCIDENT_RESOLVER_ENABLED` | **#1 bypass de revisión humana** (aceptada por operador 2026-07-17) |
| `STACKY_INCIDENT_DEV_RESOLVER_ENABLED` | **ON** | (ninguno) | ninguna (sólo actúa on-click) |

**Valores de config de visión (type="str", no bool):**

| Key | Default | Uso |
|---|---|---|
| `STACKY_INCIDENT_VISION_ENDPOINT` | `""` | **URL COMPLETA de chat-completions** (C4 — mismo contrato que `LOCAL_LLM_ENDPOINT`, ej. `http://localhost:11434/v1/chat/completions`, ver `copilot_bridge.py:257-261`); si vacío usa `LOCAL_LLM_ENDPOINT` |
| `STACKY_INCIDENT_VISION_MODEL` | `""` | modelo de visión (ej. `llama3.2-vision`, `llava`); si vacío usa `LOCAL_LLM_MODEL` |

**Diff ilustrativo — `config.py`** (agregar después de
`STACKY_INCIDENT_RESOLVER_ENABLED`, `:950-952`):

```python
    # Plan 166 F1 — persistir Ticket local al publicar Issue de incidencia
    # (espejo de _persist_epic_ticket). Default ON: sólo crea un espejo local
    # idempotente; OFF revierte a "aparece recién tras sync de ADO".
    STACKY_INCIDENT_TICKET_PERSIST_ENABLED: bool = os.getenv(
        "STACKY_INCIDENT_TICKET_PERSIST_ENABLED", "true"
    ).lower() in ("1", "true", "yes")

    # Plan 166 F2 — OCR/visión de capturas → texto inline en el manifiesto.
    # Default ON con degradación EXACTA al comportamiento de hoy si no hay
    # endpoint/modelo de visión (marca [PENDIENTE] + adjunto ADO): por eso ON
    # es seguro y no dispara excepción dura.
    STACKY_INCIDENT_VISION_OCR_ENABLED: bool = os.getenv(
        "STACKY_INCIDENT_VISION_OCR_ENABLED", "true"
    ).lower() in ("1", "true", "yes")
    STACKY_INCIDENT_VISION_ENDPOINT: str = os.getenv("STACKY_INCIDENT_VISION_ENDPOINT", "")
    STACKY_INCIDENT_VISION_MODEL: str = os.getenv("STACKY_INCIDENT_VISION_MODEL", "")

    # Plan 166 F3 — auto-publicación de la Issue de incidencia SIN confirmación
    # humana, en lote. EXCEPCIÓN DURA #1 (bypass de revisión humana), aceptada
    # por directiva explícita del operador 2026-07-17 (precedente:
    # épica-desde-brief). Kill-switch por UI: OFF restaura el gate preview+confirm.
    STACKY_INCIDENT_AUTO_PUBLISH_ENABLED: bool = os.getenv(
        "STACKY_INCIDENT_AUTO_PUBLISH_ENABLED", "true"
    ).lower() in ("1", "true", "yes")

    # Plan 166 F4/F5 — Agente Dev Resolutor de Incidencias (toma una Issue y la
    # resuelve en el repo). Default ON: sólo se lanza cuando el operador hace
    # click en "Resolver con agente" (sin autonomía proactiva).
    STACKY_INCIDENT_DEV_RESOLVER_ENABLED: bool = os.getenv(
        "STACKY_INCIDENT_DEV_RESOLVER_ENABLED", "true"
    ).lower() in ("1", "true", "yes")
```

**Registro en `_CATEGORY_KEYS` (C1/G7 — OBLIGATORIO, o el meta-test rompe):** en
`services/harness_flags.py`, ubicá la tupla de `_CATEGORY_KEYS` que contiene el literal
`"STACKY_INCIDENT_RESOLVER_ENABLED"` (`:312`) y agregá inmediatamente después, dentro de
la MISMA tupla:

```python
        "STACKY_INCIDENT_TICKET_PERSIST_ENABLED",  # Plan 166 F1 — espejo local de la Issue
        "STACKY_INCIDENT_VISION_OCR_ENABLED",      # Plan 166 F2 — OCR de capturas
        "STACKY_INCIDENT_VISION_ENDPOINT",         # Plan 166 F2 — endpoint de visión
        "STACKY_INCIDENT_VISION_MODEL",            # Plan 166 F2 — modelo de visión
        "STACKY_INCIDENT_AUTO_PUBLISH_ENABLED",    # Plan 166 F3 — creación directa/lote
        "STACKY_INCIDENT_DEV_RESOLVER_ENABLED",    # Plan 166 F4/F5 — Dev Resolutor
```

**Diff ilustrativo — `harness_flags.py`** (agregar 4 `FlagSpec` bool + 2 `FlagSpec` str
inmediatamente DESPUÉS del `FlagSpec` de `STACKY_INCIDENT_RESOLVER_ENABLED` (`:3294-3311`);
usar `group="global"` — espejo VERIFICADO del flag hermano (`:3308`); NO inventar un grupo
nuevo (C1)):

```python
    FlagSpec(
        key="STACKY_INCIDENT_TICKET_PERSIST_ENABLED",
        type="bool", default=True,
        label="Persistir Issue de incidencia en Tickets",
        description="Al publicar una incidencia, crea el ticket local de la Issue al instante (no esperás al sync de ADO).",
        group="global", requires="STACKY_INCIDENT_RESOLVER_ENABLED",
    ),
    FlagSpec(
        key="STACKY_INCIDENT_VISION_OCR_ENABLED",
        type="bool", default=True,
        label="Procesar capturas (OCR/visión)",
        description="Extrae el texto de las capturas adjuntas y lo suma al desglose. Si no hay modelo de visión configurado, degrada a marcar la captura como pendiente.",
        group="global", requires="STACKY_INCIDENT_RESOLVER_ENABLED",
    ),
    FlagSpec(
        key="STACKY_INCIDENT_VISION_ENDPOINT", type="str", default="",
        label="Endpoint de visión (OpenAI-compatible)",
        description="URL COMPLETA de chat-completions del endpoint de visión (ej. http://localhost:11434/v1/chat/completions). Mismo contrato que el endpoint del modelo local del Arnés. Vacío = usar ese endpoint local.",
        group="global", requires="STACKY_INCIDENT_VISION_OCR_ENABLED",
    ),
    FlagSpec(
        key="STACKY_INCIDENT_VISION_MODEL", type="str", default="",
        label="Modelo de visión",
        description="Nombre del modelo de visión (ej. llama3.2-vision, llava). Vacío = usar el modelo local del Arnés.",
        group="global", requires="STACKY_INCIDENT_VISION_OCR_ENABLED",
    ),
    FlagSpec(
        key="STACKY_INCIDENT_AUTO_PUBLISH_ENABLED",
        type="bool", default=True,
        label="Crear incidencias directo (sin confirmar)",
        description="Publica la Issue apenas el análisis termina, sin pedir confirmación, y permite cargar varias seguidas. Apagalo para volver al paso de revisión manual.",
        group="global", requires="STACKY_INCIDENT_RESOLVER_ENABLED",
    ),
    FlagSpec(
        key="STACKY_INCIDENT_DEV_RESOLVER_ENABLED",
        type="bool", default=True,
        label="Agente Dev Resolutor de Incidencias",
        description="Habilita el botón 'Resolver con agente' en las Issues para que un agente dev analice el repo y proponga el fix.",
        group="global",
    ),
```

**Tests (TDD):** editar `backend/tests/test_harness_flags.py` — agregar al set
`_CURATED_DEFAULTS_ON` (`:467`) las 4 claves con `default=True`:
`STACKY_INCIDENT_TICKET_PERSIST_ENABLED`, `STACKY_INCIDENT_VISION_OCR_ENABLED`,
`STACKY_INCIDENT_AUTO_PUBLISH_ENABLED`, `STACKY_INCIDENT_DEV_RESOLVER_ENABLED`. **NO**
agregar las dos `type="str"` (no son bool, no van al set). Editar
`backend/tests/test_harness_flags_requires.py` (`:186`) — agregar aristas:
```python
    "STACKY_INCIDENT_TICKET_PERSIST_ENABLED": "STACKY_INCIDENT_RESOLVER_ENABLED",
    "STACKY_INCIDENT_VISION_OCR_ENABLED": "STACKY_INCIDENT_RESOLVER_ENABLED",
    "STACKY_INCIDENT_VISION_ENDPOINT": "STACKY_INCIDENT_VISION_OCR_ENABLED",
    "STACKY_INCIDENT_VISION_MODEL": "STACKY_INCIDENT_VISION_OCR_ENABLED",
    "STACKY_INCIDENT_AUTO_PUBLISH_ENABLED": "STACKY_INCIDENT_RESOLVER_ENABLED",
```

**Comando de verificación (Git Bash):**
```bash
cd "Stacky Agents/backend" && .venv/Scripts/python -m pytest tests/test_harness_flags.py tests/test_harness_flags_requires.py -q
```

**Criterio de aceptación BINARIO:** ambos archivos verdes (0 fallos) — incluye
`test_every_registry_flag_is_categorized` (verde SOLO si hiciste el paso `_CATEGORY_KEYS`
de arriba, C1/G7). El endpoint `GET /api/harness/flags` (existente) devuelve los 6 keys
nuevos.

**Impacto por runtime:** ninguno (sólo definiciones de flags). **Fallback:** N/A.
**Trabajo del operador:** ninguno.

---

### F1 — La Issue publicada aparece en Tickets al instante

**Objetivo (1 frase):** persistir un `Ticket` local `work_item_type="Issue"` en el mismo
`publish_incident`, espejando `_persist_epic_ticket`, para que la Issue sea visible y
accionable sin esperar el sync de ADO.

**Valor:** cierra el punto 1 del operador (K1).

**Archivos a editar:**
- `Stacky Agents/backend/api/tickets.py` (agregar `_persist_incident_ticket` + llamarla en
  `publish_incident`)

**Símbolos EXACTOS:**
- Nueva función: `_persist_incident_ticket(ado_id: int, title: str, description_html: str, url: str, project_name: str | None, work_item_type: str, parent_ado_id: int | None) -> None`
- Se llama desde `publish_incident` (`:7396`) justo **después** de obtener `tracker_id` y
  `url` con éxito (después del bloque `:7508-7520`) y **antes** de `update_incident`
  (`:7544`).

**Pseudocódigo — `_persist_incident_ticket`** (espejo EXACTO de `_persist_epic_ticket`
`:6391`, cambiando `work_item_type` y agregando `parent_ado_id`):

```python
def _persist_incident_ticket(ado_id, title, description_html, url, project_name,
                             work_item_type, parent_ado_id):
    """Persiste (idempotentemente) el ticket local de la Issue de incidencia creada
    en ADO, para que aparezca en el board sin esperar el sync. Plan 166 F1."""
    if not getattr(config.config, "STACKY_INCIDENT_TICKET_PERSIST_ENABLED", True):
        return
    try:
        with session_scope() as session:
            existing = session.query(Ticket).filter(Ticket.ado_id == ado_id).first()
            if existing is None:
                session.add(Ticket(
                    ado_id=ado_id, external_id=ado_id,
                    title=title, description=description_html,
                    work_item_type=work_item_type,          # "Issue" | "Bug"
                    project=project_name or "",
                    stacky_project_name=project_name,
                    ado_url=url,
                    parent_ado_id=parent_ado_id,             # epic_id si linkeó
                    ado_state="New",
                ))
    except Exception as exc:  # noqa: BLE001 — best-effort, nunca aborta el publish
        logger.warning("incident publish: no se pudo persistir ticket local ado_id=%s err=%s", ado_id, exc)
```

**Wiring en `publish_incident`** (insertar tras `:7520`, antes de attachments `:7524`):

```python
    # Plan 166 F1 — persistir el ticket local de la Issue al instante.
    try:
        _tracker_id_int = int(tracker_id)
    except (TypeError, ValueError):
        _tracker_id_int = None
    if _tracker_id_int is not None:
        _persist_incident_ticket(
            ado_id=_tracker_id_int, title=title, description_html=html, url=url,
            project_name=project_name, work_item_type=work_item_type,
            parent_ado_id=(epic_id if isinstance(epic_id, int) else None),
        )
```

**Nota (verificada):** el sync completo NO filtra por tipo — `_DEFAULT_WIQL`
(`ado_client.py:53`) selecciona todos los WorkItems del proyecto sin `WHERE` de tipo ni
estado, y `sync_tickets` (`ado_sync.py:102`) upsertea cualquier `work_item_type`. Por eso
el próximo sync **actualiza** (no purga) la Issue ya persistida: está en ADO, así que
`_purge_orphans` no la borra. El badge ámbar de "Issue" YA existe
(`frontend/src/utils/workItemTypeColor.ts:10`, `issue: "#F59E0B"`), así que la UI la
distingue sin cambios adicionales.

**Tests (TDD):** archivo nuevo `backend/tests/test_persist_incident_ticket.py`. Casos:
1. `test_publish_persists_local_issue_ticket`: mockeando el provider para devolver un
   `{"id": 999}`, tras `POST /api/tickets/incidents/publish` con la Issue publicable, existe
   una fila `Ticket` con `ado_id=999`, `work_item_type="Issue"`.
2. `test_persist_sets_parent_when_epic_linked`: con `override_epic_id=267`, el ticket local
   tiene `parent_ado_id=267`.
3. `test_persist_idempotent`: llamar `_persist_incident_ticket` dos veces con el mismo
   `ado_id` no duplica filas.
4. `test_persist_disabled_flag_noop`: con `STACKY_INCIDENT_TICKET_PERSIST_ENABLED=False`,
   no se crea fila local (comportamiento legacy).

Registrar el archivo en `HARNESS_TEST_FILES` (G2, ambos scripts).

**Comando (Git Bash):**
```bash
cd "Stacky Agents/backend" && .venv/Scripts/python -m pytest tests/test_persist_incident_ticket.py -q
```

**Criterio BINARIO:** 4 casos verdes. Manual (smoke): publicar una incidencia → la Issue
aparece en el board sin correr sync.

**Impacto por runtime:** ninguno (la persistencia es post-publish, agnóstica). **Fallback:**
flag OFF → comportamiento de hoy (aparece tras sync). **Trabajo del operador:** ninguno.

---

### F2 — Visión de capturas → texto inline en el desglose

**Objetivo (1 frase):** extraer texto de cada imagen adjunta con un modelo de visión
OpenAI-compatible ANTES del análisis y meterlo inline en el manifiesto, para que el
desglose lo aproveche en los 3 runtimes.

**Valor:** cierra el punto 3 (K3); desacopla la visión del runtime de análisis.

**Archivos a crear/editar:**
- CREAR `Stacky Agents/backend/services/incident_vision.py`
- EDITAR `Stacky Agents/backend/services/incident_context.py`
  (`build_attachments_manifest` `:157` incluye `ocr_text` inline)
- EDITAR `Stacky Agents/backend/api/agents.py` (`run_incident` `:877` llama al enricher
  antes de `build_incident_prompt` `:998`)
- EDITAR `Stacky Agents/backend/agents/incident.py` (**F2b** — refuerzo ADITIVO del
  `system_prompt`, texto literal en §3bis.1; se CONCATENA al final del string existente,
  sin tocar nada de lo que ya hay)

**Símbolos EXACTOS (nuevos en `incident_vision.py`):**
- `extract_text_from_image(image_path: Path, mime: str, *, endpoint: str, model: str, timeout_sec: int = 120, on_log=None) -> str | None`
  — el `timeout_sec` efectivo lo pasa el caller: `int(getattr(_cfg, "LOCAL_LLM_TIMEOUT_SEC", 120))`
  (C4 — mismo patrón que `copilot_bridge.py:265`; NO se inventa un timeout nuevo).
- `enrich_incident_with_ocr(incident_id: str) -> dict` — devuelve el incidente actualizado.
- Constantes de presupuesto (C5, literales): `_MAX_IMAGES_PER_INCIDENT = 6`,
  `_TOTAL_OCR_BUDGET_SEC = 240`. El tamaño por imagen ya está acotado por el intake
  (`incident_store.MAX_FILE_BYTES`, cap aplicado en `api/incidents.py:50-55`); NO hay que
  re-validarlo, solo documentarlo.
- constante `_VISION_INSTRUCTION` (user text).
- **Contrato del endpoint (C4):** `endpoint` es la URL COMPLETA de chat-completions
  (mismo contrato que `LOCAL_LLM_ENDPOINT`, `copilot_bridge.py:257-261`); se postea
  directo, sin concatenar paths.

**Pseudocódigo — `extract_text_from_image`** (formato de visión OpenAI EXACTO; Ollama
llava / llama3.2-vision, LM Studio y OpenAI lo aceptan):

```python
import base64, requests
from pathlib import Path

_VISION_INSTRUCTION = (
    "Transcribí TODO el texto visible en esta captura de una incidencia de software "
    "(mensajes de error, stack traces, valores de pantalla, nombres de campos). Después, "
    "en una línea, describí brevemente qué muestra. NO inventes: si algo no se lee, "
    "escribí [ilegible]. Respondé sólo la transcripción + la descripción, sin preámbulo."
)

def extract_text_from_image(image_path, mime, *, endpoint, model, timeout_sec=120, on_log=None):
    try:
        raw = Path(image_path).read_bytes()
    except OSError:
        return None
    b64 = base64.b64encode(raw).decode("ascii")
    data_url = f"data:{mime or 'image/png'};base64,{b64}"
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": [
                {"type": "text", "text": _VISION_INSTRUCTION},
                {"type": "image_url", "image_url": {"url": data_url}},
            ]},
        ],
        "stream": False,
    }
    try:
        resp = requests.post(endpoint, headers={"Content-Type": "application/json"},
                             json=payload, timeout=timeout_sec)
        if resp.status_code != 200:
            return None
        data = resp.json()
        text = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        text = text.strip()
        return text or None
    except Exception:  # noqa: BLE001 — cualquier fallo → None (degradación declarada)
        return None
```

**Pseudocódigo — `enrich_incident_with_ocr`:**

```python
def enrich_incident_with_ocr(incident_id):
    from config import config as _cfg
    from services import incident_store
    incident = incident_store.get_incident(incident_id)
    if incident is None:
        return {}
    if not getattr(_cfg, "STACKY_INCIDENT_VISION_OCR_ENABLED", True):
        return incident
    endpoint = (_cfg.STACKY_INCIDENT_VISION_ENDPOINT or _cfg.LOCAL_LLM_ENDPOINT or "").strip()
    model = (_cfg.STACKY_INCIDENT_VISION_MODEL or _cfg.LOCAL_LLM_MODEL or "").strip()
    if not endpoint or not model:
        return incident  # sin modelo de visión → degradación exacta a hoy
    files = incident.get("files") or []
    incident_dir = incident_store.incidents_root() / incident_id
    timeout_sec = int(getattr(_cfg, "LOCAL_LLM_TIMEOUT_SEC", 120))  # C4
    changed = False
    processed = 0
    import time as _time
    started = _time.monotonic()
    for f in files:
        if f.get("kind") != "image" or f.get("ocr_text"):
            continue
        # C5 — presupuesto: máx _MAX_IMAGES_PER_INCIDENT imágenes y
        # _TOTAL_OCR_BUDGET_SEC segundos en total; lo que no entra queda sin
        # ocr_text (degradación declarada: manifiesto como hoy, [PENDIENTE]).
        if processed >= _MAX_IMAGES_PER_INCIDENT:
            break
        if _time.monotonic() - started > _TOTAL_OCR_BUDGET_SEC:
            break
        mime = _mime_for_ext(f.get("ext", ""))   # ".png"->"image/png", etc.
        text = extract_text_from_image(incident_dir / f["stored_name"], mime,
                                       endpoint=endpoint, model=model,
                                       timeout_sec=timeout_sec)
        processed += 1
        if text:
            f["ocr_text"] = text
            changed = True
    if changed:
        incident_store.update_incident(incident_id, files=files)
    return incident_store.get_incident(incident_id) or incident
```

`_mime_for_ext`: mapa `{".png":"image/png",".jpg":"image/jpeg",".jpeg":"image/jpeg",".gif":"image/gif",".webp":"image/webp",".bmp":"image/bmp"}`, default `"image/png"`.

**Edición — `incident_context.py::build_attachments_manifest`** (`:181-200`): tras el
bloque de archivos de texto, agregar un bloque análogo para las imágenes que tengan
`ocr_text`:

```python
    image_files = [f for f in files if f.get("kind") == "image" and f.get("ocr_text")]
    if image_files:
        lines.append("")
        lines.append("--- Texto extraído de las capturas (visión) ---")
        for f in image_files:
            lines.append(f"### {f['stored_name']} (texto extraído de la captura)")
            lines.append(str(f["ocr_text"])[:_INLINE_MAX_PER_FILE])
```

**Wiring — `api/agents.py::run_incident`** (insertar entre `:997` y `:998`, es decir antes
de `prompt = incident_context.build_incident_prompt(...)`):

```python
    # Plan 166 F2 — OCR/visión de capturas ANTES de armar el prompt (agnóstico
    # del runtime de análisis; el texto entra inline para los 3 runtimes).
    if config.STACKY_INCIDENT_VISION_OCR_ENABLED:
        try:
            from services import incident_vision
            incident = incident_vision.enrich_incident_with_ocr(incident_id) or incident
        except Exception as exc:  # noqa: BLE001 — visión es best-effort, nunca 500
            logger.info("run_incident: OCR de capturas no disponible (%s)", exc)
```

(Recordar: `run_incident` usa `config.STACKY_...` — patrón de `api/agents.py`, G1.)

**Tests (TDD):** archivo nuevo `backend/tests/test_incident_vision.py`. Casos:
1. `test_extract_returns_text_on_200`: `monkeypatch` de `requests.post` → 200 con
   `{"choices":[{"message":{"content":"ERROR 500 en login"}}]}` → devuelve `"ERROR 500 en login"`.
2. `test_extract_returns_none_on_error`: post lanza `ConnectionError` → `None`.
3. `test_extract_returns_none_on_non_200`: status 404 → `None`.
4. `test_enrich_sets_ocr_text_on_image_files`: incidente con una imagen; mock de
   `extract_text_from_image` → texto; tras `enrich_incident_with_ocr`, el archivo imagen
   tiene `ocr_text` y `get_incident` lo persiste.
5. `test_enrich_noop_without_endpoint`: sin endpoint/modelo → el archivo NO tiene `ocr_text`
   (degradación).
6. `test_manifest_includes_ocr_text`: un incidente con `ocr_text` en una imagen →
   `build_attachments_manifest` contiene `"texto extraído de la captura"` y el texto.
7. `test_enrich_respects_image_cap` (C5): incidente con 8 imágenes; mock de
   `extract_text_from_image` que cuenta llamadas → se llama exactamente
   `_MAX_IMAGES_PER_INCIDENT` (6) veces.
8. `test_incident_prompt_mentions_vision_section` (F2b): `IncidentAgent().system_prompt()`
   contiene el literal `"Texto extraído de las capturas (visión)"`.

Registrar en `HARNESS_TEST_FILES` (G2).

**Comando (Git Bash):**
```bash
cd "Stacky Agents/backend" && .venv/Scripts/python -m pytest tests/test_incident_vision.py -q
```

**Criterio BINARIO:** 8 casos verdes.

**Impacto por runtime:**
- **Claude Code CLI / Codex CLI / GitHub Copilot Pro:** idénticos — todos reciben el texto
  del OCR **inline** en el prompt, sin depender de la capacidad de visión del runtime.
- **Fallback (los 3):** sin endpoint/modelo de visión configurado, o si el OCR falla, el
  manifiesto queda como hoy (ruta + instrucción `[PENDIENTE: verificar captura]` `:174-178`)
  y la imagen sigue subiéndose como adjunto ADO en el publish (`tickets.py:7524-7531`).

**Trabajo del operador:** ninguno para el default (degrada solo). Opcional: configurar un
endpoint/modelo de visión en el panel del Arnés para activar la extracción real.

---

### F3 — Creación directa y en lote, sin confirmación

**Objetivo (1 frase):** con `STACKY_INCIDENT_AUTO_PUBLISH_ENABLED` ON, publicar la Issue
automáticamente al terminar el análisis (server-side, agnóstico de runtime) y permitir
cargar varias incidencias seguidas sin ningún diálogo.

**Valor:** cierra el punto 4 (K4). **EXCEPCIÓN DURA #1 (bypass de revisión humana)** — citada
y aceptada por directiva explícita del operador 2026-07-17, precedente épica-desde-brief.

**Archivos a crear/editar:**
- EDITAR `Stacky Agents/backend/api/tickets.py`:
  - `publish_incident` (`:7396`) — relajar el gate `confirm` cuando el flag está ON.
  - extraer el núcleo de publicación a `_do_publish_incident(incident_id, execution_id, *, work_item_type="Issue", override_epic_id=_UNSET) -> dict` reutilizable.
- CREAR `Stacky Agents/backend/services/incident_autopublish.py` (post-hook agnóstico).
- EDITAR `Stacky Agents/backend/app.py` — registrar el post-hook al crear la app.
- EDITAR `Stacky Agents/backend/services/incident_store.py` — (a) `create_incident` acepta
  y guarda `auto_publish` (bool); (b) NUEVA `find_by_execution(execution_id)` (ver 4.3.3).
  Los campos de resultado (`tracker_id`, `tracker_url`, `execution_id`, `status`) ya
  existen — no se agregan.
- EDITAR `Stacky Agents/backend/api/incidents.py` — `create_incident_endpoint` acepta
  `auto_publish` del form y lo pasa al store.
- EDITAR frontend: `IncidentResolverModal.tsx`, `incidents/incidentQueue.ts` (NUEVO, modelo
  puro), `api/endpoints.ts`.

**4.3.1 — Relajar el gate `confirm` (`publish_incident`):**

Reemplazar el bloque `:7407-7413` por:

```python
    body = _body_json()
    from config import config as _cfg   # G1: instancia de flags
    auto_ok = bool(getattr(_cfg, "STACKY_INCIDENT_AUTO_PUBLISH_ENABLED", False))
    confirm = body.get("confirm")
    if confirm is not True and not auto_ok:
        return jsonify({
            "ok": False, "error": "confirmation_required",
            "message": "Debes enviar confirm:true para publicar (human-in-the-loop).",
        }), 400
```

Con el flag ON, la ausencia de `confirm` ya no bloquea (el flag ES la autorización
permanente). Con el flag OFF, el contrato legacy se preserva byte-idéntico.

**4.3.2 — Núcleo reutilizable `_do_publish_incident` (contrato EXACTO, C2/G8):** mover el
cuerpo actual de `publish_incident` (`:7415-7568`, desde la resolución del incidente hasta
el `return jsonify(...201)`) a `_do_publish_incident(incident_id, execution_id, *,
work_item_type="Issue", override_epic_id=_UNSET) -> tuple[dict, int]`. Reglas literales:

- **PROHIBIDO `jsonify` y todo acceso a `request` dentro del núcleo** (G8): el post-hook lo
  invoca desde el thread del agent runner SIN app/request context; `jsonify` ahí lanza
  `RuntimeError: Working outside of application context`.
- Cada `return jsonify(X), N` del rango movido se convierte en `return X, N` (dict crudo +
  status HTTP). `publish_incident` queda como wrapper HTTP: valida flag/confirm, lee el
  body (`_body_json()` se queda en el wrapper), llama al núcleo y hace
  `payload, status = _do_publish_incident(...); return jsonify(payload), status`.
- `_incident_publish_terminal_error` (`:7389`, marca `status="error"` en el store y
  devuelve `jsonify(...), 502`): correr `grep -n "_incident_publish_terminal_error"
  api/tickets.py` — si SOLO se llama dentro del rango movido, cambiar su retorno a
  `(dict, int)` (sin jsonify); si tiene otros callers, crear la variante
  `_incident_publish_terminal_error_payload(...) -> tuple[dict, int]` y que la vieja la
  envuelva con jsonify.
- El núcleo incluye la llamada a `_persist_incident_ticket` de F1.
- **[ADICIÓN ARQUITECTO] Cierre del ciclo documental (C7 — bug real verificado):** hoy
  `write_incident_doc` se llama con el dict `incident` VIEJO (`:7538`) ANTES del
  `update_incident(status="publicada", tracker_id=..., ...)` (`:7544`), así que el doc de
  `docs/incidencias/` y su línea en `INDICE_INCIDENCIAS.md` quedan con `tracker_id:` vacío
  y `estado` viejo aun después de publicar (verificable en el insumo real
  `INC-_inc-prestamos-...md`, frontmatter `tracker_id:` vacío). Dentro del núcleo,
  REORDENAR: (1) `update_incident(status="publicada", tracker_id=tracker_id,
  tracker_url=url, epic_id=epic_id, title=title)` PRIMERO (sin `doc_path`); (2)
  `incident = incident_store.get_incident(incident_id)` (refrescado); (3)
  `doc_path = incident_docs.write_incident_doc(incident, title, html, related)`
  (best-effort, mismo try/except de hoy — la escritura es idempotente por marker,
  `incident_docs.py:62`); (4) `update_incident(incident_id, doc_path=doc_path)` si
  `doc_path` no es None. Resultado: el doc y el índice nacen con el tracker real y
  `estado: publicada`. Cero trabajo del operador, agnóstico de runtime,
  backward-compatible (con flag OFF el orden nuevo es igual de válido).

**4.3.3 — Post-hook agnóstico (`incident_autopublish.py`):**

```python
"""Plan 166 F3 — auto-publica la Issue de una incidencia al terminar el análisis,
sin confirmación humana. Agnóstico de runtime (corre en el post-hook de
ticket_status). EXCEPCIÓN DURA #1, aceptada por directiva del operador."""
import logging
logger = logging.getLogger("stacky.services.incident_autopublish")

def maybe_autopublish_incident(*, ticket_id, execution_id, final_status, agent_type, error=None, **_):
    from config import config as _cfg
    if not getattr(_cfg, "STACKY_INCIDENT_AUTO_PUBLISH_ENABLED", False):
        return
    if agent_type != "incident" or final_status != "completed":
        return
    from services import incident_store
    # localizar el incidente por execution_id (el store lo guardó al lanzar el
    # análisis — VERIFICADO: api/agents.py:1044 hace
    # update_incident(incident_id, status="analizando", execution_id=execution_id))
    incident = incident_store.find_by_execution(execution_id)
    if incident is None or not incident.get("auto_publish"):
        return
    if incident.get("tracker_id"):
        return  # ya publicada (idempotente)
    try:
        from api.tickets import _do_publish_incident
        payload, status = _do_publish_incident(
            incident_id=incident["id"], execution_id=execution_id,
        )
        if status >= 400:
            # Los errores terminales de tracker YA marcan status="error" en el
            # store (vía _incident_publish_terminal_error). Otros payloads de
            # error (p.ej. incident_not_in_output 422) NO — marcarlo acá para
            # que la cola del modal lo muestre (C3, plan 135: cero errores mudos).
            if (incident_store.get_incident(incident["id"]) or {}).get("status") != "error":
                incident_store.update_incident(
                    incident["id"], status="error",
                    error=str(payload.get("error") or f"http_{status}"),
                )
            logger.warning("autopublish incidencia execution=%s status=%s payload=%s",
                           execution_id, status, payload.get("error"))
    except Exception as exc:  # noqa: BLE001 — C3: el fallo NUNCA queda mudo
        logger.warning("autopublish incidencia execution=%s falló: %s", execution_id, exc)
        try:
            incident_store.update_incident(incident["id"], status="error", error=str(exc))
        except Exception:  # noqa: BLE001 — best-effort final
            pass

def register(register_post_hook):
    register_post_hook(maybe_autopublish_incident)
```

**`incident_store.find_by_execution(execution_id: int) -> dict | None` (NUEVA — decisión
tomada, C9, sin alternativas):** en `services/incident_store.py`, agregar una función que
recorre el ledger (`list_incidents()`), encuentra la entrada cuyo `execution_id` coincide
y devuelve `get_incident(id)` completo, o `None`. O(n) sobre el ledger; suficiente
(mono-operador).

**Registro en `app.py`** (dentro de `create_app`; ancla literal (C9): buscá con
`grep -n "register_post_hook" backend/app.py` el registro de hooks existente y agregá el
bloque inmediatamente DESPUÉS de ese registro; si el grep no da hits dentro de
`create_app`, agregalo justo ANTES del `return app` final):

```python
    from services import ticket_status, incident_autopublish
    incident_autopublish.register(ticket_status.register_post_hook)
```

**4.3.4 — `auto_publish` en el intake:** `create_incident` (`incident_store.py:106`)
acepta `auto_publish: bool = False` y lo guarda en el dict del incidente (`:155-170`).
`api/incidents.py::create_incident_endpoint` (`:44`) lee `request.form.get("auto_publish")`
(string `"true"`/`"false"`) y lo pasa. `Incidents.create` (frontend `endpoints.ts:4160`)
agrega `formData.append("auto_publish", String(autoPublish))`.

**4.3.5 — Modal en modo lote (frontend):**

- CREAR `frontend/src/incidents/incidentQueue.ts` — **modelo puro y testeable** (respeta el
  gap RTL/jsdom: la lógica va en un reducer puro, no en el componente):
  ```ts
  export type QueueItemStatus = "capturando" | "analizando" | "publicada" | "error";
  export interface QueueItem { id: string; title: string; status: QueueItemStatus;
                               trackerId?: string; url?: string; error?: string; }
  export function upsertQueueItem(items: QueueItem[], next: QueueItem): QueueItem[] { /* reemplaza por id o agrega */ }
  export function queueSummary(items: QueueItem[]): { total: number; publicadas: number; errores: number } { /* … */ }
  export function mapStoreStatus(status: string | null | undefined): QueueItemStatus {
    /* mapa TOTAL (C3): "capturada"->"capturando"; "analizando"|"analizada"->"analizando";
       "publicada"->"publicada"; "error" y cualquier otro/null -> "error" */ }
  ```
- `IncidentResolverModal.tsx`:
  - Leer `Incidents.status()` (ya trae `enabled`); agregar al DTO de status el campo
    `auto_publish_enabled` (backend `incidents_status` `:14` lo expone leyendo el flag,
    mismo patrón `bool(_cfg.STACKY_...)` de `:18`).
  - Cuando `auto_publish_enabled` es **true**: el botón "▶ Analizar" (`:377`) pasa a
    **"➕ Crear incidencia"**. `handleAnalyze` (`:151`) llama
    `Incidents.create(text, files, /*autoPublish*/ true)` → `Incidents.runAnalysis(...)`,
    agrega el ítem a la cola (`upsertQueueItem`, estado `"analizando"`), **limpia el form**
    (`setText("")`, `setFiles([])`) y **queda en `step="intake"`** para la siguiente. NO
    pasa por `preview`/`approved`. La cola se refresca vía `Incidents.list()` mapeando cada
    incidente a `QueueItem` con `mapStoreStatus` (función pura en `incidentQueue.ts`, mapa
    TOTAL de los 5 estados reales del store — C3/C9): `capturada`→"capturando",
    `analizando`→"analizando", `analizada`→"analizando" (aún sin publicar por el hook),
    `publicada`→"publicada", `error`→"error"; cualquier otro string→"error".
    **Polling acotado (C8, coherente con el plan 156 del latido único):** `setInterval` de
    **3000 ms**, activo SOLO mientras (a) el modal está abierto, (b) `auto_publish_enabled`
    es true y (c) hay ≥1 `QueueItem` en estado no-terminal ("capturando"/"analizando");
    `clearInterval` en el cleanup del efecto y al no cumplirse (c). Con la cola vacía o
    todo terminal: CERO requests.
  - Cuando `auto_publish_enabled` es **false**: comportamiento actual intacto
    (preview + checkbox + publish con `confirm:true`).
  - Render de la cola: una lista `<ul className={styles.queueList}>` con cada `QueueItem`
    (título, estado, y link al tracker cuando `publicada`). Usar clases del `.module.css`
    (G6, nada de `style={{}}`).

**Tests (TDD):**
- Backend nuevo `backend/tests/test_incident_autopublish.py`:
  1. `test_autopublish_publishes_when_flag_on_and_auto_flag_set`: post-hook con
     `agent_type="incident"`, `final_status="completed"`, incidente con `auto_publish=True`
     y salida publicable → llama `_do_publish_incident` (mock) una vez.
  2. `test_autopublish_skips_when_flag_off`: flag global OFF → no publica.
  3. `test_autopublish_skips_when_incident_not_auto`: `auto_publish=False` → no publica.
  4. `test_autopublish_idempotent_when_already_published`: `tracker_id` ya seteado → no
     republica.
  5. `test_publish_endpoint_allows_no_confirm_when_flag_on`: `POST /incidents/publish` sin
     `confirm` y flag ON → 201 (no 400).
  6. `test_publish_endpoint_requires_confirm_when_flag_off`: flag OFF y sin `confirm` → 400
     `confirmation_required` (legacy intacto).
  7. `test_autopublish_marks_error_on_exception` (C3): `_do_publish_incident` mockeado para
     lanzar `RuntimeError("boom")` → el incidente queda `status="error"` con `error` seteado
     (la cola nunca se queda muda en "analizando").
  8. `test_publish_backfills_doc_tracker_id` ([ADICIÓN ARQUITECTO]/C7): publish exitoso
     (provider mockeado `{"id": 999}`) → el doc escrito en `docs/incidencias/` contiene
     `tracker_id: 999` en el frontmatter (leer el archivo de `doc_path` del store).
  **Setup (C10):** espejar los helpers existentes de
  `tests/test_plan131_incident_preview_publish.py` (`_make_app`, `_patch_run`, mock del
  provider y `_flag`) — NO inventar un arnés nuevo.
  Registrar en `HARNESS_TEST_FILES` (G2).
- Frontend nuevo `frontend/src/incidents/incidentQueue.test.ts` (4 casos):
  `test upsertQueueItem reemplaza por id`, `test upsertQueueItem agrega nuevo`,
  `test queueSummary cuenta publicadas y errores`,
  `test mapStoreStatus mapa total incluye analizada y desconocidos` (C3: `"analizada"` →
  `"analizando"`, `"cualquier-cosa"`/`null` → `"error"`).

**Comandos:**
```bash
cd "Stacky Agents/backend" && .venv/Scripts/python -m pytest tests/test_incident_autopublish.py tests/test_plan131_incident_preview_publish.py -q
```
```bash
cd "Stacky Agents/frontend" && npx vitest run src/incidents/incidentQueue.test.ts
```

**Criterio BINARIO:** backend 8 casos + suite `test_plan131_incident_preview_publish.py`
(existente) siguen verdes; frontend 4 casos verdes; `npx tsc --noEmit` limpio.

**Impacto por runtime:** el auto-publish corre en `register_post_hook`, invocado por
`ticket_status.on_execution_end` para **cualquier** runtime → paridad total Codex / Claude /
Copilot. **Fallback:** flag OFF → gate preview+confirm de hoy, byte-idéntico.

**Trabajo del operador:** ninguno; con el flag ON (default) crea directo y en lote. Puede
apagarlo por UI para recuperar el paso de revisión.

---

### F4 — Agente NUEVO "Dev Resolutor de Incidencias" (backend)

**Objetivo (1 frase):** crear un agente `incident_dev` que tome una Issue de incidencia y
la resuelva en el repo (análisis + fix + evidencia + comentario), lanzable vía endpoint en
los 3 runtimes.

**Valor:** cierra el punto 2 (K2).

**Archivos a crear/editar:**
- CREAR `Stacky Agents/backend/agents/incident_dev.py` (clase `IncidentDevAgent`)
- CREAR `Stacky Agents/backend/agents/IncidentDevResolver.agent.md` (+ espejo de plantilla)
- EDITAR `Stacky Agents/backend/agents/__init__.py` (registrar en `registry` `:13`)
- CREAR `Stacky Agents/backend/services/incident_dev_context.py`
  (`ensure_incident_dev_agent_file()` + `build_incident_dev_prompt()`)
- EDITAR `Stacky Agents/backend/api/agents.py` (endpoint `run-incident-dev`)

**Símbolos EXACTOS:**
- `class IncidentDevAgent(BaseAgent)` con `type = "incident_dev"`, `name = "Incident Dev Resolver"`,
  `icon = "🔧"`, `default_blocks = ["ticket-meta", "technical-analysis", "code-tree", "ridioma-master"]`
  (espejo de `DeveloperAgent` `agents/developer.py:20-25`).
- `system_prompt()` (ver abajo).
- Endpoint: `@bp.post("/run-incident-dev")` → `run_incident_dev()` en `api/agents.py`.
- `incident_dev_context.ensure_incident_dev_agent_file() -> Path` (espejo de
  `incident_context.ensure_incident_agent_file()` `:116`).

**`system_prompt()` (literal, NORMATIVO — C6/§3bis.2; se copia carácter por carácter):**

```python
    def system_prompt(self) -> str:
        return (
            "Sos el Dev Resolutor de Incidencias: un desarrollador SENIOR del proyecto "
            "activo, experto en su stack y sus convenciones, que toma una Issue de "
            "incidencia dev-ready y la RESUELVE en el repo con evidencia real.\n\n"
            "TU ENTRADA es el desglose de la incidencia con estas secciones: RESUMEN "
            "EJECUTIVO, CONTEXTO DE NEGOCIO, ANALISIS FUNCIONAL, ANALISIS TECNICO, PASOS "
            "DE REPRODUCCION, CRITERIOS DE ACEPTACION, ARCHIVOS Y MODULOS PROBABLES, "
            "EPICA RELACIONADA, PRIORIDAD Y ESTIMACION. Usalas así: los CRITERIOS DE "
            "ACEPTACION definen tu ALCANCE EXACTO (ni más ni menos); ARCHIVOS Y MODULOS "
            "PROBABLES es tu punto de partida de lectura; el ANALISIS TECNICO puede "
            "contener HIPOTESIS del analista, no hechos — VERIFICALAS contra el código "
            "real ANTES de creerlas: leé cada archivo citado, confirmá que la línea y el "
            "símbolo existen y que la causa propuesta es real. Si el análisis se equivocó, "
            "decilo con evidencia y resolvé la causa raíz VERDADERA dentro del alcance de "
            "los criterios de aceptación.\n\n"
            "METODO OBLIGATORIO: (1) reproducí o localizá el defecto con evidencia "
            "archivo:línea; (2) implementá el fix MINIMO que cumple los criterios de "
            "aceptación — sin refactors oportunistas, sin tocar código ajeno al defecto; "
            "(3) corré los tests/compilación que el proyecto tenga para el área tocada y "
            "pegá el resultado REAL; (4) si un criterio de aceptación no queda cubierto, "
            "declaralo explícitamente — PROHIBIDO afirmarlo sin verificarlo.\n\n"
            "CASO ESPECIAL — la causa NO es de código: si tu verificación muestra que el "
            "defecto viene de DATOS o ENTORNO (por ejemplo: falta una fila en una tabla "
            "que un JOIN requiere, una config de ambiente, un job de carga que no corrió), "
            "NO inventes un workaround de código que lo tape. En ese caso NO modifiques "
            "nada y cerrá con un comentario que empiece con ⚠️ BLOQUEADO explicando: qué "
            "verificaste, por qué la causa no es de código, y qué acción externa se "
            "necesita (con el dato exacto: tabla, registro, proceso).\n\n"
            "CIERRE NORMAL: un comentario que empieza con 🚀 con EXACTAMENTE estas "
            "secciones: CAUSA RAIZ (con archivo:línea), ARCHIVOS MODIFICADOS, RESUMEN DEL "
            "FIX (diff o descripción precisa), TESTS EJECUTADOS Y RESULTADO, CRITERIOS DE "
            "ACEPTACION VERIFICADOS (uno por uno: cumplido/no cumplido y cómo lo "
            "comprobaste). PROHIBIDO narrar lo que vas a hacer sin hacerlo: entregás "
            "evidencia real. NUNCA cerrás ni transicionás la Issue en el tracker: eso lo "
            "decide el operador."
        )
```

**Endpoint `run_incident_dev` (espejo de `run_incident` `:877`, diferencias EXACTAS):**
- Gate: `if not config.STACKY_INCIDENT_DEV_RESOLVER_ENABLED: return 404 feature_disabled`.
- Input: `ticket_id: int` (el ticket local de la Issue). Cargar el `Ticket`; si
  `work_item_type` no es `"Issue"`/`"Bug"`, devolver 400 `not_an_issue`.
- Contexto: `context_blocks = [{"id":"issue","kind":"raw-conversation","title":"Issue de
  incidencia","content": build_incident_dev_prompt(ticket)}]`. `build_incident_dev_prompt`
  arma: descripción HTML de la Issue (el desglose) + link al doc del incidente si existe
  (`incident.doc_path`) + nota de alcance (resolver dentro de los criterios de aceptación).
- Auto-resolver `.agent.md` para CLI (espejo de `:957-960`): si runtime en
  `("codex_cli","claude_code_cli")` y sin `vscode_agent_filename`,
  `incident_dev_context.ensure_incident_dev_agent_file()` y
  `vscode_agent_filename = "IncidentDevResolver.agent.md"`.
- Lanzar: `agent_runner.run_agent(agent_type="incident_dev", ticket_id=ticket_id,
  context_blocks=..., user=..., runtime=runtime_raw, vscode_agent_filename=...,
  project_name=..., use_few_shot=False, use_anti_patterns=False, model_override=...,
  effort_override=...)`. Passthrough de model/effort idéntico a `run_incident`.
- Respuesta: `jsonify({"execution_id": execution_id, "status": "running"}), 202`.
- **SIN autopublish** (el Dev Resolutor produce código + comentario, no publica tickets).

**`.agent.md`** — crear `IncidentDevResolver.agent.md` con frontmatter (`name:
IncidentDevResolver`, `stacky_agent_type: incident_dev`, `tools: ['codebase','search','usages','problems','changes']`)
y el cuerpo que instruye el contrato del comentario 🚀. `incident_dev_context.py` guarda el
espejo en constante `_AGENT_TEMPLATE_MD` (patrón C10 de `incident_context.py:15-113`) para
que viaje en el bundle congelado.

**Tests (TDD):** archivo nuevo `backend/tests/test_incident_dev_agent.py`. Casos:
1. `test_incident_dev_registered`: `from agents import registry; assert "incident_dev" in registry`.
2. `test_incident_dev_system_prompt_has_contract`: el prompt contiene `"🚀"`,
   `"⚠️ BLOQUEADO"` y `"criterios de aceptación"` (§3bis.2, criterio c).
3. `test_run_incident_dev_404_when_flag_off`: flag OFF → `POST /api/agents/run-incident-dev` → 404.
4. `test_run_incident_dev_400_when_not_issue`: ticket con `work_item_type="Task"` → 400 `not_an_issue`.
5. `test_run_incident_dev_launches`: mock de `agent_runner.run_agent` → 202 con `execution_id`.
6. `test_ensure_incident_dev_agent_file_writes`: `ensure_incident_dev_agent_file()` crea el
   archivo en `stacky_agents_dir()`.

Registrar en `HARNESS_TEST_FILES` (G2).

**Comando (Git Bash):**
```bash
cd "Stacky Agents/backend" && .venv/Scripts/python -m pytest tests/test_incident_dev_agent.py -q
```

**Criterio BINARIO:** 6 casos verdes.

**Impacto por runtime:** corre vía `agent_runner.run_agent` (mismo camino que Developer) →
paridad Codex / Claude / Copilot. **Fallback:** flag OFF → el endpoint responde 404 y la UI
no muestra el botón (F5). **Trabajo del operador:** ninguno (sólo hace click cuando quiere
resolver).

---

### F5 — Botón "Resolver con agente" en las Issues del board

**Objetivo (1 frase):** en cada ticket `work_item_type == "Issue"` del board, ofrecer un
botón que lanza el Dev Resolutor (F4) y abre la consola para runtimes CLI.

**Valor:** hace accionable la Issue visible (F1) con el agente nuevo (F4) — cierra el K2 de
punta a punta.

**Archivos a editar:**
- `Stacky Agents/frontend/src/api/endpoints.ts` — agregar `Incidents.runDevResolver`.
- `Stacky Agents/frontend/src/pages/TicketBoard.tsx` — botón en `TicketCard` (`:245`).
- `Stacky Agents/frontend/src/components/IncidentResolverModal.module.css` **NO**; usar el
  `.module.css` del board (`TicketBoard.module.css`) para clases del botón.

**`endpoints.ts` — nuevo método (junto a `Incidents` `:4155`):**

```ts
  runDevResolver: (payload: {
    ticket_id: number;
    runtime?: import("../types").AgentRuntime;
    project?: string | null;
    model?: string | null;
    effort?: "low" | "medium" | "high" | "xhigh" | "max";
  }) =>
    api.post<{ execution_id: number; status: string }>("/api/agents/run-incident-dev", payload),
```

**`TicketBoard.tsx::TicketCard`:** calcular
`const isIssue = ["issue","bug"].includes((ticket.work_item_type ?? "").toLowerCase());`
(espejo de `isEpic` `:260`). El flag de disponibilidad se lee donde el board YA llama
`Incidents.status()` (VERIFICADO: `TicketBoard.tsx:715`, `const s = await
Incidents.status();`) — extender ese mismo consumo con el campo nuevo
`dev_resolver_enabled` que el backend expone en `incidents_status` (`api/incidents.py:14`,
mismo patrón que `auto_publish_enabled` de F3). Cuando `isIssue && devResolverEnabled &&
!isClosed && !isRunning`, renderizar:

```tsx
<button
  className={styles.resolveBtn}
  disabled={isLaunching}
  onClick={() => void handleResolveWithAgent()}
  title="Resolver esta incidencia con un agente dev"
>
  🔧 Resolver con agente
</button>
```

`handleResolveWithAgent` espeja `handleRunConfirm` (`:298`): llama
`Incidents.runDevResolver({ ticket_id: ticket.id, runtime: agentRuntime, project:
activeProjectName, model: agentRuntime === "claude_code_cli" ? selectedModel : undefined,
effort })`, luego `openConsoleIfCliRuntime(agentRuntime, result, (id) =>
setCodexConsoleExecution(id, false))` e invalida las queries `["tickets", ...]`,
`["tickets-hierarchy", ...]`, `["executions"]` (igual que `:315-319`). Manejo de error con
`humanizeAgentLaunchError`. Clase `resolveBtn` en `TicketBoard.module.css` (G6, sin
`style={{}}`).

**Tests (TDD):** el gap RTL/jsdom (memoria `gotcha-rtl-jsdom-structural-gap`) impide tests
de render del componente. Cubrir con un **modelo puro** nuevo
`frontend/src/incidents/devResolverModel.ts`:
```ts
export function canResolveWithAgent(args: {
  workItemType?: string | null; adoState?: string | null; isRunning: boolean;
  enabled: boolean; closedStates: string[];
}): boolean { /* isIssue && enabled && !running && !closed */ }
```
y `frontend/src/incidents/devResolverModel.test.ts` (4 casos: Issue+enabled+abierto→true;
Task→false; cerrado→false; disabled→false). El wiring del botón se valida en el smoke
manual (F6). Backend: los casos de F4 ya cubren el endpoint.

**Comando:**
```bash
cd "Stacky Agents/frontend" && npx vitest run src/incidents/devResolverModel.test.ts && npx tsc --noEmit
```

**Criterio BINARIO:** 4 casos verdes + `tsc` limpio. Smoke manual: en una Issue del board
aparece "🔧 Resolver con agente"; el click lanza un run y abre consola (CLI).

**Impacto por runtime:** el botón usa el runtime activo del workbench; para CLI abre la
consola in-page (paridad con el resto del board). **Fallback:** `dev_resolver_enabled=false`
→ el botón no se renderiza. **Trabajo del operador:** ninguno (un click cuando quiere
resolver).

---

### F6 — Cierre: ratchet, smokes y DoD

**Objetivo (1 frase):** dejar el plan verificable end-to-end y sin deuda de registro.

**Acciones:**
- Confirmar que **todos** los `test_*.py` nuevos (`test_persist_incident_ticket.py`,
  `test_incident_vision.py`, `test_incident_autopublish.py`, `test_incident_dev_agent.py`)
  están en `HARNESS_TEST_FILES` en **ambos** scripts (`run_harness_tests.sh` `:20` y
  `run_harness_tests.ps1`).
- Smoke manual E2E (documentar en `plan-166-status`): capturar 2 incidencias seguidas con
  una captura cada una → ambas se publican como Issues sin confirmación → aparecen en el
  board con badge ámbar → click "🔧 Resolver con agente" en una → corre el Dev Resolutor y
  abre consola.

**Comando de verificación agregada (Git Bash):**
```bash
cd "Stacky Agents/backend" && .venv/Scripts/python -m pytest \
  tests/test_harness_flags.py tests/test_harness_flags_requires.py \
  tests/test_persist_incident_ticket.py tests/test_incident_vision.py \
  tests/test_incident_autopublish.py tests/test_incident_dev_agent.py \
  tests/test_plan131_incident_preview_publish.py -q
```

**Criterio BINARIO:** todo verde.

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Mitigación |
|---|---|---|
| R1 | Auto-publish (F3) publica una Issue con desglose de baja calidad sin que el operador la vea. | Es la excepción dura #1 pedida por el operador; el desglose igual pasa por `_looks_like_incident` (`:7440`, gate de forma) y el reintento de repair del Plan 160. El operador puede apagar el flag por UI para recuperar el gate. |
| R2 | El endpoint de visión (F2) es lento o cuelga y demora el análisis. | `timeout_sec` = `LOCAL_LLM_TIMEOUT_SEC` (C4) + presupuesto duro (C5: máx 6 imágenes, 240 s totales) + cualquier fallo → `None` (degradación); la extracción es best-effort y no bloquea el run (`try/except` en `run_incident`). |
| R3 | La imagen contiene datos sensibles y el OCR los mete en la Issue de ADO. | El texto extraído pasa por el mismo centinela de egreso de secretos/PII (Plan 121) que el resto del contenido publicado; no se agrega superficie nueva de egreso (la imagen ya se subía como adjunto). |
| R4 | `_persist_incident_ticket` (F1) choca con el sync de ADO y duplica la Issue. | Idempotente por `ado_id` (`filter(Ticket.ado_id == ado_id).first()`); el sync upsertea por el mismo `ado_id` (`ado_sync.py:158-161`), no duplica. |
| R5 | El post-hook de auto-publish (F3) se dispara para runs que no son de incidencia. | Guard `agent_type == "incident"` + `final_status == "completed"` + `incident.auto_publish` al inicio del hook; retorno temprano en todo lo demás. |
| R6 | Merge con la sesión paralela sobre `api/tickets.py` / `IncidentResolverModal.tsx`. | Cambios aditivos (funciones y ramas nuevas); revisar `git status` en frío antes de commitear (memoria de sesión paralela). |
| R7 | El post-hook llama código de endpoint fuera del app context y crashea (`jsonify`/`request`). | Contrato C2/G8: `_do_publish_incident` devuelve `(dict, int)`, jamás usa `jsonify` ni `request`; test 1 de F3 lo ejercita desde fuera de un request. |
| R8 | En lote, un fallo de publicación queda mudo y la cola muestra "analizando" para siempre. | C3: el hook marca `status="error"` en el store ante payload ≥400 o excepción; `mapStoreStatus` es mapa TOTAL (desconocido → "error"); test 7 de F3. |
| R9 | El agente Dev Resolutor "resuelve" con un workaround de código un defecto que en realidad es de datos/entorno (caso real: fila faltante en RPRES del insumo `INC-_inc-prestamos-...md`). | Prompt experto §3bis.2: contrato ⚠️ BLOQUEADO — verificar antes de creer, prohibido tapar causas de datos con código; el operador decide la acción externa. |

---

## 6. Fuera de scope

- Reintento/repair del desglose HTML (ya lo cubre el Plan 160).
- Catálogo unificado de modelos/efforts (Plan 159) — el selector del modal sigue con su
  lista actual.
- Que el Dev Resolutor **cierre/transicione** la Issue en ADO automáticamente (sólo comenta
  con evidencia; la transición la decide el operador). Autonomía adicional queda fuera.
- Visión multimodal nativa del runtime leyendo la imagen del disco: se documenta como
  camino complementario ya presente en el manifiesto, pero NO es el mecanismo del que
  depende F2 (que es el OCR desacoplado).
- OCR de PDFs (sólo imágenes `kind == "image"`).

---

## 7. Glosario + Orden de implementación + DoD

### Glosario (términos del dominio Stacky)

- **Resolutor de Incidencias (Plan 131):** flujo modal intake multimodal → `IncidentAgent`
  → desglose HTML → publish Issue en el tracker. Flag maestro
  `STACKY_INCIDENT_RESOLVER_ENABLED`.
- **`incident_store`:** persistencia en disco de los intakes (`data_dir()/incidents/<id>/`)
  + ledger. Funciones `create_incident`/`update_incident`/`get_incident`/`list_incidents`.
- **Manifiesto de adjuntos:** bloque `<attachments-manifest>` que describe los archivos al
  agente (`incident_context.build_attachments_manifest`).
- **Patrón triple (flags):** un flag nuevo se define en `config.py` (efectivo) +
  `harness_flags.py` (`FlagSpec`, UI) + se cura en `_CURATED_DEFAULTS_ON`
  (`tests/test_harness_flags.py`) si es `default=True`.
- **Post-hook (`register_post_hook`):** callable agnóstico de runtime que corre al terminar
  cualquier ejecución de agente (`ticket_status.on_execution_end`).
- **Runtime:** motor de ejecución del agente — `codex_cli`, `claude_code_cli`,
  `github_copilot`. Todo debe funcionar en los 3 o degradar explícito.
- **Excepción dura #1:** única autonomía aceptada por default — acción automática que
  bypasea revisión humana (aquí: auto-publicar la Issue), aceptada por directiva explícita
  del operador, con kill-switch por UI.

### Orden de implementación

1. **F0** — flags + config (base de todo).
2. **F1** — persistir Ticket local de la Issue (visibilidad).
3. **F2** — visión de capturas → texto inline.
4. **F3** — creación directa + lote (relax confirm + post-hook + modal cola).
5. **F4** — agente `incident_dev` + endpoint.
6. **F5** — botón "Resolver con agente" en el board.
7. **F6** — ratchet, smokes, DoD.

### Definición de Hecho (DoD) global

- [ ] Los 6 keys de flags/config nuevos existen en `config.py` + `harness_flags.py`; los 4
      bool `default=True` están en `_CURATED_DEFAULTS_ON`; los 6 keys están en
      `_CATEGORY_KEYS` (C1/G7, junto a `STACKY_INCIDENT_RESOLVER_ENABLED`); las 5 aristas
      `requires` están en `test_harness_flags_requires.py`. `test_harness_flags*.py` verdes
      (incluye `test_every_registry_flag_is_categorized`).
- [ ] Publicar una incidencia crea el `Ticket` local de la Issue al instante
      (`test_persist_incident_ticket.py` verde; smoke: aparece en el board sin sync).
- [ ] Una captura con texto aporta ese texto al desglose vía OCR inline
      (`test_incident_vision.py` verde); sin endpoint de visión, degrada exacto a hoy.
- [ ] Con `STACKY_INCIDENT_AUTO_PUBLISH_ENABLED` ON, publicar no requiere `confirm` y el
      modal permite cargar varias seguidas sin diálogos
      (`test_incident_autopublish.py` + `incidentQueue.test.ts` verdes); con el flag OFF, el
      gate preview+confirm queda byte-idéntico.
- [ ] El agente `incident_dev` está registrado y su endpoint `run-incident-dev` lanza en los
      3 runtimes (`test_incident_dev_agent.py` verde).
- [ ] Las Issues del board muestran "🔧 Resolver con agente" que lanza el Dev Resolutor
      (`devResolverModel.test.ts` verde + smoke manual); `tsc --noEmit` limpio.
- [ ] Todos los `test_*.py` nuevos registrados en `HARNESS_TEST_FILES` (ambos scripts).
- [ ] Tras un publish exitoso, el doc del incidente en `docs/incidencias/` y su línea en
      `INDICE_INCIDENCIAS.md` tienen el `tracker_id` real ([ADICIÓN ARQUITECTO]/C7 —
      test 8 de F3 verde).
- [ ] Los 2 agentes cumplen su ficha de §3bis: `IncidentAgent` con el refuerzo F2b (test 8
      de F2) y `IncidentDevAgent` con el prompt experto completo (test 2 de F4, literales
      `🚀` / `⚠️ BLOQUEADO` / `criterios de aceptación`).
- [ ] El ciclo mantiene DOS ACTORES (cargador → resolutor): ningún rol, estado ni handoff
      nuevo introduce un tercero (verificación por lectura del diff).
- [ ] Con TODOS los flags nuevos OFF, el comportamiento es byte-idéntico al de hoy
      (backward-compatible).
- [ ] `plan-166-status` documentado con el resultado real de los smokes.

---

_Plan 166 v2 — Stacky Agents. Criticado y endurecido por `criticar-y-mejorar-plan`
(APROBADO-CON-CAMBIOS, 2026-07-17). Listo para `implementar-plan-stacky`._
