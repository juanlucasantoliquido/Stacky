# Plan 103 — Monitor vivo y persistente: badge del último pipeline en el shell DevOps, con backoff y estado legible

**Estado:** **IMPLEMENTADO** (F0 · F1 · F2 · F3 · F5.bis · F4) — 2026-07-26
**Versión:** v2 (v1: 2026-07-06 · v2: 2026-07-26 · implementado: 2026-07-26)

---

## §I — REGISTRO DE IMPLEMENTACIÓN (2026-07-26)

| Fase | Estado | Evidencia |
|---|---|---|
| F5.bis | IMPLEMENTADA | `src/__tests__/devopsPollingRatchet.test.ts` — censo extendido a `.ts` + shell |
| F0 | IMPLEMENTADA | flag **6 patas, default ON**: `config.py`, `harness_flags.py` (`_CATEGORY_KEYS` + `FlagSpec`), `harness_flags_help.py`, `api/devops.py` (`pipeline_monitor_enabled`), `_CURATED_DEFAULTS_ON`, arista `requires` |
| F1 | IMPLEMENTADA | `frontend/src/devops/pipelineMonitor.ts` (nuevo) |
| F2 | IMPLEMENTADA | `components/devops/useDevopsPipelineMonitor.ts` (nuevo), con guard de `visibilityState` |
| F3 | IMPLEMENTADA | badge en `pages/DevOpsHeaderV2.tsx`; hook invocado en el shell; delegación en `TriggerPipelineSection` |
| F4 | IMPLEMENTADA (salvo smoke) | huella `pipeline_state_lost_on_reload` registrada |

**Tests (corridos de verdad, por archivo):**

| Archivo | Resultado |
|---|---|
| `backend/tests/test_plan103_pipeline_monitor_flag.py` | **6 passed** |
| `backend/tests/test_harness_flags.py` | **56 passed** |
| `backend/tests/test_harness_flags_requires.py` | **9 passed** |
| `src/devops/pipelineMonitor.test.ts` | **11 passed** |
| `src/components/devops/__tests__/pipelineMonitorHook.test.ts` | **11 passed** |
| `src/__tests__/uiDebtRatchet.test.ts` | **3 passed** |
| `src/pages/__tests__/DevOpsPage.test.ts` / `DevOpsShellV2Regression.test.ts` | **21 / 2 passed** |
| `npx tsc --noEmit` | **0 errores** |

### F5.bis — la transición ROJO → VERDE, demostrada

Es el criterio que el plan exige y se cumplió en el orden correcto:

1. Ratchet extendido a `.ts` + shell, con `ALLOWLIST` **vacía** ⇒ sigue rojo **solo** por
   `BuildWorkshopSection.tsx:93` (deuda ajena del plan 201).
2. Hook escrito **sin** guard de visibilidad ⇒ el ratchet lo caza:
   `{"file":"useDevopsPipelineMonitor.ts","line":13,"kind":"setInterval"}`.
   **Ese es el punto entero de la fase:** el ratchet ORIGINAL era ciego a este archivo por
   ser `.ts`, y lo habría dejado pasar.
3. Guard de `visibilityState` agregado ⇒ el hook desaparece de los hallazgos.

Estado final del censo: **un solo** hallazgo, `BuildWorkshopSection.tsx:93`, **no tocado**;
`ALLOWLIST` sigue **vacía**; cero hallazgos atribuibles al 103.

### Bugs del PROPIO plan hallados al construirlo (3)

1. **El orden de §8 vuelve imposible el control negativo de F5.bis** (mismo defecto que el
   plan 98). Manda *"F5.bis primero, y verlo ROJO por `useDevopsPipelineMonitor.ts`"*, pero en
   el paso 1 ese archivo **todavía no existe**, así que el ratchet no puede nombrarlo. Criterio
   aplicado: extender el ratchet → escribir el hook **sin** guard (rojo, nombrando el archivo)
   → agregar el guard (verde). Mismo par rojo→verde, en un orden que sí se puede ejecutar.
2. **F1 remite a código del v1 que la reescritura in place borró** (idéntico al bug 1 del plan
   99). Dice *"se conserva del v1 tal cual"* listando símbolos (`BACKOFF_STEPS_MS`,
   `computeBackoffMs`, `toneForStatus`, `formatMonitorStatus`, …) cuyo cuerpo **no está en
   ninguna parte del documento**. Criterio aplicado: implementar desde el contrato semántico,
   que sí está completo, y fijarlo con los 11 tests. **Patrón que ya apareció dos veces: una
   crítica que reescribe el doc in place NO puede citar "el v1" como fuente de código.**
