# Plan 270 — El tablero de incidencias dice la verdad: cierre real en ADO y GitLab

**Estado:** CRITICADO v1 -> v2
**Fecha:** 2026-07-28
**Rama de trabajo sugerida:** `feat/plan-270-tablero-incidencias-verdad`
**Numeración:** verificada en frío listando `Stacky Agents/docs/` — máximo `269`, sin duplicados ⇒ este plan es el **270**.
**Juez v2: subagente independiente, misma corrida, contexto limpio**
**Veredicto v1: RECHAZADO** (5 BLOQUEANTES). Todos resueltos abajo.

### CHANGELOG v1 -> v2

- **C1 (BLOQ)** — F0↔F3: `services/incident_inbox.py:51` `resolve_closed_states()` devuelve una **2-tupla** `(estados, fuente)`, no la tupla de estados. El v1 la pasaba entera a `is_close_state` ⇒ **todo cierre GitLab habría fallado con `unmappable_state:Done`**. Ahora el desempaquetado es literal y hay un test que fija la aridad.
- **C2 (BLOQ)** — Censo real: hay **3 sitios vivos** que escriben estado del tracker, no 1. El v1 arreglaba `tickets.py:2076-2080` y prometía el invariante "nunca al cliente ADO" como global. Ahora se declaran los 3, F3 cubre también `tickets.py:1488-1492`, y el resto tiene carve-out escrito.
- **C3 (BLOQ)** — El KPI `divergencia = 0` era inalcanzable: el mayor productor de divergencia es el cierre **automático** (`set_stacky_status_by_ado`), no `finish_work`. F4 ahora se cablea en los dos caminos.
- **C4 (BLOQ)** — `STACKY_GITLAB_ENABLED` default **`false`** (`config.py:1185-1186`) ⇒ con defaults de fábrica **ningún** cierre GitLab funciona, y el DoD quedaba verde igual (el test monkeypatchea la fábrica). Prerequisito declarado, `workaround` que nombra la flag, smoke con la flag ON y evaluación escrita de su promoción.
- **C5 (BLOQ)** — F1 mandaba construir el `AdoClient` con `_ado_client_for_ticket` (privado de `api/tickets.py`) desde un módulo de `services/`: exactamente lo que el repo prohíbe **por escrito** en `services/completion_sync.py:93-95`. Ahora usa `project_context.build_ado_client(...)`, que es el cuerpo literal de ese helper.
- **C6..C12 (IMPORTANTES)** — `diverged_count` sin consumidor ni test y con justificación falsa; `filterDiverged` sin punto de aplicación (riesgo HITL en el lote); `closes` indefinido en la regla 2.a de F0 y `rejected` también cierra; F2 contradecía el patrón `import config` del propio archivo; F4 decía "el campo de estado" en vez de la key literal `"state"`; **7ª pata** invisible (límite de 240 chars de `PlainHelp`); categoría de `_CATEGORY_KEYS` sin nombrar.
- **C13..C16 (MENORES)** — anclajes desfasados corregidos con la línea real (`tickets.py` tiene **8332** líneas, no 7364; `finish_work` en `:1751`); chip con `Button` en vez de `<span>` clickeable; huella de regresión registrada; `IncidentInboxStatus` de TS ampliado.
- **[ADICIÓN ARQUITECTO]** — **F6: ratchet de destino (censo congelado de escrituras de estado)** + `workaround` accionable visible en la bandeja. Ver el bloque marcado más abajo.

---

## 1. Objetivo, KPI e impacto

El operador **abandonó el tablero de incidencias** y gestiona todo desde los tickets de Azure DevOps. Ese abandono no es una preferencia estética: es la consecuencia racional de que **el tablero miente después de actuar**. Hoy, cuando el operador aprieta "Cerrar" en la bandeja, recibe un toast verde y la fila **sigue diciendo "Abierta"**, porque el cierre escribe en el tracker pero nunca refresca la columna local desde la que el tablero deriva "Abierta/Cerrada". Y si el proyecto es GitLab, el cierre además hace lo contrario de lo pedido: **reabre la issue**.

Este plan cierra esa brecha con la corrección **mínima y verificable** de la cadena de cierre, para que la bandeja de incidencias vuelva a ser un punto de gestión confiable en **Azure DevOps y GitLab por igual**.

**KPI primario — `divergencia = 0`:**
> Cantidad de incidencias del proyecto con `stacky_status == "completed"` y `is_open_state(ado_state) == True`.

Es decir: incidencias que **Stacky da por cerradas** pero que el tablero **sigue pintando abiertas**. Ese número es exactamente el síntoma que expulsó al operador. Se calcula **localmente, sin una sola llamada extra al tracker** (ambos campos ya viajan en el ítem: `models.py:95` `ado_state`, `models.py:101` `stacky_status`), así que es gratis medirlo y gratis mostrarlo.

- **Antes del plan:** la divergencia crece con cada cierre y nunca se corrige sola.
- **Después del plan:** un cierre exitoso deja la fila en su estado real de inmediato (F4), un cierre imposible lo dice en vez de fingir (F3), y lo que quedó desalineado de antes se ve marcado en pantalla (F5).

**ALCANCE HONESTO DEL KPI (C3 — corregido en v2).** `stacky_status` pasa a `"completed"` desde **dos** caminos, no uno:
1. **manual** — `finish_work` (`api/tickets.py:1751`), que es el botón "Cerrar" de la bandeja (`FinishWorkButton.tsx:51,62` y el worker del lote `IncidentInboxPage.tsx:207`, ambos contra `POST /api/tickets/{id}/finish-work`);
2. **automático** — `set_stacky_status_by_ado` (`api/tickets.py`, bloque `:1487-1509`), que corre cuando **termina un agente**, y es el de **mayor volumen**.

El v1 sólo cableaba el writeback en (1) ⇒ el KPI no podía llegar a 0. En v2, **F4 se cablea en los dos**, y por eso el KPI queda enunciado sin asterisco. Para ADO el camino (2) además ya tiene refresco por `completion_sync` (flag `STACKY_ADO_SYNC_ON_COMPLETION_ENABLED` default `true`, `config.py:1398-1399`); para **GitLab ese refresco está roto** (C4 abajo) y por eso el writeback propio de F4 es la única vía.

**Impacto secundario:** un cierre desde la bandeja sobre un proyecto GitLab hoy es, en el mejor caso, un error mudo; en el peor, una escritura contra el sistema equivocado. Este plan lo elimina.

> **PREREQUISITO DECLARADO PARA GITLAB (C4).** `get_tracker_provider` (`services/tracker_provider.py:125`) levanta `TrackerConfigError` si `STACKY_GITLAB_ENABLED` está apagada (`:133`), y su default es **`false`** (`config.py:1185-1186`). Con los defaults de fábrica, un cierre GitLab **no llega al tracker**: pasa de "escribe mal en ADO" a "declara `CapabilityUnavailable` y no escribe nada". Eso es una mejora estricta (deja de escribir en el sistema equivocado), **pero no es "cerrar en GitLab"**. Por eso: (a) el `workaround` de la excepción **nombra la flag literal**, (b) F5 lo muestra en pantalla, (c) el DoD incluye un smoke con `STACKY_GITLAB_ENABLED=true`. **Evaluación escrita de su promoción a ON:** la directiva del operador rechaza "prerequisito no garantizado" como motivo de OFF, pero `STACKY_GITLAB_ENABLED` es el **master switch de un adapter entero** (creación de items, comentarios, adjuntos, deep links), ajeno al eje de este plan; promoverla acá sería scope creep con superficie de escritura no analizada. **Se difiere explícitamente al plan 259** (alta GitLab), que es su dueño. Este plan **no la apaga ni la asume**: la declara y la hace visible.

---

## 2. Por qué ahora: el gap, con evidencia

Las cuatro causas están **verificadas leyendo el código en el commit actual** (`d234021e`). No son hipótesis.

### C1 — El cierre nunca refresca el estado local ⇒ la fila miente (causa raíz del abandono)

La cadena es cerrada y determinista:

1. `backend/api/tickets.py:1751` `finish_work` (el decorador `@bp.post("/<int:ticket_id>/finish-work")` está en `:1750`) escribe el estado en el tracker (paso 4, `:2073-2094`) y marca `stacky_status="completed"` (paso 5: la llamada `ts.set_status(` arranca en `:2112`, el literal `"completed"` está en `:2114`).
2. **`finish_work` nunca actualiza `Ticket.ado_state`.** `backend/services/ticket_status.py` (734 líneas) **no contiene ni una sola aparición de `ado_state`** — `set_status` no lo toca. Y `finish_work` no llama a `ado_sync.upsert_single_work_item` ni a `run_ticket_refresh.refresh_ticket_snapshot`.
3. La bandeja deriva "Abierta/Cerrada" **de esa columna local**: `backend/api/incident_inbox.py:163` hace `payload["is_open"] = is_open_state(t.ado_state, closed)`, y los contadores agregan sobre `state_expr` = `func.lower(func.coalesce(Ticket.ado_state, ""))` (`incident_inbox.py:122`).
4. El frontend "refresca" invalidando queries (`frontend/src/pages/IncidentInboxPage.tsx:195-201` `refrescar`), lo que **vuelve a leer la misma columna rancia**.

⇒ **El refresh no puede arreglar lo que nadie escribió.** El operador cierra, ve verde, y la fila sigue abierta. Repetido dos o tres veces, el tablero pierde toda credibilidad.

### C2 — En GitLab, "Cerrar" **reabre** la issue

1. La bandeja manda el estado destino literal `"Done"`: `frontend/src/incidents/incidentInboxActionsModel.ts:15` `export const DEFAULT_FINISH_STATE = "Done";` (sugerencias en `:18`: `["Done", "Closed", "Resolved"]` — vocabulario 100 % ADO), usado en `IncidentInboxPage.tsx:210` `target_ado_state: normalizeFinishState(finishState)`.
2. En GitLab ese string cae en `backend/services/gitlab_provider.py:228` `update_item_state`, que busca `mapping = state_map.get(logical_state, {})` (`:232`) contra `_state_map_for_gitlab()` (`:94-102`), cuyas claves son **`functional`, `accepted`, `rejected`, `in_progress`** — `"Done"` **no está**.
3. `mapping` queda `{}` ⇒ no se agrega label, y en `:250-253`:
   ```python
   if mapping.get("closed"):
       update_body["state_event"] = "close"
   else:
       update_body["state_event"] = "reopen"     # ← rama que se toma
   ```
4. Se envía el `PUT` con `{"state_event": "reopen"}` (`:255-259`).

⇒ **Cerrar una incidencia de GitLab desde el tablero la reabre.** Un estado no mapeable no debe adivinar: debe fallar declarado.

### C3 — Para un ticket que no es ADO, la escritura se enruta al cliente ADO

En `finish_work` paso 4:
```python
_provider = _provider_for_ticket(ticket=ticket)          # tickets.py:2076
if _provider is not None:
    _provider.update_item_state(str(ado_id), target_ado_state)   # :2078
else:
    _ado_client_for_ticket(ticket=ticket).update_work_item_state(int(ado_id), target_ado_state)  # :2080
```
`_provider_for_ticket` (`tickets.py:409`) devuelve `None` si la flag está apagada (`:420`), y `STACKY_TICKETS_PROVIDER_ENABLED` tiene default **`false`** (`backend/config.py:1231-1233`). El Plan 70, que iba a encender esa migración, está **PROPUESTO, sin implementar**.

⇒ Con el default de fábrica, **todo ticket de GitLab cae en la rama `else` y se intenta cerrar con un cliente de Azure DevOps**, pasándole el `iid` de GitLab como si fuera un work item id de ADO. En un proyecto sin ADO configurado esto levanta y se registra como `ok: False` (`:2087-2094`); en un entorno con ADO configurado la llamada se dirige a un work item ajeno. Ninguna de las dos es aceptable: un ticket no-ADO **nunca** debe escribirse con el cliente ADO.

#### C3.bis — CENSO COMPLETO de escrituras de estado (agregado en v2 por C2)

El v1 hablaba de "el" call site. Son **tres vivos** (censo obtenido con `grep -rn "\.update_item_state(\|\.update_work_item_state(" backend/ --include=*.py`, excluyendo `backend/tests/`). Un modelo menor que lea sólo el Principio 4 y no este censo va a creer que el invariante ya vale en todo el repo:

| # | Sitio | Qué es | ¿Lo arregla este plan? |
|---|---|---|---|
| S1 | `api/tickets.py:2076-2080` | `finish_work` — el botón "Cerrar" de la bandeja | **SÍ**, F3 |
| S2 | `api/tickets.py:1487-1508` (provider `:1490`, cliente ADO `:1492`, `except` `:1498`) | `set_stacky_status_by_ado` — cierre **automático al terminar un agente**. Mismo patrón (`_provider_for_ticket` → `else` → `_ado_client_for_ticket(...).update_work_item_state(...)`), mismo bug, **más volumen** | **SÍ**, F3 (agregado en v2) |
| S3 | `api/tickets.py:4776-4787` (provider `:4779`, cliente ADO `:4781`, `except` `:4787`) | Estado inicial de una **Task recién creada** (`ado.update_work_item_state(task_ado_id, target_state)`) | **NO** — carve-out: es creación de Tasks (eje del Plan 70), no cierre de incidencias; y `target_state` sale de la config de tareas, no del operador. Congelado por el ratchet de F6 |
| S4 | `harness/task_states.py:173` | `_apply_task_state` del Plan 79, gateado por `STACKY_DETERMINISTIC_TASK_STATES_ENABLED` (**default OFF**) | **NO** — carve-out: rama inerte con los defaults de fábrica. Congelado por el ratchet de F6 |

**Efecto colateral de F2 sobre S2/S3/S4, declarado:** el guardia de F2 vive dentro de `GitLabTrackerProvider.update_item_state`, así que **protege a los cuatro** contra el `reopen` silencioso. Para S3/S4 eso convierte un `reopen` mudo en una excepción capturada por su propio `except` (`tickets.py:4787`; `harness/task_states.py` ya envuelve la llamada) ⇒ el resultado pasa de *"hizo lo contrario en silencio"* a *"no hizo nada y quedó registrado"*. Es la dirección correcta y está cubierto por el test 2 de F2 (los estados que legítimamente reabren siguen reabriendo).

### C4 — Para GitLab, el auto-sync post-completación apunta a un módulo inexistente

`backend/services/completion_sync.py:111` despacha por nombre:
```python
mod = import_module(f"services.{tracker_type}_sync")
```
Con `tracker_type == "gitlab"` eso resuelve `services.gitlab_sync`, y **`services/gitlab_sync.py` no existe** (verificado: `grep -rn "gitlab_sync" --include=*.py` sobre `backend/` devuelve **0 resultados**; en `services/` hay `gitlab_provider.py`, `gitlab_client.py`, `gitlab_ci_provider.py`, etc., pero ningún `gitlab_sync.py`). El `ModuleNotFoundError` lo traga el `except Exception` de `:116` y encima registra un fallo del breaker (`:124`).

Complementariamente, `backend/services/run_ticket_refresh.py:44-45` corta explícito:
```python
if tracker_type != "azure_devops":
    return {"refreshed": False, "reason": "non_ado_tracker"}
```

⇒ **GitLab no tiene ninguna vía de refresco de estado**, ni al completar un agente ni antes de un run. Por eso este plan **no puede** resolver C1 delegando en el sync existente: necesita un refresco propio y agnóstico de proveedor (F4).

### Frontera con planes previos

Verificada contra el código real y contra `git log --oneline -40`, **no** contra etiquetas de memoria.

