# Plan 271 — La incidencia se mueve al estado configurado al terminar el analista

**Estado:** CRITICADO v7 (veredicto v6: **APROBADO-CON-CAMBIOS** — 0 bloqueantes, 1 importante (E27) · v5: **RECHAZADO**, 2 bloqueantes (E23, E24) · v4: **RECHAZADO**, 3 · v3: **RECHAZADO**, 6 · v2: **RECHAZADO**, 6 · v1: **RECHAZADO**, 8)
**Fecha:** 2026-07-29
**Juez v7: subagente independiente y NUEVO, corrida distinta, contexto limpio, sobre el árbol compartido (rama `docs/plan-263-critica-v3-v4`, HEAD `061ea0aa` al momento de escribir esta línea — varios commits por delante del `fd68f4d3` que usó el v6, todos `docs(plan-NNN): critica...` de planes hermanos, cero código de producción tocado).** **VERIFICACIÓN #1 (la más importante), hecha con evidencia ejecutada, no leída:** se reconstruyó el diff LITERAL de F3 propuesto por el v6 (firma nueva + cuerpo completo de `_attempt_state_change`, empalmado sobre el archivo real de hoy) y se corrió, con `ast`, la lógica EXACTA de `test_5_centinela_del_residuo_s5` contra ese diff reconstruido — **intersección vacía**: el diff nunca referencia `get_tracker_provider`/`tracker_type`/`_provider_for_ticket` como `Name`/`Attribute`/`keyword`/`Constant` (las tres menciones de esos nombres dentro del diff están en comentarios `#`, invisibles al AST porque Python descarta los comentarios antes de parsear). `test_plan270_state_write_ratchet.py` corrido de verdad: **6 passed**, archivo intacto. `§3` principio 6 y `§3.5` quedaron efectivamente corregidos apuntando al router, y la DoD (§7.3) ya **no** manda tocar `test_5` — **E23 está cerrado de verdad, no en prosa**, esta es la primera versión donde eso es cierto. También re-verificados hoy: el censo de F8 (script reconstruido línea por línea desde este mismo documento — **13 entradas, idénticas** a las del v6, mismos números de línea) y los 4 anclajes de `api/tickets.py`/`gitlab_provider.py` (**exactos: `:1205`/`:1780`/`:4157`/`:243`**) y `test_b2_transition_from_config.py` (**sigue `5 failed`, mismo `TypeError`**). **Hallazgo nuevo, E27, IMPORTANTE (no bloqueante):** el frontend tiene hoy **9** archivos `*Ratchet*.test.ts`, no 8, y uno de los 8 que el v6 sí nombra (`uiDebtRatchet`) ya está rojo hoy (`ExecutionDetailDrawer.module.css`: 23 hex > baseline 21, deuda de los planes 254/269) en el mismo archivo CSS que la F6 de **este** plan edita — pero la edición real de F6 usa `var(--text-muted)`, un token, nunca un hex literal, así que no lo agrava. Ver CHANGELOG v6→v7.
**Reserva de números:** este plan usa **271**. Los huecos **261** y **262** siguen libres. El **272** queda reservado para "un solo escritor de estado" (§6.1).
**Depende de:** nada. **Coordina con:** 79 (`_apply_task_state` + `_safe_transition`), 208 (matriz), 210 (gate de build), 216 (UI de estados), 254 (`_with_outcome`), **269 (`api/executions.py`, ya mergeado — §5 R15, confirmado: `run_verdict` presente en `api/executions.py` hoy)**, **270 (cierre real ADO+GitLab, ya mergeado en `77627239` — §5 R10, y ver CHANGELOG v4→v5 E19/E20 y v5→v6 E23: el 270 le dejó a este plan un censo desactualizado, un centinela que su F3 hacía sonar a propósito, y un router (`tracker_write_router.resolve_state_writer`) que el v5 seguía sin usar de verdad)**.

---

## CHANGELOG v6 → v7 — **APROBADO-CON-CAMBIOS** (0 bloqueantes, 1 importante). Primera vez en 7 rondas que este plan no es rechazado.

El v6 hizo lo que el v5 solo simuló: F3-bis-0 dejó de ser una "evaluación" y pasó a mandato, y el diff concreto de F3 se reescribió para rutear por `resolve_state_writer` en vez de `get_tracker_provider`. Esta ronda existía precisamente para comprobar si eso era cierto en el diff real o solo en la prosa — la ronda anterior (v4→v5) ya había demostrado que "coordina con el centinela" puede quedar escrito y ser falso en el código. **No lo era esta vez.**

- **VERIFICACIÓN #1, con evidencia ejecutada (no leída).** Se tomó el cuerpo real y actual de `_attempt_state_change` (`services/agent_completion_internal.py:502-553`, leído del archivo, no del plan) y se le empalmó el diff de F3 tal cual está escrito en el documento (firma + reemplazo de `:526-553` + los dos `if` nuevos), reconstruyendo el archivo resultante completo en un script aparte. Sobre ESE archivo reconstruido se corrió, línea por línea, la MISMA lógica que usa `test_5_centinela_del_residuo_s5` (`ast.walk` sobre el `FunctionDef`, mirando `Name.id` / `Attribute.attr` / `keyword.arg` / `Constant` de tipo string): la intersección con `{"get_tracker_provider", "tracker_type", "_provider_for_ticket"}` dio **conjunto vacío**. Las tres menciones de esos nombres que SÍ aparecen en el diff (líneas de comentario explicando la decisión de diseño) son invisibles para `ast.parse`, porque Python descarta los comentarios en el tokenizer antes de construir el árbol — un centinela AST, por construcción, no puede confundir prosa con código (el propio F8 lo dice para otro censo: "un `ast.Call` no puede confundir prosa con código"; acá se comprobó que vale también para las ausencias). Se corrió además `test_plan270_state_write_ratchet.py` real: **6 passed**, sin abrir el archivo para editarlo. Se leyó `§3` principio 6 (corregido: apunta a `tracker_write_router.resolve_state_writer`, ya no receta la ruta directa), `§3.5` punto 3 (corregido: "la API implícita se resuelve cumpliéndola, no editándola") y la DoD `§7.3` (corregida: "si `test_5` falla, NO se edita: se detiene la fase y se corrige el diff"). **Los cuatro lugares que el v5 dejaba inconsistentes entre sí (el diff, el principio, la regla de §3.5 y la DoD) dicen hoy la misma cosa. E23 está cerrado.**
- **VERIFICACIÓN #2 — `test_plan270_state_write_ratchet.py`: 6 passed**, confirmado corriendo el archivo real con `backend/.venv/Scripts/python.exe` (no `backend/venv/`), sin tocar nada.
- **VERIFICACIÓN #3 — censo de F8 re-corrido contra el HEAD de hoy (`061ea0aa`): 13 entradas, byte-idénticas** (mismas funciones, mismos números de línea) a las que el v5/v6 midieron. Ningún plan hermano agregó un escritor nuevo desde entonces.
- **VERIFICACIÓN #4 — `test_b2_transition_from_config.py`: sigue `5 failed`**, mismo `TypeError: _resolve_transition_state_from_config() missing 1 required keyword-only argument: 'final_status'`. Sin cambios; F4-bis lo sigue arreglando como está escrito.
- **VERIFICACIÓN #5 — anclajes re-medidos: `api/tickets.py:1205/:1780/:4157` y `gitlab_provider.py:243`, los 4 exactos.**
- **E27 (IMPORTANTE, nuevo) — La DoD de F6 dice "8 ratchets de UI", hoy hay 9, y uno de los 8 que sí nombra ya está rojo por deuda ajena en el archivo que la propia F6 edita.** Medido: `Get-ChildItem frontend/src/__tests__/*Ratchet*.test.ts` (o su equivalente `ls`) da **9** archivos; la lista nombrada en la sección F6 y en la DoD final (`§7.3`) tiene **8** y le falta `devopsActionCatalogRatchet.test.ts` (agregado por el plan 267, ajeno a este plan). Peor: uno de los 8 SÍ nombrados, `uiDebtRatchet.test.ts`, está **rojo hoy** — medido directamente contra el baseline: `ExecutionDetailDrawer.module.css` tiene **23** colores hex contra un baseline congelado de **21** (`frontend/src/__tests__/uiDebtBaseline.json`), deuda de los planes 254/269, **no** de este plan. El DoD actual, tal cual está escrito ("los 8 ratchets de UI siguen verdes"), es una afirmación **falsa hoy**, antes de que F6 toque una sola línea — exactamente la clase de criterio que este mismo plan trató como bloqueante en E5/E19/D4 (un gate compartido rojo por deuda ajena, sin baseline declarado). Se degrada a IMPORTANTE y no a BLOQUEANTE porque, a diferencia de esos casos, (a) no es un criterio de un artefacto que ESTE plan crea (es un ratchet ajeno, del plan 138, igual que `test_error_fingerprints_catalog.py` es del 239 — y ESE caso el propio v3→v4 ya lo resolvió correctamente con un baseline declarado, patrón que solo faltaba aplicar acá también); y (b) la edición real de F6 (`color: var(--text-muted)` en vez de `var(--warn)` para `.toneEspera`) usa un **token**, nunca un hex literal, así que no puede empujar el conteo de 23 a más — verificado leyendo el diff real de F6, no supuesto. **Fix (mecánico, sin cambiar ninguna instrucción de implementación):** (1) el conteo pasa de 8 a 9 y se agrega el nombre faltante; (2) se declara el baseline real de `uiDebtRatchet` ANTES de tocar F6 (rojo, `ExecutionDetailDrawer.module.css` 23>21, ajeno) siguiendo el mismo patrón ya usado en este documento para `test_error_fingerprints_catalog.py`/`test_harness_flags_help.py`; (3) el criterio pasa de "siguen verdes" a delta: los 9 ratchets no nombran ningún archivo que F6 haya tocado como ofensor NUEVO, y en particular el hex de `ExecutionDetailDrawer.module.css` no sube de 23. Aplicado en la sección F6 y en la DoD `§7.3` de este mismo documento.
- **`[ADICIÓN ARQUITECTO v7]` — §3.7: todo ratchet compartido de frontend se reglobea y se mide, nunca se enumera de una lista fija en el documento.** Es el antídoto estructural a E27: la causa no fue no saber que existían ratchets — fue confiar en una foto de 8 nombres tomada en una versión anterior, en un documento cuyo propio §3.4 ya enseña (para el backend) que ningún número sobrevive a un merge ajeno. Ver §3.7, nueva.

---

## CHANGELOG v5 → v6

El v5 hizo bien las tres cosas que se le pidió re-medir: el censo de F8 (**13, re-confirmado hoy, línea por línea idéntico**), `test_b2_transition_from_config.py` (**sigue `5 failed`, mismo `TypeError`**) y los anclajes de `api/tickets.py`/`gitlab_provider.py` (**exactos: `:1205`/`:1780`/`:4157`/`:243`**). Todo eso se corrió de nuevo para este v6 y dio lo mismo. Pero la pieza que el v4→v5 marcó como **la más crítica** — la coordinación con el centinela del plan 270 — se escribió como una evaluación opcional ("fijate si conviene reusar el router") en vez de un mandato, y el diff concreto de F3 **ya venía comprometido** con la alternativa que el centinela prohíbe. Y perseguir esa pieza destapó una segunda, más grave: el plan nunca verificó que el valor que escribe realmente **exista** en el vocabulario del tracker al que lo rutea.

- **E23 (BLOQ)** — **F3-bis-0 no coordina con el centinela del 270: lo neutraliza, y el diff concreto de F3 nunca dejó de violarlo.** Se corrió `test_plan270_state_write_ratchet.py` de verdad: **6 passed** (baseline confirmado). Se leyó el cuerpo de `test_5_centinela_del_residuo_s5` (`backend/tests/test_plan270_state_write_ratchet.py:135-165`): además de contar escrituras, hace `ast.walk` sobre TODO el cuerpo de `_attempt_state_change` y prohíbe que aparezca `get_tracker_provider` / `tracker_type` / `_provider_for_ticket` como `Name`, `Attribute.attr`, `keyword.arg` o string literal. El diff **ya escrito** en la sección "F3" (el bloque rotulado "Diff — reemplazar `:526-553`") hace exactamente `from services.tracker_provider import get_tracker_provider` seguido de `provider = get_tracker_provider(project_name)` — un `ast.Name(id="get_tracker_provider")` textual, dentro de la función vigilada. F3-bis-0 punto 4 lo sabe ("evaluar... si conviene construirlo sobre `resolve_state_writer`") pero lo deja como **opción**, con una salida explícita ("si se decide no reusarlo... esa decisión va en el PR") que el propio diff concreto ya tomó de hecho. Y el punto 3 + la DoD (línea **"corrido DESPUÉS de F3... vuelve a 6 passed — con el test_5 editado (no borrado)"**) prescriben **editar la aserción `prohibidos` del centinela** en vez de evitar la colisión — es decir, la "coordinación" consiste en apagar la alarma, no en resolver lo que la alarma pedía. Peor: el propio §3 de este plan, **principio 6** ("Toda escritura... pasa por `services/tracker_provider.get_tracker_provider`"), sigue recetando la ruta directa como guardarraíl — nunca se corrigió para apuntar al router. **Fix real (no evaluación, mandato):** `_attempt_state_change` ya tiene el objeto `ticket` en alcance (lo trae `session.get(Ticket, ticket_id)` para leer `ado_id`, `:516` en el árbol de hoy); F3 pasa a llamar `services.tracker_write_router.resolve_state_writer(ticket)` — **no** `write_state_for_ticket` (ver E24: ese hace algo distinto) — y despachar con `writer.kind`/`writer.handle`, sin nombrar `get_tracker_provider` ni `tracker_type` en ningún punto del cuerpo de la función. Con este diff, `test_5` **no necesita tocarse**: la verificación pasa a ser correrlo tal cual después de F3 y confirmar que sigue en `6 passed` SIN EDITAR NADA — si no es así, el diff todavía referencia un nombre prohibido y hay que corregir el diff, no el centinela.
- **E24 (BLOQ)** — **El KPI "2 trackers soportados" es estructuralmente falso para casi cualquier configuración real: GitLab sólo entiende 4 palabras fijas, y la UI del operador nunca las ofrece.** Medido en `backend/services/gitlab_provider.py:109-117` (`_state_map_for_gitlab`): el mapa tiene **exactamente 4 claves** — `functional`, `accepted`, `rejected`, `in_progress` — y `update_item_state` (`:243-266`) levanta `CapabilityUnavailable` para cualquier `logical_state` que no sea una de esas cuatro. El operador configura `next_state_ok` en la única UI que existe (`StatesConfigPage.tsx`) con vocabulario **ADO** — el propio ejemplo de este plan en §2.2(a) es `"To Do"` —, y `"to do"` no es ninguna de las 4 claves. Ni la ruta directa del v5 (`get_tracker_provider`) ni el fix de E23 (`resolve_state_writer`) resuelven esto: **ninguna de las dos traduce vocabulario**, sólo resuelven *a qué proveedor* escribir. El único módulo del repo que sí traduce (`services/close_intent.py::resolve_close_target`) está construido **solo para intenciones de cierre** (`ADO_CLOSE_STATES = ("Done","Closed","Resolved")` → `GITLAB_CLOSE_STATE = "accepted"`) y para cualquier otro string devuelve `ValueError("unmappable_state:...")` — usarlo para un `next_state_ok` que no es un cierre (p. ej. `"To Do"`, que es volver a la cola de trabajo) sería semánticamente incorrecto, no sólo un cambio de función. Consecuencia medida: **en cualquier proyecto GitLab cuyo `next_state_ok` no sea una de las 4 palabras mágicas — o sea, en la práctica, todos — F3 va a devolver `reason="transition_failed"` siempre**, nunca va a mover el ticket, y el plan nunca lo dice en ninguna de sus 5 versiones (`grep -n "GITLAB_LOGICAL_STATES\|_state_map_for_gitlab\|unmappable_state" sobre el documento entero ⇒ **0 hits**). Esto no es un caso borde: es el camino feliz para todo operador con proyectos GitLab. **Fix (declarar y testear, no inventar mapeo nuevo fuera de scope — `gitlab_provider.py` es territorio del 218/270/272):** (1) §1 corrige la fila del KPI a *"Trackers soportados: 2 técnicamente (ADO + GitLab), pero GitLab sólo cuando `next_state_ok` coincide con una de las 4 claves lógicas de `_state_map_for_gitlab`; fuera de esas 4, `transition_failed` con razón visible — no hay reparación de vocabulario en este plan, ver R17"*; (2) nuevo **R17** en §5 con esta medición; (3) **caso 11 nuevo** de `test_plan271_writer_routed.py`: ticket GitLab con `target_state="To Do"` (fuera de las 4 claves) ⇒ `{"ok": False, "reason": "transition_failed", ...}`, **nunca** una excepción sin capturar ni un `skipped` mudo — así la limitación queda medida y vigilada, no es una sorpresa de producción.
- **E25 (IMPORTANTE)** — **El motor B no tiene un guardia de origen equivalente al `_origin_guard` del motor A, y F4 lo hace disparar más seguido.** `completion_state._origin_guard` (`:121-161`) existe precisamente para no pisar un ticket que "el humano movió a propósito" fuera del flujo esperado del rol — es la defensa de human-in-the-loop del motor A, y el propio §3 principio 3 la declara innegociable. `_attempt_state_change` (motor B) **nunca la llamó, ni antes ni después de este plan**: su única idempotencia es la de `_safe_transition` (`task_states.py:164-168`), que sólo compara `current == target` — si el ticket está en `"Done"` (cerrado a mano) y el `target` es `"To Do"`, `_safe_transition` **no ve coincidencia** y escribe igual, reabriendo un ticket que un humano cerró deliberadamente. Este agujero **ya existe hoy** (la rama ANTES de F3 también lo tiene: `AdoClient().update_work_item_state` sin ningún chequeo de estado actual), así que este plan no lo crea — pero **F4 (cierra RC-2) hace que el motor B deje de bloquearse por publish y dispare la escritura en más casos**, subiendo la probabilidad de ejercitar el agujero justo cuando este plan hace que el motor B escriba de verdad por primera vez en la práctica. Ninguna de las 16 filas de riesgos (R1-R16) lo menciona. **Fix (declarar y diferir, mismo patrón que R3-bis/R6-bis — no expandir a un rediseño de motor B fuera de alcance):** nuevo **R18** en §5: "aceptado y no mitigado — el motor B puede reabrir un ticket movido a mano fuera de flujo; extender `_origin_guard` (o un equivalente) al motor B es del **plan 272**, junto con la unificación de escritores". Se agrega un test que **mide** el agujero (no lo cierra): caso 12 de `test_plan271_writer_routed.py`, ticket con estado actual `"Done"` (fuera del `expected` del rol) y `target="To Do"` ⇒ hoy escribe igual (`ok=True`), documentado como riesgo conocido con el número R18.
- **E26 (MENOR)** — **R15 describe al plan 269 como "en vuelo" cuando ya está mergeado, y eso hace que su probabilidad de riesgo esté mal calibrada.** El propio encabezado de este documento (línea 7) ya dice *"269 ..., ya mergeado"*, pero el texto de R15 en §5 dice *"El 269 se está implementando AHORA en un worktree paralelo"* — contradicción interna. Verificado: `grep -n "run_verdict" backend/api/executions.py` ⇒ presente (`:58,82,90,95`), la marca inequívoca de que el 269 ya aterrizó. La estrategia de anclaje por grep (§3.4) **ya absorbió** el corrimiento real (`_with_outcome` corrido de `:65` a `:129`, confirmado re-corriendo el grep de la fila) así que esto no cambia ninguna instrucción de implementación — pero el riesgo debería re-calibrarse de "colisión futura con un merge en curso" a "verificar que la costura post-merge de F5 siga siendo válida", que es justo lo que ya se hizo acá. Corregido el tiempo verbal y la fuente de riesgo en R15.
- **`[ADICIÓN ARQUITECTO v6]` — §3.6: ningún `provider.update_item_state` nuevo se declara "soportado" sin probar el valor REAL contra el vocabulario del tracker resuelto.** Es el antídoto estructural a E24: los 10 casos de `test_plan271_writer_routed.py` en el v5 prueban que se **rutea** al proveedor correcto con un `FakeProvider` que acepta cualquier string — nunca prueban que el string **sobreviva** al vocabulario real de ese proveedor. Ver §3.6, nueva.

---

## CHANGELOG v4 → v5

El v4 acertó el diagnóstico de fondo (RC-1/RC-2/RC-3, los SEIS motores, el árbitro simétrico) y construyó, con razón, una defensa anti-drift (§3.4) después de tres rondas seguidas quemadas por números de línea. Pero esa defensa se escribió mirando solo hacia atrás (el commit base `760ac455`) y no hacia los planes que **ya estaban mergeándose al lado**: 267, 269 y **270** aterrizaron en `main` entre el 27 y el 29/07, y el 270 en particular tocó exactamente el terreno de este plan — el escritor de estado del motor B — con un ratchet propio que **anticipó textualmente** este momento. Todo lo que sigue salió de **correr el censo del propio F8 contra el HEAD real** y de **correr el ratchet del 270 antes y después de leer el diff de F3**, no de releer.

- **E19 (BLOQ)** — **F8 nace rojo el día 1, otra vez — la MISMA causa (D1) que ya tumbó tres versiones, ahora mordiendo a la propia mitigación.** Se copió el script del Paso 0 tal cual está en el documento y se corrió contra el HEAD actual (`6f451db8`, 32 commits por delante de `760ac455`). Salida real: **13 entradas**, no 12. La nueva es `services/tracker_write_router.py::write_state_for_ticket [(155, 'update_work_item_state'), (157, 'update_item_state')]`. Ese archivo **no existía** en `760ac455` (`git show 760ac455:.../tracker_write_router.py` ⇒ *"exists on disk, but not in 760ac455"`) y lo creó el **plan 270**, commit `77627239` ("el tablero de incidencias dice la verdad — F0..F7"), ya mergeado. El allow-list `ESCRITORES_CENSADOS` del v4 congela exactamente 12; con el repo de hoy, `hallados - ESCRITORES_CENSADOS` da un conjunto de un elemento, no el vacío que el test exige. **F8, implementado literalmente como dice el v4, falla en el primer `pytest`.** Corregido: la entrada 13 se agrega al allow-list (§F8) con su etiqueta, y "12" pasa a "13" en cada lugar del documento que lo citaba (KPI de §1, los dos bloques de "Salida REAL", el criterio de aceptación, la DoD).
- **E20 (BLOQ)** — **F3, tal como está escrito, va a hacer sonar — con certeza medida, no hipotética — un centinela que el plan 270 plantó a propósito esperando esta fase.** `backend/tests/test_plan270_state_write_ratchet.py::test_5_centinela_del_residuo_s5` existe hoy, está **verde (6 passed, corrido)**, y hace `ast.walk` sobre el cuerpo de `agent_completion_internal.py::_attempt_state_change` prohibiendo toda referencia a `get_tracker_provider` / `tracker_type` / `_provider_for_ticket`. El diff "DESPUÉS" de F3 agrega, dentro de esa misma función, `from services.tracker_provider import get_tracker_provider` seguido de la llamada `get_tracker_provider(project_name)` — un `ast.Name(id="get_tracker_provider")` que el centinela atrapa por diseño. Su propio mensaje de fallo, escrito por el 270 anticipando exactamente esto, dice: *"S5 cambió: alguien (probablemente el plan 271) enrutó `_attempt_state_change` por provider... actualizá §1 y re-medí la divergencia. NO subas el número ni borres este test."* El v4 no lo vio: `grep -c "tracker_write_router\|state_write_ratchet\|resolve_state_writer"` sobre el documento entero da **0**. Y hay algo peor que un test que se pone rojo a propósito: el plan 270 **ya construyó**, en `services/tracker_write_router.py::resolve_state_writer()` (usado hoy por `set_stacky_status_by_ado` y por `services/ticket_state_writeback.py`), el mecanismo de ruteo ADO↔GitLab que F3 quiere reconstruir a mano — con manejo de `CapabilityUnavailable`, mensaje de workaround para el operador, y ya probado. F3 no lo menciona ni una vez. Corregido: F3 suma un paso explícito de coordinación con el ratchet del 270 (editar `test_5` según su propio mensaje, no bypasearlo) y una nota de diseño sobre reusar `resolve_state_writer` en vez de duplicar la resolución de provider.
- **E21 (BLOQ)** — **La tabla "anclajes VOLÁTILES" de §3.4 — la defensa que el propio v4 construyó contra el drift — no cubre los DOS archivos que más se movieron.** Medido con `git diff 760ac455..HEAD --stat`: `api/tickets.py` **+109 líneas** (el corrimiento CRECE a lo largo del archivo — Motor D pasa de `:1489-1492` a `:1505/1507`, Motor E de `:1751`/`:2078,2080` a `:1780`/`:2135,2137`, Motor F de `:4080`/`:4779,4781` a `:4157`/`:4856,4858`) y `services/gitlab_provider.py` **+36 líneas** (`update_item_state` de `:228` a `:243`, medido con `grep -n`). Ambos archivos se citan por número en §2.1, §2.1bis, la "Salida REAL" de F8, §6 punto 6 y §7.1 — de los 9 archivos que §3.4 sabe re-localizar, ninguno es uno de estos dos. No son coordenadas de edición (el plan declara explícitamente que no toca ninguno de los dos), pero si alguien copia el bloque "Salida REAL" de F8 al PR sin re-correr el script — la trampa D1/E6 que este mismo plan ya sufrió tres veces — pega evidencia numérica falsa creyendo que es la medida. Corregido: dos filas nuevas en §3.4 con el grep de estos símbolos.
- **E22 (IMPORTANTE)** — **R10 (§5) da por buenos unos "0 hits" viejos y una colisión con el plan 270 que ya dejó de ser hipotética.** Decía *"el 270 no menciona `agent_completion_internal.py` ni `completion_state.py` (verificado: 0 hits)"* y recomendaba *"hacer el del 270 primero si ambos están listos"*. Las dos cosas cambiaron: el 270 está **mergeado** (`77627239`, ya en la ascendencia de este HEAD) y sí referencia `agent_completion_internal.py` — lo lee por AST en su ratchet y lo nombra por nombre y línea (`S5`, `:536`) más de diez veces en su propio documento. La disyuntiva de orden ya no aplica: el 270 llegó primero, y la colisión real es exactamente **E20**. Corregido: R10 apunta a E20 en vez de a una medición vieja.
- **`[ADICIÓN ARQUITECTO]` — §3.5: grep de colisión con ratchets de planes hermanos YA MERGEADOS, antes de tocar una función compartida.** Es el antídoto estructural a E20: la causa no fue un error de lectura, fue no preguntarle a la suite de tests si algún plan hermano *ya* vigila la función que este plan está por editar. Ver §3.5, nueva.

---

## CHANGELOG v3 → v4

El v3 acertó en lo grande y falló en lo que decía ser su fortaleza. Lo que **se verificó corriendo y resultó EXACTO**: el censo de F8 devuelve **las 9 entradas con los mismos números de línea** (reproducido); los **8 baselines de §3.3** dan **exactamente** los conteos declarados (56 / 4f+4p / 16 / 3 / 6 / 5 / 10 / 30); `test_b2_transition_from_config.py` está **ROJO con `5 failed`** y el `TypeError` literal; `api/tickets.py:574` **sí** emite `dev_build_gate_no_state`; `.toneAtencion, .toneEspera` **comparten `color: var(--warn)`** en `:150-151`; los **8 ratchets** de UI existen con esos nombres exactos; los **4 textos de ayuda llana pasan los 5 chequeos reales**; `_extract_current_state` lee `item["state"]`, así que el `FakeProvider` del plan es correcto; el test puente de F6 no tiene falsos positivos por subcadena. Nada de eso se toca.

Lo que falló salió de **correr los greps y los números**, no de releer:

- **E1 (BLOQ)** — **§2.0, la tabla rotulada "Línea REAL", es FALSA en 5 de sus 9 filas, y 4 de esas 5 "corrigieron" un anclaje del v2 que ya era correcto.** Medido en el árbol base: `_with_outcome` está en **`:65`** (no `:74-107`), el corte de flag en **`:75-76`** (no `:83-84`; `:83` es un `from services.run_outcome import ...` dentro de un `try`), `_outcome_badge_enabled` en **`:28-32`** (no `:63-68`; `:63-68` es la `def`+docstring de `_with_outcome`), el encolado del motor A en **`:183`** (`ticket_status.on_execution_end(`) y el `except` en **`:177`** — o sea que "`:183` es un `except`" es falso dos veces —, y el `return` de `publish_execution_from_review` en **`:493`** (no `:491`). La llamada `maybe_apply_state_transition(ev)` está en **`:119`**: el v2 dijo `:117` y el v3 `:118`, **los dos mal**. Peor: F5 conservó los números viejos (los correctos), así que el plan cargaba dos juegos contradictorios y rotulaba "REAL" el equivocado. §2.0 se reemplaza por la medición y **toda instrucción quirúrgica pasa a anclar por SÍMBOLO** (§3.4).
- **E2 (BLOQ)** — **los anclajes de la receta de 7 patas están desfasados y la costura P0 es la causa.** `_REQUIRES_MAP_FROZEN` pasó de 143 a **146** entradas (medido), o sea que el paquete P0 declaró 15 flags de otros planes y corrió `config.py` y `harness_flags.py` hacia abajo. Reales: `STACKY_ADO_STATE_MATRIX_ENABLED` en **`config.py:1419-1420`** (el plan decía `:1401-1406` y mandaba *"copiar el patrón exacto de `config.py:1404-1406`"*, que es otra flag), `STACKY_DETERMINISTIC_TASK_STATES_ENABLED` en **`:1260-1261`** (decía `:1245-1246`), `STACKY_UI_OUTCOME_REASON_BADGE_ENABLED` en **`:2085-2086`** (decía `:2070-2071`), y el `FlagSpec` de la matriz en **`harness_flags.py:2853-2866`** (decía `:2795-2807`, ~58 líneas de desfase). Corregidos y con su grep de re-localización en **§3.4**.
- **E3 (BLOQ)** — **el criterio `4 failed, 4 passed` NO distingue escribir los 4 textos de ayuda de no escribir ninguno. Es el falso verde del plan 270 otra vez.** Medido: `FLAG_REGISTRY` tiene **403** keys, `PLAIN_HELP` **324**, y hay **79 flags sin ayuda llana** hoy. `test_plain_help_covers_all_registry_keys` es **UN** test que ya falla por esos 79; sumarle 4 lo deja con 83 y **sigue siendo 1 test rojo** ⇒ el conteo global no se mueve. La salvaguarda añadida ("ninguna key `STACKY_FINAL_STATE_*` en la lista de **violaciones**") mira `violations`, el mensaje del test de jerga (`:76`); la ausencia de `PlainHelp` sale en `missing` (`:35`), otro test, otra lista: la guardia era ciega justo donde D5 apuntaba. Además §3.3 caracterizaba mal los 4 fallos (describía sólo el de jerga). El criterio pasa a ser **aserción de pertenencia + los 5 chequeos aplicados localmente** dentro de `test_plan271_flags.py` (§3.3, F1, F7).
- **E4 (BLOQ)** — **F9 nace con CUATRO violaciones y el plan arregla UNA; su criterio `3 passed` es insatisfacible.** Se corrió la regla del test 3 tal como está escrita: **28 returns analizados, 4 violaciones**. Además de `task_states.py:183` (la conocida, que F3-bis-3 tapa), aparece **`agent_completion_internal.py:547`** — el `except` del camino **legacy** de `_attempt_state_change` devuelve `{"ok": False, "to", "ado_id", "error", "type"}` **sin `reason`**: es el mismo defecto de D3 en la rama hermana, **el plan no lo nombra nunca**, y es justo la rama que corre en el caso común de R6-bis. Y `:493` y `:54` son **falsos positivos** (los sobres `CloseResult`, con `"ok": bool(...)` y `"ok": self.ok`) que la regla no puede distinguir porque exige `ok` literal `True`. El plan prohíbe "agregar una excepción al centinela" y su escape ("agregá la razón al catálogo") no aplica a ninguno de los tres. F9 se **acota a los `return` dentro de las funciones escritoras**, F3 agrega `reason` en `:547`, y el baseline de 4 queda declarado.
- **E5 (BLOQ)** — **las dos huellas de regresión del DoD, escritas como el plan las prescribe, rompen un test compartido — y ese test YA está rojo sin que el plan lo declare.** `docs/sistema/error_fingerprints.json` es un **dict** (`schema_version`/`description`/`fingerprints`, 42 entradas) y `tests/test_error_fingerprints_catalog.py:18` congela **9 campos obligatorios**: `id, title, class, status, log_pattern, log_guarded, killed_by, guard_test, self_test`, con `status ∈ {by_design, open, resolved}`, `log_pattern` que compile y `self_test.matches`/`.clean` que matcheen y no matcheen de verdad. El plan prescribía `{"id","patron","plan","fecha","guard_test"}`: **faltan 6 de 9** e **inventa 3** — inmediatamente después de escribir *"no inventes el esquema"*. Baseline medido y no declarado: `test_error_fingerprints_catalog.py` **3 failed, 5 passed**; `test_error_fingerprints_scan.py` **2 failed, 7 passed**.
- **E6 (BLOQ)** — **el censo de F8 es ciego al escritor de estado de GitLab, así que el KPI "un séptimo escritor rompe CI" es falso para la clase de escritor más probable.** `services/gitlab_provider.py:228 def update_item_state` escribe el estado en GitLab (labels + cierre vía `self._client._request`) y **no aparece** en las 9 entradas, porque la regla sólo ve **llamadas** `ast.Attribute` con esos dos nombres y el cuerpo de esa función no llama a ninguno. `services/ado_provider.py:82` sí aparece — sólo porque su cuerpo llama a `update_work_item_state`. Asimetría medida: el censo censa el adaptador ADO y no ve el de GitLab, en un plan cuyo titular de F3 es **paridad ADO↔GitLab**; un adaptador nuevo (Mantis, plan 217) entraría igual de invisible. F8 pasa a censar también **definiciones** y el allow-list a **12** — y al correrlo apareció además `services/ado_client.py:926 update_work_item_state`, el **escritor terminal de ADO** (el que hace el PATCH real), que **no había censado ninguna versión** de este plan… **ni la primera estimación de esta misma crítica, que dijo 11 y al correr el censo dio 12**. Es la mejor prueba de que el Paso 0 no se puede reemplazar por contar de cabeza.
- **E7..E12 (IMPORTANTES)** — la tabla de verdad del resolver **no cubre (matriz + flag OFF)** ni (employee + flag OFF), y de eso depende la promesa "byte-idéntico con las flags apagadas" (§3-7): si la flag gatea la matriz, apagarla **regresiona el 208**; el plan **no menciona el 269 ni una vez** (0 hits) y el 269 es el que comparte `api/executions.py` con F5; **`var(--text-secondary)` NO EXISTE** (0 hits en `theme.css`; los reales son `--text-primary`/`--text-muted`/`--text-faint`) y el plan lo declara real; los ~20 comandos apuntan por ruta absoluta al **árbol principal** y `backend\.venv` **no existe en un worktree**; el bloque "ANTES" de F2 omite el comentario real de `:97` y muestra indentación 0 donde el código está a 8 espacios; el criterio `0 passed, 4 failed` de F0 no admite el `SQLITE_LOCKED` que el propio plan declara probable.
- **E13..E18 (MENORES)** — **E13:** los 4 conteos de caracteres de la ayuda llana están mal (dice 113/116/104/121; reales **110/108/92/115** — pasan igual, pero el plan usa "medido" como argumento de autoridad). **E14:** el one-liner del "Paso 0 OBLIGATORIO" de F8 **no corre**: llama a `_walk()` y `_is_writer()`, dos funciones que nunca define ⇒ `NameError`, o sea que la mitigación entera de R12 era inejecutable (reemplazado por un script que sí corre). **E15:** `_CATEGORY_KEYS["flujo_funcional"]` abre en **`:272`**, no `:268-273` (`:268-270` son keys del 267). **E16:** la 7ª pata no dice que `requires` **no** hace falta (verificado: `test_requires_map_is_frozen` sólo mira flags **con** `requires`, y el archivo está en **9 passed**) ⇒ agregada como pata 8 con la prohibición explícita. **E17:** F9 tiene el bloque "Flag: ninguna (es un test)" **duplicado** palabra por palabra. **E18:** el test de jerga se cita como `:63-70` en §3.1 y `:63-76` en §3.1bis (el real es `:63-76`, con el assert en `:76`).
- **`[ADICIÓN ARQUITECTO]`** — **§3.4: tabla de anclajes VOLÁTILES con su grep de re-localización.** Es el antídoto estructural a E1+E2+E8: los anclajes de wiring se movieron una vez (costura P0) y se van a mover otra (el 269 está en vuelo sobre el mismo archivo). En vez de números, cada fila trae el `grep -n` que los encuentra.
- **`[ADICIÓN ARQUITECTO]`** — **§8: datos personales y prohibición de escribir en el tracker real.** El plan cambia lo que se escribe en el tablero de terceros del operador y persiste 27 razones que se muestran; faltaba decir qué NO se persiste, y faltaba una regla dura de que ningún test toque un tracker real.

