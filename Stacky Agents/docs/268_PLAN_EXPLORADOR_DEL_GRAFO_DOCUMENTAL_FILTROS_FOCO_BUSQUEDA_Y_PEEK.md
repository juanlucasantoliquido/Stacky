# Plan 268 — Explorador del grafo documental: filtros, foco por vecindario, búsqueda navegable, agrupación y peek de contenido

> **Estado:** CRITICADO — v3 → **v4** — 2026-07-28. **Veredicto del juez independiente sobre el v3: APROBADO-CON-CAMBIOS.** Los **9 bloqueantes** del v2 quedaron **CERRADOS los 9**, verificados uno por uno **compilando y corriendo** (no releyendo). Se halló **1 bloqueante nuevo** (N1: los bloques de cableado nunca mandan actualizar el bloque de `import` de `DocGraphView.tsx` ⇒ **5 × `TS2304`** compilando F1.3 verbatim) y esta versión lo corrige con un contrato de imports por fase.
> **Historial de veredictos:** v1 RECHAZADO (5 bloqueantes, fallas de **costura entre fases**) → v2 RECHAZADO (9 bloqueantes; **el v2 introdujo 5 propios**, cuatro otra vez en las costuras) → v3 **APROBADO-CON-CAMBIOS** (los 9 cerrados; 1 nuevo, de la misma familia pero mecánico) → v4 (esta).
> **Serie:** Documentación agéntica Obsidian (109 grafo backend → 111 graph view canvas → 114 staleness → **268 explorador**). Este plan NO toca el motor de grafo del backend: consume el mismo contrato `GET /api/docs/graph` del 109.
> **Pipeline:** este documento pasó `proponer`. Sigue `criticar-y-mejorar-plan` → `implementar-plan-stacky` → `supervisar-implementaciones-planes`.
> **Depende de:** Plan 109 (endpoint `GET /api/docs/graph`, contrato de `DocGraphResponse`/`DocGraphNode`/`DocGraphEdge`, flag `STACKY_DOCS_GRAPH_ENABLED`), Plan 111 (`forceLayout.ts`, `graphViewport.ts`, `DocGraphView.tsx`, pestaña "Grafo" en `DocsPage`), Plan 114 (campos `has_stale` / `edge.stale` / `stale_stats`).
> **Pedido literal del operador (2026-07-27):** *"Mejorar la visualización y la experiencia de uso del grafo de documentación, optimizando su estructura, legibilidad, navegación e interacción. Siempre que sea técnicamente viable, integrar Grapify directamente en la plataforma... La solución debe permitir explorar el grafo con facilidad mediante funciones como zoom, filtros, búsqueda, agrupación de nodos, navegación entre relaciones y acceso rápido al contenido asociado a cada elemento."*

---

## 0. CHANGELOG v3 → v4 (TERCERA pasada del juez, independiente — veredicto APROBADO-CON-CAMBIOS)

