# Plan 98 — Un viaje, una caché: bootstrap único del panel DevOps + escritura por clave del client-profile

**Estado:** CRITICADO (v2) — **RE-SCOPEADO POR VIGENCIA**
**Versión:** v2 (v1: 2026-07-06 · v2: 2026-07-26)
**Veredicto del juez:** RECHAZADO (v1) → v2 re-scopeada. 4 BLOQUEANTES, 5 IMPORTANTES, 3 MENORES.
**Autor v1:** StackyArchitectaUltraEficientCode · **Crítica v2:** StackyArchitectaUltraEficientCode (juez adversarial)

---

## CHANGELOG v1 → v2

- **[VIGENCIA] F0, F1, F2 y F3 YA ESTÁN IMPLEMENTADAS.** Se degradan a la §H (histórico).
  El plan vivo es SOLO F4 + F5 + F6. Evidencia en §H.
- **[VIGENCIA] La flag ya no es default OFF: es default ON desde 2026-07-09**
  (`backend/config.py:1565-1567`). Todo el andamiaje "byte-idéntico con OFF" del v1 describe
  un mundo que no existe. Reescrito.
- **[C1 BLOQUEANTE] El backend está VIVO pero INERTE**: `GET /api/devops/bootstrap` y
  `PATCH .../client-profile/keys/<key>` tienen **CERO call sites** en el frontend. El costo
  se pagó, el beneficio no se cobró. Es la razón por la que este plan sigue valiendo.
- **[C2 BLOQUEANTE] El grep-gate de F5 era INSATISFACIBLE.** Corregido (§F5).
- **[C3 BLOQUEANTE] Los callers son 7, no 6.** El 7º (`handleAutoDetect`) escribe una key
  NO parcheable. Corregido (§F5).
- **[C4 BLOQUEANTE] Todos los `archivo:línea` de F4/F5 son falsos** (las secciones se
  mudaron de `pages/` a `components/devops/`). Re-anclados uno por uno.
- **[C5..C9 IMPORTANTES]** ver §C.
- **[ADICIÓN ARQUITECTO]** §F5.bis — centinela de inercia que impide que un endpoint del
  panel vuelva a quedar vivo-sin-consumidor.

---

## §H — HISTÓRICO: lo que este plan YA construyó (NO re-implementar)

Verificado en el árbol el 2026-07-26. Estas 4 fases están **cerradas**:

| Fase v1 | Estado | Evidencia (archivo:línea, verificada) |
|---|---|---|
| F0 — flag 6 patas | **IMPLEMENTADA** | `backend/config.py:1565-1567` (default **`"true"`**, no `"false"`); `backend/services/harness_flags.py:235` (`_CATEGORY_KEYS["devops"]`), `:3292` (`FlagSpec`); `backend/services/harness_flags_help.py:818` (`PlainHelp`); key de health en `backend/api/devops.py:57` |
| F1 — validadores compartidos | **IMPLEMENTADA** | `backend/services/client_profile_keys.py` existe; `_validate_publication_presets` en `:62` |
| F2 — `PATCH .../client-profile/keys/<key>` | **IMPLEMENTADA** | `backend/api/client_profile.py:315` (comentario), `:323` (ruta), `:326` (guard por flag) |
| F3 — `GET /api/devops/bootstrap` | **IMPLEMENTADA** | `backend/api/devops.py:115` (ruta), `:118` (guard), `:148-152` (bloque `servers`) |
| Tests backend | **EXISTEN los 4** | `backend/tests/test_plan98_bootstrap_flag.py`, `test_plan98_profile_key_validators.py`, `test_plan98_profile_key_patch.py`, `test_plan98_bootstrap_endpoint.py` |

**Corolario incómodo (C1, BLOQUEANTE):** el backend está en producción con la flag **ON**
y **nadie lo llama**. Grep de `bootstrap` en `frontend/src/` devuelve solo
`api/endpoints.ts:1937-1939` (`/api/agent_bootstrap`, del ChatDrawer — **otro** endpoint sin
relación). Grep de `client-profile/keys` en `frontend/src/` = **0 hits**.
El KPI del plan (5 requests → 2; 2 requests por guardado → 1) está **100% sin cobrar**.

