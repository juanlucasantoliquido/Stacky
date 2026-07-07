# Plan 102 — Publicar en un paso: orquestador HITL materializar → commit → trigger con un solo resumen y un solo confirm

**Estado:** PROPUESTO (v1)
**Versión:** v1
**Fecha:** 2026-07-06
**Autor:** StackyArchitectaUltraEficientCode
**Serie:** UX/orquestación del panel DevOps (87-91, 97) — colapsa el flujo más
frecuente de publicación en UNA superficie. NO pertenece a la serie E2E 93-96 y NO
depende de ella; declara PUNTOS DE ENGANCHE para que 93 (preflight semáforo) y 95
(producción MR/PR + paridad ADO) se enchufen sin refactor cuando existan. Tampoco
depende de 98/99/100/101 (PROPUESTOS); ninguno depende de este.
**Frontera con el plan 93:** el 93 valida runners/placeholders ANTES de disparar; este
plan orquesta la SECUENCIA. El resumen previo de este plan reserva un slot para el
semáforo del 93 (§F2). **Frontera con el plan 95:** el 95 trae MR/PR + commit ADO real
(capability `ado_commit_supported`); este plan HEREDA la limitación actual (commit ADO
= 501 render-only) y la muestra honestamente; cuando el 95 exista, el orquestador
consume su capability sin refactor (§F2). **Frontera con el plan 100:** el 100 activa
flags en lote; este orquesta acciones de publicación. Cero intersección de lógica.

**Dependencias (todas IMPLEMENTADAS y verificadas en el working tree 2026-07-06):**

| Pieza existente reusada (NO se crean rieles paralelos) | Evidencia (archivo:línea) |
|---|---|
| Materializar preset → spec (SOLO-LECTURA) | `frontend/src/api/endpoints.ts:3093-3097` (`DevOps.materializePublication`) → `backend/api/devops.py:82-106` |
| Commit HITL del spec (confirm obligatorio; devuelve `branch`) | `frontend/src/api/endpoints.ts:3191` (`PipelineGenerator.commit`); consumo del `branch` de la respuesta en `CommitPipelineModal.tsx:37-40` |
| Trigger CI HITL (`confirm: true` tipado obligatorio) + idempotencia 60s | `frontend/src/api/endpoints.ts:2951-2963` (`CIPipeline.trigger` → `POST /api/ci/<project>/trigger`); `TriggerPipelineSection.tsx:143-146` (`would_reuse`) |
| Preview YAML del spec (para el resumen previo) | `frontend/src/api/endpoints.ts:3184-3186` (`PipelineGenerator.preview`) |
| El flujo actual de 3 superficies que este plan colapsa | `PublicationsSection.tsx:373-381` (Materializar) → `:396-402` ("Commit al repo…") → `:411-418` (`CommitPipelineModal`) → `:409` (`TriggerPipelineSection` con ref+Preview+Disparar); espejo en `EnvironmentsSection.tsx:389-424` (paso 3) |
| Aviso honesto del commit ADO 501 render-only (texto a heredar) | `CommitPipelineModal.tsx:64-66` |
| Gate inline de dependencia con `FlagGateBanner` (patrón a copiar) | `EnvironmentsSection.tsx:368-374` (gatea `publications_enabled` dentro de la sección) |
| Trigger provider-agnóstico por proyecto (CIProvider, planes 71/72) | `backend/api/ci.py` (blueprint `/ci`), adapters ADO/GitLab del plan 71 |
| Patrón flag 5 patas + gotchas + R4 | `backend/config.py:895-898`, `backend/services/harness_flags.py:177-184`, `harness_flags_help.py:632-637`, `backend/harness_defaults.env`, `_REQUIRES_MAP_FROZEN` en `backend/tests/test_harness_flags_requires.py`, ratchet `backend/scripts/run_harness_tests.ps1:127-129` |
| Patrón de módulo puro frontend testeable sin render (precedente 99) | `docs/99_PLAN_PREVIEW_SIN_ESPERA_CACHE_Y_ANTISTALE.md` F0 (`previewFetcher.ts`) |
| Patrón de test vitest TS-puro | `frontend/src/pages/__tests__/ServersSection.test.ts:1-27` |

**GAP VERIFICADO:** publicar un preset hoy exige 3 superficies encadenadas a mano:
(1) click "Materializar" (`PublicationsSection.tsx:373-381`), (2) click "Commit al
repo…" que abre `CommitPipelineModal` (target + branch + checkbox + Commit + Cerrar,
`:396-418`), (3) `TriggerPipelineSection` aparte donde el operador re-tipea el ref
(el `lastBranch` llega VACÍO en esta sección — `:409` pasa `lastBranch=""` — así que ni
siquiera hereda el branch del commit) y pulsa Preview/Disparar. Son 4-6 clicks + 1
tipeo de branch duplicado, con el estado repartido en 3 componentes. No existe ningún
orquestador de la secuencia (grep de `runPublishChain|one_click|publicar en un paso`
en `frontend/src/` = 0 matches). El espejo exacto se repite en el paso 3 de
`EnvironmentsSection` (`:389-424`).

---

## 1. Objetivo + KPI

Un botón **"Publicar en un paso…"** (en Publicaciones y en el paso 3 de Ambientes) que
abre UN modal con UN resumen previo completo — preset origen, procesos resueltos,
YAML final del target, branch destino (editable; vacío = el backend deriva), y qué
pipeline se va a disparar — y UN solo confirm. Tras el confirm ejecuta la cadena
materializar → commit → trigger REUSANDO los endpoints existentes (cero rieles
paralelos), mostrando progreso por paso (materializado ✓ → commiteado ✓ → disparado ✓).
Ante fallo en un paso CORTA ahí, muestra el error y deja al operador en el **estado
intermedio real** (sin rollback mágico): p. ej. "quedó commiteado en `<branch>` pero
NO disparado — podés dispararlo en Trigger CI". Flag propia default OFF.

