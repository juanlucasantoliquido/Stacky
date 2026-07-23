# Plan 184 — Hoja de ruta de integración de la serie DB Compare: cierre del portafolio, mapa de colisiones VIVO y gates

**Estado:** CRITICADO v2 — RE-SCOPEADO POR VIGENCIA (v1 -> v2, 2026-07-23, juez StackyArchitectaUltraEficientCode vía `criticar-y-mejorar-plan`). v1 PROPUESTO 2026-07-18.

**Veredicto sobre v1: RECHAZADO por vigencia (C1, C2 BLOQUEANTES) → reescrito a v2.** La premisa central del v1 (ordenar la integración de 8 planes pendientes) quedó obsoleta: **7 de las 8 capas (157, 178-183) ya están IMPLEMENTADAS y MERGEADAS a main (consolidación 2026-07-20)**, verificado contra código el 2026-07-23 (§0). La única capa pendiente es la **176** (en re-crítica v2 por sesión paralela en este momento). Este v2 re-scopea la hoja de ruta a lo que REALMENTE falta: (GATE-0) verificar la coherencia post-merge de lo ya integrado, y (capa única) integrar el 176 contra el main real.

## Changelog v1 -> v2

- **C1 (BLOQUEANTE, vigencia):** el v1 ordenaba implementar 8 planes "en papel"; 7 ya están en main. Evidencia verificada 2026-07-23 en §0 (archivos, firmas, rutas y tests existentes). Incluso el contexto de la re-crítica afirmaba "157 sin implementar": FALSO contra código (`dbcompare_config_import.py`, `MigrationPanel.tsx`, rutas `import-config` en `api/db_compare.py:271,298`, 4 tests `test_plan157_*` — todo existe). Fix: re-scope total; §1-§3 del v1 degradados a registro histórico (§H).
- **C2 (BLOQUEANTE, normativo-vs-histórico):** el orden canónico §3 del v1 (183→179→182→157→176→181→178→180) NO se ejecutó — los planes se implementaron en worktrees paralelos y se consolidaron juntos el 2026-07-20. Mantenerlo como instrucción induciría a un modelo menor a "implementar" capas ya hechas o a exigir un orden que ya no existe. Fix: el único orden vivo es GATE-0 → capa 176.
- **C3 (IMPORTANTE, drift del orden §2.1):** el orden vertical "canónico" del v1 ya NO coincide con main: el bloque de ambientes (157) quedó ANTES del sandbox (183) — `DbComparePage.tsx:188` (`EnvironmentsPanel` config in-place) precede a `:191` (`DemoSandboxPanel`); el v1 mandaba lo inverso (bloques 3-4). Un gate "verificación visual del orden §2.1" fallaría contra la realidad mergeada y verde. Fix: §2 v2 re-ancla el canon al ORDEN OBSERVADO de main; el 176 monta `GatesPanel` por símbolo debajo de `SummaryHero` (`:218`).
- **C4 (IMPORTANTE, colisiones resueltas de facto):** las reglas condicionales "quien mergea segundo combina" (§2.4/§2.5 v1) quedaron determinadas: solo falta el 176, ergo **el 176 SIEMPRE combina**. Estado actual verificado: `create_run` solo tiene `initiated_by` (`dbcompare_runs.py:130`); `generate_parity_bundle*` solo tiene `data_merge_mode` (`dbcompare_scripts.py:720,949`); `excluded_keys` NO existe aún (0 hits en backend y frontend). Fix: §2 v2 lo da como precondición verificada, no como regla bidireccional.
- **C5 (IMPORTANTE, S176 y regresión compuesta):** la lista S176 sigue correctamente diferida al doc v2 del 176, pero la "regresión compuesta acumulada" del v1 (S183+S179+S182+S157) quedó corta e hipotética: hoy la regresión de la capa 176 es contra TODO lo mergeado. Fix: §4 v2 enumera la lista literal contra los tests que EXISTEN en el repo (verificados por glob 2026-07-23).
- **C6 (IMPORTANTE, hueco de verificación post-merge):** la consolidación 2026-07-20 fue en paralelo (no por el orden del v1) y el gotcha del duplicado silencioso aplica a merges cruzados; el v1 no contemplaba verificar lo YA integrado. Fix: **[ADICIÓN ARQUITECTO] GATE-0** (§1): verificación comandable, hoy, de los contratos congelados de las 7 capas en main.
- **C7 (MENOR):** el riesgo R2 del v1 ("la sesión paralela implementa algo por su cuenta") se MATERIALIZÓ en su forma máxima. Se conserva como lección en §H.
- **C8 (MENOR):** DoD global del v1 ("8 capas mergeadas EN EL ORDEN §3") inválido e incumplible retroactivamente. Fix: DoD v2 (§6) = GATE-0 verde + 176 integrado + suite compuesta final verde + docs actualizados.
- **C9 (MENOR):** las citas de línea del doc 176 apuntan al main de 2026-07-18; tras 7 merges driftearon. La regla transversal del v1 (anclar por símbolo, líneas = evidencia histórica) se conserva y se ELEVA: para la capa 176 es obligatorio re-anclar cada zona contra el main real antes de editar. El 176 está en re-crítica v2 por otra sesión AHORA: este 184 cita al 176 por número y símbolo, nunca por línea de su doc.

