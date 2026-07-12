# Plan 124 — Comparador de BD entre ambientes (serie 122–126, parte 3/5): sección inmersiva — explorador visual de diferencias

**Estado:** PROPUESTO (v1, 2026-07-12)
**Serie:** 122 (núcleo) → 123 (motor de diff) → **124 (UI inmersiva)** → 125 (scripts de paridad + backups) → 126 (paridad de datos)
**Dependencias:** Planes 122 y 123 IMPLEMENTADOS (tab `dbcompare`, `DbComparePage.tsx`, namespace `DbCompare` en `frontend/src/api/endpoints.ts`, endpoints `/api/db-compare/compare|runs|export.md`, contrato SchemaDiff v1 del doc 123 §F1).
**Ortogonal a:** Plan 119 (rediseño DevOps; NO comparte componentes).

> Este documento está redactado para que un MODELO MENOR (Haiku, Codex CLI o GitHub
> Copilot Pro) lo implemente SIN inferir nada. Referencias a código del 122/123 citan el
> contrato congelado de esos docs. Todo componente nuevo separa la LÓGICA en helpers `.ts`
> puros con tests vitest que SÍ corren (gap preexistente: no hay `@testing-library/react`
> ni jsdom — ver nota en `frontend/src/components/devops/ConnectionHealthStrip.test.tsx:1-8`;
> por eso los `.tsx` NO llevan tests de render y TODA la lógica vive en `.ts` testeados).

---

## 1. Objetivo + KPI

Es el requisito explícito del operador: **"una sección muy inmersiva y gráfica visual …
mostrando resumen de lo encontrado detallado"**. Este plan convierte la tab "Comparador BD"
(hoy: gestión de ambientes del 122) en un explorador visual completo:

1. **Wizard de comparación**: elegir origen y destino como cards, modo fresco/cacheado,
   validación de mismo motor, y lanzar.
2. **Progreso vivo**: fases reales del run (`snapshot_source → snapshot_target → diff`,
   campo `phase` del run, doc 123 §F2) con polling.
3. **Hero de resultados**: parity score como gauge SVG animado, stat tiles por severidad
   (danger/warn/info) y por acción (added/removed/changed), totales por tipo de objeto.
4. **Mapa de diferencias (treemap SVG)**: cada tabla es un rectángulo, tamaño ∝ #columnas,
   color por estado; un vistazo muestra DÓNDE está el drift.
5. **Drill-down por objeto**: panel lateral side-by-side origen vs destino (columnas,
   PK, FKs, índices, checks, definición de vista) con cada diferencia resaltada.
6. **Filtros + búsqueda** (severidad, tipo de objeto, texto) y **historial de corridas**
   con re-apertura 1-click, marcadas `stale` cuando corresponde.
7. **Export**: botón que descarga el `.md` del run (endpoint 123 §F3) y copia del resumen.

**KPIs (binarios):**

- **KPI-1:** `computeTreemapLayout` produce rects que (a) no se solapan, (b) cubren área
  total = suma de pesos normalizada, (c) son deterministas — test F4.
- **KPI-2:** `filterDiffItems` con severidad `danger` + texto `"CLIEN"` devuelve
  exactamente los items esperados del fixture — test F5.
- **KPI-3:** `tsc --noEmit` 0 errores y TODOS los helpers `.ts` nuevos con vitest verde.

## 2. Por qué ahora / gap que cierra

- El 123 deja el diff consumible SOLO por API/JSON: ilegible para decidir. El valor
  operable ("veo el drift de un vistazo, entro al detalle, exporto el resumen") es este plan.
- El pedido del operador pone la inmersión visual como requisito de primera clase, no
  como adorno; la serie lo honra dedicándole un plan entero con presupuesto propio.
- Los planes 125/126 agregarán tabs (Scripts, Datos) DENTRO de esta estructura; definir el
  layout acá evita re-maquetar dos veces.

## 3. Principios y guardarraíles

1. **Cero dependencias nuevas de frontend:** todo SVG/CSS propio; polling con
   `fetch` + `setInterval` (sin sumar librerías de charts ni ampliar el uso de react-query).
