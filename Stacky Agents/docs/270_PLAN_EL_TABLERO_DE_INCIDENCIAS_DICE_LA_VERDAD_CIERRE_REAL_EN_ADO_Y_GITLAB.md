# Plan 270 — El tablero de incidencias dice la verdad: cierre real en ADO y GitLab

**Estado:** CRITICADO v1 -> v2 -> v3 -> v4
**Fecha:** 2026-07-28
**Rama de trabajo sugerida:** `feat/plan-270-tablero-incidencias-verdad`
**Numeración:** este plan es el **270**. El **271 YA ESTÁ TOMADO** (`271_PLAN_LA_INCIDENCIA_SE_MUEVE_AL_ESTADO_CONFIGURADO_AL_TERMINAR_EL_ANALISTA.md`, de una sesión paralela). El próximo libre real es el **272**. Ver §"Frontera con el plan 271".
**Juez v4: TERCERA pasada, juez independiente con contexto limpio, sobre el v3 ya commiteado (`5830e356`)**
**Veredicto v1: RECHAZADO** (5 BLOQUEANTES). **Veredicto v2: RECHAZADO** (5 BLOQUEANTES nuevos, todos hallados **ejecutando**). **Veredicto v3: RECHAZADO** (2 BLOQUEANTES: el DoD se desincronizó de sus propias fases en los DOS puntos que el v3 dijo haber arreglado). Todos resueltos abajo.

### CHANGELOG v3 -> v4

**Lo que el v3 hizo BIEN, y quedó verificado corriendo — no se toca nada de esto.** El juez del v4 re-midió, no releyó: censo AST propio (`ENTRADAS = 10 | SITIOS = 6`, idéntico), `_writes_by_function` de F6 ejecutado verbatim (**nace VERDE**: `{'finish_work': 2, 'set_stacky_status_by_ado': 2, 'create_child_task': 2}`), el objeto JSON de §6 pasado por `json.loads` + los 9 `_REQUIRED` + `re.search` del `self_test` (**todo OK**), las 4 suites del baseline corridas una por una (**4f/4p · 3f/5p · 2f/7p · 5f — los cuatro números exactos**), los 46 anclajes `archivo:línea` verificados contra el árbol (**0 archivos inexistentes, 0 líneas fuera de rango**), y los 8 `config.config` de `gitlab_provider.py` en las líneas declaradas. El v3 es, con diferencia, la mejor versión de este plan.

**Lo que igual lo hace RECHAZADO: el DoD contradice a las fases en los dos puntos exactos que el v3 declaró resueltos.** El checklist binario es lo que ejecuta un modelo menor. Si dice otra cosa que la fase, gana el checklist — y se implementa el bug.

- **D1 (BLOQ)** — **El consumidor de `diverged_count` está mal especificado POR TERCERA VEZ, ahora en el DoD.** El DoD exigía: *"el chip lo consume con `dto?.diverged_count ?? countDiverged(visible)`"*. La fase F5 especifica `resolveDivergenceCount(dto?.diverged_count, visible)` (bloque `tsx`). **No son equivalentes, y la diferencia es el bug que el plan existe para matar:** `resolveDivergenceCount` filtra con `typeof serverCount === "number" && Number.isFinite(serverCount)`, así que ante un `NaN`/`Infinity` **cae al conteo local**; `??` sólo cae ante `null`/`undefined`, deja pasar el `NaN` a `formatDivergenceCount`, y ésa devuelve `""` porque su primera guarda es `!Number.isFinite(n)`. Resultado: **el chip desaparece y la divergencia se vuelve invisible**. Además viola el docstring del propio módulo, que declara a `resolveDivergenceCount` *"el ÚNICO lugar donde se decide la precedencia"*. Historial: v1 C6 → v2 C4 → v3 DoD. Corregido abajo.
- **D2 (BLOQ)** — **El DoD pedía la huella con el id que §6 declara equivocado.** Dos bullets del mismo checklist eran mutuamente insatisfacibles: el de delta-cero nombra `PLAN270-GITLAB-SYNC-AUSENTE` y el último exigía *"la entrada `gitlab_sync_module_missing`"* — que es literalmente el id que §6 descarta por escrito. Un modelo menor que ejecute el checklist de arriba abajo escribe el id viejo y deja el catálogo incoherente con §6. Corregido abajo.
- **D3 (IMPORTANTE)** — **La justificación del rename en §6 es FALSA, medida.** §6 afirmaba que `gitlab_sync_module_missing` *"no sigue el patrón de ninguna de las 42 entradas"*. Censo real del catálogo: **32 de 42 ids son `snake_case`** (`pipeline_status_404`, `ansi_in_file_log`, `muted_500_untyped`, `epic_task_phantom_success`, …), **7** son `SCREAMING-KEBAB` y **3** son `kebab-minúscula`. El rename es igualmente correcto (`PLAN270-…` es más rastreable), pero **el motivo escrito era falso** y un modelo menor podría "normalizar" ids ajenos apoyándose en él. Reescrito con el número medido.
- **D4 (IMPORTANTE)** — **Conteo de tests desincronizado en el orden de implementación.** El paso 6 decía que `incidentDivergence.test.ts` lleva **12** casos; el criterio binario de la propia F5 dice **15** ("12 originales + los 3 de C4") y el paso 7 suma 3 para llegar a **18**, aritmética que sólo cierra desde 15. Un modelo menor que pare en 12 falla el criterio de F5. Corregido a 15.
- **D5 (MENOR)** — El 271 tiene **1790** líneas, no 1791 (medido). Y la frase *"los nombres `final_state_resolver`… no aparecen en el 270"* es literalmente falsa: aparecen **en esa misma frase**. Reescrita como lo que de verdad importa y de verdad se verificó: **ninguna fase del 270 consume un símbolo del 271** (`tracker_write_router`, `close_intent`, `ticket_state_writeback`, `incidentDivergence` dan **0** hits en el 271).
- **[ADICIÓN ARQUITECTO v4]** — **F6 caso 5: centinela del residuo S5.** El KPI del plan lleva un asterisco honesto — S5 (`agent_completion_internal.py:536`) escribe **siempre** en ADO y es del 271, que está **RECHAZADO dos veces y sin aprobar**. Hoy **nada avisa** si ese residuo desaparece (o crece): el asterisco se quedaría mintiendo en silencio, que es el pecado que este plan combate. El centinela lo convierte en señal mecánica. **Medido hoy: nace VERDE.** Ver el bloque marcado en F6.

### CHANGELOG v2 -> v3

El v2 no se releyó: se **corrió**. Censo por AST, `ast.parse` de los 13 bloques Python, `json.loads` del catálogo, y los tests que el plan nombra. Los 5 bloqueantes son de EJECUCIÓN — ninguno era visible leyendo.

- **C1 (BLOQ)** — **El censo de §2 C3.bis está incompleto: son 6 sitios / 10 entradas, no 4.** Censo por AST (script en §2 C3.bis). Faltaban: `services/agent_completion_internal.py:536` `_attempt_state_change` — que hace `AdoClient().update_work_item_state(...)` **sin mirar `tracker_type` ni provider**, es decir escribe SIEMPRE en ADO, y está VIVO (llamado desde `:274` y `:476`); `services/ado_provider.py:82` (adaptador); y la **segunda** entrada de `harness/task_states.py` (`:175`, `legacy_client_fn().update_work_item_state`), que el v2 no contó. Consecuencia: el Principio 4 prometía de más, y el KPI `divergencia = 0` era inalcanzable para GitLab en el camino de completación de agente.
- **C2 (BLOQ)** — **El ratchet de F6 nacía ROJO.** Medido: `grep -cE "provider\.update_item_state\(" harness/task_states.py` da **2**, no 1 — porque el regex cuenta el **docstring** de `:158`. El v2 congelaba 1. Un ratchet que falla el día 1 se "arregla" subiendo el número, que es exactamente lo que prohíbe. Ahora los números están **medidos y pegados**, el patrón frágil se reemplaza, y F6 se re-scopea para no chocar con el censo del 271.
- **C3 (BLOQ)** — **La huella de regresión rompía el catálogo JSON entero.** Medido: `json.loads('{"log_pattern": "No module named \'services\.gitlab_sync\'"}')` levanta `JSONDecodeError: Invalid \escape`. Además `_REQUIRED` (`tests/test_error_fingerprints_catalog.py:18`) exige **`self_test`**, campo que el v2 **ni nombraba** (y sí nombraba dos que no son obligatorios). Ahora va el objeto JSON **literal**, con `\\.` y `self_test` real, más el test y el comando.
- **C4 (BLOQ)** — **F5 se contradecía a sí misma y `diverged_count` volvía a quedar SIN consumidor** — que era exactamente el C6 que el v2 dijo haber arreglado. El bloque `tsx` renderiza `divergenceSummary(visible)`; la prosa de al lado dice que el chip usa `dto?.diverged_count ?? countDiverged(visible)`. Son incompatibles: `divergenceSummary(items: IncidentInboxItem[])` **no acepta un número** y ninguna función del módulo formatea uno. Ahora existe `formatDivergenceCount(n)` y el `tsx` consume el valor del servidor.
- **C5 (BLOQ)** — **La pata 6 declaraba UNA restricción de las SEIS que el test asserta, y dos chocan de frente con este plan.** `tests/test_harness_flags_help.py` exige además: `what` 10..200 (`:47-48`), `example` ≤300 (`:51`), `on_effect`/`off_effect` **empiezan con `"Si "`** (`:59-60`), **denylist de 15 términos** incl. `gate`/`runtime`/`backend`/`frontend`/`endpoint`/`token` (`:17-20`), **prohibido citar keys SCREAMING_SNAKE** (`_KEY_RE`, `:22`) y **prohibido citar fases `F<n>`** (`_PHASE_RE`, `:23`). El plan entero martilla "el texto NOMBRA `STACKY_GITLAB_ENABLED`" y rotula todo "F0..F6": un modelo menor copia eso a `PlainHelp` y se pone rojo. Ahora los **3 textos van literales y ya medidos**.
- **C6..C15 (IMPORTANTES)** — el v2 "corrigió" un anclaje que el v1 tenía BIEN y lo dejó mal (`incident_inbox_status` es `:65-81` con `actions_enabled` en `:76`, verificado con `grep -n`); F4 se contradice ("sólo escribe `ado_state`" vs. delegar en `upsert_single_work_item`, que escribe **8 columnas más**); **cuatro suites rojas de fábrica sin declarar**, dos de ellas en archivos que el plan DEBE tocar; frontera con el 271 ausente; numeración de continuaciones apuntando a números tomados; `gitlab_provider.py` la key `"state"` está en `:86` (no `:85` — anclaje que **agregó** el v2); `rows[:MAX_ITEMS]` en `:158` (no `:159`); `incidentInboxModel.ts` tiene `:17`=`stacky_status` y `:19`=`is_open` (invertidos en el v2); el grep de `--color-` da **4** hits (no 3); el glosario decía **6** patas mientras el resto del plan dice **7**.
- **[ADICIÓN ARQUITECTO]** — **F7: dry-run de destino.** El diálogo de cierre YA dispara un dry-run real (`api/tickets.py:1801`, early-return `:1934-1944`; `FinishWorkButton.tsx:80-81` lo lanza solo al abrir). F7 enriquece ESA respuesta con el destino resuelto por F0+F1 **sin escribir nada**: el operador ve *"va a GitLab, va a quedar `accepted`, cerrada"* **antes** de confirmar. Cero llamadas nuevas, cero flags nuevas, aditivo, y es el pago exacto de haber construido F0/F1 puros. Ver el bloque marcado.

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

**ALCANCE HONESTO DEL KPI (C3 — corregido en v2; ACOTADO EN v3 por C1).** `stacky_status` pasa a `"completed"` desde **dos** caminos, no uno:
1. **manual** — `finish_work` (`api/tickets.py:1751`), que es el botón "Cerrar" de la bandeja (`FinishWorkButton.tsx:51,62` y el worker del lote `IncidentInboxPage.tsx:207`, ambos contra `POST /api/tickets/{id}/finish-work`);
2. **automático** — `set_stacky_status_by_ado` (`api/tickets.py`, bloque `:1487-1509`), que corre cuando **termina un agente**, y es el de **mayor volumen**.

El v1 sólo cableaba el writeback en (1) ⇒ el KPI no podía llegar a 0. En v2, **F4 se cablea en los dos**. Para ADO el camino (2) además ya tiene refresco por `completion_sync` (flag `STACKY_ADO_SYNC_ON_COMPLETION_ENABLED` default `true`, `config.py:1398-1399`); para **GitLab ese refresco está roto** (C4 abajo) y por eso el writeback propio de F4 es la única vía.

