# Plan 99 — Preview sin espera: cache por spec, cancelación anti-stale y SWR honesto en el preview YAML

**Estado:** PROPUESTO (v1)
**Versión:** v1
**Fecha:** 2026-07-06
**Autor:** StackyArchitectaUltraEficientCode
**Serie:** infraestructura transversal del panel DevOps (87-91, 97, 98). NO pertenece a
la serie E2E 93-96 y NO depende de ninguno de esos planes pendientes ni del 98
(PROPUESTO); ninguno de ellos depende de este. Puede implementarse en paralelo.
**Frontera con el plan 93 (preflight):** el 93 detecta placeholders/runners ANTES de
disparar un pipeline; este plan arregla la MECÁNICA del preview (transporte, cache,
races) sin tocar qué se valida. **Frontera con el plan 96 (doctor):** el 96 diagnostica
fallos de RUNS ya ejecutados; este plan es UX/corrección del render local del YAML.
Cero intersección de archivos con 93/94/95/96 (todos frontend distinto o backend).
**Frontera con el plan 98:** el 98 optimiza el transporte del client-profile
(bootstrap + PATCH); este optimiza el preview YAML (`POST /api/pipeline-generator/preview`).
Ambos tocan `PipelineBuilderSection.tsx` en zonas DISJUNTAS (98: `saveDraft`/`loadDrafts`;
99: el useEffect fantasma `:92-106` y nada más) — implementables en cualquier orden.

**Dependencias (todas IMPLEMENTADAS y verificadas en el working tree 2026-07-06):**

| Pieza existente reusada | Evidencia (archivo:línea) |
|---|---|
| Preview vivo con debounce 800ms (el debounce VIVO, se conserva) | `frontend/src/components/devops/PipelineYamlPreview.tsx:46-53` |
| `refreshPreview` sin cancelación, sin cache, sin guard anti-stale | `PipelineYamlPreview.tsx:24-41` |
| Blanqueo prematuro de errores al iniciar cada request (`setPreviewErrors([])`) | `PipelineYamlPreview.tsx:27` |
| Branch de errores estructurados MUERTO de facto (`'errors' in e` nunca matchea) | `PipelineYamlPreview.tsx:33-37` vs `frontend/src/api/client.ts:76-79` (lanza `Error` plano con el JSON como TEXTO del message) |
| Debounce FANTASMA duplicado (timeout con callback vacío, cero efecto) | `PipelineBuilderSection.tsx:81` (ref) + `:91-106` (useEffect) |
| Cliente HTTP: `request(path, init)` hace spread del `RequestInit` (acepta `signal` si se lo pasan) pero `api.post` NO lo expone | `frontend/src/api/client.ts:67-81` (request), `:85-86` (post sin signal) |
| Endpoint de preview (PURO, determinista; NO se toca) | `frontend/src/api/endpoints.ts:3184-3186` (`PipelineGenerator.preview` → `POST /api/pipeline-generator/preview`) |
| Renderers backend puros spec→YAML (base del determinismo que habilita el cache) | `backend/services/pipeline_renderers.py:23` (`to_ado_yaml`), `:126` (`to_gitlab_yaml`) — "PUROS, sin I/O" (tabla del plan 97) |
| `toSpecDict` (serialización canónica del spec, base de la key de cache) | `frontend/src/devops/specBuilder.ts` (import en `PipelineYamlPreview.tsx:8`) |
| Consumidores del preview (heredan el fix sin cambios propios) | `PipelineBuilderSection.tsx:465`, `PublicationsSection.tsx:390-394`, `EnvironmentsSection.tsx:405` |
| Patrón de test vitest TS-puro sin render (estilo de la casa) | `frontend/src/pages/__tests__/ServersSection.test.ts:1-27` |
| Estilos del panel (badge/atenuado reusa clases existentes) | `frontend/src/components/devops/devops.module.css` (`textMuted`, `yamlPre`) |

**GAP VERIFICADO (defectos reales, no features):**
1. **Race condition:** `refreshPreview` (`PipelineYamlPreview.tsx:24-41`) no cancela el
   request en vuelo ni compara generaciones: si el operador edita rápido, la respuesta
   del spec VIEJO puede resolverse DESPUÉS que la del spec nuevo y pisar
   `preview`/`previewErrors` con datos rancios. No hay `AbortController` ni token de
   secuencia en todo `frontend/src/devops/` ni en `components/devops/` (grep de
   `AbortController` = 0 matches bajo esas carpetas).
2. **Parpadeo de errores:** `setPreviewErrors([])` se ejecuta AL INICIAR cada request
   (`:27`), no al desenlace: los avisos de validación visibles desaparecen ~800ms+RTT
   y reaparecen si el error persiste.
3. **Requests redundantes:** cada pausa de 800ms dispara un POST aunque el spec sea
   IDÉNTICO a uno ya renderizado (ej. editar y deshacer, o seleccionar otro bloque sin
   cambiar nada que dispare el effect por identidad de `spec`). No existe ningún cache.
4. **Código muerto:** `PipelineBuilderSection.tsx:91-106` arma un debounce completo
   (`refreshTimeoutRef`, `clearTimeout`, `setTimeout(..., 800)`) cuyo callback es SOLO
   un comentario — cero efecto observable. Duplica conceptualmente el debounce real
   que vive en `PipelineYamlPreview.tsx:46-53` y confunde a cualquier implementador.