2. **Lógica en `.ts` puros + tests reales:** cada componente visual delega cálculo a un
   helper testeado. Prohibido meter lógica de layout/filtrado dentro del `.tsx`.
3. **Paleta desde tokens:** colores de severidad/estado definidos UNA vez como variables
   CSS en `dbcompare.module.css` (`--dbc-danger`, `--dbc-warn`, `--dbc-info`,
   `--dbc-added`, `--dbc-removed`, `--dbc-changed`, `--dbc-unchanged`) partiendo de las
   variables existentes de `frontend/src/theme.css` donde las haya; los SVG las leen vía
   `var(...)`. Nada de hex sueltos en TSX.
4. **Accesible y honesto:** cada color acompañado de texto/ícono (nunca color solo);
   estados vacíos explícitos ("sin corridas aún", "elegí dos ambientes del mismo motor");
   errores del run visibles con su mensaje real.
5. **Flags:** ninguna nueva; toda la sección ya gatea con `STACKY_DB_COMPARE_ENABLED`.
6. **Runtimes:** feature de panel; impacto por runtime N/A (idéntico con los 3).
7. **Trabajo del operador:** ninguno (la sección aparece más rica con la misma flag).

## 4. Fases

### F1 — API client + tipos + polling hook

**Objetivo:** cablear los endpoints del 123 con tipos estrictos y un hook de polling con backoff fijo.

**Archivos:**
- Editar `Stacky Agents/frontend/src/api/endpoints.ts` — agregar a `DbCompare`:
  `compare(body: {source_alias: string; target_alias: string; mode: "fresh"|"cached"})`,
  `listRuns(limit?: number)`, `getRun(runId: string)`, `exportUrl(runId: string): string`
  (devuelve `/api/db-compare/runs/${runId}/export.md` para `<a download>`).
- Editar `Stacky Agents/frontend/src/components/dbcompare/dbcompareTypes.ts` — tipos del
  contrato 123 §F1/§F2 LITERALES: `Severity = "info"|"warn"|"danger"`,
  `DiffAction = "added"|"removed"|"changed"`, `ObjectType = "table"|"view"|"sequence"`,
  `DiffChange, DiffItem, DiffSummary, SchemaDiff, CompareRun, RunPhase`.
- Crear `Stacky Agents/frontend/src/components/dbcompare/useCompareRun.ts`:
```ts
export function isTerminal(status: string): boolean       // done|error
export function nextPollDelayMs(elapsedMs: number): number // <10s→1000; <60s→2000; después→5000
export function useCompareRun(runId: string | null): { run: CompareRun | null; error: string | null }
// useEffect: si runId null → limpiar; si no, fetch inmediato + setTimeout encadenado con
// nextPollDelayMs hasta isTerminal(run.status); cleanup cancela el timer (clearTimeout).
```

**Tests PRIMERO:** `frontend/src/components/dbcompare/__tests__/useCompareRun.test.ts`
- `isTerminal` (4 casos), `nextPollDelayMs` (3 fronteras exactas: 9999→1000, 59999→2000, 60000→5000).

**Comando:** `cd "Stacky Agents/frontend" && npx vitest run src/components/dbcompare/__tests__/useCompareRun.test.ts`

**Criterio binario:** vitest verde + `npx tsc --noEmit` 0 errores.

### F2 — Wizard de comparación + progreso vivo

**Objetivo:** lanzar una corrida eligiendo origen/destino como cards y ver sus fases reales.

**Archivos a crear en `Stacky Agents/frontend/src/components/dbcompare/`:**
- `CompareWizard.tsx` — dos columnas ("Origen (referencia)" / "Destino (a alinear)") con
  las cards de ambientes del 122 (alias, engine badge, host, `has_password`); click
  selecciona; reglas visuales: (a) el destino solo habilita ambientes del MISMO engine
  que el origen elegido (los demás se atenúan con `title` explicativo), (b) el mismo alias
  no puede ser ambos, (c) sin password → card con ⚠ y deshabilitada para selección.
  Selector de modo: radio `Fresco (toma snapshots ahora)` / `Cacheado (usa el último snapshot)`.
  Botón primario `Comparar ambientes` (disabled hasta selección válida) → `DbCompare.compare`
  → guarda `runId` en el estado de `DbComparePage` → muestra `<RunProgress/>`. Error 409 →
  banner "ya hay una comparación corriendo para este par".
