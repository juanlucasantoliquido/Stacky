# Plan 269 — Veredicto por evidencia: tres niveles y fin del falso error VISIBLE

> **Estado:** CRITICADO v4 — **APROBADO-CON-CAMBIOS. La prohibición "NO implementar" queda LEVANTADA: los cambios ya están aplicados en este v4.**
> **Autor:** StackyArchitectaUltraEficientCode
> **Juez v1→v2:** StackyArchitectaUltraEficientCode (misma corrida)
> **Juez v2→v3:** revisión INDEPENDIENTE, contexto limpio, **criticando CORRIENDO** (no releyendo): invariante simulado con el código literal del plan, censo por AST, tests ejecutados con el venv py3.13, greps sobre el árbol vivo.
> **Juez v3→v4:** **SEGUNDA pasada independiente sobre el v3**, otra corrida, otro contexto. Mandato: verificar CORRIENDO que D1..D5 estén realmente cerrados y cazar los bloqueantes que el propio v3 haya introducido. Resultado: **D1, D2, D3 y D5 cerrados** (verificados ejecutando, no releyendo); **D4 NO estaba cerrado** (su fix repetía el error que arreglaba) y se corrigió; **4 defectos IMPORTANTES introducidos por el v3** hallados y corregidos, 5 menores más.
> **Fecha:** 2026-07-28
> **Depende de:** Plan 254 (IMPLEMENTADO, commit `92e593f2`). Este plan **se apoya** en 254, **no lo reemplaza** ni lo duplica.
> **Se implementa DESPUÉS de:** Plan **271** y Plan **270** (ver §0). El 269 es **CONSUMIDOR** del estado final que esos dos definen y escriben.

---

## §0 — ORDEN ENTRE PLANES VIVOS (v3, D3/D4). Leer ANTES de tocar una línea.

Hay tres planes vivos sobre el mismo subsistema y el orden de implementación **está decidido**:

```
271  →  define QUIÉN escribe el estado final al terminar el analista
 ↓       (harness/task_states.py, completion_state.py, agent_completion_internal.py)
270  →  USA ese estado para cerrar de verdad en ADO y GitLab
 ↓       (api/tickets.py F3/F4/F7, api/incident_inbox.py F5, IncidentInboxPage.tsx F5)
269  →  LEE el resultado y emite veredicto.  ← ESTE PLAN
```

**El 269 no vuelve a definir nada de eso.** No toca `harness/task_states.py`, no toca ningún sitio de cierre, no decide quién escribe el estado. Solo lo lee (P3).

**Colisión REAL de archivos, verificada (no supuesta):**

| Archivo | Lo toca el 270 | Lo toca el 269 | Consecuencia |
|---|---|---|---|
| `backend/api/incident_inbox.py` | **Sí** (270 F5) | **Sí** (269 F5) | Los anclajes `:149`, `:160-164`, `:161` de este plan **se van a mover**. |
| `frontend/src/pages/IncidentInboxPage.tsx` | **Sí** (270 F5) | **Sí** (269 F5) | Ídem `:488`, `:503-507`. |
| `backend/api/tickets.py` | **Sí** (270 F3/F4/F7) | **Lo lee** (269 F6 reusa `:1165`) | Los anclajes `:1165` / `:1204` / `:1406` / `:1495` **se van a mover**. |
| `backend/harness/task_states.py` | No | No | Es del **271**. Intocable acá. |

**REGLA DURA DE ANCLAJE PARA EL IMPLEMENTADOR (v3):** todos los `archivo:línea` de este documento se midieron el **2026-07-28**, **antes** de que entren el 271 y el 270. Cuando llegue el turno del 269, **los números de línea de `api/tickets.py`, `api/incident_inbox.py` e `IncidentInboxPage.tsx` estarán corridos.** Por eso, en esos tres archivos:

- **Se ancla por SÍMBOLO, nunca por número.** Antes de editar, correr el grep y usar la línea que devuelva:
  ```
  cd "Stacky Agents/backend"
  grep -n "Sin N+1" api/incident_inbox.py
  grep -n "for t in rows" api/incident_inbox.py
  grep -n "def set_stacky_status(" api/tickets.py         # ← EL PARÉNTESIS ES OBLIGATORIO (v4, E4)
  grep -n "def set_stacky_status_by_ado" api/tickets.py
  cd "Stacky Agents/frontend"
  grep -n "className={styles.row}" src/pages/IncidentInboxPage.tsx
  ```
> ⚠ **v4 (E4) — POR QUÉ ESE PARÉNTESIS NO ES COSMÉTICO.** `grep -n "def set_stacky_status"` **sin** el paréntesis devuelve **DOS** líneas, porque el patrón es prefijo del otro símbolo: `:1166` (`set_stacky_status`, el endpoint **PERMITIDO**, que llama `ts.set_status` y **no publica**) y `:1205` (`set_stacky_status_by_ado`, el **PROHIBIDO**, que **publica en el ADO real del operador** y le cambia el estado del work item). Medido: sin paréntesis **2 hits**, con paréntesis **1 hit**. Una regla de anclaje que devuelve dos candidatos —y donde el candidato equivocado escribe en el tracker del operador— es peor que no tener regla. **Cada grep de anclaje de este plan tiene que devolver EXACTAMENTE 1 hit; si devuelve 2, el patrón está mal, no el árbol.**

- **Si un símbolo no aparece**, el 270 lo renombró: **PARAR** y re-anclar el plan, no improvisar.
- **Si un símbolo aparece MÁS DE UNA VEZ**, el patrón es ambiguo: **afinarlo** (agregar el `(`, el `def `, el `class `) hasta que dé 1 hit. Nunca elegir "el primero que salga".
- Los anclajes de `api/executions.py`, `services/run_verdict.py`, `services/run_outcome.py`, `models.py`, `tablePrefs.ts` y `ExecutionHistoryPage.tsx` **no** están en la zona de colisión: ahí los números valen.

**Numeración (D4 → CORREGIDO en v4, E3):** los números **270 y 271 están OCUPADOS** por planes reales y distintos. El corte de scope que el v1/v2 sugería mandaba F6+F8 "al 270" — eso era una **colisión de numeración**, el mismo error que ya forzó el renumerado 267→269.

> ⚠ **El v3 "arregló" esto mandando el corte al 272. Eso era la MISMA colisión un nivel más arriba.** Verificado con `grep -n "272"` sobre los dos vecinos:
> - **Plan 271, línea 6:** *"El **272** queda reservado para «un solo escritor de estado» (§6.1)"* — y lo referencia otras 10 veces como dueño de esa migración (extender el árbitro a los motores C..F, modelar `on_failure_state`, poblar `stacky_project_name`).
> - **Plan 270, línea 1517:** *"⇒ **plan 272 sugerido**"* para la reconciliación masiva Stacky→tracker.
> - **Plan 270, línea 1520, textual:** *"**No hardcodear 272/273 desde este documento.**"*
>
> **REGLA DE NUMERACIÓN DEL CORTE (la única que no caduca):** este documento **NO asigna un número** a la segunda mitad. Si se aplica el corte, en el momento de crear el archivo:
> 1. `ls "Stacky Agents/docs/"` **en frío** (con `ls`, no `git ls-files`: los planes de sesiones paralelas llegan untracked).
> 2. `grep -rn "plan 27[0-9]\|27[0-9]_PLAN" "Stacky Agents/docs/"` para cazar los números **reservados por texto**, que no tienen archivo todavía. **Hoy el 272 está reservado dos veces** (271 §6.1 y 270 §continuaciones): **saltarlo.**
> 3. Tomar el primer número **sin archivo y sin reserva escrita**.
>
> Un número escrito en un plan envejece mal; el procedimiento no.

---

## CHANGELOG v3 → v4 (SEGUNDA pasada independiente sobre el v3, criticando CORRIENDO)

**VEREDICTO: APROBADO-CON-CAMBIOS. 0 BLOQUEANTES, 4 IMPORTANTES, 5 MENORES.** La prohibición *"NO implementar hasta aplicar los fixes D1..D5"* **se levanta**: los cambios están aplicados acá.

### Estado real de D1..D5, uno por uno, verificado EJECUTANDO

| ID | ¿Cerrado? | Evidencia CORRIDA en esta pasada |
|---|---|---|
| **D1** | **SÍ, y es sólido** | Se extrajo a disco el módulo F0 **literal del v3** y se barrió la **grilla COMPLETA** (no la del doc): 243 combinaciones de evidencia × **7** `ticket_status` × **10** `outcome_reason` (los **9** reales de `run_outcome.OUTCOME_REASONS` + `None`) = **17.010 casos ⇒ 0 violaciones de I1**. Monotonicidad del ticket: **68.040 casos ⇒ el ticket mejoró el nivel en 0**. No terminales (`idle`/`running`/`""`/`"   "`): **0** veredictos espurios. El caso testigo `run=error` + `ticket=completed` + `publicado=True` da **`advertencia` / `falso_rojo_probable`** ✓. Además el gate de borde **A3 existe y cubre los dos endpoints**, y se verificó que el cableado es viable: en `executions_history()` la variable `rows` **es una lista de `AgentExecution`** (`q = session.query(AgentExecution).join(Ticket, ...)`), así que `row.id/.status/.metadata_dict/.ticket` existen. **Pero los dos GATES del fix estaban rotos: ver E1 y E2.** |
| **D2** | **SÍ, y el censo está completo** | Censo de literales corrido sobre `services/ado_publisher.py`: `failed`×6, **`idempotent_replay`×3 (`:399`, `:446`, `:541`)**, `ok`×1 (`:508`), más `skipped` condicional en `:326` ⇒ **4 valores**, exactamente lo que D2 afirma. Persistencia sin filtrar: `status=result.status` (`:895`). Dedupe en `:387-397`: `(ado_id, html_sha256, status=="ok")` — **por contenido y ado_id, NO por ejecución**, así que la fila `ok` queda pegada a la PRIMERA ejecución y la re-corrida solo tiene `idempotent_replay`: el diagnóstico de D2 es correcto al 100%. **Dato nuevo que cierra el censo:** en todo `backend/` hay **UN SOLO** escritor de filas (`AgentHtmlPublish(` aparece solo en `:889`), así que no hay un 5º valor escondido en otro módulo. Fix `status IN ('ok','idempotent_replay')` correcto. |
| **D3** | **SÍ** | §0 existe con el orden 271→270→269 y la tabla de colisión. Los 5 anclajes por símbolo se **corrieron**: `"Sin N+1"`→`:149` (1 hit), `"for t in rows"`→`:161` (1 hit), `"def set_stacky_status_by_ado"`→`:1205` (1 hit), `"className={styles.row}"`→`:488` (1 hit). **Pero el 5º grep es ambiguo y peligroso: ver E4.** |
| **D4** | **NO. El fix repetía el error que venía a arreglar.** | Corregido en este v4: ver **E3**. |
| **D5** | **SÍ en el diseño** | La cota es real: `scan_recent(limit: int = 200)` **verificado** en `services/run_reconciliation.py:168`, así que reusar `limit=200` es coherente. Reusar `collect_for_executions` + `_Budget` propio + `falso_rojo_probable: null` (nunca `0`) con los colectores OFF es exactamente lo correcto, y los 3 tests que lo fijan están bien planteados. **Pero la aritmética de claves está declarada de tres formas distintas: ver E5.** |

### Lo que introdujo el v3 (los defectos nuevos, todos medidos)

| ID | Sev | Qué está mal en v3 | Evidencia de haberlo CORRIDO | Fix en v4 |
|---|---|---|---|---|
| **E1** | **IMP** | **La segunda afirmación de A3 —la adición estrella del v3— es FALSA, y con ella el test estrella nace ROJO.** A3 dice: *"se asegura que el item de la ejecución `error` … mientras el item de la `completed` **sí puede ser `exito`**"*. Pero A3 solo siembra evidencia (`una fila ok en agent_html_publish`) para la ejecución **`error`**. La `completed` del mismo ticket queda **sin ninguna señal**, y con los colectores reales eso da `publicado=False`, `cambio_en_repo=False`, `gate=None`, `verificacion=None`, `entregable=False` ⇒ **`strength=0`**, muy por debajo de `UMBRAL_ENTREGA=2`. Un modelo menor que escriba el assert que la frase sugiere (`level == "exito"`) obtiene un test **ROJO** en el gate más importante del plan. | Corrido con el módulo F0 literal: la ejecución `completed` sin evidencia sembrada da **`level='advertencia'`, `cause='evidencia_indeterminada'`, `strength=0`**. `exito` es **inalcanzable** con los datos que A3 siembra. | A3 pasa a sembrar **DOS** filas en `agent_html_publish` (una por ejecución) y el test asserta el **contraste exacto**: la `error` → `advertencia`/`falso_rojo_probable`; la `completed` → `exito`/`cierre_limpio_con_entrega`. Así el test prueba lo que la adición promete (que el run manda) en vez de una frase con "puede". |
| **E2** | **IMP** | **El gate que el DoD llama "EL GATE MÁS IMPORTANTE DEL PLAN" no atrapa 2 de las 3 formas de reintroducir el bug — incluida la que el propio v3 cita textualmente.** El DoD exige `grep -rn 'stacky_status", None) or ex.status' backend/api/` = 0 hits. Ese literal tiene **espacios después de las comas**, así que matchea la variante de F2 pero **NO** la de F5, que el propio v3 transcribe en D1 **sin espacios**: `getattr(by_tid.get(tid),"stacky_status",None) or ex.status or ""`. Tampoco atrapa la reescritura más natural, por atributo: `ticket.stacky_status or ex.status`. Es **exactamente el defecto D6** (`verdictTone` vs `verdictChipTone`) reintroducido en el gate de máxima criticidad. | Probado con 3 archivos sonda en `sonda/api/`: gate del DoD → `v2_f2_variant.py` **1 hit**, `v2_f5_variant.py` **0 hits (IMPUNE)**, `v2_attr_variant.py` **0 hits (IMPUNE)**. | El gate negativo frágil se **reemplaza por un gate POSITIVO** (que no depende de adivinar la ortografía del pecado): los dos call-sites deben pasar `run_status=` explícito. Más un centinela negativo robusto con `grep -rEn` insensible a espacios. Y el fondo del problema se ataca con la **[ADICIÓN ARQUITECTO A4]**: los centinelas del DoD se auto-testean. |
| **E3** | **IMP** | **D4 no cerró: su fix repite el error que arregla.** D4 movió el corte de scope del 270 (ocupado) al **272** "primer número libre verificado". Pero el **272 está reservado por escrito por los DOS vecinos**, para dos ejes distintos, y uno de ellos **prohíbe explícitamente hardcodearlo**. Asignarle F6+F8 al 272 desde este documento es la misma colisión que forzó el renumerado 267→269, un nivel más arriba. | `grep -n "272"` sobre los vecinos: **plan 271 línea 6** — *"El **272** queda reservado para 'un solo escritor de estado' (§6.1)"*, y lo referencia 10 veces más como dueño de esa migración. **Plan 270 línea 1517** — *"**plan 272 sugerido**"* para la reconciliación masiva Stacky→tracker. **Plan 270 línea 1520**, textual: *"**No hardcodear 272/273 desde este documento**"*. | El corte **no lleva número hardcodeado**. Se escribe la regla operativa (relistar en frío, tomar el primer libre real, y **saltar el 272** porque está doblemente reservado), que es la única forma que no caduca. |
| **E4** | **IMP** | **El anclaje por símbolo de §0 devuelve DOS hits en el único lugar donde confundirse escribe en el ADO REAL del operador.** §0 manda correr `grep -n "def set_stacky_status" api/tickets.py` y *"usar la línea que devuelva"*. Ese patrón es **prefijo** de `set_stacky_status_by_ado`, así que devuelve **2** líneas: `:1166` (el endpoint PERMITIDO, que no publica) y `:1205` (el **PROHIBIDO**, que publica en ADO y cambia el work item). Un modelo menor recibe una respuesta ambigua justo en el riesgo R5, que el plan blinda en tres lugares… y después se lo desarma solo con este grep. | Corrido: `grep -c "def set_stacky_status" api/tickets.py` = **2**; `grep -c "def set_stacky_status("` (con paréntesis) = **1** → `:1166`. | El grep de §0 pasa a llevar el paréntesis de apertura: `grep -n "def set_stacky_status(" api/tickets.py`. Se agrega la advertencia de por qué. |
| **E5** | MEN | **`count_by_level` declara su contrato con TRES conteos de claves distintos.** El JSON de D5 tiene **7** claves; la línea siguiente dice *"Declarando siempre las **6** claves"*; el test se llama `test_count_by_level_declara_las_6_claves_siempre` con la lista *"(`days`, `limit`, `sampled`, y los 3 niveles)"* = 6 (sin `falso_rojo_probable`); y el pie de F8 dice *"devuelve las **4** claves en 0"*. Si el test se implementa por igualdad de conjuntos contra 6, es **ROJO** (hay 7). | Contado sobre el JSON literal del doc: `len({days, limit, sampled, exito, advertencia, error_real, falso_rojo_probable})` = **7**. | Se congela en **7** en los tres lugares y el test se renombra a `test_count_by_level_declara_las_7_claves_siempre`, con la lista explícita. |
| **E6** | MEN | **La grilla de `test_I1b` está declarada más chica que la real y no es reproducible.** Dice *"× los **6** `outcome_reason` = 10.206 casos"*, pero `OUTCOME_REASONS` tiene **9** entradas y no existe ningún subconjunto de 6 nombrado. El test hermano (`test_todo_nivel_pertenece_al_vocabulario`) usa correctamente *"los 9 + None"*: el doc se contradice. | Corrido: `len(OUTCOME_REASONS)` = **9** (`clean_exit, dirty_exit_after_work, quota_exhausted, stall_after_work, stall_no_work, preflight_blocked, reaper_timeout, reaper_heartbeat, cli_failure`). Grilla honesta = 243 × 7 × **10** = **17.010**, corrida acá con **0 violaciones**. | La grilla pasa a **17.010** (9 reasons + `None`) en el test y en P1/R1/R19. Un número más grande y, sobre todo, **reproducible**. |
| **E7** | MEN | **§3.2 sigue afirmando los 3 valores que D2 desmintió.** La tabla de evidencia dice `status ∈ ok/skipped/failed (:144)` — que es exactamente el **comentario obsoleto de la columna**, la fuente que D2 declara no confiable. La sección que un modelo menor lee para entender el modelo de datos contradice a F1. | `services/ado_publisher.py:144` → `status: Mapped[str] = mapped_column(String(20), nullable=False)  # ok \| skipped \| failed`. El comentario MIENTE: falta `idempotent_replay`. | §3.2 corregida a los **4** valores, con la advertencia de que el comentario de la columna está desactualizado. |
| **E8** | MEN | **El anclaje de fixtures de A3 es falso.** A3 dice reusar *"el patrón de fixtures que ya usan `test_plan254_falso_rojo.py` y `test_plan238_incident_inbox_api.py`"*, pero **ninguno de los dos siembra `agent_html_publish`** — y A3 lo necesita. | `grep -rln "AgentHtmlPublish" tests/` → `test_publish_ledger.py`, `test_agent_completion_gateway.py`, `test_output_watcher.py`, `test_rescue_execution.py`, `test_plan_creacion_tareas_fase0_fase1.py`. En `test_plan254_falso_rojo.py`: **0 hits**. | Se ancla en el helper REAL, `tests/test_publish_ledger.py:47-54`, y se listan las **7 columnas NOT NULL** que hay que sembrar. **Verificado además que no hay riesgo de tabla ausente:** `AgentHtmlPublish` está registrada en `init_db` (`db.py:239`), así que `create_all` la crea. |
| **E9** | MEN | El módulo F0 importa `field` de `dataclasses` y **nunca lo usa** (F401). | Leído el cuerpo entero del módulo: 0 usos de `field`. | Import reducido a `dataclass`. |
| **A4** | — | **[ADICIÓN ARQUITECTO] Los centinelas del DoD se auto-testean.** Ver F7. | — | — |

### Lo que esta pasada CONFIRMÓ como correcto (además de D1/D2/D3/D5)

- **D7 exacto, regrepeado:** los `<th data-col>` están en **526, 531, 536, 541, 546 (`estado`), 551, 556, 561, 566, 571**, `<thead>` en **507** y `</thead>` en **579**. El remapeo del v3 es correcto línea por línea; el rango `:526-576` y la posición del `<th>` nuevo (entre `estado` y `duracion`) son válidos.
- **D13 exacto:** `api/incident_inbox.py` usa `from config import config as _cfg` + `getattr(_cfg, ...)` en `_enabled()` y `_actions_enabled()`, con el comentario-gotcha literal en `:14-15`. El patrón que el v3 eligió para `_inbox_verdict_enabled()` es el que ya vive en el archivo. Correcto.
- **D6 cerrado:** el gate de K3 ya grepea `verdictChipTone`, que es el símbolo que F3/F4 crean.
- **D11 exacto:** `ExecutionHistoryItem` tiene **20** campos (`endpoints.ts:1303-1324`) y **no** trae `verdict`; `AgentHistoryPage.tsx` vive en `components/`; el literal de `IncidentInboxPage.tsx:488` es `<div key={item.id} className={styles.row}>`.
- **`StatusChip` acepta `title`** (`StatusChipProps.title?: string`, `StatusChip.tsx:13`) y su `StatusTone` es `success|warning|danger|info|neutral`: el puente `verdictChipTone` devuelve un subconjunto ⇒ **compila**.
- **F2 punto 1 encaja literal:** `list_executions()` tiene las variables `rows`, `payload` y `dirty`, y su return es exactamente `return jsonify([_with_outcome(d, dirty) for d in payload])`. El diff del plan aplica tal cual.
- **La receta de flag apunta bien:** `_CURATED_DEFAULTS_ON` se declara en `test_harness_flags.py:467` (**247** keys contadas) y el assert de `:985` es **por igualdad de conjuntos** (`known_keys == _CURATED_DEFAULTS_ON`), así que agregar las 5 keys es necesario **y** suficiente. El default ON de las 5 no es hallazgo: es la directiva vigente.
- **Las 9 causas del veredicto son TODAS alcanzables** (barrido completo: 9/9, cero causas muertas) y `set(_STATUS_TO_BASE) | _NO_TERMINALES == VALID_TICKET_STATUSES` (los 6 estados reales) ⇒ `test_no_agrega_estados_al_vocabulario` **cuadra**.

---

## CHANGELOG v2 → v3 (juez INDEPENDIENTE, criticando CORRIENDO)

**VEREDICTO: RECHAZADO. 5 BLOQUEANTES.** El v2 arregló bien las 5 trampas de superficie que hundieron al v1 (`verdict` ocupada, dos handlers, columnas configurables, módulo sin logger, `passed` vs `ok`) — **las 5 se reverificaron corriendo y las 5 están correctamente contempladas**. Lo que hundió al v2 es otra cosa: **el invariante de negocio se rompe en el CABLEADO, no en el núcleo**, y el plan es **ciego a los dos planes vivos con los que comparte archivo y línea**.

La metodología que encontró estos 5: **no se releyó el plan, se ejecutó.** Se instanció el módulo F0 literal del documento y se barrió su grilla; se simuló el cableado de F2 con objetos reales; se censó por AST; se corrieron los tests que el plan nombra con el venv py3.13.

| ID | Sev | Qué está mal en v2 | Evidencia de haberlo CORRIDO | Cómo se arregla en v3 |
|---|---|---|---|---|
| **D1** | **BLOQ** | **El invariante de negocio —"un `error` NUNCA da `exito`"— SE ROMPE EN EL CABLEADO.** La función pura está bien, pero F2 le pasa el estado **del TICKET**, no el del RUN: `estado = (getattr(ticket,"stacky_status",None) or ex.status or "")` (F2) y `estado = getattr(by_tid.get(tid),"stacky_status",None) or ex.status or ""` (F5). Un ticket que hoy está `completed` (2º intento OK, o el operador lo cerró) con una ejecución vieja de `status="error"` produce **`exito` / `cierre_limpio_con_entrega`**. Y como `ExecutionHistoryPage` lista **ejecuciones** (1 fila por ejecución, N por ticket), **TODAS** las corridas fallidas de un ticket ya cerrado se pintan "Terminó bien" **al lado del chip "Error"**. Es exactamente el falso VERDE que P1 prohíbe. Peor: **`test_I1_un_error_jamas_recibe_exito` sigue VERDE**, porque solo prueba la función pura — el test no puede ver el bug. | Se ejecutó el módulo F0 **literal del plan** (1215 combinaciones): **0 violaciones en la función pura, I1 se sostiene**. Después se simuló el cableado F2 con `ticket.stacky_status="completed"` + `ex.status="error"` + `publicado_en_tracker=True` → **`exito / cierre_limpio_con_entrega`**. Confirmado que son columnas independientes por AST: `Ticket.stacky_status` (`models.py:61`) vs `AgentExecution.status` (`models.py:254`), FK `ticket_id` (`:252`). | `evaluate_verdict` pasa a exigir **`run_status` (keyword-only, obligatorio)** y el veredicto se **ancla en el run**: el ticket solo puede **EMPEORAR** el nivel, jamás mejorarlo (`_peor(...)`). I1 queda garantizado **en todos los call-sites, estructuralmente**. Tests nuevos `test_I1b_el_ticket_completed_no_blanquea_un_run_error` y `test_el_ticket_solo_empeora_nunca_mejora`. |
| **D2** | **BLOQ** | **`publicado_en_tracker` pierde `idempotent_replay` y da FALSO NEGATIVO en la señal más pesada.** El colector filtra `AND status = 'ok'`, pero `agent_html_publish.status` tiene **4** valores, no 3: `ok`, `failed`, `skipped` y **`idempotent_replay`**. Y `idempotent_replay` significa **que el comentario SÍ está publicado** (el dedupe lo detectó). Como el dedupe pre-ADO es por `(ado_id, sha256, status='ok')`, la fila `ok` queda en la ejecución **A** y la re-corrida **B** solo tiene una fila `idempotent_replay` — con `status='ok'` la query devuelve vacío para B ⇒ señal **`False`** (peso 2 perdido), no `None`. Por P2, `False` es peor que `None`: el `falso_rojo_probable` degrada a **`error_sin_entrega_suficiente` / `error_real`**. **El plan reintroduce, en su propio colector, el falso rojo que existe para matar** — y justo en el caso más común (reintento de una corrida que ya publicó). | `services/ado_publisher.py:895` persiste `status=result.status` **sin filtrar**; los literales `status="idempotent_replay"` están en `:399`, `:446`, `:541`; el dedupe por contenido usa `AgentHtmlPublish.status == "ok"` en `:392`. | La query pasa a `status IN ('ok','idempotent_replay')`, con el motivo escrito en el pseudocódigo. Test nuevo `test_publicado_cuenta_idempotent_replay`. |
| **D3** | **BLOQ** | **Ciego a los planes 270 y 271, con los que colisiona en archivo Y línea.** El 270 edita `api/incident_inbox.py`, `IncidentInboxPage.tsx` y `api/tickets.py` — los **mismos** archivos que este plan ancla por número (`:149`, `:160-164`, `:161`, `:488`, `:503-507`, `:1165`, `:1204`, `:1406`, `:1495`). El 271 define **quién escribe el estado final**, que es literalmente la **entrada** del veredicto. El orden decidido es **271 → 270 → 269**, y este documento no lo menciona ni una vez: está escrito como si fuera el único plan vivo. Implementarlo con estos números produce parches en el lugar equivocado. | `270_PLAN_..._CIERRE_REAL_EN_ADO_Y_GITLAB.md` declara S1/S2 en `api/tickets.py` (`:203-205`), su F5 sobre `incident_inbox.py`/`IncidentInboxPage.tsx` (`:211`), y `api/incident_inbox.py:163` como anclaje propio. `271_PLAN_...` opera sobre `harness/task_states.py`. | **§0 nuevo**: orden entre planes, tabla de colisión, y **regla dura de anclaje por SÍMBOLO** (con los greps exactos) para los 3 archivos de la zona caliente. |
| **D4** | **BLOQ** | **El "corte recomendado" manda F6+F8 al plan 270 — que YA EXISTE y es otro plan.** Es una colisión de numeración: exactamente el gotcha que ya obligó a renumerar este plan de 267 a 269. Un implementador que aplique el corte pisa un plan ajeno. | `ls "Stacky Agents/docs/"` el 2026-07-28: 270 y 271 ocupados por planes distintos y vivos. | El corte va al **272**. Corregido en §CHANGELOG y en §8. |
| **D5** | **BLOQ** | **`count_by_level` y `verdict_agreement` no dicen de dónde sacan la evidencia — y sin ella nacen muertas.** Ambas cuentan `falso_rojo_probable`, causa que **solo** existe si `delivery_strength >= UMBRAL_ENTREGA`, que **solo** se puede calcular con los colectores de F1. El plan nunca lo especifica. Si no llaman a `collect_for_executions`, `fuerza` es 0 siempre ⇒ `falso_rojo_probable` es **estructuralmente 0 para siempre** ⇒ **K1, el KPI estrella del plan, reporta 0 permanente**, `verdict_agreement.propuestos` es 0 y `ratio` es `None` para siempre: **la ADICIÓN A1 completa es inerte**. Y si sí las llaman, F8 mete un barrido de **30 días con lecturas de disco** dentro del GET de `/api/diag/run-reconciliation`, que se dispara en cada carga de la card — contradiciendo R3 y el propio `COLLECTOR_BUDGET_S`. El DoD "los KPI K1/K6 están medidos" es, con el v2, inalcanzable o mentiroso. | El plan declara `count_by_level` en F8 (§`{"days":30,"exito":0,...,"falso_rojo_probable":0}`) sin una sola línea sobre las señales; `delivery_strength()` (F0) solo suma señales `True`. | Las dos funciones **reusan `collect_for_executions`** con **cota dura** (`limit=200`, el mismo de `scan_recent`) y **su propio `_Budget`**. Con los colectores OFF devuelven `falso_rojo_probable: null` (**desconocido**), **nunca 0** — 0 sería mentir. Tests nuevos `test_count_by_level_usa_los_colectores`, `test_count_by_level_esta_acotado` y `test_count_by_level_sin_colectores_reporta_null`. |
| **D6** | IMP | **El gate del KPI K3 nunca puede pasar:** `grep -c "verdictTone" ExecutionHistoryPage.tsx` — pero el símbolo que F4 crea se llama **`verdictChipTone`**, y `"verdictTone"` **no es substring** de `"verdictChipTone"`. El DoD (`:1715`) usa el nombre correcto: el documento se contradice consigo mismo. | Probado con un archivo sonda que contiene `verdictChipTone`: `grep -c "verdictTone"` → **0**; `grep -c "verdictChipTone"` → **1**. | K3 pasa a `verdictChipTone`. |
| **D7** | IMP | **El `<th>` de `estado` está FUERA del rango que el plan manda parchear.** v2 dice "los `<th>` existentes están en `:525-545`" y "el de `estado` precede a `duracion`" — pero el `<th>` de `estado` está en **`:546`** y el bloque real va de **`:526` a `:576`**. Un modelo menor que abra 525-545 encuentra `inicio/agente/runtime/modelo` y **no** encuentra `estado`: inserta la columna en el lugar equivocado y desalinea la tabla — exactamente R9/R16. | `grep -n` sobre `ExecutionHistoryPage.tsx`: `inicio` 526, `agente` 531, `runtime` 536, `modelo` 541, **`estado` 546**, `duracion` 551, `costo` 556, `prompt` 561, `archivos` 566, `ticket` 571, acciones 577. `<thead>` 507→579. | Rango corregido a `:526-576` con el `<th>` de `estado` nombrado en `:546-548`. |
| **D8** | IMP | **R1 se contradice con F0:** R1 dice *"la regla **6** (única que produce `exito`)"*, pero según la lista de precedencia del propio F0 la que produce `exito` es la **regla 7** (F0 lo dice bien dos veces). Número heredado de la numeración de v1. | Lectura cruzada F0 (`orden de precedencia`, reglas 0..9) vs R1. | R1 corregido a "regla 7". |
| **D9** | IMP | **R4 nombra un test que no existe con ese nombre:** cita `test_colector_que_lanza_no_rompe_el_listado`, pero el test que F2 declara se llama `test_colector_que_lanza_no_rompe_ninguno_de_los_dos`. Referencia colgante. | Tabla de tests de F2 vs tabla de riesgos. | Corregido. |
| **D10** | IMP | **El tono `espera` quedó inalcanzable.** `espera_cuota` mapea a nivel `advertencia` → `VERDICT_LEVEL_VIEW.advertencia.tone = "atencion"`. O sea `verdictChipTone("espera")` **nunca se llama en producción**, y una corrida frenada por cuota se le presenta al operador como "Con advertencias" en vez de "esperando" — perdiendo una semántica que `OutcomeTone` **ya tiene** (`outcomeReason.ts:12` = `"exito" \| "atencion" \| "espera" \| "error"`). El test `verdictChipTone cubre los 4 tonos` cubre una rama muerta. | `outcomeReason.ts:12` verificado literal. `_CAUSE_TO_LEVEL["espera_cuota"] == "advertencia"` en el código de F0. | `describeVerdict` pasa a resolver el tono **por causa** antes que por nivel: `espera_cuota` → tono `espera`. El nivel sigue siendo `advertencia` (no se toca la dimensión del veredicto). |
| **D11** | MEN | Anclajes con desvío verificado: `ExecutionHistoryItem` tiene **20** campos, no 21 (`endpoints.ts:1304-1323`); `AgentHistoryPage.tsx` vive en **`components/`**, no en `pages/`; el literal de `IncidentInboxPage.tsx:488` es `<div key={item.id} className={styles.row}>`, no `<div className={styles.row}>`; la tupla `observabilidad_notif` **abre en `:305`** (`:324` es una línea miembro); `.join(Ticket` está en **`:482`** (no 481); `def get_intent` está en **`:213`** (no 214); `class AgentHtmlPublish` va de **122 a 184** (no 122-154). | Todos regrepeados uno por uno. | Corregidos in situ. |
| **D12** | MEN | El plan lista **4** topes de `PlainHelp` pero hay **5**: falta `example ≤ 300` (`test_harness_flags_help.py:51`). | Los 5 textos de F7 se **midieron** contra los 5 topes reales: **todos pasan**, incluido el 5º. No hay que reescribir ninguno — pero el tope faltaba declarado. | Agregado el 5º tope a §3.7. |
| **D13** | MEN | `api/incident_inbox.py` ya lee config con `from config import config as _cfg` **dentro de** sus funciones (`:16`, `:28`), con un comentario que advierte de este gotcha exacto. El plan introduce en el **mismo archivo** un segundo patrón (`import config as _config` + `_config.config`). Los dos funcionan, pero mezclarlos en el archivo que documenta el gotcha invita al error. | `sed -n '1,30p' api/incident_inbox.py`. | `_inbox_verdict_enabled()` usa el patrón **que ya vive en ese archivo**. |
| **A3** | — | **[ADICIÓN ARQUITECTO] El gate del falso verde vive en el BORDE, no en el núcleo.** Ver F2. | — | — |