> **ASTERISCO OBLIGATORIO DEL KPI (C1 — v3, hallado por censo AST).** Existe un **tercer** motor que escribe el estado final y que el v2 no censó: `services/agent_completion_internal.py:536` `_attempt_state_change`, que hace `AdoClient().update_work_item_state(int(ado_id), target_state)` **sin consultar `tracker_type` ni provider** — o sea, escribe **siempre en Azure DevOps**, incluso para un proyecto GitLab. Está VIVO: lo llaman `:274` (paso 4 del cierre de ejecución) y `:476` (`publish_execution_from_review`). **Ese motor es territorio del plan 271** (su F3 lo enruta; ver §"Frontera con el plan 271") y **este plan NO lo toca**. Consecuencia honesta y escrita: con el 270 solo, el KPI llega a 0 en los caminos (1) y (2); **el residuo del motor de `agent_completion_internal` sólo se cierra cuando aterriza el 271**. Enunciar `divergencia = 0` sin este asterisco sería el mismo error que el v1 cometió con el camino (2). El KPI de aceptación de ESTE plan es por lo tanto: **divergencia = 0 medida sobre incidencias cerradas por (1) `finish_work` o (2) `set_stacky_status_by_ado`** — que es lo que verifican los tests 3 y 10 de F4.

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

#### C3.bis — CENSO COMPLETO de escrituras de estado (v2 lo hizo con grep y le faltaban 2 sitios; v3 lo hace por AST)

**Contar con grep textual NO alcanza** — el v2 declaró 4 sitios y la realidad son **6 sitios / 10 entradas**. Un modelo menor que lea sólo el Principio 4 y no este censo va a creer que el invariante ya vale en todo el repo.

**Censo REPRODUCIBLE, por AST. Corrélo ANTES de tocar nada** (guardalo en el scratchpad, no en el repo):

```python
import ast, pathlib, collections
ROOT = pathlib.Path(r"N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend")
TARGET = {"update_item_state", "update_work_item_state"}
hits = []
for p in sorted(ROOT.rglob("*.py")):
    rel = p.relative_to(ROOT).as_posix()
    if rel.startswith(("tests/", ".venv/", "venv/")) or "__pycache__" in rel:
        continue
    tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
    fns = [n for n in ast.walk(tree)
           if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
           and node.func.attr in TARGET:
            owner = max(
                (f for f in fns if f.lineno <= node.lineno <= (f.end_lineno or f.lineno)),
                key=lambda f: f.lineno, default=None,
            )
            hits.append((rel, owner.name if owner else "<module>", node.lineno,
                         ast.unparse(node.func.value) + "." + node.func.attr))
sites = collections.OrderedDict()
for rel, fn, ln, expr in hits:
    sites.setdefault((rel, fn), []).append((ln, expr))
for (rel, fn), e in sites.items():
    print(f"{rel}::{fn} -> {e}")
print("ENTRADAS =", len(hits), "| SITIOS =", len(sites))
```

**Salida REAL medida en `d234021e` (pegada, no estimada) — `ENTRADAS = 10 | SITIOS = 6`:**

| # | Sitio (`archivo::función`) | Entradas | Qué es | ¿Lo arregla este plan? |
|---|---|---|---|---|
| **S1** | `api/tickets.py::finish_work` | `:2078` provider · `:2080` cliente ADO | El botón **"Cerrar"** de la bandeja | **SÍ**, F3 |
| **S2** | `api/tickets.py::set_stacky_status_by_ado` | `:1490` provider · `:1492` cliente ADO | Cierre **automático al terminar un agente**. Mismo patrón, mismo bug, **más volumen** | **SÍ**, F3 |
| **S3** | `api/tickets.py::create_child_task` | `:4779` provider · `:4781` `ado.update_work_item_state` | Estado inicial de una **Task recién creada** | **NO** — carve-out: eje del **Plan 70**; `target_state` sale de la config de tareas, no del operador |
| **S4** | `harness/task_states.py::_safe_transition` | `:173` provider · **`:175` `legacy_client_fn()`** | El escritor canónico del **Plan 79**. **Su docstring (`:155`) dice "ÚNICA función que escribe estado" y ESO ES FALSO** — hay otras cinco. No creas al docstring | **NO** — carve-out: eje del Plan 79 |
| **S5** | `services/agent_completion_internal.py::_attempt_state_change` | `:536` `AdoClient().update_work_item_state` | **EL QUE FALTABA.** Construye el cliente ADO **directo**, sin mirar `tracker_type` ni provider ⇒ **escribe SIEMPRE en Azure DevOps**, incluso en un proyecto GitLab. **VIVO**: llamado desde `:274` y `:476` | **NO** — es del **plan 271** (su F3 lo enruta). Ver §"Frontera con el plan 271". Este plan **no lo toca** para no colisionar |
| **S6** | `services/ado_provider.py::update_item_state` | `:82` `self._client.update_work_item_state` | **Adaptador** del puerto `TrackerProvider` → `AdoClient`. No decide destino: ya está del lado ADO por construcción | **NO** — carve-out permanente: es la implementación del puerto, no un call site de negocio |

**Por qué S5 importa y no es una nota al pie.** Es el único sitio del repo que **no tiene ni siquiera la rama `_provider_for_ticket`**: S1/S2/S3 al menos preguntan; S5 va derecho a `AdoClient()`. Para un proyecto GitLab, S5 escribe en el ADO equivocado *hoy*, y este plan **no lo arregla**. Está declarado acá, en el KPI (§1) y en la frontera con el 271. Cualquier redacción que diga o sugiera lo contrario es falsa.

**Efecto colateral de F2 sobre S2/S3/S4, declarado:** el guardia de F2 vive dentro de `GitLabTrackerProvider.update_item_state`, así que protege a **todos los que pasan por el provider** contra el `reopen` silencioso. Eso convierte un `reopen` mudo en una excepción capturada por su propio `except` (`tickets.py:4787`; `harness/task_states.py:179-183` ya envuelve la llamada) ⇒ el resultado pasa de *"hizo lo contrario en silencio"* a *"no hizo nada y quedó registrado"*. Cubierto por el test 2 de F2 (los estados que legítimamente reabren siguen reabriendo). **S5 NO recibe este beneficio**: nunca toca el provider de GitLab.

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

### Frontera con el plan 271 (v3 — **obligatoria: pisan el mismo eje**)

`Stacky Agents/docs/271_PLAN_LA_INCIDENCIA_SE_MUEVE_AL_ESTADO_CONFIGURADO_AL_TERMINAR_EL_ANALISTA.md` **existe** (untracked, de una sesión paralela, **CRITICADO v3 — RECHAZADO en v1 y v2**). Su tema es *mover la incidencia al estado configurado al terminar el analista*, o sea **el mismo camino de escritura de estado** que el 270 corrige. **Dos planes arreglando el mismo `if` de formas distintas es una colisión real.** Esta sección la desarma. **Este plan NO edita el 271** (es untracked ajeno); sólo declara la repartición.

**Reparto de propiedad, sitio por sitio** (numeración del censo AST de §2 C3.bis):

| Sitio | Quién es DUEÑO | Qué hace cada uno | ¿Se pisan? |
|---|---|---|---|
| **S1** `api/tickets.py::finish_work` | **270** (F3, F4, F7) | El 270 enruta el destino, refresca el estado local y previsualiza. El 271 **declara `api/tickets.py` intocable** (su §6.6: *"este plan no edita ni una línea de ese archivo"*) y sólo lo censa | **NO** |
| **S2** `api/tickets.py::set_stacky_status_by_ado` | **270** (F3, F4) | Ídem. **Ojo, único punto de roce real:** el 271 cambia el **contenido** del dict que devuelve `close_execution_with_publish`, que esta función serializa. El 270 toca la variable local `state_change_result` (`:1466-1503`), que **no** es el `CloseResult` del 271 | **Roce, no colisión** — ver regla de merge abajo |
| **S3** `api/tickets.py::create_child_task` | **Plan 70** | Ninguno de los dos lo toca. El 270 lo congela en F6; el 271 lo censa | NO |
| **S4** `harness/task_states.py::_safe_transition` | **Plan 79** | El 270 **no lo toca**. El 271 le agrega **una** key (`"reason": "transition_failed"`) a su rama de error (`:180-184`) | NO |
| **S5** `services/agent_completion_internal.py::_attempt_state_change` | **271** (su F3) | **El 270 NO lo toca.** Es el escritor que hoy va siempre a ADO; el 271 lo enruta por `get_tracker_provider`. El 270 lo declara en su KPI como residuo conocido | **NO** |
| **S6** `services/ado_provider.py::update_item_state` | Nadie (adaptador) | Ninguno lo toca | NO |
| `services/gitlab_provider.py::update_item_state` | **270** (F2) | El 270 le pone el guardia anti-`reopen`. El 271 **no lo toca** (única mención: un gotcha que sólo lo cita) | **NO** |
| `services/completion_state.py`, `api/executions.py`, `frontend/src/utils/finalStateOutcome.ts` | **271** | El 270 no los menciona | NO |
| `services/incident_inbox.py`, `api/incident_inbox.py`, `IncidentInboxPage.tsx` | **270** (F5) | El 271 tiene **0 menciones** de `incident_inbox` en sus **1790** líneas (medido en `wc -l`; el v3 decía 1791) | **NO** |

**Los dos ratchets/censos, repartidos (esto es lo que más fácil se pisaba):**
- **270 F6** ⇒ `tests/test_plan270_state_write_ratchet.py`, alcance **`api/tickets.py` únicamente**, por AST, por función.
- **271 F8** ⇒ `tests/test_plan271_censo_escritores.py`, alcance **`backend/` entero** (9 entradas, incluye llamadas a `_safe_transition`), por AST.
⇒ **Archivos distintos, alcances anidados, misma técnica (AST).** El del 270 es un subconjunto estricto del del 271: si los dos están verdes, son consistentes; si el del 271 se pone rojo por un sitio nuevo en `api/tickets.py`, el del 270 también ⇒ señal doble, nunca contradictoria. **Ninguno de los dos se relaja para acomodar al otro.**

**Flags: cero solape.** El 270 da de alta `STACKY_TRACKER_STATE_WRITE_ROUTING_ENABLED`, `STACKY_TICKET_STATE_WRITEBACK_ENABLED`, `STACKY_INCIDENT_DIVERGENCE_BADGE_ENABLED`. El 271 da de alta cuatro `STACKY_FINAL_STATE_*`. Los **7** nombres son distintos; las **7** nacen ON. El roce es sólo que **los dos editan `harness_flags.py`, `harness_flags_help.py`, `config.py` y los dos arneses de forma ADITIVA** ⇒ merge de 3 vías sin conflicto, **pero** ojo con el duplicado silencioso: si los dos agregan una línea al mismo cierre de tupla, git no marca conflicto. **Tras mergear, correr `python -m compileall backend` y `pytest tests/test_harness_flags.py -q`.**

**Archivos de test: cero solape.** Los 6 del 270 son `test_plan270_*.py`; los 11 del 271 son `test_plan271_*.py`.

**REGLA DE MERGE (acordada con lo que el propio 271 declara en su R10): _si los dos están listos, entra primero el 270._** Motivo: el 270 edita `api/tickets.py` y el 271 lo declara intocable, así que el 271 **nunca** genera conflicto contra el 270 en ese archivo; al revés sí habría que rebasar el 270 sobre cambios de comportamiento del 271. Implementarlos en el otro orden **también funciona** — ningún criterio de aceptación de uno depende de un símbolo del otro. **Verificado corriendo (D5 v4 — redacción corregida; la anterior decía "no aparecen en el 270" y era literalmente falsa, porque aparecían en esa misma frase):** `tracker_write_router`, `close_intent`, `ticket_state_writeback` e `incidentDivergence` dan **0 hits** en el 271; y `final_state_resolver`, `final_state_outcome` y `STACKY_FINAL_STATE_*` aparecen en el 270 **únicamente dentro de esta sección de frontera** — es decir, como declaración *sobre* el 271, **nunca dentro de una fase, un criterio de aceptación ni un bloque de código**. **Esto es lo que importa y es lo que hay que re-verificar si alguien edita las fases: ninguna fase del 270 consume un símbolo del 271.** Consecuencia práctica: **el 270 NO está bloqueado por el 271**, que está RECHAZADO dos veces y sin aprobar. Si dependiera de él, sería un bloqueante de secuencia — pero exige re-correr `test_plan271_censo_escritores.py` después, porque el 270 no cambia los conteos del censo (F3 no borra llamadas, las mueve bajo el `else`) y eso hay que **confirmarlo, no suponerlo**.