5. **Errores estructurados rotos:** el backend responde 400 con
   `{"errors": [{field, message}]}` pero `request()` lo convierte en
   `Error("400 BAD REQUEST: {\"errors\":...}")`; el branch `'errors' in e`
   (`:33-34`) nunca matchea (un `Error` no tiene esa key) y el operador ve el JSON
   crudo en el branch genérico en vez de la lista por campo diseñada en el 87 (C12).

---

## 1. Objetivo + KPI

Hacer que el preview YAML del builder sea **instantáneo en specs ya vistos, inmune a
respuestas fuera de orden y honesto mientras recalcula**: (a) cache en memoria por
serialización canónica del spec (mismo spec ⇒ 0 requests), (b) `AbortController` +
token de secuencia (una respuesta vieja JAMÁS pisa una más nueva), (c)
stale-while-revalidate explícito (el último YAML queda visible, atenuado y con badge
"Recalculando…", y los errores NO se blanquean hasta tener desenlace), (d) parseo
correcto de los errores 400 estructurados del backend, y (e) eliminación del debounce
fantasma del builder. Todo encapsulado en un módulo puro nuevo
(`previewFetcher.ts`) que los tests vitest ejercitan sin render.

**KPI (medibles; los criterios binarios están en cada fase):**

| Métrica | Hoy | Después | Cómo se mide |
|---|---|---|---|
| POSTs de preview al editar y volver a un spec ya visto (A→B→A) | 3 | 2 (el 3º es cache hit) | test `cache hit no re-fetchea` + Network manual |
| Respuestas fuera de orden que pisan el estado | posibles (sin guard) | 0 por diseño | test determinista `anti-stale con respuestas fuera de orden` |
| Blanqueo de errores/preview durante el recálculo | errores se blanquean al iniciar cada request | nunca: solo cambian al desenlace | test del fetcher + grep de integración |
| Errores 400 estructurados mostrados por campo | 0% (branch muerto, JSON crudo) | 100% (parseados) | test `parsePreviewError extrae errors del message` |
| Código muerto de debounce en el builder | 16 líneas + 1 ref + 1 import | 0 | grep negativo `refreshTimeoutRef` |

## 2. Por qué ahora / gap que cierra (evidencia)

El preview es el feedback central del builder (planes 87/88/89/97 lo montan en 4
lugares: `PipelineBuilderSection.tsx:465`, `PublicationsSection.tsx:390`,
`EnvironmentsSection.tsx:405`, y el flujo de materialización del 88). Cada mejora de
la serie (97 sumó presets/recetas que EDITAN el spec con más frecuencia; 93/95/96
sumarán más lecturas del YAML) multiplica ediciones → más requests y más ventanas de
race. Los 5 defectos del GAP están hoy en producción con evidencia archivo:línea (ver
tabla). El fix es local, puro y chico; postergarlo encarece cada plan siguiente que
toque el builder.

## 3. Principios y guardarraíles (no negociables, verificables)

