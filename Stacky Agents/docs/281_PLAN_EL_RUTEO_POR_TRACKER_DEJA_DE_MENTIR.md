# Plan 281 — El ruteo por tracker deja de mentir

**Estado:** **IMPLEMENTADO F0..F9** (2026-08-01) — v2 MEJORADO (v1 -> v2)
**Veredicto de la crítica v1:** **RECHAZADO** (4 BLOQUEANTES) ⇒ corregido en esta versión
**Fecha:** 2026-08-01
**Rama sugerida:** `docs/plan-281`
**Rama real:** `docs/plan-279` (el árbol ya estaba ahí, con una sesión paralela viva)

> ### Registro de implementación — 2026-08-01
>
> Commits (sin push): `dedc2d0b` F0..F6 · `9f20adf0` F7 · `4c57f918` F8+F9.
>
> **Conteos REALES medidos**, contra las predicciones del plan:
>
> | Fase | Predicción | Medido | |
> |---|---|---|---|
> | F0 | `6 passed` + foto vieja `10/4/18/8/4` | `6 passed`, foto **exacta al primer intento** | ✔ |
> | F1 | `1 passed, 3 failed` | `1 passed, 3 failed` | ✔ |
> | F2 | back `2 passed, 2 failed`; front `previo+2` | `2 passed, 2 failed`; vitest **31 → 33** | ✔ |
> | F3 | `5 passed` | `5 passed` | ✔ |
> | F4 | `8 passed`, ciegos 4→3 | `8 passed`, ciegos 4→3 | ✔ |
> | F5 | `11 passed`, ciegos 3→2 | `11 passed`, ciegos 3→2 | ✔ |
> | F6 | `13 passed`, ciegos 2→1, routing `[]` | `13 passed`, ciegos 2→1, routing `[]` | ✔ |
> | F7 | `16 passed`, censo `0 2 1` | **`18 passed`**, censo `0 2 1` | ✔ +2 |
> | F8 | `6 passed` | `6 passed`, calibración verde al primer intento | ✔ |
> | F9.1 | `11 passed` | `11 passed` | ✔ |
>
> **Desvíos declarados** (ninguno cambia un criterio binario):
> 1. **F7 sitio 5** — el guard va antes del **Modo B**, no en la cabecera: el Modo A
>    (Epic en estado de entrada válido) **no toca ADO**, y gatearlo arriba lo degradaría
>    para GitLab. El censo mide igual.
> 2. **F9.2 lugar 4** — `deployment/harness_defaults.env` **no se editó a mano**: su
>    generador toma un *snapshot del `.env` de un deploy VIVO*, no un dump del registry.
>    Ninguna flag del 276/277/278 está ahí y no hay test de paridad. Regenerarlo contra
>    el deploy es tarea del operador.
> 3. **R9 del plan es incorrecto**: `_resolve_criteria` tiene **DOS** callers, no uno
>    (`self_review.review_artifact` y `acceptance_contract._get_criteria_text`). El
>    segundo cae a `getattr(ticket,"acceptance_criteria","")`, pero `models.py` **no
>    tiene esa columna**: el fallback es inerte y el valor neutro `""` es seguro.
> 4. Tras F4, `app.py::_startup_sync` no sólo deja de ser ciego: **sube a `con_seam`**
>    (resuelve el provider). El caso migrado en F9.1 lo asserta así.
> 5. **F7 son 18 casos, no 16.** El plan promete que con la flag apagada "los guards no
>    cortan", pero **no testeaba esa promesa** — habría quedado como verde sin verificar.
>    Se agregan 2 casos que la corren contra su promesa (flag OFF ⇒ el guard revierte y
>    se vuelve a construir el cliente; y el default EFECTIVO se lee sin parchear nada).
>    Para que el rollback sea real, los 8 guards quedaron gateados por la flag mediante
>    un único helper, `project_context.ruteo_estricto_por_tracker()`: ocho copias del
>    `getattr` serían ocho oportunidades de errarle al estilo de lectura, y ese archivo
>    está excluido del censo, así que no altera los conteos.
>
> **Rojos ajenos preexistentes, PROBADOS contra el commit padre `32a9b719`:**
> `test_plan218_coupling_ratchet` (3 failed; ya 42/109/21 vs baseline 36/82/19 — el
> aporte neto de este plan a ese censo es **−2**) y `test_autopublish_rescue`
> (4 failed / 7 passed idéntico; revienta en `published.rev`, código del Plan 153 F4).
>
> **Pendiente:** sólo el smoke manual de §F9.4 (exige backend levantado y token GitLab).
**Depende de:** 218 (censo de acoplamiento), 276 (GitLab self-hosted), 277 (jerarquía), 278 (publicador de épica)
**Convive con:** el fix SIN COMMITEAR del guard anti-doble-publicación de épica (ver §0)

---

## CHANGELOG v1 -> v2

Toda corrección de esta versión salió de **medir el repo**, no de releer el plan. Los comandos que
produjeron cada número están en la fase correspondiente para que se puedan re-correr.

| C# | Sev. | Qué estaba mal en v1 | Cómo quedó en v2 |
|---|---|---|---|
| **C1** | BLOQ | **F0 era insatisfacible.** Con el alcance de F0 (que **incluye `app.py`**) el censo mide **32 = 18 con seam / 4 gateados / 10 ado-only**, no `31 = 18/3/10`. `app.py::_startup_sync` cae en **gateados** (tiene los literales `"jira"`/`"mantis"`/`"azure_devops"` **y** llama `resolve_project_context`), así que el caso `test_censo_incluye_app_py` (`"app.py::_startup_sync" in ado_only`) **falla por construcción**, y es además aritméticamente imposible que app.py esté en `ado_only` y que `ado_only_count` siga siendo 10 | §4.5/§4.6 separan explícitamente los **dos alcances**; el contrato de F0 declara `gateados_count = 4`; el caso pasa a `test_app_py_es_gateado_pero_ciego_a_gitlab`; se agrega la métrica **`ciegos_a_gitlab`** (medida: **4**), que es la que SÍ detecta el defecto de `_startup_sync` de forma determinista |
| **C2** | BLOQ | **F7 sitio 3 rompía el Plan 278.** El "valor neutro" `{"published": False, "reason": "tracker_sin_publicador"}` es de **tipo incorrecto** (la función devuelve `_AutopublishResult`, un NamedTuple) y, puesto al principio de la función, **cancelaría la publicación de épicas en GitLab**, que es justo lo que el 278 habilitó | El `build_ado_client` real está en **`api/tickets.py:7564`**, dentro de un `try/except` que sólo sella `System.Rev`. Se gatea **ese bloque**, no la función. Valor neutro real: `_baseline_rev = None` |
| **C3** | BLOQ | **El detector de F8.3 y el DoD eran insatisfacibles.** Recorrer `ast.BoolOp` como dice v1 devuelve **4 sitios**, no 1: los 3 extra son la **clave compuesta de identidad del Plan 277** (`_clave:655`, `_clave_de_padre:661`, `_crea_ciclo:694`) y son legítimos. Y quitar `BoolOp` deja el detector en **0**, porque en `run_ticket_refresh` la comparación es contra una **variable local** | Detector reespecificado con **data-flow intra-función + exclusión por origen** (§F8.3). **Medido: devuelve exactamente 1** — `run_ticket_refresh.py::refresh_ticket_snapshot` |
| **C4** | BLOQ | **F7 sitio 2: valor neutro falso y regresivo.** `""` no es lo que devuelve su `except`: éste hace `eq_ado = None` y **sigue**, con retorno efectivo `"unknown"`. El contrato del consumidor son exactamente 3 valores (`exists`/`missing`/`unknown`, docstring `tickets.py:4491-4495`); `""` es un cuarto valor que nadie maneja y reabre el caso ADO-241 | Valor neutro corregido a **`"unknown"`**; y se declara que el sitio 2 **ya está funcionalmente protegido** (§F7 nota) |
| **C5** | IMP | **F7 sitio 6: `_resolve_criteria` NO TIENE `except`.** v1 afirmaba que `""` "ya es el fallback de su `except`" | Se declara el cambio real (**de excepción propagada a no-op**) y se agrega el caso de no-regresión que lo cubre |
| **C6** | IMP | **F1 caso 1 se contradecía.** Assertaba el defecto (`is None`) y a la vez se esperaba **ROJO**; y F2 exigía que quedara **verde**. Un test que asserta lo que el código hace hoy está verde hoy | El caso asserta el comportamiento **deseado** (`== "RIPLEY"`) y se renombra. El criterio `1 passed, 3 failed` se conserva y ahora **es alcanzable** |
| **C7** | IMP | **Los lugares de la flag son 6, no 5.** Faltaba el **consumidor** (`test_flag_wiring.py` marca "flag placebo" si la key no aparece como literal fuera del registry) y, sobre todo, **cómo leerla** | §F9.2 pasa a 6 lugares y fija la **regla de lectura asimétrica**: `config.config` en `api/`+`services/`, `config` a secas en `app.py` |
| **C8** | IMP | F7 sitio 5: el retorno real incluye `warnings=[...]`; v1 lo omitía | Valor neutro completo en la tabla |
| **C9** | IMP | v1 presentaba el sitio 2 como un fix real | Declarado como **cosmético para el gate** |
| **C10** | MEN | Drift de anclajes | Corregidos: `completion_sync` dispatch **109-114** (era 107-112) y su `except` en **118** (era 116); `useTicketSync.ts` headers **122-124** (era 120-123); ratchet `.sh` bloque 276 en **244** (era 242); `completion_sync` gateado en **93** (era 92) |
| **C11** | MEN | No registraba huella de regresión | §F9.5 con el **schema real** de `error_fingerprints.json` |
| **C12** | MEN | F6 no declaraba la flag que gatea la función bajo test | Declarado en el fixture |
| **C13** | MEN | v1 llamaba "tolerados" a los 3 gateados sin decir que son **ciegos a GitLab** | Medido y declarado (§4.5b) |

**Adiciones proactivas:** `[ADICIÓN ARQUITECTO]` en §F8.3 (detector con data-flow, validado) y §F0
(métrica `ciegos_a_gitlab`).

---

## 1. Objetivo

Un proyecto GitLab tiene que dejar de recibir errores de Azure DevOps.

Hoy, con RIPLEY (tracker `gitlab`, verificado en `backend/projects/RIPLEY/config.json` →
`issue_tracker.type = "gitlab"`) abierto en la vista de ticket-grafo, el operador ve cada
tanto el cartel:

```
El proyecto 'RIPLEY' no usa Azure DevOps (tracker_type=gitlab).
```

Ese texto nace en **un solo lugar** — `backend/services/project_context.py:340-343`, dentro de
`build_ado_client()` (verificado) — y llega a la pantalla porque algún camino de ejecución pidió un
cliente de Azure DevOps para un proyecto que no usa Azure DevOps. El plan cierra las tres puntas:

1. **El bug determinista y su intermitencia**: por qué aparece "cada un tiempo" y no siempre.
2. **La erradicación de los sitios ADO-only**: los lugares que construyen cliente ADO sin
   preguntar de qué tracker es el proyecto.
3. **El contrato de ruteo por tracker**, convertido en **gate por AST** que no deja volver atrás.

### KPI (todos medibles con un comando)

| # | KPI | Hoy (**medido** 2026-08-01, ver §4.5) | Meta al cerrar el plan |
|---|---|---|---|
| K1 | Funciones que construyen cliente ADO **sin** seam de provider **y sin** guard de tracker | **10** | **2** (las 2 legítimas: el constructor y la sonda de ADO) |
| K2 | Funciones que discriminan por tracker pero **son ciegas a GitLab** (`ciegos_a_gitlab`) | **4** | **1** (sólo `api/projects.py::get_tracker_states`, fuera de scope y declarado) |
| K3 | `POST /api/tickets/sync-v2` que llegan al backend **sin** nombre de proyecto | **100 %** de los `auto_poll` y `startup` | **0 %** |
| K4 | Módulos `services/<tracker>_sync.py` cuyo dispatch dinámico rompe por firma | **1** (`gitlab_sync`) | **0** |
| K5 | Funciones que **rutean** con `ticket.tracker_type` (`scan_tracker_type_routing`) | **1** (`run_ticket_refresh.py:43-44`) | **0** |