---

## §C — CRÍTICA ADVERSARIAL (C1..C12, rankeada)

### C1 — BLOQUEANTE — Endpoints vivos sin consumidor (módulo inerte)
**Qué:** F2/F3 están desplegadas y con la flag ON, pero el frontend nunca las llama. El v1
declaraba "IMPLEMENTADO" a nivel de fase sin exigir un call site.
**Por qué importa:** es el antipatrón exacto que el repo ya pagó caro (módulo testeado sin
call site ⇒ se declara hecho y no hace nada). Además la flag ON hace creer al operador que
la mejora está activa.
**Fix:** el DoD de v2 exige **call site verificado por grep** por cada endpoint (§F6), y se
agrega el centinela de inercia (§F5.bis).

### C2 — BLOQUEANTE — El grep-gate de F5 era imposible de satisfacer
**Qué:** el v1 (caso 8 de F5) exigía que `PublicationsSection.tsx` **NO** contuviera
`api.put(`. Pero `handleAutoDetect` (`components/devops/PublicationsSection.tsx:138-172`)
hace un PUT full **legítimo e irremplazable**: escribe `process_catalog` +
`devops_publication_presets` en una sola operación atómica, y `process_catalog`
**NO está en la allowlist** (`services/client_profile_keys.py`; el propio v1 §F1 la excluyó
a propósito porque su error es estructurado).
**Por qué importa:** un implementador que persiga el gate literal rompe la autodetección de
catálogo; uno que lo respete deja el test rojo para siempre. Contradicción interna pura.
**Fix:** el gate pasa a ser *acotado por función*, no por archivo (§F5, caso 8 reescrito).

### C3 — BLOQUEANTE — La tabla de callers está incompleta (7, no 6)
**Qué:** conteo real de `api.put(` en las 3 secciones: PipelineBuilder **1**, Publications
**4**, Environments **2** = **7**. El v1 listaba 6 y omitía `handleAutoDetect`.
**Por qué importa:** un caller no listado queda con el riel viejo y el plan se declara
completo igual.
**Fix:** tabla de 7 filas en §F5, con la 7ª marcada **NO MIGRABLE** y su razón.

### C4 — BLOQUEANTE — Todos los anclajes de F4/F5 son falsos
**Qué:** el v1 apunta a `PipelineBuilderSection.tsx:108-119`, `PublicationsSection.tsx:55`,
`EnvironmentsSection.tsx:82-104`, `DevOpsPage.tsx:35-41/113-129/145`, `endpoints.ts:3072-3112`.
Hoy las 3 secciones viven en **`frontend/src/components/devops/`** (no en `pages/`), y todas
las líneas cambiaron.
**Por qué importa:** un modelo menor aplica el parche a ciegas en el archivo equivocado o no
encuentra el ancla y improvisa.
**Fix:** §F4/§F5 re-anclados contra el árbol del 2026-07-26, y **regla dura: anclar por
CONTENIDO (grep del símbolo), nunca por número de línea.**

### C5 — IMPORTANTE — El v1 asume flag default OFF; hoy es ON
**Qué:** §1, §3.1, F0 y el DoD entero se apoyan en "con OFF el comportamiento es
byte-idéntico". La flag es `"true"` desde 2026-07-09 (`config.py:1566`).
**Por qué importa:** el criterio de aceptación "con flag OFF los endpoints dan 404" sigue
siendo válido como test, pero el **camino por defecto del operador es el ON**. Un plan que
solo prueba a fondo el OFF verdea sobre el camino que nadie usa.
**Fix:** §F6 invierte el orden de verificación: el camino ON es el principal; el OFF es el
fallback que se prueba por regresión.

### C6 — IMPORTANTE — `PublicationsSection` ya recibe `ctx`
**Qué:** el v1 ordenaba "cambiar la firma a `= ({ ctx }) =>` (hoy descarta el prop)".
Hoy ya es `({ ctx })` en `components/devops/PublicationsSection.tsx:61`.
**Fix:** instrucción eliminada de §F4.

