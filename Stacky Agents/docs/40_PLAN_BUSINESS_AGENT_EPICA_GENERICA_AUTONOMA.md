# Plan 40 — Business Agent: Épica genérica, rica, autónoma + modelo configurable

> **Estado:** IMPLEMENTADO (verificado contra código 2026-06-19). F1 BusinessAgent.agent.md (v1.5.0, R-BATCH), F2 .agent.md versionados, F3 wiring model_override+effort en run_brief (agents.py:589-649), tests test_run_brief_model_override.py verdes. (La cabecera "propuesto" original era stale.)
> **Entregable triple:**
> 1. Reescritura ya aplicada de `backend/Stacky/agents/BusinessAgent.agent.md` (v1.1.0) — ver F1.
> 2. `.agent.md` versionados en git (ya un-ignorados; ver F2 — verificación, no cambio).
> 3. Modelo por-run configurable en `run-brief` con default `claude-sonnet-4-6` y effort
>    fijo al máximo (`high`) — ver F3 (pasos concretos, no implementado aún).
> **No agrega trabajo al operador.** Backward-compatible con `run-brief`/`from-brief` (Plan 38)
> y con el historial de runs (Plan 39).

---

## A. CRÍTICA AL PLAN 40 ORIGINAL (v1)

El plan v1 se quedó corto. Esto es lo que estaba flojo, ambiguo o irreal, y cómo se corrige:

| # | Defecto del plan v1 | Por qué es un problema | Corrección en v2 |
|---|---------------------|------------------------|------------------|
| C1 | **Scope incompleto.** v1 solo trataba la *calidad del prompt*. Ignoraba por completo los requisitos de (a) `.agent.md` versionados, (b) modelo configurable, (c) effort máximo, (d) nombrar el batch. | El plan no cumplía 3 de los 4 requerimientos reales. | v2 incorpora F2 (versionado), F3 (modelo/effort) y la regla R-BATCH (§B.5). |
| C2 | **F2/F3 eran humo.** "Enriquecimiento más agresivo" y "telemetría" sin archivo, sin test, sin código: relleno que infla el plan sin entregar nada accionable. | Un plan para modelos menores no puede tener fases vacías: confunde al implementador. | v2 elimina las fases-humo. F2/F3 ahora son trabajo real y verificable (versionado + wiring de modelo). El enriquecimiento BD ya vive en el prompt (F1); no necesita "fase" propia. |
| C3 | **Gate de calidad débil.** "Verificación por relectura de 6 invariantes" no es un gate: es opinión. F0 solo corre 2 tests que no tocan el cuerpo del prompt. | No hay forma binaria de saber si el prompt nuevo produce épicas mejores. | v2 mantiene F0 como gate de no-regresión (correcto) y agrega un **checklist de calidad de épica** (§B.6) verificable sobre el HTML de salida, más un test de wiring real para F3. |
| C4 | **Premisa de versionado equivocada (no escrita, pero asumida en memoria).** Se asumía que los `.agent.md` estaban gitignored. | `git check-ignore` confirma que NO lo están: ya fueron un-ignorados (`.gitignore:42-47`) y los 5 están `git ls-files`-tracked. Aplicar un "un-ignore" sería redundante o, peor, romper la regla que re-ignora `manifest.json`. | v2 convierte F2 en **verificación + endurecimiento documental**, no en un cambio destructivo del `.gitignore`. |
| C5 | **"Effort = máximo" sin aterrizar.** El requisito pide effort máximo, pero el plan v1 ni lo menciona. | El CLI de Claude Code solo acepta `--effort low\|medium\|high` (`claude_code_cli_runner.py:1574-1575`). No existe `max`/`maximum`. Pedir "max" literal rompería el flag. | v2 define **effort máximo = `high`** (el techo real del CLI) y lo fija para el flujo de brief, sin permitir bajarlo. |
| C6 | **Modelo configurable sin wiring.** El requisito pide poder cambiar el modelo; el flujo `run-brief` hoy NO lee ningún `model` del payload (`agents.py:556-613`). | `run_agent` SÍ acepta `model_override` (`agent_runner.py:86`) y el runner aplica `clamp_model` (cap duro: nunca opus/fable). Pero `run_brief` nunca lo pasa → el requisito es inalcanzable sin el wiring. | v2 especifica el cambio exacto: leer `model` del payload y reenviarlo como `model_override`, con default `claude-sonnet-4-6`. |
| C7 | **KPIs no medibles.** v1 promete "% de RF aprobados sin editar" sin instrumentación que lo capture. | Un KPI que nadie mide es decorativo. | v2 baja el KPI a un **checklist binario por épica** (§B.6) que el operador (o una relectura) puede tildar; la telemetría automática queda explícitamente fuera de scope (honesto). |
| C8 | **Regla del batch ausente.** Nada impide que el agente escriba "el proceso batch" en genérico. | Ambigüedad aguas abajo: el Analista Funcional no sabe a qué batch se refiere. | v2 agrega **R-BATCH** como regla dura del prompt (§B.5) y como ítem del checklist (§B.6). |