> **K2 cambió respecto de v1.** v1 lo definía como "sitios ADO-only fuera de `api/` y `services/`",
> con valor `1` (`app.py:203`). Ese enunciado es **incompatible con el censo de F0**: con la
> heurística de guards del propio plan, `_startup_sync` **no** clasifica como ADO-only (C1). La
> métrica `ciegos_a_gitlab` mide **el mismo defecto** de forma determinista y verificable.

---

## 2. Por qué ahora / gap que cierra

El plan 276 arregló el sync de GitLab; el 277 arregló la jerarquía; el 278 unificó el publicador de
épica **entre runtimes**. Ninguno de los tres cerró la pregunta transversal: *¿quién decide, en cada
punto del backend, si este proyecto habla ADO o GitLab?*

La respuesta hoy es "depende del sitio", y esa es exactamente la falla. Hay **tres** criterios de
ruteo conviviendo (los tres anclajes verificados abriendo el archivo):

| Criterio | Dónde vive | ¿Confiable? |
|---|---|---|
| `tracker_is_azure_devops(project_name)` — lee `issue_tracker.type` del config del proyecto | `services/project_context.py:46` ✔ | **SÍ — es el canónico** |
| `_provider_for_ticket(...)` — el seam de provider | `api/tickets.py:414` ✔ | SÍ (se apoya en el anterior) |
| `ticket.tracker_type` — la columna de la fila | `services/run_ticket_refresh.py:43` ✔ | **NO — miente** |

El propio docstring del resolvedor canónico ya lo dice, textual, en
`services/project_context.py:49-53` (v1 decía 50-55; corregido):

> Deliberadamente NO mira `ticket.tracker_type`: la columna tiene default `azure_devops` y las filas
> sintéticas (Brief Pool Ticket, `api/agents.py:777-785`) se crean sin ese campo, así que MIENTEN
> para cualquier proyecto no-ADO.

La regla ya está escrita. Lo que falta es **hacerla cumplir en todos lados y clavarla con un gate**.

### El eslabón que conecta esto con el trabajo en vuelo

El fix sin commitear de `_persist_epic_ticket` (§0) existe justamente porque las filas de épica de
GitLab nacían con `tracker_type = 'azure_devops'` (el default de la columna, `models.py:49`). Es
decir: **la columna no sólo es un criterio de ruteo arquitectónicamente incorrecto, además está de
hecho mal poblada en la base del operador**. Cualquier guard que la lea hereda esa mentira.

---

## 0. Estado del árbol al escribir este plan (LEER ANTES DE TOCAR NADA)

Hay **archivos modificados sin commitear** en la rama `docs/plan-279`. Los del dominio de este plan
NO se pueden pisar ni revertir. Verificado con `git diff` al escribir la v2:

| Archivo | Qué contiene (verificado en el diff) |
|---|---|
| `Stacky Agents/backend/api/tickets.py` | `_persist_epic_ticket` upsertea por la **terna** `(stacky_project_name, tracker_type, external_id)` en vez de `ado_id` pelado; `_publish_epic_to_ado` normaliza `iid`/`id`, sella `tracker_type` desde `_provider.name` y prefiere `web_url`; se agrega `_epic_ya_publicada_payload` |
| `Stacky Agents/frontend/src/services/uiGuards.ts` | `sealedWorkItemId()` — guard anti-doble-publicación que acepta `number` **y** `string` |
| `Stacky Agents/frontend/src/components/EpicFromBriefModal.tsx` | consume ese guard |
| `Stacky Agents/backend/tests/test_plan276_gitlab_sync.py` | tests del fix anterior |

> **CONSECUENCIA DE ANCLAJE (nueva en v2):** ese diff **inserta ~90 líneas dentro de
> `api/tickets.py` en la zona 7097-7230**. **Todos los anclajes de línea de `api/tickets.py` de este
> plan están tomados sobre el ÁRBOL DE TRABAJO SUCIO, no sobre `HEAD`.** Si alguien commitea,
> descarta o reordena ese diff, los anclajes ≥ 7097 se corren. **Anclá siempre por SÍMBOLO**
> (`autopublish_epic_from_run`, `_equivalent_task_status`) y usá la línea sólo como pista.

**Regla dura para quien implemente este plan:** está PROHIBIDO `git stash`, `git reset`, `git
checkout --` y `git commit -a`. Los commits se hacen con pathspec explícito
(`git commit -- "<ruta>"`), nunca con `-a`. Antes de empezar, correr `git status --porcelain` y
guardar la lista; al terminar, compararla y verificar que **ninguna ruta previa quedó revertida**.

Este plan es **coherente** con ese trabajo: el fix de la épica arregla que las filas **nuevas**
nazcan con el `tracker_type` correcto; este plan arregla que **nadie rutee mirando esa columna**,
que es lo que hace que las filas viejas (mal pobladas) sigan siendo peligrosas.

---

## 3. Principios y guardarraíles

- **Human-in-the-loop innegociable.** El plan no agrega ninguna decisión automática nueva. Corrige
  ruteo; no publica, no escribe en el tracker del operador, no borra nada.
- **Mono-operador sin auth real.** Nada de RBAC. Un `403` sigue significando "flag apagada".
- **Toda flag/config del operador va por UI.** La única flag nueva se registra en el panel del arnés
  (los **6** lugares de §F9.2).
- **3 runtimes con paridad.** Todo el cambio es backend Python + un header en el frontend. **Ningún**
  ítem toca el runtime del agente (Codex CLI / Claude Code CLI / GitHub Copilot Pro). El impacto por
  runtime es idéntico y se declara fase por fase.
- **Cero trabajo para el operador.** No hay pasos manuales nuevos ni config nueva que cargar; es
  backward-compatible.
- **Reusar, no reinventar.** El censo NO se escribe de cero: se **extiende**
  `services/provider_coupling_audit.py` (Plan 218 F1), que ya tiene ratchet, baseline en
  `tests/provider_coupling_baseline.json` (verificado que existe) y dos allowlists.
- **El gate se corre CONTRA el defecto.** Ninguna fase se declara verde sin haber visto el test
  **rojo** con el código viejo. En v2 esto se aplicó también **a la crítica**: cada número de este
  documento se re-midió con `backend/venv` antes de escribirlo.

---

## 4. Diagnóstico verificado

### 4.1 De dónde sale el mensaje

`backend/services/project_context.py:331-343` (anclaje verificado; la firma real es multilínea):

```python
def build_ado_client(
    project_name: str | None = None,
    *,
    tracker_project: str | None = None,
    ticket=None,
):
    from services.ado_client import AdoClient, AdoConfigError

    ctx = require_project_context(project_name, tracker_project=tracker_project, ticket=ticket)
    if ctx.tracker_type != _DEFAULT_TRACKER_TYPE:                       # ← 340
        raise AdoConfigError(                                           # ← 341
            f"El proyecto '{ctx.stacky_project_name}' no usa Azure DevOps (tracker_type={ctx.tracker_type})."
        )
```

El mensaje es **correcto**: `build_ado_client` hace bien en negarse. El defecto está **aguas arriba**,
en quien la llama sin haber preguntado el tipo de tracker.

### 4.2 Por qué se ve en la vista de grafo, y por qué "cada un tiempo"

La vista de grafo (`frontend/src/components/TicketGraphView.jsx`) **no tiene temporizador propio** y
su endpoint de datos, `GET /api/tickets/hierarchy` (`api/tickets.py:735`), es **DB pura**. El error
**no viene del grafo**; viene de un poll que late en la misma pantalla, montado por la página host
`TicketBoard.tsx`. Los tres anclajes **verificados**:

| Origen | Intervalo | Endpoint |
|---|---|---|
| `frontend/src/hooks/useTicketSync.ts:243` (`setTimeout` recursivo, backoff ×2 hasta 300 000 ms) ✔ | **45 000 ms** | `POST /api/tickets/sync-v2` |
| `frontend/src/hooks/useTicketSync.ts:225` ✔ | 1 500 ms (una vez, al montar) | `POST /api/tickets/sync-v2` |
| `frontend/src/hooks/useTicketSync.ts:274` (`visibilitychange`) ✔ | por evento | `POST /api/tickets/sync-v2` |

Y `api/tickets.py:6475-6478` (verificado, literal) traduce el `AdoConfigError` a **HTTP 400**:

```python
    except AdoConfigError as e:                                          # ← 6475
        _sync_in_progress_by_project.discard(sync_scope)
        logger.warning("ADO sync-v2 — config: %s", e)
        return jsonify({"ok": False, "error": "config", "message": str(e)}), 400
```

`useTicketSync` rutea `{ok:false, message}` a `setSyncError`, así que el operador **lo ve en
pantalla**. Cada 45 s. Eso es el "cada un tiempo".

### 4.3 La causa raíz de la intermitencia — **VERIFICADA EMPÍRICAMENTE en v2**

`frontend/src/hooks/useTicketSync.ts:122-131` (v1 decía 120-123; corregido):

```ts
      const headers: Record<string, string> = {   // ← 122
        "X-Stacky-Trigger": trigger,              // ← 123
      };                                          // ← 124
      return fetch(
        `${apiBase}/api/tickets/sync-v2`,
        {
          method: "POST",
          headers,
          body: JSON.stringify(activeProjectName ? { project: activeProjectName } : {}),
        }
      )
```

**El body viaja, pero `headers` NO incluye `Content-Type: application/json`.** Con `fetch` y un body
de tipo string, el navegador rellena `Content-Type: text/plain;charset=UTF-8`, que **no** es JSON.

> **Prueba empírica (v2).** Corrida con el Flask instalado en `backend/venv` (**Flask 3.0.3**,
> Python 3.11.9), con `test_client()`:
>
> | Caso | `get_json(silent=True)` | `get_json(silent=True, force=True)` |
> |---|---|---|
> | body JSON, **sin** content-type | **`None`** | `{'project': 'RIPLEY'}` |
> | body JSON, `content_type="text/plain;charset=UTF-8"` (lo que manda el navegador) | **`None`** | `{'project': 'RIPLEY'}` |
> | body JSON, `content_type="application/json"` | `{'project': 'RIPLEY'}` | — |
> | body **no-JSON**, `force=True` | — | **`None`** (backward-compat de R4 confirmada) |
> | body **vacío**, `force=True` | — | **`None`** |
>
> La afirmación central del plan queda **CONFIRMADA**, y la mitigación R4 también: `force=True`
> **sólo agrega** casos que antes daban `None`; ningún body basura empieza a parsear.

Por lo tanto, en `api/tickets.py:288-296` (anclaje verificado, literal):

```python
def _request_project_name() -> str | None:                     # ← 288
    project = (request.args.get("project") or "").strip()
    if project:
        return project
    if request.method in {"POST", "PUT", "PATCH"}:
        body = request.get_json(silent=True) or {}             # ← 293 · None ⇒ {}
        body_project = (body.get("project") or "").strip()
        return body_project or None
    return None
```

…**`sync-v2` recibe `project_name = None` en el 100 % de los polls automáticos.** El nombre de
proyecto que el frontend sí calculó y sí serializó **nunca llega**.

Con `project_name = None`, el ruteo pasa a depender del **proyecto activo global**
(`get_active_project()`, un archivo en disco: `backend/data/active_project.json`). De ahí la
intermitencia: el mismo poll acierta o falla según un global mutable, no según la pantalla.

### 4.4 El fallo cerrado que convierte "no sé" en "es ADO"

`api/tickets.py:1153-1156` (anclaje verificado, literal), dentro de `_sync_via_provider_or_ado`:

```python
    if provider is None:                                                        # ← 1153
        ctx_sync = resolve_project_context(project_name)                        # ← 1154
        tipo = (getattr(ctx_sync, "tracker_type", None) or "azure_devops").strip().lower()  # ← 1155
        if ctx_sync is not None and tipo != "azure_devops":                     # ← 1156
```

El `getattr` se evalúa **antes** del chequeo de `None`. Si `ctx_sync is None`, `tipo` cae a
`"azure_devops"` por el `or`, la condición falla, `provider` sigue en `None` y la ejecución termina
en la línea **1188** (verificada por grep exacto):

```python
    return sync_tickets(client=_ado_client_for_ticket(project_name=project_name))  # ← 1188
```

…que construye un cliente ADO. **"No pude resolver el contexto" se traduce silenciosamente a "es
Azure DevOps".** Ese es el patrón que hay que erradicar.

