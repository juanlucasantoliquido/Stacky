# Plan 184 — Hoja de ruta de integración de la serie DB Compare: orden canónico, mapa maestro de colisiones y verificación compuesta por capa

**Estado:** PROPUESTO (v1, 2026-07-18, autor Fable 5 vía `proponer-plan-stacky`).

**Serie:** Comparador de BD — capa 0 TRANSVERSAL (integración). No agrega producto: convierte las capas 1-8 en papel (157, 176, 178-183) en una ruta EJECUTABLE por `/implementar-plan-stacky`, con orden canónico, mapa maestro de colisiones (hoy disperso en ocho §2bis) y gates de verificación compuesta por capa. HITL: este plan NO ordena auto-implementar nada — es el mapa; el operador dispara cada capa cuando quiere, como siempre.

---

## §1. Tabla maestra del portafolio

| Plan | Título corto | Estado del doc | Commits (v1 / v2) | Archivos que TOCA (según su doc) | Promete NO tocar |
|---|---|---|---|---|---|
| 157 | Config in-place + import web.config + Panel Migración | CRITICADO v2 APROBADO-CON-CAMBIOS (2026-07-17) | previo a esta serie / — | `api/db_compare.py` (rutas import-config + `_egress_selfcheck`, 157:221-230,256), `dbcompare_config_import.py` (nuevo), `EnvSetupWizard.tsx` + `CredentialWarningBanner.tsx` + `MigrationPanel.tsx` + `migrationPanelLogic.ts` (nuevos), `DbComparePage.tsx` (mover `EnvironmentsPanel` de `:200` arriba + CTA vacío + reemplazar `scriptsSection:203-230` por MigrationPanel, 157:359-384), `endpoints.ts` (extiende el namespace `DbCompare`, 157:284), registro de flags | blueprint nuevo (usa el `bp` existente, 157:221); ejecutar scripts |
| 176 | Triage curado + gates read-only + claves naturales + cierre + UX v2 | **PROPUESTO v1 — SIN CRITICAR** (sesión paralela, 2026-07-18) | 7120c2d2 / — | `api/db_compare.py` (health `:196`, endpoints triage `:270+`, export md `:287`, allowlist `:423-425`, `generate_scripts_route:427-431`, gates `:468`, data sin PK `:662-675`, re-verify `:767`, `create_run` kwargs `:854-861`), `dbcompare_scripts.py` (`excluded_keys` keyword-only en `generate_parity_bundle`/`_from_diff`, 176:411-413), `dbcompare_data.py` (176:630), `dbcompare_runs.py` (modo snapshot histórico, 176:826-854), `DbComparePage.tsx` (176:338,366-368,574-575,823-824), `SummaryHero.tsx` (176:336,364,818-821,840), `DataParitySection.tsx` (176:627,631,685,822-824), `endpoints.ts` (176:339,576,633,827), `tablePrefsLogic.ts` (nuevo), registro de flags | — (es el plan MÁS ancho del portafolio) |
| 178 | Radar de ambientes (vigía + matriz + baseline + tendencia) | CRITICADO v2 (v1 RECHAZADA: C1 cosecha, C2 baseline vs prune) | d9463212 / 9ff7a608 | `dbcompare_watch.py`/`dbcompare_baseline.py`/`api/db_compare_watch.py` (nuevos), `app.py` (loop), `dbcompare_runs.py` (kwarg `initiated_by` en `create_run:130` + dict `:154-162`), `endpoints.ts` (append `DbCompareWatch`), `DbComparePage.tsx` (1 import + 1 JSX), `dbcompare.module.css`, `api/__init__.py`, registro de flags | `api/db_compare.py`, `SummaryHero.tsx`, `dbcompareTypes.ts`, `runHistory.ts`, `dbcompare_snapshot.py` (178:1368,1427 — baseline autocontenido por COPIA, fix C2, 178:99) |
| 179 | Fidelidad Snapshot v2 (type_detail + diff quirúrgico) | CRITICADO v2 (v1 RECHAZADA: C1 `test_plan122:77` asserta `version == 1`) | fc50bf84 / 71eedbb0 | `dbcompare_snapshot.py`, `dbcompare_diff.py`, registro de flags, **+2 líneas DECLARADAS en `tests/test_plan122_dbcompare_snapshot.py::test_snapshot_estructura_v1`** (pin flag OFF — única edición de test permitida, 179:69,93,400-422) | frontend entero, `api/`, `dbcompare_runs.py`, `dbcompare_scripts.py` |
| 180 | Puente diff→repo (índice de scripts ticketeados + cobertura) | CRITICADO v2 (v1 RECHAZADA: C1 walk sin cap en GET) | accebc5c / 3888b381 | `dbcompare_repo_scripts.py`/`api/db_compare_repo.py` (nuevos), `RepoCoveragePanel.tsx`+`repoCoverageLogic.ts`+`repoCoverageTypes.ts` (nuevos), `DbComparePage.tsx` (1 import + 1 JSX), `endpoints.ts` (append `DbCompareRepo`), `dbcompare.module.css`, `api/__init__.py`, registro de flags | `api/db_compare.py`, `dbcompare_snapshot.py`, `dbcompare_diff.py`, `dbcompare_runs.py`, `dbcompare_scripts.py`, `SummaryHero.tsx` (180:835) |
| 181 | Masking de secretos en el data-diff | CRITICADO v2 (v1 RECHAZADA: C1 `GET /runs` servía data_diff crudo) | 814f8f23 / 5e72f28e | `dbcompare_masking.py`/`api/db_compare_masking.py` (nuevos), `api/db_compare.py` (SOLO `get_run_route:222-230`), **`dbcompare_runs.py` (SOLO 1 línea: `list_runs:227` excluye `data_diff` — fix C1, 181:67,72)**, `DataParitySection.tsx` (2 hunks zona `:152-155`), `DataMaskingBar.tsx`+`maskingLogic.ts` (nuevos), `endpoints.ts` (append `DbCompareMasking`), `dbcompare.module.css`, `api/__init__.py`, registro de flags | `dbcompare_data.py`, `dbcompare_scripts.py` (doctrina scripts intactos) |
| 182 | Scripts de datos v2 (MERGE idempotente por dialecto) | CRITICADO v2 (v1 RECHAZADA: C1 backups single-shot ⇒ el claim "bundle re-ejecutable" era falso; idempotencia real = piezas DML) | 73d82457 / 0326d80b | `dbcompare_scripts.py` (emisor + kwarg `data_merge_mode` + `_DATA_DML_KINDS`), registro de flags | `api/db_compare.py`, `dbcompare_data.py`, `dbcompare_sqlvalues.py`, `dbcompare_sqlnames.py`, frontend entero |
| 183 | Sandbox demo (par sqlite RS-like, 1 click) | CRITICADO v2 (v1 RECHAZADA: C1 password dummy en keyring REQUERIDA — `open_engine→get_credential` la exige; C2 DDL sin item info standalone) | 9c960484 / 1602429a | `dbcompare_demo.py`/`api/db_compare_demo.py` (nuevos), `DemoSandboxPanel.tsx`+`demoLogic.ts` (nuevos), `DbComparePage.tsx` (1 import + 1 JSX), `endpoints.ts` (append `DbCompareDemo`), **`wizardLogic.ts` (2 microhunks) + `CompareWizard.tsx` (3 microhunks)** (183:120-123), `dbcompare.module.css`, `api/__init__.py`, registro de flags | TODO el motor (`dbcompare_registry.py` incluido — usa su API pública, 183:96) |