**Lo que el plan v1 SÍ tenía bien y se conserva:** el análisis del gap del prompt v1.0.0
(§B.1), la tabla de mejoras M1-M8 (§B.2), el respeto al contrato `<hr><h2>RF-XXX`, el
human-gate como aprobación del modal (no el agente frenándose), y la degradación elegante
sin `client-profile`.

---

## B. PLAN MEJORADO (v2)

### B.0 Contexto y motivación (sin cambios de fondo)

El flujo brief→épica (Plan 38) está en producción: `POST /api/run-brief`
(`backend/api/agents.py:544`) crea/reutiliza un *Brief Pool Ticket* (`ado_id=-1`), inyecta
el brief como context block `brief` (`kind: raw-conversation`) y corre el agente `business`
auto-resolviendo `vscode_agent_filename = "BusinessAgent.agent.md"` (`agents.py:566-567`).
El agente produce el HTML de la Épica; **Stacky** la publica vía
`POST /api/tickets/epics/from-brief` tras la **aprobación del operador en un modal**
(Plan 38). El agente nunca toca ADO. El historial de runs (Plan 39) ya expone cada corrida.

El problema NO es el flujo. Son tres cosas: (1) la **calidad del prompt**, (2) la **falta de
control de modelo/effort** sobre la corrida del brief, y (3) la **trazabilidad/versionado**
de los `.agent.md`.

### B.1 Gap del Business Agent v1.0.0 (conservado del plan v1)

1. **No navega documentación funcional** → no conoce lo que ya existe.
2. **No usa la terminología del producto** → fricción de traducción con el FunctionalAnalyst.
3. **No clasifica vs funcionalidad existente** ni cita el módulo fuente.
4. **RF pobres** (solo Actores/Descripción/Reglas/Datos/Prioridad): no autocontenidos.
5. **No enriquece con datos reales** pese a tener `db/query` (solo SELECT, auditado).
6. **Exhaustividad no exigida** → pierde requisitos implícitos.

**Consecuencia:** épicas flacas → el operador rellena → se pierde la promesa del centauro.

### B.2 Mejoras del prompt (M1-M8, conservadas del plan v1)

| # | Mejora | Sube |
|---|--------|------|
| M1 | Navegar documentación funcional (INDEX → módulos → lectura) vía rutas del `client-profile`. | Calidad + autonomía |
| M2 | Usar la **terminología exacta del producto** (`client_profile.terminology.product_name` + términos del INDEX). | Calidad |
| M3 | **Clasificar cada RF** vs lo existente y **citar el módulo fuente**. | Calidad + autonomía |
| M4 | **Estructura rica por RF**: Contexto de proceso / Descripción / Criterios de aceptación verificables / Información adicional (Prioridad, Usuarios, Restricciones, Relación con lo existente). | Calidad |
| M5 | **Enriquecer con BD readonly** (`db/query`, solo SELECT) cuando ayude a validar entidades. | Calidad |
| M6 | **Autonomía total**: ambigüedad → `[SUPUESTO: ...]` y SEGUIR; cero pasos interactivos. | Autonomía |
| M7 | **Degradación elegante sin `client-profile`**: brief + notas, marcar supuestos, NO abortar. | Robustez |
| M8 | **Exhaustividad exigida** + bloque visible de supuestos para que el operador valide al aprobar. | Calidad + HITL |

**Nuevas en v2 (cierran requisitos del usuario):**