| Plan | Estado real | Qué YA está hecho (no lo rehagas) | Qué NO está y este plan asume |
|---|---|---|---|
| **238** Bandeja de incidencias | **IMPLEMENTADO** (F-1..F9). Código vivo: `backend/api/incident_inbox.py`, `backend/services/incident_inbox.py`, `frontend/src/pages/IncidentInboxPage.tsx` | La vista, el endpoint de lectura, el núcleo puro de clasificación (`is_open_state`, `build_counts`), las acciones de cerrar/resolver y el lote, las flags `STACKY_INCIDENT_INBOX_ENABLED` / `_ACTIONS_ENABLED` | **No** verifica que el cierre haya surtido efecto ni refresca `ado_state`. El plan 270 **no crea otra bandeja**: corrige la cadena de escritura detrás de la que ya existe |
| **208** Auto-sync al completar + matriz | CRITICADO v2, **no declarado implementado**; pero `services/completion_sync.py` y `completion_dispatcher.py` **existen y corren** (flag `STACKY_ADO_SYNC_ON_COMPLETION_ENABLED` default **`true`**, `config.py:1398-1399`) | El sync masivo ADO al terminar un agente, coalescido y con breaker | El sync se dispara en la **completación de una ejecución** (`completion_dispatcher.py:120`), **no** en `finish_work`, que es un endpoint manual. Y para GitLab está roto (C4). El plan 270 **no toca** `completion_sync.py`: agrega un refresco puntual en el camino de escritura |
| **216** Estados centralizados | CRITICADO v2, **no implementado**; `frontend/src/pages/StatesConfigPage.tsx` **sí existe** | La sección "Estados" de la UI | `state_flow.closed_states` es **opcional y aditivo**: `services/incident_inbox.py:64-69` ya lo lee defensivo y cae al default. El plan 270 **consume** esa precedencia, no la redefine |
| **218** Paridad ADO↔GitLab | **IMPLEMENTADO** (F0..F8) | `CapabilityUnavailable` (`services/tracker_provider.py:55-72`), `provider_capabilities.py` (la capacidad `"tracker.items.update_state" → "update_item_state"` está declarada en `:60`), destino por proyecto, vocabulario canónico | La paridad quedó declarada a nivel **catálogo**, no verificada en el camino de cierre. El plan 270 usa `CapabilityUnavailable` **como mecanismo**, no lo reinventa |
| **65** GitLab origen | **PROPUESTO** (no implementado), pero `gitlab_provider.py` / `gitlab_client.py` **existen** | `GitLabTrackerProvider` con `update_item_state`, `create_item`, comments, attachments | El mapa de estados quedó con 4 claves lógicas propias y **sin defensa ante estado desconocido** (C2). El plan 270 arregla eso |
| **70** Desacople consumers→provider | **PROPUESTO**. El helper `_provider_for_ticket` **sí existe** (`tickets.py:409`) pero su flag está default OFF | El helper y su semántica de fallback | La migración de los ~27 call sites. El plan 270 **no la hace**: sólo enruta correctamente **el write de estado**, sin depender de `STACKY_TICKETS_PROVIDER_ENABLED` |
| **71** Pipeline inference agnóstico | **PROPUESTO** | — | Eje CI, ortogonal. Sin frontera |
| **79** Estados deterministas configurables | **PROPUESTO**, `STACKY_DETERMINISTIC_TASK_STATES_ENABLED` default OFF | — | El 79 decide **qué estado** poner al completar un agente. El 270 decide **a qué sistema y cómo** se escribe el estado que el operador pidió, y que el resultado se refleje. Complementarios, sin solape |
| **131** Resolutor de incidencias | **IMPLEMENTADO** | Intake, `incident_store`, `POST /api/incidents` | Eje intake, no eje estado. Sin frontera |
| **166** Ciclo de incidencias | **IMPLEMENTADO** (F0..F6) | Dev Resolutor, `canResolveWithAgent`, auto-publish | El 270 no toca el lanzamiento de agentes |
| **188** Deploy→incidencia | CRITICADO v2, no implementado | — | Eje DevOps→intake. Sin frontera |
| **200** Consola por incidencia + SQL HITL | CRITICADO v2, no implementado | — | Eje SQL/consola. Sin frontera |
| **259** Alta GitLab | CRITICADO v2, no implementado | — | Resuelve el **alta**; el 270 resuelve la **operación** sobre un proyecto GitLab ya dado de alta. Sin solape de archivos salvo `harness_flags.py` (aditivo) |

---

## 3. Principios y guardarraíles

1. **Ninguna capacidad de escritura NUEVA sobre el tracker.** Este plan **no agrega** superficies que escriban en el ADO/GitLab del operador. Corrige el enrutado y la corrección de una escritura que **ya existe hoy** y que **el operador confirma explícitamente** apretando "Cerrar". La escritura genuinamente nueva — reconciliación masiva Stacky→tracker — queda **fuera de scope** (plan 271 sugerido) con default OFF por categoría (B).
2. **Partición lectura/escritura de flags, según la directiva del operador.** Todo lo que **lee** el tracker o **compara** estados va **default ON**. Precedente citado por el operador: `STACKY_PIPELINE_NL_EDIT_ENABLED` (ON) vs `STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED` (OFF). Las tres flags de este plan son ON y se justifica una por una en su fase.
3. **Fallar declarado, nunca adivinar.** Un estado no mapeable produce `CapabilityUnavailable` (mecanismo ya existente del 218, `tracker_provider.py:55`), nunca una acción por defecto. La regla dura: **jamás emitir `reopen` cuando la intención es cerrar.**
4. **Nunca escribir en el sistema equivocado.** Un ticket cuyo `tracker_type` no es `azure_devops` **no puede** resolverse al cliente ADO. Si el proveedor real no está disponible, la acción devuelve un error honesto. **Alcance exacto de esta promesa (C2):** vale para **S1 y S2** del censo de §2 C3.bis — los dos caminos que cierran una incidencia. **NO** vale todavía para S3 y S4, que quedan con carve-out escrito y **congelados por el ratchet de F6** para que nadie agregue un cuarto. Cualquier redacción que sugiera que el invariante ya es global en el repo es falsa.
4bis. **Una capa de `services/` NUNCA importa de `api/`.** Regla del repo escrita en `services/completion_sync.py:93-95`: *"NO importar api.tickets: acopla service->api y arriesga import circular al arrancar el daemon"*. Los módulos nuevos de este plan construyen el cliente ADO con `services.project_context.build_ado_client(...)`, jamás con `api.tickets._ado_client_for_ticket`.
5. **Human-in-the-loop innegociable.** Todo cierre sigue exigiendo confirmación del operador (`FinishWorkButton` con dry-run, y `BulkActionsBar` con `armedLabel`). Este plan no agrega autonomía; agrega veracidad.
6. **Cero trabajo extra para el operador — con una excepción declarada.** Ninguna fase pide configurar nada nuevo **para Azure DevOps**: los defaults funcionan sin tocar un archivo de perfil. **Para GitLab hay un prerequisito preexistente y ajeno a este plan** (`STACKY_GITLAB_ENABLED`, default `false`, `config.py:1185-1186`); el plan no lo crea, no lo puede resolver desde su alcance y **no lo esconde**: lo declara arriba, lo nombra en el `workaround` de la excepción y lo muestra en pantalla (F5). Corrección explícita del v1, que afirmaba lo contrario sin asterisco.
7. **Backward-compatible y aditivo.** Para `tracker_type == "azure_devops"` con los defaults de fábrica, el cuerpo enviado al tracker es **byte-idéntico** al de hoy. Sólo se **agrega** el refresco posterior.
8. **Mono-operador:** sin RBAC, sin roles, sin 403.
9. **Sin costo en reposo:** ninguna fase agrega loops, daemons, polling, prefetch ni llamadas a modelos. El KPI se calcula sobre datos ya presentes en el DTO.

### Contrato de flags — las **7 patas** (contadas abriendo el código; el v1 declaraba 6)

Toda flag nueva de este plan debe tocar **las siete**, o un meta-test se pone rojo:

| # | Archivo | Qué se agrega |
|---|---|---|
| 1 | `backend/config.py` | `STACKY_X: bool = os.getenv("STACKY_X", "true").lower() in ("1", "true", "yes")` — **el default EFECTIVO** |
| 2 | `backend/services/harness_flags.py` | Alta de la key en `_CATEGORY_KEYS` (el dict arranca en `:120`). **La categoría NO se elige por intuición (C12):** las dos flags de backend de este plan van en **`"paridad_proveedores"`** (`:478`, junto a `STACKY_PROVIDER_PARITY_ENABLED` y `STACKY_TRACKER_TARGET_PER_PROJECT_ENABLED`); la del badge va **junto a `STACKY_INCIDENT_INBOX_ACTIONS_ENABLED` (`:475`)**, en su misma categoría de UI |
| 3 | `backend/services/harness_flags.py` | El `FlagSpec(key=..., type="bool", default=True, label=..., description=..., group=...)`. Grupo: `group="global"` para las dos de backend (patrón vivo `:501`, `:515`); la del badge copia el `group` del `FlagSpec` de `STACKY_INCIDENT_INBOX_ACTIONS_ENABLED` (`:4962`) |
| 4 | `backend/tests/test_harness_flags.py` | La key en `_CURATED_DEFAULTS_ON` (el set arranca en `:467`). **Ojo: esta pata vive en `tests/`, no en `services/`.** `test_default_known_only_for_curated` compara por **igualdad exacta** (`:979`) |
| 5 | `backend/services/harness_flags_help.py` | Una entrada `PlainHelp(...)` (patrón vivo: `:1479` para `STACKY_INCIDENT_INBOX_ACTIONS_ENABLED`) |
| 6 | **(C11 — la pata invisible)** `backend/tests/test_harness_flags_help.py:49-50` | `assert len(entry.on_effect) <= 240` y `assert len(entry.off_effect) <= 240`. **Los textos de `PlainHelp` no pueden pasar de 240 caracteres.** No hay que editar este archivo: hay que **respetar el límite al escribir la pata 5**, o el arnés se pone rojo sin explicación evidente |
| 7 | `deployment/export_harness_defaults.py` | Regenerar `harness_defaults.env` con el generador (no editarlo a mano) |

**Verificación binaria de las 7 patas por flag** (correr por cada una de las 3 keys nuevas):
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
Select-String -Path config.py,services\harness_flags.py,services\harness_flags_help.py,tests\test_harness_flags.py,harness_defaults.env,..\deployment\harness_defaults.env -Pattern "STACKY_TRACKER_STATE_WRITE_ROUTING_ENABLED"
```
Debe aparecer en **los 6 archivos** (en `harness_flags.py` dos veces: `_CATEGORY_KEYS` y `FlagSpec`). **Ojo: `harness_defaults.env` existe DOS veces** — `backend/harness_defaults.env` y `deployment/harness_defaults.env` — y el generador escribe **uno por corrida**: recibe el destino en `--out` (`export_harness_defaults.py:155,169,199`; el docstring `:1` declara `backend/harness_defaults.env` como el versionado). **Correr el generador una vez por destino** y verificar que la key aparezca en los dos. Ninguno se edita a mano.

### Contrato de tests

- **Todo `test_*.py` nuevo va en los DOS arneses**, que tienen sintaxis distinta:
  - `backend/scripts/run_harness_tests.sh` — lista plana (los del 238 están en `:669-673`). **El meta-test parsea sólo este.**
  - `backend/scripts/run_harness_tests.ps1` — array `$HarnessTestFiles` (`:13`, iterado en `:801`).
- **Los tests que tocan la DB se corren POR ARCHIVO.** SQLite bajo pytest es flaky por `SQLITE_LOCKED`; la corrida completa contamina. En este plan, los archivos que tocan DB son **`test_plan270_finish_work_state.py`** y **`test_plan270_state_writeback.py`**. Los otros cuatro (`test_plan270_close_intent.py`, `test_plan270_write_router.py`, `test_plan270_gitlab_close.py`, `test_plan270_state_write_ratchet.py`) **no tocan DB ni red**: son puros, dobles o lectura de archivos.
- **Frontend: no hay RTL ni jsdom.** Toda lógica testeable va en un `.ts` **puro** con vitest; el cableado se valida con un smoke manual descrito paso a paso. **Prohibido proponer tests de componentes React.**
- **`.tsx`/`.module.css` nuevos: tolerancia CERO a `style={{}}` inline** (ratchet de deuda de UI). Colores y estilos por CSS Modules o variable CSS vía `ref.current?.style.setProperty(...)` (patrón vivo: `IncidentInboxPage.tsx:96-109`).

### Gotcha de `config` — mirar cómo importa **cada** archivo

No hay regla global. En los archivos de este plan:
- `backend/api/incident_inbox.py:16` hace `from config import config as _cfg` ⇒ `getattr(_cfg, "X", default)`. **Correcto.**
- `backend/services/completion_sync.py:29` hace `from config import config as _cfg` ⇒ `getattr(_cfg, "X", False)`. **Correcto.**
- `backend/services/tracker_provider.py:122` hace `import config` ⇒ debe leer **`config.config.X`** (así lo hace en `:133` y `:141`). **Correcto.**
- `backend/services/run_ticket_refresh.py:28` hace `from config import config` ⇒ `getattr(config, "X", False)` (`:30`). **Correcto** (ahí `config` ya es la instancia).
- **`backend/services/gitlab_provider.py:25` hace `import config` a nivel MÓDULO**, con el comentario literal *"importado a nivel módulo para poder parchear en tests"*, y sus **8** lecturas de flags usan `getattr(config.config, "X", ...)` (`:46`, `:47`, `:50`, `:51`, `:186`, `:196`, `:206`, `:217`). ⇒ **el helper nuevo de F2 usa `config.config`, NO un import local.** (C9: el v1 escribía `from config import config as _cfg` dentro del helper y a la vez ponía una nota que se contradecía con su propio código.)
- `backend/api/tickets.py` también hace `import config` — lo dice su propio comentario en `:1444-1446`: *"OJO: en este módulo `config` es el MÓDULO; la instancia de flags es `config.config`"*. Este plan **no agrega ninguna lectura de config en `api/tickets.py`** (llama a `_twr.routing_enabled()` / `_wb.writeback_enabled()`), así que no hay riesgo ahí.

**Los módulos NUEVOS de este plan (`close_intent.py`, `tracker_write_router.py`, `ticket_state_writeback.py`) usan `from config import config as _cfg` + `getattr(_cfg, KEY, default)` dentro de la función.** Los módulos **EDITADOS** conservan el patrón que ya tienen (ver `gitlab_provider.py` arriba). Errar da `AttributeError`/500 o una flag que no se puede apagar en tests.

### Comando canónico de tests

Ruta del intérprete **verificada**: `Stacky Agents\backend\.venv\Scripts\python.exe` (existe; `pytest.exe` también). Desde la raíz del repo:

```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.\.venv\Scripts\python.exe -m pytest tests\<archivo>.py -q
```

Frontend:
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx vitest run src/incidents/incidentDivergence.test.ts
npx tsc --noEmit
```

---

## 4. Fases