---

## §0. Estado real verificado del portafolio (2026-07-23, contra código en main)

| Plan | Estado doc | Estado CÓDIGO (evidencia verificada) |
|---|---|---|
| 157 config in-place + import web.config + MigrationPanel | IMPLEMENTADO (TERMINADO-POR-SUPERVISOR 2026-07-18) | `services/dbcompare_config_import.py` existe; rutas `POST /environments/import-config` (`api/db_compare.py:271`) y `/confirm` (`:298`) + `_egress_selfcheck` (`:260`); `MigrationPanel.tsx`, `EnvSetupWizard.tsx`, `CredentialWarningBanner.tsx` existen; `DbComparePage.tsx:188` (panel arriba gated `configInPlace`), `:262` (fallback), `:267` (`<MigrationPanel>`); tests `test_plan157_dbcompare_{webconfig_parse,import_api,secret_guardrails,ux_flags}.py` existen |
| 176 triage + gates + claves naturales | **PENDIENTE — única capa restante.** En re-crítica v2 por sesión paralela (2026-07-23) | 0 hits de `GatesPanel`, `excluded_keys`, `getTriage` en frontend/backend; `create_run` sin kwargs del 176 |
| 178 radar de ambientes | IMPLEMENTADO/MERGEADO 2026-07-20 | `dbcompare_watch.py`, `dbcompare_baseline.py`, `api/db_compare_watch.py` existen; `initiated_by` en `create_run` (`dbcompare_runs.py:130`); `EnvironmentRadar` montado (`DbComparePage.tsx:195`); `export const DbCompareWatch` (`endpoints.ts:4664`); 6 tests `test_plan178_*.py` |
| 179 fidelidad snapshot v2 | IMPLEMENTADO/MERGEADO 2026-07-20 | `test_plan179_{snapshot_v2,diff_v2}.py` existen |
| 180 puente diff→repo | IMPLEMENTADO/MERGEADO 2026-07-20 | `dbcompare_repo_scripts.py`, `api/db_compare_repo.py` existen; `RepoCoveragePanel` montado (`DbComparePage.tsx:241`); `export const DbCompareRepo` (`endpoints.ts:4692`); 4 tests `test_plan180_*.py` |
| 181 masking data-diff | IMPLEMENTADO/MERGEADO 2026-07-20 | `dbcompare_masking.py`, `api/db_compare_masking.py`, `DataMaskingBar.tsx` existen; `export const DbCompareMasking` (`endpoints.ts:4657`); 4 tests `test_plan181_*.py` |
| 182 scripts de datos v2 MERGE | IMPLEMENTADO/MERGEADO 2026-07-20 | kwarg `data_merge_mode` en emisor y bundle (`dbcompare_scripts.py:720,949,1198`); 3 tests `test_plan182_*.py` |
| 183 sandbox demo | IMPLEMENTADO/MERGEADO 2026-07-20 | `dbcompare_demo.py`, `api/db_compare_demo.py`, `DemoSandboxPanel` montado (`DbComparePage.tsx:191`); `export const DbCompareDemo` (`endpoints.ts:4639`); 4 tests `test_plan183_*.py` |

Nota de método: TODA afirmación de esta tabla se re-verifica con los comandos de GATE-0 (§1) antes de abrir la capa 176 — este doc también puede quedar stale.

