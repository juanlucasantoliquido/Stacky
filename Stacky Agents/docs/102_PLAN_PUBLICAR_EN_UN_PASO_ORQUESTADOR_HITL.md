# Plan 102 — Publicar en un paso: orquestador HITL materializar → commit → trigger con un solo resumen y un solo confirm

**Estado:** CRITICADO (v2) — **PARCIALMENTE SUPERADO** · prioridad **BAJA**
**Versión:** v2 (v1: 2026-07-06 · v2: 2026-07-26)
**Veredicto del juez:** RECHAZADO (v1) → v2 re-scopeada. 3 BLOQUEANTES, 4 IMPORTANTES, 2 MENORES.
**Autor v1:** StackyArchitectaUltraEficientCode · **Crítica v2:** StackyArchitectaUltraEficientCode (juez adversarial)

---

## VEREDICTO DE VIGENCIA: PARCIALMENTE SUPERADO

**Lo que sigue siendo cierto:** el orquestador **no existe**. Grep de
`publishChain|runPublishChain|OneClickPublish|one_click|runbook|stepper` en `frontend/src/` y
`backend/` = **0 hits**. Publicar un preset sigue repartido entre `PublicationsSection`,
`CommitPipelineModal` y `TriggerPipelineSection`.

**Lo que dejó de ser cierto: 3 de sus premisas.** Y una de ellas, aplicada literalmente,
**rompe una feature que funciona**.

| Premisa del v1 | Estado hoy | Evidencia |
|---|---|---|
| *"el `lastBranch` llega VACÍO en esta sección — `:409` pasa `lastBranch=""` — así que ni siquiera hereda el branch del commit"* | **FALSA** | `frontend/src/components/devops/PublicationsSection.tsx:491` → `<TriggerPipelineSection ctx={ctx} project={...} lastBranch={lastCommitBranch} />`. El branch **sí** fluye del commit al trigger; `TriggerPipelineSection.tsx:137` lo documenta: *"FIX C6 - branch del último commit exitoso como default"* y `:141` lo usa como estado inicial del `ref`. |
| *"el commit ADO devuelve 501 (render-only v1)"* | **FALSA** | `backend/services/ado_provider.py:146` — *"**Plan 95 F1.a — commit real vía Git Pushes API** (cierra el TODO del plan 73 C12)"*; hace `POST push` real en `:229-247`. El 501 de `backend/api/pipeline_generator.py:87-88` solo dispara ante `NotImplementedError`, que **AdoProvider ya no lanza**. |
| *"Puntos de enganche 93/95 (**diseñados, NO implementados**)"* | **FALSA ×2** | **93 IMPLEMENTADO**: `frontend/src/components/devops/PreflightPanel.tsx:1-5` (*"PreflightPanel (Plan 93 F4)"*) + `backend/api/devops.py:472` (`POST /api/devops/preflight/check`). **95 IMPLEMENTADO**: `frontend/src/components/devops/ProductionFlow.tsx:1-7` (*"ProductionFlow (Plan 95 F4)"*) + `backend/api/devops_production.py:1-2` (*"Plan 95 F3"*). |

**Consecuencia sobre el valor:** el KPI del v1 (*"4-6 clicks + 1 tipeo de branch duplicado"*)
estaba inflado. El re-tipeo del branch ya no existe, y ADO ya publica igual que GitLab. Lo que
queda es un ahorro real pero **menor** de lo prometido. Por eso este plan baja a **prioridad
BAJA**: se construye si el operador lo quiere, no antes que el 98 y el 99.

---

## §C — CRÍTICA ADVERSARIAL (C1..C9, rankeada)

### C1 — BLOQUEANTE — `adoCommitBlocked` **rompe una feature que funciona**
**Qué:** el v1 §F2 define `const adoCommitBlocked = (t: 'gitlab' | 'ado') => t === 'ado';` y con
eso **deshabilita el confirm** para todo preset con `target='ado'`, mostrando el aviso
*"Render-only v1 (commit devuelve 501)"* que hoy vive en
`frontend/src/components/devops/CommitPipelineModal.tsx:91`.
**Por qué importa:** ese texto es **copy STALE**. El commit ADO es real desde el Plan 95 F1.a
(`ado_provider.py:146`, push en `:229-247`). Un operador con presets ADO abriría el modal nuevo
y vería su camino **bloqueado por un plan**, mientras el camino viejo funciona. Es una
regresión introducida por creer un comentario en vez de leer el código.
**Fix:** eliminar `adoCommitBlocked` por completo. El orquestador **no bifurca por provider**
(que es lo que el propio §3.2 del v1 prometía). Si el commit falla, falla el paso `commit` de
la cadena y se muestra el error real del endpoint — que es la fuente de verdad.
**Y además (§F4):** corregir el copy stale de `CommitPipelineModal.tsx:91`.

