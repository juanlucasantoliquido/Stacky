# Plan 124 — Comparador de BD entre ambientes (serie 122–126, parte 3/5): sección inmersiva — explorador visual de diferencias

**Estado:** CRITICADO — APROBADO-CON-CAMBIOS (v1 → v2, 2026-07-14, juez `StackyArchitectaUltraEficientCode`)
**Serie:** 122 (núcleo) → 123 (motor de diff) → **124 (UI inmersiva)** → 125 (scripts de paridad + backups) → 126 (paridad de datos)
**Dependencias:** Planes 122 y 123 IMPLEMENTADOS Y MERGEADOS en la rama de trabajo donde se
ejecuta este plan (tab `dbcompare`, `DbComparePage.tsx`, namespace `DbCompare` en
`frontend/src/api/endpoints.ts`, endpoints `/api/db-compare/compare|runs|export.md`, contrato
SchemaDiff v1 del doc 123 §F1). **Ver F0 — obligatorio verificar esto ANTES de tocar código.**
**Ortogonal a:** Plan 119 (rediseño DevOps; NO comparte componentes).

**Changelog v1 → v2 (crítica adversarial):**
- **C1 (IMPORTANTE)** Falta una precondición de entorno explícita: el modelo operativo real
  de esta serie corre planes 122-126 en worktrees git AISLADOS y PARALELOS desde la misma
  base de `main`; si 122/123 aún no están mergeados en la rama donde se ejecuta 124 (escenario
  YA confirmado empíricamente el 2026-07-14: un worktree de este mismo plan verificó con
  `grep -ril "dbcompare" backend frontend/src` → CERO resultados de código, solo los docs),
  las fases F1-F6 tal como estaban escritas en v1 son inejecutables literalmente (no hay
  `DbComparePage.tsx` que editar, ni namespace `DbCompare` que extender, ni blueprint que
  consumir). v1 no daba ninguna instrucción para este caso. **Fix:** se agrega **F0 —
  Precondición de entorno**, con un fallback determinista y sin trabajo extra al operador.
- **C2 (IMPORTANTE)** F1 (`dbcompareTypes.ts`) solo enumeraba los tipos del contrato de
  diff/run (123 §F1/§F2) pero F4 (`tableTreemapInputs`) y F5 (`buildColumnRows`,
  `ObjectDrilldown`) consumen tipos del lado SNAPSHOT (122 §F3: `ColumnInfo`, `TableSnapshot`,
  etc.) que v1 nunca declaraba en ningún lado — un modelo menor tendría que inferirlos leyendo
  el doc 122, violando la regla "SIN inferir nada" y rompiendo el criterio binario `tsc 0`
  de F4/F5 apenas se referencia un tipo no declarado. **Fix:** F1 ahora enumera también los
  tipos del lado snapshot, citados 1:1 contra el contrato JSON congelado de 122 §F3.
- **C3 (IMPORTANTE)** Las variables CSS de severidad/estado (§3.3: `--dbc-danger`, etc.) solo
  se DECLARABAN en F6 (`dbcompare.module.css`), pero F3 (`ParityGauge`), F4 (`DiffTreemap`) y
  F5 (`FiltersBar`) ya las CONSUMEN antes. Implementando las fases en el orden documentado
  (§8), la UI queda sin color (variable CSS indefinida) durante 3 fases enteras — viola el
  guardrail #4 ("cada color acompañado de texto/ícono, nunca color solo") y tienta a un
  implementador a meter un hex de "por ahora", violando el DoD ("ningún hex en .tsx"). Ningún
  test automático lo detecta (los `.tsx` no tienen test de render). **Fix:** las variables
  de §3.3 se declaran en F1 (costo cero, sin dependencias); F6 solo agrega los estilos
  complementarios (transiciones, pulso, stagger, overlay).