**Lo que esta segunda pasada CONFIRMÓ como correcto (no se toca):**
- **Las 5 trampas de superficie del gotcha registrado están las 5 bien resueltas**, verificadas corriendo: (1) `verdict` ocupada — `models.py:255` col + `:327` `to_dict` ⇒ la clave nueva `run_verdict` es correcta; (2) **DOS** handlers — `list_executions()` `:96` y `executions_history()` `:443` ⇒ F2 cablea los dos; (3) columnas configurables — `HISTORY_COLUMNS` en `tablePrefs.ts:27` con las 10 entradas y 21 usos de `isColVisible` en la página ⇒ F4 registra la columna; (4) `api/incident_inbox.py` sin `logger` — `grep -c logger` = **0** confirmado ⇒ F5 paso 1 correcto; (5) el campo es **`passed`** (`exec_verification.py:70`, `to_metadata` `:79`) ⇒ C5 correcto.
- **I1 se sostiene en la función pura**: 1215 combinaciones ejecutadas, **0** violaciones.
- **I2 se sostiene**: `None` y `False` suman igual en `delivery_strength`, y `unknown` solo dispara `evidencia_indeterminada` (mismo nivel que `verde_sin_evidencia`). Nunca mejora.
- **Los anclajes del backend fuera de la zona de colisión son exactos**: `run_outcome.py` 13/55/104/113 y `_REASON_TO_STATUS` 34-44 (**9** reasons, `classify_outcome_reason` con **exactamente 8** parámetros keyword-only, tal como afirma el plan); `run_reconciliation.py` 28/72/168/217 y **`summarize()` ES PURA** (recibe `list[Discrepancy]`, no lee config ni DB) ⇒ C6 correcto; `status_vocabulary.py` 11/14/18 con **exactamente los 6** estados que el plan asume (`test_no_agrega_estados_al_vocabulario` **cuadra**); `ticket_status.py` 152/183/293/340-341; `api/executions.py` 25/28/35/65/459-460/538-559/561-564; `incident_dev_pr.py` `_intent_dir` 192-196 con el **`mkdir` en `:195` y FUERA del `try`** ⇒ C7 correcto; `models.py` 258/261/272/301/309 y el índice **`ix_exec_ticket_started (ticket_id, started_at)` EXISTE** en `:278` ⇒ la subconsulta de C10 está bien indexada.
- **`api/tickets.py:1165` NO publica** (llama `ts.set_status` en `:1189` y termina en `:1201`) y **`:1204` SÍ publica** (`:1387` `close_execution_with_publish`, `:1404-1407` log, `:1487-1497` cambia el work item). **La elección de endpoint del HITL y el default ON de `STACKY_RUN_RECONCILIATION_HITL_ENABLED` quedan RATIFICADOS por segunda vez.**
- **Las 5 flags son genuinamente nuevas**: 0 hits en `config.py`, `harness_flags.py`, `harness_flags_help.py`, `test_harness_flags.py` y en todo el repo.
- **La receta de flag es correcta**, incluidos `HARNESS_TEST_FILES` (`.sh:20`) y `$HarnessTestFiles = @(` (`.ps1:13`) — el plan nunca los confundió. **Dato nuevo:** el meta-test `test_harness_ratchet_meta.py` parsea **solo el `.sh`**; registrar únicamente en el `.ps1` deja el meta-test ROJO y solo en el `.sh` desincroniza PowerShell en silencio. El test `test_los_6_tests_estan_en_los_dos_scripts` de F7 ya cubre las dos patas: **correcto**.
- **Aritmética de tests: cuadra fila por fila.** F0 18, F1 14, F2 9, F3 11 (+2 de F4 = 13), F5 7, F6 6+7, F7 8, F8 6 ⇒ F0+F8 = 24. Ni una suma mal.
- **Tests nombrados por el plan, CORRIDOS** con `.venv` (py3.13): `test_plan254_outcome_reason` **11 passed**, `test_plan254_reconciliation` **10 passed**, `test_plan254_falso_rojo` **9 passed**, `test_plan238_incident_inbox_api` **12 passed**. Todos verdes: la base sobre la que se apoya el plan está sana.
- **Baseline de flags MEDIDO** (lo que R8 exige, hecho de verdad): `test_harness_flags` **56 passed**, `test_harness_flags_help` **4 failed / 4 passed** (los 4 fallos son **ajenos y preexistentes**), `test_harness_flags_requires` **9 passed**, `test_harness_flags_bounds` **18 passed**. Queda anotado acá para que F7 compare contra números, no contra memoria.
- **`RunReconciliationCard.tsx` no renderiza `items`**: **0** ocurrencias en todo el archivo (el tipo `RunReconciliationResponse.items` **sí** existe, `endpoints.ts:3164`). El GAP 3 es real y F6 tiene que **crear** ese render, no modificarlo.

---

## CHANGELOG v1 → v2

**Veredicto de la crítica: RECHAZADO en v1 por 6 BLOQUEANTES.** Anclajes reverificados abriendo cada archivo: **74 de 78 correctos**. Los 4 rotos y los 6 bloqueantes se corrigen abajo. El plan v1 estaba bien anclado en lo que miró; lo que lo hundió fue lo que **no** miró.

| ID | Sev | Qué estaba mal en v1 | Cómo se arregla en v2 |
|---|---|---|---|
| **C1** | BLOQ | **La clave `verdict` YA EXISTE en el payload.** `AgentExecution.verdict` es una columna real (`backend/models.py:255`, `String(20)`, veredicto de revisión humana) y `to_dict()` la emite (`backend/models.py:327`). El `_with_verdict` de v1 la **pisaba con un dict**, destruyendo un campo vivo (consumido vía `last_execution_verdict` en `frontend/src/components/AgentHistoryModal.tsx:127` y `DailyStandupModal.tsx:13`). La afirmación de v1 *"backward-compatible por construcción"* era FALSA. | La clave del payload pasa a llamarse **`run_verdict`** en TODAS las fases (F2, F3, F4, F5, F8, DoD y greps). Test nuevo `test_no_pisa_el_verdict_del_modelo`. |
| **C2** | BLOQ | **F4 pintaba el chip en una página que NO consume el endpoint que F2 cablea.** `ExecutionHistoryPage` llama `Executions.history()` → `GET /api/executions/history` → `executions_history()` (`backend/api/executions.py:442`), un handler que arma `items` **a mano** (`:538-559`), no usa `to_dict()` y **no pasa por `_with_outcome`**. F2 solo tocaba `list_executions()` (`:96`). El KPI K3 y toda F4 quedaban **inertes**. | F2 cablea **los dos** handlers: `list_executions()` y `executions_history()` (respetando `include_total` y el gate `STACKY_EXECUTION_HISTORY_ENABLED`), y agrega `run_verdict?` a `ExecutionHistoryItem` (`frontend/src/api/endpoints.ts:1303`). |
| **C3** | BLOQ | **F4 ignoraba el sistema de columnas configurables.** Cada `<th>`/`<td>` de esa tabla vive bajo `isColVisible(tablePrefs, "<id>")` contra `HISTORY_COLUMNS` (`frontend/src/services/tablePrefs.ts:27-41`), y el picker recibe `columns={HISTORY_COLUMNS}` (`ExecutionHistoryPage.tsx:454`). Un `<td>` desnudo + *"buscar el `<thead>`"* desalinea la tabla apenas el operador oculta una columna. | F4 agrega `{ id: "veredicto", label: "Veredicto" }` a `HISTORY_COLUMNS` y envuelve `<th>` y `<td>` en `isColVisible(tablePrefs, "veredicto")`, con las líneas exactas. |
| **C4** | BLOQ | **`backend/api/incident_inbox.py` NO tiene `logger`** (0 ocurrencias; ni siquiera importa `logging`). El `except` de F5 llamaba `logger.debug(...)` → `NameError` **dentro del handler de excepción** → 500 en la bandeja: exactamente lo que el plan prometía que nunca pasa. | F5 declara el logger del módulo como paso 1, con la línea literal. |
| **C5** | BLOQ | **`verificacion_ok` leía la clave equivocada.** El productor es `VerificationReport.to_metadata()` (`backend/services/exec_verification.py:79-96`): la clave es `exec_verification` y el campo es **`passed`** (`bool \| None`, `:70`), **no `ok`**. El pseudocódigo `v.get("ok") is True` daba **siempre False** y el test "discriminador" de H2 consagraba el bug. | La hipótesis H2 **se elimina**: se reemplaza por el hecho verificado. `passed` tri-estado mapea 1:1 a la señal (`None` = "could-not-verify" = desconocida). Confirmado en 3 consumidores: `api/exec_verification.py:43`, `harness/post_run.py:189`, `services/harness_health.py:848`. |
| **C6** | BLOQ | **Dos fases escribían la misma clave `hitl_enabled` en lugares distintos.** F6 decía meterla en `summarize()` — que es una función **PURA** (`run_reconciliation.py:217`, recibe una lista y no lee config; su docstring `:7-13` declara el aislamiento) — y F8 la metía en `api/diag.py:1015`. | **Una sola** escritura, en `api/diag.py`, **en F6** (F8 ya no la toca). `summarize()` queda intacta y pura. |
| **C7** | IMP | **`get_intent()` VIOLA el riel P4 ("ningún colector escribe, crea, mueve ni borra"):** `_intent_dir()` hace `d.mkdir(parents=True, exist_ok=True)` (`services/incident_dev_pr.py:192-196`). Además la afirmación de v1 *"no puede lanzar"* es falsa: el `mkdir` y el `path.is_file()` están **fuera** del `try` (`:213-220` (el `def` esta en `:213`)). | F1 lee el sidecar con un helper propio de solo lectura (`_sidecar_path`) que **no** crea nada, y envuelve todo en `try/except OSError → None`. Test nuevo `test_cambio_en_repo_no_crea_directorios`. |
| **C8** | IMP | **`cancelled` recibía una causa que MIENTE.** Base `advertencia` (el propio plan dice "el humano lo cortó, no es un fallo") pero la regla 5 le daba `cierre_sucio_pendiente_de_revision`, cuyo texto al operador es *"Entregó trabajo pero el proceso cerró mal"*. | Causa nueva **`cancelado_por_el_operador`** (nivel `advertencia`) con precedencia propia. `VERDICT_CAUSES` pasa de 8 a **9**. |
| **C9** | IMP | **Estados NO terminales pintados como advertencia.** `_STATUS_TO_BASE` no cubre `idle` ni `running` (los 2 no-terminales de `VALID_TICKET_STATUSES`): caían al default `advertencia`, así que **toda corrida en curso** se mostraba "Con advertencias" en la lista principal. | `evaluate_verdict` devuelve **`None`** para estados no terminales: un run que no terminó **no tiene veredicto**. La UI no dibuja chip. |
| **C10** | IMP | **F5 traía TODAS las ejecuciones de todos los tickets del lote** (`filter(ticket_id.in_(...)).all()`) para quedarse con la última de cada uno: fetch sin cota. | Subconsulta `max(started_at) GROUP BY ticket_id` + join. Sigue siendo **1 query**, ahora acotada a ≤1 fila por ticket. |
| **C11** | IMP | Frases vagas fatales para un modelo menor: *"el `Dialog` canónico del repo"* (el repo tiene `Dialog`, `ConfirmDialog`, `AlertDialog`, `PromptDialog` y el hook `useConfirm`), *"la interfaz de la fila de ejecución"*, *"buscar el `<thead>` del mismo archivo"*. | Nombradas literalmente: `useConfirm` de `components/ui` (patrón real `ActiveRunsPanel.tsx:7,33`), `ExecutionHistoryItem` (`endpoints.ts:1303`), `<thead>` en `ExecutionHistoryPage.tsx:507` con los `<th>` en `:525-545`. |
| **C12** | IMP | **El comando del KPI K1 era falso:** `python -c "import run_verdict_kpi"` — ese módulo no existe ni lo crea ninguna fase. | Reemplazado por el comando real de `count_by_level`. |
| **C13** | MEN | Las ramas de flag-OFF (`api/diag.py:999-1003`) y de error (`:1011-1014`) **retornan antes** de `:1015`, así que `hitl_enabled` nunca sale por ahí; el test de F6 pasaba por casualidad. | Declarado explícitamente: **ausencia ⇒ falsy ⇒ sin botones**, y la clave se agrega también en la rama de error. |
| **C14** | MEN | Anclaje `incident_dev_pr.py:199` para la ruta del sidecar: la ruta se arma en `:192-196` (`_intent_dir`) y `:199-200` (`_intent_path`). | Corregido. |
| **C15** | MEN | Anclaje de la flag del guard: es `ticket_status.py:340-341`, no `:341-342`. | Corregido. |
| **C16** | MEN | No registraba la huella de regresión. | DoD agrega la entrada en `Stacky Agents/docs/sistema/error_fingerprints.json`. |
| **A1** | — | **[ADICIÓN ARQUITECTO] Calibración observada del veredicto.** Ver F8. | — |
| **A2** | — | **[ADICIÓN ARQUITECTO] Test de espejo backend↔frontend.** Ver F0. | — |

**Lo que la crítica CONFIRMÓ como correcto en v1 (no se toca):** la aritmética de tests de las 9 fases (contadas fila por fila: 15/12/6/11+2/6/5+6/8/15+3 — todas cuadraban); la elección del endpoint HITL (`PATCH /api/tickets/<ticket_id>/stacky-status`, `api/tickets.py:1165`, **verificado**: llama `ts.set_status` y **no** publica; el `by-ado` de `:1204` **sí** publica en `:1406` y **sí** cambia el work item en `:1495`) — por lo tanto **`STACKY_RUN_RECONCILIATION_HITL_ENABLED` default ON queda APROBADO**, no cae en la excepción (B); la regla de no declarar `requires=` (`test_harness_flags_requires.py:316` solo compara specs con `requires` truthy); los topes 200/240/240 (`test_harness_flags_help.py:47-50`); el nombre de la variable del array en cada script (`HARNESS_TEST_FILES` en el `.sh:20`, `$HarnessTestFiles` en el `.ps1:13` — v1 nunca la nombró mal); los anclajes de `agent_runner.py:1029/1055/1082` y los 0 hits de `final_status` en `copilot_bridge.py`; y que los invariantes I1 e I2 **sí** se cumplen con el código escrito (I1 estructuralmente: la única regla que produce `exito` es inalcanzable desde base `error_real`).

**Corte recomendado (scope) — CORREGIDO otra vez en v4 (E3):** 9 fases / 6 archivos de test backend / 2 frontend / 5 flags / 3 `.tsx` es grande. Si hay que partirlo: **269 = F0..F5 + F7** (el veredicto y su superficie) y **`<primer número libre real>` = F6 + F8** (HITL de reconciliación y calibración). El corte es limpio porque F6 no depende de F0-F5.
> ⚠ **Historia de esta línea, porque se equivocó DOS veces:** el v2 decía "270 = F6 + F8" (270 ocupado). El v3 lo "arregló" diciendo **272** — que está **reservado por escrito** por el 271 (§6.1, *"un solo escritor de estado"*) **y** por el 270 (reconciliación masiva), y que el propio 270 **prohíbe hardcodear**. **La tercera versión no escribe ningún número:** se aplica el procedimiento de §0 (relistar en frío + grepear reservas por texto + saltar el 272). **Antes de escribir un número de plan, `ls "Stacky Agents/docs/"` Y `grep -rn "plan 27[0-9]"`.**
> **Numeración:** este plan nació como **267** y se **renumeró a 269** por colisión con una sesión paralela viva sobre el mismo árbol. Secuencia real verificada tras el renumerado: `267_PLAN_CATALOGO_UNICO_DE_ACCIONES_DEVOPS_...md` (sesión paralela, que a su vez renumeró de 266 a 267 en `07e3eae7`/`fc29e7cb`) y `268_PLAN_EXPLORADOR_DEL_GRAFO_DOCUMENTAL_...md` (`00704dee`). **269 es el primer número libre.** Todos los identificadores internos del plan (los 6 `test_plan269_*.py` y `plan269RunVerdict.test.ts`) se renumeraron junto con el archivo.

---

## 1. Objetivo e impacto

### Objetivo

El plan 254 clasificó **por qué terminó** una corrida mirando únicamente señales del **proceso** (código de salida, watchdog, reaper, marcadores de cuota). Este plan agrega la dimensión que falta y que el operador pidió textualmente: **si el proceso produjo resultados y cumplió su objetivo**. Para eso introduce una capa PURA de **veredicto por evidencia** que combina el `outcome_reason` ya existente con un conjunto de **señales de evidencia read-only** (entregable en disco, comentario publicado en el tracker, commit/PR abierto, gate de aceptación, verificación de ejecución) y produce un veredicto de **tres niveles** — **éxito / advertencia / error real** — con su causa y con la **lista explícita de evidencias presentes, ausentes y desconocidas**, para que el operador vea POR QUÉ. Ese veredicto se propaga a la **fila** de las listas (no solo al drawer de detalle), con filtro por nivel, y la reconciliación de 254 F5 deja de ser un contador mudo: pasa a ofrecer al humano un camino HITL para corregir un falso rojo concreto.

**El veredicto NUNCA cambia un estado por su cuenta.** Es una **dimensión separada** del `stacky_status`: se calcula **en tiempo de lectura**, no escribe una sola fila, y tiene un invariante duro codificado en test — **un run cuyo estado es `error` jamás puede recibir veredicto `exito`**, con ninguna combinación de evidencia. La única forma de convertir un rojo en verde sigue siendo un click del operador.

### KPI / impacto esperado

> **Anti-alucinación:** no se inventa el valor "hoy". La columna "hoy" se **mide** ejecutando el comando indicado **antes de tocar una línea** (paso 0 de F0) y se anota en este mismo documento. Un plan que declare un número sin haberlo corrido está mintiendo.

| # | KPI | Hoy (medir en F0 paso 0) | Meta | Cómo se mide (comando exacto) |
|---|---|---|---|---|
| K1 | Corridas terminadas en `error` que SÍ tienen evidencia de entrega (el falso error visible) | `SIN MEDIR` | Visible al 100% con veredicto `advertencia` + causa `falso_rojo_probable`, y **0** de ellas presentadas al operador como un rojo plano | **(C12 v2 — el comando de v1 nombraba un módulo inexistente)** `cd "Stacky Agents/backend" && .venv\Scripts\python.exe -c "from services.run_verdict import count_by_level; print(count_by_level(30))"` — la función se implementa en F8. **(D5 v3)** Devuelve una **muestra acotada** (`limit=200`, `sampled: true`), y `falso_rojo_probable` puede ser **`null`** si los colectores están OFF: `null` significa "no pude mirar" y **nunca** se reporta como `0`, porque `0` afirmaría que no hay falsos rojos |
| K6 | **[ADICIÓN ARQUITECTO A1]** Acuerdo observado del operador con el veredicto `falso_rojo_probable` | `SIN MEDIR` | Medible (no una meta numérica: es el instrumento que dice si los pesos y el umbral están bien calibrados) | `.venv\Scripts\python.exe -c "from services.run_verdict import verdict_agreement; print(verdict_agreement(30))"` — F8 |
| K2 | Degradaciones `completed`→`error` en 30 días (KPI heredado del 254) | `SIN MEDIR` | No sube (este plan no toca el cierre) | `cd "Stacky Agents/backend" && .venv\Scripts\python.exe -c "from services.error_fingerprints import count_falso_rojo_downgrades; print(count_falso_rojo_downgrades(30))"` — función real en `backend/services/error_fingerprints.py:50` |
| K3 | Niveles visibles en la **fila** de una lista de corridas | **1 dimensión** (`status` crudo vía `runStatusTone`, `frontend/src/pages/ExecutionHistoryPage.tsx:633`) | **2 dimensiones**: estado + veredicto de 3 niveles | **(D6 v3 — v2 grepeaba `verdictTone`, que NO es substring de `verdictChipTone`: el gate daba 0 para siempre)** `grep -c "verdictChipTone" frontend/src/pages/ExecutionHistoryPage.tsx` ≥ 1 |
| K4 | Items de reconciliación con camino HITL desde la UI | **0** (`RunReconciliationCard.tsx` renderiza solo contadores por `by_kind`, líneas 94-102; nunca renderiza `items`) | 100% de los items `red_with_delivered_work` con botón de corrección | `grep -c "items.map" frontend/src/components/RunReconciliationCard.tsx` ≥ 1 |
| K5 | Colectores de evidencia que pueden colgar una request | **N/A (no existen)** | **0**: todo colector tiene tope de tiempo y degrada a `None` (desconocido) | `.venv\Scripts\python.exe -m pytest tests/test_plan269_run_evidence.py -v` (test `test_colector_lento_degrada_a_desconocido`) |

---

## 2. Por qué ahora / el gap que cierra

El plan 254 dejó construido y **verificado en el árbol** (leído para este documento, no recordado):

- `backend/services/run_outcome.py` — módulo PURO con `OUTCOME_REASONS` (9 reasons, líneas 13-23), `classify_outcome_reason(...)` (línea 55) con orden de precedencia numerado en el docstring (líneas 71-83), `is_operator_actionable(reason)` (línea 104), `outcome_reason_to_status(reason)` (línea 113) → `{completed, needs_review, error}` vía `_REASON_TO_STATUS` (líneas 34-44).
- `backend/services/run_reconciliation.py` — chequeo read-only estado-vs-evidencia con `DISCREPANCY_KINDS` (línea 28), `evaluate()` PURA (línea 72), `scan_recent()` (línea 168) y `summarize()` (línea 217).
- `backend/services/status_vocabulary.py` — `TERMINAL_STATUSES` (línea 11), `NON_TERMINAL_TICKET_STATUSES` (línea 14), `VALID_TICKET_STATUSES` (línea 18).
- `backend/services/ticket_status.py` — `set_status(...)` con `guard_downgrade: bool = False` (línea 152) y la marca `blocked_downgrade` (línea 183); `on_execution_end(...)` (línea 293) que activa el guard leyendo `STACKY_TICKET_STATUS_NO_DOWNGRADE_ENABLED` (líneas 341-342).
- `frontend/src/utils/outcomeReason.ts` — `OutcomeTone` (línea 12), `OUTCOME_REASON_LABELS` (línea 22), `describeOutcomeReason()` (línea 62), `dirtyCloseNotice()` (línea 86).
- Tests: `backend/tests/test_plan254_falso_rojo.py`, `test_plan254_outcome_reason.py`, `test_plan254_reconciliation.py`, `test_plan254_stream_drain.py` (los 4 registrados en el arnés, ver §3.7).

### Los 3 gaps — VERIFICADOS uno por uno contra el árbol

**GAP 1 — CONFIRMADO. `classify_outcome_reason` no consulta evidencia de entregable.**
Su firma completa (`backend/services/run_outcome.py:55-65`) acepta exactamente 8 parámetros: `return_code`, `result_ok_seen`, `stall_fired`, `stderr_excerpt`, `last_result_text`, `ticket_already_terminal`, `reaper_kind`, `preflight_block`. **Ninguno** es evidencia de entregable: no hay artefactos en disco, ni comentario publicado, ni commit/PR, ni gate de aceptación. Los 4 call-sites reales confirman que solo se le pasan señales de proceso: `agent_runner.py:1117`, `services/agent_completion.py:67`, `services/codex_cli_runner.py:755`, `services/claude_code_cli_runner.py:1865`. El más elocuente es `agent_completion.py:66-71`, que **sintetiza** `return_code=0 if payload.status == "completed" else 1` — es decir, en el camino de auto-reporte el "código de salida" es una ficción derivada de lo que el propio agente dijo. **Diagnóstico del orquestador: correcto.**

**GAP 2 — CONFIRMADO, y peor de lo enunciado.** `frontend/src/utils/outcomeReason.ts` tiene exactamente **dos** consumidores en todo el frontend: `components/ExecutionDetailDrawer.tsx:18` (el drawer) y su propio test `utils/__tests__/plan254OutcomeReason.test.ts:6`. **Ninguna lista lo importa.** Además:
- `pages/ExecutionHistoryPage.tsx:633` pinta la fila con `runStatusTone(item.status)` / `runStatusLabel(item.status)` de `utils/runStatus.ts`, que mapea el status crudo a 5 tonos (`"success" | "warning" | "danger" | "info" | "neutral"`, `utils/runStatus.ts:1`) — **una sola dimensión**, sin causa ni evidencia.
- `pages/TicketBoard.tsx` no tiene módulo puro de estado: los colores son un dict inline `ADO_STATE_COLORS` (`pages/TicketBoard.tsx:82`) y un helper local no exportado `stateColor()` (`pages/TicketBoard.tsx:103`), pintados con estilo inline en `pages/TicketBoard.tsx:496-499`.
- `pages/IncidentInboxPage.tsx:503` dibuja `item.ado_state` como badge crudo, sin tono.

**GAP 3 — CONFIRMADO.** `backend/services/run_reconciliation.py` es read-only por diseño explícito (docstring líneas 7-13: *"No cambia ningún estado. No reintenta, no publica, no decide. Lista."*) y su `summarize()` (línea 217) **sí** devuelve `items` con `execution_id`/`ticket_id`/`kind`/`detail`. Pero la UI **tira esa lista a la basura**: `frontend/src/components/RunReconciliationCard.tsx` solo itera `report.by_kind` (líneas 95-101) para mostrar contadores. `items` **nunca se renderiza** y no hay ningún botón de acción. El operador sabe que hay 7 falsos rojos y no tiene forma de tocar ninguno.

### Corrección al diagnóstico recibido

El brief del orquestador indicaba que el dueño del desenlace de Copilot vive en `agent_runner.py:1015/1040/1067`. **Las líneas reales hoy son `agent_runner.py:1029`, `:1055` y `:1082`** (los tres `_ts.on_execution_end(...)` con `final_status="completed"`, `"cancelled"` y `"error"` respectivamente). Lo que **sí** se confirma literalmente es que `backend/copilot_bridge.py` tiene **0 ocurrencias** de `final_status` (`grep -c final_status copilot_bridge.py` = 0), tal como lo documenta el propio comentario en `agent_runner.py:1104`. Se corrige el anclaje aquí para que nadie implemente contra la línea equivocada.

**Consecuencia arquitectónica de ese dato:** este plan **no toca ningún sitio de cierre**. El veredicto se calcula **en tiempo de lectura** (cuando se sirve el payload), no en el cierre. Por eso la paridad de los 3 runtimes es **estructural, no negociada**: los tres escriben `AgentExecution`, y de ahí lee el veredicto. Ver §4, principio P3.

---

## 3. Evidencia real (anclaje anti-alucinación)

Toda ruta es relativa a `Stacky Agents/`. Todo símbolo fue abierto y leído.

### 3.1 Módulos del 254 que se REUSAN (no se reescriben)