**Lo que este plan NO hace y el 271 sí:** decidir **qué** estado poner al terminar un agente (matriz / rol / config), enrutar S5, y persistir la razón del outcome. **Lo que este plan hace y el 271 no:** que el cierre **desde la bandeja** llegue al tracker correcto, que el estado local se refresque, y que el tablero muestre la divergencia.

---

## 3. Principios y guardarraíles

1. **Ninguna capacidad de escritura NUEVA sobre el tracker.** Este plan **no agrega** superficies que escriban en el ADO/GitLab del operador. Corrige el enrutado y la corrección de una escritura que **ya existe hoy** y que **el operador confirma explícitamente** apretando "Cerrar". La escritura genuinamente nueva — reconciliación masiva Stacky→tracker — queda **fuera de scope** (plan 271 sugerido) con default OFF por categoría (B).
2. **Partición lectura/escritura de flags, según la directiva del operador.** Todo lo que **lee** el tracker o **compara** estados va **default ON**. Precedente citado por el operador: `STACKY_PIPELINE_NL_EDIT_ENABLED` (ON) vs `STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED` (OFF). Las tres flags de este plan son ON y se justifica una por una en su fase.
3. **Fallar declarado, nunca adivinar.** Un estado no mapeable produce `CapabilityUnavailable` (mecanismo ya existente del 218, `tracker_provider.py:55`), nunca una acción por defecto. La regla dura: **jamás emitir `reopen` cuando la intención es cerrar.**
4. **Nunca escribir en el sistema equivocado.** Un ticket cuyo `tracker_type` no es `azure_devops` **no puede** resolverse al cliente ADO. Si el proveedor real no está disponible, la acción devuelve un error honesto. **Alcance exacto de esta promesa (C2 v2; ACOTADO en v3 por C1):** vale para **S1 y S2** del censo de §2 C3.bis — los dos caminos que cierran una incidencia desde el tablero. **NO** vale para **S3, S4, S5 ni S6**, que quedan con carve-out escrito y dueño nombrado (S3→Plan 70, S4→Plan 79, S5→**Plan 271**, S6→adaptador del puerto). El invariante **NO es global en el repo, y este plan no lo vuelve global.** Cualquier redacción que sugiera lo contrario es falsa. Lo que F6 congela es que **no aparezca un séptimo** sin que la suite se ponga roja.
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
| 6 | **(C11 v2 / C5 v3 — la pata invisible, y es MUCHO más estricta de lo que el v2 creía)** `backend/tests/test_harness_flags_help.py` | **SEIS restricciones asertadas, no una.** Ver el recuadro de abajo. No hay que editar este archivo: hay que **respetar el contrato al escribir la pata 5** |
| 7 | `deployment/export_harness_defaults.py` | Regenerar `harness_defaults.env` con el generador (no editarlo a mano) |

#### Pata 6 — contrato COMPLETO de `PlainHelp` (leído del test, no supuesto)

El v2 declaraba sólo el límite de 240. `backend/tests/test_harness_flags_help.py` asserta **seis** cosas, y **dos de ellas chocan de frente con la redacción de este plan**:

| # | Regla | Ancla |
|---|---|---|
| 1 | `10 <= len(what) <= 200` | `:47-48` |
| 2 | `len(on_effect) <= 240` y `len(off_effect) <= 240` | `:49-50` |
| 3 | `len(example) <= 300`; ningún campo vacío | `:51-53` |
| 4 | `on_effect` y `off_effect` **empiezan con la cadena literal `"Si "`** (sin tilde) | `:59-60` |
| 5 | **Denylist de jerga** (15 términos, case-insensitive, con plural opcional): `MCP, TF-IDF, LLM, stdin, stdout, endpoint, frontmatter, prompt, token, regex, backend, frontend, gate, hook, runtime` | `:17-20`, `:68-71` |
| 6 | **PROHIBIDO citar una key `SCREAMING_SNAKE`** (`_KEY_RE = \b[A-Z]+_[A-Z0-9_]+\b`) **y PROHIBIDO citar una fase `F<n>`** (`_PHASE_RE = \bF\d`) | `:22-23`, `:72-75` |

> **La trampa exacta de ESTE plan.** El documento martilla *"el `workaround` NOMBRA la flag literal `STACKY_GITLAB_ENABLED`"* y rotula todo *"F0..F7"*. Eso es correcto **para `CapabilityUnavailable.workaround`** (que no tiene contrato de texto) y **fatal para `PlainHelp`** (reglas 5 y 6). Un modelo menor que copie el tono del plan a la ayuda llana pone el arnés rojo sin entender por qué. **Por eso los tres textos van LITERALES abajo: se copian tal cual, no se parafrasean.**

**Los 3 `PlainHelp` LITERALES (ya medidos: los 3 cumplen las 6 reglas — `what` 128/140/119, `on_effect` 202/170/172, `off_effect` 125/119/97, `example` 128/115/103; **0 violaciones**).** Copiar exactamente.

> **Es un FRAGMENTO de dict, no un módulo.** Estas tres entradas van **dentro** del `PLAIN_HELP = { ... }` de `services/harness_flags_help.py`, junto a las otras 307. Pegado como archivo suelto da `SyntaxError: illegal target for annotation` — verificado. No lo envuelvas en nada ni le agregues imports: `PlainHelp` ya está definido en ese archivo.

```python
    "STACKY_TRACKER_STATE_WRITE_ROUTING_ENABLED": PlainHelp(
        what="Manda el cambio de estado al sistema de tickets que el proyecto usa de verdad, en vez de intentarlo siempre contra Azure DevOps.",
        on_effect="Si la activás (viene así de fábrica): al cerrar una incidencia, Stacky escribe en el sistema que corresponde y traduce el estado al vocabulario de ese sistema. Si no puede, te lo dice y no escribe nada.",
        off_effect="Si la apagás: vuelve el comportamiento viejo, que intenta el cambio contra Azure DevOps aunque el proyecto viva en otro lado.",
        example="Cerrás una incidencia de un proyecto de GitLab: antes se intentaba contra Azure DevOps y quedaba mal; ahora se cierra en GitLab.",
    ),
    "STACKY_TICKET_STATE_WRITEBACK_ENABLED": PlainHelp(
        what="Despues de cambiar el estado en el sistema de tickets, vuelve a leerlo y actualiza la copia local para que la lista no muestre datos viejos.",
        on_effect="Si la activás (viene así de fábrica): al terminar el cierre, la fila del tablero pasa sola a su estado real, sin recargar la pantalla ni esperar la sincronizacion grande.",
        off_effect="Si la apagás: el cierre igual se hace, pero la fila sigue mostrando el estado anterior hasta la proxima sincronizacion.",
        example="Cerrás un reclamo y la fila pasa de Abierta a Cerrada en el momento, en vez de quedarse en Abierta y hacerte dudar.",
    ),
    "STACKY_INCIDENT_DIVERGENCE_BADGE_ENABLED": PlainHelp(
        what="Marca en la lista las incidencias que Stacky ya dio por terminadas pero el sistema de tickets sigue mostrando abiertas.",
        on_effect="Si la activás (viene así de fábrica): esas filas suman una marca que dice Sin sincronizar, y arriba aparece un boton para ver solo esas. No cambia nada, solo te lo muestra.",
        off_effect="Si la apagás: la lista se ve igual que antes y las filas desalineadas no se distinguen del resto.",
        example="Cerraste ocho reclamos y dos quedaron a medias: los ves marcados en vez de descubrirlo semanas despues.",
    ),
```