- `wizardLogic.ts` — helpers puros:
```ts
export function selectableTargets(envs: DbEnvironment[], source: DbEnvironment | null): {alias: string; enabled: boolean; reason: string}[]
export function canLaunch(source: DbEnvironment | null, target: DbEnvironment | null): {ok: boolean; reason: string}
```
- `RunProgress.tsx` — stepper horizontal con las 4 fases (`queued → snapshot_source →
  snapshot_target → diff`) marcando la actual (pulso CSS), tiempos transcurridos, y estados
  terminales: `done` → transición al hero (F3); `error` → card roja con `run.error` literal
  y botón `Reintentar`. Run `stale: true` → card ámbar "corrida abandonada (backend
  reiniciado); relanzá".
- `runProgressLogic.ts`:
```ts
export const PHASE_ORDER: RunPhase[] = ["queued","snapshot_source","snapshot_target","diff","done"];
export function phaseState(run: CompareRun, phase: RunPhase): "pending"|"active"|"done"
```

**Tests PRIMERO:** `__tests__/wizardLogic.test.ts` (mismo engine / distinto engine / mismo alias /
sin password → 6 casos) y `__tests__/runProgressLogic.test.ts` (matriz phase×run 5 casos).

**Comando:** `cd "Stacky Agents/frontend" && npx vitest run src/components/dbcompare/__tests__/wizardLogic.test.ts src/components/dbcompare/__tests__/runProgressLogic.test.ts`

**Criterio binario:** vitest verde + tsc 0.

### F3 — Hero de resultados: gauge de paridad + stat tiles

**Objetivo:** el "resumen detallado de lo encontrado" de un vistazo, con jerarquía visual fuerte.

**Archivos a crear:**
- `svgMath.ts` — helpers puros de SVG:
```ts
export function polarToCartesian(cx: number, cy: number, r: number, angleDeg: number): {x: number; y: number}
export function arcPath(cx: number, cy: number, r: number, startDeg: number, endDeg: number): string
// arco SVG "M … A …" horario; endDeg-startDeg ≤ 359.99 (clamp interno)
export function gaugeSweep(score: number): {startDeg: 135; endDeg: number}
// gauge de 270° (135°→405°): endDeg = 135 + 270 * clamp(score,0,100)/100
export function severityCounters(diff: SchemaDiff): {severity: Severity; count: number}[]  // orden fijo danger,warn,info
export function actionCounters(diff: SchemaDiff): {action: DiffAction; count: number}[]     // added,removed,changed
```
- `SummaryHero.tsx` — layout: izquierda el **ParityGauge** (SVG 200×200: arco de fondo
  `--dbc-unchanged` + arco de valor coloreado por regla `score≥95 → verde | ≥80 → ámbar |
  <80 → rojo`, número grande centrado con animación CSS `transition: stroke-dashoffset .8s`),
  derecha dos filas de **stat tiles**: severidades (3 tiles con punto de color + label +
  count) y acciones (3 tiles), más línea de totales `N tablas · N vistas · N secuencias
  comparadas — N sin diferencias`. Tile clickeado → aplica ese filtro (F5) — el tile es un
  `<button>` con `aria-pressed`.
- Botonera del hero: `Exportar .md` (`<a href={DbCompare.exportUrl(runId)} download>`),
  `Copiar resumen` (`navigator.clipboard.writeText` del texto plano de contadores),
  `Nueva comparación` (vuelve al wizard).

**Tests PRIMERO:** `__tests__/svgMath.test.ts`
- `arcPath` golden string para (100,100,80,135,405-ε) y para semicírculo; `gaugeSweep`
  (0→135, 50→270, 100→405); `severityCounters`/`actionCounters` con fixture SchemaDiff
  (orden fijo y counts exactos).

**Comando:** `cd "Stacky Agents/frontend" && npx vitest run src/components/dbcompare/__tests__/svgMath.test.ts`

**Criterio binario:** vitest verde + tsc 0.

### F4 — Mapa de diferencias: treemap SVG de tablas