| Símbolo | Ubicación | Qué aporta al 269 |
|---|---|---|
| `OUTCOME_REASONS` (9 tuplas) | `backend/services/run_outcome.py:13` | Entrada del veredicto |
| `outcome_reason_to_status(reason)` | `backend/services/run_outcome.py:113` | Deriva el **nivel base** del veredicto |
| `is_operator_actionable(reason)` | `backend/services/run_outcome.py:104` | Ya expuesto en el payload (`api/executions.py:85`) |
| `VALID_TICKET_STATUSES` | `backend/services/status_vocabulary.py:18` | Vocabulario congelado; **el 269 NO agrega estados** |
| `DISCREPANCY_KINDS` / `summarize()` | `backend/services/run_reconciliation.py:28` / `:217` | Base del HITL de F6 |
| `OutcomeTone` | `frontend/src/utils/outcomeReason.ts:12` | Tipo de tono **reusado**, no redefinido |
| `describeOutcomeReason()` | `frontend/src/utils/outcomeReason.ts:62` | Etiqueta de la causa en el drawer |

### 3.2 Fuentes de evidencia — todas existen y todas son de solo lectura

| Señal | Fuente verificada | Anclaje |
|---|---|---|
| `entregable_presente` | Columna `AgentExecution.html_output_path` (String 500) y columna `AgentExecution.output` (Text) | `backend/models.py:272` y `backend/models.py:258` |
| `publicado_en_tracker` | Tabla `agent_html_publish`, modelo `AgentHtmlPublish` con `execution_id` (`:135`), `status` (`:144`) y `comment_id` (`:153`). ⚠ **v4 (E7): `status` tiene CUATRO valores — `ok`, `failed`, `skipped` e `idempotent_replay` — y el comentario de la columna en `:144` (`# ok \| skipped \| failed`) está DESACTUALIZADO.** No creerle al comentario: el censo de los literales que el escritor produce está en F1 (D2). Escritor **único** en todo `backend/`: `:889`. | `backend/services/ado_publisher.py:122-184` (la clase va hasta `:184`; las columnas terminan en `:154`) |
| `cambio_en_repo` | Sidecar JSON por ejecución; campos escritos por `mark_intent(...)`: `pr_id, pr_url, branch, status, error, files_committed, origin`. **(C7/C14 v2)** La ruta se arma en `_intent_dir()` (`:192-196`) + `_intent_path()` (`:199-200`) = `data_dir()/incident_dev_pr/{execution_id}.json`. **NO se usa `get_intent()`**: `_intent_dir()` hace `mkdir(parents=True, exist_ok=True)` y eso **crea un directorio**, violando el riel P4. F1 lee el archivo directo. | `backend/services/incident_dev_pr.py:192-196`, `:199-200`, `:223-228` (escritor) |
| `gate_aceptacion_ok` | Columna `AgentExecution.contract_result_json` + property `contract_result` | `backend/models.py:261` y `backend/models.py:309` |
| `verificacion_ok` | **HECHO, ya no hipótesis (C5 v2).** Clave `metadata["exec_verification"]`, campo **`passed`** (`bool \| None`). Lo produce `VerificationReport.to_metadata()` en `backend/services/exec_verification.py:79-96`; el campo se declara en `:70` con el comentario literal *"None = no hay nada que verificar / could-not-verify"*. **NO es `ok`.** | Productor: `services/exec_verification.py:70,81`. Consumidores que lo confirman: `api/exec_verification.py:43`, `harness/post_run.py:189-191`, `services/harness_health.py:848`, `tests/test_exec_verification.py:330-331`. Lectura desde el modelo: `backend/models.py:301` (`metadata_dict`) |

### 3.3 Metadata de ejecución ya poblada por el 254 (se lee, no se escribe)

`run_reconciliation.scan_recent()` demuestra qué claves existen en `AgentExecution.metadata_dict`: `exit_code` (`backend/services/run_reconciliation.py:195`), `finalized_after_result` (`:202`), `outcome_reason` (`:209`), `drain_timed_out` (`:212`).

### 3.4 Puntos de inyección del payload de ejecuciones — son **DOS**, no uno (C2 v2)

Este es el error que hundió a v1. Hay **dos** rutas de ejecuciones con **dos formas distintas** de armar el payload, y la página del historial consume la SEGUNDA:

| # | Ruta | Handler | Cómo arma el payload | ¿Pasa por `_with_outcome`? | Quién la consume |
|---|---|---|---|---|---|
| 1 | `GET /api/executions` | `list_executions()` — `backend/api/executions.py:96` | `r.to_dict(include_output=False, include_ticket_context=True)` (`:154`) | **Sí** (`:159`) | `Executions.list(...)`, drawer de detalle |
| 2 | `GET /api/executions/history` | `executions_history()` — `backend/api/executions.py:442` | **A mano, dict por dict** (`:538-559`) | **NO** | **`ExecutionHistoryPage.tsx`** vía `Executions.history()` → `ExecutionHistoryItem` (`frontend/src/api/endpoints.ts:1303`) |

Consecuencias que v2 respeta:
- **F2 debe cablear los DOS handlers.** Cablear solo el (1) deja F4 y el KPI K3 completamente inertes.
- El handler (2) está gateado por `STACKY_EXECUTION_HISTORY_ENABLED` (`:459-460`) y tiene **dos formas de respuesta**: lista pelada, o `{items, total}` con `?include_total=1` (`:561-564`). El veredicto se inyecta **antes** de ese `if`, sobre `items`.
- El handler (1) hace `q.options(joinedload(AgentExecution.ticket))` (`:130`), así que `getattr(ex, "ticket", None)` **no** es N+1 ahí. El handler (2) hace `.join(Ticket, ...)` (`:482`), que **no** es eager-load: ahí `row.ticket` ya es un lazy-load preexistente (`models.py:275`, `lazy="select"` por default) y este plan **no lo empeora ni lo arregla** — usa la variable `meta` que el handler ya calculó (`:539`).

**Patrón anti-N+1 a copiar:** `_with_outcome(d, dirty_ids)` (`:65`) promueve `outcome_reason` (`:81`) y `outcome_actionable` (`:85`), gateado por `_outcome_badge_enabled()` (`:28`); `_dirty_close_execution_ids(session, execution_ids)` (`:35`) resuelve **todo el lote en UNA query** (`:48-53`). **F2 sigue exactamente ese patrón.** El módulo **ya tiene** `logger` (`:25`), así que el `logger.debug` de F2 compila.

### 3.4-bis La clave `verdict` YA ESTÁ OCUPADA (C1 v2) — la nueva se llama `run_verdict`

`AgentExecution.verdict` es una **columna real** (`backend/models.py:255`, `Mapped[str | None] = mapped_column(String(20))`) que guarda el veredicto de **revisión humana** (`approved` / `rejected` / `discarded`), y `AgentExecution.to_dict()` la emite tal cual: `"verdict": self.verdict` (`backend/models.py:327`). En el frontend la consumen `AgentHistoryModal.tsx:127-134` (vía `last_execution_verdict`, `endpoints.ts:992`) y `DailyStandupModal.tsx:13`.

**Por eso la clave nueva de este plan se llama `run_verdict`, nunca `verdict`.** Pisarla destruiría un campo vivo de otro tipo y rompería `tsc`. Gate en el DoD: `grep -c '"verdict"' backend/services/run_verdict.py` = **0**.

### 3.4-ter El historial de ejecuciones es una tabla con COLUMNAS CONFIGURABLES (C3 v2)

`frontend/src/pages/ExecutionHistoryPage.tsx` **no** es una tabla estática:
- Las columnas se declaran en `frontend/src/services/tablePrefs.ts:27-41` (`HISTORY_COLUMNS: ColumnDef[]`, hoy 10 entradas: `inicio, agente, runtime, modelo, estado, duracion, costo, prompt, archivos, ticket`).
- Cada `<th>` (`:525-545` en adelante) y cada `<td>` (`:614-645` en adelante) está envuelto en `isColVisible(tablePrefs, "<id>")`.
- El selector de columnas recibe `columns={HISTORY_COLUMNS}` (`:454`) y las prefs se sanean con `sanitizeTablePrefs(raw, HISTORY_COLUMNS)` (`:102`, `:237`).

**Un `<td>` sin su `<th>` y sin su `isColVisible` desalinea la tabla apenas el operador oculte cualquier columna.** F4 registra la columna en `HISTORY_COLUMNS` y guarda ambas celdas.

### 3.4-quater `backend/api/incident_inbox.py` NO TIENE `logger` (C4 v2)

`grep -c logger backend/api/incident_inbox.py` = **0**. El módulo ni siquiera importa `logging` (sus imports son `from __future__ import annotations` en `:6` y `from flask import Blueprint, jsonify, request` en `:8`). Cualquier `logger.debug(...)` en un `except` de ese archivo lanza `NameError` **desde el handler de excepción**, convirtiendo una degradación silenciosa en un 500. **F5 declara el logger como paso 1.**

### 3.5 Superficies de UI

| Superficie | Archivo:línea | Qué hay hoy |
|---|---|---|
| Fila del historial de ejecuciones | `frontend/src/pages/ExecutionHistoryPage.tsx:632-634` | `{isColVisible(tablePrefs, "estado") && (<td><StatusChip tone={runStatusTone(item.status)} size="sm">{runStatusLabel(item.status)}</StatusChip></td>)}` — **el `<td>` está envuelto en `isColVisible`** (C3) |
| Cabecera de esa tabla | `frontend/src/pages/ExecutionHistoryPage.tsx:507` (`<thead>`), `:525-545` (los `<th>`) | Cada `<th data-col="...">` bajo `isColVisible` |
| Declaración de columnas | `frontend/src/services/tablePrefs.ts:27-41` | `HISTORY_COLUMNS` con 10 entradas |
| Confirmación canónica del repo | `frontend/src/components/ui/index.ts` (plan 164) | `useConfirm` / `useAlert` / `useTextPrompt` desde `DialogHost`; patrón de uso real: `ActiveRunsPanel.tsx:7,33` y `components/AgentHistoryPage.tsx:10,253` *(D11 v3: vive en `components/`, NO en `pages/`)* (`const askConfirm = useConfirm()`) |
| Tipo de la fila del historial | `frontend/src/api/endpoints.ts:1303` | `interface ExecutionHistoryItem` (**20** campos, cuerpo `:1304-1323`; **no** tiene `verdict`) *(D11 v3: v2 decia 21)* |
| Filtro de estado del historial | `frontend/src/pages/ExecutionHistoryPage.tsx:400-401` | select por `filters.status` |
| Import de `runStatus` | `frontend/src/pages/ExecutionHistoryPage.tsx:30` | `runStatusTone, runStatusLabel` |
| Fila de la bandeja de incidencias | `frontend/src/pages/IncidentInboxPage.tsx:488` | Literal REAL: `<div key={item.id} className={styles.row}>` *(D11 v3: v2 omitia el `key`)*; badges en `:503-507`. **Zona de colision con el 270 - anclar por simbolo (§0)** |
| Endpoint de la bandeja | `backend/api/incident_inbox.py:160-164` | Arma `items` desde `t.to_dict()`; comentario explícito en `:149`: *"Sin N+1: NO se consulta AgentExecution"* |
| Card de reconciliación | `frontend/src/components/RunReconciliationCard.tsx:94-102` | Solo `by_kind`; `items` sin usar |
| Cliente HTTP de reconciliación | `frontend/src/api/endpoints.ts:3167-3175` | `RunReconciliation.get()` con `fetch` crudo (no `api.get`, porque lanza en non-2xx) |
| Drawer de detalle | `frontend/src/components/ExecutionDetailDrawer.tsx:80` y `:85` | Ya consume `describeOutcomeReason` y `dirtyCloseNotice` |

### 3.6 Endpoint HITL que se REUSA (y el que está PROHIBIDO usar)

- **SE USA:** `PATCH /api/tickets/<int:ticket_id>/stacky-status` — `backend/api/tickets.py:1165`. Su cuerpo es `{ "status": ..., "reason": ... }` (`:1169-1170`), toma el usuario de `X-User-Email` (`:1178`) y llama **directamente** `ts.set_status(...)` (`:1189-1194`) **sin** `guard_downgrade` (queda en su default `False`, `services/ticket_status.py:152`) y **sin** publicar nada ni correr post-hooks.
- **PROHIBIDO:** `PATCH /api/tickets/by-ado/<int:ado_id>/stacky-status` — `backend/api/tickets.py:1204`. Ese camino **SÍ publica en ADO** (`backend/api/tickets.py:1406` `publish.succeeded`) y **SÍ puede cambiar el estado del work item en ADO** (`:1495` `ado state changed`). Usarlo convertiría una corrección local en una escritura en el tracker real del operador. **Un modelo menor NO debe confundir estos dos endpoints.**

### 3.7 Receta REAL de alta de flag (verificada, no recordada) — "RECETA-FLAG"

Toda flag nueva se da de alta en **5 lugares de código + 2 archivos de arnés**. Saltarse cualquiera deja un test ROJO.

| # | Archivo | Qué agregar | Anclaje del patrón a copiar |
|---|---|---|---|
| 1 | `backend/config.py` | `STACKY_X: bool = os.getenv("STACKY_X", "true").lower() in ("1", "true", "yes")` | `backend/config.py:2072-2073` |
| 2 | `backend/services/harness_flags.py` | Un `FlagSpec(key=..., type="bool", label=..., description=..., group="global", default=True)` en el registro | `backend/services/harness_flags.py:5213-5224` |
| 3 | `backend/services/harness_flags.py` | La key dentro de la tupla de la categoría en `_CATEGORY_KEYS` (dict declarado en `:120`) | La tupla `observabilidad_notif` **abre en `:305`**; `:324` es una línea **miembro** (las 2 keys del 254) y sirve como punto de inserción. *(D11 v3: v2 presentaba `:324` como la declaración de la tupla)* |
| 4 | `backend/services/harness_flags_help.py` | Una entrada `PlainHelp(what=..., on_effect=..., off_effect=..., example=...)` en el dict `PLAIN_HELP` | `backend/services/harness_flags_help.py:1789-1794` |
| 5 | `backend/tests/test_harness_flags.py` | La key dentro del set `_CURATED_DEFAULTS_ON` | `backend/tests/test_harness_flags.py:520-523` |
| 6 | `backend/scripts/run_harness_tests.sh` | La ruta del test nuevo, **sin comillas y sin coma**, dentro del array bash | `backend/scripts/run_harness_tests.sh:849-852` |
| 7 | `backend/scripts/run_harness_tests.ps1` | La ruta del test nuevo, **con comillas dobles y con coma** (salvo el último elemento), dentro del array PowerShell | `backend/scripts/run_harness_tests.ps1:762-765` |

**Topes duros del texto de `PlainHelp`** (test real `backend/tests/test_harness_flags_help.py:47-51`) — son **CINCO**, no cuatro (**D12 v3**):
- `what` ≥ 10 caracteres (`:47`) y ≤ **200** (`:48`).
- `on_effect` ≤ **240** (`:49`).
- `off_effect` ≤ **240** (`:50`).
- `example` ≤ **300** (`:51`) — **v2 no lo declaraba.**

> **Medido, no supuesto (v3):** los 5 textos de `PlainHelp` que F7 propone se pasaron por los **5** topes reales con el venv: **todos entran, incluido el 5º**. No hay que reescribir ninguno.

**Regla dura sobre `requires`:** **ninguna** flag de este plan declara `requires=`. Motivo verificado: `backend/tests/test_harness_flags_requires.py:316` compara el mapa **completo** por igualdad (`assert actual == _REQUIRES_MAP_FROZEN`, mapa congelado en `:120`), así que declarar un `requires` obliga a editar también ese archivo o el test queda rojo. Las dependencias entre flags de este plan se resuelven **en código** (una función lee las dos flags), no en el registro. Ver F2 paso 3.

### 3.8 Gotchas del repo que este plan respeta

1. **Tests de backend por archivo.** `SQLITE_LOCKED` bajo pytest con shared cache es flaky. Cada comando de aceptación de este plan nombra **un solo archivo**.
2. **`@testing-library/react` y `jsdom` NO están instalados** (`frontend/package.json` devDependencies: solo `@types/react`, `@types/react-dom`, `@vitejs/plugin-react`, `typescript`, `vite`, `vitest@^4.1.9`). Toda lógica de UI de este plan va en módulos `.ts` **puros**; el render NO se testea.
3. **Vitest se corre por archivo** con `npx vitest run <ruta>` (no hay script `test` en `frontend/package.json`; la contaminación cross-file está documentada).
4. **Ratchet de cero inline-style en `.tsx` nuevos.** Este plan **no crea ningún `.tsx` nuevo**: edita tres `.tsx` existentes y todo estilo va por CSS Module.
5. **Se lee la INSTANCIA `config.config`, nunca el módulo.** Patrón obligatorio: `import config as _config` + `getattr(_config.config, "STACKY_X", True)` (ver `backend/api/executions.py:30-32`).
6. **(v2, C4) Antes de escribir `logger.` en un módulo, verificar que ese módulo TENGA logger.** `api/executions.py` lo tiene (`:25`); `api/diag.py` lo tiene; **`api/incident_inbox.py` NO** (0 ocurrencias). Un `logger` inexistente dentro de un `except` convierte una degradación silenciosa en un 500.
7. **(v2, C7) Un lector "de solo lectura" del repo puede escribir igual.** `incident_dev_pr.get_intent()` parece un getter pero su cadena hace `mkdir` (`:192-196`). Antes de usar un helper ajeno en un colector con riel "no escribe nada", leer su cuerpo entero, no su nombre.
8. **(v2, C1) Antes de agregar una clave a un payload, verificar que no exista.** `to_dict()` de `AgentExecution` (`models.py:315-350`) ya emite 18 claves; `verdict` es una de ellas.

---

## 4. Principios y guardarraíles

- **P1 — Prohibido crear un falso VERDE nuevo.** Invariante `I1`, codificado en test: para **toda** combinación de evidencia, si el estado terminal del run es `error`, el nivel del veredicto **nunca** es `exito`. **(v3, D1) Y se prueba en la SUPERFICIE, no solo en el módulo:** el veredicto se ancla en `run_status`; el `stacky_status` del ticket es una señal secundaria que solo puede **empeorar** el nivel. Un ticket verde **jamás** blanquea un run rojo. Verificado corriendo sobre la grilla completa de **17.010** combinaciones (**0** violaciones) más **68.040** casos de monotonicidad (el ticket mejoró el nivel en **0**), y con un test de borde contra los dos endpoints (A3). El techo al que puede subir un rojo es `advertencia` ("probable falso rojo, revisalo"). Esto es la lección C6 del 254 llevada a código ejecutable.
- **P2 — La ignorancia nunca mejora el veredicto.** Invariante `I2`, codificado en test: una señal `None` (desconocida) produce un nivel **igual o peor** que la misma señal en `False`. Nunca mejor. Si una fuente no está disponible, el veredicto degrada; jamás fabrica confianza.
- **P3 — Lectura, no cierre.** El veredicto se computa **en tiempo de lectura del payload**, no en el sitio de cierre. Consecuencias: (a) paridad de los 3 runtimes gratis, porque los tres escriben `AgentExecution` y de ahí lee el veredicto; (b) cero riesgo de regresión sobre el cierre que 254 acaba de estabilizar; (c) backward-compatible por construcción — nada existente cambia de forma.
- **P4 — Solo lectura absoluta en los colectores.** Ningún colector escribe, crea, mueve ni borra. Todos tienen tope de tiempo y degradan a `None`. Un colector que falla **jamás** rompe el listado.
- **P5 — El veredicto es una DIMENSIÓN SEPARADA, no un estado.** `status_vocabulary.py` **no se toca**: no se agrega ni un estado. El payload gana **una** clave nueva llamada **`run_verdict`** (nunca `verdict`, que ya está ocupada — §3.4-bis); `stacky_status` sigue significando exactamente lo mismo que ayer.
- **P9 — Un run que no terminó NO tiene veredicto (v2, C9).** Para `idle` y `running`, `evaluate_verdict` devuelve `None` y el payload no trae la clave. Juzgar algo que todavía está pasando es inventar. La ausencia de veredicto es información honesta; un "advertencia" por defecto habría pintado de amarillo toda la lista de corridas activas.
- **P6 — Human-in-the-loop innegociable.** Stacky nunca cambia un estado terminal a partir del veredicto. La única corrección la dispara el humano con un click, contra un endpoint que **no publica en ningún sistema externo** (§3.6).
- **P7 — Cero trabajo para el operador.** Todo es invisible y automático. Las 5 flags nacen **ON**. No hay ni una decisión nueva que tomar para que el sistema mejore.
- **P8 — Sin autonomía proactiva.** Nada de este plan corre en un loop, daemon, barrido ni polling. Todo se computa cuando el operador ya estaba pidiendo esos datos.

---

## 5. Fases

### F0 — Capa PURA de veredicto (`run_verdict.py`)

**Objetivo (1 frase):** Un módulo puro que, dado el `outcome_reason` del 254 más un conjunto de señales tri-estado de evidencia, devuelve un veredicto de 3 niveles con su causa y el detalle de qué evidencia hay y qué falta.

**Valor:** Es el corazón del plan. Sin él, "diferenciar errores reales de falsos positivos" queda en prosa. Puro ⇒ testeable sin base, sin red y sin runtime.

**Paso 0 (obligatorio, antes de escribir código):** medir el KPI K2 y anotarlo en la tabla de §1:
```
cd "Stacky Agents/backend"
.venv\Scripts\python.exe -c "from services.error_fingerprints import count_falso_rojo_downgrades; print(count_falso_rojo_downgrades(30))"
```

**Archivo a crear:** `Stacky Agents/backend/services/run_verdict.py`
**Archivo de test a crear:** `Stacky Agents/backend/tests/test_plan269_run_verdict.py`

**Contenido EXACTO del módulo (nombres congelados):**

```python
"""Plan 269 F0 — veredicto por evidencia. Módulo PURO.

Sin DB, sin red, sin disco, sin imports de `db`/`models`. Se testea solo.

El plan 254 respondió "POR QUÉ terminó así" mirando el proceso. Este módulo
responde la otra mitad que pidió el operador: "¿produjo resultados y cumplió
su objetivo?". El veredicto es una DIMENSIÓN SEPARADA de `stacky_status`: no
es un estado nuevo y NUNCA cambia uno.
"""
from __future__ import annotations

from dataclasses import dataclass          # v4 (E9): `field` NO se usa — importarlo es F401

# Los 3 niveles, de mejor a peor. Cerrado: no se agregan niveles.
VERDICT_LEVELS = ("exito", "advertencia", "error_real")

# Causa del veredicto. Cerrado. Toda causa mapea a exactamente un nivel.
# v2 (C8): son NUEVE. `cancelado_por_el_operador` se separó de
# `cierre_sucio_pendiente_de_revision` porque un run que el humano cortó a mano
# NO cerró mal, y decirle al operador "el proceso cerró mal" es mentirle.
VERDICT_CAUSES = (
    "cierre_limpio_con_entrega",           # exito
    "verde_sin_evidencia",                 # advertencia
    "evidencia_indeterminada",             # advertencia
    "cierre_sucio_pendiente_de_revision",  # advertencia
    "cancelado_por_el_operador",           # advertencia  ← v2 C8
    "falso_rojo_probable",                 # advertencia  ← el caso que pidió el operador
    "espera_cuota",                        # advertencia
    "error_sin_entrega_suficiente",        # error_real
    "bloqueado_antes_de_empezar",          # error_real
)

# Nombres de las señales de evidencia. Cerrado y ORDENADO (el orden se usa para
# serializar las listas presentes/ausentes/desconocidas de forma determinista).
EVIDENCE_SIGNALS = (
    "publicado_en_tracker",
    "cambio_en_repo",
    "gate_aceptacion_ok",
    "verificacion_ok",
    "entregable_presente",
)

# Peso de cada señal. Las 3 "fuertes" valen 2 porque son objetivas y externas al
# propio agente (una fila en agent_html_publish, un PR abierto, un gate que
# corrió). Las 2 "débiles" valen 1: un archivo en disco o una verificación
# pueden ser parciales.
_PESO = {
    "publicado_en_tracker": 2,
    "cambio_en_repo": 2,
    "gate_aceptacion_ok": 2,
    "verificacion_ok": 1,
    "entregable_presente": 1,
}
UMBRAL_ENTREGA = 2  # fuerza mínima para considerar que "produjo resultados"

# Nivel base derivado del estado terminal. `cancelled` es advertencia: el humano
# lo cortó, no es un fallo del sistema (y en v2 tiene causa propia, C8).
# Las CLAVES son exactamente los 4 TERMINAL_STATUSES de
# services/status_vocabulary.py:11. Los 2 NO terminales (`idle`, `running`,
# status_vocabulary.py:14) NO están acá A PROPÓSITO: ver `_NO_TERMINALES`.
_STATUS_TO_BASE = {
    "completed": "exito",
    "needs_review": "advertencia",
    "cancelled": "advertencia",
    "error": "error_real",
}

# v2 (C9): un run que NO terminó no tiene veredicto. Devolver "advertencia" para
# un run en curso pintaba "Con advertencias" TODA la lista de corridas activas.
_NO_TERMINALES = frozenset({"idle", "running"})

_CAUSE_TO_LEVEL = {
    "cierre_limpio_con_entrega": "exito",
    "verde_sin_evidencia": "advertencia",
    "evidencia_indeterminada": "advertencia",
    "cierre_sucio_pendiente_de_revision": "advertencia",
    "cancelado_por_el_operador": "advertencia",
    "falso_rojo_probable": "advertencia",
    "espera_cuota": "advertencia",
    "error_sin_entrega_suficiente": "error_real",
    "bloqueado_antes_de_empezar": "error_real",
}


@dataclass(frozen=True)
class EvidenceSignals:
    """Tri-estado por señal: True=presente, False=ausente, None=DESCONOCIDA.

    `None` es un valor de primera clase: significa "no pude mirar". Nunca se
    convierte en False silenciosamente (eso sería inventar evidencia negativa)
    ni en True (eso sería inventar un verde)."""

    publicado_en_tracker: bool | None = None
    cambio_en_repo: bool | None = None
    gate_aceptacion_ok: bool | None = None
    verificacion_ok: bool | None = None
    entregable_presente: bool | None = None

    def get(self, name: str) -> bool | None:
        return getattr(self, name, None)


@dataclass(frozen=True)
class RunVerdict:
    level: str                       # ∈ VERDICT_LEVELS
    cause: str                       # ∈ VERDICT_CAUSES
    strength: int                    # fuerza de entrega acumulada
    present: tuple[str, ...] = ()    # señales True, en orden de EVIDENCE_SIGNALS
    absent: tuple[str, ...] = ()     # señales False
    unknown: tuple[str, ...] = ()    # señales None

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "cause": self.cause,
            "strength": self.strength,
            "present": list(self.present),
            "absent": list(self.absent),
            "unknown": list(self.unknown),
        }


def delivery_strength(signals: EvidenceSignals) -> int:
    """Suma los pesos de las señales PRESENTES. `None` y `False` suman 0.

    Que None y False sumen igual es deliberado: la ignorancia no puede sumar
    confianza (principio P2)."""
    return sum(_PESO[name] for name in EVIDENCE_SIGNALS if signals.get(name) is True)


def _peor(a: str, b: str) -> str:
    """v3 (D1) — devuelve el PEOR de dos niveles base. Nunca el mejor.

    Es el mecanismo que hace que el invariante I1 valga en TODOS los call-sites
    y no solo adentro de esta función."""
    return a if VERDICT_LEVELS.index(a) >= VERDICT_LEVELS.index(b) else b


def evaluate_verdict(
    *,
    run_status: str,                       # ← v3 D1: OBLIGATORIO. El estado del RUN manda.
    ticket_status: str | None = None,      # ← v3 D1: opcional. Solo puede EMPEORAR.
    outcome_reason: str | None = None,
    signals: EvidenceSignals | None = None,
) -> RunVerdict | None:
    """Devuelve un RunVerdict, o None si el run NO terminó. Puro y determinístico.

    ══════════════════════════════════════════════════════════════════════════
    v3 (D1) — CAMBIO DE CONTRATO. LEER ANTES DE CABLEAR.
    ══════════════════════════════════════════════════════════════════════════
    v2 recibía UN solo estado y los call-sites (F2 y F5) le pasaban el estado del
    TICKET con el del run como respaldo:

        estado = (getattr(ticket, "stacky_status", None) or ex.status or "")   # ← BUG

    Eso rompe el invariante de negocio. Un ticket que hoy está `completed`
    (segundo intento OK, o el operador lo cerró a mano) con una ejecución vieja
    de `status="error"` producía veredicto **`exito` / `cierre_limpio_con_entrega`**.
    Y como el historial lista EJECUCIONES (N filas por ticket), TODAS las
    corridas fallidas de un ticket ya cerrado se pintaban "Terminó bien" al lado
    del chip "Error". Es el falso VERDE que P1 prohíbe. El test I1 de v2 seguía
    verde porque probaba esta función, no el cableado.

    REGLA v3, innegociable:
      · El veredicto se ANCLA en `run_status`. Es la única fuente del nivel base.
      · `ticket_status` es una señal SECUNDARIA que solo puede EMPEORAR el nivel
        (`_peor`), jamás mejorarlo. Un ticket verde NO blanquea un run rojo.
      · Con esto I1 vale ESTRUCTURALMENTE en todo call-site: si `run_status ==
        "error"`, base es `error_real` y ninguna regla puede devolver `exito`.
    ══════════════════════════════════════════════════════════════════════════

    v2 (C9): `None` para `idle`/`running`. Un run en curso NO tiene veredicto —
    devolverle "advertencia" pintaba de amarillo toda la lista de corridas
    activas. `None` significa "todavía no hay nada que juzgar" y la UI no dibuja
    chip (describeVerdict(null) → null, F3).

    ORDEN DE PRECEDENCIA OBLIGATORIO — se evalúa en este orden y se devuelve en
    el PRIMER match. Sin este orden, dos reglas pueden matchear y el resultado
    es ambiguo para un modelo menor.

      0. run_status ∈ {"idle","running"} o vacío       → None (sin veredicto)  ← C9 + D1
      1. outcome_reason == "preflight_blocked"        → bloqueado_antes_de_empezar (error_real)
      2. outcome_reason == "quota_exhausted"          → espera_cuota (advertencia)
      3. base == "error_real" y fuerza >= UMBRAL      → falso_rojo_probable (advertencia)
      4. base == "error_real"                         → error_sin_entrega_suficiente (error_real)
      5. run_status == "cancelled"                    → cancelado_por_el_operador (advertencia)  ← v2 C8
      6. base == "advertencia"                        → cierre_sucio_pendiente_de_revision
      7. base == "exito" y fuerza >= UMBRAL           → cierre_limpio_con_entrega (exito)
      8. base == "exito" y hay alguna señal None      → evidencia_indeterminada (advertencia)
      9. base == "exito" (resto)                      → verde_sin_evidencia (advertencia)

    Nota sobre 7 antes de 8: si ya hay UMBRAL de evidencia PRESENTE, una señal
    desconocida al lado no borra la evidencia que sí está. No fabrica un verde
    porque el base ya era verde (la regla 7 es inalcanzable desde un estado rojo:
    ahí está la garantía ESTRUCTURAL del invariante I1).

    Nota sobre 5 después de 3/4: un `cancelled` nunca llega a base "error_real",
    así que el orden entre ellas no cambia nada; se deja explícito para que el
    lector no tenga que razonarlo.

    Un `run_status` desconocido (ni terminal ni no-terminal) cae a base
    "advertencia" — nunca a un verde.
    """
    estado = (run_status or "").strip()
    if not estado or estado in _NO_TERMINALES:
        return None

    sig = signals or EvidenceSignals()
    base = _STATUS_TO_BASE.get(estado, "advertencia")

    # v3 (D1) — el ticket solo EMPEORA. Si el ticket está peor que el run (p.ej.
    # el operador marcó la incidencia `error` sobre un run `completed`), el
    # veredicto baja. Si el ticket está MEJOR, se IGNORA: un ticket verde jamás
    # blanquea un run rojo. Un ticket no terminal o desconocido no opina.
    t_estado = (ticket_status or "").strip()
    if t_estado in _STATUS_TO_BASE:
        base = _peor(base, _STATUS_TO_BASE[t_estado])

    fuerza = delivery_strength(sig)

    present = tuple(n for n in EVIDENCE_SIGNALS if sig.get(n) is True)
    absent = tuple(n for n in EVIDENCE_SIGNALS if sig.get(n) is False)
    unknown = tuple(n for n in EVIDENCE_SIGNALS if sig.get(n) is None)

    if outcome_reason == "preflight_blocked":
        cause = "bloqueado_antes_de_empezar"
    elif outcome_reason == "quota_exhausted":
        cause = "espera_cuota"
    elif base == "error_real" and fuerza >= UMBRAL_ENTREGA:
        cause = "falso_rojo_probable"
    elif base == "error_real":
        cause = "error_sin_entrega_suficiente"
    elif estado == "cancelled":
        cause = "cancelado_por_el_operador"
    elif base == "advertencia":
        cause = "cierre_sucio_pendiente_de_revision"
    elif fuerza >= UMBRAL_ENTREGA:
        cause = "cierre_limpio_con_entrega"
    elif unknown:
        cause = "evidencia_indeterminada"
    else:
        cause = "verde_sin_evidencia"

    return RunVerdict(
        level=_CAUSE_TO_LEVEL[cause],
        cause=cause,
        strength=fuerza,
        present=present,
        absent=absent,
        unknown=unknown,
    )
```