**KPI (medibles; los binarios están en cada fase):**

| Métrica | Hoy | Después (flag ON) | Cómo se mide |
|---|---|---|---|
| Clicks para publicar un preset (materializar→commit→trigger) | 4-6 en 3 superficies + re-tipeo del branch en el trigger | 2 (abrir modal + confirm) en 1 superficie; el branch fluye solo del commit al trigger | conteo manual + test del chain |
| Superficies/estados involucrados | 3 componentes con estado propio | 1 modal + 1 módulo puro | arquitectura F1/F2 |
| Requests | mismos 3-4 (materialize, preview, commit, trigger) | mismos (reuso estricto de endpoints) | Network |
| Honestidad ante fallo parcial | el operador debe deducir qué pasó entre 3 superficies | estado por paso explícito (ok/error/skipped) + CTA del paso siguiente manual | tests del chain (corte + estado) |
| Disparos accidentales | n/a (fricción alta) | mitigado: flag OFF + resumen único + confirm + idempotencia 60s del trigger existente | §3.1 + F2 |

## 2. Por qué ahora / gap que cierra (evidencia)

El flujo materializar→commit→trigger es EL caso de uso frecuente del panel (lo montan
igual Publicaciones y Ambientes — `PublicationsSection.tsx:373-418`,
`EnvironmentsSection.tsx:389-424`). Cada superficie tiene su estado y sus confirms; el
branch del commit NI SIQUIERA llega al trigger en estas secciones (`lastBranch=""`,
`:409`). Los tres endpoints subyacentes ya son HITL por separado (commit exige
`confirm: true`; trigger exige `confirm: true` tipado — `endpoints.ts:2956`); lo que
falta es la ORQUESTACIÓN con un resumen único honesto. Además, la serie 93-96 pendiente
va a colgar más piezas de este mismo flujo (semáforo del 93, MR/PR del 95): tener el
orquestador con slots declarados PRIMERO evita que cada plan futuro re-toque 3
componentes.

## 3. Principios y guardarraíles (no negociables, verificables)

1. **DECISIÓN DE FLAG — flag propia `STACKY_DEVOPS_ONE_CLICK_PUBLISH_ENABLED`,
   default OFF, justificado:** a diferencia del 99 (corrección de bugs) y del botón del
   100 (abrir un modal de flags), este plan COMPRIME dos side effects EXTERNOS reales
   (commit al repo + disparo de pipeline) detrás de un único confirm. Bajar la fricción
   de acciones mutantes externas es exactamente el tipo de cambio de comportamiento que
   la casa gatea (serie 87-91: cada capacidad mutante con flag propia OFF). El operador
   decide si quiere el camino comprimido; los caminos actuales (modal de commit +
   sección trigger) quedan INTACTOS con la flag ON u OFF.
   - `FlagSpec` SIN kwarg `default` (gotcha Plan 63).
   - `requires="STACKY_DEVOPS_PUBLICATIONS_ENABLED"` (su hogar funcional). OJO R4
     (profundidad 1): la cadena ONE_CLICK→PUBLICATIONS→PANEL es de longitud 2 — misma
     situación que el Plan 101 F0: **resolver por test**; si
     `test_harness_flags_requires.py` rechaza la cadena, apuntar `requires` a
     `STACKY_DEVOPS_PANEL_ENABLED` y documentar en la `description` que además necesita
     Publicaciones/Generador/Trigger. Criterio binario: el test pasa.
   - El orquestador necesita ADEMÁS `generator_enabled` (preview/commit) y
     `trigger_enabled` (disparo): el botón solo aparece con las 3 dependencias ON; si
     falta alguna, muestra `FlagGateBanner` inline de la que falte (patrón
     `EnvironmentsSection.tsx:368-374`) — `requires` declara UNA arista (R4), la UI
     informa el resto.
2. **PARIDAD ADO+GitLab (declarada y verificada):** los tres rieles reusados son
   provider-agnósticos por diseño: `materialize` produce un `PipelineSpec` neutral
   (88), `commit` recibe `target: 'gitlab'|'ado'` del preset (73/87), y `trigger` va
   por `/api/ci/<project>` que resuelve el provider del proyecto vía CIProvider
   (71/72). El orquestador NO bifurca por provider: pasa `target` y `project` tal
   cual. **Limitación heredada honesta:** el commit ADO devuelve 501 (render-only v1,
   `CommitPipelineModal.tsx:64-66`) — para un preset con `target='ado'`, el modal
   muestra EL MISMO aviso y deshabilita el confirm (no es una regresión: hoy tampoco se
   puede; es el estado del arte hasta el 95). Nada del orquestador es ADO-only ni
   GitLab-only.
3. **HITL innegociable, y honesto:** UN confirm explícito para la cadena, PERO el
   resumen previo muestra TODO lo que va a pasar (YAML final, branch, pipeline).
   Comprimir confirms NO comprime información: la AUMENTA (hoy el operador confirma el
   commit sin ver qué disparará después). Ante fallo: corta, muestra el paso exacto y
   el estado real alcanzado; NUNCA deshace nada por su cuenta (sin rollback mágico) ni
   reintenta solo.
4. **Anti-stale entre resumen y confirm:** al abrir el modal se materializa para el
   RESUMEN; al confirmar, la cadena RE-materializa fresco y compara
   (`JSON.stringify(spec)` — serialización canónica, precedente 99): si el spec cambió
   (catálogo/preset editado en el medio), ABORTA sin tocar nada externo y pide revisar
   el resumen. El operador jamás commitea un YAML distinto del que vio.
5. **Cero rieles paralelos:** el orquestador llama EXACTAMENTE
   `DevOps.materializePublication`, `PipelineGenerator.commit` y `CIPipeline.trigger`
   — cero endpoints nuevos, cero lógica de negocio duplicada. El único backend nuevo
   es la flag (5 patas + health key).