**Objetivo:** visualización espacial e inmersiva del drift: cada tabla un rect, color = estado, tamaño = #columnas.

**Archivos a crear:**
- `treemapLayout.ts` — algoritmo determinista "binary weight-split" (EXACTO, sin variantes):
```ts
export interface TreemapInput { key: string; label: string; weight: number; state: "added"|"removed"|"changed"|"unchanged" }
export interface TreemapRect extends TreemapInput { x: number; y: number; w: number; h: number }
export function computeTreemapLayout(items: TreemapInput[], width: number, height: number): TreemapRect[]
// 1) items = [...items].sort(por weight DESC, empate por key ASC); weights = max(weight,1)
// 2) recursivo partition(items, x, y, w, h):
//    - 1 item → rect (x,y,w,h)
//    - dividir la lista en prefijo A y resto B minimizando |sum(A)-sum(B)| (corte por acumulado ≥ total/2)
//      A SIEMPRE no vacío y B no vacío (si empate, A se queda el elemento del corte)
//    - si w >= h: A ocupa franja izquierda de ancho w*sum(A)/total, B la derecha
//      si w <  h: A franja superior de alto h*sum(A)/total, B la inferior
// 3) redondeo: coordenadas con 2 decimales (Math.round(v*100)/100)
export function tableTreemapInputs(diff: SchemaDiff, snapshotCounts: Record<string, number>): TreemapInput[]
// una entrada por TABLA del universo comparado: state según diff (unchanged si no hay item),
// weight = #columnas (del snapshot origen si existe ahí, si no del destino; el caller pasa
// un mapa "schema.tabla"→#columnas construido desde los snapshots del run), label = "schema.tabla".
```
  Nota de datos: `GET /runs/<id>` trae el diff pero no los snapshots; para los pesos, el
  componente pide `DbCompare.getSnapshot(source_snapshot_id)` (agregar a `endpoints.ts`;
  endpoint ya existe del 122: `GET /api/db-compare/snapshots/<id>`) y arma el mapa de
  counts en `tableTreemapInputs`. Si el fetch del snapshot falla → weight=1 uniforme
  (el mapa vacío es un fallback válido, no un error).
- `DiffTreemap.tsx` — `<svg viewBox="0 0 1000 560">` con un `<rect>` por celda
  (`fill: var(--dbc-<state>)`, borde `--dbc-bg`), `<title>` nativo con
  `schema.tabla — estado — N columnas` (tooltip), label `<text>` visible solo si
  `w>90 && h>26` (clip con `<clipPath>`), animación de entrada CSS (`opacity` stagger),
  click → abre drill-down (F5) para ese objeto; leyenda inferior con los 4 estados
  (cuadradito + texto). Encima, toggle `Mostrar solo con diferencias` (checkbox) que
  filtra `unchanged` antes del layout.

**Tests PRIMERO:** `__tests__/treemapLayout.test.ts`
- `test determinismo` (mismo input dos veces → deepEqual);
- `test sin solapes` (para el fixture de 7 items: todo par de rects no se intersecta con
  tolerancia 0.01);
- `test cubre area` (suma de áreas ≈ width*height ± 0.5);
- `test orden y corte` (fixture con pesos [8,3,2,1] → el primer split separa {8} | {3,2,1});
- `tableTreemapInputs` (fixture diff+counts → states y weights exactos; fallback mapa vacío → weight 1).

**Comando:** `cd "Stacky Agents/frontend" && npx vitest run src/components/dbcompare/__tests__/treemapLayout.test.ts`

**Criterio binario:** vitest verde (KPI-1) + tsc 0.

### F5 — Drill-down side-by-side + filtros + lista detallada

**Objetivo:** entrar a CUALQUIER objeto y ver exactamente qué difiere, campo por campo.

