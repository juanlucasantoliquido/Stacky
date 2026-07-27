# Plan 99 — Preview sin espera: cache por spec, cancelación anti-stale y SWR honesto en el preview YAML

**Estado:** **IMPLEMENTADO** (F0 · F0.bis · F1 · F2 · F3 · F4) — 2026-07-26
**Versión:** v2 (v1: 2026-07-06 · v2: 2026-07-26 · implementado: 2026-07-26)

---

## §I — REGISTRO DE IMPLEMENTACIÓN (2026-07-26)

**Los 5 defectos están muertos.** Cero líneas de backend, cero flags nuevas, cero deps npm.

| Fase | Estado | Evidencia |
|---|---|---|
| F0 + F0.bis | IMPLEMENTADA | `frontend/src/devops/previewFetcher.ts` (nuevo) |
| F1 | IMPLEMENTADA | `api/client.ts` (`isAbortError` exportada + `api.postAbortable`), `api/endpoints.ts` (`preview(spec, signal?)`) |
| F2 | IMPLEMENTADA | 5 ediciones quirúrgicas en `PipelineYamlPreview.tsx` + 3 clases en `devops.module.css` |
| F3 | IMPLEMENTADA | fantasma borrado de `PipelineBuilderSection.tsx` (ref + `useEffect` + import de `useRef`) |
| F4 | IMPLEMENTADA (salvo smoke) | 2 huellas registradas: `preview_out_of_order_response`, `preview_structured_400_unreachable` |

**Tests (corridos de verdad, por archivo):**

| Archivo | Resultado |
|---|---|
| `src/devops/previewFetcher.test.ts` | **12 passed** |
| `src/components/devops/__tests__/devopsPreview.test.ts` | **12 passed** |
| `src/__tests__/uiDebtRatchet.test.ts` | **3 passed** (criterio obligatorio de F2) |
| `src/components/devops/__tests__/PipelineBuilderSection.test.ts` | **17 passed** |
| `src/pages/__tests__/DevOpsPage.test.ts` | **21 passed** |
| `pipelinePresets` / `pipelineStepSnippets` / `pipelineRecipes` / `ServersSection` | **11 / 20 / 11 / 4 passed** |
| `npx tsc --noEmit` | **0 errores** |

**Mediciones del DoD:** `style={{` en `PipelineYamlPreview.tsx` = **13** (bajó de 14; el
ratchet exige `count <= allowed`) · hex literales = **0** · `PipelineProfiler.profile` = **1**
· `refreshTimeoutRef` = **0 matches**.

### El perfilador del 247 sobrevivió (control de C1)

Es el riesgo principal del plan y se cumplió: `refreshPreview` **no** se reemplazó. El bloque
del perfilador se conservó textual y quedó **pineado por el caso 9** de `devopsPreview.test.ts`,
que además verifica que siga DENTRO de `refreshPreview`, después del preview exitoso, y
envuelto en su propio `catch` (su fallo no puede degradar el preview).

### Bugs del PROPIO plan hallados al construirlo (3)

1. **F0 remite a un snippet que ya no existe.** §F0 dice *"contenido igual al v1"* y *"el resto
   se conserva del v1 sin cambios"*, pero la v2 **reescribió el documento in place**: el código
   de `PreviewOutcome` / `parsePreviewError` / `createPreviewFetcher` que menciona **no está en
   ninguna parte del doc**. Criterio aplicado: implementar el módulo desde el contrato
   semántico, que sí está completo (kinds `ok`/`error`/`stale`, `PREVIEW_CACHE_LIMIT = 20`,
   `Map` como LRU, `isAbortError`), y fijarlo con los 12 tests. Lección: una v2 que reescribe
   in place no puede citar "el v1" como fuente de código.
2. **El checklist se contradice con su propia Edición 5.** El DoD exige
   `grep -c 'style={{' PipelineYamlPreview.tsx` = **14**, pero la Edición 5 convierte la fila
   del título (`style={{ display:'flex', … }}`) en `className={styles.previewHeader}`, lo que
   baja el conteo a **13**. Criterio aplicado: el invariante real del ratchet es
   `count <= allowed` ("la deuda solo puede BAJAR", `uiDebtRatchet.test.ts:4`), así que 13 es
   *mejor* que 14, no un fallo. El test lo assertea como `<= 14`.