> Cada fase es autocontenida y verificable sola. **Ninguna depende de algo construido en una fase posterior.** F0, F1 y F2 son inertes respecto del comportamiento del producto hasta que F3 las cablea.
>
> **Única excepción, declarada (E2):** **F6 se implementa AL FINAL**, porque congela conteos que dependen de que F3 ya haya reescrito S1 y S2. Correrla antes daría números distintos y un ratchet mentiroso. Está numerada F6 y listada última en el orden de implementación de §7 justamente por eso; no es una dependencia oculta.
>
> **Cruce de criterios entre fases — chequeado, sin contradicciones:** el único par que podría chocar es el test 2 de F2 (`in_progress` **debe** seguir emitiendo `state_event: "reopen"`) contra el centinela anti-reopen del test 5 de F2 y del test 8 de F0. No chocan porque el centinela recorre `ADO_CLOSE_STATES` (`"Done"`, `"Closed"`, `"Resolved"`), que es **disjunto** de `GITLAB_LOGICAL_STATES` (`functional`, `accepted`, `rejected`, `in_progress`). Ningún criterio de este plan exige "0 errores sobre un corpus" ni "N/N y si algo no cierra se agrega lo que falte": todos los conteos son **cerrados y enumerados** (11, 10, 6, 10, 12, 4, 12).

---

### F0 — Resolver puro de la intención de cierre por tracker

**Objetivo (1 frase):** un módulo puro que traduzca "el operador quiere cerrar esto en el estado X" a la instrucción concreta que entiende cada tracker, sin I/O y sin adivinar.
**Valor:** es la pieza que mata C2 en la raíz — hoy el string `"Done"` viaja crudo hasta un `dict.get()` de GitLab que devuelve `{}` y termina en `reopen`.

**Archivo a CREAR:** `Stacky Agents/backend/services/close_intent.py`

**Símbolos EXACTOS a crear:**

```python
"""Plan 270 F0 — Traducción pura de la intención de cierre por tracker.

Sin I/O, sin ORM, sin red: sólo funciones deterministas sobre strings y dicts.
"""
from __future__ import annotations
from dataclasses import dataclass

# Estados de cierre del vocabulario ADO que la bandeja ofrece hoy.
# Espejo EXACTO de FINISH_STATE_SUGGESTIONS en
# frontend/src/incidents/incidentInboxActionsModel.ts:18
ADO_CLOSE_STATES: tuple[str, ...] = ("Done", "Closed", "Resolved")

# Claves lógicas que services/gitlab_provider.py:94-102 (_state_map_for_gitlab)
# realmente entiende. Cualquier otra cosa cae en el else que emite "reopen".
GITLAB_LOGICAL_STATES: tuple[str, ...] = (
    "functional", "accepted", "rejected", "in_progress",
)
# C8 — Claves lógicas cuyo mapping tiene closed=True. Son DOS, no una:
# gitlab_provider.py:99 ("accepted") y :100 ("rejected").
GITLAB_CLOSING_LOGICAL_STATES: tuple[str, ...] = ("accepted", "rejected")
# Destino CANÓNICO al que se traduce un cierre pedido en vocabulario ADO.
# Se elige "accepted" (no "rejected") porque el operador apretó "Cerrar", que
# significa "esto quedó resuelto", no "esto se descarta".
GITLAB_CLOSE_STATE: str = "accepted"


@dataclass(frozen=True)
class CloseTarget:
    """Instrucción resuelta para UN tracker concreto."""
    tracker_type: str      # "azure_devops" | "gitlab"
    native_state: str      # lo que se le pasa a update_item_state()
    closes: bool           # True si la intención es dejar el ítem CERRADO
    source: str            # "passthrough" | "mapped" | "already_logical"


def is_close_state(state: str | None, closed_states: tuple[str, ...]) -> bool:
    """¿`state` pertenece al conjunto de estados cerrados? Case/space-insensitive.

    Reusa la MISMA normalización que services/incident_inbox.py:23 `normalize`
    para que el tablero y esta capa nunca discrepen.
    """


def resolve_close_target(
    tracker_type: str | None,
    requested_state: str,
    closed_states: tuple[str, ...],
) -> CloseTarget:
    """Traduce el estado pedido por el operador al nativo del tracker.

    Reglas (en orden):
      1. tracker_type ausente/"azure_devops" -> passthrough EXACTO del string
         pedido (backward-compat byte-idéntico). closes = is_close_state(...).
      2. tracker_type == "gitlab":
         a. si requested_state ya es una clave de GITLAB_LOGICAL_STATES ->
            source="already_logical", native = esa clave, y
            closes = (native in GITLAB_CLOSING_LOGICAL_STATES).   # C8
         b. si is_close_state(requested_state, closed_states) ->
            source="mapped", native = GITLAB_CLOSE_STATE, closes=True.
         c. si no -> ValueError("unmappable_state:<requested>"). NUNCA se
            devuelve un target que termine reabriendo.
      3. cualquier otro tracker_type -> ValueError("unsupported_tracker:<t>").

    IMPORTANTE (C1) — `closed_states` es una tupla PLANA de strings. El
    llamador que la obtiene de services.incident_inbox.resolve_closed_states()
    DEBE desempaquetar la 2-tupla: esa función devuelve (estados, fuente).
    """
```

**Casos borde a cubrir explícitamente:**
- `requested_state` con espacios/mayúsculas (`"  done "`) ⇒ debe mapear igual.
- `requested_state` vacío o `None` ⇒ `ValueError("unmappable_state:")`. Nota: el frontend nunca manda vacío (`normalizeFinishState` en `incidentInboxActionsModel.ts:37-39` cae a `"Done"`), pero el módulo no confía en su llamador.
- `closed_states` vacío ⇒ regla 2.b no aplica; se cae a `ValueError`. **No** se inventa un default acá: los defaults viven en `services/incident_inbox.py:15-17` (`DEFAULT_CLOSED_STATES`) y los inyecta el llamador.
- ADO con un estado que NO es de cierre (ej. `"Active"`) ⇒ `CloseTarget(closes=False)`, válido y passthrough. F0 no es un guardia de cierre, es un traductor.

**Tests PRIMERO — archivo:** `Stacky Agents/backend/tests/test_plan270_close_intent.py` (puro, **no toca DB**)

| # | Caso | Aserción |
|---|---|---|
| 1 | `resolve_close_target("azure_devops", "Done", DEFAULT_CLOSED_STATES)` | `native_state == "Done"`, `closes is True`, `source == "passthrough"` |
| 2 | `resolve_close_target(None, "Reviewed by Dev", DEFAULT_CLOSED_STATES)` | `native_state == "Reviewed by Dev"`, `closes is False` (no rompe estados intermedios de ADO) |
| 3 | `resolve_close_target("gitlab", "Done", DEFAULT_CLOSED_STATES)` | `native_state == "accepted"`, `closes is True`, `source == "mapped"` |
| 4 | `resolve_close_target("gitlab", "  cLoSeD  ", DEFAULT_CLOSED_STATES)` | `native_state == "accepted"` (normalización) |
| 5 | `resolve_close_target("gitlab", "in_progress", DEFAULT_CLOSED_STATES)` | `native_state == "in_progress"`, `source == "already_logical"`, **`closes is False`** (C8) |
| 6 | `resolve_close_target("gitlab", "Cualquier Cosa", DEFAULT_CLOSED_STATES)` | levanta `ValueError` con mensaje que empieza en `"unmappable_state:"` |
| 7 | `resolve_close_target("jira", "Done", ...)` | levanta `ValueError` que empieza en `"unsupported_tracker:"` |
| 8 | **Centinela anti-reopen:** para cada `s in ADO_CLOSE_STATES`, `resolve_close_target("gitlab", s, DEFAULT_CLOSED_STATES).closes is True` | los 3 cierran; ninguno levanta |
| 9 | **Centinela de espejo (claves):** `set(GITLAB_LOGICAL_STATES)` == claves de `GitLabTrackerProvider._state_map_for_gitlab()` | si alguien agrega una clave en `gitlab_provider.py` y no acá, rojo |
| 10 | **Centinela de espejo (cierre) — C8:** `set(GITLAB_CLOSING_LOGICAL_STATES)` == `{k for k, v in _state_map_for_gitlab().items() if v.get("closed")}` | hoy da `{"accepted", "rejected"}`; si alguien cambia un `closed` en el mapa y no acá, rojo |
| 11 | **Centinela de aridad (C1) — el que evita el bug de integración:** `res = resolve_closed_states(None)`; `assert isinstance(res, tuple) and len(res) == 2 and isinstance(res[0], tuple) and isinstance(res[1], str)`; y `resolve_close_target("gitlab", "Done", res)` **levanta** `ValueError` mientras que `resolve_close_target("gitlab", "Done", res[0])` **devuelve** `native_state == "accepted"` | fija por escrito que pasar la 2-tupla entera es un error, para que nadie lo "descubra" en producción |

> El test 9/10 importa `GitLabTrackerProvider` sólo para leer el método; se instancia con `object.__new__(GitLabTrackerProvider)` para no requerir red ni credenciales, ya que `_state_map_for_gitlab` (`gitlab_provider.py:94-102`) devuelve un literal y no usa `self`.
> El test 11 importa `resolve_closed_states` de `services.incident_inbox` (`:51`). Es puro y no toca DB.

**Comando:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.\.venv\Scripts\python.exe -m pytest tests\test_plan270_close_intent.py -q
```

**Criterio de aceptación (BINARIO):** los **11** tests de `test_plan270_close_intent.py` pasan y el archivo está registrado en `run_harness_tests.sh` **y** en `$HarnessTestFiles` de `run_harness_tests.ps1`.
**Verificación del registro:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
Select-String -Path scripts\run_harness_tests.sh,scripts\run_harness_tests.ps1 -Pattern "test_plan270_close_intent"
```
Debe devolver **exactamente 2 líneas** (una por arnés).

**Flag que la protege:** **ninguna.** F0 es un módulo puro sin llamadores: no cambia comportamiento hasta F2/F3. Agregar una flag a código inerte sería ruido.
**Impacto por runtime:** **nulo.** Módulo puro, sin modelo, sin runtime. Codex CLI / Claude Code CLI / GitHub Copilot Pro: idénticos. Fallback: N/A.
**Trabajo del operador: ninguno.**

---

### F1 — Enrutador de escritura de estado: nunca al tracker equivocado

**Objetivo (1 frase):** decidir **quién** escribe el estado de un ticket según su `tracker_type` real, sin caer jamás al cliente ADO para un ticket que no es de ADO.
**Valor:** mata C3. Hoy el default de fábrica manda todo ticket GitLab al cliente ADO (`tickets.py:2080`).

**Archivo a CREAR:** `Stacky Agents/backend/services/tracker_write_router.py`

**Símbolos EXACTOS a crear:**

```python
"""Plan 270 F1 — A qué proveedor le corresponde escribir el estado de un ticket.

NO depende de STACKY_TICKETS_PROVIDER_ENABLED (Plan 70, default OFF en
config.py:1231-1233): esa flag gobierna la MIGRACIÓN masiva de call sites de
api/tickets.py, no la corrección de destino de una escritura puntual.
"""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class StateWriter:
    tracker_type: str
    kind: str            # "provider" | "ado_client"
    handle: object       # TrackerProvider o AdoClient, según kind


def routing_enabled() -> bool:
    """STACKY_TRACKER_STATE_WRITE_ROUTING_ENABLED (default True)."""
    from config import config as _cfg
    return bool(getattr(_cfg, "STACKY_TRACKER_STATE_WRITE_ROUTING_ENABLED", True))


def resolve_state_writer(ticket) -> StateWriter:
    """Devuelve el escritor correcto para `ticket`, o levanta.

    - tracker_type ausente / "azure_devops" -> StateWriter(kind="ado_client")
      construido con services.project_context.build_ado_client(
          project_name=ticket.stacky_project_name,
          tracker_project=ticket.project,
          ticket=ticket,
      )
      C5: NO se importa api.tickets._ado_client_for_ticket. Ese helper
      (api/tickets.py:358-367) es EXACTAMENTE esa llamada, así que la rama ADO
      queda byte-idéntica; pero un módulo de services/ importando api/ es lo
      que el repo prohíbe por escrito en services/completion_sync.py:93-95
      ("NO importar api.tickets: acopla service->api y arriesga import
      circular al arrancar el daemon"). Mismo criterio que
      run_ticket_refresh.py:50,54.

    - tracker_type == "gitlab" -> get_tracker_provider(stacky_project_name)
      (services/tracker_provider.py:125). Si esa fábrica levanta
      TrackerConfigError (p.ej. STACKY_GITLAB_ENABLED=false,
      config.py:1185-1186), se RE-LEVANTA como CapabilityUnavailable —
      NO se cae a ADO. El `workaround` NOMBRA LA FLAG LITERAL (C4):
        "activá STACKY_TRACKER_STATE_WRITE_ROUTING_ENABLED... " -> NO.
        El texto exacto es:
        "activá STACKY_GITLAB_ENABLED en Configuración > Arnés para que "
        "Stacky pueda escribir en GitLab; hasta entonces el estado hay que "
        "cambiarlo desde la issue."
      Nunca un mensaje genérico: el operador tiene que poder actuar sin
      abrir el código.

    - cualquier otro tracker_type -> CapabilityUnavailable con
      reason="tracker '<t>' sin proveedor de escritura de estado".

    CapabilityUnavailable viene de services/tracker_provider.py:55 (Plan 218);
    su .to_payload() (:69) ya produce
    {"available": false, "capability", "provider", "reason", "workaround"}.
    """
```

**Regla dura, escrita como aserción del módulo:** `resolve_state_writer` **nunca** devuelve `kind == "ado_client"` cuando `tracker_type` normalizado no es `"azure_devops"` (ni cadena vacía/None). Es lo único que F1 promete.

**Comportamiento con la flag OFF:** `routing_enabled() is False` ⇒ los llamadores (F3) conservan **exactamente** el código de hoy (`tickets.py:2076-2080`). F1 sigue siendo importable y testeable; simplemente nadie lo consulta.

**Tests PRIMERO — archivo:** `Stacky Agents/backend/tests/test_plan270_write_router.py` (**no toca DB**: usa objetos `SimpleNamespace` como ticket)

| # | Caso | Aserción |
|---|---|---|
| 1 | ticket con `tracker_type="azure_devops"` | `kind == "ado_client"` |
| 2 | ticket con `tracker_type=None` | `kind == "ado_client"` (default histórico) |
| 3 | ticket con `tracker_type="gitlab"` y fábrica monkeypatcheada a devolver un doble | `kind == "provider"`, `handle` es el doble |
| 4 | ticket `gitlab` + `get_tracker_provider` monkeypatcheado para levantar `TrackerConfigError` | levanta `CapabilityUnavailable`; `.provider == "gitlab"`; `.capability == "tracker.items.update_state"` |
| 5 | ticket con `tracker_type="jira"` | levanta `CapabilityUnavailable` |
| 6 | **Centinela anti-fallback:** para `tracker_type` en `("gitlab", "jira", "mantis")`, ninguna invocación devuelve `kind == "ado_client"` | ninguno cae a ADO |
| 7 | `routing_enabled()` con la flag forzada a `False` vía `monkeypatch.setattr(config_instance, KEY, False)` | devuelve `False` |
| 8 | `.to_payload()` de la excepción del caso 4 | contiene `available is False`, una `reason` no vacía y un **`workaround` que contiene la cadena literal `"STACKY_GITLAB_ENABLED"`** (C4) |
| 9 | **Centinela anti-acoplamiento (C5):** `import services.tracker_write_router` y luego `assert "api.tickets" not in sys.modules` en un intérprete que no lo haya importado antes; y `Select-String` del propio archivo contra `api\.tickets\|from api` devuelve 0 líneas | un módulo de `services/` no puede arrastrar `api/tickets.py` (8332 líneas y sus imports) al arrancar |
| 10 | Caso 1 con `ticket.stacky_project_name` y `ticket.project` seteados, y `services.project_context.build_ado_client` espiado | el spy recibió **exactamente** `project_name=<stacky_project_name>`, `tracker_project=<project>`, `ticket=<ticket>` — los mismos 3 kwargs que pasa `api/tickets.py:359-364` |