**Verificación binaria de la pata 6** (correr DESPUÉS de agregar las 3 entradas):
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.\.venv\Scripts\python.exe -m pytest tests\test_harness_flags_help.py -q
```
**Criterio (delta, no verde absoluto — ver §"Baseline medido"):** el resultado debe seguir siendo **exactamente `4 failed, 4 passed`** y **ninguna** de las violaciones reportadas puede nombrar una key `STACKY_TRACKER_STATE_WRITE_ROUTING_ENABLED`, `STACKY_TICKET_STATE_WRITEBACK_ENABLED` ni `STACKY_INCIDENT_DIVERGENCE_BADGE_ENABLED`. Si aparece alguna de las tres, la culpa es de este plan.

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

### Baseline MEDIDO de rojos preexistentes (C8 — v3). Sin esto, el DoD es inalcanzable

**Cuatro suites que este plan toca o nombra ya están ROJAS de fábrica, en `d234021e`, sin que nadie las haya roto.** Medido corriendo, no recordado. Si no lo declarás, el implementador cree que su cambio las rompió y "arregla" borrando asserts:

| Suite | Resultado HOY | Por qué importa acá |
|---|---|---|
| `tests/test_harness_flags_help.py` | **4 failed, 4 passed** | Es la **pata 6**. Las violaciones actuales son **1 de longitud** + **15 de la denylist** (14 de jerga + 1 de key `SCREAMING_SNAKE`), sobre **307** entradas. Criterio de este plan: **el número no puede subir y ninguna violación puede nombrar una de sus 3 keys** |
| `tests/test_error_fingerprints_catalog.py` | **3 failed, 5 passed** | Es donde va la huella de §6. Falla por deuda ajena: una huella sin `self_test`, y `status: "guarded"` que no está en `_STATUS_ENUM` (`:17`). Criterio: **seguir en 3 failed, y que ninguna falla nombre `PLAN270-GITLAB-SYNC-AUSENTE`** |
| `tests/test_error_fingerprints_scan.py` | **2 failed, 7 passed** | Misma causa (`KeyError`). Sólo se declara para que no se confunda con daño propio |
| `tests/test_b2_transition_from_config.py` | **5 failed** (`TypeError: _resolve_transition_state_from_config() missing 1 required keyword-only argument: 'final_status'`) | **No lo toca este plan** — es del eje del **271**, que lo adopta en su F4-bis. Se declara para que nadie lo "arregle de paso" y colisione |

**Regla dura:** el DoD de este plan NUNCA dice "la suite X está verde" sobre ninguna de estas cuatro. Dice **"el delta es cero y ninguna falla nombra un símbolo del plan 270"**. Un criterio de "verde absoluto" sobre una suite roja de fábrica es un DoD inalcanzable, y se "resuelve" borrando asserts ajenos.

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
> **La "única excepción" del v2 QUEDÓ ELIMINADA en v3 (E2).** El v2 declaraba que F6 debía ir al final "porque congela conteos que dependen de que F3 ya haya reescrito S1 y S2". **Medido: es falso.** F3 no borra las llamadas históricas — las mete bajo el `else` del rollback — así que el conteo AST es **idéntico antes y después** (`{'finish_work': 2, 'set_stacky_status_by_ado': 2, 'create_child_task': 2}`). F6 se puede escribir en cualquier orden. **Ahora sí, sin asteriscos: ninguna fase depende de una posterior.**
>
> **Cruce de criterios entre fases — chequeado, sin contradicciones:**
> - El par que podría chocar es el test 2 de F2 (`in_progress` **debe** seguir emitiendo `state_event: "reopen"`) contra el centinela anti-reopen del test 5 de F2 y del test 8 de F0. **No chocan:** el centinela recorre `ADO_CLOSE_STATES` (`"Done"`, `"Closed"`, `"Resolved"`), **disjunto** de `GITLAB_LOGICAL_STATES` (`functional`, `accepted`, `rejected`, `in_progress`).
> - **Costura F5↔F4 (C4):** el chip consume `diverged_count` del backend; F4 caso 12 fija el valor del servidor y F5 casos 14/15 fijan que ese número **llegue al texto**. Las dos puntas de la costura tienen test, en el lado que corresponde (backend toca DB, frontend es `.ts` puro).
> - **Costura F7↔F1/F0:** `preview_state_write` reusa **las mismas dos funciones** que `write_state_for_ticket`, en el **mismo orden**. Si alguien cambia la firma de una, los dos caminos se rompen juntos y se ve — no hay una segunda implementación que se desincronice en silencio.
> - **Aridad de los helpers que el plan invoca — verificada abriendo la firma real:** `resolve_closed_states(profile) -> tuple[tuple[str, ...], str]` (**2-tupla**, `services/incident_inbox.py:51`) · `upsert_single_work_item(client: AdoClient, ado_id: int) -> dict | None` (`ado_sync.py:235`) · `CapabilityUnavailable(capability, provider, *, reason, workaround="")` — **`reason` es keyword-only y OBLIGATORIO** (`tracker_provider.py:62`) · `build_ado_client(project_name=None, *, tracker_project=None, ticket=None)` (`project_context.py:289`) · `get_item(self, item_id: str) -> dict` (`tracker_provider.py:82`).
> - Ningún criterio exige "0 errores sobre un corpus" ni "N/N y si algo no cierra se agrega lo que falte": todos los conteos son **cerrados y enumerados** (11, 14, 6, 10, 12, 4 en backend; 18 en vitest). Los criterios sobre suites rojas de fábrica son **deltas**, no verdes absolutos (§"Baseline medido").

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

**Criterio de aceptación (BINARIO):** los **10** tests pasan; el archivo está en los 2 arneses. **(F7 le agrega 4 más ⇒ el archivo termina con 14. Al cerrar el plan el conteo exigido es 14.)**

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
  **C10 — la key es literalmente `"state"`, no "el campo de estado":** `_normalize_issue` la produce en **`gitlab_provider.py:86`** (el v2 decía `:85`, que es la línea de `"description"` — verificado con `grep -n '"state"'`) con `body.get("state") or ""`, y GitLab devuelve `"opened"` / `"closed"`. Se escribe `Ticket.ado_state = str(item.get("state") or "")`. **Que `"closed"` cuente como cerrado no es casualidad:** `DEFAULT_CLOSED_STATES` (`services/incident_inbox.py:15-17`, **cinco** valores: `Done, Closed, Resolved, Removed, Completed`) incluye `"Closed"` y la comparación es case-insensitive vía `normalize()` — está documentado en `services/incident_inbox.py:13-14`. Si `item.get("state")` viene vacío, `reason = "state_absent"` y **la columna NO se pisa**.
- **`session_scope` se importa de `db.py:485`** (`from db import session_scope`), **no de `models.py`**. Errar da `ImportError`.

**Regla de escritura mínima — ALCANCE REAL, corregido en v3 (C7).** El v2 escribía que este módulo *"sólo escribe `Ticket.ado_state`… **no** toca `title` ni `work_item_type`"* **y a la vez** mandaba delegar en `services.ado_sync.upsert_single_work_item` para la rama ADO. **Las dos cosas no pueden ser ciertas.** Verificado abriendo `ado_sync.py:326-335`: en la rama "ticket ya existe", `upsert_single_work_item` escribe **nueve** columnas — `title`, `description`, `ado_state`, `ado_url`, `priority`, `work_item_type`, `parent_ado_id`, `last_synced_at`, `assigned_to_ado` — y en la rama "no existe" además inserta una fila de `TicketStateHistory` (`:314-323`).

El contrato honesto es **por rama**, y es el que hay que implementar y testear:

| Rama | Qué escribe realmente | Por qué es aceptable |
|---|---|---|
| `kind == "ado_client"` | Las 9 columnas de `upsert_single_work_item` (**incluye `title`, `work_item_type`, `assigned_to_ado`**) | Es el helper **que ya usa el repo** para refrescar un work item puntual. Reimplementar un GET+UPDATE de una sola columna sería código nuevo duplicando uno vivo y probado, contra el principio de reusar lo existente. Todos los valores vienen del tracker, así que "pisar" es **converger a la verdad** |
| `kind == "provider"` | **Sólo** `Ticket.ado_state` y `last_synced_at` | El puerto `get_item` devuelve un dict normalizado; escribir más sería mapear a mano campos que nadie pidió |

**Lo que SÍ vale en las dos ramas, y es lo único que el plan promete:** el writeback **nunca toca `stacky_status`**. Verificado: `upsert_single_work_item` tiene **0 apariciones** de `stacky_status` (`sed -n '235,345p' services/ado_sync.py | grep -c stacky_status` ⇒ 0). Ése es el invariante que fija el test 7, y es el que importa: si el writeback pisara `stacky_status`, se comería el `"completed"` que acaba de escribir el paso 5 y el KPI mediría cualquier cosa.

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

**Por qué es gratis:** `is_open` y `stacky_status` **ya viajan** en cada ítem del DTO (`api/incident_inbox.py:163` agrega `is_open`; `models.py:101` incluye `stacky_status` en `to_dict()`; el tipo del frontend ya los declara en `frontend/src/incidents/incidentInboxModel.ts` — **`:17` es `stacky_status?: string;` y `:19` es `is_open: boolean;`**, el v2 los tenía invertidos). **Cero endpoints nuevos, cero llamadas nuevas, cero costo por fila.**

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

/** C4 (v3) — Formatea un NUMERO ya calculado. Cadena VACIA en 0, para que la UI
 *  no muestre un chip con cero (ruido).
 *
 *  Existe separada de divergenceSummary porque el chip consume el conteo del
 *  SERVIDOR (diverged_count, exacto por agregacion) y no la lista local, que
 *  viene truncada por MAX_ITEMS y filtrada por la busqueda. Sin esta funcion
 *  la key del backend NO tiene forma de llegar a la pantalla. */
export function formatDivergenceCount(n: number): string {
  if (!Number.isFinite(n) || n <= 0) return "";
  return n === 1 ? "1 sin sincronizar" : `${n} sin sincronizar`;
}

/** Texto del chip a partir de una lista local. Fallback para un backend viejo
 *  que no manda diverged_count. Delega en formatDivergenceCount: una sola
 *  regla de formato, imposible que las dos vias digan cosas distintas. */
export function divergenceSummary(items: IncidentInboxItem[]): string {
  return formatDivergenceCount(countDiverged(items));
}

/** C4 (v3) — El conteo que manda: el del servidor si vino, el local si no.
 *  Este es el UNICO lugar donde se decide la precedencia. */
export function resolveDivergenceCount(
  serverCount: number | null | undefined,
  items: IncidentInboxItem[],
): number {
  return typeof serverCount === "number" && Number.isFinite(serverCount)
    ? serverCount
    : countDiverged(items);
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

**C16 — el tipo del status hay que ampliarlo.** En `frontend/src/incidents/incidentInboxModel.ts`, dentro de `interface IncidentInboxStatus` (**`:42-53`**; el v2 decía `:42-54` y la `:54` está en blanco), agregar **opcional**:
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
   // C4 (v3) — el conteo del SERVIDOR manda; la lista local es el fallback.
   // Se calcula una sola vez y se usa para el gate Y para el texto: si el gate
   // mirara una fuente y el texto otra, el chip podria aparecer vacio.
   const divergentes = resolveDivergenceCount(dto?.diverged_count, visible);
   const textoChip = formatDivergenceCount(divergentes);
   ```
   ```tsx
   {divergenciaVisible && textoChip !== "" && (
     <Button
       variant="secondary"
       size="sm"
       aria-pressed={soloDivergentes}
       title={DIVERGENCE_BADGE_TITLE}
       onClick={() => setSoloDivergentes((v) => !v)}
     >
       {textoChip}
     </Button>
   )}
   ```
   **Por qué el conteo del servidor y no `visible` (C4 — el v2 se contradecía acá).** El v2 escribía el `tsx` con `divergenceSummary(visible)` y en el párrafo de al lado decía que el chip usaba `dto?.diverged_count ?? countDiverged(visible)`. Son **incompatibles**: `divergenceSummary` recibe una **lista**, no un número, y en el módulo del v2 **no existía ninguna función que formateara un número** ⇒ `diverged_count` volvía a quedar sin consumidor, que es exactamente el defecto C6 que el v2 dijo haber arreglado. Con `formatDivergenceCount` + `resolveDivergenceCount` la key **sí** llega a la pantalla.
   **Y además el servidor es el valor correcto:** `visible` está truncada por `MAX_ITEMS` (`api/incident_inbox.py:158`, `rows = rows[:MAX_ITEMS]`) **y** filtrada por la búsqueda (`:175` `filterBySearch`). Contar sobre `visible` haría que el número del chip **cambie mientras el operador tipea**, que es justo la clase de mentira que este plan viene a matar.
   **Ojo con el filtro:** el texto del chip **nunca** se calcula sobre `mostrados` — si no, al activar el filtro el número se congelaría en sí mismo.
2. `Stacky Agents/frontend/src/pages/IncidentInboxPage.module.css` — clase `.divergedBadge`. **Sin colores literales ni HEX**: usar los tokens que el tema **sí** define, verificados abriendo `frontend/src/theme.css`: `--danger` (`:21` dark / `:191` light), `--border` (`:8` / `:177`), `--text-primary` (`:12` / `:182`), `--bg-panel` (`:6` / `:175`), `--accent` (`:17` / `:187`). **No** inventar tokens de paleta de la familia `--color-*`: verificado con `grep -n -- "--color-" frontend/src/theme.css`, que devuelve **4** líneas (el v2 decía 3) y **ninguna es un color**: `:55` es un comentario, `:163` y `:243` definen `--color-scheme` (`dark`/`light`) y `:279` lo consume (`color-scheme: var(--color-scheme);`). Cualquier `--color-danger`, `--color-border`, etc. resuelve a vacío y deja el badge invisible.
3. `Stacky Agents/backend/api/incident_inbox.py` — agregar al payload de `/items` (junto a `untyped_count`, `:174`) una key **aditiva**.

   **C6 — el v1 lo calculaba mal y su propia justificación era falsa.** El v1 escribía `sum(1 for i in items ...)` y decía que servía "para que el conteo sea correcto aun cuando la lista venga truncada por `MAX_ITEMS`" — pero `items` **es** la lista ya truncada (`rows = rows[:MAX_ITEMS]`, **`:158`**, no `:159`), así que no arreglaba nada. Además no tenía ni consumidor ni test. La versión correcta es una agregación real, **dentro** del `with session_scope()` y **al lado de los counts que ya existen** (`:131-135`), reusando el `incident_q` y el `state_expr` ya construidos:
   ```python
        # Plan 270 F5 — divergencia EXACTA por agregación (no depende del LIMIT).
        # Misma regla de dos condiciones que isDiverged() en el .ts.
        diverged_count = incident_q.filter(
            Ticket.stacky_status == "completed"
        ).filter(~state_expr.in_(closed_norm)).count()
   ```
   Es **una** `COUNT(*)` más sobre una query ya filtrada, sin traer filas: costo despreciable y correcto con truncado. Va en la respuesta como `"diverged_count": diverged_count,`.

   **Consumidor real (si no, es código muerto):** el chip llama `resolveDivergenceCount(dto?.diverged_count, visible)` y formatea con `formatDivergenceCount(...)` — el valor del servidor manda, y el cálculo local es el fallback para un backend viejo. Así la key **tiene** consumidor **y existe la función que la puede recibir** (C4).

   **Test que lo fija (nuevo, en `test_plan270_state_writeback.py`, caso 12):** sembrar 3 tickets `completed` con `ado_state="Active"` y 2 `completed` con `ado_state="Done"` ⇒ `GET /api/incident-inbox/items?scope=all` devuelve `diverged_count == 3`. Sin este test la key vuelve a quedar sin cobertura (era el agujero de R5 en el v1).

**Gate del badge:** `divergenciaVisible = resolveDivergenceBadgeEnabled(statusQ.data)`, resuelto de la respuesta de `/api/incident-inbox/status`, agregando una key aditiva `divergence_badge_enabled` en el `jsonify` de `incident_inbox_status` — que va de **`:65` a `:81`**, con `actions_enabled` en **`:76`**. **Estricto a `true`**, igual que `resolveInboxActionsEnabled` (`incidentInboxActionsModel.ts:31-35`, comparación en `:34`): un backend viejo que no manda la key deja el badge oculto y la página sigue funcionando.