| # | Mejora | Requisito |
|---|--------|-----------|
| M9 | **R-BATCH**: jamás escribir "el proceso batch"/"el batch" en genérico. Siempre nombrar el proceso concreto (nombre real del job/servicio, p.ej. `FacturacionNocturna`, `CierreDiario`). Si el nombre no se conoce, marcarlo `[PENDIENTE: nombre del proceso batch]` — nunca dejarlo anónimo. | Req 4 |
| M10 | **Criterios de aceptación medibles**: cada uno con condición observable (dato/estado/resultado), no "debe funcionar bien". | Refuerza M4 |

**KPI objetivo (medible por checklist §B.6, no por telemetría automática):** nº de RF con
módulo fuente citado ↑; nº de campos `[PENDIENTE]` por épica ↓; nº de menciones a "batch"
anónimas = **0**.

---

### B.3 Fases (orden de implementación)

> F0, F1 y F2 no tocan código Python. F3 es el único cambio de backend y es pequeño.

#### F0 — Gate de no-regresión (antes de tocar nada)

- **Objetivo:** confirmar que el cambio de prompt NO rompe `run-brief`.
- **Archivos:** ninguno (solo correr tests existentes).
- **Test / comando exacto** (venv del repo, py3.13):
  ```
  cd "Stacky Agents/backend"
  .venv/Scripts/python.exe -m pytest tests/test_run_brief_claude_cli_repro.py tests/test_run_brief_error_handling.py -q
  ```
- **Criterio de aceptación (BINARIO):** ambos archivos pasan igual que en HEAD (el prompt es
  texto; ningún test Python referencia el cuerpo del `.agent.md`, solo el filename, que NO cambia).
- **Flag / default:** N/A. **Runtimes:** N/A. **Operador:** ninguno.

#### F1 — Reescritura del prompt `BusinessAgent.agent.md` (NÚCLEO — ya aplicada)

- **Objetivo:** elevar el prompt al flujo rico, genérico, autónomo y degradable, e incorporar
  M9 (R-BATCH) y M10 (criterios medibles).
- **Archivo exacto:** `backend/Stacky/agents/BusinessAgent.agent.md`.
- **Frontmatter (INTACTO salvo `version`):** `stacky_agent_type: business`,
  `stacky_completion_contract: v1`, `stacky_requires_client_profile: false` (deliberado — ver
  R3), `stacky_human_gate_mode_a/b: false`, `tools`, `description`. **`version: 1.0.0 → 1.1.0`**.
  El **nombre del archivo NO cambia** (lo consume `agents.py:567`).
- **Cambios de cuerpo (ya aplicados en v1.1.0):**
  - `+` "Contexto del arnés (degradación)": detectar `client-profile`; extraer
    `terminology.product_name`, `docs_indexes.functional_online/_batch`, `database.*`. Sin
    perfil → modo degradado (brief + notas, marcar supuestos, NO abortar).
  - `+` "Navegación de documentación funcional": INDEX → módulos → lectura, solo si hay perfil.
  - `+` "BD readonly": `POST /api/tickets/{id}/db/query` con `{"sql": "SELECT ...",
    "project": "{stacky_project_name}"}`; solo SELECT; opcional; degradar si falla.
  - `~` OUTPUT por RF rico (Contexto de proceso / Descripción / Criterios verificables /
    Información adicional con módulo fuente). **Preservar `<hr><h2>RF-XXX` exactamente.**
  - `+` Bloque visible "Supuestos asumidos" al pie (validación en el modal).
  - `+` Reglas de autonomía: interpretación más razonable + `[SUPUESTO]` y SEGUIR.
  - `~` Identidad **genérica** (cero "Pacífico/UCollect" salvo ejemplo entre paréntesis).
- **Pendiente de aplicar en el prompt (PEQUEÑO, este plan lo exige — ver §C.4):**
  - `+` **R-BATCH (M9)** como regla crítica: "Nunca escribas 'el proceso batch' o 'el batch'
    en genérico. Siempre nombrá el proceso concreto. Si no conocés el nombre, marcá
    `[PENDIENTE: nombre del proceso batch]`."
  - `~` Reforzar en "Criterios de aceptación" que sean **observables/medibles (M10)**.
- **Test:** el prompt es texto; gate = F0 (no-regresión) + checklist §B.6 sobre una corrida real.
- **Criterio de aceptación (BINARIO):** §B.6 (a)-(h) se cumplen en una épica de prueba y F0 verde.
- **Flag / default:** N/A (prompt por defecto, backward-compatible). **Runtimes:** texto →
  funciona en Codex CLI / Claude Code CLI / Copilot Pro; capacidades dependientes (docs,
  `db/query`) degradan con fallback escrito en el prompt. **Operador:** ninguno.

