# Plan 268 — Explorador del grafo documental: filtros, foco por vecindario, búsqueda navegable, agrupación y peek de contenido

> **Estado:** PROPUESTO — 2026-07-27 (v1, sin criticar)
> **Serie:** Documentación agéntica Obsidian (109 grafo backend → 111 graph view canvas → 114 staleness → **268 explorador**). Este plan NO toca el motor de grafo del backend: consume el mismo contrato `GET /api/docs/graph` del 109.
> **Pipeline:** este documento pasó `proponer`. Sigue `criticar-y-mejorar-plan` → `implementar-plan-stacky` → `supervisar-implementaciones-planes`.
> **Depende de:** Plan 109 (endpoint `GET /api/docs/graph`, contrato de `DocGraphResponse`/`DocGraphNode`/`DocGraphEdge`, flag `STACKY_DOCS_GRAPH_ENABLED`), Plan 111 (`forceLayout.ts`, `graphViewport.ts`, `DocGraphView.tsx`, pestaña "Grafo" en `DocsPage`), Plan 114 (campos `has_stale` / `edge.stale` / `stale_stats`).
> **Pedido literal del operador (2026-07-27):** *"Mejorar la visualización y la experiencia de uso del grafo de documentación, optimizando su estructura, legibilidad, navegación e interacción. Siempre que sea técnicamente viable, integrar Grapify directamente en la plataforma... La solución debe permitir explorar el grafo con facilidad mediante funciones como zoom, filtros, búsqueda, agrupación de nodos, navegación entre relaciones y acceso rápido al contenido asociado a cada elemento."*

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
| K5 | **Cero dependencias nuevas** | `frontend/package.json` byte-idéntico al de HEAD al terminar el plan. | `git diff --stat -- "Stacky Agents/frontend/package.json"` devuelve vacío |
| K6 | **Cero regresión de compilación** | `npx tsc --noEmit` sale con 0 errores desde `Stacky Agents/frontend`. | comando literal |
| K7 | **Cero deuda visual nueva** | `uiDebtRatchet` y `motionDebtRatchet` en verde sin regenerar baseline (⇒ 0 `style={{` en `.tsx` nuevos, 0 hex y 0 tiempos literales en el `.module.css` nuevo y en las líneas nuevas del existente). | `npx vitest run src/__tests__/uiDebtRatchet.test.ts` y `.../motionDebtRatchet.test.ts` |
| K8 | **Performance no degradada** | El dibujo de labels deja de hacer `Array.findIndex` por label por frame (O(n·L)) y pasa a `Map.get` (O(L)); el tope `MAX_ANIMATED_NODES = 300` y `prefers-reduced-motion` siguen respetados sin cambios de semántica. | F0 + revisión de diff |
| K9 | **Acceso rápido al contenido** | Seleccionar un nodo nota muestra el peek con las primeras ~600 caracteres del documento **sin** cambiar de pestaña, reusando la cache de react-query del Lector (misma `queryKey`). | Verificación visual F8, paso 9 |

---

## 2. Por qué ahora / gap que cierra (con archivo:línea)