Común a los 8: `services/harness_flags.py`, `config.py`, `tests/test_harness_flags_requires.py`, `scripts/run_harness_tests.sh` + `.ps1` (bloques ADITIVOS de registro de flags/tests) y `harness_defaults.env` REGENERADO por `scripts/export_harness_defaults.py` (nunca a mano).

---

## §2. Mapa maestro de colisiones (por archivo compartido)

**Universo y claim negativo de cobertura (comando citado):** el superset de candidatos se construyó con
`cd "Stacky Agents/docs" && for f in "DbComparePage.tsx" "endpoints.ts" "api/db_compare.py" "DataParitySection.tsx" "dbcompare_runs.py" "dbcompare_scripts.py" "dbcompare.module.css" "api/__init__.py" "harness_flags.py" "wizardLogic.ts" "CompareWizard.tsx" "SummaryHero.tsx" "dbcompare_data.py" "dbcompare_snapshot.py" "dbcompare_diff.py"; do grep -l -- "$f" 157_*.md 176_*.md 178_*.md 179_*.md 180_*.md 181_*.md 182_*.md 183_*.md; done`
— ese grep detecta MENCIONES (muchos docs citan archivos que prometen NO tocar, p.ej. `SummaryHero.tsx` aparece en 7 docs pero solo el 176 la edita); la clasificación tocar-vs-mencionar de cada fila sale de las tablas §2bis/listas de archivos de cada doc, citadas abajo. Ningún candidato del superset quedó sin fila o sin veredicto.

**Regla transversal de anclaje:** los números de línea citados en los docs son EVIDENCIA HISTÓRICA (válida al momento de escribirse contra main), NUNCA anclas de merge. Toda inserción se ancla POR SÍMBOLO (componente/función vecina) según este mapa. El doc de cada plan manda por símbolo, no por línea.

### §2.1 `frontend/src/components/dbcompare/DbComparePage.tsx` — 5 planes lo editan (157, 176, 178, 180, 183)

Orden vertical CANÓNICO final de la página (de arriba hacia abajo; cada plan monta anclado al símbolo vecino):

| # | Bloque | Dueño | Ancla de inserción |
|---|---|---|---|
| 1 | `<header>` | main | — |
| 2 | `driverWarning` | main | — |
| 3 | `<DemoSandboxPanel>` | 183 | inmediatamente DESPUÉS del bloque `missingDrivers` |
| 4 | Sección "Bases de datos configuradas" (`EnvironmentsPanel` movido + CTA vacío) | 157 | inmediatamente DESPUÉS de `<DemoSandboxPanel>` (si la capa 183 ya está; si no, después de `missingDrivers`) |
| 5 | `<DbCompareSettingsSection>` | main | — |
| 6 | `<EnvironmentRadar>` | 178 | inmediatamente DESPUÉS de `<DbCompareSettingsSection>`, ANTES de `<RunsTimeline>` |
| 7 | `<RunsTimeline>` | main | — |
| 8 | Bloque `view` (wizard/progress/results). Dentro de `results`: `SummaryHero` → `<GatesPanel>` (176, "debajo de SummaryHero", 176:574-575) → `FiltersBar` → mapa/lista → `<DataParitySection>` (con `<DataMaskingBar>` del 181 ADENTRO, zona del render `done`) → `<RepoCoveragePanel>` (180) | main + 176 + 181 + 180 | por símbolo dentro del fragmento `results` |
| 9 | `<MigrationPanel>` | 157 | REEMPLAZA la `scriptsSection` del final (157:384) |
| 10 | `<ObjectDrilldown>` (overlay) + resto | main | — |