#### F2 — `.agent.md` versionados en git (VERIFICACIÓN + endurecimiento — NO es un cambio destructivo)

- **Objetivo:** garantizar que los 5 `.agent.md` (`BusinessAgent`, `Developer`,
  `FunctionalAnalyst`, `QAUat1`, `TechnicalAnalyst.v2`) **persisten en el repo** y que el
  runtime sigue leyéndolos de `backend/Stacky/agents/`.
- **Estado de partida (verificado, NO asumido):** el `.gitignore` (líneas 42-47) **YA**
  un-ignora la carpeta y los `*.agent.md`:
  ```
  Stacky Agents/backend/Stacky/*                     # ignora todo bajo Stacky/
  !Stacky Agents/backend/Stacky/agents/              # … menos la carpeta agents/
  !Stacky Agents/backend/Stacky/agents/**            # … y su contenido
  !Stacky Agents/backend/Stacky/agents/*.agent.md    # … explícito para .agent.md
  Stacky Agents/backend/Stacky/agents/manifest.json  # re-ignora el manifest (se regenera)
  ```
  `git ls-files "Stacky Agents/backend/Stacky/agents/*.agent.md"` lista los 5; `git check-ignore`
  devuelve "trackable" para todos. **No hay nada que un-ignorar.**
- **Cambio a aplicar:** ninguno sobre `.gitignore` (ya correcto). Si se hubiera encontrado el
  patrón ignorando los `.agent.md`, el cambio habría sido añadir las negaciones `!...*.agent.md`.
- **Endurecimiento documental:** este plan deja constancia de que la creencia "los `.agent.md`
  están gitignored" es **stale**. La nota debe leer: *los `.agent.md` están versionados; el
  único re-ignorado bajo `agents/` es `manifest.json` (regenerado en runtime/release)*.
- **Verificación del runtime (cómo se lee):** el runner CLI recibe `vscode_agent_filename`
  (`agents.py:567`) y resuelve el archivo bajo `backend/Stacky/agents/` (NO bajo
  `DeployStackyAgents`). Versionar el `.agent.md` no cambia esa ruta de lectura.
- **Test / comando exacto:**
  ```
  cd "Stacky Agents"
  git check-ignore backend/Stacky/agents/BusinessAgent.agent.md ; echo "exit=$?"   # exit=1 = NO ignorado (correcto)
  git ls-files "backend/Stacky/agents/*.agent.md"                                    # debe listar los 5
  ```
- **Criterio de aceptación (BINARIO):** `git check-ignore` sale con código 1 (no ignorado)
  para los 5 archivos **y** `git ls-files` los lista; `manifest.json` SÍ está ignorado.
- **Flag / default:** N/A. **Runtimes:** N/A (es versionado, no runtime). **Operador:** ninguno.

#### F3 — Modelo por-run configurable en `run-brief` (default `claude-sonnet-4-6`, effort fijo `high`)

- **Objetivo:** permitir elegir el modelo para la corrida del brief/épica, con default
  explícito `claude-sonnet-4-6` y **effort siempre al máximo (`high`)**, sin posibilidad de
  bajarlo para este flujo.
- **Estado de partida (verificado):**
  - `run_agent` ya acepta `model_override` (`agent_runner.py:86`) y lo propaga al runner CLI.
  - El runner CLI rutea con `decide()` + `clamp_model` (`claude_code_cli_runner.py:630-647`):
    **cap duro — jamás opus/fable**, ni siquiera por override. El override admisible cae a
    sonnet como techo.
  - Default de modelo: `config.CLAUDE_CODE_CLI_MODEL = "claude-sonnet-4-6"` (`config.py:155`).
  - Effort: el CLI solo acepta `--effort low|medium|high` (`runner:1574-1575`). **No existe
    `max`/`maximum`.** El máximo real es `high`. Hoy el default es `medium` (`config.py:158`)
    y el adaptativo está OFF.
  - `run_brief` **NO** lee ningún `model`/`effort` del payload hoy (`agents.py:556-613`).
