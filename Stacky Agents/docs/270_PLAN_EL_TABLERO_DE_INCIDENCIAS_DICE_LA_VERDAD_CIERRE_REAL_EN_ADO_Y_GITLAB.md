# Plan 270 — El tablero de incidencias dice la verdad: cierre real en ADO y GitLab

**Estado:** PROPUESTO v1
**Fecha:** 2026-07-28
**Rama de trabajo sugerida:** `feat/plan-270-tablero-incidencias-verdad`
**Numeración:** verificada en frío listando `Stacky Agents/docs/` — máximo `269`, sin duplicados ⇒ este plan es el **270**.

---

## 1. Objetivo, KPI e impacto

El operador **abandonó el tablero de incidencias** y gestiona todo desde los tickets de Azure DevOps. Ese abandono no es una preferencia estética: es la consecuencia racional de que **el tablero miente después de actuar**. Hoy, cuando el operador aprieta "Cerrar" en la bandeja, recibe un toast verde y la fila **sigue diciendo "Abierta"**, porque el cierre escribe en el tracker pero nunca refresca la columna local desde la que el tablero deriva "Abierta/Cerrada". Y si el proyecto es GitLab, el cierre además hace lo contrario de lo pedido: **reabre la issue**.

Este plan cierra esa brecha con la corrección **mínima y verificable** de la cadena de cierre, para que la bandeja de incidencias vuelva a ser un punto de gestión confiable en **Azure DevOps y GitLab por igual**.

**KPI primario — `divergencia = 0`:**
> Cantidad de incidencias del proyecto con `stacky_status == "completed"` y `is_open_state(ado_state) == True`.

Es decir: incidencias que **Stacky da por cerradas** pero que el tablero **sigue pintando abiertas**. Ese número es exactamente el síntoma que expulsó al operador. Se calcula **localmente, sin una sola llamada extra al tracker** (ambos campos ya viajan en el ítem: `models.py:95` `ado_state`, `models.py:101` `stacky_status`), así que es gratis medirlo y gratis mostrarlo.

- **Antes del plan:** la divergencia crece con cada cierre hecho desde la bandeja y nunca se corrige sola.
- **Después del plan:** un cierre exitoso deja la fila en su estado real de inmediato (F4), un cierre imposible lo dice en vez de fingir (F3), y lo que quedó desalineado de antes se ve marcado en pantalla (F5).

**Impacto secundario:** un cierre desde la bandeja sobre un proyecto GitLab hoy es, en el mejor caso, un error mudo; en el peor, una escritura contra el sistema equivocado. Este plan lo elimina.

---

## 2. Por qué ahora: el gap, con evidencia

Las cuatro causas están **verificadas leyendo el código en el commit actual** (`d234021e`). No son hipótesis.

### C1 — El cierre nunca refresca el estado local ⇒ la fila miente (causa raíz del abandono)

La cadena es cerrada y determinista:

1. `backend/api/tickets.py:1750` `finish_work` escribe el estado en el tracker (paso 4, `:2074-2094`) y marca `stacky_status="completed"` (paso 5, `:2112`).
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
4. **Nunca escribir en el sistema equivocado.** Un ticket cuyo `tracker_type` no es `azure_devops` **no puede** resolverse al cliente ADO. Si el proveedor real no está disponible, la acción devuelve un error honesto.
5. **Human-in-the-loop innegociable.** Todo cierre sigue exigiendo confirmación del operador (`FinishWorkButton` con dry-run, y `BulkActionsBar` con `armedLabel`). Este plan no agrega autonomía; agrega veracidad.
6. **Cero trabajo extra para el operador.** Ninguna fase pide configurar nada nuevo. Los defaults funcionan sin tocar un solo archivo de perfil.
7. **Backward-compatible y aditivo.** Para `tracker_type == "azure_devops"` con los defaults de fábrica, el cuerpo enviado al tracker es **byte-idéntico** al de hoy. Sólo se **agrega** el refresco posterior.
8. **Mono-operador:** sin RBAC, sin roles, sin 403.
9. **Sin costo en reposo:** ninguna fase agrega loops, daemons, polling, prefetch ni llamadas a modelos. El KPI se calcula sobre datos ya presentes en el DTO.