6. **Cero trabajo extra del operador:** opt-in (flag OFF); con OFF, byte-idéntico
   (el botón no existe). Los flujos actuales no se tocan (el modal de commit y la
   sección trigger siguen exactamente igual para quien los prefiera).
7. **3 runtimes (Codex CLI, Claude Code CLI, GitHub Copilot Pro):** impacto NINGUNO —
   frontend + 1 flag backend; ningún runner/prompt/harness consume esto (precedente
   78/98/99/100/101). Verificable por grep.
8. **Mono-operador sin auth:** N/A (sin RBAC).
9. **Puntos de enganche 93/95 (diseñados, NO implementados):**
   - **93 (preflight semáforo):** el modal expone la prop opcional
     `preflightSlot?: React.ReactNode` renderizada ENTRE el resumen y el confirm; el
     93, cuando exista, monta ahí su semáforo sin tocar la cadena ni el resto del
     modal. Además `ChainDeps` admite un hook opcional `beforeCommit?` (ver F1) que el
     93 puede usar para bloquear en rojo.
   - **95 (producción MR/PR + ADO real):** el aviso/deshabilitado del target ADO se
     decide con la función `adoCommitBlocked(health)` centralizada en el modal; el 95
     la reemplaza leyendo su capability `ado_commit_supported` (un solo punto de
     cambio). El paso `commit` de la cadena es una dependencia inyectada: el 95 puede
     inyectar su variante MR/PR sin tocar `runPublishChain`.

---

## F0 — Flag `STACKY_DEVOPS_ONE_CLICK_PUBLISH_ENABLED` (5 patas) + key de health

**Objetivo:** dar de alta la flag (default OFF, UI-editable) y exponer
`one_click_publish_enabled` en el health.
**Valor:** guard listo antes de la UI; opt-in de 1 click.

**Archivos a editar (exactos):**

1. `Stacky Agents/backend/config.py` — tras el bloque de
   `STACKY_DEVOPS_STACK_DETECT_ENABLED` (`config.py:895-898`; si los planes 98/101 ya
   agregaron los suyos, va a continuación del último bloque DEVOPS):

```python
# Plan 102 — Publicar en un paso (orquestador materializar->commit->trigger). Default OFF.
STACKY_DEVOPS_ONE_CLICK_PUBLISH_ENABLED: bool = os.getenv(
    "STACKY_DEVOPS_ONE_CLICK_PUBLISH_ENABLED", "false"
).lower() in ("1", "true", "yes")
```

2. `Stacky Agents/backend/services/harness_flags.py`:
   - Entrada en `_CATEGORY_KEYS["devops"]`:
     `"STACKY_DEVOPS_ONE_CLICK_PUBLISH_ENABLED",  # Plan 102 — publicar en un paso`.
   - `FlagSpec` en `FLAG_REGISTRY` a continuación de la última devops:

```python
    # ── Plan 102 — Publicar en un paso ──────────────────────────────────────────
    FlagSpec(
        key="STACKY_DEVOPS_ONE_CLICK_PUBLISH_ENABLED",
        type="bool",
        label="Publicar en un paso (Plan 102)",
        description=(
            "Plan 102 — Boton 'Publicar en un paso' en Publicaciones y Ambientes: "
            "muestra UN resumen (YAML final, branch, pipeline a disparar) y con UN "
            "confirm ejecuta materializar -> commit -> trigger reusando los rieles "
            "existentes. Ante fallo corta y muestra el estado real alcanzado (sin "
            "rollback). Necesita ademas Publicaciones, Generador y Trigger CI "
            "activos. Con OFF el boton no aparece y todo sigue como antes."
        ),
        group="global",  # mismo group que STACKY_DEVOPS_PANEL_ENABLED
        env_only=False,  # editable por UI (categoría 'devops')
        requires="STACKY_DEVOPS_PUBLICATIONS_ENABLED",  # ver §3.1 — fallback PANEL si R4 rechaza
    ),
```

   **PROHIBIDO** pasar `default=False` (gotcha Plan 63).

3. `Stacky Agents/backend/services/harness_flags_help.py`:

```python
    "STACKY_DEVOPS_ONE_CLICK_PUBLISH_ENABLED": PlainHelp(
        what="Publicás un preset completo (armar YAML, subirlo al repo y disparar el pipeline) desde un solo botón con un solo resumen y una sola confirmación.",
        on_effect="Si la activás: aparece 'Publicar en un paso' en Publicaciones y Ambientes. Ves TODO lo que va a pasar (el YAML, el branch y qué pipeline se dispara), confirmás una vez, y Stacky encadena los tres pasos mostrando el progreso. Si un paso falla, corta ahí y te dice exactamente en qué estado quedó.",
        off_effect="Si la apagás: no cambia nada; seguís publicando por los tres pasos separados de siempre (Materializar, Commit al repo, Trigger CI).",
        example="Como el checkout de un solo click de una tienda: ves el resumen completo del pedido antes, confirmás una vez, y si la tarjeta falla te avisa en qué paso quedó — no te compra nada distinto de lo que viste.",
    ),
```

4. `Stacky Agents/backend/harness_defaults.env` — línea
   `STACKY_DEVOPS_ONE_CLICK_PUBLISH_ENABLED=false` junto a las DEVOPS.

5. `Stacky Agents/backend/api/devops.py` — en `devops_health_route` (`:26-40`):

```python
        "one_click_publish_enabled": bool(getattr(cfg, "STACKY_DEVOPS_ONE_CLICK_PUBLISH_ENABLED", False)),  # Plan 102
```

6. `Stacky Agents/backend/tests/test_harness_flags_requires.py` — arista
   `"STACKY_DEVOPS_ONE_CLICK_PUBLISH_ENABLED": "STACKY_DEVOPS_PUBLICATIONS_ENABLED",`
   en `_REQUIRES_MAP_FROZEN`. **Resolver R4 por test** (§3.1): si
   `validate_requires_graph` rechaza la cadena de longitud 2
   (ONE_CLICK→PUBLICATIONS→PANEL), cambiar el `requires` del paso 2 a
   `"STACKY_DEVOPS_PANEL_ENABLED"` y esta arista en consecuencia. Criterio binario: el
   archivo de tests pasa.