3. **F3 dice que `tsc` cazaría el `useRef` sin usos: es falso.**
   `tsconfig.json:10` tiene `"noUnusedLocals": false`, así que un import muerto **no** produce
   error. El criterio binario propuesto no habría detectado nada. Criterio aplicado: quitar el
   import igual (es lo correcto) y **fijarlo por test** — caso 10 de `devopsPreview.test.ts`
   assertea `not.toContain('useRef')` sobre el fuente del builder.

**Pendiente:** solo los 5 puntos de verificación manual HITL de §F4 (requieren la app
corriendo). No automatizables: `@testing-library/react` y `jsdom` no están instalados.

---

**Versión previa del encabezado:** CRITICADO (v2) — VIGENTE (los 5 defectos seguían vivos)
**Veredicto del juez:** RECHAZADO (v1) → v2 corregida. 3 BLOQUEANTES, 4 IMPORTANTES, 3 MENORES.
**Autor v1:** StackyArchitectaUltraEficientCode · **Crítica v2:** StackyArchitectaUltraEficientCode (juez adversarial)

---

## VEREDICTO DE VIGENCIA: **VIGENTE** — construir

Los **5 defectos** del v1 se re-verificaron uno por uno contra el árbol del 2026-07-26 y
**los 5 siguen vivos**. Este plan NO fue superado por nada de lo que aterrizó después.

| Defecto v1 | ¿Vive hoy? | Evidencia re-anclada (2026-07-26) |
|---|---|---|
| 1. Race sin abort ni secuencia | **SÍ** | `components/devops/PipelineYamlPreview.tsx:58-83` (`refreshPreview`); `grep AbortController` en `components/devops/` + `devops/` = **0 hits** |
| 2. Blanqueo prematuro de errores | **SÍ** | `PipelineYamlPreview.tsx:61` — `setPreviewErrors([])` al **iniciar**, dentro del `try` |
| 3. Sin cache (POST por cada pausa) | **SÍ** | `PipelineYamlPreview.tsx:63` pega al backend en cada disparo; no hay memo ni `useQuery` |
| 4. Debounce fantasma en el builder | **SÍ** | `components/devops/PipelineBuilderSection.tsx:96` (ref) + `:164-179` (useEffect con callback que **solo contiene un comentario**, `:171`) |
| 5. Branch de errores 400 muerto | **SÍ** | `PipelineYamlPreview.tsx:74-79` (`'errors' in e`) vs `api/client.ts:155` — `throw new Error(\`${res.status} ${res.statusText}: ${text}\`)` ⇒ un `Error` plano **nunca** tiene la key `errors` |

---

## CHANGELOG v1 → v2

- **[C1 BLOQUEANTE] El snippet de F2 BORRABA el perfilador del Plan 247.** Corregido.
- **[C2 BLOQUEANTE] Romper el `uiDebtRatchet`.** El preview está en **14/14** inline styles,
  sin margen; el v1 agregaba 3 más. Corregido: todo por CSS module.
- **[C3 BLOQUEANTE] Todos los `archivo:línea` del v1 son falsos.** Re-anclados.
- **[C4..C7 IMPORTANTES]** reuso del precedente in-house, `isAbortError`, `useRef`, KPI.
- **[ADICIÓN ARQUITECTO]** §F0.bis — el fetcher se extrae como **riel compartido** y se prueba
  contra el mecanismo que `PipelineLintPanel` ya usa, en vez de inventar un tercero.

---

## §C — CRÍTICA ADVERSARIAL (C1..C10, rankeada)

### C1 — BLOQUEANTE — El F2 del v1 borra silenciosamente el Plan 247 F5
**Qué:** el v1 dice literalmente *"`refreshPreview` (hoy `:24-41`) se reemplaza **COMPLETO**
por:"* y da un snippet que **no incluye** la llamada al perfilador. Pero hoy
`refreshPreview` contiene, entre el `preview` y el `catch`, la integración del **Plan 247 F5**:

```
PipelineYamlPreview.tsx:65-73  →  PipelineProfiler.profile({ yaml_text: result.ado })
                                  con su propio try/catch (el fallo del perfil NUNCA
                                  degrada el preview) y setProfile/setProfileError
```

**Por qué importa:** un implementador que siga la orden literal **elimina una feature
entregada hace horas**, sin que ningún test lo note (no hay test que exija el perfilador
dentro de `refreshPreview`). Falso verde perfecto, exactamente la clase de bug que este repo
viene cazando.
**Fix:** §F2 reescrito como **cirugía sobre el desenlace**, no como reemplazo de la función.
El bloque del perfilador se conserva **textual** y se agrega un test que lo pinea.