---

## CHANGELOG v2 → v3

El v2 cerró los 8 bloqueantes del v1 **de una sola pasada**, y sus ~70 anclajes verificados uno por uno resultaron casi todos **EXACTOS** (ver §2.0). Lo que falló, otra vez, fue lo mismo que en el v1 pero un nivel más arriba: **el censo** (esta vez con evidencia ejecutable en contra), **la dirección de una guardia**, y **dar por verdes dos tests que hoy están rojos**. Los seis bloqueantes salieron de **correr cosas**, no de releer el documento.

- **D1 (BLOQ)** — §2.1 decía "CUATRO motores" y F8 congelaba un allow-list de **6 entradas**. Se corrió el censo AST **exactamente como F8 lo especifica** (`update_item_state` / `update_work_item_state` como `ast.Attribute`, más `_safe_transition`, bajo `backend/` sin tests ni venvs) y devuelve **9 entradas**. Faltaban tres, dos de ellas **motores de pleno derecho**: `api/tickets.py::finish_work` (`:2078,:2080` — **el propio plan lo cita en §6.6 como `finish_work:1751` y aun así no lo censó**) y `api/tickets.py::create_child_task` (`:4779,:4781`), más el adaptador `services/ado_provider.py::update_item_state` (`:82`), que la regla AST captura de manera inevitable. Con el allow-list de 6, **F8 nace rojo el día 1**. §2.1 pasa a **SEIS motores**; F8 al allow-list **verificado de 9** con la salida del censo pegada.
- **D2 (BLOQ)** — **el árbitro de F2-bis guarda la dirección equivocada.** El motor A se **encola** en el Paso 2 (`agent_completion_internal.py:172-181`), **antes** de que el motor B escriba en `:274`. Con la cola vacía el daemon (`completion_dispatcher.py:100-121`, `maybe_apply_state_transition(ev)` en `:118`) drena de inmediato ⇒ el orden más probable es **A primero, B después**, y F2-bis solo instrumentó `completion_state.py`: el motor B escribe segundo **sin árbitro ninguno**. R3, que el propio v2 subió a "Alta" y admite que F2 **agrava**, quedaba sin mitigar en su orden más probable. El árbitro pasa a ser **simétrico** (F2-bis guardia 2 en A **y** F3-bis-2 en B, misma key, mismo helper).
- **D3 (BLOQ)** — **el catálogo no cierra, y su agujero es el caso más operable.** (a) §2.4 afirma listar "todas las razones que el código puede emitir hoy": falta `dev_build_gate_no_state`, que **`api/tickets.py:574` ya emite hoy** y que el v2 presenta como "razón nueva de F2-bis". (b) Peor: la rama de **error** de `_safe_transition` (`task_states.py:180-184`) devuelve `{"ok": False, "to", "error", "type", "phase"}` **sin `reason`**, y el helper de F5 lo traduce a `reason="unknown"` — una razón que **no está** en `ALL_FINAL_STATE_REASONS` ni en el `.ts`. O sea: el fallo real de escritura (un `ADO 400`) es exactamente el que cae **fuera** del catálogo, violando §3-4 y el KPI "23 de 23". Catálogo recontado a **27**, con `transition_failed` cableado en el origen y **F9** como centinela.
- **D4 (BLOQ)** — **`test_b2_transition_from_config.py` está ROJO HOY** (`5 failed`, `TypeError: _resolve_transition_state_from_config() missing 1 required keyword-only argument: 'final_status'`). F4 lo declaraba *"verde (5 tests)"* como criterio binario y **F7 lo registra en el arnés** ⇒ el arnés entero se pone rojo en cuanto se lo adopta. F4 ahora **lo arregla explícitamente** (agregar el kwarg en 5 call sites; no se borra ni un assert) **antes** de que F7 lo registre.
- **D5 (BLOQ)** — **faltan 3 de las 4 ayudas llanas obligatorias, y la que falta tiene trampa.** `test_plain_help_covers_all_registry_keys` (`test_harness_flags_help.py:32-35`) exige `PlainHelp` para **toda** key del registry; el v2 escribe **un solo texto** (F1) y en F3/F4/F5 dice "cablear las 7 patas" sin darlos. La denylist incluye literalmente `gate`, `hook`, `runtime`, `endpoint`, `backend`, `frontend`, `token`, `prompt` — y la flag de F4 se llama `..._PUBLISH_GATE_PRECISE_ENABLED`. Los **4 textos** van escritos y medidos campo por campo en §3.1bis.
- **D6 (BLOQ)** — **la "confirmación" de que F3 rompe `test_output_watcher.py` es FALSA, y lo que esconde es peor.** `_mk_ticket` (`test_output_watcher.py:87-107`) crea el Ticket con `project="RSPacifico"` y **sin `stacky_project_name`**; `close_execution_with_publish` lo lee de ahí (`:135`) ⇒ `project_name is None` ⇒ la regla dura de F3 toma el **camino legacy** y el doble actual funciona sin tocar una línea. F3-bis era innecesario y R6 ("Confirmada, no es hipótesis") era falso. Lo que eso destapa: **un ticket sin `stacky_project_name` sigue escribiendo en ADO aunque el proyecto sea GitLab, en silencio y sin razón visible** — el bug que F3 dice cerrar. F3 emite ahora `no_project_context` y el KPI de paridad se sincera.
- **D7..D14 (IMPORTANTES)** — `_with_outcome` está en `:74-107` y su corte de flag en **`:83`** (el v2 decía `:65-92` y `:75-76`), y eso sostiene una edición quirúrgica; `_outcome_badge_enabled` está en `:63-68` (no `:28-32`); el encolado del motor A es `:172-181` (no `:183`); `_post_hook` es `:53-59` y `enqueue_completion` `:30-50`; el `return` de `publish_execution_from_review` es `:491`; `outcomeToneClass` es `:89-94`; la guardia 1 hacía **dos lookups de DB/disco por cada completación** aunque `gate_final_state` sea no-op para todo lo que no sea `developer`; los helpers de F0 seguían con cuerpo `...` (C15 quedó a medio cerrar); `.toneEspera` y `.toneAtencion` **comparten `color: var(--warn)`** ⇒ el cuarto tono que F6 manda agregar es un no-op visual.
- **D15..D18 (MENORES)** — el `:280` del CHANGELOG C7 se lee como `task_states.py:280`, archivo de **262 líneas** (es `agent_completion_internal.py:280`); F6 mandaba correr "los ratchets bajo `frontend/src/**/__tests__/`" cuando viven en `src/__tests__/` y son **8** archivos nombrables; `error_fingerprints.json` **existe** ⇒ el hedge "si no existe no lo crees" sobra y la huella es obligatoria; `test_harness_flags_help.py` tiene **4 fallos ajenos preexistentes** que ninguna fase declaraba con números.
- **`[ADICIÓN ARQUITECTO]`** — **F9: ninguna razón fuera del catálogo.** Un centinela que corre los escritores por sus ramas de error y afirma que **todo** dict que devuelven trae `reason ∈ ALL_FINAL_STATE_REASONS`. Es el defecto D3 convertido en test: el plan promete "cero skip mudo" y hoy su propio helper inventa `"unknown"`. Sin esto, la promesa vuelve a vivir en la cabeza de quien implementa.
- **`[ADICIÓN ARQUITECTO]`** — **§3.3: baseline medido de rojos ajenos.** Los números reales de hoy, corridos, para que "ya estaba rojo" deje de ser una excusa reusable y pase a ser una comparación.

---

## CHANGELOG v1 → v2

Anclajes verificados abriendo los archivos: **~70 citas**. La mayoría (config, flags, `agent_completion_internal`, `api/executions`, frontend) estaban **EXACTAS**. Lo que falló fue el **censo** y las **costuras entre fases**.

- **C1 (BLOQ)** — §2.1 decía "conviven **dos** motores". Son **CUATRO**: faltaban el **Motor C** `api/tickets.py:531 _apply_task_state` (plan 79, llamado desde `set_stacky_status_by_ado` `:1473`), que **ya honra el `next_state_ok` de nivel rol** porque toma `plan.final_ok` sin exigir `source=="matrix"`, y el **Motor D** inline `api/tickets.py:1489-1491`, sin plan dueño. §2 reescrita entera; KPI corregido; agregada la **hipótesis del deploy** (`harness_defaults.env:33`); alcance del Motor D declarado en §2.1bis.
- **C2 (BLOQ)** — F2 podía **pisar el gate de build del plan 210**: `_apply_task_state` aplica `dev_build_verify.gate_final_state` (`api/tickets.py:576-582`) y `completion_state.py` tiene **0** apariciones de `dev_build_verify`. Nueva **F2-bis** obligatoria.
- **C3 (BLOQ)** — el criterio de F0 (`0 passed, 4 failed`) era insatisfacible: `test_rc1_razon_del_skip_nunca_es_silenciosa` nacía **VERDE** (`completion_state.py:50` y `:53` ya devuelven `reason`). Test reemplazado.
- **C4 (BLOQ)** — F0-test4 ("el archivo no debe contener `from services.ado_client import AdoClient`") era **mutuamente insatisfacible** con F3, que conserva a propósito el camino legacy y agrega `_legacy_ado_client()`. Test reescrito en forma **positiva** y acotado a la función.
- **C5 (BLOQ)** — F3 declaraba `test_output_watcher.py` verde como criterio binario, pero lo **rompe**: el doble del test (`:359-361`) no acepta los kwargs con que `build_ado_client` construye `AdoClient`. F3 ahora especifica la adaptación exacta del doble (sin borrar asserts).
- **C6 (BLOQ)** — F3 no definía `project_name=None`: `get_tracker_provider(None)` resuelve el **proyecto activo** y podía escribir en el tracker equivocado. Regla explícita agregada.
- **C7 (BLOQ)** — F5 exigía `source="role"` pero `_safe_transition` hardcodea `"source": "config"` (`harness/task_states.py:178`). Firma del helper y contrato de `source` corregidos; el `setdefault("source", ...)` de `:280` también quedaba roto por F3.
- **C8 (BLOQ)** — las "12 razones" de §2.4 y las 12 del mapa de F6 eran **conjuntos distintos** (intersección: 7). Catálogo único de **23** razones, congelado en Python y verificado contra el `.ts` por un test real.
- **C9..C17 (IMPORTANTES)** — anclaje falso de RC-3 (`api/tickets.py:1520` serializa otra variable); `set_stacky_status_by_ado` declarado fuera de scope pero tocado de hecho (arranca en **:1205**, no `:1487`); R3 "no lo empeora" era falso (carrera daemon vs inline); el "resolutor único" nacía con 2 de 4 ramas sin productor; agujero de **celda de matriz parcial**; F5 gateado por una flag **ajena** (`STACKY_UI_OUTCOME_REASON_BADGE_ENABLED`, `api/executions.py:75-76`); F0 no ejecutable ("los helpers los escribís vos"); `on_failure_state` sin una línea; anclajes desfasados corregidos con la línea real.
- **C18..C22 (MENORES)** — límites reales de `PlainHelp`; `styles.toneEspera` **sí existe**; huella de regresión; ambigüedad `.venv`/`venv`; renombre silencioso `no_final_state`→`no_config`.
- **`[ADICIÓN ARQUITECTO]`** — **F8: censo ejecutable de escritores de estado** (`test_plan271_censo_escritores.py`). Es exactamente el defecto que hizo caer al v1: nadie podía saber cuántos motores escriben estado. Ahora el repo lo sabe y se rompe solo si aparece un cuarto.
- **`[ADICIÓN ARQUITECTO]`** — **F2-bis: árbitro anti-doble-escritura por `execution_id`**, que resuelve C2 y C11 sin fusionar los motores.

---

## 1. Objetivo, KPI e impacto

El operador configuró, en la pantalla que Stacky le dio para eso, que al terminar el **Analista Técnico** la incidencia pase a `To Do`. Stacky corre el agente, lo cierra en verde… y la incidencia se queda exactamente en el estado en el que llegó. Sin error, sin aviso, sin razón visible en ningún lado.

Este plan hace cuatro cosas, en este orden: **(1)** diagnostica **cuál de los seis motores** debía moverla y no lo hizo; **(2)** repara esa causa sin romper las guardias que otros planes ya pusieron; **(3)** elimina el *skip mudo* — todo no-cambio de estado deja una razón que el operador ve donde ya mira; **(4)** deja la escritura de estado en paridad ADO ↔ GitLab y **censada**, que hoy no lo está.

No es una feature nueva. Es **reparar un comportamiento que el operador ya configuró y que Stacky prometió aplicar**.

### KPI (medibles, sin instrumentación nueva)

| KPI | Hoy | Después |
|---|---|---|
| Incidencias que quedan en el estado de entrada tras un cierre por **post-hook** (los 3 runtimes) con `next_state_ok` a nivel rol | **100 %** (skip `no_matrix_cell`, `completion_state.py:90-92`) | **0 %** |
| Incidencias que quedan en el estado de entrada tras un cierre por `PATCH /by-ado/<id>/stacky-status` con la flag del 79 **apagada en deploy** (`harness_defaults.env:33`) | **100 %** | **0 %** (lo cubre el post-hook, que no depende de esa flag) |
| Razones de no-transición visibles para el operador | **0 de 27** (mueren en `CloseResult.ado_state_change` y en `SystemLog`) | **27 de 27** en el drawer de la ejecución |
| Escrituras de estado que fallan y **no dicen por qué** (`_safe_transition` rama de error, `task_states.py:180-184`, devuelve dict **sin `reason`**) | **100 %** (el v2 las traducía a `"unknown"`, razón fuera de todo catálogo — **D3**) | **0 %** (`transition_failed`, cableado en el origen y verificado por **F9**) |
| Trackers soportados por el escritor de estado del chokepoint, **para tickets con `stacky_project_name`** | **1** (ADO; `agent_completion_internal.py:527,536`) | **2 técnicamente** (ADO + GitLab, ruteado vía `tracker_write_router.resolve_state_writer`) — **pero GitLab sólo cuando `next_state_ok` coincide con una de las 4 claves lógicas de `gitlab_provider._state_map_for_gitlab` (`functional`/`accepted`/`rejected`/`in_progress`)**; fuera de esas 4 — el caso común, dado que la UI enseña vocabulario ADO — `reason="transition_failed"`, visible pero sin reparación de vocabulario en este plan (**E24, R17, plan 272**) |
| Tickets **sin** `stacky_project_name` en un proyecto GitLab: escritura silenciosa a ADO | **100 % mudo** | **100 % legacy pero con razón visible** (`no_project_context`) — la reparación de fondo es del **272** (**D6**) |
| Motores de estado conocidos y verificados por un test | **0** (el v1 contó 2 y el v2 contó 4 donde hay **6**) | **6/6 motores + 2 helpers del 79 + 4 adaptadores/cliente/puerto + 1 router del plan 270 censados**, allow-list de **13 entradas** (**[v5, E19] no 12: re-corrido contra el HEAD de hoy apareció `tracker_write_router.py::write_state_for_ticket`, del plan 270, ya mergeado**); un **octavo escritor o un adaptador de tracker nuevo** rompe CI |
| Clics del operador para arreglarlo | N/A (hoy no puede: no sabe que pasó) | **0** |

> **KPI corregido (C1).** El v1 afirmaba "100 % con `next_state_ok` a nivel rol" a secas. Es falso en general: por el camino `set_stacky_status_by_ado` (`api/tickets.py:1205`), con `STACKY_DETERMINISTIC_TASK_STATES_ENABLED` **ON** (default de `config.py:1245-1246`), `_apply_task_state` **sí** aplica el nivel rol. El 100 % vale para el camino del post-hook, y para el camino del 79 **solo cuando la flag está apagada**, que es exactamente lo que hace el deploy (`harness_defaults.env:33` fuerza `=false`).

### Impacto esperado

El operador deja de tener que mover incidencias a mano después de cada corrida del analista técnico, y — más importante — deja de tener que *adivinar por qué* no se movieron. El tablero vuelve a decir la verdad sin intervención.

---

## 2. Por qué ahora, y la causa raíz diagnosticada

### 2.0 Estado de los anclajes — TERCERA medición, contra el commit base `760ac455` (E1)

Las **afirmaciones negativas** del v2/v3 se re-verificaron y dieron **todas verdaderas**: `STACKY_FINAL_STATE*` = 0 hits en `backend/` y `frontend/src`; `final_state_resolver` / `finalStateOutcome` / `final_state_outcome` = 0 hits; `dev_build_verify` = 0 hits en `completion_state.py`; `_apply_task_state` llamado **solo** desde `:1473`; `test_b2_transition_from_config` = 0 hits en ambos scripts del arnés. Eso se conserva.

Lo que **no** se sostuvo es la tabla de "correcciones" del v3. Se midió fila por fila abriendo los archivos en el commit base:

| Anclaje | v2 decía | v3 "corrigió" a | **REAL (medido en `760ac455`)** | Veredicto |
|---|---|---|---|---|
| `api/executions.py` `_with_outcome` | `:65-92` | `:74-107` | **`def` en `:65`, cuerpo `:75-92`** | **el v2 tenía razón; el v3 lo rompió** |
| `api/executions.py` corte de flag | `:75-76` | `:83-84` | **`:75-76`** (`:83` es `from services.run_outcome import ...` dentro de un `try`) | **el v2 tenía razón** |
| `api/executions.py` `_outcome_badge_enabled` | `:28-32` | `:63-68` | **`:28-32`** (`:63-68` es la `def`+docstring de `_with_outcome`) | **el v2 tenía razón** |
| `agent_completion_internal.py` encolado del motor A | `:183` | `:172-181`, *"`:183` es un `except`"* | **`ticket_status.on_execution_end(` en `:183`**; el `except` está en **`:177`**; el Paso 2 abre en `:180-181` | **el v2 tenía razón; la justificación del v3 es falsa** |
| `publish_execution_from_review` `return` | `:493` | `:491` | **`:493`** (`ast.Return.lineno`) | **el v2 tenía razón** |
| `completion_dispatcher.py` `_post_hook` | `:51-57` | `:53-59` | **`def` en `:53`** | v3 correcto |
| `completion_dispatcher.py` `enqueue_completion` | `:28-48` | `:30-50` | **`def` en `:30`** | v3 correcto |
| `completion_dispatcher.py` `_drain_loop` | `:98-120` | `:100-121` | **`def` en `:100`** | v3 correcto |
| `completion_dispatcher.py` llamada `maybe_apply_state_transition(ev)` | `:117` | `:118` | **`:119`** | **los dos mal** |
| `ExecutionDetailDrawer.tsx` `outcomeToneClass` | `:90-95` | `:89-94` | **`:89`** | v3 correcto |
| `harness/task_states.py` total de líneas | — | 262 | **262** | v3 correcto |
| CHANGELOG C7 `setdefault("source", ...)` | `:280` ambiguo | `agent_completion_internal.py:280` | **`agent_completion_internal.py`** (task_states tiene 262 líneas) | v3 correcto |

> **Corolario 3 (E1) — la lección estructural.** Tres versiones seguidas se equivocaron con anclajes numéricos, y la tercera se equivocó **corrigiendo cuatro que estaban bien**. La causa no es descuido: es que estos archivos se mueven entre pasadas (la costura P0 los movió; el 269 los va a mover otra vez). Por eso el v4 **deja de anclar por número** en toda instrucción que edite código: §3.4 da el símbolo y el `grep` que lo encuentra. Los números que quedan en el documento son **evidencia de una medición fechada**, no coordenadas de edición.

**Anclajes re-verificados y EXACTOS** (no hace falta re-medirlos): `completion_state.py` `:88-99` como rango del bloque a reemplazar, con `no_matrix_cell` en `:92`, `no_final_state` en `:96`, `state_not_applicable` en `:99`, `_OK_STATUSES` `:24-25`, `matrix_enabled` `:28`, `_origin_guard` `:121`, `_logged` `:164`, `return result` `:191`, import local de `get_tracker_provider` en `:101`, `_safe_transition(...)` en `:113`; `task_states.py` `:104-113` (bloque de `resolve_task_state_plan`), `def _safe_transition` `:146`, docstring *"ÚNICA función que escribe estado"* `:155`, `_extract_current_state` `:128`, rama de error `:183`; `agent_completion_internal.py` `close_execution_with_publish` `:66`, `stacky_project_name` `:135`, `_resolve_transition_state_from_config` `:321`, `_set_publish_hold` `:419`, `publish_execution_from_review` `:434`, `_attempt_state_change` `:502`; `api/tickets.py:574` (`dev_build_gate_no_state`); `dev_build_verify.py` `workspace_root_for_ado` `:343`, `gate_final_state` `:413` con el `not_applicable` en `:422`; `tracker_provider.py` `get_tracker_provider` `:125`, chequeo de GitLab `:133-135`; `StatesConfigPage.tsx` `:76-78`, `:102`, `:196-202` con el `onChange` en `:201`; `harness_defaults.env:33`; `harness_flags_help.py:893-898`; `models.py:331`; `ExecutionDetailDrawer.module.css:150-151`.

### 2.1 Los SEIS motores que hoy pueden mover el `System.State` (censados corriendo el AST, no supuestos) — D1

Ninguno sabe que los otros existen. **El v1 contó dos, el v2 contó cuatro. Son seis.** Esta lista no salió de leer: salió de correr el censo AST que F8 especifica.

**Motor A — "matriz" (plan 208), asíncrono.**
`app.py:997-1000` registra `completion_dispatcher` en `ticket_status.register_post_hook` y arranca su daemon. Al terminar **cualquier** agente en **cualquiera de los 3 runtimes**, `ticket_status.on_execution_end` (`services/ticket_status.py:293`) llama `_run_post_hooks` (`:349-355`), el hook encola O(1) (`completion_dispatcher.py:51-57` → `:28-48`) y el **daemon de fondo** `_drain_loop` (`completion_dispatcher.py:98-120`) llama `completion_state.maybe_apply_state_transition(ev)` en **`:117`**. Escribe vía `harness/task_states.py:146 _safe_transition`, provider-aware (`:171-177`). Flag `STACKY_ADO_STATE_MATRIX_ENABLED` **ON** (`config.py:1404-1406`; `harness_flags.py:2795-2807 default=True`; **ausente** de `harness_defaults.env`, o sea que el default del código manda también en deploy).

**Motor B — "employee_config" (B2 / plan 216), síncrono.**
`services/agent_completion_internal.py:66 close_execution_with_publish` es el chokepoint de `api/tickets.py:1386`, `api/qa_browser.py:373`, `api/qa_uat.py:394`, `services/output_watcher.py:412` y `:618`. Paso 3.5 (`:242-258`) resuelve `transition_state` con `_resolve_transition_state_from_config` (`:321-386`); Paso 4 (`:260-280`) escribe con `_attempt_state_change` (`:502-553`).

**Motor C — "determinista" (plan 79 + gate del 210), síncrono. ⟵ EL QUE EL v1 NO VIO.**
`api/tickets.py:531 _apply_task_state`, llamado **solo** desde `set_stacky_status_by_ado` en `api/tickets.py:1473`, gateado por `deterministic_task_states_enabled()` (`harness/task_states.py:19-28`, lee el atributo de **clase** `Config`). Su código relevante:

```python
# api/tickets.py:545-551
plan = resolve_task_state_plan(profile, agent_type, getattr(ticket, "work_item_type", None))
target = plan.in_progress if phase == "start" else plan.final_ok   # ← NO exige source=="matrix"
if not target:
    return {"skipped": True, "reason": f"no_{phase}_state", "source": plan.source}
if target not in applicable_states(plan):
    return {"skipped": True, "reason": "state_not_applicable"}
```

y antes de escribir aplica el **gate de build del plan 210** (`api/tickets.py:576-582`), que puede **degradar** el target cuando el Developer no tiene veredicto de máquina fresco.

**Motor D — escritor inline (sin plan dueño).**
`api/tickets.py:1489-1492`, dentro del mismo `set_stacky_status_by_ado`, rama `elif target_ado_state:`: llama `_provider.update_item_state(...)` (`:1490`) o `_ado_client_for_ticket(...).update_work_item_state(...)` (`:1492`) directo, sin `_safe_transition`.

**Motor E — `finish_work` (sin plan dueño). ⟵ EL QUE EL v2 NO VIO, PESE A CITARLO EN §6.6.**
`api/tickets.py:1751 finish_work`, bloque *"── 4. Cambiar estado en ADO ──"*: `_provider.update_item_state(str(ado_id), target_ado_state)` (`:2078`) o `_ado_client_for_ticket(ticket=ticket).update_work_item_state(...)` (`:2080`), sin `_safe_transition`, sin idempotencia, sin guardia de origen. El v2 lo nombró en §6.6 como *"`finish_work:1751`"* y **aun así lo dejó fuera del allow-list de F8** — exactamente el mismo error del v1, un nivel más arriba.

**Motor F — `create_child_task`. ⟵ TAMPOCO ESTABA.**
`api/tickets.py:4080 create_child_task`: `_provider.update_item_state(str(task_ado_id), target_state)` (`:4779`) o `ado.update_work_item_state(task_ado_id, target_state)` (`:4781`). Escribe el estado de la **tarea hija** recién creada. Es el más lejano al síntoma reportado, pero es un escritor de `System.State` y el censo lo encuentra, así que o está en el allow-list o F8 nace rojo.

**Adaptadores (no son motores; el censo captura uno solo por accidente) — E6.**
- `services/ado_provider.py:82 AdoTrackerProvider.update_item_state` hace `self._client.update_work_item_state(int(item_id), logical_state)`. La regla AST de F8 (`ast.Attribute` con `attr == "update_work_item_state"`) **lo marca** — pero lo marca por el **nombre de lo que llama**, no por ser un escritor.
- `services/gitlab_provider.py:228 GitLabTrackerProvider.update_item_state` **escribe el estado en GitLab** (agrega el label de estado y cierra el issue vía `self._client._request`). **La regla del v3 NO lo ve**, porque es una `def` y su cuerpo no llama a ninguno de los dos nombres vigilados. Medido: no aparece en las 9 entradas.
- `services/tracker_provider.py:85 update_item_state` es el **Protocol** del puerto (cuerpo `...`). Tampoco aparece.
- `services/ado_client.py:926 update_work_item_state` es el **cliente terminal de ADO**: el que hace el PATCH real de `System.State`. **Nunca lo censó nadie**, en ninguna versión de este plan — ni el v4 en su primera estimación (§F8, ver la nota del Paso 0).

**Son CUATRO escritores de puerto/adaptador/cliente, y el v3 censaba UNO.**

> **Por qué esto invalidaba el KPI.** El censo del v3 censaba el adaptador **ADO** y era estructuralmente ciego al de **GitLab**, en un plan cuyo titular de F3 es *paridad ADO ↔ GitLab*. Un adaptador nuevo (Mantis, plan 217) entraría igual de invisible, y el KPI *"un séptimo escritor rompe CI"* sería falso justo para la clase de escritor que más probablemente aparezca. **F8 pasa a censar también las `FunctionDef` llamadas `update_item_state`/`update_work_item_state`**, y el allow-list sube a **11**.

> **Corolario 1 (C1, conservado).** La frase del v1 "el plan 208 eligió no honrar el nivel de rol" es cierta **solo para el motor A**. El motor C sí lo honra. Por eso el síntoma reportado no puede explicarse sin decir **por qué camino se cerró la ejecución**.
>
> **Corolario 2 (D1, nuevo).** Dos versiones seguidas de este plan contaron mal los motores, y las dos veces el error sobrevivió a una crítica con anclajes exactos. Eso no se arregla contando mejor: se arregla **corriendo el censo antes de escribir el allow-list**, que es lo que F8 ahora obliga (§F8, paso 0).

### 2.1bis Alcance de cada motor en ESTE plan (tabla vinculante)

Esta tabla manda. Si alguna fase parece contradecirla, gana la tabla.

| Motor | Símbolo | ¿Este plan lo **modifica**? | ¿Lo **censa** (F8)? | ¿Lo cubre el **árbitro simétrico**? |
|---|---|---|---|---|
| **A** | `completion_state.maybe_apply_state_transition` | **SÍ** — F2, F2-bis, F5 | SÍ | **SÍ** (guardia en F2-bis) |
| **B** | `agent_completion_internal._attempt_state_change` | **SÍ** — F3, F3-bis-2, F4, F5 | SÍ | **SÍ** (guardia simétrica en F3-bis-2 — **D2**) |
| **C** | `api/tickets.py:531 _apply_task_state` | **NO** (§6.6) | **SÍ** | **NO** |
| **D** | `api/tickets.py:1489-1492` inline | **NO** (§6.6) | **SÍ** | **NO** |
| **E** | `api/tickets.py:1751 finish_work` (`:2078,:2080`) | **NO** (§6.6) | **SÍ** | **NO** |
| **F** | `api/tickets.py:4080 create_child_task` (`:4779,:4781`) | **NO** (§6.6) | **SÍ** | **NO** |
| — | `services/ado_provider.py:82` (adaptador) | **NO** | **SÍ** (etiquetado adaptador) | N/A |

**Decisión explícita sobre los motores D, E y F, en una frase:** *el 271 los **censa** en el allow-list de F8 con su etiqueta para que queden nombrados y no vuelvan a desaparecer de un censo, pero **no los modifica ni los arbitra**, y difiere su unificación al **plan 272**.*

**Por qué el árbitro no cubre C, D, E ni F (y no es un olvido):** el árbitro se apoya en la key `final_state_outcome` del `metadata_json` de la ejecución, que **solo F5 escribe**, y F5 solo toca los motores A y B. C, D, E y F viven en `api/tickets.py`, que §6.6 declara intocable en este plan (territorio del 270 y del 272). **Consecuencia aceptada y declarada:** un cierre por `PATCH /by-ado/<id>/stacky-status` o por `finish_work` puede seguir produciendo dos escrituras (C/D/E, más A por el post-hook). Eso **ya pasa hoy** y este plan no lo empeora en esos caminos, porque no toca ninguno. Lo que sí cierra es la carrera **A vs B**, que es la que F2 sí agrava — **y la cierra en las dos direcciones**, no en una (D2).

### 2.2 CAUSA RAÍZ PRIMARIA (RC-1) — la única UI que el operador tiene escribe en una clave que el motor A se niega a leer

Cuatro anclajes, los cuatro **verificados**:

**(a) Dónde escribe el operador.** La pantalla "Estados del tracker" (plan 216, montada en `SettingsPage.tsx:246` bajo el sub-tab `flow`) es la única que dice literalmente *"Por cada rol: en qué estados actúa y **a cuál mueve el ticket al terminar**"* (`frontend/src/pages/StatesConfigPage.tsx:100-103`) y se presenta como *"Una sola fuente"* (`:84-88`). Su guardado es:

```ts
// frontend/src/pages/StatesConfigPage.tsx:76-78
function actualizarRol(rol: StateRole, parche: Partial<RoleStateMachine>) {
  guardar.mutate({ ...maquina, [rol]: { ...(maquina[rol] ?? {}), ...parche } });
}
```

y el campo del estado final es `next_state_ok` **a nivel de rol** (`:196-202`, `onChange={(v) => onChange({ next_state_ok: v })}` en `:201`). Escribe, por tanto, `tracker_state_machine.technical.next_state_ok = "To Do"`. **Nunca** escribe `by_work_item_type`.

**(b) Qué exige el motor A.** `services/completion_state.py:88-92`:

```python
plan = resolve_task_state_plan(profile, agent_type, work_item_type)
ctx["source"] = plan.source
if plan.source != "matrix":
    # Backward-compat DURA: sin cell configurado, los paths de runner NO transicionan.
    return _logged(ctx, ev, {"skipped": True, "reason": "no_matrix_cell", "source": plan.source})
```

**(c) Cuándo `source == "matrix"`.** `backend/harness/task_states.py:104-113`:

```python
cell = _matrix_cell(m, work_item_type)          # m["by_work_item_type"][<wit>]
ip_m = (cell.get("in_progress") or "").strip() or None
fk_m = (cell.get("next_state_ok") or "").strip() or None
if ip_m is not None or fk_m is not None:        # ← BASTA in_progress para ganar "matrix"
    return TaskStatePlan(ip_m, fk_m, "matrix")
ip = (m.get("in_progress") or "").strip() or None   # ← nivel ROL
fk = (m.get("next_state_ok") or "").strip() or None # ← lo que escribió el operador
if ip is None and fk is None:
    return TaskStatePlan(None, None, "absent")
return TaskStatePlan(ip, fk, "config")              # ← "config", NO "matrix"
```

Lo que el operador configuró produce `source="config"`, y `completion_state.py:90` lo descarta.

**(d) El propio código lo admite y nadie lo cerró.** `config.py:1401-1403` dice textualmente: *"NO-OP hasta que el operador configure la matriz (`tracker_state_machine.<rol>.by_work_item_type`) desde la UI"*, y el texto de la flag repite lo mismo (`harness_flags.py:2800-2802`). Pero la UI de "Estados" no ofrece `by_work_item_type`: solo lo hace `ClientProfileEditor.tsx:467-477`, en otro sub-tab (`SettingsPage.tsx:248`, sub `client-profile`), que es el editor crudo del perfil.

**Agravante 1 (`work_item_type` NULL).** Aun con la matriz configurada, si el ticket tiene `work_item_type` en NULL (`models.py:55`, columna nullable), `_matrix_cell` devuelve `{}` (`task_states.py:70-72`) y se cae al mismo skip.

**Agravante 2 (celda parcial) — NUEVO, C13.** Si el operador escribió en `by_work_item_type` **solo** `in_progress` (sin `next_state_ok`), `resolve_task_state_plan` devuelve `source="matrix"` con `final_ok=None` (`task_states.py:107-108`). El motor A entra al camino "matriz", no encuentra estado final, y **el `next_state_ok` de rol queda inalcanzable para siempre**. Es el mismo síntoma. F2 tiene que cubrirlo explícitamente.

### 2.3 CAUSA RAÍZ SECUNDARIA (RC-2) — el motor B ata el cambio de estado al éxito del publish

`services/agent_completion_internal.py:265-278`:

```python
if not effective_target:
    state_result = {"skipped": True, "reason": "not_requested"}
elif final_status == "completed" and not publish_result.get("ok"):
    state_result = {"skipped": True, "reason": "publish_not_ok", ...}
else:
    state_result = _attempt_state_change(...)
```