**Tests PRIMERO (TDD)** — archivo nuevo
`Stacky Agents/backend/tests/test_plan102_one_click_flag.py`, 5 casos (patrón exacto
de `test_plan101_server_bootstrap_flag.py`):

1. `test_flag_registered_bool` — `FlagSpec` con la key, `type=="bool"`,
   `env_only is False`.
2. `test_flag_categorized_devops` — la key está en `_CATEGORY_KEYS["devops"]`.
3. `test_flag_requires_valid` — `spec.requires` ∈
   {`STACKY_DEVOPS_PUBLICATIONS_ENABLED`, `STACKY_DEVOPS_PANEL_ENABLED`} y la arista
   correspondiente está en `_REQUIRES_MAP_FROZEN`.
4. `test_default_off_effective` — env limpio ⇒
   `config.STACKY_DEVOPS_ONE_CLICK_PUBLISH_ENABLED is False`.
5. `test_health_exposes_one_click_key` — `GET /api/devops/health` 200 con
   `one_click_publish_enabled: False` por default.

**Comandos (venv real `.venv`):**

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan102_one_click_flag.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags_requires.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags_help.py" -q
```

**Criterio de aceptación (binario):** 5 tests nuevos + 3 meta-tests del arnés verdes.
**Flag:** `STACKY_DEVOPS_ONE_CLICK_PUBLISH_ENABLED`, default OFF.
**Impacto por runtime:** NINGUNO. Fallback: N/A.
**Trabajo del operador:** ninguno (opt-in default off).

---

## F1 — Módulo puro `publishChain.ts` (la cadena con corte honesto, sin React)

**Objetivo:** encapsular la secuencia materializar→commit→trigger como una función pura
con dependencias inyectadas, estados por paso, corte en fallo, anti-stale y CERO
rollback.
**Valor:** el corazón del plan, 100% unit-testeable de forma determinista (precedente
`previewFetcher.ts` del 99).

**Archivo NUEVO:** `Stacky Agents/frontend/src/devops/publishChain.ts`

```ts
/**
 * publishChain.ts — Plan 102 F1.
 * Orquestador PURO de la cadena materializar -> commit -> trigger.
 * - Reusa endpoints EXISTENTES vía dependencias inyectadas (cero rieles paralelos).
 * - Corte honesto: ante fallo en un paso, corta ahí; los pasos posteriores quedan
 *   'skipped'; NUNCA deshace nada (sin rollback mágico).
 * - Anti-stale: re-materializa y compara contra el spec del resumen; si difiere,
 *   aborta SIN side effects externos.
 */

export type ChainStepId = 'materialize' | 'commit' | 'trigger';
export type StepState = 'pending' | 'running' | 'ok' | 'error' | 'skipped';

export interface ChainDeps {
  materialize: () => Promise<{ spec: object }>;
  commit: (spec: object) => Promise<{ branch: string }>;
  trigger: (branch: string) => Promise<{ pipeline_id: string | null; status: string }>;
  /** Enganche Plan 93 (opcional): corre tras materializar y ANTES del commit; si
   *  devuelve un string, la cadena aborta con ese motivo (semáforo en rojo). */
  beforeCommit?: (spec: object) => Promise<string | null>;
}

export interface ChainResult {
  outcome: 'completed' | 'aborted_stale' | 'aborted_preflight' | 'failed';
  failedStep?: ChainStepId;
  error?: string;
  branch?: string;              // presente si el commit llegó a ejecutarse OK
  pipelineId?: string | null;   // presente si el trigger llegó a ejecutarse OK
  steps: Record<ChainStepId, StepState>;
}