El mismo fallo cerrado existe, deliberadamente, en `tracker_is_azure_devops`
(`services/project_context.py:64-66`): sin `project_name` devuelve `True`. Ahí es **correcto** (es un
gate de compatibilidad), pero significa que pasarle `None` equivale a decir "es ADO".

### 4.5 Censo de sitios ADO-only — **RE-MEDIDO en v2**

> Los números de v1 eran correctos **para el alcance de §4.5** (sin `app.py`) y **contradecían el
> alcance de F0** (con `app.py`). v2 declara los dos por separado. Ésta es la corrección C1.

**Alcance A — `backend/api/*.py` + `backend/services/*.py`**, excluyendo la familia
`services/ado_*.py` (un adaptador ADO tiene derecho a ser ADO-only) y `services/project_context.py`
(es el constructor):

```
Funciones que construyen cliente ADO           : 31
  con seam de provider (_provider_for_ticket)  : 18   ← ya correctas
  sin seam                                     : 13
    gateadas por tipo de tracker (toleradas)   :  3
    SIN NINGÚN GUARD → ADO-ONLY DURAS          : 10
```

**Alcance B — el de F0: Alcance A + `backend/app.py`** (medido con el mismo detector):

```
Funciones que construyen cliente ADO           : 32
  con seam de provider                         : 18
  sin seam                                     : 14
    gateadas por tipo de tracker               :  4   ← app.py::_startup_sync entra ACÁ, no en ado_only
    SIN NINGÚN GUARD → ADO-ONLY DURAS          : 10
  violaciones (ado_only − justificados)        :  8
```

Las 10 duras, **con anclaje verificado abriendo cada archivo** (líneas de `def`, todas confirmadas):

| # | Anclaje | Símbolo | `build` en línea | Veredicto |
|---|---|---|---|---|
| 1 | `backend/api/agents.py:1798` ✔ | `_build_ado_enrichment_sections` | 1821 | **VIOLACIÓN** |
| 2 | `backend/api/tickets.py:363` ✔ | `_ado_client_for_ticket` | 365/371/372 | **legítimo** — ES el constructor del cliente ADO |
| 3 | `backend/api/tickets.py:4912` ✔ | `_equivalent_task_status` | 4919 | **VIOLACIÓN (cosmética — ver §F7 nota C9)** |
| 4 | `backend/api/tickets.py:7342` ✔ | `autopublish_epic_from_run` | **7564** | **VIOLACIÓN** |
| 5 | `backend/services/acceptance_criteria.py:25` ✔ | `resolve` | 34 | **VIOLACIÓN** |
| 6 | `backend/services/business_preflight.py:37` ✔ | `_evaluate_functional` | 86 | **VIOLACIÓN** |
| 7 | `backend/services/local_diagnostics.py:175` ✔ | `_probe_ado` | 178 | **legítimo** — sondea ADO a propósito |
| 8 | `backend/services/self_review.py:43` ✔ | `_resolve_criteria` | 46 | **VIOLACIÓN** |
| 9 | `backend/services/similar_tickets.py:91` ✔ | `find_similar_tickets` | 129 | **VIOLACIÓN** |
| 10 | `backend/services/ticket_assigner.py:356` ✔ | `auto_assign_on_run` | 404 | **VIOLACIÓN** |

⇒ **8 violaciones reales.** (Este número de v1 **se confirmó**.)

### 4.5b Los 4 gateados, y por qué "gateado" no es "correcto" — **NUEVO en v2 (C13)**

Los 4 que construyen cliente ADO pero **sí** preguntan primero por el tipo de tracker:

| Sitio | Literales de tracker que menciona | Guard | ¿Menciona `"gitlab"`? |
|---|---|---|---|
| `api/projects.py:900` `get_tracker_states` (gate en 954) | `azure_devops`, `jira`, `mantis` | — | **NO** |
| `app.py:99` `_startup_sync` (build en 203) | `azure_devops`, `jira`, `mantis` | `resolve_project_context` | **NO** |
| `services/completion_sync.py:82` `_do_project_sync` (gate en **93**, v1 decía 92) | `azure_devops` | — | **NO** |
| `services/run_ticket_refresh.py:21` `refresh_ticket_snapshot` (gate en 44) | `azure_devops` | — | **NO** |

**Los 4 son ciegos a GitLab.** Ésa es la señal — determinista, medible por AST — que captura el
defecto real de `_startup_sync` que v1 quería expresar con K2 y no podía. Métrica
`ciegos_a_gitlab = 4` hoy.

### 4.6 El sitio que el censo del 218 NO ve — y por qué el censo de F0 tampoco lo marca ADO-only

`backend/app.py:196-221`, dentro de `_startup_sync` (verificado leyendo la función completa):

```python
    else:
        # Azure DevOps
        ...
        client = build_ado_client(project_name=active) if active else None   # ← 203
        result = _ado_sync(client=client)
        ...
        except AdoConfigError as e:
            logger.warning("sync ADO saltado: %s", e)
```

`_startup_sync` **discrimina** `jira` / `mantis` / *resto*, y GitLab cae en el `else` de ADO. Con un
proyecto GitLab activo, el sync de arranque **muere en `AdoConfigError` y se traga el error como un
`warning`**. Consecuencia medible: **los proyectos GitLab nunca se sincronizan al arrancar.**

> **CORRECCIÓN C1.** v1 llamaba a esto "la novena violación" y hacía que F0 lo exigiera dentro de
> `ado_only`. **Es imposible**: la heurística de F0 (deliberadamente laxa: literales de tracker
> **o** guards conocidos) lo perdona por partida doble — `_startup_sync` menciona `"jira"`,
> `"mantis"` y `"azure_devops"`, **y** llama `resolve_project_context`. Endurecer la heurística para
> atraparlo la volvería agresiva y llenaría el censo de falsos positivos.
> **La señal correcta es `ciegos_a_gitlab`** (§4.5b): discrimina por tracker y **no** contempla
> GitLab. Es exacta, no perdona a `_startup_sync`, y no rompe nada más.

### 4.7 Dos defectos adyacentes, verificados, dentro del alcance

**(a) El dispatch dinámico de `completion_sync` está roto para GitLab.**
`backend/services/completion_sync.py:109-114` (v1 decía 107-112; **corregido**, verificado por grep):

```python
        else:
            # Jira y Mantis NO aceptan project_name: su entrada es tracker_config.
            from importlib import import_module          # ← 109

            mod = import_module(f"services.{tracker_type}_sync")                        # ← 111
            result = mod.sync_tickets(tracker_config=_tracker_config_for(project)) or {} # ← 114
```

Pero `backend/services/gitlab_sync.py` **no tiene `sync_tickets`**. Su única función pública es
`sync_gitlab_tickets(project_name, *, provider=None)` (línea **235** ✔; `__all__` en la línea
**410** ✔ lista exactamente una entrada). Verificado por comparación de firmas:

| Módulo | ¿`sync_tickets`? | Firma |
|---|---|---|
| `services/ado_sync.py` | sí | `(client=None, project_name=None)` |
| `services/jira_sync.py` | sí | `(client=None, tracker_config=None)` |
| `services/mantis_sync.py` | sí | `(...)` |
| `services/gitlab_sync.py` | **NO** | — |

⇒ Para GitLab, `_do_project_sync` levanta `AttributeError`, que el `except Exception` de la línea
**118** (v1 decía 116; corregido) se traga como best-effort. **El sync post-completación nunca corre
en GitLab, en silencio.**

**(b) `run_ticket_refresh` rutea por la columna que miente.**
`backend/services/run_ticket_refresh.py:43-45` (anclaje verificado, literal):

```python
        tracker_type = ticket.tracker_type or "azure_devops"          # ← 43
        if tracker_type != "azure_devops":                            # ← 44
            return {"refreshed": False, "reason": "non_ado_tracker"}  # ← 45
```

Es el patrón prohibido. Una fila de GitLab creada antes del fix de §0 tiene
`tracker_type = 'azure_devops'` ⇒ el guard la deja pasar ⇒ `build_ado_client` en la línea **54** ✔ ⇒
`AdoConfigError`. Se traga en el `except` de la línea 64, pero deja el snapshot sin refrescar.

> **Contexto de flag (C12):** la función entera está gateada por
> `STACKY_RUN_TICKET_REFRESH_ENABLED`, cuyo **default efectivo es `"true"`** (`config.py:979`,
> verificado). Se lee con `getattr(config, ..., False)` — el `False` es sólo el fallback del
> `getattr`, no el default. **El bug SÍ se ejecuta hoy.**

---

## 5. Fases

> **Comando base de tests** (todas las fases). Desde `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend`:
> ```
> ./venv/Scripts/python.exe -m pytest tests/<archivo>.py -v
> ```
> El venv correcto es **`backend/venv`** (Python **3.11.9**, Flask **3.0.3** — verificado). Existe
> otro, `backend/.venv`; **no se usa**.
>
> **Correr SIEMPRE por archivo.** `pytest tests` entero NO es un veredicto (contaminación cruzada
> conocida). El gate agregado es `scripts/run_harness_tests.ps1`.
>
> **Todo criterio de aceptación exige el conteo de seleccionados.** Un `pytest -k` sin match da
> exit 0. La forma válida es leer la línea final `N passed` y compararla con el número de la fase.

---

### F0 — Congelar la foto vieja antes de construir el gate

**Objetivo:** que el censo de sitios ADO-only exista como código y **reproduzca exactamente los
números del Alcance B de §4.5 sobre el código de HOY**, antes de arreglar nada.

**Por qué primero:** un censo que se escribe *después* del fix no prueba nada — reporta 0 porque ya
no hay nada que contar. El censo tiene que demostrar que **detecta el defecto** mientras el defecto
está vivo. Si esta fase no reproduce `10 duras / 4 gateadas / 18 con seam / 4 ciegos`, el detector
está mal y **hay que arreglar el detector, no el baseline**.

**Archivo a editar:** `Stacky Agents/backend/services/provider_coupling_audit.py`
(se **extiende**; no se crea un módulo nuevo — ya tiene ratchet y allowlists).

**Símbolos nuevos, nombres exactos:**