Reglas: los montajes de 178/180/183 son "1 import + 1 JSX" cada uno (declarado en sus docs); el 157 es el ÚNICO que reordena bloques existentes (por eso su posición en el orden canónico §3 es ANTES del 176, que agrega estado/fetch/catches — 176:366-368,823-824); el 176 además reemplaza los `.catch(() => ...)` silenciosos (`DbComparePage.tsx:50,55`) — zona de estado, no de montaje, disjunta de todos. Gate post-merge de CADA capa que toque este archivo: `npx tsc --noEmit` + verificación visual del orden §2.1 + grep de 1 ocurrencia del componente montado.

### §2.2 `frontend/src/api/endpoints.ts` — 6 planes lo editan (157, 176, 178, 180, 181, 183)

Dos clases de edición, con reglas distintas:

- **Extensiones del namespace `DbCompare` EXISTENTE** (objeto que arranca en `:3967`): 157 (`importConfig`/`confirmImport`, 157:284) y 176 (`getTriage`/`putTriageItem`/gates/export, 176:339,576). Van DENTRO del objeto, ancladas al final de sus métodos; conflicto esperable entre 157 y 176: adyacencia trivial — conservar ambos.
- **Objetos NUEVOS append al FINAL del archivo**: `DbCompareDemo` (183), `DbCompareMasking` (181), `DbCompareWatch` (178), `DbCompareRepo` (180). El final REAL del archivo se verifica con `tail -n 3` al implementar (el 181 v2 documenta que hoy el último export es `Incidents`, `:4155` — 181:74; eso DRIFTEA con cada capa: regla por símbolo "después del último `export const` existente").
- Gate anti-duplicado-silencioso (OBLIGATORIO tras cada merge que lo toque): `npx tsc --noEmit` + `grep -c "export const <ObjetoNuevo>" endpoints.ts` == 1 por CADA objeto ya integrado + `grep -c "export const DbCompare = " endpoints.ts` == 1.

### §2.3 `backend/api/db_compare.py` — 3 planes lo editan (157, 176, 181)

| Plan | Zona (símbolos) | Cita |
|---|---|---|
| 157 | rutas NUEVAS `import-config`/`confirm` + helper `_egress_selfcheck` + gate `_require_webconfig_import_enabled` | 157:221-230,256 |
| 176 | `health_route` (campo aditivo), rutas nuevas de triage/gates/re-verify, `export_run_markdown_route`, `_scripts_allowlist` (extensión aditiva), `generate_scripts_route` (pasa `excluded_keys`), `data_candidates_route`/`start_data_diff_route` (claves naturales) | 176:196,270,287,423-431,662-675,767 |
| 181 | SOLO el cuerpo de `get_run_route` (2 líneas: `jsonify(run)` → `jsonify(dbcompare_masking.apply_to_run_response(run))`) | 181:71 (el juez verificó: 0 menciones de `get_run_route` en el doc 176) |

Zonas DISJUNTAS por símbolo. Composición: 157 y 176 agregan rutas (bloques nuevos — conflicto de adyacencia trivial); 181 edita un route existente que nadie más toca. Gate: `python -m compileall api/db_compare.py` + re-correr `test_plan122_dbcompare_api.py` + `test_plan123_dbcompare_api.py` + los tests de API de las capas ya integradas.

### §2.4 `backend/services/dbcompare_runs.py` — 3 planes lo editan (176, 178, 181)

| Plan | Zona | Cita |
|---|---|---|
| 178 | FIRMA de `create_run` (`:130`): kwarg keyword-only `initiated_by="operator"` + clave en el dict del run (`:154-162`) | 178:480,1379 (fix C3: colisión de firma con 176 DECLARADA como conocida) |
| 176 | "modo snapshot histórico": kwargs keyword-only ADICIONALES en `create_run` + lógica alrededor | 176:826-854 |
| 181 | 1 línea: filtro de metadata de `list_runs` (`:227`) excluye también `data_diff` | 181:67,72 |

Regla de composición de la FIRMA (la colisión más delicada del portafolio): `create_run` termina con LOS DOS sets de kwargs keyword-only — los del 176 (nombres según su doc v2 post-crítica) y el `initiated_by` del 178 — combinados en UNA firma, orden alfabético tras `mode`, TODOS con default que preserva la conducta de main. Quien mergea SEGUNDO combina y re-corre los tests de AMBOS planes + `test_plan123_dbcompare_runs.py`. `list_runs:227` (181) es ortogonal a ambos. Gate: grep de la firma final esperando ambos kwargs presentes UNA vez.

### §2.5 `backend/services/dbcompare_scripts.py` — 2 planes lo editan (176, 182)

176 agrega `excluded_keys: set[str] | None = None` (176:411-413) y 182 agrega `data_merge_mode: bool = False` a las MISMAS firmas (`generate_parity_bundle`, `generate_parity_bundle_from_diff`). Composables por diseño (filtrar → emitir): defaults inocuos, orden alfabético al combinar, el segundo re-corre `test_plan176_*` (los que su v2 nombre) + `test_plan182_data_merge_*` + `test_plan125_dbcompare_bundle.py` + `test_plan126_dbcompare_data_scripts.py`. En el orden canónico §3 el 182 aterriza PRIMERO ⇒ el que combina es el 176.