export async function runPublishChain(
  deps: ChainDeps,
  expectedSpecJson: string,     // JSON.stringify del spec mostrado en el resumen
  onProgress: (step: ChainStepId, state: StepState) => void,
): Promise<ChainResult> {
  const steps: Record<ChainStepId, StepState> =
    { materialize: 'pending', commit: 'pending', trigger: 'pending' };
  const set = (s: ChainStepId, st: StepState) => { steps[s] = st; onProgress(s, st); };
  const msg = (e: unknown) => (e instanceof Error ? e.message : String(e));

  // Paso 1 — materializar (re-fresh, SOLO-LECTURA)
  set('materialize', 'running');
  let spec: object;
  try {
    const r = await deps.materialize();
    spec = r.spec;
  } catch (e) {
    set('materialize', 'error'); steps.commit = 'skipped'; steps.trigger = 'skipped';
    return { outcome: 'failed', failedStep: 'materialize', error: msg(e), steps };
  }
  if (JSON.stringify(spec) !== expectedSpecJson) {
    set('materialize', 'error'); steps.commit = 'skipped'; steps.trigger = 'skipped';
    return { outcome: 'aborted_stale',
             error: 'El preset o el catálogo cambiaron desde el resumen. Revisá y volvé a abrir.',
             steps };
  }
  set('materialize', 'ok');

  // Enganche 93 — preflight opcional (sin efecto si no está inyectado)
  if (deps.beforeCommit) {
    const veto = await deps.beforeCommit(spec);
    if (veto) {
      steps.commit = 'skipped'; steps.trigger = 'skipped';
      return { outcome: 'aborted_preflight', error: veto, steps };
    }
  }

  // Paso 2 — commit (side effect externo #1)
  set('commit', 'running');
  let branch: string;
  try {
    const r = await deps.commit(spec);
    branch = r.branch;
  } catch (e) {
    set('commit', 'error'); steps.trigger = 'skipped';
    return { outcome: 'failed', failedStep: 'commit', error: msg(e), steps };
  }
  set('commit', 'ok');

  // Paso 3 — trigger (side effect externo #2)
  set('trigger', 'running');
  try {
    const r = await deps.trigger(branch);
    set('trigger', 'ok');
    return { outcome: 'completed', branch, pipelineId: r.pipeline_id, steps };
  } catch (e) {
    set('trigger', 'error');
    // HONESTIDAD: el commit YA ocurrió; branch se devuelve para que la UI diga
    // "quedó commiteado en <branch>, no disparado" — SIN rollback.
    return { outcome: 'failed', failedStep: 'trigger', error: msg(e), branch, steps };
  }
}
```

**Casos borde fijados:** fallo en materialize ⇒ commit/trigger `skipped`, cero side
effects; stale ⇒ aborta sin side effects; veto del preflight (93, opcional) ⇒ aborta
sin side effects; fallo en commit ⇒ trigger `skipped`, `branch` ausente (nada
commiteado... el backend pudo fallar DESPUÉS de commitear — se reporta el error crudo
del endpoint, que es la fuente de verdad); fallo en trigger ⇒ `branch` PRESENTE
(commit ok) para el mensaje honesto; `onProgress` se emite en cada transición; NUNCA
se invoca nada que deshaga (no existe tal dependencia — imposible por construcción).

**Tests PRIMERO (TDD)** — archivo nuevo
`Stacky Agents/frontend/src/devops/publishChain.test.ts`, 9 casos (unit puro, spies
con contadores, promesas controladas):

1. `cadena feliz: 3 pasos en orden, cada dep llamada exactamente 1 vez, outcome
   completed con branch y pipelineId`.
2. `orden de ejecución: commit no se llama hasta que materialize resuelve; trigger no
   se llama hasta que commit resuelve` (promesas pendientes + asserts intermedios).
3. `stale aborta sin side effects: expectedSpecJson distinto ⇒ outcome aborted_stale,
   commit y trigger con 0 llamadas, steps {materialize:'error', commit:'skipped',
   trigger:'skipped'}`.
4. `fallo en materialize ⇒ failed/materialize, commit+trigger skipped y 0 llamadas`.
5. `fallo en commit ⇒ failed/commit, trigger skipped (0 llamadas), sin branch`.
6. `fallo en trigger ⇒ failed/trigger CON branch presente (honestidad del estado
   intermedio)`.
7. `beforeCommit veta ⇒ aborted_preflight, commit+trigger 0 llamadas` y
   `beforeCommit ausente ⇒ cadena normal` (enganche 93 inocuo por default).
8. `onProgress emite pending→running→ok por paso en la cadena feliz (secuencia exacta
   de 6 eventos: materialize running/ok, commit running/ok, trigger running/ok)`.
9. `los mensajes de error se mapean a string (Error.message y no-Error)`.

**Comandos (cwd `Stacky Agents/frontend`; vitest SIEMPRE por archivo):**

```
npx vitest run src/devops/publishChain.test.ts
npx tsc --noEmit
```

**Criterio de aceptación (binario):** 9 tests verdes + `tsc --noEmit` 0 errores.
**Flag:** gateado aguas arriba (F3); el módulo es una librería pura.
**Impacto por runtime:** NINGUNO. Fallback: N/A.
**Trabajo del operador:** ninguno.

---

## F2 — `OneClickPublishModal.tsx` (resumen único + confirm + progreso por paso)

**Objetivo:** el modal que muestra el resumen previo completo, exige UN confirm,
ejecuta `runPublishChain` con los endpoints reales inyectados y muestra el progreso y
el desenlace honesto.
**Valor:** la superficie única que reemplaza 3 componentes encadenados a mano.

**Archivo NUEVO:**
`Stacky Agents/frontend/src/components/devops/OneClickPublishModal.tsx`

Contrato y comportamiento EXACTOS:

```tsx
export interface OneClickPublishModalProps {
  project: string;
  presetName: string;
  target: 'gitlab' | 'ado';           // del preset (presetsModel)
  onClose: () => void;
  /** Enganche Plan 93 (opcional): semáforo montado entre el resumen y el confirm. */
  preflightSlot?: React.ReactNode;
}
```

1. **Al montar (fase resumen, SOLO-LECTURA):** llama
   `DevOps.materializePublication(project, presetName)` → guarda
   `summarySpec` + `resolved` + `unknown_processes`, y
   `PipelineGenerator.preview(summarySpec)` → muestra SOLO `preview[target]` en un
   `<pre className={styles.yamlPre}>` (no monta `PipelineYamlPreview` — ese componente
   re-pide con debounce; acá el spec es fijo). Muestra: nombre del preset, procesos
   resueltos, desconocidos (warn), input `branch` (placeholder "vacío = el backend
   deriva"), y la línea "Tras el commit se dispara el pipeline con ref = `<branch>`".
2. **Camino ADO (limitación heredada honesta):** helper local
   `const adoCommitBlocked = (t: 'gitlab' | 'ado') => t === 'ado';` — si
   `adoCommitBlocked(target)`, se muestra EL MISMO texto del modal existente
   ("Azure DevOps (pipeline.yml) — Render-only v1 (commit devuelve 501)",
   `CommitPipelineModal.tsx:64-66`) y el confirm queda deshabilitado. **Enganche 95:**
   cuando exista la capability `ado_commit_supported` (95), SOLO se reescribe este
   helper para leerla del health — un punto de cambio, cero refactor.
3. **`preflightSlot`** se renderiza entre el resumen y el confirm (enganche 93; hoy
   nadie lo pasa y no renderiza nada).
4. **Confirm:** checkbox "Confirmo publicar: commit del YAML al repo y disparo del
   pipeline." + botón "Publicar en un paso" (disabled sin checkbox, con
   `adoCommitBlocked`, o mientras corre).
5. **Post-confirm:** ejecuta

```tsx
    const result = await runPublishChain(
      {
        materialize: async () => {
          const r = await DevOps.materializePublication(project, presetName);
          return { spec: r.spec };
        },
        commit: async (spec) => {
          const resp = await PipelineGenerator.commit({
            ...(spec as Record<string, unknown>), target, branch: branch || undefined,
            project, confirm: true,
          }) as Record<string, unknown>;
          return { branch: String(resp.branch ?? '') };
        },
        trigger: async (ref) => {
          const r = await CIPipeline.trigger(project, ref, '', '', true);
          return { pipeline_id: r.pipeline_id ?? null, status: r.status };
        },
      },
      JSON.stringify(summarySpec),
      (step, state) => setStepStates((prev) => ({ ...prev, [step]: state })),
    );