**Archivos a crear:**
- `filterLogic.ts`:
```ts
export interface DiffFilters { severities: Severity[]; objectTypes: ObjectType[]; text: string }
export const EMPTY_FILTERS: DiffFilters = { severities: [], objectTypes: [], text: "" }  // [] = sin filtro
export function filterDiffItems(items: DiffItem[], f: DiffFilters): DiffItem[]
// severities/objectTypes vacíos no filtran; text hace includes case-insensitive sobre `${schema}.${name}` y sobre los kinds.
export function countByState(items: DiffItem[]): Record<DiffAction, number>
```
- `sideBySide.ts` — la lógica del comparador visual de tablas:
```ts
export interface ColumnRow { name: string; source: ColumnInfo | null; target: ColumnInfo | null;
                             state: "added"|"removed"|"changed"|"unchanged"; changedFields: string[] }
export function buildColumnRows(item: DiffItem, sourceTable: TableSnapshot | null, targetTable: TableSnapshot | null): ColumnRow[]
// une columnas de ambos lados por name (orden: primero las del origen en su orden, después
// las solo-destino en su orden); state y changedFields ("type"|"nullable"|"default"|"autoincrement")
// derivados comparando campo a campo; si un lado es null (tabla added/removed) todas las filas added/removed.
export function buildSectionRows<T>(sourceList: T[], targetList: T[], keyOf: (t: T) => string): {key: string; source: T|null; target: T|null; state: string}[]
// genérico para indexes / foreign_keys / unique_constraints / check_constraints
```
- `FiltersBar.tsx` — chips toggle de severidad (con sus colores), select de tipo de objeto,
  input de búsqueda con debounce 250ms; muestra `N de M objetos` según filtro activo.
- `DiffList.tsx` — lista virtual simple (paginado en cliente de 100 items con botón
  `Mostrar 100 más`; sin librerías) de items filtrados: fila = severidad (punto color),
  `schema.nombre`, tipo, acción, kinds resumidos; click → drill-down.
- `ObjectDrilldown.tsx` — panel lateral fijo derecho (overlay, `Esc`/click-afuera cierra):
  encabezado (nombre, chips de severidad y acción), y secciones colapsables:
  **Columnas** (tabla de `ColumnRow`: célula origen y destino por campo; filas added fondo
  `--dbc-added` translúcido, removed `--dbc-removed`, changed resalta SOLO las celdas de
  `changedFields` con `--dbc-changed`), **PK**, **Foreign keys**, **Índices**, **Uniques**,
  **Checks** (vía `buildSectionRows`), **Vista** (dos `<pre>` lado a lado con
  `definition` origen/destino y aviso si `unverifiable`). Los snapshots completos se piden
  1 vez al abrir el primer drill-down (mismos fetch de F4) y se cachean en estado de página.
- Integrar en `DbComparePage.tsx`: layout final de la sección con las zonas
  `[Wizard | RunProgress] → [SummaryHero] → [FiltersBar] → [DiffTreemap | DiffList]`
  (toggle de vista `Mapa / Lista`) + `ObjectDrilldown` overlay + `RunsTimeline` (F6).

**Tests PRIMERO:** `__tests__/filterLogic.test.ts` (5 casos: vacío no filtra, severidad,
tipo, texto sobre nombre, texto sobre kind — KPI-2) y `__tests__/sideBySide.test.ts`
(fixture tabla con columna added+removed+type-changed → rows con states y changedFields
exactos; orden de filas; caso tabla added con target null).

**Comando:** `cd "Stacky Agents/frontend" && npx vitest run src/components/dbcompare/__tests__/filterLogic.test.ts src/components/dbcompare/__tests__/sideBySide.test.ts`

**Criterio binario:** vitest verde + tsc 0.

### F6 — Historial de corridas + estados vacíos + pulido

**Objetivo:** memoria de comparaciones y microdetalles que hacen "inmersiva" la sección sin deuda.

**Archivos:**
- Crear `RunsTimeline.tsx` — banda horizontal superior (o lateral en pantallas angostas)
  con las últimas corridas (`DbCompare.listRuns(20)`): card compacta = par
  `ORIGEN → DESTINO`, fecha relativa, mini-score coloreado, contadores 🔴/🟠/🔵, badge
  `stale`/`error` si aplica; click → carga ese run en el explorador (mismo estado de página,
  sin re-comparar). Corrida activa (status running) aparece primera con spinner.
- Crear `relativeTime.ts`: `export function relativeTimeEs(iso: string, nowIso: string): string`
  (reglas exactas: <60s `hace segundos`; <60m `hace N min`; <24h `hace N h`; si no `hace N d`).