> **Cambio de contrato respecto de v1 (C9), obligatorio para el implementador:** `evaluate_verdict` ahora puede devolver `None`. **Todo call-site** (F2 en los dos handlers, F5 en la bandeja) debe hacer `v = evaluate_verdict(...)` y `if v is None: continue` **antes** de llamar `.to_dict()`. Un `.to_dict()` sobre `None` es un `AttributeError` que caería en el `except` y borraría el veredicto de TODO el lote.

> **Cambio de contrato v2 → v3 (D1), EL MÁS IMPORTANTE DE ESTE PLAN:** la firma pasa de `evaluate_verdict(ticket_status=..., ...)` a **`evaluate_verdict(run_status=..., ticket_status=..., ...)`**, donde **`run_status` es obligatorio** y `ticket_status` es opcional y **solo puede empeorar**. Todo call-site pasa `run_status=ex.status` y, si lo tiene a mano sin costo, `ticket_status=<stacky_status del ticket>`. **Está PROHIBIDO el patrón de v2** `estado = (ticket.stacky_status or ex.status)`: colapsaba las dos dimensiones en una y dejaba que un ticket verde blanqueara un run rojo.
>
> **Verificado corriendo, no razonado (números de la 2ª pasada, v4 E6):** con la firma v3/v4, sobre la grilla **COMPLETA** de **17.010** combinaciones (`run_status="error"` × los **7** `ticket_status` posibles × las **243** combinaciones de evidencia × los **9 `OUTCOME_REASONS` + `None`**), las violaciones de I1 son **0**. La monotonicidad del ticket se barrió aparte: **68.040** casos, el ticket **mejoró el nivel en 0**. Los no terminales (`idle`, `running`, `""`, `"   "`) devolvieron `None` en el 100%. El caso concreto que rompía v2 —`run=error` + `ticket=completed` + `publicado_en_tracker=True`— devuelve **`advertencia` / `falso_rojo_probable`**, que es exactamente el resultado que este plan existe para producir. *(El v3 declaraba 10.206 usando 6 reasons; el número real y reproducible es 17.010.)*

> **Nota de diseño para el implementador (actualizada en v2):** la regla 6 (`base == "advertencia"`) ahora captura **solo `needs_review`**, porque `cancelled` sale antes por la regla 5 (C8). Si el `outcome_reason` era `dirty_exit_after_work` o `stall_after_work`, el 254 ya mapeó el estado a `needs_review` (`services/run_outcome.py:36,38`), así que llegan acá y reciben `cierre_sucio_pendiente_de_revision`. **No** hay que replicar esa lógica.

**Tests PRIMERO — `backend/tests/test_plan269_run_verdict.py`**, casos exactos:

| Test | Qué prueba |
|---|---|
| `test_todo_nivel_pertenece_al_vocabulario` | Barre `itertools.product` sobre `(True, False, None)^5` × los 4 estados de `_STATUS_TO_BASE` + `"basura"` × los 9 `OUTCOME_REASONS` + `None`; asegura `v is not None`, `v.level in VERDICT_LEVELS` y `v.cause in VERDICT_CAUSES` **siempre**. Nunca `KeyError`. (v2: la grilla excluye `idle`/`running`, que tienen su test propio.) |
| `test_I1_un_error_jamas_recibe_exito` | **INVARIANTE DURO.** Sobre la misma grilla, con `run_status="error"`, asegura `v.level != "exito"` en el 100% de los casos. |
| `test_I1b_el_ticket_completed_no_blanquea_un_run_error` | **v3 D1 — EL TEST QUE FALTABA, y el que hundió a v2. Grilla corregida en v4 (E6).** Barre `run_status="error"` × **los 7 `ticket_status` posibles** (los 6 de `VALID_TICKET_STATUSES` + `"basura"`) × las **243** combinaciones de evidencia × **los 9 `OUTCOME_REASONS` + `None` = 10** ⇒ **17.010 casos**, y asegura `v.level != "exito"` en todos. *(El v3 decía "los 6 `outcome_reason` = 10.206". `OUTCOME_REASONS` tiene **9** entradas y no hay ningún subconjunto de 6 nombrado en el repo: el número no era reproducible. El test hermano `test_todo_nivel_pertenece_al_vocabulario` ya usaba bien "los 9 + None".)* El caso testigo explícito: `run_status="error", ticket_status="completed", publicado_en_tracker=True` → `cause == "falso_rojo_probable"`, `level == "advertencia"`. **Con la firma de v2 este test es ROJO** — es su razón de existir. **Medido en la crítica v4 sobre la grilla de 17.010: 0 violaciones.** |
| `test_el_ticket_solo_empeora_nunca_mejora` | **v3 D1.** Para cada `run_status` terminal, cada `ticket_status` y cada combinación de evidencia, el nivel con `ticket_status` debe ser **igual o peor** que sin él. El ticket nunca mejora el veredicto. |
| `test_I2_desconocido_nunca_mejora` | Para cada señal `s` y cada estado base, compara `evaluate_verdict(signals=... s=None ...)` contra `... s=False ...`: el índice del nivel en `VERDICT_LEVELS` con `None` debe ser **≥** (igual o peor) que con `False`. |
| `test_falso_rojo_probable_con_publicacion` | `run_status="error"`, `publicado_en_tracker=True` → `cause == "falso_rojo_probable"`, `level == "advertencia"`, `strength == 2`. |
| `test_falso_rojo_probable_con_dos_debiles` | `run_status="error"`, `verificacion_ok=True`, `entregable_presente=True` → `strength == 2` → `falso_rojo_probable`. |
| `test_error_con_una_sola_debil_sigue_siendo_error` | `run_status="error"`, solo `entregable_presente=True` → `strength == 1` → `cause == "error_sin_entrega_suficiente"`, `level == "error_real"`. |
| `test_preflight_gana_sobre_toda_evidencia` | `outcome_reason="preflight_blocked"` con las 5 señales en `True` → sigue siendo `bloqueado_antes_de_empezar` / `error_real`. Prueba la precedencia 1. |
| `test_cuota_gana_sobre_error` | `run_status="error"`, `outcome_reason="quota_exhausted"` → `espera_cuota` / `advertencia`. |
| `test_verde_sin_evidencia_es_advertencia` | `run_status="completed"`, las 5 señales en `False` → `verde_sin_evidencia` / `advertencia`. |
| `test_verde_con_desconocidas_es_advertencia` | `run_status="completed"`, las 5 en `None` → `evidencia_indeterminada` / `advertencia`. |
| `test_verde_con_entrega_es_exito` | `run_status="completed"`, `publicado_en_tracker=True` → `cierre_limpio_con_entrega` / `exito`. |
| `test_needs_review_es_advertencia` | `run_status="needs_review"` con cualquier evidencia → `cierre_sucio_pendiente_de_revision` / `advertencia`. |
| `test_cancelado_no_dice_cierre_sucio` | **v2 C8.** `run_status="cancelled"` con cualquier evidencia → `cause == "cancelado_por_el_operador"`, `level == "advertencia"`, y explícitamente `cause != "cierre_sucio_pendiente_de_revision"`. |
| `test_no_terminal_no_tiene_veredicto` | **v2 C9.** `evaluate_verdict(run_status="running")` y `="idle"` (y `run_status=""`) → `None`, con **cualquier** combinación de evidencia y de `outcome_reason` (barre la grilla). |
| `test_listas_present_absent_unknown_particionan` | Para cualquier entrada terminal, `set(present) | set(absent) | set(unknown) == set(EVIDENCE_SIGNALS)` y las tres son disjuntas. |
| `test_causa_mapea_a_un_solo_nivel` | `set(_CAUSE_TO_LEVEL) == set(VERDICT_CAUSES)`, `len(VERDICT_CAUSES) == 9` y todo valor ∈ `VERDICT_LEVELS`. |
| `test_no_agrega_estados_al_vocabulario` | Importa `status_vocabulary.VALID_TICKET_STATUSES` y asegura que **ningún** `VERDICT_LEVEL` está adentro (son dimensiones distintas y no deben confundirse). También asegura que `set(_STATUS_TO_BASE) | _NO_TERMINALES == VALID_TICKET_STATUSES` — es decir, que el veredicto **cubre el vocabulario completo** y no se olvida de un estado. |
| `test_espejo_ts_no_tiene_drift` | **[ADICIÓN ARQUITECTO A2].** Ver abajo. |

#### [ADICIÓN ARQUITECTO A2] — El espejo backend↔frontend se verifica, no se promete

**Problema real que resuelve:** este plan mantiene **a mano** tres espejos entre Python y TypeScript: las 9 `VERDICT_CAUSES` ↔ `VERDICT_CAUSE_DETAIL` (F3), las 5 `EVIDENCE_SIGNALS` ↔ `EVIDENCE_LABELS` (F3) y los 3 `VERDICT_LEVELS` ↔ `VERDICT_LEVEL_VIEW` (F3). Los espejos a mano **derivan**: el propio 254 tiene el mismo patrón (`OUTCOME_REASONS` ↔ `OUTCOME_REASON_LABELS`) y su única defensa es un comentario que dice *"ni uno más ni uno menos"*. Un comentario no es un gate. El día que alguien agregue una causa en Python, la UI mostrará el string crudo `error_sin_entrega_suficiente` al operador y nadie se va a enterar.

**Solución, costo cero:** un test **de texto** en el archivo que ya existe. No agrega archivo, no agrega flag, no agrega dependencia, no corre en producción.

```python
def test_espejo_ts_no_tiene_drift():
    """A2 — el .ts de F3 debe nombrar TODAS las causas y señales del .py.

    Se lee como TEXTO (no se ejecuta TS): mismo patrón que
    `test_los_6_tests_estan_en_los_dos_scripts` (F7), que ya valida los
    scripts del arnés leyéndolos como texto.
    """
    from pathlib import Path
    from services.run_verdict import EVIDENCE_SIGNALS, VERDICT_CAUSES, VERDICT_LEVELS

    ts = Path(__file__).resolve().parents[2] / "frontend" / "src" / "utils" / "runVerdict.ts"
    if not ts.is_file():          # F3 todavía no implementada: no rompe F0
        import pytest
        pytest.skip("runVerdict.ts aún no existe (F3 pendiente)")
    texto = ts.read_text(encoding="utf-8")
    faltan = [n for n in (*VERDICT_CAUSES, *EVIDENCE_SIGNALS, *VERDICT_LEVELS) if n not in texto]
    assert not faltan, f"drift Python→TS: la UI no conoce {faltan}"
```

**Por qué respeta los rieles:** solo lectura de un archivo del repo; no toca los 3 runtimes (es un test); cero trabajo del operador; reusa un patrón que el propio plan ya usa en F7; y el `skip` condicional lo hace seguro cuando F0 se implementa antes que F3.

**Comando de aceptación (BINARIO):**
```
cd "Stacky Agents/backend"
.venv\Scripts\python.exe -m pytest tests/test_plan269_run_verdict.py -v
```
**Criterio:** **20/20** verdes (v1 declaraba 15; v2 sumo 3 -> 18; **v3 suma `test_I1b_el_ticket_completed_no_blanquea_un_run_error` y `test_el_ticket_solo_empeora_nunca_mejora` -> 20**). Cero fallos. Tras F8 este mismo archivo llega a **29** (20 + 9).

**Flag que la protege:** `STACKY_RUN_VERDICT_ENABLED` — **default ON**. Sin excepción: es un módulo puro que calcula en memoria y no escribe nada, no llama a ningún modelo y no corre en reposo. Alta completa según **RECETA-FLAG** (§3.7), categoría `observabilidad_notif`.

**Impacto por runtime:** ninguno. Es un módulo puro sin dependencia de runtime. Codex / Claude Code / Copilot: idéntico.
**Trabajo del operador:** ninguno.

---

### F1 — Colectores de evidencia read-only (`run_evidence.py`)

**Objetivo (1 frase):** Un módulo que arma `EvidenceSignals` para un lote de ejecuciones leyendo **solo** fuentes ya existentes, con tope de tiempo, sin N+1 y degradando a `None` ante cualquier problema.

**Valor:** Es lo que convierte el veredicto de F0 en algo que refleja la realidad del operador.

**Archivo a crear:** `Stacky Agents/backend/services/run_evidence.py`
**Archivo de test a crear:** `Stacky Agents/backend/tests/test_plan269_run_evidence.py`

**API pública EXACTA:**

```python
"""Plan 269 F1 — colectores de evidencia. SOLO LECTURA, con tope de tiempo.

Rieles duros:
- No escribe, no crea, no borra, no mueve. Ni una fila, ni un archivo.
- Sin red: no llama a la API de ADO ni de GitLab. La evidencia de publicación
  sale de la tabla local `agent_html_publish`, que ya es el registro de lo que
  Stacky publicó (services/ado_publisher.py:122).
- Sin N+1: `collect_for_executions` resuelve TODO el lote con 3 queries fijas.
- Ante cualquier fallo la señal queda en None (desconocida), NUNCA en False y
  NUNCA en True. Un colector jamás rompe el listado que lo llama.
- Sin autonomía: nadie lo llama en un loop. Se invoca cuando el operador ya
  estaba pidiendo el listado.
"""
from __future__ import annotations

COLLECTOR_BUDGET_S = 2.0   # presupuesto TOTAL del lote para las lecturas de disco

def collectors_enabled() -> bool: ...
    # Lee la INSTANCIA: getattr(_config.config, "STACKY_RUN_EVIDENCE_COLLECTORS_ENABLED", True)

def collect_for_executions(session, executions: list) -> dict[int, "EvidenceSignals"]: ...
    # Devuelve {execution_id: EvidenceSignals}. Con la flag OFF devuelve {}.

def _publish_ok_execution_ids(session, execution_ids: list[int]) -> set[int]: ...
def _signals_from_execution(ex, *, publicado: bool | None, presupuesto: "_Budget") -> "EvidenceSignals": ...
```

**Cómo se computa cada señal (pseudocódigo, sin ambigüedad):**

```
publicado_en_tracker:
    ⚠ v3 (D2) — `agent_html_publish.status` tiene CUATRO valores, no tres:
    'ok', 'failed', 'skipped' y **'idempotent_replay'**. La persistencia es
    incondicional: `status=result.status` (services/ado_publisher.py:895).
    Los literales `status="idempotent_replay"` están en :399, :446 y :541.

    Y `idempotent_replay` significa **QUE EL COMENTARIO SÍ ESTÁ PUBLICADO**: el
    dedupe lo detectó y por eso no volvió a llamar a ADO. Como el dedupe pre-ADO
    es por `(ado_id, sha256, status='ok')` (:392), la fila 'ok' queda pegada a la
    PRIMERA ejecución y toda re-corrida del mismo contenido solo tiene una fila
    'idempotent_replay'. Filtrar `status = 'ok'` le habría dado **False** (no
    None) a esa re-corrida: perdía los 2 puntos de la señal MÁS PESADA y, por
    P2, False es peor que None ⇒ el `falso_rojo_probable` degradaba a
    `error_sin_entrega_suficiente` / `error_real`.
    Es decir: v2 REINTRODUCÍA, dentro de su propio colector, el falso rojo que
    este plan existe para matar — y justo en el caso más frecuente.

    UNA query para todo el lote (patrón api/executions.py:48-53):
        SELECT execution_id FROM agent_html_publish
         WHERE execution_id IN (:ids)
           AND status IN ('ok', 'idempotent_replay')     ← v3 D2
    → True  si el id está en el set
    → False si NO está Y la query corrió sin excepción
    → None  si la query lanzó (se captura y se loguea en debug)

    NO se cuentan 'failed' ni 'skipped': ahí no hay comentario publicado.

cambio_en_repo:
    ⚠ v2 (C7) — PROHIBIDO usar `incident_dev_pr.get_intent()`. Ese lector llama
    `_intent_path()` → `_intent_dir()`, que hace `d.mkdir(parents=True,
    exist_ok=True)` (services/incident_dev_pr.py:192-196) y por lo tanto CREA UN
    DIRECTORIO EN DISCO: viola el riel P4 ("ningún colector escribe, crea, mueve
    ni borra"). Además el `mkdir` y el `path.is_file()` están FUERA del try de
    `get_intent` (:214-220), así que SÍ puede lanzar — v1 afirmaba lo contrario.

    Se usa un lector propio, de solo lectura, en run_evidence.py:

        def _sidecar_path(execution_id: int) -> "Path":
            """Misma ruta que services/incident_dev_pr.py:192-200, SIN mkdir."""
            from runtime_paths import data_dir     # noqa: PLC0415
            return data_dir() / "incident_dev_pr" / f"{int(execution_id)}.json"

        def _read_sidecar(execution_id: int) -> dict | None:
            p = _sidecar_path(execution_id)
            try:
                if not p.is_file():
                    return None
                return json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                raise _SidecarUnreadable    # → señal None, NO False

    → None  si el presupuesto de tiempo ya se agotó (no se lee el disco)
    → None  si la lectura lanzó (_SidecarUnreadable): no se pudo mirar
    → False si el archivo NO existe (ausencia informada: este agente no toca repo)
    → True  si intent.get("pr_url") o intent.get("pr_id")
             o (intent.get("files_committed") or 0) > 0
    → False en cualquier otro caso con sidecar presente y legible

gate_aceptacion_ok:
    cr = ex.contract_result            # property, models.py:309
    → None  si cr es None (no hubo contrato: no se puede afirmar nada)
    → True  si cr.get("passed") is True o cr.get("status") == "passed"
    → False en el resto
    HIPÓTESIS DECLARADA (H1): que la clave sea "passed" NO está verificado en
    este documento. El test `test_gate_lee_ambas_formas_y_desconoce_el_resto`
    DISCRIMINA la hipótesis: prueba las 2 formas y prueba que una tercera forma
    (p.ej. {"resultado": "ok"}) devuelve False, no True. Si en el árbol la clave
    real fuera otra, el implementador la agrega a la condición y AL TEST — nunca
    adivina en silencio.

verificacion_ok:
    ⚠ v2 (C5) — H2 YA NO ES UNA HIPÓTESIS. Se verificó el productor y el campo
    NO se llama "ok": se llama "passed". El código de v1 (`v.get("ok") is True`)
    habría devuelto SIEMPRE False y el colector nunca habría visto una sola
    verificación.

    Productor: VerificationReport.to_metadata() en
    backend/services/exec_verification.py:79-96, que escribe:
        metadata["exec_verification"] = {
            "mode", "ran", "hard_failed", "soft", "could_not_verify",
            "passed",          # ← bool | None   (declarado en :70)
            "skipped_reason", "duration_ms", "fake_green",
        }
    El comentario literal de :70 dice: "None = no hay nada que verificar /
    could-not-verify". Ese None es EXACTAMENTE la señal desconocida del 269:
    mapea 1:1, no hay que inventar nada.
    Consumidores que confirman la clave y el campo: api/exec_verification.py:43,
    harness/post_run.py:189-191, services/harness_health.py:848,
    tests/test_exec_verification.py:330-331.

    meta = ex.metadata_dict            # property, models.py:301
    v = meta.get("exec_verification")
    → None  si v no es un dict            (no corrió la verificación)
    → None  si v.get("passed") is None    (could-not-verify: el propio productor
                                           declara que no pudo mirar)
    → True  si v.get("passed") is True
    → False si v.get("passed") is False

entregable_presente:
    → True si (ex.output or "").strip() tiene más de 0 caracteres
    → si no, y ex.html_output_path no es vacío:
         → None si el presupuesto se agotó (no se toca el disco)
         → True si Path(html_output_path).is_file() y st_size > 0
         → False si no existe o mide 0 bytes
         → None si la llamada al filesystem lanzó OSError
    → False si no hay output ni html_output_path
```

**El presupuesto de tiempo (`_Budget`), explícito:**
```python
class _Budget:
    """Presupuesto TOTAL del lote, no por fila. Un lote de 200 ejecuciones no
    puede gastar 200 x timeout. `spent()` se consulta antes de CADA lectura de
    disco; agotado ⇒ la señal queda None (desconocida) y se sigue."""
    def __init__(self, seconds: float): self._deadline = time.monotonic() + seconds
    def exhausted(self) -> bool: return time.monotonic() >= self._deadline
```

**Tests PRIMERO — `backend/tests/test_plan269_run_evidence.py`** (usan objetos falsos con los mismos atributos; **no tocan la base real**):

| Test | Qué prueba |
|---|---|
| `test_flag_off_devuelve_dict_vacio` | Con `STACKY_RUN_EVIDENCE_COLLECTORS_ENABLED=False` en la instancia, `collect_for_executions` devuelve `{}` y **no hace ni una query** (se pasa un `session` que lanza si lo tocan). |
| `test_entregable_por_output_no_toca_disco` | `ex.output = "resultado"` → `entregable_presente is True` sin llamar a `Path.is_file` (monkeypatch que lanza). |
| `test_entregable_por_html_existente` | `tmp_path` con un archivo de >0 bytes → `True`. Archivo de 0 bytes → `False`. Ruta inexistente → `False`. |
| `test_entregable_oserror_es_desconocido` | `monkeypatch` de `Path.is_file` que lanza `OSError` → señal `None`, no `False`. |
| `test_colector_lento_degrada_a_desconocido` | `_Budget(0)` (presupuesto agotado desde el arranque) → todas las señales que requieren disco quedan `None` y la función **retorna**; nada cuelga. |
| `test_publicado_en_una_sola_query` | Un `session` falso que cuenta invocaciones: con 50 ejecuciones se hace **exactamente 1** query a `agent_html_publish`. |
| `test_publicado_query_que_lanza_es_desconocido` | El `session` falso lanza → todas las señales `publicado_en_tracker` quedan `None`, y las demás señales se siguen computando igual. |
| `test_publicado_cuenta_idempotent_replay` | **v3 D2 — el test que v2 no tenía.** Una ejecución cuya única fila en `agent_html_publish` tiene `status="idempotent_replay"` → `publicado_en_tracker is True` (**no** `False`). Y `status="failed"` → `False`; `status="skipped"` → `False`. **Con el filtro `status='ok'` de v2 este test es ROJO**, y con él rojo el falso rojo más frecuente (una re-corrida que ya publicó) se presentaba al operador como `error_real`. |
| `test_cambio_en_repo_sin_sidecar_es_false` | `_sidecar_path` monkeypatcheado a una ruta inexistente de `tmp_path` → `False` (ausencia informada, no ignorancia). |
| `test_cambio_en_repo_con_pr_url_es_true` | Sidecar en `tmp_path` con `{"pr_url": "https://..."}` → `True`. También con `{"files_committed": 3}`. |
| `test_cambio_en_repo_no_crea_directorios` | **v2 C7.** `_sidecar_path` apunta a `tmp_path/"no_existe"/"7.json"`; tras `collect_for_executions`, `(tmp_path/"no_existe").exists()` es **False**. Prueba que el colector **no crea el directorio** (lo que sí haría `incident_dev_pr.get_intent`). Además: `grep -c "get_intent" services/run_evidence.py` = **0**. |
| `test_cambio_en_repo_json_roto_es_desconocido` | Sidecar con bytes que no parsean → señal `None`, **no** `False`. |
| `test_gate_lee_ambas_formas_y_desconoce_el_resto` | **Discrimina H1** (la única hipótesis que queda). `{"passed": True}` → `True`; `{"status": "passed"}` → `True`; `{"passed": False}` → `False`; `contract_result = None` → `None`; `{"resultado": "ok"}` → `False`. Si el árbol usa otra clave, el implementador la agrega a la condición **y al test**. |
| `test_verificacion_lee_passed_tri_estado` | **v2 C5 — ya no discrimina una hipótesis: fija el HECHO.** `{"exec_verification": {"passed": True}}` → `True`; `{"passed": False}` → `False`; `{"passed": None}` → `None`; metadata sin `exec_verification` → `None`; y **`{"exec_verification": {"ok": True}}` → `None`** (el campo `ok` no existe: leerlo era el bug de v1). |
| `test_no_escribe_nada` | El `session` falso hace que `add`, `merge`, `delete`, `commit` y `flush` lancen `AssertionError`; la corrida completa pasa sin tocarlos. |

**Comando de aceptación (BINARIO):**
```
cd "Stacky Agents/backend"
.venv\Scripts\python.exe -m pytest tests/test_plan269_run_evidence.py -v
```
**Criterio:** **15/15** verdes (v1 declaraba 12; v2 subio a 14; **v3 suma `test_publicado_cuenta_idempotent_replay` (D2) -> 15**).

**Flag:** `STACKY_RUN_EVIDENCE_COLLECTORS_ENABLED` — **default ON**. Categoría `observabilidad_notif`. **No es excepción:** solo lee (una query local + `stat()` de archivos ya escritos), no llama a ningún modelo, no corre en reposo y no escribe nada. Es exactamente el caso que la regla de la casa manda dejar ON. Se separa de `STACKY_RUN_VERDICT_ENABLED` para que el operador pueda matar solo las lecturas de disco sin perder el veredicto (que degradaría a `evidencia_indeterminada`).

**Impacto por runtime:**
- **Claude Code CLI:** lee `AgentExecution` que el runner ya escribió (`services/claude_code_cli_runner.py:1865` deja `outcome_reason` en el metadata). Sin cambios en el runner.
- **Codex CLI:** ídem (`services/codex_cli_runner.py:755`). Sin cambios en el runner.
- **GitHub Copilot Pro:** `copilot_bridge.py` no cierra ejecuciones (**0 hits de `final_status`**, §2); el cierre lo hace `agent_runner.py:1029/1055/1082`, que también escribe la fila de `AgentExecution`. Por eso el colector funciona igual. **Fallback explícito:** si un runtime no produce alguna señal (p. ej. Copilot sin sidecar de PR), esa señal es `False` o `None` — nunca inventada — y el veredicto degrada a `advertencia` en vez de fabricar un verde.

**Trabajo del operador:** ninguno.

---

### F2 — Cablear el veredicto a los **DOS** payloads de ejecuciones

**Objetivo (1 frase):** Que los dos endpoints de ejecuciones que la UI consume traigan la clave **`run_verdict`** calculada en el lote, sin N+1 y sin pisar ninguna clave existente.

**Valor:** Alimenta el drawer, el historial y cualquier consumidor futuro.

> **DOS correcciones de v2 que un modelo menor NO debe saltear:**
> - **(C1) La clave se llama `run_verdict`, NUNCA `verdict`.** `verdict` ya existe en el payload: es la columna `AgentExecution.verdict` (`backend/models.py:255`) que `to_dict()` emite en `backend/models.py:327` y que el frontend consume en `AgentHistoryModal.tsx:127-134` y `DailyStandupModal.tsx:13`. Pisarla borraría un campo vivo de otro tipo. Ver §3.4-bis.
> - **(C2) Hay DOS handlers, no uno.** `list_executions()` (`:96`, usa `to_dict`) **y** `executions_history()` (`:442`, arma los items a mano en `:538-559` y NO pasa por `_with_outcome`). La página del historial —donde vive toda F4— consume el **segundo**. Cablear solo el primero deja F4 inerte. Ver §3.4.

**Archivo a editar:** `Stacky Agents/backend/api/executions.py`
**Archivo a editar:** `Stacky Agents/frontend/src/api/endpoints.ts` (agregar `run_verdict?: RunVerdictPayload` a `ExecutionHistoryItem`, `:1303`; campo **opcional**, backward-compatible)
**Archivo de test a crear:** `Stacky Agents/backend/tests/test_plan269_executions_payload.py`

**Diff ilustrativo (se agrega **debajo** de `_with_outcome`, sin tocar su cuerpo):**