```

   y muestra la lista de pasos con su estado (`materializado ✓ / commiteado ✓ /
   disparado ✓`, error ✗ en rojo, `skipped` atenuado).
6. **Desenlaces honestos (copy exacta):**
   - `completed`: "Publicado: commit en `<branch>`, pipeline `<pipelineId>` disparado."
   - `aborted_stale`: el mensaje del chain + botón "Recargar resumen" (re-monta la
     fase 1).
   - `failed` en `commit`: "El commit falló: `<error>`. No se commiteó ni disparó
     nada." (más el error crudo del endpoint como fuente de verdad).
   - `failed` en `trigger`: "Quedó commiteado en `<branch>` pero NO disparado:
     `<error>`. Podés dispararlo a mano en Trigger CI con ese ref." — estado intermedio
     real, sin rollback.
7. Cerrar el modal NUNCA revierte nada (los pasos ya ejecutados son reales).

**Tests PRIMERO (TDD)** — casos 1-5 de archivo nuevo
`Stacky Agents/frontend/src/pages/__tests__/DevOpsOneClick.test.ts` (TS-puro, greps):

1. `el modal reusa los 3 endpoints existentes (cero rieles paralelos)` — su fuente
   contiene `DevOps.materializePublication`, `PipelineGenerator.commit` y
   `CIPipeline.trigger`, y NO contiene `api.post('/api/devops/one-click` (grep
   negativo de endpoint propio).
2. `el confirm es obligatorio y único` — contiene `confirmChecked` en el disabled del
   botón y `confirm: true` en commit y trigger.
3. `camino ADO deshabilitado con el texto honesto` — contiene `adoCommitBlocked` y
   `Render-only v1` (texto heredado del modal existente).
4. `el enganche del 93 existe` — contiene `preflightSlot` renderizado y
   `beforeCommit` tipado en `publishChain.ts` (grep en ambos archivos).
5. `honestidad ante fallo de trigger` — contiene la copy `NO disparado` y usa
   `result.branch` en ese mensaje.

**Comandos:**

```
npx vitest run src/pages/__tests__/DevOpsOneClick.test.ts
npx tsc --noEmit
```

**Criterio de aceptación (binario):** tests 1-5 verdes + `tsc` 0 errores.
**Flag:** el modal solo es alcanzable desde los botones de F3 (gateados).
**Impacto por runtime:** NINGUNO. Fallback: flag OFF ⇒ el modal no se monta nunca.
**Trabajo del operador:** ninguno.

---

## F3 — Botones "Publicar en un paso…" en Publicaciones y Ambientes (gateados)

**Objetivo:** montar el punto de entrada en las DOS secciones que hoy encadenan el
flujo a mano, gateado por la flag propia + sus 3 dependencias.
**Valor:** el flujo queda disponible exactamente donde el operador ya trabaja.

**Archivos a editar:**

1. `Stacky Agents/frontend/src/components/devops/PublicationsSection.tsx`:
   - La firma pasa a consumir el ctx: `= ({ ctx }) => {` (hoy lo descarta,
     `PublicationsSection.tsx:55`). **Nota de colisión determinista:** el Plan 98 F4
     (PROPUESTO) especifica el MISMO cambio de firma; es idéntico e idempotente — si el
     98 ya se implementó, este paso ya está hecho y se salta.
   - Junto al botón "Materializar" (`:373-381`), agregar:

```tsx
          {ctx.health.one_click_publish_enabled === true &&
           ctx.health.generator_enabled === true &&
           ctx.health.trigger_enabled === true && (
            <button
              onClick={() => setShowOneClick(true)}
              disabled={catalogEmpty || !editing.name}
              className={styles.btnPrimary}
              style={{ padding: '10px 20px', marginBottom: '16px', marginLeft: '8px' }}
              title="Materializar, commitear y disparar con un solo resumen y un solo confirm"
            >
              Publicar en un paso…
            </button>
          )}
```

     más el estado `const [showOneClick, setShowOneClick] = useState(false);` y el
     montaje del modal:

```tsx
          {showOneClick && (
            <OneClickPublishModal
              project={activeProject}
              presetName={editing.name}
              target={editing.target ?? 'gitlab'}
              onClose={() => setShowOneClick(false)}
            />
          )}
```

   - Si `one_click_publish_enabled === true` pero falta `generator_enabled` o
     `trigger_enabled`, mostrar UN `FlagGateBanner` inline de la flag faltante (patrón
     `EnvironmentsSection.tsx:368-374`; si faltan ambas, la del generador primero —
     regla determinista).

2. `Stacky Agents/frontend/src/components/devops/EnvironmentsSection.tsx` — en el paso
   3 (`:389-424`), MISMO botón/estado/modal junto a "Materializar publicación inicial"
   (`presetName={selectedPresetName}`, `target` del preset seleccionado —
   `presets.find((p) => p.name === selectedPresetName)?.target ?? 'gitlab'`).

3. `Stacky Agents/frontend/src/pages/DevOpsPage.tsx` — `DevOpsHealth` suma la key
   explícita `one_click_publish_enabled?: boolean;` (aditiva; el index signature ya la
   admite, se declara por claridad, patrón de las demás).