1. **La búsqueda existente no navega.** `frontend/src/components/docs/DocGraphView.tsx:97` declara `const [query, setQuery] = useState("")` y `:112` hace `filterRef.current = filterNodeIds(graph, query)`. `filterNodeIds` (`frontend/src/docs/docGraphModel.ts:127-138`) solo devuelve un `Set` de ids; el dibujo lo usa en `:176` para bajar el alpha de lo que no matchea. **No hay conteo de resultados, no hay "siguiente", no hay zoom al resultado.** Si el nodo que buscás quedó fuera del viewport, buscarlo no sirve de nada.
2. **No hay ningún filtro.** No existe ni el concepto: el componente recibe `graph` (`DocGraphView.tsx:34-38`) y lo dibuja entero. Con varias fuentes de docs (`DocsPage.tsx:295-310` ofrece un `<select>` de fuentes; el grafo del 109 mezcla TODAS) el canvas es un hairball.
3. **La agrupación existe pero es invisible.** `frontend/src/docs/forceLayout.ts:62-64` tiene `groupOf(kind, sourceId)` **privado**, usado solo para el color y para las columnas del `staticLayout` (`forceLayout.ts:203-231`). Peor: `colorForGroup` (`DocGraphView.tsx:71-75`) devuelve `pal.note` para **cualquier** grupo `note:<source>` ⇒ **todas las notas de todas las fuentes se pintan del mismo color**. La agrupación no se ve, no se puede colapsar y no se puede filtrar por ella.
4. **No hay navegación por relaciones.** El hover resalta vecinos (`DocGraphView.tsx:151-158`, `neighborsOf`) pero es efímero: al mover el mouse se pierde. No se puede fijar un nodo como raíz, ver su vecindario a profundidad 2, ni volver al nodo anterior.
5. **No hay acceso al contenido desde el grafo.** El único acceso es `onOpenNoteById` (`DocGraphView.tsx:422`), que **abandona la vista** (`DocsPage.tsx:230` hace `setDocsView("reader")`). No hay forma de espiar una nota y seguir explorando.
6. **El zoom no es descubrible.** Solo rueda (`DocGraphView.tsx:434-444`) y doble click para resetear (`:446-448`). El único botón de la toolbar es "Centrar" (`:519-526`). No hay `+`, `−`, "Ajustar a pantalla", ni teclado. Un operador que use trackpad o teclado no descubre el zoom.
7. **Hay un costo O(n) escondido por label y por frame.** `DocGraphView.tsx:266` hace `graph.nodes.findIndex((n) => n.id === c.id)` **dentro del loop de dibujo de labels**, que corre hasta 60 veces por frame (`pickVisibleLabels(candidates, 60)`, `:261`). Con 300 nodos son hasta 18.000 comparaciones por frame gratis. Se arregla con un `Map` en F0.
8. **`docsView` ya soporta tres vistas** (`DocsPage.tsx:76`: `"reader" | "coverage" | "graph"`) y la pestaña "Grafo" ya está cableada (`DocsPage.tsx:392-400`, `:410-416`). Este plan **no** agrega una pestaña nueva: mejora la que ya está.

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

- **G1 — Cero dependencias nuevas.** Está **PROHIBIDO** tocar `Stacky Agents/frontend/frontend/package.json`… (ruta correcta: `Stacky Agents/frontend/package.json`). Si una fase parece necesitar un paquete, la fase se rediseña. Gate: K5.
- **G2 — Toda la lógica en módulos `.ts` PUROS.** En este repo **no hay React Testing Library ni jsdom instalados** (gotcha estructural conocido). Por lo tanto: **prohibido** proponer tests de componente React. Cada `.tsx` es un **cascarón delgado** que solo llama helpers puros de `frontend/src/docs/*.ts`; toda la decisión (qué filtrar, qué está seleccionado, a dónde saltar) vive en esos helpers y se prueba con vitest sin DOM.
- **G3 — Read-only absoluto.** Ninguna fase escribe un documento, un ticket, una rama ni una fila de BD. El único verbo HTTP usado es `GET` (`/api/docs/graph`, `/api/docs/content`, `/api/docs/sources`).
- **G4 — Human-in-the-loop.** Nada se decide solo: los filtros, el foco, el colapso y el peek son acciones explícitas del operador. No hay auto-foco, no hay auto-filtrado "inteligente", no hay llamadas a modelos. El grafo nunca "decide" qué es importante en lugar del operador.
- **G5 — Mono-operador sin auth.** No se agrega identidad, ni RBAC, ni preferencias por usuario. El estado del explorador es de sesión (en memoria del componente); no se persiste en disco ni en BD.
- **G6 — Theme-aware.** Todo color del canvas se lee de CSS custom properties vía `readPalette` (`DocGraphView.tsx:52-69`), nunca hardcodeado. Todo color de CSS usa `var(--token)`.
- **G7 — Respetar `prefers-reduced-motion` y `MAX_ANIMATED_NODES = 300`.** Ninguna fase toca esa lógica (`forceLayout.ts:11`, `:101`; `DocGraphView.tsx:127-130`). Cualquier redibujo nuevo en modo estático debe llamar `drawRef.current()` explícitamente, igual que hoy (`DocGraphView.tsx:114`, `:119`).
- **G8 — Ratchets de deuda visual.** `frontend/src/__tests__/uiDebtRatchet.test.ts` congela **por archivo** la cantidad de `style={{` en `*.tsx` y de colores **hex** en `*.module.css`; `motionDebtRatchet.test.ts` congela tiempos literales (`120ms`, `0.2s`) y `cubic-bezier(` en `*.module.css`. **Consecuencia dura:** los `.tsx` nuevos van con **cero** `style={{`, y **toda línea CSS nueva** (tanto en el `.module.css` nuevo como en las que se agreguen a `DocGraphView.module.css`) usa `var(--token)` **sin fallback hex** y `var(--duration-*)` / `var(--ease-*)` para tiempos. Ambos ratchets deben quedar verdes **sin regenerar baseline**.
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
> - Backend, desde `Stacky Agents`: `.venv\Scripts\python.exe -m pytest backend/tests/<archivo>.py -q`

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