```python
def _verdict_badge_enabled() -> bool:
    """Plan 269 F2 — kill-switch del veredicto en el payload. Se lee la INSTANCIA.

    Dependencia resuelta EN CÓDIGO, no con `requires=` en la FlagSpec (ver §3.7):
    el veredicto solo se sirve si están ON la flag de UI Y la del núcleo.
    """
    import config as _config  # noqa: PLC0415

    return (
        bool(getattr(_config.config, "STACKY_UI_RUN_VERDICT_BADGE_ENABLED", True))
        and bool(getattr(_config.config, "STACKY_RUN_VERDICT_ENABLED", True))
    )


def _verdicts_for_batch(session, executions: list) -> dict[int, dict]:
    """Plan 269 F2 — veredicto de TODO el lote. Read-only, sin N+1.

    Nunca lanza: cualquier fallo devuelve {} y el listado sale como antes.
    """
    if not _verdict_badge_enabled():
        return {}
    try:
        from services.run_evidence import collect_for_executions  # noqa: PLC0415
        from services.run_verdict import evaluate_verdict  # noqa: PLC0415

        signals_by_id = collect_for_executions(session, executions)
        out: dict[int, dict] = {}
        for ex in executions:
            ticket = getattr(ex, "ticket", None)
            # ⚠ v3 (D1) — DOS argumentos, NO uno colapsado.
            # PROHIBIDO el patrón de v2 `(ticket.stacky_status or ex.status)`:
            # dejaba que un ticket `completed` blanqueara un run `error` y el
            # historial pintaba "Terminó bien" al lado del chip "Error" en TODAS
            # las corridas fallidas de un ticket ya cerrado.
            # El run manda; el ticket solo puede EMPEORAR (nunca mejorar).
            meta = ex.metadata_dict if isinstance(ex.metadata_dict, dict) else {}
            v = evaluate_verdict(
                run_status=(ex.status or ""),
                ticket_status=getattr(ticket, "stacky_status", None),
                outcome_reason=meta.get("outcome_reason"),
                signals=signals_by_id.get(ex.id),
            )
            if v is None:          # v2 C9 — run no terminado: NO tiene veredicto
                continue
            out[ex.id] = v.to_dict()
        return out
    except Exception:  # noqa: BLE001 — enriquecer JAMÁS rompe el listado
        logger.debug("run_verdict 269 falló", exc_info=True)
        return {}


def _with_verdict(d: dict, verdicts: dict[int, dict]) -> dict:
    """Agrega `run_verdict` si hay uno. Con la flag OFF no agrega NINGUNA clave:
    la UI simplemente no dibuja el chip (sin hueco ni error).

    ⚠ La clave es `run_verdict`, NO `verdict`: `verdict` ya lo emite
    AgentExecution.to_dict() (models.py:327) con la revisión humana.
    """
    v = verdicts.get(d.get("id"))
    if v:
        d["run_verdict"] = v
    return d
```

**Punto de llamada 1 — `list_executions()` (`backend/api/executions.py:96`) y el handler de detalle.** Dentro del mismo `with session_scope()` donde ya se calcula `dirty`, agregar `verdicts = _verdicts_for_batch(session, rows)` y cambiar el return:

```diff
-        return jsonify([_with_outcome(d, dirty) for d in payload])
+        verdicts = _verdicts_for_batch(session, rows)
+        return jsonify([_with_verdict(_with_outcome(d, dirty), verdicts) for d in payload])
```
`rows` ya viene con `joinedload(AgentExecution.ticket)` (`:130`), así que `getattr(ex, "ticket", None)` **no** dispara N+1. **No se reordena ni se borra nada de lo que ya hace `_with_outcome`.**

**Punto de llamada 2 — `executions_history()` (`backend/api/executions.py:442`), OBLIGATORIO (C2).** Este handler arma cada item a mano (`:538-559`) y **no** usa `to_dict`. Se inyecta **dentro del mismo `with session_scope()`**, después del `for row in rows` que llena `items` y **antes** del `if include_total` (`:561`), para que las **dos** formas de respuesta lo lleven:

```diff
         # Para cada ejecución construimos el item del contrato.
         items = []
+        rows_servidas = []            # solo las que sobrevivieron el filtro de runtime
         for row in rows:
             ...
             if runtime_filter and row_runtime != runtime_filter:
                 continue
             ...
             items.append({ ... })
+            rows_servidas.append(row)
+
+        # Plan 269 F2 (C2) — el historial es la superficie de F4. Misma función
+        # de lote, mismo try/except: si falla, `items` sale exactamente como hoy.
+        verdicts = _verdicts_for_batch(session, rows_servidas)
+        for d in items:
+            _with_verdict(d, verdicts)

     if include_total:
         return jsonify({"items": items, "total": total})
     return jsonify(items)
```
> **Nota de performance para este handler:** `executions_history` hace `.join(Ticket, ...)` (`:481`), que **no** es eager-load, así que `row.ticket` ya era un lazy-load por fila **antes** de este plan (`models.py:275`). Este plan **no lo empeora** (`_verdicts_for_batch` toca el mismo atributo que el handler ya toca en `:534`) y **no lo arregla** (está fuera de scope). El test `test_sin_n_mas_uno` mide el **delta** de queries entre flag ON y flag OFF sobre el MISMO lote, no el absoluto — así no se atribuye a este plan una deuda ajena.

**Forma EXACTA de la clave nueva en el payload (los dos endpoints):**
```json
"run_verdict": {
  "level": "advertencia",
  "cause": "falso_rojo_probable",
  "strength": 2,
  "present": ["publicado_en_tracker"],
  "absent": ["cambio_en_repo", "gate_aceptacion_ok"],
  "unknown": ["verificacion_ok", "entregable_presente"]
}
```

**Tests PRIMERO — `backend/tests/test_plan269_executions_payload.py`:**

| Test | Qué prueba |
|---|---|
| `test_flag_off_no_agrega_la_clave` | Con `STACKY_UI_RUN_VERDICT_BADGE_ENABLED=False`, `"run_verdict" not in payload` — **no** una clave con `None`. |
| `test_flag_nucleo_off_tambien_apaga` | Con `STACKY_RUN_VERDICT_ENABLED=False` y la de UI en ON, tampoco aparece la clave (dependencia en código). |
| `test_flag_on_agrega_la_clave_con_las_6_subclaves` | `set(payload["run_verdict"]) == {"level","cause","strength","present","absent","unknown"}`. |
| `test_no_pisa_el_verdict_del_modelo` | **v2 C1, el test que v1 no tenía.** Una ejecución con `AgentExecution.verdict = "approved"` en la base: tras el enriquecimiento, `payload["verdict"] == "approved"` (string, intacto) **y** `isinstance(payload["run_verdict"], dict)`. Las dos claves conviven. |
| `test_history_endpoint_tambien_trae_run_verdict` | **v2 C2, el test que v1 no tenía.** `GET /api/executions/history` devuelve items con `run_verdict`; y con `?include_total=1` la clave también está dentro de `data["items"]`. Sin esto, F4 es decorado inerte. |
| `test_colector_que_lanza_no_rompe_ninguno_de_los_dos` | `collect_for_executions` monkeypatcheado a lanzar → **ambos** endpoints siguen dando 200, y las claves del 254 (`outcome_reason`, `outcome_actionable`) siguen presentes en `/api/executions`. |
| `test_no_pisa_claves_del_254` | `outcome_reason` y `outcome_actionable` conservan exactamente el mismo valor con la flag del 269 en ON y en OFF. |
| `test_run_en_curso_no_trae_veredicto` | **v2 C9.** Una ejecución con `ex.status = "running"` → `"run_verdict" not in item`, en **ambos** endpoints. |
| `test_ticket_completed_no_blanquea_un_run_error` | **[ADICIÓN ARQUITECTO A3] — v3 D1, corregido en v4 (E1). EL GATE DEL FALSO VERDE, EN EL BORDE.** Se siembra un `Ticket` con `stacky_status="completed"` y **dos** `AgentExecution` bajo él, **CADA UNA con su propia fila `ok` en `agent_html_publish`** (dos filas, no una — ver E1): la ejecución **A** con `status="completed"` y la **B** con `status="error"`. Se piden **los dos** endpoints (`GET /api/executions` y `GET /api/executions/history`) y se asertan **los dos lados del contraste**, que es lo que prueba que el run manda: el item de **B** (`error`) → `run_verdict["level"] == "advertencia"` y `run_verdict["cause"] == "falso_rojo_probable"`; el item de **A** (`completed`) → `run_verdict["level"] == "exito"` y `cause == "cierre_limpio_con_entrega"`. **Con el cableado de v2 este test es ROJO** (B daría `exito`). Ver el bloque A3 abajo. |
| `test_sin_n_mas_uno` | Se cuenta el **delta** de queries entre la flag ON y la flag OFF sobre el MISMO lote, con 3 y con 30 ejecuciones. El delta debe ser **el mismo número** en los dos casos (no crece con el tamaño del lote). Se mide el delta y no el absoluto para no cargarle a este plan el lazy-load preexistente de `executions_history` (`:534`). |

**Comando de aceptación (BINARIO):**
```
cd "Stacky Agents/backend"
.venv\Scripts\python.exe -m pytest tests/test_plan269_executions_payload.py -v
```
#### [ADICIÓN ARQUITECTO A3] — El gate del falso verde vive en el BORDE, no en el núcleo

**El agujero que tapa, con nombre y apellido.** El invariante I1 de este plan estaba probado **solo sobre la función pura**, y por eso `test_I1_un_error_jamas_recibe_exito` se quedó **verde** mientras el producto mostraba un falso verde: el bug no estaba en la función, estaba en los **dos argumentos que el cableado le pasaba**. Un test de núcleo no puede ver un bug de costura. Esta es, literalmente, la lección del repo: *"censá corriendo, no contando"*.

**La regla que queda escrita, y que vale más que el fix puntual:**

> **Todo invariante de negocio se prueba en la SUPERFICIE que el operador mira, no solo en el módulo que lo implementa.** Si el invariante es "un `error` nunca da `exito`", el test tiene que pedirle el JSON al endpoint y mirar la fila — no llamar a la función pura con los argumentos que uno cree que le van a llegar.

**Qué se agrega — un solo test, cero archivos nuevos, cero flags:** `test_ticket_completed_no_blanquea_un_run_error` en `test_plan269_executions_payload.py` (el archivo que F2 ya crea). Recorre **el camino completo**: base sembrada → handler → JSON. Cubre **los dos** endpoints, porque son dos armados de payload distintos (C2) y el invariante tiene que valer en los dos.

> ⚠ **v4 (E1) — EL TEST DEL v3 NACÍA ROJO. Lo que hay que sembrar, exacto.**
> El v3 sembraba **una sola** fila `ok` en `agent_html_publish` (para la ejecución `error`) y después afirmaba que *"el item de la `completed` sí puede ser `exito`"*. **No puede.** Medido con el módulo F0 literal: una ejecución `completed` **sin evidencia sembrada** recibe de los colectores `publicado=False, cambio_en_repo=False, gate=None, verificacion=None, entregable=False` ⇒ **`strength = 0`**, contra `UMBRAL_ENTREGA = 2` ⇒ el veredicto es **`advertencia` / `evidencia_indeterminada`**, no `exito`. Un modelo menor que escriba el assert que la frase sugiere obtiene un **ROJO en el gate más importante del plan**, y va a "arreglarlo" bajando el assert — perdiendo justo la mitad que demuestra el contraste.
>
> **Siembra correcta: DOS filas `ok`, una por ejecución.** Así el único factor que difiere entre A y B es `AgentExecution.status`, que es **exactamente** la variable que el test quiere aislar. Con evidencia idéntica y ticket idéntico, si B sale `error_real`/`advertencia` y A sale `exito`, queda probado que **el nivel lo manda el run** y que el `stacky_status="completed"` del ticket **no blanqueó** a B.
>
> **Helper de siembra — el anclaje REAL (v4, E8).** El v3 decía reusar *"el patrón de fixtures de `test_plan254_falso_rojo.py`"*, pero ese archivo tiene **0 ocurrencias** de `AgentHtmlPublish`. El helper que sí existe y que hay que copiar es `_add_html_publish` en **`backend/tests/test_publish_ledger.py:47-54`**:
> ```python
> from services.ado_publisher import AgentHtmlPublish
> with session_scope() as s:
>     s.add(AgentHtmlPublish(
>         execution_id=exec_id, ticket_id=1, ado_id=ado_id, html_path="x",
>         html_sha256=f"sha{exec_id}", status=status, triggered_by="test",
>     ))
> ```
> Esas **7** columnas son las `nullable=False` del modelo (`services/ado_publisher.py:134-149`): omitir cualquiera es un `IntegrityError`. **No hay riesgo de tabla ausente:** `AgentHtmlPublish` está registrada en `init_db` (`db.py:239`), así que `Base.metadata.create_all` la crea como cualquier otra. El mismo helper sirve para `test_publicado_cuenta_idempotent_replay` (D2), porque ya recibe `status` como parámetro.

**Por qué sale gratis y respeta todos los rieles:** no agrega archivo (va en uno que F2 ya registra en el arnés), no agrega flag, no agrega dependencia, no corre en producción, no toca los 3 runtimes (es un test de backend), y reusa el patrón de fixtures de `test_plan254_falso_rojo.py` / `test_plan238_incident_inbox_api.py` para el `Ticket` + `AgentExecution` (**los dos verificados verdes** en este árbol: 9 passed y 12 passed) y el de `test_publish_ledger.py:47-54` para las filas de `agent_html_publish`.

**Comando de aceptación (BINARIO):**
```
cd "Stacky Agents/backend"
.venv\Scripts\python.exe -m pytest tests/test_plan269_executions_payload.py::test_ticket_completed_no_blanquea_un_run_error -v
```

---

**Criterio:** **10/10** verdes (v1 declaraba 6; v2 subió a 9; **v3 suma `test_ticket_completed_no_blanquea_un_run_error` (A3) → 10**). Y sin regresión en el 254, validado **por archivo** (medidos hoy con el venv: **11 passed** y **10 passed** respectivamente):
```
.venv\Scripts\python.exe -m pytest tests/test_plan254_outcome_reason.py -v
.venv\Scripts\python.exe -m pytest tests/test_plan254_reconciliation.py -v
```

**Flag:** `STACKY_UI_RUN_VERDICT_BADGE_ENABLED` — **default ON**, categoría `observabilidad_notif`. Solo enriquece un payload de lectura.
**Impacto por runtime:** ninguno (P3: se calcula al leer). **Fallback:** con cualquiera de las dos flags OFF, el payload es **byte-idéntico** al de hoy.
**Trabajo del operador:** ninguno.

---

### F3 — Módulo PURO de presentación del veredicto (`runVerdict.ts`)

**Objetivo (1 frase):** Un `.ts` puro que traduce el veredicto a etiqueta en castellano llana, tono y explicación de la evidencia, reusando `OutcomeTone` del 254.

**Valor:** Toda la lógica de UI queda testeable con vitest; los `.tsx` solo consumen.

**Archivo a crear:** `Stacky Agents/frontend/src/utils/runVerdict.ts`
**Archivo de test a crear:** `Stacky Agents/frontend/src/utils/__tests__/plan269RunVerdict.test.ts`

**Por qué un módulo puro y no un test de render:** `@testing-library/react` y `jsdom` **no están instalados** en este repo (`frontend/package.json` devDependencies). Un test de vitest que renderice React **no es ejecutable acá**. Mismo criterio que `outcomeReason.ts` (ver su comentario de cabecera, líneas 2-6).

**Contenido EXACTO (nombres congelados):**

```typescript
// Plan 269 F3 — veredicto por evidencia → etiqueta + tono + explicación.
//
// Reusa OutcomeTone de outcomeReason.ts (254 F4): NO se define un tipo de tono
// nuevo. El veredicto es una DIMENSIÓN SEPARADA del estado, no un estado más.

import type { OutcomeTone } from "./outcomeReason";

export type VerdictLevel = "exito" | "advertencia" | "error_real";

export interface RunVerdictPayload {
  level: string;
  cause: string;
  strength?: number;
  present?: string[];
  absent?: string[];
  unknown?: string[];
}

export interface VerdictView {
  level: VerdictLevel;
  tone: OutcomeTone;      // "exito" | "atencion" | "espera" | "error"
  label: string;          // texto del chip de la fila, corto
  detail: string;         // una línea explicando la causa
  needsOperator: boolean; // true ⇒ merece un ojo humano
}

/** Los 3 niveles → tono + etiqueta corta de fila. */
export const VERDICT_LEVEL_VIEW: Record<VerdictLevel, { tone: OutcomeTone; label: string }> = {
  exito:       { tone: "exito",    label: "Terminó bien" },
  advertencia: { tone: "atencion", label: "Con advertencias" },
  error_real:  { tone: "error",    label: "Error real" },
};

/** Las 9 causas de VERDICT_CAUSES (services/run_verdict.py), ni una más ni una
 *  menos. El drift contra el .py lo ATRAPA `test_espejo_ts_no_tiene_drift`
 *  (F0, ADICIÓN ARQUITECTO A2): esto ya no es un comentario de buena fe. */
export const VERDICT_CAUSE_DETAIL: Record<string, string> = {
  cierre_limpio_con_entrega: "Terminó sin errores y dejó resultados verificables.",
  verde_sin_evidencia: "Figura como terminado, pero no se encontró ningún resultado que lo respalde.",
  evidencia_indeterminada: "Figura como terminado, pero no se pudo comprobar si dejó resultados.",
  cierre_sucio_pendiente_de_revision: "Entregó trabajo pero el proceso cerró mal: convendría mirarlo.",
  cancelado_por_el_operador: "Lo cortaste vos. No es una falla del sistema.",   // v2 C8
  falso_rojo_probable: "Figura como fallado, pero hay resultados: probablemente NO sea un error.",
  espera_cuota: "Se agotó la cuota del plan. No es un error del trabajo: hay que reintentar más tarde.",
  error_sin_entrega_suficiente: "Falló y no se encontraron resultados: requiere atención.",
  bloqueado_antes_de_empezar: "Se bloqueó antes de arrancar: nunca llegó a trabajar.",
};

/** Nombres humanos de EVIDENCE_SIGNALS (services/run_verdict.py). */
export const EVIDENCE_LABELS: Record<string, string> = {
  publicado_en_tracker: "comentario publicado en el tablero",
  cambio_en_repo: "cambios en el repositorio",
  gate_aceptacion_ok: "criterios de aceptación verificados",
  verificacion_ok: "verificación de la ejecución",
  entregable_presente: "archivo de resultado",
};

const NIVELES: VerdictLevel[] = ["exito", "advertencia", "error_real"];

/**
 * Traduce el veredicto. Un nivel o causa del futuro NO rompe la UI: cae a
 * "advertencia" con el texto crudo, nunca a `undefined` y NUNCA a "exito"
 * (un nivel desconocido jamás se presenta como éxito).
 */
/** v3 (D10) — causas que tienen un tono PROPIO, más específico que el del nivel.
 *  `espera_cuota` NO es lo mismo que "con advertencias": el trabajo no falló,
 *  se agotó la cuota y hay que reintentar más tarde. `OutcomeTone` ya tiene el
 *  vocabulario ("espera"); v2 lo perdía porque resolvía el tono SOLO por nivel,
 *  dejando `verdictChipTone("espera")` como rama muerta.
 *  El NIVEL no cambia (sigue siendo `advertencia`): solo cambia cómo se pinta. */
export const VERDICT_CAUSE_TONE: Record<string, OutcomeTone> = {
  espera_cuota: "espera",
};

export function describeVerdict(v: RunVerdictPayload | null | undefined): VerdictView | null {
  if (!v || !v.level) return null;
  const level: VerdictLevel = (NIVELES as string[]).includes(v.level)
    ? (v.level as VerdictLevel)
    : "advertencia";
  const view = VERDICT_LEVEL_VIEW[level];
  return {
    level,
    tone: VERDICT_CAUSE_TONE[v.cause] ?? view.tone,   // v3 D10: la causa gana
    label: view.label,
    detail: VERDICT_CAUSE_DETAIL[v.cause] ?? v.cause,
    needsOperator: level !== "exito",
  };
}

/** Frase de evidencia para el detalle: qué se encontró y qué no. */
export function evidenceSummary(v: RunVerdictPayload | null | undefined): string {
  if (!v) return "";
  const nombre = (k: string) => EVIDENCE_LABELS[k] ?? k;
  const partes: string[] = [];
  if (v.present?.length) partes.push(`Se encontró: ${v.present.map(nombre).join(", ")}.`);
  if (v.absent?.length) partes.push(`No hay: ${v.absent.map(nombre).join(", ")}.`);
  if (v.unknown?.length) partes.push(`No se pudo comprobar: ${v.unknown.map(nombre).join(", ")}.`);
  return partes.join(" ");
}

/** Filtro por nivel para las listas. `null`/"" = sin filtro (devuelve todo). */
export function matchesVerdictLevel(
  v: RunVerdictPayload | null | undefined,
  filtro: string | null | undefined,
): boolean {
  if (!filtro) return true;
  const view = describeVerdict(v);
  if (!view) return false;   // sin veredicto no matchea un filtro explícito
  return view.level === filtro;
}
```

**Tests PRIMERO — `frontend/src/utils/__tests__/plan269RunVerdict.test.ts`:**

| Test | Qué prueba |
|---|---|
| `las 9 causas tienen texto` | **v2 C8.** `Object.keys(VERDICT_CAUSE_DETAIL).length === 9`, ninguno vacío, y el texto de `cancelado_por_el_operador` **no** contiene "cerró mal". |
| `los 3 niveles tienen tono y etiqueta` | Cada `VerdictLevel` mapea a un tono ∈ `["exito","atencion","espera","error"]`. |
| `un nivel del futuro no se presenta como exito` | `describeVerdict({level:"nivel_del_futuro", cause:"x"})?.level === "advertencia"` y `tone === "atencion"`. |
| `espera_cuota se pinta con tono espera` | **v3 D10.** `describeVerdict({level:"advertencia", cause:"espera_cuota"})?.tone === "espera"` y `level === "advertencia"` (el nivel NO cambia, solo el tono). Y `cause:"falso_rojo_probable"` sigue dando `tone === "atencion"`. Sin esto, `verdictChipTone("espera")` era una rama muerta y una corrida frenada por cuota se le presentaba al operador como si algo hubiera salido mal. |
| `una causa del futuro muestra el texto crudo` | `detail === "causa_rara"`, no `undefined`. |
| `null y undefined devuelven null` | `describeVerdict(null)`, `describeVerdict(undefined)`, `describeVerdict({level:""} as any)` → `null`. |
| `needsOperator es false solo en exito` | Recorre los 3 niveles. |
| `evidenceSummary nombra las 3 categorías` | Con `present`/`absent`/`unknown` poblados, el texto contiene "Se encontró", "No hay" y "No se pudo comprobar". |
| `evidenceSummary vacío no rompe` | `evidenceSummary({level:"exito",cause:"x"})` → `""`. |
| `matchesVerdictLevel sin filtro devuelve todo` | `matchesVerdictLevel(null, "")` → `true`. |
| `matchesVerdictLevel filtra por nivel` | `advertencia` matchea `"advertencia"` y no `"error_real"`. |
| `matchesVerdictLevel sin veredicto no matchea un filtro explícito` | `matchesVerdictLevel(null, "exito")` → `false`. |

**Comando de aceptación (BINARIO):**
```
cd "Stacky Agents/frontend"
npx vitest run src/utils/__tests__/plan269RunVerdict.test.ts
```
(Correr **por archivo**: la corrida completa de vitest tiene contaminación cross-file conocida en este repo.)
**Criterio:** **12/12** verdes (v2 declaraba 11; **v3 suma `espera_cuota se pinta con tono espera` (D10)**). Y `npx tsc --noEmit` sin errores nuevos.

**Flag:** protegido por `STACKY_UI_RUN_VERDICT_BADGE_ENABLED` (F2): sin la clave `verdict` en el payload, `describeVerdict` devuelve `null` y no se dibuja nada.
**Impacto por runtime:** ninguno.
**Trabajo del operador:** ninguno.

---

### F4 — El veredicto en la FILA del historial de ejecuciones + filtro por nivel

**Objetivo (1 frase):** Que la fila del historial muestre **dos** dimensiones —estado y veredicto— y que el operador pueda filtrar por nivel de veredicto.

**Valor:** Cierra el GAP 2 en la superficie donde el operador mira las corridas. Hoy `ExecutionHistoryPage.tsx:633` pinta un solo chip.

**Archivos a editar (los 4, ninguno opcional):**
- `Stacky Agents/frontend/src/services/tablePrefs.ts` — **registrar la columna** (C3)
- `Stacky Agents/frontend/src/pages/ExecutionHistoryPage.tsx` — `<th>` + `<td>` + filtro
- `Stacky Agents/frontend/src/pages/ExecutionHistoryPage.module.css` (ya existe; **cero estilo inline** por el ratchet de deuda de UI)
- `Stacky Agents/frontend/src/api/endpoints.ts` — `run_verdict?: RunVerdictPayload` en **`interface ExecutionHistoryItem`** (`:1303`; **campo opcional**, backward-compatible). *(C11: v1 decía "la interfaz de la fila de ejecución" sin nombrarla.)*

**Paso 1 (C3) — registrar la columna en `frontend/src/services/tablePrefs.ts:27-41`.** Esta tabla NO es estática: cada `<th>`/`<td>` vive bajo `isColVisible(tablePrefs, "<id>")`, el picker recibe `columns={HISTORY_COLUMNS}` (`ExecutionHistoryPage.tsx:454`) y las prefs se sanean con `sanitizeTablePrefs(raw, HISTORY_COLUMNS)` (`:102`, `:237`). Una columna no registrada no aparece en el selector y se pierde al sanear.

```diff
   { id: "estado", label: "Estado", sortKey: "status" },
+  // Plan 269 F4 — segunda dimensión: el veredicto por evidencia. SIN `sortKey`:
+  // el veredicto se calcula al leer y el backend no puede ordenar por él
+  // (mismo criterio que `duracion` y `costo`, líneas 33-35).
+  { id: "veredicto", label: "Veredicto" },
   { id: "duracion", label: "Duración" },
```

**Paso 2 — el `<th>`, en el `<thead>` de `ExecutionHistoryPage.tsx:507`** (cierra en `:579`). *(C11: v1 decía "buscar el `<thead>` del mismo archivo".)*

> ⚠ **v3 (D7) — el rango de v2 estaba MAL y se comía el ancla.** v2 decía *"los `<th>` existentes están en `:525-545`"*, pero el `<th>` de **`estado` está en `:546`, FUERA de ese rango**. Un modelo menor que abriera 525-545 habría encontrado `inicio/agente/runtime/modelo` y **no** `estado`, insertando la columna en el lugar equivocado y desalineando la tabla — exactamente R9/R16.
>
> **Mapa REAL de los `<th>`, regrepeado el 2026-07-28** (bulk-select en `:510`):
>
> | `data-col` | línea | | `data-col` | línea |
> |---|---|---|---|---|
> | `inicio` | 526 | | `costo` | 556 |
> | `agente` | 531 | | `prompt` | 561 |
> | `runtime` | 536 | | `archivos` | 566 |
> | `modelo` | 541 | | `ticket` | 571 |
> | **`estado`** | **546-548** | | acciones | 577 |
> | `duracion` | 551 | | | |
>
> **El bloque real va de `:526` a `:576`.** El `<th>` nuevo va **inmediatamente después del bloque de `estado` (`:546-548`) y antes del de `duracion` (`:551`)**, para que el orden de los `<th>` coincida con el de los `<td>` y con el de `HISTORY_COLUMNS`.

```diff
+                {isColVisible(tablePrefs, "veredicto") && (
+                  <th data-col="veredicto">Veredicto</th>
+                )}
```
> Sin `onClick` de sort y sin `sortMarca(...)` **a propósito**: `veredicto` no tiene `sortKey`, y ofrecer un orden que el backend no puede dar sería prometer algo falso (es la misma decisión ya tomada para `duracion`/`costo`, `tablePrefs.ts:33-35`).

**Paso 3 — el `<td>`, inmediatamente después del bloque `estado` de `ExecutionHistoryPage.tsx:632-634`:**

```diff
+import { describeVerdict, matchesVerdictLevel, verdictChipTone } from "../utils/runVerdict";
...
   {isColVisible(tablePrefs, "estado") && (
   <td><StatusChip tone={runStatusTone(item.status)} size="sm">{runStatusLabel(item.status)}</StatusChip></td>
   )}
+  {isColVisible(tablePrefs, "veredicto") && (
+  <td>
+    {(() => {
+      const v = describeVerdict(item.run_verdict);   // ⚠ run_verdict, NO verdict (C1)
+      if (!v) return null;
+      return (
+        <StatusChip tone={verdictChipTone(v.tone)} size="sm" title={v.detail}>
+          {v.label}
+        </StatusChip>
+      );
+    })()}
+  </td>
+  )}
```
`StatusChip` acepta `title` (`frontend/src/components/ui/StatusChip.tsx:13`), así que el diff compila. **Un run en curso no trae `run_verdict` (C9), así que la celda queda vacía en vez de decir "Con advertencias".**

**Puente de tonos (va en `runVerdict.ts`, NO en el `.tsx`), para no acoplar `utils/` a `ui/`:**
```typescript
// `StatusChip` usa StatusTone ("success"|"warning"|"danger"|"info"|"neutral",
// utils/runStatus.ts:1). OutcomeTone es otro vocabulario. Este puente traduce.
export function verdictChipTone(tone: OutcomeTone): "success" | "warning" | "danger" | "neutral" {
  if (tone === "exito") return "success";
  if (tone === "error") return "danger";
  if (tone === "espera") return "neutral";
  return "warning";
}
```
**Paso 4 — filtro por nivel:** agregar un `<select className={styles.filterSelect}>` junto al de estado (`ExecutionHistoryPage.tsx:398-406`) con opciones `""` (Todos) / `exito` / `advertencia` / `error_real`, guardado en el mismo objeto `filters` (`interface Filters`, `:72`) bajo la clave `verdict_level`, y **filtrado en cliente** con `matchesVerdictLevel(item.run_verdict, filters.verdict_level)` justo antes del `.map` de filas. Agregar `"verdict_level"` al array `urlFilterKeys` (`ExecutionHistoryPage.tsx:450`, hoy `["agent_type", "runtime", "status", "days"]`) para que el filtro viaje en la URL como los demás. **No** se toca el backend: el filtro es de presentación.

> **Interacción con la paginación, declarada:** el filtro es de cliente y la lista viene paginada del servidor (`offset`/`limit`, y `total` cuando se pide `include_total`). Filtrar en cliente puede dejar una página con menos filas que `limit`. Es **exactamente** el mismo comportamiento que ya tiene el filtro `runtime`, que el backend aplica en Python después de paginar y cuya limitación está documentada en el docstring de `executions_history` (`backend/api/executions.py:453-456`). No se introduce una anomalía nueva; se hereda una conocida.

**Tests PRIMERO:** la lógica pura ya está cubierta por F3 (`matchesVerdictLevel`, `verdictChipTone`). Se **agrega** a `plan269RunVerdict.test.ts`:

| Test | Qué prueba |
|---|---|
| `verdictChipTone cubre los 4 tonos` | `exito→success`, `error→danger`, `espera→neutral`, `atencion→warning`. |
| `filtrar una lista por nivel` | Dado un array de 4 filas con veredictos distintos, `rows.filter(r => matchesVerdictLevel(r.run_verdict, "advertencia"))` devuelve exactamente las de advertencia. |