**Tests PRIMERO (TDD)** — casos 6-8 de `DevOpsOneClick.test.ts`:

6. `Publicaciones monta el botón triple-gateado` — su fuente contiene
   `one_click_publish_enabled === true`, `generator_enabled === true`,
   `trigger_enabled === true` y `OneClickPublishModal`.
7. `Ambientes monta el mismo botón en el paso 3` — ídem en
   `EnvironmentsSection.tsx`.
8. `las secciones NO hand-rollean el gate de su propia flag como banner propio` — el
   fuente de ambas NO contiene `STACKY_DEVOPS_ONE_CLICK_PUBLISH_ENABLED` (el botón se
   oculta por health; los `FlagGateBanner` inline que sí aparecen son de las flags
   DEPENDENCIA generador/trigger, patrón 89 — grep de esas keys permitido).

**Comandos:**

```
npx vitest run src/pages/__tests__/DevOpsOneClick.test.ts
npx tsc --noEmit
```

**Criterio de aceptación (binario):** tests 6-8 verdes + `tsc` 0 errores + los vitest
preexistentes del panel verdes sin modificarlos (`DevOpsPage.test.ts`,
`ServersSection.test.ts`).
**Flag:** `STACKY_DEVOPS_ONE_CLICK_PUBLISH_ENABLED` vía health (OFF ⇒ botón ausente,
byte-idéntico).
**Impacto por runtime:** NINGUNO. Fallback: caminos actuales intactos siempre.
**Trabajo del operador:** ninguno.

---

## F4 — Cierre: ratchet, verificación manual HITL y checklist binario

**Objetivo:** registrar el test backend, verificar end-to-end y dejar el checklist.

**Archivos a editar:** `Stacky Agents/backend/scripts/run_harness_tests.ps1` y `.sh` —
agregar a `HARNESS_TEST_FILES`:

```
  "tests/test_plan102_one_click_flag.py",
```

**Verificación manual (HITL, con la app corriendo, proyecto GitLab con catálogo y
preset cargados, flags PUBLICATIONS+GENERATOR+TRIGGER+ONE_CLICK ON):**
1. Flag OFF: el botón no existe en ninguna de las dos secciones (byte-idéntico).
2. Flag ON: en Publicaciones, "Publicar en un paso…" abre el modal con el YAML del
   target, procesos resueltos y branch editable; el confirm está deshabilitado sin
   checkbox.
3. Confirmar ⇒ progreso materializado ✓ → commiteado ✓ → disparado ✓; verificar en
   GitLab que el commit existe en el branch informado y el pipeline corrió (Network:
   exactamente los 3 endpoints existentes, cero endpoints nuevos).
4. Editar el preset en otra pestaña ENTRE abrir el modal y confirmar ⇒ al confirmar,
   la cadena aborta con `aborted_stale` y nada externo cambió.
5. Simular fallo de trigger (apagar `STACKY_PIPELINE_TRIGGER_ENABLED` justo antes de
   confirmar) ⇒ mensaje "quedó commiteado en `<branch>` pero NO disparado" con el
   branch real (verificar el commit en GitLab; nada se revirtió).
6. Preset con `target='ado'` ⇒ el confirm queda deshabilitado con el aviso Render-only
   v1 (idéntico al modal existente).

**Checklist binario:**
- [ ] Flag default OFF; con OFF el botón no existe y todo es byte-idéntico
      (`test_plan102_one_click_flag.py` 5/5 + meta-tests del arnés verdes; cuestión R4
      resuelta por test).
- [ ] `publishChain.ts`: 9/9 verdes — orden estricto, corte honesto, stale sin side
      effects, veto del preflight inocuo por default, branch preservado en fallo de
      trigger, cero rollback por construcción.
- [ ] `DevOpsOneClick.test.ts`: 8/8 verdes — reuso estricto de los 3 endpoints (grep
      negativo de rieles paralelos), confirm único, ADO honesto, enganches 93/95
      presentes, botones triple-gateados en ambas secciones.
- [ ] `tsc --noEmit` 0 errores; vitest preexistentes verdes sin modificar.
- [ ] Cero endpoints backend nuevos (el único backend es la flag F0); test backend
      registrado en ambos ratchets.
- [ ] Paridad declarada verificada: el orquestador pasa `target`/`project` sin
      bifurcar por provider; camino ADO deshabilitado SOLO por la limitación 501
      heredada, con el mismo texto del modal existente.
- [ ] Los caminos actuales (Materializar / CommitPipelineModal /
      TriggerPipelineSection) intactos con flag ON u OFF.
- [ ] Verificación manual HITL de los 6 pasos anotada en el reporte (incluidos el
      abort stale y el estado intermedio honesto).

**Trabajo del operador:** ninguno (opt-in default off).

---

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Comprimir 3 confirms en 1 facilita un disparo accidental de pipeline | Flag propia default OFF (decisión §3.1); el resumen único muestra MÁS información que los flujos separados (YAML + branch + pipeline juntos); confirm explícito; idempotencia 60s del trigger existente (would_reuse) amortigua el doble click. |
| El spec cambia entre el resumen y el confirm (catálogo/preset editado) | Anti-stale §3.4: la cadena re-materializa y compara `JSON.stringify`; si difiere, aborta SIN side effects (test 3 de F1; verificación manual paso 4). |
| Fallo del trigger deja un commit "huérfano" | Comportamiento DISEÑADO (honestidad del estado): el resultado preserva `branch` y la UI dice exactamente qué quedó hecho y cómo seguir a mano. Sin rollback mágico (un revert automático de un commit es más peligroso que el commit). |
| El commit del backend falla DESPUÉS de commitear (error de red en la respuesta) | El chain reporta el error crudo del endpoint (fuente de verdad); el operador verifica en el repo. Igual que hoy con el modal existente — no se agrega una clase nueva de riesgo. |
| El 93/95 no encajan y exigen refactor | Enganches diseñados: `preflightSlot` (render) + `beforeCommit` (veto) para el 93; `adoCommitBlocked` centralizado + `commit` inyectable para el 95. Tests 4 (F2) fijan su existencia desde el día 1. |
| Cambio de firma de `PublicationsSection` colisiona con el Plan 98 F4 | Cambio IDÉNTICO e idempotente declarado en F3.1: si el 98 ya lo hizo, se salta; verificación por contenido, no por línea. |
| `ChainDeps.commit` devuelve `branch` vacío si el backend no lo informa | El chain lo pasa tal cual al trigger; `CIPipeline.trigger` con ref vacío falla con el error del backend (`El ref es obligatorio` ya existe como validación en la sección actual) ⇒ desenlace `failed/trigger` honesto con el commit informado. Caso cubierto por la copy del desenlace. |
| El preview del resumen difiere del YAML commiteado (dos renders) | Ambos nacen del MISMO spec materializado y los renderers son puros (99 §3.1); el commit re-renderiza server-side del mismo spec validado. El anti-stale garantiza que el spec no cambió. |