4. **`Stacky Agents/backend/services/harness_flags_help.py`** — agregar la entrada de ayuda llana justo después de `"STACKY_DOCS_GRAPH_ENABLED"` (línea 274):
```python
    "STACKY_DOCS_GRAPH_EXPLORER_ENABLED": PlainHelp(
        what="Agrega herramientas para explorar el mapa de documentos: filtros, buscador que salta al resultado, foco en los vecinos de una nota, colores por carpeta, zoom con botones y una vista previa del texto.",
        on_effect="Si la activás: la pestaña 'Grafo' de Docs suma barra de filtros, buscador con contador, botones de zoom, minimapa y un panel que muestra el principio del documento del nodo elegido.",
        off_effect="Si la apagás: la pestaña 'Grafo' se ve como antes, con el buscador simple y el botón Centrar.",
        example="Como pasar de una foto del mapa a un mapa con lupa, filtros y buscador.",
    ),
```
   ⚠️ **Límite duro:** cada campo de `PlainHelp` tiene un tope de **240 caracteres** verificado por `backend/tests/test_harness_flags_help.py`. Si un texto se pasa, **reescribilo más corto**; jamás toques el test. ⚠️ Ese archivo de test tiene **4 fallos preexistentes ajenos**: validá **solo** tu entrada leyendo el output; no lo cuentes como rojo tuyo.

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