**Comando de aceptación (BINARIO):**
```
cd "Stacky Agents/frontend"
npx vitest run src/utils/__tests__/plan269RunVerdict.test.ts
npx tsc --noEmit
```
**Criterio:** **14/14** verdes (12 de F3 + 2 de F4) y `tsc` sin errores nuevos. Además, gates de presencia:
```
grep -c "verdictChipTone" src/pages/ExecutionHistoryPage.tsx          # >= 1
grep -c "veredicto" src/services/tablePrefs.ts                        # >= 1   (C3)
grep -c "isColVisible(tablePrefs, \"veredicto\")" src/pages/ExecutionHistoryPage.tsx  # == 2  (th + td, C3)
grep -c "item.verdict" src/pages/ExecutionHistoryPage.tsx             # == 0   (C1: es run_verdict)
grep -c "style={{" src/pages/ExecutionHistoryPage.tsx                 # no debe AUMENTAR vs. HEAD
```

**Flag:** `STACKY_UI_RUN_VERDICT_BADGE_ENABLED` (la de F2). Con la flag OFF el payload no trae `run_verdict`, `describeVerdict` devuelve `null` y la celda queda vacía. **La columna sigue registrada y el operador puede ocultarla** desde el selector de columnas que ya existe (`:454`) — ese es el mecanismo de la casa para "no la quiero ver", y por eso **no** se agrega una condición ad-hoc tipo `rows.some(...)` (v1 la sugería como alternativa: queda descartada, era una segunda forma de hacer lo mismo).
**Impacto por runtime:** ninguno. **Fallback:** sin veredicto, la fila se ve exactamente como hoy.
**Trabajo del operador:** ninguno (el filtro es opcional y arranca en "Todos").

---

### F5 — El veredicto en la FILA de la bandeja de incidencias

**Objetivo (1 frase):** Que la bandeja de incidencias muestre el veredicto de la **última ejecución** de cada incidencia, sin romper la promesa de "sin N+1" que el endpoint ya declara.

**Valor:** Es la lista que el operador llama "incidencias". Hoy solo muestra `ado_state` crudo (`IncidentInboxPage.tsx:503`).

**Archivos a editar:**
- `Stacky Agents/backend/api/incident_inbox.py`
- `Stacky Agents/frontend/src/pages/IncidentInboxPage.tsx`
- `Stacky Agents/frontend/src/pages/IncidentInboxPage.module.css`
**Archivo de test a crear:** `Stacky Agents/backend/tests/test_plan269_inbox_verdict.py`

**Restricción heredada, no negociable:** `backend/api/incident_inbox.py:149` declara textualmente *"Sin N+1: NO se consulta AgentExecution ni pipeline_summary"*. Este plan **conserva** esa propiedad: se agrega **una sola** query extra para todo el lote.

**Paso 1 (OBLIGATORIO, C4) — el módulo NO tiene logger.** `grep -c logger backend/api/incident_inbox.py` = **0**; ni siquiera importa `logging` (sus únicos imports son `:6` y `:8`). Sin esto, el `except` de abajo lanza `NameError` **desde el handler de excepción** y devuelve un 500 en la bandeja — justo lo contrario de lo que el plan promete. Agregar arriba del archivo, junto a los imports existentes:

```python
import logging

logger = logging.getLogger("stacky_agents.api.incident_inbox")
```
Gate: `grep -c "^logger = logging.getLogger" backend/api/incident_inbox.py` = **1**.

**Paso 2 — el pseudocódigo del backend (se inserta después de armar `rows`, antes del `for t in rows` de la línea 161):**

```python
def _last_execution_by_ticket(session, ticket_ids: list[int]) -> dict[int, "AgentExecution"]:
    """UNA query ACOTADA para todo el lote: como mucho 1 fila por ticket.

    v2 (C10): v1 hacía `.filter(ticket_id.in_(ids)).all()` y se quedaba con la
    primera de cada ticket EN MEMORIA. Eso no es N+1, pero trae TODAS las
    ejecuciones históricas de todos los tickets del lote: un fetch sin cota que
    crece con la antigüedad del proyecto, no con el tamaño de la página.

    La subconsulta `max(started_at) GROUP BY ticket_id` deja el trabajo en el
    motor y devuelve <= len(ticket_ids) filas. El índice ix_exec_ticket_started
    (models.py:278, sobre (ticket_id, started_at)) cubre exactamente este acceso.
    """
    if not ticket_ids:
        return {}
    from sqlalchemy import func  # noqa: PLC0415

    from models import AgentExecution  # noqa: PLC0415

    sub = (
        session.query(
            AgentExecution.ticket_id.label("tid"),
            func.max(AgentExecution.started_at).label("ult"),
        )
        .filter(AgentExecution.ticket_id.in_(ticket_ids))
        .group_by(AgentExecution.ticket_id)
        .subquery()
    )
    filas = (
        session.query(AgentExecution)
        .join(
            sub,
            (AgentExecution.ticket_id == sub.c.tid)
            & (AgentExecution.started_at == sub.c.ult),
        )
        .all()
    )
    out: dict[int, AgentExecution] = {}
    for ex in filas:
        # Empate exacto de started_at (posible en SQLite): gana el id mayor.
        prev = out.get(ex.ticket_id)
        if prev is None or ex.id > prev.id:
            out[ex.ticket_id] = ex
    return out


def _inbox_verdict_enabled() -> bool:
    # ⚠ v3 (D13) — se usa EL PATRÓN QUE YA VIVE EN ESTE ARCHIVO:
    # `from config import config as _cfg` + `getattr(_cfg, ...)`, igual que
    # `_enabled()` (:16) y `_actions_enabled()` (:28). El propio archivo tiene
    # un comentario en :14-15 advirtiendo de este gotcha exacto. v2 proponía
    # `import config as _config` + `_config.config` — también funciona, pero
    # mezclar los dos patrones en el archivo que documenta el gotcha es pedir
    # el error. Un solo patrón por archivo.
    from config import config as _cfg  # noqa: PLC0415

    return (
        bool(getattr(_cfg, "STACKY_INCIDENT_INBOX_VERDICT_ENABLED", True))
        and bool(getattr(_cfg, "STACKY_RUN_VERDICT_ENABLED", True))
    )
```

Y en el armado de items:
```python
verdicts = {}
if _inbox_verdict_enabled():
    try:
        ultimas = _last_execution_by_ticket(session, [t.id for t in rows])
        from services.run_evidence import collect_for_executions
        from services.run_verdict import evaluate_verdict
        señales = collect_for_executions(session, list(ultimas.values()))
        # El estado del TICKET manda (es el que el operador ve en la bandeja);
        # `ex.status` es el respaldo. NUNCA se inventa "idle": un estado no
        # terminal hace que evaluate_verdict devuelva None (C9) y entonces no
        # se agrega la clave, que es la verdad ("todavía no hay veredicto").
        by_tid = {t.id: t for t in rows}
        for tid, ex in ultimas.items():
            meta = ex.metadata_dict if isinstance(ex.metadata_dict, dict) else {}
            # ⚠ v3 (D1) — el run manda, el ticket solo empeora. Ver F2.
            v = evaluate_verdict(
                run_status=(ex.status or ""),
                ticket_status=getattr(by_tid.get(tid), "stacky_status", None),
                outcome_reason=meta.get("outcome_reason"),
                signals=señales.get(ex.id),
            )
            if v is not None:              # v2 C9
                verdicts[tid] = v.to_dict()
    except Exception:  # noqa: BLE001 — la bandeja JAMÁS se rompe por el veredicto
        logger.debug("run_verdict 269 en la bandeja falló", exc_info=True)
        verdicts = {}

for t in rows:
    payload = t.to_dict()
    payload["is_open"] = is_open_state(t.ado_state, closed)
    if t.id in verdicts:
        payload["run_verdict"] = verdicts[t.id]  # clave OPCIONAL: nunca se agrega vacía
    items.append(payload)
```
> **Detalle de eficiencia (v2):** se usa `by_tid` armado desde `rows`, que **ya están en memoria**, en vez de `getattr(ex, "ticket", None)`. La relación `AgentExecution.ticket` es `lazy="select"` (`models.py:275`), así que tocarla por fila **sí** habría sido un N+1 encubierto — exactamente lo que el comentario `:149` del endpoint prohíbe.

**Frontend:** en `IncidentInboxPage.tsx`, justo después del badge `openBadge`/`closedBadge` de `:504-506`, agregar:
```tsx
{(() => {
  const v = describeVerdict(item.run_verdict);   // ⚠ run_verdict, NO verdict (C1)
  return v ? <span className={styles.verdictBadge} data-tone={v.tone} title={v.detail}>{v.label}</span> : null;
})()}
```
y en el CSS Module una regla `.verdictBadge` con selectores `[data-tone="exito"|"atencion"|"espera"|"error"]`. **Cero estilo inline** (ratchet de deuda de UI).

**Tests PRIMERO — `backend/tests/test_plan269_inbox_verdict.py`:**

| Test | Qué prueba |
|---|---|
| `test_flag_off_la_bandeja_es_identica` | Con `STACKY_INCIDENT_INBOX_VERDICT_ENABLED=False`, ningún item tiene la clave `run_verdict` y el resto del payload es idéntico clave por clave. |
| `test_flag_on_agrega_verdict_solo_a_los_que_tienen_ejecucion` | Un ticket sin ejecuciones **no** recibe la clave. |
| `test_una_sola_query_extra` | Cuenta las queries del endpoint con 3 tickets y con 30: la diferencia entre ambos casos debe ser **0** (el costo extra no crece con el lote). |
| `test_lote_acotado_no_trae_el_historico` | **v2 C10.** Un ticket con **50** ejecuciones: `_last_execution_by_ticket` devuelve **1** objeto y la query materializa **≤ len(ticket_ids)** filas (se instrumenta contando los objetos devueltos por la query, no las filas del ticket). |
| `test_ultima_ejecucion_es_la_mas_reciente` | Ticket con 3 ejecuciones de `started_at` distintos → el veredicto corresponde a la de `started_at` mayor. Y con 2 ejecuciones de `started_at` **idéntico**, gana la de `id` mayor (empate determinista). |
| `test_excepcion_en_el_veredicto_no_rompe_la_bandeja` | `evaluate_verdict` monkeypatcheado a lanzar → HTTP 200, `items` completos, sin clave `run_verdict`. **Este test es el que fallaba en v1 por el `logger` inexistente (C4): sin el paso 1 da 500, no 200.** |
| `test_no_se_agregan_estados_al_ticket` | El `stacky_status` de cada item es exactamente el mismo con la flag ON y OFF. |

**Comando de aceptación (BINARIO):**
```
cd "Stacky Agents/backend"
.venv\Scripts\python.exe -m pytest tests/test_plan269_inbox_verdict.py -v
.venv\Scripts\python.exe -m pytest tests/test_plan238_incident_inbox_api.py -v
```
**Criterio:** **7/7** verdes en el nuevo (v1 declaraba 6; v2 suma `test_lote_acotado_no_trae_el_historico`), y el del plan 238 **sin regresiones** (es el contrato de forma de la bandeja: `test_plan238_incident_inbox_api.py:147` verifica las 7 claves obligatorias `id, ado_id, title, work_item_type, ado_state, stacky_status, is_open`, que este plan **no quita**).
Además: `cd "Stacky Agents/frontend" && npx tsc --noEmit` sin errores nuevos.

**Flag:** `STACKY_INCIDENT_INBOX_VERDICT_ENABLED` — **default ON**, categoría `observabilidad_notif`. Solo lectura; una query indexada más por request que el operador ya estaba pidiendo.
**Impacto por runtime:** ninguno (lee `AgentExecution`, común a los 3). **Fallback:** una incidencia sin ejecuciones simplemente no muestra chip.
**Trabajo del operador:** ninguno.

---

### F6 — HITL: de "hay 7 falsos rojos" a "corregí este"

**Objetivo (1 frase):** Que la card de reconciliación liste los items concretos y ofrezca al operador un botón para corregir el estado de UNA incidencia, usando el endpoint que **no** publica en ningún sistema externo.

**Valor:** Cierra el GAP 3. Hoy el operador ve un número y no tiene camino.

**Archivos a editar:**
- `Stacky Agents/frontend/src/components/RunReconciliationCard.tsx`
- `Stacky Agents/frontend/src/components/RunReconciliationCard.module.css`
- `Stacky Agents/frontend/src/api/endpoints.ts`
**Archivo a crear (lógica pura):** `Stacky Agents/frontend/src/components/reconciliationActions.ts`
**Archivos de test a crear:** `Stacky Agents/frontend/src/components/reconciliationActions.test.ts` (colocado, como `incidentConsole.test.ts`) y `Stacky Agents/backend/tests/test_plan269_hitl_correccion.py`

**Regla dura del HITL (codificada en el módulo puro):**
```typescript
// Plan 269 F6 — qué acción ofrece cada discrepancia. PURO, sin fetch.
//
// RIEL DURO: Stacky NUNCA cambia un estado terminal por su cuenta. Este módulo
// solo decide QUÉ botón se ofrece; el cambio lo dispara un click del operador.
//
// RIEL DURO 2: la corrección va SIEMPRE a PATCH /api/tickets/{ticket_id}/stacky-status
// (backend/api/tickets.py:1165), que llama a ts.set_status y NO publica nada.
// Está PROHIBIDO usar /api/tickets/by-ado/{ado_id}/stacky-status
// (backend/api/tickets.py:1204) porque ese camino SÍ publica en ADO
// (backend/api/tickets.py:1406) y SÍ cambia el estado del work item (:1495).

export interface ReconciliationItem {
  execution_id: number;
  ticket_id: number;
  kind: string;
  detail: string;
}

export interface ItemAction {
  label: string;          // texto del botón
  targetStatus: string;   // stacky_status al que se movería
  confirm: string;        // texto de la confirmación explícita
  reason: string;         // se manda en el body como `reason`
}

/** Solo 2 de los 5 DISCREPANCY_KINDS tienen una corrección obvia y segura.
 *  Los otros 3 devuelven null: se listan para que el humano mire, sin botón. */
export function actionForItem(item: ReconciliationItem): ItemAction | null {
  if (item.kind === "red_with_delivered_work") {
    return {
      label: "Marcar como terminado",
      targetStatus: "completed",
      confirm: `La incidencia #${item.ticket_id} figura como fallada pero entregó trabajo. ¿La marcás como terminada?`,
      reason: `[269] corrección manual de falso rojo (execution ${item.execution_id})`,
    };
  }
  if (item.kind === "green_with_dirty_close") {
    return {
      label: "Marcar para revisión",
      targetStatus: "needs_review",
      confirm: `La incidencia #${item.ticket_id} figura como terminada sobre un cierre sucio. ¿La marcás para revisar?`,
      reason: `[269] cierre sucio confirmado por el operador (execution ${item.execution_id})`,
    };
  }
  return null;
}

/** La ruta EXACTA del endpoint permitido. Existe como función para que un
 *  test pueda asegurar que nadie escribió "by-ado" acá. */
export function correctionPath(ticketId: number): string {
  return `/api/tickets/${ticketId}/stacky-status`;
}
```

**En el `.tsx`:** debajo de la lista de contadores existente (`RunReconciliationCard.tsx:94-102`), agregar una lista de items (**cap de 25 filas** para no volcar 200 líneas en una card de diagnóstico) donde cada fila muestra `#ticket_id`, el `detail` y —si `actionForItem` devuelve algo **y** `report.hitl_enabled` es `true`— un `<Button size="sm">` que:
1. pide confirmación con el texto `action.confirm` usando **el hook `useConfirm`** (C11: v1 decía "el `Dialog` canónico del repo" sin nombrarlo, y el repo tiene cinco candidatos: `Dialog`, `ConfirmDialog`, `AlertDialog`, `PromptDialog`, `DialogHost`). Literal, copiado del patrón real del repo (`ActiveRunsPanel.tsx:7,33`; `AgentHistoryPage.tsx:10,253`):
   ```tsx
   import { useConfirm } from "./ui";          // barrel: components/ui/index.ts (plan 164)
   ...
   const askConfirm = useConfirm();
   ...
   if (!(await askConfirm({ message: action.confirm }))) return;
   ```
   **Nunca `window.confirm`.**
2. hace `PATCH` a `correctionPath(item.ticket_id)` con body `{ status: action.targetStatus, reason: action.reason }`,
3. al terminar vuelve a llamar `RunReconciliation.get()` para refrescar los contadores.

**Nota sobre el cliente HTTP:** usar `fetch` crudo o `rawPost`, **no** `api.patch`, porque el wrapper `api.*` **lanza** en cualquier respuesta non-2xx y una card de diagnóstico no debe romperse por eso. Mismo criterio que ya documenta `frontend/src/api/endpoints.ts:3168-3169` para `RunReconciliation.get()`.

**Tests PRIMERO — `frontend/src/components/reconciliationActions.test.ts`:**

| Test | Qué prueba |
|---|---|
| `red_with_delivered_work ofrece marcar terminado` | `targetStatus === "completed"` y el `confirm` contiene el número de ticket. |
| `green_with_dirty_close ofrece marcar para revisión` | `targetStatus === "needs_review"`. |
| `los otros 3 kinds no ofrecen acción` | `unclassified_outcome`, `drain_timeout`, `green_self_reported_only` → `null`. |
| `un kind del futuro no ofrece acción` | `actionForItem({kind:"kind_del_futuro",...})` → `null` (nunca un botón inventado). |
| `correctionPath nunca usa by-ado` | `expect(correctionPath(7)).toBe("/api/tickets/7/stacky-status")` y `expect(correctionPath(7)).not.toContain("by-ado")`. |
| `targetStatus siempre es un estado válido` | Los `targetStatus` de las 2 acciones ∈ `["completed","needs_review","error","cancelled","idle","running"]`. **Verificado en v2:** ese array es el espejo EXACTO de `VALID_TICKET_STATUSES` = `NON_TERMINAL_TICKET_STATUSES {idle, running}` ∪ `TERMINAL_STATUSES {completed, error, cancelled, needs_review}` (`backend/services/status_vocabulary.py:11,14,18`). Los 6, ni uno más. |
| `el reason de falso rojo lleva el marcador de calibración` | **[ADICIÓN ARQUITECTO A1].** `actionForItem({kind:"red_with_delivered_work",...}).reason.startsWith("[269] corrección manual de falso rojo")` → `true`. Ese prefijo es lo que `verdict_agreement()` (F8) cuenta para saber si el veredicto está calibrado. Si alguien reescribe el texto sin el prefijo, la calibración queda muda: el test lo impide. |

**Tests PRIMERO — `backend/tests/test_plan269_hitl_correccion.py`:**

| Test | Qué prueba |
|---|---|
| `test_patch_por_ticket_id_no_publica` | `PATCH /api/tickets/<id>/stacky-status` con `{"status":"completed"}` → 200 y **cero** filas nuevas en `agent_html_publish`. **Es la prueba de que el HITL no escribe en el tracker real del operador.** |
| `test_patch_por_ticket_id_no_corre_post_hooks` | Se registra un post-hook que marca una bandera; tras el PATCH la bandera sigue en `False` (el guard y los hooks son de `on_execution_end`, no de `set_status`). |
| `test_correccion_queda_auditada` | Tras el PATCH existe un `TicketStatusEvent` con `changed_by` = el header `X-User-Email` (no `"system"`), lo que además hace que `run_reconciliation._self_reported_ticket_ids` lo vea como mano humana. |
| `test_estado_invalido_devuelve_400` | `{"status":"published"}` → 400 (`services/ticket_status.set_status` valida contra `VALID_TICKET_STATUSES`). |
| `test_flag_off_no_ofrece_hitl` | Con `STACKY_RUN_RECONCILIATION_HITL_ENABLED=False`, el payload de `/api/diag/run-reconciliation` trae `hitl_enabled: false`; con la flag ON trae `true`. La card usa esa clave para decidir si dibuja botones. |
| `test_rama_de_error_no_ofrece_hitl` | **v2 C13.** Con `rr.summarize` monkeypatcheado a lanzar, el endpoint responde 200 por la rama `api/diag.py:1011-1014` y `data.get("hitl_enabled")` es **falsy** (ausente o `false`). Ausencia ⇒ sin botones: falla CERRADO, nunca abierto. |

> **Nota de v2 (C6) — dónde vive `hitl_enabled`, de una sola vez:**
> v1 se contradecía: F6 decía meter la clave en `summarize()` y F8 la metía en `api/diag.py:1015`. Dos fases escribiendo la misma clave en dos lugares distintos.
> **Resolución: la clave se escribe UNA sola vez, en `api/diag.py`, y la escribe F6.** `summarize(discrepancies: list)` (`backend/services/run_reconciliation.py:217`) es una función **PURA** que recibe una lista y no lee configuración; su docstring de módulo (`:7-13`) declara ese aislamiento. Meterle un `getattr(_config.config, ...)` la ensuciaría y rompería sus tests del 254. **`summarize()` no se toca.**
> El diff exacto, en `backend/api/diag.py` (`_config` ya está importado en `:26`):
> ```diff
>      result["ok"] = True
> +    # Plan 269 F6 — la card decide si dibuja botones desde el BACKEND, sin
> +    # que el frontend tenga que conocer flags. Escrita SOLO acá (C6).
> +    result["hitl_enabled"] = bool(
> +        getattr(_config.config, "STACKY_RUN_RECONCILIATION_HITL_ENABLED", True)
> +    )
>      return jsonify(result)
> ```
> Y la misma clave, en `false`, en la rama de error de `:1011-1014` (C13). La rama de flag-OFF de `:999-1003` devuelve **404** y la card ya se auto-oculta con su `catch` (`frontend/src/api/endpoints.ts:3168-3169`), así que ahí no hace falta.
> En el frontend: agregar `hitl_enabled?: boolean` a `interface RunReconciliationResponse` (`frontend/src/api/endpoints.ts:3160-3165`).

**Comando de aceptación (BINARIO):**
```
cd "Stacky Agents/backend"
.venv\Scripts\python.exe -m pytest tests/test_plan269_hitl_correccion.py -v
.venv\Scripts\python.exe -m pytest tests/test_plan254_reconciliation.py -v

cd "Stacky Agents/frontend"
npx vitest run src/components/reconciliationActions.test.ts
npx tsc --noEmit
```
> **Sobre el test colocado:** `src/components/reconciliationActions.test.ts` vive junto al módulo, igual que `incidentConsole.test.ts`, `devBuildModel.test.ts`, `portFindingsModel.test.ts` y otros 3 que ya existen ahí. Verificado en v2: `vite.config.ts` **no** declara bloque `test`, así que vitest usa su `include` por defecto (`**/*.{test,spec}.?(c|m)[jt]s?(x)`), que cubre tanto `src/components/*.test.ts` como `src/utils/__tests__/*.test.ts`. No hay que configurar nada.
**Criterio:** **6/6** backend (v1 declaraba 5; v2 suma `test_rama_de_error_no_ofrece_hitl`) + **7/7** frontend (v1 declaraba 6; v2 suma `el reason de falso rojo lleva el marcador de calibración`); el test del 254 sin regresiones; `tsc` limpio.

**Flag:** `STACKY_RUN_RECONCILIATION_HITL_ENABLED` — **default ON**, categoría `observabilidad_notif`.
**Justificación del default ON — RATIFICADA por la crítica v2, con el código reabierto.** Es la única flag de este plan que habilita una escritura, así que el juez la verificó línea por línea en vez de creerle al plan:
- El endpoint elegido, `PATCH /api/tickets/<int:ticket_id>/stacky-status` (`backend/api/tickets.py:1165`), hace exactamente tres cosas: valida que `status` no venga vacío (`:1175-1176`), verifica que el ticket exista (`:1178-1181`) y llama `ts.set_status(...)` (`:1189-1194`) con `changed_by` del header `X-User-Email` (`:1173`). **No publica, no toca ADO/GitLab, no corre DDL/DML en la BD del operador, no dispara post-hooks** (el guard y los hooks viven en `on_execution_end`, `services/ticket_status.py:293`, no en `set_status`).
- El endpoint **prohibido**, `by-ado` (`:1204`), **sí** publica en ADO (`:1405-1407`, `publish.succeeded`) y **sí** cambia el estado del work item (`:1490-1497`, `update_item_state` / `update_work_item_state`). Confirmado.
- La escritura la dispara **el humano** con un click y una confirmación, y va a la **propia base de Stacky** (`stacky_status` + `TicketStatusEvent`).

Por lo tanto **no** cae en la excepción (B) —que aplica a Stacky escribiendo **por su cuenta** en un sistema real del operador— ni en la (A) —no hay loop ni consumo de tokens. **ON aprobado.** **Si el implementador se ve tentado de usar el endpoint `by-ado`, la flag pasaría a ser excepción (B) y default OFF — por eso está prohibido y hay un test que lo vigila.**

**Impacto por runtime:** ninguno; opera sobre tickets, no sobre runners. **Fallback:** con la flag OFF la card queda exactamente como hoy (solo contadores).
**Trabajo del operador:** ninguno obligatorio. La corrección es una **oportunidad** que aparece solo cuando hay una discrepancia real; si no hay ninguna, la card sigue diciendo "0" y no pide nada.

---

### F7 — Alta completa de las 5 flags y registro en el arnés

**Objetivo (1 frase):** Que las 5 flags estén dadas de alta en los 5 lugares de código y los 6 archivos de test estén registrados en los 2 scripts del arnés, con un test que lo demuestre.

**Valor:** Sin esta fase, `test_default_known_only_for_curated` y el meta-test de registro de tests quedan ROJOS y el plan "funciona" con el arnés roto.

**Archivos a editar (los 7 de la RECETA-FLAG, §3.7):**
1. `Stacky Agents/backend/config.py`
2. `Stacky Agents/backend/services/harness_flags.py` (bloque `FlagSpec`)
3. `Stacky Agents/backend/services/harness_flags.py` (`_CATEGORY_KEYS["observabilidad_notif"]`)
4. `Stacky Agents/backend/services/harness_flags_help.py` (`PLAIN_HELP`)
5. `Stacky Agents/backend/tests/test_harness_flags.py` (`_CURATED_DEFAULTS_ON`)
6. `Stacky Agents/backend/scripts/run_harness_tests.sh`
7. `Stacky Agents/backend/scripts/run_harness_tests.ps1`

**Archivo de test a crear:** `Stacky Agents/backend/tests/test_plan269_flags.py`

**Las 5 flags, exactas:**

| Key | Tipo | Default | Categoría | Fase | ¿Excepción? |
|---|---|---|---|---|---|
| `STACKY_RUN_VERDICT_ENABLED` | bool | **ON** | `observabilidad_notif` | F0 | No |
| `STACKY_RUN_EVIDENCE_COLLECTORS_ENABLED` | bool | **ON** | `observabilidad_notif` | F1 | No |
| `STACKY_UI_RUN_VERDICT_BADGE_ENABLED` | bool | **ON** | `observabilidad_notif` | F2/F3/F4 | No |
| `STACKY_INCIDENT_INBOX_VERDICT_ENABLED` | bool | **ON** | `observabilidad_notif` | F5 | No |
| `STACKY_RUN_RECONCILIATION_HITL_ENABLED` | bool | **ON** | `observabilidad_notif` | F6 | No (justificación completa en F6) |

**Ninguna declara `requires=`** (motivo verificado en §3.7): así no hay que tocar `_REQUIRES_MAP_FROZEN` (`backend/tests/test_harness_flags_requires.py:120`), cuyo test compara el mapa completo por igualdad (`:316`).
**Ninguna es numérica**, así que ninguna toca `_FROZEN_BOUNDS` (`backend/tests/test_harness_flags_bounds.py:149`).

**Los 6 archivos de test a registrar en los 2 scripts del arnés:**
```
tests/test_plan269_run_verdict.py
tests/test_plan269_run_evidence.py
tests/test_plan269_executions_payload.py
tests/test_plan269_inbox_verdict.py
tests/test_plan269_hitl_correccion.py
tests/test_plan269_flags.py
```
- En `run_harness_tests.sh`: una línea por archivo, **sin comillas ni comas**, con un comentario de encabezado del plan (patrón `:847-852`).
- En `run_harness_tests.ps1`: una línea por archivo, **entre comillas dobles y separadas por coma** (patrón `:762-765`). **Cuidado:** el último elemento del array no lleva coma final.

**Textos de `PlainHelp` (ya dentro de los topes de `test_harness_flags_help.py:47-50`):**

```python
"STACKY_RUN_VERDICT_ENABLED": PlainHelp(
    what="Decide si una corrida terminó bien, terminó con advertencias o falló de verdad, mirando además si dejó resultados.",
    on_effect="Si la activás: cada corrida muestra un veredicto de tres niveles con la causa. No cambia ningún estado por su cuenta.",
    off_effect="Si la apagás: se sigue viendo solo el estado crudo, como antes, sin el veredicto ni la explicación.",
    example="Como el mecánico que además de decir 'no arranca' te dice si el auto igual llegó a destino.",
),
"STACKY_RUN_EVIDENCE_COLLECTORS_ENABLED": PlainHelp(
    what="Busca las pruebas de que una corrida dejó resultados: archivos, comentario publicado, cambios en el repositorio y controles pasados.",
    on_effect="Si la activás: el veredicto se apoya en pruebas concretas y te dice cuáles encontró y cuáles no.",
    off_effect="Si la apagás: el veredicto no puede comprobar nada y queda siempre en advertencia por falta de pruebas.",
    example="Como pedir el remito antes de dar por entregado un pedido.",
),
"STACKY_UI_RUN_VERDICT_BADGE_ENABLED": PlainHelp(
    what="Muestra el veredicto de tres niveles en la lista de corridas, no solo adentro del detalle.",
    on_effect="Si la activás: cada fila muestra si terminó bien, con advertencias o con un error real, y podés filtrar por eso.",
    off_effect="Si la apagás: la lista queda como antes, con el estado crudo y sin la columna de veredicto.",
    example="Como el semáforo de tres luces en vez de una lamparita que solo se prende o se apaga.",
),
"STACKY_INCIDENT_INBOX_VERDICT_ENABLED": PlainHelp(
    what="Muestra en la bandeja de incidencias el veredicto de la última corrida de cada una.",
    on_effect="Si la activás: ves de un vistazo qué incidencias necesitan atención de verdad y cuáles solo figuran mal.",
    off_effect="Si la apagás: la bandeja se ve igual que antes y hay que abrir cada incidencia para saberlo.",
    example="Como marcar en la lista del consultorio quién está grave y quién solo espera el alta.",
),
"STACKY_RUN_RECONCILIATION_HITL_ENABLED": PlainHelp(
    what="Te deja corregir a mano, desde la pantalla, el estado de una corrida que quedó mal marcada.",
    on_effect="Si la activás: aparece un botón para arreglar cada caso. Nada se corrige solo: siempre decidís vos y queda registrado.",
    off_effect="Si la apagás: seguís viendo cuántos casos hay mal marcados, pero no hay botón para corregirlos desde ahí.",
    example="Como el arqueo de caja que además te deja anotar el ajuste, pero solo si vos lo firmás.",
),
```

**Tests PRIMERO — `backend/tests/test_plan269_flags.py`** (patrón copiado de `backend/tests/test_evolution_flags.py:55,83`):