> **C6 (v3) — ojo con este anclaje: el v2 lo ROMPIÓ "corrigiéndolo".** El v1 decía `:65-81` y `:76`, que es **exactamente lo correcto**; el v2 lo "arregló" a `:66-82`/`:77` y lo dejó desfasado en 1. Verificado con `grep -n "return jsonify({" api/incident_inbox.py` ⇒ `:65`, y `grep -n "actions_enabled" api/incident_inbox.py` ⇒ `:20` (el helper `_actions_enabled`) y **`:76`** (la key en el payload). Moraleja operativa para quien implemente: **los anclajes que una revisión "corrige" son los menos verificados del documento** — re-chequealos con `grep -n` antes de escribir.

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
| 13 | **C4 — `formatDivergenceCount`:** `(0)`, `(1)`, `(7)`, `(-2)`, `(NaN)` | `""`, `"1 sin sincronizar"`, `"7 sin sincronizar"`, `""`, `""` |
| 14 | **C4 — `resolveDivergenceCount` da precedencia al servidor:** `(9, listaCon3Divergentes)` y `(undefined, listaCon3Divergentes)` y `(null, ...)` y `(0, listaCon3Divergentes)` | `9`, `3`, `3`, y **`0`** — un `0` explícito del servidor **manda** sobre el conteo local (por eso la guarda es `typeof === "number"` y no `??`, que también dejaría pasar el 0 pero no un `NaN`) |
| 15 | **C4 — la key del backend LLEGA al texto (el test que mata el código muerto):** `formatDivergenceCount(resolveDivergenceCount(dto.diverged_count, visible))` con `dto.diverged_count = 4` y una `visible` de 3 divergentes | `"4 sin sincronizar"` — o sea el número del servidor, **no** el local. Si alguien vuelve a cablear el chip contra `divergenceSummary(visible)`, este test se pone rojo |

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

**Criterio de aceptación (BINARIO):** los **15** tests de vitest pasan (12 originales + los 3 de C4), `npx tsc --noEmit` sale limpio, y el ratchet de deuda de UI sigue verde. **(F7 le agrega 3 más ⇒ el archivo termina con 18.)**

> **Sobre el ratchet de UI — alcance REAL, verificado leyendo `src/__tests__/uiDebtRatchet.test.ts`:** no es "cero HEX en todo `.module.css`", es un **ratchet por archivo** contra `uiDebtBaseline.json`. Un archivo **que no figura en el baseline tiene presupuesto 0** — y `IncidentInboxPage.module.css` **no figura**, así que su cupo de HEX es efectivamente **0**. El cero absoluto (`forcedZero`) aplica sólo a `components/ui/`, `components/shell/` y a los diálogos nativos. Conclusión práctica sin cambios: **en el `.module.css` de F5, cero HEX y cero `style={{}}` en el `.tsx`** — pero ahora se sabe *por qué*, y no se va a intentar "regenerar el baseline" (que además rechaza el regen si algún archivo subió).
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

**Objetivo (1 frase):** convertir el Principio 4 de una promesa de prosa en un **gate binario sobre `api/tickets.py`** — el archivo que este plan edita — congelando por AST qué funciones de ese archivo escriben estado y cuántas veces, para que **nadie agregue una séptima** sin que la suite se ponga roja.

**Por qué esta fase existe (y por qué el v1 la necesitaba).** El v1 llamaba "centinela anti-fallback" al test 6 de F1 — un unit test del router. Ese test prueba que **el router** nunca devuelve `ado_client` para un ticket no-ADO; no prueba **nada** sobre el resto del repo. Con el censo de §2 C3.bis a la vista (S3..S6 siguen ahí, y `api/tickets.py` tiene **8332** líneas y una sesión paralela viva escribiendo encima), la única forma honesta de sostener el invariante es un **ratchet**: un número congelado que sólo puede bajar.

**Por qué NO es repo-wide (cambio de alcance en v3).** El v2 quería barrer `backend/api/` + `backend/harness/`. Dos problemas medidos: (a) ese barrido **excluye `backend/services/`**, que es justo donde vive **S5** (`agent_completion_internal.py:536`) — el escritor que el v2 no censó, o sea el ratchet tenía un punto ciego exactamente donde estaba el agujero; (b) **el plan 271 ya implementa el censo repo-wide por AST** en `tests/test_plan271_censo_escritores.py`, congelando las 9 entradas de `backend/` entero. Dos ratchets barriendo el mismo árbol con reglas distintas se contradicen y terminan apagándose el uno al otro. **Decisión: el 270 congela `api/tickets.py` (lo que edita); el 271 congela `backend/` (lo que audita).** Sin solape de archivos de test, sin solape de alcance. Ver §"Frontera con el plan 271".

Es el mismo mecanismo que el repo ya usa para la deuda de UI (`frontend/src/__tests__/uiDebtRatchet.test.ts`) y para la lista de tests del arnés (`run_harness_tests.sh:8`: *"La lista HARNESS_TEST_FILES es un RATCHET: solo crece"*). **Se reusa el patrón, no se inventa uno.**

**Archivo a CREAR:** `Stacky Agents/backend/tests/test_plan270_state_write_ratchet.py` (**no toca DB, no toca red**: lee archivos con `pathlib` y cuenta con `re`).

**Símbolos EXACTOS:**

**C2 (v3) — el ratchet del v2 NACÍA ROJO, y por regex.** Medido: `grep -cE "provider\.update_item_state\(" harness/task_states.py` devuelve **2**, no 1 — porque el regex también matchea el **docstring** de `:158` (*"Aplica via provider.update_item_state(str(ado_id), target)"*). El v2 congelaba **1** ⇒ el test fallaba el día 1, y la única forma de "arreglarlo" era subir el número, que es exactamente lo que un ratchet prohíbe. **La lección no es corregir el número: es que contar código con regex sobre texto cuenta comentarios y docstrings.** El ratchet de v3 cuenta **por AST**, igual que el censo de §2 C3.bis.

```python
"""Plan 270 F6 — Ratchet del censo de escrituras de estado del tracker.

CUENTA POR AST, NO POR REGEX (C2). El v2 contaba con expresiones regulares y
nacia rojo: el patron matcheaba el DOCSTRING de harness/task_states.py:158.
Un ast.Call sobre un ast.Attribute no puede confundir prosa con codigo.

ALCANCE DELIBERADAMENTE ACOTADO A LO QUE ESTE PLAN POSEE (v3): api/tickets.py.
El censo REPO-WIDE (backend/ entero, 6 sitios) es del plan 271, que ya lo
implementa en tests/test_plan271_censo_escritores.py. Dos ratchets barriendo el
mismo arbol con reglas distintas se pisan y se apagan mutuamente; ver la
seccion "Frontera con el plan 271".

NO se arregla subiendo el numero. Se arregla enrutando el sitio nuevo por
services.tracker_write_router, o agregando un carve-out al plan y bajandolo.
"""
import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent  # .../backend
TARGET_METHODS = frozenset({"update_item_state", "update_work_item_state"})

# Escrituras de estado que TODAVIA viven en api/tickets.py, por funcion.
# Formato: {nombre_de_funcion: (cantidad_esperada, por_que_sigue_ahi)}
FROZEN_TICKETS_STATE_WRITES: dict[str, tuple[int, str]] = {
    # S1/S2: quedan las DOS entradas de cada uno (provider + cliente ADO), pero
    # ya detras de la rama `else` de rollback, que solo corre con la flag OFF.
    "finish_work": (2, "S1 - rama else de rollback (flag OFF), plan 270 F3"),
    "set_stacky_status_by_ado": (2, "S2 - rama else de rollback (flag OFF), plan 270 F3"),
    # S3: carve-out, eje del plan 70. Este plan NO lo toca.
    "create_child_task": (2, "S3 - estado inicial de Task nueva, eje plan 70"),
}


def _writes_by_function(rel: str) -> dict[str, int]:
    """{nombre_funcion: cantidad de llamadas a los metodos de escritura}."""
    tree = ast.parse((BACKEND / rel).read_text(encoding="utf-8", errors="replace"))
    fns = [n for n in ast.walk(tree)
           if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    out: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
           and node.func.attr in TARGET_METHODS:
            owner = max(
                (f for f in fns
                 if f.lineno <= node.lineno <= (f.end_lineno or f.lineno)),
                key=lambda f: f.lineno, default=None,
            )
            name = owner.name if owner else "<module>"
            out[name] = out.get(name, 0) + 1
    return out
```

> **De dónde salen los números — MEDIDOS con el censo AST de §2 C3.bis en `d234021e`, no estimados.** Hoy, **antes** del plan: `finish_work` **2** (`:2078`, `:2080`), `set_stacky_status_by_ado` **2** (`:1490`, `:1492`), `create_child_task` **2** (`:4779`, `:4781`). **Después** del plan los números **no cambian**: F3 no borra las ramas históricas, las mete bajo el `else` del rollback. Por eso el ratchet se puede escribir **antes** de F3 y sigue verde después — y por eso F6 dejó de ser "la última fase obligada" (ver §7).

**Comando para re-medir antes de congelar (obligatorio: hay una sesión paralela viva moviendo `api/tickets.py`):**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'tests'); from test_plan270_state_write_ratchet import _writes_by_function; print(_writes_by_function('api/tickets.py'))"
```
Salida esperada hoy: `{'set_stacky_status_by_ado': 2, 'finish_work': 2, 'create_child_task': 2}`. Si difiere, **se ajusta el número Y se documenta acá por qué**, nunca en silencio.

**Tests — 4 casos:**

| # | Caso | Aserción |
|---|---|---|
| 1 | Por cada entrada de `FROZEN_TICKETS_STATE_WRITES`, comparar contra `_writes_by_function("api/tickets.py")` | el conteo es **exactamente** el congelado. El mensaje de fallo nombra la función, el esperado, el encontrado **y el motivo congelado**, y dice literal: *"no subas el numero: enruta el sitio nuevo por services.tracker_write_router"* |
| 2 | **Cobertura de `api/tickets.py`:** `set(_writes_by_function("api/tickets.py"))` == `set(FROZEN_TICKETS_STATE_WRITES)` | si aparece una **función nueva** que escribe estado en ese archivo, el ratchet la caza aunque los conteos de las tres viejas no hayan cambiado. Es el caso que un ratchet de "suma total" deja pasar |
| 3 | **Anti-gaming:** `_writes_by_function("services/tracker_write_router.py")` tiene **exactamente** las llamadas del propio router (las de `write_state_for_ticket`) y `api/tickets.py` **no** contiene la cadena `api.tickets` importada desde `services/` | nadie "cumple" el ratchet moviendo el problema adentro del router ni invirtiendo la dependencia |
| 4 | **El archivo existe y parsea** | si alguien renombra o rompe `api/tickets.py`, el ratchet falla por archivo faltante / `SyntaxError`, **no** por 0 hits (un ratchet que se apaga en silencio es peor que no tenerlo) |
| 5 | **[ADICIÓN ARQUITECTO v4] Centinela del residuo S5** — sobre `services/agent_completion_internal.py::_attempt_state_change`: (a) tiene **exactamente 1** llamada a `update_work_item_state`, y (b) el cuerpo de la función **no** menciona `get_tracker_provider`, `tracker_type` ni `_provider_for_ticket` | el asterisco del KPI (§1) deja de ser una promesa de papel. Mensaje de fallo literal: *"S5 cambió: alguien (probablemente el plan 271) enrutó `_attempt_state_change` por provider. El residuo declarado en el asterisco del KPI del plan 270 YA NO EXISTE: actualizá §1 y re-medí la divergencia. NO subas el número ni borres este test."* |

> **[ADICIÓN ARQUITECTO v4] Por qué este caso 5 y por qué acá.** El KPI de este plan lleva un asterisco honesto: **S5 escribe siempre en ADO y este plan no lo toca** porque es del **271** — que está **RECHAZADO dos veces y sin aprobar**, o sea que el residuo puede quedarse vivo por tiempo indefinido. Hoy **nada avisa** si ese residuo desaparece (el 271 aterriza) o si alguien lo mueve: el asterisco seguiría escrito, mintiendo en silencio. Eso es exactamente el pecado que este plan combate — *un tablero que afirma algo que ya no es cierto*. El centinela lo convierte en **señal mecánica y binaria**, en el archivo de ratchet que ya existe, sin fase nueva.
>
> **Medido HOY, no supuesto — nace VERDE:** `_attempt_state_change` tiene **1** llamada (`:536`) y **0** referencias a `get_tracker_provider` / `tracker_type` / `_provider_for_ticket`.
>
> **No viola la frontera con el 271:** el centinela **lee** `agent_completion_internal.py` con `ast.parse`, **no lo edita**. El DoD sigue exigiendo que `git diff --stat` no toque ese archivo. Cuando el 271 lo enrute, este test se pone rojo **a propósito** y el mensaje dice qué actualizar — es un handoff explícito entre planes, no una colisión.
>
> **Costo:** cero. Sin flag (es un test), sin UI, sin config, sin red, sin DB. **3 runtimes:** idéntico — sólo `pathlib` + `ast`, ningún runtime participa en la ejecución. **Trabajo del operador:** ninguno.

**Comando:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.\.venv\Scripts\python.exe -m pytest tests\test_plan270_state_write_ratchet.py -q
```