- **Cambios a aplicar (PEQUEÑOS, backend):**
  1. **`backend/api/agents.py`, función `run_brief` (≈ línea 556-613):**
     - `+` Leer modelo opcional del payload:
       ```python
       model_override = (payload.get("model") or "").strip() or None
       ```
     - `~` Pasar `model_override=model_override` en la llamada a `agent_runner.run_agent(...)`
       (junto a los kwargs ya presentes). Si el payload no trae `model`, queda `None` →
       el runner usa `config.CLAUDE_CODE_CLI_MODEL` (sonnet-4-6) como default. **Default
       explícito garantizado por el config existente; no se hardcodea en el endpoint.**
     - El cap `clamp_model` ya impide opus/fable aunque el operador mande un modelo prohibido:
       no hace falta validar en el endpoint (defensa en profundidad ya existe en el runner).
  2. **Effort fijo `high` SOLO para el flujo de brief.** Dos opciones; elegir la (a) por ser
     la de menor superficie:
     - **(a) recomendado** — pasar un `effort_override="high"` por la cadena
       `run_brief → run_agent → runner`. Requiere: añadir `effort_override: str | None = None`
       a la firma de `run_agent` (`agent_runner.py:77-96`) si no existe, propagarlo al runner, y
       que `run_brief` lo fije a `"high"`. El runner ya consume `effort_override` y gana sobre
       config (`runner:1509,1574`). **Verificar primero si `run_agent` ya expone `effort_override`;
       si sí, solo cablear desde `run_brief`.**
     - **(b) alternativa** — setear `CLAUDE_CODE_CLI_EFFORT=high` en el `.env` (global). Más
       simple pero afecta a TODOS los runs CLI, no solo al brief. Descartada salvo que el
       operador quiera effort `high` global.
  3. **Frontend (opcional, NO bloquea):** si el modal de brief (Plan 38) quiere un selector de
     modelo, agregar un `<select>` que mande `model` en el body de `POST /api/run-brief`. El
     default visible debe ser `claude-sonnet-4-6`. **No incluir selector de effort** (es fijo).
- **Test / comando exacto (TDD — escribir primero):** nuevo archivo
  `backend/tests/test_run_brief_model_override.py`:
  - **Test 1 (default):** `POST /run-brief` sin `model` → `run_agent` recibe
    `model_override=None` (mockear `agent_runner.run_agent`, assert sobre el kwarg). Documenta
    que el default cae al config sonnet-4-6.
  - **Test 2 (override válido):** body `{"brief": "...", "model": "claude-sonnet-4-6"}` →
    `run_agent` recibe `model_override="claude-sonnet-4-6"`.
  - **Test 3 (override prohibido se capa):** body con `"model": "claude-opus-..."` → tras
    pasar por el runner, `clamp_model` lo baja a sonnet (test unitario sobre `clamp_model`,
    NO end-to-end; reutiliza el test existente de `clamp_model` si lo hay).
  - **Test 4 (effort high):** assert de que `run_brief` fija el effort a `"high"` (sobre el
    kwarg pasado a `run_agent`, o sobre el comando `--effort high` que arma el runner si se
    testea el runner directamente).
  - Comando:
    ```
    cd "Stacky Agents/backend"
    .venv/Scripts/python.exe -m pytest tests/test_run_brief_model_override.py -q
    ```
  - **Patrón de mock (memoria del repo):** importar `db`/`agent_runner` a nivel de módulo y
    parchear los lazy-imports en el módulo de origen.
- **Criterio de aceptación (BINARIO):** los 4 tests pasan; sin `model` el override es `None`
  (default sonnet-4-6 vía config); con modelo prohibido el efectivo es sonnet; el effort del
  comando CLI para el brief es `high`.
- **Flag / default:** sin flag nuevo. Default de modelo = `claude-sonnet-4-6` (config existente,
  intacto). Effort del brief = `high` (fijo). **Operador:** ninguno (el selector es opcional).
- **Runtimes:** `model`/`effort` solo aplican al runtime **`claude_code_cli`** (Anthropic Pro).
  Para `codex_cli` el modelo lo gobierna `CODEX_CLI_MODEL`/denylist (`config.py:126,143`); para
  `github_copilot` lo gobierna el bridge. El endpoint acepta `model` siempre pero **solo el
  runtime CLI Claude lo honra**; los otros lo ignoran sin fallar (documentarlo así).

---

### B.4 Riesgos y mitigaciones