`publish_result` no es `ok` en cuatro escenarios normales, ninguno de los cuales es un fallo real de publicación:

| Origen | Ancla | ¿Hubo algo que publicar? |
|---|---|---|
| `html_output_path_missing` | `:228-234` | **No** |
| `already_terminal_no_html` | `:228-234` (rama `already_terminal`) | **No** |
| `auto_publish_disabled` | `:236-238` (`_should_auto_publish`, `:389-397`) | **No** |
| `ado_publisher_unavailable` | `:617-626` | **No** |
| `review_mode_hold` (early-return, ni llega al Paso 4) | `:210-224` | **No** (publicación diferida a decisión humana) |

En los cuatro primeros el gate es **espurio**: bloquea la transición "para no dejar un ticket en Done sin comentario publicado" (`:261-263`) cuando nunca hubo comentario que publicar.

### 2.4 CAUSA RAÍZ TERCIARIA (RC-3) — el skip es mudo

`CloseResult.ado_state_change` (`agent_completion_internal.py:50,61,297`) se serializa y se devuelve… y **no lo consume nadie en el frontend**: `grep -rn "ado_state_change" frontend/src` ⇒ **0 hits** (verificado).

> **Corrección de anclaje (C9).** El v1 decía "el único caller que lo expone por HTTP es `api/tickets.py:1520`". **FALSO**: en `:1520` se serializa la variable **local** `state_change_result`, calculada en `:1466-1503` por los motores C y D — no el campo del `CloseResult`. La conclusión (nadie lo mira) se refuerza: `CloseResult.ado_state_change` **no se expone por HTTP en ninguna parte**.

Del lado del motor A, `completion_state._logged` (`:164-191`) escribe una fila `SystemLog action="completion.matrix_transition"` (`:176`) con la razón — pero no hay endpoint ni componente que la muestre.

**Catálogo canónico de razones (27) — C8 + D3.** El v1 listaba 12 en §2.4 y otras 12 distintas en F6 (intersección: 7). El v2 lo unificó en 23 y afirmó que eran **todas** las que el código puede emitir hoy. **No lo eran** (D3):

1. Faltaba `dev_build_gate_no_state`, que **`api/tickets.py:574` emite HOY** (motor C, gate del 210). El v2 lo presentaba como "razón nueva de F2-bis" cuando ya existía.
2. Y sobre todo: la rama de **error** de `_safe_transition` (`harness/task_states.py:180-184`) devuelve `{"ok": False, "to", "error", "type", "phase"}` — **sin `reason`**. El helper de F5 lo traducía a `reason="unknown"`, string que no está ni en `ALL_FINAL_STATE_REASONS` ni en el `.ts`. Resultado: **el único fallo que el operador puede accionar de verdad — la escritura al tablero que devuelve error — era el único que caía fuera del catálogo**, y el test puente de F6 no lo detectaba porque `"unknown"` no está en ninguno de los dos lados. Se cierra con `transition_failed` cableado **en el origen** (F3-bis-3) y verificado por **F9**.

Estas son **todas**, con su ancla:

| # | Razón | Ancla real | Motor |
|---|---|---|---|
| 1 | `ok` | (éxito de `_safe_transition`, `task_states.py:178`) | A/B |
| 2 | `flag_off` | `completion_state.py:50` | A |
| 3 | `not_ok_status` | `completion_state.py:53` | A |
| 4 | `no_ticket` | `completion_state.py:62` | A |
| 5 | `no_ado_id_or_stacky_project` | `completion_state.py:78` | A |
| 6 | `no_matrix_cell` | `completion_state.py:92` (**legacy tras F2**) | A |
| 7 | `no_final_state` | `completion_state.py:96` (**legacy tras F2**) | A |
| 8 | `state_not_applicable` | `completion_state.py:99` | A |
| 9 | `human_moved_out_of_flow` | `completion_state.py:156` | A |
| 10 | `exception` | `completion_state.py:118` | A |
| 11 | `no_config` | **nueva, F1** | A |
| 12 | `no_agent_type` | **nueva, F1** | A |
| 13 | `no_target_or_id` | `task_states.py:162` | A/B |
| 14 | `already_in_state` | `task_states.py:168` | A/B |
| 15 | `no_provider` | `task_states.py:177` | A/B |
| 16 | `not_requested` | `agent_completion_internal.py:266,466` | B |
| 17 | `publish_not_ok` | `agent_completion_internal.py:270` | B |
| 18 | `review_mode_hold` | `agent_completion_internal.py:222-223` | B |
| 19 | `no_ticket_id` | `agent_completion_internal.py:510` | B |
| 20 | `ticket_lookup_failed` | `agent_completion_internal.py:521` | B |
| 21 | `no_ado_id` | `agent_completion_internal.py:524` | B |
| 22 | `ado_client_unavailable` | `agent_completion_internal.py:533` | B |
| 23 | `provider_unavailable` | **nueva, F3** | B |
| 24 | `dev_build_gate_no_state` | `api/tickets.py:574` (**ya existe hoy**, motor C) + **F2-bis** en A | A/C |
| 25 | `already_written_by_other_engine` | **nueva, F2-bis + F3-bis-2** | A/B |
| 26 | `transition_failed` | **nueva, F3-bis-3** — tapa el agujero de `task_states.py:180-184` (**D3**) | A/B |
| 27 | `no_project_context` | **nueva, F3** — ticket sin `stacky_project_name` (**D6**) | B |

> El bug de fondo no es que el ticket no se mueva. Es que **no se mueve y no dice por qué**. Familia "cero fallas mudas" del plan 255.
>
> **Invariante de este plan (D3):** ningún escritor de estado puede devolver un dict cuyo `reason` no esté en `ALL_FINAL_STATE_REASONS`. `"unknown"` **no es una razón**: es la confesión de que el catálogo está incompleto. **F9** lo verifica corriendo, no leyendo.

### 2.5 Hueco de paridad (E-3) — el escritor del motor B es ADO-only

`services/agent_completion_internal.py:526-541`:

```python
try:
    from services.ado_client import AdoClient
except ImportError as exc: ...
try:
    AdoClient().update_work_item_state(int(ado_id), target_state)
```

Sin `tracker_provider`, sin `_safe_transition`, sin guardia de idempotencia, sin guardia de origen. En un proyecto GitLab esto intenta escribir en ADO usando el `iid` de GitLab.

> **Corrección (C1).** El v1 decía que *"el plan 79 nunca censó este call site"* y listaba a `_attempt_state_change` como "tierra de nadie en los planes 79, 208, 216 y 270". El censo del propio v1 era peor: **no vio los motores C ni D**. El docstring *"ÚNICA función que escribe estado"* está en `harness/task_states.py:155` (no `:146`, que es la línea del `def`), y de los **seis** escritores solo A y C lo respetan (D1). Por eso F8 construye un **censo ejecutable** que se **corre antes** de escribirlo.

### 2.6 Hipótesis del deploy — obligatoria de descartar antes de construir (NUEVA, C1)

`backend/harness_defaults.env:33` fuerza `STACKY_DETERMINISTIC_TASK_STATES_ENABLED=false` mientras `config.py:1245-1246` declara `"true"`. Ese archivo es el snapshot que `deployment/build_release.ps1` hornea en cada deploy.

Consecuencia: **en el deploy del operador, el motor C está APAGADO**. Si el operador cerró la incidencia por `PATCH /by-ado/<id>/stacky-status`, el síntoma se explica enteramente por esa línea, y la reparación más barata sería una línea de env — no seis fases.

**Esto NO invalida el plan**, porque el motor A (post-hook) es el camino común de los 3 runtimes y está roto **independientemente** de esa flag. Pero F0 tiene que decirlo con evidencia, no suponerlo. Ver **F0-D**.

### 2.7 Candidatos descartados, con el porqué

| Cand. | Veredicto | Evidencia |
|---|---|---|
| **C-a** | **CONFIRMADO** = RC-2 | `agent_completion_internal.py:267-272` |
| **C-b** (`review_mode_hold`) | **Real pero NO es el caso reportado** | `:210-224` solo dispara con `publish_mode=="review"` (`_resolve_publish_mode`, `:400-416`), opt-in por proyecto y default `auto` (`:405-406`). Se documenta como razón visible en F5; su semántica NO cambia: es HITL deliberado. |
| **C-c** (`target_source="caller"`) | **Real, condicional, NO es la causa** | `:247-248`. Solo aplica si `output_watcher._read_target_state_from_meta` (`:705-729`) encontró `target_ado_state` en `comment.meta.json` (`:406,421`). Precedencia caller > config, explícita en F1. |
| **C-d** (falta `agent_filename`) | **Fragilidad, no causa** | `:355-364`; si falta, cae al fallback `:368-384`, que para `technical` acierta. |
| **C-e** (fallback no determinista) | **Fragilidad real, no causa** | `:373-382` recorre `configs.items()` y devuelve el primero que matchea; con dos archivos técnicos el resultado depende del orden del dict. Se hace determinista en F1. |
| **C-f** (heurística triplicada) | **Duplicación real, NO causó el síntoma** | `agent_completion_internal.py:304-318`, `api/agents.py:1766-1767`, `services/agent_history.py:54-55`. Las tres mapean `"technical" in filename → "technical"` igual. **Fuera de scope** (§6). |
| **C-g** (la UI escribe en otra clave) | **DESCARTADO para `transition_state`** | `api/projects.py:883` escribe `transition_state` en el payload que `project_manager.set_agent_workflow_config` (`:409-422`) guarda en `agent_workflow_configs[<filename>]`, y `get_agent_workflow_config` (`:392-406`) lo lee de ahí. La persistencia es correcta. **CONFIRMADO para `next_state_ok`**: ver RC-1. |
| **C-h** (motor C apagado en deploy) | **PLAUSIBLE, se mide en F0-D** | `harness_defaults.env:33` vs `config.py:1245-1246`. Ver §2.6. |

---

## 3. Principios y guardarraíles (aplican a TODAS las fases)

1. **Diagnóstico antes que fix.** F0 no toca una línea de producción. Escribe el rojo que prueba el bug **y** mide qué motor estaba activo. Ninguna fase posterior se escribe sin ese rojo.
2. **Reparar ≠ inventar.** Este plan solo hace que se aplique lo que el operador **ya configuró**. No inventa estados, no infiere destinos.
3. **Human-in-the-loop innegociable.** `completion_state._origin_guard` (`:121-161`) se conserva intacto. `review_mode_hold` (`:210-224`) se conserva intacto. El **gate de build del plan 210** se conserva y se **extiende** al motor A (F2-bis).
4. **Cero skip mudo.** Toda rama que decida NO cambiar el estado — **incluida la que falla al escribir** — produce una razón **del catálogo de §2.4**, persistida y visible. Un `return {"skipped": True}` sin `reason`, o un `reason` fuera del catálogo (`"unknown"`, `"error"`, `"failed"`), es un **defecto de este plan**, no un detalle. **F9** lo verifica corriendo: hasta el v2 inclusive esta regla se cumplía en la prosa y se violaba en el código (D3).
5. **Paridad de 3 runtimes por construcción.** Codex CLI, Claude Code CLI y Copilot Pro cierran todos por `ticket_status.on_execution_end` (`completion_dispatcher.py:8-10` lo declara literal) y/o por `close_execution_with_publish`. Ninguna fase toca un runner.
6. **Paridad ADO ↔ GitLab — [v6, E23] corregido.** Toda escritura de estado nueva o corregida pasa por `services/tracker_write_router.resolve_state_writer` (`:55`) — el resolver del plan 270, no por `get_tracker_provider` directo (eso es lo que prohíbe el centinela `test_5_centinela_del_residuo_s5` del 270 y lo que el v5 violaba). Nada de `AdoClient()` directo **salvo** en el camino legacy que protege una flag OFF. **[v6, E24] "Paridad" es de RUTEO, no de vocabulario:** GitLab sólo entiende 4 estados lógicos propios (R17); un `next_state_ok` en vocabulario ADO fuera de esos 4 llega al tracker correcto pero con `reason="transition_failed"`, no con éxito.
7. **Backward-compatible.** Con las 4 flags apagadas, el comportamiento es byte-idéntico al de hoy.
8. **Cero trabajo del operador.** Todas las flags nacen **ON**. Ninguna fase agrega un campo, un clic ni una configuración nueva.
9. **Tests por archivo.** Los tests que tocan la DB son flaky bajo pytest con shared-cache (`SQLITE_LOCKED`). **Nunca** correr la suite completa: siempre `pytest <archivo>`, hasta 3 reintentos del mismo archivo.
10. **Todo `test_*.py` nuevo se registra en los DOS scripts** — `backend/scripts/run_harness_tests.sh` (`HARNESS_TEST_FILES`, líneas con dos espacios de indentación y **sin** comillas) **y** `backend/scripts/run_harness_tests.ps1` (`$HarnessTestFiles`, elementos **entre comillas dobles**). Omitir uno deja el meta-test rojo.
11. **Nunca borrar un assert para poner algo en verde.** Si un criterio binario de este plan choca con la realidad, se **detiene la fase y se reporta**; no se relaja el test. (El v1 tenía dos criterios que solo podían "cumplirse" borrando asserts: C3 y C4.)
12. **Intérprete y rutas — CORREGIDO (E10).** El v3 mandaba `backend\.venv\Scripts\python.exe` y hardcodeaba `N:\GIT\RS\STACKY\Stacky\...` en los ~20 comandos. Las dos cosas están mal si se implementa en un worktree, que es como se trabaja hoy (**6 worktrees vivos**, medido con `git worktree list`):
    - En el **árbol principal** existen `backend/.venv` **y** `backend/venv`, los dos reales. En un **worktree NO existe ninguno** (medido: los dos `ls` fallan) ⇒ el comando literal del v3 **no corre** donde se implementa.
    - Regla: **el intérprete del árbol principal por ruta absoluta, el `cwd` en TU árbol.** Declaralo una vez al principio de la sesión y reusalo:
      ```powershell
      $PY = "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\venv\Scripts\python.exe"
      $RAIZ = "<la raíz de TU árbol>"      # p.ej. N:\GIT\RS\STACKY\wt-XXXX
      cd "$RAIZ\Stacky Agents\backend"
      & $PY -m pytest tests/<archivo>.py -q
      ```
      Los comandos de las fases usan `$PY` y rutas **relativas a `$RAIZ`**. Si copiás una ruta absoluta a `...\STACKY\Stacky\...` estás testeando **otro árbol**.
    - **`frontend/node_modules` es un junction al `node_modules` COMPARTIDO del árbol principal, y es de SÓLO LECTURA.** `npx vitest run <archivo>` y `npx tsc --noEmit` funcionan a través del junction sin escribir nada. **PROHIBIDO** `npm install`, `npm ci`, tocar `package.json`, y **prohibido borrar, mover, recrear o "arreglar"** el junction, su destino, o cualquier venv. Si algo ahí parece roto: **no lo toques, detenete y reportalo** (`N:` es un drive mapeado a `C:\desarrollo\...`, así que el mismo directorio se ve por dos rutas y eso **está bien así**).
    - Ninguna fase de este plan puede pedir reinstalar dependencias ni regenerar un baseline de ratchet.

### 3.1 Receta completa de una flag nueva (7 patas — el "patrón triple" es un mito)

| # | Archivo | Qué se agrega |
|---|---|---|
| 1 | `backend/config.py` | `KEY: bool = os.getenv("KEY", "true").lower() in ("1","true","yes")` — copiar el patrón del bloque de `STACKY_ADO_STATE_MATRIX_ENABLED`, que en el commit base está en **`:1419-1420`** (**localizalo con el grep de §3.4, no con este número**). |
| 2 | `backend/services/harness_flags.py` | Un `FlagSpec(key=..., type="bool", default=True, label=..., description=..., group="global", env_only=False)` en `FLAG_REGISTRY`, inmediatamente después del `FlagSpec` de `STACKY_ADO_STATE_MATRIX_ENABLED` (commit base: **`:2853-2866`**; localizalo con §3.4). **NO declares `requires=`** — ver la nota de la pata 8. |
| 3 | `backend/services/harness_flags.py` | La key en `_CATEGORY_KEYS["flujo_funcional"]`, que **abre en `:272`** (`:268-270` son keys del plan 267). Sin esto, `tests/test_harness_flags.py` queda **rojo**. |
| 4 | `backend/services/harness_flags_help.py` | Un `PlainHelp(what=..., on_effect=..., off_effect=..., example=...)`. **Restricciones duras REALES** (`tests/test_harness_flags_help.py:44-52` y `:63-76`): `what` entre **10 y 200** chars; `on_effect`/`off_effect` ≤ **240** y deben empezar con `"Si "` (`:59-60`); `example` ≤ **300**; ningún campo vacío; **sin** las palabras de `JARGON_DENYLIST` (`:17-20`: MCP, TF-IDF, LLM, stdin, stdout, endpoint, frontmatter, prompt, token, regex, backend, frontend, gate, hook, runtime) — el match es **case-insensitive, por palabra completa y con plural opcional** (`\b<term>s?\b`); **sin** identificadores `SCREAMING_SNAKE` (`_KEY_RE`, `:22`) y **sin** referencias a fases tipo `F1` (`_PHASE_RE`, `:23`). Los 4 textos ya escritos y medidos están en §3.1bis. |
| 5 | `backend/harness_defaults.env` | Línea `KEY=true`, en **orden alfabético**. Obligatorio: este archivo es el snapshot que `deployment/build_release.ps1` hornea en cada deploy. Precedente vivo: `harness_defaults.env:33` fuerza `STACKY_DETERMINISTIC_TASK_STATES_ENABLED=false` mientras `config.py:1260-1261` dice `true`. |
| 6 | `backend/tests/test_plan271_flags.py` | Test que afirma que las 4 keys están en `FLAG_REGISTRY` con `default is True`, en `_CATEGORY_KEYS["flujo_funcional"]`, con línea `=true` en `harness_defaults.env`, **y en `PLAIN_HELP` pasando los 5 chequeos aplicados localmente** (E3 — ver §3.3). |
| 7 | `backend/scripts/run_harness_tests.sh` **y** `.ps1` | Registrar todo archivo de test nuevo. |
| 8 | — | **`requires` NO es una pata para este plan, y está verificado.** `test_requires_map_is_frozen` computa `{s.key: s.requires for s in FLAG_REGISTRY if s.requires}`: una flag **sin** `requires` no toca `_REQUIRES_MAP_FROZEN` (hoy **146** entradas) y el archivo sigue en **9 passed** (medido). Las 4 flags del 271 son **independientes entre sí** ⇒ **prohibido agregar una arista `requires` "de paso"**: declararla sin sumarla al mapa congelado deja ese test rojo (le pasó al plan 237, comentado en el propio mapa). |

> **NO tocar `deployment/harness_defaults.env`.** Es un snapshot derivado de un deploy vivo (docstring de `deployment/export_harness_defaults.py:1-21`) y **ya diverge** del versionado. Fuera de scope.

### 3.4 `[ADICIÓN ARQUITECTO]` Anclajes VOLÁTILES: localizalos con el grep, nunca con el número (E1, E2, E8)

**Por qué existe esta tabla.** Tres versiones de este plan se equivocaron con números de línea, y la tercera **corrigió cuatro que estaban bien** (§2.0). La causa está medida: la **costura P0** movió `config.py` ~15 líneas y `harness_flags.py` ~58 (`_REQUIRES_MAP_FROZEN` pasó de 143 a **146**), y el **plan 269 está en vuelo sobre `api/executions.py`** (§5 R15). Cualquier número que este documento dé para esos archivos es una foto fechada. **Antes de cada edición, corré el grep de la fila y usá lo que devuelve.**

| Qué vas a editar | Grep que lo localiza (corrélo desde `<raíz del árbol>/Stacky Agents`) | Valor en `760ac455` (referencia, NO coordenada) |
|---|---|---|
| bloque de flags de estado en `config.py` | `grep -n "STACKY_ADO_STATE_MATRIX_ENABLED" backend/config.py` | `:1419-1420` |
| `STACKY_DETERMINISTIC_TASK_STATES_ENABLED` en `config.py` | `grep -n "STACKY_DETERMINISTIC_TASK_STATES_ENABLED" backend/config.py` | `:1260-1261` |
| flag ajena del 254 en `config.py` | `grep -n "STACKY_UI_OUTCOME_REASON_BADGE_ENABLED" backend/config.py` | `:2085-2086` |
| `FlagSpec` vecino en `harness_flags.py` | `grep -n "STACKY_ADO_STATE_MATRIX_ENABLED" backend/services/harness_flags.py` | `:2853-2866` |
| categoría `flujo_funcional` | `grep -n '"flujo_funcional"' backend/services/harness_flags.py` | abre en `:272` |
| `_with_outcome` y su corte de flag | `grep -n "def _with_outcome\|def _outcome_badge_enabled\|if not _outcome_badge_enabled" backend/api/executions.py` | `:65` / `:28` / `:75` |
| encolado del motor A | `grep -n "ticket_status.on_execution_end" backend/services/agent_completion_internal.py` | `:183` |
| `return` de `publish_execution_from_review` | `grep -n "def publish_execution_from_review" backend/services/agent_completion_internal.py` y leé hasta su `return` | `def :434`, `return :493` |
| bloque a reemplazar en el motor A | `grep -n "no_matrix_cell\|no_final_state\|state_not_applicable" backend/services/completion_state.py` | `:92` / `:96` / `:99` |
| **[v5, E21] Motores D/E/F en `tickets.py`** | `grep -n "def set_stacky_status_by_ado\|def finish_work\|def create_child_task" backend/api/tickets.py` | `:1205` / `:1751` / `:4080` — **YA desfasados dos de tres: `finish_work` real hoy `:1780`, `create_child_task` real hoy `:4157` (medido, `git diff 760ac455..HEAD` +109 líneas en este archivo)** |
| **[v5, E21] escritor GitLab** | `grep -n "def update_item_state" backend/services/gitlab_provider.py` | `:228` — **real hoy `:243`** (medido, +36 líneas en este archivo desde `760ac455`) |

> **Regla dura:** si el grep devuelve un número distinto al de la columna de referencia, **el grep gana** y no hay nada que reportar (es lo esperado). Si el grep devuelve **0 hits**, ahí sí: **se detiene la fase y se reporta** — significa que alguien renombró el símbolo y el plan hay que re-anclar.
>
> **[v5] Por qué estas dos filas faltaban y por qué importa igual sin que este plan edite esos archivos.** `api/tickets.py` y `services/gitlab_provider.py` son, medido, los DOS archivos que más se movieron desde `760ac455` (E21) — más que `api/executions.py`, que sí tenía su fila. Ninguna fase de este plan los edita (§6 punto 6), así que el número no es una coordenada de edición, pero SÍ es la evidencia que F8 pega en el PR (§F8, "Salida REAL") y la que sostiene §2.1/§2.1bis: si se cita de memoria en vez de re-grepear, el PR queda con una foto vieja disfrazada de medición fresca — la misma trampa D1/E6 en otra puerta.

### 3.5 `[ADICIÓN ARQUITECTO v5]` Antes de editar una función compartida: grep de ratchets de OTROS planes ya mergeados (E20)

**Por qué existe.** F3 edita `agent_completion_internal.py::_attempt_state_change`. Esa función tiene, hoy, un **dueño declarado por otro plan**: `test_plan270_state_write_ratchet.py::test_5_centinela_del_residuo_s5` (plan 270, ya mergeado) la vigila por AST y **espera** que este plan la toque de una forma específica. Nadie en el v1..v4 lo encontró porque los cuatro buscaron colisiones **leyendo el propio documento del plan vecino** (R10 lo hizo con el 270 y midió "0 hits" — cierto en su momento, falso hoy). El chequeo que sí lo encuentra es preguntarle a la **suite de tests**, no al documento.

**Regla, para esta fase y para cualquier plan futuro que edite una función que ya existía antes del plan:**
1. Antes de escribir el diff de una función compartida (cualquier `def` que no crea este plan), correr: `grep -rln "<nombre_de_la_función>" backend/tests/` y abrir cada archivo de test que no sea de este plan.
2. Si alguno hace `ast.parse` / `inspect.getsource` / import directo de esa función y **afirma algo sobre su contenido** (una ausencia, un conteo, una firma), tratarlo como una **API implícita entre planes**: declararlo en el CHANGELOG, decidir si el test debe actualizarse o si el plan debe cambiar de forma, y nunca dejar que se rompa "de sorpresa" en CI.
3. **Aplicado acá — [v6, E23] corregido.** `grep -rln "_attempt_state_change" backend/tests/` incluye `test_plan270_state_write_ratchet.py`. **La v5 leía el paso 2 de esta regla como "editar el test que afirma algo"; acá el test afirma una AUSENCIA (que la función no referencia ciertos nombres), y esa ausencia SIGUE SIENDO CIERTA si el diff rutea por `resolve_state_writer` en vez de `get_tracker_provider` directo (F3, F3-bis-0).** La API implícita entre planes se resuelve **cumpliéndola**, no editándola: `test_5` se corre tal cual antes y después del diff de F3 y debe seguir en verde sin cambios. Editar el test sólo estaría justificado si, tras intentar la ruta del router, quedara demostrado que es imposible (no es el caso acá) — y en ese escenario la edición se declara en el CHANGELOG como una excepción explícita, nunca como el camino por defecto.

### 3.6 `[ADICIÓN ARQUITECTO v6]` Ningún escritor multi-tracker se declara "soportado" sin probar el vocabulario real (E24)

**Por qué existe.** E24 se coló porque los 10 casos de `test_plan271_writer_routed.py` (v5) prueban **ruteo** (¿se llamó al proveedor correcto?) con un `FakeProvider` que acepta cualquier string como estado válido — nunca prueban que ese string **sobreviva** al vocabulario real del tracker resuelto. Un doble más permisivo que la implementación real disfraza justo el defecto que había que atrapar.

**Regla, para esta fase y para cualquier plan futuro que agregue o rutee una escritura hacia más de un tracker/proveedor:**
1. Si el plan agrega o rutea una llamada a `provider.update_item_state(...)` / `update_work_item_state(...)` hacia un proveedor que **no es ADO** (GitLab hoy; el que siga mañana), identificar el vocabulario que ese proveedor REALMENTE acepta (para GitLab: `GitLabTrackerProvider._state_map_for_gitlab().keys()`, hoy `functional`/`accepted`/`rejected`/`in_progress`).
2. Escribir al menos **un caso de test con el valor FUERA de ese vocabulario** (no sólo el camino feliz con un valor que el doble acepta ciegamente), y afirmar que el resultado es una razón visible del catálogo (`transition_failed` u otra ya existente) — **nunca** una excepción sin capturar, **nunca** un éxito falso, **nunca** un `skipped` mudo.
3. Si el vocabulario de origen (lo que el operador puede configurar) puede no coincidir con el vocabulario de destino en la mayoría de los casos reales — no sólo en un borde raro —, **no se declara "paridad" en el KPI (§1) sin la salvedad medida**, y el gap se registra como riesgo (patrón R17) en vez de asumir que "rutear bien" ya es "funcionar bien".
4. **Aplicado acá:** caso 11 de `test_plan271_writer_routed.py` (E24) y la salvedad de §1/R17.

### 3.7 `[ADICIÓN ARQUITECTO v7]` Todo ratchet compartido de frontend se reglobea y se mide, nunca se enumera de una lista fija (E27)

**Por qué existe.** El v6 nombraba, en la sección F6 y en la DoD, "los 8 ratchets de UI" con sus 8 nombres literales — la misma clase de foto fija que §3.4 ya prohíbe para los anclajes de backend, aplicada sin querer al frontend. Medido para esta crítica: hoy hay **9** archivos `*Ratchet*.test.ts` en `frontend/src/__tests__/`, no 8; el plan 267 agregó `devopsActionCatalogRatchet.test.ts` después de que la lista de este documento se escribiera, y ninguna versión anterior lo notó porque nadie volvió a correr el glob — confiaron en la lista. Un noveno ratchet nombrado "para que nadie lo busque a ojo" es exactamente lo contrario de la disciplina que corresponde: un ratchet nuevo que aparece entre versiones no es un caso raro, es el patrón normal de un repo con planes hermanos en paralelo (mismo fenómeno que `docs/sistema/error_fingerprints.json`, que crece entre hermanos, o que `_REQUIRES_MAP_FROZEN`, que pasó de 143 a 146 por la costura P0).

**Regla, para esta fase y para cualquier plan futuro que declare un criterio de aceptación sobre "los ratchets de frontend":**
1. **Nunca** copiar una lista de nombres de una versión anterior del plan. Reglobear con `Get-ChildItem frontend/src/__tests__/*Ratchet*.test.ts` (o `ls` equivalente) el día de la implementación, y usar esa salida.
2. **Nunca** afirmar "siguen verdes" sin haber corrido cada uno individualmente ese mismo día. Si alguno está rojo, verificar con un worktree en el commit base si la deuda es ajena (patrón §3.3) antes de asumir que la tocaste vos.
3. El criterio de aceptación de cualquier fase que edite `frontend/src/` nunca es "N ratchets en verde": es **delta** — ningún archivo que la fase haya tocado aparece nombrado como ofensor nuevo en el mensaje de error de ninguno de ellos.
4. **Aplicado acá:** la sección F6 y la DoD (§7.3) de este mismo documento, corregidas (E27): 9 nombres, no 8, y el baseline real (rojo) de `uiDebtRatchet` declarado en vez de asumido verde.

### 3.1bis Los CUATRO textos de ayuda llana, escritos y medidos (D5)

**Por qué están acá y no "cablealos en tu fase":** `test_harness_flags_help.py:32-35` (`test_plain_help_covers_all_registry_keys`) exige un `PlainHelp` para **toda** key de `FLAG_REGISTRY`. El v2 escribía **uno solo** y dejaba tres a criterio del implementador, con una denylist que incluye literalmente **`gate`**, `hook`, `runtime`, `endpoint`, `backend`, `frontend`, `token`, `prompt` — y una flag que se llama `..._PUBLISH_GATE_PRECISE_ENABLED`. Escribir "el gate de publicación" ahí deja el test rojo, y §3-11 prohíbe relajarlo. Los cuatro van **literales**, ya medidos.

```python
"STACKY_FINAL_STATE_ROLE_FALLBACK_ENABLED": PlainHelp(
    what="Hace que el estado al que configuraste que pase la incidencia cuando el empleado termina se aplique de verdad.",
    on_effect="Si la activás: al terminar el empleado, la incidencia pasa al estado que elegiste en la pantalla de Estados.",
    off_effect="Si la apagás: la incidencia se queda en el estado en que estaba y la tenés que mover a mano.",
    example="Como que el trámite avance solo de ventanilla cuando el funcionario lo termina, en vez de quedarse en el mostrador.",
),
"STACKY_FINAL_STATE_WRITER_ROUTED_ENABLED": PlainHelp(
    what="Escribe el nuevo estado en el tablero que ese proyecto declara, en vez de escribirlo siempre en el mismo.",
    on_effect="Si la activás: cada proyecto mueve sus incidencias en su propio tablero.",
    off_effect="Si la apagás: todos los proyectos intentan mover la incidencia en el tablero de siempre, aunque no sea el suyo.",
    example="Como mandar la carta a la sucursal del cliente y no siempre a la casa central.",
),
"STACKY_FINAL_STATE_PUBLISH_GATE_PRECISE_ENABLED": PlainHelp(
    what="Deja de frenar el cambio de estado cuando no había ningún comentario para publicar.",
    on_effect="Si la activás: si no hubo nada que publicar, la incidencia igual pasa al estado que configuraste.",
    off_effect="Si la apagás: cualquier publicación que no salga bien frena el cambio de estado, aunque no hubiera nada para publicar.",
    example="Como no retener un expediente por falta de adjunto cuando ese trámite nunca llevaba adjunto.",
),
"STACKY_FINAL_STATE_REASON_VISIBLE_ENABLED": PlainHelp(
    what="Muestra en el detalle de la corrida por qué la incidencia se movió, o por qué no se movió.",
    on_effect="Si la activás: al abrir la corrida ves en castellano el motivo y qué hacer al respecto.",
    off_effect="Si la apagás: no ves ningún motivo y tenés que revisar los registros a mano.",
    example="Como el cartel de la ventanilla que dice por qué te rechazaron el trámite en vez de mandarte a preguntar.",
),
```

**Medición campo por campo — CORRIDA de verdad esta vez (E13).** El v3 decía "hecha, no estimada" y daba cuatro números que **no coinciden** con sus propios textos (decía `what`=113, `on_effect`=116, `off_effect`=104, `example`=121 para la primera flag; los reales son **110 / 108 / 92 / 115**). Los cuatro textos **pasan igual** los cinco chequeos, así que el veredicto era correcto y los números no. Estos son los reales, ejecutando los mismos asserts del test:

| Flag | `what` | `on_effect` | `off_effect` | `example` | `"Si "` | jerga / `_KEY_RE` / `_PHASE_RE` |
|---|---|---|---|---|---|---|
| `..._ROLE_FALLBACK_ENABLED` | 110 | 108 | 92 | 115 | ✔ ✔ | limpio |
| `..._WRITER_ROUTED_ENABLED` | 105 | 72 | 111 | 78 | ✔ ✔ | limpio |
| `..._PUBLISH_GATE_PRECISE_ENABLED` | 83 | 97 | 118 | 92 | ✔ ✔ | limpio |
| `..._REASON_VISIBLE_ENABLED` | 90 | 87 | 76 | 105 | ✔ ✔ | limpio |

Límites: `what` 10..200, `on_effect`/`off_effect` ≤240 y empezando con `"Si "` (`test_harness_flags_help.py:59-60`), `example` ≤300. Ningún campo vacío. Ninguno contiene una palabra de `JARGON_DENYLIST` (`:17-20`, match con **plural opcional**) — nótese que se dice *"pantalla de Estados"*, *"tablero"* y *"frenar el cambio de estado"* precisamente para no escribir `gate`, `endpoint` ni `runtime`. Ninguno matchea `_KEY_RE` (`:22`) ni `_PHASE_RE` (`:23`).

> **Prohibido parafrasear estos textos.** Si hay que cambiarlos, se vuelven a medir contra `test_harness_flags_help.py:44-52,59-60,63-76` **antes** de commitear. Y ojo: el gate que los verifica **no es el conteo global del archivo** — es la aserción local de `test_plan271_flags.py` (§3.3, E3).

### 3.3 `[ADICIÓN ARQUITECTO]` Baseline MEDIDO de rojos ajenos (D4, D13)

El v2 repetía en cada fase *"si ya venía rojo, probalo con un worktree y declaralo"*. Eso es correcto pero **inservible sin números**: un modelo menor no sabe qué es "ya venía rojo". Estos son los conteos **corridos hoy** con `& $PY -m pytest tests/<archivo> -q` desde `$RAIZ\Stacky Agents\backend` (§3-12), por archivo:

| Archivo | Baseline REAL hoy | Qué significa para este plan |
|---|---|---|
| `test_harness_flags.py` | **56 passed** | Verde. Cualquier rojo tras tus cambios **es tuyo**. |
| `test_harness_flags_help.py` | **4 failed, 4 passed** | **Rojo ajeno — pero el conteo NO sirve como criterio. Ver §3.3bis (E3).** |
| `test_plan210_state_gate.py` | **16 passed** | Verde. F2-bis no puede romperlo. |
| `test_u2_publish_review_mode.py` | **3 passed** | Verde. |
| `test_plan79_apply_final.py` | **6 passed** | Verde. |
| `test_plan79_centinela_estados.py` | **5 passed** | Verde. |
| `test_output_watcher.py` | **30 passed** | Verde. D6: F3 **no** lo toca; tiene que seguir en 30. |
| `test_plan79_safe_transition.py` | **10 passed** | Verde. Es el dueño de la función que toca F3-bis-3. |
| `test_harness_flags_requires.py` | **9 passed** | Verde. Sigue verde **si y sólo si** no declarás `requires=` (§3.1 pata 8). |
| `test_error_fingerprints_catalog.py` | **3 failed, 5 passed** | **Rojo ajeno NO declarado por el v3, y el DoD escribe en ese archivo.** Fallan `test_campos_obligatorios` (la huella `PLAN239-OUTLET-EN-BLANCO` no tiene `self_test`), `test_status_enum` (`'guarded'` no está en `{by_design, open, resolved}`) y `test_self_test_coherente` (KeyError). **Arreglar la huella del 239 es fuera de scope (§6.12);** tus 2 huellas tienen que estar **bien formadas** (F7, E5). |
| `test_error_fingerprints_scan.py` | **2 failed, 7 passed** | **Rojo ajeno**, misma causa (`test_scan_log_limpio`, `test_scan_multiple`, KeyError por la huella del 239). |
| `test_b2_transition_from_config.py` | **5 failed** — `TypeError: _resolve_transition_state_from_config() missing 1 required keyword-only argument: 'final_status'` | **Rojo ajeno que ESTE plan arregla** (F4-bis), porque F7 lo adopta al arnés y un rojo registrado deja el arnés rojo. |

> **Regla:** "ya estaba rojo" deja de ser una excusa y pasa a ser una **comparación contra esta tabla**. Si tu conteo difiere del de acá, es tuyo hasta que pruebes lo contrario con un worktree en el commit base.

### 3.3bis `[ADICIÓN ARQUITECTO]` El gate corrido CONTRA el defecto: por qué "4 failed, 4 passed" era un falso verde (E3)

**El v3 construyó todo D5 sobre un criterio que no distingue nada.** Medido:

- `FLAG_REGISTRY` tiene **403** keys. `PLAIN_HELP` tiene **324**. Hay **79 flags sin ayuda llana HOY** (entre ellas `STACKY_ADO_STATE_MATRIX_ENABLED`, la del motor A).
- `test_plain_help_covers_all_registry_keys` (`:32-35`) es **UN** test cuyo assert es `missing == []`. Con 79 faltantes ya está rojo. Agregarle las 4 keys del 271 **sin** `PlainHelp` lo deja con 83 faltantes: **sigue siendo 1 test rojo**. El conteo del archivo **no se mueve**: `4 failed, 4 passed` en los dos escenarios.
- **Conclusión:** el criterio del v3 se cumple **exactamente igual** si escribís los 4 textos o si no escribís ninguno. Es el mismo falso verde que el plan 270 (15 casos que daban 15 passed también con la implementación prohibida).
- La salvaguarda que el v3 agregó ("ninguna key `STACKY_FINAL_STATE_*` en la lista de **violaciones**") tampoco alcanza: `violations` es el mensaje del test de **jerga** (`:76`). La ausencia de `PlainHelp` sale en `missing` (`:35`) — **otro test, otra lista**. La guardia era ciega justo en el eje que D5 quería cubrir.
- Y los 4 fallos estaban **mal caracterizados**: el v3 describía sólo el de jerga. Los cuatro reales, medidos, son: **(1)** `test_plain_help_covers_all_registry_keys` → 79 keys sin ayuda; **(2)** `test_plain_help_fields_non_empty_and_bounded` → `STACKY_DEVOPS_COCKPIT_ENABLED: on_effect 316 > 240`; **(3)** `test_plain_help_on_off_start_with_si` → `STACKY_EGRESS_SENTINEL_MAX_CHARS: off_effect no empieza con "Si "`; **(4)** `test_plain_help_avoids_jargon_denylist` → `STACKY_PLANS_BOARD_ENABLED` (cita una key), `STACKY_CODE_INTEGRITY_ENABLED` (`backend`, `endpoint`, `gate`), `STACKY_EVOLUTION_*` y `STACKY_EVAL_*` (`prompt`, `token`).

**El criterio que SÍ discrimina — va en `test_plan271_flags.py`, autocontenido, sin depender de un archivo globalmente rojo:**

```python
# backend/tests/test_plan271_flags.py — el gate de la ayuda llana de ESTE plan.
# E3: NO se mide el conteo de test_harness_flags_help.py (que ya está rojo por 79
# faltantes ajenos y no cambia de color si omitís las tuyas). Se afirma pertenencia
# y se aplican los MISMOS cinco chequeos, acotados a las 4 keys del 271.
import re

_PLAN271_KEYS = (
    "STACKY_FINAL_STATE_ROLE_FALLBACK_ENABLED",
    "STACKY_FINAL_STATE_WRITER_ROUTED_ENABLED",
    "STACKY_FINAL_STATE_PUBLISH_GATE_PRECISE_ENABLED",
    "STACKY_FINAL_STATE_REASON_VISIBLE_ENABLED",
)


def test_las_4_keys_tienen_ayuda_llana_y_pasan_los_cinco_chequeos():
    from services.harness_flags_help import PLAIN_HELP
    from tests.test_harness_flags_help import JARGON_DENYLIST, _KEY_RE, _PHASE_RE

    faltan = [k for k in _PLAN271_KEYS if k not in PLAIN_HELP]
    assert faltan == [], f"flags del 271 sin ayuda llana: {faltan}"

    for key in _PLAN271_KEYS:
        e = PLAIN_HELP[key]
        assert 10 <= len(e.what.strip()) and len(e.what) <= 200, f"{key}: what fuera de 10..200"
        for campo in ("on_effect", "off_effect"):
            v = getattr(e, campo)
            assert len(v) <= 240, f"{key}: {campo} > 240"
            assert v.startswith("Si "), f"{key}: {campo} no empieza con 'Si '"
        assert len(e.example) <= 300, f"{key}: example > 300"
        for campo in ("what", "on_effect", "off_effect", "example"):
            v = getattr(e, campo)
            assert v.strip(), f"{key}: {campo} vacío"
            for term in JARGON_DENYLIST:
                assert not re.search(rf"\b{re.escape(term)}s?\b", v, re.IGNORECASE), \
                    f"{key}.{campo}: jerga prohibida '{term}'"
            assert not _KEY_RE.search(v), f"{key}.{campo}: cita una key SCREAMING_SNAKE"
            assert not _PHASE_RE.search(v), f"{key}.{campo}: referencia a fase F<n>"
```

> **Verificación de que el gate es discriminante (obligatoria, una vez):** borrá **una** de las 4 entradas de `PLAIN_HELP` y corré `test_plan271_flags.py`: **tiene que ponerse ROJO**. Volvela a poner. Pegá las dos salidas en el PR. Un gate que no viste rojo ante el defecto que dice atrapar **no cuenta como gate**.
>
> **Y el criterio sobre el archivo compartido pasa a ser una aserción sobre los DOS mensajes, no sobre el conteo:** ninguna key `STACKY_FINAL_STATE_*` puede aparecer **ni en `missing`** (`:35`) **ni en `violations`** (`:76`). El conteo `4 failed, 4 passed` sigue siendo un dato de contexto, no el criterio.

### 3.2 Las 4 flags de este plan y su default

| Flag | Fases | Default | Justificación de la categoría |
|---|---|---|---|
| `STACKY_FINAL_STATE_ROLE_FALLBACK_ENABLED` | F1, F2, F2-bis | **ON** | Repara lo ya configurado. El operador tipeó `To Do` en `StatesConfigPage.tsx:196-202`, en una pantalla que le prometió *"a cuál mueve el ticket al terminar"*. Aplicarlo no es una escritura nueva: es cumplir la promesa. Dejarla OFF **dejaría el bug vivo**, que es lo que la regla de flags prohíbe. |
| `STACKY_FINAL_STATE_WRITER_ROUTED_ENABLED` | F3 | **ON** | Corrige el **destino** de una escritura que ya ocurre, no agrega escrituras. Hoy `agent_completion_internal.py:536` escribe siempre en ADO; con la flag ON escribe en el tracker que el proyecto declara. En un proyecto ADO el comportamiento es idéntico; en uno GitLab deja de escribir en el lugar equivocado. |
| `STACKY_FINAL_STATE_PUBLISH_GATE_PRECISE_ENABLED` | F4 | **ON** | *El único caso que roza la categoría (B) y merece precisión.* Con la flag ON, Stacky transiciona tickets que hoy no transiciona ⇒ **sí produce escrituras nuevas en el sistema real del operador**. Va **ON igual**, porque: (i) el estado destino salió íntegramente de la config del operador, no de una inferencia; (ii) el gate que se afina nunca fue una decisión del operador sino una heurística interna documentada en `:261-263`; (iii) se afina **solo** para los cuatro casos en que no había nada que publicar — el caso en que la publicación **se intentó y falló** (`event == "publish.failed"`), el `publish.idempotent_replay` y el `review_mode_hold` **conservan el gate**. La parte que podría dejar un ticket cerrado sin evidencia sigue bloqueada. |
| `STACKY_FINAL_STATE_REASON_VISIBLE_ENABLED` | F5, F6 | **ON** | Solo lectura: persiste y muestra una razón que ya se calcula. No escribe en ningún sistema del operador. Solo-lectura nunca es excepción. |

**Ninguna flag de este plan nace OFF.** No aplica la categoría (A) — no hay loop, daemon nuevo, barrido, polling ni llamada a modelo en reposo — ni (B) en su forma pura, por lo argumentado arriba.

> **F2-bis, F3-bis, F4-bis, F8 y F9 no llevan flag propia.** Las guardias del árbitro solo pueden **reducir** escrituras (nunca agregarlas) y van cableadas dentro de los caminos que ya protegen `STACKY_FINAL_STATE_ROLE_FALLBACK_ENABLED` y `STACKY_FINAL_STATE_WRITER_ROUTED_ENABLED`. F3-bis-3 agrega una key a un dict que hoy nadie lee (backward-compatible por construcción). F4-bis arregla un test. F8 y F9 son tests.

---

## 4. Fases

### F0 — Caracterización: el rojo que prueba el bug + medición del motor activo

**Objetivo (1 frase):** dejar escrito, en tests que hoy fallan, el comportamiento que el operador espera, y **medir** cuál de los seis motores estaba activo en el deploy.
**Valor:** ninguna fase posterior puede escribirse "de fe". Si F0 pasa en verde antes de tocar producción, el diagnóstico está mal.

**Archivos a crear:**
- `backend/tests/test_plan271_caracterizacion.py`
- `backend/tests/plan271_helpers.py` — **los helpers son parte del plan, no "los escribís vos"** (C15).

**Archivos a editar:** los dos scripts de arnés (§3-10).

#### F0-A — helpers exactos (`backend/tests/plan271_helpers.py`)

**Por qué un módulo aparte:** los cuatro tests y las fases F2/F4/F5 los reusan. **No toques `conftest.py`.**

**Contrato exacto de `plan271_helpers.py` (implementalo literal):**

```python
"""Plan 271 — dobles compartidos. Sin red, sin ADO real, sin GitLab real."""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class FakeProvider:
    """Doble de TrackerProvider. Registra escrituras; get_item devuelve el estado
    que le sembrés (o {} para simular 'no se pudo leer')."""

    def __init__(self, current_state: str | None = None):
        self.current_state = current_state
        self.writes: list[tuple[str, str]] = []

    def get_item(self, item_id: str) -> dict:
        return {"state": self.current_state} if self.current_state else {}

    def update_item_state(self, item_id: str, logical_state: str) -> dict:
        self.writes.append((str(item_id), logical_state))
        return {"ok": True}


class _FakeTicket:
    def __init__(self, ado_id, project, work_item_type):
        self.ado_id = ado_id
        self.stacky_project_name = project
        self.work_item_type = work_item_type


class _FakeSession:
    def __init__(self, ticket):
        self._t = ticket

    def get(self, _model, _pk):
        return self._t


def patch_motor_a(monkeypatch, *, profile: dict, ado_id=4242, project="P271",
                  work_item_type=None, provider: FakeProvider | None = None):
    """Parchea TODO lo que `completion_state.maybe_apply_state_transition` importa
    DENTRO de la función. Ojo: son imports locales, así que hay que parchear el
    MÓDULO ORIGEN, no `completion_state`.

    Parchea exactamente:
      - db.session_scope                                   (completion_state.py:56)
      - services.client_profile.load_effective_client_profile   (:85)
      - services.tracker_provider.get_tracker_provider          (:101)
      - services.completion_dispatcher.emit_completion_log      (:171)  -> no-op
    Devuelve el FakeProvider usado (para inspeccionar `.writes`).
    """
    import contextlib
    import db as _db
    import services.client_profile as _cp
    import services.completion_dispatcher as _cd
    import services.tracker_provider as _tp

    prov = provider if provider is not None else FakeProvider()
    ticket = _FakeTicket(ado_id, project, work_item_type)

    @contextlib.contextmanager
    def _scope(*_a, **_k):
        yield _FakeSession(ticket)

    monkeypatch.setattr(_db, "session_scope", _scope)
    monkeypatch.setattr(_cp, "load_effective_client_profile", lambda *_a, **_k: profile)
    monkeypatch.setattr(_tp, "get_tracker_provider", lambda *_a, **_k: prov)
    monkeypatch.setattr(_cd, "emit_completion_log", lambda **_k: None)
    return prov


def close_sin_html(monkeypatch, *, transition_state: str = "To Do"):
    """Llama close_execution_with_publish con html_output_path=None y
    final_status='completed', con la execution+ticket ya sembrados por el caller.

    `agent_completion_internal` resuelve sus helpers POR ATRIBUTO DE MÓDULO, así
    que acá sí se parchea el propio módulo (al revés que en patch_motor_a).
    Modelalo sobre `backend/tests/test_u2_publish_review_mode.py:150-162`, que ya
    siembra la execution con el mismo patrón. Devuelve el CloseResult.
    """
    import services.agent_completion_internal as aci

    monkeypatch.setattr(aci, "_resolve_transition_state_from_config",
                        lambda **_k: transition_state)
    execution_id, ticket_id = _seed_execution_y_ticket()
    return aci.close_execution_with_publish(
        execution_id=execution_id, ticket_id=ticket_id,
        final_status="completed", html_output_path=None,
    )


def _seed_execution_y_ticket() -> tuple[int, int]:
    """Siembra un Ticket (con `stacky_project_name` seteado — sin él, F3 cae al
    camino legacy, ver D6) y una AgentExecution 'running'. Devuelve (exec, ticket).
    Copiá el patrón exacto de `test_u2_publish_review_mode.py:150-162`; lo único
    que NO se puede omitir es `stacky_project_name`."""
    from db import session_scope
    from models import AgentExecution, Ticket

    with session_scope() as s:
        t = Ticket(ado_id=4242, project="P271", stacky_project_name="P271",
                   title="t-271", ado_state="New", stacky_status="running")
        s.add(t)
        s.flush()
        e = AgentExecution(ticket_id=t.id, agent_type="technical", status="running")
        s.add(e)
        s.flush()
        return e.id, t.id
```

> **D12 — por qué ya no hay `...` en este bloque.** El v1 dejaba los helpers a criterio del implementador (C15). El v2 "lo corrigió" dando **firma + docstring y cuerpo `...`**, y a la vez mandaba *"implementalo literal"*: no se puede implementar literalmente un `...`. Ahora los cuerpos están. La única parte que sigue siendo un puntero es el sembrado, y va con la **restricción que importa escrita aparte** (`stacky_project_name` no es opcional).

> **Detalle que un modelo menor no puede inferir y por eso está escrito:** `completion_state.maybe_apply_state_transition` hace todos sus imports **dentro** de la función (`:56-57`, `:80-85`, `:101`). `monkeypatch.setattr(completion_state, "get_tracker_provider", ...)` **no hace nada**. Hay que parchear `services.tracker_provider.get_tracker_provider`. En cambio `agent_completion_internal` llama a sus helpers por atributo de módulo, así que ahí sí se parchea el propio módulo.

#### F0-B — los 4 tests de caracterización

```python
# backend/tests/test_plan271_caracterizacion.py
"""Plan 271 F0 — Caracterización del bug reportado.

Describen el comportamiento ESPERADO por el operador. Al escribirlos (antes de
F1..F8) DEBEN FALLAR LOS CUATRO. Si alguno pasa en verde acá, el diagnóstico del
plan está equivocado y hay que rehacerlo antes de tocar producción.
"""
from __future__ import annotations
import inspect

from tests.plan271_helpers import FakeProvider, close_sin_html, patch_motor_a


PERFIL_SOLO_ROL = {"tracker_state_machine": {"technical": {
    "input_states": ["New"], "in_progress": "Doing", "next_state_ok": "To Do",
}}}


def test_rc1_rol_sin_matriz_deberia_transicionar(monkeypatch):
    """RC-1: el operador configuró tracker_state_machine.technical.next_state_ok
    = 'To Do' desde StatesConfigPage (nivel ROL, sin by_work_item_type).
    Hoy completion_state devuelve skipped/no_matrix_cell. Debe transicionar."""
    from services import completion_state
    prov = patch_motor_a(monkeypatch, profile=PERFIL_SOLO_ROL, work_item_type=None)
    out = completion_state.maybe_apply_state_transition(
        {"ticket_id": 1, "execution_id": 9, "final_status": "completed",
         "agent_type": "technical"}
    )
    assert out.get("ok") is True, f"esperaba transición, obtuve {out}"
    assert out.get("to") == "To Do"
    assert prov.writes == [("4242", "To Do")]


def test_rc1_celda_parcial_no_debe_enterrar_el_nivel_rol(monkeypatch):
    """RC-1 agravante 2: by_work_item_type['Bug'] con SOLO in_progress hace que
    resolve_task_state_plan devuelva source='matrix' y final_ok=None
    (task_states.py:107-108). El next_state_ok de rol queda inalcanzable."""
    from services import completion_state
    perfil = {"tracker_state_machine": {"technical": {
        "next_state_ok": "To Do",
        "by_work_item_type": {"Bug": {"in_progress": "Doing"}},
    }}}
    prov = patch_motor_a(monkeypatch, profile=perfil, work_item_type="Bug")
    out = completion_state.maybe_apply_state_transition(
        {"ticket_id": 1, "execution_id": 9, "final_status": "completed",
         "agent_type": "technical"}
    )
    assert out.get("ok") is True, f"la celda parcial enterró el nivel rol: {out}"
    assert prov.writes == [("4242", "To Do")]


def test_rc2_sin_html_no_debe_bloquear_la_transicion(monkeypatch):
    """RC-2: cierre completed sin html_output_path (nada que publicar) NO debe
    impedir el cambio de estado configurado."""
    res = close_sin_html(monkeypatch, transition_state="To Do")
    assert res.ado_state_change.get("ok") is True, \
        f"publish sin nada que publicar no debe gatear el estado: {res.ado_state_change}"


def test_e3_el_escritor_rutea_por_provider():
    """E-3: _attempt_state_change debe rutear por el router del plan 270 para
    tener paridad ADO/GitLab. Forma POSITIVA a propósito: el camino legacy con
    la flag OFF conserva el import de AdoClient y NO puede prohibirse.

    [v6, E23] Busca `resolve_state_writer`, NO `get_tracker_provider`: ese
    segundo nombre es justo lo que test_5_centinela_del_residuo_s5 del plan 270
    prohíbe dentro de esta función (F3-bis-0). Si esta aserción buscara
    "get_tracker_provider", F0 sólo se pondría verde violando el centinela del
    270 — la misma trampa que E23 encontró en el diff de la v5.
    """
    from services import agent_completion_internal as aci
    src = inspect.getsource(aci._attempt_state_change)
    assert "resolve_state_writer" in src, "el escritor de estado sigue siendo ADO-only"
```

> **Por qué cambiaron dos tests respecto del v1 (C3, C4).**
> - El viejo `test_rc1_razon_del_skip_nunca_es_silenciosa` **nacía verde**: `maybe_apply_state_transition({"final_status": "error"})` devuelve `{"skipped": True, "reason": "not_ok_status"}` (`completion_state.py:52-53`) — o `"flag_off"` (`:50`) —, así que `out.get("reason")` siempre es truthy. Se reemplazó por el caso de **celda parcial**, que sí está rojo y cubre un agujero real.
> - El viejo `test_e3_el_escritor_no_puede_ser_ado_only` prohibía el import de `AdoClient` en todo el archivo, lo que **contradice F3**, que conserva el camino legacy y agrega `_legacy_ado_client()`. Se pasó a forma positiva y acotada a la función con `inspect.getsource`.

#### F0-C — F0 y el DoD: cuándo un test de F0 se vuelve verde

| Test de F0 | Se vuelve VERDE en |
|---|---|
| `test_rc1_rol_sin_matriz_deberia_transicionar` | **F2** |
| `test_rc1_celda_parcial_no_debe_enterrar_el_nivel_rol` | **F2** |
| `test_rc2_sin_html_no_debe_bloquear_la_transicion` | **F4** |
| `test_e3_el_escritor_rutea_por_provider` | **F3** |

#### F0-D — medición del motor activo (5 minutos, sin tocar código)

Corré estos 4 comandos y **pegá la salida en el PR**. No es opcional: decide si el plan sigue completo o se recorta.

```powershell
# 1. ¿El motor C está apagado en el snapshot de deploy?
Select-String -Path "$RAIZ\Stacky Agents\backend\harness_defaults.env" -Pattern "STACKY_DETERMINISTIC_TASK_STATES_ENABLED"
# 2. ¿Y el motor A?
Select-String -Path "$RAIZ\Stacky Agents\backend\harness_defaults.env" -Pattern "STACKY_ADO_STATE_MATRIX_ENABLED"
# 3. ¿Hay .env del operador que pise cualquiera de las dos?
Select-String -Path "$RAIZ\Stacky Agents\backend\.env" -Pattern "STACKY_(DETERMINISTIC_TASK_STATES|ADO_STATE_MATRIX)_ENABLED" -ErrorAction SilentlyContinue
# 4. ¿Qué dicen los SystemLog del motor A en la base viva? SOLO LECTURA, solo reason+conteo (§8-2 punto 4).
#    La ruta de la base VIVA es del deploy del operador y NO depende de tu árbol.
& $PY -c "import sqlite3,sys,glob; p=glob.glob(r'N:\GIT\RS\STACKY\DeployStackyAgents\data\*.db'); print(p); c=sqlite3.connect(p[0]) if p else sys.exit('sin db'); print(list(c.execute(\"select json_extract(context,'$.reason'), count(*) from system_logs where action='completion.matrix_transition' group by 1\")))"
```
> **El comando 4 lee la base VIVA del operador.** Es de sólo lectura y devuelve **únicamente** `reason` y `count(*)`. **Prohibido agregarle columnas** (`title`, `description`, `ado_id`, cualquier campo del ticket): eso sería sacar datos del operador a un PR. Ver §8-2 punto 4.
>
> **Nota de medición ya hecha (v4):** los comandos 1 y 2 ya se corrieron contra el commit base. **(1) devuelve `STACKY_DETERMINISTIC_TASK_STATES_ENABLED=false`** (`harness_defaults.env:33`, verificado) ⇒ **el motor C está apagado en el snapshot de deploy**, tal como §2.6 supone. **(2) no devuelve nada** ⇒ `STACKY_ADO_STATE_MATRIX_ENABLED` está **ausente** de ese archivo y manda el default del código (`true`) ⇒ **el motor A está encendido**. **(3)** en el `.env` del árbol de trabajo: **0 hits**, ninguna de las dos está pisada. Falta sólo **(4)**, la base viva del operador, que depende de su máquina. **Consecuencia ya establecida sin escribir código: el diagnóstico de §2.6 se confirma — el motor C está apagado en deploy y el motor A está encendido y roto ⇒ F1/F2/F2-bis se justifican, y la "reparación de una línea de env" NO alcanza.**

**Interpretación (escribila en el PR, una línea):**
- Si (1) da `=false` **y** el operador cerró por `PATCH /by-ado/<id>/stacky-status` ⇒ el motor C estaba apagado; la reparación mínima sería esa línea, **pero el motor A sigue roto** y las fases F1/F2/F2-bis se justifican igual.
- Si (4) devuelve mayoría `no_matrix_cell` ⇒ **RC-1 confirmado con datos de producción**.
- Si (4) no devuelve nada ⇒ el motor A ni siquiera se disparó; revisar `app.py:997-1000` **antes** de seguir.

**Comando exacto de los tests** (con `$PY`/`$RAIZ` de §3-12):
```powershell
cd "$RAIZ\Stacky Agents\backend"; & $PY -m pytest tests/test_plan271_caracterizacion.py -v
```

**Criterio de aceptación (BINARIO) — reformulado (E12):** los **4** tests fallan, y fallan **por su propio `assert`**, no por error de colección ni de DB. Conteo esperado `0 passed, 4 failed`.
- `test_rc2_...` siembra en la DB (vía `close_sin_html` → `_seed_execution_y_ticket`). §3-9/R7 declaran `SQLITE_LOCKED` como probable, y un `SQLITE_LOCKED` da **`1 error`**, no `1 failed` ⇒ el conteo crudo del v3 era insatisfacible en ese escenario. **Si aparece `SQLITE_LOCKED`, reintentá el mismo archivo hasta 3 veces antes de leer el conteo.** Si a la tercera sigue en `error`, se reporta como flakiness de entorno, no como diagnóstico refutado.
- Cualquier test que pase **en verde** acá = el diagnóstico está mal: se detiene el plan y se reabre §2. **Prohibido relajar un test para llegar al conteo** (§3-11).
- **Y** la salida de los 4 comandos de F0-D pegada en el PR con su interpretación en una línea.

**Flag:** ninguna. **Impacto por runtime:** ninguno. **Trabajo del operador: ninguno.**

---

### F1 — Resolver único del estado final (módulo puro)

**Objetivo (1 frase):** una sola función pura que, dados el perfil y la config del empleado, diga **qué estado aplicar y por qué**, con precedencia declarada y determinista.
**Valor:** cierra C-e (no determinismo) y da la base para RC-1.

**Archivo a crear:** `backend/services/final_state_resolver.py`

```python
# backend/services/final_state_resolver.py
"""Plan 271 F1 — Resolutor ÚNICO del estado final al terminar un agente.

Puro: sin DB, sin red, sin config global mutable salvo la lectura de la flag.
Nunca lanza. Siempre devuelve una FinalStateDecision con `reason` no vacío.
"""
from __future__ import annotations
from typing import NamedTuple, Optional

# Precedencia CONGELADA, de mayor a menor. El primero que produce un estado gana.
PRECEDENCE: tuple[str, ...] = ("caller", "matrix", "role", "employee_config")

# Razones que ESTE módulo puede devolver.
REASONS: frozenset[str] = frozenset({
    "ok", "not_ok_status", "no_agent_type", "no_config", "flag_off",
})

# Catálogo COMPLETO de razones que cualquier escritor de estado puede emitir
# (§2.4 del plan 271). Fuente única para el mapa de la UI (F6), para el test
# puente (F6) y para el centinela de contrato (F9).
# Agregar una razón nueva sin agregarla acá deja DOS tests rojos.
# D3 — "unknown" NO está y NO puede estar: es la confesión de que falta una razón.
ALL_FINAL_STATE_REASONS: frozenset[str] = frozenset({
    "ok", "flag_off", "not_ok_status", "no_ticket",
    "no_ado_id_or_stacky_project", "no_matrix_cell", "no_final_state",
    "state_not_applicable", "human_moved_out_of_flow", "exception",
    "no_config", "no_agent_type", "no_target_or_id", "already_in_state",
    "no_provider", "not_requested", "publish_not_ok", "review_mode_hold",
    "no_ticket_id", "ticket_lookup_failed", "no_ado_id",
    "ado_client_unavailable", "provider_unavailable",
    # ── agregadas en el v3 (D3, D6) ──────────────────────────────────────
    "dev_build_gate_no_state",          # api/tickets.py:574 (YA existe) + F2-bis
    "already_written_by_other_engine",  # árbitro simétrico (F2-bis, F3-bis-2)
    "transition_failed",                # rama de error de _safe_transition (F3-bis-3)
    "no_project_context",               # ticket sin stacky_project_name (F3, D6)
})


class FinalStateDecision(NamedTuple):
    state: Optional[str]   # estado a aplicar; None = no aplicar
    source: str            # uno de PRECEDENCE, o "none"
    reason: str            # uno de REASONS. NUNCA vacío.


def role_fallback_enabled() -> bool:
    """Lee la INSTANCIA config.config (NO el atributo de clase Config): con la
    clase, monkeypatch.setattr(config.config, ...) del test no voltea el branch.
    Mismo patrón que completion_state.matrix_enabled (completion_state.py:32-35)."""
    try:
        from config import config as _cfg
        return bool(getattr(_cfg, "STACKY_FINAL_STATE_ROLE_FALLBACK_ENABLED", False))
    except Exception:  # noqa: BLE001
        return False


# D2 — el árbitro SIMÉTRICO vive acá, no en un motor, para que los DOS motores
# lean exactamente el mismo criterio de "ya se escribió". El cuerpo completo está
# en §F2-bis; se crea en ESTA fase porque F2-bis y F3-bis-2 lo importan los dos.
def final_state_already_written(execution_id) -> bool:
    ...  # ver el cuerpo literal en F2-bis


def resolve_final_state(
    *,
    caller_state: Optional[str] = None,
    matrix_state: Optional[str] = None,
    role_state: Optional[str] = None,
    employee_state: Optional[str] = None,
    agent_type: Optional[str] = None,
    final_status: str = "completed",
) -> FinalStateDecision:
    """Aplica PRECEDENCE. Pura. Nunca lanza."""
    ...
```

**Tabla de verdad exacta:**

| `final_status` | `agent_type` | `caller` | `matrix` | `role` | `employee` | flag rol | → `state` | `source` | `reason` |
|---|---|---|---|---|---|---|---|---|---|
| `"completed"` | `"technical"` | `"X"` | `"A"` | `"B"` | `"C"` | ON | `"X"` | `caller` | `ok` |
| `"completed"` | `"technical"` | `None` | `"A"` | `"B"` | `"C"` | ON | `"A"` | `matrix` | `ok` |
| `"completed"` | `"technical"` | `None` | `None` | `"B"` | `"C"` | ON | `"B"` | `role` | `ok` |
| `"completed"` | `"technical"` | `None` | `None` | `"B"` | `"C"` | **OFF** | `None` | `none` | `flag_off` |
| `"completed"` | `"technical"` | `None` | `None` | `None` | `"C"` | ON | `"C"` | `employee_config` | `ok` |
| `"completed"` | `"technical"` | `None` | `None` | `None` | `None` | ON | `None` | `none` | `no_config` |
| `"completed"` | `None` | `None` | `"A"` | `None` | `None` | ON | `None` | `none` | `no_agent_type` |
| `"error"` | `"technical"` | `None` | `"A"` | `"B"` | `"C"` | ON | `None` | `none` | `not_ok_status` |
| `"needs_review"` | `"technical"` | `None` | `"A"` | `"B"` | `"C"` | ON | `None` | `none` | `not_ok_status` |
| `"completed"` | `"technical"` | `"X"` | `None` | `None` | `None` | **OFF** | `"X"` | `caller` | `ok` |
| `"completed"` | `"technical"` | `None` | `"A"` | `"B"` | `"C"` | **OFF** | `"A"` | `matrix` | `ok` |
| `"completed"` | `"technical"` | `None` | `None` | `None` | `"C"` | **OFF** | `"C"` | `employee_config` | `ok` |

> **Las dos últimas filas son NUEVAS y cierran un agujero que hacía insatisfacible una promesa del propio plan (E7).** El v3 tenía 10 filas y **ninguna** con `matrix != None` y la flag OFF. Eso deja al implementador decidiendo algo que no puede decidir: si la flag gatea **también** la matriz, apagarla **regresiona el plan 208** (la matriz deja de aplicar); si no la gatea, faltaba la fila y faltaba el test. §3-7 promete *"con las 4 flags apagadas, el comportamiento es byte-idéntico al de hoy"*, y eso **exige** que `caller`, `matrix` y `employee_config` ignoren la flag. Queda escrito: **`STACKY_FINAL_STATE_ROLE_FALLBACK_ENABLED` gatea EXCLUSIVAMENTE la rama `role`.** Es lo único que este plan agrega; las otras tres ramas no son suyas.

**Casos borde obligatorios:** strings `""` y `"   "` se tratan como `None` (`.strip()` antes de evaluar). **Sólo la rama `role` consulta la flag**; `caller`, `matrix` y `employee_config` la ignoran (filas 10, 11 y 12). `final_status` se compara en minúsculas y `strip()`.

> **Por qué `needs_review` NO transiciona:** exige revisión humana; auto-transicionar violaría HITL. Mismo criterio que `completion_state.py:16-25`.

> **Sinceramiento de alcance (C12).** En este plan **solo F2/F2-bis** consumen el resolver, y le pasan `matrix_state` y `role_state`. `caller` y `employee_config` existen porque el motor B ya los tiene (`agent_completion_internal.py:247-258`), y quedan **preparados pero sin productor** hasta el plan 272. No se los describe como "unificados": están **declarados**. Esto es deuda consciente, no un descuido.
>
> **`on_failure_state` (C16):** `_resolve_transition_state_from_config` también resuelve `on_failure_state` para `final_status in {"error","needs_review"}` (`agent_completion_internal.py:249,352`). El resolver de F1 **no lo modela** y devuelve `not_ok_status` para todo lo que no sea `completed`. Mientras el motor B no use el resolver (o sea, en todo este plan), no hay pérdida. **Cablear el resolver en el motor B sin modelar `on_failure_state` sería una regresión**: queda escrito acá para el 272.

**Archivo de test a crear:** `backend/tests/test_plan271_final_state_resolver.py`
**Casos:** las **12** filas de la tabla, una por test (las 10 del v3 + las 2 de E7: matriz con flag OFF y employee con flag OFF), + 2 de casos borde (`""` y `"  "`), + 1 que afirma `PRECEDENCE == ("caller","matrix","role","employee_config")`, + 1 que afirma `REASONS ⊆ ALL_FINAL_STATE_REASONS`, + 1 que afirma `len(ALL_FINAL_STATE_REASONS) == 27` y que **`"unknown" not in ALL_FINAL_STATE_REASONS`** (D3), + 2 sobre `final_state_already_written` (sin `execution_id` ⇒ `False`; con `applied=True` sembrado ⇒ `True`). Total: **19 tests**.

**Flag que la protege:** `STACKY_FINAL_STATE_ROLE_FALLBACK_ENABLED` — **default ON**. Las 7 patas de §3.1 se cablean **en esta fase**. **Localizá los 3 primeros anclajes con los greps de §3.4 — los números del v3 estaban desfasados (E2):**
1. `backend/config.py` — junto al bloque `STACKY_ADO_STATE_MATRIX_ENABLED` (commit base **`:1419-1420`**; el v3 decía `:1401-1406`, que es otra flag).
2. `backend/services/harness_flags.py` — `FlagSpec` inmediatamente después del de `STACKY_ADO_STATE_MATRIX_ENABLED` (commit base **`:2853-2866`**; el v3 decía `:2795-2807`, ~58 líneas antes). **Sin `requires=`** (§3.1 pata 8).
3. `backend/services/harness_flags.py` — key en `_CATEGORY_KEYS["flujo_funcional"]`, que **abre en `:272`**.
4. `backend/services/harness_flags_help.py` — `PlainHelp` junto al de `STACKY_DETERMINISTIC_TASK_STATES_ENABLED` (`:893-898` — **este anclaje sí es exacto**, verificado).
5. `backend/harness_defaults.env` — `STACKY_FINAL_STATE_ROLE_FALLBACK_ENABLED=true` (orden alfabético).
6. `backend/tests/test_plan271_flags.py` (crear acá; se completa con las otras 3 keys en F3/F4/F5).
7. Registrar `test_plan271_final_state_resolver.py` y `test_plan271_flags.py` en `run_harness_tests.sh` **y** `.ps1`.