3. **El `PlainHelp` del plan no habría pasado su propio gate.** El test
   `test_plain_help_fields_non_empty_and_bounded` limita `on_effect` a **240 caracteres**; la
   primera redacción salió en **253** y puso el test en rojo — un rojo MÍO, no de los 4 ajenos
   preexistentes. El plan describe la 6ª pata pero no menciona el límite. Criterio aplicado:
   reescribir el texto a 236 y verificar que la flag desapareciera del listado de fallos
   (`grep -c PIPELINE_MONITOR` sobre el output: de 1 a **0**).

**Rojos AJENOS confirmados (NO tocados):** `devopsPollingRatchet.test.ts` 1 failed
(`BuildWorkshopSection.tsx:93`) y `test_harness_flags_help.py` 4 failed (deuda de otras flags;
verificado que ninguno menciona ya a `STACKY_DEVOPS_PIPELINE_MONITOR_ENABLED`).

**Pendiente:** los 7 puntos de verificación manual HITL de §F4 (requieren la app corriendo).
No automatizables: `@testing-library/react` y `jsdom` no están instalados.

---
**Veredicto del juez:** RECHAZADO (v1) → v2 re-diseñada. 3 BLOQUEANTES, 5 IMPORTANTES, 2 MENORES.
**Autor v1:** StackyArchitectaUltraEficientCode · **Crítica v2:** StackyArchitectaUltraEficientCode (juez adversarial)

---

## VEREDICTO DE VIGENCIA: PARCIALMENTE SUPERADO

**Sigue vivo el núcleo (3 de 5 defectos):**

| Defecto v1 | ¿Vive? | Evidencia re-anclada (2026-07-26) |
|---|---|---|
| Estado del monitor **efímero** (se pierde al recargar) | **SÍ** | `components/devops/TriggerPipelineSection.tsx:144-146` — `polling`, `pipelineId`, `monitorStatus` en `useState` |
| Resultado como **JSON crudo** | **SÍ** | `TriggerPipelineSection.tsx:362` — `{JSON.stringify(monitorStatus, null, 2)}` |
| **Sin backoff** (intervalo constante de 3s) | **SÍ** | `TriggerPipelineSection.tsx:294-302` — `setInterval(..., 3000)` |
| No hay store de "último pipeline" | **SÍ** | grep `lastPipeline|pipelineMonitor` en `frontend/src/` = **0 hits** |
| *"El estado no viaja con el operador"* / *"visibilidad nula desde otra sub-sección"* | **PARCIAL** | El **cockpit del Plan 239** ya muestra CI agregada y alerta de pipelines trabadas: `backend/services/devops_overview.py:165` (`aggregate_ci`), `:275-277` (alerta *"pipeline trabada más de N minutos"*), UI en `components/devops/DevOpsOverviewSection.tsx`. No sigue **TU** pipeline, pero la ceguera total ya no existe. |

**Lo que cambió y obliga a rediseñar:** el **Plan 239 F6** instauró una **doctrina de sondeo**
para todo el panel DevOps — *"ningún sondeo periódico de `components/devops/` puede correr con
la sección oculta"* — con un ratchet que la hace cumplir
(`frontend/src/__tests__/devopsPollingRatchet.test.ts:1-15`). **El diseño del v1 va en dirección
contraria a esa doctrina y, además, escapa a su ratchet.** Ver C1.

---

## §C — CRÍTICA ADVERSARIAL (C1..C10, rankeada)

### C1 — BLOQUEANTE — El poller del v1 **contradice al Plan 239 F6 y escapa a su ratchet**
**Qué:** el v1 §3 y §F2 ponen el poller **en el shell**, con el objetivo explícito de que
*"sobreviva al cambio de sub-sección"*. Pero la doctrina vigente dice lo opuesto
(`devopsPollingRatchet.test.ts:4`):

> *"Ningún sondeo periódico de `components/devops/` puede correr con la sección oculta."*

Peor: el ratchet **no lo vería**. Su censo es
`fs.readdirSync(DEVOPS_DIR).filter(f => f.endsWith('.tsx'))` (`:30-32`) — **solo archivos
`.tsx`, directamente en `components/devops/`, sin recursión**. El v1 ubica su poller en
`components/devops/useDevopsPipelineMonitor.ts` (**`.ts`**, no `.tsx`) y el badge en
`pages/DevOpsPage.tsx` (**fuera del directorio**). Resultado: **un sondeo que corre siempre,
invisible para el ratchet construido exactamente para cazarlo.**