### C2 — BLOQUEANTE — El badge y el atenuado rompen el `uiDebtRatchet`
**Qué:** el v1 agrega 3 `style={{` a `PipelineYamlPreview.tsx`:
`style={{ display: 'flex', ... }}`, `style={{ margin: 0 }}` + `style={{ fontSize: '13px' ... }}`,
y `style={{ opacity: loading ? 0.6 : 1 }}` en dos `<pre>`.
Medición real: el archivo tiene **exactamente 14** `style={{` y su baseline en
`src/__tests__/uiDebtBaseline.json` es **14**. **Margen: cero.**
`src/__tests__/uiDebtRatchet.test.ts:4` — *"la deuda solo puede BAJAR"*; `:114` falla con
`count > allowed`.
**Por qué importa:** el v1 ni menciona ese ratchet. La fase entrega con un test rojo que el
plan no anticipó, y el implementador "arregla" el baseline (que es exactamente lo prohibido).
**Fix:** §F2 usa **clases nuevas del CSS module** (`devops.module.css` ya tiene `.textMuted`
`:108` y `.yamlPre` `:155`). Cero `style={{` nuevos ⇒ el ratchet ni se entera.
Precedente en casa: `PipelineLintPanel.tsx:5` declara *"CERO style inline"*.

### C3 — BLOQUEANTE — Todos los anclajes del v1 son falsos
| El v1 dice | La realidad hoy |
|---|---|
| `PipelineYamlPreview.tsx:24-41` (`refreshPreview`) | `:58-83` |
| `PipelineYamlPreview.tsx:27` (blanqueo) | `:61` |
| `PipelineYamlPreview.tsx:33-37` (branch muerto) | `:74-79` |
| `PipelineYamlPreview.tsx:46-53` (debounce vivo) | `:85-95` |
| `PipelineYamlPreview.tsx:108-123` (render) | el archivo tiene 173 líneas; el render cambió |
| `client.ts:76-79` (throw) | `api/client.ts:155` |
| `client.ts:85-86` / `:89-99` (api) | `api/client.ts:160-175` |
| `endpoints.ts:3184-3186` (`preview`) | `api/endpoints.ts:4478-4480` |
| `PipelineBuilderSection.tsx:80-81` / `:91-106` | `:96` / `:164-179` |
| `PipelineBuilderSection.tsx:465`, `PublicationsSection.tsx:390-394`, `EnvironmentsSection.tsx:405` | las 3 secciones se mudaron a `components/devops/` |

**Fix:** tabla de arriba + **regla dura: anclar por CONTENIDO (grep del símbolo), nunca por
número de línea.**

### C4 — IMPORTANTE — Reinventa un mecanismo que la casa YA tiene
**Qué:** `components/devops/PipelineLintPanel.tsx` resuelve **el mismísimo problema** (mismo
panel, mismo tipo de request) con contador de secuencia: `:50` (`const seqRef = useRef(0)`),
`:95` (`const seq = ++seqRef.current`), `:101` (`if (cancelled || seq !== seqRef.current) return`).
Su cabecera lo declara: *"Anti-race por contador de secuencia (C6)"*.
**Por qué importa:** el guardarraíl de la casa es **reusar, no reinventar**. Dos mecanismos
anti-race distintos en el mismo panel es deuda.
**Fix:** el fetcher del F0 **adopta el mismo contrato semántico** que `PipelineLintPanel`
(secuencia monótona + descarte del superado) y lo declara explícitamente; el `AbortController`
se suma como **cinturón 2** (ahorro de red), no como mecanismo primario. §F0.bis fija un test
de paridad de semántica entre ambos.

### C5 — IMPORTANTE — Ignora `isAbortError`, que ya existe
**Qué:** el v1 chequea a mano `e instanceof DOMException && e.name === 'AbortError'`.
`api/client.ts:11` ya exporta/define `isAbortError(e: unknown): boolean`, y `request()` la usa
en su `catch` (`:149`) para **no** reportar un fallo de conexión falso.
**Por qué importa:** duplicar el predicado deja dos definiciones de "esto fue un abort" que
pueden divergir; y el v1 no notó que abortar **ya** está contemplado en el cliente HTTP.
**Fix:** F0 usa `isAbortError` (exportándola desde `client.ts` si hoy es privada — cambio
aditivo de 1 línea, sin tocar firmas).