## 6. Fuera de scope (v1)

- Implementar el semáforo del 93 o el camino MR/PR del 95 (solo se dejan los enganches
  `preflightSlot`/`beforeCommit`/`adoCommitBlocked` declarados y testeados como
  existentes).
- Monitoreo continuo del pipeline disparado dentro del modal (estado final del trigger
  + pipeline_id + CTA a Trigger CI; el monitor vivo/persistente es el candidato 6 del
  portafolio, plan propio).
- Reintentos automáticos de un paso fallido (el operador decide; HITL).
- Rollback/revert de commits (jamás; honestidad del estado intermedio).
- Publicar múltiples presets en lote.
- Cambiar los flujos existentes (Materializar / CommitPipelineModal /
  TriggerPipelineSection quedan intactos).
- Migrar el ctx fabricado que `PublicationsSection` le pasa hoy a
  `PipelineYamlPreview` (`PublicationsSection.tsx:392` — health hardcodeado): defecto
  preexistente fuera de scope; este plan no lo usa (su preview es un `<pre>` propio).
- Endpoint backend orquestador (server-side chain): v1 orquesta en el cliente sobre
  endpoints HITL existentes; un orquestador server-side sería otro plan con otra
  superficie de riesgo.

## 7. Glosario

- **Orquestador HITL:** secuencia de pasos mutantes ejecutada tras UN confirm explícito
  del operador, con resumen previo completo y progreso visible por paso.
- **Cadena materializar→commit→trigger:** preset → `PipelineSpec` (solo-lectura) →
  commit del YAML al repo (side effect #1) → disparo del pipeline CI (side effect #2).
- **Corte honesto / estado intermedio real:** ante fallo, la cadena para donde falló y
  reporta exactamente qué pasos ocurrieron (p. ej. commit hecho, trigger no); nunca
  deshace ni reintenta sola.
- **Anti-stale:** re-materializar al confirmar y comparar con el spec del resumen
  (`JSON.stringify`); si difiere, abortar sin side effects.
- **`preflightSlot` / `beforeCommit`:** puntos de enganche del Plan 93 (semáforo):
  un slot de render en el resumen y un hook de veto previo al commit.
- **`adoCommitBlocked` / `ado_commit_supported`:** helper local que hoy refleja la
  limitación 501 del commit ADO; el Plan 95 lo reemplazará por su capability.
- **`would_reuse` (idempotencia 60s):** el trigger existente reusa un pipeline
  reciente del mismo ref en vez de duplicarlo (Plan 72).
- **Rieles paralelos (prohibidos):** reimplementar materialize/commit/trigger en
  endpoints o lógica nueva en vez de reusar los existentes.

## 8. Orden de implementación

1. F0 — flag 5 patas + health key + arista R4 (resuelta por test) + 5 tests backend.
2. F1 — `publishChain.ts` + 9 tests unit (sin consumidores aún).
3. F2 — `OneClickPublishModal.tsx` + tests 1-5 (necesita F1).
4. F3 — botones gateados en Publicaciones y Ambientes + tests 6-8 (necesita F2; la
   firma `({ ctx })` de Publicaciones puede ya existir por el 98 — paso idempotente).
5. F4 — ratchet (sh+ps1) + verificación manual HITL + checklist binario.

## 9. Definición de Hecho (DoD)

- F0: 5 tests verdes (`test_plan102_one_click_flag.py`) + 3 meta-tests del arnés
  verdes; flag visible en Configuración → Arnés (categoría DevOps), default OFF.
- F1: 9 tests verdes (`publishChain.test.ts`) + `tsc` 0 errores; corte honesto y cero
  rollback fijados por test.
- F2: tests 1-5 verdes (`DevOpsOneClick.test.ts`) + `tsc` 0 errores; reuso estricto de
  los 3 endpoints; enganches 93/95 presentes; ADO honesto.
- F3: tests 6-8 verdes + `tsc` 0 errores + vitest preexistentes del panel verdes sin
  modificar; botones triple-gateados; caminos actuales intactos.
- F4: test backend registrado en ambos ratchets; verificación manual HITL de los 6
  pasos anotada en el reporte (commit real verificado en GitLab, abort stale, estado
  intermedio honesto, ADO deshabilitado).
- Global: UN resumen + UN confirm para la cadena completa; ante fallo, estado
  intermedio real sin rollback; paridad ADO+GitLab declarada (orquestador
  provider-agnóstico; limitación ADO 501 heredada honestamente hasta el 95); flag
  default OFF byte-idéntica en OFF; cero endpoints nuevos; cero dependencias nuevas.
- Impacto en los 3 runtimes (Codex CLI / Claude Code CLI / GitHub Copilot Pro):
  NINGUNO — frontend + 1 flag; verificable por grep de
  `publishChain|OneClickPublishModal` fuera de `frontend/` = 0 matches.