> **Método.** Juez distinto, corrida distinta, contexto limpio. No se releyó el v3: se **compiló**. Para las tres costuras (B3/B4/B5) se armó una **copia espejo del frontend** en un directorio temporal (`src` completo + `tsconfig.json` + junction a `node_modules`), se verificó que el espejo arranca **verde** (`tsc --noEmit` → **exit 0**), y recién entonces se pegaron los snippets del plan **verbatim** (extraídos con `sed` del propio `.md`, sin transcribir a mano) y se volvió a compilar. Ningún archivo del repo se tocó.
>
> ### Los 9 bloqueantes del v2: **CERRADOS los 9** (evidencia corrida)
>
> | # | Qué exigía | Verificación de esta pasada | Estado |
> |---|---|---|---|
> | **B1** | intérprete real de backend | `Stacky Agents/.venv` **no existe**; `backend/.venv/Scripts/python.exe --version` → **Python 3.13.5**; `test_docs_api.py` → **10 passed**. El plan usa `backend\.venv\` en §6, F0.0, F0 y DoD. | **CERRADO** |
> | **B2** | `graphPalette.ts` compila | Extraído verbatim (69 líneas) al espejo → `tsc --noEmit` **exit 0**. `splitThemeBlocks` tiene cuerpo; el `TS2391` desapareció. | **CERRADO** |
> | **B3** | costura F0.6→F5 (`groups`) | Aplicadas las dos ediciones de F0.6 (`groups: string[]` en `interface Palette` + `readPalette` nuevo) → `tsc --noEmit` **exit 0**. El `TS2353` desapareció. | **CERRADO** |
> | **B4** | costura F1→F2/F5 | `activeMatchId` y `groupSlots` **declarados** en F1 + `EMPTY_GROUP_SLOTS` como constante módulo → **cero** `TS2552`. | **CERRADO** |
> | **B5** | costura F2→F3 (`setViewport`) | `setViewportRef`/`zoomInRef`/`zoomOutRef`/`fitRef` declarados en F1.3-3; F2.2-4 reescrito a `setViewportRef.current(...)` → **cero** `TS2304` por esos nombres. | **CERRADO** |
> | **B6** | ratchets rojos de fábrica | Medido en limpio: `uiDebtRatchet` **1 failed / 2 passed**, **2** archivos en `REGRESION` (`ExecutionDetailDrawer.module.css` 23>21, `RunReconciliationCard.module.css` 1>0); `motionDebtRatchet` **2 failed / 1 passed**, **7** archivos, **exactamente** los 7 que el plan nombra. Criterio **delta** en K7/G8/F0/DoD-3. | **CERRADO** |
> | **B7** | DoD-11 vs DoD-9 | El comando acotado a los 4 archivos propios da hoy **17** hits (14 en `DocGraphView.module.css` + 3 en el `.tsx`), **todos** cubiertos por la tabla de sustitución de F0.6 + I4 ⇒ 0 al cerrar. La deuda ajena son **32** hits en los 3 archivos nombrados (5 + 26 + 1), fuera de alcance. | **CERRADO** |
> | **B8** | DoD-12 no rompe el catálogo | `test_error_fingerprints_catalog.py` → **3 failed / 5 passed**, y `test_patrones_compilan` **PASA** (corrido solo: **1 passed**). El v4 **no toca** el `.json`; las clases sin firma de log viven en §10.2. | **CERRADO** |
> | **B9** | topes reales de `PlainHelp` | `test_harness_flags_help.py:44-48` confirmado: `what` **≤200** (y ≥10), `on_effect` ≤240, `off_effect` ≤240, `example` ≤300. Los 4 textos propuestos miden **146 / 181 / 93 / 71** — todos holgados. | **CERRADO** |
>
> ### El bloqueante NUEVO que introduce el v3
>
> - **N1 — BLOQUEANTE. Ningún bloque de cableado manda actualizar el `import` de `DocGraphView.tsx`, y por eso F1 no puede cerrar su propio criterio.** Aplicadas F0.6 **y** F1.3 verbatim sobre el espejo, `tsc --noEmit` sale con **exit 2** y estos **5 errores**:
>   ```
>   src/components/docs/DocGraphView.tsx(122,24): error TS2304: Cannot find name 'useReducer'.
>   src/components/docs/DocGraphView.tsx(122,35): error TS2304: Cannot find name 'graphExplorerReducer'.
>   src/components/docs/DocGraphView.tsx(122,57): error TS2304: Cannot find name 'INITIAL_EXPLORER_STATE'.
>   src/components/docs/DocGraphView.tsx(123,37): error TS2304: Cannot find name 'availableFilterOptions'.
>   src/components/docs/DocGraphView.tsx(125,28): error TS2304: Cannot find name 'applyGraphFilters'.
>   ```
>   El criterio de aceptación de F1 es `tsc --noEmit` con **0 errores** ⇒ **F1 no cierra**. Es exactamente la familia de B3/B4/B5 (costura que no compila), sobreviviendo en el único eslabón que nadie miró: el **encabezado** del archivo. Y no es solo F1: el plan da instrucción de import **dos veces en todo el documento** (`nodeIndexById` en F0.3 y el bloque de `graphPalette` en F0.6) y **nunca más**, mientras F2.2 usa `searchGraphNodes`/`matchAt`/`matchIdSet`/`centerOn`, F3 `zoomAtCenter`/`fitViewport`/`ZOOM_STEP`, F4.2 `neighborhoodOf`/`rankedNeighbors`/`resolveFocusId`, F5 `groupKeyOf`/`groupLabelOf`/`assignGroupColorSlots`/`collapseGroups`, F6.3 `previewExcerpt`/`DocGraphPeek` y F7 `minimapTransform`/`viewportRectInMinimap`/`shouldDrawEdge` — **ninguno importado por instrucción**. Un modelo menor que pega los bloques tal cual acumula un `TS2304` por símbolo en **seis** fases seguidas.
>   **Fix (verificado):** agregadas las 3 líneas de import que faltaban en el espejo → `tsc --noEmit` **exit 0**. El v4 canoniza el fix en **[ADICIÓN ARQUITECTO #3]**: una **tabla de imports por fase** al principio de §6, obligatoria, más un grep-gate que falla si un símbolo se usa sin importar.
>
> ### Importantes y menores corregidos en el v4
>
> - **IMPORTANTE — el comando de conteo de los ratchets devuelve el DOBLE de lo que la foto de F0.0 registra.** `npx vitest run … 2>&1 | grep -c "REGRESION"` da **4** (ui) y **14** (motion), no 2 y 7: **vitest imprime cada error dos veces** (una en el diff inline, otra en el resumen `Failed Tests`). La tabla de F0.0, K7, G8 y DoD-3 anotaban **2** y **7** (que son los archivos **distintos**) mientras prescribían ese `grep -c` como verificación del punto 3 ("el conteo no puede subir"). Un implementador que mide 4 contra un baseline de 2 concluye que **rompió algo** sin haber tocado nada: falso rojo sobre el gate más citado del plan. **Fix:** las dos cifras quedan explícitas y separadas (archivos distintos **2/7**; salida de `grep -c` **4/14**) y el criterio delta se ancla a la que el comando realmente devuelve.
> - **MENOR** — §10.2 decía "Estas **4** clases" con una tabla de **6** filas (se le sumaron la 5 y la 6 en el v3). Es el mismo error de conteo que I2 acababa de matar en F8. → dice **6**.
> - **MENOR** — la nota de B7 en DoD-11 decía que el comando del v2 "devuelve **32** hits": devuelve **49** (32 ajenos + 17 propios). El número operativo —32 de deuda ajena en 3 archivos— es correcto; se corrige el total.
> - **MENOR** — la tabla de B9 declaraba `what`=154 / `on_effect`=179 / `off_effect`=91; medido: **146 / 181 / 93**. Todos dentro de tope; se corrigen las cifras para que el implementador no persiga un número que no va a ver.
> - **MENOR** — el bloque de contrato de F1.1 trae `export const EMPTY_GRAPH: DocGraphResponse;` (declaración sin inicializador, inválida como código literal). Está **bien** porque F1.1 es un bloque de *contrato* según la regla que el propio v3 fijó en F0.6, pero se rotula explícito para que nadie lo copie y pegue.
>
> **[ADICIÓN ARQUITECTO #3] — Contrato de imports por fase de `DocGraphView.tsx` + grep-gate de símbolo sin importar (ver §6).** Cierra N1 de raíz y, sobre todo, impide que vuelva: el gate es un `grep` de 6 líneas, 100% read-only, cero trabajo del operador, idéntico en los 3 runtimes.

---

## 0-bis. CHANGELOG v2 → v3 (segunda pasada del juez, INDEPENDIENTE — todo verificado CORRIENDO)

> **Método.** Esta pasada **no releyó** el plan: ejecutó sus gates. Cada bloqueante de abajo trae el comando que lo produjo y su salida real. Motivo: en este repo hay un gotcha registrado de que **4 de 4 críticas hechas releyendo volvieron RECHAZADAS**, y el propio v2 metió bloqueantes invisibles a la lectura.
>
> **Lo que el v2 hizo BIEN y se conserva intacto** (verificado corriendo, no se re-discute):
> - **C1 quedó bien resuelto.** `grep -n "^\s*--" src/theme.css` confirma que los 13 tokens que `graphPalette.ts` pide (`--accent`, `--accent-hot`, `--success`, `--warn`, `--danger`, `--border`, `--text-primary`, `--text-muted`, `--bg-panel`, `--bg-elev`, `--agent-business`, `--agent-functional`, `--agent-custom`) **existen los 13 en el bloque oscuro (`:root`, líneas 3-164) y en el claro (`:root[data-theme="light"]`, líneas 172-244)**. El v3 **no** vuelve a pedir tokens fantasma. El diagnóstico del bug vivo también es exacto: `DocGraphView.tsx:52-69` lee 6 nombres `--color-*` que no existen y el `interface Palette` (líneas 40-50) tiene exactamente los 9 campos que F0.6 mapea.
> - **C6 quedó bien resuelto y se comprobó.** Desde `Stacky Agents/frontend`: `git ls-files -- "Stacky Agents/frontend/package.json"` → **0 archivos**; `git ls-files -- ":/Stacky Agents/frontend/package.json"` → **1**. Y `git diff --stat` **nunca** setea código de salida. El pathspec `:/` + `--exit-code` es el fix correcto por partida doble.
> - **Grapify:** `grep -rni "grapify\|graphify"` sobre el árbol → **0 hits**. El veredicto de §3 (inviable: son charts de Node.js, sin nodos ni aristas) queda **firme y cerrado**. No se re-discute.
> - **Anclajes:** se verificaron por símbolo (no por número) `DocGraphView.tsx` 52/71/77/85/89-95/97/100/106/108/111-112/122/135/148/149/151/261/266/305-306/316/357/406/417/422/446/459/463/464, `docGraphModel.ts` 8/13/19/38/127, `forceLayout.ts` 11/47/62/89/101/203, `graphViewport.ts` 20/21/23/30/35/43/55/91, `endpoints.ts` 3317/3356/3461, `DocsPage.tsx` 76/140/146/230, `config.py` 672-675, `harness_flags.py` 400/404/2280-2295, `harness_flags_help.py` 274-**279** (cierra en la 279, el v2 acertó), `test_harness_flags.py` 467, `test_harness_flags_requires.py` 120/316, `harness_defaults.env` 158-159, `api/docs.py` 53-61. **Todos OK.** Único drift: `--text-primary` está en la línea **12**, no en la 11 (M3).
>
> **Los 9 BLOQUEANTES del v2 (con la evidencia de haberlos corrido):**
>
> - **B1 — El intérprete de TODOS los comandos de backend no existe.** El v2 escribe, en la regla transversal de §6, en F0 y en F8: `# desde "Stacky Agents"` + `.venv\Scripts\python.exe -m pytest ...`. **`Stacky Agents/.venv` NO EXISTE.** Corrido: `.venv/Scripts/python.exe -m pytest backend/tests/test_docs_api.py -q` → `No such file or directory`. El intérprete real es **`Stacky Agents/backend/.venv/Scripts/python.exe` (Python 3.13.5)**; con él, `test_docs_api.py` da **10 passed**. Un modelo menor siguiendo el comando literal no puede correr **ni un solo** test de backend. **Fix:** ruta corregida en §6, F0 y F8, y advertencia de que el `backend/venv/` (sin punto) es Python **3.11.9** y NO se usa.
> - **B2 — El código de `graphPalette.ts` que el plan manda copiar NO COMPILA.** El bloque de F0.6 trae dos funciones **con** cuerpo (`allGraphTokenNames`, `definedTokenNames`) y una **sin** cuerpo (`splitThemeBlocks`). Compilado tal cual con el `tsc` del repo: `error TS2391: Function implementation is missing or not immediately following the declaration.` Como el gate de **toda** fase es `npx tsc --noEmit` con 0 errores, F0 no puede cerrar. **Fix:** `splitThemeBlocks` se entrega **con cuerpo completo**.
> - **B3 — COSTURA F0.6→F5 rota: `interface Palette` nunca gana el campo `groups`.** F0.6 reescribe `readPalette` devolviendo `groups: GROUP_SLOT_TOKENS.map(...)` y dice "el campo `groups: string[]` se agrega **acá, en F0.6**", pero **nunca instruye editar el `interface Palette`** (`DocGraphView.tsx:40-50`, que hoy tiene 9 campos y ninguno se llama `groups`). Compilado el snippet verbatim: `error TS2353: Object literal may only specify known properties, and 'groups' does not exist in type 'Palette'.` **Fix:** F0.6 declara explícitamente la línea a agregar al `interface Palette`.
> - **B4 — COSTURA F1→F2/F5 rota: el efecto de sincronización de I2 referencia variables que en F1 no existen.** F1.3-3 manda escribir, **entero en F1**, un `useEffect` que lee `activeMatchId` (nace en F2) y `groupSlots` (nace en F5), con el comentario "null hasta F2 / Map vacío hasta F5" — pero **sin instrucción de declararlos**. Compilado verbatim: **4 errores** `TS2552: Cannot find name 'activeMatchId'` / `Cannot find name 'groupSlots'`. El gate de F1 es `tsc --noEmit` 0 errores ⇒ **F1 no puede cerrar**. La nota de dependencia cruzada de §9.2 cubre F4↔F5 (`collapseGroups`) pero **no** esta. Es el mismo modo de falla por el que el v1 fue rechazado, reintroducido por el propio fix de C2. **Fix:** F1 declara los dos placeholders con su tipo y su valor de F1.
> - **B5 — COSTURA F2→F3 rota: `setViewport` es inalcanzable desde donde el plan lo manda llamar.** F3 lo define como **función interna del efecto de layout** ("una sola función dentro del efecto"), pero F2.2-4 ordena que **otro `useEffect`, de scope distinto**, "debe usar `setViewport(...)`". Un efecto no puede ver el closure de otro: `TS2304`. El repo ya resuelve exactamente esto con refs (`resetViewRef` línea 95, asignado en la 305, invocado desde el JSX en la 522; `drawRef` línea 93). **Fix:** se canoniza **`setViewportRef`** (más `zoomInRef`/`zoomOutRef`/`fitRef`, que el v2 usaba sin declarar nunca) y **todo** llamador externo pasa por el ref.
> - **B6 — Los DOS ratchets ya están ROJOS por deuda AJENA, y el plan los usa como criterio binario en 7 lugares.** Corrido en limpio, antes de tocar nada: `npx vitest run src/__tests__/uiDebtRatchet.test.ts` → **1 failed** (`components/ExecutionDetailDrawer.module.css: 23 > 21`, `components/RunReconciliationCard.module.css: 1 > 0`); `npx vitest run src/__tests__/motionDebtRatchet.test.ts` → **2 failed**, 7 regresiones ajenas (`HarnessFlagsPanel` 9>8, `IncidentInboxEntryButton` 1>0, `IncidentResolverModal` 1>0, `IntegrationHealthBanner` 1>0, `ui/Dialog` 5>0, `PlansBoardPage` 1>0, `TicketBoard` 22>21). **Ninguno de esos 9 archivos lo toca el plan 268.** K7, F0, F1, F3, F5, F6 y DoD-3 exigen "verde sin regenerar baseline" ⇒ **son insatisfacibles**, y el único camino que le queda a un modelo menor es regenerar el baseline, que es justo lo que el plan prohíbe (y que además absorbería en silencio la deuda **propia** del plan). El v2 previó el rojo ajeno para `test_harness_flags_help.py` (R9) y lo olvidó para sus gates más citados. **Fix:** criterio **delta por archivo** (los archivos del plan no aparecen en la lista de regresiones) + baseline rojo medido y congelado en la nueva **F0.0**.
> - **B7 — DoD-11 es insatisfacible y contradice a DoD-9.** El comando literal de DoD-11, corrido: `grep -rn -- "var(--color-" src/components/docs/ src/docs/` → **32 hits**, de los cuales **32 están en archivos que el plan NO toca**: `DocBacklinksPanel.module.css` (5), `DocCoveragePanel.module.css` (26 — e incluye `--color-success-bg`, `--color-warning`, `--color-warning-bg`, `--color-danger-bg`, que ni siquiera están en la tabla de sustitución de 6 filas), `DocumenterResultPanel.tsx` (1). DoD-11 pide **0 hits**; DoD-9 prohíbe tocar esos archivos. **Fix:** DoD-11 se acota a los archivos que el plan **posee** y se deja la deuda ajena registrada como tal, con su propio candidato a plan siguiente.
> - **B8 — DoD-12 (huellas de regresión) es inimplementable y volvería ROJO un test que hoy está VERDE.** El esquema real de `docs/sistema/error_fingerprints.json` (dict `{schema_version, description, fingerprints}`, 42 huellas) exige por huella: `class, date_resolved, evidence, guard_test, id, killed_by, killed_commit, log_guarded, log_pattern, note, self_test, status, title`. Y `backend/tests/test_error_fingerprints_catalog.py` hace `re.compile(fp["log_pattern"])` (**no admite `null`** — gotcha ya registrado en la casa) y `test_self_test_coherente` exige que cada `self_test.matches` matchee y cada `self_test.clean` no. Las **4 clases** que DoD-12 manda registrar son **puramente visuales** ("el swatch se ve transparente", "el contador avanza pero el dibujo no se mueve") y **no tienen línea de log**: no existe `log_pattern` honesto para ellas. Corrido: el catálogo hoy da **3 failed / 5 passed**, y `test_patrones_compilan` está entre los que **PASAN** ⇒ agregar una huella con `log_pattern` nulo o falso lo pone rojo. Además DoD-12 es el único DoD **sin comando de verificación**. **Fix:** DoD-12 se reescribe a huellas con `log_pattern` real (o se declara N/A con justificación), nombra el test guardián, exige correrlo y documenta su rojo ajeno.
> - **B9 — El límite de `PlainHelp` que el plan declara es FALSO, y su propio texto está a 1 carácter del real.** El v2 dice: "cada campo de `PlainHelp` tiene un tope de **240 caracteres**". Los topes reales (`backend/tests/test_harness_flags_help.py:47-51`) son: `what` **≤ 200** (y ≥ 10), `on_effect` ≤ 240, `off_effect` ≤ 240, `example` ≤ 300. Medido con Python, el `what` que el propio plan propone tiene **199** caracteres: entra por **1**, mientras el plan le dice al implementador que tiene 41 de margen. Cualquier reescritura "más corta" que agregue una palabra lo pone rojo. **Fix:** los 4 topes reales, la medición hecha, y un `what` acortado a 154 con margen.
>
> **IMPORTANTES corregidos en el v3:** I1 los "gap (a)…(g)" que 7 fases citan **no están definidos en ningún lado** (§2 es una lista **numerada** 1-9, con un "8bis" y **sin** ítem 8) → §2 pasa a numerar Y letrar. I2 F8 dice "**27** pasos (20 del v1 + los **7** nuevos 18b-18g)" pero 18b→18g son **6** y la tabla tiene **26** filas → es el mismo error que C15 decía haber matado; ahora dice 26 y se cuenta. I3 F8 se contradice a sí misma sobre el esfuerzo del operador ("27 pasos / ~13 min" vs "los **20** pasos, ~10 min" vs §9.2 "20 pasos") → unificado. I4 F0.6 declara **opcional** ("sí se puede y conviene") corregir los 3 `style={{ background: "var(--color-accent, …)" }}` de `DocGraphView.tsx:507/511/515`, pero DoD-11 lo exige **binario** → pasa a obligatorio. I5 el grep-gate de F1 es `grep -n "graph\."`, que es **case-sensitive** y por lo tanto **jamás** puede reportar `visibleGraph.` (G mayúscula) — corrido: `echo 'visibleGraph.nodes' | grep -c "graph\."` → **0** — así que su regla "todos los hits deben ser `visibleGraph.…`" describe un resultado imposible → gate reescrito. I6 F2.2 tiene **dos ítems numerados 6** → renumerado. I7 F3 usa `zoomInRef`/`zoomOutRef`/`fitRef` sin declararlos nunca → declarados.
>
> **[ADICIÓN ARQUITECTO #2] — nueva fase F0.0 "Foto del rojo ajeno" (ver §6).** Antes de escribir una línea, el implementador corre los 5 gates compartidos y **congela su rojo preexistente en una tabla dentro de este mismo documento**. Sin eso, B6 y B8 se repiten en cada plan que use estos gates: es imposible distinguir "lo rompí yo" de "ya estaba roto", y el atajo siempre es regenerar el baseline. Cuesta ~2 minutos, es 100% read-only, no le pide nada al operador y **convierte 7 criterios insatisfacibles en 7 criterios delta que sí pueden fallar de verdad**.

---

## 0-ter. CHANGELOG v1 → v2 (histórico — qué corrigió la primera pasada)

Cada bullet cita el hallazgo que resuelve. **Nada del v1 se borró**: todo lo que era correcto se conserva.

**Bloqueantes (el v1 quedaba inimplementable o producía un bug silencioso):**

- **C1 — Los tokens de color que el v1 asumía NO EXISTEN.** Verificado abriendo `Stacky Agents/frontend/src/theme.css`: el tema define `--accent`, `--accent-hot`, `--success`, `--warn`, `--danger`, `--border`, `--text-primary`, `--text-muted`, `--bg-panel`, `--bg-elev`, `--agent-business`, `--agent-functional`, `--agent-custom` — y **ningún** `--color-*` salvo `--color-scheme`. `grep -rn -- "--color-accent:" src` devuelve **0 hits**. Consecuencia real: `readPalette` (`DocGraphView.tsx:52-69`) **siempre** cae al hex de fallback y el canvas del 111 **no es theme-aware** aunque el código lo aparente; y `DocGraphView.module.css` usa 6 tokens inexistentes. El v1 agravaba esto (6 tokens más inventados en F5.2 y swatches CSS **sin fallback** en F5.4 ⇒ swatches transparentes y leyenda de un color distinto que el canvas). **Fix:** nueva **F0.6** con `graphPalette.ts` (lista canónica de tokens REALES) + `graphPalette.test.ts` que lee `theme.css` de disco y falla si un token no está definido **en el bloque oscuro y en el claro**. Ver **[ADICIÓN ARQUITECTO #1]**.
- **C2 — `draw()` con closures stale.** El efecto de layout tiene deps `[visibleGraph, selectedNodeId]` y `draw` se define adentro; el v1 hacía que `draw()` leyera `activeMatchId` (F2), `slots` (F5) y `explorerEnabled` (F7) sin ponerlos en deps ni en refs ⇒ apretar Enter cambiaba el contador pero el anillo se quedaba clavado en el primer resultado. **Fix:** regla dura **§4 G12** (todo valor que lee `draw()` va por `useRef`) + lista exacta de refs en F1.3.
- **C3 — El colapso de F5 y los filtros de F1 vaciaban el canvas.** Si el nodo enfocado deja de existir en el grafo compuesto (porque su grupo se colapsó o un filtro lo descartó), `focusSubgraph` devuelve —por la propia spec del v1— un grafo **vacío**. **Fix:** helper puro `resolveFocusId` (F4.1) que remapea al super-nodo o desactiva el foco, nunca vacía la pantalla; mismo tratamiento para `peekNodeId` y `activeMatchId`.
- **C4 — Gesto en conflicto sobre el super-nodo.** F4 decía "click = enfocar" y F5 "click sobre el super-nodo = des-colapsar". **Fix:** tabla única de gestos en F4.2, repetida en F5.4.
- **C5 — `indexById` apuntaba al grafo equivocado** (exactamente el riesgo R1 que el propio plan denunciaba): se calculaba sobre `graph` y se usaba para indexar `visibleGraph`. **Fix:** lista cerrada de derivados que pasan a `visibleGraph` + grep-gate en el criterio de aceptación de F1.

**Importantes:**

- **C6 — K5/DoD-4 era un falso verde perfecto:** `git diff --stat -- "Stacky Agents/frontend/package.json"` corrido desde `Stacky Agents/frontend` (el CWD de todos los demás comandos del plan) no matchea nada y devuelve vacío = "verde" aunque el archivo esté modificado. **Fix:** pathspec absoluto de repo + `--exit-code`.
- **C7 — El `%` de zoom mentía y el viewport se reseteaba en silencio** en cada cambio de filtro (re-init del efecto ⇒ `viewportRef.current = IDENTITY`, línea 149) sin que `viewScale` se enterara. **Fix:** un único `setViewport(next)` que escribe ref + estado + redibujo (F3), y re-encuadre tras cada re-init en modo explorador.
- **C8 — K9 prometía "cero fetch" y no es garantizable:** el Lector usa `selectedContentSourceId = selectedNode?.source_id ?? selectedSourceId` y `DocNode.source_id` es **opcional** (`endpoints.ts:3323`), mientras que `DocGraphNode.source_id` es obligatorio. **Fix:** se mantiene la misma `queryKey` (es lo correcto) pero el hit de cache deja de ser criterio binario.
- **C9 — Atajos de teclado muertos:** `.canvasBox` con `tabIndex={0}` nunca recibe foco porque el click cae en el `<canvas>` hijo. **Fix:** `boxRef.current?.focus({ preventScroll: true })` en `onPointerDown` + `:focus-visible`.
- **C10 — Umbrales de tiempo (`200 ms` / `150 ms` / `50 ms`) como criterio binario** son no deterministas. **Fix:** presupuesto 2000 ms (sigue cazando un O(n²)) y un rojo de tiempo **no** bloquea la fase.
- **C11 — `availableFilterOptions` sin fuente de verdad:** no se decía de dónde sale el label de cada fuente. **Fix:** de `graph.sources` (`DocGraphSource.label`, `docGraphModel.ts:38-44`), con regla explícita para el id no encontrado.
- **C12 — F2.2 decía "reemplazar el `useState` query" y después seguía usándolo.** **Fix:** el `useState` se **conserva** (camino flag-OFF) y se declara cuál es la fuente de verdad en cada modo.
- **C13 — F7 no decía dónde vive el canvas del minimapa** ni cómo entra a `draw()`, y el umbral de LOD `r < 6` no era verificable. **Fix:** cableado explícito del segundo canvas + el umbral expresado en `in_degree` (con `nodeRadius`, `forceLayout.ts:47-49`) + predicado puro `shouldDrawEdge` con tests.

**Menores:** C14 ruta falsa `src/styles/theme.css` → es `src/theme.css`; C15 DoD-1 decía "8 archivos" y listaba 10; C16 anclajes de inserción de `harness_flags_help.py` (la entrada del 109 **termina** en la línea 279) y de `harness_defaults.env` (el archivo está **ordenado alfabéticamente** y **no** se regenera); C17 "byte-idéntico al 111" pasa a ser "observacionalmente idéntico" (F0.3 y F5.3 no están gateados, a propósito); C18 se agrega el registro en `docs/sistema/error_fingerprints.json`.

**Anclajes verificados uno por uno contra el código real (2026-07-27):** `DocGraphView.tsx` 34-38, 52-75, 97, 100, 112, 114, 119, 122, 127-130, 135-145, 151-158, 176, 247, 261, 266-267, 305, 422, 434-448, 459-475, 492, 505-518, 519-526, 529-533, 537-539 → **todos OK**. `docGraphModel.ts:127-138` OK. `forceLayout.ts` 11, 47-49, 62-64, 101, 203-231 OK. `graphViewport.ts:57` (fin de `panBy`) OK; `IDENTITY`/`MIN_SCALE`/`MAX_SCALE`/`zoomAt`/`toScreen` OK. `DocsPage.tsx` 76, 146, 230, 295-310, 392-416 OK. `config.py:672-675` OK. `harness_flags.py` 120, 400, 2280-2295 OK. `harness_flags_help.py:274` OK (la entrada cierra en 279). `api/docs.py` 52-60 OK. `test_harness_flags.py:467` OK. `test_harness_flags_requires.py` 120 y 316 OK. `harness_defaults.env:158` OK. `endpoints.ts:3356-3370` OK. **Contrato:** `DocGraphNode.source_id/.kind/.in_degree/.out_degree/.has_stale`, `DocGraphEdge.kind`, `graph.orphans`, `graph.sources` **existen**; `Docs.getContent(path, {project, sourceId})` existe (`endpoints.ts:3461-3469`) y la `queryKey` del Lector es la de `DocsPage.tsx:146`. **Único anclaje FALSO del v1:** `frontend/src/styles/theme.css` (no existe; es `frontend/src/theme.css`) — y con él, toda la familia `--color-*`.

---

## 1. Título, objetivo y KPI

**Objetivo (1 párrafo).** El plan 111 dejó un graph view que **se ve** (canvas propio, force layout, hover, click-para-abrir, pan con drag, zoom con rueda) pero que todavía **no se explora**: no hay filtros, no hay agrupación colapsable, no se puede aislar el vecindario de una nota, la búsqueda solo atenúa lo que no matchea (no navega ni encuadra), no hay controles de zoom visibles ni atajos de teclado, y no se puede ver el contenido de una nota sin abandonar la vista. Este plan convierte esa vista en un **Explorador**: una barra de filtros (fuente, tipo de nodo, tipo de arista, grado mínimo, ocultar huérfanas, solo stale), **búsqueda navegable** (n de m, Enter salta y encuadra el resultado), **foco por vecindario** a profundidad 1–3 con historial y migas (volver atrás), **agrupación** por fuente con color propio y colapso a super-nodo, **controles de zoom descubribles** (`+ / − / Ajustar / Centrar`) más atajos de teclado, **minimapa** con rectángulo de viewport, y un **peek** lateral que muestra el principio del documento del nodo seleccionado sin salir del grafo. Todo es **100% read-only**, **sin una sola dependencia nueva** en `frontend/package.json`, y sobre los módulos puros que ya existen (`forceLayout.ts`, `graphViewport.ts`, `docGraphModel.ts`).

**KPI / impacto esperado (metas MEDIBLES y binarias).**

| # | KPI | Meta binaria | Cómo se verifica |
|---|---|---|---|
| K1 | **Reducción de hairball** | Con un filtro de una sola fuente activo, el número de nodos dibujados es exactamente el que devuelve `applyGraphFilters(...).nodes.length`, y ese número es ≤ el total. Test puro. | `npx vitest run src/docs/graphFilters.test.ts` |
| K2 | **Aislar el vecindario** | `neighborhoodOf(graph, rootId, 1)` devuelve exactamente `{root} ∪ vecinos directos`; con `depth=0` devuelve `{root}`; con un `rootId` inexistente devuelve `Set` vacío. | `npx vitest run src/docs/graphNeighborhood.test.ts` |
| K3 | **Búsqueda que navega** | Con `q` que matchea m nodos, la UI muestra `1 de m` y `NEXT_MATCH` cicla `1→2→…→m→1` sin salirse de rango; con m=0 el índice queda en 0 y no lanza. | `npx vitest run src/docs/graphSearch.test.ts` + `graphExplorerState.test.ts` |
| K4 | **Encuadre determinista** | `fitViewport(points, w, h)` deja **todos** los puntos dentro del rectángulo `[0,w]×[0,h]` con al menos `padding` px de margen, para 1, 2 y 500 puntos. | `npx vitest run src/docs/graphViewport.test.ts` |
| K5 | **Cero dependencias nuevas** | `frontend/package.json` byte-idéntico al de HEAD al terminar el plan. | `git diff --exit-code -- ":/Stacky Agents/frontend/package.json"` sale con **código 0**. ⚠️ (C6) **NO** usar `git diff --stat -- "Stacky Agents/frontend/package.json"`: los comandos del plan corren desde `Stacky Agents/frontend` y ahí ese pathspec **no matchea ningún archivo**, así que devuelve vacío aunque el archivo esté modificado — un falso verde perfecto. El prefijo `:/` ancla el pathspec a la raíz del repo desde cualquier CWD. |
| K6 | **Cero regresión de compilación** | `npx tsc --noEmit` sale con 0 errores desde `Stacky Agents/frontend`. | comando literal |
| K7 | **Cero deuda visual nueva** (B6/v3) | **DELTA, no verde absoluto:** los dos ratchets **ya están rojos por deuda AJENA** (**2** y **7** archivos regresivos ⇒ `grep -c "REGRESION"` = **4** y **14**; F0.0). La meta binaria es: **ningún** archivo del plan 268 aparece en la lista de `REGRESION`, el conteo **no sube** respecto de F0.0, y **no se regeneró ningún baseline**. (⇒ 0 `style={{` en `.tsx` nuevos, 0 hex y 0 tiempos literales en el `.module.css` nuevo y en las líneas nuevas del existente). | `npx vitest run src/__tests__/uiDebtRatchet.test.ts 2>&1 \| grep "REGRESION"` y su gemelo de motion |
| K8 | **Performance no degradada** | El dibujo de labels deja de hacer `Array.findIndex` por label por frame (O(n·L)) y pasa a `Map.get` (O(L)); el tope `MAX_ANIMATED_NODES = 300` y `prefers-reduced-motion` siguen respetados sin cambios de semántica. | F0 + revisión de diff |
| K9 | **Acceso rápido al contenido** | Seleccionar un nodo nota muestra el peek con las primeras ~600 caracteres del documento **sin** cambiar de pestaña, usando **exactamente la misma `queryKey`** que el Lector (`DocsPage.tsx:146`). ⚠️ (C8) El *hit* de cache es **deseable, no binario**: el Lector arma el 3.º campo de la clave con `selectedNode?.source_id ?? selectedSourceId` y `DocNode.source_id` es **opcional** (`endpoints.ts:3323`), así que si el índice no trae `source_id` las claves difieren legítimamente y se hace un `GET` de más (costo: una lectura de disco local). Lo binario es que la clave sea la misma expresión y que el peek muestre texto real. | Verificación visual F8, paso 9 |
| K10 | **El canvas es de verdad theme-aware** (C1) | Todo token de color que el grafo lee existe en `frontend/src/theme.css` **en el bloque oscuro y en el claro**. Test puro que lee el archivo de disco. | `npx vitest run src/docs/graphPalette.test.ts` |

---

## 2. Por qué ahora / gap que cierra (con archivo:línea)

1. **(gap e) La búsqueda existente no navega.** `frontend/src/components/docs/DocGraphView.tsx:97` declara `const [query, setQuery] = useState("")` y `:112` hace `filterRef.current = filterNodeIds(graph, query)`. `filterNodeIds` (`frontend/src/docs/docGraphModel.ts:127-138`) solo devuelve un `Set` de ids; el dibujo lo usa en `:176` para bajar el alpha de lo que no matchea. **No hay conteo de resultados, no hay "siguiente", no hay zoom al resultado.** Si el nodo que buscás quedó fuera del viewport, buscarlo no sirve de nada.
2. **(gap a) No hay ningún filtro.** No existe ni el concepto: el componente recibe `graph` (`DocGraphView.tsx:34-38`) y lo dibuja entero. Con varias fuentes de docs (`DocsPage.tsx:295-310` ofrece un `<select>` de fuentes; el grafo del 109 mezcla TODAS) el canvas es un hairball.
3. **(gap b) La agrupación existe pero es invisible.** `frontend/src/docs/forceLayout.ts:62-64` tiene `groupOf(kind, sourceId)` **privado**, usado solo para el color y para las columnas del `staticLayout` (`forceLayout.ts:203-231`). Peor: `colorForGroup` (`DocGraphView.tsx:71-75`) devuelve `pal.note` para **cualquier** grupo `note:<source>` ⇒ **todas las notas de todas las fuentes se pintan del mismo color**. La agrupación no se ve, no se puede colapsar y no se puede filtrar por ella.
4. **(gap c) No hay navegación por relaciones.** El hover resalta vecinos (`DocGraphView.tsx:151-158`, `neighborsOf`) pero es efímero: al mover el mouse se pierde. No se puede fijar un nodo como raíz, ver su vecindario a profundidad 2, ni volver al nodo anterior.
5. **(gap d) No hay acceso al contenido desde el grafo.** El único acceso es `onOpenNoteById` (`DocGraphView.tsx:422`), que **abandona la vista** (`DocsPage.tsx:230` hace `setDocsView("reader")`). No hay forma de espiar una nota y seguir explorando.
6. **(gap f) El zoom no es descubrible.** Solo rueda (`DocGraphView.tsx:434-444`) y doble click para resetear (`:446-448`). El único botón de la toolbar es "Centrar" (`:519-526`). No hay `+`, `−`, "Ajustar a pantalla", ni teclado. Un operador que use trackpad o teclado no descubre el zoom.
7. **(sin letra — es el KPI K8) Hay un costo O(n) escondido por label y por frame.** `DocGraphView.tsx:266` hace `graph.nodes.findIndex((n) => n.id === c.id)` **dentro del loop de dibujo de labels**, que corre hasta 60 veces por frame (`pickVisibleLabels(candidates, 60)`, `:261`). Con 300 nodos son hasta 18.000 comparaciones por frame gratis. Se arregla con un `Map` en F0.
8. **(gap g) Alejado, el grafo es ilegible y uno se pierde.** No hay minimapa, así que al acercarse no se sabe en qué parte del corpus se está; y no hay nivel de detalle por escala, así que alejarse muestra *todas* las aristas de golpe (un plato de fideos) en vez de la estructura troncal. `DocGraphView.tsx` dibuja siempre todo: el único ajuste por escala es `zoomedIn` para los labels (`:237`). **Lo cierra F7.**
8bis. **(C1 — hallazgo del juez, bug VIVO) El grafo NO es theme-aware, aunque el código lo aparente.** `readPalette` (`DocGraphView.tsx:52-69`) lee `--color-accent`, `--color-success`, `--color-danger`, `--color-border`, `--color-text`, `--color-surface`; el tema (`frontend/src/theme.css`) define `--accent` (línea 17), `--success` (19), `--danger` (21), `--border` (8), `--text-primary` (11), `--bg-panel` (6) — y **ningún** `--color-*` salvo `--color-scheme` (163/243/279). `grep -rn -- "--color-accent:" src` → **0 hits**. Como `readPalette` hace `raw || fallback` (línea 56), el canvas dibuja **siempre** los hex hardcodeados y no se entera del tema claro. Peor: `DocGraphView.module.css` usa **6** tokens inexistentes (`--color-accent`, `--color-border`, `--color-surface`, `--color-surface-2`, `--color-text`, `--color-text-muted`), que en CSS resuelven a *unset*. **F0.6 lo arregla y deja un test que impide que vuelva.**

9. **`docsView` ya soporta tres vistas** (`DocsPage.tsx:76`: `"reader" | "coverage" | "graph"`) y la pestaña "Grafo" ya está cableada (`DocsPage.tsx:392-400`, `:410-416`). Este plan **no** agrega una pestaña nueva: mejora la que ya está.

---

## 3. Sobre Grapify: evaluación y veredicto

El operador pidió, textualmente, *"siempre que sea técnicamente viable, integrar **Grapify** directamente en la plataforma"*. Se evaluó. **NO es técnicamente viable, y la cláusula condicional del propio pedido es la que aplica.** Evidencia, con fecha:

**Evidencia (verificada 2026-07-27):**

- **E1 — Qué es realmente.** El paquete npm `grapify` (https://www.npmjs.com/package/grapify, repo https://github.com/AdnanDLuffy/Grapify, autor `AdnanDLuffy`) se describe a sí mismo como *"A lightweight npm package for generating graphs based on user inputs... percentage-based charts, bar graphs, or pie (under construction) charts... Ideal for data visualization in **Node.js** applications"*. Es decir: un generador de **gráficos estadísticos** (barras / torta / porcentaje) para **Node.js**.
- **E2 — No modela relaciones.** No tiene el concepto de nodo ni de arista, no tiene force layout, no tiene render de navegador (canvas/SVG/WebGL) ni interacción (hover, drag, zoom). Representar "relaciones entre documentos, conceptos, dependencias y referencias" —que es exactamente lo que el operador quiere ver— está **fuera de su modelo de datos**, no es una cuestión de esfuerzo de integración.
- **E3 — No está en el repo ni referenciado.** `grep -rni "grapify\|graphify"` sobre todo el árbol de Stacky Agents: **0 hits**. No hay integración previa, ni un spike, ni una nota de diseño que lo asuma.

**Tres razones por las que NO se integra:**

1. **Inadecuación funcional (bloqueante).** Es una librería de *charts*, no de *graphs* en el sentido de teoría de grafos. Aunque se integrara perfecto, no podría dibujar el grafo documental: no tiene nodos ni aristas (E1, E2).
2. **Inadecuación de entorno (bloqueante).** Apunta a Node.js, no al navegador. El graph view de Stacky corre en el cliente, sobre `<canvas>` 2D. No hay superficie de render compartida.
3. **Violación de una decisión de arquitectura vigente (bloqueante por rieles).** `Stacky Agents/frontend/package.json` **no tiene ninguna** librería de grafos, y el plan 111 dejó la decisión tomada por escrito: *"graph view force-directed dibujado en un `<canvas>` propio, **SIN dependencias nuevas**... nada de mermaid, d3, cytoscape ni react-force-graph"*, con el motivo explícito *"cero riesgo de supply chain"*. Sumar una dependencia chica, de un solo autor y sin adopción, para una capacidad que ya tenemos resuelta sería **degradar seguridad y DX** — algo que los guardarraíles de la casa prohíben (§4).

**Alternativa adoptada (entregamos igual TODO lo pedido).** Se implementa la capacidad completa —zoom, filtros, búsqueda, agrupación de nodos, navegación entre relaciones y acceso rápido al contenido— sobre el **motor canvas propio que ya existe** (`DocGraphView.tsx` + `forceLayout.ts` + `graphViewport.ts`), extendiéndolo con módulos `.ts` puros y testeados. Mapa pedido → fase que lo entrega:

| Pedido del operador | Se entrega en | Sobre qué motor |
|---|---|---|
| Zoom | **F3** (botones `+ / − / Ajustar / Centrar` + teclado) | `graphViewport.zoomAt` / `fitViewport` (propios) |
| Filtros | **F1** (fuente, tipo de nodo, tipo de arista, grado, huérfanas, stale) | `graphFilters.ts` (nuevo, puro) |
| Búsqueda | **F2** (ranking, `n de m`, Enter navega y encuadra) | `graphSearch.ts` (nuevo, puro) |
| Agrupación de nodos | **F5** (color por grupo + colapsar grupo a super-nodo) | `graphGrouping.ts` (nuevo, puro) |
| Navegación entre relaciones | **F4** (foco por vecindario 1–3 + historial + migas) | `graphNeighborhood.ts` (nuevo, puro) |
| Acceso rápido al contenido | **F6** (peek lateral con excerpt, sin salir del grafo) | `Docs.getContent` ya existente + `previewExcerpt` puro |
| Legibilidad / estructura | **F7** (minimapa + nivel de detalle por escala) | `graphMinimap.ts` (nuevo, puro) |

**Conclusión que queda registrada:** *Grapify quedó descartado por inadecuación funcional y de entorno, no por falta de ganas de integrarlo. La capacidad pedida se entrega completa sobre el motor propio. Si en el futuro aparece una librería de grafos de red que justifique romper la regla de cero-dependencias, eso es una decisión de arquitectura aparte y necesita su propio plan.*

---

## 4. Principios y guardarraíles (NO negociables — codificados en cada fase)

- **G1 — Cero dependencias nuevas.** Está **PROHIBIDO** tocar `Stacky Agents/frontend/package.json` (esa es la ruta, una sola vez `frontend`; el v2 la escribía duplicada). Si una fase parece necesitar un paquete, la fase se rediseña. Gate: K5.
- **G2 — Toda la lógica en módulos `.ts` PUROS.** En este repo **no hay React Testing Library ni jsdom instalados** (gotcha estructural conocido). Por lo tanto: **prohibido** proponer tests de componente React. Cada `.tsx` es un **cascarón delgado** que solo llama helpers puros de `frontend/src/docs/*.ts`; toda la decisión (qué filtrar, qué está seleccionado, a dónde saltar) vive en esos helpers y se prueba con vitest sin DOM.
- **G3 — Read-only absoluto.** Ninguna fase escribe un documento, un ticket, una rama ni una fila de BD. El único verbo HTTP usado es `GET` (`/api/docs/graph`, `/api/docs/content`, `/api/docs/sources`).
- **G4 — Human-in-the-loop.** Nada se decide solo: los filtros, el foco, el colapso y el peek son acciones explícitas del operador. No hay auto-foco, no hay auto-filtrado "inteligente", no hay llamadas a modelos. El grafo nunca "decide" qué es importante en lugar del operador.
- **G5 — Mono-operador sin auth.** No se agrega identidad, ni RBAC, ni preferencias por usuario. El estado del explorador es de sesión (en memoria del componente); no se persiste en disco ni en BD.
- **G6 — Theme-aware DE VERDAD (reescrito por C1).** Todo color del canvas se lee de CSS custom properties vía `readPalette` (`DocGraphView.tsx:52-69`), y **el nombre del token tiene que existir en `Stacky Agents/frontend/src/theme.css`**. ⚠️ Hoy **no existe**: `readPalette` pide `--color-accent` / `--color-success` / `--color-danger` / `--color-border` / `--color-text` / `--color-surface` y el tema define `--accent` / `--success` / `--danger` / `--border` / `--text-primary` / `--bg-panel`. Verificado: `grep -rn -- "--color-accent:" "Stacky Agents/frontend/src"` → **0 hits**; en `theme.css` el único `--color-*` es `--color-scheme`. Resultado: el grafo del 111 se dibuja **siempre** con los hex de fallback y **no** cambia con el tema. **F0.6 lo arregla** y deja un test que impide que vuelva a pasar. Regla operativa: **ningún token nuevo**; se usan únicamente los ya definidos en `theme.css`, y `graphPalette.ts` es la lista canónica.
- **G12 — Todo lo que lee `draw()` va por `useRef` (nuevo por C2).** `draw()` se define **dentro** del efecto de layout, cuyas deps son `[visibleGraph, selectedNodeId]`. Por lo tanto **cualquier** valor de React que `draw()` lea y que pueda cambiar sin que esas deps cambien **queda congelado** (closure stale). El archivo ya usa este patrón: `filterRef`, `hoverRef`, `paletteRef`, `viewportRef` (`DocGraphView.tsx:89-95`). **Consecuencia dura:** cada valor nuevo que `draw()` necesite se guarda en un `useRef` y se sincroniza con un `useEffect` de dos líneas (`ref.current = valor; if (stateRef.current && !stateRef.current.animated) drawRef.current();`). **Prohibido** leer un `useState` o una variable derivada del render directamente dentro de `draw()`.
- **G13 — Ningún estado del explorador puede dejar el canvas vacío (nuevo por C3).** Filtrar, colapsar y enfocar componen; cualquier composición que dé `nodes: []` teniendo el operador un grafo cargado es un **bug**, no un estado válido. La única forma legítima de ver 0 nodos es que el operador haya puesto filtros que efectivamente no dejan nada (y ahí el `EmptyState` de `DocGraphView.tsx:529-533` lo dice, con el botón "Limpiar filtros" a mano).
- **G7 — Respetar `prefers-reduced-motion` y `MAX_ANIMATED_NODES = 300`.** Ninguna fase toca esa lógica (`forceLayout.ts:11`, `:101`; `DocGraphView.tsx:127-130`). Cualquier redibujo nuevo en modo estático debe llamar `drawRef.current()` explícitamente, igual que hoy (`DocGraphView.tsx:114`, `:119`).
- **G8 — Ratchets de deuda visual.** `frontend/src/__tests__/uiDebtRatchet.test.ts` congela **por archivo** la cantidad de `style={{` en `*.tsx` y de colores **hex** en `*.module.css`; `motionDebtRatchet.test.ts` congela tiempos literales (`120ms`, `0.2s`) y `cubic-bezier(` en `*.module.css`. **Consecuencia dura:** los `.tsx` nuevos van con **cero** `style={{`, y **toda línea CSS nueva** (tanto en el `.module.css` nuevo como en las que se agreguen a `DocGraphView.module.css`) usa `var(--token)` **sin fallback hex** y `var(--duration-*)` / `var(--ease-*)` para tiempos. ⚠️ **(B6/v3) El criterio NO es "ambos ratchets verdes": los dos YA ESTÁN ROJOS por deuda ajena** (medido en F0.0: `uiDebtRatchet` **2** archivos regresivos, `motionDebtRatchet` **7**, repartidos en 9 archivos que este plan no toca; `grep -c "REGRESION"` devuelve el doble, **4** y **14**). El criterio es **DELTA**: ningún archivo tocado o creado por el plan 268 puede aparecer en una línea `REGRESION`, el conteo de regresiones no puede subir respecto de F0.0, y **está prohibido regenerar cualquier baseline** (regenerar absorbería en silencio la deuda propia del plan, que es peor que no tener ratchet).
- **G9 — Backward-compatible.** Con `STACKY_DOCS_GRAPH_EXPLORER_ENABLED` en OFF, la pestaña "Grafo" se comporta **exactamente** como hoy (toolbar de 111: buscar + leyenda + "Centrar"). Con `STACKY_DOCS_GRAPH_ENABLED` en OFF, la pestaña ni siquiera se monta (comportamiento del 109/111, intacto).
- **G10 — Reusar, no reinventar.** Se reusan: `initLayout`/`stepLayout`/`staticLayout` (111), `Viewport`/`zoomAt`/`panBy`/`toWorld`/`toScreen`/`pickVisibleLabels` (111), `filterNodeIds`/`backlinksOf`/`buildNameIndex` (109/111), `Docs.getGraph`/`Docs.getContent` (109), el motor de flags del arnés, y el patrón de pestañas de `DocsPage`.
- **G11 — Sin ambigüedad para modelos menores.** Cada fase declara archivo exacto, símbolo exacto, firma exacta, casos borde, test nombrado y comando literal.

---

## 5. Nombres canónicos (usar EXACTAMENTE estos)

| Concepto | Nombre exacto | Dónde vive |
|---|---|---|
| Flag maestra del grafo (existente, **no** se crea) | `STACKY_DOCS_GRAPH_ENABLED` | `backend/config.py:673`, `backend/services/harness_flags.py:2281` |
| Flag nueva del explorador | `STACKY_DOCS_GRAPH_EXPLORER_ENABLED` | F0 |
| Campo del payload de `/api/docs/sources` | `graph_explorer_enabled` | F0 |
| Prop React que lo transporta | `explorerEnabled` | F0 |
| Módulo de estado del explorador | `frontend/src/docs/graphExplorerState.ts` | F0 |
| Tipo del estado | `GraphExplorerState` | F0 |
| Tipo de los filtros | `GraphFilterState` | F0 |
| Acción del reducer | `GraphExplorerAction` | F0 |
| Reducer puro | `graphExplorerReducer` | F0 |
| Estado inicial | `INITIAL_EXPLORER_STATE` | F0 |
| Índice id→posición | `nodeIndexById` | F0 (en `docGraphModel.ts`) |
| Encuadre a un conjunto de puntos | `fitViewport` | F0 (en `graphViewport.ts`) |
| Centrar en un punto del mundo | `centerOn` | F0 (en `graphViewport.ts`) |
| Zoom anclado al centro del canvas | `zoomAtCenter` | F0 (en `graphViewport.ts`) |
| Paso de zoom por click | `ZOOM_STEP` | F0 (en `graphViewport.ts`) |
| Módulo de filtros | `frontend/src/docs/graphFilters.ts` | F1 |
| Función de filtrado | `applyGraphFilters` | F1 |
| Opciones disponibles para la barra | `availableFilterOptions` | F1 |
| Filtros vacíos (todo pasa) | `EMPTY_FILTERS` | F1 |
| Módulo de búsqueda | `frontend/src/docs/graphSearch.ts` | F2 |
| Búsqueda rankeada | `searchGraphNodes` | F2 |
| Resultado de búsqueda | `GraphSearchMatch` | F2 |
| Módulo de vecindario | `frontend/src/docs/graphNeighborhood.ts` | F4 |
| Adyacencia no dirigida | `buildAdjacency` | F4 |
| Vecindario a profundidad N | `neighborhoodOf` | F4 |
| Vecinos ordenados para la lista | `rankedNeighbors` | F4 |
| Módulo de agrupación | `frontend/src/docs/graphGrouping.ts` | F5 |
| Clave canónica de grupo | `groupKeyOf` | F5 (reemplaza al privado `groupOf` de `forceLayout.ts:62`) |
| Etiqueta legible del grupo | `groupLabelOf` | F5 |
| Asignación determinista de color | `assignGroupColorSlots` | F5 |
| Colapso de grupos a super-nodos | `collapseGroups` | F5 |
| Prefijo del id de super-nodo | `GROUP_NODE_PREFIX` (`"group:"`) | F5 |
| Componente de peek | `frontend/src/components/docs/DocGraphPeek.tsx` | F6 |
| Excerpt puro del markdown | `previewExcerpt` | F6 (en `frontend/src/docs/graphPreview.ts`) |
| **Paleta canónica del grafo** (C1) | `frontend/src/docs/graphPalette.ts` | **F0.6** |
| Lista de tokens que el canvas lee | `GRAPH_PALETTE_TOKENS` | F0.6 |
| Tokens de color por slot de grupo | `GROUP_SLOT_TOKENS` | F0.6 |
| Escritor único de viewport (ref + estado + redibujo) | `setViewport` | F3 (función **interna** del efecto de layout de `DocGraphView`) |
| **Ref de comando del viewport** (única forma de llamarlo desde afuera del efecto) | `setViewportRef` | **F1** (declarado) / F3 (llenado) |
| Refs de comando del zoom | `zoomInRef`, `zoomOutRef`, `fitRef` | **F1** (declarados) / F3 (llenados) |
| Map vacío de slots, constante módulo (identidad referencial estable) | `EMPTY_GROUP_SLOTS` | F1 (arriba de `DocGraphView`) |
| Resolución del foco tras filtrar/agrupar (C3) | `resolveFocusId` | F4 (en `graphNeighborhood.ts`) |
| Predicado puro de nivel de detalle (C13) | `shouldDrawEdge` | F7 (en `graphMinimap.ts`) |
| Módulo del minimapa | `frontend/src/docs/graphMinimap.ts` | F7 |
| Transformación mundo→minimapa | `minimapTransform` | F7 |
| Rectángulo del viewport en el minimapa | `viewportRectInMinimap` | F7 |
| CSS del explorador | `frontend/src/components/docs/DocGraphExplorer.module.css` | F1 |
| Barra de filtros | `frontend/src/components/docs/DocGraphFilterBar.tsx` | F1 |
| Controles de zoom | `frontend/src/components/docs/DocGraphZoomControls.tsx` | F3 |

---

## 6. Fases

> **Regla transversal de tests (aplica a TODAS las fases):** los tests se escriben **ANTES** del código (TDD). Se corre **por archivo** (hay contaminación cross-file conocida en la corrida completa de vitest).
> - Frontend, desde `Stacky Agents/frontend`: `npx vitest run src/docs/<archivo>.test.ts`
> - Gate de tipos, desde `Stacky Agents/frontend`: `npx tsc --noEmit`
> - Backend, desde `Stacky Agents`: **`backend\.venv\Scripts\python.exe -m pytest backend/tests/<archivo>.py -q`**
>   [!] **(B1/v3) La ruta del interprete es `backend\.venv\`, NO `.venv\`.** Verificado corriendo: `Stacky Agents/.venv` **no existe** y el comando del v2 devuelve `No such file or directory`. El interprete correcto es `Stacky Agents/backend/.venv/Scripts/python.exe` -> **Python 3.13.5**. Existe ademas `Stacky Agents/backend/venv/` (sin punto) que es **Python 3.11.9**: **NO se usa**. Comprobalo una vez con `backend\.venv\Scripts\python.exe --version`.
> - **Gates compartidos con rojo AJENO preexistente (ver F0.0):** `uiDebtRatchet`, `motionDebtRatchet`, `test_harness_flags_help.py` y `test_error_fingerprints_catalog.py` **ya estan rojos** por deuda de otros planes. Para todos ellos el criterio de este plan es **DELTA**, nunca "verde absoluto": ningun archivo tocado por el plan 268 puede aparecer en la lista de regresiones, y el conteo de fallos no puede subir respecto de la foto de F0.0.

---

### §6.0 — **[ADICIÓN ARQUITECTO #3]** Contrato de imports de `DocGraphView.tsx` (N1/v4 — leer ANTES de pegar cualquier bloque)

**El problema que esto mata, medido.** Los bloques de cableado de F1.3, F2.2, F3, F4.2, F5, F6.3 y F7 muestran el **cuerpo** del código pero nunca el **encabezado**. Compilando F0.6 + F1.3 verbatim, `npx tsc --noEmit` sale con **exit 2** y 5 × `TS2304` (`useReducer`, `graphExplorerReducer`, `INITIAL_EXPLORER_STATE`, `availableFilterOptions`, `applyGraphFilters`). Como el criterio de aceptación de **cada** fase es `tsc --noEmit` con **0 errores**, la fase **no puede cerrar**. Es la misma familia de B3/B4/B5 — una costura que no compila — escondida en el único eslabón que ninguna pasada anterior miró.

**REGLA DURA, sin excepciones.** Un símbolo que aparece en un bloque de cableado y **no** está en el bloque de imports de `DocGraphView.tsx` (líneas 12-32 del archivo original) hay que **agregarlo al import en la misma edición**. No es opcional, no se "infiere del contexto", y no espera a una fase posterior. Los `import` de un módulo ES se pueden escribir en cualquier orden entre sí, pero **todos** van arriba, junto a los que ya están.

**Tabla de imports por fase — copiar la fila de la fase que estás cerrando.**

| Fase | Línea(s) de `import` a agregar en `DocGraphView.tsx` |
|---|---|
| **F0.3** | `nodeIndexById` se **suma** al import existente de la línea 14: `import { filterNodeIds, nodeIndexById } from "../../docs/docGraphModel";` |
| **F0.6** | `import { GRAPH_PALETTE_TOKENS, GROUP_SLOT_TOKENS } from "../../docs/graphPalette";` |
| **F1.3** | `useReducer` se **suma** al import de React de la línea 12: `import { useEffect, useMemo, useReducer, useRef, useState } from "react";`<br>`import { graphExplorerReducer, INITIAL_EXPLORER_STATE } from "../../docs/graphExplorerState";`<br>`import type { GraphExplorerState } from "../../docs/graphExplorerState";` *(solo si anotás algún tipo explícito)*<br>`import { applyGraphFilters, availableFilterOptions } from "../../docs/graphFilters";`<br>`import DocGraphFilterBar from "./DocGraphFilterBar";` |
| **F2.2** | `import { searchGraphNodes, matchAt, matchIdSet } from "../../docs/graphSearch";`<br>`centerOn` se **suma** al import de `graphViewport` (líneas 21-31). |
| **F3** | `import DocGraphZoomControls from "./DocGraphZoomControls";`<br>`zoomAtCenter`, `fitViewport`, `ZOOM_STEP`, `MIN_SCALE`, `MAX_SCALE` se **suman** al import de `graphViewport`. |
| **F4.2** | `import { neighborhoodOf, rankedNeighbors, resolveFocusId } from "../../docs/graphNeighborhood";` |
| **F5** | `import { groupKeyOf, groupLabelOf, assignGroupColorSlots, collapseGroups, GROUP_NODE_PREFIX } from "../../docs/graphGrouping";` |
| **F6.3** | `import DocGraphPeek from "./DocGraphPeek";` (el `previewExcerpt` lo importa **`DocGraphPeek.tsx`**, no `DocGraphView.tsx`). |
| **F7** | `import { minimapTransform, viewportRectInMinimap, shouldDrawEdge } from "../../docs/graphMinimap";` |

⚠️ **Fuera de `DocGraphView.tsx`, dos imports más que también son obligatorios y sí están dichos en su fase:** `forceLayout.ts` gana `import { groupKeyOf } from "./graphGrouping";` (F5.3) y `graphFilters.ts` gana `import type { GraphFilterState } from "./graphExplorerState";` (F1.1).

**Grep-gate de símbolo sin importar (correr al cerrar CADA fase, desde `Stacky Agents/frontend`).** Sale con **0 hits**; cualquier hit es un `TS2304` esperándote:
```
F="src/components/docs/DocGraphView.tsx"
# 1) sacar las lineas de COMENTARIO: los placeholders de F1.3 nombran matchAt y
#    assignGroupColorSlots en prosa, y sin este filtro el gate da 2 falsos positivos.
grep -vE '^[[:space:]]*(//|\*|/\*)' "$F" > /tmp/code_only.txt
for s in useReducer nodeIndexById GRAPH_PALETTE_TOKENS graphExplorerReducer INITIAL_EXPLORER_STATE \
         applyGraphFilters availableFilterOptions searchGraphNodes matchAt matchIdSet centerOn \
         zoomAtCenter fitViewport ZOOM_STEP neighborhoodOf rankedNeighbors resolveFocusId \
         groupKeyOf groupLabelOf assignGroupColorSlots collapseGroups minimapTransform \
         viewportRectInMinimap shouldDrawEdge; do
  grep -q "\b$s\b" /tmp/code_only.txt && ! grep -qE "^import .*\b$s\b|^  $s,?$" "$F" && echo "SIN IMPORTAR: $s"
done
```
[!] **Este gate se validó en las DOS direcciones** (no se "leyó", se corrió): sobre el archivo **con** los imports puestos da **0 hits**; sobre el mismo archivo **sin** las 3 líneas de import de F1.3 imprime **exactamente** `useReducer`, `graphExplorerReducer`, `INITIAL_EXPLORER_STATE`, `applyGraphFilters`, `availableFilterOptions`. El filtro de comentarios de la primera línea **no es decorativo**: sin él, el gate reporta `matchAt` y `assignGroupColorSlots` para siempre (los nombra el comentario de los placeholders de F1.3-3) y un gate que nunca puede dar verde se ignora a los dos días.

**Y el gate real, el que no se puede gamear:** `npx tsc --noEmit` con **0 errores** al cerrar la fase. Si el grep de arriba da 0 y `tsc` da errores, ganó `tsc`.

---

### F0.0 — **[ADICIÓN ARQUITECTO #2]** Foto del rojo AJENO (antes de escribir una sola línea)

**Objetivo.** Medir y **congelar en este documento** el estado rojo preexistente de los 5 gates compartidos, para que ninguna fase posterior confunda "lo rompí yo" con "ya estaba roto".

**Por qué esto es una fase y no una nota al pie.** El v2 fue **RECHAZADO** en gran parte por esto (B6 y B8): daba por verdes dos ratchets que ya estaban rojos por deuda ajena, y mandaba escribir en un catálogo cuyo test guardián ya fallaba. Cuando un criterio binario es insatisfacible, un modelo menor no se traba: **regenera el baseline**, y con eso absorbe en silencio la deuda propia del plan. Esta fase convierte 7 criterios imposibles en 7 criterios **delta** que sí pueden fallar de verdad. Es 100% read-only, no toca código, no le pide nada al operador y cuesta ~2 minutos.

**Comandos exactos (correr TODOS antes de F0.1).**
```
# desde "Stacky Agents/frontend"
npx tsc --noEmit ; echo "tsc_exit=$?"
npx vitest run src/__tests__/uiDebtRatchet.test.ts 2>&1 | grep -c "REGRESION"
npx vitest run src/__tests__/motionDebtRatchet.test.ts 2>&1 | grep -c "REGRESION"
git diff --exit-code -- ":/Stacky Agents/frontend/package.json" ; echo "pkg_exit=$?"
```
```
# desde "Stacky Agents"
backend\.venv\Scripts\python.exe --version
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_docs_api.py -q
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_harness_flags.py -q
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_harness_flags_requires.py -q
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_harness_flags_help.py -q
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_error_fingerprints_catalog.py -q
```

**Foto de referencia (medida por el juez el 2026-07-28 — si tu medición difiere, gana la TUYA y la escribís acá).**

| Gate | Estado al empezar | Detalle |
|---|---|---|
| `npx tsc --noEmit` | **VERDE** (exit 0) | limpio; cualquier error es tuyo |
| `uiDebtRatchet` | **ROJO ajeno** — 1 failed / 2 passed. Archivos distintos en `REGRESION`: **2**. Salida de `grep -c "REGRESION"`: **4** | `components/ExecutionDetailDrawer.module.css` 23>21; `components/RunReconciliationCard.module.css` 1>0 |
| `motionDebtRatchet` | **ROJO ajeno** — 2 failed / 1 passed. Archivos distintos en `REGRESION`: **7**. Salida de `grep -c "REGRESION"`: **14** | `HarnessFlagsPanel` 9>8; `IncidentInboxEntryButton` 1>0; `IncidentResolverModal` 1>0; `IntegrationHealthBanner` 1>0; `ui/Dialog` 5>0; `PlansBoardPage` 1>0; `TicketBoard` 22>21 |
| `git diff --exit-code -- ":/…package.json"` | **VERDE** (exit 0) | el pathspec relativo matchea **0** archivos desde `frontend/`; el `:/` matchea **1** |
| `test_docs_api.py` | **VERDE** — 10 passed | tu test nuevo lo deja en 11 |
| `test_harness_flags.py` | **VERDE** | |
| `test_harness_flags_requires.py` | **VERDE** | |
| `test_harness_flags_help.py` | **ROJO ajeno** — **4 failed / 4 passed** | `covers_all_registry_keys`, `fields_non_empty_and_bounded`, `on_off_start_with_si`, `avoids_jargon_denylist` |
| `test_error_fingerprints_catalog.py` | **ROJO ajeno** — **3 failed / 5 passed** | `campos_obligatorios` (`PLAN239-OUTLET-EN-BLANCO` sin `self_test`), `status_enum`, `self_test_coherente`. **`test_patrones_compilan` PASA** — no lo rompas (DoD-12) |

[!] **(v4) OJO con el conteo: `grep -c "REGRESION"` devuelve el DOBLE de los archivos regresivos.** No es un bug del ratchet: **vitest imprime cada error dos veces** (una en el diff inline del test que falla, otra en el resumen `Failed Tests` del final). Medido: **2** archivos distintos ⇒ `grep -c` da **4**; **7** archivos distintos ⇒ `grep -c` da **14**. Las dos cifras son correctas y miden cosas distintas, así que la tabla anota **las dos** y el criterio delta se ancla a **la que el comando realmente devuelve** (4 y 14). Si anotás 2 y 7 y después comparás contra `grep -c`, te vas a convencer de que rompiste algo sin haber tocado una línea. Para ver los archivos **distintos** (que es lo que de verdad importa en el punto 2 del delta):
```
# desde "Stacky Agents/frontend"
npx vitest run src/__tests__/uiDebtRatchet.test.ts 2>&1 | grep "REGRESION en " | sed 's/.*REGRESION en //' | cut -d: -f1 | sort -u
npx vitest run src/__tests__/motionDebtRatchet.test.ts 2>&1 | grep "REGRESION en " | sed 's/.*REGRESION en //' | cut -d: -f1 | sort -u
```
→ deben listar **exactamente** los 2 y los 7 archivos de la tabla, y **ninguno** que empiece con `components/docs/DocGraph` o `docs/`.

**Criterio de aceptación binario.** La tabla de arriba está rellenada con **tu** medición, en este mismo documento, con **las dos** cifras (archivos distintos y salida de `grep -c`). **Cero archivos modificados** por esta fase (`git status --porcelain` no muestra nada nuevo salvo este `.md`).

**Flag.** N/A — no hay código.

**Impacto por runtime.** Ninguno en los tres (Codex CLI / Claude Code CLI / GitHub Copilot Pro): son lecturas locales, cero LLM.

**Trabajo del operador: ninguno.**

---

### F0 — Sustrato: flag del explorador, índice id→posición, matemática de encuadre y estado puro

**Objetivo.** Dejar listos la flag que gatea todo, el helper que elimina el `findIndex` O(n) por label, la matemática de encuadre/zoom-al-centro, y el reducer puro que gobierna el estado del explorador — sin cambiar todavía nada visible.

**Valor que entrega.** Sin esta fase ninguna de las otras compila: todas dependen de `GraphExplorerState`, de `fitViewport` y del gate por flag. Además arregla ya el costo O(n·L) por frame (KPI K8).

#### F0.1 — Flag `STACKY_DOCS_GRAPH_EXPLORER_ENABLED` (SIETE lugares, ninguno opcional)

> **Default: ON.** Justificación contra la regla dura: la flag **no** cae en (A) —no hay loop, daemon, polling, prefetch ni llamada a modelo: es render de un payload que el operador ya pidió al abrir la pestaña— ni en (B) —no escribe en ningún sistema real, no destruye datos, no saltea ninguna decisión: es 100% lectura y visualización—. Por lo tanto **nace ON**. Existe solo como escape hatch para volver a la toolbar del 111 si algo molesta.

Editar, **en este orden**:

1. **`Stacky Agents/backend/config.py`** — después del bloque del plan 109 (líneas 672-675), agregar copiando **exactamente** ese patrón:
```python
    # ── Plan 268 — Explorador del grafo documental (default ON, editable por UI) ──
    STACKY_DOCS_GRAPH_EXPLORER_ENABLED: bool = os.getenv(
        "STACKY_DOCS_GRAPH_EXPLORER_ENABLED", "true"
    ).strip().lower() == "true"
```
   ⚠️ **No** poner anotación distinta ni `= True` pelado: el default EFECTIVO lo define `config.py`.

2. **`Stacky Agents/backend/services/harness_flags.py`** — agregar el `FlagSpec` **inmediatamente después** del de `STACKY_DOCS_GRAPH_ENABLED` (que termina en la línea 2295 aprox.):
```python
    FlagSpec(
        key="STACKY_DOCS_GRAPH_EXPLORER_ENABLED",
        default=True,  # Plan 268 — read-only puro: nace ON (regla de defaults 2026-07-27)
        type="bool",
        label="Explorador del grafo documental (Plan 268)",
        description=(
            "Plan 268 — Convierte la pestaña 'Grafo' de la página Docs en un "
            "explorador: barra de filtros (fuente, tipo de nodo, tipo de arista, "
            "grado, huérfanas, desactualizadas), búsqueda navegable con conteo y "
            "encuadre, foco por vecindario a profundidad 1-3 con historial, "
            "agrupación por fuente con color y colapso, controles de zoom y "
            "atajos de teclado, minimapa y vista previa del contenido del nodo "
            "seleccionado. 100% read-only: no escribe ningún documento. Si la "
            "apagás, la pestaña 'Grafo' vuelve a comportarse como en el Plan 111. "
            "Default ON."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DOCS_GRAPH_ENABLED",
    ),
```

3. **`Stacky Agents/backend/services/harness_flags.py`** — agregar la key a la tupla `"capacidades_optin"` de `_CATEGORY_KEYS` (arranca en la línea 120; la categoría `capacidades_optin` arranca en la 400), justo debajo de `"STACKY_DOCS_STALENESS_ENABLED"`:
```python
        "STACKY_DOCS_GRAPH_EXPLORER_ENABLED",   # Plan 268 — explorador del grafo (filtros/foco/peek)
```

4. **`Stacky Agents/backend/services/harness_flags_help.py`** — agregar la entrada de ayuda llana justo después de la **entrada completa** de `"STACKY_DOCS_GRAPH_ENABLED"`. ⚠️ (C16) Esa entrada **empieza** en la línea 274 y **cierra** con `),` en la línea **279**: hay que insertar **después de la 279**, no después de la 274 (si insertás en la 275 partís el `PlainHelp` del 109 al medio y el módulo no importa):
```python
    "STACKY_DOCS_GRAPH_EXPLORER_ENABLED": PlainHelp(
        what="Agrega herramientas para explorar el mapa de documentos: filtros, buscador que salta al resultado, foco en los vecinos de una nota y vista previa.",
        on_effect="Si la activás: la pestaña 'Grafo' de Docs suma barra de filtros, buscador con contador, botones de zoom, minimapa y un panel que muestra el principio del documento del nodo elegido.",
        off_effect="Si la apagás: la pestaña 'Grafo' se ve como antes, con el buscador simple y el botón Centrar.",
        example="Como pasar de una foto del mapa a un mapa con lupa, filtros y buscador.",
    ),
```
   [!] **(B9/v3) LIMITES REALES — el v2 decía "240 para todos" y era FALSO.** Verificados en `backend/tests/test_harness_flags_help.py:47-51`:

   | Campo | Tope real | Piso | El texto de arriba mide (medido con `len()`, v4) |
   |---|---|---|---|
   | `what` | **<= 200** | >= 10 | **146** OK (54 de margen) |
   | `on_effect` | <= 240 | — | **181** OK |
   | `off_effect` | <= 240 | — | **93** OK |
   | `example` | <= 300 | — | **71** OK |

   [!] **(v4)** El v3 anotaba 154 / 179 / 91 / 71; la medición real con el intérprete del repo da **146 / 181 / 93 / 71**. Los cuatro entran holgados, así que el fix de B9 sigue siendo correcto — pero las cifras van corregidas para que no persigas un número que no vas a ver. Los topes (`200/240/240/300`) están verificados contra `backend/tests/test_harness_flags_help.py:44-48`.

   El `what` que proponía el v2 medía **199 de 200**: entraba por **un** carácter mientras el plan le decía al implementador que tenía 41 de margen. El de arriba está acortado a 154 a propósito. **Antes de commitear, medí de verdad:**
```
# desde "Stacky Agents"
backend\.venv\Scripts\python.exe -c "from services.harness_flags_help import PLAIN_HELP as P; e=P['STACKY_DOCS_GRAPH_EXPLORER_ENABLED']; print(len(e.what),len(e.on_effect),len(e.off_effect),len(e.example))"
```
   -> debe imprimir 4 numeros dentro de `200/240/240/300`.
   [!] **Denylist de jerga CONGELADA** (`JARGON_DENYLIST`, mismo archivo, verificada): prohibido usar `MCP, TF-IDF, LLM, stdin, stdout, endpoint, frontmatter, prompt, token, regex, backend, frontend, gate, hook, runtime`, y prohibido citar keys `SCREAMING_SNAKE` o fases (`F1.1`). El texto propuesto no usa ninguno — no lo "mejores" agregando uno.
   [!] Ese archivo de test tiene **4 fallos preexistentes ajenos** (medidos en F0.0: `test_plain_help_covers_all_registry_keys`, `test_plain_help_fields_non_empty_and_bounded`, `test_plain_help_on_off_start_with_si`, `test_plain_help_avoids_jargon_denylist`; **4 failed / 4 passed**). Validá **solo** tu entrada con el comando de arriba; no lo cuentes como rojo tuyo, y verificá que el conteo siga siendo **4 failed** y no 5.

5. **`Stacky Agents/backend/tests/test_harness_flags.py`** — agregar la key al set `_CURATED_DEFAULTS_ON` (línea 467), en el bloque de docs:
```python
    "STACKY_DOCS_GRAPH_EXPLORER_ENABLED",         # Plan 268 — explorador read-only del grafo docs
```
   Sin esto, `test_default_known_only_for_curated` se pone **ROJO** (default=True fuera del set curado).

6. **`Stacky Agents/backend/tests/test_harness_flags_requires.py`** — agregar la arista al dict `_REQUIRES_MAP_FROZEN` (línea 120):
```python
    # Plan 268: el explorador solo tiene sentido si el grafo documental existe.
    # Profundidad 1: la madre (STACKY_DOCS_GRAPH_ENABLED) no declara requires (R4).
    "STACKY_DOCS_GRAPH_EXPLORER_ENABLED": "STACKY_DOCS_GRAPH_ENABLED",
```
   Sin esto, la aserción de la línea 316 (`actual == _REQUIRES_MAP_FROZEN`) se pone **ROJA** con "Extras: [...]".

7. **`Stacky Agents/deployment/harness_defaults.env`** — agregar **a mano** debajo de la línea 158 (`STACKY_DOCS_GRAPH_ENABLED=true`) y **antes** de la 159 (`STACKY_DOCS_RAG_HYBRID_ALPHA=1.0`):
```
STACKY_DOCS_GRAPH_EXPLORER_ENABLED=true
```
   ⚠️ (C16) Dos cosas, ninguna opcional: **(a)** el archivo está **ordenado alfabéticamente** y esa posición es la correcta (`..._GRAPH_ENABLED` < `..._GRAPH_EXPLORER_ENABLED` < `..._RAG_...`); **(b)** **NO** regenerar el archivo con el generador de `deployment/`. El archivo tiene deuda ajena congelada de otros planes; regenerarlo mete cambios que no son tuyos y contamina el diff. Se agrega **una línea, a mano**.

#### F0.2 — Exponer la flag por HTTP

**`Stacky Agents/backend/api/docs.py`** — en `get_doc_sources` (línea 52), agregar una línea después de la 60:
```python
    payload["graph_explorer_enabled"] = bool(getattr(config, "STACKY_DOCS_GRAPH_EXPLORER_ENABLED", False))  # Plan 268
```
⚠️ Usar `getattr(config, ...)` sobre la **instancia** `config` (no el módulo), igual que las 3 líneas de arriba.

**`Stacky Agents/frontend/src/api/endpoints.ts`** — en `interface DocsSourcesResponse` (línea 3356), agregar antes del `}` de la línea 3370:
```ts
  /** Plan 268 — true si STACKY_DOCS_GRAPH_EXPLORER_ENABLED está ON (gatea el explorador del grafo). */
  graph_explorer_enabled?: boolean;
```

#### F0.3 — `nodeIndexById` y fix del `findIndex` por frame

**`Stacky Agents/frontend/src/docs/docGraphModel.ts`** — agregar al final:
```ts
/** Índice id → posición en graph.nodes. O(n) una vez; reemplaza findIndex por label/frame.
 *  Grafo vacío/ausente → Map vacío. Ids duplicados: gana la PRIMERA aparición. */
export function nodeIndexById(graph: DocGraphResponse | undefined): Map<string, number> {
  const m = new Map<string, number>();
  const nodes = graph?.nodes ?? [];
  for (let i = 0; i < nodes.length; i++) {
    if (!m.has(nodes[i].id)) m.set(nodes[i].id, i);
  }
  return m;
}
```

**`Stacky Agents/frontend/src/components/docs/DocGraphView.tsx`** — reemplazar la línea 266-267:
```diff
-        const idx = graph.nodes.findIndex((n) => n.id === c.id);
-        const text = idx >= 0 ? graph.nodes[idx].label : c.id;
+        const idx = indexById.get(c.id);
+        const text = idx !== undefined ? graph.nodes[idx].label : c.id;
```
donde `indexById` se calcula con `useMemo` junto a `kindById` (línea 100) y se captura en el efecto:
```ts
  const indexById = useMemo(() => nodeIndexById(graph), [graph]);
```
⚠️ El efecto principal (línea 122, deps `[graph, selectedNodeId]`) ya se re-crea cuando cambia `graph`, así que la captura del `Map` es correcta. Agregar `nodeIndexById` al import de `../../docs/docGraphModel` (línea 14).

⚠️ **(C5) DEUDA QUE F1 TIENE QUE PAGAR — leer antes de escribir F1.** En F0 `indexById` se calcula sobre `graph` porque todavía no existe `visibleGraph`. En cuanto F1 introduce `visibleGraph`, **`indexById` PASA a calcularse sobre `visibleGraph`**, igual que `kindById` y `orphanSet`. Si queda apuntando a `graph` mientras `draw()` indexa `visibleGraph.nodes[i]`, los labels salen del nodo equivocado en cuanto haya un filtro activo — que es literalmente el riesgo R1 de este mismo plan. F1.3 lo lista explícito y el criterio de aceptación de F1 lo verifica con un grep.

#### F0.4 — Matemática de encuadre en `graphViewport.ts`

**`Stacky Agents/frontend/src/docs/graphViewport.ts`** — agregar después de `panBy` (línea 57):
```ts
/** Paso multiplicativo de un click en los botones + / − del zoom. */
export const ZOOM_STEP = 1.25;

/** Tope de escala al encuadrar: nunca ampliar más allá de esto aunque quepa. */
export const MAX_FIT_SCALE = 1.5;

export interface FitPoint { x: number; y: number; r?: number; }

/**
 * Encuadra `points` dentro de un canvas de width×height dejando `padding` px de margen.
 * - [] → IDENTITY (no hay nada que encuadrar).
 * - 1 punto (o todos coincidentes) → escala min(1.5, MAX_SCALE) y centrado en ese punto.
 * - Escala clampeada a [MIN_SCALE, MAX_SCALE] y además a MAX_FIT_SCALE.
 * El bounding box incluye el radio r de cada punto (default 0).
 */
export function fitViewport(
  points: FitPoint[],
  width: number,
  height: number,
  padding: number = 40
): Viewport {
  if (!points.length) return IDENTITY;
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const p of points) {
    const r = p.r ?? 0;
    if (p.x - r < minX) minX = p.x - r;
    if (p.y - r < minY) minY = p.y - r;
    if (p.x + r > maxX) maxX = p.x + r;
    if (p.y + r > maxY) maxY = p.y + r;
  }
  const spanX = Math.max(1e-6, maxX - minX);
  const spanY = Math.max(1e-6, maxY - minY);
  const availW = Math.max(1, width - 2 * padding);
  const availH = Math.max(1, height - 2 * padding);
  let scale = Math.min(availW / spanX, availH / spanY, MAX_FIT_SCALE);
  scale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale));
  const cx = (minX + maxX) / 2;
  const cy = (minY + maxY) / 2;
  return { scale, tx: width / 2 - cx * scale, ty: height / 2 - cy * scale };
}