**Texto del `PlainHelp` (verificado contra las restricciones REALES de §3.1 pata 4):**
```python
"STACKY_FINAL_STATE_ROLE_FALLBACK_ENABLED": PlainHelp(
    what="Hace que el estado al que configuraste que pase la incidencia cuando el empleado termina se aplique de verdad.",
    on_effect="Si la activás: al terminar el empleado, la incidencia pasa al estado que elegiste en la pantalla de Estados.",
    off_effect="Si la apagás: la incidencia se queda en el estado en que estaba y la tenés que mover a mano.",
    example="Como que el trámite avance solo de ventanilla cuando el funcionario lo termina, en vez de quedarse en el mostrador.",
),
```
> Medido de verdad (E13): `what`=**110** (10..200 ✔), `on_effect`=**108** (≤240 ✔, empieza con `"Si "` ✔), `off_effect`=**92** ✔, `example`=**115** (≤300 ✔). Sin palabras de la denylist, sin `SCREAMING_SNAKE`, sin `F\d`. (El v3 daba 113/116/104/121 — mal los cuatro, aunque el veredicto era el correcto.)

**Comando exacto:**
```powershell
cd "$RAIZ\Stacky Agents\backend"; & $PY -m pytest tests/test_plan271_final_state_resolver.py -v
```

**Criterio de aceptación (BINARIO):**
- **`19 passed`** (12 filas de la tabla + 2 borde + 5 estructurales — E7).
- **Y** `test_harness_flags.py` en **`56 passed`**.
- **Y** `test_plan271_flags.py` en **verde**, incluido `test_las_4_keys_tienen_ayuda_llana_y_pasan_los_cinco_chequeos` — **este es el gate real de la ayuda llana**, y en F1 cubre por lo menos la key de esta fase. **Con la verificación de discriminación de §3.3bis hecha y pegada en el PR** (borrar una entrada ⇒ rojo; reponerla ⇒ verde).
- **Y** en `test_harness_flags_help.py`: **ninguna key `STACKY_FINAL_STATE_*` ni en `missing` (`:35`) ni en `violations` (`:76`)**. El conteo `4 failed, 4 passed` se anota como contexto pero **no es el criterio** (E3: no discrimina).

**Impacto por runtime:** ninguno — módulo puro sin consumidores todavía. **Trabajo del operador: ninguno.**

---

### F2 — Cablear el resolver en el motor A (cierra RC-1)

**Objetivo (1 frase):** que `completion_state.maybe_apply_state_transition` honre el `next_state_ok` de nivel rol cuando la matriz no define estado final, en lugar de descartarlo.
**Valor:** **cierra la causa raíz primaria** por el camino común a los 3 runtimes.

**Archivo a editar:** `backend/services/completion_state.py`

**Diff — reemplazar `:88-99`** (el rango es exacto, verificado; localizá los bordes con `grep -n "no_matrix_cell\|state_not_applicable" backend/services/completion_state.py`).

> **E11 — el bloque "ANTES" del v3 NO era byte-idéntico al código real.** Le faltaba el comentario de `:97` (`# CENTINELA EN RUNTIME: jamás aplicar un estado fuera del conjunto cerrado.`) y mostraba indentación **0** donde el código real está a **8 espacios** (vive dentro de un `with session_scope()` anidado en un `try`). Para un reemplazo literal eso importa. Este es el bloque **real**, copiado del archivo:

```python
# ANTES (completion_state.py:88-99) — LITERAL, 8 espacios de indentación
        plan = resolve_task_state_plan(profile, agent_type, work_item_type)
        ctx["source"] = plan.source
        if plan.source != "matrix":
            # Backward-compat DURA: sin cell configurado, los paths de runner NO transicionan.
            return _logged(ctx, ev, {"skipped": True, "reason": "no_matrix_cell", "source": plan.source})
        target = plan.final_ok
        ctx["target"] = target
        if not target:
            return _logged(ctx, ev, {"skipped": True, "reason": "no_final_state"})
        # CENTINELA EN RUNTIME: jamás aplicar un estado fuera del conjunto cerrado.
        if target not in applicable_states(plan):
            return _logged(ctx, ev, {"skipped": True, "reason": "state_not_applicable"})

# DESPUÉS — mantené los 8 espacios de indentación en todo el bloque
plan = resolve_task_state_plan(profile, agent_type, work_item_type)
from services.final_state_resolver import resolve_final_state

# La matriz sigue mandando cuando DEFINE ESTADO FINAL (comportamiento 208 intacto).
matrix_state = plan.final_ok if plan.source == "matrix" else None
# C13 — celda PARCIAL: source=="matrix" con final_ok=None (task_states.py:107-108).
# El nivel de rol NO puede quedar enterrado por una celda que solo trae in_progress.
role_machine = (profile.get("tracker_state_machine") or {}).get(agent_type) or {}
role_state = (role_machine.get("next_state_ok") or "").strip() or None
decision = resolve_final_state(
    matrix_state=matrix_state,
    role_state=role_state,
    agent_type=agent_type,
    final_status=final_status,
)
ctx["source"] = decision.source
ctx["target"] = decision.state
ctx["plan_source"] = plan.source
if decision.state is None:
    # Nunca mudo: `reason` viene del conjunto cerrado REASONS.
    return _logged(ctx, ev, {"skipped": True, "reason": decision.reason,
                             "source": decision.source, "plan_source": plan.source})
target = decision.state
# CENTINELA EN RUNTIME: conjunto cerrado = lo aplicable del plan MÁS el nivel rol,
# porque `role_state` puede no estar en applicable_states(plan) cuando el plan vino
# de una celda parcial (plan.final_ok is None ⇒ applicable_states no lo contiene).
permitidos = set(applicable_states(plan))
if role_state:
    permitidos.add(role_state)
if target not in permitidos:
    return _logged(ctx, ev, {"skipped": True, "reason": "state_not_applicable",
                             "target": target})
```

> **Por qué `role_state` se lee del perfil y no de `plan.final_ok` (C13).** El v1 hacía `role_state = plan.final_ok if plan.source == "config" else None`. Eso funciona para el caso simple, pero deja el agujero de celda parcial: cuando `source=="matrix"` con `final_ok=None`, `plan.final_ok` es `None` y el rol nunca se consulta. Leer `tracker_state_machine[agent_type]["next_state_ok"]` directo del perfil cierra los dos casos con una sola línea. `_machine_for` (`task_states.py:50-55`) hace lo mismo, pero es privado: replicar las dos líneas es más barato que exportarlo.

**Lo que NO se toca en esta fase (invariantes duros):**
- `_origin_guard` (`:121-161`) se llama **antes** de `_safe_transition`, igual que hoy (`:108-111`). Es la guardia HITL.
- `_OK_STATUSES` (`:24-25`) queda en `{"completed"}`. `needs_review` sigue sin transicionar.
- `matrix_enabled()` (`:28-37`) sigue siendo el gate maestro del motor A.

**Cambio de contrato de log — declarado (C22, precisado en E7).** Tras F2, el motor A deja de emitir `no_matrix_cell` y `no_final_state` y pasa a emitir `no_config`/`no_agent_type`/`flag_off`. **Esto pasa también con la flag OFF**: el camino "sin matriz" que hoy dice `no_matrix_cell` va a decir `flag_off`. Las dos legacy **se conservan en `ALL_FINAL_STATE_REASONS`** para que las filas históricas de `SystemLog action="completion.matrix_transition"` sigan teniendo etiqueta en la UI. Escribilo en el docstring del módulo.

**Criterio de aceptación (BINARIO) — actualizado:** `10 passed` (los 9 del v3 + el 6-bis de E7).

**Archivo de test a crear:** `backend/tests/test_plan271_role_fallback.py`
**Casos (9):**
1. Rol con `next_state_ok="To Do"`, sin `by_work_item_type` ⇒ `ok=True`, `to="To Do"`, `ctx.source="role"`. **(El bug reportado.)**
2. Matriz con celda **completa** para `work_item_type="Bug"` y rol distinto ⇒ gana la matriz, `source="matrix"`.
3. Matriz configurada pero `ticket.work_item_type` NULL ⇒ cae a rol, `source="role"`, transiciona.
4. **Celda PARCIAL** (`by_work_item_type["Bug"] = {"in_progress": "Doing"}`) + rol con `next_state_ok` ⇒ transiciona al de rol, `source="role"`. **(C13.)**
5. Ni matriz ni rol ⇒ `skipped`, `reason="no_config"`, `reason` no vacío.
6. Flag `STACKY_FINAL_STATE_ROLE_FALLBACK_ENABLED=False` + solo rol ⇒ `skipped`, `reason="flag_off"`, **`prov.writes == []`**. **Ojo (E7): la CONDUCTA es idéntica a hoy (no se escribe), pero el `reason` NO lo es** — hoy ese camino emite `no_matrix_cell` (`completion_state.py:92`, verificado). El "byte-idéntico" de §3-7 se refiere a la **escritura de estado**, no a la etiqueta del `SystemLog`; el cambio de contrato de log está declarado abajo y vale también con la flag OFF.
6-bis. **Flag OFF pero matriz CON estado final ⇒ transiciona igual, `source="matrix"`** (E7, fila 11 de la tabla de verdad). Sin este caso, apagar la flag de este plan regresionaría el plan 208 y nadie lo notaría.
7. `_origin_guard` sigue bloqueando: `FakeProvider(current_state="Cerrado a mano")` fuera del flujo ⇒ `reason="human_moved_out_of_flow"`, **`prov.writes == []`**.
8. `final_status="needs_review"` ⇒ `skipped`, `reason="not_ok_status"`, sin escritura.
9. `role_state` no vacío pero distinto de todo lo aplicable **y sin rol en el perfil** (perfil manipulado) ⇒ `state_not_applicable`, sin escritura.

**Comando exacto:**
```powershell
cd "$RAIZ\Stacky Agents\backend"; & $PY -m pytest tests/test_plan271_role_fallback.py -v
```

**Criterio de aceptación (BINARIO):**
- **`10 passed`** (E7).
- **Y** de `test_plan271_caracterizacion.py`: `test_rc1_rol_sin_matriz_deberia_transicionar` y `test_rc1_celda_parcial_no_debe_enterrar_el_nivel_rol` pasan a **VERDE**; los otros 2 siguen rojos. Conteo esperado: `2 passed, 2 failed`.
- **Y** `pytest backend/tests/test_plan79_apply_final.py` y `pytest backend/tests/test_plan79_centinela_estados.py` siguen verdes (**por archivo**): usan `resolve_task_state_plan`/`applicable_states`, que esta fase **no** modifica.

**Flag:** `STACKY_FINAL_STATE_ROLE_FALLBACK_ENABLED` (cableada en F1). **Default ON.**
**Impacto por runtime:** los 3 cierran por `ticket_status.on_execution_end` → post-hook (`completion_dispatcher.py:8-10`), así que la corrección aplica a Codex CLI, Claude Code CLI y Copilot **por construcción**. Fallback: flag OFF ⇒ los 3 vuelven al comportamiento de hoy.
**Trabajo del operador: ninguno.**

---

### F2-bis — `[ADICIÓN ARQUITECTO]` Árbitro anti-doble-escritura **SIMÉTRICO** y respeto del gate de build

**Objetivo (1 frase):** que activar F2 no convierta al motor A en un pisador del motor C (gate del plan 210) ni del motor B.
**Valor:** cierra **C2** (regresión del plan 210) y **C11** (carrera daemon vs inline). Sin esta fase, F2 es una regresión disfrazada de fix.

#### El problema, con evidencia

1. **Gate de build (C2).** El motor C aplica `dev_build_verify.gate_final_state` antes de escribir (`api/tickets.py:576-582`): cuando el Developer no tiene veredicto de máquina fresco, **degrada** el `target` o lo anula. `grep -c dev_build_verify backend/services/completion_state.py` ⇒ **0**. Hoy da igual porque el motor A nunca transiciona sin matriz. **Con F2 sí transiciona**, y puede sobrescribir la degradación que el 210 acaba de aplicar. Eso reabre el "falso Build OK" que los planes 210/211 cerraron.
2. **Carrera (C11), con la dirección corregida (D2).** `close_execution_with_publish` **encola** el motor A en el Paso 2 (`agent_completion_internal.py:172-181`) y escribe con el motor B en el Paso 4 (`:274`), **en el mismo hilo**. El motor A lo drena un **daemon de fondo** (`completion_dispatcher.py:100-121`, con `maybe_apply_state_transition(ev)` en `:118`) que está bloqueado en `_Q.get(...)`: con la cola vacía — el caso normal — **despierta y corre de inmediato**, o sea **antes** de que el hilo del cierre llegue a `:274`. Los targets pueden diferir: el motor A usa `tracker_state_machine.<rol>.next_state_ok` y el motor B usa `agent_workflow_configs[<filename>].transition_state`. La idempotencia de `_safe_transition` (`task_states.py:164-168`) solo salva si **coinciden**.
   > **Esto es exactamente lo que el v2 no vio.** Su árbitro vivía **solo** en `completion_state.py`, o sea que cubría el caso "B escribió primero, A se abstiene" — el orden **menos** probable. En el orden probable (A primero, B después), **B escribía igual, sin consultar nada**. El riesgo R3, que el propio v2 subió a "Alta" y admite que **F2 agrava**, quedaba sin mitigar. Por eso el árbitro del v3 es **simétrico**.

#### Lo que se construye

**Archivos a editar:** `backend/services/completion_state.py` (guardias 1 y 2) **y** `backend/services/agent_completion_internal.py` (guardia simétrica, que por dependencia se implementa en **F3-bis-2**).

**Helper compartido — vive en `backend/services/final_state_resolver.py`** (F1), para que **los dos motores lean exactamente el mismo código** y no haya dos criterios de "ya se escribió":

```python
def final_state_already_written(execution_id) -> bool:
    """Plan 271 F2-bis / F3-bis-2 — árbitro SIMÉTRICO por execution_id.

    True si algún motor ya aplicó el estado final de esta ejecución (la key
    `final_state_outcome` que F5 persiste, con applied=True).
    Best-effort: cualquier problema ⇒ False (fail-open, nunca bloquea un cierre).
    """
    if not execution_id:
        return False
    try:
        from db import session_scope
        from models import AgentExecution
        with session_scope() as s:
            row = s.get(AgentExecution, int(execution_id))
            fso = (row.metadata_dict or {}).get("final_state_outcome") if row else None
            return bool(isinstance(fso, dict) and fso.get("applied") is True)
    except Exception:  # noqa: BLE001
        return False
```

**En `completion_state.py`** — las dos guardias, ambas **antes** de `_safe_transition` y **después** de `_origin_guard`:

```python
# GUARDIA 1 (C2) — respetar el gate de build del plan 210, igual que api/tickets.py:573-577.
# D11 — CORTOCIRCUITO OBLIGATORIO: gate_final_state (dev_build_verify.py:421-422)
# devuelve `not_applicable` para todo agent_type != "developer", pero
# workspace_root_for_ado (:343) hace una consulta a DB MÁS get_project_config.
# Sin este `if`, cada completación de CUALQUIER rol paga dos lookups para nada.
if agent_type == "developer":
    try:
        from services import dev_build_verify as _dbv
        _ws = _dbv.workspace_root_for_ado(int(ado_id))
        _exec_id = ev.get("execution_id") or _dbv.latest_execution_id_for_ado(int(ado_id))
        target, _gate = _dbv.gate_final_state(
            project_name=stacky_project, agent_type=agent_type, ado_id=int(ado_id),
            workspace_root=_ws, proposed_state=target, execution_id=_exec_id,
        )
        if target is None:
            return _logged(ctx, ev, {"skipped": True, "reason": "dev_build_gate_no_state",
                                     "gate_reason": _gate.get("reason")})
        ctx["target"] = target
    except Exception:  # noqa: BLE001 — el gate jamás rompe el cierre
        logger.debug("gate_final_state falló en motor A (no crítico)", exc_info=True)

# GUARDIA 2 (C11/D2) — mitad A del árbitro simétrico.
# ALCANCE (§2.1bis): cubre A vs B. NO cubre C, D, E ni F (viven en api/tickets.py,
# intocable acá) — eso es del plan 272.
from services.final_state_resolver import final_state_already_written
if final_state_already_written(ev.get("execution_id")):
    return _logged(ctx, ev, {"skipped": True, "reason": "already_written_by_other_engine"})
```

> **El `import` de `dev_build_verify` NO puede quedar solo adentro del `if agent_type == "developer"`.** F8 test 3 exige que `services/completion_state.py` **importe** `dev_build_verify` (invariante del 210). Como es un import local dentro de un `if`, el AST lo ve igual — pero si alguien lo mueve, el test se pone rojo con el nombre del plan que se rompe. Es el efecto buscado.

> **Orden de fases (importante, corregido).** La **guardia 1** no depende de nada posterior y va **junto con F2**. La **guardia 2** (mitad A) y su gemela **F3-bis-2** (mitad B) dependen de que exista la key `final_state_outcome`, o sea de **F5**, así que se implementan **después de F5** (§7.2). Mientras F5 no exista, `final_state_already_written` devuelve siempre `False` y **las dos mitades son no-ops inofensivos**. **No es un ciclo.**

**Razones nuevas al catálogo:** `dev_build_gate_no_state` (que **ya existe hoy** en `api/tickets.py:574`, D3) y `already_written_by_other_engine`. Ya están en `ALL_FINAL_STATE_REASONS` (F1) y en el mapa de F6 ⇒ el catálogo cierra en **27**.

**Archivo de test a crear:** `backend/tests/test_plan271_arbitro.py`
**Casos (8):**
1. `agent_type="developer"` y `gate_final_state` devuelve `(None, {"reason": "build_stale"})` ⇒ `skipped`, `reason="dev_build_gate_no_state"`, **`prov.writes == []`**.
2. `agent_type="developer"` y `gate_final_state` devuelve `("En revisión", {...})` (degradación) ⇒ se escribe **"En revisión"**, no el `next_state_ok` crudo.
3. `agent_type="developer"` y `gate_final_state` lanza ⇒ el cierre sigue y se escribe el target original (fail-open).
4. **`agent_type="technical"` ⇒ `workspace_root_for_ado` NO se llama** (espiala con un contador). **(D11: el cortocircuito de performance es un criterio, no una intención.)**
5. `metadata_dict` ya trae `final_state_outcome.applied=True` ⇒ motor A: `skipped`, `reason="already_written_by_other_engine"`, sin escritura.
6. `metadata_dict` trae `final_state_outcome.applied=False` ⇒ motor A **sí** escribe (un skip previo no bloquea el reintento).
7. **Simetría (D2), motor B:** con `final_state_outcome.applied=True` sembrado, `_attempt_state_change` devuelve `{"skipped": True, "reason": "already_written_by_other_engine"}` y **no** llama al provider ni a `AdoClient`. *(Este caso se vuelve verde recién con F3-bis-2; hasta entonces queda rojo y declarado como tal en el PR.)*
8. **Los dos motores usan el MISMO helper:** `inspect.getsource` de `completion_state.maybe_apply_state_transition` y de `agent_completion_internal._attempt_state_change` contienen ambos `final_state_already_written`. **(Evita que vuelvan a existir dos criterios de "ya se escribió".)**

**Comando exacto:**
```powershell
cd "$RAIZ\Stacky Agents\backend"; & $PY -m pytest tests/test_plan271_arbitro.py -v
```

**Criterio de aceptación (BINARIO):**
- Al terminar la **guardia 1** (junto con F2): `4 passed, 4 failed` (los casos 5..8 necesitan F5/F3-bis-2).
- Al terminar **F3-bis-2** (después de F5): **`8 passed`**.
- **Y** `pytest backend/tests/test_plan210_state_gate.py` sigue en **`16 passed`** (§3.3 — hoy está verde, así que cualquier rojo es tuyo).
- **Y** `test_plan271_role_fallback.py` sigue en **`10 passed`** (E7; la guardia no debe cambiar ningún caso feliz).

**Flag:** ninguna propia (vive dentro del camino de `STACKY_FINAL_STATE_ROLE_FALLBACK_ENABLED`; su gemela de F3-bis-2 vive dentro del de `STACKY_FINAL_STATE_WRITER_ROUTED_ENABLED`). Una guardia que solo **reduce** escrituras no necesita interruptor: apagarla sería pedir el bug.
**Impacto por runtime:** ninguno. **Trabajo del operador: ninguno.**

---

### F3 — El escritor del chokepoint rutea por provider (paridad ADO ↔ GitLab)

**Objetivo (1 frase):** que `_attempt_state_change` deje de ser ADO-only y escriba en el tracker que **el proyecto del ticket** declara.
**Valor:** cierra E-3. En un proyecto GitLab, hoy este camino escribe en ADO con un `iid` de GitLab.

**Archivo a editar:** `backend/services/agent_completion_internal.py`. Esta fase toca **cuatro** puntos (el v1 decía "solo el cuerpo" y a la vez pedía tres cambios más — contradicción corregida):
1. La firma de `_attempt_state_change` (`:502-504`).
2. Su cuerpo (`:526-553`).
3. El call site del Paso 4 (`:274-278`).
4. El call site de `publish_execution_from_review` (`:476-480`).
Más dos helpers nuevos al final del bloque de helpers.

**Firma nueva:**
```python
def _attempt_state_change(
    *, ticket_id: int | None, target_state: str, execution_id: int,
    project_name: str | None = None,
) -> dict:
```
Los dos call sites lo pasan: `:274-278` usa `stacky_project_name` (ya leído en `:135`) y `:476-480` usa `project_name` (ya leído en `:461`).

**Diff — reemplazar `:526-553`:**

```python
# ANTES (:526-541)
try:
    from services.ado_client import AdoClient
except ImportError as exc:
    return {"skipped": True, "reason": "ado_client_unavailable"}
try:
    AdoClient().update_work_item_state(int(ado_id), target_state)
    return {"ok": True, "to": target_state, "ado_id": ado_id}
except Exception as exc: ...

# DESPUÉS
# D2 — mitad B del árbitro simétrico (se activa en F3-bis-2, después de F5).
from services.final_state_resolver import final_state_already_written
if final_state_already_written(execution_id):
    return {"skipped": True, "reason": "already_written_by_other_engine"}

# C6 — REGLA DURA: sin project_name NO se rutea. resolve_state_writer(ticket)
# resuelve por el tracker_type DEL TICKET, nunca por el proyecto activo: eso
# evita exactamente el bug que esta fase cierra (escribir en el tracker
# equivocado). E23/v6 — se rutea por el RESOLVER DEL PLAN 270
# (services.tracker_write_router.resolve_state_writer), NO por
# get_tracker_provider directo: es el mismo mecanismo que ya usan
# set_stacky_status_by_ado y ticket_state_writeback.py, evita un SEGUNDO
# camino de resolución ADO/GitLab que puede divergir del primero, y — a
# diferencia de la v5 — NO referencia get_tracker_provider/tracker_type/
# _provider_for_ticket dentro de esta función, así que no toca el centinela
# del 270 (test_plan270_state_write_ratchet.py::test_5, ver F3-bis-0).
# D6 — pero el caso NO puede ser mudo: hoy un ticket sin stacky_project_name en un
# proyecto GitLab escribe en ADO con el iid de GitLab y nadie se entera. Se marca.
if _writer_routed_enabled() and not project_name:
    logger.warning("[exec=%s] sin stacky_project_name: escritura de estado por el "
                   "camino legacy (ADO) — ver plan 271 D6", execution_id)
    _sin_contexto = True   # se propaga como `reason` en el dict de retorno legacy
if _writer_routed_enabled() and project_name:
    from services.tracker_provider import CapabilityUnavailable
    from services.tracker_write_router import resolve_state_writer
    try:
        writer = resolve_state_writer(ticket)  # `ticket` ya resuelto arriba (:516)
    except CapabilityUnavailable as exc:
        logger.warning("[exec=%s] escritor no disponible: %s", execution_id, exc.reason)
        return {"skipped": True, "reason": "provider_unavailable", "error": exc.reason}
    except Exception as exc:  # noqa: BLE001 — tracker mal configurado, GitLab off, etc.
        logger.warning("[exec=%s] provider no disponible: %s", execution_id, exc)
        return {"skipped": True, "reason": "provider_unavailable", "error": str(exc)}
    from harness.task_states import _safe_transition
    # writer.kind: "provider" (GitLab, vía _safe_transition con provider=) o
    # "ado_client" (ADO, vía legacy_client_fn= — el propio handle YA es el cliente).
    result = _safe_transition(
        writer.handle if writer.kind == "provider" else None, ado_id, target_state,
        phase="final_config",
        legacy_client_fn=(lambda: writer.handle) if writer.kind == "ado_client" else None,
    )
    result.setdefault("ado_id", ado_id)
    # C7 — `_safe_transition` hardcodea {"source": "config"} en el éxito
    # (task_states.py:178). Ese valor NO es el origen de la decisión y rompería
    # el `setdefault("source", target_source)` del Paso 4. Se saca acá.
    if result.pop("source", None) is not None:
        result["writer"] = "safe_transition"
    return result
# Camino legacy (flag OFF, o sin project_name): idéntico al bloque ANTES, con DOS
# diferencias, ninguna de comportamiento de escritura:
#  (1) D6: si fue por FALTA de contexto de proyecto, el dict de ÉXITO lleva
#      `"note": "no_project_context"` para que F5/F6 lo puedan mostrar.
#  (2) E4 — OBLIGATORIO: el `except` de ese camino (hoy en :547) devuelve
#      {"ok": False, "to", "ado_id", "error", "type"} SIN `reason`. Es el MISMO
#      defecto que D3 denuncia en task_states.py:183, en la rama hermana, y el v3
#      no lo vio. Se le agrega `"reason": "transition_failed"`:
#          return {"ok": False, "reason": "transition_failed", "to": target_state,
#                  "ado_id": ado_id, "error": str(exc), "type": type(exc).__name__}
#      Sin esto, F9 test 3 NACE ROJO por un retorno que el plan no nombra, y el
#      caso común de R6-bis (ticket sin stacky_project_name) falla en silencio.
```

**[v6] Detalle que un modelo menor no puede inferir y por eso está escrito: `ticket` sigue siendo válido después de que cierra el `with session_scope()` de más arriba (`:515-521`).** `SessionLocal` se crea con `expire_on_commit=False` (`backend/db.py:39`, verificado), así que el objeto `Ticket` queda **detached pero NO expirado**: leer `ado_id`, `tracker_type`, `stacky_project_name` o `project` fuera del `with` no dispara un re-fetch ni un `DetachedInstanceError` — son columnas escalares ya cargadas en memoria antes del `close()`. No hace falta abrir una segunda sesión ni mover `resolve_state_writer(ticket)` adentro del `with`.

**[v6, E24] El valor de `target_state` NO se traduce para GitLab, y eso es una limitación real, no un bug de este diff.** `writer.handle.update_item_state(...)` (vía `_safe_transition`, cuando `writer.kind == "provider"`) recibe `target_state` **tal cual lo configuró el operador** (vocabulario ADO, p. ej. `"To Do"`). `GitLabTrackerProvider.update_item_state` sólo entiende 4 claves lógicas (`gitlab_provider.py:109-117`); cualquier otro valor levanta `CapabilityUnavailable`, que `_safe_transition` captura y devuelve como `{"ok": False, "reason": "transition_failed", ...}` (tras F3-bis-3). **No se agrega traducción de vocabulario en esta fase** — `services/close_intent.py` existe para intenciones de CIERRE, no para moverse a un estado intermedio como `"To Do"`, y forzarlo ahí sería incorrecto, no sólo trabajo de más. Ver R17 y el caso 11 de `test_plan271_writer_routed.py`.

**Helpers nuevos (al final del bloque de helpers):**
```python
def _writer_routed_enabled() -> bool:
    try:
        from config import config as _cfg
        return bool(getattr(_cfg, "STACKY_FINAL_STATE_WRITER_ROUTED_ENABLED", False))
    except Exception:  # noqa: BLE001
        return False


def _legacy_ado_client():
    from services.ado_client import AdoClient
    return AdoClient()
```

**Por qué `_safe_transition` y no una función nueva:** el plan 79 lo declara *"ÚNICA función que escribe estado"* (`harness/task_states.py:155`, docstring; el `def` está en `:146`). Ya trae idempotencia (`:164-168`) y ya es provider-agnóstica (`:171-177`). Escribir otra sería crear un **quinto** escritor.

**Por qué `resolve_state_writer` y no `write_state_for_ticket` (los dos del plan 270, E23+E24):** `write_state_for_ticket` (`tracker_write_router.py:145-163`) llama internamente a `_resolve_destination` → `resolve_close_target` (`close_intent.py:58-118`), que traduce el estado pedido **asumiendo que es una intención de cierre** (mapea a `"accepted"` en GitLab, o levanta `ValueError("unmappable_state")` si no reconoce el string). El `next_state_ok` de este plan casi nunca es un cierre (`"To Do"` es volver a la cola). Reusar `write_state_for_ticket` de punta a punta sería **semánticamente incorrecto**, no sólo un atajo — por eso este plan sólo reusa la mitad genérica (`resolve_state_writer`, que resuelve el HANDLE sin opinar sobre vocabulario) y despacha la escritura él mismo, igual que hacía antes, sólo que con el handle correcto.

> **Gotcha real de GitLab:** los write viven en `services/gitlab_provider.py`, **no** en el client. `update_item_state` está en `gitlab_provider.py:228` en el commit base (**hoy `:243`, medido — E21; re-localizalo con el grep de §3.4 antes de citarlo**). `resolve_state_writer` (`tracker_write_router.py:55-105`) exige `STACKY_GITLAB_ENABLED` para tickets GitLab y levanta `CapabilityUnavailable` si está OFF — por eso el `except` devuelve `provider_unavailable` en vez de romper el cierre.

#### F3-bis-0 — `[ADICIÓN ARQUITECTO v5, corregida en v6 — E23]` Coordinación OBLIGATORIA con el ratchet del plan 270

**Este paso va en el MISMO commit que el diff de arriba, no después.** El plan 270 (ya mergeado, commit `77627239`) construyó `services/tracker_write_router.py::resolve_state_writer()` — el mismo problema que resuelve el diff de F3 (decidir si el escritor es ADO o GitLab según el ticket) — y dejó un centinela esperando que este plan tocara `_attempt_state_change`: `backend/tests/test_plan270_state_write_ratchet.py::test_5_centinela_del_residuo_s5`, **verde hoy (6 passed, corrido)**, que prohíbe por AST que esa función referencie `get_tracker_provider` / `tracker_type` / `_provider_for_ticket`.

**[v6] El v5 leía este centinela como un obstáculo a esquivar editándolo. Es al revés: es la especificación de la fase.** El diff de F3 (arriba) YA está escrito para pasarlo tal cual, sin tocar una línea del test del 270:

1. **Antes de escribir el diff:** correr `& $PY -m pytest "$RAIZ\Stacky Agents\backend\tests\test_plan270_state_write_ratchet.py" -v` y confirmar que sigue en `6 passed` (baseline).
2. **Escribir el diff de F3 tal como está arriba** (con `resolve_state_writer`, no `get_tracker_provider`).
3. **Después del diff:** volver a correr `test_plan270_state_write_ratchet.py`. **Criterio de aceptación: sigue en `6 passed`, SIN EDITAR NINGUNA LÍNEA del archivo.** Si `test_5_centinela_del_residuo_s5` falla, el diff todavía referencia `get_tracker_provider` / `tracker_type` / `_provider_for_ticket` en el cuerpo de `_attempt_state_change` — **se detiene la fase y se corrige el diff** (§3 principio 11: nunca se edita el test para forzar el verde).
4. **Verificación (no es un caso nuevo de `test_plan271_writer_routed.py` — es un comando separado, ya en la DoD §7.3):** correr `test_plan270_state_write_ratchet.py` de nuevo después del diff de F3 y confirmar **`6 passed`, cero diffs en ese archivo** — el PR de F3 no debe tocar `test_plan270_state_write_ratchet.py` en absoluto.

#### F3-bis-1 — `test_output_watcher.py` NO se rompe: la "confirmación" del v2 era falsa (D6)

**Leé esto antes de tocar `test_output_watcher.py`.** El v2 declaraba, como riesgo *"Confirmado, no es hipótesis"*, que F3 rompe ese archivo, y mandaba parchear tres dobles. **Es falso**, y la razón importa más que el hecho.

La cadena que el v2 describió es correcta en abstracto (para el diseño de la v5: `_attempt_state_change` → `get_tracker_provider(project)` → `AdoTrackerProvider.__init__` → `build_ado_client`). **[v6, E23] Con el diff corregido la cadena es más corta pero la conclusión es la MISMA:** `_attempt_state_change` → `resolve_state_writer(ticket)` → (para `tracker_type` ADO) `services.project_context.build_ado_client(...)` **directo** (`tracker_write_router.py:78-84`, sin pasar por `AdoTrackerProvider`), que **sí** hace `from services.ado_client import AdoClient` **dentro** de `build_ado_client` (`project_context.py:295` ⇒ el monkeypatch del test aplicaría igual). Pero esa cadena **nunca se ejecuta en ese archivo, en ninguna de las dos versiones**, porque **`project_name` es `None`** y la condición de entrada (`if _writer_routed_enabled() and project_name:`) no cambió:

- `close_execution_with_publish` lee `stacky_project_name = getattr(ticket_obj, "stacky_project_name", None)` (`agent_completion_internal.py:135`).
- El helper del test, `_mk_ticket` (`test_output_watcher.py:87-107`), crea el `Ticket` con `project="RSPacifico"` y **jamás setea `stacky_project_name`**.
- Ergo `project_name is None` ⇒ la **regla dura C6** de F3 (`if _writer_routed_enabled() and project_name:`) toma el **camino legacy** ⇒ `AdoClient()` sin kwargs ⇒ el doble actual funciona **sin tocar una línea** ⇒ `assert calls == [(40109, "Reviewed by Dev")]` (`:370-371`) sigue pasando.

**Qué hacer, entonces:**
1. **No parchear los tres dobles.** Es trabajo inútil y, peor, deja la falsa sensación de que la cadena se probó.
2. **Correr `test_output_watcher.py` antes de F3 y anotar el conteo en el PR** (§3.3). Después de F3 tiene que dar **el mismo conteo**. Si cambia, es tuyo.
3. **Lo que este hallazgo destapa es el verdadero problema, y va al PR en una línea:** *un ticket sin `stacky_project_name` sigue escribiendo el estado en ADO aunque el proyecto sea GitLab.* F3 lo hace **visible** (`no_project_context`, D6) pero **no lo repara**: repararlo es poblar `stacky_project_name` en el alta del ticket, territorio de `_startup_sync` y del **plan 272**.
4. **Cobertura real de la cadena:** los casos 1, 2 y 4 de `test_plan271_writer_routed.py` **deben sembrar el ticket CON `stacky_project_name`** (por eso `_seed_execution_y_ticket` de F0 lo setea explícitamente). Sin eso, F3 quedaría con cero cobertura de su propio camino feliz — que es exactamente el agujero que este bloque cierra.

#### F3-bis-2 — mitad B del árbitro simétrico (D2) · va DESPUÉS de F5

Agregar al principio de `_attempt_state_change` la guardia ya mostrada en el diff de F3 (`final_state_already_written(execution_id)` ⇒ `already_written_by_other_engine`). Es la mitad que faltaba: sin ella, en el orden más probable (A drena primero, B escribe después) el motor B pisa igual. **Verificado por los casos 7 y 8 de `test_plan271_arbitro.py`.**