- **C4 (IMPORTANTE)** El algoritmo de `computeTreemapLayout` (F4) afirma que el corte
  "minimiza |sum(A)-sum(B)|" pero el procedimiento descrito ("corte por acumulado ≥
  total/2", quedarse con el primer cruce) NO minimiza en general — contraejemplo verificado:
  items con pesos `[5,5,4]` (total 14, mitad 7): el primer cruce da `A={5,5}=10, B={4}=4`
  (diferencia 6), pero el corte real más balanceado es `A={5}=5, B={5,4}=9` (diferencia 4).
  Esta contradicción entre lo que el texto PROMETE y lo que el procedimiento HACE es
  exactamente el tipo de ambigüedad que produce implementaciones divergentes entre modelos.
  **Fix:** regla de corte ahora compara explícitamente los dos cortes vecinos al cruce y
  elige el más cercano a la mitad — determinista, sigue siendo O(n), y ahora sí minimiza.
- **C5 (MENOR)** `nextPollDelayMs`: los 3 casos de test (9999, 59999, 60000) no cubren el
  valor exacto `10000` (frontera del primer tramo) — un `<=` en vez de `<` no se detectaría.
  **Fix:** se agrega el caso `10000 → 2000` a la lista de fixtures de F1.
- **C6 (MENOR)** El botón `Reintentar` de `RunProgress.tsx` (F2, estado `error`) no
  especificaba qué acción dispara literalmente. **Fix:** se aclara que reinvoca
  `DbCompare.compare` con el mismo `source_alias/target_alias/mode` ya seleccionados en el
  estado del wizard, permaneciendo en la vista de progreso (no vuelve al wizard).
- **C7 (MENOR)** `computeTreemapLayout` no contemplaba explícitamente el caso `items=[]`
  (ambiente sin tablas comparadas). **Fix:** se agrega caso de test explícito (`[] → []`).
- **[ADICIÓN ARQUITECTO]** F6 agrega `runHistory.ts` con `previousRunDelta`: el hero de
  resultados (F3) ahora puede mostrar, cuando existe una corrida anterior DONE del mismo par
  (en cualquier orden de alias), el delta de parity score contra ella ("▲ +3.1 pts desde la
  corrida anterior, hace 2 días") usando datos que `RunsTimeline` (F6) YA trae con
  `listRuns(20)` — cero endpoints nuevos, cero flags, mismo costo de red. Da al operador
  conciencia de tendencia (¿el drift entre ambientes crece o se achica con el tiempo?) sin
  trabajo extra. Detalle completo al final de F6.

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

### F0 — Precondición de entorno **[FIX C1 — obligatorio, primero]**

**Objetivo:** verificar que el cimiento de 122/123 existe de verdad en ESTA rama de trabajo
antes de tocar una sola línea de F1-F6, y documentar el fallback si no.

**Chequeo (ejecutar y anotar el resultado antes de seguir):**
```
cd "Stacky Agents/frontend" && test -f src/components/dbcompare/DbComparePage.tsx && echo PRESENTE || echo AUSENTE
cd "Stacky Agents/frontend" && grep -q "export const DbCompare" src/api/endpoints.ts && echo PRESENTE || echo AUSENTE
cd "Stacky Agents/backend"  && test -f api/db_compare.py && echo PRESENTE || echo AUSENTE
```

**Caso A — los 3 dan PRESENTE:** el cimiento de 122/123 está mergeado en esta rama. Seguí
F1-F7 tal como están escritas, literal, sin cambios.

**Caso B — alguno da AUSENTE (escenario de worktrees paralelos aislados, confirmado real el
2026-07-14):** NO improvises un reemplazo de 122/123 (fuera de alcance de este plan; sería
implementar planes ajenos). Tampoco te detengas sin producir nada. Hacé esto, en este orden:
1. Implementá SOLO los archivos `.ts` puros de F1, F2 (lógica), F3, F4, F5 (lógica), F6
   (lógica) — son autocontenidos, no importan nada de `DbComparePage.tsx` ni de
   `endpoints.ts`, y tienen sus propios tests con fixtures inline. Usá el
   `dbcompareTypes.ts` de este plan como interfaz PROPIA y AISLADA (no la edición de un
   archivo ajeno que no existe) — mockeable en tests, marcada en un comentario de cabecera
   `// PENDIENTE: reconciliar con frontend/src/components/dbcompare/dbcompareTypes.ts real
   // cuando el Plan 122 se mergee a esta rama`.
2. NO crees los `.tsx` (`CompareWizard`, `RunProgress`, `SummaryHero`, `DiffTreemap`,
   `FiltersBar`, `DiffList`, `ObjectDrilldown`, `RunsTimeline`) ni edites `endpoints.ts` /
   `App.tsx` / `DbComparePage.tsx` — no existen para editar, y crearlos de cero equivaldría a
   reimplementar partes del Plan 122 (fuera de alcance; el criterio "flujo completo en la
   tab" del DoD queda explícitamente NO cumplido y se reporta así, sin maquillaje).
3. Reportá con precisión: qué `.ts` quedaron verdes con tests reales, cuáles `.tsx` NO se
   crearon y por qué, y que la integración es una tarea PENDIENTE para cuando 122/123 estén
   mergeados en esta rama (momento en el que basta con reemplazar el `dbcompareTypes.ts`
   aislado por un `import` del real y construir los `.tsx` de F2-F6 tal como estaban
   especificados — la lógica ya queda hecha y testeada).

**Criterio binario:** el chequeo de los 3 comandos queda registrado (Caso A o B) antes de
cualquier otro commit de código de este plan.

### F1 — API client + tipos + polling hook

**Objetivo:** cablear los endpoints del 123 con tipos estrictos y un hook de polling con backoff fijo.

**Archivos:**
- Editar `Stacky Agents/frontend/src/api/endpoints.ts` — agregar a `DbCompare`:
  `compare(body: {source_alias: string; target_alias: string; mode: "fresh"|"cached"})`,
  `listRuns(limit?: number)`, `getRun(runId: string)`, `exportUrl(runId: string): string`
  (devuelve `/api/db-compare/runs/${runId}/export.md` para `<a download>`). **(Solo Caso A
  de F0; en Caso B este archivo no existe — ver fallback.)**
- Editar `Stacky Agents/frontend/src/components/dbcompare/dbcompareTypes.ts` (Caso A) o
  crearlo aislado (Caso B) — tipos del contrato 123 §F1/§F2 LITERALES: `Severity =
  "info"|"warn"|"danger"`, `DiffAction = "added"|"removed"|"changed"`, `ObjectType =
  "table"|"view"|"sequence"`, `DiffChange, DiffItem, DiffSummary, SchemaDiff, CompareRun,
  RunPhase`. **[FIX C2]** Agregar TAMBIÉN los tipos del lado snapshot que F4/F5 consumen,
  espejo LITERAL del contrato JSON de `services/dbcompare_snapshot.py` (doc 122 §F3):
```ts
export interface ColumnInfo { name: string; type: string; nullable: boolean; default: string | null; autoincrement: boolean }
export interface PrimaryKeyInfo { name: string | null; columns: string[] }
export interface ForeignKeyInfo { name: string | null; columns: string[]; referred_schema: string; referred_table: string; referred_columns: string[] }
export interface IndexInfo { name: string | null; columns: string[]; unique: boolean }
export interface UniqueConstraintInfo { name: string | null; columns: string[] }
export interface CheckConstraintInfo { name: string | null; sqltext: string }
export interface TableSnapshot { columns: ColumnInfo[]; primary_key: PrimaryKeyInfo; foreign_keys: ForeignKeyInfo[]; indexes: IndexInfo[]; unique_constraints: UniqueConstraintInfo[]; check_constraints: CheckConstraintInfo[] }
export interface ViewSnapshot { definition: string | null; definition_sha256: string | null; error: string | null }
export interface SchemaSnapshot { tables: Record<string, TableSnapshot>; views: Record<string, ViewSnapshot>; sequences: string[] }
export interface DbSnapshot { version: number; id: string; alias: string; engine: string; taken_at: string; duration_ms: number; schemas: Record<string, SchemaSnapshot>; counts: { tables: number; views: number; sequences: number; columns: number }; content_hash: string }
```
- Crear `Stacky Agents/frontend/src/components/dbcompare/useCompareRun.ts`:
```ts
export function isTerminal(status: string): boolean       // done|error
export function nextPollDelayMs(elapsedMs: number): number // <10s→1000; <60s→2000; después→5000
export function useCompareRun(runId: string | null): { run: CompareRun | null; error: string | null }
// useEffect: si runId null → limpiar; si no, fetch inmediato + setTimeout encadenado con
// nextPollDelayMs hasta isTerminal(run.status); cleanup cancela el timer (clearTimeout).
```
**[FIX C3]** Editar `Stacky Agents/frontend/src/components/dbcompare/dbcompare.module.css`
(Caso A) o crearlo (Caso B) — declarar ACÁ, no en F6, las variables de la escala (§3.3):
`--dbc-danger`, `--dbc-warn`, `--dbc-info`, `--dbc-added`, `--dbc-removed`, `--dbc-changed`,
`--dbc-unchanged`, partiendo de `frontend/src/theme.css` donde haya equivalentes. F6 solo
agrega los estilos complementarios (transiciones, pulso, stagger, overlay) — las variables
ya existen desde acá para que F3/F4/F5 tengan color desde su primer commit.

**Tests PRIMERO:** `frontend/src/components/dbcompare/__tests__/useCompareRun.test.ts`
- `isTerminal` (4 casos), `nextPollDelayMs` **[FIX C5]** (4 fronteras exactas: 9999→1000,
  10000→2000, 59999→2000, 60000→5000).

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
  y botón `Reintentar`. **[FIX C6]** `Reintentar` reinvoca `DbCompare.compare` con el MISMO
  `source_alias`/`target_alias`/`mode` que ya estaban seleccionados en el estado del wizard
  (no vuelve a mostrar el wizard, permanece en `RunProgress` con el nuevo `runId`). Run
  `stale: true` → card ámbar "corrida abandonada (backend reiniciado); relanzá".
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
// 0) items=[] → devolver [] (sin dividir por cero). [FIX C7]
// 1) items = [...items].sort(por weight DESC, empate por key ASC); weights = max(weight,1)
// 2) recursivo partition(items, x, y, w, h):
//    - 1 item → rect (x,y,w,h)
//    - dividir la lista en prefijo A (no vacío) y resto B (no vacío) que MINIMIZA
//      |sum(A)-sum(B)| entre TODOS los cortes prefijo válidos. [FIX C4 — algoritmo exacto,
//      no aproximado, sigue siendo O(n)]:
//        total = sum(items); acc = 0; cut = 1  // cut mínimo = 1 (A no vacío)
//        for i in 0..items.length-1: acc += items[i].weight; if acc >= total/2: cut = i+1; break
//        // cut es el primer prefijo cuyo acumulado cruza la mitad. Si cut > 1, comparar
//        // ese cruce con el prefijo INMEDIATO ANTERIOR (cut-1, todavía no vacío) y quedarse
//        // con el que esté más cerca de total/2:
//        if cut > 1:
//          accPrev = acc - items[cut-1].weight  // acumulado de los primeros (cut-1) items
//          if |accPrev - total/2| <= |acc - total/2|: cut = cut - 1  // empate → prefijo MÁS CHICO (regla de desempate)
//        A = items[0:cut]; B = items[cut:]  // ambos siempre no vacíos por construcción
//    - si w >= h: A ocupa franja izquierda de ancho w*sum(A)/total, B la derecha
//      si w <  h: A franja superior de alto h*sum(A)/total, B la inferior
// 3) redondeo: coordenadas con 2 decimales (Math.round(v*100)/100)
// Ejemplo verificado (regresión del bug de v1): pesos [5,5,4], total=14, mitad=7.
//   cruce en i=1 (acc=10, cut=2); accPrev=5 (cut=1). |5-7|=2 <= |10-7|=3 → cut=1.
//   Resultado: A={5} (peso 5), B={5,4} (peso 9) — diferencia 4, el split real más balanceado
//   (v1 daba A={5,5}=10 vs B={4}=4, diferencia 6, MÁS desbalanceado pese a decir "minimiza").
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
- `test corte balanceado` **[FIX C4]** (fixture con pesos [5,5,4] → el split separa {5} |
  {5,4}, diferencia 4 — NO {5,5} | {4}, diferencia 6);
- `test items vacios` **[FIX C7]** (`computeTreemapLayout([], 1000, 560)` → `[]`, sin lanzar);
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
- **[FIX C3]** Editar `dbcompare.module.css` — las variables de §3.3 YA fueron declaradas en
  F1; acá solo se agregan los estilos COMPLEMENTARIOS de todos los componentes de F2–F6:
  transiciones de cards (150ms), pulso de fase activa, stagger del treemap, overlay del
  drill-down (sombra + slide-in 200ms), chips, tiles.
- Estados vacíos exactos: sin ambientes → CTA "Registrá tu primer ambiente" (scroll al
  panel del 122); sin corridas → "Elegí origen y destino y lanzá tu primera comparación";
  run error → card con mensaje y `Reintentar`.
- **[ADICIÓN ARQUITECTO]** Crear `runHistory.ts`:
```ts
export function previousRunDelta(
  current: CompareRun,
  historicalRuns: CompareRun[]
): { previousRunId: string; previousScore: number; deltaPoints: number; previousFinishedAt: string } | null
// candidatos: historicalRuns con status=="done", run_id != current.run_id, y MISMO par que
// current (frozenset({source_alias,target_alias}) igual en cualquier orden). Si no hay
// candidatos → null. Si hay → el de finished_at MÁS RECIENTE (pero anterior a current.started_at
// si ambos tienen timestamp; comparar por finished_at string ISO, orden lexicográfico UTC 'Z'
// es orden cronológico). deltaPoints = round(current.summary.parity_score -
// previous.summary.parity_score, 1).
```
  `SummaryHero.tsx` (F3) recibe `historicalRuns: CompareRun[]` como prop opcional (viene de
  `DbComparePage.tsx`, que ya hace `DbCompare.listRuns(20)` para `RunsTimeline`; se pasa la
  misma respuesta hacia abajo, cero fetch nuevo) y si `previousRunDelta(...)` no es `null`,
  renderiza debajo del número del gauge: `▲ +N.N pts desde la corrida anterior (<relativeTimeEs
  del previousFinishedAt>)` en verde si `deltaPoints > 0`, rojo si `< 0` (texto "▼"), gris
  "sin cambios" si `=== 0`. Si es `null` no se renderiza nada (ni "N/A") — guardrail #4.
  Cero endpoints nuevos, cero flags, mismo costo de red que F6 ya pagaba.

**Tests PRIMERO:** `__tests__/relativeTime.test.ts` (4 fronteras exactas) y
`__tests__/runHistory.test.ts` **[ADICIÓN ARQUITECTO]** (4 casos: sin corridas previas → `null`;
una previa del mismo par en orden inverso de alias → encontrada; varias previas → se elige la
de `finished_at` más reciente; delta negativo y positivo calculado exacto).

**Comando:** `cd "Stacky Agents/frontend" && npx vitest run src/components/dbcompare/__tests__/relativeTime.test.ts src/components/dbcompare/__tests__/runHistory.test.ts`

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

0. **F0 — precondición de entorno (obligatorio primero, decide Caso A/B).** **[FIX C1]**
1. F1 tipos (diff + snapshot) + variables CSS + client + polling (cimiento).
2. F2 wizard + progreso.
3. F3 hero + svgMath.
4. F4 treemap.
5. F5 drill-down + filtros + lista.
6. F6 historial + `runHistory.ts` + pulido CSS complementario.
7. F7 no-regresión. **(Solo Caso A de F0; en Caso B, F7 corre únicamente los comandos de los
   `.ts` efectivamente creados — ver reporte del fallback.)**

## 9. Definición de Hecho (DoD)

**Caso A de F0 (122/123 mergeados en la rama de trabajo):**
- [ ] Flujo completo en la tab: elegir par → ver fases → hero con score/contadores → treemap → drill-down side-by-side → export .md.
- [ ] 9 archivos de helpers `.ts` con vitest verde (comandos exactos por fase, incluye
      `runHistory.ts` **[ADICIÓN ARQUITECTO]**); KPI-1/2/3 demostrados.
- [ ] `tsc --noEmit` 0 errores; cero dependencias npm nuevas (diff de `package.json` vacío).
- [ ] Colores solo vía variables CSS de `dbcompare.module.css` (declaradas desde F1); ningún hex en `.tsx`.
- [ ] Estados vacíos/error/stale implementados con los textos exactos de F6.
- [ ] Nada nuevo visible con `STACKY_DB_COMPARE_ENABLED` OFF.
- [ ] Hero muestra el delta contra la corrida anterior del mismo par cuando existe.

**Caso B de F0 (122/123 ausentes en la rama de trabajo — fallback):**
- [ ] Los archivos `.ts` puros de F1-F6 que NO dependen de `DbComparePage.tsx`/`endpoints.ts`
      quedan creados con tests reales verdes (comando exacto por archivo, ejecutado y su
      salida real reportada).
- [ ] Ningún `.tsx` ni edición de `endpoints.ts`/`App.tsx`/`DbComparePage.tsx` se inventó.
- [ ] El reporte final dice explícitamente: qué quedó hecho y testeado, qué falta (la capa
      `.tsx` + integración), y que es una tarea PENDIENTE de cuando 122/123 se mergeen.
- [ ] `tsc --noEmit` 0 errores sobre el subconjunto de archivos creados (no rompe el build
      existente del resto del frontend).