/** Centra el punto de MUNDO (wx, wy) en el canvas, sin cambiar la escala. */
export function centerOn(vp: Viewport, wx: number, wy: number, width: number, height: number): Viewport {
  return { scale: vp.scale, tx: width / 2 - wx * vp.scale, ty: height / 2 - wy * vp.scale };
}

/** Zoom anclado al centro del canvas (para los botones + / −). */
export function zoomAtCenter(vp: Viewport, factor: number, width: number, height: number): Viewport {
  return zoomAt(vp, factor, width / 2, height / 2);
}
```

#### F0.5 — Estado puro del explorador

**Crear `Stacky Agents/frontend/src/docs/graphExplorerState.ts`:**
```ts
/**
 * graphExplorerState.ts — Plan 268 F0.
 * Estado PURO del explorador del grafo documental: filtros, búsqueda, foco,
 * grupos colapsados y peek. Sin React, sin DOM, sin fetch. Un reducer total:
 * toda acción desconocida devuelve el mismo objeto (identidad referencial).
 */
export type NodeKind = "note" | "code" | "missing";
export type EdgeKind = "md" | "wikilink" | "code_ref";

export interface GraphFilterState {
  /** [] = todas las fuentes pasan. */
  sourceIds: string[];
  /** [] = todos los tipos de nodo pasan. */
  kinds: NodeKind[];
  /** [] = todos los tipos de arista pasan. */
  edgeKinds: EdgeKind[];
  /** true = descartar nodos cuyo id está en graph.orphans. */
  hideOrphans: boolean;
  /** true = dejar solo nodos con has_stale === true. */
  onlyStale: boolean;
  /** descartar nodos con in_degree + out_degree < minDegree. 0 = sin corte. */
  minDegree: number;
}

export interface GraphExplorerState {
  filters: GraphFilterState;
  query: string;
  /** posición 0-based dentro de la lista de coincidencias. */
  matchIndex: number;
  focusRootId: string | null;
  /** 1..3 */
  focusDepth: number;
  /** pila de raíces anteriores; el tope es a donde vuelve FOCUS_BACK. */
  focusHistory: string[];
  /** claves de grupo colapsadas (ver groupKeyOf, F5). */
  collapsedGroups: string[];
  peekNodeId: string | null;
}

export const EMPTY_FILTERS: GraphFilterState = {
  sourceIds: [],
  kinds: [],
  edgeKinds: [],
  hideOrphans: false,
  onlyStale: false,
  minDegree: 0,
};

export const INITIAL_EXPLORER_STATE: GraphExplorerState = {
  filters: EMPTY_FILTERS,
  query: "",
  matchIndex: 0,
  focusRootId: null,
  focusDepth: 1,
  focusHistory: [],
  collapsedGroups: [],
  peekNodeId: null,
};

export const MIN_FOCUS_DEPTH = 1;
export const MAX_FOCUS_DEPTH = 3;

export type GraphExplorerAction =
  | { type: "SET_QUERY"; query: string }
  | { type: "NEXT_MATCH"; total: number }
  | { type: "PREV_MATCH"; total: number }
  | { type: "TOGGLE_SOURCE"; sourceId: string }
  | { type: "TOGGLE_KIND"; kind: NodeKind }
  | { type: "TOGGLE_EDGE_KIND"; edgeKind: EdgeKind }
  | { type: "SET_MIN_DEGREE"; minDegree: number }
  | { type: "TOGGLE_HIDE_ORPHANS" }
  | { type: "TOGGLE_ONLY_STALE" }
  | { type: "RESET_FILTERS" }
  | { type: "FOCUS_NODE"; nodeId: string }
  | { type: "SET_FOCUS_DEPTH"; depth: number }
  | { type: "FOCUS_BACK" }
  | { type: "CLEAR_FOCUS" }
  | { type: "TOGGLE_GROUP_COLLAPSED"; groupKey: string }
  | { type: "SET_PEEK"; nodeId: string | null }
  | { type: "RESET_ALL" };

function toggle<T>(list: T[], value: T): T[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value].sort();
}