### C6 — IMPORTANTE — La regla del `useRef` en F3 parte de una premisa muerta
**Qué:** el v1 condiciona el borrado del import a que *"el Plan 98 F4 agrega OTRO uso potencial
de `useRef` en este archivo"*. El **Plan 98 v2** (re-scopeado hoy) **no agrega ningún `useRef`**.
Medición: los **únicos** usos de `useRef` en `PipelineBuilderSection.tsx` son la ref fantasma
(`:96`) y sus 4 referencias (`:166`, `:167`, `:170`, `:175-176`).
**Fix:** la instrucción pasa a ser determinista y sin condicional: tras borrar el fantasma,
`useRef` queda **sin usos** ⇒ **se quita del import** (`:12`). El criterio binario sigue siendo
`tsc --noEmit` en 0.

### C7 — IMPORTANTE — El KPI de "3 POSTs → 2" no es medible como está escrito
**Qué:** el v1 mide "POSTs al editar y volver a un spec ya visto (A→B→A)". Pero el debounce de
800ms puede colapsar A→B→A en **un solo** disparo si el operador teclea rápido, y entonces el
KPI da 1 en ambas columnas y no prueba nada.
**Fix:** el KPI se mide **contra el fetcher, no contra el navegador**: el test 2 de F0 cuenta
llamadas a `fetchPreview` con specs A,B,A explícitos y secuenciales. La verificación manual se
degrada a "señal cualitativa", no a criterio binario.

### C8 — MENOR — `parsePreviewError` puede tragarse un `{` legítimo
`msg.indexOf('{')` corta en el primer `{` del mensaje. Si el `statusText` alguna vez contuviera
`{`, el slice arrancaría mal. Mitigación barata: intentar el parse y, ante fallo, degradar al
mensaje plano — que es **exactamente** lo que el `try/catch` ya hace. Se deja como está, anotado.

### C9 — MENOR — Sin huella de regresión
Mata 2 clases de error (respuesta fuera de orden; branch de error muerto). Se agrega registro en
`docs/sistema/error_fingerprints.json` (§F4).

### C10 — MENOR — El v1 declara "cero backend" pero toca `client.ts`
`client.ts` es frontend; la afirmación es correcta. Se mantiene, pero el DoD debe verificar
`git diff --stat` limitado a `frontend/` de verdad.

---

## 1. Objetivo + KPI (v2)

Preview YAML **instantáneo en specs ya vistos, inmune a respuestas fuera de orden y honesto
mientras recalcula**: (a) cache LRU en memoria por serialización canónica del spec,
(b) secuencia monótona (mismo contrato que `PipelineLintPanel`) + `AbortController` como
cinturón 2, (c) SWR explícito (el último YAML queda visible y atenuado; los errores **no** se
blanquean hasta el desenlace), (d) parseo real de los 400 estructurados, (e) borrado del
debounce fantasma — **y sin perder el perfilador del Plan 247 ni romper el ratchet de deuda UI**.

| Métrica | Hoy | Después | Cómo se mide (binario) |
|---|---|---|---|
| Llamadas a `fetchPreview` con specs A→B→A | 3 | 2 | test F0 caso 2 (contador de spy) |
| Respuestas fuera de orden que pisan el estado | posibles | **0 por diseño** | test F0 caso 5 (determinista, sin sleeps) |
| Errores blanqueados al **iniciar** un request | sí (`:61`) | nunca | test F2 caso 5 (posición relativa en el fuente) |
| 400 estructurados mostrados por campo | 0% (branch muerto) | 100% | test F0 caso 8 |
| Líneas de debounce fantasma | 1 ref + 16 líneas | 0 | grep negativo `refreshTimeoutRef` |
| `style={{` en `PipelineYamlPreview.tsx` | 14 | **14** (sin cambio) | `uiDebtRatchet.test.ts` verde |
| Llamada a `PipelineProfiler.profile` en el preview | 1 | **1** (preservada) | test F2 caso 9 (nuevo) |

---

## §F0 (VIVA) — Módulo puro `previewFetcher.ts`

**Archivo NUEVO:** `frontend/src/devops/previewFetcher.ts` (no existe hoy — verificado).

Contenido igual al v1 **con dos cambios**:

1. El predicado de abort usa el de la casa (C5):