| Test | Qué prueba |
|---|---|
| `test_las_5_flags_estan_en_el_registro` | Cada key ∈ `FLAG_REGISTRY`. |
| `test_las_5_son_default_true` | `spec.default is True` para las 5. |
| `test_las_5_estan_categorizadas` | Cada key aparece en el aplanado de `_CATEGORY_KEYS.values()`. |
| `test_las_5_tienen_plain_help` | Cada key ∈ `PLAIN_HELP` de `services.harness_flags_help`. |
| `test_las_5_estan_curadas` | Cada key ∈ `tests.test_harness_flags._CURATED_DEFAULTS_ON`. |
| `test_las_5_estan_en_config` | `hasattr(config.config, key)` y el valor por defecto es `True`. |
| `test_ninguna_declara_requires` | `getattr(spec, "requires", None)` es falsy para las 5 (así `_REQUIRES_MAP_FROZEN` no cambia). |
| `test_los_6_tests_estan_en_los_dos_scripts` | Lee `scripts/run_harness_tests.sh` y `scripts/run_harness_tests.ps1` como texto y asegura que cada uno de los 6 nombres de archivo aparece en **ambos**. |
| `test_los_centinelas_del_dod_si_pueden_disparar` | **[ADICIÓN ARQUITECTO A4].** Ver abajo. |

#### [ADICIÓN ARQUITECTO A4] — Los centinelas del DoD se auto-testean

**El agujero que tapa, con nombre, apellido y reincidencia.** Este plan defiende sus invariantes con **~20 gates de `grep`** en el DoD. Los gates de `grep` de este documento **ya fallaron dos veces, en dos versiones distintas, cada una encontrada por una pasada de juez diferente**:

| Versión | Gate roto | Por qué no disparaba | Quién lo encontró |
|---|---|---|---|
| v2 | `grep -c "verdictTone"` (KPI K3) | El símbolo real es `verdictChipTone`, y `"verdictTone"` **no** es substring de `"verdictChipTone"` | juez v2→v3 (**D6**) |
| v3 | `grep -rn 'stacky_status", None) or ex.status'` (**"el gate más importante del plan"**) | El literal lleva **espacios** tras las comas; la variante de F5 —que el propio v3 transcribe— **no** los tiene. 1 de 3 reintroducciones atrapada | juez v3→v4 (**E2**) |
| v3 | `grep -n "def set_stacky_status"` (anclaje §0) | Es **prefijo** de `set_stacky_status_by_ado` ⇒ **2 hits**, y el hit equivocado publica en el ADO real | juez v3→v4 (**E4**) |

Un gate que no puede disparar es **peor que no tener gate**: da confianza falsa y ocupa el lugar del test que sí haría falta. Y el patrón es sistemático, no mala suerte: **nadie prueba los centinelas.** Se escriben mirando el código correcto y se asume que atraparían al incorrecto.

**La regla que queda escrita:**

> **Un centinela textual no está terminado hasta que se lo corrió contra el pecado que dice prohibir.** Si el gate es negativo (*"esto NO debe aparecer"*), tiene que existir una sonda que lo haga disparar. Si no se puede construir esa sonda, el gate correcto es **positivo** (*"esto SÍ debe aparecer"*), que no depende de adivinar la ortografía del error.

**Qué se agrega — un solo test, cero archivos nuevos, cero flags:** `test_los_centinelas_del_dod_si_pueden_disparar` en `test_plan269_flags.py` (archivo que F7 **ya** crea y **ya** registra en los 2 scripts del arnés). El test lleva una tabla de `(centinela, sondas_que_deben_matchear, sondas_que_NO_deben_matchear)` y verifica **las dos direcciones** con `re`, en memoria, sin tocar el disco ni el árbol:

```python
import re

# (regex del centinela del DoD, sondas POSITIVAS, sondas NEGATIVAS)
_CENTINELAS = [
    (
        # D1/E2 — el anti-patrón que colapsa run y ticket, en sus 3 ortografías.
        r'stacky_status"? *,? *(None)?\)? *or *[a-z_]+\.status',
        [
            'estado = (getattr(ticket, "stacky_status", None) or ex.status or "")',
            'estado = getattr(by_tid.get(tid),"stacky_status",None) or ex.status or ""',
            'estado = ticket.stacky_status or ex.status or ""',
        ],
        [
            'run_status=(ex.status or ""),',
            'ticket_status=getattr(ticket, "stacky_status", None),',
        ],
    ),
    (
        # D6 — el chip del veredicto. El símbolo REAL es verdictChipTone.
        r"verdictChipTone",
        ["  const t = verdictChipTone(v.tone);"],
        ["  const t = runStatusTone(item.status);"],
    ),
    (
        # E4 — el endpoint PERMITIDO, sin arrastrar el prohibido `_by_ado`.
        r"def set_stacky_status\(",
        ["def set_stacky_status(ticket_id: int):"],
        ["def set_stacky_status_by_ado(ado_id: int):"],
    ),
]


def test_los_centinelas_del_dod_si_pueden_disparar():
    """A4 — cada gate de grep del DoD se prueba en LAS DOS direcciones.

    Un centinela que no matchea el pecado que prohíbe es confianza falsa: ya
    pasó en v2 (D6) y dos veces en v3 (E2, E4). Este test lo hace imposible.
    """
    for patron, deben, no_deben in _CENTINELAS:
        rx = re.compile(patron)
        for s in deben:
            assert rx.search(s), f"centinela {patron!r} NO atrapa el pecado: {s!r}"
        for s in no_deben:
            assert not rx.search(s), f"centinela {patron!r} da FALSO POSITIVO en: {s!r}"
```

**Verificado corriendo en la crítica v4, no propuesto a ciegas:** las 3 sondas positivas del primer centinela dan **3/3 match** con esa regex, y las 2 negativas dan **0/2** — medido con `grep -rEn` sobre archivos sonda reales antes de escribirlo acá.

**Por qué sale gratis y respeta todos los rieles:** no agrega archivo (va en uno que F7 ya registra), no agrega flag, no agrega dependencia (`re` es stdlib), no toca los 3 runtimes (es un test de backend puro, sin DB ni disco), cero trabajo del operador, no corre en producción ni en ningún loop, y **reusa** el patrón de "validar texto con `re` en memoria" que el propio plan ya usa en `test_los_6_tests_estan_en_los_dos_scripts` y en `test_espejo_ts_no_tiene_drift` (A2). Cuando alguien agregue un gate nuevo al DoD, agrega su fila acá: el costo marginal es una línea.

**Comando de aceptación (BINARIO):**
```
cd "Stacky Agents/backend"
.venv\Scripts\python.exe -m pytest tests/test_plan269_flags.py::test_los_centinelas_del_dod_si_pueden_disparar -v
```

---

**Comando de aceptación (BINARIO):**
```
cd "Stacky Agents/backend"
.venv\Scripts\python.exe -m pytest tests/test_plan269_flags.py -v
.venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -v
.venv\Scripts\python.exe -m pytest tests/test_harness_flags_help.py -v
.venv\Scripts\python.exe -m pytest tests/test_harness_flags_requires.py -v
.venv\Scripts\python.exe -m pytest tests/test_harness_flags_bounds.py -v
```
**Criterio:** **9/9** verdes en el nuevo (v3 declaraba 8; **v4 suma `test_los_centinelas_del_dod_si_pueden_disparar` (A4) → 9**). En los otros 4: **cero fallos nuevos respecto a HEAD**.
> **Medido en la crítica v4:** el cuerpo de A4 tal como está escrito arriba se corrió con `.venv\Scripts\python.exe -m pytest` (py 3.13.5) y da **1 passed**. No es pseudocódigo.
> **Gotcha conocido y cómo tratarlo:** `test_harness_flags_help.py` tiene fallos ajenos preexistentes en este árbol. **No se argumenta "ya estaba rojo": se prueba.** Antes de tocar nada, correr esos 4 archivos y guardar la salida; después de F7, comparar. Si aparece un fallo que menciona una key de este plan, es propio y hay que arreglarlo; si menciona otra key, es ajeno y se documenta con el diff de salidas.

**Impacto por runtime:** ninguno. **Trabajo del operador:** ninguno (todas ON de fábrica).

---

### F8 — KPI medido y cierre

**Objetivo (1 frase):** Que el plan pueda demostrar con un número que redujo el falso error visible, y no solo afirmarlo.

**Valor:** Es la lección del 254 F5 aplicada a sí mismo: sin medición, "creemos que lo arreglamos".

**Archivos a editar:**
- `Stacky Agents/backend/services/run_verdict.py` (agregar el contador; sigue siendo el único módulo que conoce el veredicto)
- `Stacky Agents/backend/api/diag.py` (extender el payload de `/run-reconciliation`, `:987-1016`)
- `Stacky Agents/frontend/src/components/RunReconciliationCard.tsx` (mostrar el conteo por nivel)
**Archivo de test:** se **amplía** `Stacky Agents/backend/tests/test_plan269_run_verdict.py` (no se crea uno nuevo: menos archivos que registrar en el arnés).

> ### ⚠ v3 (D5) — DE DÓNDE SALE LA EVIDENCIA. Sin esto, F8 nace muerta.
>
> `count_by_level` y `verdict_agreement` cuentan **`falso_rojo_probable`**, una causa que **solo** existe si `delivery_strength(signals) >= UMBRAL_ENTREGA`. Y `delivery_strength` **solo suma señales `True`**, que **solo** las produce `collect_for_executions` (F1). v2 nunca dijo de dónde salían esas señales. Las dos consecuencias, ambas malas:
>
> - **Si no llama a los colectores:** `fuerza` es 0 en el 100% de los casos ⇒ `falso_rojo_probable` es **estructuralmente 0 para siempre** ⇒ **K1 —el KPI estrella de este plan— reporta 0 permanente**, `verdict_agreement.propuestos` es 0 y `ratio` es `None` para siempre: **la ADICIÓN A1 completa queda inerte**. El DoD "los KPI están medidos" sería una mentira verde.
> - **Si los llama sin cota:** F8 mete un barrido de **30 días con lecturas de disco** adentro del `GET /api/diag/run-reconciliation`, que se dispara en **cada carga de la card** — contradiciendo R3 y el propio `COLLECTOR_BUDGET_S`.
>
> **Resolución v3, las tres reglas:**
> 1. **Sí usan los colectores**, vía `collect_for_executions(session, rows)` — el mismo del que ya depende todo el plan. Nada de una segunda implementación.
> 2. **Con cota dura:** `limit=200`, el mismo tope que `run_reconciliation.scan_recent()` ya usa (`services/run_reconciliation.py:168`), **y su propio `_Budget(COLLECTOR_BUDGET_S)`**. El conteo es una **muestra acotada declarada como tal**, no un censo del histórico.
> 3. **Con los colectores OFF, `falso_rojo_probable` vale `null`, NUNCA 0.** `0` afirmaría "no hay ningún falso rojo"; la verdad es "no pude mirar". Es el principio P2 aplicado al propio KPI del plan: **la ignorancia no se reporta como buena noticia.**

**Función a agregar (read-only, sin loop, bajo demanda):**
```python
def count_by_level(days: int = 30, limit: int = 200) -> dict:
    """Cuántas corridas terminadas de los últimos N días caen en cada nivel.

    READ-ONLY: no escribe una sola fila. Bajo demanda: NO corre en un loop ni en
    un daemon. Nunca lanza: ante cualquier fallo devuelve los 3 niveles en 0.

    v3 (D5) — MUESTRA ACOTADA, no censo:
      · Toma como mucho `limit` ejecuciones terminadas (default 200, el mismo
        tope de run_reconciliation.scan_recent, services/run_reconciliation.py:168).
      · Resuelve la evidencia con services.run_evidence.collect_for_executions,
        que trae su propio _Budget: si se agota, las señales quedan None y el
        conteo lo refleja. NO se reimplementa la recolección.
      · Cada fila se juzga con evaluate_verdict(run_status=ex.status,
        ticket_status=<stacky_status>, ...) — la firma v3 (D1).
      · Si los colectores están OFF (STACKY_RUN_EVIDENCE_COLLECTORS_ENABLED),
        `falso_rojo_probable` es None, NO 0: sin evidencia no se puede afirmar
        que no haya falsos rojos. Los 3 niveles sí se pueden contar igual,
        porque el nivel base no depende de la evidencia.
      · Declara `sampled: True` y `limit` en la respuesta para que nadie lea el
        número como un total del histórico.

    Vive acá y no en un módulo nuevo para que `run_verdict.py` siga siendo el
    único dueño del vocabulario del veredicto. La parte pura (evaluate_verdict)
    no se contamina: esta función importa DB de forma perezosa, adentro.
    """
```
Devuelve exactamente (**v3 D5**: 2 claves nuevas de honestidad, y `falso_rojo_probable` puede ser `null`):
```json
{"days": 30, "limit": 200, "sampled": true,
 "exito": 0, "advertencia": 0, "error_real": 0, "falso_rojo_probable": null}
```
Declarando **siempre** las **SIETE** claves aunque valgan 0 o `null` (mismo criterio que `run_reconciliation.summarize()`, `services/run_reconciliation.py:223`: *"un contador que desaparece cuando vale cero no sirve para mirar una tendencia"*).

> ⚠ **v4 (E5) — el v3 declaraba este contrato con TRES conteos distintos y el test nacía ambiguo.** El JSON de arriba tiene **7** claves (`days`, `limit`, `sampled`, `exito`, `advertencia`, `error_real`, `falso_rojo_probable`), pero el v3 escribía *"las **6** claves"* acá, `test_count_by_level_declara_las_**6**_claves_siempre` en la tabla de tests (listando solo `days, limit, sampled` + los 3 niveles, es decir **sin** `falso_rojo_probable`) y *"devuelve las **4** claves en 0"* en el pie de F8. Un test implementado por igualdad de conjuntos contra 6 es **ROJO**. **El número congelado es 7**, en los tres lugares, y `falso_rojo_probable` **siempre** está presente (con valor `null` si los colectores están OFF — ése es justamente el punto de D5).

**En `api/diag.py`,** justo antes de `result["ok"] = True` (`:1015`), agregar:
```python
try:
    from services.run_verdict import count_by_level, verdict_agreement  # noqa: PLC0415
    result["verdict_counts"] = count_by_level(days=30)
    result["verdict_agreement"] = verdict_agreement(days=30)   # ADICIÓN ARQUITECTO A1
except Exception:  # noqa: BLE001
    logger.debug("verdict_counts 269 falló", exc_info=True)
```
> **v2 (C6): F8 YA NO escribe `hitl_enabled`.** Esa clave la escribe **F6**, una sola vez, unas líneas más abajo. v1 la escribía en las dos fases.

---

#### [ADICIÓN ARQUITECTO A1] — El veredicto se calibra con lo que el operador realmente hizo

**El agujero que tapa.** Todo este plan descansa en tres números **inventados**: los pesos `2/2/2/1/1` de `_PESO` y el `UMBRAL_ENTREGA = 2`. Con ellos se decide qué corrida se le presenta al operador como `falso_rojo_probable`. v1 no tiene **ninguna** forma de saber si esos números aciertan: mide *cuántos* veredictos emite (`count_by_level`), nunca *cuántos eran correctos*. Un plan que se auto-mide por volumen y no por acierto es exactamente la lección que el 254 F5 dejó escrita.

**Por qué sale gratis.** El dato de verdad **ya se está escribiendo**, sin tabla nueva y sin trabajo del operador: cada corrección de F6 crea un `TicketStatusEvent` (`services/ticket_status.py:208-215`) cuyo `reason` lo controla este plan y arranca con el marcador literal `[269] corrección manual de falso rojo`. Cada vez que el operador aprieta ese botón está **votando a favor** del veredicto. No hay que pedirle nada más.

**Qué se agrega — `verdict_agreement(days)` en `services/run_verdict.py`:**

```python
CORRECTION_MARKER = "[269] corrección manual de falso rojo"

def verdict_agreement(days: int = 30) -> dict:
    """Precisión OBSERVADA del veredicto `falso_rojo_probable`. READ-ONLY.

    propuestos  = corridas de los últimos N días con cause == falso_rojo_probable
    confirmados = TicketStatusEvent de esos tickets cuyo `reason` empieza con
                  CORRECTION_MARKER (el operador apretó el botón de F6)
    ratio       = confirmados / propuestos, o None si propuestos == 0

    Bajo demanda: NO corre en loop ni en daemon. No escribe una sola fila.
    Nunca lanza: ante cualquier fallo devuelve las 3 claves en 0/None.
    """
```
Devuelve **siempre** las 3 claves, aunque valgan 0 (mismo criterio que `run_reconciliation.summarize()`, `:223`):
```json
{"days": 30, "propuestos": 0, "confirmados": 0, "ratio": null}
```

**En la card (`RunReconciliationCard.tsx`), una línea de texto llano y nada más:**
> *"De los 14 casos que marqué como probable falso rojo en 30 días, corregiste 11 (79%)."*
> Si `propuestos === 0`: *"Todavía no hay casos suficientes para saber si estoy calibrado."*

**Los rieles que respeta, uno por uno:**
- **Human-in-the-loop:** el número se **muestra**, jamás se usa para auto-ajustar `_PESO` ni `UMBRAL_ENTREGA`. Riel duro escrito en el docstring y vigilado por un test (`test_agreement_no_muta_los_pesos`). Stacky **no** se auto-tunea: le da al operador la evidencia para que **él** decida si mover el umbral en un plan futuro.
- **Cero trabajo del operador:** no hay encuesta, no hay "¿te sirvió?", no hay ningún click nuevo. El dato es un subproducto del botón que F6 ya le da.
- **3 runtimes:** lee `AgentExecution` + `TicketStatusEvent`, comunes a Codex CLI, Claude Code CLI y Copilot. Si un runtime no produce correcciones, `propuestos > 0` y `confirmados == 0` — un dato honesto, no un error.
- **Sin autonomía:** bajo demanda, dentro del mismo GET que el operador ya estaba pidiendo. Cero loops, cero daemons.
- **Reuso:** cero tablas nuevas, cero flags nuevas (va bajo `STACKY_RUN_VERDICT_ENABLED`), cero columnas nuevas. Usa el `reason` que F6 ya escribe.
- **No degrada:** una query acotada por fecha dentro de un endpoint de diagnóstico que ya hace un `scan_recent(limit=200)`.

---

**Tests a agregar en `test_plan269_run_verdict.py`:**

| Test | Qué prueba |
|---|---|
| `test_count_by_level_declara_las_7_claves_siempre` | **v4 E5 (el v3 decía 6 y el dict tiene 7 ⇒ test ROJO).** Con base vacía, `set(count_by_level()) == {"days", "limit", "sampled", "exito", "advertencia", "error_real", "falso_rojo_probable"}` — las **7**, por igualdad de conjuntos, nunca un dict parcial. `falso_rojo_probable` está presente **siempre** (puede valer `null`). |
| `test_count_by_level_nunca_lanza` | Con `session_scope` monkeypatcheado a lanzar → **las 7 claves** presentes (v4 E5), los 3 niveles en 0 y `falso_rojo_probable` en `null` (no se pudo mirar). |
| `test_count_by_level_no_escribe` | Sesión falsa cuyos `add/commit/flush` lanzan `AssertionError` → pasa. |
| `test_count_by_level_usa_los_colectores` | **v3 D5.** `collect_for_executions` monkeypatcheado para devolver una señal fuerte sobre una ejecución `error` → `falso_rojo_probable == 1`. **Sin llamar a los colectores este test es ROJO** y demuestra que el KPI no es un cero estructural. |
| `test_count_by_level_esta_acotado` | **v3 D5.** Con 500 ejecuciones sembradas y `limit=200`, la query materializa **≤ 200** filas y `collect_for_executions` recibe **≤ 200** objetos. El conteo no crece con la antigüedad del proyecto. |
| `test_count_by_level_sin_colectores_reporta_null` | **v3 D5.** Con `STACKY_RUN_EVIDENCE_COLLECTORS_ENABLED=False`: `falso_rojo_probable is None` (**no** `0`) y los 3 niveles se cuentan igual. Sin evidencia no se afirma "no hay falsos rojos". |
| `test_agreement_declara_las_3_claves_siempre` | **A1.** Base vacía → `{"days":30,"propuestos":0,"confirmados":0,"ratio":None}`. `ratio` es `None`, **nunca 0.0** (0 de 0 no es "0% de acierto", es "no sé"). |
| `test_agreement_cuenta_solo_el_marcador_del_269` | **A1.** Un `TicketStatusEvent` con `reason="cierre manual"` NO cuenta; uno que empieza con `CORRECTION_MARKER` sí. Evita contar correcciones ajenas como acuerdo con el veredicto. |
| `test_agreement_no_muta_los_pesos` | **A1, riel duro.** Tras llamar `verdict_agreement()`, `_PESO` y `UMBRAL_ENTREGA` son idénticos a antes. El sistema **no se auto-calibra**: solo informa. |

**Comando de aceptación (BINARIO):**
```
cd "Stacky Agents/backend"
.venv\Scripts\python.exe -m pytest tests/test_plan269_run_verdict.py -v
```
**Criterio:** **29/29** verdes (20 de F0 + 9 de F8). Y las mediciones finales de K1 y K6, anotadas en §1:
```
.venv\Scripts\python.exe -c "from services.run_verdict import count_by_level, verdict_agreement; print(count_by_level(30)); print(verdict_agreement(30))"
```

**Flag:** `STACKY_RUN_VERDICT_ENABLED` (la de F0). Con ella OFF, `count_by_level` devuelve **las 7 claves** con los 3 niveles en 0 y `falso_rojo_probable` en **`null`** (*v4 E5: el v3 decía "las 4 claves en 0" — eran 7, y `falso_rojo_probable` nunca se reporta como 0*), y la card no muestra la línea.
**Impacto por runtime:** ninguno. **Trabajo del operador:** ninguno.

---

## 6. Riesgos y mitigaciones

| # | Riesgo | Mitigación (concreta y verificable) |
|---|---|---|
| R1 | **Crear un falso VERDE nuevo** — el peor resultado posible; convertiría este plan en un retroceso. | Invariante `I1` codificado en `test_I1_un_error_jamas_recibe_exito`, que barre la grilla **completa** de combinaciones. Estructuralmente: la **regla 7** (única que produce `exito`; v2 decía "regla 6", número heredado de la numeración de v1 — **D8**) es inalcanzable desde `base == "error_real"`. **Y desde v3 (D1) `base` se ancla en `run_status`**, así que la garantía vale en TODO call-site, no solo adentro de la función: probado con **17.010** combinaciones (grilla completa, v4 E6), **0** violaciones. |
| R2 | **La ignorancia se lee como éxito** — una fuente caída hace parecer que todo entregó. | Invariante `I2` codificado. `None` suma 0 en `delivery_strength` (igual que `False`) y, en la rama verde, dispara `evidencia_indeterminada` (advertencia). Nunca mejora el nivel. |
| R3 | **Los colectores degradan la performance del listado** — lecturas de disco por fila. | `_Budget` es un presupuesto **TOTAL del lote** (`COLLECTOR_BUDGET_S = 2.0`), consultado antes de cada lectura; agotado ⇒ `None` y sigue. `publicado_en_tracker` es **1 query** para todo el lote. `test_publicado_en_una_sola_query` y `test_sin_n_mas_uno` lo prueban. La bandeja agrega **exactamente 1** query indexada (`ix_exec_ticket_started`, `models.py:278`), probado por `test_una_sola_query_extra`. |
| R4 | **Se rompe el listado si un colector falla.** | Todo el bloque de veredicto está envuelto en `try/except Exception` que degrada a `{}` y loguea en `debug`. Probado por `test_colector_que_lanza_no_rompe_ninguno_de_los_dos` (F2; v2 lo nombraba mal - D9) y `test_excepcion_en_el_veredicto_no_rompe_la_bandeja` (F5). |
| R5 | **El implementador usa el endpoint `by-ado` y publica en el ADO real del operador.** | Prohibición escrita en 3 lugares del plan (§3.6, F6, comentario del módulo) + test `correctionPath nunca usa by-ado` + test backend `test_patch_por_ticket_id_no_publica` que cuenta filas en `agent_html_publish`. |
| R6 | **Hipótesis no probadas sobre la forma de `contract_result`** (H1). **H2 ya no es un riesgo: se resolvió (C5).** | H1 sigue **declarada como hipótesis** en F1, con un test que la **DISCRIMINA**. H2 se convirtió en hecho verificado: clave `exec_verification`, campo `passed` tri-estado (`services/exec_verification.py:70,81`). |
| R14 | **(v2, C1) Pisar una clave viva del payload.** `verdict` ya existe (`models.py:255,327`). | La clave nueva es `run_verdict`. Test `test_no_pisa_el_verdict_del_modelo` + gate `grep -c '"verdict"' backend/services/run_verdict.py` = 0. |
| R15 | **(v2, C2) Que la UI nueva quede inerte** porque el backend enriquece un endpoint que esa pantalla no usa. | F2 cablea **los dos** handlers (`list_executions:96` y `executions_history:442`) y el test `test_history_endpoint_tambien_trae_run_verdict` lo prueba **en el endpoint que F4 consume**, no en el otro. |
| R16 | **(v2, C3) Desalinear una tabla con columnas configurables.** | La columna se registra en `HISTORY_COLUMNS` y las dos celdas se guardan con `isColVisible`. Gate: el `grep` de `isColVisible(tablePrefs, "veredicto")` debe dar **exactamente 2**. |
| R17 | **(v2, C4) Que el manejador de errores sea el que rompa.** Un `logger` inexistente convierte una degradación silenciosa en un 500. | F5 paso 1 declara el logger con gate de grep. Regla general para el implementador: **antes de escribir `logger.` en un módulo, verificá que ese módulo tenga logger.** |
| R18 | **(v2, A1) Que la calibración se convierta en auto-tuneo.** Un número de acierto invita a "ajustar solo el umbral". | Riel duro en el docstring + `test_agreement_no_muta_los_pesos`. El número se muestra; mover `_PESO`/`UMBRAL_ENTREGA` es una decisión humana de un plan futuro. |
| R19 | **(v3, D1) EL RIESGO MÁS GRAVE DEL PLAN: crear un falso VERDE desde el CABLEADO, con el test del núcleo en verde.** Un invariante probado solo sobre la función pura no ve un bug de costura. | Firma `evaluate_verdict(run_status=..., ticket_status=...)` donde el ticket **solo empeora** (`_peor`). Tres tests: dos de núcleo (`test_I1b_...`, `test_el_ticket_solo_empeora_nunca_mejora`) **y uno de BORDE** (`test_ticket_completed_no_blanquea_un_run_error`, A3) que pide el JSON a los dos endpoints y —desde v4 (E1)— asserta **los dos lados del contraste** con evidencia sembrada en las dos ejecuciones. Gate **positivo** (`run_status=` presente en los dos call-sites) más centinela negativo `-E` **verificado 3/3 con 0 falsos positivos** (v4, E2: el del v3 atrapaba 1 de 3). Verificado corriendo: **17.010 combinaciones, 0 violaciones**. |
| R24 | **(v4, E2/E4/D6) Un gate de `grep` que NO PUEDE DISPARAR** — confianza falsa que ocupa el lugar del test que hacía falta. Ya pasó 3 veces en este mismo documento. | Gates **positivos** siempre que sea posible ("la línea correcta está presente" no depende de adivinar cómo se escribirá el error). Centinelas negativos con `-E` e insensibles a espacios. Y **[ADICIÓN ARQUITECTO A4]**: `test_los_centinelas_del_dod_si_pueden_disparar` prueba cada centinela contra sondas positivas **y** negativas. Regla: **todo grep de anclaje debe devolver EXACTAMENTE 1 hit**; si devuelve 2, el patrón está mal (E4: `def set_stacky_status` devolvía también el endpoint que publica en ADO). |
| R25 | **(v4, E3) Reservar un número de plan que otro plan ya reservó POR TEXTO** — sin archivo, así que `ls` no lo ve. | Este documento **no asigna número** a la segunda mitad. Procedimiento de §0: `ls` en frío **más** `grep -rn "plan 27[0-9]\|27[0-9]_PLAN"` para cazar reservas escritas. **Hoy el 272 está reservado dos veces** (271 §6.1 y 270). |
| R26 | **(v4, E1) Un test de gate que nace ROJO porque asserta un resultado que sus propios datos no pueden producir.** | A3 siembra evidencia en **las dos** ejecuciones y asserta el contraste completo. Regla: **antes de escribir el assert, calculá el valor esperado con la función real** — para el veredicto eso significa calcular el `strength` de la fila sembrada contra `UMBRAL_ENTREGA`, no suponerlo. |
| R20 | **(v3, D2) El colector reintroduce el falso rojo que el plan viene a matar**, por filtrar `status='ok'` en una tabla que tiene **4** valores. | `status IN ('ok','idempotent_replay')` + `test_publicado_cuenta_idempotent_replay`. Regla general: **antes de filtrar por un valor de una columna de estado, censá los literales que el escritor puede producir** (`grep -n 'status="' <escritor>.py`), no los que dice el comentario de la columna. |
| R21 | **(v3, D3/D4) Implementar contra una foto vieja del repo** — anclar por número en archivos que otros dos planes vivos van a mover, y numerar un plan nuevo con un número ya ocupado. | §0: orden 271→270→269, tabla de colisión, **regla de anclaje por SÍMBOLO** con los greps exactos, y `ls "Stacky Agents/docs/"` en frío antes de escribir cualquier número. |
| R22 | **(v3, D5) Un KPI que es cero por construcción** y una calibración que nunca tiene datos: el plan se declararía exitoso midiendo una constante. | `count_by_level`/`verdict_agreement` reusan `collect_for_executions` con cota `limit=200` y `_Budget`; sin colectores reportan **`null`**, no `0`. Tres tests lo fijan. |
| R23 | **(v3, D7) Parchear un rango de líneas que no contiene el ancla** y desalinear la tabla. | Mapa completo de los 11 `<th>` con su línea real (F4 paso 2), y la posición del nuevo definida por sus **vecinos** (`estado` / `duracion`), no por un número suelto. |
| R7 | **Alta de flag incompleta** ⇒ `test_default_known_only_for_curated` rojo. | F7 lista los 7 archivos con el anclaje del patrón a copiar, y `test_plan269_flags.py` verifica los 5 lugares + los 2 scripts del arnés en 8 asserts. |
| R8 | **Rojos preexistentes ajenos** en `test_harness_flags_help.py` se atribuyen a este plan. | F7 obliga a capturar la salida de los 4 archivos de flags **antes** de tocar nada y comparar después. Si el fallo menciona una key ajena, se documenta con el diff; no se argumenta de memoria. |
| R9 | **Columna nueva sin `<th>`** desalinea la tabla del historial. | Nota explícita en F4 + gate `npx tsc --noEmit` y verificación visual manual (el render no es automatizable acá, ver §3.8 punto 2). |
| R10 | **Estilo inline en un `.tsx`** dispara el ratchet de deuda de UI. | El plan no crea ningún `.tsx` nuevo; los badges usan CSS Modules con `data-tone`. Gate: `grep -c "style={{"` no debe aumentar respecto a HEAD en los 3 `.tsx` editados. |
| R11 | **Contaminación cross-file de vitest** da un falso rojo/verde. | Todos los comandos de aceptación del frontend corren **un archivo por vez** con `npx vitest run <ruta>`. |
| R12 | **`SQLITE_LOCKED` bajo pytest** hace flaky un test de backend. | Todos los comandos corren **un archivo por vez**. Si un test de este plan resulta flaky, se corre 8-12 veces antes de declararlo verde. |
| R13 | **Regresión sobre el 254**, que acaba de estabilizar el cierre. | Este plan **no toca ningún sitio de cierre** (P3). F2 y F6 exigen correr `test_plan254_outcome_reason.py` y `test_plan254_reconciliation.py` sin regresiones. |