### Contrato de flags — las **6 patas** (contadas abriendo el código)

Toda flag nueva de este plan debe tocar **las seis**, o un meta-test se pone rojo:

| # | Archivo | Qué se agrega |
|---|---|---|
| 1 | `backend/config.py` | `STACKY_X: bool = os.getenv("STACKY_X", "true").lower() in ("1", "true", "yes")` — **el default EFECTIVO** |
| 2 | `backend/services/harness_flags.py` | Alta de la key en `_CATEGORY_KEYS` (el dict arranca en `:120`) |
| 3 | `backend/services/harness_flags.py` | El `FlagSpec(key=..., type="bool", default=True, label=..., description=..., group="global")` |
| 4 | `backend/tests/test_harness_flags.py` | La key en `_CURATED_DEFAULTS_ON` (el set arranca en `:467`). **Ojo: esta pata vive en `tests/`, no en `services/`.** `test_default_known_only_for_curated` compara por **igualdad exacta** (`:979`) |
| 5 | `backend/services/harness_flags_help.py` | Una entrada `PlainHelp(...)` (patrón vivo: `:1479` para `STACKY_INCIDENT_INBOX_ACTIONS_ENABLED`) |
| 6 | `deployment/export_harness_defaults.py` | Regenerar `harness_defaults.env` con el generador (no editarlo a mano) |

### Contrato de tests

- **Todo `test_*.py` nuevo va en los DOS arneses**, que tienen sintaxis distinta:
  - `backend/scripts/run_harness_tests.sh` — lista plana (los del 238 están en `:669-673`). **El meta-test parsea sólo este.**
  - `backend/scripts/run_harness_tests.ps1` — array `$HarnessTestFiles` (`:13`, iterado en `:801`).
- **Los tests que tocan la DB se corren POR ARCHIVO.** SQLite bajo pytest es flaky por `SQLITE_LOCKED`; la corrida completa contamina. En este plan, los archivos que tocan DB son `test_plan270_finish_work_state.py` y `test_plan270_state_writeback.py`.
- **Frontend: no hay RTL ni jsdom.** Toda lógica testeable va en un `.ts` **puro** con vitest; el cableado se valida con un smoke manual descrito paso a paso. **Prohibido proponer tests de componentes React.**
- **`.tsx`/`.module.css` nuevos: tolerancia CERO a `style={{}}` inline** (ratchet de deuda de UI). Colores y estilos por CSS Modules o variable CSS vía `ref.current?.style.setProperty(...)` (patrón vivo: `IncidentInboxPage.tsx:96-109`).

### Gotcha de `config` — mirar cómo importa **cada** archivo

No hay regla global. En los archivos de este plan:
- `backend/api/incident_inbox.py:16` hace `from config import config as _cfg` ⇒ `getattr(_cfg, "X", default)`. **Correcto.**
- `backend/services/completion_sync.py:29` hace `from config import config as _cfg` ⇒ `getattr(_cfg, "X", False)`. **Correcto.**
- `backend/services/tracker_provider.py:122` hace `import config` ⇒ debe leer **`config.config.X`** (así lo hace en `:133` y `:141`). **Correcto.**
- `backend/services/run_ticket_refresh.py:28` hace `from config import config` ⇒ `getattr(config, "X", False)` (`:30`). **Correcto** (ahí `config` ya es la instancia).