### §2.6 `frontend/src/components/dbcompare/DataParitySection.tsx` — 2 planes lo editan (176, 181)

176: catch silencioso (`:69`) + picker (`:121-145`) + claves naturales (176:627,685). 181: zona del render `done` (`:152-155`, import + `<DataMaskingBar>`) — 181:73 declara las zonas disjuntas. En el orden §3 el 176 va antes ⇒ el 181 ancla su JSX "inmediatamente ANTES de `<DataDiffTables>`" por símbolo sobre el archivo YA reformado.

### §2.7 `backend/api/__init__.py` — 4 planes lo editan (178, 180, 181, 183)

Cada uno agrega 2 líneas (import + `register_blueprint`) con el idioma de `:57`/`:118`. Cuatro blueprints nuevos comparten `url_prefix="/db-compare"` con nombres distintos (`db_compare_demo`, `db_compare_masking`, `db_compare_watch`, `db_compare_repo`) — Flask lo admite; las rutas no se pisan (verificado por cada doc contra la tabla `api/db_compare.py:52-411`). Conflicto esperable: adyacencia trivial. Gate: `compileall` + arranque de la app de test (los tests de API de cada capa ya lo cubren).

### §2.8 `frontend/src/components/dbcompare/dbcompare.module.css` — ≥5 planes lo editan (176, 178, 180, 181, 183; el 157 según sus F4/F5)

Regla única: SIEMPRE append al final, clases con prefijo propio del plan (`.demo*`, `.masking*`, `.radar*`, `.repoCoverage*`, `.gates*`/`.triage*`), tokens `--dbc-*` existentes. Gate: `npx tsc --noEmit` (los module.css tipados) + grep de cada clase nueva esperando 1 definición.

### §2.9 Registro de flags/tests — los 8 planes

`harness_flags.py` (FlagSpec + `_CURATED_DEFAULTS_ON` + `_CATEGORY_KEYS["comparador_bd"]`), `config.py`, `test_harness_flags_requires.py` (`_REQUIRES_MAP_FROZEN`), runners sh+ps1: bloques ADITIVOS con comentario `# Plan NN`. Este archivo-familia es donde el gotcha del duplicado silencioso es MÁS probable (misma línea de cierre agregada por dos ramas — gotcha documentado del repo). Gate OBLIGATORIO tras CADA capa: `python -m compileall services/harness_flags.py config.py` + `pytest tests/test_harness_flags.py -q` + `pytest tests/test_harness_flags_requires.py -q` + regenerar `harness_defaults.env` POR SCRIPT y verificar con `git diff` que solo agrega las claves de la capa.

### §2.10 Casos especiales (1 plan, registrados por excepcionalidad)

- `wizardLogic.ts` + `CompareWizard.tsx`: SOLO el 183 los edita (183:64,120-123). Ver HALLAZGO H2 (§Hallazgos) por la ambigüedad del 157:362 — resolución canónica: el aviso "<2 ambientes" del 157 se implementa en `DbComparePage.tsx` (dueño del estado `environments`), SIN tocar `CompareWizard.tsx`, preservando el claim del 183.
- `tests/test_plan122_dbcompare_snapshot.py`: SOLO el 179, +2 líneas DECLARADAS (pin flag OFF en `test_snapshot_estructura_v1` — 179:69,400-422). Ningún otro plan puede tocar tests preexistentes.
- `app.py`: SOLO el 178 (loop del vigía). `dbcompare_data.py`: SOLO el 176 (claves naturales, 176:630). `dbcompare_snapshot.py`/`dbcompare_diff.py`: SOLO el 179 (el 178 v2 resolvió su C2 con copia autocontenida del baseline, SIN tocar snapshot.py — 178:99,1427).

---

## §3. Orden canónico de implementación (con justificación por capa)

**Orden: 183 → 179 → 182 → 157 → 176 → 181 → 178 → 180.** Toda precondición apunta a una capa ANTERIOR (KPI-2). El orden propuesto por el orquestador se ADOPTA con una precisión extra en la capa 1 (keyring) y la resolución de la adyacencia 183/157 (§2.1 anclas 3-4).