7. **`Stacky Agents/deployment/harness_defaults.env`** — agregar debajo de la línea 158:
```
STACKY_DOCS_GRAPH_EXPLORER_ENABLED=true
```

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
npx tsc --noEmit
```
```
# desde "Stacky Agents"
.venv\Scripts\python.exe -m pytest backend/tests/test_docs_api.py -q
.venv\Scripts\python.exe -m pytest backend/tests/test_harness_flags.py -q
.venv\Scripts\python.exe -m pytest backend/tests/test_harness_flags_requires.py -q
.venv\Scripts\python.exe -m pytest backend/tests/test_harness_flags_help.py -q
```

**Criterio de aceptación binario.** Los 4 archivos de test frontend en verde, `npx tsc --noEmit` con 0 errores, `test_docs_api.py` / `test_harness_flags.py` / `test_harness_flags_requires.py` en verde, y en `test_harness_flags_help.py` la entrada nueva sin fallos (los 4 fallos ajenos preexistentes NO cuentan).

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

/** Opciones disponibles derivadas del grafo COMPLETO (no del filtrado): la barra
 *  no debe cambiar de forma cuando el operador filtra. */
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
3. **⚠️ INVARIANTE CRÍTICA (no romper):** el efecto de layout (línea 122) y el dibujo de labels usan **el mismo array de nodos por índice** (`state.nodes[i]` ↔ `graph.nodes[i]`, líneas 247 y 266). Por lo tanto, a partir de esta fase **todas** las referencias a `graph` **dentro del efecto de layout y del `draw()`** pasan a ser `visibleGraph`, y la lista de deps del efecto (línea 492) pasa de `[graph, selectedNodeId]` a `[visibleGraph, selectedNodeId]`. Las referencias a `graph` que quedan fuera del efecto (`kindById`, `orphanSet`) también pasan a derivarse de `visibleGraph`. **No mezclar los dos objetos.**
4. Cuando `explorerEnabled` es falsy, `visibleGraph === graph` (misma referencia) ⇒ comportamiento byte-idéntico al 111.
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
- `it("applyGraphFilters con 5000 nodos termina en menos de 200 ms")` — genera 5000 nodos y 10000 aristas; mide con `Date.now()`; sirve de guardia de complejidad (debe ser O(n+m), sin `find` anidados).

**Comandos:**
```
# desde "Stacky Agents/frontend"
npx vitest run src/docs/graphFilters.test.ts
npx vitest run src/__tests__/uiDebtRatchet.test.ts
npx vitest run src/__tests__/motionDebtRatchet.test.ts
npx tsc --noEmit
```

**Criterio de aceptación binario.** `graphFilters.test.ts` verde (18 casos), ambos ratchets verdes **sin regenerar baseline**, `tsc --noEmit` con 0 errores, y `git diff --stat -- "Stacky Agents/frontend/package.json"` vacío.

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

1. Reemplazar el estado local `query` (línea 97) por `ui.query` del reducer (`dispatch({type:"SET_QUERY", query: e.target.value})`). **Solo cuando `explorerEnabled`**; con la flag OFF se conserva el `useState` del 111 tal cual.
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
   ⚠️ Hace falta un `canvasSizeRef = useRef({w:0,h:0})` que el efecto de layout actualice en `sizeCanvas()` (líneas 135-145) y en el `ResizeObserver` (líneas 459-475). **Sin ese ref el encuadre usa 0×0 y el nodo se va del canvas.**
5. **Resaltado del activo:** en `draw()`, el nodo cuyo id es `activeMatchId` se dibuja con el mismo anillo que el hovered (líneas 223-229) usando `palette.halo` en lugar de `palette.ring`, y su label recibe `priority: 950` en el array de candidatos (línea 258), entre `isSelected` (900) y `isHover` (1000).
6. **UI de la búsqueda** (dentro de `DocGraphFilterBar` o inmediatamente al lado, misma barra):
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
- `it("con 5000 nodos la busqueda termina en menos de 150 ms")`

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

**Handlers en `DocGraphView.tsx`** (todos dentro del efecto de layout, expuestos por refs igual que `resetViewRef`):
```ts
zoomInRef.current  = () => { viewportRef.current = zoomAtCenter(viewportRef.current, ZOOM_STEP, w, h); draw(); };
zoomOutRef.current = () => { viewportRef.current = zoomAtCenter(viewportRef.current, 1 / ZOOM_STEP, w, h); draw(); };
fitRef.current     = () => {
  const st = stateRef.current; if (!st || !st.nodes.length) return;
  viewportRef.current = fitViewport(st.nodes.map(n => ({ x: n.x, y: n.y, r: n.r })), w, h, 40);
  draw();
};
// resetViewRef ya existe (línea 305) y se conserva
```
⚠️ El `scale` que muestra el componente vive en un `useState<number>` (`viewScale`) que se actualiza **solo** al terminar una interacción de zoom (rueda, botón, fit, reset), **nunca** dentro de `tick()` — si se actualizara por frame, React re-renderizaría 60 veces por segundo (regresión de performance, prohibida por G-no-degradar).

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

**Criterio de aceptación binario.** `graphViewport.test.ts` verde, `uiDebtRatchet` verde sin regenerar, `tsc --noEmit` 0 errores, y verificación visual F8 pasos 4-6.

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

1. **Entrar en foco.** El click simple sobre un nodo, en modo explorador, **cambia de significado**: pasa a ser `dispatch({type:"FOCUS_NODE", nodeId: id})` en vez de `onOpenNoteById(id)`. **Abrir la nota** pasa al **doble click** (`onDblClick`, que hoy resetea la vista — el reset se mueve al botón "Restablecer vista" de F3 y a la tecla `0`).
   ⚠️ Con `explorerEnabled === false` el comportamiento del 111 se conserva **exacto**: click abre, doble click resetea.
2. **Componer con los filtros.** El grafo que llega al layout es:
```ts
const visibleGraph = useMemo(() => {
  if (!explorerEnabled) return graph;
  const filtered = applyGraphFilters(graph, ui.filters);
  const grouped  = collapseGroups(filtered, ui.collapsedGroups);        // F5
  return ui.focusRootId ? focusSubgraph(grouped, ui.focusRootId, ui.focusDepth) : grouped;
}, [explorerEnabled, graph, ui.filters, ui.collapsedGroups, ui.focusRootId, ui.focusDepth]);
```
   **Orden fijo y obligatorio: filtros → agrupación → foco.** (Filtrar después de enfocar daría vecindarios rotos; agrupar después de enfocar generaría super-nodos parciales.)
3. **Migas + control de profundidad** (barra sobre el canvas, solo si `ui.focusRootId`):
   - `<button>← Volver</button>` → `FOCUS_BACK`, `disabled` si `focusHistory.length === 0 && !focusRootId`.
   - `<span>Foco: {labelDelRoot}</span>`
   - 3 `<button aria-pressed>` con `1 / 2 / 3` → `SET_FOCUS_DEPTH`.
   - `<button>Ver todo</button>` → `CLEAR_FOCUS`.
   - `<span>{visibleGraph.nodes.length} de {graph.nodes.length} nodos</span>`
4. **Encuadre automático al enfocar.** Un `useEffect` sobre `[ui.focusRootId, ui.focusDepth]` que llama `fitRef.current()` tras un `requestAnimationFrame` (para que el layout ya tenga posiciones). Esto **no** es autonomía: es la consecuencia visual directa de un click del operador (G4).
5. **Panel "Relaciones"** (lista lateral, dentro del peek de F6 o encima si F6 aún no está): `rankedNeighbors(visibleGraph, ui.focusRootId)` renderizado como `<ul>` de `<button>`; click en un vecino → `FOCUS_NODE` de ese vecino. Así se "camina" el grafo.

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
- `it("neighborhoodOf sobre 5000 nodos con depth 3 termina en menos de 200 ms")`

**Comandos:**
```
# desde "Stacky Agents/frontend"
npx vitest run src/docs/graphNeighborhood.test.ts
npx vitest run src/docs/graphFilters.test.ts
npx tsc --noEmit
```

**Criterio de aceptación binario.** `graphNeighborhood.test.ts` verde (19 casos), `graphFilters.test.ts` sigue verde (no hubo regresión al componer), `tsc --noEmit` 0 errores.

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

En `DocGraphView.tsx`, `Palette` gana un array:
```ts
interface Palette {
  /* ...los 9 campos existentes... */
  groups: string[];   // Plan 268 — colores por slot de grupo
}
```
y `readPalette` lo llena leyendo **CSS custom properties existentes del tema**, en este orden fijo (slot 0..5):
```ts
groups: [
  v("--color-accent",  "#4a9eff"),
  v("--color-info",    "#58a6ff"),
  v("--color-warning", "#d29922"),
  v("--color-purple",  "#a371f7"),
  v("--color-teal",    "#39c5cf"),
  v("--color-pink",    "#db61a2"),
],
```
⚠️ Si alguna de esas custom properties **no existe** en `frontend/src/styles/theme.css`, el fallback string se usa igual (`readPalette` ya hace `raw || fallback`, línea 56) — **no** hay que agregar tokens nuevos ni tocar `theme.css`. Los fallbacks van en el `.tsx`, donde el ratchet de hex **no** cuenta (solo cuenta hex en `*.module.css`).

`colorForGroup` pasa a:
```ts
function colorForGroup(group: string, pal: Palette, slots: Map<string, number>): string {
  if (group === "code") return pal.code;
  if (group === "missing") return pal.missing;
  const slot = slots.get(group);
  return slot === undefined ? pal.note : pal.groups[slot % pal.groups.length];
}
```

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

La leyenda actual (`DocGraphView.tsx:505-518`, con 3 `style={{}}` que **ya están en el baseline del ratchet**) se **conserva tal cual** cuando `explorerEnabled` es falsy. En modo explorador se renderiza una leyenda nueva dentro de `DocGraphFilterBar`, con **cero `style={{}}`**: cada swatch usa una clase `.swatchSlot0` … `.swatchSlot5` definida en `DocGraphExplorer.module.css` con `background: var(--color-accent)` etc. (**sin fallback hex**, G8). Click en un ítem de la leyenda → `TOGGLE_GROUP_COLLAPSED`, con `aria-pressed` reflejando si está colapsado.

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

**Criterio de aceptación binario.** `graphGrouping.test.ts` verde (18 casos), `forceLayout.test.ts` verde **con todos sus casos previos intactos** (la refactorización no cambió nada), `uiDebtRatchet` verde sin regenerar, `tsc --noEmit` 0 errores (prueba que no hay ciclo de imports).

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
  ⚠️ La clave debe coincidir **campo por campo** con la de `DocsPage.tsx:146` (`["docs-content", projectName ?? "active", selectedContentSourceId, selectedNode?.path]`); si difiere, se pierde el hit de cache y se hace un fetch de más.
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
- `it("previewExcerpt sobre 100 KB termina en menos de 50 ms")`
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

**Criterio de aceptación binario.** `graphPreview.test.ts` verde (17 casos), `uiDebtRatchet` verde sin regenerar, `tsc --noEmit` 0 errores, y verificación visual F8 paso 9 (el peek muestra texto real de un documento y **no** se dispara un fetch nuevo si ese documento ya se abrió en el Lector — se comprueba en la pestaña Red del navegador).

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
```