### C7 — IMPORTANTE — El shell tiene 16 secciones y un contrato `ctx` mucho más rico
**Qué:** el v1 describe un shell de ~6 secciones. Hoy `DEVOPS_SECTIONS` (`pages/DevOpsPage.tsx:130`)
registra **16**, y `DevOpsSectionContext` (`:64`) ya trae `selectedServer` (`:68`),
`setActiveSection` (`:422`, Plan 120 F8) y **`visible`** (`:77`, Plan 239 F6).
**Por qué importa:** agregar `bootstrap` al ctx es aún más barato que en el v1 (el precedente
aditivo está triplicado), pero el plan debe declarar que **no toca** `visible` ni el ratchet
de polling del 239.
**Fix:** §F4 declara la no-interferencia explícitamente.

### C8 — IMPORTANTE — `useWorkbench` para el nombre de proyecto es innecesario
**Qué:** el v1 hacía importar `useWorkbench` en el shell para obtener `activeProject`.
Las 3 secciones ya resuelven `activeProject` por su cuenta y el shell ya tiene lo que
necesita para las queries que corre (`healthQuery` `:318`, `serversQuery` `:336`,
`overviewQuery` `:434`).
**Por qué importa:** import nuevo en el shell = superficie de conflicto con la sesión
paralela que está tocando ese archivo.
**Fix:** §F4 obtiene el proyecto de la misma fuente que ya usa el resto del shell y NO
agrega imports de store nuevos.

### C9 — IMPORTANTE — El bootstrap no expone las keys que el panel de hoy necesita
**Qué:** `profile_keys` del endpoint (`api/devops.py:141-147`) trae 5 keys pensadas para el
panel de 2026-07-06. El panel de hoy tiene 16 secciones.
**Por qué importa:** si F4 hidrata solo 3 secciones, las otras 13 siguen con sus fetches y
el KPI global se diluye.
**Fix:** el alcance de v2 se declara **explícitamente acotado a las 3 secciones que consumen
`client_profile`** (Builder/Publicaciones/Ambientes). Las otras 13 no leen client-profile —
verificado: el grep de `client-profile` en `components/devops/` solo devuelve esas 3.
El KPI se recalcula honestamente en §1.

### C10 — MENOR — `harness_defaults.env` no se edita a mano
El v1 (F0 paso 4) ordenaba agregar una línea a mano. Ese archivo es **generado**
(`deployment/export_harness_defaults.py`). Moot: F0 ya está hecha; se deja anotado para que
nadie lo repita.

### C11 — MENOR — El riesgo "PATCHes concurrentes a la misma key" sigue sin cubrir
Aceptado y sin cambios (mono-operador). Se mantiene en §5.

### C12 — MENOR — Sin huella de regresión
El plan mata una clase de error (pisada entre keys). No registra huella en
`docs/sistema/error_fingerprints.json`. Se agrega en §F6.

---

## 1. Objetivo (v2) + KPI recalculado

**Cobrar el beneficio del backend que ya existe.** Conectar el frontend a
`GET /api/devops/bootstrap` (hidratación en 1 round-trip) y a
`PATCH /api/projects/<name>/client-profile/keys/<key>` (escritura por clave), en las **3
secciones que consumen `client_profile`**: `PipelineBuilderSection`, `PublicationsSection`,
`EnvironmentsSection`.

**KPI honesto (medido contra el árbol del 2026-07-26):**

| Métrica | Hoy (endpoints inertes) | Con F4+F5 | Cómo se mide |
|---|---|---|---|
| GETs full-profile al visitar las 3 secciones | **3** (`PipelineBuilderSection.tsx:185`, `PublicationsSection.tsx:92`, `EnvironmentsSection.tsx:108`) | **0** (hidratan de `ctx.bootstrap`) | Network al recorrer las 3 secciones |
| Requests por guardado simple | **2** (GET full + PUT full) | **1** (PATCH solo-key) | Network al guardar |
| Callers con riel GET→merge→PUT | **7** | **1** (`handleAutoDetect`, no migrable por diseño) | `grep -c 'api.put(' components/devops/{3 archivos}` |
| Bytes subidos por guardado | profile ENTERO (catálogo incluido) | solo el valor de la key | tamaño del body en Network |
| Endpoints del 98 con call site | **0 de 2** | **2 de 2** | §F5.bis |