| Capa | Plan | Por qué en esta posición | Precondiciones |
|---|---|---|---|
| 1 | 183 sandbox | No depende de NADIE del portafolio y da el carril de smoke para TODAS las capas siguientes (su §2ter mapea smokes de 176/178/179/181/182). Su única edición "de motor de UI" (wizard) no colisiona con nadie (§2.10) | `keyring` disponible en la máquina (el seed v2 lo EXIGE — 183 fix C1; verbo implícito "autenticar" del perímetro §P.3) |
| 2 | 179 fidelidad | Núcleo puro sin UI ni API; cero archivos compartidos con el resto (§2.10); su edición declarada de test es autónoma. Con el 183 adentro, su smoke (type_detail en `RTABL.MONTO_TOPE NUMERIC(10,2)`) corre contra el sandbox | capa 1 (solo para el smoke; técnicamente independiente) |
| 3 | 182 MERGE | Motor de scripts puro; aterriza su kwarg `data_merge_mode` ANTES de que el 176 agregue `excluded_keys` a las mismas firmas ⇒ el que combina es el 176 (el plan que igual va a pasar por crítica y puede absorber la guía §2.5). Smoke vía sandbox (data-diff RPARAM → `03_datos/`) | capa 1 (smoke) |
| 4 | 157 entrada | El ÚNICO que REORDENA `DbComparePage.tsx` (mueve `EnvironmentsPanel`, reemplaza `scriptsSection` por `MigrationPanel`) — hacerlo ANTES del 176 evita que el reordenamiento pise los montajes/estado del 176; sus rutas nuevas en `api/db_compare.py` aterrizan antes que las del 176 (misma razón) | capa 1 (el CTA demo del 183 ya montado define el ancla §2.1-4) |
| 5 | 176 triage/gates | El más grande y el que MÁS archivos comparte (§2.3-§2.6): entra con 157/179/182 ya adentro, así sus zonas componen contra un árbol estable y es ÉL quien combina los kwargs de `dbcompare_scripts.py` (§2.5) | **GATE DURO (precondición NO opcional): pasar por `/criticar-y-mejorar-plan` (está en v1, único del portafolio sin criticar) Y re-verificar este mapa §2 contra su v2 resultante — si la crítica mueve zonas/archivos, se actualiza el 184 ANTES de implementar la capa** |
| 6 | 181 masking | Sus 2 hunks de `DataParitySection.tsx` y su hunk de `get_run_route` se colocan por símbolo sobre el árbol CON el 176 adentro (las zonas del 176 ya no driftean más); su línea en `list_runs:227` compone con el modo histórico del 176 ya mergeado (§2.4) | capa 5 |
| 7 | 178 radar | Su kwarg `initiated_by` se COMBINA con los kwargs del 176 en la firma de `create_run` — con el 176 adentro, el 178 es "el segundo que combina" y su guía C3 lo contempla textualmente (178:480) | capa 5 (firma); capa 1 (smoke matriz/baseline vía sandbox) |
| 8 | 180 puente | El más independiente hacia atrás (módulos nuevos + 2 puntos de montaje); nadie depende de él; cierra el portafolio con el bloque `results` ya estabilizado por 176/181 | capa 1 (smoke con workspace de prueba) |

Precondición GLOBAL de CADA capa (verbo implícito, perímetro §P.3): antes de abrir la rama, re-listar `docs/` y `git status`/`git log` EN FRÍO — la sesión paralela está activa (precedente: colisión del número 171) y pudo implementar o renumerar algo; si la tabla §1 ya no refleja la realidad, actualizar el 184 primero.

---

## §4. Gates de verificación compuesta por capa

Formato de comandos: backend `cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/<archivo> -q` (fallback `./.venv/...`), SIEMPRE por archivo; frontend `cd "Stacky Agents/frontend" && npx vitest run <archivo>` + `npx tsc --noEmit`; global `cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m compileall services api`.

Cada capa K ejecuta (a) su suite, (b) la regresión compuesta ACUMULADA (lista literal), (c) los gates anti-duplicado de los archivos compartidos que tocó, (d) su smoke vía sandbox. Las suites por plan (listas literales):

- **S183** = `tests/test_plan183_demo_seed.py`, `tests/test_plan183_demo_lifecycle.py`, `tests/test_plan183_demo_api.py`, `tests/test_plan183_demo_e2e.py` + vitest `__tests__/demoLogic.test.ts`, `__tests__/wizardLogicDemo.test.ts`, `__tests__/wizardLogic.test.ts` (preexistente, sin editar)
- **S179** = `tests/test_plan179_snapshot_v2.py`, `tests/test_plan179_diff_v2.py` + los 22 archivos `test_plan12*dbcompare*.py` que su F4 lista (con la edición declarada de +2 líneas en `test_plan122_dbcompare_snapshot.py` ya aplicada)
- **S182** = `tests/test_plan182_data_merge_emitters.py`, `tests/test_plan182_data_merge_bundle.py`, `tests/test_plan182_data_merge_e2e_sqlite.py` + `tests/test_plan125_dbcompare_bundle.py`, `tests/test_plan126_dbcompare_data_scripts.py`
- **S157** = `tests/test_plan157_dbcompare_webconfig_parse.py`, `tests/test_plan157_dbcompare_import_api.py`, `tests/test_plan157_dbcompare_secret_guardrails.py`, `tests/test_plan157_dbcompare_ux_flags.py` + los vitest que su doc nombre
- **S176** = los tests que su doc v2 POST-CRÍTICA nombre (la lista se fija en el gate de la capa 5; hasta entonces es deliberadamente NO enumerable) + `tests/test_plan123_dbcompare_runs.py`, `tests/test_plan125_dbcompare_bundle.py` (por §2.4/§2.5)
- **S181** = `tests/test_plan181_masking_core.py`, `tests/test_plan181_prefs.py`, `tests/test_plan181_response.py`, `tests/test_plan181_api.py` + `tests/test_plan123_dbcompare_runs.py` + vitest `maskingLogic.test.ts`
- **S178** = `tests/test_plan178_flags.py`, `tests/test_plan178_watch_store.py`, `tests/test_plan178_sweep.py`, `tests/test_plan178_events.py`, `tests/test_plan178_baseline.py`, `tests/test_plan178_api.py` + vitest `radarLogic.test.ts`
- **S180** = `tests/test_plan180_extract.py`, `tests/test_plan180_scanner.py`, `tests/test_plan180_coverage.py`, `tests/test_plan180_api.py` + `tests/test_runtime_paths.py` + vitest `repoCoverageLogic.test.ts`
- **SFLAGS** (toda capa) = `tests/test_harness_flags.py`, `tests/test_harness_flags_requires.py` + regenerar `harness_defaults.env` por script
- **SBASE** (toda capa) = `compileall` + `npx tsc --noEmit`