**Casos borde:** 0 puntos (`scale` = 1, rect = todo el minimapa); 1 punto (span 0 → usar `Math.max(1e-6, span)`, igual que `fitViewport`); viewport más grande que el grafo (el rect se clampea al minimapa completo); viewport totalmente fuera del bounding box (rect clampeado, `w`/`h` ≥ 0, nunca negativos).

#### F7.2 — Dibujo del minimapa

Un **segundo `<canvas>`** de 160×110 px CSS (con el mismo tratamiento de `devicePixelRatio` que el principal, `DocGraphView.tsx:139-143`), posicionado con la clase `.minimap` (esquina inferior izquierda del `.canvasBox`). Se redibuja **dentro del mismo `draw()`** del canvas principal (no un `requestAnimationFrame` propio: eso duplicaría el costo por frame). Dibuja:
- un punto de 1.5 px por nodo, con el color de su grupo (F5) y alpha 0.7,
- **sin aristas** (a esa escala son ruido),
- el rectángulo del viewport con `strokeStyle = palette.halo` y `lineWidth = 1`.
Click en el minimapa → `viewportFromMinimapClick` + `draw()`.

#### F7.3 — Nivel de detalle (LOD) por escala

En `draw()`, tres umbrales fijos y explícitos:

| Condición | Efecto |
|---|---|
| `vp.scale < 0.6` | **No** dibujar aristas cuyos dos extremos tengan `r < 6` (nodos poco conectados). Reduce el hairball a la estructura troncal. |
| `vp.scale < 0.6` | **No** dibujar labels salvo hover / seleccionado / coincidencia activa. |
| `vp.scale >= 1.4` | Se dibujan labels de todos los nodos visibles (ya existe: `zoomedIn`, línea 237). |
| `state.nodes.length > 800` | `pickVisibleLabels(candidates, 30)` en vez de 60. |