```ts
import { isAbortError } from '../api/client';   // reusa client.ts:11 (exportarla si es privada)
...
        if (mySeq !== seq) return { kind: 'stale' };
        if (isAbortError(e)) return { kind: 'stale' };   // abortado por un request nuevo
        return { kind: 'error', errors: parsePreviewError(e) };
```

2. Comentario de contrato que ata el mecanismo al precedente:

```ts
// Contrato anti-race IDÉNTICO al de components/devops/PipelineLintPanel.tsx:50,95,101
// (secuencia monótona + descarte del superado). El AbortController es cinturón 2:
// ahorra red, pero la corrección NO depende de él.
```

El resto (`PreviewOutcome`, `PREVIEW_CACHE_LIMIT = 20`, `parsePreviewError`,
`createPreviewFetcher` con `Map` como LRU) se conserva del v1 sin cambios.

**Tests PRIMERO** — `frontend/src/devops/previewFetcher.test.ts`, **10 casos** (los del v1,
con el 7 adaptado a `isAbortError`). Todos deterministas: promesas controladas a mano, sin
timers falsos, sin render.

**Comandos** (cwd `Stacky Agents/frontend`; vitest SIEMPRE por archivo):

```
npx vitest run src/devops/previewFetcher.test.ts
npx tsc --noEmit
```

**Criterio binario:** 10 verdes + `tsc` 0.

---

## §F0.bis — [ADICIÓN ARQUITECTO] Test de paridad de semántica anti-race

**Problema que ataca:** C4. El panel DevOps queda con **dos** mecanismos anti-race
(`PipelineLintPanel` por `seqRef`, el preview por `previewFetcher`). Sin un ancla, dentro de
tres planes habrá un tercero y ninguno igual.

**Archivo:** 2 casos extra en `previewFetcher.test.ts`:

11. `el fetcher cumple el contrato de descarte del superado` — con A en vuelo y B resuelto
    primero, el desenlace de A es `stale` **y no toca ningún estado** (assert sobre el valor
    devuelto, no sobre un mock de React).
12. `el precedente sigue vivo` — grep del fuente de
    `components/devops/PipelineLintPanel.tsx`: contiene `seqRef` y
    `seq !== seqRef.current`. Si alguien borra ese mecanismo, este test avisa que el
    contrato compartido se rompió.

**Por qué respeta los rieles:** cero trabajo del operador, cero flags, cero deps, impacto
runtime nulo, y **reusa** en vez de inventar.

---

## §F1 (VIVA) — `api.postAbortable` + `signal` opcional en `preview`

**Sigue siendo necesario:** `api.get` ya acepta `init?: RequestInit` (`api/client.ts:161`),
pero `api.post` **no** (`:162-163`). `request()` hace spread del `RequestInit`
(`api/client.ts:137-145`), así que el `signal` viaja a `fetch` sin tocar nada más.

1. `frontend/src/api/client.ts` — **una entrada aditiva** al objeto `api` (después de
   `postWithHeaders`, hoy `:171`):

```ts
  /** POST cancelable (Plan 99): pasa un AbortSignal a fetch. Aditivo — no toca post. */
  postAbortable: <T,>(path: string, body: unknown, signal: AbortSignal) =>
    request<T>(path, { method: "POST", body: JSON.stringify(body), signal }),
```

   y **exportar `isAbortError`** si hoy es privada (C5): `export function isAbortError(...)`.

2. `frontend/src/api/endpoints.ts` — `PipelineGenerator.preview` (ancla por contenido:
   el literal `"/api/pipeline-generator/preview"`, hoy `:4478-4480`) gana un segundo
   parámetro **opcional** (backward-compatible):

```ts
  preview: (spec: object, signal?: AbortSignal) =>
    signal
      ? api.postAbortable<{ ado: string; gitlab: string }>("/api/pipeline-generator/preview", spec, signal)
      : api.post<{ ado: string; gitlab: string }>("/api/pipeline-generator/preview", spec),
```

**Tests** — casos 1-3 de `frontend/src/components/devops/__tests__/devopsPreview.test.ts`:

1. `api expone postAbortable` y `api expone isAbortError`.
2. `preview acepta signal y lo enruta a postAbortable` — el fuente de `endpoints.ts` contiene
   `signal?: AbortSignal` y `postAbortable`.
3. `las firmas existentes de api no cambiaron` — el fuente de `client.ts` conserva
   `get:`, `post:`, `put:`, `patch:`, `delete:`, `postWithHeaders:`.