---

## §1. [ADICIÓN ARQUITECTO] GATE-0 — verificación post-merge comandable de lo ya integrado

Motivo (C6): las 7 capas entraron a main por consolidación paralela de ramas, el escenario EXACTO del gotcha "duplicado silencioso" (git 3-way fusiona sin conflicto dos adiciones de la misma línea de cierre). Nadie corrió la "suite compuesta final" del v1 como acto único. GATE-0 la reemplaza por una verificación barata, literal y repetible. **Correr GATE-0 (i) una vez AHORA para sellar la consolidación 2026-07-20 y (ii) de nuevo como precondición de la capa 176.**

Comandos (desde `Stacky Agents/`; backend con el venv del repo, fallback `./.venv/`):

1. **Compilación:** `cd backend && "./venv/Scripts/python.exe" -m compileall services api -q` (exit 0).
2. **Tipos frontend:** `cd frontend && npx tsc --noEmit` (exit 0).
3. **Greps de contratos congelados (conteo EXACTO, cada uno):**
   - `grep -c "export const DbCompareDemo" frontend/src/api/endpoints.ts` == 1; ídem `DbCompareMasking`, `DbCompareWatch`, `DbCompareRepo`; `grep -c "export const DbCompare = " frontend/src/api/endpoints.ts` == 1.
   - `grep -c "def create_run" backend/services/dbcompare_runs.py` == 1 y `grep -c "initiated_by" backend/services/dbcompare_runs.py` >= 1 en la firma (`:130`).
   - `grep -c "data_merge_mode: bool = False" backend/services/dbcompare_scripts.py` == 2 (emisor + bundle).
   - `grep -c "import-config" backend/api/db_compare.py` >= 2 (ruta + confirm).
   - `grep -cE "register_blueprint.*(db_compare_demo|db_compare_masking|db_compare_watch|db_compare_repo)" backend/api/__init__.py` == 4.
4. **Suites por archivo (pytest SIEMPRE por archivo; nunca full-suite — contaminación cross-run conocida):** los 27 archivos backend de la columna (b) de §4 + `pytest tests/test_harness_flags.py -q` + `pytest tests/test_harness_flags_requires.py -q`.
5. **harness_defaults.env:** regenerar por `scripts/export_harness_defaults.py` y `git diff` vacío (si difiere: drift real, reportar, NO commitear a mano).
6. **Vitest por archivo:** `npx vitest run` sobre `demoLogic.test.ts`, `wizardLogicDemo.test.ts`, `maskingLogic.test.ts`, `radarLogic.test.ts`, `repoCoverageLogic.test.ts`, `migrationPanelLogic.test.ts` (rutas reales verificadas: los 3 primeros bajo `components/dbcompare/__tests__/` los otros en `components/dbcompare/` raíz).

Criterio binario: TODO verde ⇒ consolidación sellada. CUALQUIER rojo ⇒ parar, pegar output, reportar al operador (HITL); prohibido "arreglar de paso".

---

## §2. Mapa de colisiones VIVO (solo 176 vs main actual)

Regla transversal (heredada del v1, ELEVADA por C9): los números de línea de los docs — incluido este — son evidencia histórica; toda inserción se ancla POR SÍMBOLO. Antes de editar cada archivo, re-localizar el símbolo con grep.