1. **DECISIÓN DE FLAG — SIN flag nueva, justificado ítem por ítem contra el criterio
   de la casa** ("los fixes de corrección pueden ir sin flag; cambios de
   comportamiento visibles van bajo flag default OFF o justificados como
   invisibles/automáticos sin degradación"):
   - *Anti-stale (abort + seq):* corrección de BUG (race condition). Ningún operador
     elegiría "quiero que un YAML viejo pise al nuevo". Sin flag.
   - *No-blanqueo de errores hasta el desenlace:* corrección de BUG de parpadeo (el
     estado visible mentía durante ~1s por request). Sin flag.
   - *Parseo de errores 400 estructurados:* corrección de BUG (restaura el
     comportamiento DISEÑADO en el 87 C12 que nunca funcionó — branch muerto). Sin flag.
   - *Cache por spec:* optimización INVISIBLE por determinismo probado — los
     renderers son puros sin I/O (`pipeline_renderers.py:23,126`); mismo spec ⇒ mismo
     YAML byte-idéntico. Doble red de seguridad sin flag: (i) el botón manual
     "Actualizar preview" SIEMPRE bypassa el cache (fuerza request), (ii) el cache
     vive en el componente montado (se descarta al desmontar; nunca persiste) y está
     capado a `PREVIEW_CACHE_LIMIT = 20` entradas LRU.
   - *Badge "Recalculando…" + atenuado:* cambio visual ADITIVO que solo AGREGA
     información honesta (hoy el YAML viejo ya queda visible durante la carga —
     `preview` no se blanquea, `PipelineYamlPreview.tsx:108` — pero sin ninguna señal
     de que está desactualizado; el badge lo hace explícito). No oculta nada, no
     quita nada, no requiere decisión del operador.
   - Una décima flag DevOps sin decisión real detrás degradaría la señal del panel de
     flags (anti-patrón: flags que nadie apagaría jamás). Precedente: el 97 dejó los
     presets/snippets SIEMPRE visibles sin flag (aditivo puro) y solo la detección
     (que lee disco vía backend) llevó flag. Este plan no agrega NINGUNA superficie
     backend ⇒ no hay endpoint nuevo que gatear.
2. **Cero trabajo del operador:** invisible/automático; sin pasos nuevos, sin config
   nueva, sin flag que activar. Backward-compatible: el contrato de
   `PipelineYamlPreviewProps` no cambia; los 3 consumidores existentes heredan el fix
   sin editarse (salvo la limpieza F3 del builder, que es borrado de código muerto).
3. **Human-in-the-loop intacto:** el preview es solo-lectura; commit y trigger siguen
   con sus confirmaciones actuales. Este plan no agrega ni quita decisiones.
4. **Mono-operador sin auth:** N/A (sin backend, sin credenciales, sin RBAC).
5. **3 runtimes (Codex CLI, Claude Code CLI, GitHub Copilot Pro):** impacto
   **NINGUNO** — solo componentes React y un módulo TS puro; ningún runner, prompt ni
   harness los consume (mismo precedente declarado en los planes 78 y 98).
   Verificable: grep de `previewFetcher` fuera de `frontend/` = 0 matches esperados.
6. **Sin backend nuevo ⇒ sin tests backend, justificado:** este plan toca CERO líneas
   de Python. `POST /api/pipeline-generator/preview` no cambia de contrato (mismo
   request, misma respuesta 200/400); los renderers conservan su suite propia
   intacta. Por eso NO hay archivos `test_plan99_*.py` ni cambios en
   `HARNESS_TEST_FILES` (`run_harness_tests.sh`/`.ps1`) — el ratchet del Plan 49
   aplica solo a tests backend.
7. **No degradar / reusar:** cero dependencias npm nuevas (`AbortController` y `Map`
   son estándar del runtime); el debounce VIVO de 800ms (`PipelineYamlPreview.tsx:46-53`)
   se conserva tal cual; las clases CSS existentes (`textMuted`) se reusan.
8. **Módulo puro primero (testeable sin render):** toda la lógica nueva (cache, seq,
   abort, parseo de errores) vive en `frontend/src/devops/previewFetcher.ts` sin
   ninguna dependencia de React; el componente solo lo consume. Los vitest de la casa
   son TS-puros sin `@testing-library/react` (gap preexistente documentado) — este
   diseño mantiene esa restricción sin perder cobertura real.

---

## F0 — Módulo puro `previewFetcher.ts` (cache LRU + secuencia + abort + parseo de errores)

**Objetivo:** encapsular en un módulo TS puro, sin React, toda la lógica de pedir el
preview con cache por spec, cancelación y guard anti-stale.
**Valor:** el corazón del plan, 100% unit-testeable de forma determinista.

**Archivo NUEVO:** `Stacky Agents/frontend/src/devops/previewFetcher.ts`

```ts
/**
 * previewFetcher.ts — Plan 99 F0.
 * Fetcher del preview YAML con cache LRU por serialización canónica del spec,
 * AbortController + token de secuencia (anti-stale) y parseo de errores 400.
 * PURO (sin React). Un fetcher por instancia montada de PipelineYamlPreview.
 */

export interface PreviewResult { ado: string; gitlab: string }
export interface PreviewFieldError { field: string; message: string }

export type PreviewOutcome =
  | { kind: 'success'; data: PreviewResult; fromCache: boolean }
  | { kind: 'error'; errors: PreviewFieldError[] }
  | { kind: 'stale' }; // respuesta superada por un request más nuevo: IGNORAR

export const PREVIEW_CACHE_LIMIT = 20;

/**
 * request() lanza Error("400 BAD REQUEST: {\"errors\":[...]}") — client.ts:76-79.
 * Extrae los errors estructurados del message si existen; si no, degrada al
 * mensaje plano (comportamiento actual del branch genérico).
 */
export function parsePreviewError(e: unknown): PreviewFieldError[] {
  const msg = e instanceof Error ? e.message : String(e);
  const jsonStart = msg.indexOf('{');
  if (jsonStart >= 0) {
    try {
      const parsed = JSON.parse(msg.slice(jsonStart));
      if (parsed && Array.isArray(parsed.errors)) {
        return parsed.errors
          .filter((x: unknown): x is PreviewFieldError =>
            !!x && typeof x === 'object' && typeof (x as PreviewFieldError).message === 'string')
          .map((x: PreviewFieldError) => ({ field: typeof x.field === 'string' ? x.field : 'general', message: x.message }));
      }
    } catch { /* no era JSON: cae al mensaje plano */ }
  }
  return [{ field: 'general', message: msg }];
}

export interface PreviewFetcher {
  /** Pide el preview del spec. Cache hit ⇒ resuelve sin red. */
  request(specDict: object): Promise<PreviewOutcome>;
  /** Vacía el cache (lo usa el botón manual "Actualizar preview" para bypass). */
  invalidate(): void;
  /** Cantidad de entradas cacheadas (solo para tests/diagnóstico). */
  cacheSize(): number;
}

export function createPreviewFetcher(
  fetchPreview: (spec: object, signal: AbortSignal) => Promise<PreviewResult>,
  cacheLimit: number = PREVIEW_CACHE_LIMIT,
): PreviewFetcher {
  const cache = new Map<string, PreviewResult>(); // Map preserva orden de inserción ⇒ LRU barato
  let seq = 0;
  let controller: AbortController | null = null;

  return {
    async request(specDict: object): Promise<PreviewOutcome> {
      // Key de cache: JSON.stringify del dict canónico. Es determinista porque
      // toSpecDict construye SIEMPRE las propiedades en el mismo orden de
      // inserción (mismo código ⇒ mismo orden de keys ⇒ mismo string).
      const key = JSON.stringify(specDict);
      const hit = cache.get(key);
      if (hit !== undefined) {
        cache.delete(key); cache.set(key, hit); // refrescar posición LRU
        return { kind: 'success', data: hit, fromCache: true };
      }
      seq += 1;
      const mySeq = seq;
      controller?.abort();                    // cancela el request en vuelo (si hay)
      controller = new AbortController();
      try {
        const data = await fetchPreview(specDict, controller.signal);
        if (mySeq !== seq) return { kind: 'stale' };  // guard: llegó tarde
        cache.set(key, data);
        if (cache.size > cacheLimit) {
          cache.delete(cache.keys().next().value as string); // expulsa el más viejo
        }
        return { kind: 'success', data, fromCache: false };
      } catch (e: unknown) {
        if (mySeq !== seq) return { kind: 'stale' };  // superado: da igual qué falló
        if (e instanceof DOMException && e.name === 'AbortError') {
          return { kind: 'stale' };                   // abortado por un request nuevo
        }
        return { kind: 'error', errors: parsePreviewError(e) };
      }
    },
    invalidate() { cache.clear(); },
    cacheSize() { return cache.size; },
  };
}
```

**Mecanismo anti-stale EXACTO (doble cinturón, fijado por contrato):**
- `AbortController`: al entrar un request nuevo, `controller.abort()` corta la red del
  anterior (si el transporte lo respeta).
- Token de secuencia `mySeq !== seq`: aunque el abort no llegue a tiempo (respuesta ya
  en el microtask queue), el desenlace de un request superado devuelve `stale` y el
  caller lo IGNORA. Cubre también el caso "B rápido termina antes que A lento".

**Casos borde fijados:** cache hit no toca `seq` ni aborta nada (no interrumpe un
request en vuelo de OTRO spec: si llega tarde, el guard seq ya lo maneja); `value`
cacheado se reordena al final (LRU); errores NUNCA se cachean (solo éxitos); un
`AbortError` jamás se reporta como error al operador (es `stale`).

**Tests PRIMERO (TDD)** — archivo nuevo
`Stacky Agents/frontend/src/devops/previewFetcher.test.ts`, 10 casos (unit puro,
promesas controladas a mano — sin timers falsos ni render):

1. `miss llama fetchPreview una vez y devuelve success fromCache=false`.
2. `hit del mismo spec no vuelve a llamar fetchPreview y devuelve fromCache=true`
   — dos `request()` con el mismo dict; spy con contador.
3. `keys estables: dos specs estructuralmente iguales de toSpecDict comparten cache`
   — `toSpecDict(starterSpec())` dos veces (import real de `specBuilder`), un solo
   fetch.
4. `LRU expulsa el más viejo al superar el límite` — `createPreviewFetcher(fn, 2)`,
   pedir A, B, C ⇒ `cacheSize() === 2` y pedir A re-fetchea (contador sube).
5. `anti-stale con respuestas fuera de orden` — request A con promesa pendiente;
   request B resuelve primero (success); luego resolver A ⇒ el `await` de A devuelve
   `{kind:'stale'}` y B fue `success` (el estado del caller nunca vería A).
6. `abort: el signal del request anterior queda aborted al entrar uno nuevo` —
   capturar `signal` del primer fetch; tras el segundo `request()`,
   `signal.aborted === true`.
7. `AbortError se mapea a stale, no a error` — fetch rechaza con
   `new DOMException('x','AbortError')` siendo aún el request vigente ⇒ `stale`.
8. `error 400 estructurado se parsea por campo` — fetch rechaza con
   `new Error('400 BAD REQUEST: {"errors":[{"field":"stages","message":"vacio"}]}')`
   ⇒ `{kind:'error', errors:[{field:'stages', message:'vacio'}]}`.
9. `error no-JSON degrada a general` — `new Error('500 INTERNAL SERVER ERROR: boom')`
   ⇒ `errors === [{field:'general', message:'500 INTERNAL SERVER ERROR: boom'}]`.
10. `invalidate vacía el cache y fuerza re-fetch` — hit confirmado, `invalidate()`,
    mismo spec ⇒ fetch llamado de nuevo y `cacheSize()` correcto.

**Comandos (cwd `Stacky Agents/frontend`; vitest SIEMPRE por archivo):**

```
npx vitest run src/devops/previewFetcher.test.ts
npx tsc --noEmit
```

**Criterio de aceptación (binario):** 10 tests verdes + `tsc --noEmit` 0 errores.
**Flag:** ninguna (ver §3.1 — módulo puro sin superficie de comportamiento hasta F2).
**Impacto por runtime:** NINGUNO (módulo TS puro). Fallback: N/A.
**Trabajo del operador:** ninguno.

---

## F1 — `api.postAbortable` (aditivo) + `PipelineGenerator.preview` con `signal` opcional

**Objetivo:** exponer `AbortSignal` en el cliente HTTP SIN tocar ninguna firma
existente, y enhebrarlo al endpoint de preview.
**Valor:** habilita la cancelación real de red (el cinturón 1 del anti-stale).

**Archivos a editar (exactos):**

1. `Stacky Agents/frontend/src/api/client.ts` — agregar UNA entrada al objeto `api`
   (después de `postWithHeaders`, `client.ts:93-99`); `request` ya hace spread del
   `RequestInit` (`client.ts:67-75`), así que `signal` viaja a `fetch` sin tocarlo:

```ts
  /** POST cancelable (Plan 99): pasa un AbortSignal a fetch. Aditivo — no toca post. */
  postAbortable: <T,>(path: string, body: unknown, signal: AbortSignal) =>
    request<T>(path, { method: "POST", body: JSON.stringify(body), signal }),
```

2. `Stacky Agents/frontend/src/api/endpoints.ts` — `PipelineGenerator.preview`
   (`endpoints.ts:3184-3186`) gana un segundo parámetro OPCIONAL (backward-compatible:
   los llamados existentes sin `signal` siguen compilando y comportándose igual):

```ts
  /** POST /api/pipeline-generator/preview — spec → {ado, gitlab} (200) o {errors} (400).
   *  signal (Plan 99): cancela el request en vuelo (AbortController del previewFetcher). */
  preview: (spec: object, signal?: AbortSignal) =>
    signal
      ? api.postAbortable<{ ado: string; gitlab: string }>("/api/pipeline-generator/preview", spec, signal)
      : api.post<{ ado: string; gitlab: string }>("/api/pipeline-generator/preview", spec),
```

**Tests PRIMERO (TDD)** — casos 1-3 del archivo nuevo
`Stacky Agents/frontend/src/pages/__tests__/DevOpsPreview.test.ts` (TS-puro estilo
`ServersSection.test.ts`):

1. `api expone postAbortable` — `import('../../api/client')` ⇒
   `typeof mod.api.postAbortable === 'function'`.
2. `preview acepta signal y lo enruta a postAbortable` — grep del fuente de
   `endpoints.ts`: contiene `signal?: AbortSignal` y `postAbortable` dentro del bloque
   de `PipelineGenerator`.
3. `las firmas existentes de api no cambiaron` — grep del fuente de `client.ts`:
   `get:`, `post:`, `put:`, `patch:`, `delete:`, `postWithHeaders:` siguen presentes
   (aditividad).

**Comandos:**

```
npx vitest run src/pages/__tests__/DevOpsPreview.test.ts
npx tsc --noEmit
```

**Criterio de aceptación (binario):** 3 tests verdes + `tsc --noEmit` 0 errores + cero
cambios en las firmas existentes de `api` (test 3).
**Flag:** ninguna (método aditivo sin consumidores hasta F2).
**Impacto por runtime:** NINGUNO. Fallback: `preview(spec)` sin signal se comporta
byte-idéntico a hoy.
**Trabajo del operador:** ninguno.

---

## F2 — Integración en `PipelineYamlPreview`: SWR honesto + badge + bypass manual

**Objetivo:** el componente consume el fetcher: nunca blanquea el YAML ni los errores
durante el recálculo, marca visualmente el estado "recalculando", ignora desenlaces
`stale`, y el botón manual bypassa el cache.
**Valor:** el operador ve siempre un preview coherente; ediciones repetidas se sienten
instantáneas.

**Archivo a editar:** `Stacky Agents/frontend/src/components/devops/PipelineYamlPreview.tsx`

Cambios EXACTOS (el resto del componente — gate `FlagGateBanner` `:56-65`, debounce
vivo `:46-53`, render de errores locales — queda INTACTO):

1. Imports nuevos: `useRef` (de react), `createPreviewFetcher, type PreviewFetcher`
   (de `'../../devops/previewFetcher'`), `PipelineGenerator` ya está importado.

2. Instancia por montaje (lazy ref, después de los `useState` `:19-21`):

```tsx
  // Plan 99 — fetcher con cache + anti-stale; una instancia por montaje.
  const fetcherRef = useRef<PreviewFetcher | null>(null);
  if (fetcherRef.current === null) {
    fetcherRef.current = createPreviewFetcher(
      (spec, signal) => PipelineGenerator.preview(spec, signal),
    );
  }
```

3. `refreshPreview` (hoy `:24-41`) se reemplaza COMPLETO por:

```tsx
  // Plan 99 — SWR honesto: preview y errores SOLO cambian al desenlace del request
  // vigente; los desenlaces 'stale' se descartan. force=true bypassa el cache
  // (botón manual "Actualizar preview").
  const refreshPreview = async (force = false) => {
    if (localErrors.length > 0) return; // sin cambios: no hay preview con errores locales
    if (force) fetcherRef.current!.invalidate();
    setLoading(true);
    const outcome = await fetcherRef.current!.request(toSpecDict(spec));
    if (outcome.kind === 'stale') return; // NUNCA tocar estado ni loading: hay un request más nuevo en curso
    setLoading(false);
    if (outcome.kind === 'success') {
      setPreview(outcome.data);
      setPreviewErrors([]);              // limpiar SOLO al éxito (fix parpadeo)
    } else {
      setPreviewErrors(outcome.errors);  // el preview viejo QUEDA visible (SWR)
    }
  };
```

   Notas de letra: desaparecen el `try/catch` inline, el `setPreviewErrors([])`
   inicial (`:27`) y el branch muerto `'errors' in e` (`:33-37`) — todo eso vive ahora
   en el fetcher. `refreshPreview` ya no lanza jamás (el fetcher devuelve outcomes).

4. El debounce vivo (`:46-53`) queda igual (`void refreshPreview()` — `force` default
   `false`). El botón manual (`:72-78`) pasa a `onClick={() => void refreshPreview(true)}`
   (bypass del cache; texto y disabled sin cambios).

5. Badge + atenuado durante el recálculo — en el render del preview (`:108-123`),
   envolver los `<pre>` con opacidad condicional y agregar el badge junto al título:

```tsx
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
        <h3 style={{ margin: 0 }}>
          Preview YAML{' '}
          {loading && <span className={styles.textMuted} style={{ fontSize: '13px', fontWeight: 'normal' }}>Recalculando…</span>}
        </h3>
        {/* botón existente sin cambios de layout */}
```

   y en ambos `<pre className={styles.yamlPre}>` (`:112` y `:118`):
   `style={{ opacity: loading ? 0.6 : 1 }}`.

**Casos borde fijados:** un desenlace `stale` NO apaga `loading` (el request vigente
lo apagará al terminar — apagar antes mentiría "listo" con un request en curso);
cache hit apaga `loading` en el mismo tick (flash imperceptible, aceptado); con
`localErrors` el early-return actual se conserva idéntico; el gate de flag
`generator_enabled` (`:56-65`) NO cambia (sigue siendo la flag del plan 73/87 que
gobierna el preview — este plan no la toca).

**Tests PRIMERO (TDD)** — casos 4-8 de `DevOpsPreview.test.ts` (greps de integración,
mismo estilo que la casa):

4. `PipelineYamlPreview usa el fetcher` — su fuente contiene `createPreviewFetcher` y
   `previewFetcher`.
5. `sin blanqueo prematuro de errores` — su fuente NO contiene la secuencia
   `setPreviewErrors([]);` seguida en la MISMA función de un `await` del fetch (grep
   exacto: el fuente contiene UNA sola ocurrencia de `setPreviewErrors([])` y está
   DESPUÉS de `outcome.kind === 'success'` — verificar con
   `src.indexOf("setPreviewErrors([])") > src.indexOf("outcome.kind === 'success'")`).
6. `los desenlaces stale se descartan` — su fuente contiene
   `outcome.kind === 'stale'` con `return` antes de todo `set*`.
7. `el botón manual bypassa el cache` — su fuente contiene `refreshPreview(true)` y
   el fetcher expone `invalidate` (grep en `previewFetcher.ts`).
8. `badge de recálculo presente` — su fuente contiene `Recalculando…` y
   `opacity: loading ? 0.6 : 1`.

**Comandos:**

```
npx vitest run src/pages/__tests__/DevOpsPreview.test.ts
npx tsc --noEmit
```

**Criterio de aceptación (binario):** tests 4-8 verdes + `tsc --noEmit` 0 errores +
los tests vitest preexistentes del panel (`DevOpsPage.test.ts`,
`ServersSection.test.ts`, suites del 97: `pipelinePresets.test.ts`,
`pipelineStepSnippets.test.ts`, `pipelineRecipes.test.ts`) verdes sin modificarlos.
**Flag:** ninguna (§3.1: corrección de defectos + optimización invisible + badge
aditivo; bypass manual garantizado).
**Impacto por runtime:** NINGUNO. Fallback: N/A (no hay modo degradado — el
comportamiento correcto reemplaza al defectuoso).
**Trabajo del operador:** ninguno.

---

## F3 — Limpieza del debounce fantasma en `PipelineBuilderSection`

**Objetivo:** borrar el useEffect muerto y su ref (cero efecto observable hoy).
**Valor:** elimina 16 líneas que duplican conceptualmente el debounce real y confunden
a cualquier implementador futuro (un modelo menor podría "arreglar" el fantasma en vez
del real).

**Archivo a editar:** `Stacky Agents/frontend/src/components/devops/PipelineBuilderSection.tsx`

Cambios EXACTOS (borrado puro, cero lógica nueva):

1. Eliminar la declaración de la ref (`:80-81`):

```tsx
  // Debounce para auto-refresh preview (C17)
  const refreshTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
```

2. Eliminar el useEffect completo (`:91-106`) — el bloque que arma
   `clearTimeout`/`setTimeout(..., 800)` con un callback que SOLO contiene el
   comentario "El preview se refresca automáticamente en PipelineYamlPreview".

3. En el import de React (`:12`), quitar `useRef` SOLO si queda sin usos en el
   archivo. OJO secuenciamiento: hoy `useRef` tiene un único uso (la ref borrada —
   verificado en el working tree 2026-07-06), pero el Plan 98 F4 (PROPUESTO) agrega
   OTRO uso potencial en este archivo. Regla determinista para el implementador:
   después de los borrados 1-2, correr
   `grep -n "useRef" PipelineBuilderSection.tsx`; si la única ocurrencia restante es
   la del import, quitarlo del import; si hay más ocurrencias, dejarlo.

**Tests PRIMERO (TDD)** — casos 9-10 de `DevOpsPreview.test.ts`:

9. `el debounce fantasma no existe` — el fuente de `PipelineBuilderSection.tsx` NO
   contiene `refreshTimeoutRef`.
10. `el debounce real sigue vivo donde corresponde` — el fuente de
    `PipelineYamlPreview.tsx` contiene `setTimeout` y `800` (el debounce vivo NO se
    borró por accidente).

**Comandos:**

```
npx vitest run src/pages/__tests__/DevOpsPreview.test.ts
npx tsc --noEmit
```

**Criterio de aceptación (binario):** tests 9-10 verdes + `tsc --noEmit` 0 errores
(si `useRef` quedó importado sin uso, `tsc` con `noUnusedLocals` lo reporta — el
criterio binario es `tsc` en 0 errores con la config del repo tal como está).
**Flag:** ninguna (borrado de código muerto).
**Impacto por runtime:** NINGUNO. Fallback: N/A.
**Trabajo del operador:** ninguno.

---

## F4 — Cierre: verificación manual HITL + checklist binario

**Objetivo:** verificar el comportamiento end-to-end en la app real y dejar el
checklist auditable.

**Sin cambios de archivos** (fase de verificación).

**Verificación manual (HITL, 5 minutos, con la app corriendo y
`STACKY_PIPELINE_GENERATOR_ENABLED` ON — flag preexistente del preview):**
1. Abrir el builder, aplicar un preset del 97, abrir Network: editar el nombre de un
   step varias veces rápido ⇒ se ve a lo sumo un request VIGENTE por pausa (los
   anteriores figuran `(canceled)`), el YAML nunca "retrocede" a una versión vieja y
   durante el recálculo el panel muestra "Recalculando…" con el YAML anterior
   atenuado.
2. Editar un campo y volver exactamente al valor anterior ⇒ el segundo retorno NO
   dispara request (cache hit, Network sin POST nuevo).
3. Click en "Actualizar preview" ⇒ SIEMPRE dispara un POST (bypass del cache).
4. Provocar un 400 (ej. importar un YAML y vaciar el script de un step si
   `validateSpecLocal` no lo atrapa localmente; alternativa determinista: detener el
   backend) ⇒ los errores aparecen y NO parpadean en cada recálculo; el último YAML
   bueno sigue visible.

**Checklist binario (cada ítem pasa/falla):**
- [ ] `previewFetcher.test.ts`: 10/10 verdes (cache hit/miss, LRU, fuera-de-orden,
      abort, AbortError→stale, parseo 400, no-JSON→general, invalidate).
- [ ] `DevOpsPreview.test.ts`: 10/10 verdes (postAbortable, signal en preview,
      firmas api intactas, integración SWR/stale/bypass/badge, fantasma borrado,
      debounce real vivo).
- [ ] `npx tsc --noEmit` 0 errores.
- [ ] Tests vitest preexistentes del panel verdes SIN modificarlos
      (`DevOpsPage.test.ts`, `ServersSection.test.ts`, `pipelinePresets.test.ts`,
      `pipelineStepSnippets.test.ts`, `pipelineRecipes.test.ts`).
- [ ] Cero líneas backend tocadas (git diff limitado a `frontend/`); cero cambios en
      `HARNESS_TEST_FILES` (sin tests backend nuevos — §3.6).
- [ ] Cero flags nuevas; `FLAG_REGISTRY` y `_CATEGORY_KEYS` intactos; el gate
      existente `generator_enabled` del preview intacto.
- [ ] Los 4 puntos de la verificación manual HITL observados y anotados en el
      reporte de implementación (con capturas de Network para 1-3).
- [ ] Contrato de `PipelineYamlPreviewProps` sin cambios; `PublicationsSection` y
      `EnvironmentsSection` sin ediciones (heredan el fix por composición).

**Trabajo del operador:** ninguno.

---

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| El cache sirve YAML rancio si el BACKEND cambia su render (deploy nuevo, toggle de flags del generador) con el builder abierto | Cache por instancia montada (se descarta al desmontar/navegar) + capado a 20 entradas + el botón manual SIEMPRE bypassa (`invalidate()` antes del request). El render es puro y versionado con el deploy: dentro de una sesión de edición el determinismo se sostiene (`pipeline_renderers.py` sin I/O). |
| `JSON.stringify` como key: dos specs semánticamente iguales con orden de keys distinto no compartirían cache | Imposible en la práctica: TODAS las keys de cache nacen de `toSpecDict` (mismo código, mismo orden de inserción de propiedades). Peor caso teórico = cache miss inofensivo (un request de más, nunca datos incorrectos). Fijado por el test 3 de F0. |
| Apagar `loading` en desenlaces stale mentiría estado; NO apagarlo podría dejar el badge colgado si el request vigente jamás resuelve | El request vigente SIEMPRE resuelve (éxito, error o AbortError→stale de un sucesor que a su vez resuelve): la cadena termina en un desenlace no-stale que apaga `loading`. El fetch sin timeout explícito hereda el comportamiento actual (mismo riesgo que hoy, no se agrega). |
| El borrado del fantasma (F3) choca con la WIP ajena sin commitear en `PipelineBuilderSection.tsx` (working tree 2026-07-06) y con el 98 F4 (mismo archivo) | Zonas disjuntas (98: `loadDrafts`/`saveDraft`; 99: `:80-81` y `:91-106`); regla determinista del import `useRef` en F3.3; el implementador verifica las líneas por CONTENIDO (grep de `refreshTimeoutRef`), no por número de línea. |
| `AbortSignal` no soportado por algún transporte/polyfill viejo | `fetch` nativo del navegador objetivo (Vite, browsers modernos) soporta `signal` desde hace años; y aunque el abort fuera no-op, el token de secuencia (cinturón 2) garantiza el anti-stale igual. |
| El badge/atenuado cambia el aspecto visual sin flag | Cambio ADITIVO de información honesta (§3.1); no oculta ni reordena nada; usa la clase `textMuted` existente. Si el operador lo objetara, el rollback es 2 líneas de render (sin migraciones ni datos). |
| Vitest de la casa no renderiza React: la integración F2 se verifica por greps, no por interacción real | Limitación PREEXISTENTE documentada (gap `@testing-library/react` no instalada — plan 97 §DoD F1/F3). Mitigación: TODA la lógica con estados/tiempos vive en el módulo puro F0 (10 tests deterministas); los greps solo fijan el cableado; la verificación manual F4 cubre la interacción. |

## 6. Fuera de scope (v1)

- Renderizar el YAML en el CLIENTE (duplicar `to_ado_yaml`/`to_gitlab_yaml` en TS):
  violaría la fuente única de verdad de los renderers backend (paridad ADO+GitLab).
- Tocar el endpoint `POST /api/pipeline-generator/preview` o los renderers backend
  (cero backend en este plan).
- Cache persistente (localStorage/IndexedDB) o compartido entre montajes/sesiones.
- ETag/If-None-Match u otra negociación HTTP de cache con el backend.
- Cambiar el debounce de 800ms, el gate `generator_enabled` o el contrato
  `PipelineYamlPreviewProps`.
- Aplicar el mismo fetcher a OTROS fetches del panel (materialize del 88, plan/apply
  del 89): cada uno tiene semántica propia (mutaciones/HITL); si algún día se
  generaliza, será un plan propio.
- El resto del portafolio de fricción del dashboard (bootstrap/PATCH = plan 98;
  monitor CI con backoff = candidato futuro).

## 7. Glosario

- **SWR (stale-while-revalidate):** patrón de UI donde el último dato bueno queda
  visible (marcado como potencialmente desactualizado) mientras se recalcula el
  nuevo, en vez de blanquear el panel.
- **Anti-stale / respuesta fuera de orden:** cuando dos requests A (viejo, lento) y B
  (nuevo, rápido) están en vuelo, A puede resolver DESPUÉS que B; sin guard, A
  pisaría el estado con datos rancios.
- **Token de secuencia (`seq`):** contador monótono; cada request captura su número y
  al resolver comprueba si sigue siendo el vigente. Es el cinturón que funciona
  incluso si el abort no llega a tiempo.
- **`AbortController`/`AbortSignal`:** API estándar de fetch para cancelar un request
  en vuelo; el rechazo resultante es un `DOMException` con `name === 'AbortError'`.
- **Cache LRU:** cache con expulsión del elemento usado menos recientemente;
  implementado con `Map` (que preserva orden de inserción) + re-inserción en cada hit.
- **Serialización canónica del spec:** `JSON.stringify(toSpecDict(spec))`;
  determinista porque `toSpecDict` construye el dict siempre en el mismo orden.
- **Debounce fantasma:** el useEffect de `PipelineBuilderSection.tsx:91-106` que arma
  un timeout cuyo callback está vacío — código muerto que este plan borra.
- **Renderers puros:** `to_ado_yaml`/`to_gitlab_yaml`
  (`backend/services/pipeline_renderers.py:23,126`) — funciones deterministas sin
  I/O; base del determinismo que hace válido el cache.
- **`generator_enabled`:** key del health (flag `STACKY_PIPELINE_GENERATOR_ENABLED`,
  plan 73/87) que YA gatea el preview; este plan no la modifica.

## 8. Orden de implementación

1. F0 — `previewFetcher.ts` + 10 tests unit (el corazón; sin consumidores aún).
2. F1 — `api.postAbortable` + `signal` opcional en `PipelineGenerator.preview` +
   tests 1-3 (habilita el cinturón de red; aún sin consumidores).
3. F2 — integración en `PipelineYamlPreview.tsx` (SWR + badge + bypass) + tests 4-8
   (mismo commit que F0/F1 o inmediatamente después: el fetcher necesita `preview`
   con `signal`).
4. F3 — borrado del debounce fantasma en `PipelineBuilderSection.tsx` + tests 9-10
   (independiente de F0-F2; puede ir en cualquier momento, pero se secuencia al final
   para que el grep de `useRef` (F3.3) se haga sobre el estado final del archivo).
5. F4 — verificación manual HITL + checklist binario.

## 9. Definición de Hecho (DoD)

- F0: 10 tests verdes (`previewFetcher.test.ts`) + `tsc --noEmit` 0 errores.
- F1: tests 1-3 verdes (`DevOpsPreview.test.ts`) + firmas existentes de `api`
  intactas.
- F2: tests 4-8 verdes + los vitest preexistentes del panel verdes sin modificar +
  contrato `PipelineYamlPreviewProps` sin cambios.
- F3: tests 9-10 verdes + `grep refreshTimeoutRef` en el builder = 0 matches.
- F4: 4 verificaciones manuales HITL observadas (Network: cancelaciones visibles,
  cache hit sin POST, bypass manual con POST, errores sin parpadeo) y anotadas en el
  reporte de implementación.
- Global: cero líneas backend tocadas; cero flags nuevas; cero dependencias npm
  nuevas; `PublicationsSection`/`EnvironmentsSection` sin ediciones; una respuesta
  vieja JAMÁS pisa una más nueva (fijado por el test 5 de F0 — determinista, sin
  sleeps); el preview y los errores nunca se blanquean durante un recálculo.
- Impacto en los 3 runtimes (Codex CLI / Claude Code CLI / GitHub Copilot Pro):
  NINGUNO — solo componentes React + módulo TS puro; verificable por grep de
  `previewFetcher|postAbortable` fuera de `frontend/` = 0 matches.