**Criterio binario:** 3 verdes + `tsc` 0 + cero cambios en firmas existentes.

---

## §F2 (VIVA, REESCRITA) — Integración en `PipelineYamlPreview`: cirugía, no reemplazo

**Archivo:** `frontend/src/components/devops/PipelineYamlPreview.tsx`

> **REGLA DURA (C1): está PROHIBIDO reemplazar `refreshPreview` completa.**
> Se hacen **5 ediciones quirúrgicas**. El bloque del perfilador (Plan 247 F5, hoy `:65-73`)
> se conserva **TEXTUAL, sin mover ni una línea**.

**Edición 1 — imports.** Sumar `useRef` a los imports de react y
`import { createPreviewFetcher, type PreviewFetcher } from '../../devops/previewFetcher';`

**Edición 2 — instancia por montaje** (después de los `useState`, hoy `:51-55`):

```tsx
  // Plan 99 — fetcher con cache + anti-stale; una instancia por montaje.
  const fetcherRef = useRef<PreviewFetcher | null>(null);
  if (fetcherRef.current === null) {
    fetcherRef.current = createPreviewFetcher(
      (spec, signal) => PipelineGenerator.preview(spec, signal),
    );
  }
```

**Edición 3 — cabecera de `refreshPreview`** (ancla: `const refreshPreview = async () => {`,
hoy `:58`). Cambia la firma y **elimina el `setPreviewErrors([])` de `:61`**:

```tsx
  const refreshPreview = async (force = false) => {
    if (localErrors.length > 0) return;
    if (force) fetcherRef.current!.invalidate();
    setLoading(true);
    const outcome = await fetcherRef.current!.request(toSpecDict(spec));
    if (outcome.kind === 'stale') return;   // hay un request más nuevo: NO tocar estado ni loading
    setLoading(false);
    if (outcome.kind === 'error') {
      setPreviewErrors(outcome.errors);     // el preview viejo QUEDA visible (SWR)
      return;
    }
    const result = outcome.data;
    setPreview(result);
    setPreviewErrors([]);                   // limpiar SOLO al éxito (fix del parpadeo)
```

**Edición 4 — el perfilador se CONSERVA, indentado un nivel menos.** Inmediatamente después
del bloque anterior va, **textual**, el bloque hoy en `:65-73`:

```tsx
    // Plan 247 F5 — el perfil es aditivo: su fallo NUNCA degrada el preview. NO BORRAR.
    try {
      setProfile(await PipelineProfiler.profile({ yaml_text: result.ado }));
      setProfileError(null);
    } catch (pe: unknown) {
      setProfile(null);
      setProfileError(pe instanceof Error ? pe.message : 'perfil no disponible');
    }
  };
```

Desaparecen: el `try/catch` externo, el `finally { setLoading(false) }` y el branch muerto
`'errors' in e` (`:74-79`) — todo eso vive ahora en el fetcher.

**Edición 5 — badge y atenuado SIN inline styles (C2).**
En `frontend/src/components/devops/devops.module.css`, **3 clases nuevas**:

```css
.previewHeader { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.recalcBadge   { font-size: 13px; font-weight: normal; color: var(--text-muted); }
.yamlPreStale  { opacity: 0.6; }
```

y en el render: la fila del título usa `className={styles.previewHeader}`, el badge
`<span className={styles.recalcBadge}>Recalculando…</span>` bajo `{loading && ...}`, y cada
`<pre className={styles.yamlPre}>` pasa a
`className={`${styles.yamlPre} ${loading ? styles.yamlPreStale : ''}`}`.

**Cero `style={{` nuevos.** Usar `var(--text-muted)` (token existente, `devops.module.css:108`)
y **nunca un hex literal** — el ratchet también cuenta `hexByFile`.

**El botón manual** (ancla: `onClick={() => void refreshPreview()}`, hoy `:114`) pasa a
`onClick={() => void refreshPreview(true)}` (bypass del cache). El debounce vivo (`:85-95`)
**no se toca** (`void refreshPreview()` ⇒ `force` default `false`).

**Tests** — casos 4-9 de `devopsPreview.test.ts`:

4. `usa el fetcher` — el fuente contiene `createPreviewFetcher`.
5. `sin blanqueo prematuro` — el fuente contiene **una sola** ocurrencia de
   `setPreviewErrors([])` y está **después** de `outcome.kind === 'error'`
   (`src.indexOf("setPreviewErrors([])") > src.indexOf("outcome.kind === 'error'")`).