**Criterio de aceptación (BINARIO):** los **5** tests pasan (4 del v2 + el centinela del residuo S5 de la [ADICIÓN ARQUITECTO v4]); el archivo está en los 2 arneses; y el mensaje de fallo del test 1 contiene la cadena literal `tracker_write_router` (para que el modelo menor que lo rompa lea la instrucción de cómo arreglarlo, no sólo el número).

**Colisión con sus propios gates — verificada CORRIENDO (v3).** El ratchet cuenta **`ast.Call` sobre `ast.Attribute`** en **`api/tickets.py`**. Tres consecuencias, todas comprobadas:
1. **Este documento no lo puede disparar.** Es un `.md` en `docs/`; el ratchet sólo abre `backend/api/tickets.py`.
2. **Los comentarios y docstrings ya no cuentan.** Ése era el bug del v2 (C2): con regex, la prosa de `harness/task_states.py:158` sumaba 1. Con AST, `_writes_by_function("harness/task_states.py")` devuelve `{'_safe_transition': 2}` — las dos llamadas **reales** (`:173`, `:175`), cero docstrings. Verificado ejecutando.
3. **Los diffs de F3 no mueven el conteo.** F3 no borra las llamadas históricas: las mete bajo el `else` del rollback, así que siguen siendo 2 `ast.Call` por función. Y las llamadas nuevas viven en `services/tracker_write_router.py` (`writer.handle.update_work_item_state(...)`), archivo que el ratchet **no** mira en el test 1 y que el test 3 audita aparte. Por eso el conteo congelado es idéntico antes y después del plan — y por eso F6 se puede escribir en cualquier momento.

**Flag que la protege:** **ninguna.** Es un test; los tests no se gatean. Agregar una flag acá sería una forma de apagarlo.
**Impacto por runtime:** **nulo, y esta vez verificado y no afirmado:** el test lee archivos con `pathlib.Path.read_text()` y los parsea con `ast.parse`. No importa `services.agent_runner`, no construye ningún cliente, no lee `LLM_BACKEND` ni `runtime`. Codex CLI / Claude Code CLI / GitHub Copilot Pro: **idéntico, porque ninguno participa en la ejecución del test**. Fallback: N/A.
**Paridad ADO↔GitLab:** el ratchet es **agnóstico de tracker**: cuenta `update_work_item_state` (ADO) **y** `update_item_state` (puerto/GitLab) con la misma regla. Ninguno de los dos puede crecer sin ruido.
**Trabajo del operador: ninguno.** No hay UI, no hay config, no hay flag.

---

### F7 — [ADICIÓN ARQUITECTO v3] Dry-run de destino: el operador ve a QUÉ sistema va a escribir **antes** de confirmar

**Objetivo (1 frase):** enriquecer la respuesta del **dry-run que el diálogo de cierre ya dispara** con el destino resuelto por F0+F1, para que el operador lea *"va a GitLab, va a quedar `accepted`, cerrada"* **antes** de apretar Confirmar — sin escribir absolutamente nada.

**Por qué esta fase existe.** Este plan arregla que el cierre **llegue bien**. Pero el operador sigue apretando "Cerrar" **a ciegas**: el diálogo no le dice a qué sistema va, ni en qué estado nativo va a quedar, ni si el destino está disponible. Hoy se entera **después**, por un error. Ése es exactamente el patrón que lo expulsó del tablero: *actuar y descubrir después que no era lo que creía*. F7 mueve la verdad **antes** de la decisión, que es la definición operativa de amplificar al operador (Principio 5).

**Por qué es casi gratis — el seam ya existe y está VIVO (verificado):**
- `finish_work` **ya tiene** dry-run: `dry_run = bool(body.get("dry_run", False))` (`api/tickets.py:1801`) y un early-return propio en **`:1934-1944`** que devuelve `{"ok", "dry_run", "ticket_id", "ado_id", "cancel_result", "preconditions", "actions": [], "current_status", "operator"}`.
- El frontend **ya lo llama solo**: `FinishWorkButton.tsx:49` `dryRunMutation`, `:55` `dry_run: true`, y `:80-81` lo dispara **al abrir el diálogo**, antes de cualquier confirmación. `:67` es el `dry_run: false` real.
⇒ **Cero endpoints nuevos, cero llamadas nuevas, cero flags nuevas.** F7 es una key aditiva en una respuesta que ya viaja.

**Archivo a EDITAR (1):** `Stacky Agents/backend/api/tickets.py`, **una sola inserción**, dentro del `if dry_run:` de `:1934`, antes del `return jsonify({...})`:

```python
    # ── Plan 270 F7 — destino resuelto, SIN escribir ──────────────────────────
    # Reusa F0 (vocabulario) y F1 (destino) en modo consulta. Nunca escribe:
    # write_state_for_ticket NO se llama acá.
    _destino = {"resolved": False, "reason": "no_target_state"}
    if target_ado_state and ado_id is not None:
        from services import tracker_write_router as _twr
        _destino = _twr.preview_state_write(
            ticket=ticket, requested_state=target_ado_state,
        )
```
y agregar `"destination": _destino,` como key **aditiva** del `jsonify` del dry-run.

**Símbolo NUEVO en `services/tracker_write_router.py`:**

```python
def preview_state_write(*, ticket, requested_state: str) -> dict:
    """Resuelve destino + vocabulario SIN escribir. Nunca levanta.

    Es write_state_for_ticket() menos la escritura: mismas dos llamadas
    (resolve_state_writer, resolve_close_target), mismo orden, cero I/O de
    escritura. Si algo falla, lo devuelve declarado en vez de propagarlo: el
    dry-run NUNCA puede tumbar el dialogo de cierre.

    Devuelve:
      {"resolved": True,  "tracker_type": str, "native_state": str,
       "closes": bool, "reason": "ok"}
      {"resolved": False, "tracker_type": str|None, "reason": str,
       "workaround": str}
    """
```

**Contrato de la respuesta (aditivo y hacia atrás):** se **agrega** la key `destination` al payload del dry-run. **No se quita ni se renombra ninguna key existente.** Un frontend viejo que no la lea sigue funcionando idéntico.

**Casos borde:**
- Ticket ADO ⇒ `{"resolved": True, "tracker_type": "azure_devops", "native_state": "Done", "closes": True}`.
- Ticket GitLab con la flag del adapter apagada ⇒ `{"resolved": False, "reason": "...", "workaround": "..."}` con el **mismo** `workaround` que nombra la flag literal (C4). El operador lee el prerequisito **antes** de confirmar, no después de fallar.
- Estado no mapeable ⇒ `{"resolved": False, "reason": "unmappable_state:..."}`.
- `target_ado_state` nulo ⇒ `{"resolved": False, "reason": "no_target_state"}`, sin llamar al router.
- **Cualquier excepción inesperada** ⇒ `{"resolved": False, "reason": "preview_error: <tipo>"}`. **El dry-run jamás devuelve 500 por culpa de F7.**

**Frontend (opcional dentro de esta fase, y explícitamente acotado):** `FinishWorkButton.tsx` ya renderiza el resultado del dry-run; mostrar `destination` es **una línea de texto** junto a las precondiciones. **No** se agrega ningún `.tsx` nuevo, **no** se agrega CSS nuevo, **no** hay test de componente (no hay RTL/jsdom). La lógica de redacción del texto va en `frontend/src/incidents/incidentDivergence.ts` como función pura, testeada en el `.ts` existente de F5:

```ts
/** Plan 270 F7 — Texto de una linea para el dry-run. "" si no hay que decir nada. */
export function describeCloseDestination(
  d: { resolved?: boolean; tracker_type?: string | null; native_state?: string;
       closes?: boolean; reason?: string; workaround?: string } | null | undefined,
): string {
  if (!d) return "";
  if (d.resolved !== true) {
    const causa = d.reason ?? "destino sin resolver";
    return d.workaround ? `No se puede cerrar: ${causa}. ${d.workaround}` : `No se puede cerrar: ${causa}`;
  }
  const donde = d.tracker_type === "gitlab" ? "GitLab" : "Azure DevOps";
  const cierra = d.closes === true ? "queda cerrada" : "NO queda cerrada";
  return `Se escribe en ${donde} como "${d.native_state}" — ${cierra}.`;
}
```

**Tests PRIMERO — se reparten en archivos que este plan YA crea, sin agregar un séptimo:**
- Backend ⇒ **4 casos nuevos en `tests/test_plan270_write_router.py`** (pasa de 10 a **14**), porque `preview_state_write` es del router y el archivo **no toca DB**:

| # | Caso | Aserción |
|---|---|---|
| 11 | ticket ADO, `preview_state_write(ticket=t, requested_state="Done")` | `{"resolved": True, "tracker_type": "azure_devops", "native_state": "Done", "closes": True}` |
| 12 | ticket GitLab con la fábrica levantando `TrackerConfigError` | `resolved is False` y el `workaround` contiene la cadena literal `"STACKY_GITLAB_ENABLED"` |
| 13 | ticket GitLab, `requested_state="Cualquier Cosa"` | `resolved is False`, `reason` empieza con `"unmappable_state:"` |
| 14 | **Centinela de no-escritura (el corazón de F7):** los 3 casos anteriores con dobles que **cuentan** llamadas a `update_item_state` y `update_work_item_state` | **0 llamadas en total**. `preview_state_write` no escribe nunca |

- Frontend ⇒ **3 casos nuevos en `incidentDivergence.test.ts`** (pasa de 15 a **18**): resuelto-ADO, resuelto-GitLab-cierra, no-resuelto-con-workaround.