| Archivo | Qué agrega/edita el 176 | Estado del terreno en main (verificado) | Regla de composición |
|---|---|---|---|
| `backend/services/dbcompare_runs.py` | kwargs keyword-only "modo snapshot histórico" en `create_run` | firma actual: `create_run(source_alias, target_alias, *, mode="fresh", initiated_by="operator")` (`:130`), con recordatorio de merge en comentario `:131-134` | el 176 COMBINA: agrega sus kwargs tras `mode`, orden alfabético, defaults que preservan main; re-corre `test_plan123_dbcompare_runs.py` + `test_plan178_*.py` |
| `backend/services/dbcompare_scripts.py` | `excluded_keys: set[str] \| None = None` en `generate_parity_bundle`/`_from_diff` | firmas ya tienen `data_merge_mode: bool = False` (`:720,949`) | el 176 COMBINA en la MISMA firma; re-corre `test_plan182_*` + `test_plan125_dbcompare_bundle.py` + `test_plan126_dbcompare_data_scripts.py` |
| `backend/api/db_compare.py` | campo aditivo en health, rutas triage/gates/re-verify/export, extensión `_scripts_allowlist`, `excluded_keys` en generate, claves naturales en data routes | ya contiene las rutas del 157 (`:271,298`) y el `get_run_route` enmascarado del 181 — NO tocar ninguno de los dos | rutas nuevas como bloques aditivos; gate: `compileall` + `test_plan122/123_dbcompare_api.py` + `test_plan157_dbcompare_import_api.py` + `test_plan181_api.py` |
| `backend/services/dbcompare_data.py` | claves naturales | sin colisión (nadie más lo tocó en la serie) | directo; gotcha conocido: `test_run_data_diff` flaky por timing ~1/5, re-correr aislado antes de culpar al cambio |
| `frontend/src/components/dbcompare/DbComparePage.tsx` | `GatesPanel` + estado/fetch + reemplazo de catches silenciosos | orden REAL de main (canon v2): header → `EnvironmentsPanel` config-in-place (`:188`) → `DemoSandboxPanel` (`:191`) → Settings (`:193`) → `EnvironmentRadar` (`:195`) → `RunsTimeline` (`:202`) → results [`SummaryHero` (`:218`) → … → `DataParitySection` (`:240`) → `RepoCoveragePanel` (`:241`)] → `MigrationPanel` (`:267`) | `GatesPanel` se monta por símbolo INMEDIATAMENTE DESPUÉS de `SummaryHero` dentro de `results`; PROHIBIDO reordenar bloques existentes |
| `frontend/src/components/dbcompare/DataParitySection.tsx` | catch + picker + claves naturales | ya contiene `DataMaskingBar` (181) en la zona `done` | zonas por símbolo; no tocar el render del masking |
| `frontend/src/components/dbcompare/SummaryHero.tsx` | edición del 176 (único de la serie que la edita) | sin colisión viva | directo |
| `frontend/src/api/endpoints.ts` | métodos nuevos DENTRO del namespace `DbCompare` existente (`:4374`) | ya existen 4 objetos nuevos al final (`:4639-4692`) | extender el namespace, NO crear objeto nuevo; gate: `grep -c "export const DbCompare = "` == 1 |
| `tablePrefsLogic.ts` (nuevo) + `dbcompare.module.css` | archivo nuevo + clases `.gates*`/`.triage*` append | — | prefijo propio, tokens `--dbc-*`, append al final |
| Registro flags/tests (`harness_flags.py`, `config.py`, `test_harness_flags_requires.py`, runners sh+ps1) | bloque aditivo `# Plan 176` | familia de archivos con MÁXIMA probabilidad de duplicado silencioso | gate §2.9 del v1 conservado: `compileall` + `test_harness_flags*.py` + regenerar `harness_defaults.env` POR SCRIPT |

Resoluciones H1-H3 del v1: H1 y H2 quedaron absorbidas por la implementación real del 157 (el aviso "<2 ambientes" y el mapa de intersecciones ya son código en main; verificar conducta, no re-litigar docs); H3 quedó implementada tal cual en el 183. Se conservan en §H como registro.

---

## §3. Ruta restante (capa única: 176)

**Precondiciones DURAS, en orden:**
1. **GATE-0 verde** (§1) contra el main del momento.
2. **El doc 176 tiene v2 de `/criticar-y-mejorar-plan`** — en curso por sesión paralela (2026-07-23). PROHIBIDO abrir la rama con el 176 en v1. Al llegar su v2: re-verificar §2 de ESTE plan contra las zonas/archivos del 176 v2; si difieren, actualizar el 184 ANTES de implementar.
3. **Re-listar en frío** `docs/` + `git status`/`git log` (sesión paralela activa; precedente: este mismo re-scope).
4. Regla git del árbol compartido: commits SOLO con pathspec explícito; PROHIBIDO amend/reset/stash/checkout de ramas ajenas.

**Ejecución:** 1 rama = 1 sesión de `/implementar-plan-stacky` con DOS docs a la vista (176 v2 + este 184 v2). El doc 176 manda el QUÉ; este 184 manda el DÓNDE (§2) y los gates (§4). Ante conflicto doc-vs-184 en zona compartida: parar y reportar.

---