```python
# services/provider_coupling_audit.py — agregar al final, antes de render_report_markdown

# Constructores de cliente ADO. Un módulo que llama a cualquiera de estos está pidiendo
# explícitamente Azure DevOps.
ADO_BUILDERS: frozenset[str] = frozenset({
    "_ado_client_for_ticket", "build_ado_client", "_client_for_ticket_project",
})

# Seam provider-agnóstico. Si la función lo usa, YA rutea bien.
PROVIDER_SEAMS: frozenset[str] = frozenset({
    "_provider_for_ticket", "get_tracker_provider",
})

# Señales de que la función discrimina por tipo de tracker antes de construir el cliente.
# Heurística DELIBERADAMENTE laxa (sobre-perdona) para que lo que quede marcado sea indiscutible.
# OJO (Plan 281 v2/C1): esta laxitud es la razón por la que `app.py::_startup_sync` cae en
# `gateados` y NO en `ado_only`, aunque funcionalmente sea un agujero para GitLab. Para ese
# defecto la señal correcta es `ciegos_a_gitlab` (abajo), no endurecer esta heurística.
TRACKER_GUARDS: frozenset[str] = frozenset({
    "tracker_is_azure_devops", "_tracker_type_for", "resolve_project_context",
    "require_project_context",
})
TRACKER_LITERALS: frozenset[str] = frozenset({
    "azure_devops", "gitlab", "jira", "mantis",
})

# Sitios que tienen DERECHO a ser ADO-only, con el motivo escrito.
# Toda entrada nueva acá exige justificación en el PR: es la puerta trasera del gate.
ADO_ONLY_JUSTIFICADOS: dict[str, str] = {
    "api/tickets.py::_ado_client_for_ticket": "ES el constructor del cliente ADO del módulo",
    "services/local_diagnostics.py::_probe_ado": "sonda de diagnóstico DE Azure DevOps, por definición",
}

# Sitios gateados que quedan FUERA del alcance de este plan, con el motivo.
CIEGOS_A_GITLAB_TOLERADOS: dict[str, str] = {
    "api/projects.py::get_tracker_states": "estados del tablero por tracker — su equivalente GitLab es del Plan 282",
}

def scan_ado_only_sites(raiz: Path | None = None) -> dict:
    """Censo por AST de funciones que construyen cliente ADO sin rutear por tracker.

    ALCANCE (`raiz` default = `_BACKEND`): `api/*.py` + `services/*.py` + `app.py`.
    `app.py` va INCLUIDO a propósito: el censo del Plan 218 no lo miraba y ahí vive
    `_startup_sync` (app.py:203). NO clasifica como `ado_only` (ver TRACKER_GUARDS);
    lo captura `ciegos_a_gitlab`.

    EXCLUYE: la familia `services/ado_*.py` (un adaptador ADO tiene derecho a serlo)
    y `services/project_context.py` (define `build_ado_client`).

    CENSA POR REFERENCIA, no por texto: recorre `ast.Call` y acepta tanto `ast.Name`
    (llamada directa) como `ast.Attribute` (llamada por alias de módulo, p. ej.
    `project_context.build_ado_client(...)` en services/completion_sync.py:101).
    Un censo que sólo mirara `ast.Name` daría CERO en ese archivo.

    `raiz` es parámetro para que F8.4 pueda apuntarlo a un directorio temporal.
    Devuelve claves ordenadas y deterministas.
    """
```

**`[ADICIÓN ARQUITECTO]` — la métrica `ciegos_a_gitlab`.** Es lo que convierte K2 en algo medible.
Una función está *ciega a GitLab* cuando **discrimina por tracker** (menciona algún literal de
`TRACKER_LITERALS` o llama a un `TRACKER_GUARD`) **y sin embargo** ni menciona el literal
`"gitlab"` ni llama a `tracker_is_azure_devops` (el resolvedor canónico, que sí contempla todos los
trackers). Es exactamente el patrón "agregué el tracker nuevo en el sync pero no en este `if`".

**Contrato de salida** (exacto — los tests comparan contra esto; **`gateados_count` corregido**):

```python
{
  "con_seam":            ["api/tickets.py::finish_work", ...],   # ordenada
  "con_seam_count":      18,
  "gateados":            ["api/projects.py::get_tracker_states",
                          "app.py::_startup_sync",
                          "services/completion_sync.py::_do_project_sync",
                          "services/run_ticket_refresh.py::refresh_ticket_snapshot"],
  "gateados_count":      4,                                       # v1 decía 3 — C1
  "ado_only":            ["api/agents.py::_build_ado_enrichment_sections", ...],
  "ado_only_count":      10,
  "violaciones":         [...],   # ado_only menos ADO_ONLY_JUSTIFICADOS
  "violaciones_count":   8,
  "ciegos_a_gitlab":     [...],   # NUEVO — subconjunto de `gateados`
  "ciegos_count":        4,       # NUEVO
}
```

La clave de cada sitio es `"<ruta relativa a backend, posix>::<nombre de la función>"` —
**deliberadamente SIN número de línea**: los anclajes de línea caducan en cuanto alguien edita el
archivo arriba (§0 lo demuestra: el diff sin commitear ya corrió los de `tickets.py`), y un gate que
se rompe por un `import` nuevo es un gate que se termina desactivando.

**Test PRIMERO:** `Stacky Agents/backend/tests/test_plan281_censo_ado_only.py` (archivo nuevo).

| Caso | Qué asegura |
|---|---|
| `test_censo_reproduce_la_foto_vieja` | Sobre el código **sin arreglar**: `ado_only_count == 10`, `gateados_count == 4`, `con_seam_count == 18`, `violaciones_count == 8`, `ciegos_count == 4`. **Se BORRA en F9.** Su única función es probar que el detector ve el defecto. |
| `test_app_py_es_gateado_pero_ciego_a_gitlab` | **(C1 — reemplaza a `test_censo_incluye_app_py`)** `"app.py::_startup_sync" in scan()["gateados"]` **y** `in scan()["ciegos_a_gitlab"]` **y** `not in scan()["ado_only"]`. Fija por escrito la clasificación real y guarda el alcance ampliado de §4.6. |
| `test_censo_detecta_llamada_por_alias` | `"services/completion_sync.py::_do_project_sync"` aparece en `gateados` (no ausente). **Guarda contra el censo que da CERO por alias.** |
| `test_censo_excluye_familia_ado` | Ningún sitio de la salida empieza con `services/ado_`. |
| `test_censo_es_determinista` | Dos llamadas seguidas devuelven exactamente lo mismo (listas ordenadas). |
| `test_justificados_son_subconjunto_de_ado_only` | Toda clave de `ADO_ONLY_JUSTIFICADOS` está en `ado_only`. **Impide que una justificación quede huérfana** y esconda un sitio que ya no existe. |

**Comando:**
```
./venv/Scripts/python.exe -m pytest tests/test_plan281_censo_ado_only.py -v
```

**Criterio de aceptación BINARIO:** `6 passed`, con el código de producción **sin modificar**. Si
algún conteo da distinto, el detector está mal: corregir el detector y volver a correr.
**Prohibido ajustar el número esperado para que pase.**

**Medición de referencia (v2, ya corrida — el implementador debe reproducirla):**
```
Funciones que construyen cliente ADO : 32
  con seam de provider              : 18
    gateadas por tipo de tracker    : 4
    SIN NINGUN GUARD (ADO-ONLY)     : 10
ciegos_a_gitlab HOY: 4
   api/projects.py::get_tracker_states
   app.py::_startup_sync
   services/completion_sync.py::_do_project_sync
   services/run_ticket_refresh.py::refresh_ticket_snapshot
```

**Flag:** ninguna. Es código de auditoría, puro, sin I/O de red ni DB.
**Impacto por runtime:** ninguno (Codex / Claude Code / Copilot: idéntico — no toca el runtime).
**Trabajo del operador: ninguno.**

---

### F1 — El test que reproduce el error en pantalla

**Objetivo:** dejar en rojo, y por la razón correcta, el camino completo que produce el cartel.

**Archivo nuevo:** `Stacky Agents/backend/tests/test_plan281_ruteo_por_tracker.py`

| Caso | Qué prueba | Estado ANTES del fix |
|---|---|---|
| `test_request_project_name_lee_el_body_sin_content_type` **(C6 — renombrado y assert invertido)** | `POST` a `/api/tickets/sync-v2` con `data=json.dumps({"project":"RIPLEY"})` y **sin** `content_type` ⇒ `_request_project_name()` devuelve **`"RIPLEY"`** | **ROJO** (hoy devuelve `None`) |
| `test_request_project_name_lee_el_body_con_content_type` | El mismo `POST` **con** `content_type="application/json"` ⇒ devuelve `"RIPLEY"` | **VERDE ya hoy** — es el guard del assert de ausencia |
| `test_sync_v2_de_proyecto_gitlab_no_menciona_azure_devops` | Con un proyecto de tracker `gitlab`, la respuesta de `sync-v2` **no** contiene la subcadena `"no usa Azure DevOps"` | **ROJO** |
| `test_sync_via_provider_no_asume_ado_con_contexto_nulo` | `_sync_via_provider_or_ado` con `resolve_project_context` devolviendo `None` **no** llama a `_ado_client_for_ticket` | **ROJO** |

> **C6 — por qué se invirtió el caso 1.** v1 lo llamaba `..._pierde_el_body_...` y hacía que
> assertara `is None` (el defecto) declarando estado **ROJO**. Un test que asserta lo que el código
> hace hoy está **VERDE** hoy, y además F2 exigía que quedara verde *después* del fix — dos cosas
> incompatibles a la vez. El assert correcto es el **comportamiento deseado**.

> **Los dos primeros casos van juntos y en ese orden a propósito.** Un assert de ausencia
> (`"no usa Azure DevOps" not in body`) pasa por accidente si el endpoint devuelve 500, o si el
> fixture no llegó a ejecutar el camino. El caso 2 garantiza, en el mismo archivo, que el mecanismo
> **sí detecta** la condición cuando está presente.

**Fixtures — reglas duras:**
- `monkeypatch` sobre `project_manager.get_project_config` para devolver
  `{"issue_tracker": {"type": "gitlab", "base_url": "https://ejemplo.local", "project": "g/p"}}`.
  **NUNCA** leer `backend/projects/RIPLEY/config.json` real. (Nota: `tracker_is_azure_devops`
  importa `get_project_config` **dentro** de la función a propósito, justamente para que este
  parche funcione — ver su docstring en `project_context.py:60-63`.)
- `DATABASE_URL` apuntando a SQLite temporal (`tmp_path`). **Un pytest suelto sin `DATABASE_URL`
  escribe en la base VIVA del operador**. Si el fixture no puede aislar la DB, el test se marca
  `xfail`, no se corre contra la real.
- `STACKY_TEST_MODE=1`. Cero red: el provider de GitLab se mockea; no se abre socket.

**Comando:**
```
./venv/Scripts/python.exe -m pytest tests/test_plan281_ruteo_por_tracker.py -v
```

**Criterio de aceptación BINARIO de F1:** `1 passed, 3 failed`. Los 3 fallos son los 3 defectos.
Si sale `4 passed`, los tests no están probando nada: revisarlos antes de seguir.

**Flag:** ninguna (son tests). **Impacto por runtime:** ninguno. **Trabajo del operador: ninguno.**

---

### F2 — El nombre del proyecto llega al backend (dos capas)

**Objetivo:** cerrar K3 — que `sync-v2` deje de recibir `project_name = None`.

Se arregla en **las dos puntas**, a propósito: el frontend puede volver a olvidar el header en el
próximo `fetch` que alguien copie y pegue, y el backend no debería depender de eso.

**Capa 1 — frontend.** Editar `Stacky Agents/frontend/src/hooks/useTicketSync.ts:122-124`
(v1 decía 120-123; **anclaje corregido** — anclá por el símbolo `const headers`):

```diff
       const headers: Record<string, string> = {
         "X-Stacky-Trigger": trigger,
+        // Plan 281 F2 — sin esto el navegador manda `text/plain;charset=UTF-8` y
+        // Flask `request.get_json(silent=True)` devuelve None: el body se descarta
+        // ENTERO. `_request_project_name()` (api/tickets.py:288-296) da None y el
+        // ruteo cae al proyecto ACTIVO global en vez del que el operador mira.
+        "Content-Type": "application/json",
       };
```

**Capa 2 — backend.** Editar `_request_project_name` en `Stacky Agents/backend/api/tickets.py:293`:

```diff
     if request.method in {"POST", "PUT", "PATCH"}:
-        body = request.get_json(silent=True) or {}
+        # `force=True` parsea el cuerpo aunque el cliente no haya declarado
+        # Content-Type. `silent=True` mantiene el contrato: cuerpo vacío o no-JSON
+        # devuelve None y la función cae a `return None`, como antes.
+        # Verificado en Flask 3.0.3 (el del venv): body basura + force=True => None.
+        body = request.get_json(silent=True, force=True) or {}
         body_project = (body.get("project") or "").strip()
         return body_project or None
```

**Backward-compat:** medida, no supuesta — ver la tabla empírica de §4.3. `force=True` sólo
**agrega** casos que antes devolvían `None`. Ningún caller que hoy recibe un nombre válido cambia.

**Test de la capa 1 (frontend):** RTL y jsdom **no están instalados** en este repo. La lógica se
prueba en `.ts` puro. Editar `Stacky Agents/frontend/src/services/uiGuards.test.ts` (archivo **ya
existente y ya modificado en el trabajo en vuelo — agregar al final, NO reescribir**).

Para que sea testeable sin montar el componente, extraer la construcción de headers a una función de
módulo exportada en `Stacky Agents/frontend/src/hooks/useTicketSync.ts`:

```ts
export function cabecerasDeSync(trigger: "manual" | "auto_poll" | "startup"): Record<string, string> {
  return { "X-Stacky-Trigger": trigger, "Content-Type": "application/json" };
}
```

…y consumirla en el `mutationFn` (`const headers = cabecerasDeSync(trigger);`), para que el test no
pruebe una copia muerta.

> Precedente en el mismo archivo: el Plan 276 F6/C3 ya sacó `shouldRefreshTicketQueries` de closure a
> `debeRefrescarQueriesDeTickets` a nivel de módulo, **exactamente por este motivo**
> (comentario en `useTicketSync.ts:115-117`, verificado). Se sigue ese patrón.

| Caso en `uiGuards.test.ts` | Assert |
|---|---|
| `cabecerasDeSync declara Content-Type application/json` | `cabecerasDeSync("auto_poll")["Content-Type"] === "application/json"` |
| `cabecerasDeSync conserva el trigger` | `cabecerasDeSync("startup")["X-Stacky-Trigger"] === "startup"` |

**Comando frontend** (desde `Stacky Agents/frontend`), **por archivo** — vitest contamina por orden:
```
npx vitest run src/services/uiGuards.test.ts --testTimeout=60000
```
> `--testTimeout=60000` es obligatorio: un rojo de vitest en este repo **puede ser sólo timeout**.

**Comando backend:**
```
./venv/Scripts/python.exe -m pytest tests/test_plan281_ruteo_por_tracker.py -v
```

**Criterio de aceptación BINARIO:**
- Backend: `2 passed, 2 failed` (los casos 3 y 4 siguen rojos hasta F3).
- Frontend: **medir el conteo previo con el archivo sin tocar** y exigir `previo + 2`.
- `tsc` sin errores: `npx tsc --noEmit` ⇒ salida vacía, exit 0.

**Flag:** ninguna. Es una corrección de un header HTTP faltante; ponerle flag sería ofrecer al
operador la opción de mantener el bug.
**Impacto por runtime:** ninguno. **Trabajo del operador: ninguno.**

---

### F3 — "No sé qué tracker es" deja de significar "es ADO"

**Objetivo:** cerrar el fallo cerrado de §4.4.

**Archivo a editar:** `Stacky Agents/backend/api/tickets.py:1153-1156`.

```diff
     if provider is None:
         ctx_sync = resolve_project_context(project_name)
-        tipo = (getattr(ctx_sync, "tracker_type", None) or "azure_devops").strip().lower()
-        if ctx_sync is not None and tipo != "azure_devops":
+        if ctx_sync is None and bool(
+            getattr(config.config, "STACKY_TRACKER_ROUTING_STRICT_ENABLED", True)
+        ):
+            # Plan 281 F3 — ANTES, un contexto irresoluble caía por el `or` a
+            # "azure_devops" y terminaba en el branch ADO de la línea 1188, que
+            # levanta AdoConfigError("...no usa Azure DevOps") aunque el proyecto sea
+            # GitLab. "No pude resolver" NO es "es Azure DevOps": es un error propio.
+            raise TrackerConfigError(
+                f"No se pudo resolver el contexto del proyecto "
+                f"'{project_name or '<activo>'}'. Revisá que el proyecto exista y "
+                f"tenga 'issue_tracker' configurado en Configuración del proyecto."
+            )
+        tipo = (getattr(ctx_sync, "tracker_type", None) or "azure_devops").strip().lower()
+        if ctx_sync is not None and tipo != "azure_devops":
```

> **Cómo se lee la flag acá (C7).** `api/tickets.py` importa el **módulo** `config`, así que la forma
> correcta es **`config.config.STACKY_...`**. En `app.py` (F4) es al revés: ahí `config` ya es la
> **instancia** (`from config import config`) y va `getattr(config, "STACKY_...", True)`. El propio
> `app.py` documenta esta asimetría en su nota `[C1]` (líneas 120-122 y 190-193). Usar `os.getenv`
> para una flag registrada **rompe `tests/test_flags_env_read_meta.py`**.

**Por qué `TrackerConfigError` y no `AdoConfigError`:** `sync-v2` ya tiene un handler dedicado
(`api/tickets.py:6488-6494`, verificado) que lo traduce a **400 con el mensaje accionable**, y
`useTicketSync` lo rutea a `setSyncError`. El operador ve el problema real en vez de un error del
proveedor equivocado. El precedente es el bloque de las líneas 1159-1171, que ya hace exactamente
esto para el caso de `STACKY_GITLAB_ENABLED` apagado.

**Test:** los casos 3 y 4 de `tests/test_plan281_ruteo_por_tracker.py`, más uno nuevo:

| Caso | Assert |
|---|---|
| `test_contexto_irresoluble_no_nombra_azure_devops` | El mensaje de la excepción **no** contiene `"Azure DevOps"` y **sí** contiene `"no se pudo resolver"` (case-insensitive) |

**Comando:**
```
./venv/Scripts/python.exe -m pytest tests/test_plan281_ruteo_por_tracker.py -v
```

**Criterio de aceptación BINARIO:** `5 passed, 0 failed`.

**Flag:** `STACKY_TRACKER_ROUTING_STRICT_ENABLED`, **default ON**.
**Justificación del default ON:** corrección de ruteo en **camino de LECTURA** — no publica, no
commitea, no escribe en el tracker del operador, no borra datos, no le saca ninguna decisión. No cae
en **(A)** (no enciende loop, daemon, barrido ni llamada a modelo: corrige el camino de un poll que
**ya existe** desde `useTicketSync.ts:243`) ni en **(B)**. Existe únicamente como kill-switch de
rollback: apagada, `_sync_via_provider_or_ado` restaura el `or "azure_devops"` byte-idéntico de hoy.
**Impacto por runtime:** ninguno. **Trabajo del operador: ninguno.**

---

### F4 — El sync de arranque deja de ser ADO-only

**Objetivo:** cerrar K2 (bajar `ciegos_a_gitlab` de 4 a 3) y hacer que un proyecto GitLab se
sincronice al arrancar el backend.

**Archivo a editar:** `Stacky Agents/backend/app.py`, en el `else` de `_startup_sync` (arranca en la
línea **196**; el `build_ado_client` está en la **203**). Anclá por el comentario `# Azure DevOps`.

```diff
     else:
         # Azure DevOps
+        # Plan 281 F4 — ANTES, `build_ado_client(project_name=active)` levantaba
+        # AdoConfigError para todo proyecto no-ADO y el except de más abajo lo tragaba
+        # como warning: los proyectos GitLab NUNCA se sincronizaban al arrancar.
+        # `config` acá es la INSTANCIA (from config import config, :34) — ver nota [C1].
+        from services.project_context import tracker_is_azure_devops
+        if (
+            active
+            and getattr(config, "STACKY_TRACKER_ROUTING_STRICT_ENABLED", True)
+            and not tracker_is_azure_devops(active)
+        ):
+            try:
+                from services.tracker_provider import get_tracker_provider
+                from services.gitlab_sync import sync_gitlab_tickets
+                _prov = get_tracker_provider(active)
+                if getattr(_prov, "name", "") == "gitlab":
+                    _r = sync_gitlab_tickets(active, provider=_prov)
+                    logger.info("sync GitLab ok al arranque: project=%s %s", active, _r)
+                else:
+                    logger.info(
+                        "sync de arranque omitido: el tracker '%s' de '%s' todavía no "
+                        "tiene sync propio", getattr(_prov, "name", "?"), active,
+                    )
+            except Exception:
+                logger.exception("sync de arranque no-ADO falló (continuando)")
+            return
         active_ctx = None
```

**Nota de diseño:** el `except Exception` amplio se mantiene **a propósito** — el arranque del backend
nunca puede caerse por un sync. Pero se usa `logger.exception` (traza completa), no
`logger.warning` (mensaje pelado): la diferencia entre tragar y registrar.

**Nota sobre el breaker:** con este `return` temprano, un proyecto GitLab deja de tocar el breaker
`"ado_sync"` en el arranque. Es lo correcto: la key `ado_breaker_project(active)` para un proyecto
GitLab mezclaba el estado de degradación de dos proveedores distintos.

**Test:** agregar a `tests/test_plan281_ruteo_por_tracker.py`:

| Caso | Assert |
|---|---|
| `test_startup_sync_gitlab_no_construye_cliente_ado` | Con `tracker_is_azure_devops` devolviendo `False`, `_startup_sync` **no** llama a `build_ado_client` (spy) |
| `test_startup_sync_gitlab_invoca_sync_gitlab_tickets` | …y **sí** llama a `sync_gitlab_tickets` exactamente 1 vez |
| `test_startup_sync_ado_sigue_igual` | Con `tracker_is_azure_devops` devolviendo `True`, `build_ado_client` se llama 1 vez y `sync_gitlab_tickets` 0 veces (**no-regresión ADO**) |

> **`create_app()` fuera de pytest tiene efectos reales.** Estos tests importan `_startup_sync`
> directamente y lo invocan con dependencias mockeadas; **no** llaman a `create_app()`.
> `STACKY_TEST_MODE=1` debe estar seteado en el fixture, y `get_active_project` / `get_project_config`
> mockeados (si no, el test lee el `active_project.json` real del operador).

**Comando:**
```
./venv/Scripts/python.exe -m pytest tests/test_plan281_ruteo_por_tracker.py -v
```
**Criterio de aceptación BINARIO:** `8 passed, 0 failed`.

**Verificación cruzada:** `scan_ado_only_sites()["ciegos_count"]` baja de **4 a 3**.

**Flag:** `STACKY_TRACKER_ROUTING_STRICT_ENABLED` (la misma de F3), default ON. Apagada, el bloque
nuevo no se ejecuta y el arranque queda byte-idéntico al de hoy.
**Impacto por runtime:** ninguno. **Trabajo del operador: ninguno** — al contrario, le devuelve un
sync que hoy no ocurre.

---

### F5 — El dispatch de `completion_sync` deja de romperse en GitLab

**Objetivo:** cerrar K4 (y bajar `ciegos_a_gitlab` de 3 a 2).

**Archivo a editar:** `Stacky Agents/backend/services/completion_sync.py:109-114`
(v1 decía 107-112; **anclaje corregido**, anclá por el `else:` que sigue al bloque `azure_devops`).

El defecto es que el dispatch dinámico asume que **todo** `services/<tracker>_sync.py` expone
`sync_tickets(tracker_config=...)`, y `gitlab_sync` expone `sync_gitlab_tickets(project_name, *,
provider=None)`. Hay dos arreglos posibles; se elige el **explícito**, porque un alias silencioso en
`gitlab_sync` haría que el próximo tracker repita el problema:

```diff
         else:
+            # Plan 281 F5 — el dispatch dinámico asume la firma
+            # `sync_tickets(tracker_config=...)`, que GitLab NO tiene: su entrada es
+            # `sync_gitlab_tickets(project_name, provider=...)` (gitlab_sync.py:235,
+            # __all__ en la 410). Antes esto era un AttributeError tragado por el
+            # `except Exception` de la línea 118: el sync post-completación nunca
+            # corría en GitLab, en silencio.
+            if tracker_type == "gitlab":
+                from services.gitlab_sync import sync_gitlab_tickets
+                result = sync_gitlab_tickets(project) or {}
+            else:
+                # Jira y Mantis NO aceptan project_name: su entrada es tracker_config.
+                from importlib import import_module
+                mod = import_module(f"services.{tracker_type}_sync")
+                if not hasattr(mod, "sync_tickets"):
+                    # Ruidoso a propósito: un tracker nuevo sin la firma esperada tiene
+                    # que APARECER en el log, no desaparecer.
+                    raise AttributeError(
+                        f"services.{tracker_type}_sync no expone sync_tickets(); "
+                        f"agregá su rama explícita en _do_project_sync"
+                    )
+                result = mod.sync_tickets(tracker_config=_tracker_config_for(project)) or {}
-            # Jira y Mantis NO aceptan project_name: su entrada es tracker_config.
-            from importlib import import_module
-
-            mod = import_module(f"services.{tracker_type}_sync")
-            result = mod.sync_tickets(tracker_config=_tracker_config_for(project)) or {}
```

> **Cuidado con `_breaker_target`** (`completion_sync.py:73-79`): para `gitlab` devuelve
> `("gitlab_sync", project)`. No hay que tocarlo — ya rutea bien —, pero sí verificarlo en el test de
> no-regresión para que el breaker no quede compartido con ADO.

**Test:** agregar a `tests/test_plan281_ruteo_por_tracker.py`:

| Caso | Assert |
|---|---|
| `test_completion_sync_gitlab_llama_sync_gitlab_tickets` | Con `tracker_type="gitlab"`, se llama `sync_gitlab_tickets` 1 vez con `project` posicional |
| `test_completion_sync_gitlab_no_levanta_attribute_error` | No se registra ningún `AttributeError` en el log del módulo (spy sobre `brk.record_failure`: no se llama) |
| `test_completion_sync_jira_sigue_igual` | Con `tracker_type="jira"`, se llama `jira_sync.sync_tickets` con kwarg `tracker_config` (**no-regresión**) |

**Comando:**
```
./venv/Scripts/python.exe -m pytest tests/test_plan281_ruteo_por_tracker.py -v
```
**Criterio de aceptación BINARIO:** `11 passed, 0 failed`.

**Flag:** ninguna. Reparar un `AttributeError` que hoy se traga no necesita interruptor.
**Impacto por runtime:** ninguno. **Trabajo del operador: ninguno.**

---

### F6 — `run_ticket_refresh` deja de leer la columna que miente

**Objetivo:** cerrar K5 (y bajar `ciegos_a_gitlab` de 2 a 1).

**Archivo a editar:** `Stacky Agents/backend/services/run_ticket_refresh.py:43-45`.

```diff
-        tracker_type = ticket.tracker_type or "azure_devops"
-        if tracker_type != "azure_devops":
-            return {"refreshed": False, "reason": "non_ado_tracker"}
         stacky_project_name = ticket.stacky_project_name
         tracker_project = ticket.project
+
+    # Plan 281 F6 — el guard sale del `with` y pasa a preguntar por el CONFIG DEL
+    # PROYECTO, no por la columna. `Ticket.tracker_type` tiene default 'azure_devops'
+    # (models.py:49) y las filas creadas antes del fix del publicador de épica nacieron
+    # con ese default aun siendo de GitLab: el guard viejo las dejaba pasar y terminaban
+    # en build_ado_client (línea 54) con AdoConfigError. El resolvedor canónico ya
+    # documenta por qué no se mira la columna (project_context.py:49-53).
+    from services.project_context import tracker_is_azure_devops
+    if not tracker_is_azure_devops(stacky_project_name):
+        return {"refreshed": False, "reason": "non_ado_tracker"}
```

**Contrato preservado:** el `reason` sigue siendo exactamente `"non_ado_tracker"`. Ningún consumidor
cambia. `tracker_is_azure_devops` es fail-closed a `True` sin nombre de proyecto, así que un ticket
sin `stacky_project_name` se comporta como hoy.

**Test:** agregar a `tests/test_plan281_ruteo_por_tracker.py`:

| Caso | Assert |
|---|---|
| `test_refresh_no_confia_en_la_columna_mentirosa` | Ticket con `tracker_type="azure_devops"` (la mentira) en un proyecto cuyo config dice `gitlab` ⇒ `reason == "non_ado_tracker"` y `build_ado_client` **no** se llama. **ROJO antes del fix.** |
| `test_refresh_ado_sigue_refrescando` | Proyecto ADO real ⇒ `refreshed is True` (**no-regresión**) |

> **C12 — la flag que gatea la función bajo test.** `refresh_ticket_snapshot` sale por `flag_off` si
> `config.STACKY_RUN_TICKET_REFRESH_ENABLED` es falso (línea 30). Su default efectivo es `"true"`
> (`config.py:979`, verificado), pero el fixture **debe forzarlo con `monkeypatch.setattr`** para no
> depender del `.env` de la máquina: si no, el test pasa por la razón equivocada.

**Comando:**
```
./venv/Scripts/python.exe -m pytest tests/test_plan281_ruteo_por_tracker.py -v
```
**Criterio de aceptación BINARIO:** `13 passed, 0 failed`.

**Flag:** ninguna (el comportamiento observable no cambia para ADO; para GitLab pasa de "error
tragado" a "no-op declarado").
**Impacto por runtime:** ninguno. **Trabajo del operador: ninguno.**

---

### F7 — Erradicar las 8 violaciones ADO-only

**Objetivo:** cerrar K1 — bajar `violaciones_count` de **8** a **0**.

**Patrón único, aplicado a 7 de los 8 sitios.** No se inventa nada nuevo: se usa el mismo
`tracker_is_azure_devops` que ya usan los 18 sitios correctos.

```python
# Al principio de la función, ANTES de construir el cliente:
from services.project_context import tracker_is_azure_devops
if not tracker_is_azure_devops(<nombre_del_proyecto_stacky>):
    return <valor neutro documentado en la tabla>
```

**El sitio 3 NO usa ese patrón** (ver C2 abajo). El sitio 2 lo usa **con matices** (ver C4/C9).

**Los 8 sitios, uno por uno — la columna "valor neutro" fue VERIFICADA abriendo cada `except`:**

| # | Archivo:línea | Función | Nombre de proyecto disponible | Valor neutro en no-ADO | ¿Coincide con su `except` real? |
|---|---|---|---|---|---|
| 1 | `api/agents.py:1798` | `_build_ado_enrichment_sections` | parámetro `project_name` | `sections` (lista vacía) | **SÍ** — `except Exception: … return sections` |
| 2 | `api/tickets.py:4912` | `_equivalent_task_status` | closure: `project_name` del scope | **`"unknown"`** *(v1 decía `""` — C4)* | **CORREGIDO** — su `except` hace `eq_ado = None` y sigue; el retorno efectivo es `"unknown"` |
| 3 | `api/tickets.py:**7564**` | `autopublish_epic_from_run` — **sólo el bloque `_baseline_rev`** | parámetro `project_name` | **`_baseline_rev = None`** *(v1 abortaba la función — C2)* | **CORREGIDO** — su `except` ya loguea warning y deja `_baseline_rev` en `None` |
| 4 | `services/acceptance_criteria.py:25` | `resolve` | `ticket.stacky_project_name` | `""` | **SÍ** — `except Exception: return ""` |
| 5 | `services/business_preflight.py:37` | `_evaluate_functional` | `stacky_project_name or tracker_project` | `BusinessPreflightResult(ok=True, mode=None, warnings=["tracker no-ADO: sin cross-check de comentarios"])` *(v1 omitía `warnings` — C8)* | **SÍ en `ok=True`**, completado el resto |
| 6 | `services/self_review.py:43` | `_resolve_criteria` | `ticket.stacky_project_name` | `""` | **NO — la función NO TIENE `except` (C5)**. Hoy propaga la excepción a `review_artifact` (que la llama fuera de `try`, línea 69). El cambio es de **excepción propagada → `skipped_reason="no_acceptance_criteria"`**: es la dirección correcta, pero **es un cambio de comportamiento**, no un no-op |
| 7 | `services/similar_tickets.py:91` | `find_similar_tickets` | parámetro `project_name` | `[]` | **SÍ** — `except Exception as exc: … return []` |
| 8 | `services/ticket_assigner.py:356` | `auto_assign_on_run` | `ticket.stacky_project_name or project_name` | `None` | **SÍ** — `except Exception: … return None` (línea final) |

#### C2 — Cómo se arregla el sitio 3 (lo que v1 tenía MAL)

v1 dictaba: *"usar `_provider_for_ticket(project_name=...)`; si es `None`,
`{"published": False, "reason": "tracker_sin_publicador"}`"*. **Eso rompe dos cosas:**

1. **Tipo incorrecto.** `autopublish_epic_from_run` devuelve un `_AutopublishResult` (NamedTuple con
   `ado_id`, `error`, `skipped`, `grounding_warnings`, …), no un `dict`. Un `dict` reventaría a
   cualquier consumidor que haga `resultado.ado_id`.
2. **Cancelaría la publicación de épicas en GitLab**, que es exactamente lo que el **Plan 278**
   acaba de habilitar. Sería una regresión directa contra un plan ya implementado.

**El `build_ado_client` real de esta función está en la línea 7564**, dentro de un bloque que sólo
sella el baseline de `System.Rev` para el aprendizaje bidireccional del Plan 60:

```python
    if _learning_enabled:
        _published_html = clean_html
        if published.rev is not None:
            _baseline_rev = published.rev
        else:
            try:
                _rev_client = _ado_client_for_ticket(project_name=project_name)   # ← 7564
                ...
            except Exception as _exc_rev:
                logger.warning("autopublish_epic_from_run: no se pudo obtener System.Rev: %s", _exc_rev)
```

**El fix correcto** es gatear **ese `else`**, no la función:

```diff
         if published.rev is not None:
             _baseline_rev = published.rev
+        elif not tracker_is_azure_devops(project_name):
+            # Plan 281 F7/C2 — `System.Rev` es un concepto de Azure DevOps. En un
+            # tracker no-ADO no hay baseline que sellar: se deja en None, que es
+            # exactamente lo que ya dejaba el `except` de abajo. NO se aborta la
+            # publicación: el Plan 278 publica épicas en GitLab y este bloque es
+            # sólo el sellado del aprendizaje bidireccional (Plan 60 F1).
+            _baseline_rev = None
         else:
```

#### C4 / C9 — El sitio 2 y por qué su guard es cosmético

`_equivalent_task_status` **ya está funcionalmente protegido**: su `try/except Exception` captura el
`AdoConfigError` de `_ado_client_for_ticket` y deja `eq_ado = None`; `_consumed_task_ado_status`
devuelve entonces `"unknown"` (porque `getattr(ado, "get_work_item", None)` no es callable). **El
guard de F7 acá NO arregla un bug: sirve sólo para que el censo lo deje de marcar.** Se aplica
igual, por consistencia del gate, pero:

> **El valor neutro DEBE ser `"unknown"`, nunca `""`.** El contrato del consumidor está documentado
> en `api/tickets.py:4491-4495` y son exactamente **tres** valores: `"exists"`, `"missing"`,
> `"unknown"`. Devolver `""` introduce un cuarto valor que ningún camino produce hoy y que
> `_find_equivalent_consumed_pending_task` no maneja — **reabre el caso ADO-241** (marker `consumed`
> stale que hace responder "idempotente" sin crear nada).

**Orden de aplicación (de menor a mayor riesgo):** 4 → 6 → 7 → 1 → 2 → 8 → 5 → 3.

**Test:** archivo nuevo `Stacky Agents/backend/tests/test_plan281_sitios_ado_only.py`, con **una
clase por sitio**, cada una con 2 casos:

| Caso por sitio | Assert |
|---|---|
| `test_<sitio>_no_construye_cliente_ado_en_gitlab` | Con `tracker_is_azure_devops` mockeado a `False`, el spy sobre `build_ado_client` registra **0 llamadas** y el retorno es **exactamente** el valor neutro de la tabla (comparación por igualdad, no por truthiness) |
| `test_<sitio>_sigue_igual_en_ado` | Con `tracker_is_azure_devops` a `True`, `build_ado_client` se llama **1 vez** (**no-regresión**) |

⇒ 8 sitios × 2 casos = **16 casos**.

> **Ajustes obligatorios por sitio** (si no, el test prueba otra cosa):
> - **Sitio 3:** el caso "no construye cliente ADO en GitLab" debe **además** assertar que
>   `_provider.create_item` **SÍ se llamó** — o sea, que la épica se publicó igual. Sin ese assert,
>   una implementación que aborte la función (el error de v1) pasaría el test.
> - **Sitio 2:** el assert de retorno es `== "unknown"`.
> - **Sitio 6:** el caso ADO debe verificar que `review_artifact` sigue devolviendo un score real, no
>   `skipped_reason`.

> El segundo caso de cada par es obligatorio: sin él, un `return` mal puesto que rompa también el
> camino ADO pasaría el primer caso sin que nadie se entere.

> **El sitio 3 es distinto de los otros 7 a propósito.** `autopublish_epic_from_run` **sí** tiene un
> equivalente en GitLab (el publicador del Plan 278), así que no se degrada a no-op. Los otros 7 son
> enriquecimientos y heurísticas que **hoy no tienen equivalente GitLab**; degradarlos a un valor
> neutro es honesto. Construir el equivalente GitLab de esos 7 está **fuera de scope** (§7).

**Comando:**
```
./venv/Scripts/python.exe -m pytest tests/test_plan281_sitios_ado_only.py -v
```
**Criterio de aceptación BINARIO:** `16 passed, 0 failed`.

**Verificación cruzada obligatoria** — el censo tiene que ver la mejora:
```
./venv/Scripts/python.exe -c "from services.provider_coupling_audit import scan_ado_only_sites; s=scan_ado_only_sites(); print(s['violaciones_count'], s['ado_only_count'], s['ciegos_count'])"
```
**Debe imprimir exactamente:** `0 2 1`

**Flag:** `STACKY_TRACKER_ROUTING_STRICT_ENABLED` (la misma), default ON. Apagada, los guards no
cortan y el comportamiento vuelve a ser el de hoy.
**Impacto por runtime:** ninguno. **Trabajo del operador: ninguno.**

---

### F8 — El gate por AST: el ratchet que no deja volver atrás

**Objetivo:** convertir el censo de F0 en un gate permanente.

**F8.1 — Baseline.** Crear `Stacky Agents/backend/tests/ado_only_baseline.json`:

```json
{
  "ado_only_count": 2,
  "violaciones_count": 0,
  "ciegos_count": 1
}
```

> Archivo **separado** de `provider_coupling_baseline.json` a propósito: ese pertenece al Plan 218 y
> tiene su propio ratchet. Mezclarlos haría que un cambio de este plan rompa un gate ajeno.
> **Escribir el archivo con newline final**: `write_text` sin newline rompe la comparación de
> `sha256` en Windows.

**F8.2 — Ratchet.** Crear `Stacky Agents/backend/tests/test_plan281_ratchet_ado_only.py`:

| Caso | Assert |
|---|---|
| `test_violaciones_no_crecen` | `scan()["violaciones_count"] <= baseline["violaciones_count"]` |
| `test_ado_only_no_crece` | `scan()["ado_only_count"] <= baseline["ado_only_count"]` |
| `test_ciegos_a_gitlab_no_crecen` | **(NUEVO v2)** `scan()["ciegos_count"] <= baseline["ciegos_count"]`, y el único tolerado es el declarado en `CIEGOS_A_GITLAB_TOLERADOS` |
| `test_justificados_siguen_siendo_dos` | `len(ADO_ONLY_JUSTIFICADOS) == 2` — **impide agrandar la allowlist en silencio** |
| `test_ningun_sitio_nuevo_lee_tracker_type_para_rutear` | Ver F8.3 |
| `test_el_ratchet_detecta_una_violacion_inyectada` | Ver F8.4 |

⇒ **6 casos** (v1 decía 5; el 6.º es el de `ciegos_a_gitlab`).

**F8.3 — El detector de `ticket.tracker_type`. `[ADICIÓN ARQUITECTO]` — REESPECIFICADO (C3).**

> **Por qué la especificación de v1 no servía — medido, no supuesto.** v1 decía: *"Camina `ast.If`,
> `ast.While`, `ast.IfExp` y `ast.BoolOp` y busca en su `test` un `ast.Attribute` con
> `attr == "tracker_type"`"*. Implementado **literalmente** con `backend/venv`, devuelve **4**:
>
> ```
>    api/tickets.py::_clave  (L655)
>    api/tickets.py::_clave_de_padre  (L661)
>    api/tickets.py::_crea_ciclo  (L694)
>    services/run_ticket_refresh.py::refresh_ticket_snapshot  (L43)
>    TOTAL: 4
> ```
>
> Los 3 primeros son la **clave compuesta de identidad del Plan 277**
> (`(tk.tracker_type or _TRACKER_POR_DEFECTO, tk.ado_id)`), que existe precisamente para que un
> `iid` de GitLab no colisione con un `id` de ADO. **Son correctos y no se tocan.** Los marca el
> `or` de coalescencia, que es un `ast.BoolOp`.
>
> Y **quitar `ast.BoolOp` deja el detector en 0**: en `run_ticket_refresh` la lectura
> (`tracker_type = ticket.tracker_type or "azure_devops"`, L43) y la comparación
> (`if tracker_type != "azure_devops"`, L44) están en **sentencias distintas**, unidas por una
> variable local. El detector de v1 estaba atrapado entre 4 falsos positivos y 0 verdaderos.
>
> **Con esta especificación el detector devuelve exactamente 1 — medido y verificado.**

```python
def scan_tracker_type_routing(raiz: Path | None = None) -> list[str]:
    """Funciones que RUTEAN por la columna `<algo>.tracker_type` (no las que la muestran).

    Regla, en dos pasos (data-flow intra-función; NO basta con mirar el `test` de
    un `if`, porque el idioma real separa la lectura de la comparación):

      1. LECTURA — se recolectan los nombres locales asignados desde una expresión
         que contiene un `ast.Attribute` con `attr == "tracker_type"`, incluyendo la
         coalescencia `x.tracker_type or "<default>"`.
      2. RUTEO   — la función se marca si un `ast.Compare` tiene, del lado izquierdo
         o entre sus comparadores, (a) un literal de TRACKER_LITERALS y (b) el
         Attribute directo o alguno de los nombres del paso 1.

    La coalescencia SOLA no cuenta: `(tk.tracker_type or DEF).strip().lower()` usada
    como parte de una clave de identidad es LECTURA legítima (Plan 277,
    api/tickets.py::_clave / _clave_de_padre / _crea_ciclo) y NO debe marcarse.
    Serializar la columna en una respuesta (`d["tracker_type"] = t.tracker_type`)
    tampoco cuenta: mostrarla es legítimo, decidir con ella no.

    EXCLUYE POR ORIGEN: un `.tracker_type` que cuelga directamente de una llamada a
    `resolve_project_context` / `require_project_context` / `get_tracker_provider` /
    `_provider_for_ticket` NO es la columna, es la fuente de verdad ya resuelta
    (p. ej. `api/devops.py::preflight_check_route:505`). Sin esta exclusión el
    detector devuelve 2 y marca un sitio correcto.

    EXCLUYE POR ARCHIVO: `services/project_context.py` (ahí `ctx.tracker_type` ES la
    verdad resuelta desde el config) y `services/tracker_write_router.py`
    (`target.tracker_type` viene del TrackerTarget resuelto).
    """
```

**Calibración obligatoria antes de usarlo como gate:** correr el detector sobre el código **anterior
a F6** y verificar que devuelve **exactamente**:

```
['services/run_ticket_refresh.py::refresh_ticket_snapshot']   (compare en L44)
```

y que las 3 funciones de jerarquía del Plan 277 (`_clave`, `_clave_de_padre`, `_crea_ciclo`)
**NO** aparecen. Si devuelve `[]`, o si devuelve las 3 del 277, el detector está mal —
**arreglarlo, no bajar la expectativa.** Este par de controles (un positivo obligatorio + tres
negativos obligatorios) va **como asserts dentro del propio test**, no como paso manual.

**F8.4 — El gate se corre CONTRA el defecto.** El caso
`test_el_ratchet_detecta_una_violacion_inyectada` escribe un módulo Python temporal en `tmp_path` con
una función que llama a `build_ado_client()` sin guard, apunta el scanner a ese directorio
(parámetro `raiz: Path | None = None`, default `_BACKEND`) y **exige que la detecte**. Sin este caso,
un scanner que devolviera `[]` siempre pasaría el ratchet para siempre. Se agrega el gemelo para el
detector nuevo: un módulo temporal con `t = x.tracker_type or "azure_devops"` + `if t != "gitlab":`
tiene que ser detectado.

**F8.5 — Registrar en los DOS ratchets.** Los tests nuevos van en **ambos** scripts, que tienen
sintaxis distinta (verificado — el `.sh` usa líneas sueltas indentadas, el `.ps1` usa strings con
coma):

- `Stacky Agents/backend/scripts/run_harness_tests.sh` — agregar junto al bloque del Plan 277, que
  **empieza en la línea 249** (`# — Plan 277 · Jerarquía de GitLab…`) y termina en la **256**.
  El bloque del 276 está en **235-244** (v1 decía 242; corregido). Formato: dos espacios + ruta.
- `Stacky Agents/backend/scripts/run_harness_tests.ps1` — misma lista, formato
  `  "tests/<archivo>.py",` (el bloque del 277 está en **243-249**).

Rutas a registrar (sin espacios — el ratchet **no admite rutas con espacios**):
```
tests/test_plan281_ruteo_por_tracker.py
tests/test_plan281_sitios_ado_only.py
tests/test_plan281_ratchet_ado_only.py
```
> `tests/test_plan281_censo_ado_only.py` **NO se registra**: se borra en F9.

**Comando:**
```
./venv/Scripts/python.exe -m pytest tests/test_plan281_ratchet_ado_only.py -v
```
**Criterio de aceptación BINARIO:** `6 passed, 0 failed` (v1 decía 5).

**Flag:** ninguna (es un test).
**Impacto por runtime:** ninguno. **Trabajo del operador: ninguno.**

---

### F9 — Flag, limpieza y cierre

**F9.1 — Borrar el andamio.** Eliminar `Stacky Agents/backend/tests/test_plan281_censo_ado_only.py`.
Cumplió su función (probar que el detector veía el defecto) y su caso
`test_censo_reproduce_la_foto_vieja` es **falso por diseño** una vez aplicado F7. Los otros **5**
casos se **mueven** a `test_plan281_ratchet_ado_only.py` **antes** de borrar el archivo.

> **Ojo con el caso migrado `test_app_py_es_gateado_pero_ciego_a_gitlab`:** tras F4,
> `app.py::_startup_sync` deja de estar en `ciegos_a_gitlab`. **Al migrarlo hay que reescribir su
> assert** a: `"app.py::_startup_sync" not in scan()["ciegos_a_gitlab"]` **y**
> `not in scan()["ado_only"]`. Si se migra tal cual, falla. *(Éste es exactamente el modo de falla
> que hizo insatisfacible a F0 en v1 — C1.)*

⇒ `test_plan281_ratchet_ado_only.py` queda en **11 casos** (6 propios + 5 migrados).

**F9.2 — Registrar la flag.** `STACKY_TRACKER_ROUTING_STRICT_ENABLED`, **default ON**. Una flag es un
**bloque atómico**; se toca en los **6** lugares (v1 decía 5 — C7), todos en la misma corrida:

| # | Archivo | Anclaje por estructura | Qué se agrega |
|---|---|---|---|
| 1 | `backend/config.py` | junto a `STACKY_GITLAB_SYNC_ENABLED` (línea **1355** ✔) | `STACKY_TRACKER_ROUTING_STRICT_ENABLED: bool = os.getenv("STACKY_TRACKER_ROUTING_STRICT_ENABLED", "true").strip().lower() in ("1","true","yes")` — **este es el default EFECTIVO** |
| 2 | `backend/services/harness_flags.py` | dict `_CATEGORY_KEYS` (línea **120** ✔) | la clave en la categoría de integraciones/tracker, la misma donde vive `STACKY_GITLAB_SYNC_ENABLED` (línea **544** ✔) |
| 3 | `backend/services/harness_flags.py` | tupla `FLAG_REGISTRY` (línea **556** ✔) | un `FlagSpec(key=..., default=True, ...)` con el mismo formato que el de la línea **5529** ✔ |
| 4 | `deployment/harness_defaults.env` | regenerar con su generador (está en `deployment/`) | la entrada nueva |
| **5** | **el CONSUMIDOR** (F3 `api/tickets.py`, F4 `app.py`, F7) | — | **NUEVO (C7).** `tests/test_flag_wiring.py` falla con *"Flags registradas SIN consumidor en código productivo"* si la key no aparece como **literal** fuera del registry. F3/F4/F7 ya la consumen; **verificar que quedó, no asumirlo** |
| 6 | Panel de flags (UI) | se alimenta de `FLAG_REGISTRY` | **nada manual** si 2 y 3 están bien |

> **REGLA DE LECTURA — asimétrica, y `os.getenv` está PROHIBIDO (C7).**
> `tests/test_flags_env_read_meta.py` escanea `backend/api/` y `backend/services/` y **falla** si una
> flag registrada se lee con `os.getenv(...)`/`os.environ.get(...)` fuera de la allowlist congelada
> `tests/flags_env_read_allowlist.txt`. La forma correcta:
> - en `backend/api/**` y `backend/services/**`: **`config.config.STACKY_...`** (ahí `config` es el módulo);
> - en `backend/app.py`: **`getattr(config, "STACKY_...", True)`** (ahí `config` ya es la instancia —
>   el propio archivo lo documenta en su nota `[C1]`). `app.py` **no** está en el escaneo, pero la
>   asimetría es real y equivocarse deja la flag muerta en silencio.

> **El comentario de una flag MIENTE sobre su default.** El único default que vale es el string del
> `os.getenv` en `config.py`. Verificarlo leyendo esa línea, no el comentario.
>
> **Dos suites del arnés están ROJAS DE FÁBRICA** al registrar una flag
> (`test_harness_flags_help`, 4 fallos ajenos; `test_flags_env_read_meta`, 1). El criterio de
> aceptación es **delta**: el conteo de fallos tiene que ser **igual** antes y después de agregar la
> flag, no cero. **Medirlo ANTES**, con el registro sin tocar, y pegar los dos números.

**F9.3 — Gate agregado.** Correr el arnés completo:
```
./scripts/run_harness_tests.ps1
```
**Criterio:** el conteo de fallos es **igual o menor** al medido antes de empezar el plan (guardar ese
número en F0 y pegarlo en el PR). No se acepta "pasó todo" sin la salida pegada.

**F9.4 — Smoke manual (human-in-the-loop, lo hace el operador).** Requiere backend levantado y token
de GitLab; no se puede automatizar:

1. Abrir Stacky con **RIPLEY** activo, ir a la vista de ticket-grafo.
2. Dejarla abierta **5 minutos** (≥ 6 ciclos del poll de 45 s).
3. **Criterio binario:** el cartel `"no usa Azure DevOps"` **no aparece ni una vez**.
4. En la consola del navegador, verificar que `POST /api/tickets/sync-v2` lleva
   `Content-Type: application/json` y `{"project":"RIPLEY"}` en el body.
5. Reiniciar el backend y verificar en el log la línea `sync GitLab ok al arranque: project=RIPLEY`.

**F9.5 — Registrar la huella de regresión. NUEVO en v2 (C11).**
Agregar una entrada a `Stacky Agents/docs/sistema/error_fingerprints.json`. **Schema real
verificado** (57 huellas; el archivo NO tiene el schema que suponen otros planes):

| Clave | ¿Obligatoria? | Valor para esta huella |
|---|---|---|
| `id` | sí (57/57) | `"plan281-ruteo-ado-en-proyecto-gitlab"` |
| `title` | sí (57/57) | `"Un proyecto GitLab recibe un error de configuracion de Azure DevOps"` |
| `class` | sí (57/57) | `"routing"` |
| `status` | sí (57/57) | `"resolved"` — **valores realmente presentes: `resolved` (50), `by_design` (4), `open` (2), `guarded` (1)** |
| `log_pattern` | sí (57/57) | regex sobre `ADO sync-v2 . config:.{0,80}no usa Azure DevOps` |
| `log_guarded` | sí (57/57) | `true` |
| `killed_by` | sí (57/57) | `"plan 281 F3/F7"` |
| `killed_commit` | 51/57 | `null` hasta commitear |
| `date_resolved` | 54/57 | `"2026-08-01"` |
| `guard_test` | sí (57/57) | `"tests/test_plan281_ruteo_por_tracker.py"` |
| `evidence` | 54/57 | libre |
| `note` | 48/57 | libre |
| `self_test` | **38/57 — opcional** | `{"matches": [...], "clean": [...]}` |

> **El catálogo está ROJO DE FÁBRICA**: 19 huellas sin `self_test` y un `status` fuera del enum
> declarado. **El criterio es delta**: correr su suite antes y después y exigir el **mismo** conteo
> de fallos. Incluir `self_test` en la entrada nueva (con al menos 1 `matches` y 1 `clean`) para no
> engrosar la deuda.

---

## 6. Riesgos y mitigaciones

| # | Riesgo | Prob. | Mitigación |
|---|---|---|---|
| R1 | Uno de los 8 guards de F7 rompe también el camino ADO | Media | El **segundo caso de cada par** (`_sigue_igual_en_ado`) existe para esto. 8 de 16 casos son de no-regresión ADO |
| R2 | El censo por AST da CERO porque la llamada va por alias de módulo | **Alta** — modo de falla clásico | El scanner acepta `ast.Attribute` además de `ast.Name`, y `test_censo_detecta_llamada_por_alias` lo prueba contra `completion_sync.py:101`, que es literalmente una llamada por alias |
| R3 | El baseline se ajusta para que el gate pase | Media | F0 exige reproducir la foto **vieja** (números re-medidos en v2); F8.4 inyecta una violación sintética y exige detectarla |
| R4 | `force=True` en `get_json` rompe un caller que hoy manda basura | **Descartada** | **Medido** en Flask 3.0.3: body basura + `force=True` ⇒ `None`; body vacío ⇒ `None` (§4.3) |
| R5 | Colisión con el trabajo sin commitear de la épica | **Alta** — F7 sitio 3 toca `tickets.py` cerca | §0: pathspec explícito, prohibido `-a`/`stash`/`reset`. **Y todos los anclajes de `tickets.py` ≥ 7097 están tomados sobre el árbol SUCIO**: anclar por símbolo |
| R6 | `SQLITE_LOCKED` hace flaky los tests con DB | Media | Los tests mockean el acceso a datos; los que necesitan DB usan SQLite en `tmp_path`, nunca la base viva |
| R7 | F3 cambia una excepción y algún caller la esperaba `AdoConfigError` | Baja | `sync-v2` ya tiene handler para `TrackerConfigError` (`tickets.py:6488` ✔). Callers de `_sync_via_provider_or_ado`: **2** (`/sync` línea 1198 y `sync-v2` línea 6474 ✔), ambos con handler |
| R8 | El operador apaga la flag y vuelve el bug | Baja | Kill-switch de rollback declarado; el mensaje del panel lo dice |
| **R9** | **El sitio 6 pasa de lanzar excepción a no-op y algún caller dependía de la excepción** | **Media (NUEVO — C5)** | `_resolve_criteria` es llamada en un solo lugar (`self_review.review_artifact:69`), que ya maneja el vacío con `skipped_reason="no_acceptance_criteria"`. **Censar los callers antes de aplicar el sitio 6** y pegarlo en el PR |
| **R10** | **El detector de F8.3 marca las 3 funciones de jerarquía del Plan 277 y el DoD se vuelve insatisfacible** | **Alta si se copia v1 (NUEVO — C3)** | La calibración de F8.3 lleva los 3 negativos obligatorios **como asserts del test**, no como paso manual |

---

## 7. Fuera de scope (explícito)

**Va al Plan 282** (fluidez general de la integración GitLab, en escritura paralela):
- Construir el equivalente GitLab de los 7 sitios que F7 degrada a valor neutro (criterios de
  aceptación, self-review, similar tickets, auto-assign, business preflight, enriquecimiento de
  contexto, estado equivalente de tarea).
- **`api/projects.py::get_tracker_states`** — el único `ciego_a_gitlab` que queda tras este plan.
  Declarado en `CIEGOS_A_GITLAB_TOLERADOS` con su motivo.
- Rediseño de UX de la vista de grafo o del banner de error de sync.
- La cadencia de polling en sí (hoy `GET /api/tickets` late a ~8 s por colisión de `queryKey` entre
  `TicketBoard.tsx:987-993` y `useRunningStatus.ts:51-61`).
- El breaker `"ado_sync"` usado con key de proyecto GitLab en `api/tickets.py:6430`.
- La **idempotencia del endpoint** `POST /api/tickets/epics/from-brief` (hoy publica siempre que lo
  llamen; el trabajo sin commitear de §0 la mitiga **del lado del cliente**, con `sealedWorkItemId`).
- Deep links de GitLab, `base_url` con namespace pegado, y demás features a medio portar.

**No entra en ningún plan de esta serie:** RBAC, multiusuario, cambiar el modelo de datos de
`Ticket`, migrar las filas existentes con `tracker_type` mal poblado (es una operación sobre la base
**viva** del operador y exige su decisión explícita).

---

## 8. Glosario

| Término | Significado en Stacky |
|---|---|
| **Seam de provider** | `_provider_for_ticket()` (`api/tickets.py:414`) — devuelve un `TrackerProvider` agnóstico o `None` para caer al camino ADO |
| **Sitio ADO-only** | Función que construye un cliente de Azure DevOps sin preguntar antes de qué tracker es el proyecto |
| **Ciego a GitLab** | Función que **sí** discrimina por tracker pero cuya discriminación **no contempla GitLab** — el agujero de `_startup_sync`. Métrica nueva de v2 |
| **Ratchet** | Test que compara una métrica contra un baseline en disco y sólo la deja **bajar** |
| **Fail-closed a ADO** | Que la ausencia de información se interprete como "es Azure DevOps". Es el defecto central de este plan |
| **Valor neutro** | Lo que devuelve una función degradada en no-ADO. **Se verifica abriendo su `except`, no se supone** (2 de los 8 de v1 estaban mal) |
| **Foto vieja** | La medición del censo sobre el código **antes** de arreglarlo. Un gate que no reproduce la foto vieja no prueba nada |
| **Flag del arnés** | Interruptor en `services/harness_flags.py` administrable por UI; el default efectivo vive en `config.py` |

---

## 9. Orden de implementación

1. **F0** — censo que reproduce la foto vieja (`10 / 4 / 18 / 8 / 4 ciegos`). **Si no reproduce, PARAR.**
2. **F1** — tests en rojo (`1 passed, 3 failed`).
3. **F2** — `Content-Type` en el frontend + `force=True` en el backend (`2 passed, 2 failed`).
4. **F3** — contexto irresoluble deja de ser ADO (`5 passed`).
5. **F4** — sync de arranque para GitLab (`8 passed`; `ciegos` 4→3).
6. **F5** — dispatch de `completion_sync` (`11 passed`; `ciegos` 3→2).
7. **F6** — `run_ticket_refresh` deja de leer la columna (`13 passed`; `ciegos` 2→1).
8. **F7** — los 8 sitios, en el orden 4→6→7→1→2→8→5→3 (`16 passed`; `0 2 1`).
9. **F8** — baseline, ratchet, detector reespecificado, registro en los 2 arneses (`6 passed`).
10. **F9** — flag (6 lugares), borrar andamio (ratchet ⇒ `11 passed`), huella, arnés completo,
    smoke manual del operador.

**Dependencias duras:** F0 antes que F8 (el baseline sale del censo calibrado). F1 antes que F2-F6.
F8.3 requiere que F6 **no** esté aplicada al momento de calibrar (o calibrar contra el commit previo).

---

## 10. Definición de Hecho (DoD)

El plan está cerrado cuando **todas** estas líneas son verdaderas y hay salida pegada de cada una:

- [ ] `pytest tests/test_plan281_ruteo_por_tracker.py` ⇒ **13 passed, 0 failed**
- [ ] `pytest tests/test_plan281_sitios_ado_only.py` ⇒ **16 passed, 0 failed**
- [ ] `pytest tests/test_plan281_ratchet_ado_only.py` ⇒ **6 passed** antes de F9.1 y **11 passed**
      después (6 propios + 5 migrados con el assert de app.py reescrito)
- [ ] `scan_ado_only_sites()` ⇒ `violaciones_count == 0`, `ado_only_count == 2`, `ciegos_count == 1`
- [ ] `scan_tracker_type_routing()` ⇒ `[]` — **y su test incluye los 3 negativos obligatorios del
      Plan 277 (`_clave`, `_clave_de_padre`, `_crea_ciclo`), que NO deben aparecer nunca**
- [ ] `npx vitest run src/services/uiGuards.test.ts --testTimeout=60000` ⇒ conteo previo **+2**
- [ ] `npx tsc --noEmit` ⇒ exit 0, salida vacía
- [ ] `scripts/run_harness_tests.ps1` ⇒ fallos **≤** el número medido antes de empezar (pegar ambos)
- [ ] `test_flag_wiring.py` y `test_flags_env_read_meta.py` ⇒ **mismo conteo de fallos** que antes de
      registrar la flag (son rojos ajenos: criterio **delta**, no cero)
- [ ] Los 3 archivos de test nuevos están en `run_harness_tests.sh` **y** en `run_harness_tests.ps1`
- [ ] La huella `plan281-ruteo-ado-en-proyecto-gitlab` está en `docs/sistema/error_fingerprints.json`
      con `self_test`, y el conteo de fallos de su suite no subió
- [ ] `git status --porcelain` sigue mostrando las rutas de §0 más las de este plan, y **ninguna
      revertida**
- [ ] Smoke manual F9.4 confirmado **por el operador**: 5 minutos en la vista de grafo de RIPLEY sin
      el cartel, y `sync GitLab ok al arranque` en el log
- [ ] **Sin `git push`** — el push es siempre manual y lo decide el operador