---

## §F4 (VIVA) — Hidratación desde `ctx.bootstrap` en las 3 secciones

**Regla dura para el implementador:** **anclá por CONTENIDO, no por número de línea.**
Los números de abajo son del 2026-07-26 y sirven de orientación; el ancla real es el símbolo.

### F4.1 — `frontend/src/api/endpoints.ts`

Dentro del objeto `DevOps` (el que ya expone `overview` — buscar el literal
`"/api/devops/health"`, hoy `endpoints.ts:3896`, y `"/api/devops/overview"`, hoy `:3900-3908`):

```ts
export interface DevOpsBootstrapResponse {
  health: Record<string, boolean | undefined>;
  has_profile: boolean;
  profile_keys: {
    devops_pipeline_drafts: Array<{ name: string; spec: object; updated_at: string }>;
    devops_publication_presets: object[];
    devops_publication_settings: { step_templates?: Record<string, string> };
    devops_environment_settings: object | null;
    process_catalog: object[];
  };
  servers: { servers: ServerSummary[]; keyring_available: boolean } | null;
}
```

y el método (**el prefijo `/api` es OBLIGATORIO** — las 470 rutas del archivo lo llevan; una
ruta sin él da 404 mudo):

```ts
  /** GET /api/devops/bootstrap — Plan 98 F3 (backend YA existe). Hidratación en 1 round-trip. */
  bootstrap: (project: string) =>
    api.get<DevOpsBootstrapResponse>(
      `/api/devops/bootstrap?project=${encodeURIComponent(project)}`,
    ),
```

### F4.2 — `frontend/src/pages/DevOpsPage.tsx` (3 cambios ADITIVOS, nada más)

1. `DevOpsHealth` (hoy `:32`) suma `bootstrap_enabled?: boolean;`.
2. `DevOpsSectionContext` (hoy `:64`) suma `bootstrap?: DevOpsBootstrapResponse | null;`
   — **key aditiva**, mismo precedente que `selectedServer` (`:68`), `setActiveSection`
   (`:422`) y `visible` (`:77`).
3. Query nueva junto a `healthQuery` (`:318`) / `serversQuery` (`:336`), usando **la misma
   fuente de proyecto activo que ya usa el shell** (NO importar `useWorkbench` — C8):

```ts
  // Plan 98 F4 — bootstrap único. Guard por flag: si está OFF el endpoint da 404.
  const bootstrapQuery = useQuery({
    queryKey: ['devops-bootstrap', activeProjectName],
    queryFn: () => DevOps.bootstrap(activeProjectName),
    retry: false,
    enabled: healthQuery.data?.bootstrap_enabled === true && !!activeProjectName,
  });
```

   y en el `ctx` (hoy `:420`): `bootstrap: bootstrapQuery.data ?? null,`.

**PROHIBIDO en esta fase:** tocar `DEVOPS_SECTIONS` (`:130`), el cálculo de `visible`
(`:552-554`, Plan 239 F6), `overviewQuery` (`:434`) o el ratchet de polling. Este plan **no
agrega ningún `setInterval` ni `refetchInterval`** — el `devopsPollingRatchet` no debe
cambiar de estado.

### F4.3 — Early-path en las 3 secciones (patrón idéntico)

| Sección (ruta real) | Función a modificar | Ancla por contenido |
|---|---|---|
| `frontend/src/components/devops/PipelineBuilderSection.tsx` | `loadDrafts` (hoy `:181`) | `const loadDrafts = async () => {` |
| `frontend/src/components/devops/PublicationsSection.tsx` | `loadProfile` (hoy `:88`) | `const loadProfile = async () => {` |
| `frontend/src/components/devops/EnvironmentsSection.tsx` | `loadProfile` (hoy `:104`) | `const loadProfile = async () => {` |

Patrón (ejemplo del builder):