**Por qué importa:** no es un detalle de estilo. El shell `DevOpsPage` está montado mientras el
operador esté en la ruta DevOps, y el v1 no gatea por visibilidad **de nada**. Sería el único
sondeo del panel sin guarda, y encima indetectable.

**Fix (§F2 rediseñada):** el poller **sí puede vivir en el shell** —eso resuelve el problema
real (sobrevivir al cambio de *sub*-sección)— pero **debe gatearse por visibilidad del
documento**, no de la sub-sección:
- guard con `document.visibilityState === 'visible'` (+ listener de `visibilitychange`) para
  pausar cuando la pestaña del navegador no está al frente;
- reanudación inmediata al volver al frente (el mismo error que el 239 F6 documenta:
  *"sin esto el efecto no se re-evalúa al volver y el sondeo no se REANUDA — peor que sondear
  de más"*);
- y **extender el ratchet** para que lo vea (§F5.bis).

### C2 — BLOQUEANTE — El ratchet de polling **ya está ROJO** por deuda ajena
**Qué:** corrido el 2026-07-26:

```
npx vitest run src/__tests__/devopsPollingRatchet.test.ts
  → 1 failed | 9 passed
  → sondeo sin guarda: [{ "file": "BuildWorkshopSection.tsx", "kind": "refetchInterval", "line": 93 }]
```

`BuildWorkshopSection.tsx:93` (Taller de Compilación, Plan 201) declara un `refetchInterval` sin
la palabra `visible` en su ventana de 2 líneas.
**Por qué importa:** el v1 no lo sabe. Un implementador que agregue un poller y corra el ratchet
lo verá rojo y **creerá que lo rompió él**; el riesgo real es que "arregle" deuda ajena o —peor—
agregue `BuildWorkshopSection.tsx` a la `ALLOWLIST` (hoy vacía a propósito, `:22`) para poner
todo en verde, desactivando el ratchet para ese archivo de forma permanente.
**Fix:** §F0 declara el rojo preexistente como **hecho conocido**, con la regla dura:
**no tocar `BuildWorkshopSection.tsx`, no tocar la `ALLOWLIST`.** El criterio binario de este
plan es *"el censo no gana hallazgos NUEVOS atribuibles al 103"*, no *"el archivo entero verde"*.
(Mismo criterio que ya se usa con `test_harness_flags_help.py`, rojo de fábrica por 4 fallos ajenos.)

### C3 — BLOQUEANTE — Todos los anclajes del v1 son falsos
| El v1 dice | La realidad hoy |
|---|---|
| `TriggerPipelineSection.tsx:20-22` (estado efímero) | `:144-146` |
| `TriggerPipelineSection.tsx:97-104` / `:99-101` (polling 3s) | `:293-302` |
| `TriggerPipelineSection.tsx:163-165` (JSON crudo) | `:362` |
| `DevOpsPage.tsx:131-136` (localStorage `selectedServer`) | `:343-348` |
| `DevOpsPage.tsx:22-32` (`DevOpsHealth`) / `:112-129` (queries) | `:32` / `:318`, `:336`, `:434` |
| `backend/api/devops.py:26-40` (health) | `:109` + el helper `_health_payload()` (la key va en `:57`) |
| `harness_flags.py:177-184` (`_CATEGORY_KEYS`) | `:235` |
| `endpoints.ts:2934-2942`, `:2967-2970` (`CIPipeline.monitor`) | movidos |
| `uiSectionsStore.ts:25-31` | `:28` (`create` plano — el patrón sigue siendo correcto) |
**Fix:** **anclar por CONTENIDO (grep del símbolo), nunca por número de línea.**

### C4 — IMPORTANTE — El KPI de requests está inflado: el sondeo de hoy **ya se pausa**
**Qué:** el v1 promete *"~40 requests en 2 min → ~7 (−82%)"*. Pero el `setInterval` de 3s
**ya está gateado** por el Plan 239 F6: `TriggerPipelineSection.tsx:294` —
`if (polling && pipelineId && ctx.visible !== false)`, con `ctx.visible` en las deps (`:301`);
y **ya se detiene** en estado terminal (`:284`). El escenario de 40 requests solo ocurre si el
operador **se queda mirando** la sección Trigger CI 2 minutos seguidos.
**Fix:** KPI recalculado en §1 contra el comportamiento real, con el escenario declarado.

### C5 — IMPORTANTE — Ignora el cap de polls del backend (429)
**Qué:** `backend/api/ci.py:35-36` define `_ACTIVE_POLLS` con
`_MAX_ACTIVE_POLLS_PER_PIPELINE = 5`, y `:197-199` responde **429
`"too many active polls for pipeline"`**. Hoy ya hay **dos** pollers en la misma sección
(`TriggerPipelineSection.tsx:203-218`, bitácora, hasta 5 ids; y `:293-302`, el recién
disparado). El v1 agrega un **tercero** sobre el mismo `pipeline_id`.
**Por qué importa:** el badge nuevo puede recibir **429** y, sin manejo, mostraría "error" sobre
un pipeline perfectamente sano.
**Fix:** §F2 trata el **429 como estado transitorio**: no cambia el tono del badge, no bumpea el
error visible, y **sube el backoff un escalón** (es exactamente la señal de "estás sondeando de
más"). Caso de test obligatorio.

### C6 — IMPORTANTE — Flag default OFF **sin citar ninguna de las 4 excepciones duras**
**Qué:** el v1 §3.1 declara `STACKY_DEVOPS_PIPELINE_MONITOR_ENABLED` default OFF y lo justifica
solo con *"byte-idéntico con OFF"*. La regla de la casa es **default ON** salvo que se cite cuál
de las 4 excepciones aplica; el v1 **no cita ninguna**. Es una brecha.
**Fix:** resolver de frente. El badge es **solo-lectura, sin side effects externos y sin gasto
de tokens de LLM** ⇒ **no califica** para ninguna de las 4 excepciones ⇒ **default ON**, en línea
con la directiva del operador y con el resto del panel (las 7 flags DevOps son `"true"` hoy).
**Condición previa, no negociable:** el default ON solo es defendible **una vez resuelto C1**
(el poller pausado con la pestaña en segundo plano). Un poller siempre-encendido y default-ON
sería consumo ocioso, y ahí sí correspondería la excepción. **El orden importa: primero el
guard, después el default.**

### C7 — IMPORTANTE — "Evitar doble polling" está declarado pero no diseñado
**Qué:** el v1 §3.9 dice que con la flag ON `TriggerPipelineSection` *"DELEGA el polling al
shell"*. No dice **cómo**, ni qué pasa con el **segundo** poller de la sección (la bitácora,
`:203-218`), que el v1 ni menciona porque no existía.
**Fix:** §F3 lo fija: con la flag ON, el efecto de `:293-302` (el del recién disparado) **no
corre** (guard adicional por `pipeline_monitor_enabled`); el poller de la **bitácora** (`:203-218`)
**no se toca** — es otro dominio (lista de corridas históricas, no "mi último pipeline") y
mezclarlos sería scope creep.

### C8 — IMPORTANTE — La flag son **6 patas**; `harness_defaults.env` no se edita a mano
La sexta es `backend/services/harness_flags_help.py`. `harness_defaults.env` lo genera
`deployment/export_harness_defaults.py`. Además el archivo de test nuevo va en
`HARNESS_TEST_FILES` de **`run_harness_tests.ps1` Y `.sh`** (sintaxis distinta entre ambos).

### C9 — MENOR — El badge en el shell puede chocar con el cockpit
El shell hoy renderiza `DevOpsCockpitNav` o `DevOpsTabsV2` según `cockpit_enabled`
(`pages/DevOpsPage.tsx:498-500`), más `DevOpsHeaderV2`. El v1 asume una "barra de sub-tabs"
simple. **Fix:** el badge se monta en `DevOpsHeaderV2` (que ya es la franja de contexto del
panel), **no** en la barra de tabs — así funciona igual con cockpit ON u OFF.

### C10 — MENOR — Sin huella de regresión
Se agrega en §F5 (clase: *"estado de pipeline perdido al recargar"*).

---

## 1. Objetivo + KPI (v2, honesto)

Sacar el estado del último pipeline disparado de la sub-sección efímera y llevarlo a un **badge
persistente en el header del panel DevOps**, que (a) sobrevive al cambio de sub-sección y a la
recarga (`localStorage`), (b) sondea con **backoff** (3s→5s→10s→30s) **y se pausa con la pestaña
en segundo plano**, (c) muestra el estado en lenguaje legible en vez de JSON crudo, y (d) cambia
de color al terminar.

| Métrica | Hoy (medido) | Después | Cómo se mide |
|---|---|---|---|
| Estado del pipeline tras **recargar** la página | **se pierde** (`useState`, `:144-146`) | **se restaura** y el sondeo se reanuda | recargar con un pipeline corriendo |
| Requests en 2 min **mirando Trigger CI** | ~40 (3s fijo, `:294`) | ~7 (backoff) | Network |
| Requests en 2 min **en otra sub-sección** | **0** (ya pausado por 239 F6) | ~7 | Network — **este es el costo nuevo, declarado** |
| Requests con la **pestaña en segundo plano** | 0 | **0** (guard de `visibilityState` — C1) | Network |
| Visibilidad del estado desde otra sub-sección | nula para *tu* pipeline | badge en el header | cambiar de sub-tab |
| Legibilidad | `JSON.stringify` crudo (`:362`) | estado + ref + link, con tono | inspección |
| Respuestas 429 que ensucian el badge | n/a | **0** (429 ⇒ sube backoff, no es error) | test F2 |

> **Honestidad sobre el trade-off (C4):** este plan **agrega** requests en el escenario "operador
> en otra sub-sección" (hoy 0, después ~7 cada 2 min) a cambio de no perder el hilo del pipeline.
> Es un intercambio deliberado, no una mejora pura. El guard de pestaña acota el peor caso.

---

## §F0 (VIVA) — Flag `STACKY_DEVOPS_PIPELINE_MONITOR_ENABLED` (**6 patas, default ON**)

Idéntica al v1 salvo **el default** (C6) y las patas (C8):

1. `backend/config.py` — ancla por contenido: el bloque de `STACKY_DEVOPS_BOOTSTRAP_ENABLED`
   (hoy `:1565`). Default **`"true"`** — sin excepción dura aplicable; badge solo-lectura.
2. `backend/services/harness_flags.py` — `_CATEGORY_KEYS["devops"]` (ancla: la entrada de
   `STACKY_DEVOPS_BOOTSTRAP_ENABLED`, hoy `:235`) + `FlagSpec` (ancla: `key="STACKY_DEVOPS_BOOTSTRAP_ENABLED"`,
   hoy `:3292`) con `requires="STACKY_DEVOPS_PANEL_ENABLED"`.
   **Default ON ⇒ la key DEBE ir en `_CURATED_DEFAULTS_ON`** (gotcha del Plan 63: una flag con
   default conocido fuera de la lista curada rompe `test_default_known_only_for_curated`).
   Seguir la receta completa de flag default-ON, no la de default-OFF del v1.
3. `backend/services/harness_flags_help.py` — `PlainHelp` (**6ª pata**), con `on_effect`/`off_effect`
   reescritos para default ON.
4. `backend/api/devops.py` — key `pipeline_monitor_enabled` en `_health_payload()` (ancla: la
   línea de `bootstrap_enabled`, hoy `:57`).
5. `backend/tests/test_harness_flags_requires.py` — arista
   `"STACKY_DEVOPS_PIPELINE_MONITOR_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED",`.
6. `harness_defaults.env` — **NO tocar a mano.**

**Tests** — `backend/tests/test_plan103_pipeline_monitor_flag.py`, 5 casos (registro / categoría /
`requires` + arista / **default ON efectivo** en `config.py` / health expone la key en `True`).
**Registrar el archivo en `HARNESS_TEST_FILES` de `run_harness_tests.ps1` Y `.sh`.**

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan103_pipeline_monitor_flag.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags_requires.py" -q
```

> **HECHO CONOCIDO, NO TOCAR (C2):** `devopsPollingRatchet.test.ts` está **ROJO hoy** por
> `BuildWorkshopSection.tsx:93` (deuda del Plan 201). **Prohibido** editar ese archivo y
> **prohibido** agregarlo a la `ALLOWLIST` (`:22`, vacía a propósito). Igual criterio con
> `test_harness_flags_help.py` (4 fallos ajenos preexistentes): validar la entrada propia aparte.

---

## §F1 (VIVA) — Módulo puro `pipelineMonitor.ts`

**Se conserva del v1 tal cual** (`frontend/src/devops/pipelineMonitor.ts`): `BACKOFF_STEPS_MS`,
`computeBackoffMs` (con clamp), `isTerminalStatus`, `toneForStatus`, `formatMonitorStatus`,
`loadPersistedPipeline`/`persist` con `try/catch`, y el store zustand `useDevopsMonitorStore`
con `create` plano (precedente: `store/uiSectionsStore.ts:28`).

**Una adición (C5):**

```ts
/** 429 del cap de polls (backend/api/ci.py:197) NO es un fallo del pipeline:
 *  es la señal de "estás sondeando de más". Sube un escalón de backoff. */
export function isPollCapError(e: unknown): boolean {
  const m = e instanceof Error ? e.message : String(e);
  return m.startsWith('429') || m.includes('too many active polls');
}
```

**Tests** — `frontend/src/devops/pipelineMonitor.test.ts`, los **10 casos del v1** + 1:

11. `isPollCapError reconoce el 429 del cap y no confunde otros errores` — `'429 TOO MANY
    REQUESTS: {"error":"too many active polls for pipeline"}'` ⇒ `true`;
    `'500 INTERNAL SERVER ERROR: boom'` ⇒ `false`.

**Criterio binario:** 11 verdes + `tsc --noEmit` 0.

---

## §F2 (VIVA, REDISEÑADA) — Hook `useDevopsPipelineMonitor` **con guard de visibilidad**

**Archivo NUEVO:** `frontend/src/components/devops/useDevopsPipelineMonitor.ts`

Diferencias duras contra el v1:

1. **Guard de pestaña (C1).** El efecto no sondea si `document.visibilityState !== 'visible'`, y
   se suscribe a `visibilitychange` para **reanudar** al volver al frente (el 239 F6 documenta
   que no reanudar es *"peor que sondear de más"*). El nombre de la variable de guard **debe
   contener la palabra `visible`** — no es cosmético: es lo que hace que el ratchet extendido
   (§F5.bis) lo reconozca.
2. **Se detiene en estado terminal** (`isTerminalStatus`) y **nunca** re-arranca solo.
3. **429 ⇒ no es error (C5):** si `isPollCapError(e)`, **no** toca el tono ni el mensaje del
   badge; solo bumpea `attempt` (sube el backoff) y reintenta.
4. Usa `setTimeout` re-armado con `computeBackoffMs(attempt)` (no `setInterval`: el intervalo
   cambia en cada vuelta).

**Tests** — `frontend/src/components/devops/__tests__/pipelineMonitorHook.test.ts`, 5 casos
(greps de integración + import real; sin render — `@testing-library/react` y `jsdom` **no están
instalados**, gap estructural declarado):

1. `el hook existe y es función`.
2. **`el hook gatea por visibilidad`** (control de C1) — su fuente contiene `visibilityState` y
   `visibilitychange`.
3. **`el hook trata el 429 como no-error`** (control de C5) — su fuente contiene `isPollCapError`.
4. `se detiene en terminal` — su fuente contiene `isTerminalStatus`.
5. `usa backoff, no intervalo fijo` — su fuente contiene `computeBackoffMs` y **no** contiene
   `setInterval(`.

**Criterio binario:** 5 verdes + `tsc` 0.

---

## §F3 (VIVA) — Badge en `DevOpsHeaderV2` + delegación del poller de la sección

1. **Badge** en `frontend/src/pages/DevOpsHeaderV2.tsx` (C9 — **no** en la barra de tabs: así
   funciona con cockpit ON u OFF). Muestra `formatMonitorStatus(...)`: tono por color (clases
   `alertSuccess` / `alertWarning` / `alertError` de `devops.module.css`), `ref`, link a
   `webUrl`, y un botón "×" que llama `clear()` (HITL: el operador lo descarta cuando quiere).
   **CERO `style={{`, cero hex** — el header ya tiene su `DevOpsPage.module.css`.
2. **Shell** (`pages/DevOpsPage.tsx`): invoca `useDevopsPipelineMonitor(health.pipeline_monitor_enabled === true)`.
   **No se agrega ningún `refetchInterval` ni `setInterval` al shell.**
3. **Registro del pipeline:** `TriggerPipelineSection` llama `setLast({...})` tras un trigger
   exitoso (ancla: donde hoy setea `pipelineId`/`polling`).
4. **Delegación (C7):** con la flag ON, el efecto de `TriggerPipelineSection.tsx:293-302` no
   corre — se suma `&& ctx.health.pipeline_monitor_enabled !== true` a su guard, **conservando
   `ctx.visible !== false`** (no romper el 239 F6). El poller de la **bitácora** (`:203-218`)
   **NO se toca**.
5. **Sustituir el JSON crudo:** el `<pre>` de `:362` pasa a mostrar `formatMonitorStatus(...)`
   cuando la flag está ON; con OFF, queda el JSON como hoy.

**Tests** — 4 casos en `pipelineMonitorHook.test.ts`:

6. `el badge vive en el header` — el fuente de `DevOpsHeaderV2.tsx` contiene
   `useDevopsMonitorStore` y `formatMonitorStatus`.
7. `sin doble polling` — el fuente de `TriggerPipelineSection.tsx` contiene
   `pipeline_monitor_enabled !== true` **en la misma línea o la anterior** al guard de
   `polling && pipelineId`.
8. **`el guard de visible del 239 F6 sigue vivo`** — el fuente de `TriggerPipelineSection.tsx`
   sigue conteniendo `ctx.visible !== false` **dos veces** (los dos pollers).
9. `deuda UI cero en el badge` — el fuente de `DevOpsHeaderV2.tsx` no gana `style={{` ni hex.

**Criterio binario:** 6-9 verdes + `tsc` 0 + **`uiDebtRatchet.test.ts` verde**.

---

## §F5.bis — [ADICIÓN ARQUITECTO] Extender el ratchet de sondeo a `.ts` y al shell

**Problema que ataca:** C1 en su raíz. El ratchet del Plan 239 F6 solo mira **`.tsx` directos de
`components/devops/`** (`devopsPollingRatchet.test.ts:30-32`). Cualquier sondeo puesto en un
`.ts` (hooks, modelos) o en `pages/` es **invisible** — y este plan crea exactamente un hook
`.ts` que sondea. Sin esto, el 103 abre el agujero que el 239 vino a cerrar.

**Cambio (aditivo, no destructivo):** en `frontend/src/__tests__/devopsPollingRatchet.test.ts`,
extender `tsxFiles()` a un `pollingFiles()` que recorra:
- `components/devops/**` con extensión `.tsx` **y `.ts`** (excluyendo `*.test.ts`/`*.test.tsx`);
- más los archivos del shell: `pages/DevOpsPage.tsx`, `pages/DevOpsHeaderV2.tsx`.

La regla de guarda **no cambia** (`visible` en la ventana). El helper puro `unguardedPolling`
tampoco. **`ALLOWLIST` sigue vacía.**

**Control negativo obligatorio (esto es lo que prueba que sirve):**
- Correr el ratchet extendido **antes** de agregar el guard de `visibilityState` al hook ⇒ debe
  **fallar** nombrando `useDevopsPipelineMonitor.ts`.
- Agregar el guard ⇒ debe **pasar** (salvo el rojo ajeno de `BuildWorkshopSection.tsx:93`, que
  **queda como está**).

Ese par rojo→verde se anota en el reporte de implementación. Un ratchet que nace verde no prueba
nada.

**Por qué respeta los rieles:** cero trabajo del operador, cero flags, cero deps, impacto runtime
nulo, **reusa** el helper y la doctrina existentes en vez de inventar otra, y **no toca deuda
ajena**.

---

## §F4 (VIVA) — Cierre: verificación HITL + huella

**Verificación manual (con la app corriendo y `STACKY_PIPELINE_TRIGGER_ENABLED` ON):**
1. Disparar un pipeline ⇒ el badge aparece en el header con tono "corriendo".
2. Cambiar de sub-sección ⇒ el badge **sigue visible y actualizándose**.
3. **Recargar la página** con el pipeline corriendo ⇒ el badge **se restaura** y el sondeo se
   reanuda (esto es lo que hoy no existe).
4. **Cambiar a otra pestaña del navegador** 1 minuto ⇒ en Network, **cero** requests de monitor;
   al volver, se reanuda de inmediato (control de C1).
5. Esperar el fin del pipeline en otra sub-sección ⇒ el badge cambia a verde/rojo.
6. Apretar "×" ⇒ el badge desaparece y no vuelve solo.
7. Apagar la flag por UI ⇒ el badge desaparece y `TriggerPipelineSection` vuelve al polling de 3s
   con JSON crudo.

**Huella (C10):** en `Stacky Agents/docs/sistema/error_fingerprints.json`, clase *"estado de
pipeline perdido al recargar la página"*, `plan: 103`,
`guard_test: pipelineMonitor.test.ts` (casos 7-10 de persistencia).

**Checklist binario:**
- [ ] `pipelineMonitor.test.ts` 11/11 verdes.
- [ ] `pipelineMonitorHook.test.ts` 9/9 verdes.
- [ ] **`devopsPollingRatchet.test.ts` EXTENDIDO**: control negativo rojo→verde documentado; el
      censo **no gana ningún hallazgo atribuible al 103**; `BuildWorkshopSection.tsx:93` sigue
      siendo el **único** rojo y **no fue tocado**; `ALLOWLIST` sigue **vacía**.
- [ ] `uiDebtRatchet.test.ts` verde; el badge no agregó `style={{` ni hex.
- [ ] `tsc --noEmit` 0 errores.
- [ ] `test_plan103_pipeline_monitor_flag.py` 5/5 verdes; archivo en **ambos** ratchets del arnés;
      la key en `_CURATED_DEFAULTS_ON` (default ON).
- [ ] `ctx.visible !== false` sigue presente **2 veces** en `TriggerPipelineSection.tsx`.
- [ ] Los 7 puntos de verificación manual observados y anotados.
- [ ] Huella registrada.

---

## 5. Riesgos y mitigaciones (v2)

| Riesgo | Mitigación |
|---|---|
| **Sondear con la pestaña en segundo plano** | Guard de `visibilityState` + `visibilitychange` (C1), verificado por el ratchet extendido y por el punto 4 de la verificación manual. |
| **Tocar/allowlistear deuda ajena para poner el ratchet verde** | Regla dura en §F0: prohibido editar `BuildWorkshopSection.tsx` y prohibido tocar la `ALLOWLIST`. El criterio es "sin hallazgos NUEVOS", no "archivo verde". |
| **429 del cap de polls ensuciando el badge** | `isPollCapError` ⇒ sube backoff, no cambia tono (C5), con test propio. |
| Doble/triple polling sobre el mismo `pipeline_id` | Delegación explícita (C7): con flag ON el poller del recién-disparado no corre; el de la bitácora es otro dominio y no se toca. |
| `localStorage` lleno/denegado | `try/catch` en `load`/`persist`; el badge degrada a memoria. |
| El badge choca con el cockpit | Se monta en `DevOpsHeaderV2`, que existe con cockpit ON y OFF (C9). |
| Vitest no renderiza React (`@testing-library/react` y `jsdom` **no instalados**) | **Gap estructural declarado.** Toda la lógica vive en `pipelineMonitor.ts` (11 tests deterministas); los greps fijan el cableado; la interacción la cubre la verificación manual F4. |
| Datos de un proyecto viejo en `localStorage` al cambiar de proyecto | `MonitoredPipeline.project` se compara con el proyecto activo; si difiere, el badge no se muestra (caso de test a agregar en F1). |

## 6. Fuera de scope (v2)

- Tocar el poller de la **bitácora** (`TriggerPipelineSection.tsx:203-218`) o el `_ACTIVE_POLLS`
  del backend.
- Notificaciones del navegador / sonido / toasts al terminar el pipeline.
- Monitorear **varios** pipelines a la vez (v1 = "el último", singular).
- Cancelar o re-disparar desde el badge (**solo lectura**; el HITL vive en Trigger CI).
- Persistencia server-side del estado del badge (es `localStorage`, no toca DB ni client-profile).
- Arreglar la deuda ajena de `BuildWorkshopSection.tsx:93` (plan propio del dueño del 201).
- Unificar el badge con la alerta de "pipeline trabada" del cockpit (Plan 239) — son dominios
  distintos: el cockpit agrega, este sigue *tu* pipeline.

## 8. Orden de implementación (v2)

1. **F5.bis primero, y verlo ROJO** por `useDevopsPipelineMonitor.ts`. Sin ese control negativo
   el ratchet extendido no prueba nada.
2. F0 — flag 6 patas **default ON** (+ `_CURATED_DEFAULTS_ON`) + ambos ratchets del arnés.
3. F1 — `pipelineMonitor.ts` + 11 tests.
4. F2 — hook **con guard de visibilidad** + 5 tests. **Correr el ratchet extendido acá** ⇒ verde.
5. F3 — badge en el header + delegación + sustitución del JSON crudo + tests 6-9.
6. F4 — verificación HITL + huella.

## 9. Definición de Hecho (v2)

- F0: 5 verdes + `requires` + `_CURATED_DEFAULTS_ON` + archivo en ambos ratchets.
- F1: 11 verdes + `tsc` 0.
- F2: 5 verdes + guard de visibilidad presente.
- F3: 4 verdes + `uiDebtRatchet` verde + `ctx.visible !== false` intacto ×2.
- F5.bis: transición **rojo → verde** demostrada y anotada; `ALLOWLIST` vacía; deuda ajena intacta.
- F4: 7 verificaciones manuales anotadas + huella registrada.
- **Global:** el estado del pipeline sobrevive a la recarga; **cero** requests con la pestaña en
  segundo plano; un 429 nunca se muestra como fallo del pipeline; ningún sondeo del panel queda
  fuera del ratchet.
- Impacto en los 3 runtimes (Codex CLI / Claude Code CLI / GitHub Copilot Pro): **NINGUNO** —
  UI del panel + 1 flag; verificable por grep de `pipelineMonitor|useDevopsPipelineMonitor` fuera
  de `frontend/` = 0 matches.