⚠️ El LOD **solo** aplica en modo explorador (`explorerEnabled`); con la flag OFF el dibujo es el del 111, byte-idéntico.

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

**Comandos:**
```
# desde "Stacky Agents/frontend"
npx vitest run src/docs/graphMinimap.test.ts
npx vitest run src/docs/graphViewport.test.ts
npx tsc --noEmit
```

**Criterio de aceptación binario.** `graphMinimap.test.ts` verde (11 casos), `graphViewport.test.ts` sigue verde, `tsc --noEmit` 0 errores, y verificación visual F8 paso 10.

**Flag.** `STACKY_DOCS_GRAPH_EXPLORER_ENABLED` — **default ON**.

**Impacto por runtime.** Ninguno en los tres. Es dibujo en un canvas del navegador. Fallback en los tres: flag OFF → sin minimapa ni LOD, como en el 111.

**Trabajo del operador: ninguno.**

---

### F8 — Verificación visual manual (la hace el operador)

**Objetivo.** Cerrar lo que este repo **no puede** automatizar.

**Por qué es una fase y no un apéndice.** En `Stacky Agents/frontend` **no están instalados** React Testing Library ni jsdom (`package.json`: devDeps = `@types/react`, `@types/react-dom`, `@vitejs/plugin-react`, `typescript`, `vite`, `vitest` — nada más). Por lo tanto **ningún test automatizado puede tocar el DOM ni el canvas**. La única verificación posible del render es humana. Esta fase existe para que quede escrito qué mirar, y para que nadie declare "listo" sin haberlo mirado.