**Comandos:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.\.venv\Scripts\python.exe -m pytest tests\test_plan270_write_router.py -q
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx vitest run src/incidents/incidentDivergence.test.ts
```

**Criterio de aceptación (BINARIO):** `test_plan270_write_router.py` pasa con **14** casos; `incidentDivergence.test.ts` pasa con **18**; y el caso 14 demuestra **0** escrituras.

**Flag que la protege:** **ninguna, y es deliberado.** F7 no agrega comportamiento nuevo apagable: agrega una **key aditiva** a una respuesta que ya existe, dentro de un camino (`dry_run=True`) que **por definición no escribe**. Gatearla sería agregar una flag para poder ocultarle información al operador, que es lo contrario del Principio 5. Las 3 flags del plan siguen siendo 3.
**Justificación de que NO cae en (A) ni en (B):** (A) no hay loop, daemon, polling ni llamada a modelo — es la misma petición que el diálogo ya hace, con dos funciones puras más; (B) **no escribe nada, por construcción**, y el test 14 lo fija.
**Human-in-the-loop:** F7 es HITL en estado puro — **más** información antes de la decisión, **cero** automatización. No cierra, no confirma, no elige.
**Paridad ADO↔GitLab:** en la **misma** fase y con el **mismo** código: `preview_state_write` es `write_state_for_ticket` sin la escritura, así que los dos trackers se previsualizan por el mismo camino. Casos 11 (ADO) y 12/13 (GitLab).
**Impacto por runtime:** **nulo.** Es una petición HTTP que el operador dispara desde la UI; ningún modelo participa. Codex CLI / Claude Code CLI / GitHub Copilot Pro: idéntico. Fallback: N/A.
**Trabajo del operador: ninguno.** Aparece solo, en un diálogo que ya abría.

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
| R7 | Alguien "arregla" un test borrando un assert para pasar el gate (falso verde) | Media | Los criterios están redactados con **conteos exactos** (11, 14, 6, 10, 12, 4 en backend; 18 en vitest). Un archivo con menos tests de los declarados es un incumplimiento verificable con `pytest --collect-only -q` |
| R12 | **El implementador cree que rompió una suite que YA estaba roja** y "arregla" borrando asserts ajenos — o peor, toca `test_b2_transition_from_config.py`, que es del 271 | **Alta** (son **4** suites rojas de fábrica y dos están en archivos que este plan toca) | §"Baseline medido" declara los cuatro resultados **medidos** (`4/4`, `3/5`, `2/7`, `5 failed`) y convierte sus criterios en **deltas**. El DoD lo repite y agrega la verificación por `git diff --stat` de que los archivos del 271 no se tocaron |
| R13 | **Se implementa el 270 creyendo que deja `divergencia = 0` global, y queda el residuo de S5** (`agent_completion_internal.py:536`, que escribe siempre en ADO) | **Alta** — el v2 no lo censaba siquiera | El asterisco del KPI (§1), la fila **S5** del censo (§2 C3.bis) y la §"Frontera con el plan 271" dicen los tres que **ese motor es del 271 y este plan no lo toca**. El KPI de aceptación está acotado por escrito a los caminos (1) y (2), que son los que miden los tests 3 y 10 de F4 |
| R14 | **Los dos ratchets (270 F6 y 271 F8) se pisan** y alguien relaja uno para que pase el otro | Media | Alcances **anidados a propósito**: el del 270 mira sólo `api/tickets.py`; el del 271 mira `backend/` entero. Archivos de test distintos, misma técnica (AST). Un sitio nuevo en `api/tickets.py` pone **los dos** rojos — señal doble, nunca contradictoria. Escrito en §"Frontera con el plan 271" |
| R10 | **El invariante del Principio 4 se erosiona**: alguien agrega un quinto sitio que escribe estado con el cliente ADO y nadie se entera hasta que un cierre GitLab vuelve a escribir en ADO | **Alta** (ya pasó: son 4 sitios y el v1 sólo veía 1) | **F6 [ADICIÓN ARQUITECTO]**: ratchet de conteo congelado sobre los 3 archivos del censo, con un cuarto test que cubre el resto de `backend/api/` y `backend/harness/` para cazar un sitio en un archivo no censado |
| R11 | El operador enciende `STACKY_GITLAB_ENABLED` esperando que "ahora sí cierra" y se encuentra con otro prerequisito (token, destino por proyecto) | Media | El `workaround` de `CapabilityUnavailable` viaja hasta la UI (ver el diff del `except` de F3) y lo dice el **proveedor**, no este plan: cualquier otro prerequisito que falte va a producir su propio `TrackerConfigError` con su propio mensaje. El smoke 8b del F5 lo verifica de punta a punta contra una issue real |
| R8 | La flakiness de SQLite hace fallar F3/F4 y se interpreta como bug del plan | Alta | El plan lo declara en cada comando: **correr por archivo** y reintentar hasta 3 veces ante `database table is locked` antes de declarar fallo |
| R9 | El `.module.css` nuevo usa un token de color inexistente y el badge queda invisible | Media | El plan nombra los tokens **reales** del tema (`--danger`, `--border`, `--text-primary`, `--bg-panel`) y prohíbe explícitamente la familia `--color-*`, que **no existe** en este repo. El paso 4 del smoke manual verifica que el badge se ve |

---

## 6. Fuera de scope

Explícito, para que nadie lo agregue "de paso":

1. **Reconciliación masiva Stacky→tracker** (empujar el estado de Stacky a todas las filas divergentes de una). Es la **única** capacidad de escritura genuinamente nueva del eje ⇒ **categoría (B)**, default OFF, flag sugerida `STACKY_INCIDENT_RECONCILE_WRITEBACK_ENABLED`. ⇒ **plan 272 sugerido.**
2. **Crear `services/gitlab_sync.py`** para arreglar C4 (el auto-sync post-completación de GitLab). Es un sync masivo con breaker y coalescing: un eje propio, no una fase de este plan. El plan 270 **no lo necesita** porque F4 hace un refresco puntual y agnóstico. ⇒ **plan 273 sugerido.**

> **CORRECCIÓN DE NUMERACIÓN (I3 — v3).** El v2 sugería "plan 271" y "plan 272" para estas dos continuaciones. **El 271 YA ESTÁ TOMADO** (`271_PLAN_LA_INCIDENCIA_SE_MUEVE_AL_ESTADO_CONFIGURADO_AL_TERMINAR_EL_ANALISTA.md`, untracked, de una sesión paralela). Verificado relistando `Stacky Agents/docs/`: el máximo es **271**, el próximo libre es el **272**. Además el propio 271 **reserva el 272 para "un solo escritor de estado"**, que es un eje distinto del de estos dos ítems. **Antes de crear cualquiera de estos planes: relistá `Stacky Agents/docs/` en frío** (incluyendo untracked con `ls`, no sólo `git ls-files`) y tomá el primer número libre real. No hardcodear 272/273 desde este documento.
3. **Migrar los ~27 call sites de `api/tickets.py` al puerto** (Plan **70**, ya PROPUESTO). El 270 sólo enruta correctamente **el write de estado**.
4. **Rediseño visual de la bandeja.** El 270 agrega un badge y un chip; no reordena, no re-maqueta.
5. **Sincronizar comentarios/adjuntos/asignaciones** ADO↔GitLab. Sólo se trata el **estado**.
6. **Estados deterministas por tipo de agente** (Plan **79**) y la **matriz** `(work_item_type × agent_type)` (Plan **208**). El 270 no decide *qué* estado poner; hace que el estado que el operador eligió llegue bien y se refleje.
7. **Webhooks del tracker hacia Stacky** (que ADO/GitLab avisen al cambiar). Invertiría el modelo de pull y exige exponer un endpoint entrante. ⇒ eje futuro.
8. **Jira y Mantis.** `resolve_state_writer` los rechaza con `CapabilityUnavailable` declarada (test 5 de F1); ampliarlos es otro plan.
9. **Enrutar S3 y S4** (creación de Tasks y `_apply_task_state` del Plan 79). Censados en §2 C3.bis, con carve-out escrito y **congelados por el ratchet de F6**. No se tocan acá porque son ejes ajenos (Plan 70 y Plan 79) y S4 está inerte con los defaults de fábrica.
10. **Promover `STACKY_GITLAB_ENABLED` a ON.** Evaluada por escrito en §1 y **diferida al plan 259**, que es su dueño. Este plan la declara, la nombra en el `workaround` y la verifica en el smoke, pero no la flipea: es el master switch de un adapter entero con superficie de escritura que este plan no analizó.

### Huella de regresión (§ error_fingerprints)

`Stacky Agents/docs/sistema/error_fingerprints.json` es un catálogo de **patrones de log** (`schema_version: 1`, key raíz `fingerprints`, hoy **42** entradas). De las clases de error que toca este plan, **sólo una tiene firma en log** y por eso es la única que se registra — no se inventan `log_pattern` para bugs silenciosos.

**C3 (v3) — el v2 rompía el catálogo entero de DOS formas, ambas medidas corriendo:**

1. **JSON inválido.** El v2 escribía el patrón como `No module named 'services\.gitlab_sync'`. Copiado literal a un `.json`, `\.` **no es un escape válido de JSON**: `json.loads` levanta `JSONDecodeError: Invalid \escape`. Eso no rompe una huella: **rompe el archivo completo**, y con él `test_json_valido` y todo consumidor del catálogo. En JSON hay que escribir **`\\.`**.
2. **Campo obligatorio faltante.** El v2 enumeraba los campos como `id, title, class, status, log_pattern, log_guarded, killed_by, killed_commit, date_resolved, guard_test`. La lista real de obligatorios está en `tests/test_error_fingerprints_catalog.py:18`:
   `_REQUIRED = ("id", "title", "class", "status", "log_pattern", "log_guarded", "killed_by", "guard_test", "self_test")`
   ⇒ el v2 **omitía `self_test`** (obligatorio) y presentaba como contrato dos que **no** lo son (`killed_commit`, `date_resolved`). Y `test_self_test_coherente` (`:53-59`) exige que `self_test.matches` **matcheen** el patrón y `self_test.clean` **no**.
3. Además `_STATUS_ENUM` (`:17`) es `{"resolved", "open", "by_design"}` ⇒ el `status: "open"` del plan **es válido**. Eso el v2 lo tenía bien.

**Entrada a agregar — objeto JSON LITERAL, copiar tal cual dentro del array `fingerprints`:**

```json
    {
      "id": "PLAN270-GITLAB-SYNC-AUSENTE",
      "title": "El auto-sync post-completacion de GitLab apunta a un modulo inexistente",
      "class": "import-error",
      "status": "open",
      "log_pattern": "No module named 'services\\.gitlab_sync'",
      "log_guarded": false,
      "killed_by": "",
      "guard_test": "",
      "self_test": {
        "matches": [
          "completion_sync: sync de MiProy fallo (best-effort): No module named 'services.gitlab_sync'"
        ],
        "clean": [
          "completion_sync: sync de MiProy fallo (best-effort): No module named 'services.jira_sync'",
          "completion_sync: sync de MiProy ok"
        ]
      },
      "note": "Documentada, NO guardada. completion_sync.py:111 despacha a services.<tracker>_sync y services/gitlab_sync.py no existe (0 hits en backend/). El plan 270 NO lo mata: su F4 hace un refresco puntual y agnostico que no depende de este modulo. Dueno: el plan sugerido en la seccion 6.2."
    }
```

- **`id` en SCREAMING-KEBAB con prefijo de plan** (ej. `PLAN239-OUTLET-EN-BLANCO`). **Corrección D3 (v4): el catálogo NO tiene una convención única, y decir lo contrario era falso.** Censo medido de los 42 ids: **32 `snake_case`** (`pipeline_status_404`, `ansi_in_file_log`, `muted_500_untyped`, `epic_task_phantom_success`, …), **7 `SCREAMING-KEBAB`**, **3 `kebab-minúscula`**. O sea que `gitlab_sync_module_missing` (la propuesta del v2) **sí** habría seguido el patrón mayoritario. Se elige igual `PLAN270-GITLAB-SYNC-AUSENTE` por una razón real y acotada: **el prefijo de plan hace rastreable la huella hasta el documento que la registró**, que es lo que uno quiere cuando la huella reaparece meses después. **No "normalices" ids ajenos apoyándote en esta línea: las 32 `snake_case` están bien como están y tocarlas es alcance de otro plan.**
- **`killed_by: ""`** (no una frase tipo *"plan 272 sugerido"*): la huella está **abierta**, nadie la mató. Poner un plan que no existe en `killed_by` con `status: "open"` es contradictorio.
- El `self_test.clean` incluye **`services.jira_sync`** a propósito: prueba que el patrón está anclado a `gitlab_sync` y no matchea cualquier `No module named`.

**Verificación binaria (obligatoria — es el paso que el v2 no tenía):**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.\.venv\Scripts\python.exe -m pytest tests\test_error_fingerprints_catalog.py -q
```
**Criterio (delta, ver §"Baseline medido"):** el resultado debe seguir siendo **exactamente `3 failed, 5 passed`**, y **ninguna** de las 3 fallas puede nombrar `PLAN270-GITLAB-SYNC-AUSENTE`. Si `test_json_valido` (que hoy **pasa**) se pone rojo, rompiste el JSON — casi seguro por el `\\.`.

**Lo que NO se registra, y por qué:** el `reopen` de C2 y el mis-routing de C3 **son silenciosos: no dejan ninguna línea de log.** El `reopen` es un `PUT` exitoso (200) y el mis-routing termina en un `logger.exception` genérico sin firma estable. Inventarles un `log_pattern` sería meter ruido en un catálogo cuyo contrato es "el smoke alarma si el patrón REAPARECE". **Sus guardias son tests, no huellas de log:** el test 5 de F2 (anti-reopen) y el test 6 de F1 + F6 (anti-fallback). Queda dicho acá para que nadie lo interprete como un olvido.

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
| **Pata (de una flag)** | Cada uno de los **7** lugares que hay que tocar para dar de alta una flag sin poner un meta-test en rojo. Ver §3. (El v2 decía **6** acá y **7** en todo el resto del documento: contradicción interna corregida en v3) |
| **Fail-open** | Ante un error de red, degradar devolviendo un resultado negativo declarado en vez de levantar y tumbar la operación |
| **Delta (de una suite roja)** | Criterio de aceptación sobre una suite que ya está roja de fábrica: no se exige verde, se exige **mismo número de fallas y ninguna que nombre un símbolo de este plan**. Ver §"Baseline medido" |
| **Motor de estado** | Cada uno de los **6** sitios del censo de §2 C3.bis que escriben el estado del tracker. El 270 posee S1 y S2; S5 es del 271 |

### Orden de implementación (lista numerada, estricto)