```ts
  const bootstrapOn = ctx.health.bootstrap_enabled === true;

  const loadDrafts = async () => {
    if (!activeProject) return;
    // Plan 98 F4 — con bootstrap ON, hidratar desde ctx (0 requests propios).
    if (bootstrapOn) {
      if (ctx.bootstrap) {
        setDrafts(ctx.bootstrap.profile_keys.devops_pipeline_drafts as typeof drafts);
      }
      return; // en vuelo o ya hidratado: NUNCA fetch propio con la flag ON
    }
    /* ...camino actual INTACTO (api.get client-profile)... */
  };
```

y el `useEffect` de montado de cada sección suma `ctx.bootstrap` a sus deps.

**Caso borde fijado:** `EnvironmentsSection` debe conservar la distinción
`devops_environment_settings === null` ⇒ `setHasSavedSettings(false)`; el endpoint ya
devuelve `null` (no `{}`) para ese caso (`api/devops.py:145-146`), así que la semántica se
preserva sin trabajo extra.

**Tests (TDD)** — archivo nuevo
`frontend/src/components/devops/__tests__/devopsBootstrapWiring.test.ts` (TS-puro con `fs`,
estilo `pages/__tests__/ServersSection.test.ts`), 6 casos:

1. `endpoints expone DevOps.bootstrap` — `typeof mod.DevOps.bootstrap === 'function'`.
2. `la ruta del bootstrap lleva prefijo /api` — el fuente de `endpoints.ts` contiene
   `'/api/devops/bootstrap?project='` (**control negativo del bug de las 11 rutas sin `/api`**).
3. `el shell declara la query y la key aditiva` — el fuente de `DevOpsPage.tsx` contiene
   `'devops-bootstrap'` y `bootstrap: bootstrapQuery.data ?? null`.
4. `el shell NO agregó polling` — el fuente de `DevOpsPage.tsx` no gana ningún
   `refetchInterval` nuevo respecto del estado previo (assert: la cuenta de
   `refetchInterval` en el archivo es la misma que antes del cambio; el número exacto se fija
   al implementar y queda pineado en el test).
5. `las 3 secciones tienen early-path` — el fuente de cada una contiene
   `ctx.health.bootstrap_enabled === true` y `ctx.bootstrap`.
6. `EnvironmentsSection conserva la semántica null` — su fuente contiene
   `devops_environment_settings` leído de `ctx.bootstrap.profile_keys`.

**Comandos** (cwd `Stacky Agents/frontend`; vitest SIEMPRE por archivo):

```
npx vitest run src/components/devops/__tests__/devopsBootstrapWiring.test.ts
npx tsc --noEmit
```

**Criterio binario:** 6 verdes + `tsc` 0 errores + `DevOpsPage.test.ts`,
`DevOpsCockpitRegression.test.ts`, `devopsPollingRatchet.test.ts` verdes **sin modificarlos**.

---

## §F5 (VIVA) — Escritura por clave: helper único + migración de 6 de 7 callers

**Archivo NUEVO:** `frontend/src/devops/profileKeys.ts` (no existe hoy — verificado).

```ts
/**
 * profileKeys.ts — Plan 98 F5.
 * Escritura por clave del client-profile. ÚNICO punto de escritura de keys devops_*.
 * Con la flag ON: 1 PATCH chico (merge server-side bajo lock, api/client_profile.py:323).
 * Con la flag OFF: riel GET→merge→PUT actual, byte-idéntico.
 */
import { api } from '../api/client';
import { mergeKeysIntoProfile } from './presetsModel';   // existe: presetsModel.ts:68

export type PatchableProfileKey =
  | 'devops_pipeline_drafts'
  | 'devops_publication_presets'
  | 'devops_publication_settings'
  | 'devops_environment_settings';

export async function saveProfileKey(
  project: string,
  key: PatchableProfileKey,
  value: unknown,
  bootstrapEnabled: boolean,
): Promise<void> {
  if (bootstrapEnabled) {
    await api.patch(
      `/api/projects/${encodeURIComponent(project)}/client-profile/keys/${key}`,
      { value },
    );
    return;
  }
  const json = await api.get<{ profile?: Record<string, unknown> }>(
    `/api/projects/${encodeURIComponent(project)}/client-profile`,
  );
  const base = json.profile ?? {};
  const merged = mergeKeysIntoProfile(base, { [key]: value });
  await api.put(`/api/projects/${encodeURIComponent(project)}/client-profile`, { profile: merged });
}
```