**Preparación.**
1. Desde `Stacky Agents`, levantar el backend con `.venv\Scripts\python.exe backend/app.py` (o el launcher habitual).
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
| 9 | Click simple en un nodo nota | El grafo se reduce a ese nodo y sus vecinos; aparecen las migas `← Volver · Foco: <nota> · 1 2 3 · Ver todo`; a la derecha aparece el peek con el título y las primeras líneas del documento y la lista `Relaciones`. **Abrir la pestaña Red del navegador: si ese documento ya se abrió antes en el Lector, NO debe haber un request nuevo a `/api/docs/content`.** |
| 10 | Click en un vecino de la lista `Relaciones` | El foco salta a ese vecino, el peek cambia de documento y `← Volver` queda habilitado. |
| 11 | Click en `← Volver` | Vuelve al nodo anterior. |
| 12 | Click en `2` en el control de profundidad | Aparecen los vecinos de los vecinos; el contador de nodos sube. |
| 13 | Click en "Ver todo" | Vuelve el grafo completo (con los filtros que hubiera puestos). |
| 14 | Click en un ítem de la leyenda | Ese grupo colapsa a un único nodo grande con la etiqueta `Notas · <fuente> (k)`; las aristas hacia ese grupo se conservan; el ítem queda presionado. Click de nuevo → se expande. |
| 15 | Doble click en un nodo nota | Se abre el Lector con esa nota (la vista cambia de pestaña). |
| 16 | Click en el minimapa, en una zona lejana | El canvas se desplaza a esa zona; el rectángulo del minimapa se mueve ahí. |
| 17 | Alejar hasta ~40% | Desaparecen las aristas entre nodos poco conectados y casi todos los labels: se ve la estructura troncal, no un plato de fideos. |
| 18 | Cambiar el tema claro/oscuro de la app | Todos los colores del canvas, del minimapa y del peek acompañan el tema. Ningún color queda "pegado" del tema anterior (puede requerir volver a entrar a la pestaña: **documentarlo si pasa**, no es bloqueante). |
| 19 | Apagar `STACKY_DOCS_GRAPH_EXPLORER_ENABLED` desde el panel de flags y recargar | La pestaña Grafo vuelve **exactamente** a la del plan 111: buscador simple, leyenda, botón "Centrar"; click abre la nota; doble click resetea la vista. |
| 20 | Apagar `STACKY_DOCS_GRAPH_ENABLED` y recargar | Las tres pestañas (Lector/Cobertura/Grafo) desaparecen y la página Docs se comporta como antes del plan 109. |

**Criterio de aceptación binario.** Los 20 pasos dan el resultado esperado. Cualquier desvío se anota **en este mismo documento**, en una sección `## 10. Desvíos de la verificación visual`, con el paso, lo observado y si se corrigió.

**Flag.** N/A (se verifican los dos estados de `STACKY_DOCS_GRAPH_EXPLORER_ENABLED`).

**Impacto por runtime.** Ninguno en los tres: la verificación es del navegador contra el backend local.

**Trabajo del operador: SÍ — esta fase es explícitamente suya** (los 20 pasos, ~10 minutos). Es la única del plan que lo requiere, y es inevitable: el repo no tiene entorno de test de DOM. Ninguna otra fase le pide nada.

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