> El valor `"tracker.items.update_state"` **no se inventa**: es la clave declarada en `backend/services/provider_capabilities.py:60`.
> El test 9 se escribe como dos aserciones separadas; si el chequeo de `sys.modules` resulta frágil por el orden de colección de pytest, **el que manda es el `Select-String`**, que es determinista. No se relaja ninguno de los dos: se marca el de `sys.modules` con `@pytest.mark.xfail(strict=False)` sólo si falla por orden de import, nunca borrándolo.

**Comando:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.\.venv\Scripts\python.exe -m pytest tests\test_plan270_write_router.py -q
```

**Criterio de aceptación (BINARIO):** los **10** tests pasan; el archivo está en los 2 arneses.

**Flag que la protege:** `STACKY_TRACKER_STATE_WRITE_ROUTING_ENABLED` — **default `True` (ON)**.
**Justificación del default ON (obligatoria):** esta flag **no habilita ninguna escritura nueva**; sólo **impide** que una escritura ya existente vaya al sistema equivocado. El efecto neto es **estrictamente menos escrituras erróneas**. Ninguna de las 2 categorías de excepción aplica: (A) no consume tokens en reposo — no hay loop, daemon, barrido, polling ni llamada a modelo; (B) no escribe en un sistema real del operador — al contrario, **evita** una escritura mal dirigida, y no le quita ninguna decisión (el cierre lo sigue confirmando él). Dejarla OFF significaría "por default, seguí intentando cerrar issues de GitLab con el cliente de Azure DevOps", que es exactamente el bug.
**Las 7 patas:** `config.py` · `_CATEGORY_KEYS` categoría **`"paridad_proveedores"`** (`harness_flags.py:478`) · `FlagSpec(group="global")` · `_CURATED_DEFAULTS_ON` (`tests/test_harness_flags.py:467`) · `PlainHelp` en `harness_flags_help.py` **con ≤240 chars en `on_effect` y `off_effect`** (`tests/test_harness_flags_help.py:49-50`) · regenerar `harness_defaults.env` con `deployment/export_harness_defaults.py` en sus **dos** destinos.
**Impacto por runtime:** **nulo.** La decisión de enrutado es determinista y no consulta ningún modelo. Codex CLI / Claude Code CLI / GitHub Copilot Pro: idénticos. Fallback por runtime: N/A (no hay dependencia de runtime).
**Trabajo del operador: ninguno.**

---

### F2 — GitLab deja de reabrir lo que se le pidió cerrar

**Objetivo (1 frase):** que `GitLabTrackerProvider.update_item_state` jamás emita `state_event: "reopen"` ante un estado que no supo mapear, y que en su lugar falle declarado.
**Valor:** mata C2, el bug más destructivo del eje (cerrar ⇒ reabrir).

**Archivo a EDITAR:** `Stacky Agents/backend/services/gitlab_provider.py`

**Cambio EXACTO — en `update_item_state` (`:228-260`):**

```diff
     def update_item_state(self, item_id: str, logical_state: str) -> dict:
         """Mapea logical_state → label GitLab + close si corresponde."""
         state_map = self._state_map_for_gitlab()
         proj_path = self._client._project_path()
-        mapping = state_map.get(logical_state, {})
+        mapping = state_map.get(logical_state)
+        # Plan 270 F2 — un estado no mapeable NO puede caer en el else de abajo:
+        # con mapping={} se emitía state_event="reopen", es decir, cerrar
+        # REABRÍA la issue. Ahora se declara la incapacidad (Plan 218).
+        if mapping is None:
+            if _unknown_state_guard_enabled():
+                from services.tracker_provider import CapabilityUnavailable
+                raise CapabilityUnavailable(
+                    "tracker.items.update_state",
+                    "gitlab",
+                    reason=(
+                        f"el estado '{logical_state}' no existe en el mapa de "
+                        f"estados de GitLab ({', '.join(sorted(state_map))})"
+                    ),
+                    workaround=(
+                        "usá uno de los estados lógicos soportados, o definí el "
+                        "mapeo en el perfil del cliente"
+                    ),
+                )
+            mapping = {}   # comportamiento histórico, sólo con la flag apagada
 
         update_body: dict = {}
         if mapping.get("label"):
```

**Símbolo NUEVO a crear en el mismo archivo (helper de módulo, junto a los demás helpers privados):**

```python
def _unknown_state_guard_enabled() -> bool:
    """Plan 270 F2 — STACKY_TRACKER_STATE_WRITE_ROUTING_ENABLED (default True).

    Comparte flag con F1: son la misma promesa ("no escribas cualquier cosa en
    el sistema equivocado"), y separarlas permitiría una combinación incoherente
    (enrutar bien pero seguir reabriendo).

    C9: `config` acá es el MÓDULO (gitlab_provider.py:25 hace `import config`
    "para poder parchear en tests"). La instancia de flags es `config.config`,
    igual que en las otras 8 lecturas del archivo (:46, :47, :50, :51, :186,
    :196, :206, :217). NO usar un import local.
    """
    return bool(getattr(config.config, "STACKY_TRACKER_STATE_WRITE_ROUTING_ENABLED", True))
```

> **Nota de importación (C9, corregida en v2):** `gitlab_provider.py` **ya hace `import config` a nivel módulo** (`:25`). El helper usa `config.config` y **no** agrega ningún import. El v1 escribía `from config import config as _cfg` y a la vez ponía una nota que se contradecía con su propio bloque de código; un modelo menor copia el bloque, no la nota.
> **Cómo apagar la flag en el test (F2, caso 4):** `monkeypatch.setattr(config.config, "STACKY_TRACKER_STATE_WRITE_ROUTING_ENABLED", False)` importando `config` en el test. No usar `importlib.reload(config)`: contamina el resto de la corrida.

**Casos borde:**
- `logical_state` que SÍ está en el mapa y tiene `closed=False` (ej. `"in_progress"`) ⇒ comportamiento **intacto**: emite `state_event: "reopen"`, que ahí es correcto (reabrir un ítem que vuelve a estar en progreso).
- `logical_state == "accepted"` ⇒ `state_event: "close"` + label `stacky::accepted`. Intacto.
- Flag OFF ⇒ `mapping = {}` y el comportamiento vuelve a ser **byte-idéntico** al de hoy, bug incluido. Es el rollback.

**Tests PRIMERO — archivo:** `Stacky Agents/backend/tests/test_plan270_gitlab_close.py` (**no toca DB**: doble del cliente que captura el body del `PUT`)

El doble reemplaza `self._client` por un objeto con `_project_path()` y `_request(method, path, json_body=None, params=None)` que **registra** las llamadas y devuelve `({}, 200)`.

| # | Caso | Aserción |
|---|---|---|
| 1 | `update_item_state("7", "accepted")` | el `PUT` lleva `state_event == "close"` |
| 2 | `update_item_state("7", "in_progress")` | el `PUT` lleva `state_event == "reopen"` (no regresión: sigue siendo correcto) |
| 3 | `update_item_state("7", "Done")` con flag ON | levanta `CapabilityUnavailable` y **NO se emitió ningún `PUT`** (el doble registró 0 llamadas `PUT`) |
| 4 | `update_item_state("7", "Done")` con flag OFF | emite el `PUT` con `reopen` (comportamiento histórico preservado) |
| 5 | **Centinela anti-reopen (el corazón del plan):** para cada `s` en `close_intent.ADO_CLOSE_STATES`, resolver con `resolve_close_target("gitlab", s, DEFAULT_CLOSED_STATES)` y pasarle el `native_state` a `update_item_state` | en los 3 casos el `PUT` lleva `state_event == "close"`. **Ninguno** lleva `"reopen"` |
| 6 | El mensaje de la `CapabilityUnavailable` del caso 3 | contiene el estado ofensor (`"Done"`) y lista los estados soportados |

> El test 5 es el que ata F0 con F2 y demuestra que la cadena real (lo que manda la bandeja ⇒ lo que recibe GitLab) cierra de verdad.

**Comando:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.\.venv\Scripts\python.exe -m pytest tests\test_plan270_gitlab_close.py -q
```

**Criterio de aceptación (BINARIO):** los **6** tests pasan; el archivo está en los 2 arneses; y el centinela textual siguiente devuelve **0 líneas**:
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
Select-String -Path services\gitlab_provider.py -Pattern 'state_map\.get\(logical_state, \{\}\)'
```
(la forma vieja, la que producía el `reopen` silencioso, ya no existe en el archivo).

**Flag que la protege:** `STACKY_TRACKER_STATE_WRITE_ROUTING_ENABLED` (la **misma** de F1, ya declarada; no se agrega una segunda) — **default `True` (ON)**, misma justificación: elimina una escritura destructiva, no agrega ninguna.
**Impacto por runtime:** **nulo.** Ningún modelo participa del mapeo. Los 3 runtimes: idéntico. Fallback: N/A.
**Trabajo del operador: ninguno.**

---

### F3 — `finish_work` escribe en el tracker correcto, con el estado correcto

**Objetivo (1 frase):** cablear F0 + F1 dentro del paso 4 de `finish_work`, de modo que el cierre desde el tablero llegue al tracker real del ticket traducido a su vocabulario, y que si no puede, lo diga.
**Valor:** convierte F0/F1/F2 (inertes) en el arreglo efectivo de C2 y C3 para **la acción que el operador usa**.

**Archivo a EDITAR:** `Stacky Agents/backend/api/tickets.py` — **exactamente DOS bloques**, ambos del censo de §2 C3.bis:
- **S1** — `── 4. Cambiar estado en ADO ──` (`:2073-2094`), dentro de `finish_work`.
- **S2** — `:1486-1508`, dentro de `set_stacky_status_by_ado` (**agregado en v2 por C2/C3**).

**Ninguna otra parte del archivo se toca** (es un archivo de **8332** líneas — el v1 decía 7364 — disputado por otros planes y por una sesión paralela viva). `git diff --stat` sobre `api/tickets.py` debe mostrar **sólo** esos dos bloques más la inserción `4.bis` de F4.

**Diff ilustrativo:**

```diff
     # ── 4. Cambiar estado en ADO ──────────────────────────────────────────────
     if target_ado_state and ado_id is not None:
         try:
-            _provider = _provider_for_ticket(ticket=ticket)
-            if _provider is not None:
-                _provider.update_item_state(str(ado_id), target_ado_state)
-            else:
-                _ado_client_for_ticket(ticket=ticket).update_work_item_state(int(ado_id), target_ado_state)
-            actions.append({
-                "action": "update_ado_state",
-                "ok": True,
-                "to": target_ado_state,
-                "reason": None,
-            })
+            from services import tracker_write_router as _twr
+            if _twr.routing_enabled():
+                # Plan 270 F3 — destino y vocabulario correctos, o error honesto.
+                _applied = _twr.write_state_for_ticket(
+                    ticket=ticket, ado_id=ado_id, requested_state=target_ado_state,
+                )
+                actions.append({
+                    "action": "update_ado_state",
+                    "ok": True,
+                    "to": _applied["native_state"],
+                    "requested": target_ado_state,
+                    "tracker_type": _applied["tracker_type"],
+                    "reason": None,
+                })
+            else:
+                # Camino histórico byte-idéntico (rollback por flag).
+                _provider = _provider_for_ticket(ticket=ticket)
+                if _provider is not None:
+                    _provider.update_item_state(str(ado_id), target_ado_state)
+                else:
+                    _ado_client_for_ticket(ticket=ticket).update_work_item_state(int(ado_id), target_ado_state)
+                actions.append({
+                    "action": "update_ado_state",
+                    "ok": True,
+                    "to": target_ado_state,
+                    "reason": None,
+                })
         except Exception as exc:  # noqa: BLE001
             logger.exception("finish_work: update_ado_state falló")
+            # [ADICIÓN ARQUITECTO] (C4) — el `workaround` de CapabilityUnavailable
+            # NO viaja en str(exc): su __str__ (tracker_provider.py:63) sólo arma
+            # "'<cap>' no disponible en <prov>: <reason>". Sin esto, el operador ve
+            # el problema pero nunca la solución, y el plan lo dejaría a ciegas.
+            _wa = getattr(exc, "workaround", "") or ""
             actions.append({
                 "action": "update_ado_state",
                 "ok": False,
                 "to": target_ado_state,
-                "reason": f"{type(exc).__name__}: {exc}",
+                "reason": f"{type(exc).__name__}: {exc}" + (f" — {_wa}" if _wa else ""),
             })
```

> **Por qué esto importa y no es cosmético:** el frontend ya muestra ese string tal cual (`IncidentInboxPage.tsx:215-216` `throw new Error(fallo?.reason ?? ...)`, y `FinishWorkButton` lo mismo). Concatenar el `workaround` convierte *"no disponible en gitlab"* en *"...: activá `STACKY_GITLAB_ENABLED` en Configuración > Arnés"*. **Amplifica al operador sin decidir por él** (Principio 5): le dice qué hacer, no lo hace. Cero llamadas nuevas, cero flags nuevas, cambio aditivo dentro de una key que ya existía.

**Símbolo NUEVO en `services/tracker_write_router.py` (agregado en F3, no en F1):**

```python
def write_state_for_ticket(*, ticket, ado_id, requested_state: str) -> dict:
    """Resuelve destino (F1) + vocabulario (F0) y ejecuta la escritura.

    Devuelve {"tracker_type": str, "native_state": str, "closes": bool}.
    Levanta CapabilityUnavailable (destino imposible) o ValueError
    (estado no mapeable) — el caller las traduce a actions[].ok = False.
    """
    from services.incident_inbox import resolve_closed_states
    from services.close_intent import resolve_close_target

    profile = _profile_for_ticket(ticket)          # try/except -> None
    # C1 — resolve_closed_states() devuelve (estados, fuente): DOS elementos.
    # Pasarla entera haría que is_close_state() nunca reconozca "Done" y todo
    # cierre GitLab muera con unmappable_state. Todos los callers vivos la
    # desempaquetan así (api/incident_inbox.py:65 y :118).
    closed_states, _closed_source = resolve_closed_states(profile)

    writer = resolve_state_writer(ticket)          # F1
    target = resolve_close_target(                 # F0
        writer.tracker_type, requested_state, closed_states,
    )
    if writer.kind == "ado_client":
        writer.handle.update_work_item_state(int(ado_id), target.native_state)
    else:
        writer.handle.update_item_state(str(ado_id), target.native_state)
    return {
        "tracker_type": target.tracker_type,
        "native_state": target.native_state,
        "closes": target.closes,
    }
```

- **Orden obligatorio:** `resolve_state_writer` **antes** que `resolve_close_target`, porque el `tracker_type` que traduce el vocabulario tiene que ser el mismo que se resolvió para escribir. Invertirlo permite traducir a GitLab y escribir en ADO.
- **`_profile_for_ticket(ticket)`** es un helper privado NUEVO del router: `services.client_profile.load_client_profile(ticket.stacky_project_name)` (`client_profile.py:358`) dentro de un `try/except Exception: return None` — mismo patrón defensivo que `api/incident_inbox.py:36-55` `_profile_for`, pero **sin importar `api/`** (C5).

**Diff del bloque S2 (`api/tickets.py:1486-1508`) — agregado en v2:** misma cirugía, misma forma. Se reemplazan las líneas `:1488-1492` por:

```diff
             try:
-                _provider = _provider_for_ticket(ticket=t)
-                if _provider is not None:
-                    _provider.update_item_state(str(ado_id), target_ado_state)
-                else:
-                    _ado_client_for_ticket(ticket=t).update_work_item_state(int(ado_id), target_ado_state)
-                state_change_result = {"ok": True, "to": target_ado_state}
+                from services import tracker_write_router as _twr
+                if _twr.routing_enabled():
+                    # Plan 270 F3 (S2) — mismo enrutado que finish_work: el
+                    # cierre AUTOMATICO al terminar un agente es el que mas
+                    # divergencia produce (ver KPI, seccion 1).
+                    _applied = _twr.write_state_for_ticket(
+                        ticket=t, ado_id=ado_id, requested_state=target_ado_state,
+                    )
+                    state_change_result = {
+                        "ok": True,
+                        "to": _applied["native_state"],
+                        "requested": target_ado_state,
+                        "tracker_type": _applied["tracker_type"],
+                    }
+                else:
+                    _provider = _provider_for_ticket(ticket=t)
+                    if _provider is not None:
+                        _provider.update_item_state(str(ado_id), target_ado_state)
+                    else:
+                        _ado_client_for_ticket(ticket=t).update_work_item_state(int(ado_id), target_ado_state)
+                    state_change_result = {"ok": True, "to": target_ado_state}
                 logger.info(
```
El `except` de `:1498-1508` **no se toca**: ya convierte cualquier excepción en `{"ok": False, "to": ..., "error": ..., "type": ...}`, y `CapabilityUnavailable`/`ValueError` caen ahí igual que en S1.

**Contrato de respuesta — ADITIVO:** se **agregan** las keys `requested` y `tracker_type` al action `update_ado_state` (S1) y al `state_change_result` (S2). **No se quita ni se renombra ninguna key existente** (`action`, `ok`, `to`, `reason` siguen). Un frontend viejo que sólo lea `ok`/`reason` sigue funcionando. El frontend actual lee `r.actions?.find((a) => !a.ok)` y `fallo?.reason` (`IncidentInboxPage.tsx:215-217`): intacto.

**Casos borde:**
- Ticket ADO, flag ON ⇒ `native_state == requested_state` (passthrough de F0 regla 1) ⇒ **la llamada al tracker es byte-idéntica a la de hoy**.
- Ticket GitLab sin `STACKY_GITLAB_ENABLED` ⇒ `CapabilityUnavailable` ⇒ `actions[].ok = False` con una `reason` legible. **Antes** esto escribía en ADO. Ahora no escribe nada y lo dice.
- Ticket GitLab con estado no mapeable ⇒ `ValueError("unmappable_state:...")` ⇒ `ok: False`. No hay `PUT`.
- `target_ado_state` nulo ⇒ el bloque entero se saltea, igual que hoy (`if target_ado_state and ado_id is not None`).

**Tests PRIMERO — archivo:** `Stacky Agents/backend/tests/test_plan270_finish_work_state.py` (**TOCA LA DB** ⇒ correr por archivo)

| # | Caso | Aserción |
|---|---|---|
| 1 | Ticket `azure_devops`, `finish-work` con `target_ado_state="Done"`, cliente ADO doblado | el doble recibió `update_work_item_state(<ado_id>, "Done")` — **exactamente el mismo argumento que hoy** |
| 2 | Ticket `gitlab` con provider doblado, `target_ado_state="Done"` | el doble recibió `update_item_state("<iid>", "accepted")`. **El cliente ADO no fue instanciado** (spy sobre `_ado_client_for_ticket` con 0 llamadas) |
| 3 | Ticket `gitlab` y `get_tracker_provider` levantando `TrackerConfigError` | respuesta 200 con `actions[].action == "update_ado_state"` y `ok is False`; `reason` menciona `gitlab`. **Cero llamadas al cliente ADO** |
| 4 | Mismo que 2 pero con la flag OFF | se toma el camino histórico (el spy del cliente ADO **sí** registra la llamada) — prueba de que el rollback funciona |
| 5 | Respuesta del caso 1 | contiene las keys aditivas `requested` y `tracker_type`, y conserva `action`/`ok`/`to`/`reason` |
| 6 | Ticket `gitlab`, `target_ado_state="Cualquier Cosa"` | `ok is False`, `reason` empieza con `ValueError`; el provider doblado registró **0** llamadas a `update_item_state` |
| 7 | **C1 — el bug de integración, fijado:** ticket `gitlab` con provider doblado y `target_ado_state="Done"`, con `resolve_closed_states` **sin monkeypatchear** (o sea, devolviendo su 2-tupla real) | el doble recibió `update_item_state("<iid>", "accepted")`. Si el implementador olvida el desempaquetado, este test da `ok is False` con `reason` empezando en `ValueError: unmappable_state:Done` y **no se arregla borrando el assert** |
| 8 | **S2 (C2) — mismo caso que el 2 pero en el camino automático:** ticket `gitlab`, `PATCH /api/tickets/by-ado/<ado_id>/stacky-status` (ruta verificada: `api/tickets.py:1204`, handler `set_stacky_status_by_ado` en `:1205`) con body que incluya `target_ado_state="Done"` y `status="completed"`, provider doblado, `publish_result.ok` forzado a `True`. **Dos condiciones previas verificadas leyendo el archivo:** la rama `elif target_ado_state:` (`:1477`) sólo entra si `publish_result.get("ok")` es verdadero (`:1480`), y sólo si `deterministic_task_states_enabled()` es falso (`:1467`) — con `STACKY_DETERMINISTIC_TASK_STATES_ENABLED` en su default OFF, esa es la rama viva | el doble recibió `update_item_state("<iid>", "accepted")` y el **cliente ADO no fue instanciado** (spy en 0). Es la prueba de que el camino de mayor volumen también quedó enrutado |
| 9 | **S2 con la flag OFF** | camino histórico: el spy del cliente ADO **sí** registra la llamada |
| 10 | **Paridad ADO byte-idéntica en S2:** ticket `azure_devops` con cliente ADO doblado | recibió `update_work_item_state(<ado_id>, "<target>")` con **exactamente** el mismo argumento que antes del plan |

**Comando (POR ARCHIVO — obligatorio, la DB es flaky bajo pytest):**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.\.venv\Scripts\python.exe -m pytest tests\test_plan270_finish_work_state.py -q
```
Si aparece `database table is locked`, **reintentar el mismo archivo** hasta 3 veces antes de considerarlo un fallo real (flakiness conocida de SQLite bajo pytest, no un bug del plan).

**Criterio de aceptación (BINARIO):** los **10** tests pasan; el archivo está en los 2 arneses; y el bloque histórico sigue presente bajo la rama `else` en **los dos** sitios (verificable porque los tests 4 y 9 pasan).

**Flag que la protege:** `STACKY_TRACKER_STATE_WRITE_ROUTING_ENABLED` (la misma de F1/F2) — **default ON**, misma justificación.
**Impacto por runtime:** **nulo.** `finish_work` es un endpoint HTTP que el operador dispara desde la UI; no invoca ningún runtime de agente. Codex CLI / Claude Code CLI / GitHub Copilot Pro: **idéntico**, porque ninguno participa. Fallback: N/A. (El único punto del tablero que sí depende del runtime es el botón "Resolver" — `IncidentInboxPage.tsx:226-231` pasa `runtime: agentRuntime` — y **este plan no lo toca**.)
**Trabajo del operador: ninguno.**

---

### F4 — Después de escribir, el tablero se entera: writeback del estado local

**Objetivo (1 frase):** tras una escritura de estado exitosa, releer el ítem del tracker y actualizar `Ticket.ado_state` en la base local, para que la fila deje de mentir.
**Valor:** **mata C1, la causa raíz del abandono.** Es la fase con mayor impacto sobre el KPI.

**Archivo a CREAR:** `Stacky Agents/backend/services/ticket_state_writeback.py`

```python
"""Plan 270 F4 — Refresco del snapshot local de estado tras escribir en el tracker.

Por qué un módulo propio y no reusar lo existente:
  - services/run_ticket_refresh.py:44-45 corta con "non_ado_tracker": no sirve
    para GitLab.
  - services/completion_sync.py:111 despacha a services.<tracker>_sync, y
    services/gitlab_sync.py NO EXISTE (0 hits en todo el backend): para GitLab
    levanta ModuleNotFoundError, que además abre el breaker.
  - Además completion_sync se dispara en la completación de una EJECUCIÓN
    (completion_dispatcher.py:120), no en finish_work, que es manual.

Este módulo lee del tracker y escribe SÓLO en la base local de Stacky.
"""
from __future__ import annotations

def writeback_enabled() -> bool:
    """STACKY_TICKET_STATE_WRITEBACK_ENABLED (default True)."""
    from config import config as _cfg
    return bool(getattr(_cfg, "STACKY_TICKET_STATE_WRITEBACK_ENABLED", True))


def refresh_local_state(ticket_id: int) -> dict:
    """Relee el ítem del tracker y persiste su estado en Ticket.ado_state.

    Devuelve {"refreshed": bool, "reason": str, "ado_state": str|None}.
    NUNCA levanta: un fallo de refresco no puede tumbar un cierre que YA se
    escribió en el tracker (fail-open, mismo criterio que
    run_ticket_refresh.py:64-69).

    Razones posibles: "ok" | "flag_off" | "ticket_not_found" | "no_ado_id" |
    "writer_unavailable" | "tracker_error: <detalle>" | "state_absent".
    """
```

**Cómo lee el estado, por proveedor** (reusa el enrutador de F1, `resolve_state_writer`):
- `kind == "ado_client"` ⇒ `services.ado_sync.upsert_single_work_item(handle, int(ado_id))` (`ado_sync.py:235`), que ya persiste el ticket completo en la base local (`ado_sync.py:337` lo registra).
- `kind == "provider"` ⇒ `handle.get_item(str(ado_id))` (método del puerto, declarado en `tracker_provider.py:82`; la implementación GitLab está en `gitlab_provider.py:174-177` y devuelve `self._normalize_issue(body)`).
  **C10 — la key es literalmente `"state"`, no "el campo de estado":** `_normalize_issue` la produce en `gitlab_provider.py:85` con `body.get("state") or ""`, y GitLab devuelve `"opened"` / `"closed"`. Se escribe `Ticket.ado_state = str(item.get("state") or "")`. **Que `"closed"` cuente como cerrado no es casualidad:** `DEFAULT_CLOSED_STATES` incluye `"Closed"` y la comparación es case-insensitive vía `normalize()` — está documentado en `services/incident_inbox.py:13-14`. Si `item.get("state")` viene vacío, `reason = "state_absent"` y **la columna NO se pisa**.
- **`session_scope` se importa de `db.py:485`** (`from db import session_scope`), **no de `models.py`**. Errar da `ImportError`.

**Regla de escritura mínima:** este módulo **sólo** escribe `Ticket.ado_state` (y `last_synced_at` si ya existe la columna — existe: `models.py` la declara y `api/incident_inbox.py:156` ordena por ella). **No** toca `stacky_status`, ni `title`, ni `work_item_type`: no es un sync, es un refresco quirúrgico de la columna de la que depende el tablero.

**Cableado — archivo a EDITAR:** `Stacky Agents/backend/api/tickets.py`, **DOS inserciones** (el v1 tenía una sola, y por eso el KPI era inalcanzable — C3):

**(a) S1 — en `finish_work`**, inmediatamente después del bloque del paso 4 (tras el `except` que cierra en `:2094`) y **antes** del paso 5:

```python
    # ── 4.bis Plan 270 F4 — reflejar el estado real en la base local ──────────
    # Sin esto, la bandeja sigue pintando "Abierta" una fila recién cerrada,
    # porque deriva is_open de Ticket.ado_state (api/incident_inbox.py:163) y
    # set_status NO toca esa columna (services/ticket_status.py no la menciona).
    if target_ado_state and ado_id is not None:
        from services import ticket_state_writeback as _wb
        if _wb.writeback_enabled():
            _wb_result = _wb.refresh_local_state(ticket_id)
            actions.append({
                "action": "refresh_local_state",
                "ok": bool(_wb_result.get("refreshed")),
                "to": _wb_result.get("ado_state"),
                "reason": _wb_result.get("reason"),
            })
```

**(b) S2 — en `set_stacky_status_by_ado`** (agregado en v2), inmediatamente después del bloque `:1477-1508` (el `elif target_ado_state:` completo) y **antes** del `return jsonify({` de `:1510`:

```python
    # ── Plan 270 F4 (S2) — reflejar el estado real en la base local ───────────
    # Este es el camino de MAYOR volumen: lo dispara el fin de un agente. Sin
    # esto, cada agente que termina deja una fila divergente (stacky_status
    # "completed" + ado_state viejo) y el KPI del plan nunca llega a 0.
    if target_ado_state and ado_id is not None and state_change_result.get("ok"):
        from services import ticket_state_writeback as _wb
        if _wb.writeback_enabled():
            state_change_result["local_refresh"] = _wb.refresh_local_state(t.id)
```

> **Diferencia deliberada con (a):** en S1 el writeback corre **aunque la escritura haya fallado** (para mostrar la verdad); en S2 corre **sólo si `state_change_result.ok`**, porque S2 no tiene una lista de `actions[]` donde contar el fallo y agregar una lectura de red por cada agente que falla al transicionar sería costo sin señal. El fallo de S2 ya queda registrado en `state_change_result` (`:1503-1508`).
> **Por qué `t.id` y no `ticket_id`:** en `set_stacky_status_by_ado` el parámetro de ruta es `ado_id`, y la fila local es `t` (resuelta en `:1283` y alrededores). `refresh_local_state` toma el **id local**, no el del tracker.

**Casos borde:**
- La escritura del paso 4 falló ⇒ el writeback **igual corre**, y trae el estado real (que seguirá siendo el viejo). Eso es **deseable**: la fila muestra la verdad, no el deseo. El action `update_ado_state.ok = False` ya cuenta la historia del fallo.
- El tracker no responde ⇒ `{"refreshed": False, "reason": "tracker_error: ..."}`, el cierre **no** se revierte y el endpoint sigue devolviendo 200. Fail-open explícito.
- Ticket con `ado_id` sentinela (negativo) ⇒ `"no_ado_id"`, sin llamada de red. (Los sentinelas `-1..-9` son un patrón vivo del repo; `run_ticket_refresh.py:41-42` ya los descarta con `ado_id <= 0`.)
- Flag OFF ⇒ no se agrega el action y el comportamiento es idéntico al de hoy.

**Tests PRIMERO — archivo:** `Stacky Agents/backend/tests/test_plan270_state_writeback.py` (**TOCA LA DB** ⇒ correr por archivo)

| # | Caso | Aserción |
|---|---|---|
| 1 | Ticket ADO con `ado_state="Active"`; `upsert_single_work_item` doblado para dejar `"Done"` en la fila | tras `refresh_local_state`, `Ticket.ado_state == "Done"` en la base |
| 2 | Ticket GitLab con provider doblado cuyo `get_item` devuelve estado `"closed"` | `Ticket.ado_state == "closed"`; `refreshed is True` |
| 3 | **El KPI, medido de punta a punta:** ticket incidencia (`work_item_type="Issue"`) abierto; se llama `finish-work` con `target_ado_state="Done"`; el doble del tracker pasa a reportar `"Done"` | luego, `GET /api/incident-inbox/items?scope=open` **NO** devuelve ese ítem, y en `scope=all` el ítem tiene `is_open is False`. **Este es el test que prueba que el tablero dejó de mentir.** |
| 4 | Provider que levanta al leer | `{"refreshed": False}`, `reason` empieza con `"tracker_error:"`, y **el ticket conserva** su `ado_state` previo (no se pisa con `None`) |
| 5 | Flag `STACKY_TICKET_STATE_WRITEBACK_ENABLED` OFF | `reason == "flag_off"`; la columna no cambia; el action `refresh_local_state` **no** aparece en la respuesta de `finish-work` |
| 6 | Ticket con `ado_id = -3` | `reason == "no_ado_id"`; cero llamadas de red (spy en 0) |
| 7 | El writeback **no** pisa `stacky_status` | tras el caso 1, `stacky_status` conserva el valor que tenía antes de llamar a `refresh_local_state` |
| 8 | **C10 — estado ausente:** provider doblado cuyo `get_item` devuelve `{"state": ""}` | `reason == "state_absent"`; `Ticket.ado_state` **conserva su valor previo** (no se pisa con `""`) |
| 9 | **C10 — el mapeo GitLab→cerrado, fijado:** `is_open_state("closed", DEFAULT_CLOSED_STATES) is False` y `is_open_state("opened", DEFAULT_CLOSED_STATES) is True` | prueba que los dos valores literales que devuelve GitLab caen del lado correcto, sin depender de que alguien "sepa" que `"Closed"` está en el default |
| 10 | **C3 — el KPI en el camino AUTOMÁTICO:** ticket GitLab incidencia abierto; `PATCH /api/tickets/by-ado/<ado_id>/stacky-status` con `status="completed"`, `target_ado_state="Done"`, provider doblado que tras el `update_item_state` pasa a reportar `{"state": "closed"}` en `get_item` | `GET /api/incident-inbox/items?scope=open` **NO** devuelve ese ítem. **Este es el test que prueba que el plan cierra el eje y no sólo el botón manual.** |
| 11 | S2 con `state_change_result.ok is False` | `local_refresh` **no** aparece en la respuesta y el provider registró **0** llamadas a `get_item` (no se gasta una lectura de red por cada fallo) |
| 12 | **C6 — `diverged_count` por agregación** (el test que le faltaba a la key en el v1): sembrar 3 tickets incidencia `stacky_status="completed"` con `ado_state="Active"` y 2 `completed` con `ado_state="Done"` | `GET /api/incident-inbox/items?scope=all` devuelve `diverged_count == 3`, **independientemente** de cuántas filas traiga `items` |

**Comando (POR ARCHIVO):**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.\.venv\Scripts\python.exe -m pytest tests\test_plan270_state_writeback.py -q
```

**Criterio de aceptación (BINARIO):** los **12** tests pasan (en particular el **3** y el **10**, que son el KPI en los dos caminos, y el **12**, que le da cobertura a `diverged_count`); el archivo está en los 2 arneses.

> **Costura F4↔F5 declarada:** el caso 12 vive en **este** archivo (backend, toca DB) aunque la key `diverged_count` se especifique en F5. Es deliberado: F5 es la fase de frontend y su archivo de tests es `.ts` puro, que **no puede** golpear un endpoint. No duplicar el caso en los dos lados.

**Flag que la protege:** `STACKY_TICKET_STATE_WRITEBACK_ENABLED` — **default `True` (ON)**.
**Justificación del default ON (obligatoria):** la operación es **leer del tracker y escribir en la base local de Stacky**. No escribe en ningún sistema del operador, no destruye datos y no le saca ninguna decisión ⇒ **no aplica la categoría (B)**. No hay loop, daemon, barrido, polling, prefetch ni llamada a modelo: se ejecuta **una vez, sincrónicamente, dentro de una acción que el operador acaba de disparar** ⇒ **no aplica la categoría (A)**. Es lectura + reflejo local, y la directiva es explícita: **todo lo de solo lectura va ON, sin excepción**. Dejarla OFF sería dejar el bug principal apagado por default.
**Las 7 patas:** literalmente ídem F1 (misma categoría `"paridad_proveedores"`, mismo `group="global"`, mismo límite de 240 chars, mismo generador en los dos destinos).
**Impacto por runtime:** **nulo.** Ningún modelo participa; es una lectura HTTP al tracker. Los 3 runtimes: idéntico. Fallback: N/A.
**Trabajo del operador: ninguno.**

---

### F5 — El tablero muestra lo que quedó desalineado (solo lectura, costo cero)

**Objetivo (1 frase):** marcar en la bandeja las incidencias que Stacky da por cerradas pero el tracker sigue mostrando abiertas, con una comparación **puramente local** que no agrega ni una llamada de red.
**Valor:** hace visible el KPI, cubre las filas que ya quedaron desalineadas antes de este plan, y le devuelve al operador la señal que hoy no tiene: *"esto no se sincronizó, revisalo"*.

**Por qué es gratis:** `is_open` y `stacky_status` **ya viajan** en cada ítem del DTO (`api/incident_inbox.py:163` agrega `is_open`; `models.py:101` incluye `stacky_status` en `to_dict()`; el tipo del frontend ya los declara en `frontend/src/incidents/incidentInboxModel.ts:17` y `:19`). **Cero endpoints nuevos, cero llamadas nuevas, cero costo por fila.**

**Archivo a CREAR:** `Stacky Agents/frontend/src/incidents/incidentDivergence.ts` (`.ts` **puro**: sin React, sin DOM, sin fetch)

```ts
/**
 * Plan 270 F5 — Detección PURA de divergencia entre Stacky y el tracker.
 *
 * Divergente = Stacky dice "completed" pero el tablero sigue pintando la fila
 * como abierta. Es exactamente el sintoma que hizo que el operador abandonara
 * el tablero, y se calcula sin una sola llamada extra: ambos campos ya viajan
 * en el DTO de /api/incident-inbox/items.
 */
import type { IncidentInboxItem, IncidentInboxStatus } from "./incidentInboxModel";

/** Estado terminal de Stacky que implica "yo ya cerre esto". Espejo de
 *  services/status_vocabulary.py:11 TERMINAL_STATUSES, subconjunto "exitoso". */
export const STACKY_CLOSED_STATUS = "completed";

export const DIVERGENCE_BADGE_LABEL = "Sin sincronizar";
export const DIVERGENCE_BADGE_TITLE =
  "Stacky dio esta incidencia por cerrada, pero el tracker la sigue mostrando abierta.";

/** ¿Esta fila esta desalineada respecto del tracker? */
export function isDiverged(item: IncidentInboxItem): boolean {
  return item.stacky_status === STACKY_CLOSED_STATUS && item.is_open === true;
}

/** Cuantas filas de la lista estan desalineadas (el KPI del plan 270). */
export function countDiverged(items: IncidentInboxItem[]): number {
  return items.filter(isDiverged).length;
}

/** Texto del chip de resumen. Cadena VACIA cuando no hay divergencia, para que
 *  la UI no muestre un chip con cero (ruido). */
export function divergenceSummary(items: IncidentInboxItem[]): string {
  const n = countDiverged(items);
  if (n === 0) return "";
  return n === 1 ? "1 sin sincronizar" : `${n} sin sincronizar`;
}

/** Filtro del chip: cuando esta activo, solo las divergentes. */
export function filterDiverged(
  items: IncidentInboxItem[],
  onlyDiverged: boolean,
): IncidentInboxItem[] {
  return onlyDiverged ? items.filter(isDiverged) : items;
}

/** C16 — Gate del badge, ESTRICTO a `true`, espejo de resolveInboxActionsEnabled
 *  (incidentInboxActionsModel.ts:31-35): un backend viejo que no manda la key
 *  deja el badge oculto y la pagina sigue funcionando. */
export function resolveDivergenceBadgeEnabled(
  status: IncidentInboxStatus | null | undefined,
): boolean {
  return status?.divergence_badge_enabled === true;
}
```

**C16 — el tipo del status hay que ampliarlo.** En `frontend/src/incidents/incidentInboxModel.ts`, dentro de `interface IncidentInboxStatus` (`:42-54`), agregar **opcional**:
```ts
  /** Plan 270 F5 — gate del badge "Sin sincronizar". OPCIONAL: un backend
   *  viejo no la manda y el badge queda oculto. */
  divergence_badge_enabled?: boolean;
```
y en `interface IncidentInboxResponse` (`:28-40`), junto a `untyped_count` (`:34`):
```ts
  /** Plan 270 F5 — incidencias completed en Stacky pero abiertas en el tracker.
   *  Conteo EXACTO por agregacion: no depende del LIMIT de la lista. */
  diverged_count: number;
```
Sin esto `npx tsc --noEmit` no falla (las keys extra de un `jsonify` no rompen), pero el frontend **no puede leerlas tipadas** y alguien las va a acceder con `as any`.

**Archivos a EDITAR:**
1. `Stacky Agents/frontend/src/pages/IncidentInboxPage.tsx` — insertar, dentro del `.map` de filas (bloque `:487-540`), inmediatamente **después** del badge Abierta/Cerrada (`:504-506`):
   ```tsx
   {divergenciaVisible && isDiverged(item) && (
     <span className={styles.divergedBadge} title={DIVERGENCE_BADGE_TITLE}>
       {DIVERGENCE_BADGE_LABEL}
     </span>
   )}
   ```
   **C7 — DÓNDE se aplica el filtro, literal (el v1 sólo decía "sobre `visible`", y las dos lecturas posibles tienen defecto).** `visible` (`:175`) alimenta **tres** consumidores: `byState` (`:176`), `visibleIds` (`:182` → `useRowSelection` → "Seleccionar todo" → **cierre en LOTE, que ESCRIBE en el tracker**) y el `.map` de filas (`:478`). Si el filtro se aplica sólo dentro del `.map`, "Seleccionar todo" selecciona filas **ocultas** y un cierre en lote escribe sobre incidencias que el operador **nunca vio** — violación directa del Principio 5. La única forma correcta:
   ```tsx
   const [soloDivergentes, setSoloDivergentes] = useState(false);
   // NUEVO memo, entre :176 y :182:
   const mostrados = useMemo(
     () => filterDiverged(visible, soloDivergentes),
     [visible, soloDivergentes],
   );
   ```
   - el `.map` de filas (`:478`) itera **`mostrados`**;
   - `visibleIds` (`:182`) se calcula sobre **`mostrados`** (nunca se puede seleccionar lo que no se ve);
   - `byState` (`:176`) **sigue sobre `visible`** (los chips de estado deben mostrar los totales reales, no los del filtro).

   **C14 — el chip es un `Button`, no un `<span>` clickeable.** El bloque `:455-476` sólo tiene `<span className={styles.chip}>` no interactivos; un `<span>` con `onClick` no es alcanzable por teclado. El archivo **ya importa `Button`** de `../components/ui` (`:72`). El chip nuevo va **después** del `byState.map` (`:471-475`), dentro del mismo `<div className={styles.chips}>`:
   ```tsx
   {divergenciaVisible && divergenceSummary(visible) !== "" && (
     <Button
       variant="secondary"
       size="sm"
       aria-pressed={soloDivergentes}
       title={DIVERGENCE_BADGE_TITLE}
       onClick={() => setSoloDivergentes((v) => !v)}
     >
       {divergenceSummary(visible)}
     </Button>
   )}
   ```
   Ojo: el texto del chip se calcula sobre **`visible`** (el total desalineado), no sobre `mostrados` — si no, al activar el filtro el número se congelaría en sí mismo.
2. `Stacky Agents/frontend/src/pages/IncidentInboxPage.module.css` — clase `.divergedBadge`. **Sin colores literales ni HEX**: usar los tokens que el tema **sí** define, verificados abriendo `frontend/src/theme.css`: `--danger` (`:21` dark / `:191` light), `--border` (`:8` / `:177`), `--text-primary` (`:12` / `:182`), `--bg-panel` (`:6` / `:175`), `--accent` (`:17` / `:187`). **No** inventar tokens de paleta de la familia `--color-*`: verificado con `grep -n -- "--color-" frontend/src/theme.css`, lo **único** que existe con ese prefijo es `--color-scheme` (`:163`, `:243`, `:279`), que es el switch light/dark de CSS y **no es un color**. Cualquier `--color-danger`, `--color-border`, etc. resuelve a vacío y deja el badge invisible.
3. `Stacky Agents/backend/api/incident_inbox.py` — agregar al payload de `/items` (junto a `untyped_count`, `:174`) una key **aditiva**.

   **C6 — el v1 lo calculaba mal y su propia justificación era falsa.** El v1 escribía `sum(1 for i in items ...)` y decía que servía "para que el conteo sea correcto aun cuando la lista venga truncada por `MAX_ITEMS`" — pero `items` **es** la lista ya truncada (`rows = rows[:MAX_ITEMS]`, `:159`), así que no arreglaba nada. Además no tenía ni consumidor ni test. La versión correcta es una agregación real, **dentro** del `with session_scope()` y **al lado de los counts que ya existen** (`:131-135`), reusando el `incident_q` y el `state_expr` ya construidos:
   ```python
        # Plan 270 F5 — divergencia EXACTA por agregación (no depende del LIMIT).
        # Misma regla de dos condiciones que isDiverged() en el .ts.
        diverged_count = incident_q.filter(
            Ticket.stacky_status == "completed"
        ).filter(~state_expr.in_(closed_norm)).count()
   ```
   Es **una** `COUNT(*)` más sobre una query ya filtrada, sin traer filas: costo despreciable y correcto con truncado. Va en la respuesta como `"diverged_count": diverged_count,`.

   **Consumidor real (si no, es código muerto):** el chip usa `dto?.diverged_count ?? countDiverged(visible)` — el valor del servidor manda, y el cálculo local es el fallback para un backend viejo. Así la key **tiene** consumidor y el `.ts` sigue siendo la fuente de la regla.

   **Test que lo fija (nuevo, en `test_plan270_state_writeback.py`, caso 12):** sembrar 3 tickets `completed` con `ado_state="Active"` y 2 `completed` con `ado_state="Done"` ⇒ `GET /api/incident-inbox/items?scope=all` devuelve `diverged_count == 3`. Sin este test la key vuelve a quedar sin cobertura (era el agujero de R5 en el v1).

**Gate del badge:** `divergenciaVisible = resolveDivergenceBadgeEnabled(statusQ.data)`, resuelto de la respuesta de `/api/incident-inbox/status`, agregando una key aditiva `divergence_badge_enabled` en el `jsonify` de `incident_inbox_status` — que va de **`:66` a `:82`**, con `actions_enabled` en **`:77`** (el v1 decía `:65-81` y `:76`: desfasado en 1). **Estricto a `true`**, igual que `resolveInboxActionsEnabled` (`incidentInboxActionsModel.ts:31-35`): un backend viejo que no manda la key deja el badge oculto y la página sigue funcionando.

**Casos borde:**
- Ítem sin `stacky_status` (backend viejo) ⇒ `isDiverged` devuelve `false`. Nunca marca de más.
- Ítem con `stacky_status: "running"` y abierto ⇒ **no** divergente (está trabajando, no desincronizado).
- Ítem con `stacky_status: "error"` y abierto ⇒ **no** divergente (falló, y eso ya se ve por otro lado). La regla es deliberadamente estrecha: **sólo** `completed` + abierto.
- Lista vacía ⇒ `divergenceSummary` devuelve `""` y no se renderiza chip.
- `scope === "open"` ⇒ todas las divergentes están en la lista por definición (son abiertas). El chip es útil justamente ahí.

**Tests PRIMERO — archivo:** `Stacky Agents/frontend/src/incidents/incidentDivergence.test.ts` (vitest, **puro**, sin RTL ni jsdom)

| # | Caso | Aserción |
|---|---|---|
| 1 | `{stacky_status: "completed", is_open: true}` | `isDiverged` ⇒ `true` |
| 2 | `{stacky_status: "completed", is_open: false}` | `false` |
| 3 | `{stacky_status: "running", is_open: true}` | `false` |
| 4 | `{stacky_status: "error", is_open: true}` | `false` |
| 5 | ítem sin `stacky_status` | `false` |
| 6 | lista con 3 divergentes de 7 | `countDiverged === 3`; `divergenceSummary === "3 sin sincronizar"` |
| 7 | lista sin divergentes | `divergenceSummary === ""` |
| 8 | 1 divergente | `"1 sin sincronizar"` (singular) |
| 9 | `filterDiverged(items, true)` / `(items, false)` | devuelve sólo divergentes / la lista intacta (misma referencia de elementos) |
| 10 | `resolveDivergenceBadgeEnabled(undefined)` y `(null)` | `false` (C16) |
| 11 | `resolveDivergenceBadgeEnabled({...status, divergence_badge_enabled: true})` | `true`; y con la key ausente ⇒ `false` (estricto, nunca fail-open) |
| 12 | **C14/C7 — coherencia chip↔filtro:** `divergenceSummary(visible)` sobre una lista con 3 divergentes y luego `filterDiverged(visible, true)` | el texto sigue diciendo `"3 sin sincronizar"` y la lista filtrada tiene largo 3 (el número no se calcula sobre la lista ya filtrada) |

**Comando:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx vitest run src/incidents/incidentDivergence.test.ts
npx tsc --noEmit
```

**Smoke manual (obligatorio — no hay RTL/jsdom para cubrirlo), paso a paso:**
1. Levantar backend y frontend en dev.
2. Ir a la pestaña **Incidencias** (ruta `/incidencias`).
3. En la base local, forzar una fila a `stacky_status='completed'` con un `ado_state` abierto (ej. `Active`).
4. Recargar la bandeja: la fila muestra el badge **"Sin sincronizar"** y el chip de resumen dice **"1 sin sincronizar"**.
5. Click en el chip ⇒ la lista se reduce a esa fila. Segundo click ⇒ vuelve a la lista completa. **Con el chip activo, marcar "Seleccionar todo" y verificar que el contador del lote dice `1`, no el total sin filtrar** (C7 — si dice más, el filtro se aplicó en el lugar equivocado y el lote escribiría sobre filas ocultas).
6. Apretar **Cerrar** sobre una incidencia abierta real y confirmar. Verificar que, **sin recargar la página**, la fila pasa a "Cerrada" (o desaparece si el scope es "Solo abiertas"). **Ese es el smoke que valida F4 de punta a punta.**
7. Verificar en las herramientas de desarrollo que **no aparece ninguna petición nueva** por fila (el badge no dispara red).
8. **Smoke GitLab (C4) — obligatorio, es la mitad del título del plan.** Con un proyecto GitLab dado de alta: (8a) con `STACKY_GITLAB_ENABLED` **apagada** (default), apretar Cerrar ⇒ el toast/fila muestra el error y el texto **nombra `STACKY_GITLAB_ENABLED`**; **nada** se escribió en GitLab (verificar la issue). (8b) encender la flag desde Configuración > Arnés, repetir ⇒ la issue de GitLab queda **cerrada** (no reabierta) con el label `stacky::accepted`, y la fila del tablero pasa a "Cerrada" sin recargar.
9. **Smoke del camino automático (C3).** Lanzar el Dev Resolutor sobre una incidencia y dejar que termine. Sin tocar nada más, la fila debe reflejar el estado real del tracker. Antes del plan quedaba `completed` + "Abierta".

**Criterio de aceptación (BINARIO):** los **12** tests de vitest pasan, `npx tsc --noEmit` sale limpio, y el ratchet de deuda de UI sigue verde (cero `style={{}}` inline en los archivos tocados y **cero HEX** en el `.module.css` nuevo).
**Verificación del ratchet:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx vitest run src/__tests__/uiDebtRatchet.test.ts
```

**Flag que la protege:** `STACKY_INCIDENT_DIVERGENCE_BADGE_ENABLED` — **default `True` (ON)**.
**Justificación del default ON (obligatoria):** es **solo lectura pura sobre datos ya presentes en la respuesta**. No hace ninguna llamada de red nueva, no consulta ningún modelo, no escribe en ningún lado. No aplica (A) — no hay loop/daemon/polling/prefetch ni gasto de tokens en reposo, el cálculo es una comparación de dos strings por fila. No aplica (B) — no escribe nada, no destruye nada, no decide nada por el operador: **le muestra** el problema para que decida él. La directiva es explícita: **todo lo de solo lectura va ON**.
**Las 7 patas:** ídem F1, con una diferencia: `STACKY_INCIDENT_DIVERGENCE_BADGE_ENABLED` va en `_CATEGORY_KEYS` **junto a `STACKY_INCIDENT_INBOX_ACTIONS_ENABLED` (`harness_flags.py:475`)**, no en `"paridad_proveedores"`, y su `FlagSpec` copia el `group` del de `:4962`. (Para `STACKY_TICKET_STATE_WRITEBACK_ENABLED` sí es literalmente ídem F1.)
**Impacto por runtime:** **nulo.** Es una función pura de frontend. Codex CLI / Claude Code CLI / GitHub Copilot Pro: idéntico. Fallback: N/A.
**Trabajo del operador: ninguno.** El badge aparece solo; el chip es opcional y no modifica nada.

---

### F6 — [ADICIÓN ARQUITECTO] Ratchet de destino: el censo de escrituras de estado queda congelado

**Objetivo (1 frase):** convertir el Principio 4 de una promesa de prosa en un **gate binario y repo-wide**, congelando el conjunto exacto de sitios que todavía pueden escribir el estado sin pasar por el enrutador, para que **nadie pueda agregar un cuarto** sin que la suite se ponga roja.

**Por qué esta fase existe (y por qué el v1 la necesitaba).** El v1 llamaba "centinela anti-fallback" al test 6 de F1 — un unit test del router. Ese test prueba que **el router** nunca devuelve `ado_client` para un ticket no-ADO; no prueba **nada** sobre el resto del repo. Con el censo de §2 C3.bis a la vista (S3 y S4 siguen ahí, y `api/tickets.py` tiene 8332 líneas y una sesión paralela viva escribiendo encima), la única forma honesta de sostener el invariante es un **ratchet**: un número congelado que sólo puede bajar.

Es el mismo mecanismo que el repo ya usa para la deuda de UI (`frontend/src/__tests__/uiDebtRatchet.test.ts`) y para la lista de tests del arnés (`run_harness_tests.sh:8`: *"La lista HARNESS_TEST_FILES es un RATCHET: solo crece"*). **Se reusa el patrón, no se inventa uno.**

**Archivo a CREAR:** `Stacky Agents/backend/tests/test_plan270_state_write_ratchet.py` (**no toca DB, no toca red**: lee archivos con `pathlib` y cuenta con `re`).

**Símbolos EXACTOS:**

```python
"""Plan 270 F6 — Ratchet del censo de escrituras de estado del tracker.

El Principio 4 del plan 270 ("un ticket no-ADO nunca se escribe con el cliente
ADO") vale hoy para S1 (api/tickets.py finish_work) y S2
(set_stacky_status_by_ado). S3 y S4 quedaron con carve-out escrito. Este test
CONGELA ese censo: si aparece un quinto sitio, se pone rojo.

NO se arregla subiendo el número. Se arregla enrutando el sitio nuevo por
services.tracker_write_router, o agregando un carve-out al plan y bajándolo.
"""
# Sitios que TODAVÍA escriben estado sin pasar por tracker_write_router.
# Formato: (ruta_relativa_a_backend, patrón_regex, cantidad_esperada)
FROZEN_UNROUTED_STATE_WRITES: tuple[tuple[str, str, int], ...] = (
    # S3: estado inicial de una Task recién creada (eje Plan 70).
    # S1 y S2 ya NO cuentan acá: quedaron detrás de la rama `else` del rollback,
    # que es código histórico gateado, no un camino vivo por default.
    ("api/tickets.py", r"_ado_client_for_ticket\([^)]*\)\.update_work_item_state\(", 2),
    ("api/tickets.py", r"\bado\.update_work_item_state\(", 1),
    ("harness/task_states.py", r"provider\.update_item_state\(", 1),
)
```

> **De dónde salen los números (contados, no estimados).** Con el plan aplicado, `_ado_client_for_ticket(...).update_work_item_state(` queda **2** veces en `api/tickets.py` — las dos ramas `else` de rollback de S1 (`:2080` hoy) y S2 (`:1492` hoy), que sólo corren con la flag apagada. `ado.update_work_item_state(` queda **1** vez (S3, `:4781` hoy). `provider.update_item_state(` en `harness/task_states.py` queda **1** vez (S4, `:173` hoy). **El implementador DEBE re-contar con el comando de abajo antes de congelar**, porque una sesión paralela puede haber movido el archivo; si el conteo real difiere, se ajusta el número **y se documenta en este plan por qué**, nunca en silencio.

**Comando para obtener los números reales antes de congelar:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
(Select-String -Path api\tickets.py -Pattern '_ado_client_for_ticket\([^)]*\)\.update_work_item_state\(').Count
(Select-String -Path api\tickets.py -Pattern '\bado\.update_work_item_state\(').Count
(Select-String -Path harness\task_states.py -Pattern 'provider\.update_item_state\(').Count
```

**Tests — 4 casos:**

| # | Caso | Aserción |
|---|---|---|
| 1 | Por cada entrada de `FROZEN_UNROUTED_STATE_WRITES`, contar las coincidencias en el archivo real | el conteo es **exactamente** el congelado. El mensaje de fallo nombra el archivo, el patrón, el esperado, el encontrado **y las líneas nuevas**, y dice explícitamente: *"no subas el número: enrutá el sitio nuevo por services.tracker_write_router"* |
| 2 | Los 3 archivos del censo **existen** | si alguien renombra `harness/task_states.py`, el ratchet no se apaga en silencio (falla por archivo faltante, no por 0 hits) |
| 3 | **Anti-gaming:** `services/tracker_write_router.py` **no** contiene ninguno de los 3 patrones congelados | nadie "cumple" el ratchet moviendo el problema adentro del router |
| 4 | **Cobertura del censo:** el conteo total de `\.update_work_item_state\(|\.update_item_state\(` en `backend/api/` + `backend/harness/` (excluyendo `backend/tests/`) es **exactamente** la suma de los congelados **más** los del router | si aparece un sitio en un archivo que el censo ni siquiera mira, este test lo caza |

**Comando:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.\.venv\Scripts\python.exe -m pytest tests\test_plan270_state_write_ratchet.py -q
```

**Criterio de aceptación (BINARIO):** los **4** tests pasan; el archivo está en los 2 arneses; y el mensaje de fallo del test 1 contiene la cadena literal `tracker_write_router` (para que el modelo menor que lo rompa lea la instrucción de cómo arreglarlo, no sólo el número).

**Colisión con sus propios gates — verificada:** los patrones congelados son **regex sobre `.py` de `backend/`**; este plan (`.md` en `docs/`) y este test (`backend/tests/`, excluido por el test 4) no los pueden disparar. El único texto de código que este documento escribe hacia archivos de producto son los diffs de F2/F3/F4, y ninguno contiene `ado.update_work_item_state(` ni `provider.update_item_state(` — usa `writer.handle.update_work_item_state(` y `writer.handle.update_item_state(`, que **no matchean** los patrones congelados (`_ado_client_for_ticket(...)`, `\bado\.`, `provider\.`). Comprobado leyendo los tres bloques.

**Flag que la protege:** **ninguna.** Es un test; los tests no se gatean. Agregar una flag acá sería una forma de apagarlo.
**Impacto por runtime:** **nulo, y esta vez verificado y no afirmado:** el test lee archivos con `pathlib.Path.read_text()` y cuenta con `re.findall`. No importa `services.agent_runner`, no construye ningún cliente, no lee `LLM_BACKEND` ni `runtime`. Codex CLI / Claude Code CLI / GitHub Copilot Pro: **idéntico, porque ninguno participa en la ejecución del test**. Fallback: N/A.
**Paridad ADO↔GitLab:** el ratchet es **agnóstico de tracker**: congela el uso del cliente ADO **y** el del provider (que hoy es GitLab). Ninguno de los dos puede crecer sin ruido.
**Trabajo del operador: ninguno.** No hay UI, no hay config, no hay flag.

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Probabilidad | Mitigación concreta |
|---|---|---|---|
| R1 | El writeback de F4 agrega latencia perceptible al cierre (una llamada de red extra por cierre, y el lote cierra de a muchas) | Media | El writeback es **una** lectura puntual del ítem ya identificado, no un sync masivo. En el lote, `createBulkRunner` (`frontend/src/services/bulkModel.ts`) ya serializa el trabajo con progreso visible. Si aun así molesta, la flag `STACKY_TICKET_STATE_WRITEBACK_ENABLED` lo apaga sin tocar código |
| R2 | F2 rompe un flujo vivo que **dependía** de que un estado desconocido reabriera la issue | Muy baja | El único emisor conocido manda `"Done"` (`incidentInboxActionsModel.ts:15`), donde reabrir es inequívocamente el bug. Los estados que legítimamente reabren (`in_progress`, `functional`) siguen en el mapa y **conservan** su comportamiento — cubierto por el test 2 de F2 |
| R3 | F3/F4 tocan `api/tickets.py`, archivo de **8332** líneas disputado por otros planes y por **una sesión paralela viva** en este mismo árbol | Alta | La cirugía está acotada a **cuatro puntos** y ninguno más: S1 (`:2073-2094`), S2 (`:1486-1508`), la inserción `4.bis` (a) tras `:2094` y la inserción `4.bis` (b) tras `:1508`. Commitear siempre con pathspec explícito (`git commit -- "<ruta>"`). **Prohibido** `amend`/`reset`/`rebase`/`stash`/`checkout`. **Antes de escribir, re-verificar los números de línea**: la sesión paralela los mueve, y el ancla estable es el texto del comentario (`# ── 4. Cambiar estado en ADO ──`) y el nombre de la función (`set_stacky_status_by_ado`), no el número |
| R4 | `CapabilityUnavailable` se propaga como 500 mudo en vez de `ok: False` | Baja | El `except Exception` de `finish_work` (`:2087`) ya la captura y la convierte en `actions[].ok = False`. Cubierto por los tests 3 y 6 de F3 |
| R5 | El `diverged_count` del backend y el `countDiverged` del frontend divergen entre sí (ironía fatal) | Media | **Corregido en v2 (C6): la mitigación del v1 era falsa** — el test 3 de F4 no asertaba `diverged_count` y el 6 de F5 es puro TS, así que la key no tenía cobertura. Ahora el **caso 12 de `test_plan270_state_writeback.py`** fija el valor del backend con datos sembrados, y el **caso 6 de `incidentDivergence.test.ts`** fija el del frontend con la misma regla de dos condiciones. Además el chip consume `dto?.diverged_count` con el cálculo local como fallback, así que la divergencia entre ambos es **visible**, no silenciosa |
| R6 | Un test nuevo se olvida en el arnés `.ps1` (el meta-test sólo parsea el `.sh` y no lo detecta) | Media | El criterio de aceptación de F0 exige que `Select-String` sobre **los dos** archivos devuelva 2 líneas. Repetirlo para cada archivo nuevo (son **6** en total con F6) |
| R7 | Alguien "arregla" un test borrando un assert para pasar el gate (falso verde) | Media | Los criterios están redactados con **conteos exactos** (11, 10, 6, 10, 12, 4 en backend; 12 en vitest). Un archivo con menos tests de los declarados es un incumplimiento verificable con `pytest --collect-only -q` |
| R10 | **El invariante del Principio 4 se erosiona**: alguien agrega un quinto sitio que escribe estado con el cliente ADO y nadie se entera hasta que un cierre GitLab vuelve a escribir en ADO | **Alta** (ya pasó: son 4 sitios y el v1 sólo veía 1) | **F6 [ADICIÓN ARQUITECTO]**: ratchet de conteo congelado sobre los 3 archivos del censo, con un cuarto test que cubre el resto de `backend/api/` y `backend/harness/` para cazar un sitio en un archivo no censado |
| R11 | El operador enciende `STACKY_GITLAB_ENABLED` esperando que "ahora sí cierra" y se encuentra con otro prerequisito (token, destino por proyecto) | Media | El `workaround` de `CapabilityUnavailable` viaja hasta la UI (ver el diff del `except` de F3) y lo dice el **proveedor**, no este plan: cualquier otro prerequisito que falte va a producir su propio `TrackerConfigError` con su propio mensaje. El smoke 8b del F5 lo verifica de punta a punta contra una issue real |
| R8 | La flakiness de SQLite hace fallar F3/F4 y se interpreta como bug del plan | Alta | El plan lo declara en cada comando: **correr por archivo** y reintentar hasta 3 veces ante `database table is locked` antes de declarar fallo |
| R9 | El `.module.css` nuevo usa un token de color inexistente y el badge queda invisible | Media | El plan nombra los tokens **reales** del tema (`--danger`, `--border`, `--text-primary`, `--bg-panel`) y prohíbe explícitamente la familia `--color-*`, que **no existe** en este repo. El paso 4 del smoke manual verifica que el badge se ve |

---

## 6. Fuera de scope

Explícito, para que nadie lo agregue "de paso":

1. **Reconciliación masiva Stacky→tracker** (empujar el estado de Stacky a todas las filas divergentes de una). Es la **única** capacidad de escritura genuinamente nueva del eje ⇒ **categoría (B)**, default OFF, flag sugerida `STACKY_INCIDENT_RECONCILE_WRITEBACK_ENABLED`. ⇒ **plan 271 sugerido.**
2. **Crear `services/gitlab_sync.py`** para arreglar C4 (el auto-sync post-completación de GitLab). Es un sync masivo con breaker y coalescing: un eje propio, no una fase de este plan. El plan 270 **no lo necesita** porque F4 hace un refresco puntual y agnóstico. ⇒ **plan 272 sugerido.**
3. **Migrar los ~27 call sites de `api/tickets.py` al puerto** (Plan **70**, ya PROPUESTO). El 270 sólo enruta correctamente **el write de estado**.
4. **Rediseño visual de la bandeja.** El 270 agrega un badge y un chip; no reordena, no re-maqueta.
5. **Sincronizar comentarios/adjuntos/asignaciones** ADO↔GitLab. Sólo se trata el **estado**.
6. **Estados deterministas por tipo de agente** (Plan **79**) y la **matriz** `(work_item_type × agent_type)` (Plan **208**). El 270 no decide *qué* estado poner; hace que el estado que el operador eligió llegue bien y se refleje.
7. **Webhooks del tracker hacia Stacky** (que ADO/GitLab avisen al cambiar). Invertiría el modelo de pull y exige exponer un endpoint entrante. ⇒ eje futuro.
8. **Jira y Mantis.** `resolve_state_writer` los rechaza con `CapabilityUnavailable` declarada (test 5 de F1); ampliarlos es otro plan.
9. **Enrutar S3 y S4** (creación de Tasks y `_apply_task_state` del Plan 79). Censados en §2 C3.bis, con carve-out escrito y **congelados por el ratchet de F6**. No se tocan acá porque son ejes ajenos (Plan 70 y Plan 79) y S4 está inerte con los defaults de fábrica.
10. **Promover `STACKY_GITLAB_ENABLED` a ON.** Evaluada por escrito en §1 y **diferida al plan 259**, que es su dueño. Este plan la declara, la nombra en el `workaround` y la verifica en el smoke, pero no la flipea: es el master switch de un adapter entero con superficie de escritura que este plan no analizó.

### Huella de regresión (§ error_fingerprints)

`Stacky Agents/docs/sistema/error_fingerprints.json` es un catálogo de **patrones de log** (`schema_version: 1`; campos `id`, `title`, `class`, `status`, `log_pattern`, `log_guarded`, `killed_by`, `killed_commit`, `date_resolved`, `guard_test`). De las clases de error que toca este plan, **sólo una tiene firma en log** y por eso es la única que se registra — no se inventan `log_pattern` para bugs silenciosos:

| Registrar | Por qué |
|---|---|
| `gitlab_sync_module_missing` — `log_pattern`: `No module named 'services\.gitlab_sync'`, `class`: `import-error`, **`status`: `"open"`**, `killed_by`: `"plan 272 (sugerido, no implementado)"`, `guard_test`: `""` | Es real, se loguea (`completion_sync.py:127` — `logger.warning("completion_sync: sync de %s falló (best-effort): %s", project, exc)`, dentro del `except` que arranca en `:116`) y **este plan NO lo mata** (§6.2). El schema admite `status: "open"` = *"documentada, NO guardada"*. Registrarla evita que el próximo que la vea en un log crea que es nueva |
| **NO registrar** el `reopen` de C2 ni el mis-routing de C3 | **Son silenciosos: no dejan ninguna línea de log.** El `reopen` es un `PUT` exitoso (200) y el mis-routing termina en un `logger.exception` genérico sin firma estable. Inventarles un `log_pattern` sería meter ruido en un catálogo cuyo contrato es "el smoke alarma si el patrón REAPARECE". **Sus guardias son tests, no huellas de log:** el test 5 de F2 (anti-reopen) y el test 6 de F1 + F6 (anti-fallback). Queda dicho acá para que nadie lo interprete como un olvido |

---

## 7. Glosario, orden de implementación y DoD

### Glosario

| Término | Definición operativa en este plan |
|---|---|
| **Divergencia** | Incidencia con `stacky_status == "completed"` y `is_open_state(ado_state) == True`. El KPI del plan |
| **Writeback** | Releer el ítem del tracker y persistir su estado en `Ticket.ado_state`. Lee del tracker, **escribe sólo en la base local de Stacky** |
| **Enrutado de escritura** | Decidir a qué proveedor le corresponde escribir el estado de un ticket, según su `tracker_type` |
| **Estado nativo** | El string que el tracker concreto entiende: para ADO el `System.State` (`"Done"`); para GitLab una clave lógica del mapa (`"accepted"`) |
| **Estado lógico (GitLab)** | Una de las 4 claves de `_state_map_for_gitlab()` (`gitlab_provider.py:94-102`): `functional`, `accepted`, `rejected`, `in_progress` |
| **`CapabilityUnavailable`** | Excepción del Plan 218 (`tracker_provider.py:55`) que declara que una capacidad no existe en el proveedor activo. **No es un bug**: es una degradación informada |
| **Passthrough** | Para ADO, el estado pedido se pasa **sin transformar** — garantiza retrocompatibilidad byte-idéntica |
| **Pata (de una flag)** | Cada uno de los 6 lugares que hay que tocar para dar de alta una flag sin poner un meta-test en rojo |
| **Fail-open** | Ante un error de red, degradar devolviendo un resultado negativo declarado en vez de levantar y tumbar la operación |

### Orden de implementación (lista numerada, estricto)

1. **F0** — `services/close_intent.py` + `tests/test_plan270_close_intent.py` (**11** casos, incluido el centinela de aridad del test 11 que evita el bug C1). Registrar el test en los **dos** arneses. Correr y ver verde.
2. **F1** — Alta de la flag `STACKY_TRACKER_STATE_WRITE_ROUTING_ENABLED` en las **7 patas** (ojo con el límite de 240 chars de `PlainHelp`, pata 6). Luego `services/tracker_write_router.py` (sin `write_state_for_ticket` todavía) + `tests/test_plan270_write_router.py` (**10** casos). El cliente ADO se construye con `project_context.build_ado_client`, **nunca** importando `api.tickets` (C5). Registrar en los dos arneses. Verde.
3. **F2** — Editar `services/gitlab_provider.py` (`update_item_state` + `_unknown_state_guard_enabled` **con `config.config`**, C9) + `tests/test_plan270_gitlab_close.py` (**6** casos). Registrar. Verde. **Correr el centinela textual** que prueba que la forma vieja desapareció.
4. **F3** — Agregar `write_state_for_ticket` al router **con el desempaquetado literal de `resolve_closed_states`** (C1); editar los **dos** bloques de `api/tickets.py` (S1 `:2073-2094` y S2 `:1486-1508`) y el `except` de S1 para concatenar el `workaround`; + `tests/test_plan270_finish_work_state.py` (**10** casos). Registrar. Correr **por archivo**. Verde.
5. **F4** — Alta de la flag `STACKY_TICKET_STATE_WRITEBACK_ENABLED` (7 patas). `services/ticket_state_writeback.py` (key literal `"state"`, `session_scope` desde `db.py:485`) + las **dos** inserciones `4.bis` en `api/tickets.py` + `tests/test_plan270_state_writeback.py` (**12** casos, contando el 12 que fija `diverged_count`). Registrar. Correr **por archivo**. Verde (los tests 3 y 10 son el KPI en los dos caminos).
6. **F5** — Alta de la flag `STACKY_INCIDENT_DIVERGENCE_BADGE_ENABLED` (7 patas). `frontend/src/incidents/incidentDivergence.ts` + su `.test.ts` (**12** casos); ampliar `incidentInboxModel.ts` con `divergence_badge_enabled` y `diverged_count`; luego las keys del backend (`diverged_count` **por agregación**, `divergence_badge_enabled`); luego `IncidentInboxPage.tsx` (memo `mostrados`, `visibleIds` sobre `mostrados`, chip con `Button`) + `.module.css`. Vitest verde, `tsc --noEmit` limpio, ratchet de UI verde, **smoke manual de 9 pasos hecho** (incluido el 8b de GitLab).
7. **F6 [ADICIÓN ARQUITECTO]** — **Re-contar** los 3 patrones con el comando declarado en la fase, escribir `tests/test_plan270_state_write_ratchet.py` con esos números y **verlo fallar** subiendo a mano un conteo antes de dejarlo verde (si nunca lo viste rojo, no sabés si mide algo). Registrar en los dos arneses.
8. **Cierre** — Regenerar `harness_defaults.env` con `deployment/export_harness_defaults.py` (**los dos destinos**, `--out` por corrida). Correr los **6** archivos de test del plan, **uno por uno**. Verificar que los 6 estén en `run_harness_tests.sh` **y** en `$HarnessTestFiles` de `run_harness_tests.ps1`. Agregar la entrada `gitlab_sync_module_missing` a `docs/sistema/error_fingerprints.json` con `status: "open"`.

### Definition of Done global

El plan 270 está terminado cuando **todo** lo siguiente es cierto y verificable:

- [ ] Los **6** archivos de test nuevos existen, están registrados en **ambos** arneses, y pasan corridos **por archivo** con `.\.venv\Scripts\python.exe -m pytest tests\<archivo>.py -q`:
      `test_plan270_close_intent.py` (11) · `test_plan270_write_router.py` (10) · `test_plan270_gitlab_close.py` (6) · `test_plan270_finish_work_state.py` (10) · `test_plan270_state_writeback.py` (12) · `test_plan270_state_write_ratchet.py` (4). **Total: 53 tests.**
- [ ] `incidentDivergence.test.ts` pasa (**12** casos) y `npx tsc --noEmit` sale limpio.
- [ ] Las **3** flags nuevas están dadas de alta en sus **7 patas** cada una, las 3 con `default=True`, ninguna entrada de `PlainHelp` supera **240** caracteres, y `harness_defaults.env` fue **regenerado con el generador** en sus **dos** destinos (no editado a mano).
- [ ] **Centinela anti-reopen:** `Select-String -Path services\gitlab_provider.py -Pattern 'state_map\.get\(logical_state, \{\}\)'` devuelve **0 líneas**.
- [ ] **Centinela anti-fallback (unit):** el test 6 de `test_plan270_write_router.py` demuestra que ningún `tracker_type` no-ADO resuelve a `kind == "ado_client"`.
- [ ] **Centinela anti-fallback (repo-wide) — F6 [ADICIÓN ARQUITECTO]:** `test_plan270_state_write_ratchet.py` congela el censo de §2 C3.bis y su test 4 cubre `backend/api/` + `backend/harness/` completos. **Se vio fallar al menos una vez** antes de dejarlo verde.
- [ ] **Centinela anti-acoplamiento (C5):** `Select-String -Path services\tracker_write_router.py,services\ticket_state_writeback.py -Pattern 'api\.tickets|from api'` devuelve **0 líneas**.
- [ ] **KPI verificado en los DOS caminos (C3):** el test 3 de `test_plan270_state_writeback.py` (manual, `finish-work`) **y** el test 10 (automático, `PATCH /api/tickets/by-ado/<ado_id>/stacky-status`) prueban que el ítem **desaparece** de `/api/incident-inbox/items?scope=open`.
- [ ] **Bug de integración C1 fijado:** el test 11 de `test_plan270_close_intent.py` y el test 7 de `test_plan270_finish_work_state.py` prueban que `resolve_closed_states` se desempaqueta y que un cierre GitLab con `"Done"` llega como `"accepted"`.
- [ ] **Paridad ADO byte-idéntica en los dos sitios:** el test 1 (S1) y el test 10 (S2) de `test_plan270_finish_work_state.py` prueban que un ticket ADO recibe **exactamente** el mismo argumento de estado que antes del plan.
- [ ] **Paridad GitLab efectiva en los dos sitios:** los tests 2 (S1) y 8 (S2) prueban que un ticket GitLab se cierra vía su provider y que el cliente ADO **no se instancia**.
- [ ] **Prerequisito GitLab declarado y accionable (C4):** el test 8 de `test_plan270_write_router.py` prueba que el `workaround` contiene `"STACKY_GITLAB_ENABLED"`, y el smoke 8a/8b de F5 lo verifica contra una issue real (apagada ⇒ error que nombra la flag y **nada** escrito; encendida ⇒ issue **cerrada**, no reabierta).
- [ ] **Rollback probado en los dos sitios:** los tests 4 (S1) y 9 (S2) de `test_plan270_finish_work_state.py` y el 4 de `test_plan270_gitlab_close.py` prueban que con las flags OFF el comportamiento vuelve al histórico.
- [ ] **`diverged_count` tiene consumidor Y test (C6):** el caso 12 de `test_plan270_state_writeback.py` fija el valor del backend por agregación, y el chip lo consume con `dto?.diverged_count ?? countDiverged(visible)`.
- [ ] El ratchet de deuda de UI sigue verde: **cero** `style={{}}` inline y **cero** HEX en los archivos de frontend tocados.
- [ ] El smoke manual de F5 (**9** pasos) fue ejecutado, incluidos el 5 (con el chip activo, "Seleccionar todo" cuenta **sólo lo visible** — C7), el 6 (la fila cambia **sin recargar**), el 7 (**cero** peticiones nuevas por fila), el 8b (GitLab cierra de verdad) y el 9 (el camino automático refleja el estado real).
- [ ] La entrada `gitlab_sync_module_missing` está en `docs/sistema/error_fingerprints.json` con `status: "open"`.
- [ ] Ningún archivo fuera de la lista declarada fue modificado. Verificable con `git status --short`; y `git diff --stat -- "Stacky Agents/backend/api/tickets.py"` muestra **sólo** los cuatro puntos de R3.