> `api.patch` YA existe (`frontend/src/api/client.ts:166-167`) y sigue sin usos DevOps.

### Tabla de callers — **7 reales** (C3 corregido)

| # | Caller | Ubicación real (2026-07-26) | Key | Acción |
|---|---|---|---|---|
| 1 | `saveDraft` | `components/devops/PipelineBuilderSection.tsx:194` (PUT en `:202`) | `devops_pipeline_drafts` | **MIGRAR** → 1 PATCH |
| 2 | `savePresets` | `components/devops/PublicationsSection.tsx:106` (PUT en `:114`) | `devops_publication_presets` | **MIGRAR** → 1 PATCH |
| 3 | `saveSettings` | `components/devops/PublicationsSection.tsx:123` (PUT en `:130`) | `devops_publication_settings` | **MIGRAR** → 1 PATCH |
| 4 | `handleSaveAsDraft` | `components/devops/PublicationsSection.tsx:239` (PUT en `:252`) | `devops_pipeline_drafts` | **MIGRAR** (conserva su GET previo: hace APPEND sobre lo persistido) |
| 5 | `saveSettings` | `components/devops/EnvironmentsSection.tsx:128` (PUT en `:136`) | `devops_environment_settings` | **MIGRAR** → 1 PATCH |
| 6 | `handleCreateTodoPreset` | `components/devops/EnvironmentsSection.tsx:248` (PUT en `:258`) | `devops_publication_presets` | **MIGRAR** (conserva su GET previo: APPEND) |
| 7 | `handleAutoDetect` | `components/devops/PublicationsSection.tsx:138` (PUT en `:168`) | `process_catalog` **+** `devops_publication_presets` | **NO MIGRABLE — DEJAR INTACTO** |

**Por qué el 7 no se migra (razón dura, no pereza):** escribe **dos keys en una sola
operación atómica**, y una de ellas —`process_catalog`— **no está en la allowlist**
(`services/client_profile_keys.py`; se excluyó a propósito porque su error de validación es
estructurado, no un string). Partirlo en 2 PATCHes rompería la atomicidad
catálogo↔presets que `applyAutodetectedCatalog` garantiza. **Ampliar la allowlist a
`process_catalog` es un plan futuro, NO este.**

### Caso 8 del test — reescrito (C2)

**v1 (imposible):** "el fuente de `PublicationsSection.tsx` NO contiene `api.put(`".
**v2 (satisfacible y verdadero):**

> `ninguna función de guardado migrada re-implementa el PUT full` — para cada uno de los 6
> callers migrados, el cuerpo de la función (desde su `const <nombre> = async` hasta el
> siguiente `const ` en el mismo nivel) **no contiene `api.put(`**; y
> `PublicationsSection.tsx` contiene **exactamente 1** ocurrencia de `api.put(` en total,
> y está dentro de `handleAutoDetect`.

Ese assert es binario, prueba lo que importa y **puede fallar de verdad** si alguien deja un
caller sin migrar.

**Tests (TDD)** — archivo nuevo `frontend/src/devops/profileKeys.test.ts`, 5 casos unit
(`vi.mock('../api/client')`):

1. `con flag ON hace PATCH a la URL exacta con body {value}` — `api.patch` recibe
   `/api/projects/p1/client-profile/keys/devops_pipeline_drafts` y `{ value: [...] }`;
   `api.get`/`api.put` **no** llamados.
2. `con flag OFF ejecuta GET→merge→PUT` — el PUT lleva `otra_key` intacta + la key nueva.
3. `con flag OFF y profile ausente parte de {}`.
4. `propaga errores del PATCH` — `api.patch` rechaza ⇒ `saveProfileKey` rechaza.
5. `encodeURIComponent en project` — `mi proyecto` ⇒ `mi%20proyecto`.