1. **F0** — Flag (7 patas) + `nodeIndexById` + fix del `findIndex` + `fitViewport`/`centerOn`/`zoomAtCenter`/`ZOOM_STEP` + `graphExplorerState.ts` + tests. **Nada visible cambia todavía.**
2. **F1** — `graphFilters.ts` + `DocGraphFilterBar.tsx` + `DocGraphExplorer.module.css` + cableado de `visibleGraph` en `DocGraphView` y de `explorerEnabled` en `DocsPage`.
3. **F2** — `graphSearch.ts` + contador `n de m` + Enter/Shift+Enter/Escape + encuadre al resultado activo (necesita `canvasSizeRef`).
4. **F3** — `DocGraphZoomControls.tsx` + atajos de teclado + `.hint` nuevo. (Reusa `fitViewport` de F0.)
5. **F4** — `graphNeighborhood.ts` + migas + profundidad 1-3 + cambio de gesto (click enfoca / doble click abre) + composición **filtros → agrupación → foco**.
6. **F5** — `graphGrouping.ts` + mover `groupOf` → `groupKeyOf` + color por grupo + leyenda accionable + colapso.
7. **F6** — `graphPreview.ts` + `DocGraphPeek.tsx` + lista `Relaciones` + layout en grid.
8. **F7** — `graphMinimap.ts` + segundo canvas + LOD por escala.
9. **F8** — Verificación visual manual del operador (20 pasos).

> **Nota de dependencia cruzada F4↔F5:** F4 escribe la composición `filtros → agrupación → foco` y por lo tanto **referencia** `collapseGroups`, que recién existe en F5. Para que F4 compile sola, en F4 se escribe la composición **sin** la línea de `collapseGroups` (solo filtros → foco) y F5 la **inserta** en el medio. Está indicado así a propósito: cada fase queda verificable sola.

### 9.3 Definición de Hecho (DoD) global

El plan 268 está HECHO cuando **todas** estas condiciones se cumplen y se pueden mostrar:

- [ ] **DoD-1.** Los 8 archivos de test frontend nombrados en el plan están en verde, corridos **uno por uno** desde `Stacky Agents/frontend`:
  `graphViewport.test.ts`, `graphExplorerState.test.ts`, `docGraphModel.test.ts`, `graphFilters.test.ts`, `graphSearch.test.ts`, `graphNeighborhood.test.ts`, `graphGrouping.test.ts`, `graphPreview.test.ts`, `graphMinimap.test.ts`, `forceLayout.test.ts`.
- [ ] **DoD-2.** `npx tsc --noEmit` desde `Stacky Agents/frontend` sale con **0 errores**.
- [ ] **DoD-3.** `npx vitest run src/__tests__/uiDebtRatchet.test.ts` y `npx vitest run src/__tests__/motionDebtRatchet.test.ts` en verde **sin haber regenerado ningún baseline**.
- [ ] **DoD-4.** `git diff --stat -- "Stacky Agents/frontend/package.json"` devuelve **vacío** (KPI K5).
- [ ] **DoD-5.** Backend en verde desde `Stacky Agents`: `test_docs_api.py`, `test_harness_flags.py`, `test_harness_flags_requires.py`; y en `test_harness_flags_help.py` la entrada nueva sin fallos (los 4 fallos ajenos preexistentes documentados como tales).
- [ ] **DoD-6.** Las **7 patas** de `STACKY_DOCS_GRAPH_EXPLORER_ENABLED` están puestas: `config.py`, `FlagSpec`, `_CATEGORY_KEYS`, `harness_flags_help.py`, `_CURATED_DEFAULTS_ON`, `_REQUIRES_MAP_FROZEN`, `harness_defaults.env`. Verificable con `grep -rn "STACKY_DOCS_GRAPH_EXPLORER_ENABLED"` → **≥ 8 hits** (7 patas + `backend/api/docs.py`).
- [ ] **DoD-7.** Los 20 pasos de F8 verificados por el operador; los desvíos anotados en `## 10` de este documento.
- [ ] **DoD-8.** Con la flag nueva en OFF, la pestaña Grafo se comporta **exactamente** como el plan 111 (F8 paso 19), y con `STACKY_DOCS_GRAPH_ENABLED` en OFF la página Docs se comporta como antes del 109 (F8 paso 20).
- [ ] **DoD-9.** Ninguna fase escribió en un documento, ticket, rama, BD ni sistema del operador: el diff completo del plan toca **solo** `frontend/src/**`, `backend/api/docs.py`, `backend/config.py`, `backend/services/harness_flags*.py`, `backend/tests/**`, `deployment/harness_defaults.env` y este documento.
- [ ] **DoD-10.** El estado de este documento se actualiza a `IMPLEMENTADO — <fecha>` con el detalle de qué fases quedaron cerradas y con qué evidencia (conteos de tests y comandos corridos), para que `supervisar-implementaciones-planes` pueda auditarlo.