| ID | Riesgo | Mitigación |
|----|--------|------------|
| R1 | Cambiar el formato de salida rompe el desglose del FunctionalAnalyst (`<hr><h2>`). | Invariante DURO en el prompt + §B.6(a). F0 no lo cubre (es Python) → checklist obligatorio. |
| R2 | Al importar ideas del agente nuevo se reintroduce ADO/PowerShell. | Regla negativa explícita en el prompt + §B.6(c). |
| R3 | `stacky_requires_client_profile: false` permite correr sin perfil → épica genérica. | Deliberado: degradación elegante (M7). Ponerlo `true` rompería `run-brief` en proyectos sin perfil. Se documenta y mantiene `false`. |
| R4 | El agente se frena pidiendo confirmación. | Regla de autonomía (M6) + §B.6(d). |
| R5 | `db/query` con `{id}` del pool ticket (`ado_id=-1`) podría no resolver BD. | `db/query` es opcional y degradable; el prompt instruye a no abortar si falla. |
| R6 | **El operador manda un modelo prohibido (opus/fable) en `model`.** | `clamp_model` (runner) lo baja a sonnet — cap duro server-side. El endpoint no necesita validar. Cubierto por Test 3 de F3. |
| R7 | **"effort=max" se implementa como literal `max`** y rompe el flag CLI. | El máximo real es `high`; F3 lo fija a `high`. Cualquier valor fuera de `low\|medium\|high` el runner lo descarta (`runner:1575`). |
| R8 | **El selector de modelo en el frontend manda `model` a runtimes que no lo honran** (copilot/codex). | El backend ignora `model_override` para esos runtimes sin fallar; documentado en F3 (Runtimes). El selector, si se agrega, solo se muestra para `claude_code_cli`. |

---

### B.5 R-BATCH — Regla dura del prompt (Requisito 4, doble cara)

**(a) En la redacción de ESTE plan:** ningún punto dice "el proceso batch" en genérico. Donde
aplica, se nombra el proceso concreto o se marca como placeholder explícito.

**(b) Como regla del BusinessAgent (en el prompt, ver §C.4):** al generar briefs/épicas, el
agente **nunca** se refiere a "el batch"/"el proceso batch" sin nombrarlo. Debe:
- Usar el nombre real del job/servicio batch que aparezca en el brief o en la documentación
  funcional (p.ej. `FacturacionNocturna`, `CierreMensual`, `SyncCatalogos`).
- Si el brief menciona un proceso batch pero no su nombre, marcarlo
  `[PENDIENTE: nombre del proceso batch]` — **jamás dejarlo anónimo**.
- Esto es un ítem del checklist de calidad (§B.6 g): **0 menciones anónimas a "batch"**.

### B.6 Checklist de calidad de épica (gate verificable, reemplaza el KPI decorativo)

Sobre una épica de prueba generada con el prompt v1.1.0 (relectura o validación del operador
en el modal). Todos deben tildarse:

- **(a)** Emite bloques `<hr><h2>RF-XXX` bien formados (contrato intacto).
- **(b)** Frontmatter intacto salvo `version` (1.1.0); `stacky_requires_client_profile: false`
  documentado.
- **(c)** Cero integración ADO directa (sin PAT/WIQL/PowerShell/creación de Epic/`Procesados`).
- **(d)** Cero pasos interactivos; ambigüedad → `[SUPUESTO]` y sigue.
- **(e)** Genérico (cero "Pacífico/UCollect" salvo ejemplo entre paréntesis).
- **(f)** Degradación explícita si falta `client-profile`.
- **(g)** **0 menciones anónimas a "batch"/"proceso batch"** (R-BATCH); cada batch nombrado o
  marcado `[PENDIENTE]`.
- **(h)** Cada RF tiene **criterios de aceptación observables** (M10) y **módulo fuente citado**
  cuando se navegó documentación (M3).

---

## C. INTEGRACIÓN DE LOS 4 REQUERIMIENTOS