---

## 7. Fuera de scope (explícito)

1. **`pages/TicketBoard.tsx`** — no se toca. Tiene 1355 líneas, colores hardcodeados sin módulo puro (`:82`, `:103`) y una cola de trabajo ajena pendiente. Agregar el veredicto ahí es un plan aparte que primero debe extraer `stateColor()` a un `.ts` puro.
2. **Cambiar `status_vocabulary.py`** — no se agrega ni un estado. El veredicto es una dimensión separada (P5).
3. **Modificar `classify_outcome_reason`** — la firma del 254 (`services/run_outcome.py:55`) queda **intacta**. Agregarle parámetros rompería sus 4 call-sites y sus tests.
4. **Corrección automática de estados** — Stacky nunca corrige por su cuenta. Ni con un umbral, ni con "alta confianza", ni con un modo experto.
5. **Llamar a la API de ADO/GitLab para verificar la publicación** — la evidencia sale de la tabla local `agent_html_publish`. Nada de red en un colector.
6. **Un barrido periódico del veredicto** — nada corre en loop. Si algún día se quisiera, se engancharía al `_maintenance_loop` compartido del plan 253 F4, como ya documenta `run_reconciliation.py:11-13`; no se inventa otro loop.
7. **Reintentar corridas desde la card de reconciliación** — el HITL de F6 solo corrige el estado. Reintentar es otra capacidad, con otro riesgo.
8. **Tests de render de React** — imposible en este repo (§3.8 punto 2). La verificación visual es manual.

---

## 8. Glosario, orden de implementación y DoD

### Glosario

| Término | Significado en este plan |
|---|---|
| **`outcome_reason`** | Los 9 desenlaces del 254 (`services/run_outcome.py:13`). Responde **por qué terminó**. Señales del proceso. |
| **Veredicto** | Los 3 niveles del 269 (`exito` / `advertencia` / `error_real`) y sus **9** causas. Responde **si cumplió su objetivo**. Combina el `outcome_reason` con evidencia. Viaja en el payload bajo la clave **`run_verdict`** (nunca `verdict`: esa ya existe y es la revisión humana, `models.py:255`). **Un run no terminado no tiene veredicto** (`None`). |
| **Acuerdo observado** | **[A1]** Proporción de veredictos `falso_rojo_probable` que el operador **confirmó** apretando el botón de F6. Se deduce del `reason` que F6 ya escribe. Se **muestra**; nunca se usa para auto-ajustar los pesos. |
| **Señal de evidencia** | Uno de los 5 hechos de `EVIDENCE_SIGNALS`, tri-estado: `True` presente, `False` ausente, `None` **desconocida**. |
| **Fuerza de entrega** | Suma de pesos de las señales **presentes**. Umbral `UMBRAL_ENTREGA = 2`. |
| **Falso rojo** | Corrida con estado `error` que sí entregó trabajo. En el 269 recibe causa `falso_rojo_probable` y nivel `advertencia` — **nunca** `exito` automático. |
| **Nivel base** | Nivel derivado solo del estado terminal, antes de mirar evidencia (`_STATUS_TO_BASE`). |
| **HITL** | El humano decide y hace click. Stacky ofrece, nunca ejecuta por su cuenta. |

### Orden de implementación (dependencias estrictas)

> **ANTES DE F0: leer §0.** Este plan se implementa **después del 271 y del 270**. Los anclajes de `api/tickets.py`, `api/incident_inbox.py` e `IncidentInboxPage.tsx` se re-greppean **por símbolo** en ese momento; los números de este documento son de la foto del 2026-07-28.

```
F0 (puro, sin dependencias)
 └─ F1 (usa EvidenceSignals de F0)
     └─ F2 (usa F0 + F1; cablea los DOS handlers de executions.py — C2)
         ├─ F3 (puro frontend; solo necesita la FORMA del payload de F2)
         │   └─ F4 (usa F3 + registra la columna en tablePrefs.ts — C3)
         └─ F5 (usa F0 + F1; independiente de F3/F4; paso 1 = declarar el logger — C4)
F6 (independiente de F0-F5: solo necesita el `items` del 254 F5 que YA existe)
     └─ escribe `hitl_enabled` en api/diag.py — ÚNICO lugar (C6)
F7 (después de F0..F6: registra las 5 flags y los 6 tests)
F8 (después de F0, F6 y F7; NO vuelve a escribir `hitl_enabled` — C6)
```
**F6 se puede implementar en paralelo** con F0-F5 si conviene: no depende de la capa de veredicto, solo del `items` que `run_reconciliation.summarize()` **ya** devuelve hoy. **Ojo (v3):** `RunReconciliationCard.tsx` tiene **0 ocurrencias** de `items` — F6 tiene que **crear** ese render, no modificarlo. **Única atadura nueva de v2:** F8 lee el marcador de `reason` que F6 escribe (`[269] corrección manual de falso rojo`), así que la métrica de calibración A1 solo tiene datos después de F6. Si se aplica el corte sugerido (**269 = F0..F5+F7** / **F6+F8 al primer número libre REAL**, resuelto con el procedimiento de §0 — **v4 E3: NO 270 (ocupado) y NO 272 (doblemente reservado)**), F6 y F8 viajan **juntas** — es por eso que el corte es ahí y no en otro lado.

### Definición de Hecho (DoD) global

- [ ] Existe `backend/services/run_verdict.py`, **puro** (0 imports de `db`/`models` a nivel de módulo; el único import de DB es perezoso, dentro de `count_by_level`). Verificable: `grep -n "^from db\|^from models\|^import db" backend/services/run_verdict.py` → 0 hits.
- [ ] Existe `backend/services/run_evidence.py` y **no escribe nada**. Verificable: `test_no_escribe_nada` verde.
- [ ] **Invariante I1 verde:** ningún `error` recibe `exito` en la grilla completa (`test_I1_un_error_jamas_recibe_exito`).
- [ ] **Invariante I2 verde:** `None` nunca mejora el nivel (`test_I2_desconocido_nunca_mejora`).
- [ ] `status_vocabulary.py` **sin cambios**. Verificable: `git diff --stat -- backend/services/status_vocabulary.py` → vacío.
- [ ] `run_outcome.py` **sin cambios** de firma. Verificable: `git diff -- backend/services/run_outcome.py` → vacío.
- [ ] **(C1)** La clave del payload es `run_verdict`, con sus 6 subclaves, con la flag ON; y **no aparece** con la flag OFF. Gates: `grep -c '"verdict"' backend/services/run_verdict.py` = **0**; `grep -c "item.verdict" frontend/src/pages/ExecutionHistoryPage.tsx` = **0**. La clave preexistente `verdict` (revisión humana, `models.py:327`) **sigue intacta**: `test_no_pisa_el_verdict_del_modelo` verde.
- [ ] **(C2)** **Los DOS** endpoints traen `run_verdict`: `GET /api/executions` y `GET /api/executions/history` (este último también dentro de `{items,total}` con `?include_total=1`). `test_history_endpoint_tambien_trae_run_verdict` verde.
- [ ] **(C3)** La columna está registrada: `grep -c "veredicto" frontend/src/services/tablePrefs.ts` ≥ 1, y `grep -c 'isColVisible(tablePrefs, "veredicto")' frontend/src/pages/ExecutionHistoryPage.tsx` = **2** (el `<th>` y el `<td>`).
- [ ] **(C4)** `grep -c "^logger = logging.getLogger" backend/api/incident_inbox.py` = **1**.
- [ ] **(C5)** `grep -c '"passed"' backend/services/run_evidence.py` ≥ 1 y `grep -c 'get("ok")' backend/services/run_evidence.py` = **0**.
- [ ] **(C6)** `hitl_enabled` se escribe en **un solo lugar**: `grep -c "hitl_enabled" backend/services/run_reconciliation.py` = **0**; `grep -c "hitl_enabled" backend/api/diag.py` = **2** (rama normal + rama de error).
- [ ] **(C7)** El colector no usa el lector que crea directorios: `grep -c "get_intent" backend/services/run_evidence.py` = **0**; `test_cambio_en_repo_no_crea_directorios` verde.
- [ ] **(C9)** Un run en `running`/`idle` **no** trae la clave: `test_run_en_curso_no_trae_veredicto` y `test_no_terminal_no_tiene_veredicto` verdes.
- [ ] La fila del historial muestra el chip de veredicto: `grep -c "verdictChipTone" frontend/src/pages/ExecutionHistoryPage.tsx` ≥ 1.
- [ ] **(D1) EL GATE MÁS IMPORTANTE DEL PLAN — reescrito en v4 (E2), porque el del v3 no atrapaba el bug.**
      **(a) Gate POSITIVO (el que vale). Los dos call-sites tienen que pasar `run_status=` explícito:**
      `grep -c "run_status=" backend/api/executions.py` ≥ **1**
      `grep -c "run_status=" backend/api/incident_inbox.py` ≥ **1**
      `grep -c "run_status" backend/services/run_verdict.py` ≥ 3
      **(b) Centinela NEGATIVO robusto** (insensible a espacios y a `getattr` vs atributo), con `-E`:
      `grep -rEn 'stacky_status"? *,? *(None)?\)? *or *[a-z_]+\.status' backend/api/` = **0 hits**
      **(c) Los tests, que son la defensa REAL:** `test_I1b_el_ticket_completed_no_blanquea_un_run_error` y `test_el_ticket_solo_empeora_nunca_mejora` (núcleo) **y `test_ticket_completed_no_blanquea_un_run_error` (A3 — en el BORDE, sobre los dos endpoints)**. Los tres son ROJOS con el cableado de v2: ésa es la prueba de que el fix entró.
      > ⚠ **Por qué se reemplazó el gate del v3 (medido con archivos sonda).** El v3 exigía `grep -rn 'stacky_status", None) or ex.status' backend/api/` = 0. Ese literal lleva **espacios después de las comas**, así que atrapa la variante de F2 pero **NO** la de F5 — que el propio v3 transcribe en su changelog D1 **sin** espacios: `getattr(by_tid.get(tid),"stacky_status",None) or ex.status or ""`. Tampoco atrapa la reescritura más natural, por atributo: `ticket.stacky_status or ex.status`. Probado con 3 sondas: **1 hit de 3 variantes; 2 quedaban impunes.** Es el defecto **D6** (`verdictTone` vs `verdictChipTone`) otra vez, en el gate de máxima criticidad. **Lección que queda escrita: un centinela negativo tiene que probarse contra el pecado que dice prohibir, y un gate POSITIVO —"la línea correcta está presente"— es siempre más robusto que uno negativo, porque no depende de adivinar cómo se escribirá el error.** Operacionalizado en la **[ADICIÓN ARQUITECTO A4]** (F7).
- [ ] **(D2)** El colector cuenta las publicaciones idempotentes: `grep -c "idempotent_replay" backend/services/run_evidence.py` ≥ 1 y `test_publicado_cuenta_idempotent_replay` verde.
- [ ] **(D5)** `count_by_level` está acotado y usa los colectores: `test_count_by_level_usa_los_colectores`, `test_count_by_level_esta_acotado` y `test_count_by_level_sin_colectores_reporta_null` verdes. Con los colectores OFF, `falso_rojo_probable` es **`null`**, nunca `0`.
- [ ] **(D7)** El `<th>` nuevo quedó **entre `estado` (`:546-548`) y `duracion` (`:551`)**: el orden de los `data-col` del `<thead>` coincide con el de `HISTORY_COLUMNS` y con el de los `<td>`. Verificación visual manual (el render no es automatizable acá, §3.8 punto 2).
- [ ] **(D10)** `grep -c "VERDICT_CAUSE_TONE" frontend/src/utils/runVerdict.ts` ≥ 1 y el test `espera_cuota se pinta con tono espera` verde.
- [ ] **(§0 / D3)** Los anclajes de la zona de colisión se **re-greppearon después** de que entraron el 271 y el 270: `api/tickets.py`, `api/incident_inbox.py`, `IncidentInboxPage.tsx`. **Ningún número de línea de esos 3 archivos se usó a ciegas.**
- [ ] **(§0 / D4 / v4 E3)** Si se aplicó el corte de scope, la segunda mitad se numeró con el **primer número sin archivo Y sin reserva escrita**, resuelto en el momento de crear el archivo con los **dos** comandos de §0: `ls "Stacky Agents/docs/"` **en frío** y `grep -rn "plan 27[0-9]\|27[0-9]_PLAN" "Stacky Agents/docs/"`. **No se usó 270 (ocupado) ni 272 (reservado por el 271 §6.1 y por el 270).**
- [ ] La bandeja de incidencias muestra el chip: `grep -c "describeVerdict" frontend/src/pages/IncidentInboxPage.tsx` ≥ 1.
- [ ] **[ADICIÓN ARQUITECTO A1]** `verdict_agreement(30)` devuelve las 3 claves y `ratio` es `None` (no `0.0`) cuando `propuestos == 0`; `test_agreement_no_muta_los_pesos` verde.
- [ ] **[ADICIÓN ARQUITECTO A2]** `test_espejo_ts_no_tiene_drift` verde (no `skipped`) una vez implementada F3.
- [ ] **[ADICIÓN ARQUITECTO A4]** `test_los_centinelas_del_dod_si_pueden_disparar` verde, y **cada gate de `grep` que se agregue al DoD de acá en adelante tiene su fila en `_CENTINELAS`** con al menos una sonda positiva y una negativa. Ningún centinela textual se da por bueno sin haberlo hecho disparar.
- [ ] La card de reconciliación renderiza items con acción: `grep -c "actionForItem" frontend/src/components/RunReconciliationCard.tsx` ≥ 1.
- [ ] El HITL usa **solo** el endpoint por `ticket_id`: `grep -c "by-ado" frontend/src/components/reconciliationActions.ts` = **0**.
- [ ] Las **5 flags** están en los 5 lugares con `default=True` (`test_plan269_flags.py` 8/8 verde).
- [ ] Los **6 archivos de test** están registrados en `run_harness_tests.sh` **y** en `run_harness_tests.ps1`.
- [ ] Los 6 archivos de test de backend corren **por archivo** y dan verde (conteos actualizados en v2):
      `test_plan269_run_verdict.py` (**29**) . `test_plan269_run_evidence.py` (**15**) . `test_plan269_executions_payload.py` (**10**) . `test_plan269_inbox_verdict.py` (**7**) . `test_plan269_hitl_correccion.py` (**6**) . `test_plan269_flags.py` (**9** — v4: +A4).
- [ ] Los 2 archivos de test de frontend corren **por archivo** y dan verde:
      `plan269RunVerdict.test.ts` (**14**) . `reconciliationActions.test.ts` (**7**).
- [ ] `cd "Stacky Agents/frontend" && npx tsc --noEmit` sin errores nuevos.
- [ ] **Sin regresiones del 254**, validado por archivo: `test_plan254_outcome_reason.py`, `test_plan254_reconciliation.py`, `test_plan254_falso_rojo.py`, `test_plan254_stream_drain.py`.
- [ ] **Sin regresiones del 238**: `test_plan238_incident_inbox_api.py` verde (contrato de forma de la bandeja).
- [ ] Los KPI K1, K2 y K6 están **medidos y anotados** en la tabla de §1 (no "SIN MEDIR").
- [ ] **(C16)** La huella de regresión está registrada en `Stacky Agents/docs/sistema/error_fingerprints.json`: una entrada para el falso rojo visible (`estado terminal 'error' + evidencia de entrega presente ⇒ cause falso_rojo_probable`) apuntando a `test_plan269_run_verdict.py::test_falso_rojo_probable_con_publicacion`. Sin esto, el bug puede volver sin que ningún gate lo note.
- [ ] Ningún estilo inline nuevo: `grep -c "style={{"` no aumenta en los 3 `.tsx` editados respecto a HEAD.
- [ ] **Cero autonomía nueva:** ningún loop, daemon, barrido ni polling agregado. Verificable: `git diff | grep -cE "while True|Thread\(|schedule|setInterval"` = 0.

---

## 9-bis. VEREDICTO DEL JUEZ v3 → v4 (SEGUNDA pasada independiente, 2026-07-28)

### APROBADO-CON-CAMBIOS — 0 BLOQUEANTES · 4 IMPORTANTES · 5 MENORES · los cambios YA están aplicados en este v4

> ## ✅ LA PROHIBICIÓN "NO IMPLEMENTAR" QUEDA LEVANTADA
> El v3 llevaba escrito *"NO implementar hasta aplicar los fixes D1..D5"*. Esta pasada verificó **corriendo** que **D1, D2, D3 y D5 están cerrados**, encontró que **D4 no lo estaba** (su fix repetía el error que arreglaba) y lo corrigió, y cazó **4 defectos IMPORTANTES que el propio v3 introdujo** (E1..E4) más 5 menores — **todos aplicados en este documento**. No queda ningún bloqueante. **El plan es implementable a partir de F0**, con la única condición de orden que ya declaraba §0: **va después del 271 y del 270**, y los anclajes de los 3 archivos de la zona caliente se re-greppean **por símbolo** en ese momento.

**Criterios binarios que lo sustentan:**

| Criterio | Resultado en v4 |
|---|---|
| ¿El invariante de negocio ("un `error` nunca da `exito`") se sostiene en **todos** los caminos? | **SÍ.** Grilla completa de **17.010** casos ⇒ **0** violaciones. Monotonicidad del ticket: **68.040** casos ⇒ el ticket mejoró el nivel en **0**. No terminales: **0** veredictos espurios. Y el gate de **borde** (A3) existe, cubre los **dos** endpoints y ahora asserta **los dos lados del contraste** (E1). |
| ¿El fix de D1 está además **protegido** por gates que funcionan? | **SÍ, tras E2.** El centinela del v3 atrapaba **1 de 3** reintroducciones (probado con sondas). Reemplazado por un gate **positivo** (`run_status=` presente en los dos call-sites) + un centinela negativo `-E` verificado **3/3 con 0 falsos positivos**. |
| ¿Algún colector produce evidencia FALSA (no solo desconocida)? | **NO.** Censo corrido: 4 literales de `status`, un **único** escritor de filas (`ado_publisher.py:889`), dedupe por `(ado_id, sha256, 'ok')` ⇒ el diagnóstico de D2 es exacto y el filtro `IN ('ok','idempotent_replay')` es el correcto. |
| ¿El plan está escrito como CONSUMIDOR del 271 y del 270? | **SÍ.** §0 con orden, tabla de colisión y anclaje por símbolo — con el grep ambiguo corregido (E4: `def set_stacky_status(` con paréntesis, porque sin él devolvía también el endpoint **prohibido** que publica en ADO). |
| ¿Todos los números de plan que el documento asigna están libres? | **SÍ, y ahora no asigna ninguno.** El v3 mandaba el corte al **272**, que está **reservado por escrito** por el 271 (§6.1) y por el 270 — que además **prohíbe hardcodearlo**. El v4 reemplaza el número por el **procedimiento** (relistar en frío + grepear reservas + saltar el 272). |
| ¿Los KPI que el plan promete medir son medibles? | **SÍ.** D5 reusa `collect_for_executions` con cota `limit=200` (**verificada** contra `scan_recent(limit=200)`, `run_reconciliation.py:168`) y reporta `null` —no `0`— sin colectores. Contrato de claves congelado en **7** (el v3 lo declaraba 4, 6 y 7 en tres lugares distintos: E5). |
| ¿Toda flag nueva es default ON, o cita una de las 2 categorías de excepción? | **SÍ.** Las 5 en ON, alineadas con la directiva vigente. La única que habilita una escritura (`..._HITL_ENABLED`) queda **ratificada por tercera vez**: `api/tickets.py` `def set_stacky_status(` en `:1166` llama `ts.set_status` y **no publica**; el prohibido `set_stacky_status_by_ado` (`:1205`) sí. |
| ¿Human-in-the-loop intacto? | **SÍ.** El veredicto nunca cambia un estado; la corrección la dispara un click con `useConfirm`; A1 **muestra** el acierto y `test_agreement_no_muta_los_pesos` prohíbe el auto-tuneo. |
| ¿Paridad de los 3 runtimes? | **SÍ, estructural.** P3: se calcula al leer; los 3 escriben `AgentExecution`. Ninguna fase toca un runner. |
| ¿Cero trabajo extra al operador? | **SÍ.** Todo invisible, 5 flags ON de fábrica, el filtro arranca en "Todos". |
| ¿Mono-operador sin auth (sin RBAC)? | **SÍ.** |
| ¿Backward-compatible? | **SÍ.** `run_verdict` es clave nueva y opcional; con las flags OFF el payload es byte-idéntico. Verificado que no pisa la columna viva `verdict` (`models.py:255/327`) ni los 20 campos de `ExecutionHistoryItem`. |
| ¿Reusa lo existente? | **SÍ.** Cero tablas y cero columnas nuevas. Y el helper de siembra de `agent_html_publish` ahora apunta al que **existe de verdad** (`test_publish_ledger.py:47-54`; el del v3 no seedeaba esa tabla — E8). |

### Qué encontró esta pasada que la anterior no podía encontrar

El v3 hizo bien lo difícil: encontró un bug de **costura** simulando el cableado. Su punto ciego fue el **opuesto**: dio por buenos **sus propios gates**. Los 4 IMPORTANTES tienen una firma común: **el fix era correcto y la verificación del fix no lo era.**

- **E1**: el test estrella del v3 afirmaba un resultado (`exito`) que sus propios datos **no pueden producir**. Solo aparece si se **calcula el strength** de la fila que el test siembra.
- **E2**: el centinela del bug más grave del plan atrapaba **1 de 3** ortografías. Solo aparece si se **corre el grep contra el pecado**, no contra el código correcto.
- **E3**: el fix de numeración eligió un número que dos vecinos **reservaron por texto** (sin archivo). Solo aparece si se **grepea el número**, no si se lista el directorio.
- **E4**: la regla de anclaje por símbolo devolvía **2 hits** en el único símbolo donde equivocarse escribe en el ADO real. Solo aparece si se **corre el grep y se cuentan los hits**.

**La regla que sale de acá, y que vale para la próxima pasada:** *criticar corriendo* no alcanza si se corre solo el **código**. Hay que correr también **los gates, los greps, los conteos y los números de plan** — o sea, todo lo que el documento afirma que va a verificar por uno. Un plan tiene dos capas de verdad: lo que construye y **cómo dice que va a comprobar que lo construyó bien**. La segunda capa falló en v2 (D6) y tres veces en v3 (E2, E4, E5). La **[ADICIÓN ARQUITECTO A4]** la convierte en un test.

### Método aplicado en esta pasada (para que la próxima lo repita y lo supere)

1. Se extrajo a disco el módulo F0 **literal del v3** y se barrió la grilla **COMPLETA** (17.010) — no la que el doc declaraba (10.206, con 6 reasons de 9 reales).
2. Se **calculó el strength** de las filas que A3 siembra, en vez de leer su prosa. Ahí apareció E1.
3. Se escribieron **archivos sonda** con las 3 ortografías del anti-patrón y se corrió el gate del DoD contra ellas. Ahí apareció E2. Después se **verificó el gate de reemplazo** (3/3, 0 falsos positivos) antes de escribirlo.
4. Se corrieron **los 5 greps de anclaje de §0 contando los hits**. Ahí apareció E4.
5. Se hizo `grep -n "272"` **sobre los vecinos**, no `ls`. Ahí apareció E3 (reservas por texto, sin archivo).
6. Se **contaron las claves** del JSON de D5 y se compararon con las tres afirmaciones del doc. Ahí apareció E5.
7. Se censó el **único escritor** de `agent_html_publish` para cerrar el censo de D2, y se buscó qué test **realmente** siembra esa tabla (E8).
8. Se corrió el cuerpo del test de A4 con el venv (**1 passed**) para no proponer pseudocódigo.

### Baseline REVERIFICADO en esta pasada

Los números del baseline del v3 se mantienen (no se re-corrieron todos: el v3 los midió y siguen siendo la referencia de R8). Lo que **sí** se reverificó acá, por ser lo que sustenta los fixes: `scan_recent(limit=200)` en `run_reconciliation.py:168`; `_CURATED_DEFAULTS_ON` en `test_harness_flags.py:467` con assert por **igualdad de conjuntos** en `:985`; `AgentHtmlPublish` registrada en `init_db` (`db.py:239`); los 10 `<th data-col>` en 526/531/536/541/**546**/551/556/561/566/571 con `<thead>` 507→579; `StatusChipProps.title` en `StatusChip.tsx:13`; `ExecutionHistoryItem` con **20** campos y sin `verdict`.

> **Nota sobre los rojos de fábrica (vale para el DoD entero):** en este árbol hay gates ROJOS **preexistentes y ajenos** — `test_harness_flags_help.py` (**4 failed / 4 passed**), `uiDebtRatchet`, `motionDebtRatchet`, `test_error_fingerprints_catalog.py`. **Ningún criterio de este plan exige verde absoluto ahí**: todos los criterios sobre archivos ajenos son de **delta** ("cero fallos **nuevos** respecto a HEAD", "`grep -c "style={{"` **no aumenta**"). Un DoD que pidiera verde absoluto en esos 4 sería insatisfacible por causas ajenas.

---

## 9. VEREDICTO DEL JUEZ v2 → v3 (revisión independiente, 2026-07-28) — HISTÓRICO

### RECHAZADO — 5 BLOQUEANTES *(superado por la pasada v3→v4: ver §9-bis)*

**Criterios binarios que lo sustentan:**

| Criterio | Resultado |
|---|---|
| ¿El invariante de negocio ("un `error` nunca da `exito`") se sostiene en **todos** los caminos? | **NO en v2.** Se sostiene en la función pura (0/1215 violaciones) pero **se rompe en el cableado de F2 y F5** (probado corriendo). ⇒ **D1** |
| ¿Algún colector produce evidencia FALSA (no solo desconocida)? | **SÍ en v2.** `publicado_en_tracker` da `False` para toda re-corrida publicada por `idempotent_replay`. ⇒ **D2** |
| ¿El plan está escrito como CONSUMIDOR del 271 y del 270, con los que colisiona en archivo y línea? | **NO.** Cero menciones. ⇒ **D3** |
| ¿Todos los números de plan que el documento asigna están libres? | **NO.** Manda F6+F8 al **270**, ocupado. ⇒ **D4** |
| ¿Los KPI que el plan promete medir son medibles? | **NO en v2.** K1 y A1 son 0 por construcción. ⇒ **D5** |
| ¿Toda flag nueva es default ON, o cita una de las 2 categorías de excepción? | **SÍ.** Las 5 en ON. La única que habilita una escritura (`..._HITL_ENABLED`) se reverificó línea por línea: `api/tickets.py:1165` **no publica**. **ON ratificado por segunda vez.** |
| ¿Human-in-the-loop intacto? | **SÍ.** El veredicto nunca cambia un estado; la corrección la dispara un click con confirmación (`useConfirm`, nunca `window.confirm`); A1 **muestra** el acierto y tiene un test que prohíbe auto-tunear los pesos. |
| ¿Paridad de los 3 runtimes? | **SÍ, estructural.** P3: se calcula al leer, los 3 escriben `AgentExecution`. Ninguna fase toca un runner. |
| ¿Cero trabajo extra al operador? | **SÍ.** Todo invisible, 5 flags ON de fábrica, el filtro arranca en "Todos". |
| ¿Mono-operador sin auth (sin RBAC)? | **SÍ.** Nada de roles ni permisos. |
| ¿Backward-compatible? | **SÍ.** Clave nueva `run_verdict` opcional; con las flags OFF el payload es byte-idéntico. |
| ¿Reusa lo existente? | **SÍ.** `run_outcome`, `run_reconciliation`, `status_vocabulary`, `OutcomeTone`, `useConfirm`, `agent_html_publish`, `ix_exec_ticket_started`, el `reason` de `TicketStatusEvent`. Cero tablas y cero columnas nuevas. |

**Con D1..D5 aplicados (ya están escritos en este v3), el veredicto pasa a APROBADO-CON-CAMBIOS.** Lo que queda son los IMPORTANTES/MENORES D6..D13, todos ya corregidos in situ.

### Qué encontró esta pasada que la anterior no podía encontrar

Los 5 bloqueantes tienen una firma común: **ninguno es visible releyendo el documento.** D1 aparece solo si se **instancia** el módulo y se **simula** el cableado con objetos reales; D2 solo si se **censan los literales que el escritor produce** en vez de creerle al comentario de la columna; D3/D4 solo si se **listan los planes vecinos**; D5 solo si se **traza el dato hacia atrás** desde el KPI hasta su fuente. El v2 releyó con mucho cuidado y **acertó las 5 trampas de superficie** — pero las 5 trampas eran las del v1.

### Método aplicado (para que la próxima pasada lo repita)

1. Se ejecutó el módulo F0 **literal del documento** y se barrió su grilla completa. Así se supo que I1 valía en el núcleo.
2. Se **simuló el cableado** de F2 con `Ticket`/`Execution` falsos y la línea exacta del plan. Ahí apareció D1.
3. Se censó por **AST** que `Ticket.stacky_status` (`models.py:61`) y `AgentExecution.status` (`:254`) son columnas independientes con FK `ticket_id` (`:252`) — o sea, N ejecuciones por ticket. Eso convirtió D1 de "caso raro" en "sistemático".
4. Se corrieron **los tests que el plan nombra**, por archivo, con el venv py3.13: 254 (11+10+9) y 238 (12) verdes; baseline de flags **medido** (56 / 4F+4P / 9 / 18).
5. Se verificó **cada anclaje por símbolo**, no por número.
6. Se leyeron **los planes vecinos vivos** (270, 271) para buscar colisión de archivo y de numeración.

### Baseline medido el 2026-07-28 (para que F7 compare contra números, no contra memoria)

```
tests/test_plan254_outcome_reason.py      11 passed
tests/test_plan254_reconciliation.py      10 passed
tests/test_plan254_falso_rojo.py           9 passed
tests/test_plan238_incident_inbox_api.py  12 passed
tests/test_harness_flags.py               56 passed
tests/test_harness_flags_help.py           4 failed, 4 passed   ← AJENOS y PREEXISTENTES
tests/test_harness_flags_requires.py       9 passed
tests/test_harness_flags_bounds.py        18 passed
```
Los 4 fallos de `test_harness_flags_help.py` **no son de este plan** y estaban antes de tocar nada. R8 exige comparar contra estos números exactos después de F7.