## §4. Gates de la capa 176

Formato: backend `cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/<archivo> -q` POR ARCHIVO; frontend `npx vitest run <archivo>` + `npx tsc --noEmit`.

- **(a) Suite propia S176:** la lista literal de tests que nombre el doc 176 v2 (se fija al abrir la capa; hoy deliberadamente no enumerable — C5).
- **(b) Regresión compuesta (lista LITERAL, todos existentes verificados por glob 2026-07-23):**
  `test_plan122_dbcompare_registry.py`, `test_plan122_dbcompare_api.py`, `test_plan122_dbcompare_snapshot.py`, `test_plan123_dbcompare_runs.py`, `test_plan123_dbcompare_api.py` (si existe; verificar con glob), `test_plan125_dbcompare_bundle.py`, `test_plan126_dbcompare_data_scripts.py`, `test_plan126_dbcompare_data_diff.py`,
  `test_plan157_dbcompare_webconfig_parse.py`, `test_plan157_dbcompare_import_api.py`, `test_plan157_dbcompare_secret_guardrails.py`, `test_plan157_dbcompare_ux_flags.py`,
  `test_plan178_flags.py`, `test_plan178_watch_store.py`, `test_plan178_sweep.py`, `test_plan178_events.py`, `test_plan178_baseline.py`, `test_plan178_api.py`,
  `test_plan179_snapshot_v2.py`, `test_plan179_diff_v2.py`,
  `test_plan180_extract.py`, `test_plan180_scanner.py`, `test_plan180_coverage.py`, `test_plan180_api.py`,
  `test_plan181_masking_core.py`, `test_plan181_prefs.py`, `test_plan181_response.py`, `test_plan181_api.py`,
  `test_plan182_data_merge_emitters.py`, `test_plan182_data_merge_bundle.py`, `test_plan182_data_merge_e2e_sqlite.py`,
  `test_plan183_demo_seed.py`, `test_plan183_demo_lifecycle.py`, `test_plan183_demo_api.py`, `test_plan183_demo_e2e.py`
  + SFLAGS (`test_harness_flags.py`, `test_harness_flags_requires.py` + regenerar `harness_defaults.env` por script) + SBASE (`compileall services api` + `tsc --noEmit`)
  + vitest: `demoLogic.test.ts`, `wizardLogicDemo.test.ts`, `wizardLogic.test.ts`, `maskingLogic.test.ts`, `radarLogic.test.ts`, `repoCoverageLogic.test.ts`, `migrationPanelLogic.test.ts` + los del 176 v2.
- **(c) Anti-duplicado:** greps de GATE-0 §1.3 + `grep -c "excluded_keys" backend/services/dbcompare_scripts.py` >= 2 con UNA sola aparición por firma + firma de `create_run` con `initiated_by` Y los kwargs del 176 UNA vez cada uno.
- **(d) Smoke sandbox (183 ya en main, gratis):** seed demo → comparar par → triage de ítems demo → excluir 1 → regenerar scripts → el excluido NO está en el bundle.

Criterio binario global: (a)+(b)+(c)+(d) verdes con output pegado en el PR. "Pasó todo" sin output NO cuenta.

---

## §5. Reglas para el implementador (modelos menores)

1. NO implementar los planes 157/178-183: YA ESTÁN EN MAIN (§0). Si un doc de la serie parece "pendiente", verificar contra código con los comandos de §0/GATE-0 antes de creer el papel.
2. Anclar por símbolo, nunca por línea (§2). Re-grep antes de cada hunk.
3. Si CUALQUIER gate falla: parar, pegar output, reportar. Prohibido aflojar asserts, editar tests preexistentes no declarados o saltear gates.
4. Al terminar: actualizar encabezado de estado del doc 176 y de ESTE 184 (regla de la casa) y dejar los gates en el PR.
5. HITL: el operador dispara la capa; nada corre solo.

## §6. DoD global v2

1. GATE-0 verde y documentado (sella la consolidación 2026-07-20).
2. Capa 176 integrada con gates (a)-(d) verdes y output en el PR.
3. `create_run` y `generate_parity_bundle*` con firmas COMBINADAS (kwargs de 176 + `initiated_by` + `data_merge_mode`) y los tests de todos los planes involucrados verdes.
4. `endpoints.ts` con namespace `DbCompare` único y extendido; 4 objetos nuevos intactos (1 ocurrencia c/u).
5. Encabezados de estado: 176 → IMPLEMENTADO; 184 → EJECUTADO.
6. `harness_defaults.env` regenerado por script, diff limitado a las claves del 176.