6. `los desenlaces stale se descartan` — el fuente contiene `outcome.kind === 'stale'` seguido
   de `return` antes de cualquier `set`.
7. `el botón manual bypassa el cache` — el fuente contiene `refreshPreview(true)`.
8. `badge por clase, no inline` — el fuente contiene `styles.recalcBadge` y
   `styles.yamlPreStale`, y **NO** contiene `opacity: loading`.
9. **`el perfilador del Plan 247 sigue vivo`** (control de C1) — el fuente contiene
   `PipelineProfiler.profile` y `setProfileError`. **Este test es el que impide el borrado
   silencioso.**

**Criterio binario:** 4-9 verdes + `tsc` 0 + **`npx vitest run src/__tests__/uiDebtRatchet.test.ts`
VERDE** (criterio nuevo, obligatorio) + los vitest preexistentes del panel verdes sin
modificarlos (`DevOpsPage.test.ts`, `ServersSection.test.ts`, `pipelinePresets.test.ts`,
`pipelineStepSnippets.test.ts`, `pipelineRecipes.test.ts`, `DevOpsCockpitRegression.test.ts`).

---

## §F3 (VIVA) — Borrado del debounce fantasma

**Archivo:** `frontend/src/components/devops/PipelineBuilderSection.tsx`

1. Borrar la ref (ancla: `const refreshTimeoutRef = useRef`, hoy `:96`).
2. Borrar el `useEffect` completo (ancla: el comentario `// Auto-refresh preview con debounce (C17)`,
   hoy `:164-179`) — el que arma `clearTimeout`/`setTimeout(..., 800)` con un callback cuyo
   cuerpo es **solo** el comentario `// El preview se refresca automáticamente en PipelineYamlPreview`
   (`:171`).
3. **Quitar `useRef` del import** (`:12`) — **sin condicional** (C6): medido, los únicos usos
   son los de los pasos 1-2.

**Tests** — casos 10-11 de `devopsPreview.test.ts`:

10. `el fantasma no existe` — el fuente de `PipelineBuilderSection.tsx` **no** contiene
    `refreshTimeoutRef`.
11. `el debounce real sigue vivo` — el fuente de `PipelineYamlPreview.tsx` contiene `setTimeout`
    y `800`.

**Criterio binario:** 10-11 verdes + `tsc --noEmit` **0 errores** (si `useRef` quedó importado
sin uso, `tsc` lo reporta) + `uiDebtRatchet` verde (el borrado **baja** deuda o la deja igual,
nunca la sube).

---

## §F4 (VIVA) — Cierre: verificación HITL + huella

**Verificación manual (con la app corriendo y `STACKY_PIPELINE_GENERATOR_ENABLED` ON):**
1. Editar el nombre de un step varias veces rápido ⇒ el YAML **nunca retrocede** a una versión
   vieja; durante el recálculo se ve "Recalculando…" con el YAML anterior atenuado.
2. Editar un campo y volver al valor anterior ⇒ el retorno **no** dispara POST (señal
   cualitativa; el criterio binario es el test F0 caso 2 — C7).
3. Click en "Actualizar preview" ⇒ **siempre** dispara POST.
4. Provocar un 400 ⇒ los errores aparecen **por campo** y **no parpadean**; el último YAML
   bueno sigue visible.
5. **La ficha de perfil del Plan 247 sigue apareciendo bajo el preview** (control de C1).

**Huella de regresión (C9):** registrar en `Stacky Agents/docs/sistema/error_fingerprints.json`
dos entradas — "respuesta de preview fuera de orden pisa el estado"
(`guard_test: previewFetcher.test.ts` caso 5) y "branch de error estructurado inalcanzable por
Error plano" (`guard_test: previewFetcher.test.ts` caso 8), ambas con `plan: 99`.