- Editar `dbcompare.module.css` — definir las variables de la escala (§3.3) y los estilos
  de todos los componentes de F2–F6: transiciones de cards (150ms), pulso de fase activa,
  stagger del treemap, overlay del drill-down (sombra + slide-in 200ms), chips, tiles.
- Estados vacíos exactos: sin ambientes → CTA "Registrá tu primer ambiente" (scroll al
  panel del 122); sin corridas → "Elegí origen y destino y lanzá tu primera comparación";
  run error → card con mensaje y `Reintentar`.

**Tests PRIMERO:** `__tests__/relativeTime.test.ts` (4 fronteras exactas).

**Comando:** `cd "Stacky Agents/frontend" && npx vitest run src/components/dbcompare/__tests__/relativeTime.test.ts`

**Criterio binario:** vitest verde + tsc 0.

### F7 — No-regresión y cierre

**Comandos:**
```
cd "Stacky Agents/frontend" && npx vitest run src/components/dbcompare/
cd "Stacky Agents/frontend" && npx vitest run src/components/devops/connectionHealth.test.ts
cd "Stacky Agents/frontend" && npx tsc --noEmit
cd "Stacky Agents/backend"  && .venv\Scripts\python.exe -m pytest tests/test_plan122_dbcompare_api.py tests/test_plan123_dbcompare_api.py -q
```
**Criterio binario:** todos los vitest de `dbcompare/` verdes; vitest devops de muestra sin
fallos nuevos; tsc 0; APIs 122/123 sin regresión.

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Diff con miles de tablas tumba el render | Treemap opera sobre tablas (no columnas) + toggle "solo con diferencias" + DiffList paginada de a 100. |
| Snapshot fetch pesado para pesos del treemap | 1 solo fetch por run, cacheado en estado; fallback weight=1 si falla (test F4). |
| Sin RTL/jsdom no se testean los .tsx | Doctrina del plan: TODA la lógica en `.ts` puros testeados (layout, filtros, side-by-side, polling, tiempos); los .tsx quedan como capa declarativa mínima. |
| Polling eterno si el backend muere | `useCompareRun` corta en `stale`/`error`; backoff 1s→2s→5s acota el costo. |
| Colores ilegibles en dark theme | Variables definidas sobre `theme.css` existente + texto/ícono SIEMPRE junto al color. |

## 6. Fuera de scope

- Tab "Scripts de paridad + backups" → **Plan 125** (se monta en esta página).
- Diff/grid de DATOS → **Plan 126**.
- Comparar 3+ ambientes a la vez; diffs programados; notificaciones.
- Librerías de charts/virtualización; tests de render de componentes (gap RTL preexistente).

## 7. Glosario

- **Hero:** bloque superior de resultados con el score y los contadores clave.
- **Treemap binario:** partición recursiva del plano por mitades de peso (§F4, algoritmo cerrado).
- **Drill-down:** panel lateral con el detalle side-by-side de un objeto.
- **Stat tile:** tarjeta chica con métrica + label, clickeable como filtro.
- **stale:** corrida `running` >30 min (contrato 123 §F2) — se muestra como abandonada.

## 8. Orden de implementación

1. F1 tipos + client + polling (cimiento).
2. F2 wizard + progreso.
3. F3 hero + svgMath.
4. F4 treemap.
5. F5 drill-down + filtros + lista.
6. F6 historial + pulido CSS.
7. F7 no-regresión.

## 9. Definición de Hecho (DoD)

- [ ] Flujo completo en la tab: elegir par → ver fases → hero con score/contadores → treemap → drill-down side-by-side → export .md.
- [ ] 8 archivos de helpers `.ts` con vitest verde (comandos exactos por fase); KPI-1/2/3 demostrados.
- [ ] `tsc --noEmit` 0 errores; cero dependencias npm nuevas (diff de `package.json` vacío).
- [ ] Colores solo vía variables CSS de `dbcompare.module.css`; ningún hex en `.tsx`.
- [ ] Estados vacíos/error/stale implementados con los textos exactos de F6.
- [ ] Nada nuevo visible con `STACKY_DB_COMPARE_ENABLED` OFF.