### C2 — BLOQUEANTE — El `requires` propuesto es **cadena prohibida** por R4
**Qué:** el v1 §3.1 y §F0 proponen `requires="STACKY_DEVOPS_PUBLICATIONS_ENABLED"` con la
coletilla *"OJO R4... **resolver por test**; si `test_harness_flags_requires.py` rechaza la
cadena, apuntar a `STACKY_DEVOPS_PANEL_ENABLED`"*.
**Por qué importa:** **la respuesta era determinable leyendo el código, no "resolviendo por
test"**. Medido:
- `backend/services/harness_flags.py:4959-4960` — *"**R4: profundidad máxima 1** — un master
  apuntado **NO puede tener a su vez `requires`**"*; el validador emite `"cadena prohibida"`
  (`:4979-4980`).
- `STACKY_DEVOPS_PUBLICATIONS_ENABLED` **sí declara** `requires="STACKY_DEVOPS_PANEL_ENABLED"`.

⇒ la propuesta del v1 deja `test_harness_flags_requires.py` **rojo desde el primer commit**.
Dejar la decisión "para el test" es exactamente la ambigüedad prohibida para modelos menores.
**Fix:** `requires="STACKY_DEVOPS_PANEL_ENABLED"`, **sin condicional**, y la dependencia
funcional de Publicaciones/Generador/Trigger se documenta en la `description` y se informa en
la UI con `FlagGateBanner` inline. Arista en `_REQUIRES_MAP_FROZEN`:
`"STACKY_DEVOPS_ONE_CLICK_PUBLISH_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED",`.

### C3 — BLOQUEANTE — El `.tsx` nuevo nace violando el ratchet de deuda UI
**Qué:** `OneClickPublishModal.tsx` es un archivo **nuevo**. La regla de la casa para archivos
nuevos es **alcance 0**: primitivas `Input/Select/Textarea/Checkbox` y **cero `style={{`**
(`frontend/src/__tests__/uiDebtRatchet.test.ts:4`, `:161`). El v1 no lo menciona y su hermano
de tanda (el modal del plan 100) traía ~15 `style={{` y un `<input type="checkbox">` crudo.
**Fix:** §F2 exige explícitamente: **0 `style={{`, 0 hex literales, primitivas `Input` y
`Checkbox`, clases de `devops.module.css`**. Criterio binario: `uiDebtRatchet.test.ts` verde
inmediatamente después de F2 (no al final).

### C4 — IMPORTANTE — El KPI está inflado (premisa del branch, C-vigencia)
**Fix:** KPI recalculado en §1 contra el árbol real. La cadena ahorra **superficies y estado**,
no un tipeo que ya no existe.

### C5 — IMPORTANTE — Diseña slots vacíos para features ya construidas
**Qué:** §3.9 reserva `preflightSlot?: React.ReactNode` y `beforeCommit?` "para cuando el 93
exista", y un punto de cambio "para cuando el 95 exista". **Los dos existen.**
**Por qué importa:** entregar ganchos vacíos junto a componentes reales es deuda inmediata: el
operador vería el modal nuevo **sin** el semáforo que ya tiene en `PreflightPanel`.
**Fix:** los slots dejan de ser opcionales-para-el-futuro y pasan a **cablearse de verdad**
en §F2/§F3: `preflightSlot` monta el `PreflightPanel` existente, y `beforeCommit` queda
**deliberadamente sin cablear** — porque `PreflightPanel.tsx:3-4` declara que es
*"SOLO-LECTURA, informativo, **NUNCA bloquea** commit/trigger (HITL §3.3: el operador decide)"*.
Cablear un veto automático **violaría el human-in-the-loop** de ese plan. Se documenta como
decisión, no como pendiente.