| Capa | (a) Suite propia | (b) Regresión compuesta (acumulada, literal) | (c) Gates anti-duplicado específicos | (d) Smoke sandbox |
|---|---|---|---|---|
| 1 (183) | S183 | SFLAGS + SBASE + `test_plan122_dbcompare_registry.py`, `test_plan122_dbcompare_api.py`, `test_plan122_dbcompare_snapshot.py`, `test_plan123_dbcompare_runs.py`, `test_plan126_dbcompare_data_diff.py` (perímetro 183 F6) | endpoints: `grep -c "export const DbCompareDemo"` == 1; DbComparePage: orden §2.1 | seed → comparar par demo → diff rico en pantalla → quitar demo → re-seed |
| 2 (179) | S179 | S183 + SFLAGS + SBASE | `git diff` de `tests/` = SOLO los 2 nuevos + las 2 líneas declaradas | seed → snapshot de `test-demo-dev` → JSON con `type_detail` (`MONTO_TOPE` precision 10, scale 2) |
| 3 (182) | S182 | S183 + S179 + SFLAGS + SBASE | grep de firma: `grep -n "data_merge_mode" services/dbcompare_scripts.py` == firma + caller | seed → data-diff `RPARAM` → generar scripts → `03_datos/` con upsert sqlite de 1 línea por fila |
| 4 (157) | S157 | S183 + S179 + S182 + SFLAGS + SBASE | endpoints: `grep -c "export const DbCompare = "` == 1 (namespace extendido, no duplicado); DbComparePage: orden §2.1 con bloques 4 y 9 | flujo entrada: panel arriba + CTA; sandbox convive (bloques 3 y 4 adyacentes verificados a ojo) |
| 5 (176) | S176 (fijada post-crítica) | S183 + S179 + S182 + S157 + SFLAGS + SBASE | `create_run`: kwargs del 176 presentes 1 vez; `generate_parity_bundle_from_diff`: `excluded_keys` Y `data_merge_mode` en la MISMA firma (grep); endpoints: namespace único; DbComparePage orden §2.1 con bloque 8 | seed → comparar → triage de los ítems demo → excluir 1 → regenerar scripts → el excluido no está |
| 6 (181) | S181 | S183 + S179 + S182 + S157 + S176 + SFLAGS + SBASE | endpoints: `grep -c "export const DbCompareMasking"` == 1; `dbcompare_runs.py:227`-zona: `grep -n "data_diff" services/dbcompare_runs.py` muestra el filtro 1 vez | seed → data-diff `RCREDENCIAL` → grid enmascarado → revelar 1 click |
| 7 (178) | S178 | S183 + S179 + S182 + S157 + S176 + S181 + SFLAGS + SBASE | `create_run`: firma con kwargs de 176 Y `initiated_by` combinados (grep 1 ocurrencia de cada uno); endpoints: `grep -c "export const DbCompareWatch"` == 1 | seed → 2-3 compares demo → matriz con el par en rojo → pin baseline → tendencia |
| 8 (180) | S180 | S183 + S179 + S182 + S157 + S176 + S181 + S178 + SFLAGS + SBASE (= SUITE COMPUESTA FINAL) | endpoints: los 4 objetos nuevos con `grep -c` == 1 cada uno + namespace único | workspace de prueba con 1 `.sql` ticketeado → cobertura del diff demo con candidato |

---

## §5. Reglas para el implementador (especialmente modelos menores)

1. **1 capa = 1 rama = 1 sesión** de `/implementar-plan-stacky`, con DOS documentos a la vista: el doc v2 del plan de la capa y ESTE 184. PROHIBIDO implementar 2 capas en la misma rama o sesión.
2. El doc del plan manda sobre el QUÉ; el 184 manda sobre el DÓNDE (anclas §2) y el CUÁNDO (orden §3). Ante conflicto doc-vs-184 en una zona compartida: parar y reportar (no resolver creativamente).
3. Los números de línea de los docs son evidencia, NO anclas: insertar por símbolo (§2, regla transversal).
4. El merge a la rama de integración SIEMPRE ejecuta el gate (c) de su capa ANTES de commitear el merge (gotcha real del repo: el 3-way merge de git NO marca conflicto cuando dos ramas agregan la misma línea de cierre — el duplicado es SILENCIOSO y solo lo cazan `compileall`/`tsc`/grep).
5. Si CUALQUIER gate falla: PARAR y reportar con el output pegado. PROHIBIDO "arreglar" el plan de otra capa, aflojar un assert, editar un test preexistente no declarado, o saltear un gate para avanzar.
6. Capa 5 (176): NO abrir la rama hasta que el 176 tenga v2 de `/criticar-y-mejorar-plan` Y este 184 esté re-verificado contra esa v2 (§3, precondición dura).
7. Al terminar la capa: actualizar el encabezado de estado del doc del plan implementado (regla de la casa) y dejar el resultado de los gates en el PR.

---

## KPIs binarios del 184

| KPI | Criterio binario | Verificación |
|---|---|---|
| KPI-1 | El mapa §2 cubre el 100% de los archivos que ≥2 planes declaran EDITAR: cada archivo del superset del comando §2 tiene fila con veredicto (editan-quiénes o mención-sin-edición) y cita doc:línea | releer §2 contra el comando citado |
| KPI-2 | El orden §3 no tiene dependencias hacia adelante: toda precondición de la capa K referencia capas < K (o precondiciones externas explícitas: keyring, crítica del 176) | leer la columna Precondiciones |
| KPI-3 | Cada capa tiene su regresión compuesta ACUMULADA con listas LITERALES (S183…S180 enumeradas; la única lista diferida es S176, fijada en el gate de su propia capa con justificación) | leer §4 |
| KPI-4 | El gate "176 sin criticar" está declarado como precondición DURA de la capa 5 (no recomendación) | §3 fila 5 + §5 regla 6 |
| KPI-5 | Toda capa que toca un archivo compartido (§2.1-§2.9) tiene gate anti-duplicado-silencioso específico en §4(c) | cruzar §2 con §4 |
| KPI-6 | Cero anclas por número de línea en las reglas de merge: todas las inserciones de §2 se definen por símbolo | releer §2 |