1. **F0** — `services/close_intent.py` + `tests/test_plan270_close_intent.py` (**11** casos, incluido el centinela de aridad del test 11 que evita el bug C1). Registrar el test en los **dos** arneses. Correr y ver verde.
2. **F1** — Alta de la flag `STACKY_TRACKER_STATE_WRITE_ROUTING_ENABLED` en las **7 patas** (ojo con el límite de 240 chars de `PlainHelp`, pata 6). Luego `services/tracker_write_router.py` (sin `write_state_for_ticket` todavía) + `tests/test_plan270_write_router.py` (**10** casos). El cliente ADO se construye con `project_context.build_ado_client`, **nunca** importando `api.tickets` (C5). Registrar en los dos arneses. Verde.
3. **F2** — Editar `services/gitlab_provider.py` (`update_item_state` + `_unknown_state_guard_enabled` **con `config.config`**, C9) + `tests/test_plan270_gitlab_close.py` (**6** casos). Registrar. Verde. **Correr el centinela textual** que prueba que la forma vieja desapareció.
4. **F3** — Agregar `write_state_for_ticket` al router **con el desempaquetado literal de `resolve_closed_states`** (C1); editar los **dos** bloques de `api/tickets.py` (S1 `:2073-2094` y S2 `:1486-1508`) y el `except` de S1 para concatenar el `workaround`; + `tests/test_plan270_finish_work_state.py` (**10** casos). Registrar. Correr **por archivo**. Verde.
5. **F4** — Alta de la flag `STACKY_TICKET_STATE_WRITEBACK_ENABLED` (7 patas). `services/ticket_state_writeback.py` (key literal `"state"`, `session_scope` desde `db.py:485`) + las **dos** inserciones `4.bis` en `api/tickets.py` + `tests/test_plan270_state_writeback.py` (**12** casos, contando el 12 que fija `diverged_count`). Registrar. Correr **por archivo**. Verde (los tests 3 y 10 son el KPI en los dos caminos).
6. **F5** — Alta de la flag `STACKY_INCIDENT_DIVERGENCE_BADGE_ENABLED` (7 patas). `frontend/src/incidents/incidentDivergence.ts` + su `.test.ts` (**15** casos — D4 v4: acá decía "12", que es el número del v2 **antes** de los 3 casos de C4; el criterio binario de F5 pide **15** y el paso 7 suma 3 para llegar a 18, aritmética que sólo cierra desde 15); ampliar `incidentInboxModel.ts` con `divergence_badge_enabled` y `diverged_count`; luego las keys del backend (`diverged_count` **por agregación**, `divergence_badge_enabled`); luego `IncidentInboxPage.tsx` (memo `mostrados`, `visibleIds` sobre `mostrados`, chip con `Button`) + `.module.css`. Vitest verde, `tsc --noEmit` limpio, ratchet de UI verde, **smoke manual de 9 pasos hecho** (incluido el 8b de GitLab).
7. **F7 [ADICIÓN ARQUITECTO v3]** — `preview_state_write` en el router + la inserción en el `if dry_run:` de `api/tickets.py:1934` + `describeCloseDestination` en el `.ts` de F5. Los tests **no crean archivo nuevo**: 4 casos más en `test_plan270_write_router.py` (⇒ **14**) y 3 más en `incidentDivergence.test.ts` (⇒ **18**). Verde.
8. **F6 [ADICIÓN ARQUITECTO v2 + v4]** — **Re-medir** con el comando AST declarado en la fase, escribir `tests/test_plan270_state_write_ratchet.py` con esos números (**5** casos: los 4 del v2 + el **centinela del residuo S5** de la [ADICIÓN ARQUITECTO v4]) y **verlo fallar** subiendo a mano un conteo antes de dejarlo verde (si nunca lo viste rojo, no sabés si mide algo). Registrar en los dos arneses.
   > **Ya NO es obligatorio dejarla última (cambio en v3).** El v2 la ponía al final porque congelaba conteos que F3 supuestamente cambiaba. Medido: **F3 no cambia los conteos** — no borra las llamadas históricas, las mueve bajo el `else` del rollback, y siguen siendo 2 `ast.Call` por función. El ratchet da `{'finish_work': 2, 'set_stacky_status_by_ado': 2, 'create_child_task': 2}` **antes y después**. Se deja acá por orden narrativo, no por dependencia. **Ya no hay ninguna excepción al principio de "ninguna fase depende de una posterior".**
9. **Cierre** — Regenerar `harness_defaults.env` con `deployment/export_harness_defaults.py` (**los dos destinos**, `--out` por corrida). Correr los **6** archivos de test del plan, **uno por uno**. Verificar que los 6 estén en `run_harness_tests.sh` **y** en `$HarnessTestFiles` de `run_harness_tests.ps1`. Agregar la entrada `PLAN270-GITLAB-SYNC-AUSENTE` a `docs/sistema/error_fingerprints.json` **con el objeto JSON literal de §6** (incluye `self_test` y el `\\.` escapado) y correr `test_error_fingerprints_catalog.py` verificando el **delta cero**.

### Definition of Done global

El plan 270 está terminado cuando **todo** lo siguiente es cierto y verificable:

- [ ] Los **6** archivos de test nuevos existen, están registrados en **ambos** arneses, y pasan corridos **por archivo** con `.\.venv\Scripts\python.exe -m pytest tests\<archivo>.py -q`:
      `test_plan270_close_intent.py` (11) · `test_plan270_write_router.py` (**14**, incluye los 4 de F7) · `test_plan270_gitlab_close.py` (6) · `test_plan270_finish_work_state.py` (10) · `test_plan270_state_writeback.py` (12) · `test_plan270_state_write_ratchet.py` (**5**, incluye el centinela del residuo S5 de la [ADICIÓN ARQUITECTO v4]). **Total: 58 tests.**
- [ ] `incidentDivergence.test.ts` pasa (**18** casos: 12 de F5 + 3 de C4 + 3 de F7) y `npx tsc --noEmit` sale limpio.
- [ ] Las **3** flags nuevas están dadas de alta en sus **7 patas** cada una, las 3 con `default=True`, los **3 textos de `PlainHelp` son los LITERALES de §3** (cumplen las **6** reglas del contrato, no sólo el límite de 240), y `harness_defaults.env` fue **regenerado con el generador** en sus **dos** destinos (no editado a mano).
- [ ] **Delta cero sobre las 4 suites rojas de fábrica** (§"Baseline medido"): `test_harness_flags_help.py` sigue en **4 failed, 4 passed** · `test_error_fingerprints_catalog.py` sigue en **3 failed, 5 passed** · `test_error_fingerprints_scan.py` sigue en **2 failed, 7 passed** · `test_b2_transition_from_config.py` sigue en **5 failed** y **nadie lo tocó** (es del 271). **Y ninguna falla de ninguna de las cuatro nombra un símbolo de este plan.**
- [ ] **F7 no escribe:** el caso 14 de `test_plan270_write_router.py` demuestra **0** llamadas a `update_item_state`/`update_work_item_state` en los tres escenarios de `preview_state_write`.
- [ ] **El censo de §2 C3.bis se re-corrió** con el script AST y sigue dando **`ENTRADAS = 10 | SITIOS = 6`**. Si da otra cosa, hay un motor nuevo: se censa **antes** de seguir.
- [ ] **La frontera con el 271 se respetó:** `git diff --stat` **no** toca `services/agent_completion_internal.py`, `services/completion_state.py`, `harness/task_states.py`, `api/executions.py` ni `tests/test_b2_transition_from_config.py`.
- [ ] **Centinela anti-reopen:** `Select-String -Path services\gitlab_provider.py -Pattern 'state_map\.get\(logical_state, \{\}\)'` devuelve **0 líneas**.
- [ ] **Centinela anti-fallback (unit):** el test 6 de `test_plan270_write_router.py` demuestra que ningún `tracker_type` no-ADO resuelve a `kind == "ado_client"`.
- [ ] **Centinela anti-fallback sobre `api/tickets.py` — F6 [ADICIÓN ARQUITECTO]:** `test_plan270_state_write_ratchet.py` congela **por AST** las 3 funciones de `api/tickets.py` que escriben estado (2 llamadas cada una) y su test 2 caza una **función nueva** en ese archivo. **Se vio fallar al menos una vez** antes de dejarlo verde. El censo **repo-wide** es del 271 (`test_plan271_censo_escritores.py`) y **no se duplica acá**. **[ADICIÓN ARQUITECTO v4]** su **caso 5** congela además el **residuo S5** (`agent_completion_internal.py::_attempt_state_change`: 1 llamada, 0 referencias a provider/tracker) — el archivo se **lee** con `ast.parse`, **nunca** se edita, así que la frontera con el 271 se mantiene.
- [ ] **Centinela anti-acoplamiento (C5):** `Select-String -Path services\tracker_write_router.py,services\ticket_state_writeback.py -Pattern 'api\.tickets|from api'` devuelve **0 líneas**.
- [ ] **KPI verificado en los DOS caminos (C3):** el test 3 de `test_plan270_state_writeback.py` (manual, `finish-work`) **y** el test 10 (automático, `PATCH /api/tickets/by-ado/<ado_id>/stacky-status`) prueban que el ítem **desaparece** de `/api/incident-inbox/items?scope=open`.
- [ ] **Bug de integración C1 fijado:** el test 11 de `test_plan270_close_intent.py` y el test 7 de `test_plan270_finish_work_state.py` prueban que `resolve_closed_states` se desempaqueta y que un cierre GitLab con `"Done"` llega como `"accepted"`.
- [ ] **Paridad ADO byte-idéntica en los dos sitios:** el test 1 (S1) y el test 10 (S2) de `test_plan270_finish_work_state.py` prueban que un ticket ADO recibe **exactamente** el mismo argumento de estado que antes del plan.
- [ ] **Paridad GitLab efectiva en los dos sitios:** los tests 2 (S1) y 8 (S2) prueban que un ticket GitLab se cierra vía su provider y que el cliente ADO **no se instancia**.
- [ ] **Prerequisito GitLab declarado y accionable (C4):** el test 8 de `test_plan270_write_router.py` prueba que el `workaround` contiene `"STACKY_GITLAB_ENABLED"`, y el smoke 8a/8b de F5 lo verifica contra una issue real (apagada ⇒ error que nombra la flag y **nada** escrito; encendida ⇒ issue **cerrada**, no reabierta).
- [ ] **Rollback probado en los dos sitios:** los tests 4 (S1) y 9 (S2) de `test_plan270_finish_work_state.py` y el 4 de `test_plan270_gitlab_close.py` prueban que con las flags OFF el comportamiento vuelve al histórico.
- [ ] **`diverged_count` tiene consumidor Y test (C6 / D1 v4):** el caso 12 de `test_plan270_state_writeback.py` fija el valor del backend por agregación, y el chip lo consume **exactamente así**, que es lo que dice el bloque `tsx` de F5:
      ```ts
      const divergentes = resolveDivergenceCount(dto?.diverged_count, visible);
      const textoChip   = formatDivergenceCount(divergentes);
      ```
      **PROHIBIDO escribirlo como `dto?.diverged_count ?? countDiverged(visible)`** (así lo pedía el DoD hasta el v3, y estaba mal): `??` sólo cae ante `null`/`undefined`, así que un `NaN`/`Infinity` del servidor **atraviesa** y `formatDivergenceCount` devuelve `""` ⇒ **el chip desaparece y la divergencia se vuelve invisible**, que es exactamente el bug que este plan existe para matar. `resolveDivergenceCount` filtra con `Number.isFinite` y cae al conteo local. Es además **el único lugar donde se decide la precedencia** (docstring del módulo). El caso **15** de `incidentDivergence.test.ts` es el que lo fija; el caso **13** cubre `(NaN)` ⇒ `""`.
- [ ] El ratchet de deuda de UI sigue verde: **cero** `style={{}}` inline y **cero** HEX en los archivos de frontend tocados.
- [ ] El smoke manual de F5 (**9** pasos) fue ejecutado, incluidos el 5 (con el chip activo, "Seleccionar todo" cuenta **sólo lo visible** — C7), el 6 (la fila cambia **sin recargar**), el 7 (**cero** peticiones nuevas por fila), el 8b (GitLab cierra de verdad) y el 9 (el camino automático refleja el estado real).
- [ ] **(D2 v4 — corregido)** La entrada **`PLAN270-GITLAB-SYNC-AUSENTE`** está en `docs/sistema/error_fingerprints.json` con `status: "open"`, copiada del **objeto JSON literal de §6** (con `\\.` escapado y `self_test` presente). **El id `gitlab_sync_module_missing` era el del v2 y §6 lo descarta: no lo uses.** Hasta el v3 este bullet pedía el id viejo y contradecía al bullet de delta-cero de más arriba — el checklist era insatisfacible.
- [ ] Ningún archivo fuera de la lista declarada fue modificado. Verificable con `git status --short`; y `git diff --stat -- "Stacky Agents/backend/api/tickets.py"` muestra **sólo** los cuatro puntos de R3.