### C6 — IMPORTANTE — Anclajes de frontend obsoletos
`PublicationsSection.tsx:373-418`, `:409`, `EnvironmentsSection.tsx:389-424`,
`CommitPipelineModal.tsx:37-40`/`:64-66`, `endpoints.ts:3093-3097`/`:3184-3186`/`:2951-2963`,
`config.py:895-898`, `harness_flags.py:177-184` — **todos movidos**. Anclas reales en §F0/§F2/§F3.
**Fix:** **anclar por CONTENIDO (grep del símbolo), nunca por número de línea.**

### C7 — IMPORTANTE — La flag son **6 patas**, no 5
La sexta es `backend/services/harness_flags_help.py`. Y `harness_defaults.env` **no se edita a
mano** (lo genera `deployment/export_harness_defaults.py`).
**Nota de flag:** el default **OFF** de este plan **sí está justificado** por la excepción dura
(1): comprime dos side effects externos reales (commit al repo + disparo de pipeline) detrás de
un confirm. Debe citarse esa excepción explícitamente en el doc, cosa que el v1 hacía bien en
§3.1 y se conserva.

### C8 — MENOR — El caso borde del fallo de commit está mal razonado
El v1 dice: *"fallo en commit ⇒ `branch` ausente (nada commiteado... el backend pudo fallar
DESPUÉS de commitear)"*. Los dos paréntesis se contradicen. **Fix:** el mensaje al operador
debe ser explícitamente incierto: *"el commit falló; verificá el repo antes de reintentar"*, y
`branch` se omite. Nunca afirmar "nada se commiteó" cuando no se sabe.