#### F3-bis-3 — los DOS escritores dejan de fallar en silencio (D3 + E4)

**Son dos ramas, no una.** El v3 sólo vio la de `task_states.py`. Medido con la regla de F9 corrida contra el árbol base: hay **dos** `return` de escritor sin `reason`.

| # | Archivo · función | `return` real | Estado en el v3 |
|---|---|---|---|
| 1 | `harness/task_states.py::_safe_transition`, `except` | `:183` | lo arreglaba ✔ |
| 2 | `services/agent_completion_internal.py::_attempt_state_change`, `except` del camino **legacy** | `:547` | **no lo nombraba nunca (E4)** |

**Archivo a editar (1):** `backend/harness/task_states.py`, rama de error de `_safe_transition` (el `return` está en `:183`; el `except` abre en `:179`).

```python
# ANTES (:184)
return {"ok": False, "to": target, "error": str(exc), "type": type(exc).__name__, "phase": phase}
# DESPUÉS — D3: la ÚNICA rama de todo el sistema que decidía no cambiar el estado
# y no decía por qué. F5 la traducía a reason="unknown", string fuera del catálogo.
return {"ok": False, "to": target, "reason": "transition_failed",
        "error": str(exc), "type": type(exc).__name__, "phase": phase}
```

**Archivo a editar (2):** `backend/services/agent_completion_internal.py`, `except` del camino legacy de `_attempt_state_change` (`return` en `:547`) — el diff está en el bloque de F3, punto (2).

**Por qué es backward-compatible (las dos):** hoy **nadie lee `reason` en la rama de error** — `_logged` (`completion_state.py`) hace `result.get("reason")` y persiste `None`, y el Paso 4 del motor B solo hace `setdefault("source", ...)`. Agregar la key no cambia ningún branch existente; solo deja de perder la información.

**Test que lo cubre:** casos 9 **y 9-bis** de `test_plan271_writer_routed.py` — provider ruteado que lanza ⇒ `{"ok": False, "reason": "transition_failed", ...}`; **y `AdoClient` del camino legacy que lanza (flag OFF o `project_name=None`) ⇒ también `reason="transition_failed"`** (E4).
**Y** `pytest backend/tests/test_plan79_safe_transition.py` **por archivo**: es el archivo dueño de esa función. Si tenía un assert de igualdad estricta sobre el dict de error, **se detiene la fase y se reporta** (§3-11) — la key nueva es correcta, pero el cambio de expectativa se documenta, no se silencia.

**Archivo de test a crear:** `backend/tests/test_plan271_writer_routed.py`
**Casos (13, v6: +11 y +12 por E24/E25) — los casos 1, 2 y 4 siembran el ticket CON `stacky_project_name` (D6):**
1. Proyecto ADO ⇒ `resolve_state_writer(ticket)` devuelve `StateWriter(kind="ado_client")`; `legacy_client_fn().update_work_item_state("4242", "To Do")` exactamente una vez, vía `_safe_transition`. **[v6, E23]**
2. Proyecto GitLab ⇒ `resolve_state_writer(ticket)` devuelve `StateWriter(kind="provider")` y se llama `update_item_state` del `GitLabTrackerProvider`, **y no** `AdoClient`. **[v6, E23]**
3. `resolve_state_writer` lanza `CapabilityUnavailable` ⇒ `{"skipped": True, "reason": "provider_unavailable"}` y `close_execution_with_publish` **no** lanza. **[v6, E23]**
4. Idempotencia: `provider.get_item` devuelve el estado ya igual al target ⇒ `{"skipped": True, "reason": "already_in_state"}` sin escribir.
5. Flag OFF ⇒ camino legacy: `AdoClient().update_work_item_state(4242, "To Do")` (byte-idéntico a hoy). **`AdoClient` va monkeypatcheado con un doble — ver §8-2: ningún test de este plan construye un cliente real.**
9-bis. **Camino legacy cuyo `AdoClient` (doble) lanza ⇒ `{"ok": False, "reason": "transition_failed", ...}`**, nunca `reason` ausente. **(E4, `:547`.)**
6. `ado_id` es `None` ⇒ `{"skipped": True, "reason": "no_ado_id"}` (`:523-524`, preservado).
7. **`project_name=None` con la flag ON ⇒ camino legacy `AdoClient`, NUNCA se llama `resolve_state_writer`** — **y el dict de éxito lleva `note="no_project_context"`** (C6 + D6: el camino legacy deja de ser mudo).
8. Éxito ruteado ⇒ el dict devuelto **no** trae `source` (para que la asignación de `target_source` del Paso 4 siga funcionando) y sí trae `writer="safe_transition"`. (C7.)
9. **El provider lanza al escribir ⇒ `{"ok": False, "reason": "transition_failed", ...}`** — nunca `reason` ausente ni `"unknown"`. **(D3, F3-bis-3.)**
10. **Todo dict devuelto por `_attempt_state_change` en los 9 casos anteriores tiene `reason ∈ ALL_FINAL_STATE_REASONS`** (salvo el éxito ruteado, que trae `ok=True`). **(D3, adelanto local de F9.)**
11. **[v6, E24] Proyecto GitLab con `target_state="To Do"` (fuera de las 4 claves de `_state_map_for_gitlab`)** ⇒ `{"ok": False, "reason": "transition_failed", ...}` — **nunca** una excepción sin capturar, nunca un `skipped` mudo, nunca un `ok=True` falso. El `FakeProvider` de este caso **no** puede ser el genérico: tiene que replicar el `state_map.get(logical_state) is None ⇒ levanta` de `GitLabTrackerProvider.update_item_state` real (`gitlab_provider.py:243-266`), para que el test pruebe el vocabulario y no sólo el ruteo.
12. **[v6, E25] Ticket con estado ACTUAL `"Done"` (fuera del `expected` del rol) y `target_state="To Do"`** ⇒ hoy escribe igual (`ok=True`) porque `_safe_transition` sólo compara `current == target`, no si `current` es un estado terminal fuera de flujo. Este caso **mide** el agujero de R18 (motor B sin `_origin_guard`); no lo cierra. **[v7, ADICIÓN ARQUITECTO menor]** El caso también afirma que, en ese mismo escenario, `_attempt_state_change` deja un `logger.warning("[exec=%s] escribiendo estado %s sobre %s, que no es el esperado por el rol — sin origin-guard, ver R18", ...)` — una línea, mismo patrón que ya usa C6/D6 para "sin `stacky_project_name`" (§F3). No cambia el `ok=True` ni ningún criterio binario: es visibilidad barata para el humano que audite logs mientras el R18 real (extender `_origin_guard` al motor B) se resuelve en el 272. Si en el futuro se agrega un guardia y este caso empieza a devolver `skipped`, actualizar este comentario y R18 — no borrar el caso.

**Comando exacto:**
```powershell
cd "$RAIZ\Stacky Agents\backend"; & $PY -m pytest tests/test_plan271_writer_routed.py -v
```

**Criterio de aceptación (BINARIO):**
- **`13 passed`** (los 10 del v3 + el 9-bis de E4 + el 11 y el 12 de E24/E25, v6).
- **Y** `test_e3_el_escritor_rutea_por_provider` de F0 pasa a **VERDE** (conteo de F0: `3 passed, 1 failed`).
- **Y** `pytest backend/tests/test_output_watcher.py` **sigue en `30 passed`** (§3.3) — **por archivo, hasta 3 reintentos si aparece `SQLITE_LOCKED`**. **Sin tocar ni un doble** (D6). Si baja de 30, es tuyo: se detiene la fase y se reporta; no se borra el assert.
- **Y** `pytest backend/tests/test_plan79_safe_transition.py` **sigue en `10 passed`** tras F3-bis-3.
- **Y** `pytest backend/tests/test_u2_publish_review_mode.py` en **`3 passed`**: su doble es `lambda **_kwargs: {...}` (`:158-162`), que acepta el kwarg nuevo `project_name` sin cambios.

**Flag:** `STACKY_FINAL_STATE_WRITER_ROUTED_ENABLED` — **default ON**. Cablear las 7 patas; agregar la key a `test_plan271_flags.py`.
**Impacto por runtime:** ninguno específico — el chokepoint es común a los 3. Fallback: flag OFF ⇒ `AdoClient` directo, idéntico a hoy.
**Trabajo del operador: ninguno.**

---

### F4 — Gate de publish preciso (cierra RC-2)

**Objetivo (1 frase):** que el estado deje de bloquearse cuando no había nada que publicar, conservando el bloqueo cuando la publicación se intentó y falló.
**Valor:** cierra la causa raíz secundaria. Va **después** de F3 para que la escritura que se desbloquea ya vaya al tracker correcto.

**Archivo a editar:** `backend/services/agent_completion_internal.py` — el bloque `:260-280` (Paso 4) y un helper nuevo.

```python
# Razones de publish que significan "no había nada que publicar" ⇒ el gate es espurio.
_PUBLISH_REASONS_SIN_NADA_QUE_PUBLICAR: frozenset[str] = frozenset({
    "html_output_path_missing",     # :228-234
    "already_terminal_no_html",     # :228-234 (rama already_terminal)
    "auto_publish_disabled",        # :236-238
    "ado_publisher_unavailable",    # :617-626
})


def _publish_gate_blocks(publish_result: dict) -> bool:
    """True si el gate de publish debe seguir bloqueando el cambio de estado."""
    if publish_result.get("ok"):
        return False                      # publicó bien: nunca bloquea
    if not _publish_gate_precise_enabled():
        return True                       # legacy: cualquier no-ok bloquea
    return publish_result.get("reason") not in _PUBLISH_REASONS_SIN_NADA_QUE_PUBLICAR
```

**Diff — reemplazar `:265-280`:**

```python
# DESPUÉS
if not effective_target:
    state_result = {"skipped": True, "reason": "not_requested"}
elif final_status == "completed" and _publish_gate_blocks(publish_result):
    state_result = {"skipped": True, "reason": "publish_not_ok",
                    "publish_status": publish_result.get("reason") or publish_result.get("event")}
else:
    state_result = _attempt_state_change(
        ticket_id=ticket_id, target_state=effective_target,
        execution_id=execution_id, project_name=stacky_project_name,   # ← F3
    )
    # C7 — asignación EXPLÍCITA, no setdefault: `target_source` es el origen de la
    # DECISIÓN y debe ganar. `_attempt_state_change` ya no devuelve `source` (F3).
    if isinstance(state_result, dict) and target_source:
        state_result["source"] = target_source
```

**Lo que NO se toca (invariantes duros):**
- El early-return de `review_mode_hold` (`:210-224`) **queda igual**. Es HITL deliberado. Su razón se vuelve visible en F5; su semántica no cambia.
- `publish.failed` y `publish.idempotent_replay` **siguen bloqueando**: ahí sí hubo un intento de publicación que no llegó.

**Archivo de test a crear:** `backend/tests/test_plan271_publish_gate.py`
**Casos (8) — tabla de verdad, uno por fila:**

| # | `publish_result` | flag | `_publish_gate_blocks` | `ado_state_change` esperado |
|---|---|---|---|---|
| 1 | `{"ok": True, ...}` | ON | `False` | `ok=True` |
| 2 | `{"skipped": True, "reason": "html_output_path_missing"}` | ON | `False` | `ok=True` ← **el bug** |
| 3 | `{"skipped": True, "reason": "auto_publish_disabled"}` | ON | `False` | `ok=True` |
| 4 | `{"skipped": True, "reason": "ado_publisher_unavailable"}` | ON | `False` | `ok=True` |
| 5 | `{"skipped": True, "reason": "already_terminal_no_html"}` | ON | `False` | `ok=True` |
| 6 | `{"ok": False, "event": "publish.failed", "reason": "ADO 400"}` | ON | `True` | `skipped`, `reason="publish_not_ok"` |
| 7 | `{"ok": False, "event": "publish.idempotent_replay"}` | ON | `True` | `skipped`, `reason="publish_not_ok"` |
| 8 | `{"skipped": True, "reason": "html_output_path_missing"}` | **OFF** | `True` | `skipped`, `reason="publish_not_ok"` (byte-idéntico a hoy) |

**Comando exacto:**
```powershell
cd "$RAIZ\Stacky Agents\backend"; & $PY -m pytest tests/test_plan271_publish_gate.py -v
```

#### F4-bis — `test_b2_transition_from_config.py` está ROJO HOY y este plan lo arregla (D4)

**No es opcional y no es scope creep: es la condición para que F7 pueda registrarlo sin romper el arnés.**

Estado real, medido (§3.3): **`5 failed`**, los cinco con el mismo error:

```
TypeError: _resolve_transition_state_from_config() missing 1 required keyword-only argument: 'final_status'
```

El test quedó desfasado cuando un plan posterior agregó el kwarg `final_status` a `_resolve_transition_state_from_config` (`agent_completion_internal.py:321`; el caller real lo pasa en `:250-256`). Los cinco tests (`:28,42,63,73,83`) llaman al resolver **sin** ese kwarg.

**Arreglo exacto (no se borra ni un assert, §3-11):** en las **cinco** invocaciones de `_resolver()(...)` agregar `final_status="completed"`, que es el valor con el que el caller real lo invoca en el camino feliz. Nada más. Si algún assert cambia de resultado con el kwarg puesto, **se detiene la fase y se reporta**: significaría que la semántica del resolver cambió y eso es un hallazgo, no un test a maquillar.

> **Por qué lo hace este plan y no "el dueño":** F7 lo **adopta** al arnés (`HARNESS_TEST_FILES`), y un archivo rojo registrado deja el arnés rojo para todos. Adoptarlo sin arreglarlo sería regalarle una rotura a la casa. Adoptarlo **arreglado** es exactamente el trabajo que este plan ya estaba haciendo sobre esa función.

**Criterio de aceptación (BINARIO):**
- `8 passed` en `test_plan271_publish_gate.py`.
- **Y** `test_rc2_sin_html_no_debe_bloquear_la_transicion` de F0 pasa a **VERDE** ⇒ los **4 de F0 quedan verdes**.
- **Y** `pytest backend/tests/test_b2_transition_from_config.py` pasa de **`5 failed` (hoy, §3.3)** a **`5 passed`** tras F4-bis. **Recién entonces** F7 lo registra en `run_harness_tests.sh` y `.ps1` (hoy NO está registrado; verificado: `grep -c` devuelve `0` en ambos).
- **Y** `pytest backend/tests/test_u2_publish_review_mode.py` en `3 passed`.
- **Y** `pytest backend/tests/test_output_watcher.py` **sigue en `30 passed`**: F4 desbloquea el modo A (`:618` cierra con `html_output_path=None`), así que si algún test asumía "modo A nunca cambia estado", **se detiene la fase y se reporta** — el comportamiento nuevo es el correcto, pero el cambio de expectativa se documenta explícitamente, no se silencia.

**Flag:** `STACKY_FINAL_STATE_PUBLISH_GATE_PRECISE_ENABLED` — **default ON**, justificación en §3.2. Cablear las 7 patas.
**Impacto por runtime:** el chokepoint es común a los 3. En Copilot/vscode_bridge el cierre suele venir por `output_watcher` (`:412`) con `html_output_path` presente ⇒ el caso 2 casi no aplica; en Codex/Claude CLI el cierre por `api/tickets.py:1386` puede venir sin HTML ⇒ ahí el fix se nota. Fallback: flag OFF ⇒ comportamiento actual, idéntico en los 3.
**Trabajo del operador: ninguno.**

---

### F5 — La razón del no-cambio se persiste (backend)

**Objetivo (1 frase):** que la razón por la que un ticket no se movió quede escrita en el `metadata_json` de la ejecución y se promueva en el payload de `/api/executions/<id>`.
**Valor:** cierra RC-3 del lado backend. Hoy la razón muere en `CloseResult` y en `SystemLog`.

**Archivos a editar:**
1. `backend/services/agent_completion_internal.py` — persistir antes del `return CloseResult(...)` (`:290-298`).
2. `backend/services/completion_state.py` — persistir dentro de `_logged` (`:164`, antes del `return result` de `:191`).
3. `backend/api/executions.py` — promover la key en `_with_outcome` (**`def` en `:65`, cuerpo `:75-92`** — los números del v3 en §2.0 estaban mal, E1; **localizalo con el grep de §3.4**, porque el plan 269 está en vuelo sobre este archivo, R15).

**Nombres exactos:**
- Key en `metadata_json`: **`final_state_outcome`**.
- Forma congelada: `{"applied": bool, "to": str|None, "source": str, "reason": str, "at": "<iso8601>Z"}`.
- Key promovida en el payload HTTP: **`final_state_outcome`** (mismo nombre, nivel superior).
- Helper en `agent_completion_internal.py`: `_persist_final_state_outcome(*, execution_id, result, source=None) -> None` — best-effort, nunca lanza, modelado sobre `_set_publish_hold` (`:419-431`), que ya hace este patrón de merge en `metadata_dict`.
- `completion_state.py` lo **importa** (import local dentro de `_logged`, para no acoplar el daemon).

```python
def _persist_final_state_outcome(*, execution_id: int, result: dict,
                                 source: str | None = None) -> None:
    """Plan 271 F5 — deja la razón del cambio (o del no-cambio) donde la UI ya mira.
    Best-effort: nunca lanza, nunca bloquea el cierre."""
    if not _reason_visible_enabled() or not execution_id:
        return
    try:
        with session_scope() as session:
            row = session.get(AgentExecution, execution_id)
            if row is None:
                return
            md = dict(row.metadata_dict or {})
            md["final_state_outcome"] = {
                "applied": bool(result.get("ok")),
                "to": result.get("to"),
                # C7 — el `source` EXPLÍCITO gana. `_safe_transition` hardcodea
                # {"source": "config"} en el éxito (task_states.py:178) y ese valor
                # NO es el origen de la decisión.
                "source": source or result.get("source") or "none",
                # D3 — PROHIBIDO "unknown": no es una razón, es un catálogo
                # incompleto. Tras F3-bis-3 la rama de error ya trae
                # `transition_failed`, así que este fallback solo cubre dicts
                # legacy; si alguna vez se dispara, F9 lo deja rojo.
                "reason": result.get("reason") or (
                    "ok" if result.get("ok") else "transition_failed"),
                "at": _utc_now_iso(),
            }
            row.metadata_dict = md
    except Exception:  # noqa: BLE001
        logger.debug("[exec=%s] persistir final_state_outcome falló (no crítico)",
                     execution_id, exc_info=True)
```

**Puntos de llamada exactos (4), con el `source` que le corresponde a cada uno:**

| # | Dónde | `result` | `source` |
|---|---|---|---|
| 1 | `agent_completion_internal.py`, antes del `return CloseResult(...)` de `:290` | `state_result` | `target_source` |
| 2 | `agent_completion_internal.py`, en el early-return de `review_mode_hold` (`:216-224`) | `{"skipped": True, "reason": "review_mode_hold"}` | `"none"` |
| 3 | `agent_completion_internal.py`, en `publish_execution_from_review` antes del `return` de `:493` | `state_result` | `"employee_config"` |
| 4 | `completion_state.py`, en `_logged` antes del `return result` de `:191` | `result` | `ctx.get("source")` |

**Edición en `api/executions.py` — C14, LEER ANTES DE ESCRIBIR.**
`_with_outcome` corta arriba de todo con `if not _outcome_badge_enabled(): return d` (**`:75-76`** — verificado; el "`:83-84`" de §2.0 del v3 era falso y apunta a un `import` dentro de un `try`), y esa flag es **ajena** (`STACKY_UI_OUTCOME_REASON_BADGE_ENABLED`, plan 254, default `True` en **`config.py:2085-2086`** — el v3 decía `:2070-2071`). Si insertás la promoción después de ese corte, tu feature queda gateada por una flag que este plan no controla. **Insertá antes del corte:**

```python
def _with_outcome(d: dict, dirty_ids: set[int] | None = None) -> dict:
    # Plan 271 F5 — la razón del cambio de estado NO depende de la flag del 254.
    meta_271 = d.get("metadata") or {}
    if _reason_visible_enabled() and isinstance(meta_271, dict):
        fso = meta_271.get("final_state_outcome")
        if isinstance(fso, dict):
            d["final_state_outcome"] = fso
    if not _outcome_badge_enabled():
        return d
    ...  # resto sin cambios
```
Agregá `_reason_visible_enabled()` en `api/executions.py` con el mismo patrón de instancia que `_outcome_badge_enabled` (**`:28-32`** — verificado; el "`:63-68`" del v3 era falso y apunta a la `def` de `_with_outcome`).

> `AgentExecution.to_dict` incluye `"metadata": self.metadata_dict` (`models.py:331` ✔ verificado), y `get_execution` (`:233`) devuelve `jsonify(_with_outcome(row.to_dict(...), dirty))` en `:243` ✔ ⇒ `d.get("metadata")` funciona en el listado **y** en el detalle.

> **Alcance de la promoción, declarado para que nadie lo "arregle de paso" (R15).** `GET /api/executions/history` (`executions_history`, `:442`) **no pasa por `_with_outcome`**: arma cada item **a mano** (`:538-559`) y **no incluye `metadata`** (verificado). Por lo tanto `final_state_outcome` **no llega** a ese endpoint, **y está bien así**: el único consumidor de este plan es el drawer, que se alimenta de `Executions.byId()` → `get_execution` → `_with_outcome` (verificado en `ExecutionDetailDrawer.tsx:55-57`), así que **F6 no queda inerte**. Cablearlo también en `executions_history` es alcance del **plan 269**, que ya está haciendo exactamente esa costura para su propio `run_verdict` (su C2). **No lo dupliques.**

> **Por qué acá y no un endpoint nuevo:** `_with_outcome` ya es el promotor canónico del plan 254, se aplica al listado y al detalle, y `ExecutionDetailDrawer.tsx:79-88` ya consume ese payload. Endpoint nuevo = superficie nueva sin necesidad.

**Archivo de test a crear:** `backend/tests/test_plan271_reason_persisted.py`
**Casos (8):**
1. Cierre con transición OK por el motor A ⇒ `metadata["final_state_outcome"] == {"applied": True, "to": "To Do", "source": "role", "reason": "ok", "at": <iso>}`. **(C7: `source` debe ser `"role"`, no `"config"`.)**
2. Cierre con `publish_not_ok` ⇒ `applied=False`, `reason="publish_not_ok"`.
3. Cierre en `review_mode_hold` ⇒ `applied=False`, `reason="review_mode_hold"`, `source="none"`.
4. Skip del motor A con `no_config` ⇒ `applied=False`, `reason="no_config"`.
5. Flag `STACKY_FINAL_STATE_REASON_VISIBLE_ENABLED=False` ⇒ la key **no** se agrega al metadata **ni** al payload (sin hueco ni error).
6. `GET /api/executions/<id>` devuelve `final_state_outcome` con la forma exacta.
7. **`STACKY_UI_OUTCOME_REASON_BADGE_ENABLED=False` + `STACKY_FINAL_STATE_REASON_VISIBLE_ENABLED=True` ⇒ `final_state_outcome` SIGUE presente** en el payload. **(C14.)**
8. `execution_id=None` ⇒ el helper no lanza y no escribe nada.

**Comando exacto:**
```powershell
cd "$RAIZ\Stacky Agents\backend"; & $PY -m pytest tests/test_plan271_reason_persisted.py -v
```
> Este archivo toca la DB. Si aparece `SQLITE_LOCKED`, **volvé a correr el mismo archivo** (hasta 3 intentos). No corras la suite completa.

**Criterio de aceptación (BINARIO):**
- `8 passed`.
- **Y** `pytest backend/tests/test_plan254_*.py` — **cada archivo por separado** — sigue verde.

**Flag:** `STACKY_FINAL_STATE_REASON_VISIBLE_ENABLED` — **default ON** (solo lectura). Cablear las 7 patas; `test_plan271_flags.py` ahora cubre **las 4**.
**Impacto por runtime:** ninguno. Fallback: flag OFF ⇒ ninguna key nueva, la UI no dibuja nada.
**Trabajo del operador: ninguno.**

---

### F6 — La razón se ve donde el operador ya mira (frontend)

**Objetivo (1 frase):** mostrar en el drawer de la ejecución, en castellano y con acción sugerida, por qué la incidencia se movió o por qué no.
**Valor:** cierra RC-3. El operador deja de necesitar leer logs.

**Archivos a crear:**
- `frontend/src/utils/finalStateOutcome.ts` — módulo **puro**.
- `frontend/src/utils/__tests__/plan271FinalStateOutcome.test.ts` — vitest sobre el módulo puro.
- `backend/tests/test_plan271_reason_catalog.py` — **el puente entre los dos idiomas (C8)**.

**Archivos a editar:**
- `frontend/src/types.ts` — campo opcional junto a `dirty_close_pending_review` (`:161`).
- `frontend/src/components/ExecutionDetailDrawer.tsx` — consumir el módulo y renderizar, junto al bloque `:79-88`.

> **Por qué un módulo `.ts` puro y no un test de render:** `@testing-library/react` y `jsdom` **no están instalados**. Mismo razonamiento que `frontend/src/utils/outcomeReason.ts:1-10` ya dejó escrito. **Copiá esa estructura.**

**Contenido del módulo — las 27 razones del catálogo (§2.4), ni una más ni una menos:**

```ts
// frontend/src/utils/finalStateOutcome.ts
// Plan 271 F6 — mapa puro `final_state_outcome.reason` → etiqueta + tono + acción.
// El catálogo canónico vive en backend/services/final_state_resolver.py
// (ALL_FINAL_STATE_REASONS). `test_plan271_reason_catalog.py` verifica que este
// archivo cubra TODAS las razones de ese conjunto: agregar una allá sin agregarla
// acá deja el test rojo. NO cambies las keys sin cambiar el conjunto de Python.

export type FinalStateTone = "exito" | "atencion" | "espera" | "error";

export interface FinalStateLabel { label: string; tone: FinalStateTone; action: string; }

export interface FinalStateOutcome {
  applied?: boolean; to?: string | null; source?: string; reason?: string; at?: string;
}

export const FINAL_STATE_REASON_LABELS: Record<string, FinalStateLabel> = {
  // ── se movió ────────────────────────────────────────────────────────────
  ok:                 { label: "Movida al estado configurado", tone: "exito", action: "" },
  already_in_state:   { label: "Ya estaba en ese estado", tone: "exito", action: "" },
  // ── falta configurar (acción del operador) ──────────────────────────────
  no_config:          { label: "Nadie configuró a qué estado mover", tone: "atencion", action: "Configuralo en Ajustes → Estados, en la tarjeta del rol" },
  no_final_state:     { label: "El rol no tiene estado de salida", tone: "atencion", action: "Elegí 'Al terminar OK, mover a' en Ajustes → Estados" },
  no_matrix_cell:     { label: "Sin regla para este tipo de incidencia", tone: "atencion", action: "Configuralo en Ajustes → Estados, en la tarjeta del rol" },
  not_requested:      { label: "Sin estado destino para este cierre", tone: "atencion", action: "Configuralo en Ajustes → Estados" },
  state_not_applicable: { label: "El estado configurado no aplica a este rol", tone: "atencion", action: "Revisá los estados del rol en Ajustes → Estados" },
  flag_off:           { label: "El movimiento automático está apagado", tone: "atencion", action: "Prendé 'estado final del empleado' en Ajustes → Arnés" },
  // ── decisión humana / espera (no hay nada que arreglar) ─────────────────
  review_mode_hold:   { label: "En espera de tu revisión", tone: "espera", action: "Aprobá la publicación para que se mueva" },
  human_moved_out_of_flow: { label: "La moviste vos: Stacky no la pisó", tone: "espera", action: "" },
  not_ok_status:      { label: "No terminó bien: no se movió", tone: "espera", action: "Revisá el resultado antes de moverla" },
  dev_build_gate_no_state: { label: "Sin compilación verde reciente: no se movió", tone: "espera", action: "Corré el build y volvé a intentar" },
  already_written_by_other_engine: { label: "Ya la había movido otro paso del cierre", tone: "espera", action: "" },
  // ── error operable ──────────────────────────────────────────────────────
  publish_not_ok:     { label: "No se publicó el comentario: no se movió", tone: "error", action: "Mirá el error de publicación y reintentá" },
  transition_failed:  { label: "El tablero rechazó el cambio de estado", tone: "error", action: "Mirá el detalle del error y verificá que el estado exista en el tablero" },
  no_project_context: { label: "Se movió, pero sin saber a qué tablero pertenece", tone: "atencion", action: "Revisá que la incidencia esté vinculada a un proyecto de Stacky" },
  no_ado_id:          { label: "La incidencia no tiene id en el tablero", tone: "error", action: "Vinculala al tablero" },
  no_ado_id_or_stacky_project: { label: "Falta el id en el tablero o el proyecto", tone: "error", action: "Revisá que la incidencia esté vinculada a un proyecto" },
  no_ticket:          { label: "No se encontró la incidencia", tone: "error", action: "Refrescá el tablero" },
  no_ticket_id:       { label: "La ejecución no está atada a una incidencia", tone: "error", action: "Revisá cómo se lanzó el empleado" },
  ticket_lookup_failed: { label: "No se pudo leer la incidencia", tone: "error", action: "Reintentá el cierre" },
  no_agent_type:      { label: "No se pudo saber qué rol terminó", tone: "error", action: "Revisá el empleado asignado a la incidencia" },
  no_target_or_id:    { label: "Faltó el estado destino o el id", tone: "error", action: "Configuralo en Ajustes → Estados" },
  // ── conexión con el tablero ─────────────────────────────────────────────
  provider_unavailable: { label: "No se pudo hablar con el tablero", tone: "error", action: "Revisá la conexión del tablero en Ajustes" },
  no_provider:        { label: "Sin conexión configurada al tablero", tone: "error", action: "Configurá la conexión en Ajustes" },
  ado_client_unavailable: { label: "Falta el conector del tablero", tone: "error", action: "Revisá la instalación" },
  exception:          { label: "Error inesperado al mover la incidencia", tone: "error", action: "Mirá el detalle de la ejecución" },
};

/** Un reason futuro NO rompe la UI: string crudo, tono neutro, nunca `undefined`. */
export function describeFinalState(o: FinalStateOutcome | null | undefined): FinalStateLabel | null {
  if (!o || !o.reason) return null;
  const known = FINAL_STATE_REASON_LABELS[o.reason];
  if (known) {
    if (o.reason === "ok" && o.to) return { ...known, label: `Movida a "${o.to}"` };
    return known;
  }
  return { label: o.reason, tone: "atencion", action: "" };
}
```

**Edición en `ExecutionDetailDrawer.tsx`** — junto al bloque de `:79-88`:
```tsx
// Plan 271 F6 — POR QUÉ la incidencia se movió (o no) al terminar.
const finalState = describeFinalState(
  content?.final_state_outcome ?? (metadata.final_state_outcome as FinalStateOutcome | undefined),
);
```
y renderizalo con las **cuatro** clases de tono. **C19 + D14:** `styles.toneEspera` **sí existe** (`ExecutionDetailDrawer.module.css:151`) — pero comparte **la misma regla** que `.toneAtencion`:

```css
/* ExecutionDetailDrawer.module.css:150-152 — HOY */
.toneAtencion,
.toneEspera {
  color: var(--warn);
}
```

O sea que la "cuarta rama" que el v2 manda agregar a `outcomeToneClass` (que está en **`:89-94`**, no en `:90-95`) es, tal cual, **un no-op visual**: el operador ve exactamente el mismo color para *"falta configurar"* (acción suya) y para *"en espera de tu revisión"* (nada que arreglar), que es justo la distinción que este plan existe para hacer. **Separalas:**

```css
/* DESPUÉS — .toneEspera deja de ser un alias de .toneAtencion */
.toneAtencion { color: var(--warn); }
.toneEspera   { color: var(--text-muted); }
```

> **E9 — `var(--text-secondary)` NO EXISTE, y el v3 lo declaraba real.** Medido: `grep -c -- "--text-secondary" frontend/src/theme.css` ⇒ **0**. Los tokens de texto reales son **`--text-primary`** (`theme.css:12`), **`--text-muted`** (`:13`) y **`--text-faint`** (`:14`), los tres re-declarados en el tema claro (`:182-184`). El token correcto y existente para "secundario" es **`--text-muted`** — usalo tal cual; el hedge del v3 (`--text-primary` + `opacity:.75`) era una solución peor a un problema inventado.
>
> **Tokens que sí existen y podés usar:** `--accent` (`:17`), `--success` (`:19`), `--warn` (`:20`), `--danger` (`:21`), `--text-primary`, `--text-muted`, `--text-faint`. La familia `--color-*` **no existe** en este tema. **Nunca un hex crudo** (lo caza `uiDebtRatchet`). `theme.css` está en `frontend/src/`, no en un subdirectorio.

> **Ratchet de deuda UI (obligatorio):** en esta fase no se crea ningún `.tsx` nuevo, así que alcanza con **no introducir `style={{}}` inline** en el drawer ni **HEX crudos** en el `.module.css`. Usá clases y tokens.

**Test de vitest (`plan271FinalStateOutcome.test.ts`) — 6 casos:**
1. `describeFinalState(null)` ⇒ `null`.
2. `describeFinalState({})` ⇒ `null`.
3. `describeFinalState({reason: "ok", to: "To Do"})` ⇒ `label` contiene `"To Do"`, `tone === "exito"`.
4. `describeFinalState({reason: "no_config"})` ⇒ `tone === "atencion"` y `action` **no vacío**.
5. `describeFinalState({reason: "inventado_futuro"})` ⇒ `label === "inventado_futuro"`, `tone === "atencion"`, no lanza.
6. **Estructural, no numérico:** toda entrada tiene `label` no vacío y `tone` en `{"exito","atencion","espera","error"}`. **(El v1 congelaba `length === 12`, que era el número equivocado.)**

**Test puente (`backend/tests/test_plan271_reason_catalog.py`) — 2 casos. `[ADICIÓN ARQUITECTO]` menor:**
```python
def test_toda_razon_del_backend_tiene_etiqueta_en_el_frontend():
    from pathlib import Path
    from services.final_state_resolver import ALL_FINAL_STATE_REASONS
    ts = (Path(__file__).resolve().parents[2] / "frontend" / "src" / "utils"
          / "finalStateOutcome.ts").read_text(encoding="utf-8")
    faltan = sorted(r for r in ALL_FINAL_STATE_REASONS if f"\n  {r}:" not in ts
                    and f" {r}:" not in ts)
    assert faltan == [], f"razones sin etiqueta en la UI: {faltan}"
```
más un test simétrico que afirma que el `.ts` no tiene keys huérfanas fuera de `ALL_FINAL_STATE_REASONS`. **Esto es lo que impide que vuelva a pasar C8.**

**Comandos exactos:**
```powershell
cd "$RAIZ\Stacky Agents\frontend"; npx vitest run src/utils/__tests__/plan271FinalStateOutcome.test.ts
cd "$RAIZ\Stacky Agents\frontend"; npx tsc --noEmit
cd "$RAIZ\Stacky Agents\backend"; & $PY -m pytest tests/test_plan271_reason_catalog.py -v
```
> **Correr vitest por archivo.** La corrida completa tiene contaminación cross-file conocida en este repo.