**Los módulos NUEVOS de este plan usan `from config import config as _cfg` + `getattr(_cfg, KEY, default)`.** Errar da `AttributeError`/500.

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
# Clave lógica de GitLab cuyo mapping tiene closed=True (gitlab_provider.py:99).
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
            source="already_logical", native = esa clave.
         b. si is_close_state(requested_state, closed_states) ->
            source="mapped", native = GITLAB_CLOSE_STATE, closes=True.
         c. si no -> ValueError("unmappable_state:<requested>"). NUNCA se
            devuelve un target que termine reabriendo.
      3. cualquier otro tracker_type -> ValueError("unsupported_tracker:<t>").
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
| 5 | `resolve_close_target("gitlab", "in_progress", DEFAULT_CLOSED_STATES)` | `native_state == "in_progress"`, `source == "already_logical"` |
| 6 | `resolve_close_target("gitlab", "Cualquier Cosa", DEFAULT_CLOSED_STATES)` | levanta `ValueError` con mensaje que empieza en `"unmappable_state:"` |
| 7 | `resolve_close_target("jira", "Done", ...)` | levanta `ValueError` que empieza en `"unsupported_tracker:"` |
| 8 | **Centinela anti-reopen:** para cada `s in ADO_CLOSE_STATES`, `resolve_close_target("gitlab", s, DEFAULT_CLOSED_STATES).closes is True` | los 3 cierran; ninguno levanta |
| 9 | **Centinela de espejo:** `set(GITLAB_LOGICAL_STATES)` == claves de `GitLabTrackerProvider._state_map_for_gitlab()` | si alguien agrega una clave en `gitlab_provider.py` y no acá, rojo |

> El test 9 importa `GitLabTrackerProvider` sólo para leer el método; se instancia con `object.__new__(GitLabTrackerProvider)` para no requerir red ni credenciales, ya que `_state_map_for_gitlab` (`gitlab_provider.py:94-102`) devuelve un literal y no usa `self`.

**Comando:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.\.venv\Scripts\python.exe -m pytest tests\test_plan270_close_intent.py -q
```

**Criterio de aceptación (BINARIO):** los **9** tests de `test_plan270_close_intent.py` pasan y el archivo está registrado en `run_harness_tests.sh` **y** en `$HarnessTestFiles` de `run_harness_tests.ps1`.
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
      construido con el MISMO helper que usa hoy api/tickets.py, para que la
      rama ADO quede byte-idéntica.
    - tracker_type == "gitlab" -> get_tracker_provider(stacky_project_name)
      (services/tracker_provider.py:125). Si esa fábrica levanta
      TrackerConfigError (p.ej. STACKY_GITLAB_ENABLED=false,
      config.py:1185-1186), se RE-LEVANTA como CapabilityUnavailable —
      NO se cae a ADO.
    - cualquier otro tracker_type -> CapabilityUnavailable.

    CapabilityUnavailable viene de services/tracker_provider.py:55 (Plan 218);
    su .to_payload() (:69) ya produce {"available": false, ...}.
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
| 8 | `.to_payload()` de la excepción del caso 4 | contiene `available is False` y una `reason` no vacía |

> El valor `"tracker.items.update_state"` **no se inventa**: es la clave declarada en `backend/services/provider_capabilities.py:60`.

**Comando:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.\.venv\Scripts\python.exe -m pytest tests\test_plan270_write_router.py -q
```

**Criterio de aceptación (BINARIO):** los **8** tests pasan; el archivo está en los 2 arneses.