Más los casos 7-8 agregados a `devopsBootstrapWiring.test.ts`:

7. `las 3 secciones importan saveProfileKey` — cada fuente contiene `from '../../devops/profileKeys'`.
8. (el reescrito de arriba).

**Comandos:**

```
npx vitest run src/devops/profileKeys.test.ts
npx vitest run src/components/devops/__tests__/devopsBootstrapWiring.test.ts
npx tsc --noEmit
```

**Criterio binario:** 5 + 8 verdes, `tsc` 0 errores, y `grep -c 'api.put(' ` devuelve
**0** en PipelineBuilderSection, **1** en PublicationsSection, **0** en EnvironmentsSection.

---

## §F5.bis — [ADICIÓN ARQUITECTO] Centinela de endpoint inerte

**Problema que ataca:** C1. Un endpoint del panel DevOps puede quedar vivo, con flag ON y
tests verdes, **sin un solo consumidor** — y nadie se entera. Es lo que pasó con este mismo
plan durante 20 días.

**Archivo NUEVO:** `frontend/src/components/devops/__tests__/devopsEndpointReach.test.ts`

Test puro con `fs`, sin red y sin render. Lógica:

1. Lee `frontend/src/api/endpoints.ts` y extrae todos los literales que empiezan con
   `/api/devops/` (regex sobre el fuente).
2. Para cada ruta, verifica que **el método que la envuelve** esté referenciado al menos una
   vez fuera de `endpoints.ts` (grep del nombre del método en `frontend/src/`).
3. Falla nombrando la ruta huérfana.

Con una **ALLOWLIST explícita y vacía al nacer**: si alguien agrega un endpoint sin
consumidor, tiene que escribir su nombre en la allowlist **a propósito**, con un comentario
del porqué. Es el mismo mecanismo que ya usa `devopsPollingRatchet.test.ts:69`.

**Por qué respeta los rieles:** cero trabajo del operador (es un test), cero flags nuevas,
cero impacto en los 3 runtimes, no degrada nada, y **reusa** el patrón de ratchet con
allowlist que la casa ya tiene.

**Criterio binario:** el test es **verde recién agregado** (porque F4/F5 acaban de cablear
las 2 rutas del 98) y se pondría **rojo** si se revirtiera F4 o F5. Verificarlo revirtiendo
mentalmente no alcanza: correr el test **antes** de F4 (debe fallar nombrando
`/api/devops/bootstrap`) y **después** (debe pasar). Ese par rojo→verde es el criterio.

---

## §F6 (VIVA) — Cierre: ratchets, verificación HITL y huella

1. **Ratchet backend:** verificar que los 4 `test_plan98_*.py` estén en `HARNESS_TEST_FILES`
   de **`backend/scripts/run_harness_tests.ps1` Y `.sh`** (sintaxis DISTINTA entre ambos: no
   copiar la receta de uno al otro). Si ya están, no tocar nada.
2. **Verificación manual HITL (camino ON primero — C5):**
   - Flag ON (default hoy): abrir el panel con Network, recorrer Pipelines → Publicaciones →
     Ambientes ⇒ **1 solo** `GET /api/devops/bootstrap` y **0** `GET .../client-profile`.
   - Guardar un preset ⇒ **1 solo** `PATCH .../keys/devops_publication_presets`.
   - Apretar "Detectar automáticamente" en Publicaciones ⇒ sigue haciendo GET+PUT full
     (correcto: es el caller 7, no migrable) y el catálogo se carga.
   - Editar un draft y un preset seguidos ⇒ releer el profile ⇒ **ambas keys presentes**.
   - Apagar la flag por UI (Configuración → Arnés, categoría DevOps) ⇒ el panel vuelve al
     riel viejo sin errores y `GET /api/devops/bootstrap` responde **404**.
3. **Huella de regresión (C12):** registrar en `Stacky Agents/docs/sistema/error_fingerprints.json`
   la clase "pisada entre keys del client-profile por PUT full concurrente", con
   `plan: 98`, `guard_test: test_plan98_profile_key_patch.py::test_patch_preserves_other_keys`.