**Criterio de aceptación (BINARIO):**
- `6 passed` en vitest, `2 passed` en `test_plan271_reason_catalog.py`, `tsc --noEmit` con **0 errores**.
- **Y** los ratchets de UI compartidos, corridos delta contra su propio baseline — **[v7, E27] NO confíes en un número fijo: reglobeá primero** (`Get-ChildItem frontend/src/__tests__/*Ratchet*.test.ts` o el `ls` equivalente) — medido HOY da **9**, no 8, y el noveno (`devopsActionCatalogRatchet.test.ts`, agregado por el plan 267 después de que este documento fijara la lista) no estaba nombrado en ninguna versión anterior:
  `adhocModalRatchet.test.ts`, `copyDebtRatchet.test.ts`, `devopsActionCatalogRatchet.test.ts`, `devopsPollingRatchet.test.ts`, `formatDebtRatchet.test.ts`, `formDebtRatchet.test.ts`, `motionDebtRatchet.test.ts`, `uiDebtRatchet.test.ts`, `undoConfirmRatchet.test.ts`.
  Correr **uno por uno** (`npx vitest run src/__tests__/<archivo>`), nunca la suite completa. **[v7, E27] Baseline declarado, no "verde" a secas:** `uiDebtRatchet.test.ts` está **rojo HOY, antes de tocar una línea de F6** — `ExecutionDetailDrawer.module.css` tiene **23** hex contra el baseline congelado de **21** (`uiDebtBaseline.json`), deuda de los planes 254/269, no de este plan. **El criterio no es "9 en verde": es que ninguno de los 9 nombre como ofensor un archivo que F6 haya tocado, y que el hex de `ExecutionDetailDrawer.module.css` siga en 23 después de F6** (la edición de F6 usa `var(--text-muted)`, un token existente, nunca un hex nuevo — así que no debería moverse; si se mueve, es tuyo). Cualquier otro rojo ya venía de deuda ajena: se prueba con un worktree en el commit base y se declara con su conteo, igual que en §3.3.
- **Y** `describeFinalState` cubre las **27** razones: el test estructural (caso 6) más el puente de Python garantizan que el número no vuelva a divergir.

**Flag:** `STACKY_FINAL_STATE_REASON_VISIBLE_ENABLED` (cableada en F5). El frontend no lee la flag: si el backend no manda la key, `describeFinalState` devuelve `null` y no se dibuja nada. **Sin hueco ni error.**
**Impacto por runtime:** ninguno — es UI, común a los 3. **Trabajo del operador: ninguno.**

---

### F7 — Cierre: meta-tests, registro y huella de regresión

**Objetivo (1 frase):** garantizar que nada de lo agregado deja un meta-test rojo, que las 4 flags están completas en sus 7 patas, y que esta clase de error queda registrada.
**Valor:** evita el falso verde clásico (test nuevo que nadie corre porque no está en `HARNESS_TEST_FILES`).

**Checklist de archivos que DEBEN estar en AMBOS scripts al terminar (10):**
1. `tests/test_plan271_caracterizacion.py`
2. `tests/test_plan271_final_state_resolver.py`
3. `tests/test_plan271_flags.py`
4. `tests/test_plan271_role_fallback.py`
5. `tests/test_plan271_arbitro.py`
6. `tests/test_plan271_writer_routed.py`
7. `tests/test_plan271_publish_gate.py`
8. `tests/test_plan271_reason_persisted.py`
9. `tests/test_plan271_reason_catalog.py`
10. `tests/test_plan271_censo_escritores.py` (F8)
11. `tests/test_plan271_razon_del_catalogo.py` (F9)
12. `tests/test_b2_transition_from_config.py` — **preexistente y hoy NO registrado, y ROJO (`5 failed`)**. Este plan lo adopta **solo después de arreglarlo en F4-bis** (D4). Registrarlo rojo deja el arnés rojo para todos: si F4-bis no está hecho, **no se registra**.

> `backend/tests/plan271_helpers.py` **NO** se registra: no es un `test_*.py`.
> Formato: `.sh` ⇒ línea con dos espacios y **sin** comillas; `.ps1` ⇒ `"tests/..."` **con** comillas dobles dentro de `$HarnessTestFiles`.

**Huella de regresión (C20 + D17, ESQUEMA CORREGIDO — E5).** `docs/sistema/error_fingerprints.json` EXISTE (verificado, 49 KB) ⇒ la huella es obligatoria. **Pero el v3 mandaba "copiá el shape de las entradas vecinas, no inventes el esquema" y acto seguido inventaba el esquema.** Medido: el archivo es un **dict** con `schema_version` (=1), `description` y `fingerprints` (**42** entradas), y `tests/test_error_fingerprints_catalog.py:18` congela **NUEVE campos obligatorios**:

```python
_REQUIRED = ("id", "title", "class", "status", "log_pattern", "log_guarded",
             "killed_by", "guard_test", "self_test")
```

más: `status ∈ {"by_design", "open", "resolved"}`; `log_pattern` tiene que **compilar** con `re.compile`; y `self_test["matches"]` / `self_test["clean"]` tienen que **matchear y no matchear de verdad** contra ese patrón (`test_self_test_coherente`); y no puede haber caracteres de control crudos. Las entradas del v3 traían `{"id","patron","plan","fecha","guard_test"}`: **faltaban 6 de los 9** e **inventaban 3** (`patron`, `plan`, `fecha`). Escritas así, el DoD **rompe** ese test.

**Baseline OBLIGATORIO antes de tocar el archivo (§3.3):** `test_error_fingerprints_catalog.py` está en **`3 failed, 5 passed`** y `test_error_fingerprints_scan.py` en **`2 failed, 7 passed`**, por una huella ajena (`PLAN239-OUTLET-EN-BLANCO`, sin `self_test` y con `status: "guarded"`). **Arreglar esa huella es fuera de scope (§6.12).** El criterio de este plan es: **los mismos 3+2 fallos, ni uno más, y ninguna huella `FS-271-*` en los mensajes de error.**

**Las dos entradas, con los 9 campos reales:**

```json
{
  "id": "FS-271-NO-MATRIX-CELL",
  "title": "La incidencia no se mueve al estado configurado a nivel rol",
  "class": "state-transition-skipped",
  "status": "resolved",
  "log_pattern": "completion\\.matrix_transition.*no_matrix_cell",
  "log_guarded": true,
  "killed_by": "plan 271 (F1+F2: el motor A honra tracker_state_machine.<rol>.next_state_ok)",
  "guard_test": "backend/tests/test_plan271_role_fallback.py",
  "self_test": {
    "matches": ["action=completion.matrix_transition reason=no_matrix_cell source=config"],
    "clean": ["action=completion.matrix_transition reason=ok source=role"]
  }
}
```

```json
{
  "id": "FS-271-RAZON-FUERA-DEL-CATALOGO",
  "title": "El escritor de estado falla y no dice por que",
  "class": "state-transition-mute",
  "status": "resolved",
  "log_pattern": "final_state_outcome.*\"reason\": ?\"(unknown|error|failed)\"",
  "log_guarded": true,
  "killed_by": "plan 271 (F3-bis-3 + F9: transition_failed cableado en los dos escritores)",
  "guard_test": "backend/tests/test_plan271_razon_del_catalogo.py",
  "self_test": {
    "matches": ["final_state_outcome {\"applied\": false, \"reason\": \"unknown\"}"],
    "clean": ["final_state_outcome {\"applied\": false, \"reason\": \"transition_failed\"}"]
  }
}
```

> **Dos trampas de este archivo, las dos verificadas:** (1) el `log_pattern` es una **regex dentro de un JSON**, así que un `\.` va escrito `\\.` — un `\.` crudo hace fallar `json.loads` y rompe el catálogo **entero**; (2) el `self_test` no es decorativo: `test_self_test_coherente` corre `re.search(pattern, sample)` sobre cada `matches` y cada `clean`. **Corré `test_error_fingerprints_catalog.py` inmediatamente después de agregar las dos entradas**, antes de seguir.
>
> **Estas dos entradas están VALIDADAS, no propuestas.** Se corrieron los cinco chequeos del test contra ellas antes de escribirlas acá: los 9 campos presentes, `status` en el enum, `log_pattern` compila, cada `matches` **matchea** y cada `clean` **no matchea**. Copialas literales; si las tocás, volvé a correr esa validación.

**Comandos de verificación (corré los 5, uno por uno):**
```powershell
cd "$RAIZ\Stacky Agents\backend"; & $PY -m pytest tests/test_harness_flags.py -v
cd "$RAIZ\Stacky Agents\backend"; & $PY -m pytest tests/test_harness_flags_help.py -v
cd "$RAIZ\Stacky Agents\backend"; & $PY -m pytest tests/test_plan271_flags.py -v
cd "$RAIZ\Stacky Agents\backend"; & $PY -m pytest tests/test_plan271_caracterizacion.py -v
cd "$RAIZ\Stacky Agents\backend"; & $PY -m compileall -q services api harness
```

**Criterio de aceptación (BINARIO):**
- `test_harness_flags.py` en **`56 passed`** y `test_harness_flags_requires.py` en **`9 passed`** (§3.3: hoy verdes ⇒ cualquier rojo es tuyo).
- **Y** en `test_harness_flags_help.py`: **ninguna key `STACKY_FINAL_STATE_*` ni en la lista `missing` del assert de `:35` ni en la lista `violations` del de `:76`**. **E3: el criterio NO es el conteo.** Ese archivo está rojo de fábrica por **79** faltantes ajenos, y `4 failed, 4 passed` sale igual escribas los 4 textos o ninguno — o sea que como gate no distingue nada. Pegá **los dos mensajes de assert** en el PR y comprobá que ninguna key del 271 aparece en ellos.
- **Y** `test_plan271_flags.py` en verde, **incluido `test_las_4_keys_tienen_ayuda_llana_y_pasan_los_cinco_chequeos` (el gate real de la ayuda llana), con su verificación de discriminación hecha y pegada** (borrar una entrada ⇒ rojo; reponerla ⇒ verde — §3.3bis).
- **Y** `test_plan271_caracterizacion.py` en verde y `compileall` sin salida.
- **Y** `test_error_fingerprints_catalog.py` en **`3 failed, 5 passed`** y `test_error_fingerprints_scan.py` en **`2 failed, 7 passed`** — los mismos rojos ajenos de §3.3, **sin ninguna huella `FS-271-*` en los mensajes** (E5).
- **Y** un `grep` de cada uno de los **12** nombres del checklist devuelve **≥1 hit en `.sh` y ≥1 hit en `.ps1`** (12 × 2 = **24 hits**, ni uno menos).
- **Y** los **4** tests de `test_plan271_caracterizacion.py` en **verde** (de `0 passed, 4 failed` en F0 a `4 passed` acá).
- **Y** `test_b2_transition_from_config.py` en **`5 passed`** (F4-bis) **antes** de aparecer en los scripts.

> **Alcance acotado a propósito.** El corpus es exactamente esos 12 archivos y esas 4 flags. Un rojo preexistente ajeno **no** es alcance de este plan: si aparece, se compara contra **§3.3** y, si no está ahí, se prueba con un worktree en el commit base y se declara con su conteo. Este criterio **no** dice "y si algo más queda rojo se arregla".

**Flag:** ninguna. **Impacto por runtime:** ninguno. **Trabajo del operador: ninguno.**

---

### F8 — `[ADICIÓN ARQUITECTO]` Censo ejecutable de escritores de estado

**Objetivo (1 frase):** que el repo sepa, y verifique en cada corrida, **cuántas** funciones escriben el estado de un work item y **quién es su plan dueño**.

**Por qué esta fase existe.** El v1 afirmó, con cuatro anclajes exactos, que *"conviven **dos** motores"*. El v2 lo corrigió a **cuatro** y congeló un allow-list de 6 entradas. **Son seis motores y nueve entradas** (D1). Dos versiones seguidas contaron mal, las dos veces con anclajes correctos, y las dos veces la crítica anterior no lo detectó porque **releyó en vez de correr**. Esta fase saca el censo de la cabeza de quien escribe el plan y lo mete en el repo. Es barata (un test AST, sin infraestructura nueva), determinista, idéntica en los 3 runtimes, y no agrega ni un clic al operador.

**Archivo a crear:** `backend/tests/test_plan271_censo_escritores.py`

#### Paso 0 — OBLIGATORIO: correr el censo ANTES de escribir el allow-list (D1)

**Nadie escribe el `dict` de memoria.** Primero se corre el censo y **se pega su salida en el PR**; el allow-list es esa salida más una etiqueta por línea. El v2 hizo lo contrario y por eso nació rojo.

> **E14 — el one-liner del v3 NO CORRÍA.** Llamaba a `_walk(...)` y `_is_writer(...)`, dos funciones que **nunca definía**: cualquier intento daba `NameError`. O sea que el "Paso 0 OBLIGATORIO", que es la mitigación entera de R12 y la lección central de D1, era **inejecutable como estaba escrito** — y por eso nadie lo corrió. Este script sí corre. Guardalo fuera del repo (en tu carpeta temporal, **no** en `backend/`) y corrélo con `& $PY <ruta>`:

```python
# censo271.py — MISMA regla que el test de F8 (v4: llamadas + DEFINICIONES).
import ast, pathlib, sys
ATTRS = {"update_item_state", "update_work_item_state"}
BACKEND = pathlib.Path(sys.argv[1]) / "backend"   # sys.argv[1] = "<$RAIZ>/Stacky Agents"

class V(ast.NodeVisitor):
    def __init__(self, rel): self.rel, self.stack, self.hits = rel, [], []
    def visit_FunctionDef(self, node):
        self.stack.append(node.name)
        if node.name in ATTRS:                      # ← E6: la DEFINICION tambien cuenta
            self.hits.append((f"{self.rel}::{node.name}", node.lineno, "def " + node.name))
        self.generic_visit(node); self.stack.pop()
    visit_AsyncFunctionDef = visit_FunctionDef
    def visit_Call(self, node):
        f, name = node.func, None
        if isinstance(f, ast.Attribute) and f.attr in ATTRS: name = f.attr
        elif isinstance(f, ast.Attribute) and f.attr == "_safe_transition": name = "_safe_transition"
        elif isinstance(f, ast.Name) and f.id == "_safe_transition": name = "_safe_transition"
        if name:
            cont = self.stack[-1] if self.stack else "<module>"
            self.hits.append((f"{self.rel}::{cont}", node.lineno, name))
        self.generic_visit(node)

agg = {}
for p in BACKEND.rglob("*.py"):
    s = p.as_posix()
    if any(x in s for x in ("/tests/", "/.venv/", "/venv/", "__pycache__")): continue
    v = V(p.relative_to(BACKEND).as_posix())
    v.visit(ast.parse(p.read_text(encoding="utf-8")))
    for key, lineno, name in v.hits: agg.setdefault(key, []).append((lineno, name))

for key in sorted(agg): print(f"{key:<62} {sorted(agg[key])}")
print("TOTAL ENTRADAS:", len(agg))
```
> **La regla del test y la del script tienen que ser la MISMA** (mismos `attr`, mismos nombres de `def`, misma exclusión, misma atribución a función contenedora). Si divergen, el Paso 0 deja de probar nada.

**Salida REAL, RE-VERIFICADA en la pasada del v4 corriendo el censo del v3 tal cual (9 entradas, mismos números de línea — el v3 acertó esto):**

```
api/tickets.py::_apply_task_state                              [(577, '_safe_transition')]
api/tickets.py::create_child_task                              [(4779, 'update_item_state'), (4781, 'update_work_item_state')]
api/tickets.py::finish_work                                    [(2078, 'update_item_state'), (2080, 'update_work_item_state')]
api/tickets.py::set_stacky_status_by_ado                       [(1490, 'update_item_state'), (1492, 'update_work_item_state')]
harness/task_states.py::_safe_transition                       [(173, 'update_item_state'), (175, 'update_work_item_state')]
harness/task_states.py::apply_task_start_state                 [(206, '_safe_transition')]
services/ado_provider.py::update_item_state                    [(82, 'update_work_item_state')]
services/agent_completion_internal.py::_attempt_state_change   [(536, 'update_work_item_state')]
services/completion_state.py::maybe_apply_state_transition     [(113, '_safe_transition')]
TOTAL ENTRADAS: 9
```

**Qué hace el test, exactamente (regla AMPLIADA en el v4 — E6):**
1. Recorre con `ast` todos los `.py` bajo `backend/` **excluyendo** `backend/tests/`, `backend/.venv/`, `backend/venv/` y `__pycache__`.
2. Marca todo `ast.Call` cuyo `func` sea un `ast.Attribute` con `attr in {"update_item_state", "update_work_item_state"}`, más toda llamada a `_safe_transition` (como `ast.Name` **o** como `ast.Attribute`).
3. **NUEVO (E6): marca también toda `ast.FunctionDef`/`AsyncFunctionDef` cuyo `name` esté en `{"update_item_state", "update_work_item_state"}`.** Sin esta regla el censo es **estructuralmente ciego al escritor de GitLab**: `services/gitlab_provider.py:228 update_item_state` escribe el estado en GitLab (label + cierre vía `self._client._request`) y **no aparecía** en las 9 entradas, porque es una `def` y su cuerpo no llama a ninguno de los dos nombres vigilados. El adaptador de ADO aparecía **sólo de casualidad**, porque su cuerpo sí llama a `update_work_item_state`. Un adaptador nuevo (Mantis, plan 217) entraría igual de invisible, y el KPI *"un séptimo escritor rompe CI"* sería falso justo para la clase de escritor más probable.
4. Atribuye cada hallazgo a la **función que lo contiene** — con un visitor que mantiene una pila de `FunctionDef`/`AsyncFunctionDef`, así que un método anidado se atribuye al método, no a la clase. Una `def` vigilada se atribuye **a sí misma**.
5. Compara el conjunto contra el allow-list **congelado en el propio test**, con el plan dueño de cada entrada:

**Salida REAL con la regla del v4, tal como la corrió el v4 contra `760ac455` (12 entradas):**

```
api/tickets.py::_apply_task_state                              [(577, '_safe_transition')]
api/tickets.py::create_child_task                              [(4779, 'update_item_state'), (4781, 'update_work_item_state')]
api/tickets.py::finish_work                                    [(2078, 'update_item_state'), (2080, 'update_work_item_state')]
api/tickets.py::set_stacky_status_by_ado                       [(1490, 'update_item_state'), (1492, 'update_work_item_state')]
harness/task_states.py::_safe_transition                       [(173, 'update_item_state'), (175, 'update_work_item_state')]
harness/task_states.py::apply_task_start_state                 [(206, '_safe_transition')]
services/ado_client.py::update_work_item_state                 [(926, 'def update_work_item_state')]
services/ado_provider.py::update_item_state                    [(81, 'def update_item_state'), (82, 'update_work_item_state')]
services/agent_completion_internal.py::_attempt_state_change   [(536, 'update_work_item_state')]
services/completion_state.py::maybe_apply_state_transition     [(113, '_safe_transition')]
services/gitlab_provider.py::update_item_state                 [(228, 'def update_item_state')]
services/tracker_provider.py::update_item_state                [(85, 'def update_item_state')]
TOTAL ENTRADAS: 12
```

> **[v5, E19] Y esto es la prueba de que ni el v4 se salvó — re-corrida HOY contra el HEAD real (`6f451db8`), no contra `760ac455`, da 13, no 12.** El v4 ya había mostrado que estimar de cabeza (11) fallaba contra correr el script (12); esta crítica re-corrió el MISMO script del v4, sin cambiarle una línea, y el número volvió a subir:

```
api/tickets.py::_apply_task_state                              [(577, '_safe_transition')]
api/tickets.py::create_child_task                              [(4856, 'update_item_state'), (4858, 'update_work_item_state')]
api/tickets.py::finish_work                                    [(2135, 'update_item_state'), (2137, 'update_work_item_state')]
api/tickets.py::set_stacky_status_by_ado                       [(1505, 'update_item_state'), (1507, 'update_work_item_state')]
harness/task_states.py::_safe_transition                       [(173, 'update_item_state'), (175, 'update_work_item_state')]
harness/task_states.py::apply_task_start_state                 [(206, '_safe_transition')]
services/ado_client.py::update_work_item_state                 [(926, 'def update_work_item_state')]
services/ado_provider.py::update_item_state                    [(81, 'def update_item_state'), (82, 'update_work_item_state')]
services/agent_completion_internal.py::_attempt_state_change   [(536, 'update_work_item_state')]
services/completion_state.py::maybe_apply_state_transition     [(113, '_safe_transition')]
services/gitlab_provider.py::update_item_state                 [(243, 'def update_item_state')]
services/tracker_provider.py::update_item_state                [(85, 'def update_item_state')]
services/tracker_write_router.py::write_state_for_ticket        [(155, 'update_work_item_state'), (157, 'update_item_state')]
TOTAL ENTRADAS: 13
```

La 13ª entrada, `services/tracker_write_router.py::write_state_for_ticket`, no existía en `760ac455` — la creó el **plan 270** (commit `77627239`, ya mergeado) como el punto único de resolución ADO/GitLab que hoy usan `set_stacky_status_by_ado` y `services/ticket_state_writeback.py`. Nótese además que los números de línea de `api/tickets.py` y de `gitlab_provider.py` **también** cambiaron (Motor D/E/F y el adaptador GitLab) — es la misma foto fechada de §3.4/E21, y aquí queda medida dos veces: al principio de esta crítica y al final, con el mismo script, sin tocarle una línea.

> **Y esto es la prueba de por qué el Paso 0 no es opcional, ahora en su cuarta recurrencia.** El v3 estimó de cabeza y contó 9 donde había que ampliar la regla; el v4 estimó 11 y el censo dio 12; esta crítica re-corrió el censo del v4 sin cambiarlo y dio 13. **Cuatro pasadas seguidas, corriendo el mismo tipo de comando, y las cuatro el número subió.** La lección no es "correlo una vez antes de escribir el allow-list": es que el allow-list **caduca con cada merge ajeno**, y el número que hay que confiar es el de la corrida más reciente, nunca el impreso en un documento. Escribí el `dict` copiando el bloque de arriba (13 entradas), no de memoria, y volvé a correr el script el día que se implemente esta fase — puede haber subido otra vez.

```python
# 13 entradas [v5, E19] = los SEIS motores de §2.1 (A..F) + los dos helpers del
# plan 79 + los DOS adaptadores + el Protocol del puerto + el cliente terminal
# de ADO + el router del plan 270. La letra/origen va escrito a propósito: el
# v1 contó DOS motores, el v2 CUATRO donde hay SEIS, el v3 censó UN adaptador
# donde hay CUATRO, el v4 estimó 11 donde había 12, y esta crítica re-corrió el
# script SIN CAMBIARLE UNA LINEA y dio 13 — el plan 270 (ya mergeado) agregó un
# escritor nuevo entre que el v4 midió y hoy. Ahora el repo lo sabe; igual
# VOLVÉ A CORRER el script antes de congelar el número: puede haber subido de
# nuevo si otro plan mergeó en el medio.
ESCRITORES_CENSADOS: dict[str, str] = {
    # ── escritor canónico y helper de arranque (plan 79) ────────────────────
    "harness/task_states.py::_safe_transition":            "plan 79 — el escritor canónico (lo usan A, B y C)",
    "harness/task_states.py::apply_task_start_state":      "plan 79 — estado al INICIAR (fuera del alcance del 271)",
    # ── los SEIS motores ───────────────────────────────────────────────────
    "services/completion_state.py::maybe_apply_state_transition": "MOTOR A — plan 208 + 271 F2/F2-bis",
    "services/agent_completion_internal.py::_attempt_state_change": "MOTOR B — plan 271 F3/F3-bis-2",
    "api/tickets.py::_apply_task_state":                   "MOTOR C — plan 79 + gate del 210 (el 271 NO lo modifica, §6.6)",
    "api/tickets.py::set_stacky_status_by_ado":            "MOTOR D — inline, ya parcialmente ruteado por el plan 270 vía tracker_write_router (el 271 NO lo modifica; unificación en el 272)",
    "api/tickets.py::finish_work":                         "MOTOR E — inline, ídem D (el v2 lo citó en §6.6 y NO lo censó; 272)",
    "api/tickets.py::create_child_task":                   "MOTOR F — estado de la TAREA HIJA recién creada, sin plan dueño (272)",
    # ── puerto, adaptadores y cliente terminal (E6): NO deciden, pero SÍ escriben ──
    "services/tracker_provider.py::update_item_state":     "PUERTO — Protocol (cuerpo `...`); acá para que un tracker nuevo no entre invisible",
    "services/ado_provider.py::update_item_state":         "ADAPTADOR ADO → AdoClient.update_work_item_state",
    "services/gitlab_provider.py::update_item_state":      "ADAPTADOR GitLab → label de estado + cierre del issue (el v3 NO lo veía)",
    "services/ado_client.py::update_work_item_state":      "CLIENTE TERMINAL ADO — el PATCH real de System.State (nadie lo había censado nunca)",
    # ── [v5, E19] agregado por el plan 270, mergeado DESPUÉS del commit base de este plan ──
    "services/tracker_write_router.py::write_state_for_ticket": "ROUTER — plan 270, resuelve ADO/GitLab para set_stacky_status_by_ado y ticket_state_writeback.py (ver §3.5 sobre F3 y este mismo router)",
}
```
6. Asserts:
   - `hallados - ESCRITORES_CENSADOS == set()`: *"Escritor de estado NUEVO sin censar: `<x>`. Agregalo al censo con su plan dueño, o rutealo por `_safe_transition`."*
   - `ESCRITORES_CENSADOS - hallados == set()`: *"Escritor censado que ya no existe: `<x>`. Sacalo del censo."*
7. Un tercer test afirma que **`services/completion_state.py` importa `dev_build_verify`** — el invariante concreto de C2: si alguien vuelve a sacar el gate de build del motor A, el test se pone rojo con el nombre del plan que se rompe (210). **Hoy ese import NO existe** (verificado: `grep -c dev_build_verify backend/services/completion_state.py` ⇒ **0**), así que este test **nace rojo y se pone verde con F2-bis guardia 1**.

> **Verificación de que el censo es discriminante (obligatoria, E6).** Antes de dar F8 por hecho: comprobá que con la regla **sólo-llamadas** del v3 el censo devuelve **9** y `services/gitlab_provider.py::update_item_state` **no** está; con la regla del v4 devuelve **13** (no 12 — E19) y sí está (y aparecen también el Protocol, `ado_client` y el router del 270). Pegá los dos conteos en el PR. Es la prueba de que la ampliación atrapa un escritor real que antes se colaba — no una preferencia de estilo.
>
> **[v5, E19] Verificación adicional, obligatoria por ser la cuarta recurrencia:** correr el censo **el mismo día** en que se implementa esta fase, no confiar en el número de este documento. Si volvió a subir (otro plan mergeó de por medio), es exactamente el resultado que F8 existe para atrapar: se agrega la entrada nueva al `dict` de arriba con su etiqueta, en el mismo commit, y se sube el número en el criterio de aceptación de abajo y en la DoD (§7.3).

**Alcance del barrido, declarado (para que no se lo interprete):** el censo recorre **solo `backend/`**. `Stacky pipeline/`, `Stacky tools/`, `deployment/` y los `.ps1` **no** se barren, y hoy **no contienen escritores de `System.State`** (verificado en esta pasada). Extender el barrido fuera de `backend/` es alcance del 272; anotarlo acá evita que alguien "amplíe el censo de paso" y rompa CI con hallazgos de otro dominio.

**Comando exacto:**
```powershell
cd "$RAIZ\Stacky Agents\backend"; & $PY -m pytest tests/test_plan271_censo_escritores.py -v
```

**Criterio de aceptación (BINARIO) — [v5, E19] corregido de 12 a 13:** `3 passed` con el allow-list en **exactamente 13 entradas** (12 del v4 + `services/tracker_write_router.py::write_state_for_ticket`, del plan 270 ya mergeado), y esas 13 iguales a la salida del Paso 0 pegada en el PR **con la regla ampliada, corrida el mismo día de la implementación**. Si el censo encuentra una **decimocuarta entrada** que esta pasada no vio, **eso es el resultado, otra vez**: se la agrega al allow-list con su plan dueño **en el mismo commit**, se dice si es un **séptimo motor**, un helper o un **adaptador de tracker**, y se anota en §6 si merece su propio plan. **No se relaja el assert. El número de este documento es de referencia, no de confianza: la corrida del día de la implementación manda.**

> **AST, nunca regex.** Precedente del repo: un centinela textual sobre flags rompió el motor entero. El AST no confunde un string en un comentario con una llamada real.

---

### F9 — `[ADICIÓN ARQUITECTO]` Ninguna razón fuera del catálogo (centinela de contrato)

**Objetivo (1 frase):** que sea **imposible** que un escritor de estado devuelva un dict cuyo `reason` no esté en `ALL_FINAL_STATE_REASONS`.

**Por qué esta fase existe.** El titular de este plan es *"cero skip mudo"* y el KPI dice *"27 de 27 razones visibles"*. Y sin embargo, hasta el v2 inclusive, **el fallo más operable de todos — el tablero rechaza la escritura — era el único sin razón**: `_safe_transition` devolvía un dict sin `reason` (`task_states.py:180-184`) y el helper de F5 lo bautizaba `"unknown"`, un string que no está en el catálogo de Python ni en el mapa de TypeScript. El test puente de F6 **no lo detecta**, porque compara los dos catálogos entre sí y `"unknown"` no está en ninguno: los dos lados coinciden **en no tenerlo**. Es un falso verde perfecto. F3-bis-3 tapa el agujero conocido; **F9 impide que se abra otro**.

**Archivo a crear:** `backend/tests/test_plan271_razon_del_catalogo.py`

**Qué hace (3 tests, sin infraestructura nueva):**
1. **Runtime, motor A:** invoca `completion_state.maybe_apply_state_transition` con `patch_motor_a` en **todas** las combinaciones de F2 que producen skip o error (perfil vacío, `agent_type=None`, flag OFF, `final_status="error"`, provider que lanza, ticket sin `ado_id`) y afirma para cada retorno: `"reason" in out` **y** `out["reason"] in ALL_FINAL_STATE_REASONS`.
2. **Runtime, motor B:** ídem sobre `_attempt_state_change` con los 10 escenarios de `test_plan271_writer_routed.py` (`ticket_id=None`, lookup que lanza, `ado_id=None`, provider que lanza, flag OFF, `project_name=None`, ya escrito por el otro motor, …).
3. **Estático — ALCANCE CORREGIDO (E4).** `ast` sobre `services/completion_state.py`, `services/agent_completion_internal.py` y `harness/task_states.py`, **pero SÓLO sobre los `return` que están DENTRO de las funciones escritoras**: `maybe_apply_state_transition`, `_logged`, `_attempt_state_change`, `_safe_transition`, `apply_task_start_state`. Para todo `return` de un `ast.Dict` cuyas claves incluyan `"skipped"` u `"ok"`, exige que **también** incluya `"reason"` **o** que el valor de `"ok"` sea `True`. Mensaje: *"Retorno mudo en `<archivo>:<línea>`: un no-cambio de estado sin `reason` es un defecto del plan 271 (§3-4)."*

> **BASELINE MEDIDO, y por qué el alcance del v3 hacía el criterio insatisfacible.** Se corrió la regla del v3 (**archivos enteros**) contra el commit base: **28 `return` analizados, 4 violaciones**.
>
> | Violación | Qué es | Qué hacía el v3 |
> |---|---|---|
> | `harness/task_states.py:183` | `except` de `_safe_transition` — escritor real, sin `reason` | **la arreglaba** (F3-bis-3) ✔ |
> | `services/agent_completion_internal.py:547` | `except` del camino **legacy** de `_attempt_state_change` — escritor real, sin `reason` | **no la nombraba nunca** ⇒ F9 nacía rojo (E4) |
> | `services/agent_completion_internal.py:493` | `return` de `publish_execution_from_review`: el **sobre** del cierre, `"ok": bool(publish_result.get("ok"))` | **falso positivo** que la regla no puede distinguir (exige `ok` literal `True`) |
> | `services/agent_completion_internal.py:54` | `CloseResult.to_dict()`: el **sobre** del resultado, `"ok": self.ok` | **falso positivo**, ídem |
>
> O sea: el criterio `3 passed` del v3 era **inalcanzable** siguiendo el plan (arreglaba 1 de 4), y su escape ("agregá la razón al catálogo") no aplica a ninguna de las 3 restantes — `transition_failed` ya está en el catálogo, y los dos sobres no son decisiones de estado. Además el plan prohíbe explícitamente "agregar una excepción al centinela". **Acotar el barrido a las funciones escritoras elimina los dos sobres por construcción** (no por excepción), y F3/F3-bis-3 tapan las dos reales. Resultado esperado tras F3-bis-3: **0 violaciones**.

> **Por qué el test estático además del de runtime:** el de runtime prueba los caminos que hoy sabemos enumerar; el estático atrapa el `return` **nuevo** que alguien agregue el mes que viene. Los dos juntos son lo que convierte "cero skip mudo" de promesa en invariante.

**Comando exacto:**
```powershell
cd "$RAIZ\Stacky Agents\backend"; & $PY -m pytest tests/test_plan271_razon_del_catalogo.py -v
```

**Criterio de aceptación (BINARIO):** `3 passed`, con **0 violaciones** del test 3 y la lista de violaciones **pegada en el PR antes y después** de F3-bis-3 (de **4 a 0**: las 2 reales arregladas, las 2 falsas eliminadas por el acotamiento del alcance). Si el test 3 encuentra un retorno mudo **dentro de una función escritora** que este plan no previó, **se le agrega `reason` a ese `return` con una razón del catálogo, en el mismo commit**; si la razón que corresponde no existe, se la agrega a `ALL_FINAL_STATE_REASONS` **y al `.ts`**. **No se agrega una excepción al centinela ni se amplía la lista de funciones exentas.** **Prohibido usar `"unknown"`, `"error"`, `"failed"` o cualquier etiqueta genérica: si no sabés por qué no se movió, el plan no está terminado.**