export function graphExplorerReducer(
  state: GraphExplorerState,
  action: GraphExplorerAction
): GraphExplorerState {
  switch (action.type) {
    case "SET_QUERY":
      // toda query nueva resetea el cursor de coincidencias a la primera
      return { ...state, query: action.query, matchIndex: 0 };
    case "NEXT_MATCH":
      if (action.total <= 0) return { ...state, matchIndex: 0 };
      return { ...state, matchIndex: (state.matchIndex + 1) % action.total };
    case "PREV_MATCH":
      if (action.total <= 0) return { ...state, matchIndex: 0 };
      return { ...state, matchIndex: (state.matchIndex - 1 + action.total) % action.total };
    case "TOGGLE_SOURCE":
      return { ...state, filters: { ...state.filters, sourceIds: toggle(state.filters.sourceIds, action.sourceId) } };
    case "TOGGLE_KIND":
      return { ...state, filters: { ...state.filters, kinds: toggle(state.filters.kinds, action.kind) } };
    case "TOGGLE_EDGE_KIND":
      return { ...state, filters: { ...state.filters, edgeKinds: toggle(state.filters.edgeKinds, action.edgeKind) } };
    case "SET_MIN_DEGREE":
      return { ...state, filters: { ...state.filters, minDegree: Math.max(0, Math.floor(action.minDegree || 0)) } };
    case "TOGGLE_HIDE_ORPHANS":
      return { ...state, filters: { ...state.filters, hideOrphans: !state.filters.hideOrphans } };
    case "TOGGLE_ONLY_STALE":
      return { ...state, filters: { ...state.filters, onlyStale: !state.filters.onlyStale } };
    case "RESET_FILTERS":
      return { ...state, filters: EMPTY_FILTERS };
    case "FOCUS_NODE":
      if (state.focusRootId === action.nodeId) return state;
      return {
        ...state,
        focusRootId: action.nodeId,
        focusHistory: state.focusRootId ? [...state.focusHistory, state.focusRootId] : state.focusHistory,
        peekNodeId: action.nodeId,
      };
    case "SET_FOCUS_DEPTH": {
      const d = Math.min(MAX_FOCUS_DEPTH, Math.max(MIN_FOCUS_DEPTH, Math.floor(action.depth || 1)));
      return d === state.focusDepth ? state : { ...state, focusDepth: d };
    }
    case "FOCUS_BACK": {
      if (!state.focusHistory.length) return { ...state, focusRootId: null };
      const hist = state.focusHistory.slice(0, -1);
      const prev = state.focusHistory[state.focusHistory.length - 1];
      return { ...state, focusRootId: prev, focusHistory: hist, peekNodeId: prev };
    }
    case "CLEAR_FOCUS":
      return { ...state, focusRootId: null, focusHistory: [] };
    case "TOGGLE_GROUP_COLLAPSED":
      return { ...state, collapsedGroups: toggle(state.collapsedGroups, action.groupKey) };
    case "SET_PEEK":
      return state.peekNodeId === action.nodeId ? state : { ...state, peekNodeId: action.nodeId };
    case "RESET_ALL":
      return INITIAL_EXPLORER_STATE;
    default:
      return state;
  }
}
```

**Casos borde cubiertos:** query vacía (`matchIndex` vuelve a 0), `total = 0` (no divide por cero), `PREV_MATCH` desde 0 (envuelve al último), `depth` fuera de `[1,3]` (clampea), `FOCUS_BACK` con historial vacío (limpia el foco en vez de romper), re-focar el mismo nodo (no duplica historial), `minDegree` negativo o `NaN` (→ 0).

#### F0.6 — **[ADICIÓN ARQUITECTO #1]** Paleta REAL del grafo: que "theme-aware" deje de ser mentira

> **Por qué esto entra al plan (C1).** El plan 111 escribió `readPalette` leyendo `--color-accent`, `--color-success`, `--color-danger`, `--color-border`, `--color-text`, `--color-surface`. **Ninguno de esos tokens existe.** Evidencia, verificable en 5 segundos:
> ```
> # desde "Stacky Agents/frontend"
> grep -rn -- "--color-accent:" src        # → 0 hits
> grep -n -- "--color-" src/theme.css      # → solo --color-scheme (líneas 163, 243, 279)
> grep -n -- "--accent:\|--success:\|--danger:" src/theme.css   # → 17,19,21 (oscuro) y 187,189,191 (claro)
> ```
> Es decir: **el canvas del grafo nunca cambió de color con el tema**; siempre dibujó los hex de fallback del `.tsx`. Y `DocGraphView.module.css` usa 6 tokens inexistentes (`--color-accent`, `--color-border`, `--color-surface`, `--color-surface-2`, `--color-text`, `--color-text-muted`), que en CSS resuelven a *unset* — de ahí que la pestaña Grafo se vea "casi bien pero rara".
> El v1 de este plan **empeoraba** el problema: inventaba 6 tokens más (`--color-info/purple/teal/pink`) para los colores de grupo y, peor, exigía que los swatches de la leyenda usaran `var(--color-teal)` **sin fallback** (G8) — o sea, swatches transparentes en la leyenda mientras el canvas dibuja el hex de fallback: **la leyenda y el grafo mostrando colores distintos**.
> Costo de arreglarlo acá: un archivo puro de 30 líneas y un test. Beneficio: el paso 18 de F8 (cambiar de tema) pasa a significar algo, la leyenda y el canvas quedan garantizados iguales, y el bug no puede volver.

**Crear `Stacky Agents/frontend/src/docs/graphPalette.ts`:**
```ts
/**
 * graphPalette.ts — Plan 268 F0.6.
 * ÚNICA fuente de verdad de los tokens de color que el grafo documental lee del
 * tema. PURO: solo nombres y fallbacks, sin DOM. El test lee theme.css de disco y
 * verifica que cada token esté definido en el bloque oscuro Y en el claro.
 *
 * ⚠️ REGLA: acá NO se inventan tokens. Todo nombre de esta lista tiene que existir
 * ya en frontend/src/theme.css. Si hace falta un color nuevo, se elige otro token
 * existente; agregar tokens al tema es otro plan (contrato congelado del 138 §10.1,
 * vigilado por src/__tests__/themeTokens.test.ts).
 */

/** Rol semántico dentro del grafo → token del tema + fallback (por si el tema no cargó aún). */
export const GRAPH_PALETTE_TOKENS = {
  note:    { token: "--accent",       fallback: "#388bfd" },
  code:    { token: "--success",      fallback: "#3fb950" },
  missing: { token: "--danger",       fallback: "#f85149" },
  edge:    { token: "--border",       fallback: "#30363d" },
  stale:   { token: "--danger",       fallback: "#f85149" },
  label:   { token: "--text-primary", fallback: "#e6edf3" },
  labelBg: { token: "--bg-panel",     fallback: "#161b22" },
  halo:    { token: "--accent-hot",   fallback: "#58a6ff" },
  ring:    { token: "--text-primary", fallback: "#e6edf3" },
} as const;

/** Colores por SLOT de grupo (F5). Orden fijo = orden de asignación de slots.
 *  Los 6 existen en el bloque oscuro y en el claro de theme.css. */
export const GROUP_SLOT_TOKENS = [
  { token: "--accent",            fallback: "#388bfd" },  // slot 0
  { token: "--accent-hot",        fallback: "#58a6ff" },  // slot 1
  { token: "--warn",              fallback: "#d29922" },  // slot 2
  { token: "--agent-business",    fallback: "#a371f7" },  // slot 3
  { token: "--agent-functional",  fallback: "#f78166" },  // slot 4
  { token: "--agent-custom",      fallback: "#8b949e" },  // slot 5
] as const;

/** Todos los nombres de token usados por el grafo (para el test de existencia). */
export function allGraphTokenNames(): string[] {
  const a = Object.values(GRAPH_PALETTE_TOKENS).map((e) => e.token);
  const b = GROUP_SLOT_TOKENS.map((e) => e.token);
  return Array.from(new Set([...a, ...b])).sort();
}

/** Parseo PURO de un CSS: nombres de custom properties DEFINIDAS (`--x: valor;`). */
export function definedTokenNames(css: string): Set<string> {
  const out = new Set<string>();
  const re = /(--[a-zA-Z0-9-]+)\s*:/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(css)) !== null) out.add(m[1]);
  return out;
}

/**
 * Corta el CSS del tema en sus dos bloques: el `:root` base (oscuro) y el bloque
 * del tema claro. Devuelve `{ dark, light }` con el TEXTO de cada uno.
 * Criterio: el bloque claro arranca en el selector que contiene `data-theme="light"`.
 * Si no se encuentra ese selector, `light` queda vacio (y el test correspondiente
 * falla, que es el comportamiento deseado: significa que el tema claro se rompio).
 */
export function splitThemeBlocks(css: string): { dark: string; light: string } {
  const marker = css.indexOf('[data-theme="light"]');
  if (marker < 0) return { dark: css, light: "" };
  const open = css.indexOf("{", marker);
  const close = css.indexOf("}", open);
  return {
    dark: css.slice(0, marker),
    light: open < 0 || close < 0 ? "" : css.slice(open + 1, close),
  };
}
```
[!] **(B2/v3) Este bloque se copia TAL CUAL y compila.** El v2 dejaba `splitThemeBlocks` como una firma **sin cuerpo** en medio de un archivo que ya traía dos funciones **con** cuerpo. Compilado con el `tsc` del repo daba `error TS2391: Function implementation is missing or not immediately following the declaration`, y como el gate de toda fase es `npx tsc --noEmit` con 0 errores, **F0 no podía cerrar**. Regla para el resto del plan: los bloques de F1/F4/F5/F6/F7 que muestran **solo firmas** son *contrato* (llevan su pseudocódigo aparte y así están rotulados); los que dicen "Crear `<archivo>`:" son **código literal completo**.

**Referencia de los bloques del tema (verificada 2026-07-28):** `:root { ... }` = líneas **3-164** (oscuro, con `--color-scheme: dark` en la 163); `:root[data-theme="light"] { ... }` = líneas **172-244** (claro, con `--color-scheme: light` en la 243). Los 13 tokens de `GRAPH_PALETTE_TOKENS` + `GROUP_SLOT_TOKENS` están definidos **en los dos**.

**Cablear en `DocGraphView.tsx`** — **DOS ediciones, ninguna opcional.**

**(a) [!] (B3/v3) PRIMERO el `interface Palette` (líneas 40-50), o nada compila.** Hoy tiene exactamente 9 campos (`note, code, missing, edge, stale, label, labelBg, halo, ring`) y **ninguno se llama `groups`**. El v2 mandaba devolver `groups` desde `readPalette` sin tocar la interfaz; compilado verbatim da `error TS2353: Object literal may only specify known properties, and 'groups' does not exist in type 'Palette'`. Agregar **una línea**, antes del `}` de la línea 50:
```diff
   halo: string;
   ring: string;
+  /** Plan 268 F0.6 — un color por SLOT de grupo (F5). Orden = GROUP_SLOT_TOKENS. */
+  groups: string[];
 }
```
**Esta es la costura F0.6->F5 y se paga entera en F0.6**: F5 solo consume `pal.groups`, no vuelve a tocar ni la interfaz ni `readPalette`.

**(b) DESPUES** `readPalette` (líneas 52-69) pasa a:
```ts
import { GRAPH_PALETTE_TOKENS, GROUP_SLOT_TOKENS } from "../../docs/graphPalette";