---

## Riesgos y mitigaciones

| # | Riesgo | Impacto | Mitigación |
|---|---|---|---|
| R1 | La crítica del 176 (capa 5) cambia sus zonas/archivos | El mapa §2 queda parcialmente stale | Precondición dura: re-verificar §2 contra el 176 v2 ANTES de abrir la capa 5; S176 se fija recién ahí (KPI-3/KPI-4) |
| R2 | La sesión paralela implementa o renumera algo del portafolio por su cuenta | Tabla §1 desactualizada; colisiones nuevas | Precondición global §3: re-listar `docs/` + `git status`/`log` EN FRÍO al abrir CADA capa; si difiere, actualizar el 184 primero (precedente real: colisión del número 171) |
| R3 | Drift de números de línea entre los docs y main al momento de implementar | Hunks mal colocados por modelos menores | Regla transversal §2: anclar por SÍMBOLO; los números son evidencia histórica. §5 regla 3 |
| R4 | Duplicado silencioso de merge en archivos de registro (flags/runners/endpoints) | Suite rota o conducta doble | Gotcha documentado del repo; gates §4(c) + §2.9 OBLIGATORIOS en cada capa; `compileall`+`tsc`+greps con conteo esperado |
| R5 | Fatiga de regresión (las capas tardías re-corren ~40 archivos) | Tentación de saltear gates | Los comandos son POR ARCHIVO (paralelizables y cortos); §5 regla 5 prohíbe saltear; la suite compuesta final es el DoD — no hay atajo |
| R6 | Dos capas abiertas en paralelo por impaciencia | Las colisiones §2 explotan en merges cruzados | §5 regla 1 (1 capa = 1 rama = 1 sesión) + orden §3 estrictamente secuencial |
| R7 | El 184 mismo queda stale tras cada capa | Guía desactualizada | El DoD de cada capa incluye actualizar el encabezado del doc implementado; el 184 solo se re-edita en las precondiciones R1/R2 (cambios de mapa), no por avance normal |

---

## Fuera de scope

- **Implementar cualquiera de las 8 capas**: lo hace `/implementar-plan-stacky` por capa, disparado por el operador (HITL).
- **Criticar el 176**: lo hace su propio juicio con `/criticar-y-mejorar-plan` (precondición de la capa 5, no tarea del 184).
- **Re-criticar los docs v2 ya juzgados**: sus contenidos mandan tal cual.
- **Crear flags, endpoints, código de producto o tests nuevos**: el 184 no agrega superficies de runtime — "Flag: N/A — hereda las de cada plan NN" aplica a TODAS sus fases/capas.
- **Automatizar la ejecución de la ruta** (pipeline que encadene capas sin operador): PROHIBIDO por HITL.

---

## Glosario

- **Capa**: un plan del portafolio en su posición del orden canónico §3.
- **Rama de integración**: la rama donde se van mergeando las capas en orden (main o la que el operador designe).
- **Gate (a)/(b)/(c)/(d)**: suite propia / regresión compuesta acumulada / anti-duplicado por archivo compartido / smoke vía sandbox (§4).
- **Ancla por símbolo**: punto de inserción definido por componente/función vecina (§2), inmune al drift de líneas.
- **Duplicado silencioso**: el gotcha real del repo — git 3-way merge fusiona sin conflicto dos adiciones de la misma línea de cierre.
- **SNNN**: la suite literal del plan NNN (§4).
- **Suite compuesta final**: la unión S183…S180 + SFLAGS + SBASE — el DoD del portafolio completo.

---

## DoD global del 184

1. Las 8 capas mergeadas EN EL ORDEN §3, cada una con sus gates (a)-(d) verdes y documentados en su PR.
2. La suite compuesta final (fila 8 de §4) verde POR ARCHIVO.
3. El orden vertical de `DbComparePage.tsx` coincide con §2.1 (verificación visual + tsc).
4. `create_run` y `generate_parity_bundle_from_diff` con sus firmas COMBINADAS (§2.4/§2.5) y los tests de todos los planes involucrados verdes.
5. `endpoints.ts` con los 4 objetos nuevos (1 ocurrencia cada uno) y el namespace `DbCompare` único y extendido.
6. Los 8 encabezados de estado de los docs actualizados a IMPLEMENTADO.
7. `harness_defaults.env` regenerado y consistente con las ~15 flags nuevas del portafolio.

---

## PERÍMETRO enumerado

### P.1 Superficies (= archivos compartidos)

Las §2.1-§2.10 SON el perímetro de superficies, cada una con dueños, zonas, citas y gate. Sello de cobertura: el comando del universo (§2) + KPI-1.

### P.2 Comportamientos (verbos prometidos)