**Flag que la protege:** `STACKY_TRACKER_STATE_WRITE_ROUTING_ENABLED` — **default `True` (ON)**.
**Justificación del default ON (obligatoria):** esta flag **no habilita ninguna escritura nueva**; sólo **impide** que una escritura ya existente vaya al sistema equivocado. El efecto neto es **estrictamente menos escrituras erróneas**. Ninguna de las 2 categorías de excepción aplica: (A) no consume tokens en reposo — no hay loop, daemon, barrido, polling ni llamada a modelo; (B) no escribe en un sistema real del operador — al contrario, **evita** una escritura mal dirigida, y no le quita ninguna decisión (el cierre lo sigue confirmando él). Dejarla OFF significaría "por default, seguí intentando cerrar issues de GitLab con el cliente de Azure DevOps", que es exactamente el bug.
**Las 6 patas:** `config.py` · `_CATEGORY_KEYS` (`harness_flags.py:120`) · `FlagSpec(group="global")` · `_CURATED_DEFAULTS_ON` (`tests/test_harness_flags.py:467`) · `PlainHelp` en `harness_flags_help.py` · regenerar con `deployment/export_harness_defaults.py`.
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
    """
    from config import config as _cfg
    return bool(getattr(_cfg, "STACKY_TRACKER_STATE_WRITE_ROUTING_ENABLED", True))
```

> **Nota de importación:** `gitlab_provider.py` debe usar `from config import config as _cfg` + `getattr(...)`. **No** usar `config.config` acá salvo que el archivo ya haga `import config` — verificar el encabezado del archivo antes de escribir la línea (regla de la sección 3).

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

**Archivo a EDITAR:** `Stacky Agents/backend/api/tickets.py` — **sólo** el bloque `── 4. Cambiar estado en ADO ──` (`:2073-2094`). **Ninguna otra parte del archivo se toca** (es un archivo de 7364 líneas disputado por otros planes y por una sesión paralela viva).

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
             actions.append({
                 "action": "update_ado_state",
                 "ok": False,
                 "to": target_ado_state,
                 "reason": f"{type(exc).__name__}: {exc}",
             })
```

**Símbolo NUEVO en `services/tracker_write_router.py` (agregado en F3, no en F1):**

```python
def write_state_for_ticket(*, ticket, ado_id, requested_state: str) -> dict:
    """Resuelve destino (F1) + vocabulario (F0) y ejecuta la escritura.

    Devuelve {"tracker_type": str, "native_state": str, "closes": bool}.
    Levanta CapabilityUnavailable (destino imposible) o ValueError
    (estado no mapeable) — el caller las traduce a actions[].ok = False.

    Los closed_states se resuelven con la MISMA precedencia que usa el tablero:
    services.incident_inbox.resolve_closed_states(profile), para que "lo que el
    tablero considera cerrado" y "lo que se escribe al cerrar" no diverjan.
    """
```

- Para `kind == "ado_client"` invoca `handle.update_work_item_state(int(ado_id), target.native_state)`.
- Para `kind == "provider"` invoca `handle.update_item_state(str(ado_id), target.native_state)`.
- El `profile` se obtiene con `services.client_profile.load_client_profile(ticket.stacky_project_name)` dentro de un `try/except` que cae a `None` (mismo patrón defensivo que `api/incident_inbox.py:36-54` `_profile_for`).

**Contrato de respuesta — ADITIVO:** se **agregan** las keys `requested` y `tracker_type` al action `update_ado_state`. **No se quita ni se renombra ninguna key existente** (`action`, `ok`, `to`, `reason` siguen). Un frontend viejo que sólo lea `ok`/`reason` sigue funcionando. El frontend actual lee `r.actions?.find((a) => !a.ok)` y `fallo?.reason` (`IncidentInboxPage.tsx:215-217`): intacto.

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

**Comando (POR ARCHIVO — obligatorio, la DB es flaky bajo pytest):**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.\.venv\Scripts\python.exe -m pytest tests\test_plan270_finish_work_state.py -q
```
Si aparece `database table is locked`, **reintentar el mismo archivo** hasta 3 veces antes de considerarlo un fallo real (flakiness conocida de SQLite bajo pytest, no un bug del plan).

**Criterio de aceptación (BINARIO):** los **6** tests pasan; el archivo está en los 2 arneses; y el bloque histórico sigue presente bajo la rama `else` (verificable porque el test 4 pasa).

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
- `kind == "provider"` ⇒ `handle.get_item(str(ado_id))` (método del puerto, declarado en `tracker_provider.py:82`) y se toma el campo de estado del dict normalizado; se persiste **sólo** `Ticket.ado_state` con `session_scope()`.

**Regla de escritura mínima:** este módulo **sólo** escribe `Ticket.ado_state` (y `last_synced_at` si ya existe la columna). **No** toca `stacky_status`, ni `title`, ni `work_item_type`: no es un sync, es un refresco quirúrgico de la columna de la que depende el tablero.

**Cableado — archivo a EDITAR:** `Stacky Agents/backend/api/tickets.py`, **una sola inserción** inmediatamente después del bloque del paso 4 (tras el `except` que cierra en `:2094`) y **antes** del paso 5:

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

**Comando (POR ARCHIVO):**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.\.venv\Scripts\python.exe -m pytest tests\test_plan270_state_writeback.py -q
```

**Criterio de aceptación (BINARIO):** los **7** tests pasan (en particular el **3**, que es el KPI); el archivo está en los 2 arneses.

**Flag que la protege:** `STACKY_TICKET_STATE_WRITEBACK_ENABLED` — **default `True` (ON)**.
**Justificación del default ON (obligatoria):** la operación es **leer del tracker y escribir en la base local de Stacky**. No escribe en ningún sistema del operador, no destruye datos y no le saca ninguna decisión ⇒ **no aplica la categoría (B)**. No hay loop, daemon, barrido, polling, prefetch ni llamada a modelo: se ejecuta **una vez, sincrónicamente, dentro de una acción que el operador acaba de disparar** ⇒ **no aplica la categoría (A)**. Es lectura + reflejo local, y la directiva es explícita: **todo lo de solo lectura va ON, sin excepción**. Dejarla OFF sería dejar el bug principal apagado por default.
**Las 6 patas:** ídem F1.
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
import type { IncidentInboxItem } from "./incidentInboxModel";

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
```

**Archivos a EDITAR:**
1. `Stacky Agents/frontend/src/pages/IncidentInboxPage.tsx` — insertar, dentro del `.map` de filas (bloque `:487-540`), inmediatamente **después** del badge Abierta/Cerrada (`:504-506`):
   ```tsx
   {divergenciaVisible && isDiverged(item) && (
     <span className={styles.divergedBadge} title={DIVERGENCE_BADGE_TITLE}>
       {DIVERGENCE_BADGE_LABEL}
     </span>
   )}
   ```
   y en la barra de chips (bloque `:455-476`) un chip clickeable con `divergenceSummary(visible)` que togglea el estado `soloDivergentes`, aplicado sobre `visible` con `filterDiverged`.
2. `Stacky Agents/frontend/src/pages/IncidentInboxPage.module.css` — clase `.divergedBadge`. **Sin colores literales ni HEX**: usar los tokens que el tema **sí** define (`--danger`, `--border`, `--text-primary`, `--bg-panel`). **No** inventar tokens de la familia `--color-*`: esa familia **no existe** en el tema del repo.
3. `Stacky Agents/backend/api/incident_inbox.py` — agregar al payload de `/items` (junto a `untyped_count`, `:174`) una key **aditiva**:
   ```python
   "diverged_count": sum(
       1 for i in items
       if i.get("stacky_status") == "completed" and i.get("is_open") is True
   ),
   ```
   Es la misma regla que el `.ts`, calculada sobre la lista ya construida (**sin query extra**). Sirve para que el conteo sea correcto aun cuando la lista venga truncada por `MAX_ITEMS` (`services/incident_inbox.py:20`).

**Gate del badge:** `divergenciaVisible` se resuelve de la respuesta de `/api/incident-inbox/status`, agregando una key aditiva `divergence_badge_enabled` en `api/incident_inbox.py:65-81` (junto a `actions_enabled`, `:76`). **Estricto a `true`**, igual que `resolveInboxActionsEnabled` (`incidentInboxActionsModel.ts:31-35`): un backend viejo que no manda la key deja el badge oculto y la página sigue funcionando.

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
5. Click en el chip ⇒ la lista se reduce a esa fila. Segundo click ⇒ vuelve a la lista completa.
6. Apretar **Cerrar** sobre una incidencia abierta real y confirmar. Verificar que, **sin recargar la página**, la fila pasa a "Cerrada" (o desaparece si el scope es "Solo abiertas"). **Ese es el smoke que valida F4 de punta a punta.**
7. Verificar en las herramientas de desarrollo que **no aparece ninguna petición nueva** por fila (el badge no dispara red).

**Criterio de aceptación (BINARIO):** los **9** tests de vitest pasan, `npx tsc --noEmit` sale limpio, y el ratchet de deuda de UI sigue verde (cero `style={{}}` inline en los archivos tocados y **cero HEX** en el `.module.css` nuevo).
**Verificación del ratchet:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx vitest run src/__tests__/uiDebtRatchet.test.ts
```

**Flag que la protege:** `STACKY_INCIDENT_DIVERGENCE_BADGE_ENABLED` — **default `True` (ON)**.
**Justificación del default ON (obligatoria):** es **solo lectura pura sobre datos ya presentes en la respuesta**. No hace ninguna llamada de red nueva, no consulta ningún modelo, no escribe en ningún lado. No aplica (A) — no hay loop/daemon/polling/prefetch ni gasto de tokens en reposo, el cálculo es una comparación de dos strings por fila. No aplica (B) — no escribe nada, no destruye nada, no decide nada por el operador: **le muestra** el problema para que decida él. La directiva es explícita: **todo lo de solo lectura va ON**.
**Las 6 patas:** ídem F1.
**Impacto por runtime:** **nulo.** Es una función pura de frontend. Codex CLI / Claude Code CLI / GitHub Copilot Pro: idéntico. Fallback: N/A.
**Trabajo del operador: ninguno.** El badge aparece solo; el chip es opcional y no modifica nada.

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Probabilidad | Mitigación concreta |
|---|---|---|---|
| R1 | El writeback de F4 agrega latencia perceptible al cierre (una llamada de red extra por cierre, y el lote cierra de a muchas) | Media | El writeback es **una** lectura puntual del ítem ya identificado, no un sync masivo. En el lote, `createBulkRunner` (`frontend/src/services/bulkModel.ts`) ya serializa el trabajo con progreso visible. Si aun así molesta, la flag `STACKY_TICKET_STATE_WRITEBACK_ENABLED` lo apaga sin tocar código |
| R2 | F2 rompe un flujo vivo que **dependía** de que un estado desconocido reabriera la issue | Muy baja | El único emisor conocido manda `"Done"` (`incidentInboxActionsModel.ts:15`), donde reabrir es inequívocamente el bug. Los estados que legítimamente reabren (`in_progress`, `functional`) siguen en el mapa y **conservan** su comportamiento — cubierto por el test 2 de F2 |
| R3 | F3 toca `api/tickets.py`, archivo de 7364 líneas disputado por otros planes y por **una sesión paralela viva** en este mismo árbol | Alta | La cirugía está acotada a **un bloque de 22 líneas** (`:2073-2094`) más **una inserción** después. Commitear siempre con pathspec explícito (`git commit -- "<ruta>"`). **Prohibido** `amend`/`reset`/`rebase`/`stash`/`checkout` |
| R4 | `CapabilityUnavailable` se propaga como 500 mudo en vez de `ok: False` | Baja | El `except Exception` de `finish_work` (`:2087`) ya la captura y la convierte en `actions[].ok = False`. Cubierto por los tests 3 y 6 de F3 |
| R5 | El `diverged_count` del backend y el `countDiverged` del frontend divergen entre sí (ironía fatal) | Media | Ambos implementan la **misma** regla de dos condiciones. El test 3 de F4 y el test 6 de F5 la fijan de los dos lados. Si alguien cambia una, el otro test queda rojo |
| R6 | Un test nuevo se olvida en el arnés `.ps1` (el meta-test sólo parsea el `.sh` y no lo detecta) | Media | El criterio de aceptación de F0 exige que `Select-String` sobre **los dos** archivos devuelva 2 líneas. Repetirlo para cada archivo nuevo (son 5 en total) |
| R7 | Alguien "arregla" un test borrando un assert para pasar el gate (falso verde) | Media | Los criterios están redactados con **conteos exactos** (9, 8, 6, 6, 7, 9 tests). Un archivo con menos tests de los declarados es un incumplimiento verificable con `pytest --collect-only -q` |
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

1. **F0** — `services/close_intent.py` + `tests/test_plan270_close_intent.py`. Registrar el test en los **dos** arneses. Correr y ver verde.
2. **F1** — Alta de la flag `STACKY_TRACKER_STATE_WRITE_ROUTING_ENABLED` en las **6 patas**. Luego `services/tracker_write_router.py` (sin `write_state_for_ticket` todavía) + `tests/test_plan270_write_router.py`. Registrar en los dos arneses. Verde.
3. **F2** — Editar `services/gitlab_provider.py` (`update_item_state` + `_unknown_state_guard_enabled`) + `tests/test_plan270_gitlab_close.py`. Registrar. Verde. **Correr el centinela textual** que prueba que la forma vieja desapareció.
4. **F3** — Agregar `write_state_for_ticket` al router; editar **sólo** el bloque `:2073-2094` de `api/tickets.py` + `tests/test_plan270_finish_work_state.py`. Registrar. Correr **por archivo**. Verde.
5. **F4** — Alta de la flag `STACKY_TICKET_STATE_WRITEBACK_ENABLED` (6 patas). `services/ticket_state_writeback.py` + la inserción `4.bis` en `api/tickets.py` + `tests/test_plan270_state_writeback.py`. Registrar. Correr **por archivo**. Verde (el test 3 es el KPI).
6. **F5** — Alta de la flag `STACKY_INCIDENT_DIVERGENCE_BADGE_ENABLED` (6 patas). `frontend/src/incidents/incidentDivergence.ts` + su `.test.ts`; luego las keys aditivas del backend (`diverged_count`, `divergence_badge_enabled`); luego `IncidentInboxPage.tsx` + `.module.css`. Vitest verde, `tsc --noEmit` limpio, ratchet de UI verde, **smoke manual de 7 pasos hecho**.
7. **Cierre** — Regenerar `harness_defaults.env` con `deployment/export_harness_defaults.py`. Correr los 5 archivos de test del plan, **uno por uno**. Verificar que los 5 estén en `run_harness_tests.sh` **y** en `$HarnessTestFiles` de `run_harness_tests.ps1`.

### Definition of Done global

El plan 270 está terminado cuando **todo** lo siguiente es cierto y verificable:

- [ ] Los **5** archivos de test nuevos existen, están registrados en **ambos** arneses, y pasan corridos **por archivo** con `.\.venv\Scripts\python.exe -m pytest tests\<archivo>.py -q`:
      `test_plan270_close_intent.py` (9) · `test_plan270_write_router.py` (8) · `test_plan270_gitlab_close.py` (6) · `test_plan270_finish_work_state.py` (6) · `test_plan270_state_writeback.py` (7). **Total: 36 tests.**
- [ ] `incidentDivergence.test.ts` pasa (**9** casos) y `npx tsc --noEmit` sale limpio.
- [ ] Las **3** flags nuevas están dadas de alta en sus **6 patas** cada una, las 3 con `default=True`, y `harness_defaults.env` fue **regenerado con el generador** (no editado a mano).
- [ ] **Centinela anti-reopen:** `Select-String -Path services\gitlab_provider.py -Pattern 'state_map\.get\(logical_state, \{\}\)'` devuelve **0 líneas**.
- [ ] **Centinela anti-fallback:** el test 6 de `test_plan270_write_router.py` demuestra que ningún `tracker_type` no-ADO resuelve a `kind == "ado_client"`.
- [ ] **KPI verificado:** el test 3 de `test_plan270_state_writeback.py` prueba que, tras un `finish-work` exitoso, el ítem **desaparece** de `/api/incident-inbox/items?scope=open`.
- [ ] **Paridad ADO byte-idéntica:** el test 1 de `test_plan270_finish_work_state.py` prueba que un ticket ADO recibe **exactamente** el mismo argumento de estado que antes del plan.
- [ ] **Paridad GitLab efectiva:** el test 2 de `test_plan270_finish_work_state.py` prueba que un ticket GitLab se cierra vía su provider y que el cliente ADO **no se instancia**.
- [ ] **Rollback probado:** el test 4 de `test_plan270_finish_work_state.py` y el 4 de `test_plan270_gitlab_close.py` prueban que con las flags OFF el comportamiento vuelve al histórico.
- [ ] El ratchet de deuda de UI sigue verde: **cero** `style={{}}` inline y **cero** HEX en los archivos de frontend tocados.
- [ ] El smoke manual de F5 (7 pasos) fue ejecutado, incluido el paso 6 (la fila cambia **sin recargar**) y el paso 7 (**cero** peticiones nuevas por fila).
- [ ] Ningún archivo fuera de la lista declarada fue modificado. Verificable con `git status --short`.