function readPalette(el: HTMLElement): Palette {
  const cs = getComputedStyle(el);
  const v = (name: string, fallback: string) => cs.getPropertyValue(name).trim() || fallback;
  const t = GRAPH_PALETTE_TOKENS;
  return {
    note:    v(t.note.token,    t.note.fallback),
    code:    v(t.code.token,    t.code.fallback),
    missing: v(t.missing.token, t.missing.fallback),
    edge:    v(t.edge.token,    t.edge.fallback),
    stale:   v(t.stale.token,   t.stale.fallback),
    label:   v(t.label.token,   t.label.fallback),
    labelBg: v(t.labelBg.token, t.labelBg.fallback),
    halo:    v(t.halo.token,    t.halo.fallback),
    ring:    v(t.ring.token,    t.ring.fallback),
    groups:  GROUP_SLOT_TOKENS.map((g) => v(g.token, g.fallback)),   // Plan 268 F5
  };
}
```
⚠️ El campo `groups: string[]` se agrega **acá, en F0.6** (F5 ya lo asume; el v1 lo agregaba en F5.2 con tokens inventados).

**Reparar `DocGraphView.module.css`** — sustitución 1 a 1, **sin agregar tokens ni hex** (el ratchet de hex se mide sobre `*.module.css`, así que meter un fallback hex sería deuda nueva):

| Lo que dice hoy (no existe) | Lo que tiene que decir |
|---|---|
| `var(--color-accent)` | `var(--accent)` |
| `var(--color-border)` | `var(--border)` |
| `var(--color-surface)` | `var(--bg-panel)` |
| `var(--color-surface-2)` | `var(--bg-elev)` |
| `var(--color-text)` | `var(--text-primary)` |
| `var(--color-text-muted)` | `var(--text-muted)` |

[!] **(I4/v3) Los 3 `style={{ background: "var(--color-…)" }}` de la leyenda vieja (`DocGraphView.tsx:507`, `:511`, `:515`) SE CORRIGEN — es OBLIGATORIO, no opcional.** El v2 lo dejaba como "sí se puede (y conviene)" mientras DoD-11 lo exigía **binario** (0 hits de `var(--color-` en los archivos del plan): opcional contra binario es una contradicción que un modelo menor resuelve salteándolo. Sustitución exacta, **conservando el fallback** (no se **quitan** los tres `style={{`: ya están contados en el baseline de `uiDebtRatchet`, quitarlos bajaría el conteo y eso está permitido pero cambia el camino flag-OFF; mantenerlos deja el conteo **igual** y el ratchet en delta 0):
```diff
-<span className={styles.swatch} style={{ background: "var(--color-accent, #4a9eff)" }} />
+<span className={styles.swatch} style={{ background: "var(--accent, #388bfd)" }} />
-<span className={styles.swatch} style={{ background: "var(--color-success, #3fb950)" }} />
+<span className={styles.swatch} style={{ background: "var(--success, #3fb950)" }} />
-<span className={styles.swatch} style={{ background: "var(--color-danger, #f85149)" }} />
+<span className={styles.swatch} style={{ background: "var(--danger, #f85149)" }} />
```
El conteo de `style={{` **no cambia** (3 antes, 3 después) ⇒ `uiDebtRatchet` no se mueve, y la leyenda del camino flag-OFF pasa a acompañar el tema igual que el canvas.

**Test nuevo `Stacky Agents/frontend/src/docs/graphPalette.test.ts`** (puro, lee el archivo con `fs`, igual que hacen los ratchets — no necesita DOM):
- `it("todos los tokens del grafo estan definidos en el bloque OSCURO de theme.css")`
- `it("todos los tokens del grafo estan definidos en el bloque CLARO de theme.css")`
- `it("ningun token del grafo empieza con --color- (esa familia no existe en el tema)")`
- `it("los 6 slots de grupo son tokens DISTINTOS entre si")`
- `it("definedTokenNames encuentra una custom property y ignora un var() de uso")`
- `it("splitThemeBlocks separa el bloque claro por --color-scheme: light")`
- `it("DocGraphView.module.css no usa ningun token inexistente")` — lee `src/components/docs/DocGraphView.module.css`, `src/components/docs/DocGraphExplorer.module.css` (si ya existe) **y `src/components/docs/DocGraphView.tsx`** (I4/v3: ahí viven los 3 `style={{ background: "var(--…)" }}` de la leyenda), extrae todos los `var(--x)` **usados** y verifica que cada uno esté en `definedTokenNames(theme.css)`. **Este caso es el que impide que el bug vuelva.**
  [!] **Alcance CERRADO (B7/v3): esos 3 archivos y nada más.** El test **no** barre `src/components/docs/` entero: `DocBacklinksPanel.module.css`, `DocCoveragePanel.module.css` y `DocumenterResultPanel.tsx` arrastran **32 hits** de `var(--color-*)` de deuda ajena que este plan no puede tocar (DoD-9, y hay 6 agentes en el mismo árbol). Ampliar el alcance deja el test rojo para siempre. Queda anotado en DoD-11 como candidato al plan siguiente.

⚠️ El último caso empieza en **ROJO** (los 6 tokens actuales de `DocGraphView.module.css` no existen) y pasa a verde con la sustitución de la tabla. Eso es TDD correcto: el test reproduce un bug **real y vivo** antes de arreglarlo.

**Ruta del tema (C14):** es `Stacky Agents/frontend/src/theme.css`. **No** existe `frontend/src/styles/theme.css` (el v1 lo citaba mal).

#### Tests de F0 (TDD — escribir primero)

**`Stacky Agents/frontend/src/docs/graphViewport.test.ts`** (EDITAR el existente; agregar un `describe`):
- `it("fitViewport con lista vacia devuelve IDENTITY")`
- `it("fitViewport con un solo punto centra y no supera MAX_FIT_SCALE")`
- `it("fitViewport deja todos los puntos dentro del canvas con padding")` — 500 puntos generados con `x = (i*37)%800`, `y = (i*53)%600`; para cada punto, `toScreen(vp, x, y)` debe caer en `[padding-1, w-padding+1]` × `[padding-1, h-padding+1]`.
- `it("fitViewport clampea la escala a MIN_SCALE con un grafo gigantesco")` — puntos separados 100000 px.
- `it("centerOn deja el punto del mundo en el centro de la pantalla")`
- `it("zoomAtCenter mantiene fijo el punto del mundo bajo el centro")`
- `it("ZOOM_STEP aplicado y luego su inverso vuelve al viewport original")`

**`Stacky Agents/frontend/src/docs/graphExplorerState.test.ts`** (NUEVO):
- `it("SET_QUERY resetea matchIndex a 0")`
- `it("NEXT_MATCH cicla 0->1->2->0 con total=3")`
- `it("PREV_MATCH desde 0 envuelve al ultimo")`
- `it("NEXT_MATCH con total=0 deja matchIndex en 0")`
- `it("TOGGLE_KIND agrega y saca el mismo kind")`
- `it("TOGGLE_SOURCE mantiene la lista ordenada")`
- `it("SET_MIN_DEGREE clampea negativos a 0")`
- `it("RESET_FILTERS vuelve a EMPTY_FILTERS sin tocar la query")`
- `it("FOCUS_NODE apila la raiz anterior en focusHistory")`
- `it("FOCUS_NODE sobre la misma raiz no duplica historial")`
- `it("FOCUS_BACK vuelve a la raiz anterior y desapila")`
- `it("FOCUS_BACK con historial vacio limpia el foco")`
- `it("SET_FOCUS_DEPTH clampea a [1,3]")`
- `it("TOGGLE_GROUP_COLLAPSED agrega y saca la clave")`
- `it("accion desconocida devuelve el MISMO objeto de estado")`

**`Stacky Agents/frontend/src/docs/docGraphModel.test.ts`** (EDITAR; agregar):
- `it("nodeIndexById mapea cada id a su posicion")`
- `it("nodeIndexById con grafo vacio devuelve Map vacio")`
- `it("nodeIndexById con undefined no lanza")`

**`Stacky Agents/backend/tests/test_docs_api.py`** (EDITAR; agregar):
- `test_sources_expone_graph_explorer_enabled` — hace `GET /api/docs/sources` y verifica que la clave `graph_explorer_enabled` esté presente y sea `bool`.

**Comandos exactos (desde `Stacky Agents/frontend` salvo el último):**
```
npx vitest run src/docs/graphViewport.test.ts
npx vitest run src/docs/graphExplorerState.test.ts
npx vitest run src/docs/docGraphModel.test.ts
npx vitest run src/docs/graphPalette.test.ts
npx vitest run src/__tests__/uiDebtRatchet.test.ts
npx tsc --noEmit
```
```
# desde "Stacky Agents"  --  OJO: backend\.venv\ , NO .venv\   (B1/v3)
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_docs_api.py -q
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_harness_flags.py -q
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_harness_flags_requires.py -q
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_harness_flags_help.py -q
```
**Baseline medido (F0.0, 2026-07-28):** `test_docs_api.py` -> **10 passed** (verde limpio; tu test nuevo debe dejarlo en **11 passed**). `test_harness_flags_help.py` -> **4 failed / 4 passed** (rojo ajeno; no puede pasar a 5 failed).

**Criterio de aceptación binario.** Los **4** archivos de test frontend **propios** en verde absoluto (`graphViewport`, `graphExplorerState`, `docGraphModel`, `graphPalette`); `npx tsc --noEmit` con **0 errores**; `test_docs_api.py` en **11 passed** (los 10 del baseline + el tuyo); `test_harness_flags.py` y `test_harness_flags_requires.py` en **verde absoluto**; `test_harness_flags_help.py` en **4 failed / 4 passed exactos** (mismo conteo que F0.0) y los 4 largos dentro de `200/240/240/300`; **`uiDebtRatchet` y `motionDebtRatchet` en DELTA** (regla de abajo). Además: `git diff --exit-code -- ":/Stacky Agents/frontend/package.json"` sale con código 0.

> **(B6/v3) REGLA DELTA DE LOS RATCHETS — aplica a F0, F1, F3, F5, F6 y al DoD.** Los dos ratchets **ya están rojos por deuda AJENA** (medido en F0.0). Exigir "verde sin regenerar baseline", como hacía el v2 en 7 lugares, es **insatisfacible**, y el único atajo que le deja a un modelo menor es regenerar el baseline — justo lo prohibido, y que además absorbería en silencio la deuda **propia** del plan. El criterio correcto es:
> 1. Correr el ratchet y **leer la lista de archivos** de la salida.
> 2. **Ningún** archivo tocado o creado por el plan 268 puede aparecer en esa lista.
> 3. El **número de líneas `REGRESION`** no puede ser mayor que el de F0.0 — comparando **contra la cifra que devuelve el mismo comando** (ver el aviso de F0.0: `grep -c` da **4** y **14**, no 2 y 7, porque vitest imprime cada error dos veces).
> 4. **Prohibido** regenerar el baseline (`UI_DEBT_RE...`) por cualquier motivo.
>
> Comando de verificación del delta, desde `Stacky Agents/frontend`:
> ```
> npx vitest run src/__tests__/uiDebtRatchet.test.ts 2>&1 | grep -c "REGRESION"          # F0.0 = 4
> npx vitest run src/__tests__/motionDebtRatchet.test.ts 2>&1 | grep -c "REGRESION"      # F0.0 = 14
> npx vitest run src/__tests__/uiDebtRatchet.test.ts 2>&1 | grep "REGRESION" | grep -E "DocGraph|docs/"
> npx vitest run src/__tests__/motionDebtRatchet.test.ts 2>&1 | grep "REGRESION" | grep -E "DocGraph|docs/"
> ```
> Los dos primeros no pueden **subir** respecto de F0.0 (**4** y **14** al 2026-07-28); los dos últimos deben dar **0 líneas**.

**Flag que la protege.** `STACKY_DOCS_GRAPH_EXPLORER_ENABLED` — **default ON**. (Los helpers puros no están gateados: son código muerto hasta que F1+ los use; el gate está en el montaje de la UI.)

**Impacto por runtime.**
- **Codex CLI:** ninguno — F0 no invoca ningún runtime. Fallback: N/A.
- **Claude Code CLI:** ninguno — ídem. Fallback: N/A.
- **GitHub Copilot Pro:** ninguno — ídem. Fallback: N/A.
- Razón concreta: el único consumo de datos es `GET /api/docs/graph`, servido por `backend/services/doc_graph.py`, que parsea markdown y git — **cero LLM**. No hay superficie donde los runtimes puedan diferir.

**Trabajo del operador: ninguno.**

---

### F1 — Filtros del grafo (fuente, tipo de nodo, tipo de arista, grado, huérfanas, stale)

**Objetivo.** Que el operador pueda reducir el grafo a lo que le importa con una barra de filtros visible, y que el canvas dibuje exactamente ese subgrafo.

**Valor.** Cierra el gap (a). Es lo que convierte un hairball de N fuentes mezcladas en un mapa legible.

**Archivos.**
- CREAR `Stacky Agents/frontend/src/docs/graphFilters.ts`
- CREAR `Stacky Agents/frontend/src/docs/graphFilters.test.ts`
- CREAR `Stacky Agents/frontend/src/components/docs/DocGraphFilterBar.tsx`
- CREAR `Stacky Agents/frontend/src/components/docs/DocGraphExplorer.module.css`
- EDITAR `Stacky Agents/frontend/src/components/docs/DocGraphView.tsx`
- EDITAR `Stacky Agents/frontend/src/pages/DocsPage.tsx`

#### F1.1 — `graphFilters.ts` (puro)

> [!] **Bloque de CONTRATO, no código literal (regla fijada en F0.6/B2).** Lo de abajo son **firmas + JSDoc**: el cuerpo de `applyGraphFilters` está en el pseudocódigo que sigue, y `export const EMPTY_GRAPH: DocGraphResponse;` es una **declaración de contrato** — como código literal no compila (una `const` necesita inicializador). Al implementar: escribí los cuerpos y dale a `EMPTY_GRAPH` su valor (`{ nodes: [], edges: [], orphans: [], sources: [], ... }` con la forma completa de `DocGraphResponse`). Los bloques que empiezan con "Crear `<archivo>`:" **sí** son código literal completo.

```ts
/**
 * graphFilters.ts — Plan 268 F1.
 * Filtrado PURO de un DocGraphResponse. Devuelve OTRO DocGraphResponse (misma
 * forma) con el subconjunto de nodos/aristas que pasa el filtro. No muta la entrada.
 */
import type { DocGraphResponse, DocGraphNode, DocGraphEdge } from "./docGraphModel";
import type { GraphFilterState } from "./graphExplorerState";

export interface FilterOption { value: string; label: string; count: number; }
export interface FilterOptions {
  sources: FilterOption[];   // ordenadas por label asc
  kinds: FilterOption[];     // orden fijo: note, code, missing
  edgeKinds: FilterOption[]; // orden fijo: md, wikilink, code_ref
  staleCount: number;
  orphanCount: number;
  maxDegree: number;
}

/**
 * Opciones disponibles derivadas del grafo COMPLETO (no del filtrado): la barra
 * no debe cambiar de forma cuando el operador filtra.
 *
 * (C11) Reglas EXACTAS, no interpretables:
 *  - `sources`: una entrada por cada `source_id` NO VACÍO que aparezca en al menos
 *    un nodo. `count` = cuántos nodos lo tienen. El `label` sale de `graph.sources`
 *    (`DocGraphSource.label`, docGraphModel.ts:38-44) buscando por `id`; si ese id
 *    NO está en graph.sources, el label ES el propio id. Orden: por `label` asc con
 *    `localeCompare`, y a igual label por `value` asc. Las fuentes declaradas en
 *    graph.sources con 0 nodos NO se listan (un chip que no filtra nada es ruido).
 *  - `kinds`: SIEMPRE las 3 entradas en orden fijo note, code, missing, aun con
 *    count 0 (la barra no debe cambiar de forma). Labels: "Notas", "Código", "Faltantes".
 *  - `edgeKinds`: SIEMPRE las 3 en orden fijo md, wikilink, code_ref, aun con count 0.
 *    Labels: "Links markdown", "Wikilinks", "Referencias a código".
 *  - `staleCount`: nodos con has_stale === true. `orphanCount`: graph.orphans.length.
 *  - `maxDegree`: max(in_degree + out_degree) sobre todos los nodos; 0 si no hay nodos.
 *  - graph undefined o sin nodos → sources [], kinds y edgeKinds con las 3 entradas
 *    en count 0, staleCount 0, orphanCount 0, maxDegree 0.
 */
export function availableFilterOptions(graph: DocGraphResponse | undefined): FilterOptions

/**
 * Aplica los filtros. Reglas, en este orden:
 *  1. nodos: kind ∈ filters.kinds (si kinds no está vacío)
 *  2. nodos: source_id ∈ filters.sourceIds (si sourceIds no está vacío).
 *     ⚠️ Los nodos kind !== "note" pueden tener source_id vacío: solo se filtran
 *     por fuente si su source_id es no vacío; si es vacío, PASAN siempre.
 *  3. nodos: si hideOrphans, descartar los que están en graph.orphans
 *  4. nodos: si onlyStale, dejar solo has_stale === true
 *  5. nodos: (in_degree + out_degree) >= minDegree
 *  6. aristas: kind ∈ filters.edgeKinds (si edgeKinds no está vacío)
 *  7. aristas: source Y target deben haber sobrevivido al filtro de nodos
 * Devuelve un DocGraphResponse nuevo con nodes/edges filtrados, `orphans`
 * recortado a los nodos vivos, y `sources`/`stats`/`doc_health` copiados tal cual.
 * Entrada undefined → devuelve un grafo vacío válido (ver EMPTY_GRAPH).
 */
export function applyGraphFilters(
  graph: DocGraphResponse | undefined,
  filters: GraphFilterState
): DocGraphResponse

/** Grafo vacío pero estructuralmente válido (nunca null: el canvas no debe ramificar). */
export const EMPTY_GRAPH: DocGraphResponse;
```

Pseudocódigo de `applyGraphFilters`:
```
if (!graph) return EMPTY_GRAPH
kindSet   = new Set(filters.kinds)
srcSet    = new Set(filters.sourceIds)
edgeSet   = new Set(filters.edgeKinds)
orphanSet = new Set(graph.orphans ?? [])

keptNodes = []
for (n of graph.nodes) {
  if (kindSet.size && !kindSet.has(n.kind)) continue
  if (srcSet.size && n.source_id && !srcSet.has(n.source_id)) continue
  if (filters.hideOrphans && orphanSet.has(n.id)) continue
  if (filters.onlyStale && n.has_stale !== true) continue
  if (((n.in_degree||0) + (n.out_degree||0)) < filters.minDegree) continue
  keptNodes.push(n)
}
alive = new Set(keptNodes.map(n => n.id))
keptEdges = graph.edges.filter(e =>
  (!edgeSet.size || edgeSet.has(e.kind)) && alive.has(e.source) && alive.has(e.target))
return { ...graph,
         nodes: keptNodes,
         edges: keptEdges,
         orphans: (graph.orphans ?? []).filter(id => alive.has(id)) }
```

**Casos borde:** grafo vacío (`nodes: []` → devuelve vacío, no lanza); 1 nodo sin aristas (pasa si `minDegree === 0`, se descarta si `minDegree >= 1`); ciclo A→B→A (ambas aristas sobreviven si ambos nodos sobreviven); filtro que deja 0 nodos (devuelve `nodes: []`, `edges: []` — el canvas ya tiene su `EmptyState` en `DocGraphView.tsx:529-533`); nodo `code` con `source_id: ""` filtrando por fuente (PASA, regla 2); `has_stale` ausente porque la flag 114 está OFF (`onlyStale` deja 0 nodos — es correcto y la barra debe deshabilitar ese toggle si `staleCount === 0`).

#### F1.2 — `DocGraphFilterBar.tsx` (cascarón delgado, **cero lógica**)

Props exactas:
```ts
interface DocGraphFilterBarProps {
  options: FilterOptions;             // de availableFilterOptions
  filters: GraphFilterState;
  onToggleSource: (sourceId: string) => void;
  onToggleKind: (kind: NodeKind) => void;
  onToggleEdgeKind: (edgeKind: EdgeKind) => void;
  onSetMinDegree: (n: number) => void;
  onToggleHideOrphans: () => void;
  onToggleOnlyStale: () => void;
  onReset: () => void;
  visibleNodes: number;               // solo para el contador
  totalNodes: number;
}
```
Render (todo con clases del `.module.css`, **cero `style={{`**):
- Un `<fieldset>` por grupo, con `<button type="button" aria-pressed={...}>` por opción, mostrando `label (count)`.
- Un `<input type="range" min="0" max={options.maxDegree} step="1">` para `minDegree` con su `<label>`.
- Dos `<button aria-pressed>` para `hideOrphans` y `onlyStale`. El de `onlyStale` va `disabled` si `options.staleCount === 0`, con `title="No hay notas desactualizadas (o la señal está apagada)"`.
- Un `<button>` "Limpiar filtros", `disabled` cuando los filtros son `EMPTY_FILTERS`.
- Un `<span>` con `Mostrando {visibleNodes} de {totalNodes} nodos`.

#### F1.3 — Cableado en `DocGraphView.tsx`

1. Agregar props opcionales (backward-compatible, G9):
```ts
interface DocGraphViewProps {
  graph: DocGraphResponse;
  onOpenNoteById: (nodeId: string) => void;
  selectedNodeId?: string | null;
  /** Plan 268 — si false/undefined, el componente se comporta EXACTAMENTE como en el 111. */
  explorerEnabled?: boolean;
  /** Plan 268 F6 — necesario para el peek. */
  projectName?: string;
}
```
2. Dentro del componente:
```ts
const [ui, dispatch] = useReducer(graphExplorerReducer, INITIAL_EXPLORER_STATE);
const filterOptions = useMemo(() => availableFilterOptions(graph), [graph]);
const visibleGraph = useMemo(
  () => (explorerEnabled ? applyGraphFilters(graph, ui.filters) : graph),
  [explorerEnabled, graph, ui.filters]
);
```
[!] **(N1/v4) PRIMERO los imports, o esto NO COMPILA — 5 × `TS2304`.** Los 5 símbolos del bloque de arriba (`useReducer`, `graphExplorerReducer`, `INITIAL_EXPLORER_STATE`, `availableFilterOptions`, `applyGraphFilters`) **no** están importados en `DocGraphView.tsx`. Compilado verbatim sobre un espejo del frontend, `npx tsc --noEmit` sale con **exit 2**:
```
src/components/docs/DocGraphView.tsx(122,24): error TS2304: Cannot find name 'useReducer'.
src/components/docs/DocGraphView.tsx(122,35): error TS2304: Cannot find name 'graphExplorerReducer'.
src/components/docs/DocGraphView.tsx(122,57): error TS2304: Cannot find name 'INITIAL_EXPLORER_STATE'.
src/components/docs/DocGraphView.tsx(123,37): error TS2304: Cannot find name 'availableFilterOptions'.
src/components/docs/DocGraphView.tsx(125,28): error TS2304: Cannot find name 'applyGraphFilters'.
```
Y el criterio de aceptación de F1 exige `tsc --noEmit` con **0 errores** ⇒ **F1 no cerraría**. Antes de pegar el bloque, aplicar la fila **F1.3** de la tabla de **§6.0**, que son estas ediciones (verificadas: con ellas, `tsc --noEmit` vuelve a **exit 0**):
```diff
-import { useEffect, useMemo, useRef, useState } from "react";
+import { useEffect, useMemo, useReducer, useRef, useState } from "react";
+import { graphExplorerReducer, INITIAL_EXPLORER_STATE } from "../../docs/graphExplorerState";
+import { applyGraphFilters, availableFilterOptions } from "../../docs/graphFilters";
+import DocGraphFilterBar from "./DocGraphFilterBar";
```
3. **⚠️ INVARIANTE CRÍTICA I1 (no romper):** el efecto de layout (línea 122) y el dibujo de labels usan **el mismo array de nodos por índice** (`state.nodes[i]` ↔ `graph.nodes[i]`, líneas 247 y 266). Por lo tanto, a partir de esta fase **todas** las referencias a `graph` **dentro del efecto de layout y del `draw()`** pasan a ser `visibleGraph`, y la lista de deps del efecto (línea 492) pasa de `[graph, selectedNodeId]` a `[visibleGraph, selectedNodeId]`. **No mezclar los dos objetos.**

   **(C5) Lista CERRADA de derivados — copiar tal cual, no interpretar:**

   | Símbolo | Antes | Después | Por qué |
   |---|---|---|---|
   | `kindById` (línea 100) | `graph` | **`visibleGraph`** | decide el cursor y si un click abre nota |
   | `orphanSet` (línea 106) | `graph` | **`visibleGraph`** | alpha de huérfanas por id |
   | `indexById` (F0.3) | `graph` | **`visibleGraph`** | **se indexa por posición**: si difiere del array del layout, labels cruzados |
   | `nodeCount` (línea 108) | `graph` | **`visibleGraph`** | decide el `EmptyState` (`:529`) |
   | `initLayout(...)` (líneas 148 y 463) | `graph` | **`visibleGraph`** | el layout ES el subgrafo visible |
   | `graph.nodes[i]` en `draw()` (línea 247) | `graph` | **`visibleGraph`** | ídem I1 |
   | `filterOptions` (F1.3-2) | — | **`graph`** (¡el completo!) | **excepción a propósito**: la barra no debe cambiar de forma al filtrar |
   | `totalNodes` del contador | — | **`graph`** | es el denominador "N de TOTAL" |

   **Las dos últimas filas son las ÚNICAS referencias legítimas a `graph` que quedan fuera del efecto.**

   **⚠️ INVARIANTE CRÍTICA I2 — refs para todo lo que lee `draw()` (C2, guardarraíl G12).** `draw()` vive **dentro** del efecto de deps `[visibleGraph, selectedNodeId]`. Cualquier valor que cambie sin cambiar esas deps queda **congelado en el closure**. El archivo ya resuelve esto con `filterRef`/`hoverRef`/`paletteRef` (líneas 89-95). A partir de acá se agregan estos refs, **todos declarados en F1 aunque los llene una fase posterior** (así ninguna fase tiene que tocar la firma del efecto de nuevo):
```ts
  // --- refs que lee draw() (I2) ---
  const activeMatchIdRef   = useRef<string | null>(null);   // F2 — resultado de búsqueda activo
  const groupSlotsRef      = useRef<Map<string, number>>(new Map()); // F5 — slot de color por grupo
  const explorerEnabledRef = useRef<boolean>(false);        // F7 — gatea el LOD y el minimapa
  const canvasSizeRef      = useRef<{ w: number; h: number }>({ w: 0, h: 0 }); // F2/F3 — encuadre

  // --- refs de COMANDO: funciones definidas DENTRO del efecto de layout y
  //     llamadas desde afuera (JSX u otros efectos). Patrón ya usado por el
  //     archivo: resetViewRef (línea 95) y drawRef (93). (B5/v3) ---
  const setViewportRef = useRef<(next: Viewport) => void>(() => {});
  const zoomInRef      = useRef<() => void>(() => {});
  const zoomOutRef     = useRef<() => void>(() => {});
  const fitRef         = useRef<() => void>(() => {});
```
[!] **(B5/v3) Los cuatro refs de COMANDO son obligatorios y nacen en F1**, aunque F1 no los llene. El v2 definía `setViewport` como función **interna** del efecto de layout (F3) y después ordenaba, desde **otro** `useEffect` (F2.2-4), "este efecto **debe** usar `setViewport(...)`". Un efecto **no puede ver el closure de otro**: eso es `TS2304` y rompe el gate `tsc --noEmit` de F2. La regla, sin excepciones: **desde afuera del efecto de layout siempre se llama `xxxRef.current(...)`**; el nombre pelado `setViewport` solo existe **dentro** del efecto.

[!] **(B4/v3) Placeholders obligatorios en F1 — sin esto F1 NO COMPILA.** El efecto de sincronización de abajo lee `activeMatchId` (nace en **F2**) y `groupSlots` (nace en **F5**). El v2 lo mandaba escribir entero en F1 con el comentario "null hasta F2 / Map vacío hasta F5" pero **sin declararlos**; compilado verbatim da **4 errores** `TS2552: Cannot find name 'activeMatchId'` / `Cannot find name 'groupSlots'`, y el criterio de F1 exige `tsc --noEmit` con 0 errores. En F1 se declaran así, **inmediatamente antes** del efecto:
```ts
  // Plan 268 — placeholders de F1. F2 REEMPLAZA la primera línea por el matchAt real
  // y F5 la segunda por assignGroupColorSlots(...). El tipo NO cambia en ninguna fase,
  // así que el efecto de sincronización de abajo se escribe UNA sola vez y nunca se toca.
  const activeMatchId: string | null = null;                  // F2 lo reemplaza
  const groupSlots: Map<string, number> = EMPTY_GROUP_SLOTS;  // F5 lo reemplaza
```
y arriba del componente, al lado de `LABEL_FONT_PX` (línea 77), **una constante módulo** para que la identidad referencial no cambie por render (si no, el efecto de sincronización se dispara en **cada** render):
```ts
const EMPTY_GROUP_SLOTS: Map<string, number> = new Map();
```
**Contrato de la costura F1->F2->F5:** F2 sustituye la línea de `activeMatchId` por `const activeMatchId = matchAt(matches, ui.matchIndex);` y F5 la de `groupSlots` por `const groupSlots = useMemo(() => assignGroupColorSlots(groupKeysOf(visibleGraph)), [visibleGraph]);`. **Ninguna de las dos toca el efecto de sincronización ni la lista de refs.**
   y **un** efecto de sincronización (uno solo, no cuatro), que además fuerza el redibujo en modo estático:
```ts
  useEffect(() => {
    activeMatchIdRef.current   = activeMatchId;       // null hasta F2
    groupSlotsRef.current      = groupSlots;          // Map vacío hasta F5
    explorerEnabledRef.current = Boolean(explorerEnabled);
    if (stateRef.current && !stateRef.current.animated) drawRef.current();
  }, [activeMatchId, groupSlots, explorerEnabled]);
```
   **Regla de oro:** dentro de `draw()` se lee **`xxxRef.current`**, nunca la variable del render. Si una fase posterior necesita un dato nuevo en `draw()`, agrega un ref y una línea a este efecto — **jamás** una dep al efecto de layout (eso re-inicializaría el grafo entero en cada tecla).
4. Cuando `explorerEnabled` es falsy, `visibleGraph === graph` (misma referencia) ⇒ comportamiento **observacionalmente idéntico** al 111. ⚠️ (C17) No es "byte-idéntico" en sentido literal: F0.3 (`findIndex` → `Map`), F0.6 (nombres de token reales) y F5.3 (`groupOf` → `groupKeyOf`) corren en **ambos** modos, a propósito — son correcciones sin cambio de semántica, cubiertas por test. Lo que sí es idéntico es **lo que el operador ve y puede hacer**.
5. Render de la toolbar:
```tsx
{explorerEnabled ? (
  <DocGraphFilterBar
    options={filterOptions}
    filters={ui.filters}
    onToggleSource={(id) => dispatch({ type: "TOGGLE_SOURCE", sourceId: id })}
    /* ...el resto igual... */
    visibleNodes={visibleGraph.nodes.length}
    totalNodes={graph.nodes.length}
  />
) : null}
```
(la toolbar del 111 —búsqueda + leyenda + "Centrar"— se conserva tal cual; F2/F3 la reemplazan solo en modo explorador).

#### F1.4 — Cableado en `DocsPage.tsx`

```diff
   const stalenessEnabled = sourcesData?.staleness_enabled === true;  // Plan 114
+  const explorerEnabled = sourcesData?.graph_explorer_enabled === true;  // Plan 268
```
```diff
             <DocGraphView
               graph={graphData}
               onOpenNoteById={handleOpenNoteById}
               selectedNodeId={currentNodeId}
+              explorerEnabled={explorerEnabled}
+              projectName={projectName}
             />
```

#### Tests de F1 (TDD)

**`Stacky Agents/frontend/src/docs/graphFilters.test.ts`** (NUEVO):
- `it("sin filtros devuelve todos los nodos y aristas")`
- `it("grafo undefined devuelve EMPTY_GRAPH sin lanzar")`
- `it("grafo vacio devuelve nodes y edges vacios")`
- `it("filtrar por kind note descarta code y missing")`
- `it("filtrar por sourceId deja solo esa fuente")`
- `it("un nodo code con source_id vacio pasa el filtro de fuente")`
- `it("hideOrphans descarta los ids listados en graph.orphans")`
- `it("onlyStale deja solo nodos con has_stale true")`
- `it("onlyStale con has_stale ausente (flag 114 OFF) deja 0 nodos")`
- `it("minDegree 1 descarta el nodo sin aristas")`
- `it("una arista sobrevive solo si sus dos extremos sobreviven")`
- `it("filtrar por edgeKind wikilink descarta md y code_ref")`
- `it("un ciclo A->B->A conserva ambas aristas")`
- `it("orphans se recorta a los nodos vivos")`
- `it("no muta el grafo de entrada")`
- `it("availableFilterOptions cuenta nodos por fuente y por kind")`
- `it("availableFilterOptions con grafo vacio devuelve listas vacias y maxDegree 0")`
- `it("applyGraphFilters con 5000 nodos termina en menos de 2000 ms")` — genera 5000 nodos y 10000 aristas; mide con `Date.now()`; sirve de **guardia de complejidad** (una implementación O(n·m) con `find` anidados tarda decenas de segundos y cae; una O(n+m) tarda milisegundos). ⚠️ **(C10) Presupuesto de tiempo, no de performance.** Un rojo **solo por tiempo** en una máquina cargada **NO bloquea la fase**: se re-corre una vez y, si vuelve a dar rojo, se anota en `## 10` y se sigue. Lo que bloquea es un rojo de **corrección**.
- `it("availableFilterOptions toma el label de graph.sources y cae al id si no esta")` — (C11).
- `it("availableFilterOptions no lista fuentes con 0 nodos")` — (C11).
- `it("availableFilterOptions devuelve SIEMPRE los 3 kinds y los 3 edgeKinds, aun con count 0")` — (C11).

**Comandos:**
```
# desde "Stacky Agents/frontend"
npx vitest run src/docs/graphFilters.test.ts
npx vitest run src/__tests__/uiDebtRatchet.test.ts
npx vitest run src/__tests__/motionDebtRatchet.test.ts
npx vitest run src/docs/graphPalette.test.ts
npx tsc --noEmit
```
```
# desde la RAIZ del repo o desde donde sea (el prefijo :/ ancla el pathspec)
git diff --exit-code -- ":/Stacky Agents/frontend/package.json"
```

**Criterio de aceptación binario.** `graphFilters.test.ts` verde (**21 casos**: los 18 del v1 + los 3 de C11); `graphPalette.test.ts` verde (incluido el caso que valida `DocGraphExplorer.module.css`); `tsc --noEmit` con **0 errores**; los dos ratchets **en DELTA** (regla de F0, B6/v3); `git diff --exit-code -- ":/Stacky Agents/frontend/package.json"` con código 0; **y** el grep-gate de la invariante I1:
```
# desde "Stacky Agents/frontend"  --  el \b evita matchear visibleGraph
grep -nE "(^|[^a-zA-Z])graph\." src/components/docs/DocGraphView.tsx
```
[!] **(I5/v3) El gate del v2 estaba mal escrito.** Decía `grep -n "graph\."` y después "todos los hits deben ser `visibleGraph.…`" — imposible: `grep` es **case-sensitive** y `visibleGraph.` lleva **G mayúscula**, así que ese patrón **jamás** puede reportarlo. Comprobado: `echo 'visibleGraph.nodes' | grep -c "graph\."` -> **0**. El patrón de arriba busca a propósito **solo** el `graph.` pelado, que es exactamente el bug R1.

**Salida esperada al cerrar F1: EXACTAMENTE UN hit**, el denominador del contador (`totalNodes={graph.nodes.length}` en el JSX). **Cualquier otro hit es el bug R1** y se corrige antes de cerrar la fase. Para referencia, el baseline **antes** de F1 tiene **6 hits** (líneas 102, 106, 108, 247, 266, 267): los 6 tienen que migrar a `visibleGraph` salvo el del contador. `availableFilterOptions(graph, ...)` **no** aparece en esta salida (es `graph,` con coma, no `graph.`) y es una referencia legítima igual.

**Flag.** `STACKY_DOCS_GRAPH_EXPLORER_ENABLED` — **default ON**.

**Impacto por runtime.** Codex CLI: ninguno (no se invoca). Claude Code CLI: ninguno. GitHub Copilot Pro: ninguno. Es filtrado en memoria del navegador sobre un JSON ya recibido; ningún runtime participa. Fallback en los tres: si el backend responde `graph_explorer_enabled: false` (flag OFF o backend viejo), `explorerEnabled` queda `false` y la vista es la del 111.

**Trabajo del operador: ninguno** (la barra aparece sola con la flag ON, que es el default).

---

### F2 — Búsqueda navegable: ranking, contador `n de m`, Enter salta y encuadra

**Objetivo.** Que buscar deje de ser "atenuar el resto" y pase a ser "llevame al resultado".

**Valor.** Cierra el gap (e).

**Archivos.**
- CREAR `Stacky Agents/frontend/src/docs/graphSearch.ts`
- CREAR `Stacky Agents/frontend/src/docs/graphSearch.test.ts`
- EDITAR `Stacky Agents/frontend/src/components/docs/DocGraphView.tsx`
- EDITAR `Stacky Agents/frontend/src/components/docs/DocGraphExplorer.module.css`

#### F2.1 — `graphSearch.ts` (puro)

```ts
/**
 * graphSearch.ts — Plan 268 F2.
 * Búsqueda rankeada y DETERMINISTA sobre los nodos del grafo. Sin fetch, sin DOM.
 */
import type { DocGraphResponse, DocGraphNode } from "./docGraphModel";

export interface GraphSearchMatch {
  nodeId: string;
  /** 3 = el label empieza con la query; 2 = el label la contiene; 1 = solo el path la contiene */
  rank: 3 | 2 | 1;
  node: DocGraphNode;
}

/**
 * Devuelve las coincidencias ordenadas por rank DESC y, a igual rank, por
 * `path` ascendente (localeCompare) y luego por `id` ascendente — determinista.
 * Query vacía o solo espacios → []. Comparación case-insensitive sobre trim().
 * `limit` acota el resultado (default 200) para que la lista no explote.
 */
export function searchGraphNodes(
  graph: DocGraphResponse | undefined,
  query: string,
  limit: number = 200
): GraphSearchMatch[]

/** Set de ids de las coincidencias (para el resaltado del canvas; reemplaza a filterNodeIds). */
export function matchIdSet(matches: GraphSearchMatch[]): Set<string>

/** El nodeId de la coincidencia en `index`, o null si no hay coincidencias. index se toma módulo length. */
export function matchAt(matches: GraphSearchMatch[], index: number): string | null
```

Pseudocódigo:
```
q = query.trim().toLowerCase()
if (!q) return []
out = []
for (n of graph?.nodes ?? []) {
  lab = (n.label ?? "").toLowerCase()
  pth = (n.path ?? "").toLowerCase()
  rank = lab.startsWith(q) ? 3 : lab.includes(q) ? 2 : pth.includes(q) ? 1 : 0
  if (rank) out.push({ nodeId: n.id, rank, node: n })
}
out.sort((a,b) => b.rank - a.rank
                || a.node.path.localeCompare(b.node.path)
                || (a.nodeId < b.nodeId ? -1 : a.nodeId > b.nodeId ? 1 : 0))
return out.slice(0, limit)
```

**Casos borde:** query vacía → `[]`; query con solo espacios → `[]`; query sin resultados → `[]` (y la UI muestra `0 de 0`, deshabilita los botones ▲▼); `matchAt([], 5)` → `null`; `matchAt(m, 7)` con `m.length === 3` → `m[1]` (módulo); label vacío (`""`) → no matchea salvo por path; grafo `undefined` → `[]`; 5000 nodos → una sola pasada + un sort.

#### F2.2 — Cableado en `DocGraphView.tsx`

> [!] **(N1/v4) Aplicá PRIMERO la fila `F2.2` de la tabla de imports de §6.0.** Esta fase usa `searchGraphNodes`, `matchAt`, `matchIdSet` (de `graphSearch`) y `centerOn` (de `graphViewport`): ninguno está importado en `DocGraphView.tsx`. Sin esas dos líneas, el criterio `tsc --noEmit` **0 errores** de esta fase falla con un `TS2304` por símbolo.

1. **(C12) El `useState<string>` de la línea 97 SE CONSERVA** — el v1 decía "reemplazar" y después seguía usándolo, lo cual era una contradicción literal. La regla exacta es:
   - `explorerEnabled === true` → la **fuente de verdad es `ui.query`**. El `onChange` del input hace `dispatch({type:"SET_QUERY", query: e.target.value})` y **no** llama a `setQuery`.
   - `explorerEnabled` falsy → la fuente de verdad es el `useState` `query`, exactamente como en el 111.
   - El `value` del input es **`explorerEnabled ? ui.query : query`**. Una sola línea, sin ramas de render duplicadas.
2. Calcular:
```ts
const matches = useMemo(
  () => (explorerEnabled ? searchGraphNodes(visibleGraph, ui.query) : []),
  [explorerEnabled, visibleGraph, ui.query]
);
const activeMatchId = matchAt(matches, ui.matchIndex);
```
3. El efecto de la línea 111 pasa a:
```ts
useEffect(() => {
  filterRef.current = explorerEnabled ? matchIdSet(matches) : filterNodeIds(graph, query);
  if (stateRef.current && !stateRef.current.animated) drawRef.current();
}, [explorerEnabled, matches, query, graph]);
```
4. **Encuadre al resultado activo** — efecto nuevo:
```ts
useEffect(() => {
  if (!explorerEnabled || !activeMatchId) return;
  const st = stateRef.current;
  if (!st) return;
  const idx = st.nodes.findIndex((n) => n.id === activeMatchId);   // 1 vez por salto, NO por frame
  if (idx < 0) return;
  const n = st.nodes[idx];
  viewportRef.current = centerOn(viewportRef.current, n.x, n.y, canvasSizeRef.current.w, canvasSizeRef.current.h);
  drawRef.current();
}, [explorerEnabled, activeMatchId]);
```
   ⚠️ `canvasSizeRef` ya quedó declarado en F1.3-3 (I2). El efecto de layout lo actualiza en **dos** lugares: dentro de `sizeCanvas()` antes del `return` (líneas 135-145) y en el callback del `ResizeObserver` (líneas 459-475). **Sin ese ref el encuadre usa 0×0 y el nodo se va del canvas.**
   [!] **(B5/v3) Este efecto NO puede llamar a `setViewport` a secas.** `setViewport` vive **dentro** del efecto de layout (F3) y este es **otro** efecto: referenciarlo por nombre da `TS2304` y rompe el gate de F2. Se llama **`setViewportRef.current(...)`**, que ya quedó declarado en F1.3-3 y que F3 llena. La línea del bloque de arriba pasa a:
```ts
  setViewportRef.current(centerOn(viewportRef.current, n.x, n.y, canvasSizeRef.current.w, canvasSizeRef.current.h));
```
   y se **borra** el `drawRef.current()` siguiente: `setViewport` ya redibuja (si no, se dibuja dos veces por salto). En F2, antes de que F3 exista, `setViewportRef.current` es el no-op del `useRef` inicial — el encuadre no hace nada todavía, la fase compila y pasa sus tests puros, y **F3 lo enciende sin tocar F2**. Eso es la costura F2->F3, y es lo único que se difiere.
5. **Resaltado del activo:** en `draw()`, el nodo cuyo id es **`activeMatchIdRef.current`** (I2 — **NO** la variable `activeMatchId` del render: quedaría congelada en el primer resultado y el anillo no se movería nunca al apretar Enter, C2) se dibuja con el mismo anillo que el hovered (líneas 223-229) usando `palette.halo` en lugar de `palette.ring`, y su label recibe `priority: 950` en el array de candidatos (línea 258), entre `isSelected` (900) y `isHover` (1000).
6. **(C3) Coherencia del contador.** `matches` se calcula sobre `visibleGraph`, así que buscar **estando enfocado o con filtros** busca dentro de lo visible — es lo correcto y hay que decírselo al operador: si `ui.focusRootId` o los filtros no son `EMPTY_FILTERS`, el contador se muestra como `n de m (en lo visible)`. Así nadie interpreta que "no está" una nota que sí está pero filtrada.
7. **UI de la búsqueda** (dentro de `DocGraphFilterBar` o inmediatamente al lado, misma barra):
   - el `<input type="search">` existente,
   - `<span>{matches.length ? ui.matchIndex + 1 : 0} de {matches.length}</span>`,
   - `<button type="button" title="Coincidencia anterior" aria-label="Coincidencia anterior" disabled={!matches.length} onClick={() => dispatch({type:"PREV_MATCH", total: matches.length})}>` con el glifo `▲`,
   - idem `▼` para `NEXT_MATCH`,
   - `onKeyDown` del input: `Enter` → `NEXT_MATCH`; `Shift+Enter` → `PREV_MATCH`; `Escape` → `SET_QUERY` con `""`. **Siempre `ev.preventDefault()` en esos tres casos.**

#### Tests de F2 (TDD)

**`Stacky Agents/frontend/src/docs/graphSearch.test.ts`** (NUEVO):
- `it("query vacia devuelve lista vacia")`
- `it("query de solo espacios devuelve lista vacia")`
- `it("grafo undefined devuelve lista vacia")`
- `it("prefijo del label rankea 3 y va primero")`
- `it("substring del label rankea 2")`
- `it("coincidencia solo por path rankea 1 y va ultimo")`
- `it("empate de rank ordena por path ascendente")`
- `it("empate de rank y path ordena por id ascendente")`
- `it("la busqueda es case-insensitive")`
- `it("query sin resultados devuelve lista vacia")`
- `it("limit acota el numero de coincidencias")`
- `it("matchIdSet devuelve exactamente los ids de las coincidencias")`
- `it("matchAt con lista vacia devuelve null")`
- `it("matchAt aplica modulo al indice fuera de rango")`
- `it("matchAt con indice negativo devuelve null")`
- `it("con 5000 nodos la busqueda termina en menos de 2000 ms")` — (C10) guardia de complejidad, no de performance; un rojo solo por tiempo no bloquea la fase.

**Comandos:**
```
# desde "Stacky Agents/frontend"
npx vitest run src/docs/graphSearch.test.ts
npx vitest run src/docs/graphExplorerState.test.ts
npx tsc --noEmit
```

**Criterio de aceptación binario.** `graphSearch.test.ts` verde (16 casos), `graphExplorerState.test.ts` sigue verde, `tsc --noEmit` 0 errores.

**Flag.** `STACKY_DOCS_GRAPH_EXPLORER_ENABLED` — **default ON**.

**Impacto por runtime.** Codex CLI / Claude Code CLI / GitHub Copilot Pro: **ninguno en los tres**. La búsqueda es `String.includes` en el navegador sobre nodos ya cargados; no hay embeddings, no hay LLM, no hay endpoint nuevo. Fallback en los tres: flag OFF → el buscador del 111 (solo resalta).

**Trabajo del operador: ninguno.**

---

### F3 — Controles de zoom descubribles + ajustar a pantalla + atajos de teclado

**Objetivo.** Hacer visible y accesible el zoom que hoy solo existe en la rueda del mouse.

**Valor.** Cierra el gap (f). Es la mejora de UX más barata del plan.

**Archivos.**
- CREAR `Stacky Agents/frontend/src/components/docs/DocGraphZoomControls.tsx`
- EDITAR `Stacky Agents/frontend/src/components/docs/DocGraphView.tsx`
- EDITAR `Stacky Agents/frontend/src/components/docs/DocGraphExplorer.module.css`

**Contrato del componente:**
```ts
interface DocGraphZoomControlsProps {
  scale: number;                 // solo para el % que se muestra
  onZoomIn: () => void;
  onZoomOut: () => void;
  onFit: () => void;
  onReset: () => void;
  canZoomIn: boolean;            // scale < MAX_SCALE
  canZoomOut: boolean;           // scale > MIN_SCALE
}
```
Render: 4 `<button type="button">` con `title` y `aria-label` en español (`Acercar`, `Alejar`, `Ajustar a pantalla`, `Restablecer vista`), más un `<span>{Math.round(scale*100)}%</span>`. Cero `style={{}}`; posicionado con la clase `.zoomControls` (esquina inferior derecha del `.canvasBox`, `position: absolute`).

**(C7) ESCRITOR ÚNICO DEL VIEWPORT — obligatorio.** El v1 dejaba `viewportRef.current = …` esparcido por 6 lugares y el `%` de zoom en un `useState` que solo se actualizaba "al terminar una interacción de zoom". Eso miente en dos casos **reales y frecuentes**: (i) el `ResizeObserver` ya hace `viewportRef.current = IDENTITY` (línea 464) sin avisarle a nadie; (ii) a partir de F1 **cada cambio de filtro re-ejecuta el efecto de layout** (deps `[visibleGraph, …]`) y la línea 149 vuelve a poner `IDENTITY` — el grafo vuelve a 100% mientras el indicador sigue diciendo 195%. Se resuelve con **una sola función** dentro del efecto:
```ts
    // UNICO lugar del componente donde se escribe viewportRef.current.
    // Vive DENTRO del efecto de layout; los llamadores externos usan setViewportRef.
    function setViewport(next: Viewport) {
      if (next === viewportRef.current) return;   // zoomAt devuelve el MISMO objeto si clampeó
      viewportRef.current = next;
      setViewScale(next.scale);                   // mantiene el % sincronizado (React re-render barato)
      draw();
    }
```
y **todos** los escritores pasan por ahí: `onWheel` (línea 438-443), `onPointerMove` del pan (línea 382), `resetViewRef` (línea 306), el `ResizeObserver` (línea 464), el encuadre de F2, y los handlers de abajo.
```ts
// Los 4 refs YA están declarados en F1.3-3 (B5/v3). Acá solo se LLENAN, dentro
// del efecto de layout, junto a resetViewRef (línea 305):
setViewportRef.current = setViewport;                       // <- lo que usan F2 y F7
zoomInRef.current  = () => setViewport(zoomAtCenter(viewportRef.current, ZOOM_STEP, w, h));
zoomOutRef.current = () => setViewport(zoomAtCenter(viewportRef.current, 1 / ZOOM_STEP, w, h));
fitRef.current     = () => {
  const st = stateRef.current; if (!st || !st.nodes.length) return;
  setViewport(fitViewport(st.nodes.map(n => ({ x: n.x, y: n.y, r: n.r })), w, h, 40));
};
// resetViewRef (línea 305) se conserva, pero pasa a llamar setViewport(IDENTITY).
```
[!] **(B5/v3) `setViewportRef.current = setViewport;` es la línea que cierra la costura F2->F3 y F7->F3.** Sin ella, el encuadre al resultado de búsqueda (F2.2-4) y el click en el minimapa (F7.2-4) quedan como no-ops silenciosos: no fallan, simplemente **no hacen nada** — y no hay ningún test de componente en este repo que lo note. Se verifica en F8 pasos 8 y 16.
⚠️ `setViewScale` **nunca** se llama desde `tick()`: eso re-renderizaría React 60 veces por segundo (regresión de performance, prohibida). `tick()` llama `draw()` a secas, que **no** toca estado de React. `setViewport` solo se invoca en respuesta a un gesto o a un re-init — como mucho unas pocas veces por segundo.

**(C7) Re-encuadre tras cada re-init en modo explorador.** Al final del efecto de layout, en modo explorador y **solo** si `visibleGraph.nodes.length > 0`, se llama una vez a `fitRef.current()` (dentro de un `requestAnimationFrame` para que `staticLayout`/el primer `stepLayout` ya hayan corrido). Así, cuando el operador toca un filtro, el subgrafo aparece **encuadrado** en vez de aparecer a escala 1 con la mitad fuera de pantalla. Con la flag OFF esto **no** se hace (comportamiento del 111). Esto no es autonomía (G4): es la consecuencia visual directa del click del operador.

**Atajos de teclado.** Se registran sobre el `.canvasBox` con `tabIndex={0}` y `onKeyDown` (**no** sobre `window`: no deben dispararse mientras el operador escribe en otro lado de la app):

| Tecla | Acción | Guardia |
|---|---|---|
| `+` / `=` | `onZoomIn` | — |
| `-` | `onZoomOut` | — |
| `0` | `onReset` | — |
| `f` | `onFit` | — |
| `Escape` | `CLEAR_FOCUS` + `SET_PEEK(null)` | — |
| flechas ← ↑ → ↓ | `panBy` de 40 px en esa dirección | `ev.preventDefault()` para no scrollear la página |

⚠️ **Guardia obligatoria en el handler** (patrón conocido de la casa: los atajos sin modificador NO deben dispararse con foco en un campo editable):
```ts
const t = ev.target as HTMLElement | null;
const tag = (t?.tagName || "").toLowerCase();
if (tag === "input" || tag === "textarea" || tag === "select" || t?.isContentEditable) return;
```

⚠️ **(C9) SIN ESTO LOS ATAJOS ESTÁN MUERTOS.** `tabIndex={0}` hace al `.canvasBox` **enfocable**, pero el click del operador cae en el `<canvas>` hijo y `pointerdown` **no** enfoca a un ancestro con `tabIndex`. Resultado: el operador hace click en el grafo, aprieta `f` y **no pasa nada** — el `keydown` se fue al `<body>`. Dos líneas obligatorias:
1. En `onPointerDown` (línea 357), **primera** instrucción: `boxRef.current?.focus({ preventScroll: true });`
2. En `DocGraphExplorer.module.css`, `.canvasBox:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }` — así el operador **ve** que el grafo tiene el foco del teclado (y es requisito de accesibilidad: un elemento enfocable sin indicador visible es una regresión de a11y).
3. El `.hint` en modo explorador agrega, al final: `· Click en el grafo para usar el teclado`.

**Descubribilidad.** El `.hint` existente (`DocGraphView.tsx:537-539`) pasa, en modo explorador, a:
`Rueda o + / −: zoom · F: ajustar · 0: restablecer · Arrastrá el fondo: mover · Click: enfocar · Doble click: abrir`

**Tests de F3.** La lógica pura ya está cubierta por `graphViewport.test.ts` (F0: `fitViewport`, `centerOn`, `zoomAtCenter`, `ZOOM_STEP`). **No se agregan tests de componente** (G2: no hay RTL/jsdom). Se agrega **un** caso puro más a `graphViewport.test.ts`:
- `it("fitViewport sobre las posiciones de un LayoutState deja todos los nodos visibles")` — arma un `LayoutState` con `initLayout` de un grafo de 50 nodos, corre 100 `stepLayout`, y verifica el encuadre.

**Comandos:**
```
# desde "Stacky Agents/frontend"
npx vitest run src/docs/graphViewport.test.ts
npx vitest run src/__tests__/uiDebtRatchet.test.ts
npx tsc --noEmit
```

**Criterio de aceptación binario.** `graphViewport.test.ts` verde, **los dos ratchets en DELTA** (regla B6/v3 de F0: ningún archivo del plan en la lista de `REGRESION` y el conteo no sube respecto de F0.0; **prohibido** regenerar baseline), `tsc --noEmit` 0 errores, y verificación visual F8 pasos 4-6.

**Flag.** `STACKY_DOCS_GRAPH_EXPLORER_ENABLED` — **default ON**.

**Impacto por runtime.** Ninguno en los tres (Codex / Claude Code / Copilot): son botones y teclas del navegador. Fallback en los tres: flag OFF → solo rueda + doble click, como en el 111.

**Trabajo del operador: ninguno.**

---

### F4 — Foco por vecindario: aislar un nodo a profundidad 1–3, con historial y migas

**Objetivo.** Poder decir "mostrame solo esta nota y lo que la rodea", movete de vecino en vecino, y volver.

**Valor.** Cierra el gap (c). Es la funcionalidad que convierte el mapa en una herramienta de navegación.

**Archivos.**
- CREAR `Stacky Agents/frontend/src/docs/graphNeighborhood.ts`
- CREAR `Stacky Agents/frontend/src/docs/graphNeighborhood.test.ts`
- EDITAR `Stacky Agents/frontend/src/components/docs/DocGraphView.tsx`
- EDITAR `Stacky Agents/frontend/src/components/docs/DocGraphExplorer.module.css`

#### F4.1 — `graphNeighborhood.ts` (puro)

```ts
/**
 * graphNeighborhood.ts — Plan 268 F4.
 * Vecindario NO DIRIGIDO a profundidad N (BFS) sobre un DocGraphResponse.
 */
import type { DocGraphResponse, DocGraphNode } from "./docGraphModel";

/** id → Set de ids adyacentes (arista en cualquier dirección). Self-loops ignorados. */
export function buildAdjacency(graph: DocGraphResponse | undefined): Map<string, Set<string>>

/**
 * BFS desde rootId hasta `depth` saltos, inclusive.
 *  - rootId inexistente en el grafo → Set VACÍO (no {rootId}).
 *  - depth <= 0 → {rootId} si existe.
 *  - depth >= diámetro → toda la componente conexa.
 * Nunca entra en bucle infinito con ciclos (usa `seen`).
 */
export function neighborhoodOf(
  graph: DocGraphResponse | undefined,
  rootId: string | null,
  depth: number
): Set<string>

/** Sub-grafo con SOLO los nodos del vecindario y las aristas entre ellos. */
export function focusSubgraph(
  graph: DocGraphResponse,
  rootId: string | null,
  depth: number
): DocGraphResponse

/**
 * Vecinos DIRECTOS del root, para la lista lateral "Relaciones".
 * Orden: primero los que apuntan al root (entrantes, "lo referencian"),
 * después los que el root apunta (salientes, "referencia a"); dentro de cada
 * bloque por path ascendente. Cada entrada trae la dirección y el kind de arista.
 */
export interface NeighborEntry {
  node: DocGraphNode;
  direction: "in" | "out" | "both";
  edgeKinds: Array<"md" | "wikilink" | "code_ref">;
}
export function rankedNeighbors(graph: DocGraphResponse, rootId: string): NeighborEntry[]

/**
 * (C3) Resuelve el id de foco CONTRA EL GRAFO YA COMPUESTO (filtrado + agrupado).
 * Existe porque el foco lo eligió el operador sobre un grafo que después puede
 * cambiar de forma: un filtro puede descartar el nodo enfocado y un colapso de
 * grupo puede reemplazarlo por su super-nodo. Sin esto, focusSubgraph recibe un
 * root inexistente y —por su propia spec— devuelve un grafo VACÍO: pantalla en
 * blanco sin explicación (viola G13).
 *
 * Reglas, en este orden:
 *  1. focusRootId null → null.
 *  2. focusRootId presente en composed.nodes → ese mismo id.
 *  3. Si el nodo original (buscado en `original.nodes`) existe y su grupo está
 *     colapsado, devolver GROUP_NODE_PREFIX + groupKeyOf(kind, source_id) si ese
 *     super-nodo está en composed.nodes.
 *  4. En cualquier otro caso → null (⇒ se muestra el grafo compuesto ENTERO,
 *     nunca vacío) y el caller avisa al operador (ver F4.2 punto 6).
 */
export function resolveFocusId(
  composed: DocGraphResponse,
  original: DocGraphResponse,
  focusRootId: string | null
): string | null
```

Pseudocódigo de `neighborhoodOf`:
```
if (!graph || !rootId) return new Set()
const ids = new Set(graph.nodes.map(n => n.id))
if (!ids.has(rootId)) return new Set()
const adj = buildAdjacency(graph)
const seen = new Set([rootId])
let frontier = [rootId]
for (let d = 0; d < Math.max(0, depth); d++) {
  const next = []
  for (const id of frontier)
    for (const nb of (adj.get(id) ?? []))
      if (!seen.has(nb)) { seen.add(nb); next.push(nb) }
  if (!next.length) break
  frontier = next
}
return seen
```

**Casos borde:** grafo vacío → `Set` vacío; `rootId === null` → vacío; root sin aristas → `{root}`; ciclo A→B→C→A con `depth=5` → los 3, sin colgarse; self-loop A→A → `{A}` (ignorado en la adyacencia); `depth = 0` → `{root}`; `depth` negativo → `{root}`; grafo con 5000 nodos y `depth=3` → BFS acotado, una sola pasada.

#### F4.2 — Cableado

1. **(C4) TABLA ÚNICA DE GESTOS — esta tabla manda sobre cualquier otra frase del plan.** El v1 se contradecía: F4 decía "click = enfocar (siempre)" y F5 decía "click sobre el super-nodo = des-colapsar". Regla desempatada, a implementar **literalmente** en `onPointerUp` (línea 406-423) y `onDblClick` (línea 446-448):

   | `explorerEnabled` | Gesto | Sobre qué nodo | Acción exacta |
   |---|---|---|---|
   | **false** | click | cualquiera | comportamiento del 111: `if (kindById.get(id) === "note") onOpenNoteById(id)` |
   | **false** | doble click | cualquiera | `resetViewRef.current()` (111) |
   | **true** | click | `isGroupNodeId(id)` (super-nodo, F5) | `dispatch({type:"TOGGLE_GROUP_COLLAPSED", groupKey: groupKeyFromNodeId(id)!})` — **des-colapsa**. No enfoca, no abre nada. |
   | **true** | click | nodo normal (`note` / `code` / `missing`) | `dispatch({type:"FOCUS_NODE", nodeId: id})` — enfoca y abre el peek |
   | **true** | doble click | nodo `note` | `onOpenNoteById(id)` — abre en el Lector |
   | **true** | doble click | `code` / `missing` / super-nodo | **nada** (no hay documento que abrir) |
   | **true** | doble click | el vacío (ningún nodo bajo el cursor) | `resetViewRef.current()` — el reset del 111 sigue existiendo sobre el fondo |

   ⚠️ `onDblClick` hoy no sabe qué nodo hay debajo: hay que darle las coordenadas y llamar a `nearestNode(x, y)` (línea 316), igual que `onPointerUp`. Firma: `function onDblClick(ev: MouseEvent)` con `const { x, y } = toLocal(ev as any)`.
   ⚠️ El reset de vista **sigue disponible** en modo explorador por el botón "Restablecer vista" de F3 y por la tecla `0`, además del doble click al vacío.
2. **Componer con los filtros.** El grafo que llega al layout es:
```ts
const { visibleGraph, effectiveFocusId } = useMemo(() => {
  if (!explorerEnabled) return { visibleGraph: graph, effectiveFocusId: null as string | null };
  const filtered = applyGraphFilters(graph, ui.filters);
  const grouped  = collapseGroups(filtered, ui.collapsedGroups);        // F5
  // (C3) el foco se RESUELVE contra el grafo ya compuesto: si el nodo enfocado
  // desapareció (filtro) o fue absorbido por un super-nodo (colapso), esto
  // devuelve el super-nodo o null — NUNCA deja el canvas vacío (G13).
  const focusId  = resolveFocusId(grouped, graph, ui.focusRootId);
  return {
    visibleGraph: focusId ? focusSubgraph(grouped, focusId, ui.focusDepth) : grouped,
    effectiveFocusId: focusId,
  };
}, [explorerEnabled, graph, ui.filters, ui.collapsedGroups, ui.focusRootId, ui.focusDepth]);
```
   **Orden fijo y obligatorio: filtros → agrupación → RESOLUCIÓN DEL FOCO → foco.** (Filtrar después de enfocar daría vecindarios rotos; agrupar después de enfocar generaría super-nodos parciales; y **sin el paso de resolución, colapsar el grupo del nodo enfocado o filtrarlo deja la pantalla en blanco** — C3.)
   ⚠️ A partir de acá, **todo lo que se muestre del foco usa `effectiveFocusId`, no `ui.focusRootId`**: las migas, el título del peek, `rankedNeighbors`, y el `aria-pressed` de los botones de profundidad. `ui.focusRootId` sigue siendo lo que el operador pidió; `effectiveFocusId` es lo que se puede mostrar.
   ⚠️ Lo mismo para el peek y para la búsqueda: `peekNodeId` y `activeMatchId` se resuelven **contra `visibleGraph`**; si el id ya no está, el peek se cierra solo (`SET_PEEK` con `null`) y el contador de búsqueda se recalcula (ya lo hace, porque `matches` depende de `visibleGraph`).
3. **Migas + control de profundidad** (barra sobre el canvas, solo si `ui.focusRootId`):
   - `<button>← Volver</button>` → `FOCUS_BACK`, `disabled` si `focusHistory.length === 0 && !focusRootId`.
   - `<span>Foco: {labelDelRoot}</span>`
   - 3 `<button aria-pressed>` con `1 / 2 / 3` → `SET_FOCUS_DEPTH`.
   - `<button>Ver todo</button>` → `CLEAR_FOCUS`.
   - `<span>{visibleGraph.nodes.length} de {graph.nodes.length} nodos</span>`
4. **Encuadre automático al enfocar.** Un `useEffect` sobre `[ui.focusRootId, ui.focusDepth]` que llama `fitRef.current()` tras un `requestAnimationFrame` (para que el layout ya tenga posiciones). Esto **no** es autonomía: es la consecuencia visual directa de un click del operador (G4).
5. **Panel "Relaciones"** (lista lateral, dentro del peek de F6 o encima si F6 aún no está): `rankedNeighbors(visibleGraph, effectiveFocusId)` renderizado como `<ul>` de `<button>`; click en un vecino → `FOCUS_NODE` de ese vecino. Así se "camina" el grafo.
6. **(C3) Aviso cuando el foco pedido no se puede mostrar.** Si `ui.focusRootId !== null` y `effectiveFocusId === null`, en la barra de migas se muestra, en lugar de `Foco: <nota>`, el texto llano: **`El nodo enfocado no está en la vista actual (lo ocultó un filtro o un grupo colapsado).`** más el botón `Ver todo` (`CLEAR_FOCUS`) ya existente. **Nunca** se limpia el foco solo: el operador decide (G4). Y si `effectiveFocusId !== ui.focusRootId` (se remapeó al super-nodo), las migas dicen `Foco: <etiqueta del grupo> (grupo colapsado)`.

#### Tests de F4 (TDD)

**`Stacky Agents/frontend/src/docs/graphNeighborhood.test.ts`** (NUEVO):
- `it("buildAdjacency es no dirigida: A->B pone B en A y A en B")`
- `it("buildAdjacency ignora self-loops")`
- `it("buildAdjacency con grafo vacio devuelve Map vacio")`
- `it("neighborhoodOf con rootId inexistente devuelve Set vacio")`
- `it("neighborhoodOf con rootId null devuelve Set vacio")`
- `it("neighborhoodOf depth 0 devuelve solo el root")`
- `it("neighborhoodOf depth negativo devuelve solo el root")`
- `it("neighborhoodOf depth 1 devuelve root mas vecinos directos")`
- `it("neighborhoodOf depth 2 alcanza a los vecinos de los vecinos")`
- `it("neighborhoodOf en un nodo sin aristas devuelve solo el root")`
- `it("neighborhoodOf con un ciclo A-B-C-A no se cuelga")`
- `it("neighborhoodOf con depth mayor al diametro devuelve la componente conexa entera")`
- `it("neighborhoodOf no cruza a otra componente desconectada")`
- `it("focusSubgraph conserva solo las aristas internas al vecindario")`
- `it("focusSubgraph con root inexistente devuelve un grafo vacio")`
- `it("rankedNeighbors lista primero los entrantes y despues los salientes")`
- `it("rankedNeighbors marca direction both cuando hay arista en los dos sentidos")`
- `it("rankedNeighbors agrupa los edgeKinds del mismo par de nodos")`
- `it("neighborhoodOf sobre 5000 nodos con depth 3 termina en menos de 2000 ms")` — (C10) guardia de complejidad; un rojo solo por tiempo no bloquea la fase.
- **(C3) Los 5 casos de `resolveFocusId` — ninguno opcional:**
- `it("resolveFocusId con focusRootId null devuelve null")`
- `it("resolveFocusId devuelve el mismo id si el nodo sigue en el grafo compuesto")`
- `it("resolveFocusId remapea al super-nodo cuando el grupo del nodo enfocado esta colapsado")`
- `it("resolveFocusId devuelve null si un filtro descarto el nodo enfocado")`
- `it("resolveFocusId nunca devuelve un id ausente del grafo compuesto")` — propiedad: para 20 combinaciones de filtros/colapsos generadas, el resultado o es null o está en `composed.nodes`.
- **(G13) El caso que prueba que el canvas nunca queda vacío:**
- `it("componer filtros + colapso + foco sobre el grupo del nodo enfocado NO devuelve un grafo vacio")` — arma un grafo de 12 nodos en 2 fuentes, enfoca uno, colapsa su fuente, compone en el orden de F4.2-2 y verifica `visibleGraph.nodes.length > 0`.

**Comandos:**
```
# desde "Stacky Agents/frontend"
npx vitest run src/docs/graphNeighborhood.test.ts
npx vitest run src/docs/graphFilters.test.ts
npx vitest run src/docs/graphGrouping.test.ts
npx tsc --noEmit
```
⚠️ El último comando **solo aplica cuando F5 ya existe**. Si F4 se implementa antes que F5 (que es el orden del plan), los 6 casos nuevos que dependen de `collapseGroups` se escriben en F4 y quedan **skippeados** (`it.skip`) con el comentario `// se activa en F5`; F5 los des-skippea. Esto es explícito para que un modelo menor no invente un `collapseGroups` provisorio.

**Criterio de aceptación binario.** `graphNeighborhood.test.ts` verde (**25 casos**: los 19 del v1 + 5 de `resolveFocusId` + 1 de G13; de esos, los que dependen de `collapseGroups` pueden estar `it.skip` hasta F5), `graphFilters.test.ts` sigue verde (no hubo regresión al componer), `tsc --noEmit` 0 errores.

**Flag.** `STACKY_DOCS_GRAPH_EXPLORER_ENABLED` — **default ON**.

**Impacto por runtime.** Ninguno en los tres. BFS en memoria del navegador. Fallback en los tres: flag OFF → sin foco; click abre la nota como en el 111.

**Trabajo del operador: ninguno.**

---

### F5 — Agrupación: color por grupo, leyenda accionable y colapso a super-nodo

**Objetivo.** Que se **vea** a qué fuente pertenece cada nota y que se pueda colapsar una fuente entera en un solo nodo.

**Valor.** Cierra el gap (b) y buena parte de (g). Hoy **todas** las notas se pintan igual (`DocGraphView.tsx:71-75`).

**Archivos.**
- CREAR `Stacky Agents/frontend/src/docs/graphGrouping.ts`
- CREAR `Stacky Agents/frontend/src/docs/graphGrouping.test.ts`
- EDITAR `Stacky Agents/frontend/src/docs/forceLayout.ts`
- EDITAR `Stacky Agents/frontend/src/docs/forceLayout.test.ts`
- EDITAR `Stacky Agents/frontend/src/components/docs/DocGraphView.tsx`

#### F5.1 — `graphGrouping.ts` (puro)

```ts
/**
 * graphGrouping.ts — Plan 268 F5.
 * Agrupación canónica de nodos del grafo documental + colapso a super-nodos.
 * ESTE MÓDULO es la ÚNICA definición de la clave de grupo (forceLayout la importa).
 */
import type { DocGraphResponse, DocGraphNode, DocGraphEdge } from "./docGraphModel";

export const GROUP_NODE_PREFIX = "group:";

/** Notas → "note:<source_id>"; code y missing → su propio kind. IDÉNTICA al groupOf
 *  privado que hoy vive en forceLayout.ts:62-64 (se mueve acá sin cambiar semántica). */
export function groupKeyOf(kind: string, sourceId: string): string {
  return kind === "note" ? "note:" + (sourceId || "") : kind;
}

/** Etiqueta legible: "note:stacky" → "Notas · stacky"; "code" → "Código"; "missing" → "Faltantes".
 *  "note:" (source vacío) → "Notas · (sin fuente)". */
export function groupLabelOf(groupKey: string): string

/** Todas las claves de grupo presentes, ordenadas: primero las note:* por source_id
 *  asc, después "code", después "missing". Determinista. */
export function groupKeysOf(graph: DocGraphResponse | undefined): string[]

/** Slot de color 0..N-1 por grupo, asignado por la posición en groupKeysOf.
 *  El consumidor mapea slot → CSS custom property (ver tabla en F5.2). */
export function assignGroupColorSlots(groupKeys: string[]): Map<string, number>

/**
 * Colapsa cada grupo de `collapsedKeys` en UN super-nodo:
 *   id    = GROUP_NODE_PREFIX + groupKey
 *   kind  = "note" si el grupo empieza con "note:", si no el propio kind
 *   label = groupLabelOf(groupKey) + " (" + miembros + ")"
 *   path  = ""            (no abre nada: el click sobre él lo DES-colapsa)
 *   source_id = el source del grupo (o "")
 *   in_degree / out_degree = suma de los miembros
 *   exists = true, has_frontmatter = false
 * Las aristas se remapean al super-nodo, se DEDUPLICAN por (source,target,kind)
 * y se DESCARTAN las que quedan como self-loop del super-nodo.
 * collapsedKeys vacío → devuelve el MISMO objeto (identidad referencial, sin copiar).
 */
export function collapseGroups(
  graph: DocGraphResponse,
  collapsedKeys: string[]
): DocGraphResponse

/** true si el id es un super-nodo de grupo. */
export function isGroupNodeId(id: string): boolean

/** groupKey a partir del id del super-nodo, o null. */
export function groupKeyFromNodeId(id: string): string | null
```

#### F5.2 — Color por grupo (theme-aware, G6)

⚠️ **(C1) REESCRITO. El v1 inventaba tokens que no existen** (`--color-info`, `--color-purple`, `--color-teal`, `--color-pink`) y se apoyaba en que "el fallback string se usa igual". Eso funcionaba **solo** en el canvas, no en la leyenda (que por G8 va sin fallback), dejando **leyenda y grafo con colores distintos**. Y citaba una ruta inexistente (`frontend/src/styles/theme.css` → es `frontend/src/theme.css`).

La paleta —incluido el array `groups: string[]` del `interface Palette`— **ya quedó definida y cableada en F0.6**, con los **tokens reales de `theme.css`** (`GROUP_SLOT_TOKENS`: `--accent`, `--accent-hot`, `--warn`, `--agent-business`, `--agent-functional`, `--agent-custom`; los 6 existen en el bloque oscuro **y** en el claro). **F5 no toca `readPalette`**: solo consume `pal.groups`.

`colorForGroup` pasa a:
```ts
function colorForGroup(group: string, pal: Palette, slots: Map<string, number>): string {
  if (group === "code") return pal.code;
  if (group === "missing") return pal.missing;
  const slot = slots.get(group);
  return slot === undefined ? pal.note : pal.groups[slot % pal.groups.length];
}
```
⚠️ **(C2/I2)** El `slots` que `draw()` usa es **`groupSlotsRef.current`**, no la variable del render: `assignGroupColorSlots` produce un `Map` nuevo cada vez que cambia `visibleGraph`, y el efecto de layout no se re-ejecuta por eso solo. El ref ya está declarado en F1.3-3 y lo llena el efecto de sincronización.

#### F5.3 — Una sola definición de `groupOf`

En `Stacky Agents/frontend/src/docs/forceLayout.ts`:
```diff
+import { groupKeyOf } from "./graphGrouping";
@@
-/** Grupo de color/columna: notas por fuente, código y faltantes por su kind. */
-function groupOf(kind: string, sourceId: string): string {
-  return kind === "note" ? "note:" + (sourceId || "") : kind;
-}
@@
-      group: groupOf(n.kind, n.source_id),
+      group: groupKeyOf(n.kind, n.source_id),
```
⚠️ **Cuidado con el import circular:** `graphGrouping.ts` importa **solo tipos** de `docGraphModel.ts` (`import type`), y `forceLayout.ts` importa la función de `graphGrouping.ts`. `graphGrouping.ts` **NO debe importar** `forceLayout.ts`. Verificar con `npx tsc --noEmit`.

#### F5.4 — Leyenda accionable

La leyenda actual (`DocGraphView.tsx:505-518`, con 3 `style={{}}` que **ya están en el baseline del ratchet**) se **conserva tal cual** cuando `explorerEnabled` es falsy (F0.6 solo le corrige el **nombre** del token dejando el fallback: el conteo de `style={{` no cambia y `uiDebtRatchet` sigue verde).

En modo explorador se renderiza una leyenda nueva dentro de `DocGraphFilterBar`, con **cero `style={{}}`**: cada swatch usa una clase `.swatchSlot0` … `.swatchSlot5` definida en `DocGraphExplorer.module.css`. **(C1) Los `background` de esas 6 clases tienen que ser EXACTAMENTE los mismos tokens que `GROUP_SLOT_TOKENS` (F0.6), en el mismo orden**, o la leyenda le miente al operador:
```css
.swatchSlot0 { background: var(--accent); }
.swatchSlot1 { background: var(--accent-hot); }
.swatchSlot2 { background: var(--warn); }
.swatchSlot3 { background: var(--agent-business); }
.swatchSlot4 { background: var(--agent-functional); }
.swatchSlot5 { background: var(--agent-custom); }
```
(**sin fallback hex**, G8 — y ahora eso es seguro porque los 6 tokens **existen de verdad**; el caso `it("DocGraphView.module.css no usa ningun token inexistente")` de F0.6 cubre también este archivo). Click en un ítem de la leyenda → `TOGGLE_GROUP_COLLAPSED`, con `aria-pressed` reflejando si está colapsado.

⚠️ **(C4) El gesto sobre el super-nodo dibujado en el canvas está definido en la TABLA ÚNICA DE GESTOS de F4.2-1** y esa tabla manda: click sobre un `isGroupNodeId(id)` ⇒ `TOGGLE_GROUP_COLLAPSED` (des-colapsa), **no** `FOCUS_NODE`. La leyenda y el super-nodo hacen exactamente lo mismo; son dos accesos al mismo comando.

#### Tests de F5 (TDD)

**`Stacky Agents/frontend/src/docs/graphGrouping.test.ts`** (NUEVO):
- `it("groupKeyOf de una nota devuelve note: mas su source_id")`
- `it("groupKeyOf de una nota sin source devuelve note:")`
- `it("groupKeyOf de code y missing devuelve el kind pelado")`
- `it("groupLabelOf traduce note:stacky a una etiqueta legible")`
- `it("groupLabelOf de note: sin fuente dice sin fuente")`
- `it("groupKeysOf ordena note:* por source y deja code y missing al final")`
- `it("groupKeysOf con grafo vacio devuelve lista vacia")`
- `it("assignGroupColorSlots asigna slots consecutivos y estables")`
- `it("collapseGroups con lista vacia devuelve el MISMO objeto")`
- `it("collapseGroups reemplaza los miembros por un unico super-nodo")`
- `it("el super-nodo suma los grados de sus miembros")`
- `it("collapseGroups remapea las aristas al super-nodo")`
- `it("collapseGroups deduplica aristas iguales tras el remapeo")`
- `it("collapseGroups descarta las aristas internas al grupo colapsado")`
- `it("collapseGroups de DOS grupos deja una arista entre los dos super-nodos")`
- `it("collapseGroups de un grupo inexistente no cambia nada")`
- `it("isGroupNodeId y groupKeyFromNodeId son inversas")`
- `it("collapseGroups no muta el grafo de entrada")`

**`Stacky Agents/frontend/src/docs/forceLayout.test.ts`** (EDITAR):
- `it("initLayout asigna el group con la misma clave que groupKeyOf")` — guardia contra que la refactorización cambie la semántica.

**Comandos:**
```
# desde "Stacky Agents/frontend"
npx vitest run src/docs/graphGrouping.test.ts
npx vitest run src/docs/forceLayout.test.ts
npx vitest run src/__tests__/uiDebtRatchet.test.ts
npx tsc --noEmit
```

**Criterio de aceptación binario.** `graphGrouping.test.ts` verde (18 casos), `forceLayout.test.ts` verde **con sus 7 casos previos intactos** (baseline medido: 7 passed — la refactorización no cambió nada), **los dos ratchets en DELTA** (regla B6/v3), `tsc --noEmit` 0 errores (prueba que no hay ciclo de imports).

**Flag.** `STACKY_DOCS_GRAPH_EXPLORER_ENABLED` — **default ON**. (El movimiento de `groupOf` → `groupKeyOf` NO está gateado: es un refactor de identidad semántica cubierto por test.)

**Impacto por runtime.** Ninguno en los tres. Es agrupación en memoria + colores del tema. Fallback en los tres: flag OFF → un solo color de nota y sin colapso, como en el 111.

**Trabajo del operador: ninguno.**

---

### F6 — Peek: ver el principio del documento sin salir del grafo

**Objetivo.** Acceso rápido al contenido asociado a cada elemento, que es literalmente lo último que pidió el operador.

**Valor.** Cierra el gap (d).

**Archivos.**
- CREAR `Stacky Agents/frontend/src/docs/graphPreview.ts`
- CREAR `Stacky Agents/frontend/src/docs/graphPreview.test.ts`
- CREAR `Stacky Agents/frontend/src/components/docs/DocGraphPeek.tsx`
- EDITAR `Stacky Agents/frontend/src/components/docs/DocGraphView.tsx`
- EDITAR `Stacky Agents/frontend/src/components/docs/DocGraphExplorer.module.css`

#### F6.1 — `graphPreview.ts` (puro)

```ts
/**
 * graphPreview.ts — Plan 268 F6.
 * Extracto legible del principio de un markdown, para el peek del grafo.
 * PURO: recibe el texto ya bajado, no hace fetch.
 */

/**
 * Devuelve hasta `maxChars` caracteres de texto plano:
 *  1. quita el frontmatter YAML inicial (bloque entre --- y --- al principio)
 *  2. quita los fences de código completos (```...```)
 *  3. quita marcas markdown de encabezado (#), énfasis (*_`), citas (>) y viñetas (-,*,+)
 *  4. convierte [texto](url) → texto y [[nombre|alias]] → alias (o nombre)
 *  5. colapsa runs de espacios/saltos a un solo espacio y hace trim
 *  6. corta en el último espacio antes de maxChars y agrega "…" si cortó
 * Entrada vacía/undefined → "". Texto más corto que maxChars → sin "…".
 */
export function previewExcerpt(markdown: string | undefined, maxChars: number = 600): string

/** Primer encabezado H1 del markdown (sin el #), o null. Ignora el frontmatter. */
export function previewTitle(markdown: string | undefined): string | null
```

**Casos borde:** `undefined` → `""`; `""` → `""`; solo frontmatter → `""`; documento de 1 palabra → esa palabra sin `…`; documento de 100 KB → corta en 600 y agrega `…` (una sola pasada, sin regex catastrófica: usar `String.indexOf`/`slice` para el frontmatter y los fences, **no** un regex greedy multilinea); frontmatter sin cierre (`---` inicial y nunca más) → **no** borrar todo el documento, devolver el texto tal cual; wikilink sin alias (`[[nota]]`) → `nota`; link markdown con paréntesis anidados → dejar el texto del corchete (aceptable, documentado).

#### F6.2 — `DocGraphPeek.tsx` (cascarón; hace el fetch, no la lógica)

```ts
interface DocGraphPeekProps {
  node: DocGraphNode | null;      // el nodo seleccionado (ui.peekNodeId resuelto)
  projectName?: string;
  neighbors: NeighborEntry[];     // de rankedNeighbors (F4)
  onOpenNote: (nodeId: string) => void;   // "Abrir en el Lector" → onOpenNoteById
  onFocusNode: (nodeId: string) => void;  // click en un vecino
  onClose: () => void;
}
```
Comportamiento:
- Si `node === null` → renderiza `null` (el panel no ocupa lugar).
- Si `node.kind !== "note"` o `!node.path` → muestra solo la ficha (label, kind, grados, fuente) y la lista de vecinos, **sin** fetch (los nodos `code`/`missing`/super-nodo no tienen documento).
- Si es nota → `useQuery` con **exactamente esta clave**, para reusar la cache del Lector:
```ts
useQuery({
  queryKey: ["docs-content", projectName ?? "active", node.source_id, node.path],
  queryFn: () => Docs.getContent(node.path, { project: projectName, sourceId: node.source_id }),
  enabled: node.kind === "note" && Boolean(node.path),
  staleTime: 5 * 60 * 1000,
  retry: 1,
})
```
  ⚠️ La clave debe coincidir **campo por campo** con la de `DocsPage.tsx:146` (`["docs-content", projectName ?? "active", selectedContentSourceId, selectedNode?.path]`).
  ⚠️ **(C8) Pero el hit de cache NO es un criterio binario, y el v1 se equivocaba al prometerlo.** En el Lector el 3.º campo es `selectedContentSourceId = selectedNode?.source_id ?? selectedSourceId` (`DocsPage.tsx:140`) y **`DocNode.source_id` es opcional** (`endpoints.ts:3323`), mientras que `DocGraphNode.source_id` es obligatorio (`docGraphModel.ts:13`). Si el índice de documentos no trae `source_id` para ese nodo, el Lector usa el id del `<select>` y las dos claves **difieren legítimamente** ⇒ se hace un `GET /api/docs/content` de más. Costo real: una lectura de disco local, sin LLM. **Lo binario es:** (a) la clave es esa expresión, (b) el peek muestra el texto correcto, (c) mover la selección N veces sobre el **mismo** nodo no dispara N fetches (eso sí lo garantiza `staleTime`).
- Render: título (`previewTitle(content) ?? node.label`), chip de fuente, chip `Desactualizada` si `node.has_stale`, `<p>{previewExcerpt(content, 600)}</p>`, botón **"Abrir en el Lector"**, botón **"Enfocar"**, y la lista `Relaciones` (F4).
- Estados: cargando → `SkeletonList` (`frontend/src/components/SkeletonList.tsx`, ya existe); error → texto llano `No se pudo cargar la vista previa.` **sin** lanzar.

#### F6.3 — Cableado

- `ui.peekNodeId` se setea en `FOCUS_NODE` (ya lo hace el reducer) y con un click simple sobre un nodo cuando **no** se quiere enfocar (misma acción: enfocar ya abre el peek — un solo gesto, menos ruido).
- El panel va **a la derecha** del `.canvasBox`, dentro de `.wrap`, con `display: grid; grid-template-columns: 1fr minmax(0, 320px);` cuando hay peek y `1fr` cuando no. El canvas ya se re-dimensiona solo por el `ResizeObserver` (`DocGraphView.tsx:459`).
- `Escape` cierra el peek (`SET_PEEK` con `null`), ya cubierto en F3.

#### Tests de F6 (TDD)

**`Stacky Agents/frontend/src/docs/graphPreview.test.ts`** (NUEVO):
- `it("previewExcerpt con undefined devuelve cadena vacia")`
- `it("previewExcerpt con cadena vacia devuelve cadena vacia")`
- `it("previewExcerpt quita el frontmatter YAML inicial")`
- `it("previewExcerpt con frontmatter sin cierre NO borra el documento")`
- `it("previewExcerpt quita los bloques de codigo cercados")`
- `it("previewExcerpt quita las almohadillas de los encabezados")`
- `it("previewExcerpt convierte un link markdown en su texto")`
- `it("previewExcerpt convierte un wikilink con alias en el alias")`
- `it("previewExcerpt convierte un wikilink sin alias en el nombre")`
- `it("previewExcerpt colapsa saltos de linea en un solo espacio")`
- `it("previewExcerpt corta en maxChars y agrega puntos suspensivos")`
- `it("previewExcerpt no agrega puntos suspensivos si el texto entra entero")`
- `it("previewExcerpt corta en el ultimo espacio, no a mitad de palabra")`
- `it("previewExcerpt sobre 100 KB termina en menos de 1000 ms")` — (C10) guardia contra regex catastrófica; un rojo solo por tiempo no bloquea la fase.
- `it("previewTitle devuelve el primer H1 sin la almohadilla")`
- `it("previewTitle ignora un H1 que este dentro del frontmatter")`
- `it("previewTitle devuelve null si no hay H1")`

**Comandos:**
```
# desde "Stacky Agents/frontend"
npx vitest run src/docs/graphPreview.test.ts
npx vitest run src/__tests__/uiDebtRatchet.test.ts
npx tsc --noEmit
```

**Criterio de aceptación binario.** `graphPreview.test.ts` verde (17 casos), **los dos ratchets en DELTA** (regla B6/v3), `tsc --noEmit` 0 errores, y verificación visual F8 paso 9 (el peek muestra **texto real** del documento correcto, y hacer click 3 veces sobre el mismo nodo dispara **como mucho un** `GET /api/docs/content`). ⚠️ (C8) Que además reuse la entrada de cache del Lector es deseable pero **no** es criterio de aceptación.

**Flag.** `STACKY_DOCS_GRAPH_EXPLORER_ENABLED` — **default ON**.

**Impacto por runtime.** Ninguno en los tres: `GET /api/docs/content` es lectura de disco con guardia de path traversal (`backend/services/doc_indexer.py`, `read_content()`), sin LLM. Fallback en los tres: flag OFF → sin peek; se abre la nota en el Lector como en el 111. Si `GET /api/docs/content` falla (404/500), el panel muestra el mensaje de error y el grafo sigue funcionando.

**Trabajo del operador: ninguno.**

---

### F7 — Minimapa y nivel de detalle por escala

**Objetivo.** No perderse cuando se está muy adentro, y no ver un plato de fideos cuando se está muy afuera.

**Valor.** Cierra el gap (g).

**Archivos.**
- CREAR `Stacky Agents/frontend/src/docs/graphMinimap.ts`
- CREAR `Stacky Agents/frontend/src/docs/graphMinimap.test.ts`
- EDITAR `Stacky Agents/frontend/src/components/docs/DocGraphView.tsx`
- EDITAR `Stacky Agents/frontend/src/components/docs/DocGraphExplorer.module.css`

#### F7.1 — `graphMinimap.ts` (puro)

```ts
/**
 * graphMinimap.ts — Plan 268 F7. Matemática pura del minimapa. Sin canvas.
 */
import type { Viewport } from "./graphViewport";

export interface Bounds { minX: number; minY: number; maxX: number; maxY: number; }
export interface MinimapTransform { scale: number; offsetX: number; offsetY: number; }
export interface Rect { x: number; y: number; w: number; h: number; }

/** Bounding box de los puntos (con radio). Lista vacía → {0,0,0,0}. */
export function boundsOf(points: { x: number; y: number; r?: number }[]): Bounds

/** Transformación mundo → minimapa (mmW × mmH px) preservando el aspect ratio y centrando. */
export function minimapTransform(b: Bounds, mmW: number, mmH: number, padding?: number): MinimapTransform

/** Rectángulo (en px del minimapa) que representa lo que se ve hoy en el canvas.
 *  CLAMPEADO al rectángulo del minimapa: nunca sale de sus bordes. */
export function viewportRectInMinimap(
  vp: Viewport, canvasW: number, canvasH: number, t: MinimapTransform
): Rect

/** Click en (mx,my) del minimapa → Viewport centrado en ese punto del mundo, misma escala. */
export function viewportFromMinimapClick(
  vp: Viewport, mx: number, my: number, t: MinimapTransform, canvasW: number, canvasH: number
): Viewport

/**
 * (C13) Predicado PURO del nivel de detalle: ¿se dibuja esta arista a esta escala?
 * Sacado de draw() a propósito: dentro de draw() sería intesteable (no hay jsdom ni
 * canvas en este repo), y una regla de dibujo sin test es una regla que nadie sabe
 * si funciona.
 *
 * Regla: a escala < LOD_SCALE_THRESHOLD (0.6) se ocultan las aristas cuyos DOS
 * extremos son nodos poco conectados. "Poco conectado" = radio < LOD_MIN_RADIUS (6).
 * Con nodeRadius(d) = 4 + min(11, d*1.15) (forceLayout.ts:47-49), r < 6 equivale
 * EXACTAMENTE a in_degree <= 1 (d=1 → r=5.15; d=2 → r=6.3). O sea: a alejarse se
 * ven los troncos y desaparecen las hojas. A escala >= 0.6 se dibuja todo.
 */
export const LOD_SCALE_THRESHOLD = 0.6;
export const LOD_MIN_RADIUS = 6;
export function shouldDrawEdge(rA: number, rB: number, scale: number): boolean
```

**Casos borde:** 0 puntos (`scale` = 1, rect = todo el minimapa); 1 punto (span 0 → usar `Math.max(1e-6, span)`, igual que `fitViewport`); viewport más grande que el grafo (el rect se clampea al minimapa completo); viewport totalmente fuera del bounding box (rect clampeado, `w`/`h` ≥ 0, nunca negativos).

#### F7.2 — Dibujo del minimapa

Un **segundo `<canvas>`** de 160×110 px CSS, posicionado con la clase `.minimap` (esquina inferior izquierda del `.canvasBox`). **(C13) Cableado exacto — el v1 no lo decía y sin esto la fase no es implementable:**

1. **Ref:** `const minimapRef = useRef<HTMLCanvasElement | null>(null);` junto a `canvasRef` (línea 85). El `<canvas ref={minimapRef} className={styles.minimap} />` se renderiza **solo** si `explorerEnabled && nodeCount > 0`, hermano del `<canvas>` principal dentro del `.canvasBox` (línea 536).
2. **Tamaño y DPR:** dentro del efecto de layout, una función `sizeMinimap()` que hace **exactamente** lo mismo que `sizeCanvas()` (líneas 135-145) sobre `minimapRef.current` con `MM_W = 160`, `MM_H = 110` fijos (no dependen del `getBoundingClientRect`, así que no hace falta observarlo con el `ResizeObserver`). Si `minimapRef.current` es `null` (flag OFF), **sale sin hacer nada**.
3. **Dibujo:** una función `drawMinimap()` llamada **al final de `draw()`**, no en un `requestAnimationFrame` propio (eso duplicaría el costo por frame). Primera línea: `if (!explorerEnabledRef.current) return;` (I2 — se lee el **ref**, no la variable del render). Dibuja:
   - un punto de 1.5 px por nodo, con el color de su grupo (`colorForGroup` + `groupSlotsRef.current`) y alpha 0.7,
   - **sin aristas** (a esa escala son ruido),
   - el rectángulo de `viewportRectInMinimap(...)` con `strokeStyle = palette.halo` y `lineWidth = 1`.
4. **Click:** se registra `minimap.addEventListener("pointerdown", onMinimapDown)` **dentro del mismo efecto** de layout y se quita en su `return` de limpieza (líneas 478-490), junto a los otros 6 listeners. El handler calcula `(mx,my)` con el `getBoundingClientRect()` **del minimapa** (no del canvas principal) y llama `setViewport(viewportFromMinimapClick(...))` (F3, C7).
5. **Aislamiento del hit-test:** el minimapa es un elemento hermano **encima** del canvas principal, así que sus eventos **no** llegan a `onPointerDown`/`nearestNode`. Igual, el handler hace `ev.stopPropagation()` como cinturón y tirantes. En CSS, `.minimap { pointer-events: auto; }` y `.hint { pointer-events: none; }` (el hint ya está por encima y no debe robar clicks).

#### F7.3 — Nivel de detalle (LOD) por escala

En `draw()`, tres umbrales fijos y explícitos:

| Condición | Efecto | Cómo se decide |
|---|---|---|
| `vp.scale < LOD_SCALE_THRESHOLD` (0.6) | **No** dibujar aristas cuyos dos extremos tengan `r < LOD_MIN_RADIUS` (6), es decir `in_degree <= 1`. Reduce el hairball a la estructura troncal. | **`shouldDrawEdge(a.r, b.r, vp.scale)`** — predicado puro con test (C13), no un `if` suelto dentro de `draw()` |
| `vp.scale < 0.6` | **No** dibujar labels salvo hover / seleccionado / coincidencia activa | `if` en el armado de candidatos (líneas 236-260) |
| `vp.scale >= 1.4` | Se dibujan labels de todos los nodos visibles (ya existe: `zoomedIn`, línea 237) | sin cambios |
| `state.nodes.length > 800` | `pickVisibleLabels(candidates, 30)` en vez de 60 | línea 261 |

⚠️ El LOD **solo** aplica en modo explorador: la guarda es **`explorerEnabledRef.current`** (I2 — leer el ref, no la variable del render, o el LOD queda pegado al valor del primer render, que es `false` porque `sourcesData` llega **después**; C2). Con la flag OFF el dibujo es observacionalmente el del 111.
⚠️ Los umbrales `0.6`, `6`, `1.4`, `800`, `60`, `30` son **constantes exportadas**, no números mágicos repartidos por `draw()`: `LOD_SCALE_THRESHOLD` y `LOD_MIN_RADIUS` van en `graphMinimap.ts`; los otros cuatro quedan como `const` con nombre arriba de `DocGraphView.tsx`, junto a `LABEL_FONT_PX` (línea 77).

#### Tests de F7 (TDD)

**`Stacky Agents/frontend/src/docs/graphMinimap.test.ts`** (NUEVO):
- `it("boundsOf con lista vacia devuelve ceros")`
- `it("boundsOf incluye el radio de cada punto")`
- `it("minimapTransform preserva el aspect ratio")`
- `it("minimapTransform con un solo punto no divide por cero")`
- `it("minimapTransform centra el contenido dentro del minimapa")`
- `it("viewportRectInMinimap devuelve el minimapa entero cuando el viewport abarca todo")`
- `it("viewportRectInMinimap se achica al acercar el zoom")`
- `it("viewportRectInMinimap queda clampeado dentro del minimapa")`
- `it("viewportRectInMinimap nunca devuelve ancho o alto negativos")`
- `it("viewportFromMinimapClick centra el punto clickeado y conserva la escala")`
- `it("viewportFromMinimapClick en una esquina no rompe el viewport")`
- **(C13) LOD:**
- `it("shouldDrawEdge devuelve true a escala normal aunque los dos nodos sean chicos")`
- `it("shouldDrawEdge oculta la arista entre dos nodos de radio menor a 6 al alejar")`
- `it("shouldDrawEdge conserva la arista si al menos un extremo es un hub")`
- `it("shouldDrawEdge con los radios que produce nodeRadius oculta exactamente in_degree<=1")` — usa `nodeRadius` de `forceLayout.ts` para que el umbral quede atado al modelo real y no a un número inventado.

**Comandos:**
```
# desde "Stacky Agents/frontend"
npx vitest run src/docs/graphMinimap.test.ts
npx vitest run src/docs/graphViewport.test.ts
npx tsc --noEmit
```

**Criterio de aceptación binario.** `graphMinimap.test.ts` verde (**15 casos**: 11 del v1 + 4 de `shouldDrawEdge`), `graphViewport.test.ts` sigue verde, `tsc --noEmit` 0 errores, y verificación visual F8 pasos 16-17.

**Flag.** `STACKY_DOCS_GRAPH_EXPLORER_ENABLED` — **default ON**.

**Impacto por runtime.** Ninguno en los tres. Es dibujo en un canvas del navegador. Fallback en los tres: flag OFF → sin minimapa ni LOD, como en el 111.

**Trabajo del operador: ninguno.**

---

### F8 — Verificación visual manual (la hace el operador)

**Objetivo.** Cerrar lo que este repo **no puede** automatizar.

**Por qué es una fase y no un apéndice.** En `Stacky Agents/frontend` **no están instalados** React Testing Library ni jsdom (`package.json`: devDeps = `@types/react`, `@types/react-dom`, `@vitejs/plugin-react`, `typescript`, `vite`, `vitest` — nada más). Por lo tanto **ningún test automatizado puede tocar el DOM ni el canvas**. La única verificación posible del render es humana. Esta fase existe para que quede escrito qué mirar, y para que nadie declare "listo" sin haberlo mirado.

**Preparación.**
1. Desde `Stacky Agents`, levantar el backend con **`backend\.venv\Scripts\python.exe backend/app.py`** (o el launcher habitual). [!] **(B1/v3)** El v2 decía `.venv\Scripts\python.exe` y esa ruta **no existe**.
2. Confirmar en `http://localhost:5050/api/docs/sources` que el JSON trae `"graph_enabled": true` y `"graph_explorer_enabled": true`.
3. Desde `Stacky Agents/frontend`, `npm run dev` y abrir la app.
4. Ir a **Docs** → pestaña **Grafo**.

**Pasos y qué debe verse EXACTAMENTE.**

| # | Acción | Resultado esperado |
|---|---|---|
| 1 | Abrir la pestaña Grafo | Se ve la barra de filtros arriba, el canvas con el grafo, los botones de zoom abajo a la derecha y el minimapa abajo a la izquierda. El contador dice `Mostrando N de N nodos`. |
| 2 | Click en el chip de una sola fuente en "Fuente" | El canvas se redibuja con menos nodos; el contador baja; el chip queda con estado presionado. |
| 3 | Click en "Limpiar filtros" | Vuelven todos los nodos; el contador vuelve a `N de N`; el botón queda deshabilitado. |
| 4 | Click en `+` tres veces | El grafo se agranda anclado al centro; el porcentaje sube (≈100% → 195%); el rectángulo del minimapa se achica. |
| 5 | Tecla `f` con foco en el canvas | Todo el grafo entra en pantalla con margen; ningún nodo queda cortado por los bordes. |
| 6 | Tecla `0` | Vuelve a 100% y a la posición original. |
| 7 | Escribir una palabra en el buscador | Los nodos que no matchean se atenúan; aparece `1 de m`; el primer resultado queda centrado y con anillo resaltado. |
| 8 | Enter varias veces | El contador avanza `2 de m`, `3 de m`, …, vuelve a `1 de m`; el canvas se centra en cada resultado. |
| 9 | Click simple en un nodo nota, tres veces seguidas sobre el mismo | El grafo se reduce a ese nodo y sus vecinos; aparecen las migas `← Volver · Foco: <nota> · 1 2 3 · Ver todo`; a la derecha aparece el peek con el título y las **primeras líneas reales** del documento y la lista `Relaciones`. **En la pestaña Red: como mucho UN `GET /api/docs/content` para los tres clicks.** (C8) Que además reuse la entrada que dejó el Lector es deseable, **no** obligatorio. |
| 10 | Click en un vecino de la lista `Relaciones` | El foco salta a ese vecino, el peek cambia de documento y `← Volver` queda habilitado. |
| 11 | Click en `← Volver` | Vuelve al nodo anterior. |
| 12 | Click en `2` en el control de profundidad | Aparecen los vecinos de los vecinos; el contador de nodos sube. |
| 13 | Click en "Ver todo" | Vuelve el grafo completo (con los filtros que hubiera puestos). |
| 14 | Click en un ítem de la leyenda | Ese grupo colapsa a un único nodo grande con la etiqueta `Notas · <fuente> (k)`; las aristas hacia ese grupo se conservan; el ítem queda presionado. Click de nuevo → se expande. |
| 15 | Doble click en un nodo nota | Se abre el Lector con esa nota (la vista cambia de pestaña). |
| 16 | Click en el minimapa, en una zona lejana | El canvas se desplaza a esa zona; el rectángulo del minimapa se mueve ahí. |
| 17 | Alejar hasta ~40% | Desaparecen las aristas entre nodos poco conectados y casi todos los labels: se ve la estructura troncal, no un plato de fideos. |
| 18 | Cambiar el tema claro/oscuro de la app | **(C1) Este paso recién ahora significa algo.** Los colores del canvas, del minimapa y del peek acompañan el tema: en claro las notas se ven `#0969da` y no `#388bfd`. Ningún color queda "pegado" del tema anterior (puede requerir volver a entrar a la pestaña: **documentarlo si pasa**, no es bloqueante). |
| 18b | Con el tema claro puesto, mirar la leyenda del explorador y el canvas | **(C1) Cada swatch de la leyenda tiene EXACTAMENTE el mismo color que los nodos de su grupo en el canvas.** Ningún swatch transparente o invisible. |
| 18c | Zoom al 195% con `+`, y después tocar un chip de fuente en la barra de filtros | **(C7)** El grafo se re-encuadra solo con el subgrafo filtrado **y el porcentaje del control de zoom coincide con lo que se ve**. No puede decir 195% mientras el grafo está al 100%. |
| 18d | Con un nodo enfocado, colapsar desde la leyenda el grupo al que ese nodo pertenece | **(C3/G13) El canvas NO queda en blanco.** O el foco salta al super-nodo del grupo (migas: `Foco: Notas · <fuente> (grupo colapsado)`), o aparece el aviso `El nodo enfocado no está en la vista actual…` con el grafo agrupado completo detrás. |
| 18e | Buscar una palabra con ≥3 coincidencias y apretar Enter dos veces | **(C2) El anillo resaltado se MUEVE al 2.º y al 3.º resultado.** Si el contador avanza pero el anillo se queda en el primero, el `draw()` tiene un closure stale: falta el `activeMatchIdRef` de I2. |
| 18f | Click sobre el nodo grande de un grupo colapsado | **(C4)** El grupo se **expande** (no se enfoca, no abre nada). Doble click sobre él: **no pasa nada**. |
| 18g | Click en el canvas y después apretar `f` sin tocar nada más | **(C9)** El grafo se ajusta a pantalla. Si no pasa nada, falta el `boxRef.current?.focus()` del `onPointerDown` y **todos** los atajos están muertos. Además, al hacer click debe verse el contorno de foco en el borde del canvas. |
| 19 | Apagar `STACKY_DOCS_GRAPH_EXPLORER_ENABLED` desde el panel de flags y recargar | La pestaña Grafo vuelve **exactamente** a la del plan 111: buscador simple, leyenda, botón "Centrar"; click abre la nota; doble click resetea la vista. |
| 20 | Apagar `STACKY_DOCS_GRAPH_ENABLED` y recargar | Las tres pestañas (Lector/Cobertura/Grafo) desaparecen y la página Docs se comporta como antes del plan 109. |

**Criterio de aceptación binario.** Los **26** pasos de la tabla dan el resultado esperado. [!] **(I2/v3) El v2 decía "27 pasos (20 del v1 + los 7 nuevos 18b-18g)" y las dos cifras estaban mal**: `18b, 18c, 18d, 18e, 18f, 18g` son **6**, no 7, y la tabla tiene **26** filas (1-18 = 18, + 6 intercaladas, + 19 y 20). Es exactamente el error que C15 decía haber matado en el v1 ("DoD-1 decía 8 y listaba 10"), reintroducido. **Contá las filas antes de firmar.** Cualquier desvío se anota **en este mismo documento**, en una sección `## 10. Desvíos de la verificación visual`, con el paso, lo observado y si se corrigió.

**Trabajo del operador (recuento honesto y ÚNICO — I3/v3).** **26 pasos, ~13 minutos**, una sola vez, al final. Es la **única** fase del plan que le pide algo al operador, y es inevitable: no hay RTL ni jsdom en el repo. Los 6 pasos nuevos (18b-18g) suman ~3 minutos y cada uno caza un bloqueante concreto. [!] El v2 decía tres cifras distintas en el mismo documento ("27 pasos / ~13 min", "los 20 pasos, ~10 minutos" y "20 pasos" en §9.2). **La cifra correcta, y la única que aparece de acá en adelante, es 26 pasos / ~13 minutos.**

**Flag.** N/A (se verifican los dos estados de `STACKY_DOCS_GRAPH_EXPLORER_ENABLED`).

**Impacto por runtime.** Ninguno en los tres: la verificación es del navegador contra el backend local.

**Trabajo del operador: SÍ — esta fase es explícitamente suya** (los **26** pasos, **~13 minutos**; misma cifra que el recuento de arriba, I3/v3). Es la única del plan que lo requiere, y es inevitable: el repo no tiene entorno de test de DOM. Ninguna otra fase le pide nada.

---

## 7. Riesgos y mitigaciones

| # | Riesgo | Probabilidad | Impacto | Mitigación (concreta) |
|---|---|---|---|---|
| R1 | **Desalineación de índices**: el layout indexa `state.nodes[i]` contra `graph.nodes[i]`; si una parte del componente usa `graph` y otra `visibleGraph`, los labels y los colores salen del nodo equivocado. | Alta | Alto (bug silencioso, se ve como "labels cruzados") | Invariante escrita en F1.3: **dentro del efecto de layout y de `draw()` se usa SOLO `visibleGraph`**; deps del efecto = `[visibleGraph, selectedNodeId]`. En la revisión de diff, `grep -n "graph\." DocGraphView.tsx` y verificar cada hit. |
| R2 | **Re-inicialización del layout en cada tecleo**: `visibleGraph` es un objeto nuevo por cada cambio de filtro/foco ⇒ el efecto se re-ejecuta ⇒ el grafo "salta" y se re-simula desde cero. | Alta | Medio (UX molesta) | `applyGraphFilters` con `EMPTY_FILTERS` y `collapseGroups` con lista vacía devuelven el **MISMO objeto** (identidad referencial, especificado en F1.1 y F5.1). Además `useMemo` con deps exactas. El salto al **cambiar un filtro** es aceptable y esperado (el subgrafo es otro). |
| R3 | **Ratchet de deuda visual rojo** por agregar hex o `style={{}}`. | Media | Bajo (pero bloquea) | G8: `.tsx` nuevos con cero `style={{}}`; CSS nuevo con `var(--token)` **sin** fallback hex y `var(--duration-*)`. Correr `uiDebtRatchet` y `motionDebtRatchet` al cerrar **cada** fase, no al final. |
| R4 | **Import circular** `forceLayout ↔ graphGrouping`. | Baja | Alto (build roto) | F5.3: `graphGrouping.ts` importa **solo tipos** de `docGraphModel`. Gate: `npx tsc --noEmit`. |
| R5 | **Peek que dispara fetches de más** al mover la selección rápido. | Media | Medio (ruido de red) | La `queryKey` es idéntica a la del Lector ⇒ cache compartida; `staleTime: 5 min`; `enabled` solo para `kind === "note"` con `path` no vacío. Verificación visual paso 9 mira la pestaña Red. |
| R6 | **Performance con miles de nodos**: los filtros y el BFS corren en cada render. | Media | Medio | Todo memoizado con `useMemo` de deps exactas; los helpers son O(n+m) y tienen tests de tiempo (F1, F2, F4, F6). El tope `MAX_ANIMATED_NODES = 300` sigue vigente sin cambios. |
| R7 | **El operador pierde el gesto conocido**: en el 111 el click abre la nota; en el explorador el click enfoca. | Alta | Bajo | El `.hint` lo dice explícitamente (`Click: enfocar · Doble click: abrir`), el peek trae el botón "Abrir en el Lector", y con la flag OFF el gesto viejo vuelve intacto. Se valida en el paso 15 de F8. |
| R8 | **La flag nueva rompe tres tests del arnés** si se olvida alguna de las 7 patas. | Media | Bajo (rojo evidente) | F0.1 lista las 7 patas numeradas, y F0 exige correr `test_harness_flags.py`, `test_harness_flags_requires.py` y `test_harness_flags_help.py`. |
| R9 | **`test_harness_flags_help.py` tiene 4 fallos ajenos preexistentes** y se interpreta como rojo propio. | Alta | Bajo | Escrito en F0.1 punto 4: validar **solo** la entrada nueva leyendo el output; los 4 fallos ajenos no cuentan. |
| R10 | **El operador insiste con Grapify.** | Baja | Bajo | §3 documenta la evidencia, la fecha y las 3 razones. Si aparece una librería de grafos de red que valga la pena, es un plan aparte con su propia decisión de arquitectura. |
| R11 | **Sobrecarga de la barra de filtros** (demasiados controles arriba del canvas). | Media | Medio (UX) | La barra es una sola fila con `flex-wrap`; los grupos poco usados (`minDegree`, `edgeKinds`) van detrás de un `<details>` "Más filtros" cerrado por default. Se valida en F8 paso 1. |
| R12 | **(C2) Closure stale en `draw()`**: el anillo del resultado de búsqueda, los colores de grupo o el LOD quedan congelados en el valor del primer render. Es **silencioso**: nada falla, simplemente no se actualiza. | **Alta** (el v1 lo tenía) | Alto | Guardarraíl **G12** + invariante **I2** en F1.3 (lista cerrada de refs + un único efecto de sincronización) + F8 paso 18e, que lo caza en 5 segundos. |
| R13 | **(C3) Canvas vacío por composición**: colapsar el grupo del nodo enfocado o filtrarlo deja `nodes: []`. | **Alta** (el v1 lo tenía) | Alto (parece que la app se rompió) | Guardarraíl **G13** + `resolveFocusId` (F4.1) con 5 tests + el caso de propiedad "componer nunca devuelve vacío" + F8 paso 18d. |
| R14 | **(C1) Colores que no existen**: se agregan tokens `var(--algo)` que el tema no define. En el canvas se ve el fallback; en el CSS se ve **nada**. | Media (es el estado ACTUAL del 111) | Medio | `graphPalette.ts` es la única lista de tokens y `graphPalette.test.ts` lee `theme.css` de disco y falla si un token no está en el bloque oscuro **y** en el claro; incluye un caso que barre los `.module.css` de `components/docs/`. |
| R15 | **(C6) Gates que no pueden fallar** (falso verde). El `git diff --stat` con pathspec relativo era el caso concreto. | Media | Alto (da confianza falsa) | Todo gate del plan se ejecuta al menos una vez **esperando ROJO** antes de darlo por bueno: el `git diff --exit-code` se prueba tocando el `package.json` y revirtiendo; el caso de tokens de F0.6 **nace rojo** por diseño. Verificado: `git ls-files -- "Stacky Agents/frontend/package.json"` desde `frontend/` matchea **0** archivos; con `:/` matchea **1**. |
| R16 | **(B6/B8/v3) Gates que NO PUEDEN PASAR** (el espejo de R15): un criterio binario que exige "verde" sobre un gate compartido **que ya está rojo por deuda ajena**. El v2 lo tenía en 7 lugares con los dos ratchets y en DoD-12 con el catálogo de huellas. | **Alta** (el v2 lo tenía) | **Alto**: el modelo menor no se traba, **regenera el baseline** — y con eso absorbe en silencio la deuda propia del plan, que es peor que no tener ratchet. | **F0.0** mide y congela el rojo ajeno **antes** de escribir código; todos los criterios pasan a **delta** (ningún archivo del plan en la lista, conteo que no sube, baseline intacto). Regla general para planes futuros: **un gate compartido nunca se pide "en verde", siempre "sin empeorar"**. |
| R17 | **(B3/B4/B5/v3) Costura entre fases que no compila**: F(n) escribe código que referencia símbolos que recién nacen en F(n+1) o F(n+2). El v2 lo tenía **tres** veces (`Palette.groups`, `activeMatchId`/`groupSlots`, `setViewport`), y las tres son invisibles leyendo: solo aparecen compilando. | **Alta** (el v2 lo tenía; es el motivo por el que el v1 fue rechazado) | **Alto**: la fase no cierra, y el gate que lo detecta (`tsc --noEmit`) es el mismo que la fase declara como criterio ⇒ deadlock. | Regla dura: **toda fase compila sola**. Si necesita un símbolo futuro, F(n) declara el **placeholder tipado** y F(n+1) lo sustituye **sin tocar nada más** (contratos escritos en F1.3-3 para `activeMatchId`/`groupSlots`, en F0.6 para `Palette.groups`, y en F1.3-3 + F3 para `setViewportRef`). Verificación: al cerrar cada fase, `npx tsc --noEmit` con **0** errores, y el diff de la fase siguiente **no** debe tocar la lista de refs ni el efecto de sincronización. |

---

## 8. Fuera de scope (y por qué)

- **Integrar Grapify.** Técnicamente inviable (§3, E1-E3). Se entrega la capacidad completa sobre el motor propio.
- **Cualquier dependencia nueva de `frontend/package.json`** (d3, cytoscape, react-force-graph, sigma.js, vis-network). Prohibido por G1 y por la decisión del plan 111.
- **Cambios en el backend del grafo** (`backend/services/doc_graph.py`): el contrato del 109 alcanza y sobra. **Único** cambio backend del plan: una línea en `backend/api/docs.py` para exponer la flag nueva.
- **Persistir el estado del explorador** (filtros/foco/grupos colapsados) entre sesiones o en la URL. Se evaluó y se deja fuera: agregaría superficie de persistencia (store, deep-link, migración) para una ganancia menor, y el estado se reconstruye en 2 clics. **Candidato claro para un plan siguiente** si el operador lo pide.
- **Layout jerárquico / por capas (dagre-like) o clustering automático por comunidades (Louvain).** Fuera: el force layout + la agrupación por fuente ya cubren la estructura que el corpus real tiene (docs agrupadas por carpeta/fuente). Un clustering automático además sería una forma de "decidir por el operador" (roza G4).
- **Exportar el grafo a PNG/SVG.** Fuera: no lo pidió el operador y agrega superficie (descarga de archivos) por poco valor.
- **Editar el grafo desde la vista** (crear links arrastrando, borrar nodos). Fuera y **prohibido**: G3 (read-only) y G4 (HITL). El grafo es el reflejo de los documentos; se cambia editando los documentos.
- **Tests de componente React de la nueva UI.** Imposible en este repo: no hay RTL ni jsdom. Sustituido por F8 (verificación visual manual) más cobertura pura exhaustiva de toda la lógica.
- **Búsqueda semántica / por embeddings en el grafo.** Fuera: introduciría una llamada a modelo en una vista que hoy es 100% local e instantánea, y rompería la paridad trivial de runtimes. Si se quiere, es un plan aparte sobre `docs-rag` (plan 112).

---

## 9. Glosario, orden de implementación y Definición de Hecho

### 9.1 Glosario (términos de la casa que un modelo menor puede no conocer)

| Término | Qué significa acá |
|---|---|
| **Arnés (harness)** | El sistema de *feature flags* de Stacky. Una flag vive en `backend/services/harness_flags.py` (registro `FlagSpec`), su default efectivo en `backend/config.py`, su ayuda llana en `harness_flags_help.py`, y se edita desde la UI. |
| **`FlagSpec`** | La declaración de una flag: `key`, `default`, `type`, `label`, `description`, `group`, `env_only`, `requires`. |
| **`_CURATED_DEFAULTS_ON`** | Set en `backend/tests/test_harness_flags.py` que lista las flags cuyo default es ON **a propósito**. Una flag con `default=True` que no esté ahí pone el meta-test en rojo. |
| **`_REQUIRES_MAP_FROZEN`** | Dict en `backend/tests/test_harness_flags_requires.py` que congela el grafo de dependencias entre flags. Declarar `requires=` sin agregarlo acá = rojo. |
| **R4 (profundidad 1)** | Regla: la flag "madre" de una dependencia no puede a su vez declarar `requires`. `STACKY_DOCS_GRAPH_ENABLED` no lo declara, así que la cadena es válida. |
| **Ratchet** | Test que congela una métrica de deuda **por archivo** y solo la deja bajar. Acá importan `uiDebtRatchet` (hex en `*.module.css`, `style={{` en `*.tsx`) y `motionDebtRatchet` (tiempos y `cubic-bezier` literales en `*.module.css`). |
| **Rojo ajeno / preexistente** | Un test que ya fallaba antes de tocar nada. No es responsabilidad de esta implementación; se documenta y se sigue. Se prueba corriendo el mismo test en un worktree del commit base. |
| **Falso verde** | Un test que pasa sin probar nada real (por ejemplo, porque una guardia temprana corta antes de llegar al código bajo prueba). Prohibido. |
| **Runtime** | El CLI que ejecuta a un agente: Codex CLI, Claude Code CLI o GitHub Copilot Pro. Este plan no invoca ninguno. |
| **HITL (human-in-the-loop)** | Riel duro de Stacky: el sistema amplifica al operador, nunca decide por él. |
| **Wikilink** | `[[nombre]]` o `[[nombre|alias]]` en un markdown; el plan 111 los hace clickeables resolviéndolos contra el índice del grafo. |
| **Huérfana (orphan)** | Nota que ningún otro documento referencia; el backend del 109 las lista en `graph.orphans`. |
| **Stale (desactualizada)** | Plan 114: una nota cuya referencia a código apunta a un archivo que cambió en git **después** de la última edición de la nota. Señal 100% git, sin LLM. |
| **`docsView`** | Estado de `DocsPage` que elige la vista: `"reader" | "coverage" | "graph"`. |
| **Mundo vs pantalla** | "Mundo" = coordenadas del layout del grafo; "pantalla" = píxeles del canvas. `toWorld`/`toScreen` convierten entre ambos usando el `Viewport`. |
| **Super-nodo** | Nodo sintético que representa un grupo colapsado; su id empieza con `group:`. |

### 9.2 Orden de implementación (estricto — cada fase depende de las anteriores)

0. **F0.0** — **[ADICIÓN ARQUITECTO #2]** Foto del rojo AJENO de los 5 gates compartidos, escrita en la tabla de F0.0. **Cero código.** Sin esto, B6 y B8 se repiten y el atajo siempre es regenerar el baseline.
1. **F0** — Flag (7 patas) + `nodeIndexById` + fix del `findIndex` + `fitViewport`/`centerOn`/`zoomAtCenter`/`ZOOM_STEP` + `graphExplorerState.ts` + **F0.6 `graphPalette.ts` (paleta REAL, C1)** + tests. **Lo único visible que cambia acá:** el grafo pasa a acompañar el tema, que es un bug vivo del 111 que este plan arregla de paso.
2. **F1** — `graphFilters.ts` + `DocGraphFilterBar.tsx` + `DocGraphExplorer.module.css` + cableado de `visibleGraph` en `DocGraphView` y de `explorerEnabled` en `DocsPage`.
3. **F2** — `graphSearch.ts` + contador `n de m` + Enter/Shift+Enter/Escape + encuadre al resultado activo (necesita `canvasSizeRef`).
4. **F3** — `DocGraphZoomControls.tsx` + atajos de teclado + `.hint` nuevo. (Reusa `fitViewport` de F0.)
5. **F4** — `graphNeighborhood.ts` + migas + profundidad 1-3 + cambio de gesto (click enfoca / doble click abre) + composición **filtros → agrupación → foco**.
6. **F5** — `graphGrouping.ts` + mover `groupOf` → `groupKeyOf` + color por grupo + leyenda accionable + colapso.
7. **F6** — `graphPreview.ts` + `DocGraphPeek.tsx` + lista `Relaciones` + layout en grid.
8. **F7** — `graphMinimap.ts` + segundo canvas + LOD por escala.
9. **F8** — Verificación visual manual del operador (**26** pasos, ~13 min; I3/v3).

> **Nota de dependencia cruzada F4↔F5:** F4 escribe la composición `filtros → agrupación → resolución del foco → foco` y por lo tanto **referencia** `collapseGroups`, que recién existe en F5. Para que F4 compile sola: en F4 la línea de `collapseGroups` se omite (`const grouped = filtered;`) y **`resolveFocusId` se implementa COMPLETO desde F4** — su regla 3 (remapeo al super-nodo) simplemente no se dispara todavía, y sus tests que dependen de `collapseGroups` quedan `it.skip` con el comentario `// se activa en F5`. F5 hace **dos** cosas: inserta `collapseGroups` en el medio y des-skippea esos casos. **Prohibido** escribir un `collapseGroups` provisorio en F4.
>
> **(C2) Nota transversal:** los cuatro `useRef` de la invariante I2 (`activeMatchIdRef`, `groupSlotsRef`, `explorerEnabledRef`, `canvasSizeRef`) y su efecto de sincronización se escriben **enteros en F1**, aunque F1 solo llene dos de ellos. Motivo: si cada fase agrega un ref, alguna se olvida y el bug de closure stale entra sin que ningún test lo note (no hay tests de componente en este repo). Se paga una vez, en F1.

### 9.3 Definición de Hecho (DoD) global

El plan 268 está HECHO cuando **todas** estas condiciones se cumplen y se pueden mostrar:

- [ ] **DoD-1.** (C15 — el v1 decía "8" y listaba 10) Los **11** archivos de test frontend nombrados en el plan están en verde, corridos **uno por uno** desde `Stacky Agents/frontend` (hay contaminación cross-file conocida en la corrida completa):
  `graphViewport.test.ts`, `graphExplorerState.test.ts`, `docGraphModel.test.ts`, **`graphPalette.test.ts`**, `graphFilters.test.ts`, `graphSearch.test.ts`, `graphNeighborhood.test.ts`, `graphGrouping.test.ts`, `graphPreview.test.ts`, `graphMinimap.test.ts`, `forceLayout.test.ts`.
- [ ] **DoD-2.** `npx tsc --noEmit` desde `Stacky Agents/frontend` sale con **0 errores**. [!] **(N1/v4)** Este gate es el que caza la clase de bug más recurrente de este plan (costura que no compila): se corre al cerrar **cada** fase, no solo al final. Las tres pasadas del juez encontraron `TS2391`, `TS2353`, `TS2552` y `TS2304` **compilando los snippets**, no leyéndolos.
- [ ] **DoD-2bis.** (N1/v4) El **grep-gate de símbolo sin importar** de §6.0 da **0 hits** sobre `DocGraphView.tsx`, y la **tabla de imports por fase** de §6.0 quedó aplicada entera (los 9 grupos de `import`). Sin esto, F1..F7 acumulan un `TS2304` por símbolo: compilado verbatim, el v3 daba **exit 2** con 5 errores solo en F1.3.
- [ ] **DoD-3.** (B6/v3 — **DELTA**, no verde absoluto) Los dos ratchets **ya están rojos por deuda AJENA** medida en F0.0 (`uiDebtRatchet` **2** archivos regresivos, `motionDebtRatchet` **7**, en 9 archivos que este plan **no toca**). Se cumple cuando, con `npx vitest run src/__tests__/uiDebtRatchet.test.ts` y `.../motionDebtRatchet.test.ts`:
  1. **ningún** archivo tocado o creado por el plan 268 aparece en una línea `REGRESION`,
  2. el conteo de líneas `REGRESION` **no superó** el de F0.0 — **4** (ui) y **14** (motion), que es lo que devuelve `grep -c "REGRESION"`; los archivos **distintos** son 2 y 7 (vitest imprime cada error dos veces),
  3. **no se regeneró ningún baseline**.
  Exigir "verde absoluto" (lo que hacía el v2) es insatisfacible y empuja a regenerar el baseline, que absorbería en silencio la deuda propia del plan.
- [ ] **DoD-4.** (C6) `git diff --exit-code -- ":/Stacky Agents/frontend/package.json"` sale con **código 0** (KPI K5). El prefijo `:/` es obligatorio: sin él, corrido desde `Stacky Agents/frontend`, el pathspec no matchea nada y el gate **nunca puede fallar**. Verificar el gate una vez a propósito: tocar el `package.json`, confirmar que sale con código 1, y revertir.
- [ ] **DoD-5.** Backend en verde desde `Stacky Agents`: `test_docs_api.py`, `test_harness_flags.py`, `test_harness_flags_requires.py`; y en `test_harness_flags_help.py` la entrada nueva sin fallos (los 4 fallos ajenos preexistentes documentados como tales).
- [ ] **DoD-6.** Las **7 patas** de `STACKY_DOCS_GRAPH_EXPLORER_ENABLED` están puestas: `config.py`, `FlagSpec`, `_CATEGORY_KEYS`, `harness_flags_help.py`, `_CURATED_DEFAULTS_ON`, `_REQUIRES_MAP_FROZEN`, `harness_defaults.env`. Verificable con `grep -rn "STACKY_DOCS_GRAPH_EXPLORER_ENABLED"` → **≥ 8 hits** (7 patas + `backend/api/docs.py`).
- [ ] **DoD-7.** Los **26** pasos de F8 (1-18, 18b-18g, 19 y 20) verificados por el operador; los desvíos anotados en `## 10` de este documento. (I2/v3: el v2 decía 27.)
- [ ] **DoD-11.** (C1, reescrito por **B7/v3**) Ningún archivo **que este plan posee** usa un token CSS que `frontend/src/theme.css` no defina. Los archivos poseídos son exactamente **cuatro**: `DocGraphView.module.css`, `DocGraphView.tsx`, `DocGraphExplorer.module.css` (nuevo) y los `.tsx` nuevos de `components/docs/` que crea el plan. Verificable con el caso `it("DocGraphView.module.css no usa ningun token inexistente")` de `graphPalette.test.ts`, y a mano con:
  ```
  # desde "Stacky Agents/frontend"
  grep -rn -- "var(--color-" src/components/docs/DocGraphView.module.css src/components/docs/DocGraphView.tsx src/components/docs/DocGraphExplorer.module.css src/docs/
  ```
  → **0 hits**.

  [!] **(B7/v3) El comando del v2 era insatisfacible y además contradecía a DoD-9.** Corrido tal cual: `grep -rn -- "var(--color-" src/components/docs/ src/docs/` devuelve **49 hits** — **17 propios** (14 en `DocGraphView.module.css` + 3 en `DocGraphView.tsx`, que F0.6 + I4 sí corrigen) y **32 AJENOS** que DoD-9 prohíbe tocar. **(v4:** el v3 anotaba "32 hits" como total; 32 es el subconjunto ajeno, el total es 49. El número operativo no cambia.**)** Los 32 ajenos están en: `DocBacklinksPanel.module.css` (**5**), `DocCoveragePanel.module.css` (**26** — y usa además `--color-success-bg`, `--color-warning`, `--color-warning-bg`, `--color-danger-bg`, que ni figuran en la tabla de sustitución de 6 filas de F0.6), `DocumenterResultPanel.tsx` (**1**, y es un `style={{}}` inline). Pedir 0 hits sobre todo el directorio obligaba a tocar 3 archivos ajenos — con 6 agentes trabajando en este mismo árbol, eso es una colisión asegurada.

  **Deuda ajena registrada (no se arregla acá):** esos 3 archivos arrastran el mismo bug que C1 encontró en `DocGraphView` — tokens `--color-*` inexistentes que resuelven a *unset* o al fallback. **Candidato claro para el plan siguiente**, con el mismo `graphPalette.ts` + `definedTokenNames()` que este plan deja construido: el fix sería mecánico y el test ya existiría. Anotarlo, no hacerlo.
- [ ] **DoD-12.** (C18, reescrito por **B8/v3** — huella de regresión) Se agrega a `Stacky Agents/docs/sistema/error_fingerprints.json` una entrada **solo por las clases que tienen una firma de log REAL**.

  [!] **(B8/v3) El DoD-12 del v2 era inimplementable y además rompía un test que hoy está VERDE.** Evidencia corrida:
  * El archivo es un **dict** `{schema_version, description, fingerprints}` con **42** huellas; las entradas van dentro de la lista `fingerprints`, no en la raíz.
  * Campos obligatorios por huella (verificados): `class, date_resolved, evidence, guard_test, id, killed_by, killed_commit, log_guarded, log_pattern, note, self_test, status, title`.
  * `backend/tests/test_error_fingerprints_catalog.py::test_patrones_compilan` hace **`re.compile(fp["log_pattern"])`**: `log_pattern` **NO puede ser `null`** (gotcha ya registrado en la casa: un `log_pattern: null` rompe el catálogo entero). Y `test_self_test_coherente` exige que **cada** `self_test.matches` matchee el patrón y **cada** `self_test.clean` no.
  * Ese archivo hoy da **3 failed / 5 passed** (rojo ajeno: `campos_obligatorios` por `PLAN239-OUTLET-EN-BLANCO` sin `self_test`, `status_enum`, `self_test_coherente`) — pero **`test_patrones_compilan` PASA**. Meter una huella con `log_pattern` nulo o inventado lo pondría **rojo por culpa de este plan**.
  * De las 4 clases que el v2 mandaba registrar, **tres son puramente visuales** ("el swatch se ve transparente", "el contador avanza pero el dibujo no se mueve", "la pantalla queda en blanco"): **no existe línea de log** para ellas, así que no hay `log_pattern` honesto posible.

  **Regla del v3:** una clase de error entra al catálogo **si y solo si** se puede escribir un `log_pattern` real y un `self_test` con `matches` y `clean` de verdad. Las que no, se registran **como prosa en la sección `## 10` de este documento**, que es donde ya viven los desvíos, y **no** se tocan el `.json`.

  | # | Clase | ¿Tiene firma de log? | Dónde se registra |
  |---|---|---|---|
  | 1 | Token CSS inexistente en un `.module.css` o en `readPalette` | **No** (defecto visual, sin log) | `## 10` + el test `graphPalette.test.ts` es la guardia real |
  | 2 | Closure stale en un `draw()` de canvas | **No** (silencioso por definición) | `## 10` + guardarraíl G12 + F8 paso 18e |
  | 3 | Canvas vacío por composición de filtros | **No** | `## 10` + G13 + `resolveFocusId` |
  | 4 | Gate de `git diff` con pathspec relativo | **No** (falso verde, no hay excepción) | `## 10` + R15 |

  ⇒ **En este plan, el `.json` NO se toca.** Se elimina de la lista de archivos del diff (ver DoD-9). Si en la implementación aparece una clase **con** firma de log, recién ahí se agrega, y el criterio de cierre es:
  ```
  # desde "Stacky Agents"
  backend\.venv\Scripts\python.exe -m pytest backend/tests/test_error_fingerprints_catalog.py -q
  ```
  → debe seguir dando **exactamente 3 failed / 5 passed** (mismo conteo que F0.0). Cualquier número distinto es daño propio.

  <details><summary>Texto original del v2 (conservado por trazabilidad; NO ejecutar)</summary>

  respetando el esquema que ya usa el archivo (leerlo antes de escribir; **no** inventar campos):
  1. **Token CSS inexistente en un `.module.css` o en `readPalette`** → síntoma: "el componente se ve casi bien pero los colores no cambian con el tema / un swatch se ve transparente"; causa: se usó `var(--color-x)` y el tema define `--x`; detección: `graphPalette.test.ts`.
  2. **Closure stale en un `draw()` de canvas** → síntoma: "el contador avanza pero el dibujo no se mueve"; causa: `draw()` definido dentro de un `useEffect` lee una variable del render que no está en las deps; detección: F8 paso 18e / guardarraíl G12.
  3. **Canvas vacío por composición de filtros** → síntoma: "la pantalla queda en blanco después de filtrar/colapsar"; causa: un id de selección sobrevive a una transformación que lo eliminó; detección: G13 + `resolveFocusId`.
  4. **Gate de `git diff` con pathspec relativo** → síntoma: "el gate siempre pasa"; causa: pathspec relativo al CWD; detección: probar el gate esperando rojo (R15).

  </details>
- [ ] **DoD-8.** Con la flag nueva en OFF, la pestaña Grafo se comporta **exactamente** como el plan 111 (F8 paso 19), y con `STACKY_DOCS_GRAPH_ENABLED` en OFF la página Docs se comporta como antes del 109 (F8 paso 20).
- [ ] **DoD-9.** Ninguna fase escribió en un documento, ticket, rama, BD ni sistema del operador: el diff completo del plan toca **solo** `frontend/src/**` (incluido `frontend/src/components/docs/DocGraphView.module.css`, cuyos 6 nombres de token se corrigen en F0.6; **`frontend/src/theme.css` NO se toca**), `backend/api/docs.py`, `backend/config.py`, `backend/services/harness_flags*.py`, `backend/tests/test_docs_api.py`, `backend/tests/test_harness_flags.py`, `backend/tests/test_harness_flags_requires.py`, `deployment/harness_defaults.env` y este documento. [!] **(B8/v3) `docs/sistema/error_fingerprints.json` SALE de la lista**: ver DoD-12 — las 4 clases que este plan mata no tienen firma de log y el catálogo no admite `log_pattern` nulo. **Cero archivos `test_*.py` nuevos** ⇒ no hay que registrar nada en `HARNESS_TEST_FILES` del arnés `.sh` ni en `$HarnessTestFiles` del `.ps1` (verificado: el plan solo **edita** archivos de test ya registrados).
- [ ] **DoD-10.** El estado de este documento se actualiza a `IMPLEMENTADO — <fecha>` con el detalle de qué fases quedaron cerradas y con qué evidencia (conteos de tests y comandos corridos), para que `supervisar-implementaciones-planes` pueda auditarlo.

---

## 10. Desvíos de la verificación visual y huellas SIN firma de log

### 10.1 Desvíos de F8 (lo completa el operador)

| Paso | Lo esperado | Lo observado | ¿Se corrigió? |
|---|---|---|---|
| _(vacío hasta correr F8)_ | | | |

### 10.2 Huellas de regresión SIN firma de log (B8/v3)

Estas **7** clases de error las **mata** este plan, pero **no tienen línea de log**, así que **no entran** en `docs/sistema/error_fingerprints.json` (su test guardián hace `re.compile(log_pattern)` y no admite `null`). Se registran acá, en prosa, con su guardia real. **(v4)** El v3 decía "4" mientras su tabla ya tenía **6** filas (las 5 y 6 las agregó él mismo) — el mismo error de conteo que I2 acababa de matar en F8. El v4 suma la fila **7** (N1) y deja la cifra igual a las filas. **Contá las filas antes de firmar.**

| # | Clase de error | Síntoma | Causa | Guardia que la mata |
|---|---|---|---|---|
| 1 | **Token CSS inexistente** en un `.module.css` o en `readPalette` | "se ve casi bien pero los colores no cambian con el tema"; un swatch transparente | se usó `var(--color-x)` y el tema define `--x` | `graphPalette.test.ts` (lee `theme.css` de disco; falla si el token no está en el bloque oscuro **y** en el claro) |
| 2 | **Closure stale en un `draw()` de canvas** | "el contador avanza pero el dibujo no se mueve" | `draw()` definido dentro de un `useEffect` lee una variable del render que no está en sus deps | guardarraíl **G12** + invariante **I2** (todo por `useRef`) + F8 paso 18e |
| 3 | **Canvas vacío por composición** | "la pantalla queda en blanco después de filtrar/colapsar" | un id de selección sobrevive a una transformación que lo eliminó | guardarraíl **G13** + `resolveFocusId` (F4.1, 5 tests + 1 de propiedad) + F8 paso 18d |
| 4 | **Gate de `git diff` con pathspec relativo** | "el gate siempre pasa" | pathspec relativo al CWD (matchea 0 archivos) y/o `--stat` sin `--exit-code` | pathspec `:/` + `--exit-code`, probado **esperando rojo** (R15) |
| 5 | **(B6/v3) Criterio binario sobre un gate compartido ya rojo** | "es imposible cerrar la fase" → se regenera el baseline | se pidió "verde absoluto" sobre un ratchet con deuda ajena | **F0.0** + criterio **delta** en todos lados (R16) |
| 6 | **(B3/B4/B5/v3) Costura entre fases que no compila** | `TS2353` / `TS2552` / `TS2304` al cerrar una fase | F(n) referencia símbolos que nacen en F(n+1) | placeholders tipados + refs de comando; `tsc --noEmit` al cerrar **cada** fase (R17) |
| 7 | **(N1/v4) Bloque de cableado sin su `import`** | `TS2304: Cannot find name '<símbolo>'` — 5 de golpe solo en F1.3 | el plan muestra el **cuerpo** del código y nunca el **encabezado**: el símbolo se usa pero no se importa | **tabla de imports por fase** + **grep-gate de símbolo sin importar** (§6.0, [ADICIÓN ARQUITECTO #3]), validado en las dos direcciones; y `tsc --noEmit` como gate final (R18) |