| Verbo | Garantía | Sello |
|---|---|---|
| **Mergear** (cada capa) | guía por archivo (§2) + regla "el segundo combina" (§2.4/§2.5) + §5 regla 4 | gates §4(c) |
| **Re-verificar** (regresión) | listas acumuladas literales por capa | §4(b), KPI-3 |
| **Parar-si-falla** | regla dura §5.5 (reportar con output, no improvisar) | revisión del PR de la capa |
| **Smokear** (cada capa) | pasos de 1-3 líneas vía sandbox 183 | §4(d) |
| **Ordenar** (secuencia) | §3 sin dependencias hacia adelante | KPI-2 |

### P.3 Verbos IMPLÍCITOS (lo que el portafolio asume gratis)

| Verbo implícito | Dónde estaba escondido | Evidencia y resolución |
|---|---|---|
| **Criticar** el 176 antes de implementarlo | Su encabezado: PROPUESTO v1 (único sin juicio) | Precondición dura capa 5 (§3, KPI-4) |
| **Autenticar** (keyring) para el sandbox | 183 fix C1: el seed EXIGE `keyring_available()` y guarda password dummy (183:33,136,309-331) | Precondición capa 1: keyring disponible; si no, el seed falla con mensaje accionable (por diseño del 183) |
| **Actualizar** este 184 cuando el terreno cambie | R1/R2 | Precondiciones de capa 5 y global |
| **Re-listar en frío** docs y git al abrir cada capa | Sesión paralela activa (precedente 171) | Precondición global §3 |
| **Regenerar** `harness_defaults.env` por capa | Cada plan lo pide individualmente | Elevado a SFLAGS en TODAS las capas (§4) |
| **Apagar/encender** flags para byte-identidad | KPIs "OFF ⇒ idéntico" de cada plan | Cubierto por las suites propias S-NNN (sus tests OFF); el 184 no re-testea flags, re-CORRE esas suites |
| **Conectar** a BDs reales | NINGUNA capa lo requiere para sus gates (el sandbox es sqlite local; 180 usa filesystem) | Los smokes §4(d) corren sin credenciales reales — por eso la capa 1 va primera |

---

## Hallazgos de contradicciones entre docs (con citas y resolución)

- **H1 — La lista corta del 157 en cinco §2bis:** los docs 178/180/181/182/183 listan al 157 tocando SOLO 4 archivos (`EnvSetupWizard.tsx`, `CredentialWarningBanner.tsx`, `dbcompare_config_import.py`, `MigrationPanel.tsx` — p.ej. 181:62) y concluyen "intersección: NINGUNA" — pero el doc REAL del 157 también edita `api/db_compare.py` (157:221-230,256), `DbComparePage.tsx` (157:359-384) y `endpoints.ts` (157:284). Impacto: las intersecciones 157∩181 (api/db_compare.py) y 157∩{176,178,180,183} (DbComparePage/endpoints) EXISTEN — todas componibles por zonas disjuntas. Resolución: el mapa §2 de ESTE plan es la fuente canónica y las incluye; no hace falta re-editar los 5 docs (sus guías por archivo siguen siendo válidas).
- **H2 — CompareWizard ambiguo en el 157 vs claim del 183:** 157:362 ("El `CompareWizard` ya recibe `environments`; si hay <2, mostrar inline 'Necesitás al menos 2 ambientes'…") no dice DÓNDE se implementa ese aviso, mientras el 183:64 afirma que NINGÚN otro plan declara tocar `CompareWizard.tsx`/`wizardLogic.ts`. Resolución canónica (§2.10): el aviso del 157 se implementa en `DbComparePage.tsx` (dueño del estado `environments`), `CompareWizard.tsx` queda propiedad exclusiva del 183 — el implementador de la capa 4 sigue esta regla.
- **H3 — Redundancia deliberada del 183 (nota, no contradicción):** el 183 v2 agrega la password dummy en keyring (fix C1, 183:136) Y conserva los 5 microhunks del wizard "sqlite sin password" (183:120-123). Con la dummy, el fix del wizard ya no es condición NECESARIA para el demo — pero sigue siendo semánticamente correcto para cualquier ambiente sqlite futuro y el doc v2 lo mantiene: se implementa tal cual (el doc manda); anotado para que el implementador no lo "optimice" por su cuenta.

---

**Changelog interno:** v1 (2026-07-18) — propuesta inicial.
Auto-consistencia KPI↔spec verificada: KPI-1↔el universo de §2 sale del comando citado (superset por menciones) y CADA candidato tiene fila con veredicto tocar-vs-mencionar respaldado por las tablas §2bis reales (incluida la corrección H1, que AMPLÍA el universo en vez de confiar en las listas cortas heredadas); KPI-2↔la columna Precondiciones de §3 solo referencia capas anteriores o precondiciones EXTERNAS explícitas (keyring, crítica del 176) — no hay referencia a capas 6-8 desde capas 1-5; KPI-3↔las listas S183…S180 están enumeradas archivo por archivo y la ÚNICA diferida (S176) tiene justificación estructural (su doc aún no tiene v2) y momento de fijación declarado (gate capa 5) — no es un "las anteriores" encubierto; KPI-4↔la precondición del 176 aparece DOS veces (fila 5 de §3 y regla 6 de §5) como bloqueo, no como sugerencia; KPI-5↔cada archivo de §2.1-§2.9 aparece en la columna (c) de §4 en TODAS las capas que lo tocan (cruce verificado fila por fila al redactar); KPI-6↔las anclas de §2 son símbolos (componentes/funciones) y la regla transversal degrada explícitamente los números de línea a evidencia; P.3↔cada verbo implícito tiene evidencia doc:línea u origen (gotcha/precedente) y una resolución operativa dentro del propio 184.