**Checklist binario:**
- [ ] `previewFetcher.test.ts` 12/12 verdes.
- [ ] `devopsPreview.test.ts` 11/11 verdes — **incluido el caso 9** (perfilador vivo).
- [ ] `npx tsc --noEmit` 0 errores.
- [ ] **`uiDebtRatchet.test.ts` VERDE**; `grep -c 'style={{' PipelineYamlPreview.tsx` = **14**.
- [ ] `grep -c 'PipelineProfiler.profile' PipelineYamlPreview.tsx` = **1**.
- [ ] `grep refreshTimeoutRef PipelineBuilderSection.tsx` = 0 matches.
- [ ] `git diff --stat` limitado a `frontend/`; cero flags nuevas; `FLAG_REGISTRY` intacto.
- [ ] Vitest preexistentes del panel verdes **sin modificarlos**.
- [ ] Los 5 puntos de verificación manual observados y anotados.
- [ ] Huella registrada.

---

## 5. Riesgos y mitigaciones (v2)

| Riesgo | Mitigación |
|---|---|
| **Borrar el perfilador del 247 sin querer** | REGLA DURA de §F2 (cirugía, no reemplazo) + test 9 que lo pinea + punto 5 de la verificación manual. |
| **Romper `uiDebtRatchet`** | Cero `style={{` nuevos; 3 clases en el CSS module con tokens (`var(--text-muted)`), nunca hex. Criterio binario explícito en F2. |
| Anclajes que vuelven a moverse (sesión paralela viva en estos archivos) | Anclar por CONTENIDO (grep del símbolo), nunca por número de línea. Commit con pathspec explícito. |
| El cache sirve YAML rancio si el backend cambia su render con el builder abierto | Cache por instancia montada (se descarta al desmontar), capado a 20, y el botón manual siempre bypassa. Los renderers son puros (`backend/services/pipeline_renderers.py`). |
| `JSON.stringify` como key: orden de propiedades | Todas las keys nacen de `toSpecDict` (mismo código, mismo orden). Peor caso teórico = cache miss inofensivo. Fijado por el test 3 de F0. |
| Vitest no renderiza React (`@testing-library/react` y `jsdom` NO instalados) | **Gap estructural declarado.** Toda la lógica con estados/tiempos vive en el módulo puro F0 (12 tests deterministas); los greps solo fijan el cableado; la interacción la cubre la verificación manual F4. |

## 6. Fuera de scope (v2)

- Renderizar el YAML en el cliente (rompería la fuente única de verdad de los renderers).
- Tocar `POST /api/pipeline-generator/preview` o los renderers backend (**cero Python**).
- Cache persistente (localStorage/IndexedDB) o compartido entre montajes.
- ETag/If-None-Match; cambiar el debounce de 800ms; tocar el gate `generator_enabled`.
- Aplicar el fetcher a otros fetches del panel (materialize, plan/apply): cada uno tiene
  semántica de mutación/HITL propia.
- **Unificar `PipelineLintPanel` al fetcher nuevo**: F0.bis solo fija el contrato compartido;
  migrar el lint es un plan futuro.

## 8. Orden de implementación (v2)

1. F0 + F0.bis — `previewFetcher.ts` + 12 tests (corazón, sin consumidores).
2. F1 — `postAbortable` + export de `isAbortError` + `signal` opcional + tests 1-3.
3. F2 — **las 5 ediciones quirúrgicas** + 3 clases CSS + tests 4-9.
   **Correr `uiDebtRatchet.test.ts` INMEDIATAMENTE después de F2**, no al final.
4. F3 — borrado del fantasma + tests 10-11 (se secuencia al final para que el chequeo del
   import de `useRef` se haga sobre el estado final del archivo).
5. F4 — verificación HITL + huella.

## 9. Definición de Hecho (v2)

- F0/F0.bis: 12 verdes + `tsc` 0.
- F1: 3 verdes + firmas de `api` intactas.
- F2: 6 verdes (4-9) + **`uiDebtRatchet` verde** + `PipelineProfiler.profile` presente 1 vez +
  contrato `PipelineYamlPreviewProps` sin cambios.
- F3: 2 verdes + `refreshTimeoutRef` = 0 matches + `tsc` 0.
- F4: 5 verificaciones manuales anotadas + huella registrada.
- **Global:** cero líneas backend; cero flags nuevas; cero deps npm; una respuesta vieja
  **jamás** pisa una más nueva (test determinista, sin sleeps); el preview y los errores nunca
  se blanquean durante un recálculo; **el perfilador del 247 sigue funcionando**.
- Impacto en los 3 runtimes (Codex CLI / Claude Code CLI / GitHub Copilot Pro): **NINGUNO** —
  componentes React + módulo TS puro; verificable por grep de `previewFetcher|postAbortable`
  fuera de `frontend/` = 0 matches.