| Req | Qué pedía | Dónde se cumple en v2 | Estado |
|-----|-----------|------------------------|--------|
| **C.1 — Criticar y mejorar el plan** | Crítica explícita + mejora sustancial, realista, en 3 runtimes, sin carga al operador, HITL. | §A (crítica C1-C8) + §B (plan v2 con F0-F3 accionables, checklist §B.6, riesgos R1-R8). | **Hecho en este doc.** |
| **C.2 — `.agent.md` no gitignored** | Versionar los agentes; verificar lectura del runtime. | §B.3 F2: verificado que YA están versionados (`.gitignore:42-47`, `git ls-files` los lista); runtime lee de `backend/Stacky/agents/`. | **Verificado.** No requería cambio; `.gitignore` ya correcto. |
| **C.3 — Modelo configurable, default sonnet-4-6, effort máximo** | Poder cambiar el modelo; default `claude-sonnet-4-6`; effort máximo fijo. | §B.3 F3: `run_brief` lee `model` → `model_override`; default cae a `config.CLAUDE_CODE_CLI_MODEL` (sonnet-4-6); effort fijo `high` (máximo real del CLI). Cap `clamp_model` impide opus/fable. | **Pasos concretos (no implementado aún).** |
| **C.4 — Nombrar siempre el batch concreto** | (a) en el plan; (b) como regla del agente. | §B.5 R-BATCH (regla dura del prompt, M9) + §B.6(g) (checklist). En el prompt: añadir R-BATCH a las reglas críticas y reforzar criterios medibles (M10). | **Pendiente de aplicar en el prompt (pequeño).** |

---

## D. Fuera de scope

- Telemetría automática de calidad de épica (el KPI se valida por checklist §B.6, no por
  instrumentación — decisión honesta vs el plan v1).
- Desglose funcional módulo-a-módulo, cobertura y `pending-task.json` → es del FunctionalAnalyst.
- Numeración/ID de la Épica (lo gobierna Stacky; el agente numera RF local `RF-001..RF-NNN`).
- RBAC / multiusuario (Stacky es mono-operador).
- Selector de modelo en el frontend (opcional en F3; no bloquea).
- Modelo/effort para runtimes `codex_cli` y `github_copilot` (gobernados por su propia config).

## E. Glosario

- **Brief Pool Ticket:** ticket local `ado_id=-1` por proyecto que ancla la corrida del brief.
- **`client-profile`:** context block con terminología, índices de docs y config de BD del
  proyecto activo. Puede faltar.
- **RF-XXX:** requerimiento funcional, un bloque `<hr><h2>RF-XXX` en el HTML de la épica.
- **Human gate:** aprobación del operador en el modal de épica (Plan 38). NO es el agente frenándose.
- **`clamp_model`:** cap duro del runner CLI; jamás deja correr opus/fable aunque el override lo pida.
- **Effort máximo:** `high` (techo real del CLI Claude Code; no existe `max`).
- **R-BATCH:** regla que prohíbe referirse a "el batch" sin nombrar el proceso concreto.

## F. Orden de implementación

1. **F0** — gate de no-regresión (`pytest test_run_brief_*`).
2. **F1** — prompt v1.1.0 (ya aplicado) + añadir R-BATCH y reforzar criterios medibles.
3. **F2** — verificar versionado de `.agent.md` (`git check-ignore` / `git ls-files`).
4. **F3** — wiring de `model_override` + effort `high` en `run_brief` (TDD con el test nuevo).
5. Validar §B.6 sobre una épica de prueba.

---

## Checklist de aceptación del plan

- [x] Numeración consecutiva (40, siguiente libre tras `39_*`).
- [x] **Crítica explícita** del plan v1 con defectos C1-C8 y su corrección.
- [x] Análisis del gap con archivos/símbolos reales citados (`agents.py:544`, `agent_runner.py:86`,
      `config.py:155/158`, `claude_code_cli_runner.py:630-647/1574-1575`, `.gitignore:42-47`).
- [x] Fases F0..F3 con archivo exacto, claves/líneas, pseudo-diff, test + comando con venv,
      criterio binario, flag + default, impacto por runtime + fallback, y "Operador: ninguno".
- [x] Req 2 resuelto con evidencia (`.agent.md` ya versionados; nada que un-ignorar).
- [x] Req 3 aterrizado al código real (default sonnet-4-6 vía config; effort máximo = `high`;
      cap `clamp_model`).
- [x] Req 4 como regla dura del prompt (R-BATCH) + ítem de checklist; y respetado en este doc.
- [x] Riesgos R1-R8 + mitigaciones, Fuera de scope, Glosario, Orden, Checklist de calidad §B.6.
- [x] Compatible con los 3 runtimes (prompt + fallbacks; modelo/effort solo honrado por CLI Claude).
- [x] No agrega trabajo al operador; backward-compatible con `run-brief`/`from-brief` y Plan 39.
- [x] Human-in-the-loop preservado (gate = aprobación del operador en el modal).