## KPIs binarios v2

| KPI | Criterio binario | Verificación |
|---|---|---|
| KPI-1 | §0 refleja el código real: cada fila tiene evidencia archivo:línea o glob verificable | correr GATE-0 §1.3 |
| KPI-2 | La ruta viva tiene UNA sola capa pendiente y sus precondiciones son externas explícitas (176 v2, GATE-0) — cero dependencias fantasma | leer §3 |
| KPI-3 | La regresión compuesta de la capa 176 es una lista LITERAL de archivos existentes (única diferida: S176, fijada al abrir la capa con justificación) | glob de §4(b) |
| KPI-4 | GATE-0 es comandable de punta a punta (ningún paso "a ojo" salvo el smoke §4(d), que es HITL por diseño) | leer §1 |
| KPI-5 | Cero instrucciones de implementar planes ya mergeados | leer §3/§5 |

## Riesgos v2

| # | Riesgo | Mitigación |
|---|---|---|
| R1 | El 176 v2 (re-crítica en curso) cambia zonas/archivos y §2 queda stale | Precondición 2 de §3: re-verificar §2 contra el 176 v2 ANTES de abrir la rama |
| R2 | GATE-0 encuentra un rojo heredado de la consolidación paralela | Es EXACTAMENTE para eso: reportar al operador con output; no es bloqueo del 176 salvo que el rojo toque sus archivos |
| R3 | Duplicado silencioso al mergear el 176 (familia flags/endpoints) | Gates §4(c) + GATE-0 re-corrido post-merge |
| R4 | Flaky conocidos contaminan el veredicto (`test_run_data_diff` timing ~1/5; contaminación cross-run pytest/vitest) | SIEMPRE por archivo; re-correr aislado el flaky antes de culpar al cambio |
| R5 | Este 184 vuelve a quedar stale por la sesión paralela | Precondición 3 de §3 (re-listar en frío) — lección del propio v1 (C7) |

## Fuera de scope (sin cambios de fondo vs v1)

- Implementar el 176: lo hace `/implementar-plan-stacky` disparado por el operador (HITL).
- Criticar el 176: lo está haciendo su propio juicio en paralelo.
- Crear flags/endpoints/código de producto: el 184 no agrega superficies de runtime ("Flag: N/A — hereda las del 176").
- Automatizar el encadenamiento: PROHIBIDO por HITL.

---

## §H. Apéndice histórico (registro del v1, ya no normativo)

- El v1 (2026-07-18) definió: tabla maestra de 8 planes, mapa de colisiones §2.1-§2.10 por archivo compartido, orden canónico 183→179→182→157→176→181→178→180, gates compuestos acumulados S183…S180 y hallazgos H1-H3. Sirvió como mapa de colisiones DURANTE la implementación paralela (p.ej. el comentario de merge en `dbcompare_runs.py:131-134` cita su §2bis), pero su orden secuencial nunca se ejecutó: las capas se construyeron en worktrees paralelos y se consolidaron a main el 2026-07-20.
- H1 (lista corta del 157 en cinco §2bis) y H2 (ambigüedad CompareWizard 157-vs-183): resueltas por el código real mergeado. H3 (redundancia deliberada del 183: password dummy + microhunks wizard): implementada tal cual.
- Lección durable (C7): un roadmap de integración en un repo con sesiones paralelas activas DEBE incluir su propio gate de vigencia comandable (GATE-0) y asumir que puede despertar con el terreno ya tomado.

**Changelog interno:** v1 (2026-07-18) — propuesta inicial, 8 capas. v2 (2026-07-23) — RECHAZO por vigencia y re-scope: C1-C2 bloqueantes (7/8 capas ya en main, orden nunca ejecutado), C3 canon de `DbComparePage` re-anclado al main real, C4 combinación de firmas resuelta de facto (el 176 combina), C5 regresión compuesta literal contra tests existentes, C6 [ADICIÓN ARQUITECTO] GATE-0 post-merge comandable, C7-C9 menores (riesgo materializado, DoD, drift de citas del 176).