**Checklist binario:**
- [ ] `GET /api/devops/bootstrap` y `PATCH .../client-profile/keys/<key>` tienen **≥1 call
      site cada uno** en `frontend/src/` (grep) — cierra C1.
- [ ] 6 de 7 callers migrados; `handleAutoDetect` **intacto y funcionando**.
- [ ] `grep -c 'api.put('`: 0 / 1 / 0 en las 3 secciones.
- [ ] `devopsEndpointReach.test.ts` pasó de rojo (pre-F4) a verde (post-F5).
- [ ] `tsc --noEmit` 0 errores; vitest por archivo verdes.
- [ ] `DevOpsPage.test.ts`, `DevOpsCockpitRegression.test.ts`, `devopsPollingRatchet.test.ts`
      verdes **sin modificarlos** (no se agregó polling ni se tocó el registro de secciones).
- [ ] Los 4 `test_plan98_*.py` siguen verdes (backend no se toca en v2).
- [ ] Huella registrada.

---

## 5. Riesgos y mitigaciones (v2)

| Riesgo | Mitigación |
|---|---|
| **La sesión paralela está tocando `DevOpsPage.tsx` y las secciones DevOps** | Anclar por CONTENIDO (grep del símbolo), nunca por línea. Commit con pathspec explícito por archivo. Verificar `git status` antes y después. |
| PATCHes concurrentes a la MISMA key (dos tabs) siguen siendo last-write-wins | Igual que hoy; el plan elimina la clase peor (pisar OTRAS keys). Versionado/ETag: fuera de scope (mono-operador). |
| El bootstrap queda stale si el operador edita el catálogo en Configuración → Perfil | `refetchOnWindowFocus` de react-query + el gate de catálogo vacío que Publicaciones ya muestra. Invalidación cross-página fina: fuera de scope. |
| Con flag ON y el bootstrap fallando, las 3 secciones quedan sin datos | `retry: false`; estados iniciales vacíos; el operador apaga la flag por UI (kill-switch). **Y `handleAutoDetect` sigue funcionando** porque no depende del bootstrap. |
| Ampliar la allowlist a `process_catalog` "de paso" | **PROHIBIDO en este plan.** Rompería el contrato de error estructurado que el PUT garantiza hoy. Plan futuro. |

## 6. Fuera de scope (v2)

- Backend: **nada**. F0-F3 están cerradas (§H); v2 no toca una línea de Python.
- Agregar `process_catalog` u otras keys a `PATCHABLE_PROFILE_KEYS`.
- Las otras 13 secciones del panel (ninguna lee `client_profile` — verificado por grep).
- Migrar las secciones a react-query completo (mutations/invalidation fina).
- Versionado/ETag por key; SSE/WebSockets; `ClientProfileEditor.tsx` (usa GET/PUT full a
  propósito: edita el perfil entero).

## 8. Orden de implementación (v2)

1. **F5.bis primero, y verlo ROJO** (nombra `/api/devops/bootstrap` como huérfano). Es el
   control negativo que prueba que el centinela sirve.
2. F4 — `endpoints.ts` + shell + early-path en las 3 secciones + tests.
3. F5 — `profileKeys.ts` + migración de los 6 callers + tests.
4. F5.bis **verde**.
5. F6 — ratchets, verificación HITL, huella.

## 9. Definición de Hecho (v2)

- F4: 6 vitest verdes + `tsc` 0 + los 3 tests del shell verdes sin modificar.
- F5: 5 + 8 vitest verdes + el conteo de `api.put(` exacto (0/1/0).
- F5.bis: transición **rojo → verde** demostrada y anotada en el reporte.
- F6: checklist binario completo + huella registrada.
- **Global:** los 2 endpoints del 98 dejan de estar inertes; el KPI de §1 se cumple medido en
  Network; `handleAutoDetect` sigue funcionando; cero líneas backend tocadas.
- Impacto en los 3 runtimes (Codex CLI / Claude Code CLI / GitHub Copilot Pro): **NINGUNO** —
  solo componentes React y un módulo TS puro; verificable por grep de `profileKeys|devops/bootstrap`
  fuera de `frontend/` + `backend/api/`.