### C9 — MENOR — Sin huella de regresión
Se agrega en §F4 la huella del copy stale del 501 (clase: "la UI afirma una limitación que el
backend ya no tiene").

---

## 1. Objetivo + KPI (v2, honesto)

Un botón **"Publicar en un paso…"** en Publicaciones (y en el paso 3 de Ambientes) que abre UN
modal con UN resumen previo (preset, procesos resueltos, YAML final del target, branch destino
editable, pipeline a disparar) y UN confirm. Tras el confirm ejecuta materializar → commit →
trigger **reusando los endpoints existentes**, con progreso por paso y **corte honesto sin
rollback**. Flag propia default OFF (excepción dura 1: comprime side effects externos).

| Métrica | Hoy (medido 2026-07-26) | Con flag ON | Cómo se mide |
|---|---|---|---|
| Superficies para publicar un preset | **3** (`PublicationsSection` → `CommitPipelineModal` → `TriggerPipelineSection`) | **1** modal | inspección |
| Clicks | 4-5 | **2** (abrir + confirm) | conteo manual |
| Re-tipeo del branch | **0 — ya resuelto** (`PublicationsSection.tsx:491`) | 0 | — |
| Estados independientes | 3 componentes con `useState` propio | 1 modal + 1 módulo puro | arquitectura F1/F2 |
| Requests | mismos 3-4 | **los mismos** (reuso estricto) | Network |
| Presets ADO bloqueados por la UI | **0** (ADO commitea de verdad) | **0** | test F2 |
| Honestidad ante fallo parcial | el operador deduce entre 3 superficies | estado por paso + CTA del siguiente paso manual | tests F1 |

---

## §F0 (VIVA) — Flag `STACKY_DEVOPS_ONE_CLICK_PUBLISH_ENABLED` (**6 patas**)

1. `backend/config.py` — junto al resto del bloque DEVOPS (ancla por contenido: el bloque de
   `STACKY_DEVOPS_BOOTSTRAP_ENABLED`, hoy `:1565`):

```python
    # Plan 102 — Publicar en un paso (orquestador materializar->commit->trigger).
    # Default OFF — EXCEPCIÓN DURA (1): comprime DOS side effects externos reales
    # (commit al repo + disparo de pipeline) detrás de un único confirm.
    STACKY_DEVOPS_ONE_CLICK_PUBLISH_ENABLED: bool = os.getenv(
        "STACKY_DEVOPS_ONE_CLICK_PUBLISH_ENABLED", "false"
    ).lower() in ("1", "true", "yes")
```

2. `backend/services/harness_flags.py` — entrada en `_CATEGORY_KEYS["devops"]` (ancla: la
   entrada de `STACKY_DEVOPS_BOOTSTRAP_ENABLED`, hoy `:235`) + `FlagSpec` en `FLAG_REGISTRY`
   (ancla: `key="STACKY_DEVOPS_BOOTSTRAP_ENABLED"`, hoy `:3292`), con
   **`requires="STACKY_DEVOPS_PANEL_ENABLED"`** (C2 — sin condicional) y **SIN kwarg `default`**.
3. `backend/services/harness_flags_help.py` — `PlainHelp` (ancla: la entrada de
   `STACKY_DEVOPS_BOOTSTRAP_ENABLED`, hoy `:818`). **6ª pata.**
4. `backend/api/devops.py` — key aditiva `one_click_publish_enabled` en `_health_payload()`
   (ancla: la línea de `bootstrap_enabled`, hoy `:57`).
5. `backend/tests/test_harness_flags_requires.py` — arista
   `"STACKY_DEVOPS_ONE_CLICK_PUBLISH_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED",`.
6. `harness_defaults.env` — **NO tocar a mano**; lo regenera
   `deployment/export_harness_defaults.py`.

**Tests** — `backend/tests/test_plan102_one_click_flag.py`, 5 casos (registro / categoría /
`requires == "STACKY_DEVOPS_PANEL_ENABLED"` + arista congelada / default OFF efectivo en
`config.py` / health expone la key). **Registrar el archivo en `HARNESS_TEST_FILES` de
`run_harness_tests.ps1` Y `.sh`** (sintaxis DISTINTA entre ambos).

**Comandos** (venv real: `backend/.venv` = py3.13.5; **por archivo, nunca la suite**):

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan102_one_click_flag.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags_requires.py" -q
```

**Criterio binario:** 5 verdes + `test_harness_flags_requires.py` **verde** (C2).
*Nota: `test_harness_flags_help.py` tiene 4 fallos ajenos preexistentes — validar la entrada
propia por separado, no tomar el archivo entero como criterio.*

---

## §F1 (VIVA) — Módulo puro `publishChain.ts`

**Se conserva del v1 tal cual** (es la mejor parte del plan): `frontend/src/devops/publishChain.ts`
con `runPublishChain(deps, expectedSpecJson, onProgress)`, `ChainDeps` con dependencias
inyectadas, corte honesto, anti-stale por comparación de `JSON.stringify`, y **cero rollback por
construcción** (no existe ninguna dependencia que deshaga).

**Dos correcciones:**
- `beforeCommit?` se conserva en el tipo pero **se documenta como NO cableado** (C5): el
  preflight del Plan 93 es informativo y **nunca bloquea** por diseño.
- El caso de fallo en `commit` devuelve `error` + un flag `commitUncertain: true`, y el mensaje
  al operador es *"el commit falló; verificá el repo antes de reintentar"* (C8). Nunca afirmar
  "nada se commiteó".

**Tests** — `frontend/src/devops/publishChain.test.ts`, los **9 casos del v1** + 1:

10. `fallo en commit NO afirma que nada se commiteó` — el resultado trae `commitUncertain: true`
    y **no** trae `branch`.

**Criterio binario:** 10 verdes + `tsc --noEmit` 0.

---

## §F2 (VIVA) — `OneClickPublishModal.tsx` con **deuda UI cero**

**Archivo NUEVO:** `frontend/src/components/devops/OneClickPublishModal.tsx`

```tsx
export interface OneClickPublishModalProps {
  project: string;
  presetName: string;
  target: 'gitlab' | 'ado';
  onClose: () => void;
  /** Plan 93 — el PreflightPanel REAL se monta acá (C5). */
  preflightSlot?: React.ReactNode;
}
```

**Reglas duras de esta fase:**
- **CERO `style={{`. CERO hex literales.** Todo por `devops.module.css` con tokens
  (`var(--text-muted)` etc.). Primitivas `Input` y `Checkbox` de `components/ui/`, nunca
  `<input>` crudo. Precedente en casa: `PipelineLintPanel.tsx:5` declara *"CERO style inline"*.
- **`adoCommitBlocked` NO EXISTE** (C1). El modal no bifurca por provider. Si el commit falla,
  falla el paso y se muestra el error real.

**Comportamiento:**
1. Al montar (SOLO-LECTURA): `DevOps.materializePublication(project, presetName)` →
   `summarySpec` + `resolved` + `unknown_processes`; luego `PipelineGenerator.preview(summarySpec)`
   y se muestra **solo** `preview[target]` en un `<pre className={styles.yamlPre}>`
   (no se monta `PipelineYamlPreview`: ese re-pide con debounce; acá el spec es fijo).
2. Resumen: preset, procesos resueltos, desconocidos (warn), `Input` de `branch`
   (placeholder "vacío = el backend deriva"), y la línea "Tras el commit se dispara el pipeline
   con ref = `<branch>`".
3. `preflightSlot` se renderiza **entre el resumen y el confirm**.
4. `Checkbox` de confirmación obligatorio ⇒ botón "Publicar" habilitado.
5. Al confirmar: `runPublishChain` con los 3 endpoints reales inyectados y `onProgress`
   pintando el estado por paso.
6. Desenlace: `completed` ⇒ resumen con branch + link al pipeline; `failed` en `trigger` ⇒
   *"quedó commiteado en `<branch>` pero NO disparado — podés dispararlo en Trigger CI"*;
   `failed` en `commit` ⇒ el mensaje incierto de C8; `aborted_stale` ⇒ pedir reabrir el resumen.

**Tests** — `frontend/src/components/devops/__tests__/oneClickPublish.test.ts`, 6 casos (greps
de integración + import real):

1. `el modal usa runPublishChain` — su fuente contiene `runPublishChain`.
2. `exige confirm` — su fuente contiene el guard del checkbox en el handler y el `disabled`.
3. **`no bloquea ADO`** (control de C1) — su fuente **NO** contiene `adoCommitBlocked` ni
   `render-only` ni `501`.
4. **`deuda UI cero`** (control de C3) — su fuente **NO** contiene `style={{` ni un hex
   (`/#[0-9a-fA-F]{3,8}\b/`), y **SÍ** importa `Checkbox` de las primitivas.
5. `monta el preflightSlot entre resumen y confirm` — su fuente contiene `preflightSlot`.
6. `no existe ninguna dependencia de rollback` — el fuente de `publishChain.ts` no contiene
   `rollback|undo|revert`.

**Criterio binario:** 6 verdes + `tsc --noEmit` 0 + **`npx vitest run src/__tests__/uiDebtRatchet.test.ts`
VERDE inmediatamente después de esta fase** (no al final).

---

## §F3 (VIVA) — Montaje en Publicaciones y Ambientes

- `frontend/src/components/devops/PublicationsSection.tsx` — botón "Publicar en un paso…"
  junto a "Materializar", visible solo si
  `ctx.health.one_click_publish_enabled === true && ctx.health.generator_enabled &&
  ctx.health.trigger_enabled`; si falta alguna dependencia, `FlagGateBanner` inline de la que
  falte (patrón existente en `EnvironmentsSection`).
- `frontend/src/components/devops/EnvironmentsSection.tsx` — mismo botón en el paso 3.
- **PROHIBIDO** tocar `CommitPipelineModal` y `TriggerPipelineSection` como flujos: siguen
  intactos y disponibles (backward-compatible duro).
- El `preflightSlot` se completa con el `PreflightPanel` existente.

**Criterio binario:** con la flag OFF, el botón **no se renderiza** y el diff de comportamiento
es nulo (test de grep del guard) + los vitest preexistentes del panel verdes sin modificar.

---

## §F4 (VIVA) — [ADICIÓN ARQUITECTO] Cerrar el copy stale del 501 + huella

**Problema que ataca:** C1 en su raíz. El texto *"Azure DevOps (pipeline.yml) — Render-only v1
(commit devuelve 501)"* (`frontend/src/components/devops/CommitPipelineModal.tsx:91`) **miente
desde el Plan 95 F1.a**. Ese copy es lo que indujo al v1 a diseñar `adoCommitBlocked`, es decir:
**una mentira en la UI ya se propagó a un plan y casi se convierte en una regresión.**

1. Corregir el texto de `CommitPipelineModal.tsx:91` para que refleje el estado real
   (commit ADO real vía Git Pushes API, Plan 95 F1.a).
2. Test de centinela en `oneClickPublish.test.ts`:
   `CommitPipelineModal no afirma la limitación 501` — su fuente **no** contiene `501` ni
   `Render-only`.
3. **Huella de regresión** en `Stacky Agents/docs/sistema/error_fingerprints.json`:
   clase *"la UI afirma una limitación que el backend ya no tiene"*, `plan: 102`,
   `guard_test: oneClickPublish.test.ts`.

**Por qué respeta los rieles:** cero trabajo del operador, no toca backend, corrige (no degrada),
y ataca la **causa** del bloqueante en vez del síntoma.

---

## 5. Riesgos y mitigaciones (v2)

| Riesgo | Mitigación |
|---|---|
| **Re-introducir el bloqueo de ADO** | `adoCommitBlocked` prohibido; test 3 de F2 lo pinea por grep negativo. |
| **`requires` en cadena prohibida** | Resuelto en el doc (`PANEL`, sin condicional); `test_harness_flags_requires.py` es criterio binario de F0. |
| **Deuda UI en el `.tsx` nuevo** | Test 4 de F2 (grep negativo de `style={{` y hex) + `uiDebtRatchet` verde como criterio de fase. |
| Comprimir confirms reduce fricción de 2 side effects externos | Flag default OFF citando la excepción dura (1); el resumen **aumenta** la información (hoy el operador confirma el commit sin ver qué se disparará); idempotencia de 60s del trigger sigue vigente; caminos viejos intactos. |
| Fallo parcial deja estado intermedio | Por diseño: corte honesto, **sin rollback**, estado por paso y CTA manual. C8 evita afirmar certezas falsas. |
| Vitest no renderiza React (`@testing-library/react` y `jsdom` NO instalados) | **Gap estructural declarado.** Toda la lógica vive en `publishChain.ts` (10 tests deterministas); los greps fijan el cableado; la interacción se verifica a mano. |
| La sesión paralela toca estos archivos | Anclar por CONTENIDO; commit con pathspec explícito. |

## 6. Fuera de scope (v2)

- Rollback/undo de un commit o de un pipeline disparado.
- Monitoreo continuo del pipeline tras el disparo (eso es el plan **103**).
- Cablear `beforeCommit` con el preflight del 93 (**violaría su HITL**: es informativo y nunca
  bloquea — C5).
- Tocar `CommitPipelineModal` / `TriggerPipelineSection` como flujos (solo se corrige un texto).
- Endpoints nuevos: **cero**. El único backend es la flag.
- Extender la cadena al Publicador de Soluciones (215) o al Centro de Despliegues (120): son
  otros dominios con su propio HITL.

## 8. Orden de implementación (v2)

1. F0 — flag 6 patas con `requires=PANEL` + ratchet en ambos scripts + tests.
2. F1 — `publishChain.ts` + 10 tests (corazón puro, sin consumidores).
3. F2 — modal con deuda UI cero + 6 tests. **Correr `uiDebtRatchet` acá, no al final.**
4. F3 — montaje en las 2 secciones + gates.
5. F4 — corregir el copy stale del 501 + centinela + huella.

## 9. Definición de Hecho (v2)

- F0: 5 verdes + `test_harness_flags_requires.py` verde + archivo en **ambos** ratchets.
- F1: 10 verdes + `tsc` 0.
- F2: 6 verdes + **`uiDebtRatchet` verde** + `grep 'style={{'` = 0 en el archivo nuevo.
- F3: con flag OFF el botón no existe; vitest preexistentes verdes sin modificar.
- F4: copy corregido + centinela verde + huella registrada.
- **Global:** cero endpoints nuevos; cero rieles paralelos; **ningún preset ADO bloqueado**;
  ante fallo nunca se deshace nada ni se afirma una certeza que no se tiene.
- Impacto en los 3 runtimes (Codex CLI / Claude Code CLI / GitHub Copilot Pro): **NINGUNO** —
  frontend + 1 flag; verificable por grep de `publishChain|one_click_publish` fuera de
  `frontend/` + `backend/config.py` + `backend/services/harness_flags*`.

---

## 10. Recomendación del juez sobre la prioridad

**Construir DESPUÉS del 98 y del 99.** Aquellos cierran gaps con beneficio ya pagado o defectos
en producción; este agrega comodidad sobre un flujo que —tras el fix del branch y el commit ADO
real— **ya funciona de punta a punta**. El módulo `publishChain.ts` es barato y de buena
factura; el resto es UI. Si hay que elegir uno solo de los tres supervivientes, **no es este**.