**Flag:** ninguna (es un test). **Impacto por runtime:** ninguno. **Trabajo del operador: ninguno.**

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Probabilidad | Mitigación (concreta, en el plan) |
|---|---|---|---|
| R1 | **Proyectos que hoy dependen de que el nivel de rol NO transicione** cambian de comportamiento al prender F2 (lo que el 208 quiso evitar). | Media | El destino sale de una UI cuyo texto literal es *"a cuál mueve el ticket al terminar"* (`StatesConfigPage.tsx:102`). `_origin_guard` (`completion_state.py:121-161`) sigue impidiendo pisar un ticket movido a mano, y la flag permite volver atrás sin redeploy. |
| R2 | F4 provoca transiciones que hoy no ocurren ⇒ escritura nueva en el tracker real. | Media | Acotado a **4 razones enumeradas** en `_PUBLISH_REASONS_SIN_NADA_QUE_PUBLICAR`. `publish.failed`, `publish.idempotent_replay` y `review_mode_hold` **siguen bloqueando**. Los casos 6/7/8 de F4 lo prueban. |
| R3 | **Doble transición / carrera A vs B.** El motor B escribe **inline** (`agent_completion_internal.py:274`) y el motor A lo hace desde un **daemon** (`completion_dispatcher.py:100-121`) **encolado en `:172-181`, o sea ANTES**. Con la cola vacía el daemon drena de inmediato ⇒ el orden probable es **A primero, B después**. Con F2 el motor A pasa a escribir en el caso común, así que la superposición **aumenta**. | **Alta** (el v1 decía "no lo empeora" — falso; el v2 la mitigaba **en una sola dirección** — insuficiente, **D2**) | **Árbitro SIMÉTRICO**: F2-bis guardia 2 en el motor A **y** F3-bis-2 en el motor B, **el mismo helper `final_state_already_written`** (F1), verificado por los casos 7 y 8 de `test_plan271_arbitro.py`. Más `_safe_transition` idempotente (`task_states.py:164-168`) cuando los targets coinciden, y `final_state_outcome.source` que hace visible cualquier discrepancia. |
| R3-bis | **Doble transición A vs C/D/E/F**, en los caminos `PATCH /by-ado/<id>/stacky-status` y `finish_work`. El árbitro **no** los cubre (§2.1bis). | Media | **Aceptada y declarada, no mitigada.** Ya ocurre hoy y este plan no toca `api/tickets.py` (§6.6), así que no la agrava en esos caminos. F8 la deja **censada y visible**; extender el árbitro a C, D, E y F es alcance del **plan 272** (§6.1). |
| R4 | **Regresión del gate de build del plan 210**: el motor A pisa la degradación que el motor C acaba de aplicar. | **Alta sin F2-bis** | **F2-bis guardia 1** replica `dev_build_verify.gate_final_state` en el motor A, y **F8 test 3** deja rojo el repo si alguien lo saca. |
| R5 | **[v6, E23]** `resolve_state_writer` lanza `CapabilityUnavailable` (envuelve el `TrackerConfigError` interno) en un proyecto GitLab con `STACKY_GITLAB_ENABLED=false` y rompe el cierre. | Baja | F3 lo envuelve en `try/except` ⇒ `{"skipped": True, "reason": "provider_unavailable"}`. El cierre nunca falla (caso 3 de F3) y la razón se muestra (F6). |
| R6 | ~~F3 rompe `test_output_watcher.py`~~ | **DESCARTADA (D6).** El v2 la declaraba *"Confirmada, no es hipótesis"*; **es falsa.** | `_mk_ticket` (`test_output_watcher.py:87-107`) no setea `stacky_project_name`, que es de donde `close_execution_with_publish:135` lo lee ⇒ `project_name is None` ⇒ camino legacy ⇒ el doble actual alcanza. **No se toca ni un doble.** Baseline `30 passed` en §3.3; F3 tiene que dejarlo en 30. |
| R6-bis | **El fix de F3 es INERTE para todo ticket sin `stacky_project_name`**: en un proyecto GitLab sigue escribiendo en ADO con el `iid` de GitLab. Es el bug que F3 dice cerrar, sobreviviendo en su propio camino. | **Alta** (destapada por D6) | **Parcial y declarada.** F3 lo hace **visible** (`no_project_context`, razón 27, caso 7 de `test_plan271_writer_routed.py`) pero **no lo repara**: repararlo es poblar `stacky_project_name` en el alta del ticket, territorio de `_startup_sync` y del **plan 272** (§6.10). El KPI de paridad se sinceró en §1 para no prometer lo que no cumple. |
| R7 | `SQLITE_LOCKED` hace flaky a F5 y F2-bis. | Alta | §3-9 y repetido en cada fase: correr **por archivo**, reintentar hasta 3 veces el mismo archivo, nunca la suite completa. |
| R8 | El implementador toca `run_harness_tests.ps1` con la sintaxis del `.sh`. | Media | §3-10 y F7 dan la diferencia literal. El criterio de F7 exige **24 hits**, 12 por script. |
| R9 | El texto del `PlainHelp` rompe uno de los meta-tests. | Media | §3.1 pata 4 enumera las restricciones **reales** (verificadas en `test_harness_flags_help.py:44-52,63-70`), y F1 trae un texto ya medido campo por campo. |
| R10 | **[v5, E22] Colisión con el plan 270 — YA NO es hipotética.** El 270 está **mergeado** (`77627239`) y SÍ referencia `agent_completion_internal.py`: lo lee por AST en `test_plan270_state_write_ratchet.py::test_5_centinela_del_residuo_s5` y lo nombra por nombre y línea (`S5`, `:536`) más de diez veces en su propio documento, anticipando textualmente que **este** plan enrutaría `_attempt_state_change` por provider. | **Alta, medida (no ya "Media" ni hipotética)** | Frontera explícita conservada: **este plan no edita ni una línea de `api/tickets.py`** (§6.6). Pero SÍ edita `agent_completion_internal.py::_attempt_state_change`, y ESO es exactamente lo que el centinela S5 del 270 vigila. La colisión real, medida y con fix, es **E20/F3-bis-0** (nuevo, v5): el `test_5` se edita en el mismo commit que F3, siguiendo su propio mensaje de fallo. Los nombres `final_state_resolver.py` / `final_state_outcome` / `finalStateOutcome.ts` / las 4 flags `STACKY_FINAL_STATE_*` siguen sin existir hoy (re-verificado) y no colisionan por sí mismos — el punto de fricción es únicamente `_attempt_state_change`. **Orden de merge:** ya resuelto, el 270 llegó primero; no queda decisión pendiente. |
| R11 | El diagnóstico está errado y el problema real era `harness_defaults.env:33`. | Media | **F0-D** lo mide antes de escribir una línea de producción, y su salida va al PR. Aun si se confirma, el motor A sigue roto y F1/F2/F2-bis se justifican. |
| R12 | **El allow-list del censo vuelve a nacer mal** y F8 rompe CI el día 1 (le pasó al v2 con 6 entradas donde hay 9). | **Alta si se escribe de memoria** | **F8 Paso 0**: correr el censo **antes** de escribir el `dict` y **pegar su salida en el PR**. El allow-list es esa salida más una etiqueta por línea. Nunca al revés. |
| R13 | **El implementador escribe las 3 ayudas llanas que faltan y usa una palabra de la denylist** (`gate` es la trampa obvia, con una flag llamada `..._PUBLISH_GATE_PRECISE_ENABLED`), dejando `test_harness_flags_help.py` con **más** de sus 4 fallos ajenos. | **Alta sin los textos escritos** | **§3.1bis** trae los **4** textos literales, ya medidos campo por campo, y §3.3 fija el baseline exacto contra el cual comparar (`4 failed, 4 passed`, y ninguna key `STACKY_FINAL_STATE_*` entre las violaciones). |
| R14 | **Un `return` nuevo sin `reason`** reabre el skip mudo dentro de seis meses, sin que ningún test lo note (el puente de F6 no lo ve: `"unknown"` no está en ninguno de los dos catálogos). | Media | **F9** test 3, con el alcance acotado a las **funciones escritoras** (E4): todo `return` de dict con `"skipped"`/`"ok"` dentro de ellas debe traer `"reason"` salvo que `ok is True`. Baseline medido: **4 violaciones hoy → 0 tras F3/F3-bis-3**. |
| **R15** | **Colisión con el plan 269 sobre `api/executions.py`.** [v6, E26: corregido de "en vuelo" a "ya mergeado"] El 269 **ya está mergeado** (confirmado hoy: `grep -n "run_verdict" backend/api/executions.py` ⇒ presente en `:58,82,90,95`; el encabezado de este doc, línea 7, ya lo decía) y editó `list_executions()` y `executions_history()` (`:442`, items a mano `:538-559`); F5 de este plan edita `_with_outcome`. | **Media** (ya no "concurrente": el merge ya ocurrió y su costura ya se midió hoy) | **Frontera por símbolo, no por línea — y ya se ejerció.** (a) F5 ancla `_with_outcome` / `_outcome_badge_enabled` con el grep de §3.4: re-corrido hoy da `:129` / `:28` / `:139` (se movió de `:65` a `:129`, +64 líneas por el bloque de `run_verdict` que el 269 insertó entre medio — confirmado leyendo el archivo). (b) Son **funciones distintas** ⇒ no hubo colisión textual, sólo drift numérico, y el grep ya lo absorbió. (c) `final_state_outcome` **no** se cablea en `executions_history` (declarado arriba): esa costura sigue siendo del 269/272, no de este plan. (d) Las keys son disjuntas: el 269 promueve `run_verdict`, este plan `final_state_outcome` (0 hits cruzados, re-verificado hoy). **Ya no queda una decisión de orden de merge pendiente: re-correr el grep de §3.4 antes de editar es la única acción que falta.** |
| **R16** | **Un test de este plan escribe en el tracker REAL del operador.** F3 caso 5 dice *"camino legacy: `AdoClient().update_work_item_state(4242, "To Do")`"* sin decir que `AdoClient` va monkeypatcheado, y `_legacy_ado_client()` hace `from services.ado_client import AdoClient; return AdoClient()` de verdad. | Media | **§8-2 lo prohíbe por escrito y con un guard ejecutable**: ningún test de este plan construye un cliente real; `services.ado_client.AdoClient` y `services.tracker_write_router.resolve_state_writer` van parcheados en **todos** los casos, y un test del propio plan lo verifica. |
| **R17** | **[v6, E24] GitLab sólo entiende 4 claves lógicas (`functional`/`accepted`/`rejected`/`in_progress`, `gitlab_provider.py:109-117`), y la UI del operador enseña vocabulario ADO (`"To Do"`, `"Done"`...). Un `next_state_ok` GitLab que no sea una de esas 4 palabras — el caso común — hace que F3 devuelva `transition_failed` SIEMPRE para ese proyecto.** | **Alta, medida** (es el camino feliz para la mayoría de los proyectos GitLab, no un borde) | **Aceptada y declarada, no reparada en este plan.** Traducir vocabulario es territorio de `services/close_intent.py`, construido sólo para intenciones de CIERRE — extenderlo a estados intermedios es un cambio de diseño propio, candidato a **plan 272**. Este plan la deja **medida y vigilada**: caso 11 de `test_plan271_writer_routed.py`, KPI de §1 corregido para no prometer paridad completa, y la razón (`transition_failed`) es visible en el drawer (F6) en vez de fallar en silencio. |
| **R18** | **[v6, E25] El motor B no tiene un guardia de origen equivalente a `_origin_guard` del motor A: puede reabrir un ticket que un humano cerró o movió a propósito fuera del flujo, porque `_safe_transition` sólo compara `current == target`.** F4 (cierra RC-2) hace que el motor B escriba en más casos, subiendo la probabilidad de ejercitar este agujero preexistente. | **Media** (agujero viejo, probabilidad de disparo sube con F4) | **Aceptada y declarada, no mitigada — mismo patrón que R3-bis/R6-bis.** Extender `_origin_guard` (o un equivalente) al motor B es del **plan 272**, junto con la unificación de escritores (§6.1). Este plan la deja **medida y observable**: caso 12 de `test_plan271_writer_routed.py` documenta el comportamiento actual (escribe igual) para que un cambio futuro lo note en vez de sorprender, **y [v7] agrega un `logger.warning` en el momento en que ocurre** (mismo patrón que la advertencia de `no_project_context`), para que el operador tenga rastro en el log aunque este plan no bloquee la escritura. **No es una transición irreversible sin supervisión**: el tracker sigue siendo la fuente de verdad y un humano puede revertir el estado con el mismo clic con que lo movió la primera vez; lo que R18 documenta es una sorpresa evitable, no una pérdida de datos. |

---

## 6. Fuera de scope (explícito, para que nadie lo agregue "de paso")

1. **Unificar los SEIS escritores (motores A..F de §2.1) en uno solo.** Es el arreglo estructural correcto y ahora los seis están **censados** (F8), pero es una migración con riesgo propio: **plan 272**. Este plan deja **A y B** coherentes, **arbitrados en las dos direcciones** y observables, y **C, D, E y F** censados pero intactos (§2.1bis). El 272 debe: (a) extender el árbitro simétrico a C, D, E y F, (b) modelar `on_failure_state` (§F1) antes de cablear el resolver en el motor B, (c) darle plan dueño a D, E y F o eliminarlos, y (d) **garantizar `stacky_project_name` en todo ticket** (ver §6.10, R6-bis).
2. **Deduplicar `_infer_agent_type_from_filename`** (`agent_completion_internal.py:304-318`, `api/agents.py:1766-1767`, `services/agent_history.py:54-55`). Las tres copias coinciden para `technical`; no causó el bug.
3. **Construir la UI de la matriz `by_work_item_type` dentro de `StatesConfigPage`.** Es alcance del 208. Este plan hace que **no haga falta**.
4. **Cambiar la semántica de `review_mode_hold`.** HITL deliberado. Solo se hace visible.
5. **Transicionar en `needs_review`.** Exige revisión humana.
6. **`api/tickets.py` en cualquiera de sus formas** — `set_stacky_status_by_ado` (**empieza en `:1205`**, no en `:1487` como decía el v1; este número **no** se movió, verificado), `_apply_task_state:531` (**motor C**, tampoco se movió), el escritor inline (**motor D**, medido en `760ac455` en `:1489-1492`, **hoy `:1505/:1507` — E21**), `finish_work` (**motor E**, medido en `760ac455` en `:1751` con escrituras en `:2078,:2080`, **hoy `:1780` con escrituras en `:2135,:2137` — E21**) y `create_child_task` (**motor F**, medido en `760ac455` en `:4080` con las suyas en `:4779,:4781`, **hoy `:4157` con `:4856,:4858` — E21**). Territorio del 270 y del 272. **Este plan no edita ni una línea de ese archivo**, solo lo cita — pero ahora los **censa a los cuatro** (F8, hoy 13 entradas — E19), que es la diferencia entre "fuera de scope" y "no lo vimos". **Los motores E y F son exactamente lo segundo hasta esta versión. Re-localizá estos símbolos con el grep de §3.4 antes de citarlos: es el archivo que más se movió de todo el plan.**
7. **`deployment/harness_defaults.env`.** Snapshot derivado, ya divergente.
8. **Migrar `agent_workflow_configs.transition_state` al perfil del cliente.** El 216 lo declaró fuera de scope.
9. **Cambiar `STACKY_DETERMINISTIC_TASK_STATES_ENABLED` en `harness_defaults.env:33`.** F0-D lo **mide** y lo reporta; cambiarlo es una decisión del operador, no de este plan.
10. **Poblar `stacky_project_name` en los tickets que no lo tienen** (R6-bis, D6). Es la reparación de fondo del hueco de paridad, toca `_startup_sync` (`app.py:196,203`) y el alta de tickets, y tiene riesgo de migración propio: **plan 272**. Este plan solo lo hace **visible** (`no_project_context`).
11. **Arreglar los 4 fallos ajenos de `test_harness_flags_help.py`.** Los cuatro, medidos: las **79 flags sin ayuda llana** (`:35`), `STACKY_DEVOPS_COCKPIT_ENABLED` con `on_effect` de 316 chars (`:49`), `STACKY_EGRESS_SENTINEL_MAX_CHARS` con `off_effect` que no empieza con `"Si "` (`:60`), y la jerga de `STACKY_PLANS_BOARD_ENABLED` / `STACKY_CODE_INTEGRITY_ENABLED` / `STACKY_EVOLUTION_*` / `STACKY_EVAL_*` (`:76`). Están declarados en §3.3 como baseline. **Excepción única y justificada:** `test_b2_transition_from_config.py` **sí** se arregla (F4-bis), porque F7 lo **adopta** al arnés y adoptar un rojo rompe CI para todos.
12. **Arreglar la huella ajena `PLAN239-OUTLET-EN-BLANCO`** de `docs/sistema/error_fingerprints.json` (le falta `self_test` y su `status` es `"guarded"`, fuera del enum), que es la causa de los **3 failed** de `test_error_fingerprints_catalog.py` y los **2 failed** de `test_error_fingerprints_scan.py` (§3.3). Este plan **agrega dos huellas bien formadas** y **no toca** la del 239. Corresponde al dueño del 239 o a un plan de higiene.
13. **Cablear `final_state_outcome` en `GET /api/executions/history`.** Ese handler arma los items a mano y no incluye `metadata` (`api/executions.py:538-559`). El drawer no lo usa, así que este plan no lo necesita; la costura de ese endpoint es del **plan 269** (su C2). Ver R15.

---

## 7. Glosario, orden de implementación y DoD

### 7.1 Glosario

| Término | Significado en este plan |
|---|---|
| **Motor A / "matriz"** | `completion_state.maybe_apply_state_transition`, disparado por post-hook del `completion_dispatcher`, **asíncrono** (daemon). Lee `tracker_state_machine`. |
| **Motor B / "employee_config"** | `agent_completion_internal.close_execution_with_publish`, Pasos 3.5 y 4, **síncrono**. Lee `agent_workflow_configs[<filename>].transition_state`. |
| **Motor C / "determinista"** | `api/tickets.py:531 _apply_task_state` (plan 79 + gate del 210), **síncrono**, solo desde `set_stacky_status_by_ado:1473`. **Ya honra el nivel rol.** |
| **Motor D / "inline"** | `api/tickets.py::set_stacky_status_by_ado`, medido `:1489-1492` en `760ac455`, **hoy `:1505/:1507` (E21, re-localizar con §3.4)**, sin plan dueño. Este plan lo **censa** (F8) pero **no** lo modifica ni lo arbitra (§2.1bis); su unificación es del **272**. |
| **Motor E / "finish_work"** | `api/tickets.py::finish_work`, medido `:1751` con escrituras en `:2078,:2080` en `760ac455`, **hoy `:1780` con `:2135,:2137` (E21)**, sin plan dueño. **Censado, no modificado, no arbitrado** (§2.1bis). El v2 lo citó en §6.6 y aun así lo dejó fuera del censo (**D1**). |
| **Motor F / "tarea hija"** | `api/tickets.py::create_child_task`, medido `:4080` con escrituras en `:4779,:4781` en `760ac455`, **hoy `:4157` con `:4856,:4858` (E21)**. **Censado, no modificado, no arbitrado.** |
| **Árbitro simétrico** | El par de guardias `final_state_already_written(execution_id)` — una en el motor A (F2-bis) y **su gemela en el motor B** (F3-bis-2) — que usan **el mismo helper** de `final_state_resolver.py`. Un árbitro en un solo motor cubre un solo orden de carrera, y no es el probable (**D2**). |
| **Razón fuera del catálogo** | Cualquier `reason` que no esté en `ALL_FINAL_STATE_REASONS`. `"unknown"` es el caso patológico: no es una razón, es un catálogo incompleto. **F9** lo prohíbe corriendo (**D3**). |
| **Nivel rol** | `tracker_state_machine.<agent_type>.next_state_ok`. Lo que `StatesConfigPage.tsx` sabe escribir. |
| **Celda de matriz** | `tracker_state_machine.<agent_type>.by_work_item_type.<tipo>`. Solo `ClientProfileEditor.tsx:467-477` la escribe. **Celda parcial** = celda con `in_progress` pero sin `next_state_ok`. |
| **Chokepoint** | `close_execution_with_publish` (`agent_completion_internal.py:66`). |
| **Gate espurio** | Un `if` que bloquea una acción por una condición que no aplica al caso. |
| **Skip mudo** | Un `return {"skipped": True}` cuya razón no llega a ninguna superficie que el operador mire. |
| **7 patas** | Los 7 lugares que toca una flag nueva (§3.1). El "patrón triple" es un mito. |
| **Censo** | El allow-list ejecutable de F8. Un escritor nuevo sin censar deja el repo rojo. |

### 7.2 Orden de implementación (estricto, por dependencia)

```
F-1 (30 s, sin código) — correr los 11 greps de §3.4 [v5: +2, tickets.py y gitlab_provider.py] y anotar los números de HOY
 └─> F0 (rojo 0/4 + medición F0-D, sin prod)
 └─> F1 (resolver puro de 12 filas + catálogo de 27 + final_state_already_written + flag 1)
      └─> F2 (cablear motor A)              ← cierra RC-1  [F0 pasa a 2/4]
           └─> F2-bis GUARDIA 1 (gate 210, con cortocircuito developer)  [va JUNTO con F2]
 └─> F3-bis-0 [v6, E23] (baseline `test_plan270_state_write_ratchet.py` en 6 passed, ANTES de tocar `_attempt_state_change`)
      └─> F3 (writer ruteado vía `resolve_state_writer` + flag 2) ← cierra E-3 [F0 pasa a 3/4]
      ├─> F3-bis-0 cont. (re-correr el ratchet del 270: sigue en 6 passed SIN EDITAR NADA — E23; si no, corregir el diff de F3, no el test)
      ├─> F3-bis-1 (VERIFICAR que output_watcher NO se rompe — no se toca nada)
      ├─> F3-bis-3 (los DOS escritores dejan de fallar mudos: task_states:183 Y aci:547)
      └─> F4 (gate preciso + flag 3)        ← cierra RC-2   [F0 pasa a 4/4]
           ├─> F4-bis (arreglar test_b2_transition_from_config, hoy 5 failed)
           └─> F5 (persistir razón + flag 4)
                └─> ÁRBITRO SIMÉTRICO — necesita la key de F5:
                    ├─ F2-bis GUARDIA 2  (mitad A, completion_state.py)
                    └─ F3-bis-2          (mitad B, agent_completion_internal.py)
                     └─> F6 (mostrar razón + puente de catálogo) ← cierra RC-3
                          └─> F8 (censo ejecutable, Paso 0 = correrlo primero)
                               └─> F9 (ninguna razón fuera del catálogo)
                                    └─> F7 (cierre y registro)
```

**Verificación ítem por ítem de que ninguna fase depende de algo posterior:**
- **F-1 no construye nada**: corre los greps de §3.4 y deja los números de hoy en el PR. Cuesta 30 segundos y es lo único que impide repetir E1/E2 por cuarta vez. ✔
- F2 usa solo `final_state_resolver` (F1). ✔
- **F2-bis guardia 1** usa `dev_build_verify`, **preexistente** (`api/tickets.py:573-577` ya lo llama). ✔
- F3 usa `tracker_provider` y `_safe_transition`, ambos **preexistentes**. ✔
- **F3-bis-1 no construye nada**: verifica y anota el conteo. ✔
- **F3-bis-3** toca solo la rama de error de `_safe_transition`, sin dependencias. ✔
- F4 usa el kwarg `project_name` que **F3 ya agregó**. ✔ · **F4-bis** solo arregla un test preexistente. ✔
- F5 usa las razones que F2/F3/F4 ya producen. ✔
- **Las DOS mitades del árbitro** usan la key `final_state_outcome` que **F5 ya persiste** ⇒ por eso van después de F5. Mientras tanto son no-ops fail-open. ✔ **(El v1 no vio esta arista; el v2 la vio pero solo cableó una mitad — D2.)**
- F6 usa la key de F5 y `ALL_FINAL_STATE_REASONS` de F1. ✔
- **F9** necesita que F3-bis-3 ya haya tapado el agujero conocido y que el catálogo de F1 esté completo. ✔
- F8 solo lee código. ✔ · F7 solo verifica y registra, **después** de F4-bis. ✔

**Ninguna fase intermedia rompe el verde de la anterior (verificado contra §3.3):** F3 deja `test_output_watcher.py` en 30 (D6, no lo toca); F3-bis-3 deja `test_plan79_safe_transition.py` en 10 (agrega una key, no cambia branches); F2-bis deja `test_plan210_state_gate.py` en 16 (replica el gate, no lo modifica); F4-bis **sube** `test_b2_transition_from_config.py` de 5 failed a 5 passed; F5 no toca `test_plan254_*`; F6 no crea `.tsx` nuevos.

**F1+F2+F2-bis(guardia 1) se pueden entregar solas** y ya cierran el bug reportado sin regresionar el plan 210. F3..F9 son el resto de la deuda.

### 7.3 Definition of Done

- [ ] **F0-D**: salida de los 4 comandos de medición pegada en el PR, con una línea de interpretación.
- [ ] `test_plan271_caracterizacion.py`: `0 passed, 4 failed` al terminar F0 (fallando **por su assert**, no por `SQLITE_LOCKED` — E12) → **`4 passed`** al terminar F7.
- [ ] `test_plan271_final_state_resolver.py`: **19 passed** (12 filas de la tabla incluidas las 2 de E7 + 2 borde + `len(ALL_FINAL_STATE_REASONS) == 27` + `"unknown" not in ...` + `PRECEDENCE` + `REASONS ⊆ ALL` + los 2 de `final_state_already_written`).
- [ ] `test_plan271_role_fallback.py`: **10 passed** (incluye el caso 6-bis: flag OFF + matriz con estado final ⇒ **transiciona**, para que apagar esta flag no regresione el 208 — E7).
- [ ] `test_plan271_arbitro.py`: **8 passed** (4/8 tras la guardia 1; los 8 tras F3-bis-2).
- [ ] `test_plan271_writer_routed.py`: **13 passed** (los 10 del v3 + el 9-bis de E4 + el 11 de E24 [GitLab con estado fuera de vocabulario ⇒ `transition_failed`] + el 12 de E25 [motor B sin origin-guard, medido]).
- [ ] **[v6, E23] `test_plan270_state_write_ratchet.py` (F3-bis-0):** corrido ANTES de F3 en `6 passed` (baseline); corrido DESPUÉS de F3, **sigue en `6 passed` SIN NINGÚN CAMBIO al archivo** — `test_5_centinela_del_residuo_s5` pasa tal cual porque el diff de F3 rutea por `resolve_state_writer` y no referencia `get_tracker_provider`/`tracker_type`/`_provider_for_ticket` dentro de `_attempt_state_change`. Si `test_5` falla, NO se edita: se detiene la fase y se corrige el diff de F3 (§3 principio 11).
- [ ] `test_plan271_publish_gate.py`: 8 passed.
- [ ] `test_plan271_reason_persisted.py`: 8 passed.
- [ ] `test_plan271_reason_catalog.py`: 2 passed, sobre **27** razones.
- [ ] `test_plan271_censo_escritores.py`: 3 passed, con el allow-list de **13 entradas** (**[v5, E19] corregido de 12 a 13**: los 6 motores + 2 helpers del 79 + puerto + 2 adaptadores + el cliente terminal de ADO + el router del plan 270 `tracker_write_router.py::write_state_for_ticket`) — **y los DOS conteos del Paso 0 pegados en el PR, corridos el día de la implementación** (regla sólo-llamadas ⇒ 9 y sin GitLab; regla ampliada ⇒ 13 y con GitLab + ado_client + el router). Si el censo encuentra una 14ª entrada, se agrega con su etiqueta en el mismo commit — a esta altura es la cuarta vez que el número sube entre versiones, así que no re-correrlo el día de la implementación es la causa más probable de que F8 nazca rojo.
- [ ] `test_plan271_razon_del_catalogo.py` (**F9**): 3 passed, con la lista de violaciones del test 3 **de 4 a 0**, pegada antes y después. **Ningún `reason` fuera de `ALL_FINAL_STATE_REASONS`; cero apariciones de `"unknown"`.**
- [ ] `test_plan271_flags.py`: las 4 keys con `default is True`, en `_CATEGORY_KEYS["flujo_funcional"]`, con línea `=true` en `harness_defaults.env`, **en `PLAIN_HELP` y pasando los 5 chequeos aplicados localmente** (§3.3bis), **sin `requires=`** (§3.1 pata 8). **Y la verificación de discriminación hecha**: borrar una entrada de `PLAIN_HELP` ⇒ **rojo**; reponerla ⇒ verde; las dos salidas en el PR.
- [ ] `plan271FinalStateOutcome.test.ts`: 6 passed. `npx tsc --noEmit`: 0 errores. **[v7, E27]** Reglobeado `frontend/src/__tests__/*Ratchet*.test.ts` el día de la implementación (medido hoy: **9**, no 8 — no confíes en la lista de la sección F6, es de referencia) y los 9 corridos uno por uno **a través del junction, sin instalar nada**: ninguno nombra un archivo que F6 haya tocado como ofensor nuevo, y `ExecutionDetailDrawer.module.css` sigue en **23** hex (baseline 21, deuda de los planes 254/269, ya roja antes de F6 — no es un criterio de este plan ponerla verde). `.toneEspera` usa **`var(--text-muted)`** (existe; `--text-secondary` **NO** existe — E9).
- [ ] `test_harness_flags.py`: **56 passed**. `test_harness_flags_requires.py`: **9 passed**. En `test_harness_flags_help.py`: **ninguna key `STACKY_FINAL_STATE_*` ni en `missing` (`:35`) ni en `violations` (`:76`)** — el conteo `4 failed, 4 passed` se anota como contexto, **no es el criterio** (E3: no discrimina).
- [ ] `test_error_fingerprints_catalog.py`: **los mismos `3 failed, 5 passed`** de §3.3 y `test_error_fingerprints_scan.py` **`2 failed, 7 passed`** — **ninguna huella `FS-271-*` en los mensajes de error** (E5). Arreglar la del 239 es fuera de scope (§6.12).
- [ ] `test_b2_transition_from_config.py`: de **`5 failed` (hoy)** a **`5 passed`** (F4-bis), **antes** de registrarlo.
- [ ] `test_u2_publish_review_mode.py` **3 passed**, `test_output_watcher.py` **30 passed** (sin tocar ni un doble — D6), `test_plan79_apply_final.py` **6 passed**, `test_plan79_safe_transition.py` **10 passed**, `test_plan79_centinela_estados.py` **5 passed**, `test_plan210_state_gate.py` **16 passed`** — todos **por archivo**, comparados contra **§3.3**. Cualquier desvío se prueba preexistente con un worktree en el commit base **o se arregla**; no se borra el assert.
- [ ] Los **12** archivos del checklist de F7 registrados en **ambos** scripts (**24 hits**).
- [ ] `compileall` de `services/`, `api/` y `harness/` sin salida.
- [ ] Las 4 flags con línea `=true` en `backend/harness_defaults.env`. (Verificable: `grep "STACKY_FINAL_STATE_" backend/harness_defaults.env` ⇒ **4 líneas, todas `=true`**.)
- [ ] **Las DOS huellas de regresión registradas** en `docs/sistema/error_fingerprints.json` (**el archivo existe** — D17 —, así que no hay salida por "inexistente"), con el shape copiado de las entradas vecinas.
- [ ] **Smoke manual (una vez, el operador o el implementador):** con un proyecto que tenga `tracker_state_machine.technical.next_state_ok = "To Do"` y **sin** `by_work_item_type`, correr el Analista Técnico sobre una incidencia y verificar (a) en el tracker que quedó en `To Do`, (b) en el drawer que dice **“Movida a "To Do"”**, y (c) que el `System.State` **no** cambió dos veces (una sola escritura, comprobable en el historial del work item). **(c) es la prueba de campo del árbitro simétrico: con el árbitro en un solo motor, este paso fallaba (D2).** **Este es el ÚNICO paso del plan que toca un tracker real, y lo decide el operador (§8-2).**
- [ ] **§8 cumplido:** ningún test construyó un cliente de tracker real (guard de §8-2 en verde); `final_state_outcome` no persiste `error` ni texto libre (§8-1); el `%s` del `logger.warning` de F3 pasa por el enmascarado (§8-3).

---

## 8. `[ADICIÓN ARQUITECTO]` Datos personales, retención y prohibición de escribir en un tracker real

**Por qué esta sección existe.** Este plan hace dos cosas sensibles que ninguna versión anterior evaluó: **cambia lo que Stacky escribe en el tablero de terceros del operador** (ADO/GitLab) y **persiste 27 razones que después se muestran en la UI**. Riesgo evaluado: **MEDIO**, mitigable con tres reglas que ya son casi ciertas por diseño y sólo faltaba escribir.

### 8-1. Qué se persiste, y qué NO — el diseño ya es correcto, queda congelado

La forma de `final_state_outcome` está **cerrada**: `{"applied": bool, "to": str|None, "source": str, "reason": str, "at": iso8601}`.

| Campo | Contenido | ¿Puede arrastrar datos personales? |
|---|---|---|
| `applied` | bool | No |
| `to` | nombre de un estado del tablero, salido de la config del operador (`"To Do"`) | No |
| `source` | uno de `caller`/`matrix`/`role`/`employee_config`/`none` | No |
| `reason` | **uno de los 27 identificadores** de `ALL_FINAL_STATE_REASONS` | No — es un enum cerrado, y **F9 lo verifica corriendo** |
| `at` | timestamp | No |

**Lo que queda EXPLÍCITAMENTE fuera, y es una decisión, no un olvido:** `_persist_final_state_outcome` **no** copia `result["error"]` (el `str(exc)` del tracker), **ni** `result["type"]`, **ni** el título o la descripción del ticket, **ni** `ado_id`. Un `str(exc)` de ADO/GitLab puede traer una URL con query string, el nombre del usuario del tablero o un fragmento del cuerpo de la respuesta — nada de eso entra al `metadata_json` ni al payload HTTP. **Prohibido agregar un campo de texto libre a esta forma**: si hace falta más detalle para depurar, va al log (§8-3), no al registro que la UI muestra.

**Retención, declarada:** `final_state_outcome` vive **exactamente lo que vive la fila `AgentExecution`** que lo contiene — no crea un almacén nuevo, no crea un archivo, no crea una tabla, y se borra cuando se borra la ejecución. Al ser un enum cerrado más un nombre de estado y un timestamp, **no requiere política de retención propia**. Este párrafo es la declaración: si una versión futura mete texto libre acá, deja de ser cierto y hay que revisarlo.

**Superficie de UI:** `describeFinalState` tiene un fallback que renderiza el `reason` **crudo** si no lo conoce (`{ label: o.reason, ... }`). Con el catálogo cerrado y F9 vigilándolo eso nunca debería tener contenido arbitrario, pero es defensa en profundidad barata: **sanitizá antes de renderizar** — recortá a 64 chars y quedate sólo con `[a-z0-9_]`, cualquier otra cosa se muestra como `"Motivo no reconocido"`. Es una línea y cierra la única vía por la que un string del backend llegaría literal a la pantalla.

### 8-2. REGLA DURA: ningún test de este plan escribe en un tracker real

El v3 no lo decía en ninguna parte, y **F3 caso 5 lo invitaba**: *"camino legacy: `AdoClient().update_work_item_state(4242, "To Do")`"*, sin aclarar que `AdoClient` va doblado. `_legacy_ado_client()` hace `from services.ado_client import AdoClient; return AdoClient()` de verdad; sin parche, un test intenta una llamada saliente al ADO del operador.

**Regla, vinculante para todas las fases:**
1. **Todo** test de este plan parchea `services.ado_client.AdoClient` **y** `services.tracker_write_router.resolve_state_writer` (**[v6, E23]** — antes decía `services.tracker_provider.get_tracker_provider`, que ya no es el punto de entrada) antes de ejercitar cualquier camino de escritura. El `FakeProvider` de `plan271_helpers.py` cubre el camino ruteado — y, para el caso 11 (E24), debe replicar el `state_map.get(...) is None` real de GitLab, no aceptar cualquier string; el camino **legacy** necesita su propio doble y hasta ahora nadie lo había dicho.
2. **Guard ejecutable** en `test_plan271_writer_routed.py`: un test que afirma que, tras correr los 11 casos, **`services.ado_client.AdoClient` nunca se instanció sin parche** (contador en el doble; si el contador del doble no cuadra con la cantidad de casos legacy, es que alguno pasó por el cliente real).
3. `plan271_helpers.py` ya declara en su docstring *"Sin red, sin ADO real, sin GitLab real"*: eso pasa de comentario a **requisito verificado**.
4. **F0-D es de sólo lectura** y está bien así: los 4 comandos leen `harness_defaults.env`, `.env` y la DB viva, y el cuarto sólo agrega `reason` y `count(*)` — **no imprime títulos, descripciones ni identificadores de ticket**. No lo "mejores" agregando columnas: un `select` que traiga `title` o `description` de la base viva al PR sí sería una fuga.
5. El **único** contacto con un tracker real en todo el plan es el **smoke manual** del DoD, que lo corre el operador sobre una incidencia que él elige. Human-in-the-loop intacto.

### 8-3. El `str(exc)` del provider no se loguea crudo

F3 introduce `logger.warning("[exec=%s] provider no disponible: %s", execution_id, exc)`. `TrackerConfigError` trae texto de configuración, pero un fallo HTTP de ADO/GitLab puede traer URL con query string, usuario del tablero o cuerpo de respuesta. **Pasá ese `%s` por el enmascarado que el repo ya tiene** (el mismo que usan los flujos de secretos) en vez de interpolar `exc` directo, y **nunca** loguees el token ni la URL completa. Reusar, no reinventar: si el helper de enmascarado no aplica a este caso, se recorta a los primeros 200 chars y se anota el `type(exc).__name__`, que es lo que sirve para depurar.
